import {
  expect,
  type Page,
  type Request,
  type Response,
  type Route,
  type TestInfo,
} from "@playwright/test";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { constants } from "node:fs";
import { access, open, readFile, unlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { operationMetadata } from "../src/api/generated/operations";
import validators from "../src/api/generated/validators.cjs";
import type { ApiOperationId } from "../src/api/generated/operations";
import type { ApiOperationBody } from "../src/api/client";

export type DebuggingWorkflow = "S" | "C" | "G" | "R";

export const WORKFLOW_TITLES: Record<DebuggingWorkflow, string> = {
  S: "installed saved answers retain frozen evidence",
  C: "installed comparison preserves both saved contexts",
  G: "installed groups retain snapshots and frozen regression inputs",
  R: "installed reports preserve exact protected downloads",
};

const WORKFLOW_TIMEOUT_MS: Record<DebuggingWorkflow, number> = {
  S: 120_000,
  C: 240_000,
  G: 540_000,
  R: 180_000,
};

const BODY_TIMEOUT_MS = 12_000;

export type SeedMetadata = {
  workflow: DebuggingWorkflow;
  run_id: string;
  evaluation_id: string;
  evaluation_content_hash: string;
  result_snapshot_id: string;
  label_snapshot_id: string;
  decision_id: string;
  dataset_id: string;
  fixture_set_id: string;
  original_fixture_set_id: string;
  imported_selected_count: number;
  imported_fixture_calls: number;
  preparation_dispatch_calls: number;
  prepared_binding_count: number;
  original_records_unchanged: true;
  execution_records_unchanged: true;
  original_order: readonly string[];
  min_seed_alternate: readonly string[];
  max_seed_alternate: readonly string[];
};

export type SafeProgress = {
  qualification_scope: "M12 installed debugging workflow";
  workflow: DebuggingWorkflow;
  active_phase: string;
  completed_phases: string[];
  phases: Array<{
    id: string;
    status: "active" | "complete";
    elapsed_ms: number;
  }>;
  screenshots: string[];
  api_failures: Array<{
    route_pattern: string;
    method: string;
    status: number;
    code: string | null;
    reason: string | null;
  }>;
  pending_reads: Record<string, number>;
  fixture_calls: {
    fixture_dispatch_calls: number;
    for_case_calls: number;
    live_dispatch_calls: number;
  };
  equality: Record<string, boolean>;
  timings_ms: Record<string, number>;
  witnesses: Record<string, string | number | boolean | null>;
};

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value)
    throw new Error(`Missing installed qualification environment: ${name}`);
  return value;
}

function safeIdentifier(value: unknown): string | null {
  return typeof value === "string" && /^[a-z][a-z0-9_]{0,99}$/.test(value)
    ? value
    : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSafeId(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
}

function isStringIdList(value: unknown, length: number): value is string[] {
  return (
    Array.isArray(value) &&
    value.length === length &&
    value.every(isSafeId) &&
    new Set(value).size === length
  );
}

function isSeedMetadata(value: unknown): value is SeedMetadata {
  if (!isRecord(value)) return false;
  return (
    (value.workflow === "S" ||
      value.workflow === "C" ||
      value.workflow === "G" ||
      value.workflow === "R") &&
    isSafeId(value.run_id) &&
    isSafeId(value.evaluation_id) &&
    isSafeId(value.result_snapshot_id) &&
    isSafeId(value.label_snapshot_id) &&
    isSafeId(value.decision_id) &&
    isSafeId(value.dataset_id) &&
    isSafeId(value.fixture_set_id) &&
    isSafeId(value.original_fixture_set_id) &&
    typeof value.evaluation_content_hash === "string" &&
    /^[a-f0-9]{64}$/.test(value.evaluation_content_hash) &&
    Number.isSafeInteger(value.imported_selected_count) &&
    value.imported_selected_count === 12 &&
    Number.isSafeInteger(value.imported_fixture_calls) &&
    value.imported_fixture_calls === 11 &&
    Number.isSafeInteger(value.preparation_dispatch_calls) &&
    value.preparation_dispatch_calls === 0 &&
    Number.isSafeInteger(value.prepared_binding_count) &&
    (value.prepared_binding_count as number) >= 0 &&
    value.original_records_unchanged === true &&
    value.execution_records_unchanged === true &&
    isStringIdList(value.original_order, 4) &&
    isStringIdList(value.min_seed_alternate, 4) &&
    isStringIdList(value.max_seed_alternate, 4)
  );
}

export function routeTemplate(pathname: string): string {
  const actual = pathname.split("/");
  const match = Object.values(operationMetadata)
    .map(({ path }) => path.split("/"))
    .find(
      (template) =>
        template.length === actual.length &&
        template.every((segment, index) =>
          /^\{[a-z_]+\}$/.test(segment)
            ? actual[index] !== ""
            : actual[index] === segment,
        ),
    );
  return match
    ? match
        .map((segment) =>
          /^\{[a-z_]+\}$/.test(segment) ? `:${segment.slice(1, -1)}` : segment,
        )
        .join("/")
    : "<unknown-route>";
}

export class DebuggingQualification {
  readonly workflow: DebuggingWorkflow;
  readonly projectPath: string;
  readonly secondaryProjectPath?: string;
  readonly seedMetadata: SeedMetadata;
  readonly controlDirectory: string;
  readonly installedPython: string;
  readonly workerPath: string;
  readonly sourceEvidencePath?: string;
  readonly progressPath: string;
  readonly startedAt = performance.now();
  readonly progress: SafeProgress;
  private readonly testInfo: TestInfo;
  private saveQueue: Promise<void> = Promise.resolve();

  private constructor(
    testInfo: TestInfo,
    workflow: DebuggingWorkflow,
    seedMetadata: SeedMetadata,
  ) {
    this.testInfo = testInfo;
    this.workflow = workflow;
    this.seedMetadata = seedMetadata;
    this.projectPath = requiredEnvironment("DEYKIT_DEBUGGING_PROJECT");
    this.secondaryProjectPath = process.env.DEYKIT_DEBUGGING_SECONDARY_PROJECT;
    this.controlDirectory = requiredEnvironment(
      "DEYKIT_FIXTURE_CONTROL_DIRECTORY",
    );
    this.installedPython = requiredEnvironment("DEYKIT_INSTALLED_PYTHON");
    this.workerPath = requiredEnvironment("DEYKIT_INSTALLED_PROJECT_WORKER");
    this.sourceEvidencePath = process.env.DEYKIT_DEBUGGING_G_SOURCE_EVIDENCE;
    this.progressPath = testInfo.outputPath("debugging-progress.json");
    this.progress = {
      qualification_scope: "M12 installed debugging workflow",
      workflow,
      active_phase: "preflight",
      completed_phases: [],
      phases: [{ id: "preflight", status: "active", elapsed_ms: 0 }],
      screenshots: [],
      api_failures: [],
      pending_reads: {},
      fixture_calls: {
        fixture_dispatch_calls: 0,
        for_case_calls: 0,
        live_dispatch_calls: 0,
      },
      equality: {},
      timings_ms: {},
      witnesses: {},
    };
  }

  static async create(testInfo: TestInfo): Promise<DebuggingQualification> {
    const workflowValue = requiredEnvironment("DEYKIT_DEBUGGING_WORKFLOW");
    if (!(
      workflowValue === "S" ||
      workflowValue === "C" ||
      workflowValue === "G" ||
      workflowValue === "R"
    ))
      throw new Error("Installed qualification workflow is invalid.");
    const raw = await readFile(
      requiredEnvironment("DEYKIT_DEBUGGING_SEED_METADATA"),
      "utf8",
    );
    const parsed: unknown = JSON.parse(raw);
    if (!isSeedMetadata(parsed))
      throw new Error("Installed seed metadata is malformed.");
    const metadata = parsed;
    if (
      metadata.workflow !== workflowValue ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.run_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.evaluation_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.result_snapshot_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.label_snapshot_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.decision_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.dataset_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.fixture_set_id) ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(metadata.original_fixture_set_id) ||
      !/^[a-f0-9]{64}$/.test(metadata.evaluation_content_hash) ||
      metadata.original_records_unchanged !== true ||
      metadata.execution_records_unchanged !== true ||
      metadata.preparation_dispatch_calls !== 0 ||
      metadata.imported_fixture_calls !== 11 ||
      metadata.imported_selected_count !== 12 ||
      !Number.isSafeInteger(metadata.prepared_binding_count) ||
      metadata.prepared_binding_count < 0 ||
      !Array.isArray(metadata.original_order) ||
      metadata.original_order.length !== 4 ||
      new Set(metadata.original_order).size !== 4 ||
      !Array.isArray(metadata.min_seed_alternate) ||
      metadata.min_seed_alternate.length !== 4 ||
      new Set(metadata.min_seed_alternate).size !== 4 ||
      !Array.isArray(metadata.max_seed_alternate) ||
      metadata.max_seed_alternate.length !== 4 ||
      new Set(metadata.max_seed_alternate).size !== 4 ||
      (workflowValue === "S" && metadata.prepared_binding_count !== 0) ||
      (workflowValue === "C" && metadata.prepared_binding_count === 0) ||
      (workflowValue === "G" && metadata.prepared_binding_count !== 4) ||
      (workflowValue === "R" &&
        (!process.env.DEYKIT_DEBUGGING_SECONDARY_PROJECT ||
          !process.env.DEYKIT_DEBUGGING_G_SOURCE_EVIDENCE))
    )
      throw new Error("Installed seed metadata failed qualification checks.");
    return new DebuggingQualification(testInfo, workflowValue, metadata);
  }

  async configure(): Promise<void> {
    this.testInfo.setTimeout(WORKFLOW_TIMEOUT_MS[this.workflow]);
    this.progress.active_phase = "project-open";
    this.progress.phases[0] = {
      id: "project-open",
      status: "active",
      elapsed_ms: 0,
    };
    await this.save();
  }

  async enterPhase(id: string): Promise<void> {
    if (!/^[a-z][a-z0-9-]{0,79}$/.test(id))
      throw new Error("Qualification phase name is invalid.");
    const current = this.progress.phases.find(
      (phase) => phase.id === this.progress.active_phase,
    );
    if (current) current.status = "complete";
    if (!this.progress.completed_phases.includes(this.progress.active_phase))
      this.progress.completed_phases.push(this.progress.active_phase);
    this.progress.active_phase = id;
    this.progress.phases.push({
      id,
      status: "active",
      elapsed_ms: this.elapsedMs(),
    });
    await this.save();
  }

  elapsedMs(): number {
    return Math.max(0, Math.round(performance.now() - this.startedAt));
  }

  setCounts(counts: SafeProgress["fixture_calls"]): void {
    this.progress.fixture_calls = counts;
  }

  setEquality(name: string, value: boolean): void {
    if (!/^[a-z][a-z0-9_]{0,79}$/.test(name))
      throw new Error("Qualification equality name is invalid.");
    this.progress.equality[name] = value;
  }

  setWitness(name: string, value: string | number | boolean | null): void {
    if (!/^[a-z][a-z0-9_]{0,79}$/.test(name))
      throw new Error("Qualification witness name is invalid.");
    if (typeof value === "string" && !/^[A-Za-z0-9_.:-]{1,256}$/.test(value))
      throw new Error(
        "Qualification witness value is not a safe identifier or hash.",
      );
    this.progress.witnesses[name] = value;
  }

  async captureScreenshot(page: Page, name: string): Promise<void> {
    if (!/^[a-z0-9-]{1,80}\.png$/.test(name))
      throw new Error("Screenshot name is invalid.");
    const path = this.testInfo.outputPath(name);
    await page.screenshot({ path, fullPage: true });
    await this.testInfo.attach(name, { path, contentType: "image/png" });
    if (!this.progress.screenshots.includes(name))
      this.progress.screenshots.push(name);
    await this.save();
  }

  async observeFailure(response: Response): Promise<void> {
    if (response.status() < 400) return;
    let code: string | null = null;
    let reason: string | null = null;
    try {
      const body: unknown = await response.json();
      const error =
        isRecord(body) && isRecord(body.error) ? body.error : undefined;
      code = safeIdentifier(error?.code);
      reason = safeIdentifier(error?.reason);
    } catch {
      // Preserve only status and route for non-JSON failures.
    }
    this.progress.api_failures.push({
      route_pattern: routeTemplate(new URL(response.url()).pathname),
      method: response.request().method(),
      status: response.status(),
      code,
      reason,
    });
    await this.save();
  }

  setPendingReads(values: Record<string, number>): void {
    this.progress.pending_reads = values;
  }

  async save(): Promise<void> {
    const active = this.progress.phases.find(
      (phase) => phase.id === this.progress.active_phase,
    );
    if (active) active.elapsed_ms = this.elapsedMs();
    const snapshot = `${JSON.stringify(this.progress, null, 2)}\n`;
    this.saveQueue = this.saveQueue.then(async () => {
      await writeFile(this.progressPath, snapshot, { mode: 0o600 });
    });
    await this.saveQueue;
  }

  async complete(): Promise<void> {
    const current = this.progress.phases.find(
      (phase) => phase.id === this.progress.active_phase,
    );
    if (current) current.status = "complete";
    if (!this.progress.completed_phases.includes(this.progress.active_phase))
      this.progress.completed_phases.push(this.progress.active_phase);
    this.progress.active_phase = "complete";
    this.progress.phases.push({
      id: "complete",
      status: "complete",
      elapsed_ms: this.elapsedMs(),
    });
    await this.save();
  }
}

export async function startDebuggingQualification(
  page: Page,
  testInfo: TestInfo,
  workflow: DebuggingWorkflow,
): Promise<{
  qualification: DebuggingQualification;
  registrationId: string;
  reads: BrowserReadTracker;
}> {
  const qualification = await DebuggingQualification.create(testInfo);
  if (qualification.workflow !== workflow)
    throw new Error("The installed driver selected a different workflow.");
  await qualification.configure();
  page.setDefaultTimeout(12_000);
  const apiURL = requiredEnvironment("DEYKIT_INSTALLED_API_URL");
  const reads = new BrowserReadTracker(page, qualification, apiURL);
  try {
    const opened = await openPreparedProject(page, qualification.projectPath);
    qualification.setWitness("registration_id", opened.registrationId);
    await qualification.save();
    return { qualification, registrationId: opened.registrationId, reads };
  } catch (cause) {
    await reads.dispose().catch(() => undefined);
    throw cause;
  }
}

export async function finishDebuggingQualification(
  qualification: DebuggingQualification,
  reads: BrowserReadTracker,
  succeeded: boolean,
): Promise<void> {
  let disposed = false;
  try {
    await reads.dispose();
    disposed = true;
  } catch (cause) {
    if (succeeded) throw cause;
    qualification.setWitness("read_disposal_failure", "failed");
    await qualification.save();
    return;
  }
  if (succeeded && disposed) await qualification.complete();
  else await qualification.save();
}

export async function captureResponse(
  page: Page,
  predicate: (response: Response) => boolean,
  action: () => Promise<void>,
  timeoutMs = BODY_TIMEOUT_MS,
): Promise<{ response: Response; body: Buffer }> {
  const responsePromise = page.waitForResponse(predicate, {
    timeout: timeoutMs,
  });
  void responsePromise.catch(() => undefined);
  await action();
  const response = await responsePromise;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const body = await Promise.race([
      response.body(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("An installed response body did not settle.")),
          timeoutMs,
        );
      }),
    ]);
    return { response, body };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export async function captureOperation(
  page: Page,
  operation: ApiOperationId,
  pathParameters: Record<string, string>,
  action: () => Promise<void>,
  queryMatches: (query: URLSearchParams) => boolean = () => true,
  timeoutMs = BODY_TIMEOUT_MS,
): Promise<{ response: Response; body: Buffer }> {
  const metadata = operationMetadata[operation];
  const expectedPath = metadata.path.replace(
    /\{([a-z_]+)\}/g,
    (_whole, name: string) => {
      const value = pathParameters[name];
      if (!value)
        throw new Error("An installed operation path parameter is missing.");
      return encodeURIComponent(value);
    },
  );
  const captured = await captureResponse(
    page,
    (response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === metadata.method &&
        url.pathname === expectedPath &&
        queryMatches(url.searchParams)
      );
    },
    action,
    timeoutMs,
  );
  return captured;
}

export async function captureNextProgressAndSnapshots(
  page: Page,
  registrationId: string,
  groupId: string,
  timeoutMs = BODY_TIMEOUT_MS,
): Promise<{
  progress: { response: Response; body: Buffer };
  snapshots: { response: Response; body: Buffer };
}> {
  type Operation = "readChoiceOrder" | "listChoiceOrderSnapshots";
  type Captured = { response: Response; body: Buffer };
  type Deferred<T> = {
    promise: Promise<T>;
    resolve: (value: T) => void;
    reject: (reason: Error) => void;
  };
  type OperationCapture = Deferred<Captured> & {
    request?: Request;
    seenResponse: boolean;
    headerTimer?: ReturnType<typeof setTimeout>;
    bodyTimer?: ReturnType<typeof setTimeout>;
  };
  const operations: readonly Operation[] = [
    "readChoiceOrder",
    "listChoiceOrderSnapshots",
  ];
  const deadline = performance.now() + timeoutMs;
  const remaining = () => Math.max(1, Math.floor(deadline - performance.now()));
  const deferred = <T>(): Deferred<T> => {
    let resolve!: (value: T) => void;
    let reject!: (reason: Error) => void;
    const promise = new Promise<T>((complete, fail) => {
      resolve = complete;
      reject = fail;
    });
    return { promise, resolve, reject };
  };
  const captures = new Map<Operation, OperationCapture>();
  for (const operation of operations) {
    captures.set(operation, {
      ...deferred<Captured>(),
      seenResponse: false,
    });
  }
  const capturesPromise = Promise.all(
    operations.map((operation) => captures.get(operation)!.promise),
  );
  void capturesPromise.catch(() => undefined);
  const requestOperations = new Map<Request, Operation>();
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const addTimer = (callback: () => void, timeout: number) => {
    let timer: ReturnType<typeof setTimeout>;
    timer = setTimeout(
      () => {
        timers.delete(timer);
        callback();
      },
      Math.max(1, timeout),
    );
    timers.add(timer);
    return timer;
  };
  const clearTimer = (timer: ReturnType<typeof setTimeout> | undefined) => {
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.delete(timer);
    }
  };
  let overallReject!: (reason: Error) => void;
  const overallFailure = new Promise<never>((_resolve, reject) => {
    overallReject = reject;
  });
  const overallTimer = addTimer(
    () =>
      overallReject(
        new Error(
          "The next progress and snapshot reads exceeded their bounded window.",
        ),
      ),
    remaining(),
  );
  const matches = (request: Request, operation: Operation): boolean => {
    const metadata = operationMetadata[operation];
    const expectedPath = metadata.path.replace(
      /\{([a-z_]+)\}/g,
      (_whole, name: string) => {
        const value =
          name === "registration_id"
            ? registrationId
            : name === "group_id"
              ? groupId
              : undefined;
        if (!value)
          throw new Error("A next-read observer path parameter is missing.");
        return encodeURIComponent(value);
      },
    );
    try {
      return (
        request.method() === metadata.method &&
        new URL(request.url()).pathname === expectedPath
      );
    } catch {
      return false;
    }
  };
  const onRequest = (request: Request) => {
    const progress = captures.get("readChoiceOrder")!;
    const snapshots = captures.get("listChoiceOrderSnapshots")!;
    if (!progress.request && matches(request, "readChoiceOrder")) {
      progress.request = request;
      requestOperations.set(request, "readChoiceOrder");
      progress.headerTimer = addTimer(
        () => {
          progress.seenResponse = true;
          progress.reject(
            new Error("The first progress response headers timed out."),
          );
        },
        Math.min(remaining(), BODY_TIMEOUT_MS),
      );
      return;
    }
    if (
      progress.request &&
      !snapshots.request &&
      matches(request, "listChoiceOrderSnapshots")
    ) {
      snapshots.request = request;
      requestOperations.set(request, "listChoiceOrderSnapshots");
      snapshots.headerTimer = addTimer(
        () => {
          snapshots.seenResponse = true;
          snapshots.reject(
            new Error("The first snapshot-list response headers timed out."),
          );
        },
        Math.min(remaining(), BODY_TIMEOUT_MS),
      );
    }
  };
  const onResponse = (response: Response) => {
    const request = response.request();
    const operation = requestOperations.get(request);
    if (!operation) return;
    const capture = captures.get(operation)!;
    if (capture.seenResponse) return;
    capture.seenResponse = true;
    clearTimer(capture.headerTimer);
    capture.headerTimer = undefined;
    capture.bodyTimer = addTimer(
      () =>
        capture.reject(
          new Error("The first progress or snapshot response body timed out."),
        ),
      Math.min(remaining(), BODY_TIMEOUT_MS),
    );
    void response.body().then(
      (body) => {
        if (capture.bodyTimer === undefined) return;
        clearTimer(capture.bodyTimer);
        capture.bodyTimer = undefined;
        capture.resolve({ response, body });
      },
      () => {
        if (capture.bodyTimer === undefined) return;
        clearTimer(capture.bodyTimer);
        capture.bodyTimer = undefined;
        capture.reject(
          new Error("The first progress or snapshot response body failed."),
        );
      },
    );
  };
  const onRequestFailed = (request: Request) => {
    const operation = requestOperations.get(request);
    if (!operation) return;
    const capture = captures.get(operation)!;
    if (capture.seenResponse) return;
    capture.seenResponse = true;
    clearTimer(capture.headerTimer);
    capture.headerTimer = undefined;
    capture.reject(new Error("The first progress or snapshot request failed."));
  };

  try {
    page.on("request", onRequest);
    page.on("response", onResponse);
    page.on("requestfailed", onRequestFailed);
    const [progress, snapshots] = await Promise.race([
      capturesPromise,
      overallFailure,
    ]);
    clearTimer(overallTimer);
    const [progressResponse, snapshotsResponse] = [
      progress.response,
      snapshots.response,
    ];
    return {
      progress: { response: progressResponse, body: progress.body },
      snapshots: { response: snapshotsResponse, body: snapshots.body },
    };
  } finally {
    clearTimer(overallTimer);
    for (const timer of timers) clearTimeout(timer);
    timers.clear();
    page.off("request", onRequest);
    page.off("response", onResponse);
    page.off("requestfailed", onRequestFailed);
  }
}

export type LostAcknowledgement = {
  firstStatus: number;
  replayStatus: number;
  firstRequestHash: string;
  replayRequestHash: string;
  firstResponseHash: string;
  replayResponseHash: string;
  sameRequestBytes: boolean;
  firstRequestBody: Buffer;
  firstResponseBody: Buffer;
  replayResponseBody: Buffer;
};

export type FirstAcknowledgement = {
  firstStatus: number;
  firstRequestHash: string;
  firstResponseHash: string;
  firstRequestBody: Buffer;
  firstResponseBody: Buffer;
};

type LostAcknowledgementTraceStage =
  | "observer_armed"
  | "resume_click_begin"
  | "resume_click_complete"
  | "first_receipt_decoded"
  | "replay_capture_complete"
  | "route_entered"
  | "request_hashed"
  | "upstream_fetch_started"
  | "upstream_headers_received"
  | "upstream_body_completed"
  | "abort_started"
  | "abort_completed"
  | "fulfill_started"
  | "fulfill_completed"
  | "route_exited"
  | "route_failed";

type LostAcknowledgementTraceFailure =
  | "request_body_missing"
  | "upstream_fetch_failed"
  | "upstream_body_failed"
  | "abort_failed"
  | "fulfill_failed"
  | "route_continue_failed";

type ServerResumeTraceStage = "admitted" | "response_started" | "body_complete";

type ServerResumeTrace = {
  schema_version: 1;
  events: Array<{
    ordinal: 1 | 2;
    stage: ServerResumeTraceStage;
    elapsed_ms: number;
    status?: number;
    sha256?: string;
  }>;
};

export type LostAcknowledgementTrace = {
  schema_version: 1;
  events: Array<{
    stage: LostAcknowledgementTraceStage;
    elapsed_ms: number;
    ordinal?: 1 | 2;
    status?: number;
    sha256?: string;
    failure?: LostAcknowledgementTraceFailure;
  }>;
};

export type ExpectedCreateReportRequest = {
  targetKind: "run" | "evaluation" | "comparison" | "diagnostic" | "check";
  targetId: string;
  raw: { inputs: boolean; requests: boolean; responses: boolean };
  evaluationId?: string;
  resultSnapshotId?: string;
  groupSnapshotId?: string;
};

export function assertCreateReportRequestBody(
  bytes: Uint8Array,
  expected: ExpectedCreateReportRequest,
): ApiOperationBody<"createReport"> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(bytes).toString("utf8"));
  } catch {
    throw new Error("The captured report request was not valid JSON.");
  }
  if (!isRecord(parsed))
    throw new Error("The captured report request was not an object.");
  const body = parsed as ApiOperationBody<"createReport">;
  const expectedKeys = [
    "operation_id",
    "raw",
    "schema_version",
    "target_id",
    "target_kind",
  ];
  if (expected.evaluationId !== undefined) expectedKeys.push("evaluation_id");
  if (expected.resultSnapshotId !== undefined)
    expectedKeys.push("result_snapshot_id");
  if (expected.groupSnapshotId !== undefined)
    expectedKeys.push("group_snapshot_id");
  expect(Object.keys(parsed).sort()).toEqual(expectedKeys.sort());
  expect(body.schema_version).toBe(1);
  expect(body.operation_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  expect(body.target_kind).toBe(expected.targetKind);
  expect(body.target_id).toBe(expected.targetId);
  expect(body.raw).toEqual(expected.raw);
  expect(Object.keys(body.raw ?? {}).sort()).toEqual([
    "inputs",
    "requests",
    "responses",
  ]);
  expect(body.evaluation_id).toBe(expected.evaluationId);
  expect(body.result_snapshot_id).toBe(expected.resultSnapshotId);
  expect(body.group_snapshot_id).toBe(expected.groupSnapshotId);
  return body;
}

export function installLostAcknowledgement(
  page: Page,
  path: string,
  expectedSuccessStatus: number,
): Promise<{
  observation: () => LostAcknowledgement | undefined;
  firstObservation: () => FirstAcknowledgement | undefined;
  mark: (
    stage: Extract<
      LostAcknowledgementTraceStage,
      | "observer_armed"
      | "resume_click_begin"
      | "resume_click_complete"
      | "first_receipt_decoded"
      | "replay_capture_complete"
    >,
  ) => void;
  trace: () => LostAcknowledgementTrace;
  dispose: () => Promise<void>;
}> {
  let first: { status: number; request: Buffer; response: Buffer } | undefined;
  let replay: { status: number; request: Buffer; response: Buffer } | undefined;
  const traceStartedAt = performance.now();
  const traceEvents: LostAcknowledgementTrace["events"] = [];
  let interceptedOrdinal = 0;
  const record = (
    stage: LostAcknowledgementTraceStage,
    ordinal?: 1 | 2,
    detail?: {
      status?: number;
      sha256?: string;
      failure?: LostAcknowledgementTraceFailure;
    },
  ) => {
    if (traceEvents.length >= 32) return;
    traceEvents.push({
      stage,
      elapsed_ms: Math.max(0, Math.round(performance.now() - traceStartedAt)),
      ...(ordinal === undefined ? {} : { ordinal }),
      ...(detail?.status === undefined ? {} : { status: detail.status }),
      ...(detail?.sha256 === undefined ? {} : { sha256: detail.sha256 }),
      ...(detail?.failure === undefined ? {} : { failure: detail.failure }),
    });
  };
  const handler = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (
      request.method() !== "POST" ||
      url.pathname !== path ||
      (first && replay)
    ) {
      await route.continue();
      return;
    }
    if (interceptedOrdinal >= 2) {
      await route.continue();
      return;
    }
    const ordinal = ++interceptedOrdinal as 1 | 2;
    record("route_entered", ordinal);
    let failure: LostAcknowledgementTraceFailure = "request_body_missing";
    try {
      const requestBody = request.postDataBuffer();
      if (!requestBody)
        throw new Error("The retained API request body was unavailable.");
      record("request_hashed", ordinal, { sha256: bodySha256(requestBody) });
      failure = "upstream_fetch_failed";
      record("upstream_fetch_started", ordinal);
      const upstream = await route.fetch({ maxRetries: 0, maxRedirects: 0 });
      record("upstream_headers_received", ordinal, {
        status: upstream.status(),
      });
      failure = "upstream_body_failed";
      const responseBody = await upstream.body();
      record("upstream_body_completed", ordinal, {
        status: upstream.status(),
        sha256: bodySha256(responseBody),
      });
      if (!first) {
        first = {
          status: upstream.status(),
          request: requestBody,
          response: responseBody,
        };
        if (upstream.status() === expectedSuccessStatus) {
          failure = "abort_failed";
          record("abort_started", ordinal);
          await route.abort("failed");
          record("abort_completed", ordinal);
          record("route_exited", ordinal);
          return;
        }
        failure = "fulfill_failed";
        record("fulfill_started", ordinal);
        await route.fulfill({ response: upstream });
        record("fulfill_completed", ordinal);
        record("route_exited", ordinal);
        return;
      }

      replay = {
        status: upstream.status(),
        request: requestBody,
        response: responseBody,
      };
      record("fulfill_started", ordinal);
      await route.fulfill({ response: upstream });
      record("fulfill_completed", ordinal);
      record("route_exited", ordinal);
    } catch (cause) {
      record("route_failed", ordinal, { failure });
      throw cause;
    }
  };
  const pattern = `**${path}`;
  return page.route(pattern, handler).then(() => ({
    firstObservation() {
      if (!first) return undefined;
      return {
        firstStatus: first.status,
        firstRequestHash: bodySha256(first.request),
        firstResponseHash: bodySha256(first.response),
        firstRequestBody: first.request,
        firstResponseBody: first.response,
      };
    },
    observation() {
      if (!first || !replay) return undefined;
      return {
        firstStatus: first.status,
        replayStatus: replay.status,
        firstRequestHash: bodySha256(first.request),
        replayRequestHash: bodySha256(replay.request),
        firstResponseHash: bodySha256(first.response),
        replayResponseHash: bodySha256(replay.response),
        sameRequestBytes: Buffer.compare(first.request, replay.request) === 0,
        firstRequestBody: first.request,
        firstResponseBody: first.response,
        replayResponseBody: replay.response,
      };
    },
    mark(stage) {
      record(stage);
    },
    trace() {
      return {
        schema_version: 1,
        events: traceEvents.map((event) => ({ ...event })),
      };
    },
    async dispose() {
      await page.unroute(pattern, handler);
    },
  }));
}

export async function saveServerResumeTrace(
  controlDirectory: string,
  outputPath: string,
): Promise<"present" | "absent"> {
  const sourcePath = join(controlDirectory, "resume-observation.json");
  let source: string;
  try {
    source = await readFile(sourcePath, "utf8");
  } catch (cause) {
    if (isRecord(cause) && cause.code === "ENOENT") return "absent";
    throw cause;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(source);
  } catch {
    throw new Error("The server resume observation was malformed.");
  }
  if (!isRecord(parsed) || parsed.schema_version !== 1)
    throw new Error("The server resume observation was malformed.");
  const events = parsed.events;
  if (!Array.isArray(events) || events.length > 6)
    throw new Error("The server resume observation was malformed.");
  const safeStages = new Set<ServerResumeTraceStage>([
    "admitted",
    "response_started",
    "body_complete",
  ]);
  const safeEvents: ServerResumeTrace["events"] = [];
  for (const value of events) {
    if (
      !isRecord(value) ||
      (value.ordinal !== 1 && value.ordinal !== 2) ||
      typeof value.stage !== "string" ||
      !safeStages.has(value.stage as ServerResumeTraceStage) ||
      !Number.isSafeInteger(value.elapsed_ms) ||
      (value.elapsed_ms as number) < 0 ||
      (value.status !== undefined &&
        (!Number.isSafeInteger(value.status) ||
          (value.status as number) < 100 ||
          (value.status as number) > 599)) ||
      (value.sha256 !== undefined &&
        (typeof value.sha256 !== "string" ||
          !/^[a-f0-9]{64}$/.test(value.sha256)))
    )
      throw new Error("The server resume observation was malformed.");
    safeEvents.push({
      ordinal: value.ordinal,
      stage: value.stage as ServerResumeTraceStage,
      elapsed_ms: value.elapsed_ms as number,
      ...(value.status === undefined ? {} : { status: value.status as number }),
      ...(value.sha256 === undefined ? {} : { sha256: value.sha256 as string }),
    });
  }
  const safeTrace: ServerResumeTrace = {
    schema_version: 1,
    events: safeEvents,
  };
  await writeFile(outputPath, `${JSON.stringify(safeTrace, null, 2)}\n`, {
    flag: "wx",
    mode: 0o600,
  });
  return "present";
}

export function decodeJSONBody<T>(body: Uint8Array): T {
  return JSON.parse(Buffer.from(body).toString("utf8")) as T;
}

export function decodeSuccessEnvelope<T>(
  body: Uint8Array,
  expectedStatus: number,
  actualStatus: number,
): T {
  expect(actualStatus).toBe(expectedStatus);
  const envelope: unknown = decodeJSONBody(body);
  if (
    !isRecord(envelope) ||
    envelope.schema_version !== 1 ||
    !isRecord(envelope.data)
  )
    throw new Error("The installed API returned an invalid success envelope.");
  return envelope.data as T;
}

export function decodeSuccessListEnvelope<T>(
  body: Uint8Array,
  expectedStatus: number,
  actualStatus: number,
): T {
  expect(actualStatus).toBe(expectedStatus);
  const envelope: unknown = decodeJSONBody(body);
  if (
    !isRecord(envelope) ||
    envelope.schema_version !== 1 ||
    !Array.isArray(envelope.data) ||
    !envelope.data.every(isRecord)
  )
    throw new Error("The installed API returned an invalid list envelope.");
  return envelope.data as T;
}

export function requireSafeId(value: unknown, context: string): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value))
    throw new Error(`The installed ${context} identity is invalid.`);
  return value;
}

export function bodySha256(body: Uint8Array): string {
  return createHash("sha256").update(body).digest("hex");
}

export async function openPreparedProject(
  page: Page,
  projectPath: string,
): Promise<{ registrationId: string; registrationBody: unknown }> {
  const bootstrap = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/session/bootstrap",
    { timeout: BODY_TIMEOUT_MS },
  );
  await page.goto("/");
  const bootstrapResponse = await bootstrap;
  expect(bootstrapResponse.status()).toBe(200);
  const bootstrapBody: unknown = await bootstrapResponse.json();
  if (
    !isRecord(bootstrapBody) ||
    !isRecord(bootstrapBody.data) ||
    typeof bootstrapBody.data.capability !== "string"
  )
    throw new Error("The local project session was not initialized.");

  const registrationPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/projects/register",
    { timeout: BODY_TIMEOUT_MS },
  );
  await page.getByRole("button", { name: /^Open project/ }).click();
  const dialog = page.getByRole("dialog", {
    name: "Open project",
    exact: true,
  });
  await dialog.getByLabel("Project folder path").fill(projectPath);
  await dialog
    .getByRole("button", { name: "Open project", exact: true })
    .click();
  const registrationResponse = await registrationPromise;
  expect(registrationResponse.status()).toBe(200);
  const registrationBody: unknown = await registrationResponse.json();
  if (
    !isRecord(registrationBody) ||
    registrationBody.schema_version !== 1 ||
    !isRecord(registrationBody.data) ||
    !validators.validateRegistrationDTO(registrationBody.data)
  )
    throw new Error("The prepared project registration receipt was malformed.");
  const registrationId = registrationBody.data.registration_id;
  const project = registrationBody.data.project;
  if (
    typeof registrationId !== "string" ||
    !/^[A-Za-z0-9_-]{1,128}$/.test(registrationId) ||
    !isRecord(project) ||
    typeof project.name !== "string"
  )
    throw new Error("The prepared project registration receipt was malformed.");
  await expect(
    page.getByRole("heading", { name: project.name, exact: true }),
  ).toBeVisible();
  await registrationResponse.body();
  return { registrationId, registrationBody };
}

export async function waitForCountFile(
  controlDirectory: string,
  expected: (counts: FixtureCounts) => boolean,
  timeoutMs = 12_000,
): Promise<FixtureCounts> {
  const deadline = performance.now() + timeoutMs;
  while (performance.now() < deadline) {
    try {
      const raw = await readFile(`${controlDirectory}/counts.json`, "utf8");
      const value: unknown = JSON.parse(raw);
      const counts = parseFixtureCounts(value);
      if (counts && expected(counts)) return counts;
    } catch {
      // The worker publishes counts by atomic replacement; retry only this local witness read.
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(
    "The installed fixture-dispatch witness did not reach its bounded count.",
  );
}

export async function readFixtureCountsNow(
  controlDirectory: string,
): Promise<FixtureCounts | undefined> {
  let raw: string;
  try {
    raw = await readFile(join(controlDirectory, "counts.json"), "utf8");
  } catch (cause) {
    if (isRecord(cause) && cause.code === "ENOENT") return undefined;
    throw new Error("The fixture count witness could not be read.");
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("The fixture count witness was malformed.");
  }
  const counts = parseFixtureCounts(value);
  if (!counts) throw new Error("The fixture count witness was malformed.");
  return counts;
}

export type FixtureCounts = {
  fixture_dispatch_calls: number;
  for_case_calls: number;
  live_dispatch_calls: 0;
  fixture_dispatch_by_case: Record<string, number>;
  for_case_by_case: Record<string, number>;
};

function countMap(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) return undefined;
  const entries = Object.entries(value);
  if (
    entries.some(
      ([key, count]) =>
        !/^[A-Za-z0-9_-]{1,128}$/.test(key) ||
        !Number.isSafeInteger(count) ||
        (count as number) < 0,
    )
  )
    return undefined;
  return Object.fromEntries(entries) as Record<string, number>;
}

function parseFixtureCounts(value: unknown): FixtureCounts | undefined {
  if (
    !isRecord(value) ||
    !Number.isSafeInteger(value.fixture_dispatch_calls) ||
    !Number.isSafeInteger(value.for_case_calls) ||
    value.live_dispatch_calls !== 0
  )
    return undefined;
  const fixtureDispatchByCase = countMap(value.fixture_dispatch_by_case);
  const forCaseByCase = countMap(value.for_case_by_case);
  if (!fixtureDispatchByCase || !forCaseByCase) return undefined;
  return {
    fixture_dispatch_calls: value.fixture_dispatch_calls as number,
    for_case_calls: value.for_case_calls as number,
    live_dispatch_calls: 0,
    fixture_dispatch_by_case: fixtureDispatchByCase,
    for_case_by_case: forCaseByCase,
  };
}

export async function waitForBarrierEntry(
  controlDirectory: string,
  caseId: string,
  timeoutMs = 12_000,
): Promise<void> {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(caseId))
    throw new Error("Fixture case ID is invalid.");
  const enteredPath = `${controlDirectory}/${caseId}.entered`;
  const deadline = performance.now() + timeoutMs;
  while (performance.now() < deadline) {
    try {
      await access(enteredPath, constants.F_OK);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  throw new Error("The installed fixture settlement barrier was not entered.");
}

export async function waitForAnyBarrierEntry(
  controlDirectory: string,
  caseIds: readonly string[],
  timeoutMs = 12_000,
): Promise<string> {
  if (
    caseIds.length === 0 ||
    caseIds.some((caseId) => !/^[A-Za-z0-9_-]{1,128}$/.test(caseId))
  )
    throw new Error("Fixture case IDs are invalid.");
  const deadline = performance.now() + timeoutMs;
  while (performance.now() < deadline) {
    for (const caseId of caseIds) {
      try {
        await access(`${controlDirectory}/${caseId}.entered`, constants.F_OK);
        return caseId;
      } catch {
        // A barrier entry is published by atomic file creation.
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("No selected fixture settlement barrier was entered.");
}

export async function createFixtureHold(
  controlDirectory: string,
  caseId: string,
): Promise<{ path: string; release: () => Promise<void> }> {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(caseId))
    throw new Error("Fixture case ID is invalid.");
  await unlink(`${controlDirectory}/${caseId}.entered`).catch(() => undefined);
  const path = `${controlDirectory}/${caseId}.hold`;
  const handle = await open(path, "wx", 0o600);
  try {
    await handle.writeFile("hold\n", "utf8");
  } catch (cause) {
    await unlink(path).catch(() => undefined);
    throw cause;
  } finally {
    await handle.close();
  }
  return {
    path,
    async release() {
      await unlink(path).catch(() => undefined);
    },
  };
}

export async function invokeReportWitness(
  qualification: DebuggingQualification,
  projectPath: string,
  reportId: string,
  outputPath: string,
): Promise<void> {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(reportId))
    throw new Error("Report ID is invalid.");
  await new Promise<void>((resolve, reject) => {
    const child = spawn(
      qualification.installedPython,
      [
        "-I",
        qualification.workerPath,
        "report-witness",
        "--project",
        projectPath,
        "--report-id",
        reportId,
        "--output",
        outputPath,
      ],
      {
        cwd: projectPath,
        stdio: ["ignore", "ignore", "ignore"],
        windowsHide: true,
      },
    );
    let timedOut = false;
    let forceKillTimer: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      forceKillTimer = setTimeout(() => child.kill("SIGKILL"), 1_000);
    }, BODY_TIMEOUT_MS);
    child.once("error", () => {
      clearTimeout(timer);
      if (forceKillTimer !== undefined) clearTimeout(forceKillTimer);
      reject(new Error("The installed report witness could not be started."));
    });
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      if (forceKillTimer !== undefined) clearTimeout(forceKillTimer);
      if (!timedOut && code === 0 && signal === null) resolve();
      else reject(new Error("The installed report witness failed."));
    });
  });
}

export async function readReportWitness(path: string, reportId: string) {
  const raw: unknown = JSON.parse(await readFile(path, "utf8"));
  if (
    !isRecord(raw) ||
    raw.report_id !== reportId ||
    raw.read_only_witness !== true ||
    !isRecord(raw.artifacts)
  )
    throw new Error("The installed report witness metadata is invalid.");
  const formats = ["json", "markdown"] as const;
  const output: Record<
    (typeof formats)[number],
    { file: string; bytes_hash: string; byte_count: number }
  > = {
    json: { file: "", bytes_hash: "", byte_count: 0 },
    markdown: { file: "", bytes_hash: "", byte_count: 0 },
  };
  for (const format of formats) {
    const artifact = raw.artifacts[format];
    if (
      !isRecord(artifact) ||
      typeof artifact.file !== "string" ||
      typeof artifact.bytes_hash !== "string" ||
      !Number.isSafeInteger(artifact.byte_count)
    )
      throw new Error("The installed report witness artifact is invalid.");
    output[format] = {
      file: artifact.file,
      bytes_hash: artifact.bytes_hash,
      byte_count: artifact.byte_count as number,
    };
  }
  return output;
}

export async function assertExactArtifactBytes(
  actual: Uint8Array,
  expectedPath: string,
  expectedHash: string,
): Promise<boolean> {
  const expected = await readFile(expectedPath);
  return (
    actual.byteLength === expected.byteLength &&
    bodySha256(actual) === expectedHash &&
    bodySha256(expected) === expectedHash &&
    Buffer.compare(Buffer.from(actual), expected) === 0
  );
}

export class BrowserReadTracker {
  private readonly pending = new Map<Request, string>();
  private readonly baseOrigin: string;
  private readonly onRequest = (request: Request) => {
    if (request.method() !== "GET") return;
    const url = new URL(request.url());
    if (url.origin !== this.baseOrigin || !url.pathname.startsWith("/api/"))
      return;
    this.pending.set(request, routeTemplate(url.pathname));
    this.publish();
  };
  private readonly onResponse = (response: Response) => {
    const request = response.request();
    if (!this.pending.has(request)) return;
    void response
      .body()
      .then(
        async () => {
          try {
            await this.qualification.observeFailure(response);
          } finally {
            this.settle(request);
          }
        },
        () => this.settle(request),
      )
      .catch(() => this.settle(request));
  };
  private readonly onFailure = (request: Request) => this.settle(request);

  constructor(
    private readonly page: Page,
    private readonly qualification: DebuggingQualification,
    baseURL: string,
  ) {
    this.baseOrigin = new URL(baseURL).origin;
    page.on("request", this.onRequest);
    page.on("response", this.onResponse);
    page.on("requestfailed", this.onFailure);
  }

  private settle(request: Request): void {
    this.pending.delete(request);
    this.publish();
  }

  private publish(): void {
    const counts: Record<string, number> = {};
    for (const route of this.pending.values())
      counts[route] = (counts[route] ?? 0) + 1;
    this.qualification.setPendingReads(counts);
    void this.qualification.save();
  }

  async waitForIdle(timeoutMs = BODY_TIMEOUT_MS): Promise<void> {
    const deadline = performance.now() + timeoutMs;
    while (this.pending.size > 0 && performance.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 50));
    if (this.pending.size > 0)
      throw new Error(
        "Installed browser reads did not finish their response bodies.",
      );
  }

  async dispose(): Promise<void> {
    try {
      await this.waitForIdle();
    } finally {
      this.page.off("request", this.onRequest);
      this.page.off("response", this.onResponse);
      this.page.off("requestfailed", this.onFailure);
      // Keep any unfinished reads visible in the final progress artifact.
      this.publish();
      await this.qualification.save();
    }
  }
}

export async function settleOnSandbox(
  page: Page,
  reads: BrowserReadTracker,
): Promise<void> {
  const heading = page.getByRole("heading", { name: "Sandbox", exact: true });
  if (!(await heading.isVisible().catch(() => false)))
    await page.getByRole("button", { name: "Sandbox", exact: true }).click();
  await expect(heading).toBeVisible();
  await reads.waitForIdle();
}

import { useEffect, useRef, useState } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import type {
  DecisionAuthoringOperations,
  ExecutionGateway,
  ProjectOverview,
} from "../../workspace/gateway";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import { RunCaseInspector } from "./RunCaseInspector";

type Run = ApiOperationData<"readRun">;
type Accepted = ApiOperationData<"resumeRun">;
type ResumePreview = ApiOperationData<"previewRunResume">;
type CancelReceipt = ApiOperationData<"cancelRun">;
type ResumeBody = ApiOperationBody<"resumeRun">;
type CancelBody = ApiOperationBody<"cancelRun">;

function integerText(value: string): number | null {
  if (!/^(?:0|[1-9][0-9]*)$/.test(value)) return null;
  const result = Number(value);
  return Number.isSafeInteger(result) && result > 0 ? result : null;
}

export function RunDetail({
  registrationId,
  runId,
  evaluationId,
  caseId,
  execution,
  navigation,
  project,
  readRevision,
}: {
  registrationId: string;
  runId: string;
  evaluationId?: string;
  caseId?: string;
  execution: ExecutionGateway;
  navigation: WorkspaceNavigation;
  project: ProjectOverview;
  readRevision: DecisionAuthoringOperations["revision"];
}) {
  const [run, setRun] = useState<Run>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [lastUpdated, setLastUpdated] = useState<string>();
  const [cancelState, setCancelState] = useState<MutationState<CancelReceipt>>({
    kind: "idle",
  });
  const [resumeState, setResumeState] = useState<MutationState<Accepted>>({
    kind: "idle",
  });
  const [resumePreview, setResumePreview] = useState<ResumePreview>();
  const [resumeError, setResumeError] = useState<string>();
  const [retryUnknown, setRetryUnknown] = useState(false);
  const [attemptLimit, setAttemptLimit] = useState("");
  const [previewingResume, setPreviewingResume] = useState(false);
  const [refreshGeneration, setRefreshGeneration] = useState(0);
  const readGeneration = useRef(0);
  const resumeReviewGeneration = useRef(0);
  const resumePreviewController = useRef<AbortController | undefined>(
    undefined,
  );
  const cancelMutation = useRef<
    | RetainedMutation<
        { registrationId: string; runId: string; body: CancelBody },
        CancelReceipt
      >
    | undefined
  >(undefined);
  const resumeMutation = useRef<
    | RetainedMutation<
        { registrationId: string; runId: string; body: ResumeBody },
        Accepted
      >
    | undefined
  >(undefined);

  if (!cancelMutation.current) {
    cancelMutation.current = new RetainedMutation(async (request) => {
      const result = await execution.runs.cancel(request);
      if (result.data.run_id !== request.runId)
        throw new Error("The cancellation receipt belongs to a different run.");
      return result.data;
    }, setCancelState);
  }
  if (!resumeMutation.current) {
    resumeMutation.current = new RetainedMutation(async (request) => {
      const result = await execution.runs.resume(request);
      if (
        result.data.run_id !== request.runId ||
        result.data.operation_id !== request.body.operation_id
      )
        throw new Error(
          "The resume receipt does not match the original run request.",
        );
      return result.data;
    }, setResumeState);
  }

  function currentCancelState() {
    return cancelMutation.current?.state;
  }

  function currentResumeState() {
    return resumeMutation.current?.state;
  }

  const mutationBlocked =
    cancelState.kind === "submitting" ||
    cancelState.kind === "outcome-unknown" ||
    resumeState.kind === "submitting" ||
    resumeState.kind === "outcome-unknown";
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: mutationBlocked,
    isDirtyNow: () => {
      const cancelKind = cancelMutation.current?.state.kind;
      const resumeKind = resumeMutation.current?.state.kind;
      return (
        cancelKind === "submitting" ||
        cancelKind === "outcome-unknown" ||
        resumeKind === "submitting" ||
        resumeKind === "outcome-unknown"
      );
    },
    save: async () => undefined,
    discard: () => undefined,
    isBlockedNow: () => mutationBlocked,
    blockedMessage: mutationBlocked
      ? "A run mutation is still settling. Retry the identical request before leaving."
      : undefined,
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `run-mutation:${registrationId}:${runId}`,
        guard,
      ),
    [navigation, registrationId, runId, guard],
  );

  useEffect(() => () => resumePreviewController.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let executionActive: boolean | undefined;
    const generation = ++readGeneration.current;
    setLoading(true);
    setError(undefined);

    function schedule(delay: number) {
      if (!active || document.visibilityState === "hidden") return;
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(() => void poll(), delay);
    }
    async function poll() {
      if (!active || inFlight || document.visibilityState === "hidden") return;
      inFlight = true;
      try {
        const result = await execution.runs.read({
          registrationId,
          runId,
          signal: controller.signal,
        });
        if (
          !active ||
          controller.signal.aborted ||
          generation !== readGeneration.current
        )
          return;
        if (result.data.run_id !== runId)
          throw new Error("The service returned progress for a different run.");
        executionActive = result.data.execution_active;
        const route = navigation.current;
        if (
          route.kind === "run" &&
          route.registrationId === registrationId &&
          route.runId === runId
        ) {
          setRun(result.data);
          setLastUpdated(new Date().toLocaleTimeString());
          setError(undefined);
        }
        failures = 0;
      } catch (cause) {
        if (active && !controller.signal.aborted) {
          setError(safeMessage(cause));
          failures = Math.min(failures + 1, 4);
        }
      } finally {
        inFlight = false;
        if (active) {
          setLoading(false);
          const delay =
            failures === 0 ? 1000 : [2000, 4000, 8000, 15000][failures - 1];
          if (executionActive !== false) schedule(delay);
        }
      }
    }
    function visibilityChanged() {
      if (document.visibilityState === "hidden") {
        if (timer !== undefined) clearTimeout(timer);
      } else {
        void poll();
      }
    }
    document.addEventListener("visibilitychange", visibilityChanged);
    void poll();
    return () => {
      active = false;
      readGeneration.current += 1;
      if (timer !== undefined) clearTimeout(timer);
      document.removeEventListener("visibilitychange", visibilityChanged);
      controller.abort();
    };
  }, [execution, navigation, registrationId, runId, refreshGeneration]);

  async function cancelRun() {
    if (!run || cancelMutation.current?.state.kind !== "idle") return;
    await cancelMutation.current.submit({
      registrationId,
      runId,
      body: { schema_version: 1, operation_id: crypto.randomUUID() },
    });
    const receipt = currentCancelState();
    if (receipt?.kind === "committed") {
      setRun(receipt.receipt);
      setRefreshGeneration((value) => value + 1);
    }
  }

  async function retryCancel() {
    await cancelMutation.current?.retryOriginal();
    const receipt = currentCancelState();
    if (receipt?.kind === "committed") {
      setRun(receipt.receipt);
      setRefreshGeneration((value) => value + 1);
    }
  }

  async function reviewResume() {
    if (
      !run ||
      resumePreviewController.current ||
      resumeState.kind === "submitting" ||
      resumeState.kind === "outcome-unknown"
    )
      return;
    const maximum = attemptLimit ? integerText(attemptLimit) : null;
    if (attemptLimit && maximum === null) {
      setResumeError("Enter a positive whole-number total attempt cap.");
      return;
    }
    setPreviewingResume(true);
    setResumeError(undefined);
    const generation = resumeReviewGeneration.current;
    const controller = new AbortController();
    resumePreviewController.current = controller;
    try {
      const result = await execution.runs.previewResume({
        registrationId,
        runId,
        body: { schema_version: 1 },
        query: {
          retry_unknown: retryUnknown ? "true" : "false",
          ...(maximum === null ? {} : { max_attempts: String(maximum) }),
        },
        signal: controller.signal,
      });
      if (result.data.run.run_id !== runId)
        throw new Error("The resume review belongs to a different run.");
      if (
        generation !== resumeReviewGeneration.current ||
        controller.signal.aborted
      )
        return;
      setResumePreview(result.data);
    } catch (cause) {
      if (
        generation === resumeReviewGeneration.current &&
        !controller.signal.aborted
      ) {
        setResumeError(safeMessage(cause));
        setResumePreview(undefined);
      }
    } finally {
      if (resumePreviewController.current === controller) {
        resumePreviewController.current = undefined;
        if (generation === resumeReviewGeneration.current)
          setPreviewingResume(false);
      }
    }
  }

  async function submitResume() {
    if (!resumePreview || resumeMutation.current?.state.kind !== "idle") return;
    const body: ResumeBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      retry_unknown: retryUnknown,
      max_attempts: attemptLimit ? integerText(attemptLimit) : null,
    };
    await resumeMutation.current.submit({ registrationId, runId, body });
    const state = currentResumeState();
    if (state?.kind === "committed") {
      if (state.receipt.mode !== run?.mode)
        setResumeError("The resumed run returned a different execution mode.");
      setRefreshGeneration((value) => value + 1);
    }
  }

  async function retryResume() {
    await resumeMutation.current?.retryOriginal();
    const state = currentResumeState();
    if (state?.kind === "committed") {
      if (state.receipt.mode !== run?.mode)
        setResumeError("The resumed run returned a different execution mode.");
      setRefreshGeneration((value) => value + 1);
    }
  }

  if (loading && !run)
    return (
      <article className="document">
        <h1>Run</h1>
        <LoadingState>Loading run progress…</LoadingState>
      </article>
    );
  if (!run)
    return (
      <article className="document">
        <h1>Run</h1>
        {error && (
          <ErrorSummary
            message={error}
            retry={() => setRefreshGeneration((value) => value + 1)}
          />
        )}
      </article>
    );
  const associationValid =
    project.id === registrationId &&
    project.decisions.some((decision) => decision.id === run.decision_id) &&
    project.datasets.some((dataset) => dataset.id === run.dataset_id);
  if (!associationValid)
    return (
      <article className="document">
        <h1>Run association unavailable</h1>
        <p>
          The service returned a run whose decision or dataset is not present in
          this project overview.
        </p>
        <button
          type="button"
          disabled={loading}
          onClick={() => setRefreshGeneration((value) => value + 1)}
        >
          Refresh run
        </button>
      </article>
    );

  return (
    <>
      <article className="document run-detail">
        <h1>Run {run.run_id}</h1>
        <p className="lead">
          {run.state}
          {run.execution_active ? " · execution active" : " · inactive"};{" "}
          {run.mode}
        </p>
        <div className="actions">
          <button
            type="button"
            onClick={() =>
              void navigation.navigate({ kind: "runs", registrationId })
            }
          >
            Runs
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => setRefreshGeneration((value) => value + 1)}
          >
            Refresh progress
          </button>
          {run.execution_active && (
            <button
              type="button"
              disabled={cancelState.kind !== "idle"}
              onClick={() => void cancelRun()}
            >
              Cancel run
            </button>
          )}
          {cancelState.kind === "outcome-unknown" && (
            <section className="warning-summary">
              <p>{cancelState.message}</p>
              <button type="button" onClick={() => void retryCancel()}>
                Retry original cancellation
              </button>
            </section>
          )}
          {cancelState.kind === "committed" && (
            <p role="status">
              Cancellation acknowledged. Run progress is being refreshed;
              already dispatched work may still settle.
            </p>
          )}
          {(cancelState.kind === "failed" ||
            cancelState.kind === "conflict") && (
            <ErrorSummary message={cancelState.message} />
          )}
        </div>
        {error && (
          <ErrorSummary
            message={error}
            retry={() => setRefreshGeneration((value) => value + 1)}
          />
        )}
        {lastUpdated && (
          <p role="status">
            Last updated {lastUpdated}. Polling pauses while this page is
            hidden; failed reads back off to 15 seconds.
          </p>
        )}
        {run.reason && (
          <section className="warning-summary">
            <strong>{run.reason.code}</strong>: {run.reason.message}
            {run.reason.reason && <span> ({run.reason.reason})</span>}
          </section>
        )}
        <dl>
          <dt>Decision / dataset</dt>
          <dd>
            {run.decision_id} / {run.dataset_id}
          </dd>
          <dt>Attempts</dt>
          <dd>
            {run.attempts_used} used / {run.attempt_limit} lifetime limit /{" "}
            {run.attempts_remaining} remaining
          </dd>
          <dt>Settings</dt>
          <dd>
            {run.settings.concurrency} concurrent;{" "}
            {run.settings.timeout_seconds}s timeout;{" "}
            {run.settings.deadline_seconds}s segment deadline;{" "}
            {run.settings.max_retries_per_case} rate retries per case.
          </dd>
          <dt>Source snapshots</dt>
          <dd>
            Revision {run.sources.decision_revision_id}; dataset{" "}
            {run.sources.dataset_snapshot_id}; labels{" "}
            {run.sources.label_snapshot_id}; development dataset{" "}
            {run.sources.development_dataset_snapshot_id}; development labels{" "}
            {run.sources.development_label_snapshot_id}
          </dd>
          <dt>Execution identity</dt>
          <dd>
            {run.sources.evidence_mode ?? "Unavailable"}; adapter{" "}
            {run.sources.adapter ?? "Unavailable"}; requested model{" "}
            {run.requested_model}; compiler{" "}
            {run.sources.compiler_id ??
              run.sources.compiler_id_unavailable_reason ??
              "Unavailable"}{" "}
            {run.sources.compiler_version ?? ""}
          </dd>
          <dt>Segments</dt>
          <dd>{run.segment_ids.join(", ") || "None"}</dd>
        </dl>
        <section aria-label="Run attempts and segments">
          <h2>Attempts and segments</h2>
          {run.attempts.length > 0 ? (
            <div className="table-region">
              <table>
                <caption>Service-reported attempts</caption>
                <thead>
                  <tr>
                    <th>Attempt</th>
                    <th>Case</th>
                    <th>Kind / state</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {run.attempts.map((attempt) => (
                    <tr key={attempt.attempt_id}>
                      <td>
                        {attempt.number} · {attempt.attempt_id}
                      </td>
                      <td>{attempt.case_id}</td>
                      <td>
                        {attempt.kind} / {attempt.state}
                      </td>
                      <td>{attempt.duration_seconds ?? "Unavailable"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No attempt records are available.</p>
          )}
          {run.segments.length > 0 && (
            <div className="table-region">
              <table>
                <caption>Run segments</caption>
                <thead>
                  <tr>
                    <th>Segment</th>
                    <th>Started</th>
                    <th>Deadline</th>
                    <th>Ended</th>
                    <th>Unknown retries</th>
                  </tr>
                </thead>
                <tbody>
                  {run.segments.map((segment) => (
                    <tr key={segment.segment_id}>
                      <td>{segment.segment_id}</td>
                      <td>{segment.started_at}</td>
                      <td>{segment.deadline_at}</td>
                      <td>{segment.ended_at ?? "Active"}</td>
                      <td>{segment.retry_unknown ? "Included" : "Excluded"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section aria-label="Run case outcomes">
          <h2>Cases</h2>
          <div className="table-region">
            <table>
              <caption>Service-reported case lifecycle</caption>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Status</th>
                  <th>Attempt</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {run.cases.map((item) => (
                  <tr key={item.case_id}>
                    <td>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() =>
                          void navigation.navigate({
                            kind: "run",
                            registrationId,
                            runId,
                            ...(evaluationId ? { evaluationId } : {}),
                            caseId: item.case_id,
                          })
                        }
                      >
                        {item.case_id}
                      </button>
                    </td>
                    <td>{item.status}</td>
                    <td>{item.attempt_id ?? "None"}</td>
                    <td>
                      {item.error
                        ? `${item.error.code}: ${item.error.message}`
                        : "None"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        {!run.execution_active && (
          <section className="resume-review" aria-label="Resume review">
            <h2>Review resume</h2>
            <label>
              <input
                type="checkbox"
                checked={retryUnknown}
                onChange={(event) => {
                  resumeReviewGeneration.current += 1;
                  resumePreviewController.current?.abort();
                  resumePreviewController.current = undefined;
                  setPreviewingResume(false);
                  setRetryUnknown(event.currentTarget.checked);
                  setResumePreview(undefined);
                }}
              />{" "}
              Retry cases with unknown prior outcome
            </label>
            <label className="field">
              Proposed lifetime attempt cap (optional)
              <input
                inputMode="numeric"
                value={attemptLimit}
                onChange={(event) => {
                  resumeReviewGeneration.current += 1;
                  resumePreviewController.current?.abort();
                  resumePreviewController.current = undefined;
                  setPreviewingResume(false);
                  setAttemptLimit(event.currentTarget.value);
                  setResumePreview(undefined);
                }}
              />
            </label>
            <button
              type="button"
              disabled={
                previewingResume ||
                resumeState.kind === "submitting" ||
                resumeState.kind === "outcome-unknown"
              }
              onClick={() => void reviewResume()}
            >
              {previewingResume ? "Reviewing…" : "Preview resume"}
            </button>
            {resumeError && <ErrorSummary message={resumeError} />}
            {resumePreview && (
              <>
                <p>
                  Planned cases:{" "}
                  {resumePreview.planned_case_ids.join(", ") || "None"}.
                  Proposed total cap: {resumePreview.proposed_attempt_limit}.
                  Unknown retries:{" "}
                  {resumePreview.retry_unknown ? "included" : "excluded"}. This
                  review is advisory against the original frozen history.
                </p>
                <button
                  className="primary"
                  type="button"
                  disabled={resumeState.kind !== "idle"}
                  onClick={() => void submitResume()}
                >
                  Resume run
                </button>
              </>
            )}
            {resumeState.kind === "outcome-unknown" && (
              <section className="warning-summary">
                <p>
                  {resumeState.message} The original resume request is retained.
                </p>
                <button type="button" onClick={() => void retryResume()}>
                  Retry original resume request
                </button>
              </section>
            )}
            {resumeState.kind === "committed" && (
              <p role="status">
                Resume acknowledged for run {resumeState.receipt.run_id};
                segment{" "}
                {resumeState.receipt.segment_id ?? "acknowledgement incomplete"}
                .
              </p>
            )}
            {(resumeState.kind === "failed" ||
              resumeState.kind === "conflict") && (
              <ErrorSummary message={resumeState.message} />
            )}
          </section>
        )}
        {!run.execution_active && (
          <RunCaseInspector
            key={`${registrationId}:${run.run_id}:${evaluationId ?? "current"}`}
            registrationId={registrationId}
            run={run}
            execution={execution}
            readRevision={readRevision}
            navigation={navigation}
            evaluationId={evaluationId}
            caseId={caseId}
          />
        )}
      </article>
      {prompt}
    </>
  );
}

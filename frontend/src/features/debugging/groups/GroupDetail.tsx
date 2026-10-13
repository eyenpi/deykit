import { useEffect, useRef, useState } from "react";
import { safeMessage } from "../../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../../api/client";
import { ErrorSummary, LoadingState } from "../../../components/States";
import type {
  ProjectOverview,
  WorkspaceGateway,
} from "../../../workspace/gateway";
import type { WorkspaceNavigation } from "../../../workspace/navigation";
import { useDirtyNavigationGuard } from "../../../workspace/NavigationGuardPrompt";
import { RetainedMutation } from "../../../workspace/mutation-controller";
import type { MutationState } from "../../../workspace/mutation-controller";
import { presentDiagnosticSummary } from "./summary";
import { SnapshotPanel } from "./SnapshotPanel";
import "./groups.css";

type DiagnosticView = ApiOperationData<"readChoiceOrder">;
type CheckView = ApiOperationData<"readCheck">;
type DiagnosticSnapshots = ApiOperationData<"listChoiceOrderSnapshots">;
type CheckSnapshots = ApiOperationData<"listCheckSnapshots">;
type Snapshot = DiagnosticSnapshots[number] | CheckSnapshots[number];
type DiagnosticSnapshot = ApiOperationData<"readChoiceOrderSnapshot">;
type CheckSnapshot = ApiOperationData<"readCheckSnapshot">;
type SnapshotDetail = DiagnosticSnapshot | CheckSnapshot;
type CancelBody = ApiOperationBody<"cancelChoiceOrder">;
type CancelReceipt = ApiOperationData<"cancelChoiceOrder">;
type ResumeBody = ApiOperationBody<"resumeChoiceOrder">;
type ResumeReceipt = ApiOperationData<"resumeChoiceOrder">;
type ResumePreview = ApiOperationData<"previewChoiceOrderResume">;
type GroupProgress = DiagnosticView["group"] | CheckView["group"];
type GroupPollingCoordinator = {
  token: number;
  epoch: number;
  gateway: WorkspaceGateway;
  registrationId: string;
  kind: "diagnostic" | "check";
  groupId: string;
  routeSnapshotId?: string;
  controller?: AbortController;
  timer?: number;
  inFlight?: Promise<void>;
  refreshRequested: boolean;
  disposed: boolean;
  generation: number;
  progressReceiptRevision: number;
  requestRefresh: () => void;
};
type CancelIntent = {
  registrationId: string;
  groupId: string;
  body: CancelBody;
  kind: "diagnostic" | "check";
  gateway: WorkspaceGateway;
};
type ResumeIntent = {
  registrationId: string;
  groupId: string;
  body: ResumeBody;
  kind: "diagnostic" | "check";
  gateway: WorkspaceGateway;
};

function readMutationState<Request, Receipt>(
  mutation: RetainedMutation<Request, Receipt> | undefined,
): MutationState<Receipt> | undefined {
  return mutation?.state;
}

const SETTLED_MEMBER_STATES = new Set([
  "cancelled",
  "completed",
  "completed_with_errors",
  "budget_exhausted",
  "interrupted",
  "preflight_failed",
]);

function isSettledGroup(group: GroupProgress | undefined): boolean {
  return Boolean(
    group &&
    group.members.length > 0 &&
    group.members.every(
      (member) =>
        !member.execution_active && SETTLED_MEMBER_STATES.has(member.state),
    ),
  );
}

export type GroupReportTarget = {
  targetKind: "diagnostic" | "check";
  targetId: string;
  groupSnapshotId: string;
};

export function GroupDetail({
  project,
  gateway,
  navigation,
  kind,
  groupId,
  snapshotId,
  onReport,
}: {
  project: ProjectOverview;
  gateway: WorkspaceGateway;
  navigation: WorkspaceNavigation;
  kind: "diagnostic" | "check";
  groupId: string;
  snapshotId?: string;
  onReport?: (target: GroupReportTarget) => void;
}) {
  const [progress, setProgress] = useState<GroupProgress>();
  const [progressError, setProgressError] = useState<string>();
  const [snapshots, setSnapshots] = useState<readonly Snapshot[]>([]);
  const [snapshotsError, setSnapshotsError] = useState<string>();
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(
    snapshotId ?? null,
  );
  const [snapshot, setSnapshot] = useState<SnapshotDetail>();
  const [snapshotError, setSnapshotError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [retryUnknown, setRetryUnknown] = useState(false);
  const [resumePreview, setResumePreview] = useState<ResumePreview>();
  const [resumeError, setResumeError] = useState<string>();
  const [cancelState, setCancelState] = useState<MutationState<CancelReceipt>>({
    kind: "idle",
  });
  const [resumeState, setResumeState] = useState<MutationState<ResumeReceipt>>({
    kind: "idle",
  });
  const [actionBusy, setActionBusy] = useState(false);
  const snapshotReadGeneration = useRef(0);
  const scope = `${project.id}:${kind}:${groupId}`;
  const mounted = useRef(true);
  const renderEpoch = useRef(0);
  const cancelEpoch = useRef(0);
  const resumeEpoch = useRef(0);
  const cancelCallbackScopeToken = useRef<number | undefined>(undefined);
  const resumeCallbackScopeToken = useRef<number | undefined>(undefined);
  const scopeToken = useRef(0);
  const tokenScope = useRef({ scope, gateway, snapshotId });
  if (
    tokenScope.current.scope !== scope ||
    tokenScope.current.gateway !== gateway ||
    tokenScope.current.snapshotId !== snapshotId
  ) {
    tokenScope.current = { scope, gateway, snapshotId };
    scopeToken.current += 1;
  }
  const pollingCoordinator = useRef<GroupPollingCoordinator | undefined>(
    undefined,
  );
  const resumeReviewGeneration = useRef(0);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const cancelMutation = useRef<
    RetainedMutation<CancelIntent, CancelReceipt> | undefined
  >(undefined);
  const resumeMutation = useRef<
    RetainedMutation<ResumeIntent, ResumeReceipt> | undefined
  >(undefined);

  if (!cancelMutation.current) {
    cancelMutation.current = new RetainedMutation(
      async (request) => {
        const payload = {
          registrationId: request.registrationId,
          groupId: request.groupId,
          body: request.body,
        };
        const result =
          request.kind === "diagnostic"
            ? await request.gateway.debugging.diagnostics.cancel(payload)
            : await request.gateway.debugging.checks.cancel(payload);
        if (
          result.data.group_id !== request.groupId ||
          result.data.kind !==
            (request.kind === "diagnostic"
              ? "choice_order"
              : "regression_check")
        )
          throw new Error(
            "The cancellation receipt does not match this group request.",
          );
        return result.data as CancelReceipt;
      },
      (state) => {
        if (
          mounted.current &&
          cancelEpoch.current === renderEpoch.current &&
          cancelCallbackScopeToken.current === scopeToken.current
        )
          setCancelState(state);
      },
    );
  }
  if (!resumeMutation.current) {
    resumeMutation.current = new RetainedMutation(
      async (request) => {
        const payload = {
          registrationId: request.registrationId,
          groupId: request.groupId,
          body: request.body,
        };
        const result =
          request.kind === "diagnostic"
            ? await request.gateway.debugging.diagnostics.resume(payload)
            : await request.gateway.debugging.checks.resume(payload);
        if (
          result.data.group_id !== request.groupId ||
          result.data.operation_id !== request.body.operation_id ||
          result.data.kind !==
            (request.kind === "diagnostic"
              ? "choice_order"
              : "regression_check")
        )
          throw new Error(
            "The resume receipt does not match this group request.",
          );
        return result.data as ResumeReceipt;
      },
      (state) => {
        if (
          mounted.current &&
          resumeEpoch.current === renderEpoch.current &&
          resumeCallbackScopeToken.current === scopeToken.current
        )
          setResumeState(state);
      },
    );
  }

  const resumePreviewRef = useRef(resumePreview);
  resumePreviewRef.current = resumePreview;
  function hasUnresolvedMutation() {
    return [
      cancelMutation.current?.state.kind,
      resumeMutation.current?.state.kind,
    ].some((state) => state === "submitting" || state === "outcome-unknown");
  }
  const pendingMutation = hasUnresolvedMutation();
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: pendingMutation || Boolean(resumePreview),
    isDirtyNow: () =>
      hasUnresolvedMutation() || Boolean(resumePreviewRef.current),
    save: async () => {},
    discard: () => {
      if (hasUnresolvedMutation()) return;
      resumePreviewRef.current = undefined;
      setResumePreview(undefined);
    },
    blockedMessage: pendingMutation
      ? "A group request is still settling. Retry its original request before leaving."
      : resumePreview
        ? "A reviewed resume is staged. Discard it or keep editing before leaving."
        : undefined,
    isBlockedNow: hasUnresolvedMutation,
    allowDiscardWhenBlocked: true,
  });

  useEffect(
    () => navigation.registerDirtyGuard(`group-detail:${scope}`, guard),
    [navigation, scope, guard],
  );

  useEffect(() => {
    mounted.current = true;
    renderEpoch.current += 1;
    resumeReviewGeneration.current += 1;
    setProgress(undefined);
    setProgressError(undefined);
    setSnapshots([]);
    setSnapshotsError(undefined);
    setSelectedSnapshotId(snapshotId ?? null);
    setSnapshot(undefined);
    setSnapshotError(undefined);
    setLoading(true);
    if (
      cancelMutation.current &&
      !["submitting", "outcome-unknown"].includes(
        cancelMutation.current.state.kind,
      )
    ) {
      cancelMutation.current.reset();
      setCancelState({ kind: "idle" });
    }
    if (
      resumeMutation.current &&
      !["submitting", "outcome-unknown"].includes(
        resumeMutation.current.state.kind,
      )
    ) {
      resumeMutation.current.reset();
      setResumeState({ kind: "idle" });
    }
    return () => {
      mounted.current = false;
    };
  }, [scope, snapshotId]);

  useEffect(() => {
    mounted.current = true;
    const coordinator: GroupPollingCoordinator = {
      token: scopeToken.current,
      epoch: renderEpoch.current,
      gateway,
      registrationId: project.id,
      kind,
      groupId,
      routeSnapshotId: snapshotId,
      refreshRequested: false,
      disposed: false,
      generation: 0,
      progressReceiptRevision: 0,
      requestRefresh: () => {},
    };
    const isCurrent = () =>
      mounted.current &&
      !coordinator.disposed &&
      pollingCoordinator.current === coordinator &&
      scopeToken.current === coordinator.token &&
      renderEpoch.current === coordinator.epoch;

    const requestRefresh = () => {
      if (!isCurrent()) return;
      if (coordinator.inFlight) {
        coordinator.refreshRequested = true;
        return;
      }
      if (coordinator.timer !== undefined) {
        window.clearTimeout(coordinator.timer);
        coordinator.timer = undefined;
      }

      const generation = ++coordinator.generation;
      const controller = new AbortController();
      coordinator.controller = controller;
      const progressRevision = coordinator.progressReceiptRevision;
      const request = {
        registrationId: coordinator.registrationId,
        groupId: coordinator.groupId,
        signal: controller.signal,
      };

      coordinator.inFlight = Promise.resolve().then(async () => {
        try {
          try {
            const result =
              coordinator.kind === "diagnostic"
                ? await coordinator.gateway.debugging.diagnostics.read(request)
                : await coordinator.gateway.debugging.checks.read(request);
            if (!isCurrent() || generation !== coordinator.generation) return;
            if (
              result.data.group.group_id !== coordinator.groupId ||
              result.data.group.kind !==
                (coordinator.kind === "diagnostic"
                  ? "choice_order"
                  : "regression_check")
            )
              throw new Error(
                "The service returned progress for a different group.",
              );
            if (progressRevision === coordinator.progressReceiptRevision) {
              setProgress(result.data.group);
              setProgressError(undefined);
            }
          } catch (cause) {
            if (
              isCurrent() &&
              generation === coordinator.generation &&
              progressRevision === coordinator.progressReceiptRevision &&
              !controller.signal.aborted
            )
              setProgressError(safeMessage(cause));
          } finally {
            if (
              isCurrent() &&
              generation === coordinator.generation &&
              progressRevision === coordinator.progressReceiptRevision
            )
              setLoading(false);
          }

          if (!isCurrent() || generation !== coordinator.generation) return;
          try {
            const result =
              coordinator.kind === "diagnostic"
                ? await coordinator.gateway.debugging.diagnostics.listSnapshots(
                    request,
                  )
                : await coordinator.gateway.debugging.checks.listSnapshots(
                    request,
                  );
            if (!isCurrent() || generation !== coordinator.generation) return;
            const next = result.data;
            if (next.some((item) => item.group_id !== coordinator.groupId))
              throw new Error(
                "The service returned a snapshot from a different group.",
              );
            setSnapshots(next);
            setSnapshotsError(undefined);
            setSelectedSnapshotId(
              (current) =>
                current ??
                coordinator.routeSnapshotId ??
                next.at(-1)?.id ??
                null,
            );
          } catch (cause) {
            if (
              isCurrent() &&
              generation === coordinator.generation &&
              !controller.signal.aborted
            )
              setSnapshotsError(safeMessage(cause));
          }
        } finally {
          if (generation === coordinator.generation) {
            coordinator.inFlight = undefined;
            coordinator.controller = undefined;
            if (!isCurrent()) return;
            if (coordinator.refreshRequested) {
              coordinator.refreshRequested = false;
              requestRefresh();
            } else {
              coordinator.timer = window.setTimeout(() => {
                coordinator.timer = undefined;
                requestRefresh();
              }, 2500);
            }
          }
        }
      });
    };
    coordinator.requestRefresh = requestRefresh;
    pollingCoordinator.current = coordinator;
    requestRefresh();

    return () => {
      coordinator.disposed = true;
      coordinator.refreshRequested = false;
      if (coordinator.timer !== undefined)
        window.clearTimeout(coordinator.timer);
      coordinator.controller?.abort();
      if (pollingCoordinator.current === coordinator)
        pollingCoordinator.current = undefined;
      mounted.current = false;
      snapshotReadGeneration.current += 1;
    };
  }, [gateway, groupId, kind, project.id, scope, snapshotId]);

  function refreshAfterReceipt(progressReceipt?: GroupProgress) {
    const coordinator = pollingCoordinator.current;
    if (
      !coordinator ||
      coordinator.disposed ||
      coordinator.token !== scopeToken.current ||
      coordinator.epoch !== renderEpoch.current ||
      scopeRef.current !== scope
    )
      return;
    coordinator.progressReceiptRevision += 1;
    if (progressReceipt) {
      setProgress(progressReceipt);
      setProgressError(undefined);
    }
    coordinator.requestRefresh();
  }

  useEffect(() => {
    if (!selectedSnapshotId) {
      setSnapshot(undefined);
      setSnapshotError(undefined);
      return;
    }
    const controller = new AbortController();
    const generation = ++snapshotReadGeneration.current;
    const readScopeToken = scopeToken.current;
    const readRenderEpoch = renderEpoch.current;
    const readScope = scope;
    const isCurrentSnapshotRead = () =>
      mounted.current &&
      !controller.signal.aborted &&
      generation === snapshotReadGeneration.current &&
      scopeToken.current === readScopeToken &&
      renderEpoch.current === readRenderEpoch &&
      scopeRef.current === readScope;
    setSnapshot(undefined);
    setSnapshotError(undefined);
    void (async () => {
      try {
        const request = {
          registrationId: project.id,
          groupId,
          snapshotId: selectedSnapshotId,
          signal: controller.signal,
        };
        const result =
          kind === "diagnostic"
            ? await gateway.debugging.diagnostics.readSnapshot(request)
            : await gateway.debugging.checks.readSnapshot(request);
        if (!isCurrentSnapshotRead()) return;
        if (
          result.data.snapshot.id !== selectedSnapshotId ||
          result.data.snapshot.group_id !== groupId
        )
          throw new Error(
            "The service returned a different immutable group snapshot.",
          );
        setSnapshot(result.data);
      } catch (cause) {
        if (isCurrentSnapshotRead()) setSnapshotError(safeMessage(cause));
      }
    })();
    return () => controller.abort();
  }, [gateway, groupId, kind, project.id, selectedSnapshotId]);

  async function cancelGroup() {
    if (cancelMutation.current?.state.kind !== "idle") return;
    const body: CancelBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
    };
    cancelCallbackScopeToken.current = scopeToken.current;
    cancelEpoch.current = renderEpoch.current;
    const dispatchScopeToken = scopeToken.current;
    await cancelMutation.current.submit({
      registrationId: project.id,
      groupId,
      body,
      kind,
      gateway,
    });
    const receipt = readMutationState(cancelMutation.current);
    if (
      receipt?.kind === "committed" &&
      mounted.current &&
      scopeToken.current === dispatchScopeToken &&
      cancelCallbackScopeToken.current === dispatchScopeToken &&
      scopeRef.current === scope
    ) {
      setResumePreview(undefined);
      refreshAfterReceipt(receipt.receipt);
    }
  }

  async function retryCancel() {
    const dispatchScopeToken = cancelCallbackScopeToken.current;
    if (dispatchScopeToken === undefined) return;
    await cancelMutation.current?.retryOriginal();
    const receipt = cancelMutation.current?.state;
    if (
      receipt?.kind === "committed" &&
      mounted.current &&
      scopeToken.current === dispatchScopeToken &&
      cancelCallbackScopeToken.current === dispatchScopeToken &&
      scopeRef.current === scope
    ) {
      setResumePreview(undefined);
      refreshAfterReceipt(receipt.receipt);
    }
  }

  async function reviewResume() {
    if (
      actionBusy ||
      resumeMutation.current?.state.kind === "submitting" ||
      resumeMutation.current?.state.kind === "outcome-unknown"
    )
      return;
    setActionBusy(true);
    setResumeError(undefined);
    const generation = ++resumeReviewGeneration.current;
    try {
      const retryUnknownQuery: "true" | "false" = retryUnknown
        ? "true"
        : "false";
      const request = {
        registrationId: project.id,
        groupId,
        body: { schema_version: 1 as const },
        query: { retry_unknown: retryUnknownQuery },
      };
      const result =
        kind === "diagnostic"
          ? await gateway.debugging.diagnostics.previewResume(request)
          : await gateway.debugging.checks.previewResume(request);
      if (
        generation !== resumeReviewGeneration.current ||
        scopeRef.current !== scope
      )
        return;
      if (
        result.data.group.group_id !== groupId ||
        !result.data.dry_run ||
        result.data.retry_unknown !== retryUnknown
      )
        throw new Error(
          "The resume preview does not match this group request.",
        );
      setResumePreview(result.data as ResumePreview);
    } catch (cause) {
      if (
        generation !== resumeReviewGeneration.current ||
        scopeRef.current !== scope
      )
        return;
      setResumePreview(undefined);
      setResumeError(safeMessage(cause));
    } finally {
      if (generation === resumeReviewGeneration.current) setActionBusy(false);
    }
  }

  async function resumeGroup() {
    if (!resumePreview || resumeMutation.current?.state.kind !== "idle") return;
    const body: ResumeBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      retry_unknown: retryUnknown,
    };
    resumeCallbackScopeToken.current = scopeToken.current;
    resumeEpoch.current = renderEpoch.current;
    const dispatchScopeToken = scopeToken.current;
    await resumeMutation.current.submit({
      registrationId: project.id,
      groupId,
      body,
      kind,
      gateway,
    });
    const receipt = readMutationState(resumeMutation.current);
    if (
      receipt?.kind === "committed" &&
      mounted.current &&
      scopeToken.current === dispatchScopeToken &&
      resumeCallbackScopeToken.current === dispatchScopeToken &&
      scopeRef.current === scope
    ) {
      setResumePreview(undefined);
      refreshAfterReceipt();
    }
  }

  async function retryResume() {
    const dispatchScopeToken = resumeCallbackScopeToken.current;
    if (dispatchScopeToken === undefined) return;
    await resumeMutation.current?.retryOriginal();
    const receipt = readMutationState(resumeMutation.current);
    if (
      receipt?.kind === "committed" &&
      mounted.current &&
      scopeToken.current === dispatchScopeToken &&
      resumeCallbackScopeToken.current === dispatchScopeToken &&
      scopeRef.current === scope
    ) {
      setResumePreview(undefined);
      refreshAfterReceipt();
    }
  }

  function openMember(runId: string) {
    if (localControlsLocked || hasUnresolvedMutation()) return;
    void navigation.navigate({
      kind: "run",
      registrationId: project.id,
      runId,
      returnGroup: { kind, groupId },
    });
  }

  function reportSnapshot(groupSnapshotId: string) {
    if (!onReport || localControlsLocked || hasUnresolvedMutation()) return;
    onReport({ targetKind: kind, targetId: groupId, groupSnapshotId });
  }

  const blocked =
    cancelState.kind === "submitting" ||
    cancelState.kind === "outcome-unknown" ||
    resumeState.kind === "submitting" ||
    resumeState.kind === "outcome-unknown";
  const localControlsLocked = blocked || actionBusy || Boolean(resumePreview);
  const presentedSummary =
    snapshot && kind === "diagnostic"
      ? presentDiagnosticSummary(
          "summary" in snapshot ? snapshot.summary : undefined,
        )
      : undefined;

  return (
    <main className="group-detail">
      {prompt}
      <header>
        <p className="eyebrow">
          {kind === "diagnostic"
            ? "Choice order diagnostic"
            : "Regression check"}
        </p>
        <h1>{kind === "diagnostic" ? "Group progress" : "Check progress"}</h1>
        <p>
          Group <code>{groupId}</code>
        </p>
      </header>
      {loading && !progress && (
        <LoadingState>Loading group progress…</LoadingState>
      )}
      {progressError && <ErrorSummary message={progressError} />}
      {progress && (
        <section aria-labelledby="group-current-progress">
          <h2 id="group-current-progress">Current progress</h2>
          <dl>
            <dt>State</dt>
            <dd>{isSettledGroup(progress) ? "Settled" : "Running"}</dd>
            <dt>Independent cases</dt>
            <dd>{progress.independent_case_count}</dd>
            <dt>Initial requests</dt>
            <dd>{progress.initial_requests}</dd>
            <dt>Lifetime attempt limit</dt>
            <dd>{progress.attempt_limit}</dd>
            <dt>Attempts used</dt>
            <dd>{progress.attempts_used}</dd>
            <dt>Attempts remaining</dt>
            <dd>{progress.attempts_remaining}</dd>
            {progress.seed !== null && (
              <>
                <dt>Frozen seed</dt>
                <dd>
                  <code>{progress.seed}</code>
                </dd>
              </>
            )}
            {progress.algorithm && (
              <>
                <dt>Algorithm</dt>
                <dd>{progress.algorithm}</dd>
              </>
            )}
          </dl>
          <ol>
            {progress.members.map((member) => (
              <li key={member.run_id}>
                <p>
                  Member run{" "}
                  <button
                    type="button"
                    className="text-button"
                    disabled={localControlsLocked || hasUnresolvedMutation()}
                    onClick={() => openMember(member.run_id)}
                  >
                    <code>{member.run_id}</code>
                  </button>
                </p>
                <p>
                  {member.state} · {member.attempts_used} attempts ·{" "}
                  {member.attempts_remaining} remaining
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}
      <div className="actions">
        <button
          type="button"
          onClick={() => void cancelGroup()}
          disabled={!progress || blocked || cancelState.kind !== "idle"}
        >
          Cancel group
        </button>
        {cancelState.kind === "outcome-unknown" && (
          <>
            <ErrorSummary message={cancelState.message} />
            <button type="button" onClick={() => void retryCancel()}>
              Retry original cancellation
            </button>
          </>
        )}
        {cancelState.kind === "committed" && (
          <p role="status">Cancellation receipt received.</p>
        )}
        {(cancelState.kind === "failed" || cancelState.kind === "conflict") && (
          <ErrorSummary message={cancelState.message} />
        )}
      </div>
      <section aria-labelledby="resume-group-title">
        <h2 id="resume-group-title">Resume group</h2>
        <label>
          <input
            type="checkbox"
            checked={retryUnknown}
            disabled={localControlsLocked}
            onChange={(event) => {
              setRetryUnknown(event.currentTarget.checked);
              setResumePreview(undefined);
            }}
          />{" "}
          Retry members with unknown outcomes
        </label>
        <button
          type="button"
          onClick={() => void reviewResume()}
          disabled={!progress || blocked || actionBusy}
        >
          Review resume
        </button>
        {resumeError && <ErrorSummary message={resumeError} />}
        {resumePreview && (
          <>
            <p>
              Reviewed resume for {resumePreview.members.length} members;{" "}
              {resumePreview.segment_ids.length} frozen segments will continue
              under attempt cap {resumePreview.proposed_attempt_limit}. This
              preview is read-only.
            </p>
            <button
              type="button"
              onClick={() => void resumeGroup()}
              disabled={blocked || resumeState.kind !== "idle"}
            >
              Resume reviewed group
            </button>
          </>
        )}
        {resumeState.kind === "outcome-unknown" && (
          <>
            <ErrorSummary message={resumeState.message} />
            <button type="button" onClick={() => void retryResume()}>
              Retry original resume request
            </button>
          </>
        )}
        {resumeState.kind === "committed" && (
          <p role="status">
            Resume accepted: <code>{resumeState.receipt.group_id}</code>
          </p>
        )}
        {(resumeState.kind === "failed" || resumeState.kind === "conflict") && (
          <ErrorSummary message={resumeState.message} />
        )}
      </section>
      {snapshotsError && <ErrorSummary message={snapshotsError} />}
      <SnapshotPanel
        snapshots={snapshots}
        selectedId={selectedSnapshotId}
        onSelect={setSelectedSnapshotId}
        disabled={localControlsLocked}
      />
      {snapshotError && <ErrorSummary message={snapshotError} />}
      {!snapshot && selectedSnapshotId && !snapshotError && (
        <LoadingState>Reading selected immutable snapshot…</LoadingState>
      )}
      {snapshot && (
        <section aria-labelledby="snapshot-detail-title">
          <h2 id="snapshot-detail-title">Selected immutable snapshot</h2>
          <dl>
            <dt>Snapshot</dt>
            <dd>
              <code>{snapshot.snapshot.id}</code>
            </dd>
            <dt>Sequence</dt>
            <dd>{snapshot.snapshot.sequence}</dd>
            <dt>Group</dt>
            <dd>
              <code>{snapshot.snapshot.group_id}</code>
            </dd>
            <dt>Segment</dt>
            <dd>
              <code>{snapshot.snapshot.segment_id ?? "none"}</code>
            </dd>
            <dt>Content hash</dt>
            <dd>
              <code>{snapshot.snapshot.content_hash}</code>
            </dd>
            <dt>Created</dt>
            <dd>{snapshot.snapshot.created_at}</dd>
          </dl>
          {kind === "diagnostic" ? (
            presentedSummary ? (
              <>
                <h3>Observed request-order sensitivity</h3>
                <p>
                  {presentedSummary.independentCases} cases ·{" "}
                  {presentedSummary.orders} orders ·{" "}
                  {presentedSummary.expandedResults} expanded results ·{" "}
                  {presentedSummary.fullyObservedCases} fully observed
                </p>
                <p>
                  Disagreement: {presentedSummary.disagreement.numerator}/
                  {presentedSummary.disagreement.denominator} ·{" "}
                  {presentedSummary.disagreement.value ??
                    presentedSummary.disagreement.reason}
                </p>
                <ol>
                  {presentedSummary.cases.map((item) => (
                    <li key={item.caseId}>
                      <code>{item.caseId}</code> · {item.statuses.join(", ")} ·{" "}
                      {item.disagreed ? "disagreed" : "agreed"} · options{" "}
                      {item.options
                        .map((value) => value ?? "no answer")
                        .join(" → ")}
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <p>
                Diagnostic summary is unavailable or has an unexpected shape.
              </p>
            )
          ) : (
            <>
              <h3>Frozen regression cases</h3>
              <p>
                {"expectation_failures" in snapshot
                  ? snapshot.expectation_failures
                  : "0"}{" "}
                expectation failures · baseline unavailable:{" "}
                {"baseline_unavailable" in snapshot
                  ? snapshot.baseline_unavailable.replaceAll("_", " ")
                  : "reason unavailable"}
              </p>
              <ol>
                {"cases" in snapshot &&
                  snapshot.cases.map((item) => (
                    <li
                      key={`${item.regression_id}:${item.run_id}:${item.result_snapshot_id}`}
                    >
                      <p>
                        <strong>{item.case_id}</strong> · {item.status} ·{" "}
                        {item.passed === null
                          ? "not evaluated"
                          : item.passed
                            ? "passed"
                            : "failed"}
                      </p>
                      <p>{item.reason}</p>
                      <p>
                        Frozen input <code>{item.input_hash}</code> · source
                        result{" "}
                        <code>
                          {item.source_result_snapshot_id ?? "unavailable"}
                        </code>
                      </p>
                    </li>
                  ))}
              </ol>
            </>
          )}
          <h3>Frozen member context</h3>
          <ol>
            {snapshot.members.map((member) => (
              <li key={`${member.run_id}:${member.result_snapshot_id}`}>
                <p>
                  Run{" "}
                  <button
                    type="button"
                    className="text-button"
                    disabled={localControlsLocked || hasUnresolvedMutation()}
                    onClick={() => openMember(member.run_id)}
                  >
                    <code>{member.run_id}</code>
                  </button>{" "}
                  · result <code>{member.result_snapshot_id}</code>
                </p>
                <p>
                  Decision <code>{member.decision_id}</code> revision{" "}
                  <code>{member.decision_revision_id}</code> definition{" "}
                  <code>{member.decision_definition_hash}</code>
                </p>
                <p>
                  Dataset <code>{member.dataset_id}</code> snapshot{" "}
                  <code>{member.dataset_snapshot_id}</code> content{" "}
                  <code>{member.dataset_content_hash}</code>
                </p>
                <p>
                  Label snapshot <code>{member.label_snapshot_id}</code> content{" "}
                  <code>{member.label_content_hash}</code>
                </p>
                <p>
                  Result content <code>{member.result_content_hash}</code>{" "}
                  through event <code>{member.through_event_sequence}</code>
                </p>
              </li>
            ))}
          </ol>
          {onReport && (
            <button
              type="button"
              disabled={localControlsLocked || hasUnresolvedMutation()}
              onClick={() => reportSnapshot(snapshot.snapshot.id)}
            >
              Create report from this snapshot
            </button>
          )}
        </section>
      )}
    </main>
  );
}

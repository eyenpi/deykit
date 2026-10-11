import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { safeMessage } from "../../api/client";
import type {
  ApiDownload,
  ApiOperationBody,
  ApiOperationData,
} from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type {
  DebuggingGateway,
  ExecutionGateway,
} from "../../workspace/gateway";
import type { GroupReportTarget } from "./groups/GroupDetail";
import { useRenderedScopeEpoch } from "./useRenderedScopeEpoch";

type Report = ApiOperationData<"readReport">;
type CreateBody = ApiOperationBody<"createReport">;
type ReportTarget =
  "run" | "evaluation" | "comparison" | "diagnostic" | "check";
type VerifiedTarget = {
  kind: ReportTarget;
  id: string;
  runId?: string;
  evaluationId?: string;
  resultSnapshotId?: string;
  labelSnapshotId?: string;
  groupSnapshotId?: string;
  content: string;
};
type ReportIntent = {
  registrationId: string;
  kind: ReportTarget;
  id: string;
  groupSnapshotId?: string;
  body: CreateBody;
  scopeEpoch: number;
  operations: DebuggingGateway["reports"];
};

function reportContext(report: Report): string {
  return [
    `Target ${report.target_kind ?? "Unavailable"}: ${report.target_id ?? "Unavailable"}`,
    `Evaluations: ${report.evaluation_ids.join(", ") || "None"}`,
    `Results: ${report.result_snapshot_ids.join(", ") || "None"}`,
    `Labels: ${report.label_snapshot_ids.join(", ") || "None"}`,
    `Diagnostic snapshot: ${report.diagnostic_snapshot_id ?? "None"}`,
    `Check snapshot: ${report.check_snapshot_id ?? "None"}`,
    `Evidence modes: ${report.evidence_modes.join(", ") || "Unavailable"}`,
  ].join("\n");
}

export function ReportList({
  registrationId,
  debugging,
  execution,
  navigation,
}: {
  registrationId: string;
  debugging: DebuggingGateway;
  execution: ExecutionGateway;
  navigation: WorkspaceNavigation;
}) {
  const [items, setItems] = useState<readonly Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [createOpen, setCreateOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(undefined);
    void debugging.reports
      .list({
        registrationId,
        query: { limit: 50 },
        signal: controller.signal,
      })
      .then((result) => {
        if (active) setItems(result.data.items);
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted) setError(safeMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [debugging.reports, refreshToken, registrationId]);

  return (
    <article className="document">
      <div className="document-title-row">
        <h1>Saved reports</h1>
        <button type="button" onClick={() => setCreateOpen(true)}>
          Create report from verified target
        </button>
      </div>
      <p>
        Reports preserve the exact selected evidence boundary. Raw inputs,
        requests, and responses start disabled.
      </p>
      {error && (
        <ErrorSummary
          message={error}
          retry={() => setRefreshToken((value) => value + 1)}
        />
      )}
      {loading ? <LoadingState>Loading saved reports…</LoadingState> : null}
      {!loading && items.length === 0 ? (
        <p className="muted">No saved reports.</p>
      ) : null}
      {items.length > 0 && (
        <ul aria-label="Saved reports">
          {items.map((item) => (
            <li key={item.report_id}>
              <button
                type="button"
                onClick={() =>
                  void navigation.navigate({
                    kind: "report",
                    registrationId,
                    reportId: item.report_id,
                  })
                }
              >
                {item.target_kind ?? "Unavailable target"}:{" "}
                {item.target_id ?? item.report_id}
              </button>
              <p className="muted">
                {item.created_at} · report <code>{item.report_id}</code> ·
                content hash <code>{item.content_hash}</code>
              </p>
            </li>
          ))}
        </ul>
      )}
      {createOpen && (
        <ReportSheet
          registrationId={registrationId}
          debugging={debugging}
          execution={execution}
          navigation={navigation}
          onClose={() => setCreateOpen(false)}
          onCreated={(reportId) => {
            setCreateOpen(false);
            setRefreshToken((value) => value + 1);
            void navigation.navigate({
              kind: "report",
              registrationId,
              reportId,
            });
          }}
        />
      )}
    </article>
  );
}

export function ReportSheet({
  registrationId,
  debugging,
  execution,
  navigation,
  onClose,
  onCreated,
  initialTarget,
}: {
  registrationId: string;
  debugging: DebuggingGateway;
  execution: ExecutionGateway;
  navigation: WorkspaceNavigation;
  onClose: () => void;
  onCreated: (reportId: string) => void;
  initialTarget?: GroupReportTarget;
}) {
  const [kind, setKind] = useState<ReportTarget>(
    initialTarget?.targetKind ?? "run",
  );
  const [targetId, setTargetId] = useState(initialTarget?.targetId ?? "");
  const [verified, setVerified] = useState<VerifiedTarget>();
  const scopeEpoch = useRenderedScopeEpoch(
    `${registrationId}|${kind}|${targetId}|${initialTarget?.groupSnapshotId ?? ""}`,
  );
  const scopeEpochRef = useRef(scopeEpoch);
  scopeEpochRef.current = scopeEpoch;
  const [rawInputs, setRawInputs] = useState(false);
  const [rawRequests, setRawRequests] = useState(false);
  const [rawResponses, setRawResponses] = useState(false);
  const [checkingView, setCheckingView] = useState({
    scopeEpoch,
    value: false,
  });
  const checking = checkingView.scopeEpoch === scopeEpoch && checkingView.value;
  const [error, setError] = useState<string>();
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [view, setView] = useState<{
    scopeEpoch: number;
    state: MutationState<Report>;
  }>({ scopeEpoch, state: { kind: "idle" } });
  const mutation = useRef<RetainedMutation<ReportIntent, Report> | undefined>(
    undefined,
  );
  if (!mutation.current) {
    mutation.current = new RetainedMutation(
      async (intent) => {
        const result = await intent.operations.create({
          registrationId: intent.registrationId,
          body: intent.body,
        });
        if (
          result.data.target_kind !== intent.kind ||
          result.data.target_id !== intent.id ||
          (intent.body.evaluation_id !== undefined &&
            intent.body.evaluation_id !== null &&
            !result.data.evaluation_ids.includes(intent.body.evaluation_id)) ||
          (intent.body.result_snapshot_id !== undefined &&
            intent.body.result_snapshot_id !== null &&
            !result.data.result_snapshot_ids.includes(
              intent.body.result_snapshot_id,
            )) ||
          (intent.kind === "diagnostic" &&
            result.data.diagnostic_snapshot_id !== intent.groupSnapshotId) ||
          (intent.kind === "check" &&
            result.data.check_snapshot_id !== intent.groupSnapshotId) ||
          ((intent.kind === "run" ||
            intent.kind === "evaluation" ||
            intent.kind === "comparison") &&
            intent.groupSnapshotId !== undefined)
        )
          throw new Error(
            "The report receipt does not match the verified target.",
          );
        return result.data;
      },
      (next) => {
        const owner = mutation.current?.originalRequest;
        if (owner) setView({ scopeEpoch: owner.scopeEpoch, state: next });
      },
    );
  }
  const state =
    view.scopeEpoch === scopeEpoch ? view.state : { kind: "idle" as const };
  const mutationKind = mutation.current.state.kind;
  const retainedOwner = mutation.current.originalRequest;
  const retainedViewStale =
    retainedOwner !== undefined && retainedOwner.scopeEpoch !== scopeEpoch;
  const busy =
    mutationKind === "submitting" || mutationKind === "outcome-unknown";
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const dirty =
    state.kind !== "committed" &&
    (targetId.length > 0 || rawInputs || rawRequests || rawResponses);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: dirty || busy,
    isDirtyNow: () => dirtyRef.current || busyRef.current,
    save: async () => {
      throw new Error(
        "Verify the report target and create the report before leaving.",
      );
    },
    discard: () => {
      if (!busyRef.current) {
        setTargetId("");
        setVerified(undefined);
        setRawInputs(false);
        setRawRequests(false);
        setRawResponses(false);
        onClose();
      }
    },
    blockedMessage: busy
      ? "The report request may have been saved. Retry the original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(`${registrationId}:report:create`, guard),
    [guard, navigation, registrationId],
  );

  async function verifyTarget() {
    const id = targetId.trim();
    if (!id || busy) return;
    setCheckingView({ scopeEpoch, value: true });
    setError(undefined);
    setVerified(undefined);
    const epoch = scopeEpochRef.current;
    try {
      if (kind === "run") {
        const result = await execution.runs.read({ registrationId, runId: id });
        const run = result.data;
        if (run.run_id !== id || !run.latest_result_snapshot_id)
          throw new Error(
            "This run has no verified result snapshot to report.",
          );
        if (epoch !== scopeEpochRef.current) return;
        setVerified({
          kind,
          id,
          runId: run.run_id,
          resultSnapshotId: run.latest_result_snapshot_id,
          content: `Run ${run.run_id}\nResult ${run.latest_result_snapshot_id}\nEvidence mode ${run.sources.evidence_mode ?? "Unavailable"}`,
        });
      } else if (kind === "evaluation") {
        const result = await execution.inspection.readEvaluation({
          registrationId,
          evaluationId: id,
        });
        const evaluation = result.data;
        if (evaluation.evaluation_id !== id)
          throw new Error("The service returned a different saved evaluation.");
        if (epoch !== scopeEpochRef.current) return;
        setVerified({
          kind,
          id,
          runId: evaluation.run_id,
          evaluationId: evaluation.evaluation_id,
          resultSnapshotId: evaluation.result_snapshot_id,
          labelSnapshotId: evaluation.label_snapshot_id,
          content: `Evaluation ${evaluation.evaluation_id}\nRun ${evaluation.run_id}\nResult ${evaluation.result_snapshot_id}\nLabels ${evaluation.label_snapshot_id}\nMode ${evaluation.mode}`,
        });
      } else if (kind === "comparison") {
        const result = await debugging.comparisons.read({
          registrationId,
          comparisonId: id,
        });
        const comparison = result.data;
        if (comparison.comparison_id !== id)
          throw new Error("The service returned a different saved comparison.");
        if (epoch !== scopeEpochRef.current) return;
        setVerified({
          kind,
          id,
          content: `Comparison ${comparison.comparison_id}\nLeft evaluation ${comparison.left_evaluation_id}\nLeft result ${comparison.left_result_snapshot_id}\nRight evaluation ${comparison.right_evaluation_id}\nRight result ${comparison.right_result_snapshot_id}`,
        });
      } else {
        if (
          !initialTarget ||
          !initialTarget.groupSnapshotId ||
          initialTarget.targetKind !== kind ||
          initialTarget.targetId !== id
        )
          throw new Error(
            "The report target is missing its pinned group snapshot.",
          );
        const groupSnapshotId = initialTarget.groupSnapshotId;
        const request = {
          registrationId,
          groupId: id,
          snapshotId: groupSnapshotId,
        };
        const result =
          kind === "diagnostic"
            ? await debugging.diagnostics.readSnapshot(request)
            : await debugging.checks.readSnapshot(request);
        if (
          result.data.snapshot.group_id !== id ||
          result.data.snapshot.id !== groupSnapshotId
        )
          throw new Error("The service returned a different group snapshot.");
        if (epoch !== scopeEpochRef.current) return;
        setVerified({
          kind,
          id,
          groupSnapshotId,
          content: `${kind === "diagnostic" ? "Diagnostic" : "Check"} ${id}\nSnapshot ${groupSnapshotId}\nContent hash ${result.data.snapshot.content_hash}`,
        });
      }
    } catch (cause) {
      if (epoch === scopeEpochRef.current) setError(safeMessage(cause));
    } finally {
      if (epoch === scopeEpochRef.current)
        setCheckingView({ scopeEpoch: epoch, value: false });
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (
      !verified ||
      busy ||
      verified.id !== targetId.trim() ||
      verified.kind !== kind
    )
      return;
    const body: CreateBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      target_kind: verified.kind,
      target_id: verified.id,
      ...(verified.evaluationId
        ? { evaluation_id: verified.evaluationId }
        : {}),
      ...(verified.resultSnapshotId
        ? { result_snapshot_id: verified.resultSnapshotId }
        : {}),
      ...(verified.groupSnapshotId
        ? { group_snapshot_id: verified.groupSnapshotId }
        : {}),
      raw: {
        inputs: rawInputs,
        requests: rawRequests,
        responses: rawResponses,
      },
    };
    const epoch = scopeEpochRef.current;
    const receipt = await mutation.current?.submit({
      registrationId,
      kind: verified.kind,
      id: verified.id,
      ...(verified.groupSnapshotId
        ? { groupSnapshotId: verified.groupSnapshotId }
        : {}),
      body,
      scopeEpoch: epoch,
      operations: debugging.reports,
    });
    if (receipt && epoch === scopeEpochRef.current)
      onCreated(receipt.report_id);
  }

  async function retryOriginal() {
    const owner = mutation.current?.originalRequest;
    const receipt = await mutation.current?.retryOriginal();
    if (receipt && owner?.scopeEpoch === scopeEpochRef.current)
      onCreated(receipt.report_id);
  }

  function resetKnown() {
    mutation.current?.reset();
    setView({ scopeEpoch, state: { kind: "idle" } });
  }

  return (
    <Modal
      title="Create a pinned report"
      sheet
      onDismiss={() => {
        if (!busy && !dirty) onClose();
      }}
    >
      <form className="modal-body" onSubmit={(event) => void create(event)}>
        <p>
          Verify the selected resource first. This report uses its actual saved
          identity and result boundary.
        </p>
        <label className="field">
          Target kind
          <select
            value={kind}
            disabled={!!initialTarget || busy || state.kind === "committed"}
            onChange={(event) => {
              const value = event.currentTarget.value;
              if (
                value === "run" ||
                value === "evaluation" ||
                value === "comparison" ||
                value === "diagnostic" ||
                value === "check"
              )
                setKind(value);
              setVerified(undefined);
            }}
          >
            <option value="run">Run</option>
            <option value="evaluation">Saved evaluation</option>
            <option value="comparison">Saved comparison</option>
            {initialTarget?.targetKind === "diagnostic" && (
              <option value="diagnostic">Diagnostic snapshot</option>
            )}
            {initialTarget?.targetKind === "check" && (
              <option value="check">Regression check snapshot</option>
            )}
          </select>
        </label>
        <label className="field">
          Target ID
          <input
            value={targetId}
            disabled={!!initialTarget || busy || state.kind === "committed"}
            onChange={(event) => {
              setTargetId(event.currentTarget.value);
              setVerified(undefined);
            }}
          />
        </label>
        <button
          type="button"
          disabled={checking || busy || state.kind === "committed"}
          onClick={() => void verifyTarget()}
        >
          {checking ? "Verifying target…" : "Verify saved target"}
        </button>
        {verified && (
          <pre aria-label="Verified report target">{verified.content}</pre>
        )}
        <fieldset disabled={busy || state.kind === "committed"}>
          <legend>Raw source options (each off by default)</legend>
          <label>
            <input
              type="checkbox"
              checked={rawInputs}
              onChange={(event) => setRawInputs(event.currentTarget.checked)}
            />{" "}
            Include raw inputs
          </label>
          <label>
            <input
              type="checkbox"
              checked={rawRequests}
              onChange={(event) => setRawRequests(event.currentTarget.checked)}
            />{" "}
            Include raw requests
          </label>
          <label>
            <input
              type="checkbox"
              checked={rawResponses}
              onChange={(event) => setRawResponses(event.currentTarget.checked)}
            />{" "}
            Include raw responses
          </label>
        </fieldset>
        {error && <ErrorSummary message={error} />}
        {(state.kind === "failed" ||
          state.kind === "conflict" ||
          state.kind === "outcome-unknown") && (
          <ErrorSummary message={state.message} />
        )}
        {retainedViewStale && mutationKind === "outcome-unknown" && (
          <section role="status">
            <p>
              An earlier report request is unresolved and can only be retried
              unchanged.
            </p>
            <button type="button" onClick={() => void retryOriginal()}>
              Retry original unchanged report
            </button>
          </section>
        )}
        {retainedViewStale && mutationKind === "committed" && (
          <button type="button" onClick={resetKnown}>
            Start a new report for this view
          </button>
        )}
        {(state.kind === "failed" || state.kind === "conflict") && (
          <button
            type="button"
            onClick={() => {
              mutation.current?.reset();
              setView({ scopeEpoch, state: { kind: "idle" } });
              setVerified(undefined);
            }}
          >
            Verify a new report request
          </button>
        )}
        {state.kind === "committed" && (
          <p role="status">
            Report <code>{state.receipt.report_id}</code> is saved. The report
            list/detail is a separate read.
          </p>
        )}
        <div className="actions">
          <button
            type="submit"
            disabled={!verified || busy || state.kind === "committed"}
          >
            Create report
          </button>
          {state.kind === "outcome-unknown" && (
            <button type="button" onClick={() => void retryOriginal()}>
              Retry original unchanged report
            </button>
          )}
          {state.kind === "committed" && (
            <button type="button" onClick={resetKnown}>
              Create another report
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (dirty) setConfirmDiscard(true);
              else onClose();
            }}
          >
            Close
          </button>
        </div>
        {confirmDiscard && (
          <section role="alert" aria-label="Discard report proposal">
            <p>Discard the verified report target and raw source choices?</p>
            <div className="actions">
              <button type="button" onClick={onClose}>
                Discard proposal
              </button>
              <button type="button" onClick={() => setConfirmDiscard(false)}>
                Keep editing
              </button>
            </div>
          </section>
        )}
      </form>
      {prompt}
    </Modal>
  );
}

export function ReportPage({
  registrationId,
  reportId,
  operations,
}: {
  registrationId: string;
  reportId: string;
  operations: DebuggingGateway["reports"];
}) {
  const scopeKey = `${registrationId}|${reportId}`;
  const [refreshToken, setRefreshToken] = useState(0);
  const renderedIdentity = useRef({
    scopeKey,
    operations,
    refreshToken: 0,
    epoch: 0,
  });
  if (
    renderedIdentity.current.scopeKey !== scopeKey ||
    renderedIdentity.current.operations !== operations ||
    renderedIdentity.current.refreshToken !== refreshToken
  )
    renderedIdentity.current = {
      scopeKey,
      operations,
      refreshToken,
      epoch: renderedIdentity.current.epoch + 1,
    };
  const scopeEpoch = renderedIdentity.current.epoch;
  const scopeEpochRef = useRef(scopeEpoch);
  scopeEpochRef.current = scopeEpoch;
  const [metadata, setMetadata] = useState<{
    scopeEpoch: number;
    report?: Report;
    loading: boolean;
    error?: string;
  }>({ scopeEpoch, loading: true });
  const currentMetadata: typeof metadata =
    metadata.scopeEpoch === scopeEpoch
      ? metadata
      : { scopeEpoch, loading: true };
  const report = currentMetadata.report;
  const loading = currentMetadata.loading;
  const error = currentMetadata.error;
  const [format, setFormat] = useState<"json" | "markdown">("json");
  type ReportByteView = {
    scopeEpoch: number;
    ticket: number;
    busy: boolean;
    format?: "json" | "markdown";
    preview?: string;
    download?: ApiDownload;
    notice?: string;
  };
  const [byteView, setByteView] = useState<ReportByteView>({
    scopeEpoch,
    ticket: 0,
    busy: false,
  });
  const currentByteView: ReportByteView =
    byteView.scopeEpoch === scopeEpoch
      ? byteView
      : { scopeEpoch, ticket: 0, busy: false };
  const downloading = currentByteView.busy;
  const downloadTicket = useRef(0);
  const mounted = useRef(false);
  const activeDownload = useRef<
    | {
        scopeEpoch: number;
        ticket: number;
        controller: AbortController;
      }
    | undefined
  >(undefined);
  const objectUrl = useRef<
    { url: string; scopeEpoch: number; ticket: number } | undefined
  >(undefined);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function revokeObjectUrl(epoch?: number) {
    const current = objectUrl.current;
    if (!current || (epoch !== undefined && current.scopeEpoch !== epoch))
      return;
    URL.revokeObjectURL(current.url);
    objectUrl.current = undefined;
  }

  useEffect(() => {
    const epoch = scopeEpoch;
    const sourceOperations = operations;
    const controller = new AbortController();
    let active = true;
    downloadTicket.current += 1;
    setByteView({
      scopeEpoch: epoch,
      ticket: downloadTicket.current,
      busy: false,
    });
    setMetadata({ scopeEpoch: epoch, loading: true });
    const queuedDownload = activeDownload.current;
    if (queuedDownload) {
      queuedDownload.controller.abort();
      activeDownload.current = undefined;
    }
    void sourceOperations
      .read({ registrationId, reportId, signal: controller.signal })
      .then((result) => {
        if (result.data.report_id !== reportId)
          throw new Error("The service returned a different report.");
        if (active && epoch === scopeEpochRef.current)
          setMetadata({
            scopeEpoch: epoch,
            report: result.data,
            loading: false,
          });
      })
      .catch((cause: unknown) => {
        if (
          active &&
          epoch === scopeEpochRef.current &&
          !controller.signal.aborted
        )
          setMetadata({
            scopeEpoch: epoch,
            loading: false,
            error: safeMessage(cause),
          });
      })
      .finally(() => {
        if (active && epoch === scopeEpochRef.current)
          setMetadata((previous) =>
            previous.scopeEpoch === epoch
              ? { ...previous, loading: false }
              : previous,
          );
      });
    return () => {
      active = false;
      controller.abort();
      const currentDownload = activeDownload.current;
      if (currentDownload?.scopeEpoch === epoch) {
        currentDownload.controller.abort();
        activeDownload.current = undefined;
      }
      const currentUrl = objectUrl.current;
      if (currentUrl?.scopeEpoch === epoch) {
        URL.revokeObjectURL(currentUrl.url);
        objectUrl.current = undefined;
      }
    };
  }, [operations, refreshToken, registrationId, reportId, scopeEpoch]);

  async function loadBytes(save: boolean) {
    const epoch = scopeEpoch;
    const requestedFormat = format;
    const sourceOperations = operations;
    const ticket = ++downloadTicket.current;
    const controller = new AbortController();
    activeDownload.current = { scopeEpoch: epoch, ticket, controller };
    const isCurrent = () =>
      mounted.current &&
      scopeEpochRef.current === epoch &&
      downloadTicket.current === ticket;
    setByteView({ ...currentByteView, scopeEpoch: epoch, ticket, busy: true });
    setMetadata((previous) =>
      previous.scopeEpoch === epoch
        ? { ...previous, error: undefined }
        : previous,
    );
    try {
      const bytes = await sourceOperations.download({
        registrationId,
        reportId,
        query: { format: requestedFormat },
        signal: controller.signal,
      });
      const text = await bytes.blob.text();
      if (!isCurrent()) return;
      revokeObjectUrl();
      if (save) {
        const url = URL.createObjectURL(bytes.blob);
        objectUrl.current = { url, scopeEpoch: epoch, ticket };
        window.setTimeout(() => {
          const current = objectUrl.current;
          if (
            current?.url === url &&
            current.scopeEpoch === epoch &&
            current.ticket === ticket
          )
            revokeObjectUrl(epoch);
        }, 0);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = bytes.filename;
        anchor.rel = "noopener";
        anchor.click();
      }
      setByteView((previous) =>
        previous.scopeEpoch === epoch && previous.ticket === ticket
          ? {
              ...previous,
              format: requestedFormat,
              preview: text,
              download: bytes,
              notice: save ? `Download started: ${bytes.filename}` : undefined,
            }
          : previous,
      );
    } catch (cause) {
      if (isCurrent())
        setMetadata((previous) =>
          previous.scopeEpoch === epoch
            ? { ...previous, error: safeMessage(cause) }
            : previous,
        );
    } finally {
      if (activeDownload.current?.ticket === ticket)
        activeDownload.current = undefined;
      if (isCurrent())
        setByteView((previous) =>
          previous.scopeEpoch === epoch && previous.ticket === ticket
            ? { ...previous, busy: false }
            : previous,
        );
    }
  }

  return (
    <article className="document">
      <h1>Saved report</h1>
      {loading ? <LoadingState>Loading report metadata…</LoadingState> : null}
      {error && (
        <ErrorSummary
          message={error}
          retry={() => {
            if (report) void loadBytes(false);
            else setRefreshToken((value) => value + 1);
          }}
        />
      )}
      {report && (
        <>
          <p>
            Report <code>{report.report_id}</code>; content hash{" "}
            <code>{report.content_hash}</code>; saved {report.created_at}.
          </p>
          <pre aria-label="Pinned report identity">{reportContext(report)}</pre>
          {report.legacy && (
            <p className="warning-summary">This report is a legacy record.</p>
          )}
          {report.nonexportable_reason && (
            <p className="warning-summary">
              Export unavailable: {report.nonexportable_reason}
            </p>
          )}
          <label className="field">
            Download format
            <select
              value={format}
              disabled={downloading}
              onChange={(event) => {
                const value = event.currentTarget.value;
                if (value === "json" || value === "markdown") {
                  revokeObjectUrl();
                  setFormat(value);
                  setByteView({
                    scopeEpoch,
                    ticket: downloadTicket.current,
                    busy: false,
                  });
                }
              }}
            >
              <option value="json">JSON bytes</option>
              <option value="markdown">Markdown bytes</option>
            </select>
          </label>
          <div className="actions">
            <button
              type="button"
              disabled={downloading || !!report.nonexportable_reason}
              onClick={() => void loadBytes(false)}
            >
              {downloading ? "Reading report bytes…" : "Preview report bytes"}
            </button>
            <button
              type="button"
              disabled={downloading || !!report.nonexportable_reason}
              onClick={() => void loadBytes(true)}
            >
              Download {format === "json" ? "JSON" : "Markdown"}
            </button>
          </div>
          {currentByteView.download && currentByteView.format && (
            <p role="status">
              Read {currentByteView.download.blob.size} report bytes as{" "}
              {currentByteView.format}; filename{" "}
              {currentByteView.download.filename}.
            </p>
          )}
          {currentByteView.notice && (
            <p role="status">{currentByteView.notice}</p>
          )}
          {currentByteView.preview !== undefined && (
            <section>
              <h2>Inert text preview</h2>
              <pre className="source-editor" aria-label="Report text preview">
                {currentByteView.preview}
              </pre>
            </section>
          )}
        </>
      )}
    </article>
  );
}

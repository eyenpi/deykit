import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { safeMessage } from "../../api/client";
import type { ApiDownload, ApiOperationBody, ApiOperationData } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway, ExecutionGateway } from "../../workspace/gateway";
import type { GroupReportTarget } from "./groups/GroupDetail";

type Report = ApiOperationData<"readReport">;
type CreateBody = ApiOperationBody<"createReport">;
type ReportTarget = "run" | "evaluation" | "comparison" | "diagnostic" | "check";
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
    void debugging.reports.list({
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
      <p>Reports preserve the exact selected evidence boundary. Raw inputs, requests, and responses start disabled.</p>
      {error && <ErrorSummary message={error} retry={() => setRefreshToken((value) => value + 1)} />}
      {loading ? <LoadingState>Loading saved reports…</LoadingState> : null}
      {!loading && items.length === 0 ? <p className="muted">No saved reports.</p> : null}
      {items.length > 0 && (
        <ul aria-label="Saved reports">
          {items.map((item) => (
            <li key={item.report_id}>
              <button
                type="button"
                onClick={() => void navigation.navigate({
                  kind: "report",
                  registrationId,
                  reportId: item.report_id,
                })}
              >
                {item.target_kind ?? "Unavailable target"}: {item.target_id ?? item.report_id}
              </button>
              <p className="muted">
                {item.created_at} · report <code>{item.report_id}</code> · content hash{" "}
                <code>{item.content_hash}</code>
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
            void navigation.navigate({ kind: "report", registrationId, reportId });
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
  const [kind, setKind] = useState<ReportTarget>(initialTarget?.targetKind ?? "run");
  const [targetId, setTargetId] = useState(initialTarget?.targetId ?? "");
  const [verified, setVerified] = useState<VerifiedTarget>();
  const [rawInputs, setRawInputs] = useState(false);
  const [rawRequests, setRawRequests] = useState(false);
  const [rawResponses, setRawResponses] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string>();
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [state, setState] = useState<MutationState<Report>>({ kind: "idle" });
  const mutation = useRef<RetainedMutation<ReportIntent, Report> | undefined>(undefined);
  if (!mutation.current) {
    mutation.current = new RetainedMutation(async (intent) => {
      const result = await debugging.reports.create({
        registrationId: intent.registrationId,
        body: intent.body,
      });
      if (
        result.data.target_kind !== intent.kind ||
        result.data.target_id !== intent.id ||
        (intent.kind === "diagnostic" &&
          result.data.diagnostic_snapshot_id !== intent.groupSnapshotId) ||
        (intent.kind === "check" &&
          result.data.check_snapshot_id !== intent.groupSnapshotId) ||
        ((intent.kind === "run" || intent.kind === "evaluation" || intent.kind === "comparison") &&
          intent.groupSnapshotId !== undefined)
      )
        throw new Error("The report receipt does not match the verified target.");
      return result.data;
    }, setState);
  }
  const busy = state.kind === "submitting" || state.kind === "outcome-unknown";
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
      throw new Error("Verify the report target and create the report before leaving.");
    },
    discard: () => {
      if (!busyRef.current) {
        setTargetId("");
        setVerified(undefined);
        setRawInputs(false);
        setRawRequests(false);
        setRawResponses(false);
      }
    },
    blockedMessage: busy
      ? "The report request may have been saved. Retry the original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () => navigation.registerDirtyGuard(`${registrationId}:report:create`, guard),
    [guard, navigation, registrationId],
  );

  async function verifyTarget() {
    const id = targetId.trim();
    if (!id || busy) return;
    setChecking(true);
    setError(undefined);
    setVerified(undefined);
    try {
      if (kind === "run") {
        const result = await execution.runs.read({ registrationId, runId: id });
        const run = result.data;
        if (run.run_id !== id || !run.latest_result_snapshot_id)
          throw new Error("This run has no verified result snapshot to report.");
        setVerified({
          kind,
          id,
          runId: run.run_id,
          resultSnapshotId: run.latest_result_snapshot_id,
          content: `Run ${run.run_id}\nResult ${run.latest_result_snapshot_id}\nEvidence mode ${run.sources.evidence_mode ?? "Unavailable"}`,
        });
      } else if (kind === "evaluation") {
        const result = await execution.inspection.readEvaluation({ registrationId, evaluationId: id });
        const evaluation = result.data;
        if (evaluation.evaluation_id !== id)
          throw new Error("The service returned a different saved evaluation.");
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
        const result = await debugging.comparisons.read({ registrationId, comparisonId: id });
        const comparison = result.data;
        if (comparison.comparison_id !== id)
          throw new Error("The service returned a different saved comparison.");
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
          throw new Error("The report target is missing its pinned group snapshot.");
        const groupSnapshotId = initialTarget.groupSnapshotId;
        const request = { registrationId, groupId: id, snapshotId: groupSnapshotId };
        const result = kind === "diagnostic"
          ? await debugging.diagnostics.readSnapshot(request)
          : await debugging.checks.readSnapshot(request);
        if (
          result.data.snapshot.group_id !== id ||
          result.data.snapshot.id !== groupSnapshotId
        )
          throw new Error("The service returned a different group snapshot.");
        setVerified({
          kind,
          id,
          groupSnapshotId,
          content: `${kind === "diagnostic" ? "Diagnostic" : "Check"} ${id}\nSnapshot ${groupSnapshotId}\nContent hash ${result.data.snapshot.content_hash}`,
        });
      }
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setChecking(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!verified || busy || verified.id !== targetId.trim() || verified.kind !== kind) return;
    const body: CreateBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      target_kind: verified.kind,
      target_id: verified.id,
      ...(verified.evaluationId ? { evaluation_id: verified.evaluationId } : {}),
      ...(verified.resultSnapshotId ? { result_snapshot_id: verified.resultSnapshotId } : {}),
      ...(verified.groupSnapshotId ? { group_snapshot_id: verified.groupSnapshotId } : {}),
      raw: {
        inputs: rawInputs,
        requests: rawRequests,
        responses: rawResponses,
      },
    };
    const receipt = await mutation.current?.submit({
      registrationId,
      kind: verified.kind,
      id: verified.id,
      ...(verified.groupSnapshotId ? { groupSnapshotId: verified.groupSnapshotId } : {}),
      body,
    });
    if (receipt) onCreated(receipt.report_id);
  }

  async function retryOriginal() {
    const receipt = await mutation.current?.retryOriginal();
    if (receipt) onCreated(receipt.report_id);
  }

  function resetKnown() {
    mutation.current?.reset();
    setState({ kind: "idle" });
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
        <p>Verify the selected resource first. This report uses its actual saved identity and result boundary.</p>
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
        <button type="button" disabled={checking || busy || state.kind === "committed"} onClick={() => void verifyTarget()}>
          {checking ? "Verifying target…" : "Verify saved target"}
        </button>
        {verified && <pre aria-label="Verified report target">{verified.content}</pre>}
        <fieldset disabled={busy || state.kind === "committed"}>
          <legend>Raw source options (each off by default)</legend>
          <label><input type="checkbox" checked={rawInputs} onChange={(event) => setRawInputs(event.currentTarget.checked)} /> Include raw inputs</label>
          <label><input type="checkbox" checked={rawRequests} onChange={(event) => setRawRequests(event.currentTarget.checked)} /> Include raw requests</label>
          <label><input type="checkbox" checked={rawResponses} onChange={(event) => setRawResponses(event.currentTarget.checked)} /> Include raw responses</label>
        </fieldset>
        {error && <ErrorSummary message={error} />}
        {(state.kind === "failed" || state.kind === "conflict" || state.kind === "outcome-unknown") && <ErrorSummary message={state.message} />}
        {(state.kind === "failed" || state.kind === "conflict") && (
          <button
            type="button"
            onClick={() => {
              mutation.current?.reset();
              setState({ kind: "idle" });
              setVerified(undefined);
            }}
          >
            Verify a new report request
          </button>
        )}
        {state.kind === "committed" && (
          <p role="status">Report <code>{state.receipt.report_id}</code> is saved. The report list/detail is a separate read.</p>
        )}
        <div className="actions">
          <button type="submit" disabled={!verified || busy || state.kind === "committed"}>Create report</button>
          {state.kind === "outcome-unknown" && <button type="button" onClick={() => void retryOriginal()}>Retry original unchanged report</button>}
          {state.kind === "committed" && <button type="button" onClick={resetKnown}>Create another report</button>}
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
              <button type="button" onClick={onClose}>Discard proposal</button>
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
  const [report, setReport] = useState<Report>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [refreshToken, setRefreshToken] = useState(0);
  const [format, setFormat] = useState<"json" | "markdown">("json");
  const [preview, setPreview] = useState<string>();
  const [download, setDownload] = useState<ApiDownload>();
  const [downloading, setDownloading] = useState(false);
  const [downloadNotice, setDownloadNotice] = useState<string>();
  const objectUrl = useRef<string | undefined>(undefined);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(undefined);
    setPreview(undefined);
    setDownload(undefined);
    setReport(undefined);
    void operations.read({ registrationId, reportId, signal: controller.signal })
      .then((result) => {
        if (result.data.report_id !== reportId)
          throw new Error("The service returned a different report.");
        if (active) setReport(result.data);
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
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    };
  }, [operations, refreshToken, registrationId, reportId]);

  async function loadBytes(save: boolean) {
    setDownloading(true);
    setError(undefined);
    try {
      const bytes = await operations.download({
        registrationId,
        reportId,
        query: { format },
      });
      setDownload(bytes);
      setPreview(await bytes.blob.text());
      setDownloadNotice(undefined);
      if (save) {
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        const url = URL.createObjectURL(bytes.blob);
        objectUrl.current = url;
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = bytes.filename;
        anchor.rel = "noopener";
        anchor.click();
        setDownloadNotice(`Download started: ${bytes.filename}`);
        window.setTimeout(() => {
          URL.revokeObjectURL(url);
          if (objectUrl.current === url) objectUrl.current = undefined;
        }, 0);
      }
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setDownloading(false);
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
          {report.legacy && <p className="warning-summary">This report is a legacy record.</p>}
          {report.nonexportable_reason && (
            <p className="warning-summary">Export unavailable: {report.nonexportable_reason}</p>
          )}
          <label className="field">
            Download format
            <select
              value={format}
              onChange={(event) => {
                const value = event.currentTarget.value;
                if (value === "json" || value === "markdown") setFormat(value);
              }}
            >
              <option value="json">JSON bytes</option>
              <option value="markdown">Markdown bytes</option>
            </select>
          </label>
          <div className="actions">
            <button type="button" disabled={downloading || !!report.nonexportable_reason} onClick={() => void loadBytes(false)}>
              {downloading ? "Reading report bytes…" : "Preview report bytes"}
            </button>
            <button type="button" disabled={downloading || !!report.nonexportable_reason} onClick={() => void loadBytes(true)}>
              Download {format === "json" ? "JSON" : "Markdown"}
            </button>
          </div>
          {download && <p role="status">Read {download.blob.size} report bytes as {format}; filename {download.filename}.</p>}
          {downloadNotice && <p role="status">{downloadNotice}</p>}
          {preview !== undefined && (
            <section>
              <h2>Inert text preview</h2>
              <pre className="source-editor" aria-label="Report text preview">{preview}</pre>
            </section>
          )}
        </>
      )}
    </article>
  );
}

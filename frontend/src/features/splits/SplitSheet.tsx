import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import type { ExampleAuthoringOperations, ProjectOverview } from "../../workspace/gateway";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";

type SplitPreview = ApiOperationData<"preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post">;
type SplitCommit = ApiOperationData<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post">;
type SplitRequest = ApiOperationBody<"preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post">;

export function SplitSheet({
  project,
  datasetId,
  examples,
  onClose,
  onApplied,
}: {
  project: ProjectOverview;
  datasetId: string;
  examples: ExampleAuthoringOperations;
  onClose: () => void;
  onApplied: (result: SplitCommit) => void;
}) {
  const [mode, setMode] = useState<"seeded" | "explicit">("seeded");
  const [seed, setSeed] = useState("0");
  const [ratiosSource, setRatiosSource] = useState('{"development":0.8,"test":0.2}');
  const [assignments, setAssignments] = useState<readonly (readonly [string, "development" | "calibration" | "test"])[]>([]);
  const [cases, setCases] = useState<ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">["items"]>([]);
  const [caseCursor, setCaseCursor] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<SplitPreview>();
  const [error, setError] = useState<string>();
  const [state, setState] = useState<MutationState<SplitCommit>>({ kind: "idle" });
  const [discardConfirm, setDiscardConfirm] = useState(false);
  const mutation = useRef<RetainedMutation<{
    registrationId: string;
    datasetId: string;
    body: ApiOperationBody<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post">;
  }, SplitCommit>>();
  function requestClose() {
    if (busy) return;
    const changed = mode !== "seeded" || seed !== "0" || ratiosSource !== '{"development":0.8,"test":0.2}' || !!preview || state.kind === "outcome-unknown";
    if (changed) setDiscardConfirm(true);
    else onClose();
  }

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    void examples.listCases({
      registrationId: project.id,
      datasetId,
      query: { limit: "100" },
      signal: controller.signal,
    }).then((result) => {
      if (!active) return;
      setCases(result.data.items);
      setCaseCursor(result.data.next_cursor ?? undefined);
      setAssignments(result.data.items.map((item) => [item.record.id, "development"] as const));
    }).catch((cause: unknown) => {
      if (active) setError(safeMessage(cause));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [datasetId, examples, project.id]);

  useEffect(() => {
    mutation.current = new RetainedMutation(async (request) => {
      const result = await examples.commitSplit({ registrationId: request.registrationId, datasetId: request.datasetId, body: request.body });
      return result.data;
    }, setState);
  }, [examples]);

  function invalidate() {
    setPreview(undefined);
    setError(undefined);
    if (state.kind !== "submitting" && state.kind !== "outcome-unknown") {
      mutation.current?.reset();
      setState({ kind: "idle" });
    }
  }

  async function loadAllCases() {
    if (!caseCursor || busy) return;
    setBusy(true);
    try {
      const result = await examples.listCases({ registrationId: project.id, datasetId, query: { cursor: caseCursor, limit: "100" } });
      setCases((current) => [...current, ...result.data.items]);
      setAssignments((current) => [...current, ...result.data.items.map((item) => [item.record.id, "development"] as const)]);
      setCaseCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  function request(): SplitRequest {
    return mode === "seeded"
      ? { schema_version: 1, seed, ratios_source: ratiosSource }
      : { schema_version: 1, assignments };
  }

  async function review() {
    setBusy(true);
    setError(undefined);
    try {
      const result = await examples.previewSplit({ registrationId: project.id, datasetId, body: request() });
      setPreview(result.data);
      mutation.current?.reset();
      setState({ kind: "idle" });
    } catch (cause) {
      setPreview(undefined);
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!preview || !mutation.current) return;
    setBusy(true);
    const requestBody = {
      schema_version: 1 as const,
      operation_id: crypto.randomUUID(),
      preview_document_source: preview.preview_document_source,
    };
    const result = state.kind === "outcome-unknown"
      ? await mutation.current.retryOriginal()
      : await mutation.current.submit({ registrationId: project.id, datasetId, body: requestBody });
    if (result) onApplied(result);
    setBusy(false);
  }

  const mutationMessage = state.kind === "conflict" || state.kind === "failed" || state.kind === "outcome-unknown" ? state.message : undefined;
  const locked = state.kind === "submitting" || state.kind === "outcome-unknown";
  return (
      <Modal title="Split dataset" onDismiss={requestClose} sheet>
      <div className="modal-body split-sheet">
        <p className="muted">The service assigns related cases together and saves a new dataset revision.</p>
        {error && <ErrorSummary message={error} />}
        {mutationMessage && <ErrorSummary message={mutationMessage} />}
        {state.kind === "outcome-unknown" && <button type="button" onClick={() => void apply()}>Retry the same split request</button>}
        <fieldset>
          <legend>Assignment method</legend>
          <label><input type="radio" checked={mode === "seeded"} disabled={locked} onChange={() => { setMode("seeded"); invalidate(); }} />Seeded grouped split</label>
          <label><input type="radio" checked={mode === "explicit"} disabled={locked} onChange={() => { setMode("explicit"); invalidate(); }} />Explicit assignments</label>
        </fieldset>
        {mode === "seeded" ? (
          <>
            <div className="field"><label htmlFor="split-seed">Seed (signed 64-bit integer text)</label><input id="split-seed" value={seed} disabled={locked} onChange={(event) => { setSeed(event.target.value); invalidate(); }} /></div>
            <JsonSourceEditor label="Ratios source" value={ratiosSource} onChange={(value) => { setRatiosSource(value); invalidate(); }} readOnly={locked} />
          </>
        ) : loading ? <LoadingState>Loading cases…</LoadingState> : (
          <>
            <table className="records-table"><caption>Complete explicit split assignments</caption><thead><tr><th scope="col">Case</th><th scope="col">Group</th><th scope="col">Split</th></tr></thead><tbody>
              {cases.map((item) => <tr key={item.record.id}><th scope="row">{item.record.id}</th><td>{item.record.group_id ?? "—"}</td><td><select disabled={locked} value={assignments.find(([id]) => id === item.record.id)?.[1] ?? "development"} onChange={(event) => { const value = event.target.value as "development" | "calibration" | "test"; setAssignments((current) => current.map(([id, split]) => [id, id === item.record.id ? value : split] as const)); invalidate(); }}><option value="development">Development</option><option value="calibration">Calibration</option><option value="test">Test</option></select></td></tr>)}
            </tbody></table>
            {caseCursor && <button type="button" disabled={busy || locked} onClick={() => void loadAllCases()}>{busy ? "Loading…" : "Load remaining cases"}</button>}
          </>
        )}
        <div className="actions"><button type="button" disabled={busy || locked || (mode === "explicit" && !!caseCursor)} onClick={() => void review()}>{busy ? "Reviewing…" : "Preview assignments"}</button></div>
        {preview && (
          <section className="section split-preview" aria-labelledby="split-preview-heading">
            <h2 id="split-preview-heading">Server split preview</h2>
            <p>Algorithm: <code>{preview.preview.algorithm}</code></p>
            <p>Input identity: <code>{preview.preview.input_identity}</code></p>
            <table className="records-table"><caption>Actual assignment counts</caption><thead><tr><th scope="col">Split</th><th scope="col">Cases</th></tr></thead><tbody>{preview.preview.counts.map(([split, count]) => <tr key={split}><th scope="row">{split}</th><td>{count}</td></tr>)}</tbody></table>
            <details><summary>Assignments</summary><table className="records-table"><thead><tr><th scope="col">Case</th><th scope="col">Split</th></tr></thead><tbody>{preview.preview.assignments.map(([id, split]) => <tr key={id}><th scope="row">{id}</th><td>{split}</td></tr>)}</tbody></table></details>
            <div className="actions"><button type="button" className="primary" disabled={busy || locked || state.kind === "committed" || state.kind === "conflict" || state.kind === "failed"} onClick={() => void apply()}>{busy ? "Applying…" : "Apply split"}</button><button type="button" disabled={busy} onClick={requestClose}>Close</button></div>
          </section>
        )}
        {state.kind === "committed" && <p role="status">Saved new dataset revision {state.receipt.snapshot.id}.</p>}
      </div>
      {discardConfirm && <Modal title="Discard this split proposal?" onDismiss={() => setDiscardConfirm(false)}><div className="modal-body"><p>The preview and unsaved split settings will be cleared when this sheet closes.</p><div className="actions"><button className="primary" onClick={onClose}>Discard proposal</button><button onClick={() => setDiscardConfirm(false)}>Keep editing</button></div></div></Modal>}
    </Modal>
  );
}

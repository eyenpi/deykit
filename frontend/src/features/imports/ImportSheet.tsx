import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { JsonSourceEditor } from "../../components/JsonSourceEditor";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import type { ExampleAuthoringOperations, ProjectOverview, SourceAuthoringOperations } from "../../workspace/gateway";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";

type ImportPreview = ApiOperationData<"preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post">;
type ImportCommit = ApiOperationData<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post">;
type MappingForm = NonNullable<ApiOperationData<"projectImportMapping">["form"]>;
type MappingEdit = ApiOperationBody<"transformImportMapping">["edit"];

const INITIAL_MAPPING = '{"input_kind":"text"}';

export function ImportSheet({
  project,
  datasetId,
  examples,
  sources,
  onClose,
  onImported,
}: {
  project: ProjectOverview;
  datasetId: string;
  examples: ExampleAuthoringOperations;
  sources: SourceAuthoringOperations;
  onClose: () => void;
  onImported: (result: ImportCommit) => void;
}) {
  const [fileName, setFileName] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [format, setFormat] = useState<"csv" | "jsonl">("csv");
  const [mappingSource, setMappingSource] = useState(INITIAL_MAPPING);
  const [mappingForm, setMappingForm] = useState<MappingForm>();
  const [decisionId, setDecisionId] = useState("");
  const [preview, setPreview] = useState<ImportPreview>();
  const [skipInvalid, setSkipInvalid] = useState(false);
  const [error, setError] = useState<string>();
  const [mappingError, setMappingError] = useState<string>();
  const [loadingMapping, setLoadingMapping] = useState(false);
  const [state, setState] = useState<MutationState<ImportCommit>>({ kind: "idle" });
  const [busy, setBusy] = useState(false);
  const [discardConfirm, setDiscardConfirm] = useState(false);
  const mutation = useRef<RetainedMutation<{
    registrationId: string;
    datasetId: string;
    body: ApiOperationBody<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post">;
  }, ImportCommit>>();
  const mappingFieldOriginals = useRef(new Map<string, string>());

  useEffect(() => {
    let active = true;
    setLoadingMapping(true);
    void sources.projectMapping({
      registrationId: project.id,
      body: { schema_version: 1, mapping_source: mappingSource },
    }).then((result) => {
      if (active) setMappingForm(result.data.form ?? undefined);
    }).catch((cause: unknown) => {
      if (active) setMappingError(safeMessage(cause));
    }).finally(() => {
      if (active) setLoadingMapping(false);
    });
    return () => { active = false; };
  }, [mappingSource, project.id, sources]);

  useEffect(() => {
    mutation.current = new RetainedMutation(async (request) => {
      const result = await examples.commitImport({
        registrationId: request.registrationId,
        datasetId: request.datasetId,
        body: request.body,
      });
      return result.data;
    }, setState);
  }, [examples]);

  function invalidatePreview() {
    setPreview(undefined);
    setSkipInvalid(false);
    setError(undefined);
    if (state.kind !== "submitting" && state.kind !== "outcome-unknown") {
      mutation.current?.reset();
      setState({ kind: "idle" });
    }
  }

  async function readFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 8_388_608) {
      setError("This file is larger than the 8 MiB import limit.");
      return;
    }
    try {
      const bytes = await file.arrayBuffer();
      const decoded = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
      setFileName(file.name);
      setSourceText(decoded);
      setFormat(file.name.toLowerCase().endsWith(".jsonl") ? "jsonl" : "csv");
      invalidatePreview();
    } catch {
      setError("The selected file is not valid UTF-8. Your current import source is unchanged.");
    }
  }

  async function transformMapping(edit: MappingEdit) {
    setMappingError(undefined);
    try {
      const result = await sources.transformMapping({
        registrationId: project.id,
        body: { schema_version: 1, mapping_source: mappingSource, edit },
      });
      setMappingSource(result.data.mapping_source);
      setMappingForm(result.data.projection.form ?? undefined);
      invalidatePreview();
    } catch (cause) {
      setMappingError(safeMessage(cause));
    }
  }

  async function previewImport() {
    setBusy(true);
    setError(undefined);
    try {
      const result = await examples.previewImport({
        registrationId: project.id,
        datasetId,
        body: {
          schema_version: 1,
          source_text: sourceText,
          format,
          mapping_source: mappingSource,
          decision_id: decisionId || null,
          decision_selector: "draft",
        },
      });
      setPreview(result.data);
      setSkipInvalid(false);
      mutation.current?.reset();
      setState({ kind: "idle" });
    } catch (cause) {
      setError(safeMessage(cause));
      setPreview(undefined);
    } finally {
      setBusy(false);
    }
  }

  async function commitImport() {
    if (!preview || !mutation.current) return;
    const rejected = preview.preview.rows.filter((row) => row.errors.length > 0).length;
    if (rejected > 0 && !skipInvalid) return;
    setBusy(true);
    const request = {
      registrationId: project.id,
      datasetId,
      body: {
        schema_version: 1 as const,
        operation_id: crypto.randomUUID(),
        preview_document_source: preview.preview_document_source,
        ...(skipInvalid ? { skip_invalid: true } : { skip_invalid: false }),
      },
    };
    const result = state.kind === "outcome-unknown"
      ? await mutation.current.retryOriginal()
      : await mutation.current.submit(request);
    if (result) onImported(result);
    setBusy(false);
  }

  const rows = preview?.preview.rows ?? [];
  const rejectedCount = rows.filter((row) => row.errors.length > 0).length;
  const validCount = rows.length - rejectedCount;
  const mutationMessage = state.kind === "conflict" || state.kind === "failed" || state.kind === "outcome-unknown" ? state.message : undefined;
  const locked = state.kind === "submitting" || state.kind === "outcome-unknown";
  const hasUnsavedImport = !!sourceText || mappingSource !== INITIAL_MAPPING || !!preview;
  function requestClose() {
    if (busy) return;
    if (hasUnsavedImport || locked) setDiscardConfirm(true);
    else onClose();
  }
  return (
    <Modal title="Import examples" onDismiss={requestClose} sheet>
      <div className="modal-body import-sheet">
        <p className="muted">Import adds cases only. It never starts a model request.</p>
        {error && <ErrorSummary message={error} />}
        {mutationMessage && <ErrorSummary message={mutationMessage} />}
        {state.kind === "outcome-unknown" && <button type="button" disabled={busy} onClick={() => void commitImport()}>Retry the same import request</button>}
        <div className="field">
          <label htmlFor="import-file">CSV or JSONL file</label>
        <input id="import-file" type="file" accept=".csv,.jsonl,text/csv,application/x-ndjson" disabled={locked} onChange={(event) => void readFile(event.currentTarget.files?.[0])} />
          {fileName && <p className="muted">Selected file: {fileName}</p>}
        </div>
        <fieldset>
          <legend>Format</legend>
          {(["csv", "jsonl"] as const).map((value) => (
            <label key={value}><input type="radio" name="import-format" checked={format === value} disabled={locked} onChange={() => { setFormat(value); invalidatePreview(); }} />{value.toUpperCase()}</label>
          ))}
        </fieldset>
        <div className="field">
          <label htmlFor="import-decision">Map expected answers for</label>
          <select id="import-decision" value={decisionId} disabled={locked} onChange={(event) => { setDecisionId(event.target.value); invalidatePreview(); }}>
            <option value="">No decision selected</option>
            {project.decisions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {loadingMapping ? <LoadingState>Loading mapping controls…</LoadingState> : mappingForm ? (
          <section className="mapping-form" aria-label="Common import mapping controls">
            <fieldset>
              <legend>Input format</legend>
              {(["text", "json"] as const).map((value) => <label key={value}><input type="radio" checked={mappingForm.input_kind === value} disabled={locked} onChange={() => void transformMapping({ kind: "set", field: "input_kind", value })} />{value.toUpperCase()}</label>)}
            </fieldset>
            {(["input_column", "id_column", "expected_column", "group_column", "tags_column", "split_column", "metadata_column"] as const).map((field) => (
              <div className="field" key={field}>
                <label htmlFor={`mapping-${field}`}>{field.replaceAll("_", " ")}</label>
                <input
                  id={`mapping-${field}`}
                  value={mappingForm[field] ?? ""}
                  disabled={locked}
                  onFocus={(event) => mappingFieldOriginals.current.set(field, event.currentTarget.value)}
                  onChange={(event) => setMappingForm({ ...mappingForm, [field]: event.target.value || null })}
                  onBlur={(event) => {
                    if (event.currentTarget.value !== mappingFieldOriginals.current.get(field))
                      void transformMapping({ kind: "set", field, value: event.currentTarget.value || null });
                  }}
                />
              </div>
            ))}
          </section>
        ) : null}
        {mappingError && <ErrorSummary message={mappingError} />}
        <JsonSourceEditor label="Advanced mapping source" value={mappingSource} onChange={(value) => { setMappingSource(value); invalidatePreview(); }} readOnly={locked} />
        <JsonSourceEditor label="Import source text" value={sourceText} onChange={(value) => { setSourceText(value); invalidatePreview(); }} readOnly={locked} />
        <div className="actions">
          <button type="button" disabled={busy || locked || !sourceText} onClick={() => void previewImport()}>{busy ? "Reviewing…" : "Preview all rows"}</button>
        </div>
        {preview && (
          <section className="section import-preview" aria-labelledby="import-preview-heading">
            <h2 id="import-preview-heading">Import review</h2>
            <p role="status">{rows.length} rows · {validCount} valid · {rejectedCount} rejected · {preview.would_import} would import</p>
            <table className="records-table">
              <caption>Actual parsed rows and server validation</caption>
              <thead><tr><th scope="col">Row</th><th scope="col">Input preview</th><th scope="col">Expected IDs</th><th scope="col">Errors</th></tr></thead>
              <tbody>{rows.map((row) => (
                <tr key={`${row.row}-${row.source_line}`}>
                  <th scope="row">{row.row}</th>
                  <td><code>{row.case?.input_source.slice(0, 120) ?? "—"}</code></td>
                  <td>{row.acceptable_option_ids.join(", ") || "—"}</td>
                  <td>{row.errors.map((item, index) => <p key={`${item.code}-${index}`} className="field-error">Line {row.source_line}: {item.message} <code>{item.code}</code></p>)}</td>
                </tr>
              )}</tbody>
            </table>
            {rejectedCount > 0 && (
              <label className="check-row">
                <input type="checkbox" checked={skipInvalid} disabled={locked} onChange={(event) => setSkipInvalid(event.target.checked)} />
                Import valid rows only ({validCount}) and keep the exclusion report
              </label>
            )}
            <div className="actions">
              <button type="button" className="primary" disabled={busy || (rejectedCount > 0 && !skipInvalid) || state.kind === "committed" || state.kind === "conflict" || state.kind === "failed"} onClick={() => void commitImport()}>
                {busy ? "Importing…" : `Import ${rejectedCount > 0 ? "valid rows" : "cases"}`}
              </button>
              <button type="button" disabled={busy} onClick={requestClose}>Close</button>
            </div>
            {state.kind === "committed" && (
              <div role="status"><p>Imported {state.receipt.imported_case_ids.length} case(s) into the selected dataset.</p><p>Excluded rows: {state.receipt.exclusions.length}. The exact server exclusions remain available in this report.</p></div>
            )}
          </section>
        )}
      </div>
      {discardConfirm && <Modal title="Discard this import review?" onDismiss={() => setDiscardConfirm(false)}><div className="modal-body"><p>The selected source, mapping, and preview will be cleared when this sheet closes.</p><div className="actions"><button className="primary" onClick={onClose}>Discard import review</button><button onClick={() => setDiscardConfirm(false)}>Keep editing</button></div></div></Modal>}
    </Modal>
  );
}

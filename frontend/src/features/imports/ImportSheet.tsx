import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { JsonSourceEditor } from "../../components/JsonSourceEditor";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import type { ExampleAuthoringOperations, ProjectOverview, SourceAuthoringOperations } from "../../workspace/gateway";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { MappingTransformQueue } from "./mapping-transform-queue";

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
  const [mappingTransformPending, setMappingTransformPending] = useState(false);
  const [state, setState] = useState<MutationState<ImportCommit>>({ kind: "idle" });
  const [busy, setBusy] = useState(false);
  const [discardConfirm, setDiscardConfirm] = useState(false);
  const mutation = useRef<RetainedMutation<{
    registrationId: string;
    datasetId: string;
    body: ApiOperationBody<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post">;
  }, ImportCommit>>();
  const mappingFieldOriginals = useRef(new Map<string, string>());
  const mappingSourceRef = useRef(INITIAL_MAPPING);
  const mappingFormRef = useRef<MappingForm>();
  const mappingQueue = useRef(new MappingTransformQueue<MappingEdit, MappingForm>(INITIAL_MAPPING));
  const mappingTransformCount = useRef(0);
  const uncommittedMappingEdits = useRef(new Map<string, MappingEdit>());
  const mappingProjectionSequence = useRef(0);

  useEffect(() => {
    let active = true;
    const sequence = ++mappingProjectionSequence.current;
    setLoadingMapping(true);
    void sources.projectMapping({
      registrationId: project.id,
      body: { schema_version: 1, mapping_source: mappingSourceRef.current },
    }).then((result) => {
      if (active && sequence === mappingProjectionSequence.current) {
        setMappingForm(result.data.form ?? undefined);
        mappingFormRef.current = result.data.form ?? undefined;
      }
    }).catch((cause: unknown) => {
      if (active && sequence === mappingProjectionSequence.current) setMappingError(safeMessage(cause));
    }).finally(() => {
      if (active && sequence === mappingProjectionSequence.current) setLoadingMapping(false);
    });
    return () => { active = false; };
  }, [project.id, sources]);

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

  function recordMappingEdit(edit: MappingEdit) {
    if (edit.kind === "set") uncommittedMappingEdits.current.set(edit.field, edit);
  }

  function mergeUncommittedEdits(form: MappingForm): MappingForm {
    const next = { ...form } as unknown as Record<string, unknown>;
    for (const edit of uncommittedMappingEdits.current.values()) {
      if (edit.kind === "set") next[edit.field] = edit.value;
    }
    return next as MappingForm;
  }

  function scheduleMappingEdits(edits: readonly MappingEdit[]) {
    if (mappingQueue.current.blocked || edits.length === 0) return;
    invalidatePreview();
    setMappingError(undefined);
    for (const edit of edits) {
      mappingTransformCount.current += 1;
      setMappingTransformPending(true);
      void mappingQueue.current.enqueue(edit, async (source, queuedEdit) => {
        const result = await sources.transformMapping({
          registrationId: project.id,
          body: { schema_version: 1, mapping_source: source, edit: queuedEdit },
        });
        return {
          mapping_source: result.data.mapping_source,
          form: result.data.projection.form ?? null,
        };
      }).then((result) => {
        if (edit.kind === "set" && uncommittedMappingEdits.current.get(edit.field) === edit)
          uncommittedMappingEdits.current.delete(edit.field);
        mappingSourceRef.current = mappingQueue.current.source;
        setMappingSource(mappingQueue.current.source);
        if (result.form) {
          const next = mergeUncommittedEdits(result.form);
          mappingFormRef.current = next;
          setMappingForm(next);
        }
      }).catch((cause: unknown) => {
        setMappingError(safeMessage(cause));
      }).finally(() => {
        mappingTransformCount.current -= 1;
        if (mappingTransformCount.current === 0) setMappingTransformPending(false);
      });
    }
  }

  function transformMapping(edit: MappingEdit) {
    recordMappingEdit(edit);
    if (edit.kind === "set" && mappingFormRef.current) {
      const next = mergeUncommittedEdits(mappingFormRef.current);
      mappingFormRef.current = next;
      setMappingForm(next);
    }
    scheduleMappingEdits([edit]);
  }

  function retryMappingEdits() {
    if (mappingTransformCount.current > 0 || uncommittedMappingEdits.current.size === 0) return;
    mappingQueue.current.reset(mappingSourceRef.current);
    scheduleMappingEdits([...uncommittedMappingEdits.current.values()]);
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
    if (
      mappingTransformCount.current > 0 ||
      mappingQueue.current.blocked ||
      uncommittedMappingEdits.current.size > 0 ||
      loadingMapping
    ) {
      setError("Finish or retry the pending mapping changes before previewing this import.");
      return;
    }
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
          mapping_source: mappingSourceRef.current,
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
                  onChange={(event) => {
                    const edit: MappingEdit = { kind: "set", field, value: event.target.value || null };
                    recordMappingEdit(edit);
                    const next = mappingFormRef.current
                      ? mergeUncommittedEdits(mappingFormRef.current)
                      : mappingForm;
                    if (next) {
                      mappingFormRef.current = next;
                      setMappingForm(next);
                    }
                    invalidatePreview();
                  }}
                  onBlur={(event) => {
                    if (
                      event.currentTarget.value !== mappingFieldOriginals.current.get(field) ||
                      uncommittedMappingEdits.current.has(field)
                    )
                      void transformMapping({ kind: "set", field, value: event.currentTarget.value || null });
                  }}
                />
              </div>
            ))}
          </section>
        ) : null}
        {mappingError && <ErrorSummary message={mappingError} />}
        {mappingQueue.current.blocked && uncommittedMappingEdits.current.size > 0 && <button type="button" disabled={busy || mappingTransformPending} onClick={retryMappingEdits}>Retry pending mapping changes</button>}
        <JsonSourceEditor label="Advanced mapping source" value={mappingSource} onChange={(value) => {
          mappingSourceRef.current = value;
          mappingQueue.current.reset(value);
          const sequence = ++mappingProjectionSequence.current;
          uncommittedMappingEdits.current.clear();
          mappingFormRef.current = undefined;
          setMappingForm(undefined);
          setMappingSource(value);
          setLoadingMapping(true);
          invalidatePreview();
          void sources.projectMapping({ registrationId: project.id, body: { schema_version: 1, mapping_source: value } })
            .then((result) => {
              if (sequence !== mappingProjectionSequence.current || mappingSourceRef.current !== value || uncommittedMappingEdits.current.size > 0) return;
              mappingFormRef.current = result.data.form ?? undefined;
              setMappingForm(result.data.form ?? undefined);
            }).catch((cause: unknown) => {
              if (sequence === mappingProjectionSequence.current) setMappingError(safeMessage(cause));
            }).finally(() => {
              if (sequence === mappingProjectionSequence.current) setLoadingMapping(false);
            });
        }} readOnly={locked || mappingTransformPending} />
        <JsonSourceEditor label="Import source text" value={sourceText} onChange={(value) => { setSourceText(value); invalidatePreview(); }} readOnly={locked} />
        <div className="actions">
          <button type="button" disabled={busy || locked || mappingTransformPending || loadingMapping || uncommittedMappingEdits.current.size > 0 || mappingQueue.current.blocked || !sourceText} onClick={() => void previewImport()}>{busy ? "Reviewing…" : "Preview all rows"}</button>
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

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { JsonSourceEditor } from "../../components/JsonSourceEditor";
import { Modal } from "../../components/Modal";
import { LoadingState, ErrorSummary } from "../../components/States";
import type { DecisionAuthoringOperations } from "../../workspace/gateway";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import { DraftAutosaveController } from "./draft-autosave";
import type { DraftSaveStatus } from "./draft-autosave";
import { isOutcomeUnknown } from "../../workspace/mutation-controller";

type DecisionDTO = ApiOperationData<"readDecision">;
type EditorForm = NonNullable<
  ApiOperationData<"projectDecisionEditor">["form"]
>;
type EditorEdit = ApiOperationBody<"transformDecisionEditor">["edit"];
type TransformReview = ApiOperationData<"transformDecisionEditor">;

const operationId = () => crypto.randomUUID();

export function DecisionPage({
  registrationId,
  decisionId,
  operations,
  navigation,
  onDecisionRenamed,
  onHistory,
  onExamples,
  onArchiveChanged,
}: {
  registrationId: string;
  decisionId: string;
  operations: DecisionAuthoringOperations;
  navigation: WorkspaceNavigation;
  onDecisionRenamed: (name: string) => void;
  onHistory: () => void;
  onExamples: () => void;
  onArchiveChanged: () => void;
}) {
  const [record, setRecord] = useState<DecisionDTO>();
  const [form, setForm] = useState<EditorForm | null>(null);
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [loadError, setLoadError] = useState<string>();
  const [editError, setEditError] = useState<string>();
  const [draftStatus, setDraftStatus] = useState<DraftSaveStatus>({
    kind: "idle",
  });
  const [draftDirty, setDraftDirty] = useState(false);
  const [working, setWorking] = useState(false);
  const [renameWorking, setRenameWorking] = useState(false);
  const [versionOutcomeUnknown, setVersionOutcomeUnknown] = useState(false);
  const [renameOutcomeUnknown, setRenameOutcomeUnknown] = useState(false);
  const [archiveOutcomeUnknown, setArchiveOutcomeUnknown] = useState(false);
  const [note, setNote] = useState("");
  const [notice, setNotice] = useState<string>();
  const [newFieldName, setNewFieldName] = useState("");
  const [removalReview, setRemovalReview] = useState<{
    optionId: string;
    optionName: string;
    review: TransformReview;
  }>();
  const [archiveConfirm, setArchiveConfirm] = useState(false);
  const sourceRef = useRef(source);
  const recordRef = useRef<DecisionDTO | undefined>(undefined);
  const draftEtagRef = useRef("");
  const sourceSequence = useRef(0);
  const formSequence = useRef(0);
  const selectedFieldOriginals = useRef(new Map<number, string>());
  const instructionOriginal = useRef<string | undefined>(undefined);
  const optionOriginals = useRef(
    new Map<string, { name: string; description: string }>(),
  );
  const schemaOriginal = useRef<string | undefined>(undefined);
  const composingSource = useRef(false);
  const schemaBlurredWhileComposing = useRef(false);
  const transformQueue = useRef<
    Array<{ edit: EditorEdit; sequence: number; sourceSequence: number }>
  >([]);
  const transformTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const transforming = useRef(false);
  const transformTask = useRef<Promise<boolean> | undefined>(undefined);
  const autosave = useRef<DraftAutosaveController | undefined>(undefined);
  const versionRequest = useRef<
    ApiOperationBody<"saveDecisionRevision"> | undefined
  >(undefined);
  const renameRequest = useRef<ApiOperationBody<"renameDecision"> | undefined>(
    undefined,
  );
  const archiveRequest = useRef<
    | ApiOperationBody<"archiveDecision">
    | ApiOperationBody<"restoreDecision">
    | undefined
  >(undefined);
  const archiveAction = useRef<"archive" | "restore" | undefined>(undefined);
  const actionLock = useRef(false);

  const setBackingSource = useCallback((next: string) => {
    sourceRef.current = next;
    setSource(next);
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoadError(undefined);
    setRecord(undefined);
    setForm(null);
    void operations
      .read({ registrationId, decisionId, signal: controller.signal })
      .then(async (result) => {
        const projection = await operations.projectEditor({
          registrationId,
          decisionId,
          body: {
            schema_version: 1,
            editor_source: result.data.draft.record.editor_source,
          },
          signal: controller.signal,
        });
        if (!active) return;
        setRecord(result.data);
        recordRef.current = result.data;
        setName(result.data.decision.record.name);
        draftEtagRef.current = result.data.draft.etag;
        sourceSequence.current += 1;
        setBackingSource(result.data.draft.record.editor_source);
        setDraftDirty(false);
        setForm(projection.data.form);
        autosave.current?.dispose();
        autosave.current = new DraftAutosaveController(
          result.data.draft.etag,
          async (request) => {
            const saved = await operations.updateDraft({
              registrationId,
              decisionId,
              body: {
                schema_version: 1,
                editor_source: request.editorSource,
                expected_etag: request.expectedDraftEtag,
                operation_id: request.operationId,
              },
            });
            draftEtagRef.current = saved.data.etag;
            if (request.editorSource === sourceRef.current)
              setDraftDirty(false);
            return { etag: saved.data.etag };
          },
          setDraftStatus,
        );
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted)
          setLoadError(safeMessage(cause));
      });
    return () => {
      active = false;
      controller.abort();
      if (transformTimer.current !== undefined)
        clearTimeout(transformTimer.current);
      autosave.current?.dispose();
    };
  }, [decisionId, operations, registrationId, setBackingSource]);

  const drainTransforms = useCallback(() => {
    if (transformTask.current) return transformTask.current;
    const task = (async (): Promise<boolean> => {
      let completed = true;
      transforming.current = true;
      while (transformQueue.current.length) {
        const queued = transformQueue.current.shift();
        if (!queued) continue;
        if (queued.sourceSequence !== sourceSequence.current) continue;
        setEditError(undefined);
        setNotice(undefined);
        try {
          const result = await operations.transformEditor({
            registrationId,
            decisionId,
            body: {
              schema_version: 1,
              editor_source: sourceRef.current,
              expected_draft_etag: draftEtagRef.current,
              edit: queued.edit,
            },
          });
          if (queued.sourceSequence !== sourceSequence.current) continue;
          const transformed = result.data.transform;
          sourceRef.current = transformed.editor_source;
          setSource(transformed.editor_source);
          setDraftDirty(true);
          autosave.current?.edit(transformed.editor_source);
          if (queued.sequence === formSequence.current)
            setForm(transformed.projection.form);
        } catch (cause) {
          setEditError(safeMessage(cause));
          transformQueue.current = [];
          completed = false;
          break;
        }
      }
      transforming.current = false;
      return completed;
    })();
    transformTask.current = task.finally(() => {
      transformTask.current = undefined;
    });
    return transformTask.current;
  }, [decisionId, operations, registrationId]);

  const unresolvedWrite =
    versionOutcomeUnknown ||
    renameOutcomeUnknown ||
    archiveOutcomeUnknown ||
    draftStatus.kind === "outcome-unknown";
  const navigationBlockedMessage = unresolvedWrite
    ? "A write may have completed. Keep editing and retry its original request before leaving this decision."
    : working || renameWorking
      ? "A write is still in progress. Keep this decision open until it finishes."
      : undefined;
  const dirtyGuard = useDirtyNavigationGuard({
    dirty: draftDirty || unresolvedWrite || working || renameWorking,
    blockedMessage: navigationBlockedMessage,
    save: async () => {
      if (navigationBlockedMessage) throw new Error(navigationBlockedMessage);
      if (composingSource.current)
        throw new Error(
          "Finish composing the schema source before saving or leaving.",
        );
      if (transformTimer.current !== undefined) {
        clearTimeout(transformTimer.current);
        transformTimer.current = undefined;
      }
      if (!(await drainTransforms()))
        throw new Error(
          "A pending editor transform failed. Review the error before leaving.",
        );
      await autosave.current?.flush();
    },
    discard: () => {
      setDraftDirty(false);
      transformQueue.current = [];
      if (transformTimer.current !== undefined)
        clearTimeout(transformTimer.current);
      sourceSequence.current += 1;
    },
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `decision:${registrationId}:${decisionId}`,
        dirtyGuard.guard,
      ),
    [decisionId, dirtyGuard.guard, navigation, registrationId],
  );

  function queueTransform(edit: EditorEdit, sequence = formSequence.current) {
    transformQueue.current.push({
      edit,
      sequence,
      sourceSequence: sourceSequence.current,
    });
    if (transformTimer.current !== undefined)
      clearTimeout(transformTimer.current);
    transformTimer.current = setTimeout(() => {
      transformTimer.current = undefined;
      void drainTransforms();
    }, 500);
  }

  function updateForm(next: EditorForm) {
    formSequence.current += 1;
    setForm(next);
    setDraftDirty(true);
    return formSequence.current;
  }

  function changeRawSource(next: string) {
    sourceSequence.current += 1;
    transformQueue.current = [];
    if (transformTimer.current !== undefined)
      clearTimeout(transformTimer.current);
    setBackingSource(next);
    setDraftDirty(true);
    autosave.current?.edit(next);
    const expectedSequence = sourceSequence.current;
    void operations
      .projectEditor({
        registrationId,
        decisionId,
        body: { schema_version: 1, editor_source: next },
      })
      .then((result) => {
        if (expectedSequence === sourceSequence.current)
          setForm(result.data.form);
      })
      .catch((cause: unknown) => {
        if (expectedSequence === sourceSequence.current)
          setEditError(safeMessage(cause));
      });
  }

  async function rename() {
    const current = recordRef.current;
    const trimmed = name.trim();
    if (
      !current ||
      actionLock.current ||
      !trimmed ||
      (trimmed === current.decision.record.name && !renameOutcomeUnknown)
    )
      return;
    actionLock.current = true;
    setRenameWorking(true);
    setEditError(undefined);
    try {
      const body =
        renameOutcomeUnknown && renameRequest.current
          ? renameRequest.current
          : {
              schema_version: 1 as const,
              expected_etag: current.decision.etag,
              operation_id: operationId(),
              name: trimmed,
            };
      renameRequest.current = body;
      const result = await operations.rename({
        registrationId,
        decisionId,
        body,
      });
      renameRequest.current = undefined;
      setRenameOutcomeUnknown(false);
      const next = { ...current, decision: result.data };
      recordRef.current = next;
      setRecord(next);
      setName(result.data.record.name);
      onDecisionRenamed(result.data.record.name);
    } catch (cause) {
      if (uncertainOutcome(cause)) setRenameOutcomeUnknown(true);
      else renameRequest.current = undefined;
      setEditError(safeMessage(cause));
    } finally {
      actionLock.current = false;
      setRenameWorking(false);
    }
  }

  async function saveRevision() {
    const current = recordRef.current;
    const controller = autosave.current;
    if (!current || !controller || actionLock.current) return;
    actionLock.current = true;
    setWorking(true);
    setEditError(undefined);
    try {
      if (composingSource.current)
        throw new Error(
          "Finish composing the schema source before saving a version.",
        );
      let request = versionRequest.current;
      let refreshedRecord = current;
      if (!versionOutcomeUnknown || !request) {
        if (transformTimer.current !== undefined) {
          clearTimeout(transformTimer.current);
          transformTimer.current = undefined;
        }
        if (!(await drainTransforms()))
          throw new Error(
            "The latest editor change could not be applied. No version was saved.",
          );
        await controller.flush();
        const refreshed = await operations.read({ registrationId, decisionId });
        refreshedRecord = refreshed.data;
        request = {
          schema_version: 1,
          expected_decision_etag: refreshed.data.decision.etag,
          expected_draft_etag: refreshed.data.draft.etag,
          operation_id: operationId(),
          ...(note ? { note } : {}),
        };
        versionRequest.current = request;
      }
      const result = await operations.saveRevision({
        registrationId,
        decisionId,
        body: request,
      });
      versionRequest.current = undefined;
      setVersionOutcomeUnknown(false);
      setNote("");
      recordRef.current = refreshedRecord;
      setRecord(refreshedRecord);
      setNotice(`Saved version ${result.data.revision.record.id}.`);
    } catch (cause) {
      if (uncertainOutcome(cause)) setVersionOutcomeUnknown(true);
      else versionRequest.current = undefined;
      setEditError(safeMessage(cause));
    } finally {
      actionLock.current = false;
      setWorking(false);
    }
  }

  async function toggleArchive() {
    const current = recordRef.current;
    if (!current || actionLock.current) return;
    actionLock.current = true;
    setRenameWorking(true);
    setEditError(undefined);
    try {
      const action = current.decision.record.archived ? "restore" : "archive";
      const body =
        archiveOutcomeUnknown && archiveRequest.current
          ? archiveRequest.current
          : {
              schema_version: 1 as const,
              expected_etag: current.decision.etag,
              operation_id: operationId(),
            };
      archiveRequest.current = body;
      archiveAction.current = action;
      if (action === "restore") {
        await operations.restore({ registrationId, decisionId, body });
      } else {
        await operations.archive({ registrationId, decisionId, body });
      }
      archiveRequest.current = undefined;
      archiveAction.current = undefined;
      setArchiveOutcomeUnknown(false);
      setArchiveConfirm(false);
      onArchiveChanged();
    } catch (cause) {
      if (uncertainOutcome(cause)) setArchiveOutcomeUnknown(true);
      else {
        archiveRequest.current = undefined;
        archiveAction.current = undefined;
      }
      setEditError(safeMessage(cause));
    } finally {
      actionLock.current = false;
      setRenameWorking(false);
    }
  }

  async function previewOptionRemoval(optionId: string, optionName: string) {
    if (composingSource.current) {
      setEditError(
        "Finish composing the schema source before reviewing option removal.",
      );
      return;
    }
    if (transformTimer.current !== undefined) {
      clearTimeout(transformTimer.current);
      transformTimer.current = undefined;
    }
    try {
      if (!(await drainTransforms()))
        throw new Error(
          "A pending editor transform failed. Review the error before removing this option.",
        );
      await autosave.current?.flush();
      const result = await operations.transformEditor({
        registrationId,
        decisionId,
        body: {
          schema_version: 1,
          editor_source: sourceRef.current,
          expected_draft_etag: draftEtagRef.current,
          edit: { kind: "remove_option", id: optionId },
        },
      });
      setRemovalReview({ optionId, optionName, review: result.data });
    } catch (cause) {
      setEditError(safeMessage(cause));
    }
  }

  async function confirmOptionRemoval() {
    if (!removalReview) return;
    const transformed = removalReview.review.transform;
    sourceSequence.current += 1;
    setBackingSource(transformed.editor_source);
    setDraftDirty(true);
    setForm(transformed.projection.form);
    setRemovalReview(undefined);
    autosave.current?.edit(transformed.editor_source);
  }

  if (loadError)
    return (
      <article className="document">
        <ErrorSummary message={loadError} />
      </article>
    );
  if (!record)
    return (
      <article className="document">
        <LoadingState>Loading decision…</LoadingState>
      </article>
    );

  const formAvailable = form !== null;
  return (
    <>
      <article className="document decision-document">
        <div className="document-title-row">
          <label className="visually-hidden" htmlFor="decision-name">
            Decision name
          </label>
          <input
            id="decision-name"
            className="document-title-input"
            value={name}
            disabled={renameOutcomeUnknown}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => void rename()}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
            }}
          />
          <span className="muted" role="status">
            {draftStatus.kind === "saving"
              ? "Saving draft…"
              : draftStatus.kind === "saved"
                ? "Draft saved"
                : draftStatus.kind === "outcome-unknown"
                  ? "Save outcome unknown"
                  : draftStatus.kind === "conflict"
                    ? "Draft conflict"
                    : "Choice decision"}
          </span>
        </div>
        <div className="decision-toolbar actions">
          <button type="button" onClick={onHistory}>
            Version history
          </button>
          <button type="button" onClick={onExamples}>
            Examples
          </button>
          {renameOutcomeUnknown && (
            <button
              type="button"
              disabled={renameWorking}
              onClick={() => void rename()}
            >
              Retry same rename
            </button>
          )}
          <button
            type="button"
            disabled={renameWorking}
            onClick={() => setArchiveConfirm(true)}
          >
            {record.decision.record.archived
              ? "Restore decision"
              : "Archive decision"}
          </button>
          <button
            type="button"
            className="primary"
            disabled={working}
            onClick={() => void saveRevision()}
          >
            {working
              ? "Saving version…"
              : versionOutcomeUnknown
                ? "Retry same version save"
                : "Save version"}
          </button>
        </div>
        {editError && <ErrorSummary message={editError} />}
        {notice && (
          <p className="save-status" role="status">
            {notice}
          </p>
        )}
        {draftStatus.kind === "failed" && (
          <ErrorSummary message={draftStatus.message} />
        )}
        {draftStatus.kind === "outcome-unknown" && (
          <section
            className="warning-summary"
            aria-label="Uncertain draft save"
          >
            <p>{draftStatus.message}</p>
            <button
              type="button"
              onClick={() => void autosave.current?.retryUnchanged()}
            >
              Retry unchanged save
            </button>
          </section>
        )}
        {draftStatus.kind === "conflict" && (
          <section className="warning-summary" aria-label="Draft conflict">
            <p>{draftStatus.message}</p>
            <button
              type="button"
              onClick={() => {
                void operations
                  .read({ registrationId, decisionId })
                  .then((result) => {
                    recordRef.current = result.data;
                    setRecord(result.data);
                    autosave.current?.reapplyAfterReview(
                      result.data.draft.etag,
                    );
                  })
                  .catch((cause: unknown) => setEditError(safeMessage(cause)));
              }}
            >
              Review current and reapply my source
            </button>
          </section>
        )}
        {formAvailable ? (
          <>
            <section className="section question-editor">
              <label htmlFor="decision-instructions">Question</label>
              <textarea
                id="decision-instructions"
                className="document-question"
                value={form.instructions}
                onFocus={(event) => {
                  instructionOriginal.current = event.currentTarget.value;
                }}
                onChange={(event) => {
                  const next = { ...form, instructions: event.target.value };
                  updateForm(next);
                }}
                onBlur={(event) => {
                  if (event.currentTarget.value !== instructionOriginal.current)
                    queueTransform({
                      kind: "set_instructions",
                      value: event.currentTarget.value,
                    });
                  instructionOriginal.current = undefined;
                }}
                rows={2}
              />
            </section>
            <section
              className="section option-editor"
              aria-labelledby="options-heading"
            >
              <div className="section-heading-row">
                <h2 id="options-heading">Options</h2>
                <button
                  type="button"
                  onClick={() => {
                    const id = `option-${crypto.randomUUID()}`;
                    const nextOption = {
                      id,
                      name: "New option",
                      description: null,
                    };
                    const sequence = updateForm({
                      ...form,
                      options: [...form.options, nextOption],
                    });
                    queueTransform(
                      { kind: "add_option", ...nextOption },
                      sequence,
                    );
                    setTimeout(
                      () =>
                        document.getElementById(`option-name-${id}`)?.focus(),
                      0,
                    );
                  }}
                >
                  + Add option
                </button>
              </div>
              <ol className="option-list">
                {form.options.map((option, index) => (
                  <li className="option-row" key={option.id}>
                    <div
                      className="option-move-actions"
                      aria-label={`Reorder ${option.name}`}
                    >
                      <button
                        type="button"
                        aria-label={`Move ${option.name} up`}
                        disabled={index === 0}
                        onClick={() => {
                          const options = [...form.options];
                          [options[index - 1], options[index]] = [
                            options[index],
                            options[index - 1],
                          ];
                          const sequence = updateForm({ ...form, options });
                          queueTransform(
                            {
                              kind: "reorder_options",
                              option_ids: options.map((item) => item.id),
                            },
                            sequence,
                          );
                        }}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        aria-label={`Move ${option.name} down`}
                        disabled={index === form.options.length - 1}
                        onClick={() => {
                          const options = [...form.options];
                          [options[index], options[index + 1]] = [
                            options[index + 1],
                            options[index],
                          ];
                          const sequence = updateForm({ ...form, options });
                          queueTransform(
                            {
                              kind: "reorder_options",
                              option_ids: options.map((item) => item.id),
                            },
                            sequence,
                          );
                        }}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove option ${option.name}`}
                        onClick={() =>
                          void previewOptionRemoval(option.id, option.name)
                        }
                      >
                        Remove
                      </button>
                    </div>
                    <div className="option-fields">
                      <label
                        className="visually-hidden"
                        htmlFor={`option-name-${option.id}`}
                      >
                        Option name
                      </label>
                      <input
                        id={`option-name-${option.id}`}
                        value={option.name}
                        onFocus={(event) => {
                          const previous = optionOriginals.current.get(
                            option.id,
                          ) ?? {
                            name: event.currentTarget.value,
                            description: option.description ?? "",
                          };
                          optionOriginals.current.set(option.id, {
                            ...previous,
                            name: event.currentTarget.value,
                          });
                        }}
                        onChange={(event) => {
                          const options = form.options.map((item) =>
                            item.id === option.id
                              ? { ...item, name: event.target.value }
                              : item,
                          );
                          updateForm({ ...form, options });
                        }}
                        onBlur={(event) => {
                          if (
                            event.currentTarget.value !==
                            optionOriginals.current.get(option.id)?.name
                          )
                            queueTransform({
                              kind: "rename_option",
                              id: option.id,
                              name: event.currentTarget.value,
                            });
                        }}
                      />
                      <label
                        className="visually-hidden"
                        htmlFor={`option-description-${option.id}`}
                      >
                        Option description
                      </label>
                      <input
                        id={`option-description-${option.id}`}
                        value={option.description ?? ""}
                        placeholder="Description (optional)"
                        onFocus={(event) => {
                          const previous = optionOriginals.current.get(
                            option.id,
                          ) ?? {
                            name: option.name,
                            description: option.description ?? "",
                          };
                          optionOriginals.current.set(option.id, {
                            ...previous,
                            description: event.currentTarget.value,
                          });
                        }}
                        onChange={(event) => {
                          const options = form.options.map((item) =>
                            item.id === option.id
                              ? { ...item, description: event.target.value }
                              : item,
                          );
                          updateForm({ ...form, options });
                        }}
                        onBlur={(event) => {
                          if (
                            event.currentTarget.value !==
                            optionOriginals.current.get(option.id)?.description
                          )
                            queueTransform({
                              kind: "describe_option",
                              id: option.id,
                              description: event.currentTarget.value,
                            });
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ol>
            </section>
            <section
              className="section input-configuration"
              aria-labelledby="input-heading"
            >
              <h2 id="input-heading">Input</h2>
              <fieldset className="input-kind-control">
                <legend>Format sent to the model</legend>
                {(["text", "json"] as const).map((kind) => (
                  <label key={kind}>
                    <input
                      type="radio"
                      name="input-kind"
                      checked={form.input_kind === kind}
                      onChange={() => {
                        const sequence = updateForm({
                          ...form,
                          input_kind: kind,
                        });
                        queueTransform(
                          { kind: "set_input_kind", input_kind: kind },
                          sequence,
                        );
                      }}
                    />
                    {kind === "text" ? "Text" : "JSON"}
                  </label>
                ))}
              </fieldset>
              {form.input_kind === "json" && (
                <div className="field">
                  <fieldset>
                    <legend>Selected top-level fields</legend>
                    {form.selected_fields.map((field, index) => (
                      <div className="selected-field-row" key={index}>
                        <label
                          className="visually-hidden"
                          htmlFor={`selected-field-${index}`}
                        >
                          Selected field name
                        </label>
                        <input
                          id={`selected-field-${index}`}
                          value={field}
                          onFocus={(event) =>
                            selectedFieldOriginals.current.set(
                              index,
                              event.currentTarget.value,
                            )
                          }
                          onChange={(event) => {
                            const fields = [...form.selected_fields];
                            fields[index] = event.target.value;
                            updateForm({ ...form, selected_fields: fields });
                          }}
                          onBlur={(event) => {
                            const fields = [...form.selected_fields];
                            fields[index] = event.currentTarget.value;
                            if (
                              event.currentTarget.value !==
                              selectedFieldOriginals.current.get(index)
                            )
                              queueTransform({
                                kind: "set_selected_fields",
                                selected_fields: fields,
                              });
                          }}
                        />
                        <button
                          type="button"
                          aria-label={`Remove selected field ${field || index + 1}`}
                          onClick={() => {
                            const fields = form.selected_fields.filter(
                              (_item, fieldIndex) => fieldIndex !== index,
                            );
                            const sequence = updateForm({
                              ...form,
                              selected_fields: fields,
                            });
                            queueTransform(
                              {
                                kind: "set_selected_fields",
                                selected_fields: fields,
                              },
                              sequence,
                            );
                          }}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <label htmlFor="new-selected-field">
                      Add a top-level field name
                    </label>
                    <input
                      id="new-selected-field"
                      value={newFieldName}
                      onChange={(event) => setNewFieldName(event.target.value)}
                      onBlur={() => {
                        if (!newFieldName) return;
                        const fields = [...form.selected_fields, newFieldName];
                        const sequence = updateForm({
                          ...form,
                          selected_fields: fields,
                        });
                        queueTransform(
                          {
                            kind: "set_selected_fields",
                            selected_fields: fields,
                          },
                          sequence,
                        );
                        setNewFieldName("");
                      }}
                    />
                  </fieldset>
                  <p className="muted">
                    The full input is validated before these fields are
                    selected.
                  </p>
                </div>
              )}
              <JsonSourceEditor
                label="Advanced JSON Schema source"
                value={form.input_schema_source ?? ""}
                onCompositionStart={() => {
                  composingSource.current = true;
                }}
                onCompositionEnd={(event) => {
                  composingSource.current = false;
                  if (!schemaBlurredWhileComposing.current) return;
                  schemaBlurredWhileComposing.current = false;
                  const original = schemaOriginal.current;
                  schemaOriginal.current = undefined;
                  if (event.currentTarget.value !== original)
                    queueTransform({
                      kind: "replace_schema",
                      input_schema_source: event.currentTarget.value || null,
                    });
                }}
                onFocus={(event) => {
                  schemaOriginal.current = event.currentTarget.value;
                }}
                onBlur={(event) => {
                  if (composingSource.current) {
                    schemaBlurredWhileComposing.current = true;
                    return;
                  }
                  if (event.currentTarget.value !== schemaOriginal.current)
                    queueTransform({
                      kind: "replace_schema",
                      input_schema_source: event.currentTarget.value || null,
                    });
                  schemaOriginal.current = undefined;
                }}
                onChange={(schemaSource) => {
                  const next = {
                    ...form,
                    input_schema_source: schemaSource || null,
                  };
                  updateForm(next);
                }}
              />
            </section>
          </>
        ) : (
          <section className="section">
            <p className="warning-summary">
              The service could not safely project this draft into fields. Edit
              its source directly; the original content remains available.
            </p>
          </section>
        )}
        <details className="section advanced-source">
          <summary>Advanced editor source</summary>
          <JsonSourceEditor
            label="Decision source"
            value={source}
            onChange={changeRawSource}
          />
        </details>
        <section className="section revision-note">
          <label htmlFor="revision-note">Version note (optional)</label>
          <input
            id="revision-note"
            value={note}
            disabled={versionOutcomeUnknown}
            onChange={(event) => setNote(event.target.value)}
          />
          <p className="muted">
            Invalid drafts remain editable and saved. Save version reports any
            validation block.
          </p>
        </section>
        {removalReview && (
          <Modal
            title={`Remove ${removalReview.optionName}?`}
            onDismiss={() => setRemovalReview(undefined)}
          >
            <div className="modal-body">
              <p>
                Existing expected answers that reference this option will remain
                in history and become visibly incompatible. Review the affected
                records before applying the draft edit.
              </p>
              {removalReview.review.incompatible_references === null ? (
                <p role="status">
                  The service could not compute affected references for this
                  invalid definition.
                </p>
              ) : removalReview.review.incompatible_references.length ? (
                <ul className="impact-list" aria-label="Affected references">
                  {removalReview.review.incompatible_references.map(
                    (reference, index) => (
                      <li key={`${reference.resource_id}-${index}`}>
                        <code>{reference.kind}</code>{" "}
                        <code>{reference.resource_id}</code>
                        <span className="muted">
                          {" "}
                          · case {reference.case_id}
                        </span>
                      </li>
                    ),
                  )}
                </ul>
              ) : (
                <p className="muted">
                  The service reported no affected references.
                </p>
              )}
              {removalReview.review.transform.validation_advice.length > 0 && (
                <ul aria-label="Definition validation advice">
                  {removalReview.review.transform.validation_advice.map(
                    (item, index) => (
                      <li key={`${item.code}-${index}`}>
                        <code>{item.kind}</code> <code>{item.code}</code>
                      </li>
                    ),
                  )}
                </ul>
              )}
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => void confirmOptionRemoval()}
                >
                  Remove option from draft
                </button>
                <button
                  type="button"
                  onClick={() => setRemovalReview(undefined)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </Modal>
        )}
        {archiveConfirm && (
          <Modal
            title={
              record.decision.record.archived
                ? "Restore this decision?"
                : "Archive this decision?"
            }
            onDismiss={() => {
              if (!renameWorking && !archiveOutcomeUnknown)
                setArchiveConfirm(false);
            }}
          >
            <div className="modal-body">
              <p>
                {record.decision.record.archived
                  ? "This decision will return to the active project list."
                  : "The decision will leave the active list. Its drafts, saved versions, labels, and evidence stay available."}
              </p>
              {archiveOutcomeUnknown && (
                <p role="status">
                  The archive outcome may be unknown. Retry the same request
                  before closing this confirmation.
                </p>
              )}
              {editError && <ErrorSummary message={editError} />}
              <div className="actions">
                <button
                  className="primary"
                  disabled={renameWorking}
                  onClick={() => void toggleArchive()}
                >
                  {archiveOutcomeUnknown
                    ? `Retry same ${archiveAction.current ?? "decision"} action`
                    : record.decision.record.archived
                      ? "Restore decision"
                      : "Archive decision"}
                </button>
                <button
                  disabled={renameWorking || archiveOutcomeUnknown}
                  onClick={() => setArchiveConfirm(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </Modal>
        )}
      </article>
      {dirtyGuard.prompt}
    </>
  );
}

function uncertainOutcome(cause: unknown): boolean {
  return isOutcomeUnknown(cause);
}

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
import {
  isOutcomeUnknown,
  QueuedMutationNotAdmitted,
} from "../../workspace/mutation-controller";

type DecisionDTO = ApiOperationData<"readDecision">;
type EditorForm = NonNullable<
  ApiOperationData<"projectDecisionEditor">["form"]
>;
type EditorEdit = ApiOperationBody<"transformDecisionEditor">["edit"];
type TransformReview = ApiOperationData<"transformDecisionEditor">;
type TransformResult = "ready" | "paused" | "failed";
type VersionPreflightReason =
  | "composing-before-save"
  | "original-save-unavailable"
  | "composing-before-retry"
  | "transform-paused"
  | "transform-failed"
  | "composing-after-transform"
  | "unrepresented-editor"
  | "editor-changed"
  | "editor-changed-during-draft-save"
  | "draft-unsaved"
  | "draft-controller-not-ready"
  | "saved-version-context-pending"
  | "editor-changed-during-read"
  | "saved-draft-mismatch"
  | "composing-before-mutation";
const VERSION_PREFLIGHT_MESSAGES: Record<VersionPreflightReason, string> = {
  "composing-before-save":
    "Finish composing the editor source before saving a version.",
  "original-save-unavailable":
    "The original version save is unavailable. Review the current version history before continuing.",
  "composing-before-retry":
    "Finish composing before retrying the original version save.",
  "transform-paused":
    "Finish composing or committing the editor source. No version was saved.",
  "transform-failed":
    "The latest editor change could not be applied. No version was saved.",
  "composing-after-transform":
    "Finish composing the editor source. No version was saved.",
  "unrepresented-editor":
    "Commit the latest editor change. No version was saved.",
  "editor-changed": "The editor changed. No version was saved.",
  "editor-changed-during-draft-save":
    "The editor changed while saving its draft. No version was saved.",
  "draft-unsaved": "The latest draft is not saved. No version was saved.",
  "draft-controller-not-ready":
    "The draft is not ready for a version save. Review its save status before continuing.",
  "saved-version-context-pending":
    "A version was saved. Refresh or review its draft context before saving another version.",
  "editor-changed-during-read":
    "The editor changed while checking the saved draft. No version was saved.",
  "saved-draft-mismatch":
    "The saved draft differs from the editor. Review it before saving a version.",
  "composing-before-mutation":
    "Finish composing before saving this version. The original request was not changed.",
};
class VersionPreflightError extends Error {
  constructor(reason: VersionPreflightReason) {
    super(VERSION_PREFLIGHT_MESSAGES[reason]);
    this.name = "VersionPreflightError";
  }
}
type VersionBaselineContext = {
  request: ApiOperationBody<"saveDecisionRevision">;
  editorSource: string;
  generation: number;
  sourceSequence: number;
  revisionId?: string;
};
type VersionBaselineIssue = {
  kind: "refreshing" | "read-failed" | "incompatible" | "controller-not-ready";
  message?: string;
};
type QueuedTransform = {
  edit: EditorEdit;
  sequence: number;
  sourceSequence: number;
  generation: number;
};
type DeferredTransform = {
  queued: QueuedTransform;
  response: TransformReview;
};
type SourceEditor = "schema" | "raw";

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
  onArchiveChanged: () => Promise<void>;
}) {
  const [record, setRecord] = useState<DecisionDTO>();
  const [form, setForm] = useState<EditorForm | null>(null);
  const formRef = useRef<EditorForm | null>(null);
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [loadError, setLoadError] = useState<string>();
  const [editError, setEditError] = useState<string>();
  const [transformError, setTransformError] = useState<string>();
  const [transformFailed, setTransformFailed] = useState(false);
  const [draftStatus, setDraftStatus] = useState<DraftSaveStatus>({
    kind: "idle",
  });
  const [draftDirty, setDraftDirty] = useState(false);
  const [working, setWorking] = useState(false);
  const [sourceControlsLocked, setSourceControlsLocked] = useState(false);
  const [, setCompositionBoundary] = useState(0);
  const [renameWorking, setRenameWorking] = useState(false);
  const [versionOutcomeUnknown, setVersionOutcomeUnknown] = useState(false);
  const [versionBaselineIssue, setVersionBaselineIssue] =
    useState<VersionBaselineIssue>();
  const [renameOutcomeUnknown, setRenameOutcomeUnknown] = useState(false);
  const [archiveOutcomeUnknown, setArchiveOutcomeUnknown] = useState(false);
  const [note, setNote] = useState("");
  const [notice, setNotice] = useState<string>();
  const [newFieldName, setNewFieldName] = useState("");
  const [removalReview, setRemovalReview] = useState<{
    optionId: string;
    optionName: string;
    review: TransformReview;
    sourceSequence: number;
    generation: number;
    source: string;
  }>();
  const [archiveConfirm, setArchiveConfirm] = useState(false);
  const sourceRef = useRef(source);
  const draftDirtyRef = useRef(false);
  const recordRef = useRef<DecisionDTO | undefined>(undefined);
  const draftEtagRef = useRef("");
  const sourceSequence = useRef(0);
  const formSequence = useRef(0);
  const editGeneration = useRef(0);
  const representedGeneration = useRef(0);
  const emptyCompositionGeneration = useRef<number | undefined>(undefined);
  const selectedFieldOriginals = useRef(new Map<number, string>());
  const instructionOriginal = useRef<string | undefined>(undefined);
  const optionOriginals = useRef(
    new Map<string, { name: string; description: string }>(),
  );
  const schemaOriginal = useRef<string | undefined>(undefined);
  const composingSource = useRef(false);
  const compositionEditor = useRef<SourceEditor | undefined>(undefined);
  const compositionBaseline = useRef<string | undefined>(undefined);
  const compositionGenerationBefore = useRef(0);
  const compositionDirtyBefore = useRef(false);
  const compositionCommitPending = useRef(false);
  const sourceControlsLockedRef = useRef(false);
  const transformQueue = useRef<QueuedTransform[]>([]);
  const deferredTransform = useRef<DeferredTransform | undefined>(undefined);
  const transformTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const transforming = useRef(false);
  const transformTask = useRef<Promise<TransformResult> | undefined>(undefined);
  const transformState = useRef<TransformResult>("ready");
  const autosave = useRef<DraftAutosaveController | undefined>(undefined);
  const lastAcknowledgedSource = useRef<string | undefined>(undefined);
  const versionRequest = useRef<
    ApiOperationBody<"saveDecisionRevision"> | undefined
  >(undefined);
  const versionBaselineContext = useRef<VersionBaselineContext | undefined>(
    undefined,
  );
  const versionBaselinePending = useRef(false);
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
  const pageLoadLifetime = useRef(0);
  const removalIdentity = useRef<
    { sourceSequence: number; generation: number; source: string } | undefined
  >(undefined);

  const setBackingSource = useCallback((next: string) => {
    sourceRef.current = next;
    setSource(next);
  }, []);

  function setDraftDirtyNow(dirty: boolean) {
    draftDirtyRef.current = dirty;
    setDraftDirty(dirty);
  }

  function setEditorForm(next: EditorForm | null) {
    formRef.current = next;
    setForm(next);
  }

  function setSourceControlsLockedNow(locked: boolean) {
    sourceControlsLockedRef.current = locked;
    setSourceControlsLocked(locked);
  }

  function publishCompositionBoundary() {
    setCompositionBoundary((revision) => revision + 1);
  }

  function hasPendingEditorWork() {
    return (
      composingSource.current ||
      compositionCommitPending.current ||
      deferredTransform.current !== undefined ||
      transformQueue.current.length > 0 ||
      transformTask.current !== undefined ||
      editGeneration.current !== representedGeneration.current ||
      transformState.current !== "ready"
    );
  }

  function reconcileAcknowledgedDraft() {
    if (
      transformState.current === "ready" &&
      !composingSource.current &&
      !compositionCommitPending.current &&
      transformQueue.current.length === 0 &&
      deferredTransform.current === undefined &&
      transformTask.current === undefined &&
      editGeneration.current === representedGeneration.current &&
      sourceRef.current === lastAcknowledgedSource.current
    )
      setDraftDirtyNow(false);
  }

  function markSourceEdited() {
    editGeneration.current += 1;
    draftDirtyRef.current = true;
    setDraftDirty(true);
    return editGeneration.current;
  }

  function snapshotIsCurrent(
    generation: number,
    sequence: number,
    editorSource: string,
  ) {
    return (
      !composingSource.current &&
      !compositionCommitPending.current &&
      editGeneration.current === generation &&
      representedGeneration.current === generation &&
      sourceSequence.current === sequence &&
      sourceRef.current === editorSource &&
      transformQueue.current.length === 0 &&
      deferredTransform.current === undefined &&
      transformTask.current === undefined &&
      transformState.current === "ready"
    );
  }

  useEffect(() => {
    let active = true;
    const lifetime = ++pageLoadLifetime.current;
    const controller = new AbortController();
    const previousAutosave = autosave.current;
    autosave.current = undefined;
    previousAutosave?.dispose();
    transformTask.current = undefined;
    transforming.current = false;
    transformQueue.current = [];
    deferredTransform.current = undefined;
    transformState.current = "paused";
    actionLock.current = false;
    versionRequest.current = undefined;
    versionBaselineContext.current = undefined;
    versionBaselinePending.current = false;
    archiveRequest.current = undefined;
    archiveAction.current = undefined;
    setArchiveOutcomeUnknown(false);
    setArchiveConfirm(false);
    setVersionOutcomeUnknown(false);
    setVersionBaselineIssue(undefined);
    setWorking(false);
    setSourceControlsLockedNow(false);
    let pageAutosave: DraftAutosaveController | undefined;
    setLoadError(undefined);
    setRecord(undefined);
    setEditorForm(null);
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
        editGeneration.current += 1;
        representedGeneration.current = editGeneration.current;
        transformQueue.current = [];
        deferredTransform.current = undefined;
        emptyCompositionGeneration.current = undefined;
        transformState.current = "ready";
        setTransformFailed(false);
        setTransformError(undefined);
        composingSource.current = false;
        compositionEditor.current = undefined;
        compositionCommitPending.current = false;
        lastAcknowledgedSource.current = result.data.draft.record.editor_source;
        setBackingSource(result.data.draft.record.editor_source);
        setDraftDirtyNow(false);
        setEditorForm(projection.data.form);
        pageAutosave = new DraftAutosaveController(
          result.data.draft.etag,
          async (request) => {
            if (
              !active ||
              pageLoadLifetime.current !== lifetime ||
              autosave.current !== pageAutosave
            )
              throw new QueuedMutationNotAdmitted();
            const saved = await operations.updateDraft({
              registrationId,
              decisionId,
              signal: controller.signal,
              body: {
                schema_version: 1,
                editor_source: request.editorSource,
                expected_etag: request.expectedDraftEtag,
                operation_id: request.operationId,
              },
            });
            if (
              active &&
              pageLoadLifetime.current === lifetime &&
              autosave.current === pageAutosave
            ) {
              draftEtagRef.current = saved.data.etag;
              lastAcknowledgedSource.current = request.editorSource;
              if (
                request.editorSource === sourceRef.current &&
                representedGeneration.current === editGeneration.current &&
                !hasPendingEditorWork()
              )
                setDraftDirtyNow(false);
              else draftDirtyRef.current = true;
            }
            return { etag: saved.data.etag };
          },
          (status) => {
            if (
              active &&
              pageLoadLifetime.current === lifetime &&
              autosave.current === pageAutosave
            )
              setDraftStatus(status);
          },
        );
        autosave.current = pageAutosave;
        setDraftStatus({ kind: "idle" });
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted)
          setLoadError(safeMessage(cause));
      });
    return () => {
      active = false;
      if (pageLoadLifetime.current === lifetime) {
        pageLoadLifetime.current += 1;
        transformTask.current = undefined;
        transforming.current = false;
      }
      controller.abort();
      if (transformTimer.current !== undefined)
        clearTimeout(transformTimer.current);
      if (autosave.current === pageAutosave) {
        autosave.current = undefined;
        pageAutosave?.dispose();
        actionLock.current = false;
        sourceControlsLockedRef.current = false;
      }
    };
  }, [decisionId, operations, registrationId, setBackingSource]);

  const drainTransforms = useCallback((): Promise<TransformResult> => {
    if (composingSource.current || compositionCommitPending.current) {
      if (transformState.current !== "failed")
        transformState.current = "paused";
      return Promise.resolve(
        transformState.current === "failed" ? "failed" : "paused",
      );
    }
    if (transformTask.current) return transformTask.current;
    if (transformState.current === "failed") return Promise.resolve("failed");
    const draftController = autosave.current;
    const lifetime = pageLoadLifetime.current;
    if (!draftController) return Promise.resolve("paused");
    const isCurrentLifetime = () =>
      pageLoadLifetime.current === lifetime &&
      autosave.current === draftController;
    const task = (async (): Promise<TransformResult> => {
      transforming.current = true;
      let result: TransformResult = "ready";
      const apply = (queued: QueuedTransform, response: TransformReview) => {
        if (queued.sourceSequence !== sourceSequence.current) return;
        const transformed = response.transform;
        sourceRef.current = transformed.editor_source;
        setSource(transformed.editor_source);
        representedGeneration.current = queued.generation;
        draftDirtyRef.current = true;
        setDraftDirty(true);
        autosave.current?.edit(transformed.editor_source);
        if (
          queued.sequence === formSequence.current &&
          !composingSource.current
        )
          setEditorForm(transformed.projection.form);
      };
      try {
        if (!isCurrentLifetime()) return "paused";
        const deferred = deferredTransform.current;
        if (deferred) {
          if (deferred.queued.sourceSequence === sourceSequence.current) {
            if (composingSource.current) result = "paused";
            else apply(deferred.queued, deferred.response);
          }
          if (result === "ready") deferredTransform.current = undefined;
        }
        while (
          result === "ready" &&
          (deferredTransform.current !== undefined ||
            transformQueue.current.length > 0)
        ) {
          if (composingSource.current || compositionCommitPending.current) {
            result = "paused";
            break;
          }
          const queued = deferredTransform.current
            ? undefined
            : transformQueue.current.shift();
          if (!queued) {
            const pending = deferredTransform.current;
            if (!pending) break;
            apply(pending.queued, pending.response);
            deferredTransform.current = undefined;
            continue;
          }
          if (queued.sourceSequence !== sourceSequence.current) continue;
          if (
            versionBaselinePending.current ||
            versionBaselineContext.current !== undefined
          ) {
            transformQueue.current.unshift(queued);
            result = "paused";
            break;
          }
          if (!isCurrentLifetime()) {
            result = "paused";
            break;
          }
          setEditError(undefined);
          setNotice(undefined);
          try {
            await draftController.flush();
          } catch (cause) {
            if (!isCurrentLifetime()) {
              result = "paused";
              break;
            }
            if (queued.sourceSequence !== sourceSequence.current) {
              result = "paused";
              break;
            }
            transformQueue.current.unshift(queued);
            setTransformError(safeMessage(cause));
            setTransformFailed(true);
            result = "failed";
            break;
          }
          if (!isCurrentLifetime()) {
            result = "paused";
            break;
          }
          if (queued.sourceSequence !== sourceSequence.current) continue;
          if (
            composingSource.current ||
            compositionCommitPending.current ||
            versionBaselinePending.current ||
            versionBaselineContext.current !== undefined
          ) {
            transformQueue.current.unshift(queued);
            result = "paused";
            break;
          }
          const requestSource = sourceRef.current;
          const expectedDraftEtag = draftEtagRef.current;
          let response: TransformReview;
          try {
            const transformed = await operations.transformEditor({
              registrationId,
              decisionId,
              body: {
                schema_version: 1,
                editor_source: requestSource,
                expected_draft_etag: expectedDraftEtag,
                edit: queued.edit,
              },
            });
            response = transformed.data;
          } catch (cause) {
            if (!isCurrentLifetime()) {
              result = "paused";
              break;
            }
            if (queued.sourceSequence !== sourceSequence.current) continue;
            transformQueue.current.unshift(queued);
            setTransformError(safeMessage(cause));
            setTransformFailed(true);
            result = "failed";
            break;
          }
          if (!isCurrentLifetime()) {
            result = "paused";
            break;
          }
          if (queued.sourceSequence !== sourceSequence.current) continue;
          if (composingSource.current || compositionCommitPending.current) {
            deferredTransform.current = { queued, response };
            result = "paused";
            break;
          }
          apply(queued, response);
        }
        if (
          result === "ready" &&
          (composingSource.current || compositionCommitPending.current)
        )
          result = "paused";
        if (
          result === "ready" &&
          transformQueue.current.length === 0 &&
          deferredTransform.current === undefined
        ) {
          if (emptyCompositionGeneration.current !== undefined) {
            representedGeneration.current = Math.max(
              representedGeneration.current,
              emptyCompositionGeneration.current,
            );
            emptyCompositionGeneration.current = undefined;
          }
        }
        if (
          result === "ready" &&
          editGeneration.current !== representedGeneration.current
        )
          result = "paused";
      } finally {
        if (isCurrentLifetime()) {
          transforming.current = false;
          transformState.current = result;
        } else result = "paused";
      }
      return result;
    })();
    const tracked = task.finally(() => {
      if (transformTask.current === tracked) {
        transformTask.current = undefined;
        if (isCurrentLifetime()) reconcileAcknowledgedDraft();
      }
    });
    transformTask.current = tracked;
    return tracked;
  }, [decisionId, operations, registrationId]);

  const unresolvedWrite =
    versionOutcomeUnknown ||
    renameOutcomeUnknown ||
    archiveOutcomeUnknown ||
    draftStatus.kind === "outcome-unknown";
  const navigationBlockedMessage = versionBaselinePending.current
    ? "A version was saved, but its draft context is unresolved. Refresh or review it before leaving this decision."
    : unresolvedWrite
      ? "A write may have completed. Keep editing and retry its original request before leaving this decision."
      : working || renameWorking
        ? "A write is still in progress. Keep this decision open until it finishes."
        : undefined;
  const decisionIsDirtyNow = () =>
    draftDirtyRef.current ||
    hasPendingEditorWork() ||
    versionBaselinePending.current ||
    versionRequest.current !== undefined ||
    renameRequest.current !== undefined ||
    archiveRequest.current !== undefined ||
    autosave.current?.status.kind === "outcome-unknown" ||
    actionLock.current;
  const dirtyGuard = useDirtyNavigationGuard({
    dirty: decisionIsDirtyNow(),
    isDirtyNow: decisionIsDirtyNow,
    blockedMessage: navigationBlockedMessage,
    save: async () => {
      if (navigationBlockedMessage) throw new Error(navigationBlockedMessage);
      if (actionLock.current)
        throw new Error("Another decision action is still in progress.");
      if (composingSource.current || compositionCommitPending.current)
        throw new Error(
          "Finish composing the editor source before saving or leaving.",
        );
      if (transformTimer.current !== undefined) {
        clearTimeout(transformTimer.current);
        transformTimer.current = undefined;
      }
      actionLock.current = true;
      try {
        const drainResult = await drainTransforms();
        if (drainResult === "paused")
          throw new Error(
            "Finish composing or committing the editor source before leaving.",
          );
        if (drainResult === "failed")
          throw new Error(
            "A pending editor transform failed. Review the error before leaving.",
          );
        if (composingSource.current || compositionCommitPending.current)
          throw new Error("Finish composing the editor source before leaving.");
        if (editGeneration.current !== representedGeneration.current)
          throw new Error("Commit the current editor change before leaving.");
        const generation = editGeneration.current;
        const sequence = sourceSequence.current;
        const editorSource = sourceRef.current;
        setSourceControlsLockedNow(true);
        try {
          await autosave.current?.flush();
          if (!snapshotIsCurrent(generation, sequence, editorSource))
            throw new Error(
              "The editor changed while saving. Review it before leaving.",
            );
          if (draftDirtyRef.current)
            throw new Error(
              "The draft save is still pending. Review its status before leaving.",
            );
        } finally {
          setSourceControlsLockedNow(false);
        }
      } finally {
        actionLock.current = false;
      }
    },
    discard: () => {
      setDraftDirtyNow(false);
      transformQueue.current = [];
      deferredTransform.current = undefined;
      transformState.current = "ready";
      setTransformFailed(false);
      setTransformError(undefined);
      if (transformTimer.current !== undefined)
        clearTimeout(transformTimer.current);
      sourceSequence.current += 1;
      editGeneration.current += 1;
      representedGeneration.current = editGeneration.current;
      composingSource.current = false;
      compositionEditor.current = undefined;
      compositionCommitPending.current = false;
      emptyCompositionGeneration.current = undefined;
      publishCompositionBoundary();
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
    if (sourceControlsLockedRef.current) return;
    transformQueue.current.push({
      edit,
      sequence,
      sourceSequence: sourceSequence.current,
      generation: editGeneration.current,
    });
    scheduleTransformDrain();
  }

  function retryPendingTransforms() {
    if (
      transformState.current !== "failed" ||
      actionLock.current ||
      sourceControlsLockedRef.current ||
      composingSource.current ||
      compositionCommitPending.current
    )
      return;
    transformState.current = "ready";
    setTransformFailed(false);
    setTransformError(undefined);
    void drainTransforms();
  }

  function scheduleTransformDrain() {
    if (
      composingSource.current ||
      compositionCommitPending.current ||
      (transformQueue.current.length === 0 && !deferredTransform.current)
    )
      return;
    if (transformTimer.current !== undefined)
      clearTimeout(transformTimer.current);
    transformTimer.current = setTimeout(() => {
      transformTimer.current = undefined;
      if (composingSource.current || compositionCommitPending.current) return;
      void drainTransforms();
    }, 500);
  }

  function updateForm(next: EditorForm) {
    if (sourceControlsLockedRef.current) return formSequence.current;
    formSequence.current += 1;
    setEditorForm(next);
    markSourceEdited();
    return formSequence.current;
  }

  function changeRawSource(next: string) {
    if (sourceControlsLockedRef.current) return;
    if (composingSource.current && compositionEditor.current === "raw") {
      setSource(next);
      markSourceEdited();
      return;
    }
    commitRawSource(next);
  }

  function commitRawSource(next: string) {
    sourceSequence.current += 1;
    transformQueue.current = [];
    deferredTransform.current = undefined;
    emptyCompositionGeneration.current = undefined;
    transformState.current = "ready";
    setTransformFailed(false);
    setTransformError(undefined);
    if (transformTimer.current !== undefined) {
      clearTimeout(transformTimer.current);
      transformTimer.current = undefined;
    }
    setBackingSource(next);
    representedGeneration.current = markSourceEdited();
    autosave.current?.edit(next);
    const expectedSequence = sourceSequence.current;
    const expectedGeneration = editGeneration.current;
    void operations
      .projectEditor({
        registrationId,
        decisionId,
        body: { schema_version: 1, editor_source: next },
      })
      .then((result) => {
        if (
          expectedSequence === sourceSequence.current &&
          expectedGeneration === editGeneration.current
        ) {
          formSequence.current += 1;
          setEditorForm(result.data.form);
        }
      })
      .catch((cause: unknown) => {
        if (
          expectedSequence === sourceSequence.current &&
          expectedGeneration === editGeneration.current
        )
          setEditError(safeMessage(cause));
      });
  }

  function startSourceComposition(
    editor: SourceEditor,
    element: HTMLTextAreaElement,
  ) {
    if (sourceControlsLockedRef.current || composingSource.current) return;
    compositionEditor.current = editor;
    compositionBaseline.current = element.value;
    compositionGenerationBefore.current = editGeneration.current;
    compositionDirtyBefore.current = draftDirtyRef.current;
    composingSource.current = true;
    editGeneration.current += 1;
    draftDirtyRef.current = true;
    setDraftDirty(true);
    if (transformState.current !== "failed") transformState.current = "paused";
    publishCompositionBoundary();
  }

  function endSourceComposition(
    editor: SourceEditor,
    element: HTMLTextAreaElement,
  ) {
    if (compositionEditor.current !== editor) return;
    composingSource.current = false;
    compositionEditor.current = undefined;
    compositionCommitPending.current = true;
    publishCompositionBoundary();
    const baseline = compositionBaseline.current ?? element.value;
    setTimeout(() => {
      if (sourceControlsLockedRef.current) {
        compositionCommitPending.current = false;
        publishCompositionBoundary();
        return;
      }
      const committed = element.value;
      if (editor === "schema") {
        const previous = schemaOriginal.current ?? baseline;
        schemaOriginal.current = committed;
        const currentForm = formRef.current;
        if (
          currentForm &&
          (currentForm.input_schema_source ?? "") !== committed
        ) {
          formSequence.current += 1;
          setEditorForm({
            ...currentForm,
            input_schema_source: committed || null,
          });
          markSourceEdited();
        }
        if (committed !== previous) {
          queueTransform({
            kind: "replace_schema",
            input_schema_source: committed || null,
          });
        }
      } else if (committed !== baseline) {
        commitRawSource(committed);
      } else {
        setSource(baseline);
      }
      if (
        committed === baseline &&
        editGeneration.current === compositionGenerationBefore.current + 1
      )
        emptyCompositionGeneration.current = editGeneration.current;
      compositionBaseline.current = undefined;
      compositionCommitPending.current = false;
      publishCompositionBoundary();
      scheduleTransformDrain();
      if (
        committed === baseline &&
        transformQueue.current.length === 0 &&
        deferredTransform.current === undefined &&
        transformTask.current === undefined
      ) {
        if (
          transformState.current !== "failed" &&
          emptyCompositionGeneration.current === editGeneration.current
        ) {
          representedGeneration.current = Math.max(
            representedGeneration.current,
            emptyCompositionGeneration.current,
          );
          emptyCompositionGeneration.current = undefined;
          transformState.current = "ready";
        }
        reconcileAcknowledgedDraft();
      }
      compositionDirtyBefore.current = false;
    }, 0);
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

  function versionReadMatchesReceipt(
    data: DecisionDTO,
    context: VersionBaselineContext,
  ): boolean {
    const revisionId = context.revisionId;
    return (
      revisionId !== undefined &&
      data.draft.record.editor_source === context.editorSource &&
      data.draft.record.base_revision_id === revisionId &&
      data.decision.record.latest_revision_id === revisionId
    );
  }

  async function refreshSavedVersionContext(alreadyLocked = false) {
    const context = versionBaselineContext.current;
    const controller = autosave.current;
    if (
      !context?.revisionId ||
      !controller ||
      (!alreadyLocked && actionLock.current)
    )
      return;
    if (composingSource.current || compositionCommitPending.current) {
      setVersionBaselineIssue({
        kind: "controller-not-ready",
        message:
          "Finish composing the editor source before refreshing the saved version context.",
      });
      return;
    }
    if (!alreadyLocked) {
      actionLock.current = true;
      setWorking(true);
      setSourceControlsLockedNow(true);
    }
    setVersionBaselineIssue({ kind: "refreshing" });
    try {
      const refreshed = await operations.read({ registrationId, decisionId });
      if (!versionReadMatchesReceipt(refreshed.data, context)) {
        setVersionBaselineIssue({
          kind: "incompatible",
          message:
            "Version saved; the current draft or decision changed. Review current state before reapplying your edits.",
        });
        return;
      }
      if (
        autosave.current !== controller ||
        draftEtagRef.current !== context.request.expected_draft_etag ||
        !controller.adoptVersionBaseline(
          context.request.expected_draft_etag,
          refreshed.data.draft.etag,
        )
      ) {
        setVersionBaselineIssue({
          kind: "controller-not-ready",
          message:
            "Version saved; the draft controller still has unresolved work. Review its save status before refreshing again.",
        });
        return;
      }
      draftEtagRef.current = refreshed.data.draft.etag;
      recordRef.current = refreshed.data;
      setRecord(refreshed.data);
      versionBaselineContext.current = undefined;
      versionBaselinePending.current = false;
      setVersionBaselineIssue(undefined);
      if (
        sourceRef.current === context.editorSource &&
        sourceSequence.current === context.sourceSequence &&
        editGeneration.current === context.generation &&
        representedGeneration.current === context.generation &&
        !hasPendingEditorWork()
      )
        setDraftDirtyNow(false);
    } catch (cause) {
      setVersionBaselineIssue({
        kind: "read-failed",
        message: `Version saved; refresh its draft context before continuing saves. ${safeMessage(cause)}`,
      });
    } finally {
      if (!alreadyLocked) {
        setSourceControlsLockedNow(false);
        actionLock.current = false;
        setWorking(false);
      }
    }
  }

  async function reviewAndReapplySavedVersionSource() {
    const controller = autosave.current;
    if (!versionBaselineContext.current?.revisionId || !controller) return;
    if (
      composingSource.current ||
      compositionCommitPending.current ||
      hasPendingEditorWork() ||
      editGeneration.current !== representedGeneration.current
    ) {
      setVersionBaselineIssue({
        kind: "controller-not-ready",
        message:
          "Finish composing or applying the current editor changes before reviewing and reapplying them.",
      });
      return;
    }
    if (actionLock.current) return;
    actionLock.current = true;
    setWorking(true);
    setSourceControlsLockedNow(true);
    try {
      const refreshed = await operations.read({ registrationId, decisionId });
      if (autosave.current !== controller) return;
      recordRef.current = refreshed.data;
      setRecord(refreshed.data);
      draftEtagRef.current = refreshed.data.draft.etag;
      controller.reapplyAfterReview(
        refreshed.data.draft.etag,
        sourceRef.current,
      );
      setDraftDirtyNow(true);
      versionBaselineContext.current = undefined;
      versionBaselinePending.current = false;
      setVersionBaselineIssue(undefined);
      setNotice(
        "Current draft reviewed. Your retained edits can now be saved.",
      );
    } catch (cause) {
      setVersionBaselineIssue({
        kind: "read-failed",
        message: `Version saved; the current draft could not be reviewed. ${safeMessage(cause)}`,
      });
    } finally {
      setSourceControlsLockedNow(false);
      actionLock.current = false;
      setWorking(false);
    }
  }

  async function saveRevision() {
    const current = recordRef.current;
    const controller = autosave.current;
    if (!current || !controller || actionLock.current) return;
    const lifetime = pageLoadLifetime.current;
    const isCurrentPage = () =>
      pageLoadLifetime.current === lifetime && autosave.current === controller;
    if (versionBaselinePending.current) {
      setEditError(VERSION_PREFLIGHT_MESSAGES["saved-version-context-pending"]);
      return;
    }
    const entryRequest = versionRequest.current;
    const entryOutcomeUnknown = versionOutcomeUnknown;
    actionLock.current = true;
    setWorking(true);
    setEditError(undefined);
    const noteSnapshot = note;
    let phase: "preflight" | "mutating" | "committed" = "preflight";
    let attemptedRequest: ApiOperationBody<"saveDecisionRevision"> | undefined;
    let committedRevisionId: string | undefined;
    let controlsLocked = false;
    try {
      if (composingSource.current || compositionCommitPending.current)
        throw new VersionPreflightError("composing-before-save");
      let request: ApiOperationBody<"saveDecisionRevision">;
      let contextForFreshRequest: VersionBaselineContext | undefined;
      if (entryOutcomeUnknown) {
        if (!entryRequest)
          throw new VersionPreflightError("original-save-unavailable");
        if (!versionBaselineContext.current)
          throw new VersionPreflightError("original-save-unavailable");
        request = entryRequest;
        attemptedRequest = request;
        setSourceControlsLockedNow(true);
        controlsLocked = true;
        if (composingSource.current || compositionCommitPending.current)
          throw new VersionPreflightError("composing-before-retry");
      } else {
        if (transformTimer.current !== undefined) {
          clearTimeout(transformTimer.current);
          transformTimer.current = undefined;
        }
        const drainResult = await drainTransforms();
        if (!isCurrentPage()) return;
        if (drainResult === "paused")
          throw new VersionPreflightError("transform-paused");
        if (drainResult === "failed")
          throw new VersionPreflightError("transform-failed");
        if (composingSource.current || compositionCommitPending.current)
          throw new VersionPreflightError("composing-after-transform");
        if (editGeneration.current !== representedGeneration.current)
          throw new VersionPreflightError("unrepresented-editor");
        const generation = editGeneration.current;
        const sequence = sourceSequence.current;
        const editorSource = sourceRef.current;
        setSourceControlsLockedNow(true);
        controlsLocked = true;
        if (!snapshotIsCurrent(generation, sequence, editorSource))
          throw new VersionPreflightError("editor-changed");
        await controller.flush();
        if (!isCurrentPage()) return;
        if (!snapshotIsCurrent(generation, sequence, editorSource))
          throw new VersionPreflightError("editor-changed-during-draft-save");
        if (draftDirtyRef.current)
          throw new VersionPreflightError("draft-unsaved");
        const refreshed = await operations.read({ registrationId, decisionId });
        if (!isCurrentPage()) return;
        if (!snapshotIsCurrent(generation, sequence, editorSource))
          throw new VersionPreflightError("editor-changed-during-read");
        if (
          refreshed.data.draft.record.editor_source !== editorSource ||
          refreshed.data.draft.etag !== draftEtagRef.current
        )
          throw new VersionPreflightError("saved-draft-mismatch");
        request = {
          schema_version: 1,
          expected_decision_etag: refreshed.data.decision.etag,
          expected_draft_etag: refreshed.data.draft.etag,
          operation_id: operationId(),
          ...(noteSnapshot ? { note: noteSnapshot } : {}),
        };
        contextForFreshRequest = {
          request,
          editorSource,
          generation,
          sourceSequence: sequence,
        };
      }
      if (composingSource.current || compositionCommitPending.current)
        throw new VersionPreflightError("composing-before-mutation");
      if (!entryOutcomeUnknown) {
        if (!contextForFreshRequest || !controller.holdVersionBaseline())
          throw new VersionPreflightError("draft-controller-not-ready");
        versionBaselineContext.current = contextForFreshRequest;
      }
      attemptedRequest = request;
      versionRequest.current = request;
      phase = "mutating";
      if (!isCurrentPage()) return;
      const result = await operations.saveRevision({
        registrationId,
        decisionId,
        body: request,
      });
      if (!isCurrentPage()) return;
      phase = "committed";
      committedRevisionId = result.data.revision.record.id;
      versionRequest.current = undefined;
      setVersionOutcomeUnknown(false);
      setNote("");
      setNotice(`Saved version ${committedRevisionId}.`);
      const context = versionBaselineContext.current;
      if (context) {
        context.revisionId = committedRevisionId;
        versionBaselinePending.current = true;
        setVersionBaselineIssue({ kind: "refreshing" });
        await refreshSavedVersionContext(true);
      } else {
        versionBaselinePending.current = true;
        setVersionBaselineIssue({
          kind: "controller-not-ready",
          message:
            "Version saved; its draft context is unavailable. Review current state before continuing.",
        });
      }
    } catch (cause) {
      if (!isCurrentPage()) return;
      if (phase === "preflight") {
        if (entryOutcomeUnknown) {
          versionRequest.current = entryRequest;
          setVersionOutcomeUnknown(true);
        } else {
          controller.releaseVersionBaseline();
          versionBaselineContext.current = undefined;
          versionBaselinePending.current = false;
          setVersionBaselineIssue(undefined);
          versionRequest.current = undefined;
          setVersionOutcomeUnknown(false);
        }
        setEditError(
          cause instanceof VersionPreflightError
            ? cause.message
            : safeMessage(cause),
        );
      } else if (phase === "mutating") {
        if (uncertainOutcome(cause) && attemptedRequest) {
          versionRequest.current = attemptedRequest;
          setVersionOutcomeUnknown(true);
        } else {
          controller.releaseVersionBaseline();
          versionBaselineContext.current = undefined;
          versionBaselinePending.current = false;
          setVersionBaselineIssue(undefined);
          versionRequest.current = undefined;
          setVersionOutcomeUnknown(false);
        }
        setEditError(safeMessage(cause));
      } else {
        versionRequest.current = undefined;
        setVersionOutcomeUnknown(false);
        setNotice(
          committedRevisionId
            ? `Saved version ${committedRevisionId}.`
            : "Version save confirmed.",
        );
        setEditError(
          `The version was saved, but its result could not be displayed. ${safeMessage(cause)}`,
        );
      }
    } finally {
      if (isCurrentPage()) {
        if (controlsLocked) setSourceControlsLockedNow(false);
        actionLock.current = false;
        setWorking(false);
      }
    }
  }

  async function toggleArchive() {
    const current = recordRef.current;
    if (!current || actionLock.current) return;
    const lifetime = pageLoadLifetime.current;
    const isCurrentPage = () => pageLoadLifetime.current === lifetime;
    actionLock.current = true;
    setRenameWorking(true);
    setEditError(undefined);
    let receipt: ApiOperationData<"archiveDecision"> | undefined;
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
        receipt = (
          await operations.restore({ registrationId, decisionId, body })
        ).data;
      } else {
        receipt = (
          await operations.archive({ registrationId, decisionId, body })
        ).data;
      }
    } catch (cause) {
      if (!isCurrentPage()) return;
      if (uncertainOutcome(cause)) setArchiveOutcomeUnknown(true);
      else {
        archiveRequest.current = undefined;
        archiveAction.current = undefined;
      }
      setEditError(safeMessage(cause));
      actionLock.current = false;
      setRenameWorking(false);
      return;
    }

    if (!receipt || !isCurrentPage()) return;
    archiveRequest.current = undefined;
    archiveAction.current = undefined;
    setArchiveOutcomeUnknown(false);
    setArchiveConfirm(false);
    const updated = { ...current, decision: receipt };
    recordRef.current = updated;
    setRecord(updated);
    actionLock.current = false;
    setRenameWorking(false);
    setNotice(
      receipt.record.archived ? "Decision archived." : "Decision restored.",
    );
    try {
      await onArchiveChanged();
    } catch (cause) {
      if (isCurrentPage())
        setEditError(
          `The decision was updated, but the project view could not be refreshed. ${safeMessage(cause)}`,
        );
    }
  }

  async function previewOptionRemoval(optionId: string, optionName: string) {
    if (actionLock.current) return;
    if (composingSource.current || compositionCommitPending.current) {
      setEditError(
        "Finish composing the editor source before reviewing option removal.",
      );
      return;
    }
    actionLock.current = true;
    setEditError(undefined);
    let reviewOpened = false;
    if (transformTimer.current !== undefined) {
      clearTimeout(transformTimer.current);
      transformTimer.current = undefined;
    }
    try {
      const drainResult = await drainTransforms();
      if (drainResult === "paused")
        throw new Error(
          "Finish composing or committing the editor source before removing an option.",
        );
      if (drainResult === "failed")
        throw new Error(
          "A pending editor transform failed. Review the error before removing this option.",
        );
      if (composingSource.current || compositionCommitPending.current)
        throw new Error(
          "Finish composing the editor source before removal review.",
        );
      if (editGeneration.current !== representedGeneration.current)
        throw new Error(
          "Commit the current editor change before removal review.",
        );
      const generation = editGeneration.current;
      const sequence = sourceSequence.current;
      const editorSource = sourceRef.current;
      setSourceControlsLockedNow(true);
      await autosave.current?.flush();
      if (!snapshotIsCurrent(generation, sequence, editorSource))
        throw new Error(
          "The editor changed. Start a new option removal review.",
        );
      if (draftDirtyRef.current)
        throw new Error(
          "The draft is not saved. Review its status before removal.",
        );
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
      if (!snapshotIsCurrent(generation, sequence, editorSource))
        throw new Error(
          "The editor changed. Start a new option removal review.",
        );
      removalIdentity.current = {
        generation,
        sourceSequence: sequence,
        source: editorSource,
      };
      setRemovalReview({
        optionId,
        optionName,
        review: result.data,
        generation,
        sourceSequence: sequence,
        source: editorSource,
      });
      reviewOpened = true;
    } catch (cause) {
      setEditError(safeMessage(cause));
    } finally {
      if (!reviewOpened) {
        setSourceControlsLockedNow(false);
        actionLock.current = false;
      }
    }
  }

  function cancelOptionRemoval() {
    removalIdentity.current = undefined;
    setRemovalReview(undefined);
    setSourceControlsLockedNow(false);
    actionLock.current = false;
  }

  async function confirmOptionRemoval() {
    const identity = removalIdentity.current;
    if (!removalReview || !identity || !actionLock.current) return;
    if (
      composingSource.current ||
      compositionCommitPending.current ||
      !snapshotIsCurrent(
        identity.generation,
        identity.sourceSequence,
        identity.source,
      )
    ) {
      setEditError(
        "The editor changed. Review the current source before removing an option.",
      );
      cancelOptionRemoval();
      return;
    }
    const transformed = removalReview.review.transform;
    sourceSequence.current += 1;
    transformQueue.current = [];
    deferredTransform.current = undefined;
    setBackingSource(transformed.editor_source);
    representedGeneration.current = markSourceEdited();
    formSequence.current += 1;
    setEditorForm(transformed.projection.form);
    setRemovalReview(undefined);
    removalIdentity.current = undefined;
    autosave.current?.edit(transformed.editor_source);
    transformState.current = "ready";
    setSourceControlsLockedNow(false);
    actionLock.current = false;
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
              : draftStatus.kind === "outcome-unknown"
                ? "Save outcome unknown"
                : draftStatus.kind === "conflict"
                  ? "Draft conflict"
                  : draftDirty || hasPendingEditorWork()
                    ? "Changes not saved"
                    : draftStatus.kind === "saved"
                      ? "Draft saved"
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
            disabled={
              working ||
              versionBaselinePending.current ||
              (versionOutcomeUnknown && !versionRequest.current)
            }
            onClick={() => void saveRevision()}
          >
            {working
              ? "Saving version…"
              : versionBaselinePending.current
                ? "Refreshing saved draft…"
                : versionOutcomeUnknown
                  ? versionRequest.current
                    ? "Retry same version save"
                    : "Original version save unavailable"
                  : "Save version"}
          </button>
        </div>
        {editError && <ErrorSummary message={editError} />}
        {transformError && <ErrorSummary message={transformError} />}
        {transformFailed && (
          <button
            type="button"
            disabled={
              sourceControlsLocked ||
              composingSource.current ||
              compositionCommitPending.current
            }
            onClick={retryPendingTransforms}
          >
            Retry pending edits
          </button>
        )}
        {notice && (
          <p className="save-status" role="status">
            {notice}
          </p>
        )}
        {versionBaselineIssue && (
          <section
            className="warning-summary"
            aria-label="Saved version draft context"
          >
            <p>
              {versionBaselineIssue.message ??
                "Refreshing the saved version draft context…"}
            </p>
            {versionBaselineIssue.kind !== "refreshing" && (
              <button
                type="button"
                disabled={working}
                onClick={() => void refreshSavedVersionContext()}
              >
                Refresh saved version context
              </button>
            )}
            {(versionBaselineIssue.kind === "incompatible" ||
              versionBaselineIssue.kind === "controller-not-ready") && (
              <button
                type="button"
                disabled={
                  working ||
                  composingSource.current ||
                  compositionCommitPending.current
                }
                onClick={() => void reviewAndReapplySavedVersionSource()}
              >
                Review current and reapply my source
              </button>
            )}
          </section>
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
        <fieldset
          className="authoring-source-controls"
          disabled={sourceControlsLocked}
        >
          <legend className="visually-hidden">Decision source controls</legend>
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
                    if (
                      event.currentTarget.value !== instructionOriginal.current
                    )
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
                              optionOriginals.current.get(option.id)
                                ?.description
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
                        onChange={(event) =>
                          setNewFieldName(event.target.value)
                        }
                        onBlur={() => {
                          if (!newFieldName) return;
                          const fields = [
                            ...form.selected_fields,
                            newFieldName,
                          ];
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
                  readOnly={sourceControlsLocked}
                  onCompositionStart={(event) => {
                    startSourceComposition("schema", event.currentTarget);
                  }}
                  onCompositionEnd={(event) => {
                    endSourceComposition("schema", event.currentTarget);
                  }}
                  onFocus={(event) => {
                    schemaOriginal.current = event.currentTarget.value;
                  }}
                  onBlur={(event) => {
                    if (composingSource.current) {
                      return;
                    }
                    if (event.currentTarget.value !== schemaOriginal.current)
                      queueTransform({
                        kind: "replace_schema",
                        input_schema_source: event.currentTarget.value || null,
                      });
                    schemaOriginal.current = event.currentTarget.value;
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
                The service could not safely project this draft into fields.
                Edit its source directly; the original content remains
                available.
              </p>
            </section>
          )}
          <details className="section advanced-source">
            <summary>Advanced editor source</summary>
            <JsonSourceEditor
              label="Decision source"
              value={source}
              readOnly={sourceControlsLocked}
              onCompositionStart={(event) => {
                startSourceComposition("raw", event.currentTarget);
              }}
              onCompositionEnd={(event) => {
                endSourceComposition("raw", event.currentTarget);
              }}
              onChange={changeRawSource}
            />
          </details>
        </fieldset>
        <section className="section revision-note">
          <label htmlFor="revision-note">Version note (optional)</label>
          <input
            id="revision-note"
            value={note}
            disabled={versionOutcomeUnknown || sourceControlsLocked}
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
            onDismiss={cancelOptionRemoval}
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
                <button type="button" onClick={cancelOptionRemoval}>
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

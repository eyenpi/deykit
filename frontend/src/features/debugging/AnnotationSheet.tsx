import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { safeMessage } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway } from "../../workspace/gateway";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { useRenderedScopeEpoch } from "./useRenderedScopeEpoch";

type AddBody = ApiOperationBody<"addAnnotation">;
type Annotation = ApiOperationData<"readAnnotation">;
type AnnotationIntent = {
  registrationId: string;
  runId: string;
  caseId: string;
  body: AddBody;
  scopeEpoch: number;
  operations: DebuggingGateway["annotations"];
};

export function AnnotationSheet({
  registrationId,
  runId,
  caseId,
  operations,
  navigation,
  onClose,
}: {
  registrationId: string;
  runId: string;
  caseId: string;
  operations: DebuggingGateway["annotations"];
  navigation: WorkspaceNavigation;
  onClose: () => void;
}) {
  const scopeEpoch = useRenderedScopeEpoch(
    `${registrationId}|${runId}|${caseId}`,
  );
  const scopeEpochRef = useRef(scopeEpoch);
  scopeEpochRef.current = scopeEpoch;
  const [noteView, setNoteView] = useState({ scopeEpoch, value: "" });
  const note = noteView.scopeEpoch === scopeEpoch ? noteView.value : "";
  function setNote(value: string) {
    setNoteView({ scopeEpoch, value });
  }
  const [itemsView, setItemsView] = useState<{
    scopeEpoch: number;
    value: readonly Annotation[];
  }>({ scopeEpoch, value: [] });
  const items = itemsView.scopeEpoch === scopeEpoch ? itemsView.value : [];
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState<string>();
  const [confirmClose, setConfirmClose] = useState(false);
  const [view, setView] = useState<{
    scopeEpoch: number;
    state: MutationState<Annotation>;
  }>({ scopeEpoch, state: { kind: "idle" } });
  const mutation = useRef<
    RetainedMutation<AnnotationIntent, Annotation> | undefined
  >(undefined);
  if (!mutation.current) {
    mutation.current = new RetainedMutation(
      async (intent) => {
        const result = await intent.operations.add({
          registrationId: intent.registrationId,
          runId: intent.runId,
          caseId: intent.caseId,
          body: intent.body,
        });
        const receipt = result.data;
        if (
          receipt.run_id !== intent.runId ||
          receipt.case_id !== intent.caseId ||
          receipt.note !== intent.body.note
        )
          throw new Error("The annotation receipt did not match this case.");
        return receipt;
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
  const dirty = note.trim().length > 0;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty,
    isDirtyNow: () => dirtyRef.current,
    save: async () => {
      const receipt = await submit();
      if (!receipt) throw new Error("The annotation could not be confirmed.");
    },
    discard: () => setNote(""),
    blockedMessage: busy
      ? "The annotation request may have been saved. Retry that original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `${registrationId}:annotation:${runId}:${caseId}`,
        guard,
      ),
    [caseId, guard, navigation, registrationId, runId],
  );

  async function refresh(signal?: AbortSignal) {
    const epoch = scopeEpochRef.current;
    setLoading(true);
    setReadError(undefined);
    try {
      const result = await operations.list({
        registrationId,
        runId,
        query: { case_id: caseId, limit: 50 },
        signal,
      });
      const matching = result.data.items.filter(
        (item) => item.run_id === runId && item.case_id === caseId,
      );
      if (matching.length !== result.data.items.length)
        throw new Error("The annotation list included a different case.");
      if (epoch === scopeEpochRef.current && !signal?.aborted)
        setItemsView({ scopeEpoch: epoch, value: matching });
    } catch (cause) {
      if (epoch === scopeEpochRef.current && !signal?.aborted)
        setReadError(safeMessage(cause));
    } finally {
      if (epoch === scopeEpochRef.current && !signal?.aborted)
        setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [caseId, registrationId, runId, operations]);

  async function submit(): Promise<Annotation | undefined> {
    const cleanedNote = note.trim();
    if (!cleanedNote || cleanedNote.length > 16_384 || busy) return undefined;
    const body: AddBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      case_id: caseId,
      note: cleanedNote,
    };
    const epoch = scopeEpochRef.current;
    const receipt = await mutation.current?.submit({
      registrationId,
      runId,
      caseId,
      body,
      scopeEpoch: epoch,
      operations,
    });
    if (receipt && epoch === scopeEpochRef.current) {
      setNote("");
      await refresh();
    }
    return receipt;
  }

  async function retryOriginal() {
    const owner = mutation.current?.originalRequest;
    const receipt = await mutation.current?.retryOriginal();
    if (receipt && owner?.scopeEpoch === scopeEpochRef.current) {
      setNote("");
      await refresh();
    }
  }

  function submitForm(event: FormEvent) {
    event.preventDefault();
    void submit();
  }

  return (
    <>
      <Modal
        title="Case annotations"
        onDismiss={() => {
          if (busy) return;
          if (dirty) setConfirmClose(true);
          else onClose();
        }}
        sheet
      >
        <div className="modal-body">
          <p>
            Add a separate append-only note to case <code>{caseId}</code> in run{" "}
            <code>{runId}</code>. This does not change the saved result or call
            a provider.
          </p>
          {state.kind === "outcome-unknown" && (
            <ErrorSummary message={state.message} />
          )}
          {retainedViewStale && mutationKind === "outcome-unknown" && (
            <section role="status">
              <p>
                An earlier case annotation is unresolved and can only be retried
                unchanged.
              </p>
              <button type="button" onClick={() => void retryOriginal()}>
                Retry original unchanged annotation
              </button>
            </section>
          )}
          {retainedViewStale && mutationKind === "committed" && (
            <button
              type="button"
              onClick={() => {
                mutation.current?.reset();
                setView({ scopeEpoch, state: { kind: "idle" } });
              }}
            >
              Start a new annotation for this case
            </button>
          )}
          {(state.kind === "failed" || state.kind === "conflict") && (
            <ErrorSummary message={state.message} />
          )}
          {state.kind === "committed" && (
            <p role="status">
              Annotation <code>{state.receipt.annotation_id}</code> is saved.
              The list below is a separate read and can be refreshed.
            </p>
          )}
          {confirmClose && (
            <section role="alert" aria-label="Discard annotation note">
              <p>The note has not been saved.</p>
              <div className="actions">
                <button
                  type="button"
                  onClick={() => {
                    setNote("");
                    setConfirmClose(false);
                    onClose();
                  }}
                >
                  Discard note and close
                </button>
                <button type="button" onClick={() => setConfirmClose(false)}>
                  Keep editing
                </button>
              </div>
            </section>
          )}
          <form onSubmit={submitForm}>
            <label className="field">
              Note
              <textarea
                value={note}
                maxLength={16_384}
                onChange={(event) => {
                  setNote(event.currentTarget.value);
                  if (state.kind === "failed" || state.kind === "conflict") {
                    mutation.current?.reset();
                    setView({ scopeEpoch, state: { kind: "idle" } });
                  }
                }}
                disabled={busy || state.kind === "committed"}
              />
            </label>
            <div className="actions">
              <button
                type="submit"
                disabled={busy || state.kind === "committed" || !note.trim()}
              >
                Save annotation
              </button>
              {state.kind === "outcome-unknown" && (
                <button type="button" onClick={() => void retryOriginal()}>
                  Retry original unchanged annotation
                </button>
              )}
              {state.kind === "committed" && (
                <button
                  type="button"
                  onClick={() => {
                    mutation.current?.reset();
                    setView({ scopeEpoch, state: { kind: "idle" } });
                  }}
                >
                  Add another note
                </button>
              )}
              <button
                type="button"
                disabled={loading}
                onClick={() => void refresh()}
              >
                Refresh annotations
              </button>
            </div>
          </form>
          {readError && (
            <ErrorSummary message={readError} retry={() => void refresh()} />
          )}
          {loading ? (
            <LoadingState>Reading annotations…</LoadingState>
          ) : items.length === 0 ? (
            <p className="muted">No annotations are saved for this case.</p>
          ) : (
            <ul aria-label="Saved annotations">
              {items.map((item) => (
                <li key={item.annotation_id}>
                  <p>{item.note}</p>
                  <p className="muted">
                    {item.created_at} · <code>{item.annotation_id}</code>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Modal>
      {prompt}
    </>
  );
}

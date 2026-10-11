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

type AddBody = ApiOperationBody<"addAnnotation">;
type Annotation = ApiOperationData<"readAnnotation">;
type AnnotationIntent = {
  registrationId: string;
  runId: string;
  caseId: string;
  body: AddBody;
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
  const [note, setNote] = useState("");
  const [items, setItems] = useState<readonly Annotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState<string>();
  const [confirmClose, setConfirmClose] = useState(false);
  const [state, setState] = useState<MutationState<Annotation>>({
    kind: "idle",
  });
  const mutation = useRef<
    RetainedMutation<AnnotationIntent, Annotation> | undefined
  >(undefined);
  if (!mutation.current) {
    mutation.current = new RetainedMutation(async (intent) => {
      const result = await operations.add(intent);
      const receipt = result.data;
      if (
        receipt.run_id !== intent.runId ||
        receipt.case_id !== intent.caseId ||
        receipt.note !== intent.body.note
      )
        throw new Error("The annotation receipt did not match this case.");
      return receipt;
    }, setState);
  }
  const busy = state.kind === "submitting" || state.kind === "outcome-unknown";
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
    () => navigation.registerDirtyGuard(`${registrationId}:annotation:${runId}:${caseId}`, guard),
    [caseId, guard, navigation, registrationId, runId],
  );

  async function refresh(signal?: AbortSignal) {
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
      setItems(matching);
    } catch (cause) {
      setReadError(safeMessage(cause));
    } finally {
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
    const receipt = await mutation.current?.submit({
      registrationId,
      runId,
      caseId,
      body,
    });
    if (receipt) {
      setNote("");
      await refresh();
    }
    return receipt;
  }

  async function retryOriginal() {
    const receipt = await mutation.current?.retryOriginal();
    if (receipt) {
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
            <code>{runId}</code>. This does not change the saved result or call a
            provider.
          </p>
          {state.kind === "outcome-unknown" && (
            <ErrorSummary message={state.message} />
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
                    setState({ kind: "idle" });
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
                    setState({ kind: "idle" });
                  }}
                >
                  Add another note
                </button>
              )}
              <button type="button" disabled={loading} onClick={() => void refresh()}>
                Refresh annotations
              </button>
            </div>
          </form>
          {readError && <ErrorSummary message={readError} retry={() => void refresh()} />}
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

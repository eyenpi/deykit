import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { safeMessage } from "../api/client";
import { ErrorSummary } from "./States";
/** Wrap keyboard focus as well as using the native inert modal background. */
function containTab(event: KeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab") return;
  const controls = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
    ),
  ).filter(
    (element) => element.getClientRects().length > 0 && element.tabIndex >= 0,
  );
  const first = controls[0];
  const last = controls.at(-1);
  if (!first || !last) {
    event.preventDefault();
    return;
  }
  const active = document.activeElement;
  if (
    event.shiftKey &&
    (active === first || !controls.includes(active as HTMLElement))
  ) {
    event.preventDefault();
    last.focus();
  } else if (
    !event.shiftKey &&
    (active === last || !controls.includes(active as HTMLElement))
  ) {
    event.preventDefault();
    first.focus();
  }
}
/** Parent owns open state and dismissal policy. */
export function Modal({
  title,
  children,
  onDismiss,
  sheet = false,
}: {
  title: string;
  children: ReactNode;
  onDismiss: () => void;
  sheet?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={sheet ? "modal sheet" : "modal"}
      aria-labelledby={titleId}
      onKeyDown={containTab}
      onCancel={(event) => {
        event.preventDefault();
        onDismiss();
      }}
    >
      <header className="modal-header">
        <h2 id={titleId}>{title}</h2>
        <button type="button" aria-label={`Close ${title}`} onClick={onDismiss}>
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function StagedDialog({
  title,
  children,
  dirty,
  onSave,
  onDiscard,
  onClose,
}: {
  title: string;
  children: ReactNode;
  dirty: boolean;
  onSave: () => Promise<void>;
  onDiscard: () => void;
  onClose: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const confirmation = useRef<HTMLHeadingElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const returnToEditor = useRef(false);
  useEffect(() => {
    if (confirm) confirmation.current?.focus();
    else if (returnToEditor.current) {
      content.current
        ?.querySelector<HTMLElement>('input, textarea, button, [tabindex="0"]')
        ?.focus();
      returnToEditor.current = false;
    }
  }, [confirm]);
  async function save() {
    setSaving(true);
    setError(undefined);
    try {
      await onSave();
      onClose();
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setSaving(false);
    }
  }
  return (
    <Modal
      title={title}
      onDismiss={() => {
        if (!saving) {
          if (dirty) setConfirm(true);
          else onClose();
        }
      }}
      sheet
    >
      <div ref={content} hidden={confirm}>
        {children}
      </div>
      {confirm && (
        <div className="modal-body">
          <h3 ref={confirmation} tabIndex={-1}>
            Save your changes?
          </h3>
          <p>Your changes have not been saved.</p>
          {error && <ErrorSummary message={error} focus />}
          <div className="actions">
            <button
              disabled={saving}
              className="primary"
              onClick={() => void save()}
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
            <button
              disabled={saving}
              onClick={() => {
                onDiscard();
                onClose();
              }}
            >
              Discard changes
            </button>
            <button
              disabled={saving}
              onClick={() => {
                returnToEditor.current = true;
                setConfirm(false);
              }}
            >
              Keep editing
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { safeMessage } from "../api/client";
import { Modal } from "../components/Modal";
import { ErrorSummary } from "../components/States";
import type { DirtyNavigationGuard } from "./navigation";
import type { WorkspaceRoute } from "./routes";

/** Supplies the agreed Save / Discard / Keep editing decision to route changes. */
export function useDirtyNavigationGuard({
  dirty,
  save,
  discard,
}: {
  dirty: boolean;
  save: () => Promise<void>;
  discard: () => void;
}): {
  guard: DirtyNavigationGuard;
  prompt: ReactNode;
} {
  const [target, setTarget] = useState<WorkspaceRoute>();
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const resolve = useRef<((allow: boolean) => void) | undefined>(undefined);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  const guardFunction = useCallback(
    (next: WorkspaceRoute) => {
      if (!dirtyRef.current) return Promise.resolve(true);
      setError(undefined);
      setTarget(next);
      return new Promise<boolean>((done) => {
        resolve.current = done;
      });
    },
    [],
  );
  const guard = useRef(guardFunction as DirtyNavigationGuard);
  guard.current = guardFunction as DirtyNavigationGuard;
  guard.current.isDirty = () => dirtyRef.current;

  useEffect(
    () => () => {
      resolve.current?.(false);
      resolve.current = undefined;
    },
    [],
  );

  function settle(allow: boolean) {
    const finish = resolve.current;
    resolve.current = undefined;
    setTarget(undefined);
    finish?.(allow);
  }

  async function saveAndLeave() {
    setSaving(true);
    setError(undefined);
    try {
      await save();
      settle(true);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setSaving(false);
    }
  }

  function discardAndLeave() {
    discard();
    settle(true);
  }

  return {
    guard: guard.current,
    prompt: target ? (
      <Modal
        title="Unsaved changes"
        onDismiss={() => {
          if (!saving) settle(false);
        }}
      >
        <div className="modal-body">
          <p>Save your changes before leaving, discard them, or keep editing.</p>
          {error && <ErrorSummary message={error} focus />}
          <div className="actions">
            <button
              type="button"
              className="primary"
              disabled={saving}
              onClick={() => void saveAndLeave()}
            >
              {saving ? "Saving…" : "Save and leave"}
            </button>
            <button type="button" disabled={saving} onClick={discardAndLeave}>
              Discard changes
            </button>
            <button type="button" disabled={saving} onClick={() => settle(false)}>
              Keep editing
            </button>
          </div>
        </div>
      </Modal>
    ) : null,
  };
}

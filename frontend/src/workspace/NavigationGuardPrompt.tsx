import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { safeMessage } from "../api/client";
import { Modal } from "../components/Modal";
import { ErrorSummary } from "../components/States";
import type { DirtyNavigationGuard } from "./navigation";
import type { WorkspaceRoute } from "./routes";

/** Supplies the agreed Save / Discard / Keep editing decision to route changes. */
export function useDirtyNavigationGuard({
  dirty,
  isDirtyNow,
  save,
  discard,
  blockedMessage,
  allowDiscardWhenBlocked = false,
}: {
  dirty: boolean;
  isDirtyNow?: () => boolean;
  save: () => Promise<void>;
  discard: () => void;
  blockedMessage?: string;
  allowDiscardWhenBlocked?: boolean;
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
  const isDirtyNowRef = useRef(isDirtyNow);
  isDirtyNowRef.current = isDirtyNow;
  const currentDirty = useCallback(
    () => isDirtyNowRef.current?.() ?? dirtyRef.current,
    [],
  );

  const guardFunction = useCallback(
    (next: WorkspaceRoute) => {
      if (!currentDirty()) return Promise.resolve(true);
      setError(undefined);
      setTarget(next);
      return new Promise<boolean>((done) => {
        resolve.current = done;
      });
    },
    [currentDirty],
  );
  const guard = useMemo<DirtyNavigationGuard>(
    () => Object.assign(guardFunction, { isDirty: currentDirty }),
    [currentDirty, guardFunction],
  );

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
      if (currentDirty())
        throw new Error(
          "Changes are still pending. Finish composing or saving them before leaving.",
        );
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
    guard,
    prompt: target ? (
      <Modal
        title="Unsaved changes"
        onDismiss={() => {
          if (!saving) settle(false);
        }}
      >
        <div className="modal-body">
          <p>
            {blockedMessage ??
              "Save your changes before leaving, discard them, or keep editing."}
          </p>
          {error && <ErrorSummary message={error} focus />}
          <div className="actions">
            <button
              type="button"
              className="primary"
              disabled={saving || !!blockedMessage}
              onClick={() => void saveAndLeave()}
            >
              {saving ? "Saving…" : "Save and leave"}
            </button>
            <button
              type="button"
              disabled={
                saving || (!!blockedMessage && !allowDiscardWhenBlocked)
              }
              onClick={discardAndLeave}
            >
              Discard changes
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => settle(false)}
            >
              Keep editing
            </button>
          </div>
        </div>
      </Modal>
    ) : null,
  };
}

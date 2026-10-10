import { useRef, useState } from "react";
import { safeMessage } from "../api/client";
import { Modal } from "../components/Modal";
import { ErrorSummary } from "../components/States";
import type {
  ProjectAction,
  ProjectOverview,
  WorkspaceGateway,
} from "./gateway";
const titles = {
  create: "Create project",
  open: "Open project",
  demo: "Try support demo",
};
export function ProjectForm({
  action,
  initialPath = "",
  gateway,
  onReconnect,
  onOpened,
  onClose,
}: {
  action: ProjectAction;
  initialPath?: string;
  gateway: WorkspaceGateway;
  onReconnect: () => Promise<void>;
  onOpened: (project: ProjectOverview) => void;
  onClose: () => void;
}) {
  const [path, setPath] = useState(initialPath);
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const previous = useRef<{ signature: string; id: string } | undefined>(
    undefined,
  );
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(undefined);
    setBusy(true);
    const signature = JSON.stringify({ action, path, name });
    if (previous.current?.signature !== signature)
      previous.current = { signature, id: crypto.randomUUID() };
    try {
      onOpened(
        await gateway.openProject({
          action,
          path,
          name,
          operationId: previous.current.id,
        }),
      );
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={titles[action]}
      onDismiss={() => {
        if (!busy) onClose();
      }}
    >
      <form onSubmit={(event) => void submit(event)}>
        <div className="modal-body">
          <p className="muted">
            {action === "open"
              ? "Enter the path to an existing project on this computer."
              : action === "demo"
                ? "Create a local copy of authored examples. The demo uses fixtures and needs no provider key."
                : "Choose a local folder for your decision definitions and examples."}
          </p>
          {error && (
            <ErrorSummary
              message={error}
              focus
              reconnect={() => {
                setError(undefined);
                void onReconnect().catch((cause) =>
                  setError(safeMessage(cause)),
                );
              }}
            />
          )}
          {action === "create" && (
            <div className="field">
              <label htmlFor="project-name">Project name</label>
              <input
                id="project-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                disabled={busy}
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="project-path">Project folder path</label>
            <input
              id="project-path"
              value={path}
              onChange={(event) => setPath(event.target.value)}
              required
              disabled={busy}
              autoComplete="off"
              spellCheck={false}
              aria-describedby="path-help"
            />
            <p id="path-help" className="muted">
              The local service validates the folder before opening or creating
              a project.
            </p>
          </div>
        </div>
        <footer className="modal-footer">
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="primary" disabled={busy}>
            {busy ? "Working…" : titles[action]}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

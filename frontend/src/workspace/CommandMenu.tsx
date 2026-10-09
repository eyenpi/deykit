import { useEffect, useMemo, useRef, useState } from "react";
import { Modal } from "../components/Modal";
import type { WorkspaceRoute } from "./routes";

export interface WorkspaceCommand {
  id: string;
  label: string;
  context: string;
  route: WorkspaceRoute;
}

export function CommandMenu({
  commands,
  onNavigate,
}: {
  commands: readonly WorkspaceCommand[];
  onNavigate: (route: WorkspaceRoute) => Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const searchField = useRef<HTMLInputElement>(null);
  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return commands.filter((command) =>
      `${command.label} ${command.context}`.toLocaleLowerCase().includes(needle),
    );
  }, [commands, search]);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    }
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, []);

  useEffect(() => {
    if (open) {
      setSearch("");
      setActiveIndex(0);
      queueMicrotask(() => searchField.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (activeIndex >= filtered.length) setActiveIndex(0);
  }, [activeIndex, filtered.length]);

  async function choose(index: number) {
    const command = filtered[index];
    if (!command) return;
    if (await onNavigate(command.route)) setOpen(false);
  }

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Search <kbd>⌘ K</kbd>
      </button>
      {open && (
        <Modal title="Search workspace" onDismiss={() => setOpen(false)}>
          <div className="modal-body command-menu">
            <label htmlFor="workspace-command-search">Search loaded workspace</label>
            <input
              id="workspace-command-search"
              ref={searchField}
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setActiveIndex(0);
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setActiveIndex((index) =>
                    filtered.length ? (index + 1) % filtered.length : 0,
                  );
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setActiveIndex((index) =>
                    filtered.length ? (index - 1 + filtered.length) % filtered.length : 0,
                  );
                } else if (event.key === "Enter") {
                  event.preventDefault();
                  void choose(activeIndex);
                }
              }}
              autoComplete="off"
            />
            {filtered.length === 0 ? (
              <p className="muted" role="status">
                No loaded workspace items match.
              </p>
            ) : (
              <ul className="command-results" role="listbox" aria-label="Loaded workspace items">
                {filtered.map((command, index) => (
                  <li key={command.id} role="option" aria-selected={index === activeIndex}>
                    <button
                      type="button"
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => void choose(index)}
                    >
                      <span>{command.label}</span>
                      <span className="muted">{command.context}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="muted">Use ↑ and ↓ to move, Enter to open, Escape to close.</p>
          </div>
        </Modal>
      )}
    </>
  );
}

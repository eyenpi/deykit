import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { CommandMenu } from "./CommandMenu";
import type { WorkspaceCommand } from "./CommandMenu";
import type { ProjectOverview, ResourceSummary } from "./gateway";
import type { WorkspaceRoute } from "./routes";

export function Shell({
  route,
  onNavigate,
  project,
  decision,
  children,
  decisionActions,
  commands,
}: {
  route: WorkspaceRoute;
  onNavigate: (route: WorkspaceRoute) => Promise<boolean>;
  project?: ProjectOverview;
  decision?: ResourceSummary;
  children: ReactNode;
  decisionActions?: ReactNode;
  commands: readonly WorkspaceCommand[];
}) {
  const [expanded, setExpanded] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const firstNavigation = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (expanded) firstNavigation.current?.focus();
  }, [expanded]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    let lastFocused = document.activeElement;
    function rememberFocus(event: FocusEvent) {
      if (event.target instanceof Element) lastFocused = event.target;
    }
    function changed(event: MediaQueryListEvent) {
      const active =
        document.activeElement === document.body
          ? lastFocused
          : document.activeElement;
      setExpanded(false);
      if (event.matches && active && sidebar.current?.contains(active)) {
        menuButton.current?.focus();
      } else if (!event.matches && active === menuButton.current) {
        firstNavigation.current?.focus();
      }
    }
    media.addEventListener("change", changed);
    document.addEventListener("focusin", rememberFocus);
    return () => {
      media.removeEventListener("change", changed);
      document.removeEventListener("focusin", rememberFocus);
    };
  }, []);

  function closeMenu() {
    setExpanded(false);
    if (expanded) menuButton.current?.focus();
  }

  function go(next: WorkspaceRoute) {
    void onNavigate(next).then((moved) => {
      if (moved) closeMenu();
    });
  }

  const registrationId = project?.id;
  const activeDecisionId =
    route.kind === "decision" ||
    route.kind === "examples" ||
    route.kind === "decision-history"
      ? route.decisionId
      : undefined;
  const decisionContext = !!decision && !!activeDecisionId;

  return (
    <div
      className="workspace"
      onKeyDown={(event) => {
        if (
          expanded &&
          event.key === "Escape" &&
          !(event.target instanceof Element && event.target.closest("dialog"))
        ) {
          event.preventDefault();
          closeMenu();
        }
      }}
    >
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside
        ref={sidebar}
        className={`sidebar ${expanded ? "expanded" : ""}`}
        id="workspace-navigation"
      >
        <button className="brand" onClick={() => go({ kind: "start" })}>
          deykit
        </button>
        <nav aria-label="Workspace">
          <CommandMenu commands={commands} onNavigate={onNavigate} />
          <button
            ref={firstNavigation}
            aria-current={route.kind === "start" ? "page" : undefined}
            onClick={() => go({ kind: "start" })}
          >
            Projects
          </button>
          {project && registrationId && (
            <>
              <button
                className="project-link"
                aria-current={route.kind === "overview" ? "page" : undefined}
                onClick={() => go({ kind: "overview", registrationId })}
              >
                {project.name}
              </button>
              <p className="nav-label">Decisions</p>
              {project.decisions.map((item) => {
                const selected = activeDecisionId === item.id;
                return (
                  <div key={item.id}>
                    <button
                      aria-current={selected ? "page" : undefined}
                      onClick={() =>
                        go({
                          kind: "decision",
                          registrationId,
                          decisionId: item.id,
                        })
                      }
                    >
                      {item.name}
                    </button>
                    {selected && (
                      <div className="decision-nav">
                        <button
                          aria-current={
                            route.kind === "decision" ? "page" : undefined
                          }
                          onClick={() =>
                            go({
                              kind: "decision",
                              registrationId,
                              decisionId: item.id,
                            })
                          }
                        >
                          Decision
                        </button>
                        <button
                          aria-current={
                            route.kind === "examples" ? "page" : undefined
                          }
                          onClick={() =>
                            go({
                              kind: "examples",
                              registrationId,
                              decisionId: item.id,
                            })
                          }
                        >
                          Examples
                        </button>
                        <button
                          aria-current={
                            route.kind === "decision-history"
                              ? "page"
                              : undefined
                          }
                          onClick={() =>
                            go({
                              kind: "decision-history",
                              registrationId,
                              decisionId: item.id,
                            })
                          }
                        >
                          History
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
              <button
                aria-current={
                  route.kind === "examples" && route.decisionId === null
                    ? "page"
                    : undefined
                }
                onClick={() =>
                  go({ kind: "examples", registrationId, decisionId: null })
                }
              >
                Project examples
              </button>
            </>
          )}
        </nav>
        {project && registrationId && (
          <nav className="sidebar-bottom" aria-label="Utilities">
            <button
              aria-current={route.kind === "runs" || route.kind === "run" ? "page" : undefined}
              onClick={() => go({ kind: "runs", registrationId })}
            >
              Runs
            </button>
            <button
              aria-current={route.kind === "providers" ? "page" : undefined}
              onClick={() => go({ kind: "providers", registrationId })}
            >
              Providers
            </button>
            <button
              aria-current={route.kind === "fixtures" ? "page" : undefined}
              onClick={() => go({ kind: "fixtures", registrationId })}
            >
              Fixtures
            </button>
          </nav>
        )}
      </aside>
      <div className="workspace-content">
        <header className="toolbar">
          <button
            ref={menuButton}
            className="nav-toggle"
            aria-expanded={expanded}
            aria-controls="workspace-navigation"
            onClick={() => {
              if (expanded) closeMenu();
              else setExpanded(true);
            }}
          >
            Menu
          </button>
          <nav aria-label="Breadcrumb">
            <span>
              {project && route.kind !== "start"
                ? project.name
                : "Local workspace"}
            </span>
            {decisionContext && (
              <>
                <span aria-hidden="true"> / </span>
                <span>{decision?.name}</span>
              </>
            )}
          </nav>
          {decisionContext && decisionActions && (
            <div className="actions">{decisionActions}</div>
          )}
        </header>
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

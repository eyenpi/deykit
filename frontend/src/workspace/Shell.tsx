import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ProjectOverview, ResourceSummary } from "./gateway";
export type View =
  | "start"
  | "overview"
  | "decision"
  | "examples"
  | "runs"
  | "results"
  | "providers"
  | "help";
export function Shell({
  view,
  onNavigate,
  project,
  decision,
  onSelectDecision,
  children,
  decisionActions,
}: {
  view: View;
  onNavigate: (view: View) => void;
  project?: ProjectOverview;
  decision?: ResourceSummary;
  onSelectDecision: (decision: ResourceSummary) => void;
  children: ReactNode;
  decisionActions?: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const firstNavigation = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (expanded) firstNavigation.current?.focus();
  }, [expanded]);
  useEffect(() => {
    // Focus must not remain in navigation that becomes hidden at the breakpoint.
    const media = window.matchMedia("(max-width: 760px)");
    // Browsers may blur a CSS-hidden control before firing the media event.
    // Retain the last focus target so breakpoint changes can restore it visibly.
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
  function navigate(next: View) {
    onNavigate(next);
    closeMenu();
  }
  const decisionView =
    decision && ["decision", "examples", "runs", "results"].includes(view);
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
        <button className="brand" onClick={() => navigate("start")}>
          deykit
        </button>
        <nav aria-label="Workspace">
          <button
            ref={firstNavigation}
            aria-current={view === "start" ? "page" : undefined}
            onClick={() => navigate("start")}
          >
            Projects
          </button>
          {project && (
            <>
              <button
                className="project-link"
                aria-current={view === "overview" ? "page" : undefined}
                onClick={() => navigate("overview")}
              >
                {project.name}
              </button>
              <p className="nav-label">Decisions</p>
              {project.decisions.map((item) => (
                <div key={item.id}>
                  <button
                    onClick={() => {
                      onSelectDecision(item);
                      navigate("decision");
                    }}
                  >
                    {item.name}
                  </button>
                  {decision?.id === item.id && (
                    <div className="decision-nav">
                      {(
                        ["decision", "examples", "runs", "results"] as const
                      ).map((section) => (
                        <button
                          key={section}
                          aria-current={view === section ? "page" : undefined}
                          onClick={() => navigate(section)}
                        >
                          {section[0].toUpperCase() + section.slice(1)}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}
        </nav>
        <nav className="sidebar-bottom" aria-label="Utilities">
          <button
            aria-current={view === "providers" ? "page" : undefined}
            onClick={() => navigate("providers")}
          >
            Providers
          </button>
          <button
            aria-current={view === "help" ? "page" : undefined}
            onClick={() => navigate("help")}
          >
            Help
          </button>
        </nav>
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
              {project && view !== "start" && view !== "help"
                ? project.name
                : "Local workspace"}
            </span>
            {decisionView && (
              <>
                <span aria-hidden="true"> / </span>
                <span>{decision.name}</span>
              </>
            )}
          </nav>
          {decisionView && <div className="actions">{decisionActions}</div>}
        </header>
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

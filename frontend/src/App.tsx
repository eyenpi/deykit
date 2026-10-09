import { useEffect, useRef, useState } from "react";
import { safeMessage } from "./api/client";
import { Modal } from "./components/Modal";
import { ErrorSummary, LoadingState, WarningList } from "./components/States";
import { disconnectedWorkspace } from "./workspace/gateway";
import type {
  ProjectAction,
  ProjectOverview,
  RecentProjectsResult,
  ResourceSummary,
  WorkspaceGateway,
} from "./workspace/gateway";
import { Overview } from "./workspace/Overview";
import { ProjectForm } from "./workspace/ProjectForm";
import { Shell } from "./workspace/Shell";
import type { View } from "./workspace/Shell";
export function App({
  gateway = disconnectedWorkspace,
}: {
  gateway?: WorkspaceGateway;
}) {
  const [view, setView] = useState<View>("start");
  const [project, setProject] = useState<ProjectOverview>();
  const [decision, setDecision] = useState<ResourceSummary>();
  const [action, setAction] = useState<{
    action: ProjectAction;
    initialPath?: string;
  }>();
  const [openSequence, setOpenSequence] = useState(0);
  const overviewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (openSequence > 0) overviewHeading.current?.focus();
  }, [openSequence]);
  const [notice, setNotice] = useState<string>();
  const [recent, setRecent] = useState<RecentProjectsResult>();
  const [error, setError] = useState<string>();
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(undefined);
    setRecent(undefined);
    void gateway.recentProjects(controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) setRecent(result);
      },
      (cause) => {
        if (!controller.signal.aborted) setError(safeMessage(cause));
      },
    );
    return () => controller.abort();
  }, [gateway, reload]);
  function selectDecision(item: ResourceSummary) {
    setDecision(item);
    setView("decision");
  }
  function opened(item: ProjectOverview) {
    setProject(item);
    setDecision(undefined);
    setView("overview");
    setAction(undefined);
    setOpenSequence((sequence) => sequence + 1);
  }
  async function reconnect(): Promise<void> {
    setError(undefined);
    try {
      await gateway.reconnect();
      setProject(undefined);
      setDecision(undefined);
      setView("start");
      setReload((value) => value + 1);
    } catch (cause) {
      setError(safeMessage(cause));
      throw cause;
    }
  }
  function reconnectFromStart() {
    void reconnect().catch(() => undefined);
  }
  return (
    <Shell
      view={view}
      onNavigate={setView}
      project={project}
      decision={decision}
      onSelectDecision={selectDecision}
      decisionActions={
        <>
          <button onClick={() => setNotice("Version history")}>History</button>
          <button className="primary" onClick={() => setNotice("Run review")}>
            Run…
          </button>
        </>
      }
    >
      {view === "start" ? (
        <article className="document welcome">
          <h1>Welcome to deykit.</h1>
          <p className="lead">Test how an AI chooses between your options.</p>
          <div className="start-actions">
            {(
              [
                {
                  action: "create",
                  title: "Create project",
                  description: "Start with your own decision and examples.",
                },
                {
                  action: "open",
                  title: "Open project",
                  description: "Continue from a project folder.",
                },
                {
                  action: "demo",
                  title: "Try support demo",
                  description: "Explore authored examples without a key.",
                },
              ] as const
            ).map((item) => (
              <button
                className="start-action"
                key={item.action}
                onClick={() => setAction({ action: item.action })}
              >
                <span aria-hidden="true">›</span>
                <span>
                  <strong>{item.title}</strong>
                  <span className="muted">{item.description}</span>
                </span>
              </button>
            ))}
          </div>
          <section className="recent-projects">
            <h2>Recent projects</h2>
            {error ? (
              <ErrorSummary
                message={error}
                retry={() => setReload(reload + 1)}
                reconnect={reconnectFromStart}
              />
            ) : recent === undefined ? (
              <LoadingState>Loading recent projects…</LoadingState>
            ) : recent.items.length === 0 ? (
              <>
                <WarningList warnings={recent.warnings} />
                <p className="muted">No recent projects yet.</p>
              </>
            ) : (
              <>
                <WarningList warnings={recent.warnings} />
                <ul>
                  {recent.items.map((item) => (
                    <li key={item.id}>
                      <strong>{item.name}</strong>
                      <p className="path muted">{item.path}</p>
                      <button
                        aria-label={`Open project folder: ${item.name}`}
                        onClick={() =>
                          setAction({ action: "open", initialPath: item.path })
                        }
                      >
                        Open project folder
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </article>
      ) : view === "overview" && project ? (
        <Overview
          headingRef={overviewHeading}
          project={project}
          onDecision={selectDecision}
          onAction={setNotice}
        />
      ) : view === "help" ? (
        <article className="document">
          <h1>Help</h1>
          <p>
            Deykit is a local tool for defining bounded decisions and inspecting
            evaluation evidence.
          </p>
          <section className="section">
            <h2>Your workspace</h2>
            <p>
              Create or open a project folder to keep definitions, examples and
              results together. The support demo contains authored examples and
              uses no provider key.
            </p>
            <h2>Connecting the local service</h2>
            <p>
              The local workspace service manages project registrations and
              reads project definitions from folders you explicitly open.
            </p>
          </section>
        </article>
      ) : (
        <article className="document">
          <h1>
            {view === "providers"
              ? "Providers"
              : (decision?.name ?? "Workspace")}
          </h1>
          <p className="muted">
            {view === "providers"
              ? "Provider controls are not connected in the browser yet. Use the CLI to configure profiles."
              : "This view will be available when its workspace service is connected."}
          </p>
        </article>
      )}
      {action && (
        <ProjectForm
          action={action.action}
          initialPath={action.initialPath}
          gateway={gateway}
          onReconnect={reconnect}
          onOpened={opened}
          onClose={() => setAction(undefined)}
        />
      )}
      {notice && (
        <Modal title={notice} onDismiss={() => setNotice(undefined)}>
          <div className="modal-body">
            <p>
              This action requires the local workspace service. No changes have
              been made.
            </p>
            <button onClick={() => setNotice(undefined)}>Close</button>
          </div>
        </Modal>
      )}
    </Shell>
  );
}

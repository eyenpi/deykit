import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { ApiOperationBody } from "./api/client";
import { safeMessage } from "./api/client";
import { Modal } from "./components/Modal";
import { JsonSourceEditor } from "./components/JsonSourceEditor";
import { ErrorSummary, LoadingState, WarningList } from "./components/States";
import { DecisionPage } from "./features/decisions/DecisionPage";
import { DefinitionHistory } from "./features/decisions/DefinitionHistory";
import { ExamplesPage } from "./features/examples/ExamplesPage";
import { FixtureLibrary } from "./features/fixtures/FixtureLibrary";
import { ImportSheet } from "./features/imports/ImportSheet";
import { ProviderPage } from "./features/providers/ProviderPage";
import { SplitSheet } from "./features/splits/SplitSheet";
import { RunReview } from "./features/execution/RunReview";
import { RunList } from "./features/execution/RunList";
import { RunDetail } from "./features/execution/RunDetail";
import { ComparisonPage } from "./features/debugging/ComparisonPage";
import { RegressionList } from "./features/debugging/RegressionList";
import {
  ReportList,
  ReportPage,
  ReportSheet,
} from "./features/debugging/ReportPages";
import { GroupReview } from "./features/debugging/groups/GroupReview";
import { GroupDetail } from "./features/debugging/groups/GroupDetail";
import type { GroupReportTarget } from "./features/debugging/groups/GroupDetail";
import { disconnectedWorkspace } from "./workspace/gateway";
import type { ProjectOverview, WorkspaceGateway } from "./workspace/gateway";
import { Overview } from "./workspace/Overview";
import { ProjectForm } from "./workspace/ProjectForm";
import { Shell } from "./workspace/Shell";
import type { WorkspaceCommand } from "./workspace/CommandMenu";
import {
  WorkspaceNavigation,
  WorkspaceSessionState,
} from "./workspace/navigation";
import { isOutcomeUnknown } from "./workspace/mutation-controller";
import type { WorkspaceRoute } from "./workspace/routes";

const EMPTY_DECISION_SOURCE = `{
  "schema_version": 1,
  "input_kind": "text",
  "input_schema_source": null,
  "selected_fields": [],
  "questions": [
    {
      "id": "question",
      "kind": "choice",
      "instructions": "",
      "options": [
        { "id": "option-a", "name": "Option A", "description": null },
        { "id": "option-b", "name": "Option B", "description": null }
      ]
    }
  ]
}`;

type Creation = { kind: "decision" } | { kind: "dataset" };

export function App({
  gateway = disconnectedWorkspace,
}: {
  gateway?: WorkspaceGateway;
}) {
  const [navigation] = useState(() => new WorkspaceNavigation());
  const [sessionState] = useState(() => new WorkspaceSessionState());
  const [route, setRoute] = useState<WorkspaceRoute>(() => navigation.current);
  const [project, setProject] = useState<ProjectOverview>();
  const [projectError, setProjectError] = useState<string>();
  const [recentError, setRecentError] = useState<string>();
  const [recent, setRecent] =
    useState<Awaited<ReturnType<WorkspaceGateway["recentProjects"]>>>();
  const [reloadRecent, setReloadRecent] = useState(0);
  const [formAction, setFormAction] = useState<{
    action: "create" | "open" | "demo";
    initialPath?: string;
  }>();
  const [creation, setCreation] = useState<Creation>();
  const [importOpen, setImportOpen] = useState(false);
  const [splitOpen, setSplitOpen] = useState(false);
  const [examplesRefresh, setExamplesRefresh] = useState(0);
  const [runReviewDecisionId, setRunReviewDecisionId] = useState<string>();
  const [groupReview, setGroupReview] = useState<
    { decisionId: string; kind: "diagnostic" | "check" } | undefined
  >();
  const [groupReportTarget, setGroupReportTarget] =
    useState<GroupReportTarget>();
  const [createdName, setCreatedName] = useState<string>();
  const [createdError, setCreatedError] = useState<string>();
  const openHeading = useRef<HTMLHeadingElement>(null);
  const pendingOpenFocus = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (
      route.kind === "overview" &&
      project?.id === route.registrationId &&
      project.id === pendingOpenFocus.current
    ) {
      openHeading.current?.focus();
      pendingOpenFocus.current = undefined;
    }
  }, [project?.id, route]);

  useEffect(() => {
    const unsubscribe = navigation.subscribe(setRoute);
    return () => {
      unsubscribe();
      navigation.dispose();
    };
  }, [navigation]);

  useEffect(() => {
    if (route.kind !== "decision" || route.decisionId !== runReviewDecisionId)
      setRunReviewDecisionId(undefined);
  }, [route, runReviewDecisionId]);

  useEffect(() => {
    const controller = new AbortController();
    setRecent(undefined);
    setRecentError(undefined);
    void gateway
      .recentProjects(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setRecent(result);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setRecentError(safeMessage(cause));
      });
    return () => controller.abort();
  }, [gateway, reloadRecent]);

  const registrationId =
    route.kind === "start" ? undefined : route.registrationId;
  useEffect(() => {
    if (!registrationId) {
      setProject(undefined);
      setProjectError(undefined);
      return;
    }
    if (project?.id === registrationId) return;
    const controller = new AbortController();
    setProject(undefined);
    setProjectError(undefined);
    void gateway
      .projectOverview(registrationId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setProject(result);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setProjectError(safeMessage(cause));
      });
    return () => controller.abort();
  }, [gateway, project?.id, registrationId]);

  const decision =
    route.kind === "decision" ||
    route.kind === "decision-history" ||
    route.kind === "regressions" ||
    route.kind === "examples"
      ? project?.decisions.find((item) => item.id === route.decisionId)
      : undefined;
  const recordProviderProfile = useCallback(
    (profileId?: string) => {
      if (project)
        sessionState.update(project.id, {
          selectedProviderProfileId: profileId,
        });
    },
    [project?.id, sessionState],
  );
  const commands = useMemo<WorkspaceCommand[]>(() => {
    if (!project) return [];
    return [
      {
        id: "overview",
        label: project.name,
        context: "Project",
        route: { kind: "overview", registrationId: project.id },
      },
      ...project.decisions.map((item) => ({
        id: `decision:${item.id}`,
        label: item.name,
        context: "Decision",
        route: {
          kind: "decision" as const,
          registrationId: project.id,
          decisionId: item.id,
        },
      })),
      ...project.decisions.map((item) => ({
        id: `regressions:${item.id}`,
        label: `Regression examples: ${item.name}`,
        context: "Debugging",
        route: {
          kind: "regressions" as const,
          registrationId: project.id,
          decisionId: item.id,
        },
      })),
      {
        id: "runs",
        label: "Runs",
        context: "Workspace",
        route: { kind: "runs" as const, registrationId: project.id },
      },
      {
        id: "comparisons",
        label: "Comparisons",
        context: "Debugging",
        route: { kind: "comparisons" as const, registrationId: project.id },
      },
      {
        id: "reports",
        label: "Reports",
        context: "Debugging",
        route: { kind: "reports" as const, registrationId: project.id },
      },
      {
        id: "project-examples",
        label: "Project examples",
        context: "Examples",
        route: {
          kind: "examples",
          registrationId: project.id,
          decisionId: null,
        },
      },
      {
        id: "providers",
        label: "Providers",
        context: "Workspace",
        route: { kind: "providers", registrationId: project.id },
      },
      {
        id: "fixtures",
        label: "Fixtures",
        context: "Workspace",
        route: { kind: "fixtures", registrationId: project.id },
      },
    ];
  }, [project]);

  async function refreshProject(
    nextRegistration = project?.id,
  ): Promise<ProjectOverview | undefined> {
    if (!nextRegistration) return undefined;
    const refreshed = await gateway.projectOverview(
      nextRegistration,
      new AbortController().signal,
    );
    const currentRoute = navigation.current;
    if (
      currentRoute.kind !== "start" &&
      currentRoute.registrationId === nextRegistration
    )
      setProject(refreshed);
    return refreshed;
  }

  async function refreshExamplesAfterSourceChange() {
    const registrationId = project?.id;
    if (!registrationId) return;
    try {
      await refreshProject(registrationId);
      const currentRoute = navigation.current;
      if (
        currentRoute.kind === "start" ||
        currentRoute.registrationId !== registrationId
      )
        return;
      setProjectError(undefined);
      setExamplesRefresh((value) => value + 1);
    } catch (cause) {
      const currentRoute = navigation.current;
      if (
        currentRoute.kind !== "start" &&
        currentRoute.registrationId === registrationId
      )
        setProjectError(safeMessage(cause));
    }
  }

  async function opened(item: ProjectOverview) {
    setProject(item);
    setProjectError(undefined);
    setFormAction(undefined);
    pendingOpenFocus.current = item.id;
    const moved = await navigation.navigate({
      kind: "overview",
      registrationId: item.id,
    });
    if (!moved) pendingOpenFocus.current = undefined;
  }

  async function reconnect(): Promise<void> {
    await gateway.reconnect();
    setReloadRecent((current) => current + 1);
    if (registrationId) {
      try {
        await refreshProject(registrationId);
        setProjectError(undefined);
      } catch (cause) {
        setProjectError(safeMessage(cause));
        throw cause;
      }
    }
  }

  function requestImport() {
    if (
      route.kind === "examples" &&
      route.datasetId &&
      project?.datasets.some((item) => item.id === route.datasetId)
    ) {
      setImportOpen(true);
    } else if (project?.datasets.length) {
      void navigation
        .navigate({
          kind: "examples",
          registrationId: project.id,
          decisionId: route.kind === "examples" ? route.decisionId : null,
          datasetId: project.datasets[0].id,
        })
        .then((moved) => {
          if (moved) setImportOpen(true);
        });
    } else {
      setCreation({ kind: "dataset" });
    }
  }

  function examplesPage() {
    if (!project || route.kind !== "examples") return null;
    const selectedDataset =
      project.datasets.find((item) => item.id === route.datasetId) ??
      project.datasets.find(
        (item) => item.id === sessionState.read(project.id).selectedDatasetId,
      ) ??
      project.datasets[0];
    return (
      <ExamplesPage
        project={project}
        decision={decision}
        operations={gateway.authoring.examples}
        datasetOperations={gateway.authoring.datasets}
        navigation={navigation}
        datasetFromRoute={route.datasetId ?? selectedDataset?.id}
        caseFromRoute={
          route.caseId ??
          (selectedDataset?.id ===
          sessionState.read(project.id).selectedDatasetId
            ? sessionState.read(project.id).selectedCaseId
            : undefined)
        }
        refreshToken={examplesRefresh}
        onDatasetChange={async (datasetId, caseId) => {
          const moved = await navigation.navigate({
            kind: "examples",
            registrationId: project.id,
            decisionId: route.kind === "examples" ? route.decisionId : null,
            ...(datasetId ? { datasetId } : {}),
            ...(caseId ? { caseId } : {}),
          });
          if (!moved) return false;
          sessionState.update(project.id, {
            selectedDatasetId: datasetId,
            selectedCaseId: caseId,
          });
          return true;
        }}
        onImport={requestImport}
        onSplit={() => setSplitOpen(true)}
      />
    );
  }

  return (
    <Shell
      route={route}
      onNavigate={(next) => navigation.navigate(next)}
      project={project}
      decision={decision}
      commands={commands}
    >
      {route.kind === "start" ? (
        <article className="document welcome">
          <h1>Welcome to deykit.</h1>
          <p className="lead">Test how an AI chooses between your options.</p>
          <div className="start-actions">
            {[
              {
                action: "create" as const,
                title: "Create project",
                description: "Start with your own decision and examples.",
              },
              {
                action: "open" as const,
                title: "Open project",
                description: "Continue from a project folder.",
              },
              {
                action: "demo" as const,
                title: "Try support demo",
                description: "Explore authored examples without a key.",
              },
            ].map((item) => (
              <button
                className="start-action"
                key={item.action}
                onClick={() => setFormAction({ action: item.action })}
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
            {recentError ? (
              <ErrorSummary
                message={recentError}
                retry={() => setReloadRecent((value) => value + 1)}
                reconnect={() => void reconnect().catch(() => undefined)}
              />
            ) : recent === undefined ? (
              <LoadingState>Loading recent projects…</LoadingState>
            ) : (
              <>
                <WarningList warnings={recent.warnings} />
                {recent.items.length === 0 ? (
                  <p className="muted">No recent projects yet.</p>
                ) : (
                  <ul>
                    {recent.items.map((item) => (
                      <li key={item.id}>
                        <strong>{item.name}</strong>
                        <p className="path muted">{item.path}</p>
                        <button
                          aria-label={`Open project folder: ${item.name}`}
                          onClick={() =>
                            setFormAction({
                              action: "open",
                              initialPath: item.path,
                            })
                          }
                        >
                          Open project folder
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </section>
        </article>
      ) : projectError ? (
        <article className="document">
          <h1>Open this project</h1>
          <ErrorSummary
            message={projectError}
            reconnect={() => void reconnect().catch(() => undefined)}
          />
          <button onClick={() => setFormAction({ action: "open" })}>
            Open a project folder
          </button>
        </article>
      ) : !project ? (
        <article className="document">
          <LoadingState>Opening workspace…</LoadingState>
        </article>
      ) : route.kind === "overview" ? (
        <Overview
          project={project}
          headingRef={openHeading}
          decisionOperations={gateway.authoring.decisions}
          navigation={navigation}
          onDecisionsChanged={() => void refreshProject()}
          onDecision={(item) =>
            void navigation.navigate({
              kind: "decision",
              registrationId: project.id,
              decisionId: item.id,
            })
          }
          onCreateDecision={() => setCreation({ kind: "decision" })}
          onCreateDataset={() => setCreation({ kind: "dataset" })}
          onExamples={() =>
            void navigation.navigate({
              kind: "examples",
              registrationId: project.id,
              decisionId: null,
            })
          }
        />
      ) : route.kind === "decision" && decision ? (
        <>
          <DecisionPage
            registrationId={project.id}
            decisionId={decision.id}
            operations={gateway.authoring.decisions}
            navigation={navigation}
            onDecisionRenamed={(name) =>
              setProject((current) =>
                current
                  ? {
                      ...current,
                      decisions: current.decisions.map((item) =>
                        item.id === decision.id ? { ...item, name } : item,
                      ),
                    }
                  : current,
              )
            }
            onHistory={() =>
              void navigation.navigate({
                kind: "decision-history",
                registrationId: project.id,
                decisionId: decision.id,
              })
            }
            onExamples={() => {
              sessionState.update(project.id, {
                selectedDecisionId: decision.id,
              });
              void navigation.navigate({
                kind: "examples",
                registrationId: project.id,
                decisionId: decision.id,
              });
            }}
            onRun={() => setRunReviewDecisionId(decision.id)}
            onArchiveChanged={async () => {
              const moved = await navigation.navigate({
                kind: "overview",
                registrationId: project.id,
              });
              if (!moved) return;
              try {
                await refreshProject(project.id);
                const currentRoute = navigation.current;
                if (
                  currentRoute.kind === "overview" &&
                  currentRoute.registrationId === project.id
                )
                  setProjectError(undefined);
              } catch (cause) {
                const currentRoute = navigation.current;
                if (
                  currentRoute.kind === "overview" &&
                  currentRoute.registrationId === project.id
                )
                  setProjectError(safeMessage(cause));
              }
            }}
          />
          <section
            className="debugging-controls"
            aria-label="Decision diagnostics"
          >
            <h2>Diagnostics and checks</h2>
            <button
              type="button"
              onClick={() =>
                setGroupReview({ decisionId: decision.id, kind: "diagnostic" })
              }
            >
              Preview choice-order diagnostic
            </button>
            <button
              type="button"
              onClick={() =>
                setGroupReview({ decisionId: decision.id, kind: "check" })
              }
            >
              Preview regression check
            </button>
          </section>
          {runReviewDecisionId === decision.id && (
            <RunReview
              key={`${project.id}:${decision.id}`}
              project={project}
              decision={decision}
              gateway={gateway}
              navigation={navigation}
              onClose={() => setRunReviewDecisionId(undefined)}
              onStarted={(runId) => {
                setRunReviewDecisionId(undefined);
                void navigation.navigate({
                  kind: "run",
                  registrationId: project.id,
                  runId,
                });
              }}
            />
          )}
          {groupReview?.decisionId === decision.id && (
            <GroupReview
              key={`${project.id}:${decision.id}:${groupReview.kind}`}
              project={project}
              decision={decision}
              gateway={gateway}
              navigation={navigation}
              kind={groupReview.kind}
              onClose={() => setGroupReview(undefined)}
              onStarted={(groupId) => {
                const kind = groupReview.kind;
                setGroupReview(undefined);
                void navigation.navigate({
                  kind,
                  registrationId: project.id,
                  groupId,
                });
              }}
            />
          )}
        </>
      ) : route.kind === "decision-history" && decision ? (
        <DefinitionHistory
          registrationId={project.id}
          decisionId={decision.id}
          operations={gateway.authoring.decisions}
          navigation={navigation}
          onRestoredToDraft={() =>
            void navigation.navigate({
              kind: "decision",
              registrationId: project.id,
              decisionId: decision.id,
            })
          }
        />
      ) : route.kind === "examples" ? (
        examplesPage()
      ) : route.kind === "runs" ? (
        <RunList
          key={project.id}
          project={project}
          gateway={gateway.execution}
          navigation={navigation}
        />
      ) : route.kind === "run" ? (
        <RunDetail
          key={`${project.id}:${route.runId}`}
          registrationId={project.id}
          runId={route.runId}
          evaluationId={route.evaluationId}
          caseId={route.caseId}
          execution={gateway.execution}
          debugging={gateway.debugging}
          labelOperations={gateway.authoring.examples}
          navigation={navigation}
          project={project}
          readRevision={gateway.authoring.decisions.revision}
        />
      ) : route.kind === "comparisons" || route.kind === "comparison" ? (
        <ComparisonPage
          key={`${project.id}:comparison:${route.kind === "comparison" ? route.comparisonId : "list"}`}
          registrationId={project.id}
          comparisonId={
            route.kind === "comparison" ? route.comparisonId : undefined
          }
          debugging={gateway.debugging}
          execution={gateway.execution}
          navigation={navigation}
        />
      ) : route.kind === "regressions" && decision ? (
        <RegressionList
          key={`${project.id}:${route.decisionId}`}
          registrationId={project.id}
          decisionId={route.decisionId}
          decisionName={decision.name}
          operations={gateway.debugging.regressions}
          navigation={navigation}
        />
      ) : route.kind === "reports" ? (
        <ReportList
          registrationId={project.id}
          debugging={gateway.debugging}
          execution={gateway.execution}
          navigation={navigation}
        />
      ) : route.kind === "report" ? (
        <ReportPage
          key={`${project.id}:${route.reportId}`}
          registrationId={project.id}
          reportId={route.reportId}
          operations={gateway.debugging.reports}
        />
      ) : route.kind === "diagnostic" || route.kind === "check" ? (
        <GroupDetail
          key={`${project.id}:${route.kind}:${route.groupId}:${route.snapshotId ?? "latest"}`}
          project={project}
          gateway={gateway}
          navigation={navigation}
          kind={route.kind}
          groupId={route.groupId}
          snapshotId={route.snapshotId}
          onReport={setGroupReportTarget}
        />
      ) : route.kind === "providers" ? (
        <ProviderPage
          project={project}
          operations={gateway.authoring.providers}
          navigation={navigation}
          initialProfileId={
            sessionState.read(project.id).selectedProviderProfileId
          }
          onProfileChange={recordProviderProfile}
        />
      ) : route.kind === "fixtures" ? (
        <FixtureLibrary
          project={project}
          operations={gateway.authoring.fixtures}
          navigation={navigation}
          initialDecisionId={sessionState.read(project.id).selectedDecisionId}
          initialDatasetId={sessionState.read(project.id).selectedDatasetId}
          initialFixtureId={sessionState.read(project.id).selectedFixtureId}
          onContextChange={(context) => {
            sessionState.update(project.id, context);
          }}
        />
      ) : (
        <article className="document">
          <h1>{project.name}</h1>
          <p className="muted">Select a workspace page.</p>
        </article>
      )}

      {formAction && (
        <ProjectForm
          action={formAction.action}
          initialPath={formAction.initialPath}
          gateway={gateway}
          onReconnect={reconnect}
          onOpened={opened}
          onClose={() => setFormAction(undefined)}
        />
      )}
      {creation && project && (
        <ResourceCreationModal
          kind={creation.kind}
          project={project}
          gateway={gateway}
          onClose={() => setCreation(undefined)}
          onCreated={async (resourceId, name) => {
            setCreation(undefined);
            setCreatedName(name);
            try {
              const refreshed = await refreshProject(project.id);
              if (creation.kind === "decision" && resourceId)
                await navigation.navigate({
                  kind: "decision",
                  registrationId: project.id,
                  decisionId: resourceId,
                });
              else if (creation.kind === "dataset" && resourceId)
                await navigation.navigate({
                  kind: "examples",
                  registrationId: project.id,
                  decisionId: null,
                  datasetId: resourceId,
                });
              if (refreshed) setProject(refreshed);
            } catch (cause) {
              setCreatedError(safeMessage(cause));
            }
          }}
        />
      )}
      {createdError && (
        <Modal
          title="Refresh workspace"
          onDismiss={() => setCreatedError(undefined)}
        >
          <div className="modal-body">
            <ErrorSummary message={createdError} />
            <p>
              {createdName} was created. Refresh the workspace to load its
              current state.
            </p>
            <button
              onClick={() =>
                void refreshProject()
                  .then(() => setCreatedError(undefined))
                  .catch((cause) => setCreatedError(safeMessage(cause)))
              }
            >
              Refresh workspace
            </button>
          </div>
        </Modal>
      )}
      {importOpen &&
        project &&
        route.kind === "examples" &&
        route.datasetId && (
          <ImportSheet
            project={project}
            datasetId={route.datasetId}
            examples={gateway.authoring.examples}
            sources={gateway.authoring.sources}
            navigation={navigation}
            onClose={() => setImportOpen(false)}
            onImported={() => {
              setImportOpen(false);
              void refreshExamplesAfterSourceChange();
            }}
          />
        )}
      {splitOpen && project && route.kind === "examples" && route.datasetId && (
        <SplitSheet
          project={project}
          datasetId={route.datasetId}
          examples={gateway.authoring.examples}
          navigation={navigation}
          onClose={() => setSplitOpen(false)}
          onApplied={() => {
            void refreshExamplesAfterSourceChange();
          }}
        />
      )}
      {groupReportTarget && project && (
        <ReportSheet
          key={`${project.id}:${groupReportTarget.targetKind}:${groupReportTarget.targetId}:${groupReportTarget.groupSnapshotId}`}
          registrationId={project.id}
          debugging={gateway.debugging}
          execution={gateway.execution}
          navigation={navigation}
          initialTarget={groupReportTarget}
          onClose={() => setGroupReportTarget(undefined)}
          onCreated={(reportId) => {
            const registrationId = project.id;
            setGroupReportTarget(undefined);
            void navigation.navigate({
              kind: "report",
              registrationId,
              reportId,
            });
          }}
        />
      )}
    </Shell>
  );
}

function ResourceCreationModal({
  kind,
  project,
  gateway,
  onClose,
  onCreated,
}: {
  kind: Creation["kind"];
  project: ProjectOverview;
  gateway: WorkspaceGateway;
  onClose: () => void;
  onCreated: (resourceId: string, name: string) => void;
}) {
  const [name, setName] = useState("");
  const [source, setSource] = useState(EMPTY_DECISION_SOURCE);
  const [metadata, setMetadata] = useState("{}");
  const [error, setError] = useState<string>();
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [busy, setBusy] = useState(false);
  const retained = useRef<
    | {
        signature: string;
        decision: ApiOperationBody<"createDecision">;
        dataset: ApiOperationBody<"createDataset">;
      }
    | undefined
  >(undefined);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!outcomeUnknown) {
      const signature = [kind, name, source, metadata]
        .map((item) => `${item.length}:${item}`)
        .join("");
      if (retained.current?.signature !== signature)
        retained.current = {
          signature,
          decision: {
            schema_version: 1,
            operation_id: crypto.randomUUID(),
            decision_id: `decision-${crypto.randomUUID()}`,
            name,
            editor_source: source,
          },
          dataset: {
            schema_version: 1,
            operation_id: crypto.randomUUID(),
            dataset_id: `dataset-${crypto.randomUUID()}`,
            name,
            metadata_source: metadata,
          },
        };
    }
    setBusy(true);
    setError(undefined);
    try {
      if (kind === "decision") {
        const result = await gateway.authoring.decisions.create({
          registrationId: project.id,
          body: retained.current!.decision,
        });
        onCreated(result.data.decision.record.id, name);
      } else {
        const result = await gateway.authoring.datasets.create({
          registrationId: project.id,
          body: retained.current!.dataset,
        });
        onCreated(result.data.record.id, name);
      }
    } catch (cause) {
      if (isOutcomeUnknown(cause)) setOutcomeUnknown(true);
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={kind === "decision" ? "Create decision" : "Create dataset"}
      onDismiss={() => {
        if (!busy) onClose();
      }}
    >
      <form onSubmit={(event) => void submit(event)}>
        <div className="modal-body resource-create-form">
          {error && <ErrorSummary message={error} focus />}
          {outcomeUnknown && (
            <p role="status">
              The service may have created this resource. Retry uses the exact
              same ID, operation ID, and source.
            </p>
          )}
          <label>
            {kind === "decision" ? "Decision name" : "Dataset name"}
            <input
              required
              disabled={outcomeUnknown}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {kind === "decision" ? (
            <JsonSourceEditor
              label="Initial editable definition source"
              value={source}
              onChange={setSource}
              readOnly={outcomeUnknown}
            />
          ) : (
            <JsonSourceEditor
              label="Dataset metadata source"
              value={metadata}
              onChange={setMetadata}
              readOnly={outcomeUnknown}
            />
          )}
        </div>
        <footer className="modal-footer">
          <button type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={busy || !name.trim()}>
            {busy
              ? "Creating…"
              : outcomeUnknown
                ? "Retry same create"
                : kind === "decision"
                  ? "Create decision"
                  : "Create dataset"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

import { useEffect, useRef, useState } from "react";
import type { ApiOperationData, ApiOperationBody } from "../../api/client";
import { ApiError, safeMessage } from "../../api/client";
import { DataTable } from "../../components/DataTable";
import {
  ErrorSummary,
  EmptyState,
  LoadingState,
} from "../../components/States";
import { JsonSourceEditor } from "../../components/JsonSourceEditor";
import type {
  FixtureAuthoringOperations,
  ProjectOverview,
} from "../../workspace/gateway";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";

type FixturePageData = ApiOperationData<"listFixtureSets">;
type FixtureData = ApiOperationData<"readFixtureSet">;
type FixtureCreate = ApiOperationBody<"createFixtureSet">;

const operationId = () => crypto.randomUUID();
const resourceId = () => `fixture-${crypto.randomUUID()}`;

export function FixtureLibrary({
  project,
  operations,
  initialDecisionId,
  initialDatasetId,
  initialFixtureId,
  onContextChange,
  navigation,
}: {
  project: ProjectOverview;
  operations: FixtureAuthoringOperations;
  initialDecisionId?: string;
  initialDatasetId?: string;
  initialFixtureId?: string;
  onContextChange: (context: {
    selectedDecisionId?: string;
    selectedDatasetId?: string;
    selectedFixtureId?: string;
  }) => void;
  navigation: WorkspaceNavigation;
}) {
  const [page, setPage] = useState<FixturePageData>();
  const [cursor, setCursor] = useState<string>();
  const [selectedId, setSelectedId] = useState(initialFixtureId ?? "");
  const [selected, setSelected] = useState<FixtureData>();
  const [showRequests, setShowRequests] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [createOpen, setCreateOpen] = useState(false);
  const [decisionId, setDecisionId] = useState(
    initialDecisionId ?? project.decisions[0]?.id ?? "",
  );
  const [datasetId, setDatasetId] = useState(
    initialDatasetId ?? project.datasets[0]?.id ?? "",
  );
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [modelIdentity, setModelIdentity] = useState("");
  const [bindingsSource, setBindingsSource] = useState("");
  const [pending, setPending] = useState<{
    body: FixtureCreate;
    signature: string;
  }>();
  const [awaitingReview, setAwaitingReview] = useState(false);
  const listGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const projectIdRef = useRef(project.id);
  projectIdRef.current = project.id;
  const decision = project.decisions.find((item) => item.id === decisionId);
  const dataset = project.datasets.find((item) => item.id === datasetId);

  useEffect(() => {
    const generation = ++listGeneration.current;
    const controller = new AbortController();
    setLoading(true);
    setError(undefined);
    void operations
      .list({
        registrationId: project.id,
        query: { limit: "50" },
        signal: controller.signal,
      })
      .then((result) => {
        if (controller.signal.aborted || listGeneration.current !== generation)
          return;
        setPage(result.data);
        setCursor(result.data.next_cursor ?? undefined);
        if (
          selectedId &&
          !result.data.items.some((item) => item.id === selectedId)
        )
          setSelectedId("");
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted && listGeneration.current === generation)
          setError(safeMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted && listGeneration.current === generation)
          setLoading(false);
      });
    return () => controller.abort();
  }, [operations, project.id]);

  useEffect(() => {
    const generation = ++detailGeneration.current;
    if (!selectedId) {
      setSelected(undefined);
      return;
    }
    const controller = new AbortController();
    setError(undefined);
    void operations
      .read({
        registrationId: project.id,
        fixtureSetId: selectedId,
        query: { include_requests: showRequests ? "true" : "false" },
        signal: controller.signal,
      })
      .then((result) => {
        if (
          !controller.signal.aborted &&
          detailGeneration.current === generation
        )
          setSelected(result.data);
      })
      .catch((cause: unknown) => {
        if (
          !controller.signal.aborted &&
          detailGeneration.current === generation
        )
          setError(safeMessage(cause));
      });
    return () => controller.abort();
  }, [operations, project.id, selectedId, showRequests]);

  async function loadMore() {
    if (!cursor || busy) return;
    const requestedGeneration = listGeneration.current;
    const requestedProjectId = project.id;
    const requestedCursor = cursor;
    setBusy(true);
    try {
      const result = await operations.list({
        registrationId: requestedProjectId,
        query: { cursor: requestedCursor, limit: "50" },
      });
      if (
        listGeneration.current !== requestedGeneration ||
        projectIdRef.current !== requestedProjectId
      )
        return;
      setPage((current) =>
        current
          ? {
              ...current,
              items: [...current.items, ...result.data.items],
              next_cursor: result.data.next_cursor,
            }
          : result.data,
      );
      setCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      if (
        listGeneration.current === requestedGeneration &&
        projectIdRef.current === requestedProjectId
      )
        setError(safeMessage(cause));
    } finally {
      if (
        listGeneration.current === requestedGeneration &&
        projectIdRef.current === requestedProjectId
      )
        setBusy(false);
    }
  }

  function beginCreate() {
    if (!decision || !dataset) return;
    setPending(undefined);
    setAwaitingReview(false);
    setName("");
    setNote("");
    setModelIdentity("");
    setBindingsSource("");
    setCreateOpen(true);
  }

  function makeRequest(): FixtureCreate {
    return {
      schema_version: 1,
      operation_id: operationId(),
      fixture_set_id: resourceId(),
      name,
      note,
      decision_id: decision!.id,
      dataset_id: dataset!.id,
      model_identity: modelIdentity,
      binding_sources: bindingsSource.split("\n"),
    };
  }

  async function create(retry = false): Promise<boolean> {
    if (!decision || !dataset || busy) return false;
    const body = retry && pending ? pending.body : makeRequest();
    const signature = `${body.decision_id}\0${body.dataset_id}\0${body.model_identity}\0${body.binding_sources.join("\n")}`;
    setBusy(true);
    setError(undefined);
    try {
      await operations.create({ registrationId: project.id, body });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setPending({ body, signature });
        setAwaitingReview(true);
      } else if (
        !(cause instanceof ApiError) ||
        cause.status === undefined ||
        cause.status >= 500 ||
        cause.code === "service_unavailable" ||
        cause.code === "cancelled"
      ) {
        setPending({ body, signature });
      } else {
        setPending(undefined);
      }
      setError(safeMessage(cause));
      return false;
    } finally {
      setBusy(false);
    }
    setPending(undefined);
    setAwaitingReview(false);
    setCreateOpen(false);
    setSelectedId(body.fixture_set_id);
    onContextChange({ selectedFixtureId: body.fixture_set_id });
    try {
      const result = await operations.list({
        registrationId: project.id,
        query: { limit: "50" },
      });
      setPage(result.data);
      setCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    }
    return true;
  }

  const pendingOutcomeUnknown = !!pending && !awaitingReview;
  const fixtureDirty =
    createOpen &&
    (!!(name || note || modelIdentity || bindingsSource) || !!pending);
  const dirtyGuard = useDirtyNavigationGuard({
    dirty: fixtureDirty,
    blockedMessage: pendingOutcomeUnknown
      ? "The fixture write may have completed. Keep this form open and retry its original request before leaving."
      : undefined,
    save: async () => {
      if (pending || awaitingReview)
        throw new Error(
          "Review the current fixture list before deliberately reapplying this source.",
        );
      if (!name.trim() || !modelIdentity.trim() || !bindingsSource.trim())
        throw new Error(
          "Complete the fixture identity and strict binding source before leaving.",
        );
      if (!(await create()))
        throw new Error(
          "The fixture set was not created. Its exact source remains available.",
        );
    },
    discard: () => {
      setCreateOpen(false);
      setPending(undefined);
      setName("");
      setNote("");
      setModelIdentity("");
      setBindingsSource("");
    },
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(`fixtures:${project.id}`, dirtyGuard.guard),
    [dirtyGuard.guard, navigation, project.id],
  );

  return (
    <>
      <article className="document authoring-page">
        <h1>Fixture library</h1>
        <p className="lead">
          Authored request bindings are exact and specific to a decision,
          dataset, model identity, and case.
        </p>
        <p className="muted">
          A fixture records authored evidence. Creating one does not run a model
          or fill in missing answers.
        </p>
        <div className="fixture-context-selector">
          <label>
            Decision
            <select
              value={decisionId}
              disabled={createOpen}
              onChange={(event) => {
                setDecisionId(event.target.value);
                onContextChange({ selectedDecisionId: event.target.value });
              }}
            >
              <option value="">Choose a decision</option>
              {project.decisions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Dataset
            <select
              value={datasetId}
              disabled={createOpen}
              onChange={(event) => {
                setDatasetId(event.target.value);
                onContextChange({ selectedDatasetId: event.target.value });
              }}
            >
              <option value="">Choose a dataset</option>
              {project.datasets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error && <ErrorSummary message={error} />}
        {loading && <LoadingState>Loading fixture sets…</LoadingState>}
        {!loading && page && page.items.length === 0 && (
          <EmptyState title="No authored fixture sets">
            Create a set from strict binding source lines when matching authored
            requests are available.
          </EmptyState>
        )}
        {page && page.items.length > 0 && (
          <DataTable
            caption="Authored fixture sets"
            rows={page.items}
            rowId={(row) => row.id}
            columns={[
              {
                key: "name",
                heading: "Fixture set",
                render: (row) => (
                  <button
                    className="text-button"
                    onClick={() => {
                      setSelectedId(row.id);
                      onContextChange({ selectedFixtureId: row.id });
                    }}
                  >
                    {row.name}
                  </button>
                ),
              },
              {
                key: "decision",
                heading: "Decision",
                render: (row) =>
                  project.decisions.find((item) => item.id === row.decision_id)
                    ?.name ?? row.decision_id,
              },
              {
                key: "dataset",
                heading: "Dataset",
                render: (row) =>
                  project.datasets.find((item) => item.id === row.dataset_id)
                    ?.name ?? row.dataset_id,
              },
              {
                key: "model",
                heading: "Model identity",
                render: (row) => <code>{row.model_identity}</code>,
              },
              {
                key: "bindings",
                heading: "Bindings",
                render: (row) => row.binding_count,
              },
            ]}
          />
        )}
        {cursor && (
          <button disabled={busy} onClick={() => void loadMore()}>
            Load more fixture sets
          </button>
        )}
        {decision && dataset && (
          <button
            className="primary"
            disabled={createOpen || pendingOutcomeUnknown}
            onClick={beginCreate}
          >
            Author fixture set
          </button>
        )}

        {selected && (
          <section
            className="section fixture-detail"
            aria-labelledby="fixture-detail-heading"
          >
            <div className="section-heading">
              <div>
                <h2 id="fixture-detail-heading">{selected.name}</h2>
                <p className="muted">
                  Set ID <code>{selected.id}</code> · content hash{" "}
                  <code>{selected.content_hash}</code>
                </p>
              </div>
              <button
                onClick={() => {
                  setSelectedId("");
                  setSelected(undefined);
                  onContextChange({ selectedFixtureId: undefined });
                }}
              >
                Close details
              </button>
            </div>
            <dl className="metadata-list">
              <dt>Decision</dt>
              <dd>
                {project.decisions.find(
                  (item) => item.id === selected.decision_id,
                )?.name ?? selected.decision_id}
              </dd>
              <dt>Dataset</dt>
              <dd>
                {project.datasets.find(
                  (item) => item.id === selected.dataset_id,
                )?.name ?? selected.dataset_id}
              </dd>
              <dt>Model identity</dt>
              <dd>
                <code>{selected.model_identity}</code>
              </dd>
              <dt>Created</dt>
              <dd>{selected.created_at}</dd>
            </dl>
            <h3>Case bindings</h3>
            {selected.bindings.length ? (
              <DataTable
                caption="Exact authored case bindings"
                rows={selected.bindings}
                rowId={(row) => row.id}
                columns={[
                  {
                    key: "case",
                    heading: "Case",
                    render: (row) => <code>{row.case_id}</code>,
                  },
                  {
                    key: "request",
                    heading: "Request hash",
                    render: (row) => <code>{row.request_hash}</code>,
                  },
                  {
                    key: "model",
                    heading: "Model",
                    render: (row) => row.model_identity,
                  },
                  {
                    key: "compiler",
                    heading: "Compiler",
                    render: (row) => `${row.compiler} ${row.compiler_version}`,
                  },
                  {
                    key: "answer",
                    heading: "Authored answer reference",
                    render: (row) =>
                      row.error_code ? (
                        <span>
                          {row.error_code}: {row.error_reason}
                        </span>
                      ) : (
                        (row.answer_option_id ??
                        row.answer_question_id ??
                        "No answer reference")
                      ),
                  },
                ]}
              />
            ) : (
              <EmptyState title="No case bindings">
                This service response contains no bindings. Nothing has been
                inferred.
              </EmptyState>
            )}
            <label className="check-line">
              <input
                type="checkbox"
                checked={showRequests}
                onChange={(event) => setShowRequests(event.target.checked)}
              />{" "}
              Show exact stored request source text
            </label>
            {showRequests &&
              selected.requests.map((request, index) => (
                <JsonSourceEditor
                  key={`${selected.id}-request-${index}`}
                  label={`Stored request source ${index + 1}`}
                  value={request}
                  readOnly
                />
              ))}
          </section>
        )}

        {createOpen && decision && dataset && (
          <section
            className="section fixture-create"
            aria-labelledby="fixture-create-heading"
          >
            <h2 id="fixture-create-heading">Author a fixture set</h2>
            <p>
              Selected decision: <strong>{decision.name}</strong> · dataset:{" "}
              <strong>{dataset.name}</strong>
            </p>
            <label>
              Fixture set name
              <input
                value={name}
                disabled={!!pending}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              Model identity
              <input
                value={modelIdentity}
                disabled={!!pending}
                onChange={(event) => setModelIdentity(event.target.value)}
                autoComplete="off"
              />
            </label>
            <label>
              Note
              <textarea
                value={note}
                disabled={!!pending}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
              />
            </label>
            <JsonSourceEditor
              label="Strict binding source lines"
              description="Paste exact authored per-case binding lines from a trusted fixture source. The service validates and binds them; the browser does not compile or invent responses."
              value={bindingsSource}
              onChange={setBindingsSource}
              rows={10}
              readOnly={!!pending}
            />
            {pending && !awaitingReview && (
              <p role="status">
                The create outcome may be unknown. Retry sends the identical
                operation ID and body.
              </p>
            )}
            {awaitingReview && (
              <div className="warning-summary">
                <p>
                  The service reported a conflict. Review the current fixture
                  list before changing and reapplying the authored source.
                </p>
                <button
                  disabled={busy}
                  onClick={() => {
                    void operations
                      .list({
                        registrationId: project.id,
                        query: { limit: "50" },
                      })
                      .then((result) => {
                        setPage(result.data);
                        setCursor(result.data.next_cursor ?? undefined);
                        setPending(undefined);
                        setAwaitingReview(false);
                      })
                      .catch((cause: unknown) => setError(safeMessage(cause)));
                  }}
                >
                  Review current fixture sets
                </button>
              </div>
            )}
            <div className="actions">
              {pending && !awaitingReview ? (
                <button disabled={busy} onClick={() => void create(true)}>
                  Retry same create
                </button>
              ) : (
                !pending && (
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      !name.trim() ||
                      !modelIdentity.trim() ||
                      !bindingsSource.trim()
                    }
                    onClick={() => void create()}
                  >
                    Create authored set
                  </button>
                )
              )}
              <button
                disabled={busy || pendingOutcomeUnknown}
                onClick={() => {
                  setCreateOpen(false);
                  setPending(undefined);
                  setAwaitingReview(false);
                }}
              >
                Close
              </button>
            </div>
          </section>
        )}
      </article>
      {dirtyGuard.prompt}
    </>
  );
}

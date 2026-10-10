import { useEffect, useState } from "react";
import type { Ref } from "react";
import type { ApiOperationData } from "../api/client";
import { safeMessage } from "../api/client";
import { DataTable } from "../components/DataTable";
import { ErrorSummary, LoadingState, WarningList } from "../components/States";
import type {
  DecisionAuthoringOperations,
  ProjectOverview,
  ResourceSummary,
} from "./gateway";
type DecisionPage = ApiOperationData<"listDecisions">;
export function Overview({
  project,
  headingRef,
  onDecision,
  onCreateDecision,
  onCreateDataset,
  onExamples,
  decisionOperations,
  onDecisionsChanged,
}: {
  project: ProjectOverview;
  headingRef?: Ref<HTMLHeadingElement>;
  onDecision: (decision: ResourceSummary) => void;
  onCreateDecision: () => void;
  onCreateDataset: () => void;
  onExamples: () => void;
  decisionOperations: DecisionAuthoringOperations;
  onDecisionsChanged: () => void;
}) {
  const [allDecisions, setAllDecisions] = useState<DecisionPage>();
  const [cursor, setCursor] = useState<string>();
  const [decisionError, setDecisionError] = useState<string>();
  const [busyId, setBusyId] = useState<string>();
  useEffect(() => {
    const controller = new AbortController();
    setDecisionError(undefined);
    void decisionOperations
      .list({
        registrationId: project.id,
        query: { include_archived: "true", limit: "50" },
        signal: controller.signal,
      })
      .then((result) => {
        if (controller.signal.aborted) return;
        setAllDecisions(result.data);
        setCursor(result.data.next_cursor ?? undefined);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setDecisionError(safeMessage(cause));
      });
    return () => controller.abort();
  }, [decisionOperations, project.id]);

  async function restore(item: DecisionPage["items"][number]) {
    setBusyId(item.decision.record.id);
    setDecisionError(undefined);
    try {
      await decisionOperations.restore({
        registrationId: project.id,
        decisionId: item.decision.record.id,
        body: {
          schema_version: 1,
          expected_etag: item.decision.etag,
          operation_id: crypto.randomUUID(),
        },
      });
      onDecisionsChanged();
    } catch (cause) {
      setDecisionError(safeMessage(cause));
    } finally {
      setBusyId(undefined);
    }
  }

  async function loadMoreArchived() {
    if (!cursor) return;
    try {
      const result = await decisionOperations.list({
        registrationId: project.id,
        query: { include_archived: "true", cursor, limit: "50" },
      });
      setAllDecisions((current) =>
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
      setDecisionError(safeMessage(cause));
    }
  }
  const archived =
    allDecisions?.items.filter((item) => item.decision.record.archived) ?? [];
  return (
    <article className="document">
      <h1 ref={headingRef} tabIndex={-1}>
        {project.name}
      </h1>
      <WarningList warnings={project.warnings} />
      <p className="muted">Project folder</p>
      <div className="section">
        <p className="muted">Project location</p>
        <p className="path">{project.path}</p>
      </div>
      <section className="section">
        <h2>Decisions</h2>
        <p className="muted">Define the question and allowed answers.</p>
        {project.decisions.length > 0 && (
          <DataTable
            caption="Project decisions"
            rows={project.decisions}
            rowId={(row) => row.id}
            columns={[
              {
                key: "name",
                heading: "Decision",
                render: (row) => (
                  <button
                    className="text-button"
                    onClick={() => onDecision(row)}
                  >
                    {row.name}
                  </button>
                ),
              },
              {
                key: "id",
                heading: "ID",
                render: (row) => <code>{row.id}</code>,
              },
            ]}
          />
        )}
        <button className="primary" onClick={onCreateDecision}>
          Create decision
        </button>
      </section>
      <section className="section">
        <h2>Examples</h2>
        <p className="muted">
          Add inputs now, even before defining a decision.
        </p>
        {project.datasets.length > 0 && (
          <DataTable
            caption="Project datasets"
            rows={project.datasets}
            rowId={(row) => row.id}
            columns={[
              { key: "name", heading: "Dataset", render: (row) => row.name },
            ]}
          />
        )}
        <div className="actions">
          <button onClick={onCreateDataset}>Create dataset</button>
          <button onClick={onExamples}>Open examples</button>
        </div>
      </section>
      <section className="section">
        <h2>Archived decisions</h2>
        {decisionError && <ErrorSummary message={decisionError} />}
        {!allDecisions && !decisionError && (
          <LoadingState>Loading decision archive…</LoadingState>
        )}
        {allDecisions && archived.length === 0 && (
          <p className="muted">No archived decisions.</p>
        )}
        {archived.length > 0 && (
          <DataTable
            caption="Archived decisions"
            rows={archived}
            rowId={(row) => row.decision.record.id}
            columns={[
              {
                key: "name",
                heading: "Decision",
                render: (row) => row.decision.record.name,
              },
              {
                key: "id",
                heading: "ID",
                render: (row) => <code>{row.decision.record.id}</code>,
              },
              {
                key: "restore",
                heading: "Action",
                render: (row) => (
                  <button
                    disabled={busyId === row.decision.record.id}
                    onClick={() => void restore(row)}
                  >
                    {busyId === row.decision.record.id
                      ? "Restoring…"
                      : "Restore"}
                  </button>
                ),
              },
            ]}
          />
        )}
        {cursor && (
          <button type="button" onClick={() => void loadMoreArchived()}>
            Load more decisions
          </button>
        )}
      </section>
    </article>
  );
}

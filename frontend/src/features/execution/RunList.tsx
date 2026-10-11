import { useEffect, useRef, useState } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationData } from "../../api/client";
import {
  EmptyState,
  ErrorSummary,
  LoadingState,
} from "../../components/States";
import type {
  ExecutionGateway,
  ProjectOverview,
} from "../../workspace/gateway";
import type { WorkspaceNavigation } from "../../workspace/navigation";

type RunPage = ApiOperationData<"listRuns">;
type RunStatus =
  | "preparing"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "completed_with_errors"
  | "budget_exhausted"
  | "interrupted"
  | "preflight_failed";

export function RunList({
  project,
  gateway,
  navigation,
}: {
  project: ProjectOverview;
  gateway: ExecutionGateway;
  navigation: WorkspaceNavigation;
}) {
  const [page, setPage] = useState<RunPage>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [cursor, setCursor] = useState<string>();
  const [status, setStatus] = useState<"all" | RunStatus>("all");
  const [decisionId, setDecisionId] = useState("");
  const [moreLoading, setMoreLoading] = useState(false);
  const [generation, setGeneration] = useState(0);
  const moreController = useRef<AbortController | undefined>(undefined);

  useEffect(() => {
    const controller = new AbortController();
    moreController.current?.abort();
    moreController.current = undefined;
    let active = true;
    setLoading(true);
    setError(undefined);
    setPage(undefined);
    setCursor(undefined);
    void gateway.runs
      .list({
        registrationId: project.id,
        query: {
          limit: 50,
          ...(status === "all" ? {} : { status }),
          ...(decisionId ? { decision_id: decisionId } : {}),
        },
        signal: controller.signal,
      })
      .then((result) => {
        if (!active) return;
        if (result.data.items.some((run) => !run.run_id))
          throw new Error("The service returned an invalid run identity.");
        setPage(result.data);
        setCursor(result.data.next_cursor ?? undefined);
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted) setError(safeMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
      moreController.current?.abort();
      moreController.current = undefined;
    };
  }, [gateway, project.id, status, decisionId, generation]);

  async function loadMore() {
    if (!cursor || moreLoading) return;
    const controller = new AbortController();
    moreController.current?.abort();
    moreController.current = controller;
    setMoreLoading(true);
    setError(undefined);
    try {
      const result = await gateway.runs.list({
        registrationId: project.id,
        query: {
          cursor,
          limit: 50,
          ...(status === "all" ? {} : { status }),
          ...(decisionId ? { decision_id: decisionId } : {}),
        },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setPage((current) => {
        if (!current) return result.data;
        const seen = new Set(current.items.map((run) => run.run_id));
        return {
          ...result.data,
          items: [
            ...current.items,
            ...result.data.items.filter((run) => !seen.has(run.run_id)),
          ],
        };
      });
      setCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      if (!controller.signal.aborted) setError(safeMessage(cause));
    } finally {
      if (moreController.current === controller) {
        moreController.current = undefined;
        setMoreLoading(false);
      }
    }
  }

  return (
    <article className="document">
      <h1>Runs</h1>
      <p className="lead">
        Service-owned executions and their current lifecycle state.
      </p>
      <div className="actions">
        <label className="field">
          Decision
          <select
            value={decisionId}
            onChange={(event) => setDecisionId(event.currentTarget.value)}
          >
            <option value="">All decisions</option>
            {project.decisions.map((decision) => (
              <option key={decision.id} value={decision.id}>
                {decision.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Status
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.currentTarget.value as "all" | RunStatus)
            }
          >
            <option value="all">All statuses</option>
            <option value="preparing">Preparing</option>
            <option value="running">Running</option>
            <option value="cancelling">Cancelling</option>
            <option value="cancelled">Cancelled</option>
            <option value="completed">Completed</option>
            <option value="completed_with_errors">Completed with errors</option>
            <option value="budget_exhausted">Budget exhausted</option>
            <option value="interrupted">Interrupted</option>
            <option value="preflight_failed">Preflight failed</option>
          </select>
        </label>
        <button
          type="button"
          disabled={loading}
          onClick={() => setGeneration((value) => value + 1)}
        >
          Refresh runs
        </button>
      </div>
      {error && (
        <ErrorSummary
          message={error}
          retry={() => setGeneration((value) => value + 1)}
        />
      )}
      {loading && <LoadingState>Loading runs…</LoadingState>}
      {page && page.items.length === 0 && (
        <EmptyState title="No runs in this page">
          This result reflects the service filter and total, not a local
          calculation.
        </EmptyState>
      )}
      {page && page.items.length > 0 && (
        <>
          <p role="status">{page.total} total runs from the service.</p>
          <div className="table-region">
            <table>
              <caption>Runs for {project.name}</caption>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Decision / dataset</th>
                  <th>Mode</th>
                  <th>State</th>
                  <th>Attempts</th>
                  <th>Activity</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((run) => (
                  <tr key={run.run_id}>
                    <td>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() =>
                          void navigation.navigate({
                            kind: "run",
                            registrationId: project.id,
                            runId: run.run_id,
                          })
                        }
                      >
                        {run.run_id}
                      </button>
                    </td>
                    <td>
                      {project.decisions.find(
                        (item) => item.id === run.decision_id,
                      )?.name ?? run.decision_id}{" "}
                      /{" "}
                      {project.datasets.find(
                        (item) => item.id === run.dataset_id,
                      )?.name ?? run.dataset_id}
                    </td>
                    <td>{run.mode}</td>
                    <td>
                      {run.state}
                      {run.execution_active ? " · active" : ""}
                    </td>
                    <td>
                      {run.attempts_used} / {run.attempt_limit} (
                      {run.attempts_remaining} remaining)
                    </td>
                    <td>
                      {run.segments.at(-1)?.ended_at ??
                        run.segments.at(-1)?.started_at ??
                        "Not started"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {cursor && (
            <button
              type="button"
              disabled={moreLoading}
              onClick={() => void loadMore()}
            >
              {moreLoading ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </article>
  );
}

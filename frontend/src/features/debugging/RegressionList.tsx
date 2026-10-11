import { useEffect, useRef, useState } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway } from "../../workspace/gateway";
import { useRenderedScopeEpoch } from "./useRenderedScopeEpoch";

type Regression = ApiOperationData<"listRegressions">["items"][number];
type RemoveBody = ApiOperationBody<"removeRegression">;
type RemoveIntent = {
  registrationId: string;
  decisionId: string;
  regressionId: string;
  body: RemoveBody;
  scopeEpoch: number;
  operations: DebuggingGateway["regressions"];
};

export function RegressionList({
  registrationId,
  decisionId,
  decisionName,
  operations,
  navigation,
}: {
  registrationId: string;
  decisionId: string;
  decisionName: string;
  operations: DebuggingGateway["regressions"];
  navigation: WorkspaceNavigation;
}) {
  const scopeEpoch = useRenderedScopeEpoch(`${registrationId}|${decisionId}`);
  const scopeEpochRef = useRef(scopeEpoch);
  scopeEpochRef.current = scopeEpoch;
  const [itemsView, setItemsView] = useState<{
    scopeEpoch: number;
    value: readonly Regression[];
  }>({ scopeEpoch, value: [] });
  const items = itemsView.scopeEpoch === scopeEpoch ? itemsView.value : [];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [lastReceiptView, setLastReceiptView] = useState<{
    scopeEpoch: number;
    value: Regression | undefined;
  }>({ scopeEpoch, value: undefined });
  const lastReceipt =
    lastReceiptView.scopeEpoch === scopeEpoch
      ? lastReceiptView.value
      : undefined;
  const [view, setView] = useState<{
    scopeEpoch: number;
    state: MutationState<Regression>;
  }>({ scopeEpoch, state: { kind: "idle" } });
  const mutation = useRef<
    RetainedMutation<RemoveIntent, Regression> | undefined
  >(undefined);
  if (!mutation.current) {
    mutation.current = new RetainedMutation(
      async (intent) => {
        const result = await intent.operations.remove({
          registrationId: intent.registrationId,
          decisionId: intent.decisionId,
          regressionId: intent.regressionId,
          body: intent.body,
        });
        if (
          result.data.decision_id !== intent.decisionId ||
          result.data.regression_id !== intent.regressionId
        )
          throw new Error(
            "The removal receipt did not match the selected regression.",
          );
        return result.data;
      },
      (next) => {
        const owner = mutation.current?.originalRequest;
        if (owner) setView({ scopeEpoch: owner.scopeEpoch, state: next });
      },
    );
  }
  const state =
    view.scopeEpoch === scopeEpoch ? view.state : { kind: "idle" as const };
  const mutationKind = mutation.current.state.kind;
  const retainedOwner = mutation.current.originalRequest;
  const retainedViewStale =
    retainedOwner !== undefined && retainedOwner.scopeEpoch !== scopeEpoch;
  const busy =
    mutationKind === "submitting" || mutationKind === "outcome-unknown";
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: busy,
    isDirtyNow: () => busyRef.current,
    save: async () => {
      throw new Error("Retry the original regression removal before leaving.");
    },
    discard: () => undefined,
    blockedMessage: busy
      ? "The removal may have been recorded. Retry its original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `${registrationId}:regressions:${decisionId}`,
        guard,
      ),
    [decisionId, guard, navigation, registrationId],
  );

  async function refresh() {
    const epoch = scopeEpochRef.current;
    setLoading(true);
    setError(undefined);
    try {
      const result = await operations.list({ registrationId, decisionId });
      if (result.data.items.some((item) => item.decision_id !== decisionId))
        throw new Error(
          "The service returned a regression for another decision.",
        );
      if (epoch === scopeEpochRef.current)
        setItemsView({ scopeEpoch: epoch, value: result.data.items });
    } catch (cause) {
      if (epoch === scopeEpochRef.current) setError(safeMessage(cause));
    } finally {
      if (epoch === scopeEpochRef.current) setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(undefined);
    void operations
      .list({ registrationId, decisionId, signal: controller.signal })
      .then((result) => {
        if (!active) return;
        if (result.data.items.some((item) => item.decision_id !== decisionId))
          throw new Error(
            "The service returned a regression for another decision.",
          );
        setItemsView({ scopeEpoch, value: result.data.items });
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
    };
  }, [decisionId, operations, registrationId]);

  async function remove(item: Regression) {
    if (busy || mutation.current?.state.kind !== "idle") return;
    const body: RemoveBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      decision_id: decisionId,
    };
    const epoch = scopeEpochRef.current;
    const receipt = await mutation.current?.submit({
      registrationId,
      decisionId,
      regressionId: item.regression_id,
      body,
      scopeEpoch: epoch,
      operations,
    });
    if (receipt) {
      if (epoch === scopeEpochRef.current)
        setLastReceiptView({ scopeEpoch: epoch, value: receipt });
      mutation.current?.reset();
      setView({ scopeEpoch: epoch, state: { kind: "idle" } });
      if (epoch === scopeEpochRef.current) await refresh();
    }
  }

  async function retryOriginal() {
    const owner = mutation.current?.originalRequest;
    const receipt = await mutation.current?.retryOriginal();
    if (receipt) {
      if (owner?.scopeEpoch === scopeEpochRef.current)
        setLastReceiptView({ scopeEpoch: owner.scopeEpoch, value: receipt });
      mutation.current?.reset();
      if (owner)
        setView({ scopeEpoch: owner.scopeEpoch, state: { kind: "idle" } });
      if (owner?.scopeEpoch === scopeEpochRef.current) await refresh();
    }
  }

  return (
    <article className="document">
      <h1>Regression examples for {decisionName}</h1>
      <p>
        Saved regressions are reviewed reference cases. They do not infer an
        expected answer or start provider work.
      </p>
      {error && <ErrorSummary message={error} retry={() => void refresh()} />}
      {state.kind === "outcome-unknown" && (
        <ErrorSummary message={state.message} />
      )}
      {retainedViewStale && mutationKind === "outcome-unknown" && (
        <section role="status">
          <p>
            An earlier regression removal is unresolved and can only be retried
            unchanged.
          </p>
          <button type="button" onClick={() => void retryOriginal()}>
            Retry original unchanged removal
          </button>
        </section>
      )}
      {(state.kind === "failed" || state.kind === "conflict") && (
        <ErrorSummary message={state.message} />
      )}
      {loading ? (
        <LoadingState>Loading regression examples…</LoadingState>
      ) : null}
      {!loading && items.length === 0 ? (
        <p className="muted">No regression examples are saved.</p>
      ) : null}
      {items.length > 0 && (
        <div className="table-region">
          <table>
            <caption>Service-reported regression records</caption>
            <thead>
              <tr>
                <th>Case</th>
                <th>Accepted options</th>
                <th>Source</th>
                <th>Status</th>
                <th>Reason</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.regression_id}>
                  <td>
                    {item.case_id} · <code>{item.regression_id}</code>
                  </td>
                  <td>{item.acceptable_option_ids.join(", ")}</td>
                  <td>
                    {item.provenance} · split {item.original_split}
                  </td>
                  <td>
                    {item.removed
                      ? "Removed"
                      : item.executable
                        ? "Executable"
                        : "Unavailable"}
                  </td>
                  <td>{item.unavailable_reason ?? item.reason}</td>
                  <td>
                    {!item.removed && (
                      <button
                        type="button"
                        disabled={busy || loading}
                        onClick={() => void remove(item)}
                      >
                        Remove from future checks
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {state.kind === "outcome-unknown" && (
        <button type="button" onClick={() => void retryOriginal()}>
          Retry original unchanged removal
        </button>
      )}
      {(state.kind === "failed" || state.kind === "conflict") && (
        <button
          type="button"
          onClick={() => {
            mutation.current?.reset();
            setView({ scopeEpoch, state: { kind: "idle" } });
          }}
        >
          Review a new removal request
        </button>
      )}
      {lastReceipt && (
        <p role="status">
          Removal for <code>{lastReceipt.regression_id}</code> is acknowledged;
          the list above was refreshed separately.
        </p>
      )}
      {prompt}
    </article>
  );
}

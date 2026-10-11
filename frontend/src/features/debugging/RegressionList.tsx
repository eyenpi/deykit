import { useEffect, useRef, useState } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway } from "../../workspace/gateway";

type Regression = ApiOperationData<"listRegressions">["items"][number];
type RemoveBody = ApiOperationBody<"removeRegression">;
type RemoveIntent = {
  registrationId: string;
  decisionId: string;
  regressionId: string;
  body: RemoveBody;
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
  const [items, setItems] = useState<readonly Regression[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [lastReceipt, setLastReceipt] = useState<Regression>();
  const [state, setState] = useState<MutationState<Regression>>({ kind: "idle" });
  const mutation = useRef<RetainedMutation<RemoveIntent, Regression> | undefined>(
    undefined,
  );
  if (!mutation.current) {
    mutation.current = new RetainedMutation(async (intent) => {
      const result = await operations.remove(intent);
      if (
        result.data.decision_id !== intent.decisionId ||
        result.data.regression_id !== intent.regressionId
      )
        throw new Error("The removal receipt did not match the selected regression.");
      return result.data;
    }, setState);
  }
  const busy = state.kind === "submitting" || state.kind === "outcome-unknown";
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
    () => navigation.registerDirtyGuard(`${registrationId}:regressions:${decisionId}`, guard),
    [decisionId, guard, navigation, registrationId],
  );

  async function refresh() {
    setLoading(true);
    setError(undefined);
    try {
      const result = await operations.list({ registrationId, decisionId });
      if (result.data.items.some((item) => item.decision_id !== decisionId))
        throw new Error("The service returned a regression for another decision.");
      setItems(result.data.items);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(undefined);
    void operations.list({ registrationId, decisionId, signal: controller.signal })
      .then((result) => {
        if (!active) return;
        if (result.data.items.some((item) => item.decision_id !== decisionId))
          throw new Error("The service returned a regression for another decision.");
        setItems(result.data.items);
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
    if (busy) return;
    const body: RemoveBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      decision_id: decisionId,
    };
    const receipt = await mutation.current?.submit({
      registrationId,
      decisionId,
      regressionId: item.regression_id,
      body,
    });
    if (receipt) {
      setLastReceipt(receipt);
      mutation.current?.reset();
      setState({ kind: "idle" });
      await refresh();
    }
  }

  async function retryOriginal() {
    const receipt = await mutation.current?.retryOriginal();
    if (receipt) {
      setLastReceipt(receipt);
      mutation.current?.reset();
      setState({ kind: "idle" });
      await refresh();
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
      {(state.kind === "failed" || state.kind === "conflict") && (
        <ErrorSummary message={state.message} />
      )}
      {loading ? <LoadingState>Loading regression examples…</LoadingState> : null}
      {!loading && items.length === 0 ? <p className="muted">No regression examples are saved.</p> : null}
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
                  <td>{item.provenance} · split {item.original_split}</td>
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
            setState({ kind: "idle" });
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

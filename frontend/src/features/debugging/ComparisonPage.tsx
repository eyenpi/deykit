import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway, ExecutionGateway } from "../../workspace/gateway";

type Comparison = ApiOperationData<"readComparison">;
type Evaluation = ApiOperationData<"readEvaluation">;
type CompareBody = ApiOperationBody<"createComparison">;
type ComparisonIntent = {
  registrationId: string;
  leftId: string;
  rightId: string;
  body: CompareBody;
};
type OutcomeRecord = { [key: string]: unknown };

const BUCKETS = [
  "left_only",
  "right_only",
  "changed_input",
  "changed_question_options",
  "changed_expectations",
  "unavailable_answer",
  "excluded_expectation",
  "unlabelled_agreement",
  "unlabelled_disagreement",
  "both_correct",
  "improved",
  "regressed",
  "both_wrong",
] as const;

function record(value: unknown): OutcomeRecord | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    return undefined;
  return Object.fromEntries(Object.entries(value));
}

function counts(value: unknown): OutcomeRecord | undefined {
  const outcomes = record(value);
  return outcomes ? record(outcomes.primary_counts) : undefined;
}

export function ComparisonPage({
  registrationId,
  comparisonId,
  debugging,
  execution,
  navigation,
}: {
  registrationId: string;
  comparisonId?: string;
  debugging: DebuggingGateway;
  execution: ExecutionGateway;
  navigation: WorkspaceNavigation;
}) {
  const [items, setItems] = useState<readonly Comparison[]>([]);
  const [comparison, setComparison] = useState<Comparison>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [refreshToken, setRefreshToken] = useState(0);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [verified, setVerified] = useState<readonly [Evaluation, Evaluation]>();
  const [checking, setChecking] = useState(false);
  const [state, setState] = useState<MutationState<Comparison>>({ kind: "idle" });
  const mutation = useRef<
    RetainedMutation<ComparisonIntent, Comparison> | undefined
  >(undefined);
  if (!mutation.current) {
    mutation.current = new RetainedMutation(async (intent) => {
      const result = await debugging.comparisons.create({
        registrationId: intent.registrationId,
        body: intent.body,
      });
      const receipt = result.data;
      if (
        receipt.left_evaluation_id !== intent.leftId ||
        receipt.right_evaluation_id !== intent.rightId
      )
        throw new Error("The comparison receipt changed the requested sides.");
      return receipt;
    }, setState);
  }
  const busy = state.kind === "submitting" || state.kind === "outcome-unknown";
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const dirty =
    state.kind !== "committed" && (!!leftId || !!rightId);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: dirty || busy,
    isDirtyNow: () => dirtyRef.current || busyRef.current,
    save: async () => {
      throw new Error("Create the comparison or discard the selected IDs before leaving.");
    },
    discard: () => {
      if (!busyRef.current) {
        setLeftId("");
        setRightId("");
        setVerified(undefined);
      }
    },
    blockedMessage: busy
      ? "The comparison request is still settling. Retry the original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () => navigation.registerDirtyGuard(`${registrationId}:comparison:create`, guard),
    [guard, navigation, registrationId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(undefined);
    setComparison(undefined);
    void (async () => {
      try {
        if (comparisonId) {
          const result = await debugging.comparisons.read({
            registrationId,
            comparisonId,
            signal: controller.signal,
          });
          if (result.data.comparison_id !== comparisonId)
            throw new Error("The service returned a different comparison.");
          if (active) setComparison(result.data);
        }
        const result = await debugging.comparisons.list({
          registrationId,
          query: { limit: 50 },
          signal: controller.signal,
        });
        if (!active) return;
        setItems(result.data.items);
      } catch (cause) {
        if (active && !controller.signal.aborted) setError(safeMessage(cause));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [comparisonId, debugging.comparisons, refreshToken, registrationId]);

  async function verifySides() {
    if (!leftId.trim() || !rightId.trim() || leftId.trim() === rightId.trim()) {
      setError("Choose two different saved evaluation IDs.");
      setVerified(undefined);
      return;
    }
    setChecking(true);
    setError(undefined);
    try {
      const [leftResult, rightResult] = await Promise.all([
        execution.inspection.readEvaluation({
          registrationId,
          evaluationId: leftId.trim(),
        }),
        execution.inspection.readEvaluation({
          registrationId,
          evaluationId: rightId.trim(),
        }),
      ]);
      const sides = [leftResult.data, rightResult.data] as const;
      if (
        sides[0].evaluation_id !== leftId.trim() ||
        sides[1].evaluation_id !== rightId.trim() ||
        sides[0].run_id === "" ||
        sides[1].run_id === ""
      )
        throw new Error("The saved evaluation details did not match the selected IDs.");
      setVerified(sides);
    } catch (cause) {
      setVerified(undefined);
      setError(safeMessage(cause));
    } finally {
      setChecking(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!verified || busy) return;
    const body: CompareBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      left_evaluation_id: verified[0].evaluation_id,
      right_evaluation_id: verified[1].evaluation_id,
    };
    await mutation.current?.submit({
      registrationId,
      leftId: verified[0].evaluation_id,
      rightId: verified[1].evaluation_id,
      body,
    });
  }

  async function retryOriginal() {
    await mutation.current?.retryOriginal();
  }

  function routeToComparison(id: string) {
    void navigation.navigate({ kind: "comparison", registrationId, comparisonId: id });
  }

  const primaryCounts = comparison ? counts(comparison.outcomes) : undefined;
  const outcomes = comparison ? record(comparison.outcomes) : undefined;

  return (
    <article className="document">
      <h1>{comparisonId ? "Saved comparison" : "Comparisons"}</h1>
      {error && <ErrorSummary message={error} retry={() => setRefreshToken((value) => value + 1)} />}
      {comparison && (
        <section aria-label="Pinned comparison details">
          <p>
            Comparison <code>{comparison.comparison_id}</code>; content hash{" "}
            <code>{comparison.content_hash}</code>; replayed {comparison.replayed ? "yes" : "no"}.
          </p>
          <dl>
            <dt>Left evaluation</dt>
            <dd>
              {comparison.left_evaluation_id} · result{" "}
              {comparison.left_result_snapshot_id}
            </dd>
            <dt>Right evaluation</dt>
            <dd>
              {comparison.right_evaluation_id} · result{" "}
              {comparison.right_result_snapshot_id}
            </dd>
            <dt>Quality denominator</dt>
            <dd>{typeof outcomes?.quality_denominator === "string" ? outcomes.quality_denominator : "Unavailable"}</dd>
          </dl>
          <h2>Service-reported outcome buckets</h2>
          {primaryCounts ? (
            <dl>
              {BUCKETS.map((bucket) => (
                <div key={bucket}>
                  <dt>{bucket.replaceAll("_", " ")}</dt>
                  <dd>
                    {(() => {
                      const count = primaryCounts[bucket];
                      return typeof count === "string" ? count : "Unavailable";
                    })()}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>The service did not provide a supported primary bucket summary.</p>
          )}
        </section>
      )}
      {loading ? <LoadingState>Loading saved comparisons…</LoadingState> : null}
      {!loading && items.length === 0 ? <p className="muted">No saved comparisons.</p> : null}
      {items.length > 0 && (
        <ul aria-label="Saved comparisons">
          {items.map((item) => (
            <li key={item.comparison_id}>
              <button type="button" onClick={() => routeToComparison(item.comparison_id)}>
                {item.comparison_id}: {item.left_evaluation_id} versus {item.right_evaluation_id}
              </button>
              <p className="muted">
                {item.created_at} · content hash <code>{item.content_hash}</code>
              </p>
            </li>
          ))}
        </ul>
      )}
      {!comparisonId && (
        <section aria-label="Create a comparison">
          <h2>Compare saved evaluations</h2>
          <p>Comparison uses two saved evaluations. Reading and comparison make zero provider calls.</p>
          <form onSubmit={(event) => void create(event)}>
            <label className="field">
              Left saved evaluation ID
              <input
              value={leftId}
              disabled={busy || checking}
                onChange={(event) => {
                  setLeftId(event.currentTarget.value);
                  setVerified(undefined);
                }}
              />
            </label>
            <label className="field">
              Right saved evaluation ID
              <input
              value={rightId}
              disabled={busy || checking}
                onChange={(event) => {
                  setRightId(event.currentTarget.value);
                  setVerified(undefined);
                }}
              />
            </label>
            <div className="actions">
              <button type="button" disabled={checking || busy} onClick={() => void verifySides()}>
                Verify saved evaluations
              </button>
              <button type="submit" disabled={!verified || busy || state.kind === "committed"}>
                Create saved comparison
              </button>
              {state.kind === "outcome-unknown" && (
                <button type="button" onClick={() => void retryOriginal()}>
                  Retry original unchanged comparison
                </button>
              )}
              {(state.kind === "failed" || state.kind === "conflict") && (
                <button
                  type="button"
                  onClick={() => {
                    mutation.current?.reset();
                    setState({ kind: "idle" });
                    setVerified(undefined);
                  }}
                >
                  Review saved evaluations again
                </button>
              )}
              {state.kind === "committed" && (
                <button
                  type="button"
                  onClick={() => {
                    const id = state.receipt.comparison_id;
                    mutation.current?.reset();
                    setState({ kind: "idle" });
                    routeToComparison(id);
                  }}
                >
                  Open saved comparison
                </button>
              )}
            </div>
          </form>
          {verified && (
            <dl aria-label="Verified evaluation context">
              {verified.map((item, index) => (
                <div key={item.evaluation_id}>
                  <dt>{index === 0 ? "Left" : "Right"} saved evaluation</dt>
                  <dd>
                    {item.evaluation_id} · run {item.run_id} · {item.mode} · result{" "}
                    {item.result_snapshot_id} · labels {item.label_snapshot_id}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {(state.kind === "failed" || state.kind === "conflict" || state.kind === "outcome-unknown") && (
            <ErrorSummary message={state.message} />
          )}
        </section>
      )}
      {prompt}
    </article>
  );
}

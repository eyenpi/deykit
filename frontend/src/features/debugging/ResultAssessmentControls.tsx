import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ErrorSummary } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import type { DebuggingGateway } from "../../workspace/gateway";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";

type Evaluation = ApiOperationData<"readEvaluation">;
type EvaluationBody = ApiOperationBody<"createEvaluation">;
type ReevaluationBody = ApiOperationBody<"reevaluateRun">;
type Intent =
  | {
      kind: "save";
      scopeIdentity: string;
      registrationId: string;
      runId: string;
      body: EvaluationBody;
    }
  | {
      kind: "reevaluate";
      scopeIdentity: string;
      registrationId: string;
      runId: string;
      body: ReevaluationBody;
    };

type MutationView = {
  scopeIdentity: string;
  state: MutationState<Evaluation>;
};

export function ResultAssessmentControls({
  registrationId,
  runId,
  resultSnapshotId,
  labelSnapshotId,
  scopeIdentity,
  isCurrent,
  onBusyChange,
  selectedEvaluation,
  operations,
  navigation,
}: {
  registrationId: string;
  runId: string;
  resultSnapshotId: string;
  labelSnapshotId: string;
  scopeIdentity: string;
  isCurrent: boolean;
  onBusyChange: (busy: boolean) => void;
  selectedEvaluation?: Evaluation;
  operations: DebuggingGateway["evaluations"];
  navigation: WorkspaceNavigation;
}) {
  const [view, setView] = useState<MutationView>({
    scopeIdentity,
    state: { kind: "idle" },
  });
  const mutation = useRef<RetainedMutation<Intent, Evaluation> | undefined>(
    undefined,
  );
  if (!mutation.current) {
    mutation.current = new RetainedMutation(
      async (intent) => {
        const result =
          intent.kind === "save"
            ? await operations.create({
                registrationId: intent.registrationId,
                runId: intent.runId,
                body: intent.body,
              })
            : await operations.reevaluate({
                registrationId: intent.registrationId,
                runId: intent.runId,
                body: intent.body,
              });
        const receipt = result.data;
        if (
          receipt.run_id !== intent.runId ||
          receipt.result_snapshot_id !== intent.body.result_snapshot_id ||
          (intent.kind === "save" &&
            receipt.label_snapshot_id !== intent.body.label_snapshot_id)
        )
          throw new Error("The evaluation receipt did not match its saved result.");
        return receipt;
      },
      (state) => {
        const owner = mutation.current?.originalRequest?.scopeIdentity;
        if (owner) setView({ scopeIdentity: owner, state });
        onBusyChange(state.kind === "submitting" || state.kind === "outcome-unknown");
      },
    );
  }
  const state = view.state;
  const uncertain = state.kind === "submitting" || state.kind === "outcome-unknown";
  const uncertainRef = useRef(uncertain);
  uncertainRef.current = uncertain;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: uncertain,
    isDirtyNow: () => uncertainRef.current,
    save: async () => {
      throw new Error("Retry the original evaluation before leaving this run.");
    },
    discard: () => undefined,
    blockedMessage: uncertain
      ? "The evaluation request is still settling. Retry the original request to resolve its outcome before leaving."
      : undefined,
    isBlockedNow: () => uncertainRef.current,
  });
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `${registrationId}:evaluation:${runId}`,
        guard,
      ),
    [guard, navigation, registrationId, runId],
  );
  const currentScope = scopeIdentity;
  const originalRequest = mutation.current.originalRequest;
  const originalScope = originalRequest?.scopeIdentity;

  function startSave() {
    const body: EvaluationBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      result_snapshot_id: resultSnapshotId,
      label_snapshot_id: labelSnapshotId,
      mode: "original",
    };
    void mutation.current?.submit({
      kind: "save",
      scopeIdentity,
      registrationId,
      runId,
      body,
    });
  }

  function startReevaluation() {
    if (!selectedEvaluation) return;
    const body: ReevaluationBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      result_snapshot_id: selectedEvaluation.result_snapshot_id,
    };
    void mutation.current?.submit({
      kind: "reevaluate",
      scopeIdentity,
      registrationId,
      runId,
      body,
    });
  }

  async function retryOriginal() {
    await mutation.current?.retryOriginal();
  }

  function beginAnother() {
    mutation.current?.reset();
    setView({ scopeIdentity, state: { kind: "idle" } });
  }

  return (
    <section className="debugging-controls" aria-label="Saved result evaluation">
      <h3>Evaluation</h3>
      <p>
        These actions assess saved results and make zero provider calls. The
        current result and label snapshots stay pinned.
      </p>
      <p>
        Result <code>{resultSnapshotId}</code>; labels{" "}
        <code>{labelSnapshotId}</code>.
      </p>
      {selectedEvaluation && (
        <p>
          Selected saved evaluation <code>{selectedEvaluation.evaluation_id}</code>;
          result <code>{selectedEvaluation.result_snapshot_id}</code>, labels{" "}
          <code>{selectedEvaluation.label_snapshot_id}</code>.
        </p>
      )}
      <div className="actions">
        <button
          type="button"
          disabled={!isCurrent || uncertain || state.kind === "committed"}
          onClick={startSave}
        >
          Save evaluation
        </button>
        {selectedEvaluation && (
          <button
            type="button"
            disabled={!isCurrent || uncertain || state.kind === "committed"}
            onClick={startReevaluation}
          >
            Re-evaluate saved answers
          </button>
        )}
        {state.kind === "outcome-unknown" && (
          <button type="button" onClick={() => void retryOriginal()}>
            Retry original unchanged request
          </button>
        )}
        {state.kind === "committed" && (
          <button type="button" onClick={beginAnother}>
            Start another explicit evaluation
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
            Review a new evaluation request
          </button>
        )}
      </div>
      {state.kind === "failed" || state.kind === "conflict" ||
      state.kind === "outcome-unknown" ? (
        <ErrorSummary message={state.message} />
      ) : null}
      {state.kind === "committed" && (
        <p role="status">
          Saved evaluation <code>{state.receipt.evaluation_id}</code> for result{" "}
          <code>{state.receipt.result_snapshot_id}</code> and labels{" "}
          <code>{state.receipt.label_snapshot_id}</code>. Replayed: {" "}
          {state.receipt.replayed ? "yes" : "no"}.
        </p>
      )}
      {originalScope && originalScope !== currentScope && uncertain && (
        <p role="status">
          The retained request still belongs to its original pinned result. Retry
          it unchanged before starting a request for this selection.
        </p>
      )}
      {!isCurrent && <p role="status">The result selection is refreshing. New evaluation requests are paused until its frozen snapshot is confirmed.</p>}
      {prompt}
    </section>
  );
}

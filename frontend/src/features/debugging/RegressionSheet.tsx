import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway } from "../../workspace/gateway";
import { useRenderedScopeEpoch } from "./useRenderedScopeEpoch";

type Regression = ApiOperationData<"addRegression">;
type AddBody = ApiOperationBody<"addRegression">;
type Option = { id: string; name: string };
type Intent = {
  registrationId: string;
  decisionId: string;
  runId: string;
  caseId: string;
  resultSnapshotId: string;
  body: AddBody;
  scopeEpoch: number;
  operations: DebuggingGateway["regressions"];
};

export function RegressionSheet({
  registrationId,
  decisionId,
  decisionName,
  runId,
  caseId,
  resultSnapshotId,
  options,
  operations,
  navigation,
  onClose,
}: {
  registrationId: string;
  decisionId: string;
  decisionName: string;
  runId: string;
  caseId: string;
  resultSnapshotId: string;
  options: readonly Option[];
  operations: DebuggingGateway["regressions"];
  navigation: WorkspaceNavigation;
  onClose: () => void;
}) {
  const scopeEpoch = useRenderedScopeEpoch(
    `${registrationId}|${decisionId}|${runId}|${caseId}|${resultSnapshotId}`,
  );
  const scopeEpochRef = useRef(scopeEpoch);
  scopeEpochRef.current = scopeEpoch;
  const [selectedView, setSelectedView] = useState<{
    scopeEpoch: number;
    value: readonly string[];
  }>({ scopeEpoch, value: [] });
  const selected =
    selectedView.scopeEpoch === scopeEpoch ? selectedView.value : [];
  function setSelected(
    value:
      readonly string[] | ((previous: readonly string[]) => readonly string[]),
  ) {
    const previous =
      selectedView.scopeEpoch === scopeEpoch ? selectedView.value : [];
    setSelectedView({
      scopeEpoch,
      value: typeof value === "function" ? value(previous) : value,
    });
  }
  const [reasonView, setReasonView] = useState({ scopeEpoch, value: "" });
  const reason = reasonView.scopeEpoch === scopeEpoch ? reasonView.value : "";
  function setReason(value: string) {
    setReasonView({ scopeEpoch, value });
  }
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [view, setView] = useState<{
    scopeEpoch: number;
    state: MutationState<Regression>;
  }>({ scopeEpoch, state: { kind: "idle" } });
  const mutation = useRef<RetainedMutation<Intent, Regression> | undefined>(
    undefined,
  );
  if (!mutation.current) {
    mutation.current = new RetainedMutation(
      async (intent) => {
        const result = await intent.operations.add({
          registrationId: intent.registrationId,
          decisionId: intent.decisionId,
          body: intent.body,
        });
        const receipt = result.data;
        if (
          receipt.decision_id !== intent.decisionId ||
          receipt.case_id !== intent.caseId ||
          receipt.source_run_id !== intent.runId ||
          receipt.source_result_snapshot_id !== intent.resultSnapshotId ||
          receipt.reason !== intent.body.reason ||
          receipt.acceptable_option_ids.length !==
            intent.body.acceptable_option_ids.length ||
          receipt.acceptable_option_ids.some(
            (id, index) => id !== intent.body.acceptable_option_ids[index],
          )
        )
          throw new Error(
            "The regression receipt did not match the pinned case and selected oracle.",
          );
        return receipt;
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
  const dirty =
    state.kind !== "committed" && (selected.length > 0 || reason.length > 0);
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: dirty || busy,
    isDirtyNow: () => dirtyRef.current || busyRef.current,
    save: async () => {
      const receipt = await save();
      if (!receipt)
        throw new Error("The regression example could not be confirmed.");
    },
    discard: () => {
      if (!busyRef.current) {
        setSelected([]);
        setReason("");
      }
    },
    blockedMessage: busy
      ? "The regression request may have been saved. Retry its original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `${registrationId}:regression:${decisionId}:${runId}:${caseId}`,
        guard,
      ),
    [caseId, decisionId, guard, navigation, registrationId, runId],
  );

  async function save() {
    const trimmedReason = reason.trim();
    if (
      !trimmedReason ||
      selected.length === 0 ||
      busy ||
      mutation.current?.state.kind !== "idle"
    )
      return undefined;
    const body: AddBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      run_id: runId,
      case_id: caseId,
      result_snapshot_id: resultSnapshotId,
      acceptable_option_ids: [...selected],
      reason: trimmedReason,
      provenance: "human",
    };
    const epoch = scopeEpochRef.current;
    return mutation.current.submit({
      registrationId,
      decisionId,
      runId,
      caseId,
      resultSnapshotId,
      body,
      scopeEpoch: epoch,
      operations,
    });
  }

  async function retryOriginal() {
    await mutation.current?.retryOriginal();
  }

  return (
    <Modal
      title={`Add regression example for ${decisionName}`}
      sheet
      onDismiss={() => {
        if (busy) return;
        if (dirty) setConfirmDiscard(true);
        else onClose();
      }}
    >
      <div className="modal-body">
        <p>
          Case <code>{caseId}</code> from run <code>{runId}</code>; pinned
          result <code>{resultSnapshotId}</code>.
        </p>
        <p>
          Choose the acceptable answer explicitly. No predicted answer is
          selected for you.
        </p>
        <fieldset disabled={busy || state.kind === "committed"}>
          <legend>Human-reviewed acceptable options</legend>
          {options.map((option) => (
            <label key={option.id}>
              <input
                type="checkbox"
                checked={selected.includes(option.id)}
                onChange={(event) =>
                  setSelected((current) =>
                    event.currentTarget.checked
                      ? [...current, option.id]
                      : current.filter((id) => id !== option.id),
                  )
                }
              />
              {option.name} · {option.id}
            </label>
          ))}
        </fieldset>
        <label className="field">
          Reason
          <textarea
            value={reason}
            disabled={busy || state.kind === "committed"}
            onChange={(event) => setReason(event.currentTarget.value)}
          />
        </label>
        {state.kind === "committed" && (
          <p role="status">
            Regression <code>{state.receipt.regression_id}</code> saved for the
            selected frozen case. The regression list is a separate read.
          </p>
        )}
        {(state.kind === "failed" ||
          state.kind === "conflict" ||
          state.kind === "outcome-unknown") && (
          <ErrorSummary message={state.message} />
        )}
        {retainedViewStale && mutationKind === "outcome-unknown" && (
          <section role="status">
            <p>
              An earlier regression request is unresolved and can only be
              retried unchanged.
            </p>
            <button type="button" onClick={() => void retryOriginal()}>
              Retry original unchanged regression
            </button>
          </section>
        )}
        {retainedViewStale && mutationKind === "committed" && (
          <button
            type="button"
            onClick={() => {
              mutation.current?.reset();
              setView({ scopeEpoch, state: { kind: "idle" } });
              setSelected([]);
              setReason("");
            }}
          >
            Start a regression for this pinned case
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
            Review a new regression request
          </button>
        )}
        <div className="actions">
          <button
            type="button"
            disabled={
              busy ||
              state.kind === "committed" ||
              selected.length === 0 ||
              reason.trim().length === 0
            }
            onClick={() => void save()}
          >
            Save regression example
          </button>
          {state.kind === "outcome-unknown" && (
            <button type="button" onClick={() => void retryOriginal()}>
              Retry original unchanged regression
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => (dirty ? setConfirmDiscard(true) : onClose())}
          >
            Close
          </button>
        </div>
        {confirmDiscard && (
          <section role="alert" aria-label="Discard regression example">
            <p>Discard this regression oracle and reason?</p>
            <button type="button" onClick={() => setConfirmDiscard(false)}>
              Keep editing
            </button>
            <button type="button" onClick={onClose}>
              Discard proposal
            </button>
          </section>
        )}
        {prompt}
      </div>
    </Modal>
  );
}

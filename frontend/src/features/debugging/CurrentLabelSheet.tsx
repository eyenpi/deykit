import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { ExampleAuthoringOperations } from "../../workspace/gateway";
import { useRenderedScopeEpoch } from "./useRenderedScopeEpoch";

type LabelView =
  ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">;
type LabelReceipt =
  ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
type LabelBody =
  ApiOperationBody<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
type Intent = {
  registrationId: string;
  decisionId: string;
  datasetId: string;
  caseId: string;
  body: LabelBody;
  frozenInputHash: string;
  scopeEpoch: number;
  operations: ExampleAuthoringOperations;
};

export function CurrentLabelSheet({
  registrationId,
  decisionId,
  datasetId,
  caseId,
  frozenInputHash,
  frozenQuestionId,
  frozenOptionIds,
  frozenExpectedOptionIds,
  operations,
  navigation,
  onClose,
}: {
  registrationId: string;
  decisionId: string;
  datasetId: string;
  caseId: string;
  frozenInputHash: string;
  frozenQuestionId: string;
  frozenOptionIds: readonly string[];
  frozenExpectedOptionIds: readonly string[];
  operations: ExampleAuthoringOperations;
  navigation: WorkspaceNavigation;
  onClose: () => void;
}) {
  const scopeEpoch = useRenderedScopeEpoch(
    `${registrationId}|${decisionId}|${datasetId}|${caseId}|${frozenInputHash}|${frozenQuestionId}`,
  );
  const scopeEpochRef = useRef(scopeEpoch);
  scopeEpochRef.current = scopeEpoch;
  const [currentView, setCurrentView] = useState<{
    scopeEpoch: number;
    value: LabelView | undefined;
  }>({ scopeEpoch, value: undefined });
  const current =
    currentView.scopeEpoch === scopeEpoch ? currentView.value : undefined;
  const [selectionView, setSelectionView] = useState<{
    scopeEpoch: number;
    value: readonly string[];
  }>({ scopeEpoch, value: [] });
  const selected =
    selectionView.scopeEpoch === scopeEpoch ? selectionView.value : [];
  function setSelected(
    update:
      readonly string[] | ((previous: readonly string[]) => readonly string[]),
  ) {
    const previous =
      selectionView.scopeEpoch === scopeEpoch ? selectionView.value : [];
    setSelectionView({
      scopeEpoch,
      value: typeof update === "function" ? update(previous) : update,
    });
  }
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState<string>();
  const [view, setView] = useState<{
    scopeEpoch: number;
    state: MutationState<LabelReceipt>;
  }>({ scopeEpoch, state: { kind: "idle" } });
  const [lastReceiptView, setLastReceiptView] = useState<{
    scopeEpoch: number;
    value: LabelReceipt | undefined;
  }>({ scopeEpoch, value: undefined });
  const lastReceipt =
    lastReceiptView.scopeEpoch === scopeEpoch
      ? lastReceiptView.value
      : undefined;
  function setLastReceipt(value: LabelReceipt | undefined) {
    setLastReceiptView({ scopeEpoch, value });
  }
  const [readRevision, setReadRevision] = useState(0);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const mutation = useRef<RetainedMutation<Intent, LabelReceipt> | undefined>(
    undefined,
  );
  if (!mutation.current) {
    mutation.current = new RetainedMutation(
      async (intent) => {
        const result = await intent.operations.saveLabels({
          registrationId: intent.registrationId,
          decisionId: intent.decisionId,
          datasetId: intent.datasetId,
          body: intent.body,
        });
        const change = result.data.changes.find(
          (item) => item.operation_id === intent.body.operation_id,
        );
        if (
          result.data.changes.length !== 1 ||
          !change ||
          change.case_id !== intent.caseId ||
          change.dataset_id !== intent.datasetId ||
          change.decision_id !== intent.decisionId ||
          change.label?.input_hash !== intent.frozenInputHash
        )
          throw new Error(
            "The label receipt did not match the frozen case input.",
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
  const savedSelection = current?.label?.acceptable_option_ids ?? [];
  const dirty =
    [...savedSelection].sort().join("\u0000") !==
    [...selected].sort().join("\u0000");
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: dirty || busy,
    isDirtyNow: () => dirtyRef.current || busyRef.current,
    save: async () => {
      const receipt = await save();
      if (!receipt) throw new Error("The label change could not be confirmed.");
    },
    discard: () => {
      if (!busyRef.current)
        setSelected(current?.label?.acceptable_option_ids ?? []);
    },
    blockedMessage: busy
      ? "The label save may have committed. Retry its exact original request before leaving."
      : undefined,
    isBlockedNow: () => busyRef.current,
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `${registrationId}:current-label:${decisionId}:${datasetId}:${caseId}`,
        guard,
      ),
    [caseId, datasetId, decisionId, guard, navigation, registrationId],
  );

  async function refresh(signal?: AbortSignal) {
    const epoch = scopeEpochRef.current;
    const sourceOperations = operations;
    setLoading(true);
    setReadError(undefined);
    try {
      const result = await sourceOperations.readLabel({
        registrationId,
        decisionId,
        datasetId,
        caseId,
        signal,
      });
      if (
        result.data.review.decision_id !== decisionId ||
        result.data.review.dataset_id !== datasetId ||
        result.data.review.case_id !== caseId ||
        result.data.review.input_hash !== frozenInputHash ||
        result.data.review.question_id !== frozenQuestionId ||
        !result.data.definition.questions.some(
          (question) => question.id === frozenQuestionId,
        )
      )
        throw new Error(
          "The current label no longer matches the frozen case and question.",
        );
      const options =
        result.data.definition.questions
          .find((question) => question.id === frozenQuestionId)
          ?.options.map((option) => option.id) ?? [];
      if (
        options.length !== frozenOptionIds.length ||
        new Set(options).size !== options.length ||
        frozenOptionIds.some((id) => !options.includes(id))
      )
        throw new Error(
          "The current question options differ from the frozen run.",
        );
      if (result.data.label && result.data.label.input_hash !== frozenInputHash)
        throw new Error("The current label belongs to a different case input.");
      if (epoch === scopeEpochRef.current && !signal?.aborted) {
        setCurrentView({ scopeEpoch: epoch, value: result.data });
        setSelected(result.data.label?.acceptable_option_ids ?? []);
      }
    } catch (cause) {
      if (epoch === scopeEpochRef.current && !signal?.aborted)
        setReadError(safeMessage(cause));
    } finally {
      if (epoch === scopeEpochRef.current && !signal?.aborted)
        setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [
    caseId,
    datasetId,
    decisionId,
    frozenInputHash,
    frozenQuestionId,
    operations,
    readRevision,
    registrationId,
  ]);

  async function save() {
    if (
      !current ||
      busy ||
      mutation.current?.state.kind !== "idle" ||
      selected.length === 0
    )
      return undefined;
    const body: LabelBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      edits: [
        {
          review: current.review,
          action: "set",
          acceptable_option_ids: [...selected],
          provenance: "human",
        },
      ],
    };
    const epoch = scopeEpochRef.current;
    const receipt = await mutation.current.submit({
      registrationId,
      decisionId,
      datasetId,
      caseId,
      body,
      frozenInputHash,
      scopeEpoch: epoch,
      operations,
    });
    if (receipt && epoch === scopeEpochRef.current) {
      setLastReceipt(receipt);
      setReadRevision((value) => value + 1);
    }
    return receipt;
  }

  async function retryOriginal() {
    const owner = mutation.current?.originalRequest;
    const receipt = await mutation.current?.retryOriginal();
    if (receipt && owner?.scopeEpoch === scopeEpochRef.current) {
      setLastReceipt(receipt);
      setReadRevision((value) => value + 1);
    }
  }

  return (
    <Modal
      title="Review current label"
      sheet
      onDismiss={() => {
        if (busy) return;
        if (dirty) setConfirmDiscard(true);
        else onClose();
      }}
    >
      <div className="modal-body">
        <section aria-label="Frozen label expectation">
          <h3>Frozen run expectation</h3>
          <p>
            Case input hash <code>{frozenInputHash}</code>; question{" "}
            {frozenQuestionId}; expected options{" "}
            {frozenExpectedOptionIds.join(", ") || "none"}.
          </p>
        </section>
        {loading ? (
          <LoadingState>Reading the current mutable label…</LoadingState>
        ) : null}
        {readError && (
          <ErrorSummary
            message={readError}
            retry={() => setReadRevision((value) => value + 1)}
          />
        )}
        {current && !readError && (
          <>
            <section aria-label="Current mutable label">
              <h3>Current mutable label</h3>
              <p>
                Current review input hash{" "}
                <code>{current.review.input_hash}</code>; label{" "}
                {current.label?.acceptable_option_ids.join(", ") || "none"};
                provenance {current.label?.provenance ?? "none"}.
              </p>
            </section>
            <fieldset disabled={busy || state.kind === "committed"}>
              <legend>Set current acceptable options</legend>
              {current.definition.questions
                .find((question) => question.id === frozenQuestionId)
                ?.options.map((option) => (
                  <label key={option.id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(option.id)}
                      onChange={(event) =>
                        setSelected((previous) =>
                          event.currentTarget.checked
                            ? [...previous, option.id]
                            : previous.filter((id) => id !== option.id),
                        )
                      }
                    />
                    {option.name} · {option.id}
                  </label>
                ))}
            </fieldset>
            <button
              type="button"
              disabled={
                busy ||
                state.kind === "committed" ||
                !dirty ||
                selected.length === 0
              }
              onClick={() => void save()}
            >
              Save current label
            </button>
          </>
        )}
        {state.kind === "outcome-unknown" && (
          <>
            <ErrorSummary message={state.message} />
            <button type="button" onClick={() => void retryOriginal()}>
              Retry original unchanged label save
            </button>
          </>
        )}
        {retainedViewStale && mutationKind === "outcome-unknown" && (
          <section role="status">
            <p>
              An earlier label save is unresolved and can only be retried
              unchanged.
            </p>
            <button type="button" onClick={() => void retryOriginal()}>
              Retry original unchanged label save
            </button>
          </section>
        )}
        {retainedViewStale && mutationKind === "committed" && (
          <button
            type="button"
            onClick={() => {
              mutation.current?.reset();
              setView({ scopeEpoch, state: { kind: "idle" } });
              setLastReceipt(undefined);
            }}
          >
            Review a new label for this case
          </button>
        )}
        {(state.kind === "failed" || state.kind === "conflict") && (
          <ErrorSummary message={state.message} />
        )}
        {lastReceipt && (
          <p role="status">
            Label receipt recorded. Current label was re-read separately; frozen
            evaluation evidence remains unchanged.
          </p>
        )}
        {prompt}
        {confirmDiscard && (
          <div role="dialog" aria-label="Discard current label changes">
            <p>Discard this staged current label selection?</p>
            <button type="button" onClick={() => setConfirmDiscard(false)}>
              Keep editing
            </button>
            <button
              type="button"
              onClick={() => {
                setSelected(current?.label?.acceptable_option_ids ?? []);
                setConfirmDiscard(false);
                onClose();
              }}
            >
              Discard changes
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

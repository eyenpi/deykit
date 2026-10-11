import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import { Modal } from "../../components/Modal";
import type {
  ProjectOverview,
  WorkspaceGateway,
} from "../../workspace/gateway";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";

type Preview = ApiOperationData<"previewRun">;
type Accepted = ApiOperationData<"startRun">;
type RunRequest = ApiOperationBody<"previewRun">["request"];
type StartBody = ApiOperationBody<"startRun">;
type CasePage =
  ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
type ProviderPage = ApiOperationData<"listProviderProfiles">;
type FixturePage = ApiOperationData<"listFixtureSets">;
type RevisionPage = ApiOperationData<"listDecisionRevisions">;

type StartIntent = { registrationId: string; body: StartBody };

const REQUEST_DEFAULTS = {
  max_attempts: "100",
  concurrency: "2",
  timeout_seconds: "60",
  deadline_seconds: "600",
  max_retries_per_case: "1",
};

function integerField(
  value: string,
  minimum: number,
  maximum: number,
): number | null {
  if (!/^(?:0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : null;
}

function option(value: string): string | null {
  return value || null;
}

export function RunReview({
  project,
  decision,
  gateway,
  navigation,
  onClose,
  onStarted,
}: {
  project: ProjectOverview;
  decision: { id: string; name: string };
  gateway: WorkspaceGateway;
  navigation: WorkspaceNavigation;
  onClose: () => void;
  onStarted: (runId: string) => void;
}) {
  const [datasetId, setDatasetId] = useState(project.datasets[0]?.id ?? "");
  const [split, setSplit] = useState<
    "all" | "development" | "calibration" | "test"
  >("all");
  const [mode, setMode] = useState<"fixture" | "live">("fixture");
  const [fixtureId, setFixtureId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [caseIds, setCaseIds] = useState<readonly string[]>([]);
  const [includeRequest, setIncludeRequest] = useState(false);
  const [settings, setSettings] = useState(REQUEST_DEFAULTS);
  const [cases, setCases] = useState<CasePage>();
  const [profiles, setProfiles] = useState<ProviderPage>();
  const [fixtures, setFixtures] = useState<FixturePage>();
  const [revisions, setRevisions] = useState<RevisionPage>();
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [optionError, setOptionError] = useState<string>();
  const [review, setReview] = useState<Preview>();
  const [reviewRequest, setReviewRequest] = useState<RunRequest>();
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string>();
  const [proposalDirty, setProposalDirty] = useState(false);
  const proposalDirtyRef = useRef(false);
  const reviewInFlight = useRef(false);
  const reviewController = useRef<AbortController | undefined>(undefined);
  const [exitPrompt, setExitPrompt] = useState(false);
  const [startState, setStartState] = useState<MutationState<Accepted>>({
    kind: "idle",
  });
  const proposalGeneration = useRef(0);
  const reviewEpoch = useRef(0);
  const startMutation = useRef<
    RetainedMutation<StartIntent, Accepted> | undefined
  >(undefined);
  const registrationRef = useRef(project.id);
  const executionRef = useRef(gateway.execution);
  registrationRef.current = project.id;
  executionRef.current = gateway.execution;

  if (!startMutation.current) {
    startMutation.current = new RetainedMutation(async (intent) => {
      const result = await executionRef.current.runs.start({
        registrationId: intent.registrationId,
        body: intent.body,
      });
      const accepted = result.data;
      if (
        accepted.operation_id !== intent.body.operation_id ||
        accepted.mode !== intent.body.request.mode ||
        !accepted.run_id
      )
        throw new Error(
          "The service returned an incomplete run acknowledgement.",
        );
      return accepted;
    }, setStartState);
  }

  function markChanged() {
    proposalGeneration.current += 1;
    reviewController.current?.abort();
    reviewController.current = undefined;
    reviewInFlight.current = false;
    setReviewing(false);
    const state = startMutation.current?.state.kind;
    if (state === "failed" || state === "conflict" || state === "committed") {
      startMutation.current?.reset();
      setStartState({ kind: "idle" });
    }
    proposalDirtyRef.current = true;
    setProposalDirty(true);
    setReview(undefined);
    setReviewRequest(undefined);
    setReviewError(undefined);
  }

  async function reviewProposal(): Promise<void> {
    if (
      reviewInFlight.current ||
      startMutation.current?.state.kind === "submitting" ||
      startMutation.current?.state.kind === "outcome-unknown"
    )
      return;
    const selectedDataset = project.datasets.find(
      (item) => item.id === datasetId,
    );
    if (!selectedDataset) {
      setReviewError("Choose a dataset before reviewing this run.");
      return;
    }
    const parsed = {
      max_attempts: integerField(
        settings.max_attempts,
        1,
        Number.MAX_SAFE_INTEGER,
      ),
      concurrency: integerField(settings.concurrency, 1, 64),
      timeout_seconds: integerField(settings.timeout_seconds, 1, 600),
      deadline_seconds: integerField(settings.deadline_seconds, 1, 86400),
      max_retries_per_case: integerField(settings.max_retries_per_case, 0, 1),
    };
    if (Object.values(parsed).some((value) => value === null)) {
      setReviewError(
        "Enter whole-number settings within the displayed limits.",
      );
      return;
    }
    if (mode === "fixture" && !fixtureId) {
      setReviewError("Choose an authored fixture set for fixture mode.");
      return;
    }
    if (mode === "live" && !providerId) {
      setReviewError("Choose a live provider profile.");
      return;
    }
    const request: RunRequest = {
      decision_id: decision.id,
      dataset_id: selectedDataset.id,
      mode,
      split,
      case_ids: caseIds,
      revision_id: option(revisionId),
      fixture_set_id: mode === "fixture" ? fixtureId : null,
      provider_id: mode === "live" ? providerId : null,
      settings: {
        max_attempts: parsed.max_attempts ?? 100,
        concurrency: parsed.concurrency ?? 2,
        timeout_seconds: parsed.timeout_seconds ?? 60,
        deadline_seconds: parsed.deadline_seconds ?? 600,
        max_retries_per_case: parsed.max_retries_per_case ?? 1,
      },
    };
    const generation = proposalGeneration.current;
    const epoch = ++reviewEpoch.current;
    const controller = new AbortController();
    reviewController.current?.abort();
    reviewController.current = controller;
    reviewInFlight.current = true;
    setReviewing(true);
    setReviewError(undefined);
    try {
      const result = await gateway.execution.runs.preview({
        registrationId: project.id,
        body: { schema_version: 1, request },
        query: { include_request: includeRequest ? "true" : "false" },
        signal: controller.signal,
      });
      if (
        result.data.decision_id !== request.decision_id ||
        result.data.dataset_id !== request.dataset_id ||
        result.data.mode !== request.mode
      )
        throw new Error(
          "The service returned a preview for a different run scope.",
        );
      if (
        generation !== proposalGeneration.current ||
        controller.signal.aborted ||
        project.id !== registrationRef.current ||
        executionRef.current !== gateway.execution
      )
        return;
      setReview(result.data);
      setReviewRequest(request);
      proposalDirtyRef.current = false;
      setProposalDirty(false);
      if (
        startMutation.current?.state.kind === "conflict" ||
        startMutation.current?.state.kind === "failed"
      ) {
        startMutation.current.reset();
        setStartState({ kind: "idle" });
      }
    } catch (cause) {
      if (
        epoch === reviewEpoch.current &&
        generation === proposalGeneration.current &&
        !controller.signal.aborted
      )
        setReviewError(safeMessage(cause));
    } finally {
      if (reviewController.current === controller) {
        reviewController.current = undefined;
        reviewInFlight.current = false;
        setReviewing(false);
      }
    }
  }

  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: proposalDirty,
    isDirtyNow: () =>
      proposalDirtyRef.current ||
      startMutation.current?.state.kind === "submitting" ||
      startMutation.current?.state.kind === "outcome-unknown",
    save: reviewProposal,
    discard: () => {
      setReview(undefined);
      setReviewRequest(undefined);
      proposalDirtyRef.current = false;
      setProposalDirty(false);
    },
    isBlockedNow: () => {
      const state = startMutation.current?.state.kind;
      return state === "submitting" || state === "outcome-unknown";
    },
    blockedMessage:
      startState.kind === "submitting" || startState.kind === "outcome-unknown"
        ? "The start request is still settling. Retry the identical request before leaving."
        : undefined,
  });
  useEffect(
    () => navigation.registerDirtyGuard("run-review", guard),
    [navigation, guard],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoadingOptions(true);
    setOptionError(undefined);
    void (async () => {
      try {
        const caseResult = await gateway.authoring.examples.listCases({
          registrationId: project.id,
          datasetId,
          query: { limit: "500" },
          signal: controller.signal,
        });
        const profileResult = await gateway.authoring.providers.list({
          registrationId: project.id,
          signal: controller.signal,
        });
        const fixtureResult = await gateway.authoring.fixtures.list({
          registrationId: project.id,
          signal: controller.signal,
        });
        const revisionResult = await gateway.authoring.decisions.revisions({
          registrationId: project.id,
          decisionId: decision.id,
          signal: controller.signal,
        });
        if (!active) return;
        setCases(caseResult.data);
        setProfiles(profileResult.data);
        setFixtures(fixtureResult.data);
        setRevisions(revisionResult.data);
        setCaseIds([]);
        const fixture = fixtureResult.data.items.find(
          (item) => item.dataset_id === datasetId,
        );
        if (fixture) setFixtureId(fixture.id);
      } catch (cause) {
        if (active && !controller.signal.aborted)
          setOptionError(safeMessage(cause));
      } finally {
        if (active) setLoadingOptions(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [gateway, project.id, datasetId, decision.id]);

  useEffect(
    () => () => {
      reviewController.current?.abort();
      reviewController.current = undefined;
      reviewInFlight.current = false;
    },
    [],
  );

  async function startRun() {
    if (
      !review ||
      !reviewRequest ||
      startMutation.current?.state.kind !== "idle"
    )
      return;
    const body: StartBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      expected_review_context_hash: review.review_context_hash,
      request: reviewRequest,
    };
    const accepted = await startMutation.current.submit({
      registrationId: project.id,
      body,
    });
    if (accepted) onStarted(accepted.run_id);
  }

  async function retryStart() {
    const accepted = await startMutation.current?.retryOriginal();
    if (accepted) onStarted(accepted.run_id);
  }

  function closeReview() {
    if (
      startState.kind === "submitting" ||
      startState.kind === "outcome-unknown"
    )
      return;
    if (proposalDirtyRef.current) setExitPrompt(true);
    else onClose();
  }

  function submitReview(event: FormEvent) {
    event.preventDefault();
    void reviewProposal();
  }

  const selectedCaseIds = useMemo(() => new Set(caseIds), [caseIds]);

  return (
    <>
      <Modal title="Review a run" onDismiss={closeReview} sheet>
        {exitPrompt ? (
          <div className="modal-body">
            <h3>Save or discard this run proposal?</h3>
            <p>
              Saving obtains a fresh server review. It does not start inference.
            </p>
            <div className="actions">
              <button
                className="primary"
                onClick={() =>
                  void reviewProposal().then(() => setExitPrompt(false))
                }
              >
                Review before leaving
              </button>
              <button
                onClick={() => {
                  setExitPrompt(false);
                  onClose();
                }}
              >
                Discard proposal
              </button>
              <button onClick={() => setExitPrompt(false)}>Keep editing</button>
            </div>
          </div>
        ) : (
          <form className="modal-body" onSubmit={submitReview}>
            <p className="muted">Decision: {decision.name}</p>
            <fieldset
              disabled={
                startState.kind === "submitting" ||
                startState.kind === "outcome-unknown"
              }
            >
              <label className="field">
                Dataset
                <select
                  value={datasetId}
                  onChange={(event) => {
                    setDatasetId(event.currentTarget.value);
                    setFixtureId("");
                    markChanged();
                  }}
                >
                  {project.datasets.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Saved definition
                <select
                  value={revisionId}
                  onChange={(event) => {
                    setRevisionId(event.currentTarget.value);
                    markChanged();
                  }}
                >
                  <option value="">Current draft</option>
                  {revisions?.items.map((item) => (
                    <option
                      key={item.revision.record.id}
                      value={item.revision.record.id}
                    >
                      {item.revision.record.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Case scope
                <select
                  value={split}
                  onChange={(event) => {
                    setSplit(event.currentTarget.value as typeof split);
                    markChanged();
                  }}
                >
                  <option value="all">All eligible cases</option>
                  <option value="development">Development split</option>
                  <option value="calibration">Calibration split</option>
                  <option value="test">Test split</option>
                </select>
              </label>
              {cases && cases.items.length > 0 && (
                <fieldset>
                  <legend>
                    Optional case selection (
                    {caseIds.length === 0
                      ? "all eligible"
                      : `${caseIds.length} selected`}
                    )
                  </legend>
                  <div className="run-case-options">
                    {cases.items.map(({ record }) => (
                      <label key={record.id}>
                        <input
                          type="checkbox"
                          checked={selectedCaseIds.has(record.id)}
                          onChange={(event) => {
                            const checked = event.currentTarget.checked;
                            setCaseIds((current) =>
                              checked
                                ? [...current, record.id]
                                : current.filter((id) => id !== record.id),
                            );
                            markChanged();
                          }}
                        />
                        {record.id}{" "}
                        <span className="muted">{record.split}</span>
                      </label>
                    ))}
                  </div>
                  <p className="muted">
                    Clear every checkbox to request all eligible cases.
                  </p>
                </fieldset>
              )}
              <fieldset>
                <legend>Execution mode</legend>
                <label>
                  <input
                    type="radio"
                    checked={mode === "fixture"}
                    onChange={() => {
                      setMode("fixture");
                      markChanged();
                    }}
                  />{" "}
                  Authored fixture
                </label>
                <label>
                  <input
                    type="radio"
                    checked={mode === "live"}
                    onChange={() => {
                      setMode("live");
                      markChanged();
                    }}
                  />{" "}
                  Live provider
                </label>
              </fieldset>
              {mode === "fixture" ? (
                <label className="field">
                  Fixture set
                  <select
                    value={fixtureId}
                    onChange={(event) => {
                      setFixtureId(event.currentTarget.value);
                      markChanged();
                    }}
                  >
                    <option value="">Choose a fixture set</option>
                    {fixtures?.items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <>
                  <label className="field">
                    Provider profile
                    <select
                      value={providerId}
                      onChange={(event) => {
                        setProviderId(event.currentTarget.value);
                        markChanged();
                      }}
                    >
                      <option value="">Choose a live profile</option>
                      {profiles?.items
                        .filter((item) => item.evidence_mode === "live")
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.id} · {item.adapter} · {item.requested_model}
                          </option>
                        ))}
                    </select>
                  </label>
                  <p className="muted">
                    Live requests may contact a provider and may incur cost. No
                    automatic fallback is used.
                  </p>
                </>
              )}
              <fieldset>
                <legend>Attempt limits</legend>
                {(
                  [
                    [
                      "max_attempts",
                      "Lifetime request cap",
                      1,
                      Number.MAX_SAFE_INTEGER,
                    ],
                    ["concurrency", "Concurrency", 1, 64],
                    ["timeout_seconds", "Timeout seconds", 1, 600],
                    ["deadline_seconds", "Deadline seconds", 1, 86400],
                    [
                      "max_retries_per_case",
                      "Rate/overload retries per case",
                      0,
                      1,
                    ],
                  ] as const
                ).map(([key, label, min, max]) => (
                  <label className="field" key={key}>
                    {label} ({min}–{max})
                    <input
                      inputMode="numeric"
                      value={settings[key]}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setSettings((current) => ({
                          ...current,
                          [key]: value,
                        }));
                        markChanged();
                      }}
                    />
                  </label>
                ))}
                <p className="muted">
                  This cap is shared across all selected cases and retries.
                </p>
              </fieldset>
              <label>
                <input
                  type="checkbox"
                  checked={includeRequest}
                  onChange={(event) => {
                    setIncludeRequest(event.currentTarget.checked);
                    markChanged();
                  }}
                />{" "}
                Reveal sanitized compiled request sources in this review
              </label>
            </fieldset>
            {optionError && <ErrorSummary message={optionError} />}
            {reviewError && <ErrorSummary message={reviewError} />}
            {loadingOptions && (
              <LoadingState>Loading run choices…</LoadingState>
            )}
            <div className="actions">
              <button
                type="submit"
                disabled={
                  loadingOptions ||
                  reviewing ||
                  startState.kind === "submitting" ||
                  startState.kind === "outcome-unknown"
                }
              >
                {reviewing ? "Reviewing…" : "Review run"}
              </button>
              <button
                type="button"
                onClick={closeReview}
                disabled={
                  startState.kind === "submitting" ||
                  startState.kind === "outcome-unknown"
                }
              >
                Close
              </button>
            </div>
            {review && (
              <section
                className="run-review-summary"
                aria-label="Reviewed run context"
              >
                <h3>Server-reviewed context</h3>
                <p>
                  Review hash <code>{review.review_context_hash}</code>
                </p>
                <dl>
                  <dt>Definition</dt>
                  <dd>
                    {review.review_context.definition_source}
                    {review.review_context.revision_id
                      ? ` · ${review.review_context.revision_id}`
                      : ""}
                  </dd>
                  <dt>Definition hash</dt>
                  <dd>
                    <code>{review.review_context.definition_hash}</code>
                  </dd>
                  <dt>Source context</dt>
                  <dd>
                    <code>{review.review_context.source_context_hash}</code>
                  </dd>
                  <dt>Selected cases</dt>
                  <dd>
                    {review.selected_case_ids.join(", ") ||
                      "All eligible cases"}
                  </dd>
                  <dt>Development cases</dt>
                  <dd>
                    {review.review_context.development_case_ids.join(", ") ||
                      "None"}
                  </dd>
                  <dt>Development labels</dt>
                  <dd>{review.review_context.development_label_count}</dd>
                  <dt>Initial requests</dt>
                  <dd>{review.initial_requests}</dd>
                  <dt>Destination / adapter</dt>
                  <dd>
                    {review.review_context.destination} /{" "}
                    {review.review_context.adapter}
                  </dd>
                  <dt>Model / compiler</dt>
                  <dd>
                    {review.review_context.requested_model} /{" "}
                    {review.review_context.compiler_id}{" "}
                    {review.review_context.compiler_version}
                  </dd>
                  <dt>Mode</dt>
                  <dd>
                    {review.mode}; authored fixture runs have no live charge
                    basis.
                  </dd>
                  <dt>Settings</dt>
                  <dd>
                    {review.settings.max_attempts} total requests across the
                    run, concurrency{" "}
                    {review.settings.concurrency},{" "}
                    {review.settings.timeout_seconds}s timeout,{" "}
                    {review.settings.deadline_seconds}s deadline,{" "}
                    {review.settings.max_retries_per_case} retry.
                  </dd>
                </dl>
                {review.review_context.source_records.length > 0 && (
                  <details>
                    <summary>Reviewed source identities</summary>
                    <ul>
                      {review.review_context.source_records.map(
                        (item, index) => (
                          <li
                            key={`${item.collection}-${item.resource_id}-${index}`}
                          >
                            {item.collection} · {item.resource_id} ·{" "}
                            <code>{item.etag}</code> · {item.body_hash}
                          </li>
                        ),
                      )}
                    </ul>
                  </details>
                )}
                <h4>Case review</h4>
                <ul className="run-case-review">
                  {review.case_reviews.map((item) => (
                    <li key={item.case_id}>
                      <strong>{item.case_id}</strong> · input {item.input_hash}{" "}
                      · request {item.request_hash ?? "not compiled"}
                      {item.input_error && (
                        <p className="warning-summary">
                          {item.input_error.code}: {item.input_error.reason}
                        </p>
                      )}
                      {item.request_source !== null && (
                        <pre className="source-editor">
                          {item.request_source}
                        </pre>
                      )}
                      {item.request_source_redacted === true && (
                        <p className="muted">
                          Request source was redacted for display; its request
                          hash remains the original compiled wire hash.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                {review.invalid_cases.length > 0 && (
                  <p className="warning-summary">
                    Some selected inputs were rejected during preview. No
                    requests were dispatched.
                  </p>
                )}
                <p role="status">
                  Dry run only. No model calls or run records are created by
                  review.
                </p>
                {startState.kind === "failed" ||
                startState.kind === "conflict" ? (
                  <ErrorSummary message={startState.message} />
                ) : null}
                {startState.kind === "outcome-unknown" && (
                  <section className="warning-summary" role="status">
                    <p>
                      {startState.message} The original request remains
                      unchanged.
                    </p>
                    <button type="button" onClick={() => void retryStart()}>
                      Retry original start request
                    </button>
                  </section>
                )}
                <div className="actions">
                  <button
                    type="button"
                    className="primary"
                    disabled={
                      startState.kind !== "idle" || reviewing || proposalDirty
                    }
                    onClick={() => void startRun()}
                  >
                    Start reviewed run
                  </button>
                </div>
              </section>
            )}
          </form>
        )}
      </Modal>
      {prompt}
    </>
  );
}

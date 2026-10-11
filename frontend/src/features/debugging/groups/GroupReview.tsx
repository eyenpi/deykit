import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { safeMessage } from "../../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../../api/client";
import { ErrorSummary, LoadingState } from "../../../components/States";
import { Modal } from "../../../components/Modal";
import type { ProjectOverview, WorkspaceGateway } from "../../../workspace/gateway";
import type { WorkspaceNavigation } from "../../../workspace/navigation";
import { useDirtyNavigationGuard } from "../../../workspace/NavigationGuardPrompt";
import { RetainedMutation } from "../../../workspace/mutation-controller";
import type { MutationState } from "../../../workspace/mutation-controller";
import "./groups.css";

type CasePage = ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
type ProviderPage = ApiOperationData<"listProviderProfiles">;
type FixturePage = ApiOperationData<"listFixtureSets">;
type RevisionPage = ApiOperationData<"listDecisionRevisions">;
type RegressionPage = ApiOperationData<"listRegressions">;
type DiagnosticPreview = ApiOperationData<"previewChoiceOrder">;
type CheckPreview = ApiOperationData<"previewRegressionCheck">;
type DiagnosticAccepted = ApiOperationData<"startChoiceOrder">;
type CheckAccepted = ApiOperationData<"startRegressionCheck">;
type GroupAccepted = DiagnosticAccepted | CheckAccepted;
type ChoiceRequest = ApiOperationBody<"previewChoiceOrder">["request"];
type CheckRequest = ApiOperationBody<"previewRegressionCheck">["request"];
type StartChoiceBody = ApiOperationBody<"startChoiceOrder">;
type StartCheckBody = ApiOperationBody<"startRegressionCheck">;

type SettingsText = {
  max_attempts: string;
  concurrency: string;
  timeout_seconds: string;
  deadline_seconds: string;
  max_retries_per_case: string;
};
const DEFAULT_SETTINGS: SettingsText = {
  max_attempts: "100",
  concurrency: "2",
  timeout_seconds: "60",
  deadline_seconds: "600",
  max_retries_per_case: "1",
};

function integerField(value: string, minimum: number, maximum: number) {
  if (!/^(?:0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : null;
}

function option(value: string): string | null {
  return value || null;
}

function parseSigned64Text(value: string): string | undefined {
  const text = value.trim();
  if (!/^-?(?:0|[1-9][0-9]*)$/.test(text)) return undefined;
  try {
    const integer = BigInt(text);
    return integer >= -(1n << 63n) && integer < (1n << 63n) ? text : undefined;
  } catch {
    return undefined;
  }
}

function SettingFields({
  settings,
  onChange,
  disabled,
}: {
  settings: SettingsText;
  onChange: (settings: SettingsText) => void;
  disabled: boolean;
}) {
  const fields = [
    ["max_attempts", "Lifetime group request cap", 1, Number.MAX_SAFE_INTEGER],
    ["concurrency", "Concurrency", 1, 64],
    ["timeout_seconds", "Timeout seconds", 1, 600],
    ["deadline_seconds", "Deadline seconds", 1, 86400],
    ["max_retries_per_case", "Rate/overload retries per case", 0, 1],
  ] as const;
  return (
    <fieldset disabled={disabled}>
      <legend>Shared execution limits</legend>
      {fields.map(([key, label, min, max]) => (
        <label className="field" key={key}>
          {label} ({min}–{max})
          <input
            inputMode="numeric"
            value={settings[key]}
            onChange={(event) =>
              onChange({ ...settings, [key]: event.currentTarget.value })
            }
          />
        </label>
      ))}
      <p className="muted">
        This lifetime request cap is shared by every group member and retry.
      </p>
    </fieldset>
  );
}

function useReferenceOptions(
  gateway: WorkspaceGateway,
  project: ProjectOverview,
  decisionId: string,
  datasetId?: string,
) {
  const [cases, setCases] = useState<CasePage>();
  const [profiles, setProfiles] = useState<ProviderPage>();
  const [fixtures, setFixtures] = useState<FixturePage>();
  const [revisions, setRevisions] = useState<RevisionPage>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const epoch = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const currentEpoch = ++epoch.current;
    setLoading(true);
    setError(undefined);
    setCases(undefined);
    setProfiles(undefined);
    setFixtures(undefined);
    setRevisions(undefined);
    const caseRequest = datasetId
      ? gateway.authoring.examples.listCases({
          registrationId: project.id,
          datasetId,
          query: { limit: "500" },
          signal: controller.signal,
        })
      : Promise.resolve(undefined);
    void Promise.all([
      caseRequest,
      gateway.authoring.providers.list({
        registrationId: project.id,
        signal: controller.signal,
      }),
      gateway.authoring.fixtures.list({
        registrationId: project.id,
        signal: controller.signal,
      }),
      gateway.authoring.decisions.revisions({
        registrationId: project.id,
        decisionId,
        signal: controller.signal,
      }),
    ]).then(
      ([caseResult, profileResult, fixtureResult, revisionResult]) => {
        if (!active || currentEpoch !== epoch.current) return;
        setCases(caseResult?.data);
        setProfiles(profileResult.data);
        setFixtures(fixtureResult.data);
        setRevisions(revisionResult.data);
      },
    ).catch((cause: unknown) => {
      if (active && !controller.signal.aborted && currentEpoch === epoch.current)
        setError(safeMessage(cause));
    }).finally(() => {
      if (active && currentEpoch === epoch.current) setLoading(false);
    });
    return () => {
      active = false;
      controller.abort();
      epoch.current += 1;
    };
  }, [gateway, decisionId, datasetId, project.id]);
  return { cases, profiles, fixtures, revisions, loading, error };
}

export type GroupReviewProps = {
  project: ProjectOverview;
  decision: { id: string; name: string };
  gateway: WorkspaceGateway;
  navigation: WorkspaceNavigation;
  onClose: () => void;
  onStarted: (groupId: string) => void;
};
type ReviewProps = GroupReviewProps;

type Intent =
  | { kind: "diagnostic"; registrationId: string; body: StartChoiceBody; gateway: WorkspaceGateway }
  | { kind: "check"; registrationId: string; body: StartCheckBody; gateway: WorkspaceGateway };

export function GroupReview({
  project,
  decision,
  gateway,
  navigation,
  onClose,
  onStarted,
  kind,
}: GroupReviewProps & { kind: "diagnostic" | "check" }) {
  return kind === "diagnostic" ? (
    <ChoiceOrderReview
      project={project}
      decision={decision}
      gateway={gateway}
      navigation={navigation}
      onClose={onClose}
      onStarted={onStarted}
    />
  ) : (
    <RegressionCheckReview
      project={project}
      decision={decision}
      gateway={gateway}
      navigation={navigation}
      onClose={onClose}
      onStarted={onStarted}
    />
  );
}

function ChoiceOrderReview(props: ReviewProps) {
  const { project, decision, gateway, navigation, onClose, onStarted } = props;
  const [datasetId, setDatasetId] = useState(project.datasets[0]?.id ?? "");
  const [split, setSplit] = useState<"all" | "development" | "calibration" | "test">("all");
  const [mode, setMode] = useState<"fixture" | "live">("fixture");
  const [fixtureId, setFixtureId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [caseIds, setCaseIds] = useState<readonly string[]>([]);
  const [ordersText, setOrdersText] = useState("2");
  const [seedText, setSeedText] = useState("0");
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [preview, setPreview] = useState<DiagnosticPreview>();
  const [previewRequest, setPreviewRequest] = useState<ChoiceRequest>();
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string>();
  const [dirty, setDirty] = useState(false);
  const [exitPrompt, setExitPrompt] = useState(false);
  const generation = useRef(0);
  const reviewController = useRef<AbortController>();
  const mutation = useRef<RetainedMutation<Intent, GroupAccepted>>();
  const scope = `${project.id}:${decision.id}:diagnostic`;
  const scopeRef = useRef(scope);
  const mounted = useRef(true);
  const mutationEpoch = useRef(0);
  const renderEpoch = useRef(0);
  const pendingIntentScope = useRef<string>();
  const callbackScopeToken = useRef<number>();
  const scopeToken = useRef(0);
  const tokenScope = useRef({ scope, gateway });
  if (tokenScope.current.scope !== scope || tokenScope.current.gateway !== gateway) {
    tokenScope.current = { scope, gateway };
    scopeToken.current += 1;
  }
  scopeRef.current = scope;
  const options = useReferenceOptions(gateway, project, decision.id, datasetId);
  const [mutationState, setMutationState] = useState<MutationState<GroupAccepted>>({ kind: "idle" });

  if (!mutation.current) {
    mutation.current = new RetainedMutation(async (intent) => {
      if (intent.kind !== "diagnostic") throw new Error("The group request kind changed.");
      const result = await intent.gateway.debugging.diagnostics.start({
        registrationId: intent.registrationId,
        body: intent.body,
      });
      if (
        result.data.kind !== "choice_order" ||
        result.data.operation_id !== intent.body.operation_id ||
        result.data.mode !== intent.body.request.run.mode ||
        !result.data.group_id
      )
        throw new Error("The service returned an incomplete group receipt.");
      return result.data;
    }, (state) => {
      if (mounted.current && mutationEpoch.current === renderEpoch.current && callbackScopeToken.current === scopeToken.current)
        setMutationState(state);
    });
  }

  const mutationBlocked = mutationState.kind === "submitting" || mutationState.kind === "outcome-unknown";
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: dirty || mutationBlocked,
    isDirtyNow: () => dirtyRef.current || mutation.current?.state.kind === "submitting" || mutation.current?.state.kind === "outcome-unknown",
    save: async () => {
      if (dirtyRef.current) await reviewProposal();
    },
    discard: () => {
      clearReview();
    },
    isBlockedNow: () => mutation.current?.state.kind === "submitting" || mutation.current?.state.kind === "outcome-unknown",
    blockedMessage: mutationBlocked ? "The group request is still settling. Retry the identical request before leaving." : undefined,
  });

  useEffect(() => navigation.registerDirtyGuard(`group-review:${scope}`, guard), [navigation, scope, guard]);
  useEffect(() => {
    mounted.current = true;
    const current = ++renderEpoch.current;
    if (mutation.current && mutation.current.state.kind !== "outcome-unknown" && mutation.current.state.kind !== "submitting") {
      mutation.current.reset();
      setMutationState({ kind: "idle" });
    }
    return () => {
      mounted.current = false;
      renderEpoch.current += 1;
      reviewController.current?.abort();
      reviewController.current = undefined;
      void current;
    };
  }, [scope]);

  const settingsNumber = useMemo(() => ({
    max_attempts: integerField(settings.max_attempts, 1, Number.MAX_SAFE_INTEGER),
    concurrency: integerField(settings.concurrency, 1, 64),
    timeout_seconds: integerField(settings.timeout_seconds, 1, 600),
    deadline_seconds: integerField(settings.deadline_seconds, 1, 86400),
    max_retries_per_case: integerField(settings.max_retries_per_case, 0, 1),
  }), [settings]);
  const selectedCaseIds = useMemo(() => new Set(caseIds), [caseIds]);

  function clearReview() {
    generation.current += 1;
    reviewController.current?.abort();
    reviewController.current = undefined;
    setPreview(undefined);
    setPreviewRequest(undefined);
    setReviewError(undefined);
    setReviewBusy(false);
    setDirty(false);
  }

  function changed() {
    generation.current += 1;
    reviewController.current?.abort();
    reviewController.current = undefined;
    setPreview(undefined);
    setPreviewRequest(undefined);
    setReviewError(undefined);
    setReviewBusy(false);
    setDirty(true);
    if (["failed", "conflict", "committed"].includes(mutation.current?.state.kind ?? "")) {
      mutation.current?.reset();
      setMutationState({ kind: "idle" });
    }
  }

  async function reviewProposal(): Promise<boolean> {
    if (reviewController.current || mutation.current?.state.kind === "submitting" || mutation.current?.state.kind === "outcome-unknown") return false;
    const dataset = project.datasets.find((item) => item.id === datasetId);
    const orders = integerField(ordersText, 1, 4);
    const seed = parseSigned64Text(seedText);
    if (!dataset || !orders || !seed || Object.values(settingsNumber).some((value) => value === null)) {
      setReviewError("Choose a dataset and enter an order count, signed 64-bit seed, and whole-number limits within the displayed ranges.");
      return false;
    }
    if (mode === "fixture" && !options.fixtures?.items.some((item) => item.id === fixtureId && item.decision_id === decision.id && item.dataset_id === dataset.id)) {
      setReviewError("Choose an authored fixture set for this decision and dataset.");
      return false;
    }
    if (mode === "live" && (!providerId || !options.profiles?.items.some((item) => item.id === providerId && item.evidence_mode === "live"))) {
      setReviewError("Choose a live provider profile.");
      return false;
    }
    const request: ChoiceRequest = {
      orders,
      seed,
      run: {
        decision_id: decision.id,
        dataset_id: dataset.id,
        mode,
        split,
        case_ids: caseIds,
        revision_id: option(revisionId),
        fixture_set_id: mode === "fixture" ? fixtureId : null,
        provider_id: mode === "live" ? providerId : null,
        settings: {
          max_attempts: settingsNumber.max_attempts ?? 100,
          concurrency: settingsNumber.concurrency ?? 2,
          timeout_seconds: settingsNumber.timeout_seconds ?? 60,
          deadline_seconds: settingsNumber.deadline_seconds ?? 600,
          max_retries_per_case: settingsNumber.max_retries_per_case ?? 1,
        },
      },
    };
    const requestGeneration = generation.current;
    const currentScope = scope;
    const controller = new AbortController();
    reviewController.current = controller;
    setReviewBusy(true);
    setReviewError(undefined);
    try {
      const result = await gateway.debugging.diagnostics.preview({
        registrationId: project.id,
        body: { schema_version: 1, request },
        signal: controller.signal,
      });
      if (result.data.kind !== "choice_order" || !result.data.dry_run)
        throw new Error("The service returned a preview for a different group kind.");
      if (result.data.members.some((member) => member.preview.decision_id !== decision.id || member.preview.dataset_id !== datasetId || member.preview.mode !== mode))
        throw new Error("The service returned a preview for a different decision, dataset, or execution mode.");
      if (requestGeneration !== generation.current || controller.signal.aborted || scopeRef.current !== currentScope) return;
      setPreview(result.data);
      setPreviewRequest(request);
      setDirty(false);
      return true;
    } catch (cause) {
      if (!controller.signal.aborted && requestGeneration === generation.current) setReviewError(safeMessage(cause));
      return false;
    } finally {
      if (reviewController.current === controller) {
        reviewController.current = undefined;
        setReviewBusy(false);
      }
    }
  }

  async function start() {
    if (!preview || !previewRequest || mutation.current?.state.kind !== "idle") return;
    const body: StartChoiceBody = {
      schema_version: 1,
      operation_id: crypto.randomUUID(),
      expected_review_context_hash: preview.review_context_hash,
      request: previewRequest,
    };
    const intent: Intent = { kind: "diagnostic", registrationId: project.id, body, gateway };
    pendingIntentScope.current = scope;
    callbackScopeToken.current = scopeToken.current;
    mutationEpoch.current = renderEpoch.current;
    const dispatchScopeToken = scopeToken.current;
    const accepted = await mutation.current.submit(intent);
    if (accepted?.kind === "choice_order" && mounted.current && scopeToken.current === dispatchScopeToken && callbackScopeToken.current === dispatchScopeToken && pendingIntentScope.current === scope && scopeRef.current === scope)
      onStarted(accepted.group_id);
  }

  async function retryStart() {
    if (pendingIntentScope.current !== scope) return;
    const dispatchScopeToken = callbackScopeToken.current;
    if (dispatchScopeToken === undefined) return;
    callbackScopeToken.current = dispatchScopeToken;
    mutationEpoch.current = renderEpoch.current;
    const accepted = await mutation.current?.retryOriginal();
    if (accepted?.kind === "choice_order" && mounted.current && scopeToken.current === dispatchScopeToken && callbackScopeToken.current === dispatchScopeToken && pendingIntentScope.current === scope && scopeRef.current === scope)
      onStarted(accepted.group_id);
  }

  function close() {
    if (mutationBlocked) return;
    if (dirty) setExitPrompt(true);
    else onClose();
  }

  return (
    <>
      <Modal title="Review choice order" onDismiss={close} sheet>
        {exitPrompt ? (
          <div className="modal-body">
            <h3>Save or discard this group proposal?</h3>
            <p>Reviewing is a read-only preview. It does not start requests.</p>
            <div className="actions">
              <button className="primary" onClick={() => void reviewProposal().then((reviewed) => { if (reviewed) setExitPrompt(false); })}>Review before leaving</button>
              <button onClick={() => { setExitPrompt(false); clearReview(); onClose(); }}>Discard proposal</button>
              <button onClick={() => setExitPrompt(false)}>Keep editing</button>
            </div>
          </div>
        ) : (
          <form className="modal-body" onSubmit={(event: FormEvent) => { event.preventDefault(); void reviewProposal(); }}>
            <p className="muted">Decision: {decision.name}</p>
            {options.error && <ErrorSummary message={options.error} />}
            {reviewError && <ErrorSummary message={reviewError} />}
            {mutationState.kind === "outcome-unknown" && <ErrorSummary message={mutationState.message} />}
            {(mutationState.kind === "failed" || mutationState.kind === "conflict") && <ErrorSummary message={mutationState.message} />}
            <fieldset disabled={mutationBlocked}>
              <label className="field">Dataset
                <select value={datasetId} onChange={(event) => { setDatasetId(event.currentTarget.value); setCaseIds([]); setFixtureId(""); changed(); }}>
                  {project.datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
                </select>
              </label>
              <label className="field">Saved definition
                <select value={revisionId} onChange={(event) => { setRevisionId(event.currentTarget.value); changed(); }}>
                  <option value="">Current draft</option>
                  {options.revisions?.items.map((item) => <option key={item.revision.record.id} value={item.revision.record.id}>{item.revision.record.id}</option>)}
                </select>
              </label>
              <label className="field">Case scope
                <select value={split} onChange={(event) => { setSplit(event.currentTarget.value as typeof split); changed(); }}>
                  <option value="all">All eligible cases</option><option value="development">Development split</option><option value="calibration">Calibration split</option><option value="test">Test split</option>
                </select>
              </label>
              {options.cases && <fieldset><legend>Optional case selection ({caseIds.length === 0 ? "all eligible" : `${caseIds.length} selected`})</legend>
                <div className="run-case-options">{options.cases.items.map(({ record }) => <label key={record.id}><input type="checkbox" checked={selectedCaseIds.has(record.id)} onChange={(event) => { const checked = event.currentTarget.checked; setCaseIds((current) => checked ? [...current, record.id] : current.filter((id) => id !== record.id)); changed(); }} />{record.id} <span className="muted">{record.split}</span></label>)}</div>
                <p className="muted">Clear every checkbox to select all eligible cases.</p>
              </fieldset>}
              <label className="field">Orders (1–4)<input inputMode="numeric" value={ordersText} onChange={(event) => { setOrdersText(event.currentTarget.value); changed(); }} /></label>
              <label className="field">Seed (signed 64-bit integer text)<input inputMode="numeric" value={seedText} onChange={(event) => { setSeedText(event.currentTarget.value); changed(); }} /></label>
              <fieldset><legend>Execution mode</legend>
                <label><input type="radio" checked={mode === "fixture"} onChange={() => { setMode("fixture"); changed(); }} /> Authored fixture</label>
                <label><input type="radio" checked={mode === "live"} onChange={() => { setMode("live"); changed(); }} /> Live provider</label>
              </fieldset>
              {mode === "fixture" ? <label className="field">Fixture set<select value={fixtureId} onChange={(event) => { setFixtureId(event.currentTarget.value); changed(); }}><option value="">Choose a fixture set</option>{options.fixtures?.items.filter((item) => item.decision_id === decision.id && item.dataset_id === datasetId).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : <><label className="field">Provider profile<select value={providerId} onChange={(event) => { setProviderId(event.currentTarget.value); changed(); }}><option value="">Choose a live profile</option>{options.profiles?.items.filter((item) => item.evidence_mode === "live").map((item) => <option key={item.id} value={item.id}>{item.id} · {item.adapter} · {item.requested_model}</option>)}</select></label><p className="muted">Live group requests may contact a provider and may incur cost. No automatic fallback is used.</p></>}
              <SettingFields settings={settings} onChange={(next) => { setSettings(next); changed(); }} disabled={mutationBlocked} />
            </fieldset>
            {options.loading && <LoadingState>Loading datasets, cases, profiles, fixtures, and revisions…</LoadingState>}
            <div className="actions"><button type="submit" className="primary" disabled={options.loading || reviewBusy || mutationBlocked}>{reviewBusy ? "Reviewing…" : "Review choice order"}</button><button type="button" onClick={close}>Close</button></div>
            {preview && <PreviewSummary preview={preview} kind="diagnostic" />}
            {preview && mutationState.kind === "idle" && <button type="button" className="primary" onClick={() => void start()}>Start reviewed group</button>}
            {mutationState.kind === "outcome-unknown" && <button type="button" disabled={pendingIntentScope.current !== scope} onClick={() => void retryStart()}>Retry original start request</button>}
            {mutationState.kind === "committed" && <p role="status">Group accepted: <code>{mutationState.receipt.group_id}</code></p>}
          </form>
        )}
      </Modal>
      {prompt}
    </>
  );
}

function RegressionCheckReview(props: ReviewProps) {
  const { project, decision, gateway, navigation, onClose, onStarted } = props;
  const [mode, setMode] = useState<"fixture" | "live">("fixture");
  const [fixtureId, setFixtureId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [regressionIds, setRegressionIds] = useState<readonly string[]>([]);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [regressions, setRegressions] = useState<RegressionPage>();
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsError, setOptionsError] = useState<string>();
  const [preview, setPreview] = useState<CheckPreview>();
  const [previewRequest, setPreviewRequest] = useState<CheckRequest>();
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string>();
  const [dirty, setDirty] = useState(false);
  const [exitPrompt, setExitPrompt] = useState(false);
  const generation = useRef(0);
  const reviewController = useRef<AbortController>();
  const mutation = useRef<RetainedMutation<Intent, GroupAccepted>>();
  const scope = `${project.id}:${decision.id}:check`;
  const scopeRef = useRef(scope);
  const mounted = useRef(true);
  const mutationEpoch = useRef(0);
  const renderEpoch = useRef(0);
  const pendingIntentScope = useRef<string>();
  const callbackScopeToken = useRef<number>();
  const scopeToken = useRef(0);
  const tokenScope = useRef({ scope, gateway });
  if (tokenScope.current.scope !== scope || tokenScope.current.gateway !== gateway) {
    tokenScope.current = { scope, gateway };
    scopeToken.current += 1;
  }
  const dirtyRef = useRef(dirty);
  const [mutationState, setMutationState] = useState<MutationState<GroupAccepted>>({ kind: "idle" });
  scopeRef.current = scope;
  dirtyRef.current = dirty;
  const options = useReferenceOptions(gateway, project, decision.id);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setOptionsLoading(true);
    setOptionsError(undefined);
    setRegressions(undefined);
    void gateway.debugging.regressions.list({ registrationId: project.id, decisionId: decision.id, signal: controller.signal }).then((result) => {
      if (!active) return;
      if (result.data.items.some((item) => item.decision_id !== decision.id))
        throw new Error("The service returned a regression from a different decision.");
      setRegressions(result.data);
    }).catch((cause: unknown) => {
      if (active && !controller.signal.aborted) setOptionsError(safeMessage(cause));
    }).finally(() => { if (active) setOptionsLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [gateway, project.id, decision.id]);

  if (!mutation.current) {
    mutation.current = new RetainedMutation(async (intent) => {
      if (intent.kind !== "check") throw new Error("The group request kind changed.");
      const result = await intent.gateway.debugging.checks.start({ registrationId: intent.registrationId, body: intent.body });
      if (
        result.data.kind !== "regression_check" ||
        result.data.operation_id !== intent.body.operation_id ||
        result.data.mode !== intent.body.request.mode ||
        !result.data.group_id
      )
        throw new Error("The service returned an incomplete group receipt.");
      return result.data;
    }, (state) => {
      if (mounted.current && mutationEpoch.current === renderEpoch.current && callbackScopeToken.current === scopeToken.current) setMutationState(state);
    });
  }

  const mutationBlocked = mutationState.kind === "submitting" || mutationState.kind === "outcome-unknown";
  const { guard, prompt } = useDirtyNavigationGuard({
    dirty: dirty || mutationBlocked,
    isDirtyNow: () => dirtyRef.current || mutation.current?.state.kind === "submitting" || mutation.current?.state.kind === "outcome-unknown",
    save: async () => { if (dirtyRef.current) await reviewProposal(); },
    discard: clearReview,
    isBlockedNow: () => mutation.current?.state.kind === "submitting" || mutation.current?.state.kind === "outcome-unknown",
    blockedMessage: mutationBlocked ? "The group request is still settling. Retry the identical request before leaving." : undefined,
  });
  useEffect(() => navigation.registerDirtyGuard(`group-review:${scope}`, guard), [navigation, scope, guard]);
  useEffect(() => {
    mounted.current = true;
    renderEpoch.current += 1;
    if (mutation.current && mutation.current.state.kind !== "outcome-unknown" && mutation.current.state.kind !== "submitting") {
      mutation.current.reset();
      setMutationState({ kind: "idle" });
    }
    return () => {
      mounted.current = false;
      renderEpoch.current += 1;
      reviewController.current?.abort();
      reviewController.current = undefined;
    };
  }, [scope]);

  const settingsNumber = useMemo(() => ({
    max_attempts: integerField(settings.max_attempts, 1, Number.MAX_SAFE_INTEGER),
    concurrency: integerField(settings.concurrency, 1, 64),
    timeout_seconds: integerField(settings.timeout_seconds, 1, 600),
    deadline_seconds: integerField(settings.deadline_seconds, 1, 86400),
    max_retries_per_case: integerField(settings.max_retries_per_case, 0, 1),
  }), [settings]);
  const visibleRegressions = regressions?.items.filter((item) => !item.removed) ?? [];
  const selected = useMemo(() => new Set(regressionIds), [regressionIds]);

  function clearReview() {
    generation.current += 1;
    reviewController.current?.abort();
    reviewController.current = undefined;
    setPreview(undefined);
    setPreviewRequest(undefined);
    setReviewError(undefined);
    setReviewBusy(false);
    setDirty(false);
  }

  function changed() {
    generation.current += 1;
    reviewController.current?.abort();
    reviewController.current = undefined;
    setPreview(undefined);
    setPreviewRequest(undefined);
    setReviewError(undefined);
    setReviewBusy(false);
    setDirty(true);
    if (["failed", "conflict", "committed"].includes(mutation.current?.state.kind ?? "")) {
      mutation.current?.reset();
      setMutationState({ kind: "idle" });
    }
  }

  async function reviewProposal(): Promise<boolean> {
    if (reviewController.current || mutation.current?.state.kind === "submitting" || mutation.current?.state.kind === "outcome-unknown") return false;
    if (regressionIds.length === 0 || regressionIds.some((id) => !visibleRegressions.some((item) => item.regression_id === id && item.executable))) {
      setReviewError("Select one or more currently visible executable regression oracles.");
      return false;
    }
    const selectedOracles = visibleRegressions.filter((item) => regressionIds.includes(item.regression_id));
    const datasetIds = new Set(selectedOracles.map((item) => item.dataset_id));
    if (mode === "fixture" && datasetIds.size !== 1) {
      setReviewError("Fixture checks need selected oracles from one dataset so one authored fixture set can cover the frozen inputs.");
      return false;
    }
    if (mode === "fixture" && !options.fixtures?.items.some((item) => item.id === fixtureId && item.decision_id === decision.id && item.dataset_id === [...datasetIds][0])) { setReviewError("Choose an authored fixture set for the selected oracle dataset."); return false; }
    if (mode === "live" && (!providerId || !options.profiles?.items.some((item) => item.id === providerId && item.evidence_mode === "live"))) { setReviewError("Choose a live provider profile."); return false; }
    if (Object.values(settingsNumber).some((value) => value === null)) { setReviewError("Enter whole-number limits within the displayed ranges."); return false; }
    const request: CheckRequest = {
      decision_id: decision.id,
      mode,
      fixture_set_id: mode === "fixture" ? fixtureId : null,
      provider_id: mode === "live" ? providerId : null,
      revision_id: option(revisionId),
      regression_ids: regressionIds,
      settings: {
        max_attempts: settingsNumber.max_attempts ?? 100,
        concurrency: settingsNumber.concurrency ?? 2,
        timeout_seconds: settingsNumber.timeout_seconds ?? 60,
        deadline_seconds: settingsNumber.deadline_seconds ?? 600,
        max_retries_per_case: settingsNumber.max_retries_per_case ?? 1,
      },
    };
    const requestGeneration = generation.current;
    const currentScope = scope;
    const controller = new AbortController();
    reviewController.current = controller;
    setReviewBusy(true);
    setReviewError(undefined);
    try {
      const result = await gateway.debugging.checks.preview({ registrationId: project.id, body: { schema_version: 1, request }, signal: controller.signal });
      if (result.data.kind !== "regression_check" || !result.data.dry_run) throw new Error("The service returned a preview for a different group kind.");
      if (result.data.members.some((member) => member.preview.decision_id !== decision.id || member.preview.mode !== mode || (mode === "fixture" && !datasetIds.has(member.preview.dataset_id)))) throw new Error("The service returned a preview outside the selected oracle context.");
      if (requestGeneration !== generation.current || controller.signal.aborted || scopeRef.current !== currentScope) return;
      setPreview(result.data);
      setPreviewRequest(request);
      setDirty(false);
      return true;
    } catch (cause) {
      if (!controller.signal.aborted && requestGeneration === generation.current) setReviewError(safeMessage(cause));
      return false;
    } finally {
      if (reviewController.current === controller) { reviewController.current = undefined; setReviewBusy(false); }
    }
  }

  async function start() {
    if (!preview || !previewRequest || mutation.current?.state.kind !== "idle") return;
    const body: StartCheckBody = { schema_version: 1, operation_id: crypto.randomUUID(), expected_review_context_hash: preview.review_context_hash, request: previewRequest };
    const intent: Intent = { kind: "check", registrationId: project.id, body, gateway };
    pendingIntentScope.current = scope;
    callbackScopeToken.current = scopeToken.current;
    mutationEpoch.current = renderEpoch.current;
    const dispatchScopeToken = scopeToken.current;
    const accepted = await mutation.current.submit(intent);
    if (accepted?.kind === "regression_check" && mounted.current && scopeToken.current === dispatchScopeToken && callbackScopeToken.current === dispatchScopeToken && pendingIntentScope.current === scope && scopeRef.current === scope) onStarted(accepted.group_id);
  }

  async function retryStart() {
    if (pendingIntentScope.current !== scope) return;
    const dispatchScopeToken = callbackScopeToken.current;
    if (dispatchScopeToken === undefined) return;
    callbackScopeToken.current = dispatchScopeToken;
    mutationEpoch.current = renderEpoch.current;
    const accepted = await mutation.current?.retryOriginal();
    if (accepted?.kind === "regression_check" && mounted.current && scopeToken.current === dispatchScopeToken && callbackScopeToken.current === dispatchScopeToken && pendingIntentScope.current === scope && scopeRef.current === scope) onStarted(accepted.group_id);
  }

  function close() { if (mutationBlocked) return; if (dirty) setExitPrompt(true); else onClose(); }

  return (
    <>
      <Modal title="Review regression check" onDismiss={close} sheet>
        {exitPrompt ? <div className="modal-body"><h3>Save or discard this group proposal?</h3><p>Reviewing is a read-only preview. It does not start requests.</p><div className="actions"><button className="primary" onClick={() => void reviewProposal().then((reviewed) => { if (reviewed) setExitPrompt(false); })}>Review before leaving</button><button onClick={() => { setExitPrompt(false); clearReview(); onClose(); }}>Discard proposal</button><button onClick={() => setExitPrompt(false)}>Keep editing</button></div></div> : (
          <form className="modal-body" onSubmit={(event: FormEvent) => { event.preventDefault(); void reviewProposal(); }}>
            <p className="muted">Decision: {decision.name}</p>
            {optionsError && <ErrorSummary message={optionsError} />}{options.error && <ErrorSummary message={options.error} />}{reviewError && <ErrorSummary message={reviewError} />}{mutationState.kind === "outcome-unknown" && <ErrorSummary message={mutationState.message} />}{(mutationState.kind === "failed" || mutationState.kind === "conflict") && <ErrorSummary message={mutationState.message} />}
            <fieldset disabled={mutationBlocked}>
              <label className="field">Saved definition<select value={revisionId} onChange={(event) => { setRevisionId(event.currentTarget.value); changed(); }}><option value="">Current draft</option>{options.revisions?.items.map((item) => <option key={item.revision.record.id} value={item.revision.record.id}>{item.revision.record.id}</option>)}</select></label>
              <fieldset><legend>Currently visible regression oracles</legend>{visibleRegressions.length === 0 ? <p className="muted">No visible regression oracles are available.</p> : <div className="run-case-options">{visibleRegressions.map((item) => <label key={item.regression_id}><input type="checkbox" disabled={!item.executable || mutationBlocked} checked={selected.has(item.regression_id)} onChange={(event) => { const checked = event.currentTarget.checked; setRegressionIds((current) => checked ? [...current, item.regression_id] : current.filter((id) => id !== item.regression_id)); setFixtureId(""); changed(); }} />{item.case_id} · {item.regression_id} <span className="muted">{item.executable ? `${item.provenance} · ${item.original_split}` : item.unavailable_reason ?? "not executable"}</span><br /><span>{item.reason}</span><br /><span className="muted">Frozen input <code>{item.input_hash}</code> · source result <code>{item.source_result_snapshot_id}</code></span></label>)}</div>}</fieldset>
              <fieldset><legend>Execution mode</legend><label><input type="radio" checked={mode === "fixture"} onChange={() => { setMode("fixture"); changed(); }} /> Authored fixture</label><label><input type="radio" checked={mode === "live"} onChange={() => { setMode("live"); changed(); }} /> Live provider</label></fieldset>
              {mode === "fixture" ? <label className="field">Fixture set<select value={fixtureId} onChange={(event) => { setFixtureId(event.currentTarget.value); changed(); }}><option value="">Choose a fixture set</option>{options.fixtures?.items.filter((item) => item.decision_id === decision.id && (datasetIds.size === 0 || item.dataset_id === [...datasetIds][0])).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.dataset_id}</option>)}</select></label> : <><label className="field">Provider profile<select value={providerId} onChange={(event) => { setProviderId(event.currentTarget.value); changed(); }}><option value="">Choose a live profile</option>{options.profiles?.items.filter((item) => item.evidence_mode === "live").map((item) => <option key={item.id} value={item.id}>{item.id} · {item.adapter} · {item.requested_model}</option>)}</select></label><p className="muted">Live group requests may contact a provider and may incur cost. No automatic fallback is used.</p></>}
              <SettingFields settings={settings} onChange={(next) => { setSettings(next); changed(); }} disabled={mutationBlocked} />
            </fieldset>
            {optionsLoading && <LoadingState>Loading currently visible regression oracles…</LoadingState>}{options.loading && <LoadingState>Loading profiles, fixtures, and revisions…</LoadingState>}
            <div className="actions"><button type="submit" className="primary" disabled={optionsLoading || options.loading || reviewBusy || mutationBlocked}>{reviewBusy ? "Reviewing…" : "Review regression check"}</button><button type="button" onClick={close}>Close</button></div>
            {preview && <PreviewSummary preview={preview} kind="check" />}
            {preview && mutationState.kind === "idle" && <button type="button" className="primary" onClick={() => void start()}>Start reviewed group</button>}
            {mutationState.kind === "outcome-unknown" && <button type="button" disabled={pendingIntentScope.current !== scope} onClick={() => void retryStart()}>Retry original start request</button>}
            {mutationState.kind === "committed" && <p role="status">Group accepted: <code>{mutationState.receipt.group_id}</code></p>}
          </form>
        )}
      </Modal>
      {prompt}
    </>
  );
}

function PreviewSummary({
  preview,
  kind,
}: {
  preview: DiagnosticPreview | CheckPreview;
  kind: "diagnostic" | "check";
}) {
  return (
    <section className="run-review-summary" aria-label="Reviewed group context">
      <h3>Reviewed group context</h3>
      <dl><dt>Kind</dt><dd>{preview.kind}</dd><dt>Independent cases</dt><dd>{preview.independent_case_count}</dd><dt>Expanded initial requests</dt><dd>{preview.initial_requests}</dd><dt>Lifetime attempt limit</dt><dd>{preview.attempt_limit}</dd><dt>Deadline seconds</dt><dd>{preview.deadline_seconds}</dd>{preview.algorithm && <><dt>Order algorithm</dt><dd>{preview.algorithm}</dd></>}{preview.seed !== null && <><dt>Seed</dt><dd><code>{preview.seed}</code></dd></>}{kind === "check" && <><dt>Oracle count</dt><dd>{preview.members.length}</dd></>}</dl>
      <ol className="run-case-review">{preview.members.map((member, index) => <li key={`${member.identity.run_id ?? "preview"}-${index}`}><strong>Member {index + 1}</strong>{member.identity.option_order && <p>Actual option order: <code>{member.identity.option_order.join(" → ")}</code></p>}<p>Run id: <code>{member.identity.run_id ?? "assigned on start"}</code></p><p>Decision {member.preview.decision_id} · dataset {member.preview.dataset_id} · model {member.preview.requested_model} · mode {member.preview.mode}</p><p>Fixture {member.preview.fixture_set_id ?? "none"} · provider {member.preview.provider_id ?? "none"}</p><p>Selected cases {member.preview.selected_case_ids.length} · requests {member.preview.initial_requests}</p><p>Limits: max attempts {member.preview.settings.max_attempts} · concurrency {member.preview.settings.concurrency} · timeout {member.preview.settings.timeout_seconds}s · deadline {member.preview.settings.deadline_seconds}s · retries per case {member.preview.settings.max_retries_per_case}</p>{member.identity.requests.length > 0 && <ul>{member.identity.requests.map((request) => <li key={request.case_id}>Case <code>{request.case_id}</code> · input <code>{request.input_hash}</code> · request <code>{request.request_hash ?? "unavailable"}</code> · compiler {request.compiler ?? "unavailable"} {request.compiler_version ?? ""}</li>)}</ul>}</li>)}</ol>
      <p className="muted">This preview is advisory and read-only. The start request is checked against this exact review context.</p>
    </section>
  );
}

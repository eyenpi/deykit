import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { ErrorSummary, EmptyState, LoadingState } from "../../components/States";
import type { ProjectOverview, ProviderAuthoringOperations } from "../../workspace/gateway";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";

type ProviderPageData = ApiOperationData<"listProviderProfiles">;
type ProviderProfile = ApiOperationData<"readProviderProfile">;
type CredentialStatus = ApiOperationData<"providerCredentialStatus">;
type ProviderMutation = ApiOperationData<"configureProviderProfile">;
type ModelList = ApiOperationData<"listProviderModels">;
type OSCredentialMutation = ApiOperationData<"setOSStoreCredential">;

type SavedProviderRequest =
  | { kind: "configure"; profileId: string; body: ApiOperationBody<"configureProviderProfile"> }
  | { kind: "environment"; profileId: string; body: ApiOperationBody<"attachEnvironmentCredential"> }
  | { kind: "forget"; profileId: string; body: ApiOperationBody<"forgetProviderCredential"> };

export function ProviderPage({
  project,
  operations,
  navigation,
  initialProfileId,
  onProfileChange,
}: {
  project: ProjectOverview;
  operations: ProviderAuthoringOperations;
  navigation: WorkspaceNavigation;
  initialProfileId?: string;
  onProfileChange: (profileId?: string) => void;
}) {
  const [page, setPage] = useState<ProviderPageData>();
  const [profileCursor, setProfileCursor] = useState<string>();
  const [profile, setProfile] = useState<ProviderProfile>();
  const [credential, setCredential] = useState<CredentialStatus>();
  const [models, setModels] = useState<ModelList>();
  const [profileId, setProfileId] = useState(initialProfileId ?? "");
  const profileIdRef = useRef(profileId);
  profileIdRef.current = profileId;
  const [adapter, setAdapter] = useState("jev");
  const [requestedModel, setRequestedModel] = useState("");
  const [destination, setDestination] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [environmentName, setEnvironmentName] = useState("");
  const [secret, setSecret] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("20");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [mutationState, setMutationState] = useState<MutationState<ProviderMutation>>({ kind: "idle" });
  const [secretMutationState, setSecretMutationState] = useState<MutationState<OSCredentialMutation>>({ kind: "idle" });
  const [creatingProfile, setCreatingProfile] = useState(false);
  const mutation = useRef<RetainedMutation<SavedProviderRequest, ProviderMutation>>();
  const secretMutation = useRef<RetainedMutation<{
    registrationId: string;
    profileId: string;
    body: ApiOperationBody<"setOSStoreCredential">;
  }, OSCredentialMutation>>();
  const actionLock = useRef(false);
  const activeProfileId = profile?.id ?? profileId;

  useEffect(() => {
    mutation.current = new RetainedMutation(async (request) => {
      const base = { registrationId: project.id, profileId: request.profileId, body: request.body };
      if (request.kind === "configure") return (await operations.configure(base)).data;
      if (request.kind === "environment") return (await operations.attachEnvironment(base)).data;
      return (await operations.forgetCredential(base)).data;
    }, setMutationState);
    secretMutation.current = new RetainedMutation(async (request) => {
      return (await operations.setOSCredential(request)).data;
    }, setSecretMutationState);
  }, [operations, project.id]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(undefined);
    void operations.list({ registrationId: project.id, query: { limit: "100" }, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setPage(result.data);
        setProfileCursor(result.data.next_cursor ?? undefined);
        if (!profileIdRef.current) {
          const initial = result.data.items.find((item) => item.id === initialProfileId) ?? result.data.items[0];
          if (initial) {
            setProfileId(initial.id);
            onProfileChange(initial.id);
          }
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(safeMessage(cause));
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [initialProfileId, onProfileChange, operations, project.id]);

  useEffect(() => {
    if (!profileId || creatingProfile) {
      setProfile(undefined);
      setCredential(undefined);
      return;
    }
    const controller = new AbortController();
    setError(undefined);
    void Promise.all([
      operations.read({ registrationId: project.id, profileId, signal: controller.signal }),
      operations.credentialStatus({ registrationId: project.id, profileId, signal: controller.signal }),
    ]).then(([profileResult, credentialResult]) => {
      if (controller.signal.aborted) return;
      setProfile(profileResult.data);
      setCredential(credentialResult.data);
      setAdapter(profileResult.data.adapter);
      setRequestedModel(profileResult.data.requested_model);
      setDestination(profileResult.data.destination);
      setCredentialRef("");
      setEnvironmentName("");
      setSecret("");
      setModels(undefined);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(safeMessage(cause));
    });
    return () => controller.abort();
  }, [creatingProfile, operations, profileId, project.id]);

  async function refreshProfile() {
    if (!profileId) return;
    const [profileResult, credentialResult, listResult] = await Promise.all([
      operations.read({ registrationId: project.id, profileId }),
      operations.credentialStatus({ registrationId: project.id, profileId }),
      operations.list({ registrationId: project.id, query: { limit: "100" } }),
    ]);
    setProfile(profileResult.data);
    setCredential(credentialResult.data);
    setPage(listResult.data);
    setProfileCursor(listResult.data.next_cursor ?? undefined);
  }

  async function loadMoreProfiles() {
    if (!profileCursor || busy) return;
    setBusy(true);
    try {
      const result = await operations.list({ registrationId: project.id, query: { cursor: profileCursor, limit: "100" } });
      setPage((current) => current ? { ...current, items: [...current.items, ...result.data.items], next_cursor: result.data.next_cursor } : result.data);
      setProfileCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function requestFor(request: SavedProviderRequest): Promise<boolean> {
    if (!mutation.current || actionLock.current || secretMutation.current?.state.kind === "outcome-unknown") return false;
    actionLock.current = true;
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    try {
      const result = await mutation.current.submit(request);
      if (result) {
        await refreshProfile();
        setNotice("Provider configuration saved.");
        mutation.current?.reset();
        setMutationState({ kind: "idle" });
        setEnvironmentName("");
        return true;
      }
      return false;
    } catch (cause) {
      setError(safeMessage(cause));
      return false;
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }

  function configure(): Promise<boolean> {
    if (!profileId || !adapter || !requestedModel || !destination) return Promise.resolve(false);
    return requestFor({
      kind: "configure",
      profileId,
      body: {
        schema_version: 1,
        profile_id: profileId,
        adapter,
        requested_model: requestedModel,
        destination,
        credential_ref: credentialRef || null,
        expected_etag: profile?.etag ?? null,
        operation_id: crypto.randomUUID(),
      },
    });
  }

  function attachEnvironment(): Promise<boolean> {
    if (!profile || !environmentName) return Promise.resolve(false);
    return requestFor({
      kind: "environment",
      profileId: profile.id,
      body: {
        schema_version: 1,
        environment_name: environmentName,
        expected_etag: profile.etag,
        operation_id: crypto.randomUUID(),
      },
    });
  }

  function forgetCredential(): Promise<boolean> {
    if (!profile) return Promise.resolve(false);
    return requestFor({
      kind: "forget",
      profileId: profile.id,
      body: { schema_version: 1, expected_etag: profile.etag, operation_id: crypto.randomUUID() },
    });
  }

  async function setOSCredential() {
    const retryingUnknown = secretMutation.current?.state.kind === "outcome-unknown";
    if (!profile || (!secret && !retryingUnknown) || actionLock.current || !secretMutation.current) return;
    actionLock.current = true;
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    const credentialValue = secret;
    setSecret("");
    try {
      const result = retryingUnknown
        ? await secretMutation.current.retryOriginal()
        : await secretMutation.current.submit({
            registrationId: project.id,
            profileId: profile.id,
            body: {
              schema_version: 1,
              credential_value: credentialValue,
              expected_etag: profile.etag,
              operation_id: crypto.randomUUID(),
            },
          });
      if (result) {
        secretMutation.current.reset();
        setNotice("Credential stored in the operating system credential store.");
        try {
          await refreshProfile();
        } catch (cause) {
          setError(`The credential was stored, but its status could not be refreshed: ${safeMessage(cause)}`);
        }
      } else if (secretMutation.current.state.kind === "outcome-unknown") {
        setError("The credential store outcome is unknown. Retry the same request or review credential status before entering another value.");
      } else {
        secretMutation.current.reset();
        setNotice("Secure credential storage failed. You can attach an environment variable reference.");
      }
    } catch (cause) {
      setError(safeMessage(cause));
      if (secretMutation.current.state.kind !== "outcome-unknown") {
        secretMutation.current.reset();
        setNotice("Secure credential storage failed. You can attach an environment variable reference.");
      }
    } finally {
      setSecret("");
      actionLock.current = false;
      setBusy(false);
    }
  }

  async function listModels() {
    if (!profile || busy) return;
    const timeout = Number(timeoutSeconds);
    if (!Number.isSafeInteger(timeout) || timeout < 1 || timeout > 600) {
      setError("Timeout must be a whole number from 1 to 600 seconds.");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const result = await operations.listModels({
        registrationId: project.id,
        profileId: profile.id,
        query: { timeout_seconds: timeoutSeconds },
        body: { schema_version: 1 },
      });
      setModels(result.data);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function createProfile(): Promise<boolean> {
    if (!profileId || profile || !adapter || !requestedModel || !destination) return false;
    const created = await configure();
    if (created) {
      setCreatingProfile(false);
      onProfileChange(profileId);
    }
    return created;
  }

  const configurationDirty = profile
    ? adapter !== profile.adapter || requestedModel !== profile.requested_model || destination !== profile.destination || credentialRef !== ""
    : creatingProfile && (adapter !== "jev" || !!requestedModel || !!destination || !!credentialRef);
  const dirtyGuard = useDirtyNavigationGuard({
    dirty: configurationDirty || !!environmentName || !!secret || secretMutationState.kind === "outcome-unknown",
    save: async () => {
      if (secretMutationState.kind === "outcome-unknown")
        throw new Error("Retry the same credential request before leaving this provider profile.");
      if (secret) throw new Error("Store the credential explicitly or discard the password field before leaving.");
      if (configurationDirty && !(await (profile ? configure() : createProfile())))
        throw new Error("The provider configuration was not saved. Your entered values are still available.");
      if (environmentName && !(await attachEnvironment()))
        throw new Error("The environment reference was not saved. Review the current profile before continuing.");
    },
    discard: () => {
      if (profile) {
        setAdapter(profile.adapter);
        setRequestedModel(profile.requested_model);
        setDestination(profile.destination);
      } else {
        setCreatingProfile(false);
        setProfileId("");
      }
      setCredentialRef("");
      setEnvironmentName("");
      setSecret("");
    },
  });
  useEffect(() => navigation.registerDirtyGuard(`providers:${project.id}:${profileId || "new"}`, dirtyGuard.guard), [dirtyGuard.guard, navigation, profileId, project.id]);

  async function chooseProfile(nextId?: string) {
    if (secretMutation.current?.state.kind === "outcome-unknown") {
      setError("Retry the same credential request before changing profiles.");
      return;
    }
    const allowed = await dirtyGuard.guard({ kind: "providers", registrationId: project.id });
    if (!allowed) return;
    mutation.current?.reset();
    setMutationState({ kind: "idle" });
    setCreatingProfile(false);
    setProfileId(nextId ?? "");
    onProfileChange(nextId);
  }

  async function beginProfileCreation() {
    if (secretMutation.current?.state.kind === "outcome-unknown") {
      setError("Retry the same credential request before adding another profile.");
      return;
    }
    const allowed = await dirtyGuard.guard({ kind: "providers", registrationId: project.id });
    if (!allowed) return;
    const id = `provider-${crypto.randomUUID()}`;
    mutation.current?.reset();
    setMutationState({ kind: "idle" });
    setCreatingProfile(true);
    setProfile(undefined);
    setProfileId(id);
    onProfileChange(id);
    setAdapter("jev");
    setRequestedModel("");
    setDestination("");
    setCredentialRef("");
  }

  const mutationError = mutationState.kind === "conflict" || mutationState.kind === "failed" || mutationState.kind === "outcome-unknown" ? mutationState.message : undefined;
  return (
    <>
    <article className="document provider-page">
      <header className="page-heading-row"><div><h1>Providers</h1><p className="muted">Configuration checks and model listing do not run inference.</p></div><button type="button" disabled={secretMutationState.kind === "outcome-unknown"} onClick={() => void beginProfileCreation()}>Add provider profile</button></header>
      {loading ? <LoadingState>Loading provider profiles…</LoadingState> : error && <ErrorSummary message={error} />}
      {mutationError && <ErrorSummary message={mutationError} />}
      {notice && <p role="status" className="save-status">{notice}</p>}
      <div className="provider-layout">
        <section aria-labelledby="provider-list-heading">
          <h2 id="provider-list-heading">Profiles</h2>
          {page?.items.length ? <ul className="provider-list">{page.items.map((item) => <li key={item.id}><button type="button" disabled={secretMutationState.kind === "outcome-unknown"} aria-current={item.id === profileId ? "true" : undefined} onClick={() => void chooseProfile(item.id)}>{item.id}</button><span className="muted">{item.requested_model} · {item.evidence_mode}</span></li>)}</ul> : !profileId ? <EmptyState title="No provider profiles">Add a profile to configure a model adapter.</EmptyState> : null}
          {profileCursor && <button type="button" disabled={busy} onClick={() => void loadMoreProfiles()}>Load more profiles</button>}
        </section>
        <section className="provider-editor" aria-labelledby="provider-editor-heading">
          <h2 id="provider-editor-heading">{profile ? profile.id : profileId ? "New profile" : "Select a profile"}</h2>
          {profileId && (
            <>
              <div className="field"><label htmlFor="provider-id">Profile ID</label><input id="provider-id" value={profileId} readOnly /></div>
              <div className="field"><label htmlFor="provider-adapter">Adapter</label><select id="provider-adapter" value={adapter} disabled={busy} onChange={(event) => setAdapter(event.target.value)}><option value="jev">Jev</option><option value="fixture">Authored fixture</option></select></div>
              <div className="field"><label htmlFor="provider-model">Requested model ID</label><input id="provider-model" value={requestedModel} disabled={busy} onChange={(event) => setRequestedModel(event.target.value)} /></div>
              <div className="field"><label htmlFor="provider-destination">Destination</label><input id="provider-destination" value={destination} disabled={busy} onChange={(event) => setDestination(event.target.value)} /></div>
              <div className="field"><label htmlFor="provider-credential-ref">Credential reference (non-secret)</label><input id="provider-credential-ref" value={credentialRef} disabled={busy} onChange={(event) => setCredentialRef(event.target.value)} /></div>
              <button type="button" className="primary" disabled={busy || secretMutationState.kind === "outcome-unknown" || !adapter || !requestedModel || !destination || mutationState.kind === "outcome-unknown"} onClick={() => void (profile ? configure() : createProfile())}>{busy ? "Saving…" : "Save profile"}</button>
              {mutationState.kind === "outcome-unknown" && <button type="button" onClick={() => void mutation.current?.retryOriginal().then(async (result) => { if (result) { await refreshProfile(); mutation.current?.reset(); setMutationState({ kind: "idle" }); } })}>Retry the same configuration</button>}
              {(mutationState.kind === "conflict" || mutationState.kind === "failed") && <button type="button" onClick={() => void refreshProfile().then(() => { mutation.current?.reset(); setMutationState({ kind: "idle" }); }).catch((cause: unknown) => setError(safeMessage(cause)))}>Review current profile</button>}
              {profile && <section className="section credential-status"><h3>Credential status</h3><p role="status">{credential?.configured ? "Configured" : "Not configured"} · {credential?.available ? "Available" : "Unavailable"}{credential?.kind ? ` · ${credential.kind}` : ""}</p><p className="muted">The secret value is never returned to the browser.</p></section>}
              {profile && (
                <section className="section credential-controls">
                  <h3>Credentials</h3>
                  <label htmlFor="environment-name">Environment variable name</label>
                  <input id="environment-name" autoComplete="off" value={environmentName} disabled={busy} onChange={(event) => setEnvironmentName(event.target.value)} />
                  <button type="button" disabled={busy || secretMutationState.kind === "outcome-unknown" || !environmentName} onClick={() => void attachEnvironment()}>Attach environment reference</button>
                  <label htmlFor="provider-secret">Store a credential in the operating system</label>
                  <input id="provider-secret" type="password" autoComplete="new-password" value={secret} disabled={busy} onChange={(event) => setSecret(event.target.value)} />
                  <button type="button" disabled={busy || !secret} onClick={() => void setOSCredential()}>{busy ? "Storing…" : "Store credential"}</button>
                  {secretMutationState.kind === "outcome-unknown" && <button type="button" disabled={busy} onClick={() => void setOSCredential()}>Retry the same credential request</button>}
                  <button type="button" disabled={busy || secretMutationState.kind === "outcome-unknown" || !credential?.configured} onClick={() => void forgetCredential()}>Forget credential</button>
                </section>
              )}
              {profile && <section className="section model-listing"><h3>Supported model IDs</h3><p>Explicit network check · 0 inference calls.</p><label htmlFor="model-timeout">Timeout in seconds</label><input id="model-timeout" inputMode="numeric" value={timeoutSeconds} disabled={busy} onChange={(event) => setTimeoutSeconds(event.target.value)} /><button type="button" disabled={busy} onClick={() => void listModels()}>{busy ? "Checking…" : "Refresh model list"}</button>{models && <><p role="status">{models.models.length} models returned · {models.network_check ? "network checked" : "not checked"} · {models.inference_calls} inference calls</p><ul>{models.models.map((item) => <li key={item.id}><code>{item.id}</code> {item.name}</li>)}</ul></>}</section>}
            </>
          )}
        </section>
      </div>
    </article>
    {dirtyGuard.prompt}
    </>
  );
}

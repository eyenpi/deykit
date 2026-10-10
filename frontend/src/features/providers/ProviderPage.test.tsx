import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationBody } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { ProviderAuthoringOperations, ProjectOverview } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { ProviderPage } from "./ProviderPage";

const project: ProjectOverview = {
  id: "registered-test",
  name: "Provider test",
  path: "/tmp/provider-test",
  decisions: [],
  datasets: [],
  warnings: [],
};

const profile = {
  schema_version: 1 as const,
  id: "profile-test",
  adapter: "jev",
  requested_model: "jev-latest",
  destination: "https://api.typesafe.ai/v1/systemone",
  etag: "profile-e0",
  compiler_id: "jev-choice",
  compiler_version: "1",
  input_kinds: ["text"] as const,
  question_kind: "choice" as const,
  max_options: 8,
  evidence_mode: "live" as const,
  credential_configured: false,
  credential_kind: null,
};

function providerOperations(
  overrides: Partial<ProviderAuthoringOperations>,
): ProviderAuthoringOperations {
  return { ...disconnectedWorkspace.authoring.providers, ...overrides };
}

afterEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

it("keeps an OS credential mounted only for its request and never calls model listing", async () => {
  const secret = "synthetic-m10-credential-never-a-provider-key";
  const setOSCredential = vi.fn(async () => {
    throw new ApiError("preflight_failed", "Secure storage is unavailable.", 422);
  });
  const listModels = vi.fn(async () => {
    throw new Error("Model listing should not run in this test.");
  });
  const operations = providerOperations({
    list: async () => ({ data: { schema_version: 1, items: [profile], total: "1", next_cursor: null }, warnings: [] }),
    read: async () => ({ data: profile, warnings: [] }),
    credentialStatus: async () => ({ data: { schema_version: 1, profile_id: profile.id, configured: false, available: false, kind: null }, warnings: [] }),
    setOSCredential,
    listModels,
  });
  const navigation = new WorkspaceNavigation(window);
  const user = userEvent.setup();
  const { unmount } = render(
    <ProviderPage
      project={project}
      operations={operations}
      navigation={navigation}
      initialProfileId={profile.id}
      onProfileChange={() => undefined}
    />,
  );

  const password = await screen.findByLabelText("Store a credential in the operating system");
  await user.type(password, secret);
  await user.click(screen.getByRole("button", { name: "Store credential" }));
  await screen.findByText("Secure credential storage failed. You can attach an environment variable reference.");
  expect(setOSCredential).toHaveBeenCalledWith(expect.objectContaining({
    registrationId: project.id,
    profileId: profile.id,
    body: expect.objectContaining({ credential_value: secret, expected_etag: profile.etag }),
  }));
  expect((password as HTMLInputElement).value).toBe("");
  expect(document.body.textContent).not.toContain(secret);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
  expect(window.location.href).not.toContain(secret);
  expect(screen.getByText("Explicit network check · 0 inference calls.")).toBeTruthy();
  expect(listModels).not.toHaveBeenCalled();

  unmount();
  navigation.dispose();
});

it("creates a provider profile using the displayed supported default adapter", async () => {
  const generatedId = "new-provider-id";
  const expectedProfileId = `provider-${generatedId}`;
  vi.stubGlobal("crypto", { randomUUID: () => generatedId });
  let configuredBody: ApiOperationBody<"configureProviderProfile"> | undefined;
  const operations = providerOperations({
    list: async () => ({ data: { schema_version: 1, items: [], total: "0", next_cursor: null }, warnings: [] }),
    read: async ({ profileId }) => ({
      data: { ...profile, id: profileId }, warnings: [],
    }),
    credentialStatus: async ({ profileId }) => ({
      data: { schema_version: 1, profile_id: profileId, configured: false, available: false, kind: null },
      warnings: [],
    }),
    configure: async ({ body }) => {
      configuredBody = body;
      return {
        data: {
          schema_version: 1,
          operation_id: body.operation_id,
          profile: {
            ...profile,
            id: body.profile_id,
            adapter: body.adapter,
            requested_model: body.requested_model,
            destination: body.destination,
          },
          replayed: false,
        },
        warnings: [],
      };
    },
  });
  const navigation = new WorkspaceNavigation(window);
  const user = userEvent.setup();
  render(
    <ProviderPage
      project={project}
      operations={operations}
      navigation={navigation}
      onProfileChange={() => undefined}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "Add provider profile" }));
  const adapter = await screen.findByLabelText("Adapter");
  expect((adapter as HTMLInputElement).value).toBe("jev");
  expect((adapter as HTMLInputElement).readOnly).toBe(true);
  await user.type(screen.getByLabelText("Requested model ID"), "jev-latest");
  await user.type(screen.getByLabelText("Destination"), "https://api.typesafe.ai/v1/systemone");
  await user.click(screen.getByRole("button", { name: "Save profile" }));

  await screen.findByRole("heading", { name: expectedProfileId });
  expect(configuredBody).toMatchObject({ profile_id: expectedProfileId, adapter: "jev" });
  navigation.dispose();
});

it("retries an unknown OS credential write with the same request after clearing the password field", async () => {
  const secret = "synthetic-m10-credential-never-a-provider-key";
  type OSCredentialSetRequest = Parameters<ProviderAuthoringOperations["setOSCredential"]>[0];
  const calls: OSCredentialSetRequest[] = [];
  const setOSCredential = vi.fn(async (request: OSCredentialSetRequest) => {
    calls.push(request);
    if (calls.length === 1) throw new ApiError("response_invalid", "Malformed success.", 200);
    return {
      data: {
        schema_version: 1 as const,
        operation_id: request.body.operation_id,
        replayed: false,
        profile,
      },
      warnings: [],
    };
  });
  const operations = providerOperations({
    list: async () => ({ data: { schema_version: 1, items: [profile], total: "1", next_cursor: null }, warnings: [] }),
    read: async () => ({ data: profile, warnings: [] }),
    credentialStatus: async () => ({ data: { schema_version: 1, profile_id: profile.id, configured: false, available: false, kind: null }, warnings: [] }),
    setOSCredential,
  });
  const navigation = new WorkspaceNavigation(window);
  const user = userEvent.setup();
  render(
    <ProviderPage
      project={project}
      operations={operations}
      navigation={navigation}
      initialProfileId={profile.id}
      onProfileChange={() => undefined}
    />,
  );

  const password = await screen.findByLabelText("Store a credential in the operating system");
  await user.type(password, secret);
  await user.click(screen.getByRole("button", { name: "Store credential" }));
  await screen.findByRole("button", { name: "Retry the same credential request" });
  expect((password as HTMLInputElement).value).toBe("");
  expect((password as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Store credential" }) as HTMLButtonElement).disabled).toBe(true);
  const replacement = "synthetic-m10-replacement-must-not-be-sent";
  await user.type(password, replacement);
  expect((password as HTMLInputElement).value).toBe("");
  expect(calls).toHaveLength(1);
  expect(document.body.textContent).not.toContain(secret);
  expect(document.body.textContent).not.toContain(replacement);
  await user.click(screen.getByRole("button", { name: "Retry the same credential request" }));

  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].body.credential_value).toBe(secret);
  expect((password as HTMLInputElement).value).toBe("");
  expect(document.body.textContent).not.toContain(secret);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
  navigation.dispose();
});

it("presents fixture profiles as authored evidence without credential or model-list actions", async () => {
  const fixtureProfile = {
    ...profile,
    adapter: "fixture",
    requested_model: "authored-sandbox-v1",
    destination: "fixture:jev-choice",
    evidence_mode: "authored_fixture" as const,
  };
  const credentialStatus = vi.fn(async () => ({
    data: { schema_version: 1 as const, profile_id: fixtureProfile.id, configured: false, available: false, kind: null },
    warnings: [],
  }));
  const operations = providerOperations({
    list: async () => ({ data: { schema_version: 1, items: [fixtureProfile], total: "1", next_cursor: null }, warnings: [] }),
    read: async () => ({ data: fixtureProfile, warnings: [] }),
    credentialStatus,
  });
  const navigation = new WorkspaceNavigation(window);
  const user = userEvent.setup();
  render(
    <ProviderPage
      project={project}
      operations={operations}
      navigation={navigation}
      initialProfileId={fixtureProfile.id}
      onProfileChange={() => undefined}
    />,
  );

  await screen.findByRole("heading", { name: "Authored fixture profile" });
  expect(screen.getByRole("region", { name: "Authored fixture provider" }).textContent).toContain("authored-sandbox-v1");
  expect(screen.queryByLabelText("Destination")).toBeNull();
  expect(screen.queryByLabelText("Environment variable name")).toBeNull();
  expect(screen.queryByLabelText("Store a credential in the operating system")).toBeNull();
  expect(screen.queryByRole("button", { name: "Refresh model list" })).toBeNull();
  expect(credentialStatus).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Open fixture library" }));
  expect(navigation.current).toEqual({ kind: "fixtures", registrationId: project.id });
  navigation.dispose();
});

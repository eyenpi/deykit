import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
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
  const listModels = vi.fn();
  const operations = {
    list: async () => ({ data: { items: [profile], total: "1", next_cursor: null }, warnings: [] }),
    read: async () => ({ data: profile, warnings: [] }),
    credentialStatus: async () => ({ data: { profile_id: profile.id, configured: false, available: false, kind: null }, warnings: [] }),
    setOSCredential,
    listModels,
  } as unknown as ProviderAuthoringOperations;
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
  vi.stubGlobal("crypto", { randomUUID: () => "new-provider-id" });
  let configuredBody: Record<string, unknown> | undefined;
  const operations = {
    list: async () => ({ data: { items: [], total: "0", next_cursor: null }, warnings: [] }),
    read: async ({ profileId }: { profileId: string }) => ({
      data: { ...profile, id: profileId }, warnings: [],
    }),
    credentialStatus: async () => ({
      data: { profile_id: "new-provider-id", configured: false, available: false, kind: null },
      warnings: [],
    }),
    configure: async ({ body }: { body: Record<string, unknown> }) => {
      configuredBody = body;
      return { data: { operation_id: body.operation_id, profile: {}, replayed: false }, warnings: [] };
    },
  } as unknown as ProviderAuthoringOperations;
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
  expect((adapter as HTMLSelectElement).value).toBe("jev");
  expect(Array.from((adapter as HTMLSelectElement).options).map((option) => option.value)).toEqual([
    "jev", "fixture",
  ]);
  await user.type(screen.getByLabelText("Requested model ID"), "jev-latest");
  await user.type(screen.getByLabelText("Destination"), "https://api.typesafe.ai/v1/systemone");
  await user.click(screen.getByRole("button", { name: "Save profile" }));

  await screen.findByRole("heading", { name: "new-provider-id" });
  expect(configuredBody).toMatchObject({ profile_id: "new-provider-id", adapter: "jev" });
  navigation.dispose();
});

it("retries an unknown OS credential write with the same request after clearing the password field", async () => {
  const secret = "synthetic-m10-credential-never-a-provider-key";
  const calls: Array<{ body: Record<string, unknown> }> = [];
  const setOSCredential = vi.fn(async (request: { body: Record<string, unknown> }) => {
    calls.push(request);
    if (calls.length === 1) throw new ApiError("response_invalid", "Malformed success.", 200);
    return { data: {}, warnings: [] };
  });
  const operations = {
    list: async () => ({ data: { items: [profile], total: "1", next_cursor: null }, warnings: [] }),
    read: async () => ({ data: profile, warnings: [] }),
    credentialStatus: async () => ({ data: { profile_id: profile.id, configured: false, available: false, kind: null }, warnings: [] }),
    setOSCredential,
  } as unknown as ProviderAuthoringOperations;
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
  expect(document.body.textContent).not.toContain(secret);
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

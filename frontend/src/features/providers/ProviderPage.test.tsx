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
});

it("keeps an OS credential mounted only for its request and never calls model listing", async () => {
  const secret = "synthetic-m10-credential-never-a-provider-key";
  const setOSCredential = vi.fn(async () => {
    throw new ApiError("credential_store_unavailable", "Secure storage is unavailable.");
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

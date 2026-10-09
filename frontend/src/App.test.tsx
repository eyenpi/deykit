import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { App } from "./App";
import { ApiError } from "./api/client";
import { disconnectedWorkspace } from "./workspace/gateway";
import type { WorkspaceGateway } from "./workspace/gateway";
it("reports unavailable service without fictional recent projects or run controls", async () => {
  render(<App />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText("Sandbox")).toBeNull();
  expect(screen.queryByRole("button", { name: "Run…" })).toBeNull();
  expect(screen.queryByText("Accuracy")).toBeNull();
});
it("keeps project form values and operation ID after a failed mutation", async () => {
  const gateway: WorkspaceGateway = {
    authoring: disconnectedWorkspace.authoring,
    recentProjects: async () => ({ items: [], warnings: [] }),
    projectOverview: async () => { throw new Error("not used"); },
    openProject: vi
      .fn()
      .mockRejectedValue(new ApiError("conflict", "Folder already exists.")),
    reconnect: async () => {},
  };
  const user = userEvent.setup();
  render(<App gateway={gateway} />);
  await user.click(screen.getByRole("button", { name: /Create project/ }));
  await user.type(screen.getByLabelText("Project name"), "My project");
  await user.type(
    screen.getByLabelText("Project folder path"),
    "/tmp/my project",
  );
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findByText("Folder already exists.");
  expect(
    (screen.getByLabelText("Project folder path") as HTMLInputElement).value,
  ).toBe("/tmp/my project");
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await waitFor(() => expect(gateway.openProject).toHaveBeenCalledTimes(2));
  const calls = vi.mocked(gateway.openProject).mock.calls;
  expect(calls[0][0].operationId).toBe(calls[1][0].operationId);
});
it(
  "renders server supplied project context and keeps Run/History within decision context",
  async () => {
    const gateway: WorkspaceGateway = {
      authoring: disconnectedWorkspace.authoring,
      recentProjects: async () => ({ items: [], warnings: [] }),
      projectOverview: async () => { throw new Error("not used"); },
      openProject: async () => ({
        id: "authored-test",
        name: "Authored test project",
        path: "/tmp/test",
        decisions: [{ id: "d", name: "Test decision" }],
        datasets: [],
        warnings: [],
      }),
      reconnect: async () => {},
    };
    const user = userEvent.setup();
    render(<App gateway={gateway} />);
    await user.click(screen.getByRole("button", { name: /Open project/ }));
    await user.type(screen.getByLabelText("Project folder path"), "/tmp/test");
    await user.click(screen.getByRole("button", { name: "Open project" }));
    await screen.findByRole("heading", { name: "Authored test project" });
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();
    await user.click(screen.getAllByRole("button", { name: "Test decision" })[0]);
    expect(screen.getByRole("button", { name: "History" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Providers" }));
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();
  },
);

it(
  "uses the selected recent path and focuses only the successful overview transition",
  async () => {
    const gateway: WorkspaceGateway = {
      authoring: disconnectedWorkspace.authoring,
      recentProjects: async () => ({
        items: [
          {
            id: "known",
            name: "Known project",
            path: "/tmp/Exact existing folder",
          },
        ],
        warnings: [],
      }),
      projectOverview: async () => { throw new Error("not used"); },
      openProject: vi.fn().mockImplementation(async (request) => ({
        id: "known",
        name: "Known project",
        path: request.path,
        decisions: [],
        datasets: [],
        warnings: [],
      })),
      reconnect: async () => {},
    };
    const user = userEvent.setup();
    const { rerender } = render(<App gateway={gateway} />);
    await user.click(
      await screen.findByRole("button", {
        name: "Open project folder: Known project",
      }),
    );
    expect(
      (screen.getByLabelText("Project folder path") as HTMLInputElement).value,
    ).toBe("/tmp/Exact existing folder");
    await user.click(screen.getByRole("button", { name: "Open project" }));
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { name: "Known project" }),
      ),
    );
    expect(gateway.openProject).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "open",
        path: "/tmp/Exact existing folder",
      }),
    );
    const create = screen.getByRole("button", { name: "Create decision" });
    create.focus();
    rerender(<App gateway={gateway} />);
    expect(document.activeElement).toBe(create);
  },
);

it("renders structured safe warnings without flattening their fields", async () => {
  const gateway: WorkspaceGateway = {
    authoring: disconnectedWorkspace.authoring,
    recentProjects: async () => ({
      items: [],
      warnings: [
        {
          schema_version: 1,
          code: "preflight_failed",
          message: "Recent projects could not be read.",
          reason: "recent_projects_unavailable",
          resource_id: null,
          row: null,
          correlation_id: null,
        },
      ],
    }),
    projectOverview: async () => { throw new Error("not used"); },
    openProject: async () => {
      throw new Error("not used");
    },
    reconnect: async () => {},
  };
  render(<App gateway={gateway} />);
  expect(
    (await screen.findByRole("status", { name: "Warnings" })).textContent,
  ).toContain("preflight_failed");
  expect(screen.getByText("recent_projects_unavailable")).toBeTruthy();
});

it("reconnects without losing a failed project form or its entered values", async () => {
  const gateway: WorkspaceGateway = {
    authoring: disconnectedWorkspace.authoring,
    recentProjects: async () => ({ items: [], warnings: [] }),
    projectOverview: async () => { throw new Error("not used"); },
    openProject: vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError("local_access_denied", "Reconnect to the local service.", 403),
      )
      .mockImplementation(async (request) => ({
        id: "registered",
        name: "My project",
        path: request.path,
        decisions: [],
        datasets: [],
        warnings: [],
      })),
    reconnect: vi.fn(async () => {}),
  };
  const user = userEvent.setup();
  render(<App gateway={gateway} />);
  await user.click(screen.getByRole("button", { name: /Create project/ }));
  await user.type(screen.getByLabelText("Project name"), "My project");
  await user.type(screen.getByLabelText("Project folder path"), "/tmp/new");
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await user.click(await screen.findByRole("button", { name: "Reconnect" }));
  await waitFor(() => expect(gateway.reconnect).toHaveBeenCalledTimes(1));
  expect(screen.queryByText("Reconnect to the local service.")).toBeNull();
  expect((screen.getByLabelText("Project name") as HTMLInputElement).value).toBe(
    "My project",
  );
  expect((screen.getByLabelText("Project folder path") as HTMLInputElement).value).toBe(
    "/tmp/new",
  );
  const firstOperationId = vi.mocked(gateway.openProject).mock.calls[0][0].operationId;
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findByRole("heading", { name: "My project" });
  expect(vi.mocked(gateway.openProject).mock.calls[1][0].operationId).toBe(
    firstOperationId,
  );
});

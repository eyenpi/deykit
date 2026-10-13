import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { ApiError } from "./api/client";
import type { ApiOperationData } from "./api/client";
import { disconnectedWorkspace } from "./workspace/gateway";
import type {
  DecisionAuthoringOperations,
  ProjectOverview,
  WorkspaceGateway,
} from "./workspace/gateway";

beforeEach(() => {
  window.history.replaceState(null, "", "#/");
});

it("reports unavailable service without fictional recent projects or run controls", async () => {
  render(<App />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText("Sandbox")).toBeNull();
  expect(screen.queryByRole("button", { name: "Run…" })).toBeNull();
  expect(screen.queryByText("Accuracy")).toBeNull();
});

it("retries a committed archive before navigating and loading the overview", async () => {
  const registrationId = "archive-registration";
  const decisionId = "archive-decision";
  const decisionName = "Archive flow decision";
  let archiveCommitted = false;
  const archivedDecision: ApiOperationData<"archiveDecision"> = {
    etag: "decision-etag-2",
    record: {
      schema_version: 1,
      id: decisionId,
      name: decisionName,
      archived: true,
    },
  };
  let rejectFirstArchive: ((cause: unknown) => void) | undefined;
  const firstArchive = new Promise<{
    data: ApiOperationData<"archiveDecision">;
    warnings: [];
  }>((_resolve, reject) => {
    rejectFirstArchive = reject;
  });
  const archive = vi
    .fn<DecisionAuthoringOperations["archive"]>()
    .mockImplementationOnce(() => firstArchive)
    .mockImplementationOnce(async () => {
      archiveCommitted = true;
      return { data: archivedDecision, warnings: [] };
    });
  const listedDecision = (archived: boolean) => ({
    schema_version: 1 as const,
    decision: {
      etag: archived ? archivedDecision.etag : "decision-etag-1",
      record: {
        schema_version: 1 as const,
        id: decisionId,
        name: decisionName,
        archived,
      },
    },
    draft: {
      etag: "draft-etag-1",
      record: {
        schema_version: 1 as const,
        decision_id: decisionId,
        editor_source: "{}",
        base_revision_id: null,
        updated_at: "2026-10-11T00:00:00Z",
      },
    },
  });
  const list = vi.fn<DecisionAuthoringOperations["list"]>(async () => ({
    data: {
      schema_version: 1,
      items: [listedDecision(archiveCommitted)],
      next_cursor: null,
      total: "1",
    },
    warnings: [],
  }));
  const project = (): ProjectOverview => ({
    id: registrationId,
    name: "Archive flow project",
    path: "/tmp/archive-flow",
    decisions: archiveCommitted ? [] : [{ id: decisionId, name: decisionName }],
    datasets: [],
    warnings: [],
  });
  const gateway: WorkspaceGateway = {
    execution: disconnectedWorkspace.execution,
    debugging: disconnectedWorkspace.debugging,
    authoring: {
      ...disconnectedWorkspace.authoring,
      decisions: {
        ...disconnectedWorkspace.authoring.decisions,
        list,
        read: async () => ({
          data: {
            schema_version: 1,
            decision: {
              etag: "decision-etag-1",
              record: {
                schema_version: 1,
                id: decisionId,
                name: decisionName,
                archived: false,
                latest_revision_id: null,
              },
            },
            draft: {
              etag: "draft-etag-1",
              record: {
                schema_version: 1,
                decision_id: decisionId,
                editor_source: "{}",
                base_revision_id: null,
                updated_at: "2026-10-11T00:00:00Z",
              },
            },
          },
          warnings: [],
        }),
        projectEditor: async ({ body }) => ({
          data: {
            schema_version: 1,
            editor_source: body.editor_source,
            form: null,
            form_unavailable_reason: "invalid_editor_source",
            source_hash: null,
            validation_advice: [],
          },
          warnings: [],
        }),
        archive,
      },
    },
    recentProjects: async () => ({ items: [], warnings: [] }),
    openProject: async () => project(),
    projectOverview: vi.fn(async () => project()),
    reconnect: async () => undefined,
  };
  const user = userEvent.setup();
  render(<App gateway={gateway} />);
  await user.click(screen.getByRole("button", { name: /Open project/ }));
  await user.type(
    screen.getByLabelText("Project folder path"),
    "/tmp/archive-flow",
  );
  await user.click(screen.getByRole("button", { name: "Open project" }));
  await screen.findByRole("heading", { name: "Archive flow project" });
  await user.click(
    within(screen.getByRole("main")).getByRole("button", {
      name: decisionName,
    }),
  );
  await screen.findByLabelText("Decision name");

  await user.click(screen.getByRole("button", { name: "Archive decision" }));
  const archiveDialog = screen.getByRole("dialog", {
    name: "Archive this decision?",
  });
  await user.click(
    within(archiveDialog).getByRole("button", { name: "Archive decision" }),
  );
  fireEvent.click(
    within(screen.getByRole("navigation", { name: "Workspace" })).getByRole(
      "button",
      {
        name: "Archive flow project",
      },
    ),
  );
  const submittingPrompt = await screen.findByRole("dialog", {
    name: "Unsaved changes",
  });
  expect(
    (
      within(submittingPrompt).getByRole("button", {
        name: "Save and leave",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(
    (
      within(submittingPrompt).getByRole("button", {
        name: "Discard changes",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await user.click(
    within(submittingPrompt).getByRole("button", { name: "Keep editing" }),
  );
  rejectFirstArchive?.(new TypeError("The first archive reply was lost."));
  const retry = await screen.findByRole("button", {
    name: "Retry same archive action",
  });
  fireEvent.click(
    within(screen.getByRole("navigation", { name: "Workspace" })).getByRole(
      "button",
      {
        name: "Archive flow project",
      },
    ),
  );
  const unknownPrompt = await screen.findByRole("dialog", {
    name: "Unsaved changes",
  });
  expect(
    (
      within(unknownPrompt).getByRole("button", {
        name: "Save and leave",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(
    (
      within(unknownPrompt).getByRole("button", {
        name: "Discard changes",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await user.click(
    within(unknownPrompt).getByRole("button", { name: "Keep editing" }),
  );
  const originalRequest = archive.mock.calls[0]?.[0];
  await user.click(retry);
  await waitFor(() => expect(archive).toHaveBeenCalledTimes(2));
  expect(archive.mock.calls[1]?.[0]).toEqual(originalRequest);
  expect(archive.mock.calls[1]?.[0].body.operation_id).toBe(
    originalRequest?.body.operation_id,
  );

  await screen.findByRole("table", { name: "Archived decisions" });
  await screen.findByRole("row", { name: /Archive flow decision/ });
  expect(gateway.projectOverview).toHaveBeenCalledTimes(1);
  expect(list).toHaveBeenCalledTimes(2);
  expect(window.location.hash).toBe(`#/p/${registrationId}`);
});
it("keeps project form values and operation ID after a failed mutation", async () => {
  const gateway: WorkspaceGateway = {
    execution: disconnectedWorkspace.execution,
    debugging: disconnectedWorkspace.debugging,
    authoring: disconnectedWorkspace.authoring,
    recentProjects: async () => ({ items: [], warnings: [] }),
    projectOverview: async () => {
      throw new Error("not used");
    },
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
it("renders server supplied project context and keeps Run/History within decision context", async () => {
  const overview = {
    id: "authored-test",
    name: "Authored test project",
    path: "/tmp/test",
    decisions: [{ id: "d", name: "Test decision" }],
    datasets: [],
    warnings: [],
  };
  const gateway: WorkspaceGateway = {
    execution: disconnectedWorkspace.execution,
    debugging: disconnectedWorkspace.debugging,
    authoring: {
      ...disconnectedWorkspace.authoring,
      decisions: {
        ...disconnectedWorkspace.authoring.decisions,
        read: async ({ decisionId }) => ({
          data: {
            schema_version: 1,
            decision: {
              etag: "decision-etag",
              record: {
                schema_version: 1,
                id: decisionId,
                name: "Test decision",
              },
            },
            draft: {
              etag: "draft-etag",
              record: {
                schema_version: 1,
                decision_id: decisionId,
                editor_source: "{}",
                updated_at: "2026-10-10T00:00:00Z",
              },
            },
          },
          warnings: [],
        }),
        projectEditor: async ({ body }) => ({
          data: {
            schema_version: 1,
            editor_source: body.editor_source,
            form: null,
            form_unavailable_reason: "invalid_editor_source",
            source_hash: null,
            validation_advice: [],
          },
          warnings: [],
        }),
        list: async () => ({
          data: { schema_version: 1, items: [], total: "0", next_cursor: null },
          warnings: [],
        }),
      },
    },
    recentProjects: async () => ({ items: [], warnings: [] }),
    projectOverview: async (registrationId) => ({
      ...overview,
      id: registrationId,
    }),
    openProject: async () => overview,
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
  await screen.findByLabelText("Decision name");
  expect(screen.getByRole("button", { name: "History" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Providers" }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "History" })).toBeNull(),
  );
});

it("uses the selected recent path and focuses only the successful overview transition", async () => {
  const gateway: WorkspaceGateway = {
    execution: disconnectedWorkspace.execution,
    debugging: disconnectedWorkspace.debugging,
    authoring: {
      ...disconnectedWorkspace.authoring,
      decisions: {
        ...disconnectedWorkspace.authoring.decisions,
        list: async () => ({
          data: { schema_version: 1, items: [], total: "0", next_cursor: null },
          warnings: [],
        }),
      },
    },
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
    projectOverview: async () => {
      throw new Error("not used");
    },
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
});

it("renders structured safe warnings without flattening their fields", async () => {
  const gateway: WorkspaceGateway = {
    execution: disconnectedWorkspace.execution,
    debugging: disconnectedWorkspace.debugging,
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
    projectOverview: async () => {
      throw new Error("not used");
    },
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
    execution: disconnectedWorkspace.execution,
    debugging: disconnectedWorkspace.debugging,
    authoring: disconnectedWorkspace.authoring,
    recentProjects: async () => ({ items: [], warnings: [] }),
    projectOverview: async () => {
      throw new Error("not used");
    },
    openProject: vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError(
          "local_access_denied",
          "Reconnect to the local service.",
          403,
        ),
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
  expect(
    (screen.getByLabelText("Project name") as HTMLInputElement).value,
  ).toBe("My project");
  expect(
    (screen.getByLabelText("Project folder path") as HTMLInputElement).value,
  ).toBe("/tmp/new");
  const firstOperationId = vi.mocked(gateway.openProject).mock.calls[0][0]
    .operationId;
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findByRole("heading", { name: "My project" });
  expect(vi.mocked(gateway.openProject).mock.calls[1][0].operationId).toBe(
    firstOperationId,
  );
});

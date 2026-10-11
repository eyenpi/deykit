import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { ApiOperationData } from "../api/client";
import type { DecisionAuthoringOperations, ProjectOverview } from "./gateway";
import { WorkspaceNavigation } from "./navigation";
import { Overview } from "./Overview";

type DecisionPage = ApiOperationData<"listDecisions">;
type DecisionItem = DecisionPage["items"][number];
type RestoreData = ApiOperationData<"restoreDecision">;

const archivedId = "decision-archived";
const projectA: ProjectOverview = {
  id: "registration-a",
  name: "Project A",
  path: "/tmp/project-a",
  decisions: [{ id: "decision-active", name: "Active decision" }],
  datasets: [],
  warnings: [],
};

function listedDecision(
  id: string,
  name: string,
  archived: boolean,
): DecisionItem {
  return {
    schema_version: 1,
    decision: {
      etag: `etag-${id}`,
      record: { schema_version: 1, id, name, archived },
    },
    draft: {
      etag: `draft-etag-${id}`,
      record: {
        schema_version: 1,
        decision_id: id,
        editor_source: "{}",
        base_revision_id: null,
        updated_at: "2026-10-11T00:00:00Z",
      },
    },
  };
}

function page(
  items: readonly DecisionItem[],
  nextCursor: string | null = null,
): DecisionPage {
  return {
    schema_version: 1,
    items,
    next_cursor: nextCursor,
    total: String(items.length),
  };
}

function restored(id: string, name: string): RestoreData {
  return {
    etag: `restored-${id}`,
    record: { schema_version: 1, id, name, archived: false },
  };
}

function makeOperations(
  list: DecisionAuthoringOperations["list"],
  restore: DecisionAuthoringOperations["restore"],
): DecisionAuthoringOperations {
  const unavailable = () =>
    Promise.reject(new ApiError("internal_error", "Unused operation."));
  return {
    list,
    create: vi.fn(unavailable),
    read: vi.fn(unavailable),
    updateDraft: vi.fn(unavailable),
    projectEditor: vi.fn(unavailable),
    transformEditor: vi.fn(unavailable),
    validate: vi.fn(unavailable),
    saveRevision: vi.fn(unavailable),
    revisions: vi.fn(unavailable),
    latestRevision: vi.fn(unavailable),
    revision: vi.fn(unavailable),
    diff: vi.fn(unavailable),
    rename: vi.fn(unavailable),
    archive: vi.fn(unavailable),
    restore,
    restoreRevisionToDraft: vi.fn(unavailable),
  };
}

function response(data: DecisionPage) {
  return Promise.resolve({ data, warnings: [] });
}

function setup(operations: DecisionAuthoringOperations, project = projectA) {
  window.history.replaceState(null, "", `#/p/${project.id}`);
  const navigation = new WorkspaceNavigation(window);
  const onDecisionsChanged = vi.fn();
  const view = render(
    <Overview
      project={project}
      navigation={navigation}
      decisionOperations={operations}
      onDecision={vi.fn()}
      onCreateDecision={vi.fn()}
      onCreateDataset={vi.fn()}
      onExamples={vi.fn()}
      onDecisionsChanged={onDecisionsChanged}
    />,
  );
  return { ...view, navigation, onDecisionsChanged };
}

const navigations: WorkspaceNavigation[] = [];
afterEach(() => {
  for (const navigation of navigations.splice(0)) navigation.dispose();
});

it("adopts a successful restore receipt into the current archive page", async () => {
  const restore = vi
    .fn<DecisionAuthoringOperations["restore"]>()
    .mockResolvedValue({
      data: restored(archivedId, "Archived decision"),
      warnings: [],
    });
  const operations = makeOperations(
    vi
      .fn<DecisionAuthoringOperations["list"]>()
      .mockImplementation(() =>
        response(page([listedDecision(archivedId, "Archived decision", true)])),
      ),
    restore,
  );
  const { navigation, onDecisionsChanged } = setup(operations);
  navigations.push(navigation);
  const user = userEvent.setup();

  const row = await screen.findByRole("row", { name: /Archived decision/ });
  await user.click(within(row).getByRole("button", { name: "Restore" }));

  await waitFor(() => {
    expect(screen.queryByRole("row", { name: /Archived decision/ })).toBeNull();
  });
  expect(restore).toHaveBeenCalledTimes(1);
  expect(onDecisionsChanged).toHaveBeenCalledTimes(1);
  expect(
    screen.getByRole("table", { name: "Project decisions" }).textContent,
  ).toContain("Active decision");
});

it("retains an unknown restore and blocks navigation until the exact retry succeeds", async () => {
  const restore = vi
    .fn<DecisionAuthoringOperations["restore"]>()
    .mockRejectedValueOnce(new TypeError("connection lost"))
    .mockResolvedValueOnce({
      data: restored(archivedId, "Archived decision"),
      warnings: [],
    });
  const operations = makeOperations(
    vi
      .fn<DecisionAuthoringOperations["list"]>()
      .mockImplementation(() =>
        response(page([listedDecision(archivedId, "Archived decision", true)])),
      ),
    restore,
  );
  const { navigation, onDecisionsChanged } = setup(operations);
  navigations.push(navigation);
  const user = userEvent.setup();
  const row = await screen.findByRole("row", { name: /Archived decision/ });
  const restoreButton = within(row).getByRole("button", { name: "Restore" });
  fireEvent.click(restoreButton);
  fireEvent.click(restoreButton);

  const retry = await screen.findByRole("button", {
    name: "Retry same restore action",
  });
  expect(restore).toHaveBeenCalledTimes(1);
  const originalRequest = restore.mock.calls[0]?.[0];
  expect(originalRequest?.body.expected_etag).toBe(`etag-${archivedId}`);

  let navigationResult: Promise<boolean> | undefined;
  act(() => {
    navigationResult = navigation.navigate({
      kind: "providers",
      registrationId: projectA.id,
    });
  });
  const prompt = await screen.findByRole("dialog", { name: "Unsaved changes" });
  expect(
    (
      within(prompt).getByRole("button", {
        name: "Save and leave",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(
    (
      within(prompt).getByRole("button", {
        name: "Discard changes",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await user.click(
    within(prompt).getByRole("button", { name: "Keep editing" }),
  );
  await expectNavigationResult(navigationResult);

  await user.click(retry);
  await waitFor(() => expect(restore).toHaveBeenCalledTimes(2));
  expect(restore.mock.calls[1]?.[0]).toEqual(originalRequest);
  await waitFor(() =>
    expect(screen.queryByRole("row", { name: /Archived decision/ })).toBeNull(),
  );
  expect(onDecisionsChanged).toHaveBeenCalledTimes(1);
});

it("requires an explicit archive review after a known restore rejection", async () => {
  const restore = vi
    .fn<DecisionAuthoringOperations["restore"]>()
    .mockRejectedValueOnce(
      new ApiError("conflict", "The decision changed.", 409),
    )
    .mockResolvedValueOnce({
      data: restored(archivedId, "Archived decision"),
      warnings: [],
    });
  const list = vi
    .fn<DecisionAuthoringOperations["list"]>()
    .mockImplementation(() =>
      response(page([listedDecision(archivedId, "Archived decision", true)])),
    );
  const operations = makeOperations(list, restore);
  const { navigation, onDecisionsChanged } = setup(operations);
  navigations.push(navigation);
  const user = userEvent.setup();
  const row = await screen.findByRole("row", { name: /Archived decision/ });
  await user.click(within(row).getByRole("button", { name: "Restore" }));
  await user.click(
    await screen.findByRole("button", { name: "Review archived decisions" }),
  );
  await waitFor(() => {
    expect(
      (
        within(
          screen.getByRole("row", { name: /Archived decision/ }),
        ).getByRole("button", { name: "Restore" }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });
  expect(restore).toHaveBeenCalledTimes(1);
  expect(list).toHaveBeenCalledTimes(2);
  await user.click(
    within(screen.getByRole("row", { name: /Archived decision/ })).getByRole(
      "button",
      { name: "Restore" },
    ),
  );
  await waitFor(() => expect(restore).toHaveBeenCalledTimes(2));
  expect(onDecisionsChanged).toHaveBeenCalledTimes(1);
});

it("hides a replaced project's old archive and ignores its late read and restore callback", async () => {
  let resolveOldList:
    | ((
        value: Awaited<ReturnType<DecisionAuthoringOperations["list"]>>,
      ) => void)
    | undefined;
  const oldList = new Promise<
    Awaited<ReturnType<DecisionAuthoringOperations["list"]>>
  >((resolve) => {
    resolveOldList = resolve;
  });
  const list = vi
    .fn<DecisionAuthoringOperations["list"]>()
    .mockImplementation((request) =>
      request.registrationId === projectA.id
        ? oldList
        : response(
            page([listedDecision(archivedId, "Project B decision", true)]),
          ),
    );
  const restore = vi
    .fn<DecisionAuthoringOperations["restore"]>()
    .mockResolvedValue({
      data: restored(archivedId, "Project B decision"),
      warnings: [],
    });
  const operations = makeOperations(list, restore);
  const { navigation, rerender } = setup(operations);
  navigations.push(navigation);
  const projectB: ProjectOverview = {
    ...projectA,
    id: "registration-b",
    name: "Project B",
  };
  rerender(
    <Overview
      project={projectB}
      navigation={navigation}
      decisionOperations={operations}
      onDecision={vi.fn()}
      onCreateDecision={vi.fn()}
      onCreateDataset={vi.fn()}
      onExamples={vi.fn()}
      onDecisionsChanged={vi.fn()}
    />,
  );
  expect(screen.queryByRole("row", { name: /Project A decision/ })).toBeNull();
  const projectBRow = await screen.findByRole("row", {
    name: /Project B decision/,
  });
  await act(async () => {
    resolveOldList?.({
      data: page([listedDecision(archivedId, "Project A decision", true)]),
      warnings: [],
    });
  });
  expect(screen.queryByRole("row", { name: /Project A decision/ })).toBeNull();
  expect(projectBRow.isConnected).toBe(true);
  expect(list).toHaveBeenCalledTimes(2);
  expect(restore).not.toHaveBeenCalled();
});

it("does not append a delayed pagination page to a replacement project", async () => {
  let resolveOldPage:
    | ((
        value: Awaited<ReturnType<DecisionAuthoringOperations["list"]>>,
      ) => void)
    | undefined;
  const oldPage = new Promise<
    Awaited<ReturnType<DecisionAuthoringOperations["list"]>>
  >((resolve) => {
    resolveOldPage = resolve;
  });
  const list = vi
    .fn<DecisionAuthoringOperations["list"]>()
    .mockImplementation((request) => {
      if (request.registrationId === projectA.id) {
        if (request.query?.cursor) return oldPage;
        return response(
          page(
            [listedDecision("decision-a", "Project A archived", true)],
            "next-a",
          ),
        );
      }
      return response(
        page([listedDecision("decision-b", "Project B archived", true)]),
      );
    });
  const operations = makeOperations(
    list,
    vi.fn<DecisionAuthoringOperations["restore"]>(),
  );
  const { navigation, rerender } = setup(operations);
  navigations.push(navigation);
  const user = userEvent.setup();
  await screen.findByRole("row", { name: /Project A archived/ });
  await user.click(screen.getByRole("button", { name: "Load more decisions" }));

  const projectB = { ...projectA, id: "registration-b", name: "Project B" };
  rerender(
    <Overview
      project={projectB}
      navigation={navigation}
      decisionOperations={operations}
      onDecision={vi.fn()}
      onCreateDecision={vi.fn()}
      onCreateDataset={vi.fn()}
      onExamples={vi.fn()}
      onDecisionsChanged={vi.fn()}
    />,
  );
  expect(screen.queryByRole("row", { name: /Project A archived/ })).toBeNull();
  await screen.findByRole("row", { name: /Project B archived/ });
  await act(async () => {
    resolveOldPage?.({
      data: page([
        listedDecision("decision-a-late", "Late Project A archived", true),
      ]),
      warnings: [],
    });
  });
  expect(
    screen.queryByRole("row", { name: /Late Project A archived/ }),
  ).toBeNull();
  expect(screen.getByRole("row", { name: /Project B archived/ })).toBeTruthy();
});

it("does not notify a replaced project when its admitted restore later settles", async () => {
  let resolveRestore:
    | ((
        value: Awaited<ReturnType<DecisionAuthoringOperations["restore"]>>,
      ) => void)
    | undefined;
  const restoreResponse = new Promise<
    Awaited<ReturnType<DecisionAuthoringOperations["restore"]>>
  >((resolve) => {
    resolveRestore = resolve;
  });
  const restore = vi
    .fn<DecisionAuthoringOperations["restore"]>()
    .mockReturnValue(restoreResponse);
  const operations = makeOperations(
    vi
      .fn<DecisionAuthoringOperations["list"]>()
      .mockImplementation(() =>
        response(page([listedDecision(archivedId, "Archived decision", true)])),
      ),
    restore,
  );
  const { navigation, rerender, onDecisionsChanged } = setup(operations);
  navigations.push(navigation);
  const user = userEvent.setup();
  const row = await screen.findByRole("row", { name: /Archived decision/ });
  await user.click(within(row).getByRole("button", { name: "Restore" }));
  expect(restore).toHaveBeenCalledTimes(1);

  const projectB = { ...projectA, id: "registration-b", name: "Project B" };
  const projectBChanged = vi.fn();
  rerender(
    <Overview
      project={projectB}
      navigation={navigation}
      decisionOperations={operations}
      onDecision={vi.fn()}
      onCreateDecision={vi.fn()}
      onCreateDataset={vi.fn()}
      onExamples={vi.fn()}
      onDecisionsChanged={projectBChanged}
    />,
  );
  await screen.findByRole("heading", { name: "Project B" });
  await act(async () => {
    resolveRestore?.({
      data: restored(archivedId, "Archived decision"),
      warnings: [],
    });
  });
  expect(onDecisionsChanged).not.toHaveBeenCalled();
  const projectBRow = screen.getByRole("row", { name: /Archived decision/ });
  expect(projectBRow.isConnected).toBe(true);
  expect(
    within(projectBRow).getByRole("button", { name: "Restore" }).isConnected,
  ).toBe(true);
  expect(projectBChanged).not.toHaveBeenCalled();
  expect(restore).toHaveBeenCalledTimes(1);
});

it("does not publish or notify after the overview is unmounted", async () => {
  let resolveRestore:
    | ((
        value: Awaited<ReturnType<DecisionAuthoringOperations["restore"]>>,
      ) => void)
    | undefined;
  const restoreResponse = new Promise<
    Awaited<ReturnType<DecisionAuthoringOperations["restore"]>>
  >((resolve) => {
    resolveRestore = resolve;
  });
  const restore = vi
    .fn<DecisionAuthoringOperations["restore"]>()
    .mockReturnValue(restoreResponse);
  const operations = makeOperations(
    vi
      .fn<DecisionAuthoringOperations["list"]>()
      .mockImplementation(() =>
        response(page([listedDecision(archivedId, "Archived decision", true)])),
      ),
    restore,
  );
  const { navigation, unmount, onDecisionsChanged } = setup(operations);
  navigations.push(navigation);
  const user = userEvent.setup();
  const row = await screen.findByRole("row", { name: /Archived decision/ });
  await user.click(within(row).getByRole("button", { name: "Restore" }));
  expect(restore).toHaveBeenCalledTimes(1);
  unmount();

  await act(async () => {
    resolveRestore?.({
      data: restored(archivedId, "Archived decision"),
      warnings: [],
    });
  });
  expect(onDecisionsChanged).not.toHaveBeenCalled();
  expect(screen.queryByRole("row", { name: /Archived decision/ })).toBeNull();
});

async function expectNavigationResult(result: Promise<boolean> | undefined) {
  await expect(result).resolves.toBe(false);
}

import { useEffect, useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { DecisionAuthoringOperations } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { routeToHash } from "../../workspace/routes";
import type { WorkspaceRoute } from "../../workspace/routes";
import { DefinitionHistory } from "./DefinitionHistory";

const historyRoute = {
  kind: "decision-history",
  registrationId: "registration-1",
  decisionId: "decision-1",
} as const;
const targetRoute = {
  kind: "overview",
  registrationId: "registration-1",
} as const;
const editorSource =
  '{"exact":9007199254740993,"fraction":0.1234567890123456789}';
const revision: ApiOperationData<"readDecisionRevision"> = {
  schema_version: 1,
  editor_source: editorSource,
  revision: {
    etag: "revision-etag",
    record: {
      schema_version: 1,
      id: "revision-1",
      decision_id: historyRoute.decisionId,
      created_at: "2026-10-10T00:00:00Z",
      content_hash: "revision-hash",
      definition: {
        schema_version: 1,
        input_kind: "json",
        input_schema_source: '{"type":"object"}',
        selected_fields: [],
        questions: [{ id: "question-1", instructions: "Choose", options: [] }],
      },
    },
  },
};
const draft: ApiOperationData<"restoreDecisionRevisionToDraft"> = {
  etag: "draft-etag",
  record: {
    schema_version: 1,
    decision_id: historyRoute.decisionId,
    editor_source: editorSource,
    updated_at: "2026-10-10T00:00:00Z",
    base_revision_id: null,
  },
};

afterEach(() => window.history.replaceState(null, "", "#/"));

it.each(["in-app", "hash"] as const)(
  "retains an in-flight restore through %s navigation and retries its exact request",
  async (navigationKind) => {
    window.history.replaceState(null, "", routeToHash(historyRoute));
    const navigation = new WorkspaceNavigation(window);
    const register = vi.spyOn(navigation, "registerDirtyGuard");
    const restored = vi.fn();
    let rejectReply!: (cause: unknown) => void;
    const heldReply = new Promise<never>((_, reject) => {
      rejectReply = reject;
    });
    let dirtyAtDispatch = false;
    const restoreRevisionToDraft = vi.fn<
      DecisionAuthoringOperations["restoreRevisionToDraft"]
    >(() => {
      // The retained mutation changes synchronously, before React renders it.
      dirtyAtDispatch = register.mock.calls[0][1].isDirty();
      return heldReply;
    });
    const read = vi.fn<DecisionAuthoringOperations["read"]>(async () => ({
      data: {
        schema_version: 1,
        decision: {
          etag: "decision-etag",
          record: {
            schema_version: 1,
            id: historyRoute.decisionId,
            name: "Decision",
            archived: false,
            latest_revision_id: "revision-1",
          },
        },
        draft,
      },
      warnings: [],
    }));
    const operations: DecisionAuthoringOperations = {
      ...disconnectedWorkspace.authoring.decisions,
      revisions: async () => ({
        data: {
          schema_version: 1,
          items: [revision],
          next_cursor: null,
          total: "1",
        },
        warnings: [],
      }),
      revision: async () => ({ data: revision, warnings: [] }),
      read,
      restoreRevisionToDraft,
    };
    function Harness() {
      const [route, setRoute] = useState<WorkspaceRoute>(navigation.current);
      useEffect(() => navigation.subscribe(setRoute), []);
      return route.kind === "decision-history" ? (
        <DefinitionHistory
          {...historyRoute}
          operations={operations}
          navigation={navigation}
          onRestoredToDraft={restored}
        />
      ) : (
        <h1>Overview</h1>
      );
    }
    async function tryLeaving() {
      await act(async () => {
        if (navigationKind === "in-app") {
          expect(await navigation.navigate(targetRoute)).toBe(false);
        } else {
          const oldURL = window.location.href;
          window.history.replaceState(null, "", routeToHash(targetRoute));
          window.dispatchEvent(
            new HashChangeEvent("hashchange", {
              oldURL,
              newURL: window.location.href,
            }),
          );
        }
      });
      expect(navigation.current).toEqual(historyRoute);
      expect(window.location.hash).toBe(routeToHash(historyRoute));
      expect(
        screen.getByRole("heading", { name: "Version history" }),
      ).toBeTruthy();
      expect(screen.getByRole("dialog")).toBeTruthy();
      expect(
        screen.getByLabelText<HTMLTextAreaElement>("Editor source to restore")
          .value,
      ).toBe(editorSource);
    }

    const mounted = render(<Harness />);
    try {
      fireEvent.click(
        await screen.findByRole("button", { name: "Restore to draft…" }),
      );
      await screen.findByRole("dialog");
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: /^Restore to draft$/ }),
        );
      });
      expect(restoreRevisionToDraft).toHaveBeenCalledTimes(1);
      expect(dirtyAtDispatch).toBe(true);
      const originalBody = restoreRevisionToDraft.mock.calls[0][0].body;
      expect(originalBody).toEqual({
        schema_version: 1,
        expected_draft_etag: draft.etag,
        revision_id: revision.revision.record.id,
        operation_id: expect.any(String),
      });
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      expect(unload.defaultPrevented).toBe(true);
      await tryLeaving();
      expect(restoreRevisionToDraft).toHaveBeenCalledTimes(1);
      expect(restored).not.toHaveBeenCalled();

      await act(async () => rejectReply(new Error("Response lost")));
      await screen.findByRole("button", {
        name: "Retry the same restore request",
      });
      await tryLeaving();
      restoreRevisionToDraft.mockResolvedValueOnce({
        data: draft,
        warnings: [],
      });
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", {
            name: "Retry the same restore request",
          }),
        );
      });
      expect(restoreRevisionToDraft).toHaveBeenCalledTimes(2);
      expect(restoreRevisionToDraft.mock.calls[1][0].body).toBe(originalBody);
      expect(read).toHaveBeenCalledTimes(1);
      expect(restored).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("dialog")).toBeNull();
      const settledUnload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(settledUnload);
      expect(settledUnload.defaultPrevented).toBe(false);
      await act(async () => {
        expect(await navigation.navigate(targetRoute)).toBe(true);
      });
      expect(screen.getByRole("heading", { name: "Overview" })).toBeTruthy();
    } finally {
      mounted.unmount();
      navigation.dispose();
    }
  },
);

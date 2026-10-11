import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationData, ApiResult } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { AnnotationSheet } from "./AnnotationSheet";

vi.mock("../../components/Modal", () => ({
  Modal: ({ children, title }: { children: ReactNode; title: string }) => (
    <div role="dialog" aria-label={title}>
      {children}
    </div>
  ),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function annotation(
  caseId: string,
  note: string,
): ApiOperationData<"readAnnotation"> {
  return {
    schema_version: 1,
    annotation_id: `annotation-${caseId}`,
    run_id: "run-1",
    case_id: caseId,
    note,
    content_hash: "a".repeat(64),
    created_at: "2026-10-11T00:00:00Z",
    replayed: false,
  };
}

it("does not publish an obsolete annotation list across A-to-B-to-A scope changes", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const pending: Array<
    ReturnType<typeof deferred<ApiResult<ApiOperationData<"listAnnotations">>>>
  > = [];
  const operations = {
    ...disconnectedWorkspace.debugging.annotations,
    list: () => {
      const request =
        deferred<ApiResult<ApiOperationData<"listAnnotations">>>();
      pending.push(request);
      return request.promise;
    },
  };
  const props = {
    registrationId: "registration-1",
    runId: "run-1",
    operations,
    navigation,
    onClose: () => undefined,
  };
  const tree = render(<AnnotationSheet {...props} caseId="case-A" />);
  try {
    await waitFor(() => expect(pending).toHaveLength(1));
    tree.rerender(<AnnotationSheet {...props} caseId="case-B" />);
    await waitFor(() => expect(pending).toHaveLength(2));
    tree.rerender(<AnnotationSheet {...props} caseId="case-A" />);
    await waitFor(() => expect(pending).toHaveLength(3));

    pending[0]?.resolve({
      data: {
        items: [annotation("case-A", "stale A1")],
        next_cursor: null,
        total: "1",
      },
      warnings: [],
    });
    pending[1]?.resolve({
      data: {
        items: [annotation("case-B", "stale B")],
        next_cursor: null,
        total: "1",
      },
      warnings: [],
    });
    await Promise.resolve();
    expect(screen.queryByText("stale A1")).toBeNull();
    expect(screen.queryByText("stale B")).toBeNull();

    pending[2]?.resolve({
      data: {
        items: [annotation("case-A", "current A2")],
        next_cursor: null,
        total: "1",
      },
      warnings: [],
    });
    expect(await screen.findByText("current A2")).toBeTruthy();
    expect(screen.queryByText("stale A1")).toBeNull();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("replays the exact annotation once and keeps a receipt when the follow-up list read fails", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const requests: Parameters<
    typeof disconnectedWorkspace.debugging.annotations.add
  >[0][] = [];
  let listReads = 0;
  let writes = 0;
  const operations = {
    ...disconnectedWorkspace.debugging.annotations,
    list: async () => {
      listReads += 1;
      if (listReads === 2) {
        throw new ApiError("read_unavailable", "read unavailable", 503);
      }
      return {
        data: {
          items: listReads >= 3 ? [annotation("case-A", "saved note")] : [],
          next_cursor: null,
          total: listReads >= 3 ? "1" : "0",
        },
        warnings: [],
      };
    },
    add: async (request: (typeof requests)[number]) => {
      requests.push(request);
      writes += 1;
      if (writes === 1) throw new Error("connection closed after send");
      return {
        data: annotation("case-A", request.body.note),
        warnings: [],
      };
    },
  };
  const tree = render(
    <AnnotationSheet
      registrationId="registration-1"
      runId="run-1"
      caseId="case-A"
      operations={operations}
      navigation={navigation}
      onClose={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await waitFor(() => expect(listReads).toBe(1));
    await user.type(screen.getByLabelText("Note"), "human note");
    const save = screen.getByRole("button", { name: "Save annotation" });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: "Retry original unchanged annotation",
        }),
      ).toBeTruthy(),
    );
    expect(requests).toHaveLength(1);
    const original = requests[0];
    if (!original) throw new Error("The annotation request was not captured.");
    await user.click(
      screen.getByRole("button", {
        name: "Retry original unchanged annotation",
      }),
    );
    const receiptStatus = await screen.findByRole("status");
    expect(receiptStatus.textContent).toContain(
      "Annotation annotation-case-A is saved",
    );
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "read unavailable",
      ),
    );
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(original);
    await user.click(
      screen.getByRole("button", { name: "Refresh annotations" }),
    );
    expect(await screen.findByText("saved note")).toBeTruthy();
    expect(writes).toBe(2);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

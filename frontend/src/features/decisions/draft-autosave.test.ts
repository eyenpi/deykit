import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { DraftAutosaveController } from "./draft-autosave";

afterEach(() => vi.useRealTimers());

describe("draft autosave sequencing", () => {
  it("sends newer typing after an older acknowledgement with the advanced ETag", async () => {
    vi.useFakeTimers();
    let releaseFirst!: () => void;
    const first = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    const calls: Array<{
      editorSource: string;
      expectedDraftEtag: string;
      operationId: string;
    }> = [];
    const controller = new DraftAutosaveController(
      "e0",
      async (request) => {
        calls.push(request);
        if (calls.length === 1) await first;
        return { etag: `e${calls.length}` };
      },
      () => undefined,
      (() => {
        let next = 0;
        return () => `op-${++next}`;
      })(),
    );

    controller.edit("older source");
    await vi.advanceTimersByTimeAsync(500);
    controller.edit("newer source");
    releaseFirst();
    await controller.flush();

    expect(
      calls.map((call) => [call.editorSource, call.expectedDraftEtag]),
    ).toEqual([
      ["older source", "e0"],
      ["newer source", "e1"],
    ]);
    expect(calls[0].operationId).not.toBe(calls[1].operationId);
    controller.dispose();
  });

  it("keeps an uncertain request and ETag for deliberate unchanged replay", async () => {
    vi.useFakeTimers();
    const calls: Array<{
      editorSource: string;
      expectedDraftEtag: string;
      operationId: string;
    }> = [];
    const controller = new DraftAutosaveController(
      "e0",
      async (request) => {
        calls.push(request);
        if (calls.length === 1)
          throw new ApiError("service_unavailable", "Unknown outcome.", 503);
        return { etag: "e1" };
      },
      () => undefined,
      () => "same-op",
    );
    controller.edit("exact source");
    await vi.advanceTimersByTimeAsync(500);
    expect(controller.status.kind).toBe("outcome-unknown");
    await controller.retryUnchanged();
    expect(calls[1]).toEqual(calls[0]);
    controller.dispose();
  });

  it("treats malformed success replies as unknown and replays once before newer typing", async () => {
    vi.useFakeTimers();
    let releaseRetry!: () => void;
    const retryBarrier = new Promise<void>((resolve) => {
      releaseRetry = resolve;
    });
    const calls: Array<{
      editorSource: string;
      expectedDraftEtag: string;
      operationId: string;
    }> = [];
    const controller = new DraftAutosaveController(
      "e0",
      async (request) => {
        calls.push(request);
        if (calls.length === 1)
          throw new ApiError(
            "response_invalid",
            "The success response was malformed.",
            200,
          );
        if (calls.length === 2) await retryBarrier;
        return { etag: `e${calls.length}` };
      },
      () => undefined,
      (() => {
        let next = 0;
        return () => `op-${++next}`;
      })(),
    );
    controller.edit("sent source");
    await vi.advanceTimersByTimeAsync(500);
    expect(controller.status.kind).toBe("outcome-unknown");
    controller.edit("newer typing");
    const firstRetry = controller.retryUnchanged();
    const duplicateRetry = controller.retryUnchanged();
    await Promise.resolve();
    expect(calls).toHaveLength(2);
    expect(calls[1]).toEqual(calls[0]);
    releaseRetry();
    await Promise.all([firstRetry, duplicateRetry]);
    expect(
      calls.map(({ editorSource, expectedDraftEtag }) => [
        editorSource,
        expectedDraftEtag,
      ]),
    ).toEqual([
      ["sent source", "e0"],
      ["sent source", "e0"],
      ["newer typing", "e2"],
    ]);
    expect(controller.status.kind).toBe("saved");
    controller.dispose();
  });

  it("keeps a confirmed validation rejection distinct from an unknown write", async () => {
    vi.useFakeTimers();
    const controller = new DraftAutosaveController(
      "e0",
      async () => {
        throw new ApiError("validation_error", "Invalid source.", 422);
      },
      () => undefined,
    );
    controller.edit("invalid but retained");
    await vi.advanceTimersByTimeAsync(500);
    expect(controller.status.kind).toBe("failed");
    controller.dispose();
  });

  it("holds newer typing until a committed version supplies its new draft ETag", async () => {
    vi.useFakeTimers();
    const calls: Array<{
      editorSource: string;
      expectedDraftEtag: string;
      operationId: string;
    }> = [];
    let nextOperation = 0;
    const controller = new DraftAutosaveController(
      "draft-before-version",
      async (request) => {
        calls.push(request);
        return { etag: `draft-after-save-${calls.length}` };
      },
      () => undefined,
      () => `op-${++nextOperation}`,
    );

    expect(controller.holdVersionBaseline()).toBe(true);
    controller.edit('{"newer":true}');
    await vi.advanceTimersByTimeAsync(1_000);
    expect(calls).toHaveLength(0);

    expect(
      controller.adoptVersionBaseline(
        "draft-before-version",
        "draft-after-version",
      ),
    ).toBe(true);
    await vi.advanceTimersByTimeAsync(500);
    await controller.flush();

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      editorSource: '{"newer":true}',
      expectedDraftEtag: "draft-after-version",
      operationId: "op-1",
    });
    controller.dispose();
  });

  it("refuses a version hold while a draft write is in flight and recovers after it settles", async () => {
    vi.useFakeTimers();
    let releaseDraft!: () => void;
    const draftBarrier = new Promise<void>((resolve) => {
      releaseDraft = resolve;
    });
    const calls: Array<{
      editorSource: string;
      expectedDraftEtag: string;
      operationId: string;
    }> = [];
    const controller = new DraftAutosaveController(
      "draft-before-version",
      async (request) => {
        calls.push(request);
        if (calls.length === 1) await draftBarrier;
        return { etag: `draft-${calls.length}` };
      },
      () => undefined,
      () => "stable-operation",
    );

    controller.edit("committed draft");
    await vi.advanceTimersByTimeAsync(500);
    expect(calls).toHaveLength(1);
    expect(controller.holdVersionBaseline()).toBe(false);
    releaseDraft();
    await controller.flush();
    expect(controller.holdVersionBaseline()).toBe(true);
    expect(
      controller.adoptVersionBaseline("draft-before-version", "draft-next"),
    ).toBe(false);
    expect(calls).toHaveLength(1);
    controller.releaseVersionBaseline();
    controller.dispose();
  });

  it("reapplies the retained opaque source only after deliberate version review", async () => {
    vi.useFakeTimers();
    const calls: Array<{
      editorSource: string;
      expectedDraftEtag: string;
      operationId: string;
    }> = [];
    const controller = new DraftAutosaveController(
      "draft-before-version",
      async (request) => {
        calls.push(request);
        return { etag: "draft-after-reapply" };
      },
      () => undefined,
      () => "review-reapply-operation",
    );

    expect(controller.holdVersionBaseline()).toBe(true);
    controller.reapplyAfterReview("draft-after-external-change", '{  "n":1 }');
    expect(calls).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(500);
    await controller.flush();

    expect(calls).toEqual([
      {
        editorSource: '{  "n":1 }',
        expectedDraftEtag: "draft-after-external-change",
        operationId: "review-reapply-operation",
      },
    ]);
    controller.dispose();
  });
});

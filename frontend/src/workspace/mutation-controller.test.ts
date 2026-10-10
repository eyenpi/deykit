import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { isOutcomeUnknown, RetainedMutation } from "./mutation-controller";

describe("retained mutation outcomes", () => {
  it("keeps malformed acknowledgements and untyped transport failures unknown", async () => {
    for (const failure of [
      new ApiError("response_invalid", "Malformed success.", 200),
      new Error("connection reset after the write"),
    ]) {
      expect(isOutcomeUnknown(failure)).toBe(true);
      const mutation = new RetainedMutation(
        async () => {
          throw failure;
        },
        () => undefined,
      );
      const request = {
        operationId: "op-original",
        etag: "e0",
        source: "exact source",
      };
      await mutation.submit(request);
      expect(mutation.state.kind).toBe("outcome-unknown");
      expect(mutation.originalRequest).toEqual(request);
    }
  });

  it("distinguishes confirmed validation errors and ETag conflicts", async () => {
    const validation = new RetainedMutation(
      async () => {
        throw new ApiError("validation_error", "Invalid input.", 422);
      },
      () => undefined,
    );
    await validation.submit({ operationId: "op-validation" });
    expect(validation.state.kind).toBe("failed");

    const conflict = new RetainedMutation(
      async () => {
        throw new ApiError("conflict", "The source changed.", 409);
      },
      () => undefined,
    );
    await conflict.submit({ operationId: "op-conflict" });
    expect(conflict.state.kind).toBe("conflict");
  });

  it("replays the retained request once after an explicit retry", async () => {
    let release!: () => void;
    const barrier = new Promise<void>((resolve) => {
      release = resolve;
    });
    const calls: Array<{ operationId: string; etag: string; source: string }> =
      [];
    const mutation = new RetainedMutation(
      async (request: (typeof calls)[number]) => {
        calls.push(request);
        if (calls.length === 1)
          throw new ApiError("service_unavailable", "Unknown result.");
        if (calls.length === 2) await barrier;
        return { saved: true };
      },
      () => undefined,
    );
    const request = {
      operationId: "op-same",
      etag: "e0",
      source: "exact source",
    };
    await mutation.submit(request);
    const first = mutation.retryOriginal();
    const duplicate = mutation.retryOriginal();
    await Promise.resolve();
    expect(calls).toEqual([request, request]);
    release();
    await Promise.all([first, duplicate]);
    expect(calls).toEqual([request, request]);
    expect(mutation.state.kind).toBe("committed");
  });
});

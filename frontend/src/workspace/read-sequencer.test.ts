import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { RegistrationReadSequencer } from "./read-sequencer";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

describe("registration read sequencing", () => {
  it("serializes reads for one registration while allowing another through", async () => {
    const sequencer = new RegistrationReadSequencer();
    const held = deferred<string>();
    const calls: string[] = [];
    const first = sequencer.enqueueRead("registration-a", undefined, () => {
      calls.push("first-start");
      return held.promise;
    });
    const second = sequencer.enqueueRead("registration-a", undefined, () => {
      calls.push("second-start");
      return Promise.resolve("second");
    });
    const independent = sequencer.enqueueRead(
      "registration-b",
      undefined,
      () => {
        calls.push("other-registration");
        return Promise.resolve("independent");
      },
    );

    await independent;
    await Promise.resolve();
    expect(calls).toEqual(["first-start", "other-registration"]);
    held.resolve("first");
    await expect(first).resolves.toBe("first");
    await expect(second).resolves.toBe("second");
    expect(calls).toEqual([
      "first-start",
      "other-registration",
      "second-start",
    ]);
  });

  it("skips a queued read whose caller has aborted", async () => {
    const sequencer = new RegistrationReadSequencer();
    const held = deferred<string>();
    const controller = new AbortController();
    const first = sequencer.enqueueRead(
      "registration",
      undefined,
      () => held.promise,
    );
    let dispatched = 0;
    const queued = sequencer.enqueueRead(
      "registration",
      controller.signal,
      async () => {
        dispatched += 1;
        return "unexpected";
      },
    );
    controller.abort();
    held.resolve("complete");
    await first;
    await expect(queued).rejects.toMatchObject({ code: "cancelled" });
    expect(dispatched).toBe(0);
  });

  it("holds the lane through an admitted read after abort and suppresses delivery", async () => {
    const sequencer = new RegistrationReadSequencer();
    const responseAndParsedBody = deferred<string>();
    const controller = new AbortController();
    const calls: string[] = [];
    const admitted = sequencer.enqueueRead(
      "registration",
      controller.signal,
      () => {
        calls.push("request-started");
        return responseAndParsedBody.promise;
      },
    );
    const next = sequencer.enqueueRead("registration", undefined, () => {
      calls.push("next-request-started");
      return Promise.resolve("next");
    });

    await Promise.resolve();
    controller.abort();
    await Promise.resolve();
    expect(calls).toEqual(["request-started"]);
    responseAndParsedBody.resolve("parsed response");
    await expect(admitted).rejects.toMatchObject({ code: "cancelled" });
    await expect(next).resolves.toBe("next");
    expect(calls).toEqual(["request-started", "next-request-started"]);
  });

  it("recovers after a failed read without automatically retrying it", async () => {
    const sequencer = new RegistrationReadSequencer();
    const failure = new ApiError("conflict", "The source changed.", 409);
    let attempts = 0;
    const failed = sequencer.enqueueRead("registration", undefined, () => {
      attempts += 1;
      return Promise.reject(failure);
    });
    const next = sequencer.enqueueRead("registration", undefined, () => {
      attempts += 1;
      return Promise.resolve("later deliberate read");
    });

    await expect(failed).rejects.toBe(failure);
    await expect(next).resolves.toBe("later deliberate read");
    expect(attempts).toBe(2);
  });
});

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

describe("registration source sequencing", () => {
  it("serializes reads and writes for one registration while allowing another through", async () => {
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
    const write = sequencer.enqueueMutation("registration-a", undefined, () => {
      calls.push("write-start");
      return Promise.resolve("write");
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
    await expect(write).resolves.toBe("write");
    expect(calls).toEqual([
      "first-start",
      "other-registration",
      "second-start",
      "write-start",
    ]);
  });

  it("serializes a read behind an admitted write", async () => {
    const sequencer = new RegistrationReadSequencer();
    const writeResponse = deferred<string>();
    const calls: string[] = [];
    const write = sequencer.enqueueMutation("registration", undefined, () => {
      calls.push("write-start");
      return writeResponse.promise;
    });
    const read = sequencer.enqueueRead("registration", undefined, () => {
      calls.push("read-start");
      return Promise.resolve("current source");
    });

    await Promise.resolve();
    expect(calls).toEqual(["write-start"]);
    writeResponse.resolve("receipt");
    await expect(write).resolves.toBe("receipt");
    await expect(read).resolves.toBe("current source");
    expect(calls).toEqual(["write-start", "read-start"]);
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

  it("preserves an admitted mutation receipt after caller abort and holds its lane", async () => {
    const sequencer = new RegistrationReadSequencer();
    const responseAndParsedBody = deferred<string>();
    const controller = new AbortController();
    const calls: string[] = [];
    const admitted = sequencer.enqueueMutation(
      "registration",
      controller.signal,
      () => {
        calls.push("mutation-started");
        return responseAndParsedBody.promise;
      },
    );
    const next = sequencer.enqueueRead("registration", undefined, () => {
      calls.push("next-read-started");
      return Promise.resolve("read");
    });

    await Promise.resolve();
    controller.abort();
    await Promise.resolve();
    expect(calls).toEqual(["mutation-started"]);
    responseAndParsedBody.resolve("receipt");
    await expect(admitted).resolves.toBe("receipt");
    await expect(next).resolves.toBe("read");
    expect(calls).toEqual(["mutation-started", "next-read-started"]);
  });

  it("preserves an admitted mutation rejection after caller abort and recovers the lane", async () => {
    const sequencer = new RegistrationReadSequencer();
    const rejectedResponse = deferred<string>();
    const controller = new AbortController();
    const rejection = new ApiError("conflict", "Current source changed.", 409);
    const admitted = sequencer.enqueueMutation(
      "registration",
      controller.signal,
      () => rejectedResponse.promise,
    );
    const next = sequencer.enqueueMutation("registration", undefined, () =>
      Promise.resolve("later deliberate mutation"),
    );

    await Promise.resolve();
    controller.abort();
    rejectedResponse.reject(rejection);
    await expect(admitted).rejects.toBe(rejection);
    await expect(next).resolves.toBe("later deliberate mutation");
  });

  it("keeps an uncertain admitted mutation error intact until its lane settles", async () => {
    const sequencer = new RegistrationReadSequencer();
    const rejectedResponse = deferred<string>();
    const controller = new AbortController();
    const rejection = new Error("connection ended after dispatch");
    const calls: string[] = [];
    const admitted = sequencer.enqueueMutation(
      "registration",
      controller.signal,
      () => {
        calls.push("mutation-started");
        return rejectedResponse.promise;
      },
    );
    const next = sequencer.enqueueRead("registration", undefined, () => {
      calls.push("next-read-started");
      return Promise.resolve("read");
    });

    await Promise.resolve();
    controller.abort();
    expect(calls).toEqual(["mutation-started"]);
    rejectedResponse.reject(rejection);
    await expect(admitted).rejects.toBe(rejection);
    await expect(next).resolves.toBe("read");
    expect(calls).toEqual(["mutation-started", "next-read-started"]);
  });

  it("marks a queued aborted mutation as not admitted and never dispatches it", async () => {
    const sequencer = new RegistrationReadSequencer();
    const held = deferred<string>();
    const controller = new AbortController();
    const first = sequencer.enqueueRead(
      "registration",
      undefined,
      () => held.promise,
    );
    let dispatched = 0;
    const queued = sequencer.enqueueMutation(
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
    await expect(queued).rejects.toMatchObject({
      name: "QueuedMutationNotAdmitted",
    });
    expect(dispatched).toBe(0);
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

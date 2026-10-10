import { ApiError } from "../api/client";
import { QueuedMutationNotAdmitted } from "./mutation-controller";

/** Serializes source operations which address the same open project registration. */
export class RegistrationReadSequencer {
  private readonly tails = new Map<string, Promise<void>>();

  enqueueRead<T>(
    registrationId: string,
    callerSignal: AbortSignal | undefined,
    perform: () => Promise<T>,
  ): Promise<T> {
    return this.enqueue(registrationId, callerSignal, "read", perform);
  }

  enqueueMutation<T>(
    registrationId: string,
    callerSignal: AbortSignal | undefined,
    perform: () => Promise<T>,
  ): Promise<T> {
    return this.enqueue(registrationId, callerSignal, "mutation", perform);
  }

  private enqueue<T>(
    registrationId: string,
    callerSignal: AbortSignal | undefined,
    mode: "read" | "mutation",
    perform: () => Promise<T>,
  ): Promise<T> {
    const previous = this.tails.get(registrationId) ?? Promise.resolve();
    const result = previous.then(async () => {
      if (callerSignal?.aborted) {
        if (mode === "mutation") throw new QueuedMutationNotAdmitted();
        throw cancelledRead();
      }
      try {
        const value = await perform();
        if (mode === "read" && callerSignal?.aborted) throw cancelledRead();
        return value;
      } catch (cause) {
        if (mode === "read" && callerSignal?.aborted) throw cancelledRead();
        throw cause;
      }
    });
    const tail = result.then(
      () => undefined,
      () => undefined,
    );
    this.tails.set(registrationId, tail);
    void tail.then(() => {
      if (this.tails.get(registrationId) === tail)
        this.tails.delete(registrationId);
    });
    return result;
  }
}

function cancelledRead(): ApiError {
  return new ApiError("cancelled", "The request was cancelled.");
}

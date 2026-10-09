import { ApiError } from "../api/client";

export type MutationState<Receipt> =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "committed"; receipt: Receipt }
  | { kind: "conflict"; message: string }
  | { kind: "failed"; message: string }
  | { kind: "outcome-unknown"; message: string };

function definitelyRejected(cause: unknown): cause is ApiError {
  return cause instanceof ApiError && (
    (cause.status !== undefined && cause.status >= 400 && cause.status < 500 &&
      cause.status !== 408 && cause.status !== 425 && cause.status !== 429) ||
    ["invalid_operation", "invalid_request", "invalid_path", "invalid_query", "invalid_body", "session_required"].includes(cause.code)
  );
}

export function isOutcomeUnknown(cause: unknown): boolean {
  return !(cause instanceof ApiError && (cause.status === 409 || cause.code === "conflict")) &&
    !definitelyRejected(cause);
}

function stateForFailure<Receipt>(cause: unknown): MutationState<Receipt> {
  const message = cause instanceof Error ? cause.message : "The change could not be saved.";
  if (cause instanceof ApiError && (cause.status === 409 || cause.code === "conflict"))
    return { kind: "conflict", message };
  if (isOutcomeUnknown(cause))
    return {
      kind: "outcome-unknown",
      message: "The service may have saved this change. Review its current state before retrying.",
    };
  return { kind: "failed", message };
}

/** Retains the exact request and operation identity until its outcome is known. */
export class RetainedMutation<Request, Receipt> {
  #send: (request: Request) => Promise<Receipt>;
  #publish: (state: MutationState<Receipt>) => void;
  #request: Request | undefined;
  #state: MutationState<Receipt> = { kind: "idle" };
  #flight: Promise<Receipt | undefined> | undefined;

  constructor(
    send: (request: Request) => Promise<Receipt>,
    publish: (state: MutationState<Receipt>) => void,
  ) {
    this.#send = send;
    this.#publish = publish;
  }

  get state(): MutationState<Receipt> {
    return this.#state;
  }

  get originalRequest(): Request | undefined {
    return this.#request;
  }

  submit(request: Request): Promise<Receipt | undefined> {
    if (this.#flight) return this.#flight;
    if (this.#state.kind !== "idle") return Promise.resolve(undefined);
    this.#request = request;
    return this.#dispatch(request);
  }

  retryOriginal(): Promise<Receipt | undefined> {
    if (this.#flight) return this.#flight;
    if (this.#state.kind !== "outcome-unknown" || this.#request === undefined)
      return Promise.resolve(undefined);
    return this.#dispatch(this.#request);
  }

  reset(): void {
    if (this.#flight) return;
    this.#request = undefined;
    this.#setState({ kind: "idle" });
  }

  async #dispatch(request: Request): Promise<Receipt | undefined> {
    this.#setState({ kind: "submitting" });
    const flight = this.#send(request).then(
      (receipt) => {
        this.#setState({ kind: "committed", receipt });
        return receipt;
      },
      (cause: unknown) => {
        this.#setState(stateForFailure(cause));
        return undefined;
      },
    );
    this.#flight = flight.finally(() => {
      this.#flight = undefined;
    });
    return this.#flight;
  }

  #setState(state: MutationState<Receipt>): void {
    this.#state = state;
    this.#publish(state);
  }
}

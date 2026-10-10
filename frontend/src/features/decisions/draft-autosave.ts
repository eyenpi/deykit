import { ApiError } from "../../api/client";
import { isQueuedMutationNotAdmitted } from "../../workspace/mutation-controller";

export type DraftSaveStatus =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "failed"; message: string }
  | { kind: "conflict"; message: string }
  | { kind: "outcome-unknown"; message: string };

export interface DraftSaveRequest {
  editorSource: string;
  expectedDraftEtag: string;
  operationId: string;
}

export interface DraftSaveReceipt {
  etag: string;
}

type SendDraft = (request: DraftSaveRequest) => Promise<DraftSaveReceipt>;
type StatusListener = (status: DraftSaveStatus) => void;
type PendingSource = { source: string; sequence: number };

function failureStatus(cause: unknown): DraftSaveStatus {
  if (isQueuedMutationNotAdmitted(cause))
    return { kind: "failed", message: cause.message };
  if (
    cause instanceof ApiError &&
    (cause.status === 409 || cause.code === "conflict")
  ) {
    return { kind: "conflict", message: cause.message };
  }
  const definitelyRejected =
    cause instanceof ApiError &&
    ((cause.status !== undefined &&
      cause.status >= 400 &&
      cause.status < 500 &&
      cause.status !== 408 &&
      cause.status !== 425 &&
      cause.status !== 429) ||
      [
        "invalid_operation",
        "invalid_request",
        "invalid_path",
        "invalid_query",
        "invalid_body",
        "session_required",
      ].includes(cause.code));
  return definitelyRejected
    ? { kind: "failed", message: cause.message }
    : {
        kind: "outcome-unknown",
        message:
          "The save may have reached the service. Review the saved draft before retrying.",
      };
}

/** Serial 500 ms draft saves. Acknowledgements advance the ETag, never editor text. */
export class DraftAutosaveController {
  #send: SendDraft;
  #listen: StatusListener;
  #makeOperationId: () => string;
  #baseEtag: string;
  #latest: PendingSource | undefined;
  #timer: ReturnType<typeof setTimeout> | undefined;
  #inFlight: Promise<void> | undefined;
  #retryFlight: Promise<void> | undefined;
  #lastRequest: DraftSaveRequest | undefined;
  #lastRequestSequence: number | undefined;
  #sequence = 0;
  #status: DraftSaveStatus = { kind: "idle" };
  #stopped = false;

  constructor(
    initialEtag: string,
    send: SendDraft,
    listen: StatusListener,
    makeOperationId: () => string = () => crypto.randomUUID(),
  ) {
    this.#baseEtag = initialEtag;
    this.#send = send;
    this.#listen = listen;
    this.#makeOperationId = makeOperationId;
  }

  get status(): DraftSaveStatus {
    return this.#status;
  }

  edit(source: string): void {
    this.#sequence += 1;
    this.#latest = { source, sequence: this.#sequence };
    if (this.#stopped) return;
    if (this.#timer !== undefined) clearTimeout(this.#timer);
    this.#setStatus({ kind: "idle" });
    this.#timer = setTimeout(() => {
      this.#timer = undefined;
      void this.#drain();
    }, 500);
  }

  async flush(): Promise<void> {
    if (this.#timer !== undefined) {
      clearTimeout(this.#timer);
      this.#timer = undefined;
    }
    await this.#drain();
    if (
      this.#status.kind === "conflict" ||
      this.#status.kind === "outcome-unknown"
    ) {
      throw new Error(this.#status.message);
    }
    if (this.#status.kind === "failed") throw new Error(this.#status.message);
  }

  /** Replays the exact uncertain request and precondition after explicit user action. */
  retryUnchanged(): Promise<void> {
    if (this.#retryFlight) return this.#retryFlight;
    if (this.#inFlight) return this.#inFlight;
    if (this.#status.kind !== "outcome-unknown" || !this.#lastRequest)
      return Promise.resolve();
    const request = this.#lastRequest;
    const task = (async () => {
      const original = this.#sendOriginal(request);
      this.#inFlight = original;
      await original;
      if (this.#inFlight === original) this.#inFlight = undefined;
      if (
        this.#status.kind === "saved" &&
        !this.#stopped &&
        this.#latest &&
        this.#lastRequestSequence !== this.#latest.sequence
      )
        await this.#drain();
    })();
    this.#retryFlight = task.finally(() => {
      this.#retryFlight = undefined;
    });
    return this.#retryFlight;
  }

  /** Reapply retained editor text after a deliberate read/review of current state. */
  reapplyAfterReview(currentEtag: string): void {
    this.#baseEtag = currentEtag;
    this.#stopped = false;
    if (!this.#latest) return;
    this.#setStatus({ kind: "idle" });
    if (this.#timer !== undefined) clearTimeout(this.#timer);
    this.#timer = setTimeout(() => {
      this.#timer = undefined;
      void this.#drain();
    }, 500);
  }

  dispose(): void {
    if (this.#timer !== undefined) clearTimeout(this.#timer);
    this.#timer = undefined;
  }

  async #drain(): Promise<void> {
    if (this.#inFlight) {
      await this.#inFlight;
      if (this.#stopped || !this.#latest) return;
      if (
        this.#status.kind === "conflict" ||
        this.#status.kind === "outcome-unknown"
      )
        return;
      return this.#drain();
    }
    if (this.#stopped || !this.#latest) return;
    const pending = this.#latest;
    const request: DraftSaveRequest = {
      editorSource: pending.source,
      expectedDraftEtag: this.#baseEtag,
      operationId: this.#makeOperationId(),
    };
    this.#lastRequest = request;
    this.#lastRequestSequence = pending.sequence;
    this.#inFlight = this.#sendOriginal(request).finally(() => {
      this.#inFlight = undefined;
    });
    await this.#inFlight;
    if (
      !this.#stopped &&
      this.#latest &&
      this.#latest.sequence > pending.sequence
    )
      await this.#drain();
  }

  async #sendOriginal(request: DraftSaveRequest): Promise<void> {
    this.#setStatus({ kind: "saving" });
    try {
      const receipt = await this.#send(request);
      this.#baseEtag = receipt.etag;
      this.#stopped = false;
      this.#setStatus({ kind: "saved" });
      if (
        this.#lastRequest === request &&
        this.#latest &&
        this.#lastRequestSequence === this.#latest.sequence
      )
        this.#latest = undefined;
    } catch (cause) {
      this.#stopped = true;
      this.#setStatus(failureStatus(cause));
    }
  }

  #setStatus(status: DraftSaveStatus): void {
    this.#status = status;
    this.#listen(status);
  }
}

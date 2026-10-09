/** User-authored JSON is always source text. Never parse it in the browser. */
export interface JsonSource {
  source_text: string;
}
export type Decoder<T> = (value: unknown) => T;
import validators from "./generated/validators.cjs";
import type { components } from "./generated/openapi";
export type ApiWarning = components["schemas"]["ErrorDTO"];
export type ApiSelection = components["schemas"]["SelectionDetails"];
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
    public readonly reason?: string | null,
    public readonly resource_id?: string | null,
    public readonly row?: number | null,
    public readonly correlation_id?: string | null,
    public readonly selection?: ApiSelection | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  query?: { cursor?: string; limit?: number };
}
export interface ApiResult<T> {
  data: T;
  warnings: readonly ApiWarning[];
  revision?: string;
}
export function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(
      "response_invalid",
      "The local service returned an unsupported response.",
    );
  return value as Record<string, unknown>;
}
export function jsonSource(value: unknown): JsonSource {
  const record = object(value);
  if (typeof record.source_text !== "string")
    throw new ApiError(
      "response_invalid",
      "The local service did not return JSON source text.",
    );
  return { source_text: record.source_text };
}
/** Only safe, structured server errors are shown; raw bodies/headers are never reflected. */
export class ApiClient {
  #capability: string | undefined;
  #connecting: Promise<void> | undefined;
  #reconnecting: Promise<void> | undefined;
  #sessionGeneration = 0;
  constructor(
    private readonly transport: typeof fetch = globalThis.fetch.bind(
      globalThis,
    ),
    private readonly currentOrigin: () => string = () =>
      globalThis.location.origin,
  ) {}
  setCapability(capability: string | undefined) {
    this.#sessionGeneration += 1;
    this.#capability = capability;
    this.#connecting = undefined;
  }
  async connect(): Promise<void> {
    if (this.#capability) return;
    if (!this.#connecting) {
      const generation = this.#sessionGeneration;
      const connecting = this.#bootstrap(generation).finally(() => {
        if (this.#connecting === connecting) this.#connecting = undefined;
      });
      this.#connecting = connecting;
    }
    await this.#connecting;
  }
  async reconnect(): Promise<void> {
    if (!this.#reconnecting) {
      this.#sessionGeneration += 1;
      this.#capability = undefined;
      this.#connecting = undefined;
      this.#reconnecting = this.connect().finally(() => {
        this.#reconnecting = undefined;
      });
    }
    await this.#reconnecting;
  }
  async #bootstrap(generation: number): Promise<void> {
    let response: Response;
    try {
      response = await this.transport("/api/v1/session/bootstrap", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Deykit-Bootstrap": "1",
        },
        body: JSON.stringify({ schema_version: 1 }),
        mode: "cors",
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
      });
    } catch {
      throw new ApiError(
        "service_unavailable",
        "Cannot connect to the local workspace service. Check that it is running and try again.",
      );
    }
    const envelope = await this.#envelope(response);
    if (!response.ok || "error" in envelope)
      throw this.#failure(envelope, response.status);
    if (!validators.validateSuccess_BootstrapReply_(envelope))
      throw new ApiError(
        "response_invalid",
        "The local service returned an invalid session response.",
        response.status,
      );
    const reply = object(envelope.data);
    if (
      typeof reply.capability !== "string" ||
      !/^[A-Za-z0-9_-]{43}$/.test(reply.capability) ||
      reply.origin !== this.currentOrigin()
    )
      throw new ApiError(
        "response_invalid",
        "The local service returned an invalid session response.",
        response.status,
      );
    if (generation === this.#sessionGeneration)
      this.#capability = reply.capability;
  }
  async request<T>(
    path: string,
    decode: Decoder<T>,
    options: RequestOptions = {},
  ): Promise<ApiResult<T>> {
    if (!/^\/api\/v1\/[a-zA-Z0-9/_-]+$/.test(path) || path.includes("//"))
      throw new ApiError(
        "invalid_path",
        "Only local API resource paths are supported.",
      );
    await this.connect();
    if (!this.#capability)
      throw new ApiError(
        "session_required",
        "Connect to the local workspace service.",
      );
    const headers = new Headers({
      Accept: "application/json",
      "X-Deykit-Capability": this.#capability,
    });
    if (options.body !== undefined)
      headers.set("Content-Type", "application/json");
    const query = new URLSearchParams();
    if (options.query?.cursor !== undefined)
      query.set("cursor", options.query.cursor);
    if (options.query?.limit !== undefined) {
      if (
        !Number.isSafeInteger(options.query.limit) ||
        options.query.limit < 1
      ) {
        throw new ApiError(
          "invalid_query",
          "The page limit must be a positive integer.",
        );
      }
      query.set("limit", String(options.query.limit));
    }
    const destination = query.size ? `${path}?${query}` : path;
    let response: Response;
    try {
      response = await this.transport(destination, {
        method: options.method ?? "GET",
        headers,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
        mode: "cors",
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
      });
    } catch {
      if (options.signal?.aborted)
        throw new ApiError("cancelled", "The request was cancelled.");
      throw new ApiError(
        "service_unavailable",
        "Cannot reach the local workspace service. Check that it is running and try again.",
      );
    }
    const envelope = await this.#envelope(response);
    if (!response.ok || "error" in envelope)
      throw this.#failure(envelope, response.status);
    if (
      Object.keys(envelope).some(
        (key) => !["schema_version", "data", "warnings"].includes(key),
      )
    )
      throw new ApiError(
        "response_invalid",
        "The local service returned an invalid response.",
        response.status,
      );
    const warnings = envelope.warnings ?? [];
    if (
      !Array.isArray(warnings) ||
      !warnings.every((warning) => validators.validateErrorDTO(warning))
    )
      throw new ApiError(
        "response_invalid",
        "The local service returned invalid warnings.",
        response.status,
      );
    return {
      data: decode(envelope.data),
      warnings: warnings as ApiWarning[],
      revision: response.headers.get("ETag") ?? undefined,
    };
  }

  async #envelope(response: Response): Promise<Record<string, unknown>> {
    if (!response.headers.get("content-type")?.includes("application/json"))
      throw new ApiError(
        "response_invalid",
        "The local service returned an unsupported response.",
        response.status,
      );
    let envelope: Record<string, unknown>;
    try {
      envelope = object(await response.json());
    } catch {
      throw new ApiError(
        "response_invalid",
        "The local service returned unreadable data.",
        response.status,
      );
    }
    if (envelope.schema_version !== 1)
      throw new ApiError(
        "response_invalid",
        "The local service uses an unsupported response version.",
        response.status,
      );
    return envelope;
  }

  #failure(envelope: Record<string, unknown>, status: number): ApiError {
    if (!validators.validateFailure(envelope))
      return new ApiError(
        "response_invalid",
        "The local service returned an invalid error.",
        status,
      );
    const error = object(envelope.error);
    return new ApiError(
      typeof error.code === "string" ? error.code : "request_failed",
      typeof error.message === "string"
        ? error.message
        : "The local service could not complete the request.",
      status,
      typeof error.reason === "string" ? error.reason : error.reason === null ? null : undefined,
      typeof error.resource_id === "string"
        ? error.resource_id
        : error.resource_id === null ? null : undefined,
      typeof error.row === "number" && Number.isSafeInteger(error.row)
        ? error.row
        : error.row === null ? null : undefined,
      typeof error.correlation_id === "string"
        ? error.correlation_id
        : error.correlation_id === null ? null : undefined,
      envelope.selection === null
        ? null
        : validators.validateSelectionDetails(envelope.selection)
          ? (envelope.selection as ApiSelection)
          : undefined,
    );
  }
}
export function safeMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "The operation could not be completed. Your changes have been kept.";
}

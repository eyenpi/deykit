/** User-authored JSON is always source text. Never parse it in the browser. */
export interface JsonSource {
  source_text: string;
}
export type Decoder<T> = (value: unknown) => T;
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  expectedRevision?: string;
  operationId?: string;
  signal?: AbortSignal;
  query?: { cursor?: string; limit?: number };
}
export interface ApiResult<T> {
  data: T;
  warnings: readonly string[];
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
  constructor(
    private readonly transport: typeof fetch = globalThis.fetch.bind(
      globalThis,
    ),
  ) {}
  setCapability(capability: string | undefined) {
    this.#capability = capability;
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
    if (!this.#capability)
      throw new ApiError(
        "session_required",
        "Connect to the local workspace service before continuing.",
      );
    const headers = new Headers({
      Accept: "application/json",
      "X-Deykit-Capability": this.#capability,
    });
    if (options.body !== undefined)
      headers.set("Content-Type", "application/json");
    if (options.expectedRevision)
      headers.set("If-Match", options.expectedRevision);
    if (options.operationId)
      headers.set("Idempotency-Key", options.operationId);
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
        credentials: "same-origin",
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
    if (!response.ok || "error" in envelope) {
      const error = object(envelope.error);
      throw new ApiError(
        typeof error.code === "string" ? error.code : "request_failed",
        typeof error.message === "string"
          ? error.message
          : "The local service could not complete the request.",
        response.status,
      );
    }
    if (
      !Array.isArray(envelope.warnings) ||
      !envelope.warnings.every((v) => typeof v === "string")
    )
      throw new ApiError(
        "response_invalid",
        "The local service returned invalid warnings.",
        response.status,
      );
    return {
      data: decode(envelope.data),
      warnings: envelope.warnings,
      revision: response.headers.get("ETag") ?? undefined,
    };
  }
}
export function safeMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "The operation could not be completed. Your changes have been kept.";
}

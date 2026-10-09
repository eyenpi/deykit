/** User-authored JSON is always source text. Never parse it in the browser. */
export interface JsonSource {
  source_text: string;
}
export type Decoder<T> = (value: unknown) => T;
import validators from "./generated/validators.cjs";
import type { components } from "./generated/openapi";
import {
  operationMetadata,
  type ApiDownloadOperationId,
  type ApiJsonOperationId,
  type ApiOperationId,
  type ApiOperationMetadata,
} from "./generated/operations";
import type { operations } from "./generated/openapi";
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
  signal?: AbortSignal;
}
export interface ApiResult<T> {
  data: T;
  warnings: readonly ApiWarning[];
  revision?: string;
}
type ApiOperation<K extends ApiOperationId> = operations[K];
type PathParameters<K extends ApiOperationId> =
  ApiOperation<K> extends {
    parameters: { path?: infer P };
  }
    ? [NonNullable<P>] extends [never]
      ? Record<never, never>
      : NonNullable<P>
    : Record<never, never>;
type QueryParameters<K extends ApiOperationId> =
  ApiOperation<K> extends {
    parameters: { query?: infer Q };
  }
    ? [NonNullable<Q>] extends [never]
      ? Record<never, never>
      : NonNullable<Q>
    : Record<never, never>;
export type ApiOperationBody<K extends ApiOperationId> =
  ApiOperation<K> extends {
    requestBody?: infer R;
  }
    ? NonNullable<R> extends { content: { "application/json": infer B } }
      ? B
      : never
    : never;
type JsonResponse<R> = R extends {
  content: { "application/json": infer E };
}
  ? E
  : never;
type JsonSuccessStatuses<K extends ApiJsonOperationId> =
  (typeof operationMetadata)[K]["success"] extends {
    readonly kind: "json";
    readonly validators: infer V;
  }
    ? keyof V
    : never;
type ResponseForStatus<R, S extends string> = S extends keyof R
  ? R[S]
  : S extends `${infer NumericStatus extends number}`
    ? NumericStatus extends keyof R
      ? R[NumericStatus]
      : never
    : never;
type SuccessEnvelope<K extends ApiJsonOperationId> =
  JsonSuccessStatuses<K> extends infer S
    ? S extends string
      ? JsonResponse<ResponseForStatus<ApiOperation<K>["responses"], S>>
      : never
    : never;
export type ApiOperationData<K extends ApiJsonOperationId> =
  SuccessEnvelope<K> extends { data: infer D } ? D : never;
type PathArgument<K extends ApiOperationId> =
  keyof PathParameters<K> extends never
    ? { path?: never }
    : { path: PathParameters<K> };
type QueryArgument<K extends ApiOperationId> =
  keyof QueryParameters<K> extends never
    ? { query?: never }
    : { query?: Partial<QueryParameters<K>> };
type BodyArgument<K extends ApiOperationId> = [ApiOperationBody<K>] extends [
  never,
]
  ? { body?: never }
  : ApiOperation<K> extends { requestBody: unknown }
    ? { body: ApiOperationBody<K> }
    : { body?: ApiOperationBody<K> };
export type ApiOperationArguments<K extends ApiJsonOperationId> =
  PathArgument<K> & QueryArgument<K> & BodyArgument<K> & RequestOptions;

export type ApiDownloadArguments<K extends ApiDownloadOperationId> =
  PathArgument<K> & { query: QueryParameters<K> } & {
    body?: never;
  } & RequestOptions;
export interface ApiDownload {
  readonly blob: Blob;
  readonly filename: string;
}

const validatorsByName = validators as unknown as Readonly<
  Record<string, (value: unknown) => boolean>
>;

function exactRecord(
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    return false;
  const actual = Reflect.ownKeys(value);
  return (
    actual.length === keys.length &&
    actual.every((key) => typeof key === "string" && keys.includes(key))
  );
}

function apiOperationPath(
  metadata: ApiOperationMetadata,
  value: unknown,
): string {
  if (metadata.pathParams.length === 0 && value === undefined)
    return metadata.path;
  if (!exactRecord(value, metadata.pathParams))
    throw new ApiError(
      "invalid_path",
      "The local API path parameters are invalid.",
    );
  return metadata.path.replace(/\{([^}]+)\}/g, (_match, name: string) => {
    const resourceId = value[name];
    if (
      typeof resourceId !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(resourceId)
    )
      throw new ApiError(
        "invalid_path",
        "The local API path parameters are invalid.",
      );
    return resourceId;
  });
}

function apiOperationQuery(
  metadata: ApiOperationMetadata,
  value: unknown,
): string {
  if (value === undefined) return "";
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(
      "invalid_query",
      "The local API query parameters are invalid.",
    );
  const record = value as Record<string, unknown>;
  if (
    Reflect.ownKeys(record).some(
      (key) => typeof key !== "string" || !metadata.queryParams.includes(key),
    )
  )
    throw new ApiError(
      "invalid_query",
      "The local API query parameters are invalid.",
    );
  const query = new URLSearchParams();
  for (const key of metadata.queryParams) {
    if (!Object.hasOwn(record, key)) continue;
    const item = record[key];
    if (item === undefined) continue;
    if (
      typeof item !== "string" &&
      typeof item !== "boolean" &&
      !(typeof item === "number" && Number.isSafeInteger(item))
    )
      throw new ApiError(
        "invalid_query",
        "The local API query parameters are invalid.",
      );
    query.set(key, String(item));
  }
  return query.size ? `?${query.toString()}` : "";
}

function apiDownloadQuery(
  metadata: ApiOperationMetadata,
  policy: Extract<ApiOperationMetadata["success"], { kind: "report-download" }>,
  value: unknown,
): {
  readonly query: string;
  readonly format: "json" | "markdown";
  readonly contentType: string;
  readonly extension: string;
} {
  if (!exactRecord(value, metadata.queryParams))
    throw new ApiError(
      "invalid_query",
      "The local API query parameters are invalid.",
    );
  const format = value[policy.formatParameter];
  if (format !== "json" && format !== "markdown")
    throw new ApiError(
      "invalid_query",
      "The local API query parameters are invalid.",
    );
  const selected = policy.formats[format];
  return {
    query: apiOperationQuery(metadata, value),
    format,
    contentType: selected.contentType,
    extension: selected.extension,
  };
}

function apiOperationBody(
  metadata: ApiOperationMetadata,
  value: unknown,
): void {
  if (metadata.bodyValidator === null) {
    if (value !== undefined)
      throw new ApiError(
        "invalid_body",
        "This local API operation does not accept a body.",
      );
    return;
  }
  if (value === undefined && !metadata.bodyRequired) return;
  const validate = validatorsByName[metadata.bodyValidator];
  if (!validate || !validate(value))
    throw new ApiError(
      "invalid_body",
      "The local API request body is invalid.",
    );
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
  #transport: typeof fetch;
  #currentOrigin: () => string;
  #capability: string | undefined;
  #connecting: Promise<void> | undefined;
  #reconnecting: Promise<void> | undefined;
  #sessionGeneration = 0;
  constructor(
    transport: typeof fetch = globalThis.fetch.bind(globalThis),
    currentOrigin: () => string = () => globalThis.location.origin,
  ) {
    this.#transport = transport;
    this.#currentOrigin = currentOrigin;
  }
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
      response = await this.#transport("/api/v1/session/bootstrap", {
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
    if (response.status !== 200) {
      await this.#cancelBody(response);
      throw new ApiError(
        "response_invalid",
        "The local service returned an invalid session response.",
        response.status,
      );
    }
    const envelope = await this.#jsonEnvelope(response);
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
      reply.origin !== this.#currentOrigin()
    )
      throw new ApiError(
        "response_invalid",
        "The local service returned an invalid session response.",
        response.status,
      );
    if (generation === this.#sessionGeneration)
      this.#capability = reply.capability;
  }
  async operation<K extends ApiJsonOperationId>(
    operation: K,
    args: ApiOperationArguments<K>,
  ): Promise<ApiResult<ApiOperationData<K>>>;
  async operation<K extends ApiJsonOperationId, T>(
    operation: K,
    args: ApiOperationArguments<K>,
    decode: Decoder<T>,
  ): Promise<ApiResult<T>>;
  async operation<K extends ApiJsonOperationId, T>(
    operation: K,
    args: ApiOperationArguments<K>,
    decode?: Decoder<T>,
  ): Promise<ApiResult<ApiOperationData<K> | T>> {
    if (!Object.hasOwn(operationMetadata, operation))
      throw new ApiError(
        "invalid_operation",
        "The local API operation is unavailable.",
      );
    const metadata = operationMetadata[operation];
    if (!metadata || metadata.success.kind !== "json")
      throw new ApiError(
        "invalid_operation",
        "The local API operation is unavailable.",
      );
    const request = args as unknown as Record<string, unknown>;
    if (
      request === null ||
      typeof request !== "object" ||
      Array.isArray(request) ||
      Reflect.ownKeys(request).some(
        (key) =>
          typeof key !== "string" ||
          !["path", "query", "body", "signal"].includes(key),
      )
    )
      throw new ApiError(
        "invalid_request",
        "The local API request is invalid.",
      );
    const path = apiOperationPath(metadata, request.path);
    const query = apiOperationQuery(metadata, request.query);
    apiOperationBody(metadata, request.body);
    return this.#request(
      metadata,
      `${path}${query}`,
      request.body,
      request.signal as AbortSignal | undefined,
      decode as Decoder<ApiOperationData<K> | T> | undefined,
    );
  }

  async download<K extends ApiDownloadOperationId>(
    operation: K,
    args: ApiDownloadArguments<K>,
  ): Promise<ApiDownload> {
    if (!Object.hasOwn(operationMetadata, operation))
      throw new ApiError(
        "invalid_operation",
        "The local API operation is unavailable.",
      );
    const metadata = operationMetadata[operation];
    if (!metadata || metadata.success.kind !== "report-download")
      throw new ApiError(
        "invalid_operation",
        "The local API operation is unavailable.",
      );
    const request = args as unknown as Record<string, unknown>;
    if (
      request === null ||
      typeof request !== "object" ||
      Array.isArray(request) ||
      Reflect.ownKeys(request).some(
        (key) =>
          typeof key !== "string" || !["path", "query", "signal"].includes(key),
      ) ||
      Object.hasOwn(request, "body")
    )
      throw new ApiError(
        "invalid_request",
        "The local API request is invalid.",
      );
    const path = apiOperationPath(metadata, request.path);
    const selected = apiDownloadQuery(
      metadata,
      metadata.success,
      request.query,
    );
    const signal = request.signal as AbortSignal | undefined;
    const response = await this.#dispatch(
      metadata,
      `${path}${selected.query}`,
      undefined,
      signal,
      `${selected.contentType}, application/json`,
    );
    if (!response.ok) {
      const envelope = await this.#jsonEnvelope(response);
      throw this.#failure(envelope, response.status);
    }
    if (response.status !== metadata.success.status) {
      await this.#cancelBody(response);
      throw this.#responseInvalid(response.status);
    }
    const reportId = (request.path as Record<string, unknown>)[
      metadata.success.reportIdParameter
    ];
    const filename = `report-${String(reportId)}.${selected.extension}`;
    if (
      !this.#downloadHeaders(response, selected.contentType, filename) ||
      !response.body ||
      typeof response.body.getReader !== "function"
    ) {
      await this.#cancelBody(response);
      throw this.#responseInvalid(response.status);
    }
    return this.#readDownload(
      response,
      signal,
      filename,
      selected.contentType,
      metadata.success.maxBytes,
    );
  }

  async #request<T>(
    metadata: ApiOperationMetadata,
    destination: string,
    body: unknown,
    signal: AbortSignal | undefined,
    decode?: Decoder<T>,
  ): Promise<ApiResult<T>> {
    const response = await this.#dispatch(
      metadata,
      destination,
      body,
      signal,
      "application/json",
    );
    if (!response.ok) {
      const envelope = await this.#jsonEnvelope(response);
      throw this.#failure(envelope, response.status);
    }
    if (metadata.success.kind !== "json")
      throw new ApiError(
        "invalid_operation",
        "The local API operation is unavailable.",
      );
    const validatorName =
      metadata.success.validators[String(response.status) as "200" | "202"];
    if (!validatorName) {
      await this.#cancelBody(response);
      throw this.#responseInvalid(response.status);
    }
    const envelope = await this.#jsonEnvelope(response);
    const validateSuccess = validatorsByName[validatorName];
    if (!validateSuccess || !validateSuccess(envelope))
      throw new ApiError(
        "response_invalid",
        "The local service returned an invalid operation response.",
        response.status,
      );
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
      data: decode ? decode(envelope.data) : (envelope.data as T),
      warnings: warnings as ApiWarning[],
      revision: response.headers.get("ETag") ?? undefined,
    };
  }

  async #dispatch(
    metadata: ApiOperationMetadata,
    destination: string,
    body: unknown,
    signal: AbortSignal | undefined,
    accept: string,
  ): Promise<Response> {
    await this.connect();
    if (!this.#capability)
      throw new ApiError(
        "session_required",
        "Connect to the local workspace service.",
      );
    const headers = new Headers({
      Accept: accept,
      "X-Deykit-Capability": this.#capability,
    });
    if (body !== undefined) headers.set("Content-Type", "application/json");
    try {
      return await this.#transport(destination, {
        method: metadata.method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
        mode: "cors",
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
      });
    } catch {
      if (signal?.aborted)
        throw new ApiError("cancelled", "The request was cancelled.");
      throw new ApiError(
        "service_unavailable",
        "Cannot reach the local workspace service. Check that it is running and try again.",
      );
    }
  }

  async #jsonEnvelope(response: Response): Promise<Record<string, unknown>> {
    const contentType = response.headers.get("content-type") ?? "";
    if (
      !/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(contentType.trim())
    )
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

  #responseInvalid(status: number): ApiError {
    return new ApiError(
      "response_invalid",
      "The local service returned an invalid operation response.",
      status,
    );
  }

  #downloadHeaders(
    response: Response,
    contentType: string,
    filename: string,
  ): boolean {
    const actualType = response.headers.get("content-type")?.split(";") ?? [];
    if (
      actualType[0]?.trim().toLowerCase() !==
      contentType.split(";")[0].toLowerCase()
    )
      return false;
    if (contentType.includes(";")) {
      if (
        actualType.length !== 2 ||
        !/^\s*charset\s*=\s*utf-8\s*$/i.test(actualType[1])
      )
        return false;
    } else if (actualType.length !== 1) {
      return false;
    }
    if (
      response.headers.get("content-disposition") !==
      `attachment; filename="${filename}"`
    )
      return false;
    if (
      response.headers.get("x-content-type-options")?.trim().toLowerCase() !==
      "nosniff"
    )
      return false;
    const cache = response.headers.get("cache-control") ?? "";
    if (
      !cache.split(",").some((part) => part.trim().toLowerCase() === "no-store")
    )
      return false;
    const length = response.headers.get("content-length");
    if (
      length !== null &&
      (!/^(?:0|[1-9][0-9]*)$/.test(length) ||
        !Number.isSafeInteger(Number(length)))
    )
      return false;
    return length === null || Number(length) <= 8388608;
  }

  async #cancelBody(response: Response): Promise<void> {
    try {
      await response.body?.cancel();
    } catch {
      // Cancellation is best effort; callers receive only the safe transport error.
    }
  }

  async #readDownload(
    response: Response,
    signal: AbortSignal | undefined,
    filename: string,
    contentType: string,
    maxBytes: number,
  ): Promise<ApiDownload> {
    const body = response.body;
    if (!body) throw this.#responseInvalid(response.status);
    const reader = body.getReader();
    const chunks: ArrayBuffer[] = [];
    let received = 0;
    let failed = false;
    const contentLength = response.headers.get("content-length");
    const expectedLength =
      contentLength === null ? undefined : Number(contentLength);
    const cancel = () => {
      void reader.cancel().catch(() => undefined);
    };
    signal?.addEventListener("abort", cancel, { once: true });
    try {
      if (signal?.aborted)
        throw new ApiError("cancelled", "The request was cancelled.");
      while (true) {
        const part = await reader.read();
        if (signal?.aborted)
          throw new ApiError("cancelled", "The request was cancelled.");
        if (part.done) break;
        if (!(part.value instanceof Uint8Array))
          throw this.#responseInvalid(response.status);
        received += part.value.byteLength;
        if (received > maxBytes) throw this.#responseInvalid(response.status);
        const ownedChunk = new Uint8Array(part.value.byteLength);
        ownedChunk.set(part.value);
        chunks.push(ownedChunk.buffer);
      }
      if (expectedLength !== undefined && received !== expectedLength)
        throw this.#responseInvalid(response.status);
      return { blob: new Blob(chunks, { type: contentType }), filename };
    } catch (error) {
      failed = true;
      await reader.cancel().catch(() => undefined);
      if (
        signal?.aborted ||
        (error instanceof ApiError && error.code === "cancelled")
      )
        throw new ApiError("cancelled", "The request was cancelled.");
      if (error instanceof ApiError && error.code === "response_invalid")
        throw error;
      throw this.#responseInvalid(response.status);
    } finally {
      signal?.removeEventListener("abort", cancel);
      if (failed) {
        try {
          reader.releaseLock();
        } catch {
          /* already released by a failed reader */
        }
      } else {
        reader.releaseLock();
      }
    }
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
      typeof error.reason === "string"
        ? error.reason
        : error.reason === null
          ? null
          : undefined,
      typeof error.resource_id === "string"
        ? error.resource_id
        : error.resource_id === null
          ? null
          : undefined,
      typeof error.row === "number" && Number.isSafeInteger(error.row)
        ? error.row
        : error.row === null
          ? null
          : undefined,
      typeof error.correlation_id === "string"
        ? error.correlation_id
        : error.correlation_id === null
          ? null
          : undefined,
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

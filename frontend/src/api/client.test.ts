import { describe, expect, it, vi } from "vitest";
import { ApiClient, object, type ApiOperationArguments } from "./client";

const reply = (
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

const success = (data: unknown, warnings: unknown[] = []) => ({
  schema_version: 1,
  data,
  warnings,
});

const recentProjects = () => success({ schema_version: 1, items: [] });
const decisionPage = () =>
  success({ schema_version: 1, items: [], total: "0", next_cursor: null });

const registerProjectRequest = {
  schema_version: 1 as const,
  operation_id: "register-project",
  action: "create" as const,
  path: "/tmp/project",
  name: "Project",
};

const downloadReply = (
  value: Uint8Array,
  contentType: string,
  filename: string,
  status = 200,
  extra: Record<string, string> = {},
) =>
  new Response(new Uint8Array(value).buffer, {
    status,
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Length": String(value.byteLength),
      ...extra,
    },
  });

describe("generated local API operations", () => {
  it("preserves exact source strings inside a validated registered request", async () => {
    const source =
      '{"integer":9007199254740993,"decimal":0.1234567890123456789,"unfinished":';
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      reply(
        success({
          schema_version: 1,
          input_source: source,
          source_hash: "a".repeat(64),
        }),
      ),
    );

    const client = new ApiClient(transport);
    client.setCapability("local-session");

    const result = await client.operation(
      "encodeTextInput",
      {
        path: { registration_id: "registration-1" },
        body: { schema_version: 1, text_value: source },
      },
      (value) => object(value),
    );

    expect(result.data.input_source).toBe(source);
    const [url, init] = transport.mock.calls[0];
    expect(url).toBe("/api/v1/projects/registration-1/authoring/text-input");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      schema_version: 1,
      text_value: source,
    });
    expect(new Headers(init?.headers).get("If-Match")).toBeNull();
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBeNull();
    expect(init?.credentials).toBe("omit");
    expect(init?.mode).toBe("cors");
    expect(init?.redirect).toBe("error");
  });

  it("sends the required version body for the provider model operation", async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      reply(
        success({
          schema_version: 1,
          profile_id: "profile-1",
          network_check: true,
          inference_calls: 0,
          models: [],
        }),
      ),
    );
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await client.operation("listProviderModels", {
      path: { registration_id: "registration-1", profile_id: "profile-1" },
      query: { timeout_seconds: "12" },
      body: { schema_version: 1 },
    });

    const [url, init] = transport.mock.calls[0];
    expect(url).toBe(
      "/api/v1/projects/registration-1/providers/profile-1/models?timeout_seconds=12",
    );
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ schema_version: 1 });
  });

  it("preserves choice-order seeds as decimal text in the generated request", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error("offline"));
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await expect(
      client.operation("previewChoiceOrder", {
        path: { registration_id: "registration-1" },
        body: {
          schema_version: 1,
          request: {
            run: {
              decision_id: "decision-1",
              dataset_id: "dataset-1",
              mode: "fixture",
              fixture_set_id: "fixture-1",
            },
            orders: 2,
            seed: "9007199254740993",
          },
        },
      }),
    ).rejects.toBeDefined();

    expect(transport).toHaveBeenCalledOnce();
    expect(JSON.parse(transport.mock.calls[0][1]?.body as string)).toEqual({
      schema_version: 1,
      request: {
        run: {
          decision_id: "decision-1",
          dataset_id: "dataset-1",
          mode: "fixture",
          fixture_set_id: "fixture-1",
        },
        orders: 2,
        seed: "9007199254740993",
      },
    });
  });

  it("encodes only declared query values and retains the response ETag", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValue(reply(decisionPage(), 200, { ETag: '"page-2"' }));
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    const result = await client.operation("listDecisions", {
      path: { registration_id: "registration-1" },
      query: {
        cursor: "a&b/next",
        include_archived: "false",
        limit: "25",
      },
    });

    expect(transport.mock.calls[0][0]).toBe(
      "/api/v1/projects/registration-1/decisions?cursor=a%26b%2Fnext&include_archived=false&limit=25",
    );
    expect(result.revision).toBe('"page-2"');
  });

  it("rejects unsafe path values and undeclared runtime fields before bootstrap", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error("offline"));
    const client = new ApiClient(transport);

    await expect(
      client.operation("showRegisteredProject", {
        path: { registration_id: "../private" },
      }),
    ).rejects.toMatchObject({ code: "invalid_path" });
    await expect(
      client.operation("listDecisions", {
        path: { registration_id: "registration-1" },
        query: {
          cursor: "x",
          token: "secret",
        } as unknown as ApiOperationArguments<"listDecisions">["query"],
      }),
    ).rejects.toMatchObject({ code: "invalid_query" });
    await expect(
      client.operation("encodeTextInput", {
        path: { registration_id: "registration-1" },
        body: {
          schema_version: 1,
          text_value: 9,
        } as unknown as ApiOperationArguments<"encodeTextInput">["body"],
      }),
    ).rejects.toMatchObject({ code: "invalid_body" });
    expect(transport).not.toHaveBeenCalled();

    if (false) {
      // @ts-expect-error only operation IDs present in generated OpenAPI are public
      client.operation("arbitraryPath", {});
      client.operation("listDecisions", {
        path: { registration_id: "registration-1" },
        query: {
          // @ts-expect-error this query key is not in the registered operation
          token: "secret",
        },
      });
      client.operation("listDecisions", {
        // @ts-expect-error path parameters must match the generated string schema
        path: { registration_id: 9 },
      });
      // @ts-expect-error bootstrap is an internal operation, not public dispatch
      client.operation("bootstrapSession", {});
      // @ts-expect-error raw path dispatch is not a public client capability
      client.request("/api/v1/arbitrary", object, {});
      // @ts-expect-error text input operation requires its generated request body
      client.operation("encodeTextInput", {
        path: { registration_id: "registration-1" },
      });
      // @ts-expect-error downloads cannot use the JSON operation transport
      client.operation("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
      });
      // @ts-expect-error the download format is required
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
      });
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: {
          // @ts-expect-error only the generated format enum is admitted
          format: "html",
        },
      });
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json" },
        // @ts-expect-error download arguments do not accept a destination
        destination: "/tmp/report.json",
      });
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json" },
        // @ts-expect-error download arguments do not accept caller headers
        headers: { Authorization: "secret" },
      });
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json" },
        // @ts-expect-error download arguments do not accept bodies
        body: {},
      });
      const downloaded = await client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json" },
      });
      const filename: string = downloaded.filename;
      void filename;
      // @ts-expect-error the transport returns bytes and a filename, never an object URL
      const href: string = downloaded.href;
      void href;
    }
  });

  it("does not resolve inherited object properties as operations", async () => {
    const transport = vi.fn<typeof fetch>();
    const client = new ApiClient(transport);

    await expect(
      client.operation("toString" as never, {} as never),
    ).rejects.toMatchObject({ code: "invalid_operation" });
    expect(transport).not.toHaveBeenCalled();
  });

  it("downloads admitted report bytes using the generated format and filename", async () => {
    const bytes = new TextEncoder().encode(
      '{"n":9007199254740993,"decimal":0.1234567890123456789}',
    );
    const markdownBytes = new TextEncoder().encode("# Report\nRésumé\n");
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        downloadReply(
          bytes,
          "application/octet-stream",
          "report-report_1.json",
        ),
      )
      .mockResolvedValueOnce(
        downloadReply(
          markdownBytes,
          "text/plain; charset=utf-8",
          "report-report_1.md",
        ),
      );
    const client = new ApiClient(transport);
    client.setCapability("local-session");
    const createObjectUrl = vi.spyOn(URL, "createObjectURL");

    const result = await client.download("downloadReport", {
      path: { registration_id: "registration-1", report_id: "report_1" },
      query: { format: "json" },
    });

    expect(result.filename).toBe("report-report_1.json");
    expect([...new Uint8Array(await result.blob.arrayBuffer())]).toEqual([
      ...bytes,
    ]);
    expect(result.blob.type).toBe("application/octet-stream");
    expect(transport.mock.calls[0][0]).toBe(
      "/api/v1/projects/registration-1/reports/report_1/download?format=json",
    );
    expect(new Headers(transport.mock.calls[0][1]?.headers).get("Accept")).toBe(
      "application/octet-stream, application/json",
    );
    expect(String(transport.mock.calls[0][0])).not.toContain("local-session");
    expect(String(transport.mock.calls[0][0])).not.toContain("capability");
    expect(transport.mock.calls[0][1]?.cache).toBe("no-store");
    expect(transport.mock.calls[0][1]?.credentials).toBe("omit");

    const markdown = await client.download("downloadReport", {
      path: { registration_id: "registration-1", report_id: "report_1" },
      query: { format: "markdown" },
    });
    expect(markdown.filename).toBe("report-report_1.md");
    expect([...new Uint8Array(await markdown.blob.arrayBuffer())]).toEqual([
      ...markdownBytes,
    ]);
    expect(markdown.blob.type).toBe("text/plain; charset=utf-8");
    expect(transport.mock.calls[1][0]).toBe(
      "/api/v1/projects/registration-1/reports/report_1/download?format=markdown",
    );
    expect(createObjectUrl).not.toHaveBeenCalled();
    createObjectUrl.mockRestore();
  });

  it("rejects invalid download formats and extra arguments before transport", async () => {
    const transport = vi.fn<typeof fetch>();
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await expect(
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "html" } as never,
      }),
    ).rejects.toMatchObject({ code: "invalid_query" });
    await expect(
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json", token: "secret" } as never,
      }),
    ).rejects.toMatchObject({ code: "invalid_query" });
    await expect(
      client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json" },
        destination: "/tmp/private",
      } as never),
    ).rejects.toMatchObject({ code: "invalid_request" });
    expect(transport).not.toHaveBeenCalled();
  });

  it("parses safe download failures as JSON and rejects unexpected success statuses", async () => {
    const notFound = reply(
      {
        schema_version: 1,
        error: {
          schema_version: 1,
          code: "not_found",
          message: "The requested resource was not found.",
          resource_id: "report-missing",
        },
      },
      404,
    );
    const unexpected = new Response("", { status: 202 });
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(notFound)
      .mockResolvedValueOnce(unexpected);
    const client = new ApiClient(transport);
    client.setCapability("local-session");
    const args = {
      path: { registration_id: "registration-1", report_id: "report-missing" },
      query: { format: "json" as const },
    };

    await expect(client.download("downloadReport", args)).rejects.toMatchObject(
      {
        code: "not_found",
        status: 404,
        resource_id: "report-missing",
      },
    );
    await expect(client.download("downloadReport", args)).rejects.toMatchObject(
      {
        code: "response_invalid",
        status: 202,
      },
    );
  });

  it("rejects unsafe download media, disposition and protection headers", async () => {
    const badHeaders: Array<[string, Record<string, string>]> = [
      ["wrong media", { "Content-Type": "text/html" }],
      ["malformed media", { "Content-Type": "application/jsonp" }],
      [
        "extra media parameter",
        { "Content-Type": "application/octet-stream; charset=utf-8" },
      ],
      [
        "inline disposition",
        { "Content-Disposition": 'inline; filename="report-report-1.json"' },
      ],
      [
        "wrong filename",
        {
          "Content-Disposition":
            'attachment; filename="../report-report-1.json"',
        },
      ],
      [
        "extended filename",
        {
          "Content-Disposition":
            'attachment; filename="report-report-1.json"; filename*=UTF-8%27%27private.json',
        },
      ],
      ["missing no-store", { "Cache-Control": "private" }],
      ["missing nosniff", { "X-Content-Type-Options": "sniff" }],
    ];
    const cancelled: boolean[] = [];
    const responses = badHeaders.map(([, overrides]) => {
      const index = cancelled.length;
      cancelled.push(false);
      const body = new ReadableStream<Uint8Array>({
        cancel() {
          cancelled[index] = true;
        },
      });
      return new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": 'attachment; filename="report-report-1.json"',
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          ...overrides,
        },
      });
    });
    const transport = vi.fn<typeof fetch>();
    for (const response of responses) transport.mockResolvedValueOnce(response);
    const client = new ApiClient(transport);
    client.setCapability("local-session");
    const args = {
      path: { registration_id: "registration-1", report_id: "report-1" },
      query: { format: "json" as const },
    };

    for (const [label] of badHeaders) {
      await expect(
        client.download("downloadReport", args),
        label,
      ).rejects.toMatchObject({
        code: "response_invalid",
        status: 200,
      });
    }
    expect(cancelled).toEqual(badHeaders.map(() => true));
  });

  it("rejects malformed, oversized, short and long Content-Length values", async () => {
    const cases: Array<[string, string]> = [
      ["malformed", "08"],
      ["oversized", "8388609"],
      ["short", "1"],
      ["long", "3"],
    ];
    const responses = cases.map(([, length]) =>
      downloadReply(
        new Uint8Array([1, 2]),
        "application/octet-stream",
        "report-report-1.json",
        200,
        { "Content-Length": length },
      ),
    );
    const transport = vi.fn<typeof fetch>();
    for (const response of responses) transport.mockResolvedValueOnce(response);
    const client = new ApiClient(transport);
    client.setCapability("local-session");
    const args = {
      path: { registration_id: "registration-1", report_id: "report-1" },
      query: { format: "json" as const },
    };

    for (const [label] of cases) {
      await expect(
        client.download("downloadReport", args),
        label,
      ).rejects.toMatchObject({
        code: "response_invalid",
        status: 200,
      });
    }
    for (const response of responses) expect(response.body?.locked).toBe(false);
  });

  it("cancels and releases a failed or aborted download reader", async () => {
    const args = {
      path: { registration_id: "registration-1", report_id: "report-1" },
      query: { format: "json" as const },
    };
    const makeResponse = (reader: {
      read: () => Promise<ReadableStreamReadResult<Uint8Array>>;
      cancel: () => Promise<void>;
      releaseLock: () => void;
    }) => {
      const response = downloadReply(
        new Uint8Array(),
        "application/octet-stream",
        "report-report-1.json",
      );
      Object.defineProperty(response, "body", {
        value: {
          getReader: () => reader,
        } as unknown as ReadableStream<Uint8Array>,
      });
      return response;
    };
    const makeReader = (
      read: () => Promise<ReadableStreamReadResult<Uint8Array>>,
      cancel: () => Promise<void>,
    ) => ({
      read: vi.fn(read),
      cancel: vi.fn(cancel),
      releaseLock: vi.fn(),
    });

    const failedReader = makeReader(
      () => Promise.reject(new Error("PRIVATE read failure")),
      async () => undefined,
    );
    const failedTransport = vi
      .fn<typeof fetch>()
      .mockResolvedValue(makeResponse(failedReader));
    const failedClient = new ApiClient(failedTransport);
    failedClient.setCapability("local-session");
    await expect(
      failedClient.download("downloadReport", args),
    ).rejects.toMatchObject({
      code: "response_invalid",
    });
    expect(failedReader.cancel).toHaveBeenCalled();
    expect(failedReader.releaseLock).toHaveBeenCalledOnce();

    const alreadyAborted = new AbortController();
    alreadyAborted.abort();
    const beforeReadReader = makeReader(
      async () => ({ done: true, value: undefined }),
      async () => undefined,
    );
    const beforeReadClient = new ApiClient(
      vi.fn<typeof fetch>().mockResolvedValue(makeResponse(beforeReadReader)),
    );
    beforeReadClient.setCapability("local-session");
    await expect(
      beforeReadClient.download("downloadReport", {
        ...args,
        signal: alreadyAborted.signal,
      }),
    ).rejects.toMatchObject({ code: "cancelled" });
    expect(beforeReadReader.read).not.toHaveBeenCalled();
    expect(beforeReadReader.cancel).toHaveBeenCalled();
    expect(beforeReadReader.releaseLock).toHaveBeenCalledOnce();

    let finishRead!: (result: ReadableStreamReadResult<Uint8Array>) => void;
    const readStarted = vi.fn<() => void>();
    const pendingRead = new Promise<ReadableStreamReadResult<Uint8Array>>(
      (resolve) => {
        finishRead = resolve;
      },
    );
    const duringReadReader = makeReader(
      () => {
        readStarted();
        return pendingRead;
      },
      async () => {
        finishRead({ done: true, value: undefined });
      },
    );
    const duringReadClient = new ApiClient(
      vi.fn<typeof fetch>().mockResolvedValue(makeResponse(duringReadReader)),
    );
    duringReadClient.setCapability("local-session");
    const controller = new AbortController();
    const pendingDownload = duringReadClient.download("downloadReport", {
      ...args,
      signal: controller.signal,
    });
    while (!readStarted.mock.calls.length) await Promise.resolve();
    controller.abort();
    await expect(pendingDownload).rejects.toMatchObject({ code: "cancelled" });
    expect(duringReadReader.cancel).toHaveBeenCalled();
    expect(duringReadReader.releaseLock).toHaveBeenCalledOnce();
  });

  it("rejects malformed JSON download failures without exposing their body", async () => {
    const response = new Response("PRIVATE malformed failure", {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
    const client = new ApiClient(
      vi.fn<typeof fetch>().mockResolvedValue(response),
    );
    client.setCapability("local-session");

    try {
      await client.download("downloadReport", {
        path: { registration_id: "registration-1", report_id: "report-1" },
        query: { format: "json" },
      });
      expect.fail("malformed JSON error bodies must be rejected");
    } catch (error) {
      expect(error).toMatchObject({ code: "response_invalid", status: 404 });
      expect(String(error)).not.toContain("PRIVATE");
    }
  });

  it("accepts the exact byte cap and cancels single-chunk and cumulative overflow", async () => {
    const cancelled: boolean[] = [];
    const streamed = (chunks: readonly Uint8Array[]) => {
      let index = 0;
      const cancelIndex = cancelled.length;
      cancelled.push(false);
      const stream = new ReadableStream<Uint8Array>({
        pull(controller) {
          if (index < chunks.length) controller.enqueue(chunks[index++]);
          else controller.close();
        },
        cancel() {
          cancelled[cancelIndex] = true;
        },
      });
      return new Response(stream, {
        status: 200,
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": 'attachment; filename="report-report-1.json"',
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    };
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(streamed([new Uint8Array(8388608)]))
      .mockResolvedValueOnce(streamed([new Uint8Array(8388609)]))
      .mockResolvedValueOnce(
        streamed([new Uint8Array(8388608), new Uint8Array(1)]),
      );
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    const args = {
      path: { registration_id: "registration-1", report_id: "report-1" },
      query: { format: "json" as const },
    };
    const exactCap = await client.download("downloadReport", args);
    expect(exactCap.blob.size).toBe(8388608);
    await expect(client.download("downloadReport", args)).rejects.toMatchObject(
      { code: "response_invalid" },
    );
    await expect(client.download("downloadReport", args)).rejects.toMatchObject(
      { code: "response_invalid" },
    );
    expect(cancelled).toEqual([false, true, true]);
  });

  it("validates the operation-specific success envelope and hides raw transport failures", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("PRIVATE", { status: 500 }))
      .mockRejectedValueOnce(new Error("PRIVATE"))
      .mockResolvedValueOnce(
        reply(success({ schema_version: 1, items: ["bad"] })),
      );
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    for (let index = 0; index < 3; index += 1) {
      try {
        await client.operation("listRecentProjects", {});
        expect.fail("the malformed response must be rejected");
      } catch (error) {
        expect(String(error)).not.toContain("PRIVATE");
      }
    }
  });

  it("retains safe conflict metadata without retrying a mutation", async () => {
    const conflict = reply(
      {
        schema_version: 1,
        error: {
          schema_version: 1,
          code: "conflict",
          message: "The project changed.",
          reason: "etag_mismatch",
          resource_id: "project-1",
        },
      },
      409,
    );
    const transport = vi.fn<typeof fetch>().mockResolvedValueOnce(conflict);
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await expect(
      client.operation("registerProject", { body: registerProjectRequest }),
    ).rejects.toMatchObject({
      code: "conflict",
      status: 409,
      reason: "etag_mismatch",
      resource_id: "project-1",
    });
    expect(transport).toHaveBeenCalledTimes(1);
  });

  it("requires explicit reconnect after a stale capability and never resends the mutation", async () => {
    const origin = "http://127.0.0.1:8765";
    const bootstrap = (capability: string) =>
      reply(success({ capability, origin, api_version: 1 }));
    const stale = reply(
      {
        schema_version: 1,
        error: {
          schema_version: 1,
          code: "local_access_denied",
          message: "The local service rejected this request.",
        },
      },
      403,
    );
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(bootstrap("a".repeat(43)))
      .mockResolvedValueOnce(stale)
      .mockResolvedValueOnce(bootstrap("b".repeat(43)))
      .mockResolvedValueOnce(reply(recentProjects()));
    const sessionSet = vi.spyOn(window.sessionStorage, "setItem");
    const localSet = vi.spyOn(window.localStorage, "setItem");
    const client = new ApiClient(transport, () => origin);

    await expect(
      client.operation("registerProject", { body: registerProjectRequest }),
    ).rejects.toMatchObject({ status: 403 });
    expect(transport).toHaveBeenCalledTimes(2);
    await client.reconnect();
    await client.operation("listRecentProjects", {});

    expect(transport.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/session/bootstrap",
      "/api/v1/projects/register",
      "/api/v1/session/bootstrap",
      "/api/v1/projects/recent",
    ]);
    expect(
      new Headers(transport.mock.calls[3][1]?.headers).get(
        "X-Deykit-Capability",
      ),
    ).toBe("b".repeat(43));
    expect(sessionSet).not.toHaveBeenCalled();
    expect(localSet).not.toHaveBeenCalled();
  });

  it("preserves transient selection metadata from failure envelopes", async () => {
    const selection = {
      choices: [
        { kind: "decision", resource_id: "decision-1", scope: ["project-1"] },
      ],
    };
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      reply(
        {
          schema_version: 1,
          error: {
            schema_version: 1,
            code: "not_found",
            message: "The requested resource was not found.",
            resource_id: "missing",
            row: 7,
            reason: "resource_missing",
            correlation_id: "request-1",
          },
          selection,
        },
        404,
      ),
    );
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await expect(
      client.operation("registerProject", { body: registerProjectRequest }),
    ).rejects.toMatchObject({
      code: "not_found",
      status: 404,
      resource_id: "missing",
      row: 7,
      reason: "resource_missing",
      correlation_id: "request-1",
      selection,
    });
  });

  it("bootstraps once, pins the origin, and keeps the capability in memory", async () => {
    const origin = "http://127.0.0.1:8765";
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        reply(success({ capability: "a".repeat(43), origin, api_version: 1 })),
      )
      .mockResolvedValueOnce(reply(recentProjects()));
    const client = new ApiClient(transport, () => origin);

    await client.connect();
    await client.operation("listRecentProjects", {});

    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[0][0]).toBe("/api/v1/session/bootstrap");
    expect(
      new Headers(transport.mock.calls[0][1]?.headers).get(
        "X-Deykit-Bootstrap",
      ),
    ).toBe("1");
    expect(
      new Headers(transport.mock.calls[0][1]?.headers).get(
        "X-Deykit-Capability",
      ),
    ).toBeNull();
    expect(JSON.parse(transport.mock.calls[0][1]?.body as string)).toEqual({
      schema_version: 1,
    });
    expect(
      new Headers(transport.mock.calls[1][1]?.headers).get(
        "X-Deykit-Capability",
      ),
    ).toBe("a".repeat(43));
  });

  it("preserves generated warnings and rejects malformed warning records", async () => {
    const warning = {
      schema_version: 1,
      code: "preflight_failed",
      message: "Recent projects could not be read.",
      reason: "recent_projects_unavailable",
    };
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(reply(recentProjects(), 200, {}))
      .mockResolvedValueOnce(
        reply(success({ schema_version: 1, items: [] }, [warning])),
      )
      .mockResolvedValueOnce(
        reply(success({ schema_version: 1, items: [] }, ["unsafe"])),
      );
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await client.operation("listRecentProjects", {});
    expect((await client.operation("listRecentProjects", {})).warnings).toEqual(
      [warning],
    );
    await expect(
      client.operation("listRecentProjects", {}),
    ).rejects.toMatchObject({
      code: "response_invalid",
    });
  });

  it("does not let an older bootstrap overwrite a concurrent reconnect", async () => {
    const origin = "http://127.0.0.1:8765";
    const bootstrap = (capability: string) =>
      reply(success({ capability, origin, api_version: 1 }));
    let finishOldBootstrap!: (response: Response) => void;
    const oldBootstrap = new Promise<Response>((resolve) => {
      finishOldBootstrap = resolve;
    });
    const transport = vi
      .fn<typeof fetch>()
      .mockReturnValueOnce(oldBootstrap)
      .mockResolvedValueOnce(bootstrap("b".repeat(43)))
      .mockResolvedValueOnce(reply(recentProjects()));
    const client = new ApiClient(transport, () => origin);
    const initialConnect = client.connect();
    await client.reconnect();
    finishOldBootstrap(bootstrap("a".repeat(43)));
    await initialConnect;
    await client.operation("listRecentProjects", {});

    expect(
      new Headers(transport.mock.calls[2][1]?.headers).get(
        "X-Deykit-Capability",
      ),
    ).toBe("b".repeat(43));
  });
});

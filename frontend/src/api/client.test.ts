import { describe, expect, it, vi } from "vitest";
import {
  ApiClient,
  object,
  type ApiOperationArguments,
} from "./client";

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
    const transport = vi.fn<typeof fetch>().mockRejectedValue(new Error("offline"));
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
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      reply(decisionPage(), 200, { ETag: '"page-2"' }),
    );
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    const result = await client.operation("listDecisions", {
      path: { registration_id: "registration-1" },
      query: {
        cursor: "a&b/next",
        include_archived: false,
        limit: 25,
      },
    });

    expect(transport.mock.calls[0][0]).toBe(
      "/api/v1/projects/registration-1/decisions?cursor=a%26b%2Fnext&include_archived=false&limit=25",
    );
    expect(result.revision).toBe('"page-2"');
  });

  it("rejects unsafe path values and undeclared runtime fields before bootstrap", async () => {
    const transport = vi.fn<typeof fetch>().mockRejectedValue(new Error("offline"));
    const client = new ApiClient(transport);

    await expect(
      client.operation("showRegisteredProject", {
        path: { registration_id: "../private" },
      }),
    ).rejects.toMatchObject({ code: "invalid_path" });
    await expect(
      client.operation("listDecisions", {
        path: { registration_id: "registration-1" },
        query: { cursor: "x", token: "secret" } as unknown as ApiOperationArguments<"listDecisions">["query"],
      }),
    ).rejects.toMatchObject({ code: "invalid_query" });
    await expect(
      client.operation("encodeTextInput", {
        path: { registration_id: "registration-1" },
        body: { schema_version: 1, text_value: 9 } as unknown as ApiOperationArguments<"encodeTextInput">["body"],
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
      client.operation("encodeTextInput", { path: { registration_id: "registration-1" } });
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

  it("validates the operation-specific success envelope and hides raw transport failures", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("PRIVATE", { status: 500 }))
      .mockRejectedValueOnce(new Error("PRIVATE"))
      .mockResolvedValueOnce(reply(success({ schema_version: 1, items: ["bad"] })));
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
    expect(new Headers(transport.mock.calls[3][1]?.headers).get("X-Deykit-Capability")).toBe(
      "b".repeat(43),
    );
    expect(sessionSet).not.toHaveBeenCalled();
    expect(localSet).not.toHaveBeenCalled();
  });

  it("preserves transient selection metadata from failure envelopes", async () => {
    const selection = {
      choices: [{ kind: "decision", resource_id: "decision-1", scope: ["project-1"] }],
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
        reply(
          success({ capability: "a".repeat(43), origin, api_version: 1 }),
        ),
      )
      .mockResolvedValueOnce(reply(recentProjects()));
    const client = new ApiClient(transport, () => origin);

    await client.connect();
    await client.operation("listRecentProjects", {});

    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[0][0]).toBe("/api/v1/session/bootstrap");
    expect(new Headers(transport.mock.calls[0][1]?.headers).get("X-Deykit-Bootstrap")).toBe("1");
    expect(new Headers(transport.mock.calls[0][1]?.headers).get("X-Deykit-Capability")).toBeNull();
    expect(JSON.parse(transport.mock.calls[0][1]?.body as string)).toEqual({ schema_version: 1 });
    expect(new Headers(transport.mock.calls[1][1]?.headers).get("X-Deykit-Capability")).toBe(
      "a".repeat(43),
    );
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
      .mockResolvedValueOnce(reply(success({ schema_version: 1, items: [] }, [warning])))
      .mockResolvedValueOnce(reply(success({ schema_version: 1, items: [] }, ["unsafe"])));
    const client = new ApiClient(transport);
    client.setCapability("local-session");

    await client.operation("listRecentProjects", {});
    expect((await client.operation("listRecentProjects", {})).warnings).toEqual([warning]);
    await expect(client.operation("listRecentProjects", {})).rejects.toMatchObject({
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

    expect(new Headers(transport.mock.calls[2][1]?.headers).get("X-Deykit-Capability")).toBe(
      "b".repeat(43),
    );
  });
});

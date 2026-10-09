import { describe, expect, it, vi } from "vitest";
import { ApiClient, jsonSource } from "./client";
const reply = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
describe("local API boundary", () => {
  it("sends exact user JSON as a string without convenience precondition headers", async () => {
    const source =
      '{"integer":9007199254740993,"decimal":0.1234567890123456789,"unfinished":';
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      reply({
        schema_version: 1,
        data: { source_text: source },
        warnings: [],
      }),
    );
    const client = new ApiClient(transport);
    client.setCapability("local-session");
    const result = await client.request("/api/v1/drafts", jsonSource, {
      method: "PUT",
      body: { source_text: source },
    });
    expect(result.data.source_text).toBe(source);
    const init = transport.mock.calls[0][1]!;
    expect(JSON.parse(init.body as string)).toEqual({ source_text: source });
    expect(new Headers(init.headers).get("If-Match")).toBeNull();
    expect(new Headers(init.headers).get("Idempotency-Key")).toBeNull();
    expect(init.credentials).toBe("omit");
    expect(init.mode).toBe("cors");
    expect(init.redirect).toBe("error");
  });
  it("requires a session and blocks external, query, and traversal destinations before fetch", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error("offline"));
    const client = new ApiClient(transport);
    await expect(
      client.request("/api/v1/projects", jsonSource),
    ).rejects.toMatchObject({ code: "service_unavailable" });
    client.setCapability("session");
    for (const path of [
      "https://example.com/api/v1/projects",
      "/api/v1/../secret",
      "/api/v1/%2e%2e",
      "/api/v1/projects?token=secret",
      "/api/v1//projects",
    ])
      await expect(client.request(path, jsonSource)).rejects.toMatchObject({
        code: "invalid_path",
      });
    expect(transport).toHaveBeenCalledTimes(1);
    expect(transport.mock.calls[0][0]).toBe("/api/v1/session/bootstrap");
  });
  it("rejects malformed envelopes and never displays raw HTML or transport exceptions", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("SECRET", { status: 500 }))
      .mockRejectedValueOnce(new Error("SECRET"))
      .mockResolvedValueOnce(
        reply({ schema_version: 9, data: {}, warnings: [] }),
      );
    const client = new ApiClient(transport);
    client.setCapability("session");
    for (let n = 0; n < 3; n++) {
      try {
        await client.request("/api/v1/projects", jsonSource);
        expect.fail("should reject");
      } catch (error) {
        expect(String(error)).not.toContain("SECRET");
      }
    }
  });
  it("preserves typed conflicts and rejects source objects that would round values", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        reply(
          {
            schema_version: 1,
            error: {
              code: "conflict",
              message: "The draft changed. Reload before saving.",
              schema_version: 1,
            },
          },
          409,
        ),
      )
      .mockResolvedValueOnce(
        reply({
          schema_version: 1,
          data: { source_text: { value: 1 } },
          warnings: [],
        }),
      );
    const client = new ApiClient(transport);
    client.setCapability("session");
    await expect(
      client.request("/api/v1/drafts", jsonSource),
    ).rejects.toMatchObject({ code: "conflict", status: 409 });
    await expect(
      client.request("/api/v1/drafts", jsonSource),
    ).rejects.toMatchObject({ code: "response_invalid" });
  });

  it("preserves transient resource choices from the top-level failure envelope", async () => {
    const selection = {
      choices: [
        {
          kind: "decision",
          resource_id: "decision-1",
          scope: ["project-1"],
        },
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
    client.setCapability("session");

    await expect(client.request("/api/v1/projects", jsonSource)).rejects.toMatchObject({
      code: "not_found",
      status: 404,
      resource_id: "missing",
      row: 7,
      reason: "resource_missing",
      correlation_id: "request-1",
      selection,
    });
  });
});

it("encodes pagination separately and captures the response revision", async () => {
  const transport = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        schema_version: 1,
        data: { source_text: "{}" },
        warnings: [],
      }),
      { headers: { "Content-Type": "application/json", ETag: '"rev-2"' } },
    ),
  );
  const client = new ApiClient(transport);
  client.setCapability("session");
  const result = await client.request("/api/v1/projects", jsonSource, {
    query: { cursor: "a&b/next", limit: 25 },
  });
  expect(transport.mock.calls[0][0]).toBe(
    "/api/v1/projects?cursor=a%26b%2Fnext&limit=25",
  );
  expect(result.revision).toBe('"rev-2"');
  await expect(
    client.request("/api/v1/projects", jsonSource, {
      query: { limit: Infinity },
    }),
  ).rejects.toMatchObject({ code: "invalid_query" });
});

it("bootstraps once with the public exemption and pins the returned origin", async () => {
  const origin = "http://127.0.0.1:8765";
  const transport = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(
      reply({
        schema_version: 1,
        data: {
          capability: "a".repeat(43),
          origin,
          api_version: 1,
        },
        warnings: [],
      }),
    )
    .mockResolvedValueOnce(
      reply({ schema_version: 1, data: { source_text: "{}" }, warnings: [] }),
    );
  const client = new ApiClient(transport, () => origin);
  await client.connect();
  await client.request("/api/v1/projects", jsonSource);
  expect(transport).toHaveBeenCalledTimes(2);
  const bootstrap = transport.mock.calls[0][1]!;
  expect(new Headers(bootstrap.headers).get("X-Deykit-Bootstrap")).toBe("1");
  expect(new Headers(bootstrap.headers).get("X-Deykit-Capability")).toBeNull();
  expect(JSON.parse(bootstrap.body as string)).toEqual({ schema_version: 1 });
  expect(
    new Headers(transport.mock.calls[1][1]!.headers).get("X-Deykit-Capability"),
  ).toBe("a".repeat(43));
});

it("preserves generated structured warnings and rejects malformed warning records", async () => {
  const warning = {
    schema_version: 1,
    code: "preflight_failed",
    message: "Recent projects could not be read.",
    reason: "recent_projects_unavailable",
  };
  const transport = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(reply({ schema_version: 1, data: {}, warnings: [warning] }))
    .mockResolvedValueOnce(reply({ schema_version: 1, data: {}, warnings: ["unsafe"] }));
  const client = new ApiClient(transport);
  client.setCapability("session");
  expect((await client.request("/api/v1/projects", (value) => value)).warnings).toEqual([
    warning,
  ]);
  await expect(
    client.request("/api/v1/projects", (value) => value),
  ).rejects.toMatchObject({ code: "response_invalid" });
});

it("requires explicit reconnect after a stale capability and never resends a mutation", async () => {
  const origin = "http://127.0.0.1:8765";
  const bootstrap = (capability: string) =>
    reply({
      schema_version: 1,
      data: { capability, origin, api_version: 1 },
      warnings: [],
    });
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
    .mockResolvedValueOnce(reply({ schema_version: 1, data: {}, warnings: [] }));
  const sessionSet = vi.spyOn(window.sessionStorage, "setItem");
  const localSet = vi.spyOn(window.localStorage, "setItem");
  const client = new ApiClient(transport, () => origin);
  await expect(
    client.request("/api/v1/projects/register", (value) => value, {
      method: "POST",
      body: { operation_id: "original-operation" },
    }),
  ).rejects.toMatchObject({ status: 403 });
  expect(transport).toHaveBeenCalledTimes(2);
  await client.reconnect();
  await client.request("/api/v1/projects/recent", (value) => value);
  expect(transport).toHaveBeenCalledTimes(4);
  expect(transport.mock.calls.map(([url]) => url)).toEqual([
    "/api/v1/session/bootstrap",
    "/api/v1/projects/register",
    "/api/v1/session/bootstrap",
    "/api/v1/projects/recent",
  ]);
  expect(
    new Headers(transport.mock.calls[3][1]!.headers).get("X-Deykit-Capability"),
  ).toBe("b".repeat(43));
  expect(sessionSet).not.toHaveBeenCalled();
  expect(localSet).not.toHaveBeenCalled();
});

it("does not let an older bootstrap overwrite an explicit reconnect", async () => {
  const origin = "http://127.0.0.1:8765";
  const bootstrap = (capability: string) =>
    reply({
      schema_version: 1,
      data: { capability, origin, api_version: 1 },
      warnings: [],
    });
  let finishOldBootstrap!: (response: Response) => void;
  const oldBootstrap = new Promise<Response>((resolve) => {
    finishOldBootstrap = resolve;
  });
  const transport = vi
    .fn<typeof fetch>()
    .mockReturnValueOnce(oldBootstrap)
    .mockResolvedValueOnce(bootstrap("b".repeat(43)))
    .mockResolvedValueOnce(reply({ schema_version: 1, data: {}, warnings: [] }));
  const client = new ApiClient(transport, () => origin);
  const initialConnect = client.connect();
  await client.reconnect();
  finishOldBootstrap(bootstrap("a".repeat(43)));
  await initialConnect;
  await client.request("/api/v1/projects/recent", (value) => value);
  expect(
    new Headers(transport.mock.calls[2][1]!.headers).get("X-Deykit-Capability"),
  ).toBe("b".repeat(43));
});


describe("structured API failures", () => {
  it("retains safe error metadata from the failure envelope", async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      reply(
        {
          schema_version: 1,
          error: {
            schema_version: 1,
            code: "conflict",
            message: "The project changed.",
            reason: "etag_mismatch",
            resource_id: "decision-1",
            row: 7,
            correlation_id: "correlation-1",
          },
        },
        409,
      ),
    );
    const client = new ApiClient(transport);
    client.setCapability("session");
    await expect(client.request("/api/v1/projects", jsonSource)).rejects.toMatchObject({
      code: "conflict",
      status: 409,
      reason: "etag_mismatch",
      resource_id: "decision-1",
      row: 7,
      correlation_id: "correlation-1",
    });
  });
});

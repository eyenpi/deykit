import { describe, expect, it, vi } from "vitest";
import { ApiClient, jsonSource } from "./client";
const reply = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
describe("local API boundary", () => {
  it("sends exact user JSON as a string with concurrency and operation headers", async () => {
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
      expectedRevision: "revision-1",
      operationId: "operation-1",
    });
    expect(result.data.source_text).toBe(source);
    const init = transport.mock.calls[0][1]!;
    expect(JSON.parse(init.body as string)).toEqual({ source_text: source });
    expect(new Headers(init.headers).get("If-Match")).toBe("revision-1");
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe(
      "operation-1",
    );
    expect(init.redirect).toBe("error");
  });
  it("requires a session and blocks external, query, and traversal destinations before fetch", async () => {
    const transport = vi.fn<typeof fetch>();
    const client = new ApiClient(transport);
    await expect(
      client.request("/api/v1/projects", jsonSource),
    ).rejects.toMatchObject({ code: "session_required" });
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
    expect(transport).not.toHaveBeenCalled();
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

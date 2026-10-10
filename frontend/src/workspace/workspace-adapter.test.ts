import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../api/client";
import { createWorkspaceGateway } from "./workspace-adapter";

const json = (data: unknown) =>
  new Response(JSON.stringify({ schema_version: 1, data, warnings: [] }), {
    headers: { "Content-Type": "application/json" },
  });
const registration = {
  registration_id: "registration-1",
  path: "/tmp/decision-project",
  project: {
    schema_version: 1,
    id: "project-1",
    name: "Decision project",
    created_at: "2026-10-05T00:00:00Z",
    default_provider_id: null,
  },
  project_etag: "a".repeat(64),
  execution_active: false,
  record_count: "1",
  demo: null,
  schema_version: 1,
};
const summary = { id: "decision-1", name: "Where to go?", schema_version: 1 };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

describe("workspace API adapter", () => {
  it("registers a project and reads its server-authoritative overview", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({
          capability: "c".repeat(43),
          origin: "http://localhost",
          api_version: 1,
        }),
      )
      .mockResolvedValueOnce(json(registration))
      .mockResolvedValueOnce(
        json({
          registration,
          decisions: [summary],
          datasets: [],
          schema_version: 1,
        }),
      );
    const gateway = createWorkspaceGateway(
      // Test origin matches the bootstrap reply; no browser globals are needed.
      new ApiClient(transport, () => "http://localhost"),
    );
    const result = await gateway.openProject({
      action: "create",
      path: "/tmp/decision-project",
      name: "Decision project",
      operationId: "operation-1",
    });
    expect(result).toEqual({
      id: "registration-1",
      path: "/tmp/decision-project",
      name: "Decision project",
      decisions: [{ id: "decision-1", name: "Where to go?" }],
      datasets: [],
      warnings: [],
    });
    expect(transport.mock.calls[1][0]).toBe("/api/v1/projects/register");
    expect(JSON.parse(transport.mock.calls[1][1]!.body as string)).toEqual({
      schema_version: 1,
      operation_id: "operation-1",
      action: "create",
      path: "/tmp/decision-project",
      name: "Decision project",
    });
    expect(transport.mock.calls[2][0]).toBe(
      "/api/v1/projects/registration-1/overview",
    );
  });

  it("creates the authored demo and resolves its registration to an overview", async () => {
    const demoData = {
      registration,
      demo: {
        operation_id: "operation-1",
        replayed: false,
        evidence_mode: "authored_fixture",
        project_id: "project-1",
        decision_id: "decision-1",
        revision_id: "revision-1",
        dataset_id: "dataset-1",
        profile_id: "profile-1",
        fixture_set_id: "fixtures-1",
        case_count: "12",
        binding_count: "11",
        label_count: "9",
        schema_version: 1,
      },
      schema_version: 1,
    };
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({
          capability: "c".repeat(43),
          origin: "http://localhost",
          api_version: 1,
        }),
      )
      .mockResolvedValueOnce(json(demoData))
      .mockResolvedValueOnce(
        json({
          registration,
          decisions: [],
          datasets: [],
          schema_version: 1,
        }),
      );
    const gateway = createWorkspaceGateway(
      new ApiClient(transport, () => "http://localhost"),
    );
    const result = await gateway.openProject({
      action: "demo",
      path: "/tmp/demo",
      name: "",
      operationId: "operation-1",
    });
    expect(result.id).toBe("registration-1");
    expect(transport.mock.calls[1][0]).toBe("/api/v1/projects/demo");
    expect(JSON.parse(transport.mock.calls[1][1]!.body as string)).toEqual({
      schema_version: 1,
      operation_id: "operation-1",
      path: "/tmp/demo",
    });
  });

  it("retries overview after a successful registration without resending the mutation", async () => {
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({
          capability: "c".repeat(43),
          origin: "http://localhost",
          api_version: 1,
        }),
      )
      .mockResolvedValueOnce(json(registration))
      .mockResolvedValueOnce(
        new Response("{}", {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        json({
          registration,
          decisions: [summary],
          datasets: [],
          schema_version: 1,
        }),
      );
    const gateway = createWorkspaceGateway(
      new ApiClient(transport, () => "http://localhost"),
    );
    const request = {
      action: "create" as const,
      path: "/tmp/decision-project",
      name: "Decision project",
      operationId: "operation-1",
    };
    await expect(gateway.openProject(request)).rejects.toMatchObject({
      status: 503,
    });
    const result = await gateway.openProject(request);
    expect(result.decisions).toEqual(
      [summary].map(({ id, name }) => ({ id, name })),
    );
    expect(transport.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/session/bootstrap",
      "/api/v1/projects/register",
      "/api/v1/projects/registration-1/overview",
      "/api/v1/projects/registration-1/overview",
    ]);
  });

  it("keeps an aborted admitted overview in the registration lane through body parsing", async () => {
    const bodyReadStarted = deferred<void>();
    const releaseBody = deferred<void>();
    const body = JSON.stringify({
      schema_version: 1,
      data: { registration, decisions: [], datasets: [], schema_version: 1 },
      warnings: [],
    });
    const heldResponse = new Response(
      new ReadableStream<Uint8Array>(
        {
          async pull(controller) {
            bodyReadStarted.resolve(undefined);
            await releaseBody.promise;
            controller.enqueue(new TextEncoder().encode(body));
            controller.close();
          },
        },
        { highWaterMark: 0 },
      ),
      { headers: { "Content-Type": "application/json" } },
    );
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({
          capability: "c".repeat(43),
          origin: "http://localhost",
          api_version: 1,
        }),
      )
      .mockResolvedValueOnce(heldResponse)
      .mockResolvedValueOnce(
        json({ registration, decisions: [], datasets: [], schema_version: 1 }),
      );
    const gateway = createWorkspaceGateway(
      new ApiClient(transport, () => "http://localhost"),
    );
    const controller = new AbortController();
    const staleOverview = gateway.projectOverview(
      "registration-1",
      controller.signal,
    );
    await bodyReadStarted.promise;
    const currentOverview = gateway.projectOverview(
      "registration-1",
      new AbortController().signal,
    );
    controller.abort();
    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[1][1]?.signal).toBeUndefined();

    releaseBody.resolve(undefined);
    await expect(staleOverview).rejects.toMatchObject({ code: "cancelled" });
    await expect(currentOverview).resolves.toMatchObject({
      id: "registration-1",
      decisions: [],
    });
    expect(transport).toHaveBeenCalledTimes(3);
  });

  it("snapshots mutation arrays at adapter entry while waiting for a source read", async () => {
    const bodyReadStarted = deferred<void>();
    const releaseBody = deferred<void>();
    const failureBody = JSON.stringify({
      schema_version: 1,
      error: {
        schema_version: 1,
        code: "service_unavailable",
        message: "The local source is temporarily unavailable.",
      },
    });
    const heldReadResponse = new Response(
      new ReadableStream<Uint8Array>(
        {
          async pull(controller) {
            bodyReadStarted.resolve(undefined);
            await releaseBody.promise;
            controller.enqueue(new TextEncoder().encode(failureBody));
            controller.close();
          },
        },
        { highWaterMark: 0 },
      ),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({
          capability: "c".repeat(43),
          origin: "http://localhost",
          api_version: 1,
        }),
      )
      .mockResolvedValueOnce(heldReadResponse)
      .mockResolvedValueOnce(
        new Response(failureBody, {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const gateway = createWorkspaceGateway(
      new ApiClient(transport, () => "http://localhost"),
    );
    const read = gateway.authoring.examples.listCases({
      registrationId: "registration-1",
      datasetId: "dataset-1",
      query: { limit: "50" },
    });
    await bodyReadStarted.promise;

    const tags = ["authored-tag"];
    const derivedFrom = ["case-original"];
    const write = gateway.authoring.examples.addCase({
      registrationId: "registration-1",
      datasetId: "dataset-1",
      body: {
        schema_version: 1,
        operation_id: "00000000-0000-4000-8000-000000000001",
        expected_dataset_etag: "a".repeat(64),
        input_kind: "text",
        input_source: "opaque input source",
        metadata_source: '{"source":"preserved"}',
        tags,
        split: "development",
        group_id: null,
        derived_from: derivedFrom,
      },
    });
    tags.push("later-tag");
    derivedFrom[0] = "case-mutated";
    expect(transport).toHaveBeenCalledTimes(2);

    releaseBody.resolve(undefined);
    await expect(read).rejects.toMatchObject({ status: 503 });
    await expect(write).rejects.toMatchObject({ status: 503 });
    expect(transport).toHaveBeenCalledTimes(3);
    expect(JSON.parse(transport.mock.calls[2][1]!.body as string)).toEqual({
      schema_version: 1,
      operation_id: "00000000-0000-4000-8000-000000000001",
      expected_dataset_etag: "a".repeat(64),
      input_kind: "text",
      input_source: "opaque input source",
      metadata_source: '{"source":"preserved"}',
      tags: ["authored-tag"],
      split: "development",
      group_id: null,
      derived_from: ["case-original"],
    });
  });
});

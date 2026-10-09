import { describe, expect, it } from "vitest";
import { MappingTransformQueue } from "./mapping-transform-queue";

describe("serialized opaque mapping transforms", () => {
  it("composes edits over each latest source even when the first response is delayed", async () => {
    let releaseFirst!: () => void;
    const firstBarrier = new Promise<void>((resolve) => { releaseFirst = resolve; });
    const requests: Array<{ source: string; field: string; value: string }> = [];
    const queue = new MappingTransformQueue<{ field: string; value: string }, { fields: string[] }>(
      '{"input_kind":"text"}',
    );
    const transform = async (source: string, edit: { field: string; value: string }) => {
      requests.push({ source, ...edit });
      if (requests.length === 1) await firstBarrier;
      const mapping_source = edit.field === "id_column"
        ? "opaque service source after ID mapping"
        : "opaque service source after ID and input mappings";
      return { mapping_source, form: { fields: [edit.field] } };
    };

    const first = queue.enqueue({ field: "id_column", value: "record_id" }, transform);
    const second = queue.enqueue({ field: "input_column", value: "prompt" }, transform);
    await Promise.resolve();
    expect(requests).toEqual([
      { source: '{"input_kind":"text"}', field: "id_column", value: "record_id" },
    ]);
    releaseFirst();
    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(requests).toHaveLength(2);
    expect(requests[1].source).toBe(firstResult.mapping_source);
    expect(secondResult.mapping_source).toBe("opaque service source after ID and input mappings");
    expect(queue.source).toBe(secondResult.mapping_source);
    expect(queue.pending).toBe(0);
  });

  it("blocks queued preview transforms after a failed request until explicit retry", async () => {
    const queue = new MappingTransformQueue<string, string>("exact source");
    const requests: Array<[string, string]> = [];
    const failed = queue.enqueue("first", async (source, edit) => {
      requests.push([source, edit]);
      throw new Error("transform response lost");
    });
    const queued = queue.enqueue("second", async (source, edit) => {
      requests.push([source, edit]);
      return { mapping_source: `${source} second`, form: null };
    });
    await expect(failed).rejects.toThrow("transform response lost");
    await expect(queued).rejects.toThrow("explicit retry");
    expect(requests).toEqual([["exact source", "first"]]);
    expect(queue.blocked).toBe(true);

    queue.reset();
    const retried = await queue.enqueue("first", async (source, edit) => {
      requests.push([source, edit]);
      return { mapping_source: `${source} first`, form: null };
    });
    expect(retried.mapping_source).toBe("exact source first");
  });
});

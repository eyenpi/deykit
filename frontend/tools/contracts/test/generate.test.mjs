import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdtemp,
  readFile,
  readdir,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";
import { mock, test } from "node:test";
import { build } from "vite";
import {
  generateArtifacts,
  main,
  writeFiles,
  compareFiles,
} from "../generate.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../..");
const cli = createRequire(import.meta.url);
const hash = (value) => createHash("sha256").update(value).digest("hex");
const localSchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "urn:deykit:test:Source",
  type: "object",
  additionalProperties: false,
  required: ["schema_version", "source_text", "short_text"],
  properties: {
    schema_version: { type: "integer", const: 1 },
    source_text: { type: "string" },
    short_text: { type: "string", minLength: 2, maxLength: 2 },
  },
};
const inputs = () => ({
  openapi: {
    openapi: "3.1.0",
    info: { title: "local", version: "1.0.0" },
    paths: {},
    components: { schemas: { Request: structuredClone(localSchema) } },
  },
  schemas: { Source: structuredClone(localSchema) },
  inputHashes: { openapi: hash("one"), schemas: hash("two") },
});

async function validatorsFor(artifacts) {
  const directory = await mkdtemp(join(here, ".validators-"));
  try {
    const path = join(directory, "validators.cjs");
    await writeFile(path, artifacts.get("validators.cjs"));
    return cli(path);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test("schema ordering does not affect deterministic declarations, validators or manifest", async () => {
  const sample = inputs();
  const forward = await generateArtifacts(
    sample.openapi,
    sample.schemas,
    sample.inputHashes,
  );
  const reverse = await generateArtifacts(
    sample.openapi,
    Object.fromEntries(Object.entries(sample.schemas).reverse()),
    sample.inputHashes,
  );
  assert.deepEqual([...forward], [...reverse]);
  const changed = await generateArtifacts(sample.openapi, sample.schemas, {
    ...sample.inputHashes,
    schemas: hash("new"),
  });
  assert.notEqual(forward.get("manifest.json"), changed.get("manifest.json"));
  assert.equal(forward.size, 5);
});

test("operation metadata is derived only from registered OpenAPI operations", async () => {
  const sample = inputs();
  sample.openapi.components.schemas.Source = structuredClone(localSchema);
  sample.openapi.paths["/api/v1/projects/{registration_id}"] = {
    get: {
      operationId: "showProject",
      parameters: [
        {
          name: "registration_id",
          in: "path",
          required: true,
          schema: { type: "string" },
        },
        { name: "cursor", in: "query", schema: { type: "string" } },
      ],
      responses: {
        "200": {
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/Source" },
            },
          },
        },
      },
    },
  };
  sample.openapi.paths["/api/v1/session/bootstrap"] = {
    post: {
      operationId: "bootstrapSession",
      "x-deykit-client-internal": true,
      responses: {
        "200": {
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/Source" },
            },
          },
        },
      },
    },
  };
  const artifacts = await generateArtifacts(
    sample.openapi,
    sample.schemas,
    sample.inputHashes,
  );
  const declarations = artifacts.get("operations.ts");
  assert.match(declarations, /showProject/);
  assert.doesNotMatch(declarations, /bootstrapSession/);
  assert.match(declarations, /method:\s*"GET"/);
  assert.match(declarations, /pathParams:\s*\[\s*"registration_id"\s*\]/);
  assert.match(declarations, /queryParams:\s*\[\s*"cursor"\s*\]/);
  assert.match(declarations, /kind:\s*"json"/);
  assert.match(declarations, /validators:\s*\{\s*"200":\s*"validateSource"/);
  assert.match(declarations, /ApiJsonOperationId/);
  assert.match(artifacts.get("openapi.d.ts"), /bootstrapSession/);
});

test("JSON operation metadata preserves each declared 200 and 202 schema", async () => {
  const sample = inputs();
  sample.openapi.components.schemas.Source = structuredClone(localSchema);
  sample.openapi.paths["/api/v1/runs"] = {
    post: {
      operationId: "startRun",
      responses: {
        "202": {
          content: { "application/json": { schema: { $ref: "#/components/schemas/Source" } } },
        },
      },
    },
  };
  sample.openapi.paths["/api/v1/mixed"] = {
    get: {
      operationId: "mixedResult",
      responses: {
        "200": {
          content: { "application/json": { schema: { $ref: "#/components/schemas/Request" } } },
        },
        "202": {
          content: { "application/json": { schema: { $ref: "#/components/schemas/Source" } } },
        },
      },
    },
  };
  const generated = await generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes);
  const metadata = generated.get("operations.ts");
  assert.match(metadata, /"startRun"[\s\S]*?"202":\s*"validateSource"/);
  assert.match(metadata, /"mixedResult"[\s\S]*?"200":\s*"validateRequest"[\s\S]*?"202":\s*"validateSource"/);
  assert.match(metadata, /ApiDownloadOperationId/);

  const unsupported = structuredClone(sample.openapi);
  unsupported.paths["/api/v1/mixed"].get.responses["201"] = {
    content: { "application/json": { schema: { $ref: "#/components/schemas/Source" } } },
  };
  await assert.rejects(
    generateArtifacts(unsupported, sample.schemas, sample.inputHashes),
    /only declare 200 or 202/,
  );
});

test("report download metadata is admitted only for the exact annotated binary contract", async () => {
  const sample = inputs();
  const policy = {
    formatParameter: "format",
    reportIdParameter: "report_id",
    maxBytes: 8388608,
    formats: {
      json: { contentType: "application/octet-stream", extension: "json" },
      markdown: { contentType: "text/plain; charset=utf-8", extension: "md" },
    },
  };
  const download = {
    operationId: "downloadReport",
    "x-deykit-report-download-v1": policy,
    parameters: [
      { name: "registration_id", in: "path", required: true, schema: { type: "string" } },
      { name: "report_id", in: "path", required: true, schema: { type: "string" } },
      { name: "format", in: "query", required: true, schema: { type: "string", enum: ["json", "markdown"] } },
    ],
    responses: {
      "200": {
        content: {
          "application/octet-stream": { schema: { type: "string", format: "binary" } },
          "text/plain; charset=utf-8": { schema: { type: "string", format: "binary" } },
        },
        headers: {
          "Content-Disposition": { schema: { type: "string" }, description: "fixed filename" },
          "Cache-Control": { schema: { type: "string", const: "no-store" } },
          "X-Content-Type-Options": { schema: { type: "string", const: "nosniff" } },
        },
      },
    },
  };
  sample.openapi.paths["/api/v1/projects/{registration_id}/reports/{report_id}/download"] = {
    get: structuredClone(download),
  };
  const generated = await generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes);
  assert.match(generated.get("operations.ts"), /kind:\s*"report-download"/);
  assert.match(generated.get("operations.ts"), /"downloadReport"/);
  assert.doesNotMatch(generated.get("operations.ts"), /binary/);

  for (const mutate of [
    (operation) => { delete operation["x-deykit-report-download-v1"]; },
    (operation) => { operation["x-deykit-report-download-v1"].maxBytes += 1; },
    (operation) => { operation["x-deykit-report-download-v1"].formats.json.extension = "txt"; },
    (operation) => { operation.parameters[2].schema.enum = ["json", "html"]; },
    (operation) => { operation.parameters.push({ name: "token", in: "query", schema: { type: "string" } }); },
    (operation) => { operation.requestBody = { required: true }; },
    (operation) => { operation.responses["200"].content["application/octet-stream"].schema = { $ref: "#/components/schemas/Source" }; },
    (operation) => { operation.responses["200"].content["text/html"] = { schema: { type: "string", format: "binary" } }; },
    (operation) => { operation.responses["200"].headers["Cache-Control"].schema.const = "private"; },
    (operation) => { operation.responses["200"].headers["X-Content-Type-Options"].schema.const = "sniff"; },
  ]) {
    const invalid = structuredClone(sample.openapi);
    mutate(invalid.paths["/api/v1/projects/{registration_id}/reports/{report_id}/download"].get);
    await assert.rejects(generateArtifacts(invalid, sample.schemas, sample.inputHashes));
  }
  const wrongPath = structuredClone(sample.openapi);
  const admitted = wrongPath.paths["/api/v1/projects/{registration_id}/reports/{report_id}/download"];
  delete wrongPath.paths["/api/v1/projects/{registration_id}/reports/{report_id}/download"];
  wrongPath.paths["/api/v1/projects/{registration_id}/other/{report_id}"] = admitted;
  await assert.rejects(generateArtifacts(wrongPath, sample.schemas, sample.inputHashes));
  const extraSuccess = structuredClone(sample.openapi);
  extraSuccess.paths["/api/v1/projects/{registration_id}/reports/{report_id}/download"].get.responses["202"] = {
    content: { "application/json": { schema: { $ref: "#/components/schemas/Source" } } },
  };
  await assert.rejects(
    generateArtifacts(extraSuccess, sample.schemas, sample.inputHashes),
    /only a 200 success/,
  );
});

test("OpenAPI discriminators retain oneOf validation in generated validators", async () => {
  const sample = inputs();
  sample.schemas.Tagged = {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: "urn:deykit:test:Tagged",
    type: "object",
    additionalProperties: false,
    required: ["edit", "discriminator"],
    properties: {
      discriminator: {
        type: "object",
        const: { label: "literal", discriminator: "preserved" },
        default: { discriminator: "default-value" },
      },
      edit: {
        discriminator: {
          propertyName: "kind",
          mapping: { set: "#/components/schemas/SetEdit" },
        },
        oneOf: [
          {
            type: "object",
            additionalProperties: false,
            required: ["kind", "value"],
            properties: {
              kind: { const: "set" },
              value: { type: "string" },
            },
          },
        ],
      },
    },
  };
  const generated = await generateArtifacts(
    sample.openapi,
    sample.schemas,
    sample.inputHashes,
  );
  const validators = await validatorsFor(generated);

  assert.equal(
    validators.validateTagged({
      discriminator: { label: "literal", discriminator: "preserved" },
      edit: { kind: "set", value: "x" },
    }),
    true,
  );
  assert.deepEqual(
    sample.schemas.Tagged.properties.discriminator.default,
    { discriminator: "default-value" },
  );
  assert.equal(
    validators.validateTagged({
      discriminator: { label: "literal", discriminator: "preserved" },
      edit: { kind: "other", value: "x" },
    }),
    false,
  );

  const malformed = structuredClone(sample.schemas);
  malformed.Tagged.properties.edit.discriminator.propertyName = 1;
  await assert.rejects(
    generateArtifacts(sample.openapi, malformed, sample.inputHashes),
    /unsupported standalone schema feature/,
  );
});

test("standalone validator enforces explicit version, strict fields and Unicode code points", async () => {
  const sample = inputs();
  const generated = await generateArtifacts(
    sample.openapi,
    sample.schemas,
    sample.inputHashes,
  );
  const validators = await validatorsFor(generated);
  const validate = validators.validateSource;
  const exactSource = '{\"n\":9007199254740993,\"x\":0.123456789012345678901}';
  assert.equal(
    validate({
      schema_version: 1,
      source_text: exactSource,
      short_text: "😀😀",
    }),
    true,
  );
  assert.equal(
    validate({ schema_version: 1, source_text: exactSource, short_text: "😀" }),
    false,
  );
  assert.equal(
    validate({
      schema_version: 1,
      source_text: exactSource,
      short_text: "😀😀😀",
    }),
    false,
  );
  assert.equal(
    validate({ source_text: exactSource, short_text: "😀😀" }),
    false,
  );
  assert.equal(
    validate({
      schema_version: true,
      source_text: exactSource,
      short_text: "ok",
    }),
    false,
  );
  assert.equal(
    validate({ schema_version: 2, source_text: exactSource, short_text: "ok" }),
    false,
  );
  assert.equal(
    validate({
      schema_version: 1,
      source_text: exactSource,
      short_text: "ok",
      extra: 1,
    }),
    false,
  );
});

test("forbidden references fail before any network entry point can run", async () => {
  const sample = inputs();
  sample.openapi.components.schemas.Request.properties.remote = {
    $ref: "https://example.invalid/schema",
  };
  let calls = 0;
  const restores = [];
  for (const [object, key] of [
    [globalThis, "fetch"],
    [cli("node:https"), "request"],
    [cli("node:http"), "request"],
    [cli("node:dns"), "lookup"],
  ]) {
    if (typeof object[key] === "function") {
      restores.push(
        mock.method(object, key, (...args) => {
          calls++;
          throw new Error("network forbidden");
        }),
      );
    }
  }
  try {
    await assert.rejects(
      generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes),
      /reference outside bundled schemas/,
    );
    assert.equal(calls, 0);
  } finally {
    for (const restore of restores) restore.mock.restore();
  }
});

test("local references resolve only through included identifiers", async () => {
  const sample = inputs();
  sample.openapi.components.schemas.Request.properties.again = {
    $ref: "urn:deykit:test:Source#/$defs/local",
  };
  sample.schemas.Source.$defs = { local: { type: "string", maxLength: 2 } };
  await assert.doesNotReject(
    generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes),
  );
  sample.openapi.components.schemas.Request.properties.other = {
    $ref: "../private.json#/Thing",
  };
  await assert.rejects(
    generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes),
    /reference outside bundled schemas/,
  );
  delete sample.openapi.components.schemas.Request.properties.other;
  sample.schemas.Source.format = "custom";
  await assert.rejects(
    generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes),
    /unsupported standalone schema feature/,
  );
  delete sample.schemas.Source.format;
  sample.schemas.Source["x-remote-behavior"] = true;
  await assert.rejects(
    generateArtifacts(sample.openapi, sample.schemas, sample.inputHashes),
    /unsupported standalone schema feature/,
  );
});

test("fixed outputs write atomically, check exact bytes, and reject extras and symlinks", async (t) => {
  const sample = inputs();
  const artifacts = await generateArtifacts(
    sample.openapi,
    sample.schemas,
    sample.inputHashes,
  );
  const parent = await mkdtemp(join(tmpdir(), "deykit-contract-test-"));
  const destination = join(parent, "generated");
  t.after(() => rm(parent, { recursive: true, force: true }));
  await writeFiles(artifacts, destination);
  await compareFiles(artifacts, destination);
  const before = await Promise.all(
    (await readdir(destination))
      .sort()
      .map(async (name) => [
        name,
        await readFile(join(destination, name), "utf8"),
      ]),
  );
  await assert.rejects(
    compareFiles(new Map([...artifacts, ["surprise.js", ""]]), destination),
    /Generated contract files are stale/,
  );
  await writeFile(join(destination, "extra.txt"), "private sentinel");
  await assert.rejects(writeFiles(artifacts, destination), /unexpected files/);
  await rm(join(destination, "extra.txt"));
  assert.deepEqual(
    await Promise.all(
      (await readdir(destination))
        .sort()
        .map(async (name) => [
          name,
          await readFile(join(destination, name), "utf8"),
        ]),
    ),
    before,
  );
  const link = join(parent, "linked");
  await symlink(destination, link);
  await assert.rejects(
    writeFiles(artifacts, link),
    /unsafe generated directory/,
  );
  const leafLink = join(destination, "openapi.d.ts");
  await rm(leafLink);
  const outside = join(parent, "outside.txt");
  await writeFile(outside, "untouched");
  await symlink(outside, leafLink);
  await assert.rejects(
    writeFiles(artifacts, destination),
    /Unsafe generated contract file/,
  );
  assert.equal(await readFile(outside, "utf8"), "untouched");
});

test("main accepts exactly one explicit mode", async () => {
  await assert.rejects(main([]), /exactly one/);
  await assert.rejects(main(["--write", "--check"]), /exactly one/);
  await assert.rejects(main(["--force"]), /exactly one/);
});

test("TypeScript 7 accepts generated declarations with library checks enabled", () => {
  const fixture = join(root, "tools/contracts/test/typecheck.cts");
  const tsc = join(root, "node_modules/.bin/tsc");
  execFileSync(
    tsc,
    [
      "--noEmit",
      "--strict",
      "--skipLibCheck",
      "false",
      "--target",
      "ES2022",
      "--module",
      "NodeNext",
      "--moduleResolution",
      "NodeNext",
      "--ignoreConfig",
      fixture,
    ],
    { cwd: root, stdio: "pipe" },
  );
});

test("Vite bundles generated validators without runtime imports or dynamic code", async (t) => {
  const outDir = await mkdtemp(join(tmpdir(), "deykit-validator-bundle-"));
  t.after(() => rm(outDir, { recursive: true, force: true }));
  await build({
    configFile: false,
    logLevel: "silent",
    build: {
      emptyOutDir: true,
      lib: {
        entry: join(root, "tools/contracts/test/validator-bundle-entry.mjs"),
        name: "GeneratedValidators",
        formats: ["iife"],
        fileName: "validator.js",
      },
      outDir,
      minify: false,
    },
  });
  const bundle = await readFile(join(outDir, "validator.js.iife.js"), "utf8");
  assert.doesNotMatch(bundle, /\bimport\s*\(/);
  assert.doesNotMatch(bundle, /\beval\s*\(/);
  const context = { globalThis: {} };
  runInNewContext(bundle, context, {
    codeGeneration: { strings: false, wasm: false },
  });
  assert.equal(
    JSON.stringify(context.globalThis.generatedValidatorResults),
    JSON.stringify({
      valid: true,
      version: false,
      text: '{"n":9007199254740993,"fraction":0.123456789012345678901}',
    }),
  );
});

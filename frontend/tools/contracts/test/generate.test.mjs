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
  assert.match(declarations, /"method": "GET"/);
  assert.match(declarations, /"pathParams": \[\s+"registration_id"/);
  assert.match(declarations, /"queryParams": \[\s+"cursor"/);
  assert.match(declarations, /"successValidator": "validateSource"/);
  assert.match(artifacts.get("openapi.d.ts"), /bootstrapSession/);
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

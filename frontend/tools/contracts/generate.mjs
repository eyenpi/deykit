/** @typedef {import('openapi-typescript').OpenAPITSOptions} OpenAPITSOptions */

import { createHash } from "node:crypto";
import {
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import standaloneCode from "ajv/dist/standalone/index.js";
import openapiTS, { astToString } from "openapi-typescript";
import prettier from "prettier";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(here, "../..");
const outputDirectory = resolve(frontendRoot, "src/api/generated");
const sourcePaths = {
  openapi: resolve(frontendRoot, "api-contracts/openapi.json"),
  schemas: resolve(frontendRoot, "api-contracts/schemas.json"),
};
const versions = Object.freeze({
  typescript: "5.9.3",
  openapiTypescript: "7.13.0",
  ajv: "8.20.0",
  prettier: "3.9.9",
});
const fixedReferenceError =
  "Contracts contain a reference outside bundled schemas.";
const fixedSchemaError =
  "Contracts use an unsupported standalone schema feature.";
const fileNames = Object.freeze([
  "openapi.d.ts",
  "operations.ts",
  "validators.cjs",
  "validators.d.cts",
  "manifest.json",
]);

const sha256 = (source) => createHash("sha256").update(source).digest("hex");
const canonicalJSON = (value) => `${JSON.stringify(value, null, 2)}\n`;
const compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function refsOf(root) {
  const found = [];
  const pending = [root];
  const seen = new Set();
  while (pending.length) {
    const item = pending.pop();
    if (item === null || typeof item !== "object" || seen.has(item)) continue;
    seen.add(item);
    if (Array.isArray(item)) {
      pending.push(...item);
      continue;
    }
    for (const [key, value] of Object.entries(item)) {
      if (
        (key === "$ref" || key === "$dynamicRef") &&
        typeof value === "string"
      ) {
        found.push(value);
      }
      if (value !== null && typeof value === "object") pending.push(value);
    }
  }
  return found;
}

function validateReferences(openapi, schemas) {
  const schemasById = new Map(
    Object.values(schemas)
      .filter((schema) => typeof schema?.$id === "string")
      .map((schema) => [schema.$id, schema]),
  );
  const check = (refs, root) => {
    for (const ref of refs) {
      const separator = ref.indexOf("#");
      if (separator === 0) {
        localPointer(root, decodeURIComponent(ref.slice(1)));
        continue;
      }
      if (separator < 1) throw new Error(fixedReferenceError);
      const target = schemasById.get(ref.slice(0, separator));
      if (!target) throw new Error(fixedReferenceError);
      localPointer(target, decodeURIComponent(ref.slice(separator + 1)));
    }
  };
  check(refsOf(openapi), openapi);
  for (const schema of Object.values(schemas)) check(refsOf(schema), schema);
}

function localPointer(root, pointer) {
  if (pointer === "") return root;
  if (!pointer.startsWith("/")) {
    const pending = [root];
    const seen = new Set();
    while (pending.length) {
      const node = pending.pop();
      if (node === null || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      if (node.$anchor === pointer || node.$dynamicAnchor === pointer)
        return node;
      pending.push(...(Array.isArray(node) ? node : Object.values(node)));
    }
    throw new Error(fixedReferenceError);
  }
  let value = root;
  for (const token of pointer.slice(1).split("/")) {
    if (/~(?![01])/.test(token)) throw new Error(fixedReferenceError);
    const key = decodeURIComponent(
      token.replaceAll("~1", "/").replaceAll("~0", "~"),
    );
    if (value === null || typeof value !== "object" || !(key in value)) {
      throw new Error(fixedReferenceError);
    }
    value = value[key];
  }
  return value;
}

function bundleSchemaIdentifierRefs(openapi, schemas) {
  const schemasById = new Map(
    Object.values(schemas)
      .filter((schema) => typeof schema?.$id === "string")
      .map((schema) => [schema.$id, schema]),
  );
  const transform = (value, expanding = new Set()) => {
    if (value === null || typeof value !== "object") return value;
    if (Array.isArray(value))
      return value.map((child) => transform(child, expanding));
    const refKey =
      typeof value.$ref === "string" && !value.$ref.startsWith("#")
        ? "$ref"
        : typeof value.$dynamicRef === "string" &&
            !value.$dynamicRef.startsWith("#")
          ? "$dynamicRef"
          : undefined;
    if (refKey) {
      if (refKey !== "$ref") throw new Error(fixedReferenceError);
      const ref = value[refKey];
      const separator = ref.indexOf("#");
      const id = ref.slice(0, separator);
      if (!schemasById.has(id) || expanding.has(ref))
        throw new Error(fixedReferenceError);
      const target = localPointer(
        schemasById.get(id),
        decodeURIComponent(ref.slice(separator + 1)),
      );
      const siblings = Object.fromEntries(
        Object.entries(value).filter(([key]) => key !== refKey),
      );
      const expanded = { ...structuredClone(target), ...siblings };
      const next = new Set(expanding);
      next.add(ref);
      return transform(expanded, next);
    }
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        transform(child, expanding),
      ]),
    );
  };
  return transform(openapi);
}

function assertSchemaSubset(schemas) {
  const vocabulary = new Set([
    "$schema",
    "$id",
    "$defs",
    "$ref",
    "$dynamicRef",
    "$anchor",
    "$dynamicAnchor",
    "$comment",
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "discriminator",
    "type",
    "enum",
    "const",
    "format",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "required",
    "properties",
    "additionalProperties",
    "propertyNames",
    "items",
    "prefixItems",
    "contains",
    "minContains",
    "maxContains",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentRequired",
    "dependentSchemas",
    "patternProperties",
    "unevaluatedProperties",
    "unevaluatedItems",
  ]);
  const inspectSchema = (schema) => {
    if (schema === true || schema === false) return;
    if (
      schema === null ||
      typeof schema !== "object" ||
      Array.isArray(schema)
    ) {
      throw new Error(fixedSchemaError);
    }
    for (const [keyword, value] of Object.entries(schema)) {
      if (!vocabulary.has(keyword)) throw new Error(fixedSchemaError);
      if (keyword === "format") throw new Error(fixedSchemaError);
      if (keyword === "discriminator") {
        if (
          value === null ||
          typeof value !== "object" ||
          Array.isArray(value) ||
          typeof value.propertyName !== "string" ||
          !value.propertyName ||
          Object.keys(value).some(
            (key) => !["propertyName", "mapping"].includes(key),
          ) ||
          (value.mapping !== undefined &&
            (value.mapping === null ||
              typeof value.mapping !== "object" ||
              Array.isArray(value.mapping) ||
              Object.values(value.mapping).some(
                (target) => typeof target !== "string",
              )))
        ) {
          throw new Error(fixedSchemaError);
        }
        continue;
      }
      if (schemaMapKeywords.has(keyword)) {
        if (
          value === null ||
          typeof value !== "object" ||
          Array.isArray(value)
        ) {
          throw new Error(fixedSchemaError);
        }
        for (const child of Object.values(value)) inspectSchema(child);
      } else if (
        schemaSingleKeywords.has(keyword) &&
        value !== true &&
        value !== false
      ) {
        inspectSchema(value);
      } else if (schemaArrayKeywords.has(keyword)) {
        if (!Array.isArray(value)) throw new Error(fixedSchemaError);
        for (const child of value) inspectSchema(child);
      }
    }
  };
  for (const schema of Object.values(schemas)) inspectSchema(schema);
}

const schemaMapKeywords = new Set([
  "$defs",
  "properties",
  "patternProperties",
  "dependentSchemas",
]);
const schemaSingleKeywords = new Set([
  "additionalProperties",
  "propertyNames",
  "items",
  "contains",
  "not",
  "if",
  "then",
  "else",
  "unevaluatedProperties",
  "unevaluatedItems",
]);
const schemaArrayKeywords = new Set(["prefixItems", "allOf", "anyOf", "oneOf"]);

function withoutDiscriminator(schema) {
  if (schema === null || typeof schema !== "object" || Array.isArray(schema)) {
    return schema;
  }
  return Object.fromEntries(
    Object.entries(schema).flatMap(([keyword, value]) => {
      if (keyword === "discriminator") return [];
      if (schemaMapKeywords.has(keyword)) {
        return [
          [
            keyword,
            Object.fromEntries(
              Object.entries(value).map(([name, child]) => [
                name,
                withoutDiscriminator(child),
              ]),
            ),
          ],
        ];
      }
      if (schemaSingleKeywords.has(keyword)) {
        return [
          [
            keyword,
            value === true || value === false
              ? value
              : withoutDiscriminator(value),
          ],
        ];
      }
      if (schemaArrayKeywords.has(keyword)) {
        return [[keyword, value.map(withoutDiscriminator)]];
      }
      return [[keyword, value]];
    }),
  );
}

function validatorAlias(name) {
  if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name))
    throw new Error(fixedSchemaError);
  return `validate${name}`;
}

const httpMethods = new Set(["get", "post", "put", "patch", "delete", "head"]);

function componentSchemaName(schema) {
  const reference = schema?.$ref;
  const prefix = "#/components/schemas/";
  if (typeof reference !== "string" || !reference.startsWith(prefix))
    throw new Error(
      "Every API operation must reference a generated JSON schema.",
    );
  const name = decodeURIComponent(reference.slice(prefix.length));
  if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name))
    throw new Error("API operation schema references are invalid.");
  return name;
}

const reportDownloadPolicy = {
  formatParameter: "format",
  reportIdParameter: "report_id",
  maxBytes: 8388608,
  formats: {
    json: { contentType: "application/octet-stream", extension: "json" },
    markdown: { contentType: "text/plain; charset=utf-8", extension: "md" },
  },
};

function sameJson(left, right) {
  const stable = (value) =>
    value !== null && typeof value === "object"
      ? Array.isArray(value)
        ? value.map(stable)
        : Object.fromEntries(
            Object.keys(value)
              .sort(compare)
              .map((key) => [key, stable(value[key])]),
          )
      : value;
  return JSON.stringify(stable(left)) === JSON.stringify(stable(right));
}

function reportDownloadMetadata(path, method, operation, parameters) {
  const annotation = operation["x-deykit-report-download-v1"];
  if (annotation === undefined) return null;
  if (
    method !== "get" ||
    path !==
      "/api/v1/projects/{registration_id}/reports/{report_id}/download" ||
    !sameJson(annotation, reportDownloadPolicy) ||
    operation.requestBody !== undefined
  )
    throw new Error("The report download policy is invalid.");

  const pathParameters = parameters
    .filter((parameter) => parameter?.in === "path")
    .map((parameter) => ({
      name: parameter.name,
      required: parameter.required,
      schemaType: parameter.schema?.type,
      keys: Object.keys(parameter).sort(compare),
    }))
    .sort((a, b) => compare(a.name, b.name));
  if (
    pathParameters.length !== 2 ||
    !sameJson(
      pathParameters.map(({ name, required }) => ({ name, required })),
      [
        { name: "registration_id", required: true },
        { name: "report_id", required: true },
      ],
    ) ||
    pathParameters.some(
      (parameter) =>
        parameter.schemaType !== "string" ||
        parameter.keys.some(
          (key) =>
            !["description", "in", "name", "required", "schema"].includes(key),
        ) ||
        Object.keys(
          parameters.find(
            (item) => item?.in === "path" && item.name === parameter.name,
          )?.schema ?? {},
        ).some((key) => !["title", "type"].includes(key)),
    )
  )
    throw new Error("The report download path parameters are invalid.");

  const queryParameters = parameters.filter(
    (parameter) => parameter?.in === "query",
  );
  const formatSchema = queryParameters[0]?.schema;
  if (
    queryParameters.length !== 1 ||
    queryParameters[0].name !== "format" ||
    queryParameters[0].required !== true ||
    Object.keys(queryParameters[0]).some(
      (key) =>
        !["description", "in", "name", "required", "schema"].includes(key),
    ) ||
    formatSchema === null ||
    typeof formatSchema !== "object" ||
    Array.isArray(formatSchema) ||
    formatSchema.type !== "string" ||
    !sameJson(formatSchema.enum, ["json", "markdown"]) ||
    (formatSchema.title !== undefined &&
      typeof formatSchema.title !== "string") ||
    Object.keys(formatSchema).some(
      (key) => !["enum", "title", "type"].includes(key),
    )
  )
    throw new Error("The report download format parameter is invalid.");

  const successResponses = Object.entries(operation.responses ?? {}).filter(
    ([status]) => /^2(?:[0-9]{2}|XX)$/.test(status),
  );
  if (successResponses.length !== 1 || successResponses[0][0] !== "200")
    throw new Error("The report download must declare only a 200 success.");
  const response = successResponses[0][1];
  if (
    Object.keys(response ?? {}).some(
      (key) => !["content", "description", "headers"].includes(key),
    )
  )
    throw new Error("The report download response shape is invalid.");
  const content = response?.content;
  const media = Object.keys(content ?? {}).sort(compare);
  const expectedMedia = [
    "application/octet-stream",
    "text/plain; charset=utf-8",
  ].sort(compare);
  const binarySchema = { type: "string", format: "binary" };
  if (
    !sameJson(media, expectedMedia) ||
    !sameJson(content["application/octet-stream"]?.schema, binarySchema) ||
    !sameJson(content["text/plain; charset=utf-8"]?.schema, binarySchema)
  )
    throw new Error("The report download response media are invalid.");

  const headers = response.headers ?? {};
  if (
    !sameJson(Object.keys(headers).sort(compare), [
      "Cache-Control",
      "Content-Disposition",
      "X-Content-Type-Options",
    ]) ||
    headers["Content-Disposition"]?.schema?.type !== "string" ||
    headers["Cache-Control"]?.schema?.type !== "string" ||
    headers["Cache-Control"]?.schema?.const !== "no-store" ||
    headers["X-Content-Type-Options"]?.schema?.type !== "string" ||
    headers["X-Content-Type-Options"]?.schema?.const !== "nosniff" ||
    Object.values(headers).some(
      (header) =>
        Object.keys(header ?? {}).some(
          (key) => !["description", "schema"].includes(key),
        ) ||
        (header?.description !== undefined &&
          typeof header.description !== "string"),
    ) ||
    typeof headers["Content-Disposition"]?.description !== "string" ||
    Object.keys(headers["Content-Disposition"]?.schema ?? {}).some(
      (key) => key !== "type",
    ) ||
    Object.keys(headers["Cache-Control"]?.schema ?? {}).some(
      (key) => !["const", "type"].includes(key),
    ) ||
    Object.keys(headers["X-Content-Type-Options"]?.schema ?? {}).some(
      (key) => !["const", "type"].includes(key),
    )
  )
    throw new Error("The report download response headers are invalid.");
  return reportDownloadPolicy;
}

function apiOperations(openapi) {
  const found = [];
  const paths = openapi.paths;
  if (paths === null || typeof paths !== "object" || Array.isArray(paths))
    throw new Error("OpenAPI paths are invalid.");
  for (const [path, item] of Object.entries(paths).sort(([a], [b]) =>
    compare(a, b),
  )) {
    if (item === null || typeof item !== "object" || Array.isArray(item))
      throw new Error("OpenAPI path items are invalid.");
    for (const [method, operation] of Object.entries(item).sort(([a], [b]) =>
      compare(a, b),
    )) {
      if (!httpMethods.has(method)) continue;
      if (operation === null || typeof operation !== "object")
        throw new Error("OpenAPI operations are invalid.");
      if (
        typeof operation.operationId !== "string" ||
        !/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(operation.operationId)
      ) {
        throw new Error("Every API operation must have a stable operationId.");
      }
      const parameters = [
        ...(Array.isArray(item.parameters) ? item.parameters : []),
        ...(Array.isArray(operation.parameters) ? operation.parameters : []),
      ];
      const pathParams = [...path.matchAll(/\{([^}]+)\}/g)].map(
        (match) => match[1],
      );
      const queryParams = parameters
        .filter((parameter) => parameter?.in === "query")
        .map((parameter) => parameter.name)
        .filter((name) => typeof name === "string");
      const bodySchema =
        operation.requestBody?.content?.["application/json"]?.schema;
      const downloadPolicy = reportDownloadMetadata(
        path,
        method,
        operation,
        parameters,
      );
      const successResponses = Object.entries(operation.responses ?? {})
        .filter(([status]) => /^2(?:[0-9]{2}|XX)$/.test(status))
        .sort(([a], [b]) => compare(a, b));
      let success;
      if (downloadPolicy) {
        success = { kind: "report-download", status: 200, ...downloadPolicy };
      } else {
        const validators = {};
        if (successResponses.length === 0)
          throw new Error(
            "Every API operation must declare a supported success response.",
          );
        for (const [status, response] of successResponses) {
          if (status !== "200" && status !== "202")
            throw new Error(
              "API operations may only declare 200 or 202 JSON successes.",
            );
          const media = Object.keys(response?.content ?? {});
          const responseSchema =
            response?.content?.["application/json"]?.schema;
          if (
            media.length !== 1 ||
            media[0] !== "application/json" ||
            !responseSchema
          )
            throw new Error(
              "Every JSON API success must declare one generated JSON schema.",
            );
          validators[status] = validatorAlias(
            componentSchemaName(responseSchema),
          );
        }
        success = { kind: "json", validators };
      }
      found.push({
        id: operation.operationId,
        internal: operation["x-deykit-client-internal"] === true,
        method: method.toUpperCase(),
        path,
        pathParams,
        queryParams: [...new Set(queryParams)].sort(compare),
        bodyValidator: bodySchema
          ? validatorAlias(componentSchemaName(bodySchema))
          : null,
        bodyRequired: Boolean(operation.requestBody?.required),
        success,
      });
    }
  }
  found.sort((a, b) => compare(a.id, b.id));
  if (new Set(found.map((operation) => operation.id)).size !== found.length)
    throw new Error("API operationIds must be unique.");
  return found;
}

function operationDeclarations(openapi) {
  const entries = apiOperations(openapi).filter(
    (operation) => !operation.internal,
  );
  const object = Object.fromEntries(
    entries.map((operation) => [
      operation.id,
      {
        method: operation.method,
        path: operation.path,
        pathParams: operation.pathParams,
        queryParams: operation.queryParams,
        bodyValidator: operation.bodyValidator,
        bodyRequired: operation.bodyRequired,
        success: operation.success,
      },
    ]),
  );
  return [
    "export type ApiOperationId = keyof typeof operationMetadata;",
    "type OperationIdOfKind<K extends ApiOperationId, Kind extends ApiOperationMetadata['success']['kind']> = { [Id in K]: typeof operationMetadata[Id]['success']['kind'] extends Kind ? Id : never }[K];",
    'export type ApiJsonOperationId = OperationIdOfKind<ApiOperationId, "json">;',
    'export type ApiDownloadOperationId = OperationIdOfKind<ApiOperationId, "report-download">;',
    "",
    "export interface ApiJsonSuccess {",
    '  readonly kind: "json";',
    '  readonly validators: Readonly<Partial<Record<"200" | "202", string>>>;',
    "}",
    "export interface ApiReportDownloadSuccess {",
    '  readonly kind: "report-download";',
    "  readonly status: 200;",
    '  readonly formatParameter: "format";',
    '  readonly reportIdParameter: "report_id";',
    "  readonly maxBytes: 8388608;",
    '  readonly formats: { readonly json: { readonly contentType: "application/octet-stream"; readonly extension: "json" }; readonly markdown: { readonly contentType: "text/plain; charset=utf-8"; readonly extension: "md" } };',
    "}",
    "",
    "export interface ApiOperationMetadata {",
    '  readonly method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD";',
    "  readonly path: string;",
    "  readonly pathParams: readonly string[];",
    "  readonly queryParams: readonly string[];",
    "  readonly bodyValidator: string | null;",
    "  readonly bodyRequired: boolean;",
    "  readonly success: ApiJsonSuccess | ApiReportDownloadSuccess;",
    "}",
    "",
    "export const operationMetadata = ",
    `${JSON.stringify(object, null, 2)} as const satisfies Record<string, ApiOperationMetadata>;`,
    "",
  ].join("\n");
}

async function formatted(contents, parser) {
  return prettier.format(contents, { parser });
}

/**
 * Build all exact checked-in artifacts without reading project state or opening network clients.
 * @param {object} openapi
 * @param {Record<string, object>} schemas
 * @param {Readonly<{openapi:string;schemas:string}>} inputHashes
 * @returns {Promise<Map<string,string>>}
 */
export async function generateArtifacts(openapi, schemas, inputHashes) {
  if (
    !/^[0-9a-f]{64}$/.test(inputHashes.openapi) ||
    !/^[0-9a-f]{64}$/.test(inputHashes.schemas)
  ) {
    throw new Error("Contract input hashes are invalid.");
  }
  validateReferences(openapi, schemas);
  assertSchemaSubset(schemas);
  const bundledOpenAPI = bundleSchemaIdentifierRefs(openapi, schemas);
  const sortedSchemas = Object.entries(schemas).sort(([a], [b]) =>
    compare(a, b),
  );
  const ids = new Set();
  const validators = {};
  for (const [name, schema] of sortedSchemas) {
    const alias = validatorAlias(name);
    if (
      typeof schema.$id !== "string" ||
      ids.has(schema.$id) ||
      validators[alias]
    ) {
      throw new Error(fixedSchemaError);
    }
    ids.add(schema.$id);
    validators[alias] = schema.$id;
  }

  const types = astToString(
    await openapiTS(bundledOpenAPI, {
      alphabetize: true,
      immutable: true,
      defaultNonNullable: false,
    }),
  );
  const ajv = new Ajv2020({
    strict: true,
    coerceTypes: false,
    useDefaults: false,
    removeAdditional: false,
    allErrors: false,
    code: { source: true, esm: false },
  });
  for (const [name, schema] of sortedSchemas)
    ajv.addSchema(withoutDiscriminator(schema), name);
  const validatorSource = standaloneCode(ajv, validators);
  const declarationSource = [
    "declare const validators: {",
    ...Object.keys(validators).map(
      (name) => `  readonly ${name}: (value: unknown) => boolean;`,
    ),
    "};",
    "export = validators;",
    "",
  ].join("\n");

  const contents = new Map([
    ["openapi.d.ts", await formatted(types, "typescript")],
    [
      "operations.ts",
      await formatted(operationDeclarations(openapi), "typescript"),
    ],
    ["validators.cjs", await formatted(validatorSource, "babel")],
    ["validators.d.cts", await formatted(declarationSource, "typescript")],
  ]);
  const outputHashes = Object.fromEntries(
    [...contents.entries()]
      .sort(([a], [b]) => compare(a, b))
      .map(([name, text]) => [name, sha256(text)]),
  );
  const manifest = {
    schema_version: 1,
    inputs: { openapi: inputHashes.openapi, schemas: inputHashes.schemas },
    outputs: outputHashes,
    generators: versions,
  };
  contents.set(
    "manifest.json",
    await formatted(canonicalJSON(manifest), "json"),
  );
  return contents;
}

async function assertRealDirectory(path) {
  try {
    const info = await lstat(path);
    if (!info.isDirectory() || info.isSymbolicLink())
      throw new Error("unsafe generated directory");
  } catch (error) {
    if (/** @type {NodeJS.ErrnoException} */ (error).code !== "ENOENT")
      throw error;
  }
}

export async function assertSafeOutputs(contents, directory = outputDirectory) {
  await assertRealDirectory(directory);
  try {
    const names = await readdir(directory);
    if (names.some((name) => !fileNames.includes(name))) {
      throw new Error(
        "Generated contract directory contains unexpected files.",
      );
    }
    for (const name of names) {
      const info = await lstat(join(directory, name));
      if (!info.isFile() || info.isSymbolicLink() || !contents.has(name)) {
        throw new Error(`Unsafe generated contract file: ${name}`);
      }
    }
  } catch (error) {
    if (/** @type {NodeJS.ErrnoException} */ (error).code !== "ENOENT")
      throw error;
  }
}

async function readInputs() {
  const [openapiBytes, schemaBytes] = await Promise.all([
    readFile(sourcePaths.openapi),
    readFile(sourcePaths.schemas),
  ]);
  let openapi;
  let schemas;
  try {
    openapi = JSON.parse(openapiBytes.toString("utf8"));
    schemas = JSON.parse(schemaBytes.toString("utf8"));
  } catch {
    throw new Error("Contract input JSON is invalid.");
  }
  if (
    openapi === null ||
    typeof openapi !== "object" ||
    Array.isArray(openapi) ||
    schemas === null ||
    typeof schemas !== "object" ||
    Array.isArray(schemas)
  ) {
    throw new Error("Contract inputs must be JSON objects.");
  }
  return {
    openapi,
    schemas,
    inputHashes: {
      openapi: sha256(openapiBytes),
      schemas: sha256(schemaBytes),
    },
  };
}

export async function compareFiles(contents, directory = outputDirectory) {
  await assertSafeOutputs(contents, directory);
  let names;
  try {
    names = await readdir(directory);
  } catch (error) {
    if (/** @type {NodeJS.ErrnoException} */ (error).code !== "ENOENT")
      throw error;
    names = [];
  }
  const expectedNames = [...contents.keys()].sort(compare);
  if (JSON.stringify(names.sort(compare)) !== JSON.stringify(expectedNames)) {
    throw new Error("Generated contract files are stale.");
  }
  for (const name of expectedNames) {
    let current;
    try {
      current = await readFile(join(directory, name), "utf8");
    } catch {
      throw new Error(`Generated contract is stale: ${name}`);
    }
    if (current !== contents.get(name))
      throw new Error(`Generated contract is stale: ${name}`);
  }
}

export async function writeFiles(contents, directory = outputDirectory) {
  await assertSafeOutputs(contents, directory);
  await mkdir(directory, { recursive: true });
  const stage = await mkdtemp(
    join(dirname(directory), ".generated-contracts-"),
  );
  try {
    for (const name of fileNames)
      await writeFile(join(stage, name), contents.get(name), { flag: "wx" });
    for (const name of fileNames) {
      const target = join(directory, name);
      try {
        await rename(join(stage, name), target);
      } catch (error) {
        if (
          /** @type {NodeJS.ErrnoException} */ (error).code !== "EEXIST" &&
          /** @type {NodeJS.ErrnoException} */ (error).code !== "EPERM"
        )
          throw error;
        await rm(target);
        await rename(join(stage, name), target);
      }
    }
  } finally {
    await rm(stage, { recursive: true, force: true });
  }
}

/** @param {readonly string[]} argv */
export async function main(argv) {
  if (argv.length !== 1 || (argv[0] !== "--write" && argv[0] !== "--check")) {
    throw new Error("Use exactly one of --write or --check.");
  }
  const { openapi, schemas, inputHashes } = await readInputs();
  const contents = await generateArtifacts(openapi, schemas, inputHashes);
  if (argv[0] === "--check") await compareFiles(contents);
  else await writeFiles(contents);
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    await main(process.argv.slice(2));
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Contract generation failed.";
    console.error(message);
    process.exitCode = 1;
  }
}

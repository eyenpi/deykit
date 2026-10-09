import validators = require("../../../src/api/generated/validators.cjs");
import { operationMetadata, type ApiOperationId } from "../../../src/api/generated/operations.js";
import type { paths } from "../../../src/api/generated/openapi.js";
type Route = keyof paths;
const route: Route = "/api/v1/session/bootstrap";
const operation: ApiOperationId = "listProviderModels";
const operationPath: string = operationMetadata[operation].path;
const accepted: boolean = validators.validateBootstrapRequest({
  schema_version: 1,
});
if (false) {
  // @ts-expect-error unknown operations are excluded from generated metadata
  const unknown: ApiOperationId = "notAnOperation";
  // @ts-expect-error bootstrap is internal and cannot be dispatched publicly
  const internal: ApiOperationId = "bootstrapSession";
  void [unknown, internal];
}
void [route, operationPath, accepted];

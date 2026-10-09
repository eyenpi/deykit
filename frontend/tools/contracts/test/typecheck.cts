import validators = require("../../../src/api/generated/validators.cjs");
import type { paths } from "../../../src/api/generated/openapi.js";
type Route = keyof paths;
const route: Route = "/api/v1/session/bootstrap";
const accepted: boolean = validators.validateBootstrapRequest({
  schema_version: 1,
});
void [route, accepted];

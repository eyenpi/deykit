import validators from "../../../src/api/generated/validators.cjs";

const sourceText = '{"n":9007199254740993,"fraction":0.123456789012345678901}';
globalThis.generatedValidatorResults = {
  valid:
    validators.validateBootstrapRequest({ schema_version: 1 }) &&
    validators.validateFailure({
      schema_version: 1,
      error: { schema_version: 1, code: "safe", message: "safe" },
    }),
  version:
    validators.validateBootstrapRequest({ schema_version: 1.0 }) &&
    validators.validateBootstrapRequest({}),
  text: sourceText,
};

"use strict";
exports.validateBootstrapReply = validate20;
const schema31 = {
  $id: "urn:deykit:transport:BootstrapReply",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    api_version: {
      const: 1,
      default: 1,
      title: "Api Version",
      type: "integer",
    },
    capability: {
      pattern: "^[A-Za-z0-9_-]{43}$",
      title: "Capability",
      type: "string",
    },
    origin: { title: "Origin", type: "string" },
  },
  required: ["capability", "origin"],
  title: "BootstrapReply",
  type: "object",
};
const pattern4 = new RegExp("^[A-Za-z0-9_-]{43}$", "u");
function validate20(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:BootstrapReply" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate20.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.capability === undefined && (missing0 = "capability")) ||
        (data.origin === undefined && (missing0 = "origin"))
      ) {
        validate20.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "api_version" ||
            key0 === "capability" ||
            key0 === "origin"
          )) {
            validate20.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.api_version !== undefined) {
            let data0 = data.api_version;
            const _errs2 = errors;
            if (!(
              typeof data0 == "number" &&
              !(data0 % 1) &&
              !isNaN(data0) &&
              isFinite(data0)
            )) {
              validate20.errors = [
                {
                  instancePath: instancePath + "/api_version",
                  schemaPath: "#/properties/api_version/type",
                  keyword: "type",
                  params: { type: "integer" },
                  message: "must be integer",
                },
              ];
              return false;
            }
            if (1 !== data0) {
              validate20.errors = [
                {
                  instancePath: instancePath + "/api_version",
                  schemaPath: "#/properties/api_version/const",
                  keyword: "const",
                  params: { allowedValue: 1 },
                  message: "must be equal to constant",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.capability !== undefined) {
              let data1 = data.capability;
              const _errs4 = errors;
              if (errors === _errs4) {
                if (typeof data1 === "string") {
                  if (!pattern4.test(data1)) {
                    validate20.errors = [
                      {
                        instancePath: instancePath + "/capability",
                        schemaPath: "#/properties/capability/pattern",
                        keyword: "pattern",
                        params: { pattern: "^[A-Za-z0-9_-]{43}$" },
                        message:
                          'must match pattern "' + "^[A-Za-z0-9_-]{43}$" + '"',
                      },
                    ];
                    return false;
                  }
                } else {
                  validate20.errors = [
                    {
                      instancePath: instancePath + "/capability",
                      schemaPath: "#/properties/capability/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.origin !== undefined) {
                const _errs6 = errors;
                if (typeof data.origin !== "string") {
                  validate20.errors = [
                    {
                      instancePath: instancePath + "/origin",
                      schemaPath: "#/properties/origin/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs6 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate20.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate20.errors = vErrors;
  return errors === 0;
}
validate20.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateBootstrapRequest = validate21;
const schema32 = {
  $id: "urn:deykit:transport:BootstrapRequest",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    schema_version: { const: 1, title: "Schema Version", type: "integer" },
  },
  required: ["schema_version"],
  title: "BootstrapRequest",
  type: "object",
};
function validate21(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:BootstrapRequest" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate21.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (data.schema_version === undefined && (missing0 = "schema_version")) {
        validate21.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(key0 === "schema_version")) {
            validate21.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.schema_version !== undefined) {
            let data0 = data.schema_version;
            if (!(
              typeof data0 == "number" &&
              !(data0 % 1) &&
              !isNaN(data0) &&
              isFinite(data0)
            )) {
              validate21.errors = [
                {
                  instancePath: instancePath + "/schema_version",
                  schemaPath: "#/properties/schema_version/type",
                  keyword: "type",
                  params: { type: "integer" },
                  message: "must be integer",
                },
              ];
              return false;
            }
            if (1 !== data0) {
              validate21.errors = [
                {
                  instancePath: instancePath + "/schema_version",
                  schemaPath: "#/properties/schema_version/const",
                  keyword: "const",
                  params: { allowedValue: 1 },
                  message: "must be equal to constant",
                },
              ];
              return false;
            }
          }
        }
      }
    } else {
      validate21.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate21.errors = vErrors;
  return errors === 0;
}
validate21.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateDemoCreateDTO = validate22;
const schema33 = {
  $id: "urn:deykit:transport:DemoCreateDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    demo: { $ref: "urn:deykit:transport:DemoSummaryDTO#" },
    registration: { $ref: "urn:deykit:transport:RegistrationDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["demo", "registration", "schema_version"],
  title: "DemoCreateDTO",
  type: "object",
};
const schema34 = {
  $id: "urn:deykit:transport:DemoSummaryDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    binding_count: {
      pattern: "^(?:0|[1-9][0-9]*)$",
      title: "Binding Count",
      type: "string",
    },
    case_count: {
      pattern: "^(?:0|[1-9][0-9]*)$",
      title: "Case Count",
      type: "string",
    },
    dataset_id: { title: "Dataset Id", type: "string" },
    decision_id: { title: "Decision Id", type: "string" },
    evidence_mode: {
      const: "authored_fixture",
      title: "Evidence Mode",
      type: "string",
    },
    fixture_set_id: { title: "Fixture Set Id", type: "string" },
    label_count: {
      pattern: "^(?:0|[1-9][0-9]*)$",
      title: "Label Count",
      type: "string",
    },
    operation_id: { title: "Operation Id", type: "string" },
    profile_id: { title: "Profile Id", type: "string" },
    project_id: { title: "Project Id", type: "string" },
    replayed: { title: "Replayed", type: "boolean" },
    revision_id: { title: "Revision Id", type: "string" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: [
    "binding_count",
    "case_count",
    "dataset_id",
    "decision_id",
    "evidence_mode",
    "fixture_set_id",
    "label_count",
    "operation_id",
    "profile_id",
    "project_id",
    "replayed",
    "revision_id",
    "schema_version",
  ],
  title: "DemoSummaryDTO",
  type: "object",
};
const func1 = Object.prototype.hasOwnProperty;
const pattern5 = new RegExp("^(?:0|[1-9][0-9]*)$", "u");
const schema35 = {
  $id: "urn:deykit:transport:RegistrationDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    demo: { title: "Demo", type: "null" },
    execution_active: { title: "Execution Active", type: "boolean" },
    path: { title: "Path", type: "string" },
    project: { $ref: "urn:deykit:transport:ProjectRecordDTO#" },
    project_etag: {
      pattern: "^[0-9a-f]{64}$",
      title: "Project Etag",
      type: "string",
    },
    record_count: {
      pattern: "^(?:0|[1-9][0-9]*)$",
      title: "Record Count",
      type: "string",
    },
    registration_id: { title: "Registration Id", type: "string" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: [
    "execution_active",
    "path",
    "project",
    "project_etag",
    "record_count",
    "registration_id",
    "schema_version",
  ],
  title: "RegistrationDTO",
  type: "object",
};
const schema36 = {
  $id: "urn:deykit:transport:ProjectRecordDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    created_at: { title: "Created At", type: "string" },
    default_provider_id: {
      anyOf: [{ type: "string" }, { type: "null" }],
      title: "Default Provider Id",
    },
    id: { title: "Id", type: "string" },
    name: { minLength: 1, title: "Name", type: "string" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["created_at", "id", "name", "schema_version"],
  title: "ProjectRecordDTO",
  type: "object",
};
const func2 = require("ajv/dist/runtime/ucs2length").default;
const pattern8 = new RegExp("^[0-9a-f]{64}$", "u");
function validate23(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:RegistrationDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate23.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.execution_active === undefined &&
          (missing0 = "execution_active")) ||
        (data.path === undefined && (missing0 = "path")) ||
        (data.project === undefined && (missing0 = "project")) ||
        (data.project_etag === undefined && (missing0 = "project_etag")) ||
        (data.record_count === undefined && (missing0 = "record_count")) ||
        (data.registration_id === undefined &&
          (missing0 = "registration_id")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate23.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "demo" ||
            key0 === "execution_active" ||
            key0 === "path" ||
            key0 === "project" ||
            key0 === "project_etag" ||
            key0 === "record_count" ||
            key0 === "registration_id" ||
            key0 === "schema_version"
          )) {
            validate23.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.demo !== undefined) {
            const _errs2 = errors;
            if (data.demo !== null) {
              validate23.errors = [
                {
                  instancePath: instancePath + "/demo",
                  schemaPath: "#/properties/demo/type",
                  keyword: "type",
                  params: { type: "null" },
                  message: "must be null",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.execution_active !== undefined) {
              const _errs4 = errors;
              if (typeof data.execution_active !== "boolean") {
                validate23.errors = [
                  {
                    instancePath: instancePath + "/execution_active",
                    schemaPath: "#/properties/execution_active/type",
                    keyword: "type",
                    params: { type: "boolean" },
                    message: "must be boolean",
                  },
                ];
                return false;
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.path !== undefined) {
                const _errs6 = errors;
                if (typeof data.path !== "string") {
                  validate23.errors = [
                    {
                      instancePath: instancePath + "/path",
                      schemaPath: "#/properties/path/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs6 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.project !== undefined) {
                  let data3 = data.project;
                  const _errs8 = errors;
                  const _errs9 = errors;
                  if (errors === _errs9) {
                    if (
                      data3 &&
                      typeof data3 == "object" &&
                      !Array.isArray(data3)
                    ) {
                      let missing1;
                      if (
                        (data3.created_at === undefined &&
                          (missing1 = "created_at")) ||
                        (data3.id === undefined && (missing1 = "id")) ||
                        (data3.name === undefined && (missing1 = "name")) ||
                        (data3.schema_version === undefined &&
                          (missing1 = "schema_version"))
                      ) {
                        validate23.errors = [
                          {
                            instancePath: instancePath + "/project",
                            schemaPath:
                              "urn:deykit:transport:ProjectRecordDTO#/required",
                            keyword: "required",
                            params: { missingProperty: missing1 },
                            message:
                              "must have required property '" + missing1 + "'",
                          },
                        ];
                        return false;
                      } else {
                        const _errs11 = errors;
                        for (const key1 in data3) {
                          if (!(
                            key1 === "created_at" ||
                            key1 === "default_provider_id" ||
                            key1 === "id" ||
                            key1 === "name" ||
                            key1 === "schema_version"
                          )) {
                            validate23.errors = [
                              {
                                instancePath: instancePath + "/project",
                                schemaPath:
                                  "urn:deykit:transport:ProjectRecordDTO#/additionalProperties",
                                keyword: "additionalProperties",
                                params: { additionalProperty: key1 },
                                message: "must NOT have additional properties",
                              },
                            ];
                            return false;
                            break;
                          }
                        }
                        if (_errs11 === errors) {
                          if (data3.created_at !== undefined) {
                            const _errs12 = errors;
                            if (typeof data3.created_at !== "string") {
                              validate23.errors = [
                                {
                                  instancePath:
                                    instancePath + "/project/created_at",
                                  schemaPath:
                                    "urn:deykit:transport:ProjectRecordDTO#/properties/created_at/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                },
                              ];
                              return false;
                            }
                            var valid2 = _errs12 === errors;
                          } else {
                            var valid2 = true;
                          }
                          if (valid2) {
                            if (data3.default_provider_id !== undefined) {
                              let data5 = data3.default_provider_id;
                              const _errs14 = errors;
                              const _errs15 = errors;
                              let valid3 = false;
                              const _errs16 = errors;
                              if (typeof data5 !== "string") {
                                const err0 = {
                                  instancePath:
                                    instancePath +
                                    "/project/default_provider_id",
                                  schemaPath:
                                    "urn:deykit:transport:ProjectRecordDTO#/properties/default_provider_id/anyOf/0/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                };
                                if (vErrors === null) {
                                  vErrors = [err0];
                                } else {
                                  vErrors.push(err0);
                                }
                                errors++;
                              }
                              var _valid0 = _errs16 === errors;
                              valid3 = valid3 || _valid0;
                              const _errs18 = errors;
                              if (data5 !== null) {
                                const err1 = {
                                  instancePath:
                                    instancePath +
                                    "/project/default_provider_id",
                                  schemaPath:
                                    "urn:deykit:transport:ProjectRecordDTO#/properties/default_provider_id/anyOf/1/type",
                                  keyword: "type",
                                  params: { type: "null" },
                                  message: "must be null",
                                };
                                if (vErrors === null) {
                                  vErrors = [err1];
                                } else {
                                  vErrors.push(err1);
                                }
                                errors++;
                              }
                              var _valid0 = _errs18 === errors;
                              valid3 = valid3 || _valid0;
                              if (!valid3) {
                                const err2 = {
                                  instancePath:
                                    instancePath +
                                    "/project/default_provider_id",
                                  schemaPath:
                                    "urn:deykit:transport:ProjectRecordDTO#/properties/default_provider_id/anyOf",
                                  keyword: "anyOf",
                                  params: {},
                                  message: "must match a schema in anyOf",
                                };
                                if (vErrors === null) {
                                  vErrors = [err2];
                                } else {
                                  vErrors.push(err2);
                                }
                                errors++;
                                validate23.errors = vErrors;
                                return false;
                              } else {
                                errors = _errs15;
                                if (vErrors !== null) {
                                  if (_errs15) {
                                    vErrors.length = _errs15;
                                  } else {
                                    vErrors = null;
                                  }
                                }
                              }
                              var valid2 = _errs14 === errors;
                            } else {
                              var valid2 = true;
                            }
                            if (valid2) {
                              if (data3.id !== undefined) {
                                const _errs20 = errors;
                                if (typeof data3.id !== "string") {
                                  validate23.errors = [
                                    {
                                      instancePath:
                                        instancePath + "/project/id",
                                      schemaPath:
                                        "urn:deykit:transport:ProjectRecordDTO#/properties/id/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid2 = _errs20 === errors;
                              } else {
                                var valid2 = true;
                              }
                              if (valid2) {
                                if (data3.name !== undefined) {
                                  let data7 = data3.name;
                                  const _errs22 = errors;
                                  if (errors === _errs22) {
                                    if (typeof data7 === "string") {
                                      if (func2(data7) < 1) {
                                        validate23.errors = [
                                          {
                                            instancePath:
                                              instancePath + "/project/name",
                                            schemaPath:
                                              "urn:deykit:transport:ProjectRecordDTO#/properties/name/minLength",
                                            keyword: "minLength",
                                            params: { limit: 1 },
                                            message:
                                              "must NOT have fewer than 1 characters",
                                          },
                                        ];
                                        return false;
                                      }
                                    } else {
                                      validate23.errors = [
                                        {
                                          instancePath:
                                            instancePath + "/project/name",
                                          schemaPath:
                                            "urn:deykit:transport:ProjectRecordDTO#/properties/name/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                  }
                                  var valid2 = _errs22 === errors;
                                } else {
                                  var valid2 = true;
                                }
                                if (valid2) {
                                  if (data3.schema_version !== undefined) {
                                    let data8 = data3.schema_version;
                                    const _errs24 = errors;
                                    if (!(
                                      typeof data8 == "number" &&
                                      !(data8 % 1) &&
                                      !isNaN(data8) &&
                                      isFinite(data8)
                                    )) {
                                      validate23.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/project/schema_version",
                                          schemaPath:
                                            "urn:deykit:transport:ProjectRecordDTO#/properties/schema_version/type",
                                          keyword: "type",
                                          params: { type: "integer" },
                                          message: "must be integer",
                                        },
                                      ];
                                      return false;
                                    }
                                    if (1 !== data8) {
                                      validate23.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/project/schema_version",
                                          schemaPath:
                                            "urn:deykit:transport:ProjectRecordDTO#/properties/schema_version/const",
                                          keyword: "const",
                                          params: { allowedValue: 1 },
                                          message: "must be equal to constant",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid2 = _errs24 === errors;
                                  } else {
                                    var valid2 = true;
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    } else {
                      validate23.errors = [
                        {
                          instancePath: instancePath + "/project",
                          schemaPath:
                            "urn:deykit:transport:ProjectRecordDTO#/type",
                          keyword: "type",
                          params: { type: "object" },
                          message: "must be object",
                        },
                      ];
                      return false;
                    }
                  }
                  var valid0 = _errs8 === errors;
                } else {
                  var valid0 = true;
                }
                if (valid0) {
                  if (data.project_etag !== undefined) {
                    let data9 = data.project_etag;
                    const _errs26 = errors;
                    if (errors === _errs26) {
                      if (typeof data9 === "string") {
                        if (!pattern8.test(data9)) {
                          validate23.errors = [
                            {
                              instancePath: instancePath + "/project_etag",
                              schemaPath: "#/properties/project_etag/pattern",
                              keyword: "pattern",
                              params: { pattern: "^[0-9a-f]{64}$" },
                              message:
                                'must match pattern "' + "^[0-9a-f]{64}$" + '"',
                            },
                          ];
                          return false;
                        }
                      } else {
                        validate23.errors = [
                          {
                            instancePath: instancePath + "/project_etag",
                            schemaPath: "#/properties/project_etag/type",
                            keyword: "type",
                            params: { type: "string" },
                            message: "must be string",
                          },
                        ];
                        return false;
                      }
                    }
                    var valid0 = _errs26 === errors;
                  } else {
                    var valid0 = true;
                  }
                  if (valid0) {
                    if (data.record_count !== undefined) {
                      let data10 = data.record_count;
                      const _errs28 = errors;
                      if (errors === _errs28) {
                        if (typeof data10 === "string") {
                          if (!pattern5.test(data10)) {
                            validate23.errors = [
                              {
                                instancePath: instancePath + "/record_count",
                                schemaPath: "#/properties/record_count/pattern",
                                keyword: "pattern",
                                params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                                message:
                                  'must match pattern "' +
                                  "^(?:0|[1-9][0-9]*)$" +
                                  '"',
                              },
                            ];
                            return false;
                          }
                        } else {
                          validate23.errors = [
                            {
                              instancePath: instancePath + "/record_count",
                              schemaPath: "#/properties/record_count/type",
                              keyword: "type",
                              params: { type: "string" },
                              message: "must be string",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid0 = _errs28 === errors;
                    } else {
                      var valid0 = true;
                    }
                    if (valid0) {
                      if (data.registration_id !== undefined) {
                        const _errs30 = errors;
                        if (typeof data.registration_id !== "string") {
                          validate23.errors = [
                            {
                              instancePath: instancePath + "/registration_id",
                              schemaPath: "#/properties/registration_id/type",
                              keyword: "type",
                              params: { type: "string" },
                              message: "must be string",
                            },
                          ];
                          return false;
                        }
                        var valid0 = _errs30 === errors;
                      } else {
                        var valid0 = true;
                      }
                      if (valid0) {
                        if (data.schema_version !== undefined) {
                          let data12 = data.schema_version;
                          const _errs32 = errors;
                          if (!(
                            typeof data12 == "number" &&
                            !(data12 % 1) &&
                            !isNaN(data12) &&
                            isFinite(data12)
                          )) {
                            validate23.errors = [
                              {
                                instancePath: instancePath + "/schema_version",
                                schemaPath: "#/properties/schema_version/type",
                                keyword: "type",
                                params: { type: "integer" },
                                message: "must be integer",
                              },
                            ];
                            return false;
                          }
                          if (1 !== data12) {
                            validate23.errors = [
                              {
                                instancePath: instancePath + "/schema_version",
                                schemaPath: "#/properties/schema_version/const",
                                keyword: "const",
                                params: { allowedValue: 1 },
                                message: "must be equal to constant",
                              },
                            ];
                            return false;
                          }
                          var valid0 = _errs32 === errors;
                        } else {
                          var valid0 = true;
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    } else {
      validate23.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate23.errors = vErrors;
  return errors === 0;
}
validate23.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
function validate22(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:DemoCreateDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate22.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.demo === undefined && (missing0 = "demo")) ||
        (data.registration === undefined && (missing0 = "registration")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate22.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "demo" ||
            key0 === "registration" ||
            key0 === "schema_version"
          )) {
            validate22.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.demo !== undefined) {
            let data0 = data.demo;
            const _errs2 = errors;
            const _errs3 = errors;
            if (errors === _errs3) {
              if (data0 && typeof data0 == "object" && !Array.isArray(data0)) {
                let missing1;
                if (
                  (data0.binding_count === undefined &&
                    (missing1 = "binding_count")) ||
                  (data0.case_count === undefined &&
                    (missing1 = "case_count")) ||
                  (data0.dataset_id === undefined &&
                    (missing1 = "dataset_id")) ||
                  (data0.decision_id === undefined &&
                    (missing1 = "decision_id")) ||
                  (data0.evidence_mode === undefined &&
                    (missing1 = "evidence_mode")) ||
                  (data0.fixture_set_id === undefined &&
                    (missing1 = "fixture_set_id")) ||
                  (data0.label_count === undefined &&
                    (missing1 = "label_count")) ||
                  (data0.operation_id === undefined &&
                    (missing1 = "operation_id")) ||
                  (data0.profile_id === undefined &&
                    (missing1 = "profile_id")) ||
                  (data0.project_id === undefined &&
                    (missing1 = "project_id")) ||
                  (data0.replayed === undefined && (missing1 = "replayed")) ||
                  (data0.revision_id === undefined &&
                    (missing1 = "revision_id")) ||
                  (data0.schema_version === undefined &&
                    (missing1 = "schema_version"))
                ) {
                  validate22.errors = [
                    {
                      instancePath: instancePath + "/demo",
                      schemaPath:
                        "urn:deykit:transport:DemoSummaryDTO#/required",
                      keyword: "required",
                      params: { missingProperty: missing1 },
                      message: "must have required property '" + missing1 + "'",
                    },
                  ];
                  return false;
                } else {
                  const _errs5 = errors;
                  for (const key1 in data0) {
                    if (!func1.call(schema34.properties, key1)) {
                      validate22.errors = [
                        {
                          instancePath: instancePath + "/demo",
                          schemaPath:
                            "urn:deykit:transport:DemoSummaryDTO#/additionalProperties",
                          keyword: "additionalProperties",
                          params: { additionalProperty: key1 },
                          message: "must NOT have additional properties",
                        },
                      ];
                      return false;
                      break;
                    }
                  }
                  if (_errs5 === errors) {
                    if (data0.binding_count !== undefined) {
                      let data1 = data0.binding_count;
                      const _errs6 = errors;
                      if (errors === _errs6) {
                        if (typeof data1 === "string") {
                          if (!pattern5.test(data1)) {
                            validate22.errors = [
                              {
                                instancePath:
                                  instancePath + "/demo/binding_count",
                                schemaPath:
                                  "urn:deykit:transport:DemoSummaryDTO#/properties/binding_count/pattern",
                                keyword: "pattern",
                                params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                                message:
                                  'must match pattern "' +
                                  "^(?:0|[1-9][0-9]*)$" +
                                  '"',
                              },
                            ];
                            return false;
                          }
                        } else {
                          validate22.errors = [
                            {
                              instancePath:
                                instancePath + "/demo/binding_count",
                              schemaPath:
                                "urn:deykit:transport:DemoSummaryDTO#/properties/binding_count/type",
                              keyword: "type",
                              params: { type: "string" },
                              message: "must be string",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid2 = _errs6 === errors;
                    } else {
                      var valid2 = true;
                    }
                    if (valid2) {
                      if (data0.case_count !== undefined) {
                        let data2 = data0.case_count;
                        const _errs8 = errors;
                        if (errors === _errs8) {
                          if (typeof data2 === "string") {
                            if (!pattern5.test(data2)) {
                              validate22.errors = [
                                {
                                  instancePath:
                                    instancePath + "/demo/case_count",
                                  schemaPath:
                                    "urn:deykit:transport:DemoSummaryDTO#/properties/case_count/pattern",
                                  keyword: "pattern",
                                  params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                                  message:
                                    'must match pattern "' +
                                    "^(?:0|[1-9][0-9]*)$" +
                                    '"',
                                },
                              ];
                              return false;
                            }
                          } else {
                            validate22.errors = [
                              {
                                instancePath: instancePath + "/demo/case_count",
                                schemaPath:
                                  "urn:deykit:transport:DemoSummaryDTO#/properties/case_count/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                        }
                        var valid2 = _errs8 === errors;
                      } else {
                        var valid2 = true;
                      }
                      if (valid2) {
                        if (data0.dataset_id !== undefined) {
                          const _errs10 = errors;
                          if (typeof data0.dataset_id !== "string") {
                            validate22.errors = [
                              {
                                instancePath: instancePath + "/demo/dataset_id",
                                schemaPath:
                                  "urn:deykit:transport:DemoSummaryDTO#/properties/dataset_id/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                          var valid2 = _errs10 === errors;
                        } else {
                          var valid2 = true;
                        }
                        if (valid2) {
                          if (data0.decision_id !== undefined) {
                            const _errs12 = errors;
                            if (typeof data0.decision_id !== "string") {
                              validate22.errors = [
                                {
                                  instancePath:
                                    instancePath + "/demo/decision_id",
                                  schemaPath:
                                    "urn:deykit:transport:DemoSummaryDTO#/properties/decision_id/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                },
                              ];
                              return false;
                            }
                            var valid2 = _errs12 === errors;
                          } else {
                            var valid2 = true;
                          }
                          if (valid2) {
                            if (data0.evidence_mode !== undefined) {
                              let data5 = data0.evidence_mode;
                              const _errs14 = errors;
                              if (typeof data5 !== "string") {
                                validate22.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/demo/evidence_mode",
                                    schemaPath:
                                      "urn:deykit:transport:DemoSummaryDTO#/properties/evidence_mode/type",
                                    keyword: "type",
                                    params: { type: "string" },
                                    message: "must be string",
                                  },
                                ];
                                return false;
                              }
                              if ("authored_fixture" !== data5) {
                                validate22.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/demo/evidence_mode",
                                    schemaPath:
                                      "urn:deykit:transport:DemoSummaryDTO#/properties/evidence_mode/const",
                                    keyword: "const",
                                    params: {
                                      allowedValue: "authored_fixture",
                                    },
                                    message: "must be equal to constant",
                                  },
                                ];
                                return false;
                              }
                              var valid2 = _errs14 === errors;
                            } else {
                              var valid2 = true;
                            }
                            if (valid2) {
                              if (data0.fixture_set_id !== undefined) {
                                const _errs16 = errors;
                                if (typeof data0.fixture_set_id !== "string") {
                                  validate22.errors = [
                                    {
                                      instancePath:
                                        instancePath + "/demo/fixture_set_id",
                                      schemaPath:
                                        "urn:deykit:transport:DemoSummaryDTO#/properties/fixture_set_id/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid2 = _errs16 === errors;
                              } else {
                                var valid2 = true;
                              }
                              if (valid2) {
                                if (data0.label_count !== undefined) {
                                  let data7 = data0.label_count;
                                  const _errs18 = errors;
                                  if (errors === _errs18) {
                                    if (typeof data7 === "string") {
                                      if (!pattern5.test(data7)) {
                                        validate22.errors = [
                                          {
                                            instancePath:
                                              instancePath +
                                              "/demo/label_count",
                                            schemaPath:
                                              "urn:deykit:transport:DemoSummaryDTO#/properties/label_count/pattern",
                                            keyword: "pattern",
                                            params: {
                                              pattern: "^(?:0|[1-9][0-9]*)$",
                                            },
                                            message:
                                              'must match pattern "' +
                                              "^(?:0|[1-9][0-9]*)$" +
                                              '"',
                                          },
                                        ];
                                        return false;
                                      }
                                    } else {
                                      validate22.errors = [
                                        {
                                          instancePath:
                                            instancePath + "/demo/label_count",
                                          schemaPath:
                                            "urn:deykit:transport:DemoSummaryDTO#/properties/label_count/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                  }
                                  var valid2 = _errs18 === errors;
                                } else {
                                  var valid2 = true;
                                }
                                if (valid2) {
                                  if (data0.operation_id !== undefined) {
                                    const _errs20 = errors;
                                    if (
                                      typeof data0.operation_id !== "string"
                                    ) {
                                      validate22.errors = [
                                        {
                                          instancePath:
                                            instancePath + "/demo/operation_id",
                                          schemaPath:
                                            "urn:deykit:transport:DemoSummaryDTO#/properties/operation_id/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid2 = _errs20 === errors;
                                  } else {
                                    var valid2 = true;
                                  }
                                  if (valid2) {
                                    if (data0.profile_id !== undefined) {
                                      const _errs22 = errors;
                                      if (
                                        typeof data0.profile_id !== "string"
                                      ) {
                                        validate22.errors = [
                                          {
                                            instancePath:
                                              instancePath + "/demo/profile_id",
                                            schemaPath:
                                              "urn:deykit:transport:DemoSummaryDTO#/properties/profile_id/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          },
                                        ];
                                        return false;
                                      }
                                      var valid2 = _errs22 === errors;
                                    } else {
                                      var valid2 = true;
                                    }
                                    if (valid2) {
                                      if (data0.project_id !== undefined) {
                                        const _errs24 = errors;
                                        if (
                                          typeof data0.project_id !== "string"
                                        ) {
                                          validate22.errors = [
                                            {
                                              instancePath:
                                                instancePath +
                                                "/demo/project_id",
                                              schemaPath:
                                                "urn:deykit:transport:DemoSummaryDTO#/properties/project_id/type",
                                              keyword: "type",
                                              params: { type: "string" },
                                              message: "must be string",
                                            },
                                          ];
                                          return false;
                                        }
                                        var valid2 = _errs24 === errors;
                                      } else {
                                        var valid2 = true;
                                      }
                                      if (valid2) {
                                        if (data0.replayed !== undefined) {
                                          const _errs26 = errors;
                                          if (
                                            typeof data0.replayed !== "boolean"
                                          ) {
                                            validate22.errors = [
                                              {
                                                instancePath:
                                                  instancePath +
                                                  "/demo/replayed",
                                                schemaPath:
                                                  "urn:deykit:transport:DemoSummaryDTO#/properties/replayed/type",
                                                keyword: "type",
                                                params: { type: "boolean" },
                                                message: "must be boolean",
                                              },
                                            ];
                                            return false;
                                          }
                                          var valid2 = _errs26 === errors;
                                        } else {
                                          var valid2 = true;
                                        }
                                        if (valid2) {
                                          if (data0.revision_id !== undefined) {
                                            const _errs28 = errors;
                                            if (
                                              typeof data0.revision_id !==
                                              "string"
                                            ) {
                                              validate22.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/demo/revision_id",
                                                  schemaPath:
                                                    "urn:deykit:transport:DemoSummaryDTO#/properties/revision_id/type",
                                                  keyword: "type",
                                                  params: { type: "string" },
                                                  message: "must be string",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid2 = _errs28 === errors;
                                          } else {
                                            var valid2 = true;
                                          }
                                          if (valid2) {
                                            if (
                                              data0.schema_version !== undefined
                                            ) {
                                              let data13 = data0.schema_version;
                                              const _errs30 = errors;
                                              if (!(
                                                typeof data13 == "number" &&
                                                !(data13 % 1) &&
                                                !isNaN(data13) &&
                                                isFinite(data13)
                                              )) {
                                                validate22.errors = [
                                                  {
                                                    instancePath:
                                                      instancePath +
                                                      "/demo/schema_version",
                                                    schemaPath:
                                                      "urn:deykit:transport:DemoSummaryDTO#/properties/schema_version/type",
                                                    keyword: "type",
                                                    params: { type: "integer" },
                                                    message: "must be integer",
                                                  },
                                                ];
                                                return false;
                                              }
                                              if (1 !== data13) {
                                                validate22.errors = [
                                                  {
                                                    instancePath:
                                                      instancePath +
                                                      "/demo/schema_version",
                                                    schemaPath:
                                                      "urn:deykit:transport:DemoSummaryDTO#/properties/schema_version/const",
                                                    keyword: "const",
                                                    params: { allowedValue: 1 },
                                                    message:
                                                      "must be equal to constant",
                                                  },
                                                ];
                                                return false;
                                              }
                                              var valid2 = _errs30 === errors;
                                            } else {
                                              var valid2 = true;
                                            }
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              } else {
                validate22.errors = [
                  {
                    instancePath: instancePath + "/demo",
                    schemaPath: "urn:deykit:transport:DemoSummaryDTO#/type",
                    keyword: "type",
                    params: { type: "object" },
                    message: "must be object",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.registration !== undefined) {
              const _errs32 = errors;
              if (
                !validate23(data.registration, {
                  instancePath: instancePath + "/registration",
                  parentData: data,
                  parentDataProperty: "registration",
                  rootData,
                  dynamicAnchors,
                })
              ) {
                vErrors =
                  vErrors === null
                    ? validate23.errors
                    : vErrors.concat(validate23.errors);
                errors = vErrors.length;
              }
              var valid0 = _errs32 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.schema_version !== undefined) {
                let data15 = data.schema_version;
                const _errs33 = errors;
                if (!(
                  typeof data15 == "number" &&
                  !(data15 % 1) &&
                  !isNaN(data15) &&
                  isFinite(data15)
                )) {
                  validate22.errors = [
                    {
                      instancePath: instancePath + "/schema_version",
                      schemaPath: "#/properties/schema_version/type",
                      keyword: "type",
                      params: { type: "integer" },
                      message: "must be integer",
                    },
                  ];
                  return false;
                }
                if (1 !== data15) {
                  validate22.errors = [
                    {
                      instancePath: instancePath + "/schema_version",
                      schemaPath: "#/properties/schema_version/const",
                      keyword: "const",
                      params: { allowedValue: 1 },
                      message: "must be equal to constant",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs33 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate22.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate22.errors = vErrors;
  return errors === 0;
}
validate22.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateDemoCreateRequest = validate25;
const schema37 = {
  $id: "urn:deykit:transport:DemoCreateRequest",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    operation_id: { title: "Operation Id", type: "string" },
    path: { minLength: 1, title: "Path", type: "string" },
    schema_version: { const: 1, title: "Schema Version", type: "integer" },
  },
  required: ["operation_id", "path", "schema_version"],
  title: "DemoCreateRequest",
  type: "object",
};
function validate25(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:DemoCreateRequest" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate25.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.operation_id === undefined && (missing0 = "operation_id")) ||
        (data.path === undefined && (missing0 = "path")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate25.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "operation_id" ||
            key0 === "path" ||
            key0 === "schema_version"
          )) {
            validate25.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.operation_id !== undefined) {
            const _errs2 = errors;
            if (typeof data.operation_id !== "string") {
              validate25.errors = [
                {
                  instancePath: instancePath + "/operation_id",
                  schemaPath: "#/properties/operation_id/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.path !== undefined) {
              let data1 = data.path;
              const _errs4 = errors;
              if (errors === _errs4) {
                if (typeof data1 === "string") {
                  if (func2(data1) < 1) {
                    validate25.errors = [
                      {
                        instancePath: instancePath + "/path",
                        schemaPath: "#/properties/path/minLength",
                        keyword: "minLength",
                        params: { limit: 1 },
                        message: "must NOT have fewer than 1 characters",
                      },
                    ];
                    return false;
                  }
                } else {
                  validate25.errors = [
                    {
                      instancePath: instancePath + "/path",
                      schemaPath: "#/properties/path/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.schema_version !== undefined) {
                let data2 = data.schema_version;
                const _errs6 = errors;
                if (!(
                  typeof data2 == "number" &&
                  !(data2 % 1) &&
                  !isNaN(data2) &&
                  isFinite(data2)
                )) {
                  validate25.errors = [
                    {
                      instancePath: instancePath + "/schema_version",
                      schemaPath: "#/properties/schema_version/type",
                      keyword: "type",
                      params: { type: "integer" },
                      message: "must be integer",
                    },
                  ];
                  return false;
                }
                if (1 !== data2) {
                  validate25.errors = [
                    {
                      instancePath: instancePath + "/schema_version",
                      schemaPath: "#/properties/schema_version/const",
                      keyword: "const",
                      params: { allowedValue: 1 },
                      message: "must be equal to constant",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs6 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate25.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate25.errors = vErrors;
  return errors === 0;
}
validate25.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateDemoSummaryDTO = validate26;
function validate26(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:DemoSummaryDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate26.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.binding_count === undefined && (missing0 = "binding_count")) ||
        (data.case_count === undefined && (missing0 = "case_count")) ||
        (data.dataset_id === undefined && (missing0 = "dataset_id")) ||
        (data.decision_id === undefined && (missing0 = "decision_id")) ||
        (data.evidence_mode === undefined && (missing0 = "evidence_mode")) ||
        (data.fixture_set_id === undefined && (missing0 = "fixture_set_id")) ||
        (data.label_count === undefined && (missing0 = "label_count")) ||
        (data.operation_id === undefined && (missing0 = "operation_id")) ||
        (data.profile_id === undefined && (missing0 = "profile_id")) ||
        (data.project_id === undefined && (missing0 = "project_id")) ||
        (data.replayed === undefined && (missing0 = "replayed")) ||
        (data.revision_id === undefined && (missing0 = "revision_id")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate26.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!func1.call(schema34.properties, key0)) {
            validate26.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.binding_count !== undefined) {
            let data0 = data.binding_count;
            const _errs2 = errors;
            if (errors === _errs2) {
              if (typeof data0 === "string") {
                if (!pattern5.test(data0)) {
                  validate26.errors = [
                    {
                      instancePath: instancePath + "/binding_count",
                      schemaPath: "#/properties/binding_count/pattern",
                      keyword: "pattern",
                      params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                      message:
                        'must match pattern "' + "^(?:0|[1-9][0-9]*)$" + '"',
                    },
                  ];
                  return false;
                }
              } else {
                validate26.errors = [
                  {
                    instancePath: instancePath + "/binding_count",
                    schemaPath: "#/properties/binding_count/type",
                    keyword: "type",
                    params: { type: "string" },
                    message: "must be string",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.case_count !== undefined) {
              let data1 = data.case_count;
              const _errs4 = errors;
              if (errors === _errs4) {
                if (typeof data1 === "string") {
                  if (!pattern5.test(data1)) {
                    validate26.errors = [
                      {
                        instancePath: instancePath + "/case_count",
                        schemaPath: "#/properties/case_count/pattern",
                        keyword: "pattern",
                        params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                        message:
                          'must match pattern "' + "^(?:0|[1-9][0-9]*)$" + '"',
                      },
                    ];
                    return false;
                  }
                } else {
                  validate26.errors = [
                    {
                      instancePath: instancePath + "/case_count",
                      schemaPath: "#/properties/case_count/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.dataset_id !== undefined) {
                const _errs6 = errors;
                if (typeof data.dataset_id !== "string") {
                  validate26.errors = [
                    {
                      instancePath: instancePath + "/dataset_id",
                      schemaPath: "#/properties/dataset_id/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs6 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.decision_id !== undefined) {
                  const _errs8 = errors;
                  if (typeof data.decision_id !== "string") {
                    validate26.errors = [
                      {
                        instancePath: instancePath + "/decision_id",
                        schemaPath: "#/properties/decision_id/type",
                        keyword: "type",
                        params: { type: "string" },
                        message: "must be string",
                      },
                    ];
                    return false;
                  }
                  var valid0 = _errs8 === errors;
                } else {
                  var valid0 = true;
                }
                if (valid0) {
                  if (data.evidence_mode !== undefined) {
                    let data4 = data.evidence_mode;
                    const _errs10 = errors;
                    if (typeof data4 !== "string") {
                      validate26.errors = [
                        {
                          instancePath: instancePath + "/evidence_mode",
                          schemaPath: "#/properties/evidence_mode/type",
                          keyword: "type",
                          params: { type: "string" },
                          message: "must be string",
                        },
                      ];
                      return false;
                    }
                    if ("authored_fixture" !== data4) {
                      validate26.errors = [
                        {
                          instancePath: instancePath + "/evidence_mode",
                          schemaPath: "#/properties/evidence_mode/const",
                          keyword: "const",
                          params: { allowedValue: "authored_fixture" },
                          message: "must be equal to constant",
                        },
                      ];
                      return false;
                    }
                    var valid0 = _errs10 === errors;
                  } else {
                    var valid0 = true;
                  }
                  if (valid0) {
                    if (data.fixture_set_id !== undefined) {
                      const _errs12 = errors;
                      if (typeof data.fixture_set_id !== "string") {
                        validate26.errors = [
                          {
                            instancePath: instancePath + "/fixture_set_id",
                            schemaPath: "#/properties/fixture_set_id/type",
                            keyword: "type",
                            params: { type: "string" },
                            message: "must be string",
                          },
                        ];
                        return false;
                      }
                      var valid0 = _errs12 === errors;
                    } else {
                      var valid0 = true;
                    }
                    if (valid0) {
                      if (data.label_count !== undefined) {
                        let data6 = data.label_count;
                        const _errs14 = errors;
                        if (errors === _errs14) {
                          if (typeof data6 === "string") {
                            if (!pattern5.test(data6)) {
                              validate26.errors = [
                                {
                                  instancePath: instancePath + "/label_count",
                                  schemaPath:
                                    "#/properties/label_count/pattern",
                                  keyword: "pattern",
                                  params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                                  message:
                                    'must match pattern "' +
                                    "^(?:0|[1-9][0-9]*)$" +
                                    '"',
                                },
                              ];
                              return false;
                            }
                          } else {
                            validate26.errors = [
                              {
                                instancePath: instancePath + "/label_count",
                                schemaPath: "#/properties/label_count/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                        }
                        var valid0 = _errs14 === errors;
                      } else {
                        var valid0 = true;
                      }
                      if (valid0) {
                        if (data.operation_id !== undefined) {
                          const _errs16 = errors;
                          if (typeof data.operation_id !== "string") {
                            validate26.errors = [
                              {
                                instancePath: instancePath + "/operation_id",
                                schemaPath: "#/properties/operation_id/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                          var valid0 = _errs16 === errors;
                        } else {
                          var valid0 = true;
                        }
                        if (valid0) {
                          if (data.profile_id !== undefined) {
                            const _errs18 = errors;
                            if (typeof data.profile_id !== "string") {
                              validate26.errors = [
                                {
                                  instancePath: instancePath + "/profile_id",
                                  schemaPath: "#/properties/profile_id/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                },
                              ];
                              return false;
                            }
                            var valid0 = _errs18 === errors;
                          } else {
                            var valid0 = true;
                          }
                          if (valid0) {
                            if (data.project_id !== undefined) {
                              const _errs20 = errors;
                              if (typeof data.project_id !== "string") {
                                validate26.errors = [
                                  {
                                    instancePath: instancePath + "/project_id",
                                    schemaPath: "#/properties/project_id/type",
                                    keyword: "type",
                                    params: { type: "string" },
                                    message: "must be string",
                                  },
                                ];
                                return false;
                              }
                              var valid0 = _errs20 === errors;
                            } else {
                              var valid0 = true;
                            }
                            if (valid0) {
                              if (data.replayed !== undefined) {
                                const _errs22 = errors;
                                if (typeof data.replayed !== "boolean") {
                                  validate26.errors = [
                                    {
                                      instancePath: instancePath + "/replayed",
                                      schemaPath: "#/properties/replayed/type",
                                      keyword: "type",
                                      params: { type: "boolean" },
                                      message: "must be boolean",
                                    },
                                  ];
                                  return false;
                                }
                                var valid0 = _errs22 === errors;
                              } else {
                                var valid0 = true;
                              }
                              if (valid0) {
                                if (data.revision_id !== undefined) {
                                  const _errs24 = errors;
                                  if (typeof data.revision_id !== "string") {
                                    validate26.errors = [
                                      {
                                        instancePath:
                                          instancePath + "/revision_id",
                                        schemaPath:
                                          "#/properties/revision_id/type",
                                        keyword: "type",
                                        params: { type: "string" },
                                        message: "must be string",
                                      },
                                    ];
                                    return false;
                                  }
                                  var valid0 = _errs24 === errors;
                                } else {
                                  var valid0 = true;
                                }
                                if (valid0) {
                                  if (data.schema_version !== undefined) {
                                    let data12 = data.schema_version;
                                    const _errs26 = errors;
                                    if (!(
                                      typeof data12 == "number" &&
                                      !(data12 % 1) &&
                                      !isNaN(data12) &&
                                      isFinite(data12)
                                    )) {
                                      validate26.errors = [
                                        {
                                          instancePath:
                                            instancePath + "/schema_version",
                                          schemaPath:
                                            "#/properties/schema_version/type",
                                          keyword: "type",
                                          params: { type: "integer" },
                                          message: "must be integer",
                                        },
                                      ];
                                      return false;
                                    }
                                    if (1 !== data12) {
                                      validate26.errors = [
                                        {
                                          instancePath:
                                            instancePath + "/schema_version",
                                          schemaPath:
                                            "#/properties/schema_version/const",
                                          keyword: "const",
                                          params: { allowedValue: 1 },
                                          message: "must be equal to constant",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid0 = _errs26 === errors;
                                  } else {
                                    var valid0 = true;
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    } else {
      validate26.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate26.errors = vErrors;
  return errors === 0;
}
validate26.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateErrorDTO = validate27;
const schema39 = {
  $id: "urn:deykit:transport:ErrorDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    code: { title: "Code", type: "string" },
    correlation_id: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      title: "Correlation Id",
    },
    message: { title: "Message", type: "string" },
    reason: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      title: "Reason",
    },
    resource_id: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      title: "Resource Id",
    },
    row: {
      anyOf: [
        { maximum: 9007199254740991, minimum: 0, type: "integer" },
        { type: "null" },
      ],
      default: null,
      title: "Row",
    },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["code", "message", "schema_version"],
  title: "ErrorDTO",
  type: "object",
};
function validate27(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:ErrorDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate27.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.code === undefined && (missing0 = "code")) ||
        (data.message === undefined && (missing0 = "message")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate27.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "code" ||
            key0 === "correlation_id" ||
            key0 === "message" ||
            key0 === "reason" ||
            key0 === "resource_id" ||
            key0 === "row" ||
            key0 === "schema_version"
          )) {
            validate27.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.code !== undefined) {
            const _errs2 = errors;
            if (typeof data.code !== "string") {
              validate27.errors = [
                {
                  instancePath: instancePath + "/code",
                  schemaPath: "#/properties/code/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.correlation_id !== undefined) {
              let data1 = data.correlation_id;
              const _errs4 = errors;
              const _errs5 = errors;
              let valid1 = false;
              const _errs6 = errors;
              if (typeof data1 !== "string") {
                const err0 = {
                  instancePath: instancePath + "/correlation_id",
                  schemaPath: "#/properties/correlation_id/anyOf/0/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                };
                if (vErrors === null) {
                  vErrors = [err0];
                } else {
                  vErrors.push(err0);
                }
                errors++;
              }
              var _valid0 = _errs6 === errors;
              valid1 = valid1 || _valid0;
              const _errs8 = errors;
              if (data1 !== null) {
                const err1 = {
                  instancePath: instancePath + "/correlation_id",
                  schemaPath: "#/properties/correlation_id/anyOf/1/type",
                  keyword: "type",
                  params: { type: "null" },
                  message: "must be null",
                };
                if (vErrors === null) {
                  vErrors = [err1];
                } else {
                  vErrors.push(err1);
                }
                errors++;
              }
              var _valid0 = _errs8 === errors;
              valid1 = valid1 || _valid0;
              if (!valid1) {
                const err2 = {
                  instancePath: instancePath + "/correlation_id",
                  schemaPath: "#/properties/correlation_id/anyOf",
                  keyword: "anyOf",
                  params: {},
                  message: "must match a schema in anyOf",
                };
                if (vErrors === null) {
                  vErrors = [err2];
                } else {
                  vErrors.push(err2);
                }
                errors++;
                validate27.errors = vErrors;
                return false;
              } else {
                errors = _errs5;
                if (vErrors !== null) {
                  if (_errs5) {
                    vErrors.length = _errs5;
                  } else {
                    vErrors = null;
                  }
                }
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.message !== undefined) {
                const _errs10 = errors;
                if (typeof data.message !== "string") {
                  validate27.errors = [
                    {
                      instancePath: instancePath + "/message",
                      schemaPath: "#/properties/message/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs10 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.reason !== undefined) {
                  let data3 = data.reason;
                  const _errs12 = errors;
                  const _errs13 = errors;
                  let valid2 = false;
                  const _errs14 = errors;
                  if (typeof data3 !== "string") {
                    const err3 = {
                      instancePath: instancePath + "/reason",
                      schemaPath: "#/properties/reason/anyOf/0/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    };
                    if (vErrors === null) {
                      vErrors = [err3];
                    } else {
                      vErrors.push(err3);
                    }
                    errors++;
                  }
                  var _valid1 = _errs14 === errors;
                  valid2 = valid2 || _valid1;
                  const _errs16 = errors;
                  if (data3 !== null) {
                    const err4 = {
                      instancePath: instancePath + "/reason",
                      schemaPath: "#/properties/reason/anyOf/1/type",
                      keyword: "type",
                      params: { type: "null" },
                      message: "must be null",
                    };
                    if (vErrors === null) {
                      vErrors = [err4];
                    } else {
                      vErrors.push(err4);
                    }
                    errors++;
                  }
                  var _valid1 = _errs16 === errors;
                  valid2 = valid2 || _valid1;
                  if (!valid2) {
                    const err5 = {
                      instancePath: instancePath + "/reason",
                      schemaPath: "#/properties/reason/anyOf",
                      keyword: "anyOf",
                      params: {},
                      message: "must match a schema in anyOf",
                    };
                    if (vErrors === null) {
                      vErrors = [err5];
                    } else {
                      vErrors.push(err5);
                    }
                    errors++;
                    validate27.errors = vErrors;
                    return false;
                  } else {
                    errors = _errs13;
                    if (vErrors !== null) {
                      if (_errs13) {
                        vErrors.length = _errs13;
                      } else {
                        vErrors = null;
                      }
                    }
                  }
                  var valid0 = _errs12 === errors;
                } else {
                  var valid0 = true;
                }
                if (valid0) {
                  if (data.resource_id !== undefined) {
                    let data4 = data.resource_id;
                    const _errs18 = errors;
                    const _errs19 = errors;
                    let valid3 = false;
                    const _errs20 = errors;
                    if (typeof data4 !== "string") {
                      const err6 = {
                        instancePath: instancePath + "/resource_id",
                        schemaPath: "#/properties/resource_id/anyOf/0/type",
                        keyword: "type",
                        params: { type: "string" },
                        message: "must be string",
                      };
                      if (vErrors === null) {
                        vErrors = [err6];
                      } else {
                        vErrors.push(err6);
                      }
                      errors++;
                    }
                    var _valid2 = _errs20 === errors;
                    valid3 = valid3 || _valid2;
                    const _errs22 = errors;
                    if (data4 !== null) {
                      const err7 = {
                        instancePath: instancePath + "/resource_id",
                        schemaPath: "#/properties/resource_id/anyOf/1/type",
                        keyword: "type",
                        params: { type: "null" },
                        message: "must be null",
                      };
                      if (vErrors === null) {
                        vErrors = [err7];
                      } else {
                        vErrors.push(err7);
                      }
                      errors++;
                    }
                    var _valid2 = _errs22 === errors;
                    valid3 = valid3 || _valid2;
                    if (!valid3) {
                      const err8 = {
                        instancePath: instancePath + "/resource_id",
                        schemaPath: "#/properties/resource_id/anyOf",
                        keyword: "anyOf",
                        params: {},
                        message: "must match a schema in anyOf",
                      };
                      if (vErrors === null) {
                        vErrors = [err8];
                      } else {
                        vErrors.push(err8);
                      }
                      errors++;
                      validate27.errors = vErrors;
                      return false;
                    } else {
                      errors = _errs19;
                      if (vErrors !== null) {
                        if (_errs19) {
                          vErrors.length = _errs19;
                        } else {
                          vErrors = null;
                        }
                      }
                    }
                    var valid0 = _errs18 === errors;
                  } else {
                    var valid0 = true;
                  }
                  if (valid0) {
                    if (data.row !== undefined) {
                      let data5 = data.row;
                      const _errs24 = errors;
                      const _errs25 = errors;
                      let valid4 = false;
                      const _errs26 = errors;
                      if (!(
                        typeof data5 == "number" &&
                        !(data5 % 1) &&
                        !isNaN(data5) &&
                        isFinite(data5)
                      )) {
                        const err9 = {
                          instancePath: instancePath + "/row",
                          schemaPath: "#/properties/row/anyOf/0/type",
                          keyword: "type",
                          params: { type: "integer" },
                          message: "must be integer",
                        };
                        if (vErrors === null) {
                          vErrors = [err9];
                        } else {
                          vErrors.push(err9);
                        }
                        errors++;
                      }
                      if (errors === _errs26) {
                        if (typeof data5 == "number" && isFinite(data5)) {
                          if (data5 > 9007199254740991 || isNaN(data5)) {
                            const err10 = {
                              instancePath: instancePath + "/row",
                              schemaPath: "#/properties/row/anyOf/0/maximum",
                              keyword: "maximum",
                              params: {
                                comparison: "<=",
                                limit: 9007199254740991,
                              },
                              message: "must be <= 9007199254740991",
                            };
                            if (vErrors === null) {
                              vErrors = [err10];
                            } else {
                              vErrors.push(err10);
                            }
                            errors++;
                          } else {
                            if (data5 < 0 || isNaN(data5)) {
                              const err11 = {
                                instancePath: instancePath + "/row",
                                schemaPath: "#/properties/row/anyOf/0/minimum",
                                keyword: "minimum",
                                params: { comparison: ">=", limit: 0 },
                                message: "must be >= 0",
                              };
                              if (vErrors === null) {
                                vErrors = [err11];
                              } else {
                                vErrors.push(err11);
                              }
                              errors++;
                            }
                          }
                        }
                      }
                      var _valid3 = _errs26 === errors;
                      valid4 = valid4 || _valid3;
                      const _errs28 = errors;
                      if (data5 !== null) {
                        const err12 = {
                          instancePath: instancePath + "/row",
                          schemaPath: "#/properties/row/anyOf/1/type",
                          keyword: "type",
                          params: { type: "null" },
                          message: "must be null",
                        };
                        if (vErrors === null) {
                          vErrors = [err12];
                        } else {
                          vErrors.push(err12);
                        }
                        errors++;
                      }
                      var _valid3 = _errs28 === errors;
                      valid4 = valid4 || _valid3;
                      if (!valid4) {
                        const err13 = {
                          instancePath: instancePath + "/row",
                          schemaPath: "#/properties/row/anyOf",
                          keyword: "anyOf",
                          params: {},
                          message: "must match a schema in anyOf",
                        };
                        if (vErrors === null) {
                          vErrors = [err13];
                        } else {
                          vErrors.push(err13);
                        }
                        errors++;
                        validate27.errors = vErrors;
                        return false;
                      } else {
                        errors = _errs25;
                        if (vErrors !== null) {
                          if (_errs25) {
                            vErrors.length = _errs25;
                          } else {
                            vErrors = null;
                          }
                        }
                      }
                      var valid0 = _errs24 === errors;
                    } else {
                      var valid0 = true;
                    }
                    if (valid0) {
                      if (data.schema_version !== undefined) {
                        let data6 = data.schema_version;
                        const _errs30 = errors;
                        if (!(
                          typeof data6 == "number" &&
                          !(data6 % 1) &&
                          !isNaN(data6) &&
                          isFinite(data6)
                        )) {
                          validate27.errors = [
                            {
                              instancePath: instancePath + "/schema_version",
                              schemaPath: "#/properties/schema_version/type",
                              keyword: "type",
                              params: { type: "integer" },
                              message: "must be integer",
                            },
                          ];
                          return false;
                        }
                        if (1 !== data6) {
                          validate27.errors = [
                            {
                              instancePath: instancePath + "/schema_version",
                              schemaPath: "#/properties/schema_version/const",
                              keyword: "const",
                              params: { allowedValue: 1 },
                              message: "must be equal to constant",
                            },
                          ];
                          return false;
                        }
                        var valid0 = _errs30 === errors;
                      } else {
                        var valid0 = true;
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    } else {
      validate27.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate27.errors = vErrors;
  return errors === 0;
}
validate27.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateFailure = validate28;
const schema40 = {
  $id: "urn:deykit:transport:Failure",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    error: { $ref: "urn:deykit:transport:ErrorDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["error", "schema_version"],
  title: "Failure",
  type: "object",
};
function validate28(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Failure" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate28.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.error === undefined && (missing0 = "error")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate28.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(key0 === "error" || key0 === "schema_version")) {
            validate28.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.error !== undefined) {
            let data0 = data.error;
            const _errs2 = errors;
            const _errs3 = errors;
            if (errors === _errs3) {
              if (data0 && typeof data0 == "object" && !Array.isArray(data0)) {
                let missing1;
                if (
                  (data0.code === undefined && (missing1 = "code")) ||
                  (data0.message === undefined && (missing1 = "message")) ||
                  (data0.schema_version === undefined &&
                    (missing1 = "schema_version"))
                ) {
                  validate28.errors = [
                    {
                      instancePath: instancePath + "/error",
                      schemaPath: "urn:deykit:transport:ErrorDTO#/required",
                      keyword: "required",
                      params: { missingProperty: missing1 },
                      message: "must have required property '" + missing1 + "'",
                    },
                  ];
                  return false;
                } else {
                  const _errs5 = errors;
                  for (const key1 in data0) {
                    if (!(
                      key1 === "code" ||
                      key1 === "correlation_id" ||
                      key1 === "message" ||
                      key1 === "reason" ||
                      key1 === "resource_id" ||
                      key1 === "row" ||
                      key1 === "schema_version"
                    )) {
                      validate28.errors = [
                        {
                          instancePath: instancePath + "/error",
                          schemaPath:
                            "urn:deykit:transport:ErrorDTO#/additionalProperties",
                          keyword: "additionalProperties",
                          params: { additionalProperty: key1 },
                          message: "must NOT have additional properties",
                        },
                      ];
                      return false;
                      break;
                    }
                  }
                  if (_errs5 === errors) {
                    if (data0.code !== undefined) {
                      const _errs6 = errors;
                      if (typeof data0.code !== "string") {
                        validate28.errors = [
                          {
                            instancePath: instancePath + "/error/code",
                            schemaPath:
                              "urn:deykit:transport:ErrorDTO#/properties/code/type",
                            keyword: "type",
                            params: { type: "string" },
                            message: "must be string",
                          },
                        ];
                        return false;
                      }
                      var valid2 = _errs6 === errors;
                    } else {
                      var valid2 = true;
                    }
                    if (valid2) {
                      if (data0.correlation_id !== undefined) {
                        let data2 = data0.correlation_id;
                        const _errs8 = errors;
                        const _errs9 = errors;
                        let valid3 = false;
                        const _errs10 = errors;
                        if (typeof data2 !== "string") {
                          const err0 = {
                            instancePath:
                              instancePath + "/error/correlation_id",
                            schemaPath:
                              "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                            keyword: "type",
                            params: { type: "string" },
                            message: "must be string",
                          };
                          if (vErrors === null) {
                            vErrors = [err0];
                          } else {
                            vErrors.push(err0);
                          }
                          errors++;
                        }
                        var _valid0 = _errs10 === errors;
                        valid3 = valid3 || _valid0;
                        const _errs12 = errors;
                        if (data2 !== null) {
                          const err1 = {
                            instancePath:
                              instancePath + "/error/correlation_id",
                            schemaPath:
                              "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                            keyword: "type",
                            params: { type: "null" },
                            message: "must be null",
                          };
                          if (vErrors === null) {
                            vErrors = [err1];
                          } else {
                            vErrors.push(err1);
                          }
                          errors++;
                        }
                        var _valid0 = _errs12 === errors;
                        valid3 = valid3 || _valid0;
                        if (!valid3) {
                          const err2 = {
                            instancePath:
                              instancePath + "/error/correlation_id",
                            schemaPath:
                              "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                            keyword: "anyOf",
                            params: {},
                            message: "must match a schema in anyOf",
                          };
                          if (vErrors === null) {
                            vErrors = [err2];
                          } else {
                            vErrors.push(err2);
                          }
                          errors++;
                          validate28.errors = vErrors;
                          return false;
                        } else {
                          errors = _errs9;
                          if (vErrors !== null) {
                            if (_errs9) {
                              vErrors.length = _errs9;
                            } else {
                              vErrors = null;
                            }
                          }
                        }
                        var valid2 = _errs8 === errors;
                      } else {
                        var valid2 = true;
                      }
                      if (valid2) {
                        if (data0.message !== undefined) {
                          const _errs14 = errors;
                          if (typeof data0.message !== "string") {
                            validate28.errors = [
                              {
                                instancePath: instancePath + "/error/message",
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                          var valid2 = _errs14 === errors;
                        } else {
                          var valid2 = true;
                        }
                        if (valid2) {
                          if (data0.reason !== undefined) {
                            let data4 = data0.reason;
                            const _errs16 = errors;
                            const _errs17 = errors;
                            let valid4 = false;
                            const _errs18 = errors;
                            if (typeof data4 !== "string") {
                              const err3 = {
                                instancePath: instancePath + "/error/reason",
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              };
                              if (vErrors === null) {
                                vErrors = [err3];
                              } else {
                                vErrors.push(err3);
                              }
                              errors++;
                            }
                            var _valid1 = _errs18 === errors;
                            valid4 = valid4 || _valid1;
                            const _errs20 = errors;
                            if (data4 !== null) {
                              const err4 = {
                                instancePath: instancePath + "/error/reason",
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                keyword: "type",
                                params: { type: "null" },
                                message: "must be null",
                              };
                              if (vErrors === null) {
                                vErrors = [err4];
                              } else {
                                vErrors.push(err4);
                              }
                              errors++;
                            }
                            var _valid1 = _errs20 === errors;
                            valid4 = valid4 || _valid1;
                            if (!valid4) {
                              const err5 = {
                                instancePath: instancePath + "/error/reason",
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                keyword: "anyOf",
                                params: {},
                                message: "must match a schema in anyOf",
                              };
                              if (vErrors === null) {
                                vErrors = [err5];
                              } else {
                                vErrors.push(err5);
                              }
                              errors++;
                              validate28.errors = vErrors;
                              return false;
                            } else {
                              errors = _errs17;
                              if (vErrors !== null) {
                                if (_errs17) {
                                  vErrors.length = _errs17;
                                } else {
                                  vErrors = null;
                                }
                              }
                            }
                            var valid2 = _errs16 === errors;
                          } else {
                            var valid2 = true;
                          }
                          if (valid2) {
                            if (data0.resource_id !== undefined) {
                              let data5 = data0.resource_id;
                              const _errs22 = errors;
                              const _errs23 = errors;
                              let valid5 = false;
                              const _errs24 = errors;
                              if (typeof data5 !== "string") {
                                const err6 = {
                                  instancePath:
                                    instancePath + "/error/resource_id",
                                  schemaPath:
                                    "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                };
                                if (vErrors === null) {
                                  vErrors = [err6];
                                } else {
                                  vErrors.push(err6);
                                }
                                errors++;
                              }
                              var _valid2 = _errs24 === errors;
                              valid5 = valid5 || _valid2;
                              const _errs26 = errors;
                              if (data5 !== null) {
                                const err7 = {
                                  instancePath:
                                    instancePath + "/error/resource_id",
                                  schemaPath:
                                    "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                  keyword: "type",
                                  params: { type: "null" },
                                  message: "must be null",
                                };
                                if (vErrors === null) {
                                  vErrors = [err7];
                                } else {
                                  vErrors.push(err7);
                                }
                                errors++;
                              }
                              var _valid2 = _errs26 === errors;
                              valid5 = valid5 || _valid2;
                              if (!valid5) {
                                const err8 = {
                                  instancePath:
                                    instancePath + "/error/resource_id",
                                  schemaPath:
                                    "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                  keyword: "anyOf",
                                  params: {},
                                  message: "must match a schema in anyOf",
                                };
                                if (vErrors === null) {
                                  vErrors = [err8];
                                } else {
                                  vErrors.push(err8);
                                }
                                errors++;
                                validate28.errors = vErrors;
                                return false;
                              } else {
                                errors = _errs23;
                                if (vErrors !== null) {
                                  if (_errs23) {
                                    vErrors.length = _errs23;
                                  } else {
                                    vErrors = null;
                                  }
                                }
                              }
                              var valid2 = _errs22 === errors;
                            } else {
                              var valid2 = true;
                            }
                            if (valid2) {
                              if (data0.row !== undefined) {
                                let data6 = data0.row;
                                const _errs28 = errors;
                                const _errs29 = errors;
                                let valid6 = false;
                                const _errs30 = errors;
                                if (!(
                                  typeof data6 == "number" &&
                                  !(data6 % 1) &&
                                  !isNaN(data6) &&
                                  isFinite(data6)
                                )) {
                                  const err9 = {
                                    instancePath: instancePath + "/error/row",
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                    keyword: "type",
                                    params: { type: "integer" },
                                    message: "must be integer",
                                  };
                                  if (vErrors === null) {
                                    vErrors = [err9];
                                  } else {
                                    vErrors.push(err9);
                                  }
                                  errors++;
                                }
                                if (errors === _errs30) {
                                  if (
                                    typeof data6 == "number" &&
                                    isFinite(data6)
                                  ) {
                                    if (
                                      data6 > 9007199254740991 ||
                                      isNaN(data6)
                                    ) {
                                      const err10 = {
                                        instancePath:
                                          instancePath + "/error/row",
                                        schemaPath:
                                          "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                        keyword: "maximum",
                                        params: {
                                          comparison: "<=",
                                          limit: 9007199254740991,
                                        },
                                        message: "must be <= 9007199254740991",
                                      };
                                      if (vErrors === null) {
                                        vErrors = [err10];
                                      } else {
                                        vErrors.push(err10);
                                      }
                                      errors++;
                                    } else {
                                      if (data6 < 0 || isNaN(data6)) {
                                        const err11 = {
                                          instancePath:
                                            instancePath + "/error/row",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                          keyword: "minimum",
                                          params: {
                                            comparison: ">=",
                                            limit: 0,
                                          },
                                          message: "must be >= 0",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err11];
                                        } else {
                                          vErrors.push(err11);
                                        }
                                        errors++;
                                      }
                                    }
                                  }
                                }
                                var _valid3 = _errs30 === errors;
                                valid6 = valid6 || _valid3;
                                const _errs32 = errors;
                                if (data6 !== null) {
                                  const err12 = {
                                    instancePath: instancePath + "/error/row",
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                    keyword: "type",
                                    params: { type: "null" },
                                    message: "must be null",
                                  };
                                  if (vErrors === null) {
                                    vErrors = [err12];
                                  } else {
                                    vErrors.push(err12);
                                  }
                                  errors++;
                                }
                                var _valid3 = _errs32 === errors;
                                valid6 = valid6 || _valid3;
                                if (!valid6) {
                                  const err13 = {
                                    instancePath: instancePath + "/error/row",
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                    keyword: "anyOf",
                                    params: {},
                                    message: "must match a schema in anyOf",
                                  };
                                  if (vErrors === null) {
                                    vErrors = [err13];
                                  } else {
                                    vErrors.push(err13);
                                  }
                                  errors++;
                                  validate28.errors = vErrors;
                                  return false;
                                } else {
                                  errors = _errs29;
                                  if (vErrors !== null) {
                                    if (_errs29) {
                                      vErrors.length = _errs29;
                                    } else {
                                      vErrors = null;
                                    }
                                  }
                                }
                                var valid2 = _errs28 === errors;
                              } else {
                                var valid2 = true;
                              }
                              if (valid2) {
                                if (data0.schema_version !== undefined) {
                                  let data7 = data0.schema_version;
                                  const _errs34 = errors;
                                  if (!(
                                    typeof data7 == "number" &&
                                    !(data7 % 1) &&
                                    !isNaN(data7) &&
                                    isFinite(data7)
                                  )) {
                                    validate28.errors = [
                                      {
                                        instancePath:
                                          instancePath +
                                          "/error/schema_version",
                                        schemaPath:
                                          "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                        keyword: "type",
                                        params: { type: "integer" },
                                        message: "must be integer",
                                      },
                                    ];
                                    return false;
                                  }
                                  if (1 !== data7) {
                                    validate28.errors = [
                                      {
                                        instancePath:
                                          instancePath +
                                          "/error/schema_version",
                                        schemaPath:
                                          "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                        keyword: "const",
                                        params: { allowedValue: 1 },
                                        message: "must be equal to constant",
                                      },
                                    ];
                                    return false;
                                  }
                                  var valid2 = _errs34 === errors;
                                } else {
                                  var valid2 = true;
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              } else {
                validate28.errors = [
                  {
                    instancePath: instancePath + "/error",
                    schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                    keyword: "type",
                    params: { type: "object" },
                    message: "must be object",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data8 = data.schema_version;
              const _errs36 = errors;
              if (!(
                typeof data8 == "number" &&
                !(data8 % 1) &&
                !isNaN(data8) &&
                isFinite(data8)
              )) {
                validate28.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data8) {
                validate28.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs36 === errors;
            } else {
              var valid0 = true;
            }
          }
        }
      }
    } else {
      validate28.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate28.errors = vErrors;
  return errors === 0;
}
validate28.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateProjectOverviewDTO = validate29;
const schema42 = {
  $id: "urn:deykit:transport:ProjectOverviewDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    datasets: {
      items: { $ref: "urn:deykit:transport:ResourceSummaryDTO#" },
      title: "Datasets",
      type: "array",
    },
    decisions: {
      items: { $ref: "urn:deykit:transport:ResourceSummaryDTO#" },
      title: "Decisions",
      type: "array",
    },
    registration: { $ref: "urn:deykit:transport:RegistrationDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["datasets", "decisions", "registration", "schema_version"],
  title: "ProjectOverviewDTO",
  type: "object",
};
const schema43 = {
  $id: "urn:deykit:transport:ResourceSummaryDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    id: { title: "Id", type: "string" },
    name: { title: "Name", type: "string" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["id", "name", "schema_version"],
  title: "ResourceSummaryDTO",
  type: "object",
};
function validate29(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:ProjectOverviewDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate29.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.datasets === undefined && (missing0 = "datasets")) ||
        (data.decisions === undefined && (missing0 = "decisions")) ||
        (data.registration === undefined && (missing0 = "registration")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate29.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "datasets" ||
            key0 === "decisions" ||
            key0 === "registration" ||
            key0 === "schema_version"
          )) {
            validate29.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.datasets !== undefined) {
            let data0 = data.datasets;
            const _errs2 = errors;
            if (errors === _errs2) {
              if (Array.isArray(data0)) {
                var valid1 = true;
                const len0 = data0.length;
                for (let i0 = 0; i0 < len0; i0++) {
                  let data1 = data0[i0];
                  const _errs4 = errors;
                  const _errs5 = errors;
                  if (errors === _errs5) {
                    if (
                      data1 &&
                      typeof data1 == "object" &&
                      !Array.isArray(data1)
                    ) {
                      let missing1;
                      if (
                        (data1.id === undefined && (missing1 = "id")) ||
                        (data1.name === undefined && (missing1 = "name")) ||
                        (data1.schema_version === undefined &&
                          (missing1 = "schema_version"))
                      ) {
                        validate29.errors = [
                          {
                            instancePath: instancePath + "/datasets/" + i0,
                            schemaPath:
                              "urn:deykit:transport:ResourceSummaryDTO#/required",
                            keyword: "required",
                            params: { missingProperty: missing1 },
                            message:
                              "must have required property '" + missing1 + "'",
                          },
                        ];
                        return false;
                      } else {
                        const _errs7 = errors;
                        for (const key1 in data1) {
                          if (!(
                            key1 === "id" ||
                            key1 === "name" ||
                            key1 === "schema_version"
                          )) {
                            validate29.errors = [
                              {
                                instancePath: instancePath + "/datasets/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ResourceSummaryDTO#/additionalProperties",
                                keyword: "additionalProperties",
                                params: { additionalProperty: key1 },
                                message: "must NOT have additional properties",
                              },
                            ];
                            return false;
                            break;
                          }
                        }
                        if (_errs7 === errors) {
                          if (data1.id !== undefined) {
                            const _errs8 = errors;
                            if (typeof data1.id !== "string") {
                              validate29.errors = [
                                {
                                  instancePath:
                                    instancePath + "/datasets/" + i0 + "/id",
                                  schemaPath:
                                    "urn:deykit:transport:ResourceSummaryDTO#/properties/id/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                },
                              ];
                              return false;
                            }
                            var valid3 = _errs8 === errors;
                          } else {
                            var valid3 = true;
                          }
                          if (valid3) {
                            if (data1.name !== undefined) {
                              const _errs10 = errors;
                              if (typeof data1.name !== "string") {
                                validate29.errors = [
                                  {
                                    instancePath:
                                      instancePath +
                                      "/datasets/" +
                                      i0 +
                                      "/name",
                                    schemaPath:
                                      "urn:deykit:transport:ResourceSummaryDTO#/properties/name/type",
                                    keyword: "type",
                                    params: { type: "string" },
                                    message: "must be string",
                                  },
                                ];
                                return false;
                              }
                              var valid3 = _errs10 === errors;
                            } else {
                              var valid3 = true;
                            }
                            if (valid3) {
                              if (data1.schema_version !== undefined) {
                                let data4 = data1.schema_version;
                                const _errs12 = errors;
                                if (!(
                                  typeof data4 == "number" &&
                                  !(data4 % 1) &&
                                  !isNaN(data4) &&
                                  isFinite(data4)
                                )) {
                                  validate29.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/datasets/" +
                                        i0 +
                                        "/schema_version",
                                      schemaPath:
                                        "urn:deykit:transport:ResourceSummaryDTO#/properties/schema_version/type",
                                      keyword: "type",
                                      params: { type: "integer" },
                                      message: "must be integer",
                                    },
                                  ];
                                  return false;
                                }
                                if (1 !== data4) {
                                  validate29.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/datasets/" +
                                        i0 +
                                        "/schema_version",
                                      schemaPath:
                                        "urn:deykit:transport:ResourceSummaryDTO#/properties/schema_version/const",
                                      keyword: "const",
                                      params: { allowedValue: 1 },
                                      message: "must be equal to constant",
                                    },
                                  ];
                                  return false;
                                }
                                var valid3 = _errs12 === errors;
                              } else {
                                var valid3 = true;
                              }
                            }
                          }
                        }
                      }
                    } else {
                      validate29.errors = [
                        {
                          instancePath: instancePath + "/datasets/" + i0,
                          schemaPath:
                            "urn:deykit:transport:ResourceSummaryDTO#/type",
                          keyword: "type",
                          params: { type: "object" },
                          message: "must be object",
                        },
                      ];
                      return false;
                    }
                  }
                  var valid1 = _errs4 === errors;
                  if (!valid1) {
                    break;
                  }
                }
              } else {
                validate29.errors = [
                  {
                    instancePath: instancePath + "/datasets",
                    schemaPath: "#/properties/datasets/type",
                    keyword: "type",
                    params: { type: "array" },
                    message: "must be array",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.decisions !== undefined) {
              let data5 = data.decisions;
              const _errs14 = errors;
              if (errors === _errs14) {
                if (Array.isArray(data5)) {
                  var valid4 = true;
                  const len1 = data5.length;
                  for (let i1 = 0; i1 < len1; i1++) {
                    let data6 = data5[i1];
                    const _errs16 = errors;
                    const _errs17 = errors;
                    if (errors === _errs17) {
                      if (
                        data6 &&
                        typeof data6 == "object" &&
                        !Array.isArray(data6)
                      ) {
                        let missing2;
                        if (
                          (data6.id === undefined && (missing2 = "id")) ||
                          (data6.name === undefined && (missing2 = "name")) ||
                          (data6.schema_version === undefined &&
                            (missing2 = "schema_version"))
                        ) {
                          validate29.errors = [
                            {
                              instancePath: instancePath + "/decisions/" + i1,
                              schemaPath:
                                "urn:deykit:transport:ResourceSummaryDTO#/required",
                              keyword: "required",
                              params: { missingProperty: missing2 },
                              message:
                                "must have required property '" +
                                missing2 +
                                "'",
                            },
                          ];
                          return false;
                        } else {
                          const _errs19 = errors;
                          for (const key2 in data6) {
                            if (!(
                              key2 === "id" ||
                              key2 === "name" ||
                              key2 === "schema_version"
                            )) {
                              validate29.errors = [
                                {
                                  instancePath:
                                    instancePath + "/decisions/" + i1,
                                  schemaPath:
                                    "urn:deykit:transport:ResourceSummaryDTO#/additionalProperties",
                                  keyword: "additionalProperties",
                                  params: { additionalProperty: key2 },
                                  message:
                                    "must NOT have additional properties",
                                },
                              ];
                              return false;
                              break;
                            }
                          }
                          if (_errs19 === errors) {
                            if (data6.id !== undefined) {
                              const _errs20 = errors;
                              if (typeof data6.id !== "string") {
                                validate29.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/decisions/" + i1 + "/id",
                                    schemaPath:
                                      "urn:deykit:transport:ResourceSummaryDTO#/properties/id/type",
                                    keyword: "type",
                                    params: { type: "string" },
                                    message: "must be string",
                                  },
                                ];
                                return false;
                              }
                              var valid6 = _errs20 === errors;
                            } else {
                              var valid6 = true;
                            }
                            if (valid6) {
                              if (data6.name !== undefined) {
                                const _errs22 = errors;
                                if (typeof data6.name !== "string") {
                                  validate29.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/decisions/" +
                                        i1 +
                                        "/name",
                                      schemaPath:
                                        "urn:deykit:transport:ResourceSummaryDTO#/properties/name/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid6 = _errs22 === errors;
                              } else {
                                var valid6 = true;
                              }
                              if (valid6) {
                                if (data6.schema_version !== undefined) {
                                  let data9 = data6.schema_version;
                                  const _errs24 = errors;
                                  if (!(
                                    typeof data9 == "number" &&
                                    !(data9 % 1) &&
                                    !isNaN(data9) &&
                                    isFinite(data9)
                                  )) {
                                    validate29.errors = [
                                      {
                                        instancePath:
                                          instancePath +
                                          "/decisions/" +
                                          i1 +
                                          "/schema_version",
                                        schemaPath:
                                          "urn:deykit:transport:ResourceSummaryDTO#/properties/schema_version/type",
                                        keyword: "type",
                                        params: { type: "integer" },
                                        message: "must be integer",
                                      },
                                    ];
                                    return false;
                                  }
                                  if (1 !== data9) {
                                    validate29.errors = [
                                      {
                                        instancePath:
                                          instancePath +
                                          "/decisions/" +
                                          i1 +
                                          "/schema_version",
                                        schemaPath:
                                          "urn:deykit:transport:ResourceSummaryDTO#/properties/schema_version/const",
                                        keyword: "const",
                                        params: { allowedValue: 1 },
                                        message: "must be equal to constant",
                                      },
                                    ];
                                    return false;
                                  }
                                  var valid6 = _errs24 === errors;
                                } else {
                                  var valid6 = true;
                                }
                              }
                            }
                          }
                        }
                      } else {
                        validate29.errors = [
                          {
                            instancePath: instancePath + "/decisions/" + i1,
                            schemaPath:
                              "urn:deykit:transport:ResourceSummaryDTO#/type",
                            keyword: "type",
                            params: { type: "object" },
                            message: "must be object",
                          },
                        ];
                        return false;
                      }
                    }
                    var valid4 = _errs16 === errors;
                    if (!valid4) {
                      break;
                    }
                  }
                } else {
                  validate29.errors = [
                    {
                      instancePath: instancePath + "/decisions",
                      schemaPath: "#/properties/decisions/type",
                      keyword: "type",
                      params: { type: "array" },
                      message: "must be array",
                    },
                  ];
                  return false;
                }
              }
              var valid0 = _errs14 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.registration !== undefined) {
                const _errs26 = errors;
                if (
                  !validate23(data.registration, {
                    instancePath: instancePath + "/registration",
                    parentData: data,
                    parentDataProperty: "registration",
                    rootData,
                    dynamicAnchors,
                  })
                ) {
                  vErrors =
                    vErrors === null
                      ? validate23.errors
                      : vErrors.concat(validate23.errors);
                  errors = vErrors.length;
                }
                var valid0 = _errs26 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.schema_version !== undefined) {
                  let data11 = data.schema_version;
                  const _errs27 = errors;
                  if (!(
                    typeof data11 == "number" &&
                    !(data11 % 1) &&
                    !isNaN(data11) &&
                    isFinite(data11)
                  )) {
                    validate29.errors = [
                      {
                        instancePath: instancePath + "/schema_version",
                        schemaPath: "#/properties/schema_version/type",
                        keyword: "type",
                        params: { type: "integer" },
                        message: "must be integer",
                      },
                    ];
                    return false;
                  }
                  if (1 !== data11) {
                    validate29.errors = [
                      {
                        instancePath: instancePath + "/schema_version",
                        schemaPath: "#/properties/schema_version/const",
                        keyword: "const",
                        params: { allowedValue: 1 },
                        message: "must be equal to constant",
                      },
                    ];
                    return false;
                  }
                  var valid0 = _errs27 === errors;
                } else {
                  var valid0 = true;
                }
              }
            }
          }
        }
      }
    } else {
      validate29.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate29.errors = vErrors;
  return errors === 0;
}
validate29.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateProjectRecordDTO = validate31;
function validate31(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:ProjectRecordDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate31.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.created_at === undefined && (missing0 = "created_at")) ||
        (data.id === undefined && (missing0 = "id")) ||
        (data.name === undefined && (missing0 = "name")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate31.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "created_at" ||
            key0 === "default_provider_id" ||
            key0 === "id" ||
            key0 === "name" ||
            key0 === "schema_version"
          )) {
            validate31.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.created_at !== undefined) {
            const _errs2 = errors;
            if (typeof data.created_at !== "string") {
              validate31.errors = [
                {
                  instancePath: instancePath + "/created_at",
                  schemaPath: "#/properties/created_at/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.default_provider_id !== undefined) {
              let data1 = data.default_provider_id;
              const _errs4 = errors;
              const _errs5 = errors;
              let valid1 = false;
              const _errs6 = errors;
              if (typeof data1 !== "string") {
                const err0 = {
                  instancePath: instancePath + "/default_provider_id",
                  schemaPath: "#/properties/default_provider_id/anyOf/0/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                };
                if (vErrors === null) {
                  vErrors = [err0];
                } else {
                  vErrors.push(err0);
                }
                errors++;
              }
              var _valid0 = _errs6 === errors;
              valid1 = valid1 || _valid0;
              const _errs8 = errors;
              if (data1 !== null) {
                const err1 = {
                  instancePath: instancePath + "/default_provider_id",
                  schemaPath: "#/properties/default_provider_id/anyOf/1/type",
                  keyword: "type",
                  params: { type: "null" },
                  message: "must be null",
                };
                if (vErrors === null) {
                  vErrors = [err1];
                } else {
                  vErrors.push(err1);
                }
                errors++;
              }
              var _valid0 = _errs8 === errors;
              valid1 = valid1 || _valid0;
              if (!valid1) {
                const err2 = {
                  instancePath: instancePath + "/default_provider_id",
                  schemaPath: "#/properties/default_provider_id/anyOf",
                  keyword: "anyOf",
                  params: {},
                  message: "must match a schema in anyOf",
                };
                if (vErrors === null) {
                  vErrors = [err2];
                } else {
                  vErrors.push(err2);
                }
                errors++;
                validate31.errors = vErrors;
                return false;
              } else {
                errors = _errs5;
                if (vErrors !== null) {
                  if (_errs5) {
                    vErrors.length = _errs5;
                  } else {
                    vErrors = null;
                  }
                }
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.id !== undefined) {
                const _errs10 = errors;
                if (typeof data.id !== "string") {
                  validate31.errors = [
                    {
                      instancePath: instancePath + "/id",
                      schemaPath: "#/properties/id/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs10 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.name !== undefined) {
                  let data3 = data.name;
                  const _errs12 = errors;
                  if (errors === _errs12) {
                    if (typeof data3 === "string") {
                      if (func2(data3) < 1) {
                        validate31.errors = [
                          {
                            instancePath: instancePath + "/name",
                            schemaPath: "#/properties/name/minLength",
                            keyword: "minLength",
                            params: { limit: 1 },
                            message: "must NOT have fewer than 1 characters",
                          },
                        ];
                        return false;
                      }
                    } else {
                      validate31.errors = [
                        {
                          instancePath: instancePath + "/name",
                          schemaPath: "#/properties/name/type",
                          keyword: "type",
                          params: { type: "string" },
                          message: "must be string",
                        },
                      ];
                      return false;
                    }
                  }
                  var valid0 = _errs12 === errors;
                } else {
                  var valid0 = true;
                }
                if (valid0) {
                  if (data.schema_version !== undefined) {
                    let data4 = data.schema_version;
                    const _errs14 = errors;
                    if (!(
                      typeof data4 == "number" &&
                      !(data4 % 1) &&
                      !isNaN(data4) &&
                      isFinite(data4)
                    )) {
                      validate31.errors = [
                        {
                          instancePath: instancePath + "/schema_version",
                          schemaPath: "#/properties/schema_version/type",
                          keyword: "type",
                          params: { type: "integer" },
                          message: "must be integer",
                        },
                      ];
                      return false;
                    }
                    if (1 !== data4) {
                      validate31.errors = [
                        {
                          instancePath: instancePath + "/schema_version",
                          schemaPath: "#/properties/schema_version/const",
                          keyword: "const",
                          params: { allowedValue: 1 },
                          message: "must be equal to constant",
                        },
                      ];
                      return false;
                    }
                    var valid0 = _errs14 === errors;
                  } else {
                    var valid0 = true;
                  }
                }
              }
            }
          }
        }
      }
    } else {
      validate31.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate31.errors = vErrors;
  return errors === 0;
}
validate31.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateRebuildIndexDTO = validate32;
const schema46 = {
  $id: "urn:deykit:transport:RebuildIndexDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    record_count: {
      pattern: "^(?:0|[1-9][0-9]*)$",
      title: "Record Count",
      type: "string",
    },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["record_count", "schema_version"],
  title: "RebuildIndexDTO",
  type: "object",
};
function validate32(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:RebuildIndexDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate32.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.record_count === undefined && (missing0 = "record_count")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate32.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(key0 === "record_count" || key0 === "schema_version")) {
            validate32.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.record_count !== undefined) {
            let data0 = data.record_count;
            const _errs2 = errors;
            if (errors === _errs2) {
              if (typeof data0 === "string") {
                if (!pattern5.test(data0)) {
                  validate32.errors = [
                    {
                      instancePath: instancePath + "/record_count",
                      schemaPath: "#/properties/record_count/pattern",
                      keyword: "pattern",
                      params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                      message:
                        'must match pattern "' + "^(?:0|[1-9][0-9]*)$" + '"',
                    },
                  ];
                  return false;
                }
              } else {
                validate32.errors = [
                  {
                    instancePath: instancePath + "/record_count",
                    schemaPath: "#/properties/record_count/type",
                    keyword: "type",
                    params: { type: "string" },
                    message: "must be string",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data1 = data.schema_version;
              const _errs4 = errors;
              if (!(
                typeof data1 == "number" &&
                !(data1 % 1) &&
                !isNaN(data1) &&
                isFinite(data1)
              )) {
                validate32.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data1) {
                validate32.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
          }
        }
      }
    } else {
      validate32.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate32.errors = vErrors;
  return errors === 0;
}
validate32.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateRecentProjectDTO = validate33;
const schema47 = {
  $id: "urn:deykit:transport:RecentProjectDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    id: { title: "Id", type: "string" },
    last_opened_at: { title: "Last Opened At", type: "string" },
    name: { title: "Name", type: "string" },
    path: { title: "Path", type: "string" },
    project_id: { title: "Project Id", type: "string" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: [
    "id",
    "last_opened_at",
    "name",
    "path",
    "project_id",
    "schema_version",
  ],
  title: "RecentProjectDTO",
  type: "object",
};
function validate33(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:RecentProjectDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate33.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.id === undefined && (missing0 = "id")) ||
        (data.last_opened_at === undefined && (missing0 = "last_opened_at")) ||
        (data.name === undefined && (missing0 = "name")) ||
        (data.path === undefined && (missing0 = "path")) ||
        (data.project_id === undefined && (missing0 = "project_id")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate33.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "id" ||
            key0 === "last_opened_at" ||
            key0 === "name" ||
            key0 === "path" ||
            key0 === "project_id" ||
            key0 === "schema_version"
          )) {
            validate33.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.id !== undefined) {
            const _errs2 = errors;
            if (typeof data.id !== "string") {
              validate33.errors = [
                {
                  instancePath: instancePath + "/id",
                  schemaPath: "#/properties/id/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.last_opened_at !== undefined) {
              const _errs4 = errors;
              if (typeof data.last_opened_at !== "string") {
                validate33.errors = [
                  {
                    instancePath: instancePath + "/last_opened_at",
                    schemaPath: "#/properties/last_opened_at/type",
                    keyword: "type",
                    params: { type: "string" },
                    message: "must be string",
                  },
                ];
                return false;
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.name !== undefined) {
                const _errs6 = errors;
                if (typeof data.name !== "string") {
                  validate33.errors = [
                    {
                      instancePath: instancePath + "/name",
                      schemaPath: "#/properties/name/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs6 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.path !== undefined) {
                  const _errs8 = errors;
                  if (typeof data.path !== "string") {
                    validate33.errors = [
                      {
                        instancePath: instancePath + "/path",
                        schemaPath: "#/properties/path/type",
                        keyword: "type",
                        params: { type: "string" },
                        message: "must be string",
                      },
                    ];
                    return false;
                  }
                  var valid0 = _errs8 === errors;
                } else {
                  var valid0 = true;
                }
                if (valid0) {
                  if (data.project_id !== undefined) {
                    const _errs10 = errors;
                    if (typeof data.project_id !== "string") {
                      validate33.errors = [
                        {
                          instancePath: instancePath + "/project_id",
                          schemaPath: "#/properties/project_id/type",
                          keyword: "type",
                          params: { type: "string" },
                          message: "must be string",
                        },
                      ];
                      return false;
                    }
                    var valid0 = _errs10 === errors;
                  } else {
                    var valid0 = true;
                  }
                  if (valid0) {
                    if (data.schema_version !== undefined) {
                      let data5 = data.schema_version;
                      const _errs12 = errors;
                      if (!(
                        typeof data5 == "number" &&
                        !(data5 % 1) &&
                        !isNaN(data5) &&
                        isFinite(data5)
                      )) {
                        validate33.errors = [
                          {
                            instancePath: instancePath + "/schema_version",
                            schemaPath: "#/properties/schema_version/type",
                            keyword: "type",
                            params: { type: "integer" },
                            message: "must be integer",
                          },
                        ];
                        return false;
                      }
                      if (1 !== data5) {
                        validate33.errors = [
                          {
                            instancePath: instancePath + "/schema_version",
                            schemaPath: "#/properties/schema_version/const",
                            keyword: "const",
                            params: { allowedValue: 1 },
                            message: "must be equal to constant",
                          },
                        ];
                        return false;
                      }
                      var valid0 = _errs12 === errors;
                    } else {
                      var valid0 = true;
                    }
                  }
                }
              }
            }
          }
        }
      }
    } else {
      validate33.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate33.errors = vErrors;
  return errors === 0;
}
validate33.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateRecentProjectsDTO = validate34;
const schema48 = {
  $id: "urn:deykit:transport:RecentProjectsDTO",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    items: {
      items: { $ref: "urn:deykit:transport:RecentProjectDTO#" },
      title: "Items",
      type: "array",
    },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
  },
  required: ["items", "schema_version"],
  title: "RecentProjectsDTO",
  type: "object",
};
function validate34(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:RecentProjectsDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate34.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.items === undefined && (missing0 = "items")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate34.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(key0 === "items" || key0 === "schema_version")) {
            validate34.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.items !== undefined) {
            let data0 = data.items;
            const _errs2 = errors;
            if (errors === _errs2) {
              if (Array.isArray(data0)) {
                var valid1 = true;
                const len0 = data0.length;
                for (let i0 = 0; i0 < len0; i0++) {
                  let data1 = data0[i0];
                  const _errs4 = errors;
                  const _errs5 = errors;
                  if (errors === _errs5) {
                    if (
                      data1 &&
                      typeof data1 == "object" &&
                      !Array.isArray(data1)
                    ) {
                      let missing1;
                      if (
                        (data1.id === undefined && (missing1 = "id")) ||
                        (data1.last_opened_at === undefined &&
                          (missing1 = "last_opened_at")) ||
                        (data1.name === undefined && (missing1 = "name")) ||
                        (data1.path === undefined && (missing1 = "path")) ||
                        (data1.project_id === undefined &&
                          (missing1 = "project_id")) ||
                        (data1.schema_version === undefined &&
                          (missing1 = "schema_version"))
                      ) {
                        validate34.errors = [
                          {
                            instancePath: instancePath + "/items/" + i0,
                            schemaPath:
                              "urn:deykit:transport:RecentProjectDTO#/required",
                            keyword: "required",
                            params: { missingProperty: missing1 },
                            message:
                              "must have required property '" + missing1 + "'",
                          },
                        ];
                        return false;
                      } else {
                        const _errs7 = errors;
                        for (const key1 in data1) {
                          if (!(
                            key1 === "id" ||
                            key1 === "last_opened_at" ||
                            key1 === "name" ||
                            key1 === "path" ||
                            key1 === "project_id" ||
                            key1 === "schema_version"
                          )) {
                            validate34.errors = [
                              {
                                instancePath: instancePath + "/items/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:RecentProjectDTO#/additionalProperties",
                                keyword: "additionalProperties",
                                params: { additionalProperty: key1 },
                                message: "must NOT have additional properties",
                              },
                            ];
                            return false;
                            break;
                          }
                        }
                        if (_errs7 === errors) {
                          if (data1.id !== undefined) {
                            const _errs8 = errors;
                            if (typeof data1.id !== "string") {
                              validate34.errors = [
                                {
                                  instancePath:
                                    instancePath + "/items/" + i0 + "/id",
                                  schemaPath:
                                    "urn:deykit:transport:RecentProjectDTO#/properties/id/type",
                                  keyword: "type",
                                  params: { type: "string" },
                                  message: "must be string",
                                },
                              ];
                              return false;
                            }
                            var valid3 = _errs8 === errors;
                          } else {
                            var valid3 = true;
                          }
                          if (valid3) {
                            if (data1.last_opened_at !== undefined) {
                              const _errs10 = errors;
                              if (typeof data1.last_opened_at !== "string") {
                                validate34.errors = [
                                  {
                                    instancePath:
                                      instancePath +
                                      "/items/" +
                                      i0 +
                                      "/last_opened_at",
                                    schemaPath:
                                      "urn:deykit:transport:RecentProjectDTO#/properties/last_opened_at/type",
                                    keyword: "type",
                                    params: { type: "string" },
                                    message: "must be string",
                                  },
                                ];
                                return false;
                              }
                              var valid3 = _errs10 === errors;
                            } else {
                              var valid3 = true;
                            }
                            if (valid3) {
                              if (data1.name !== undefined) {
                                const _errs12 = errors;
                                if (typeof data1.name !== "string") {
                                  validate34.errors = [
                                    {
                                      instancePath:
                                        instancePath + "/items/" + i0 + "/name",
                                      schemaPath:
                                        "urn:deykit:transport:RecentProjectDTO#/properties/name/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid3 = _errs12 === errors;
                              } else {
                                var valid3 = true;
                              }
                              if (valid3) {
                                if (data1.path !== undefined) {
                                  const _errs14 = errors;
                                  if (typeof data1.path !== "string") {
                                    validate34.errors = [
                                      {
                                        instancePath:
                                          instancePath +
                                          "/items/" +
                                          i0 +
                                          "/path",
                                        schemaPath:
                                          "urn:deykit:transport:RecentProjectDTO#/properties/path/type",
                                        keyword: "type",
                                        params: { type: "string" },
                                        message: "must be string",
                                      },
                                    ];
                                    return false;
                                  }
                                  var valid3 = _errs14 === errors;
                                } else {
                                  var valid3 = true;
                                }
                                if (valid3) {
                                  if (data1.project_id !== undefined) {
                                    const _errs16 = errors;
                                    if (typeof data1.project_id !== "string") {
                                      validate34.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/items/" +
                                            i0 +
                                            "/project_id",
                                          schemaPath:
                                            "urn:deykit:transport:RecentProjectDTO#/properties/project_id/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid3 = _errs16 === errors;
                                  } else {
                                    var valid3 = true;
                                  }
                                  if (valid3) {
                                    if (data1.schema_version !== undefined) {
                                      let data7 = data1.schema_version;
                                      const _errs18 = errors;
                                      if (!(
                                        typeof data7 == "number" &&
                                        !(data7 % 1) &&
                                        !isNaN(data7) &&
                                        isFinite(data7)
                                      )) {
                                        validate34.errors = [
                                          {
                                            instancePath:
                                              instancePath +
                                              "/items/" +
                                              i0 +
                                              "/schema_version",
                                            schemaPath:
                                              "urn:deykit:transport:RecentProjectDTO#/properties/schema_version/type",
                                            keyword: "type",
                                            params: { type: "integer" },
                                            message: "must be integer",
                                          },
                                        ];
                                        return false;
                                      }
                                      if (1 !== data7) {
                                        validate34.errors = [
                                          {
                                            instancePath:
                                              instancePath +
                                              "/items/" +
                                              i0 +
                                              "/schema_version",
                                            schemaPath:
                                              "urn:deykit:transport:RecentProjectDTO#/properties/schema_version/const",
                                            keyword: "const",
                                            params: { allowedValue: 1 },
                                            message:
                                              "must be equal to constant",
                                          },
                                        ];
                                        return false;
                                      }
                                      var valid3 = _errs18 === errors;
                                    } else {
                                      var valid3 = true;
                                    }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    } else {
                      validate34.errors = [
                        {
                          instancePath: instancePath + "/items/" + i0,
                          schemaPath:
                            "urn:deykit:transport:RecentProjectDTO#/type",
                          keyword: "type",
                          params: { type: "object" },
                          message: "must be object",
                        },
                      ];
                      return false;
                    }
                  }
                  var valid1 = _errs4 === errors;
                  if (!valid1) {
                    break;
                  }
                }
              } else {
                validate34.errors = [
                  {
                    instancePath: instancePath + "/items",
                    schemaPath: "#/properties/items/type",
                    keyword: "type",
                    params: { type: "array" },
                    message: "must be array",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data8 = data.schema_version;
              const _errs20 = errors;
              if (!(
                typeof data8 == "number" &&
                !(data8 % 1) &&
                !isNaN(data8) &&
                isFinite(data8)
              )) {
                validate34.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data8) {
                validate34.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs20 === errors;
            } else {
              var valid0 = true;
            }
          }
        }
      }
    } else {
      validate34.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate34.errors = vErrors;
  return errors === 0;
}
validate34.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateRegisterProjectRequest = validate35;
const schema50 = {
  $id: "urn:deykit:transport:RegisterProjectRequest",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    action: { enum: ["open", "create"], title: "Action", type: "string" },
    name: { anyOf: [{ type: "string" }, { type: "null" }], title: "Name" },
    operation_id: { title: "Operation Id", type: "string" },
    path: { minLength: 1, title: "Path", type: "string" },
    schema_version: { const: 1, title: "Schema Version", type: "integer" },
  },
  required: ["action", "operation_id", "path", "schema_version"],
  title: "RegisterProjectRequest",
  type: "object",
};
function validate35(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:RegisterProjectRequest" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate35.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.action === undefined && (missing0 = "action")) ||
        (data.operation_id === undefined && (missing0 = "operation_id")) ||
        (data.path === undefined && (missing0 = "path")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate35.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "action" ||
            key0 === "name" ||
            key0 === "operation_id" ||
            key0 === "path" ||
            key0 === "schema_version"
          )) {
            validate35.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.action !== undefined) {
            let data0 = data.action;
            const _errs2 = errors;
            if (typeof data0 !== "string") {
              validate35.errors = [
                {
                  instancePath: instancePath + "/action",
                  schemaPath: "#/properties/action/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                },
              ];
              return false;
            }
            if (!(data0 === "open" || data0 === "create")) {
              validate35.errors = [
                {
                  instancePath: instancePath + "/action",
                  schemaPath: "#/properties/action/enum",
                  keyword: "enum",
                  params: { allowedValues: schema50.properties.action.enum },
                  message: "must be equal to one of the allowed values",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.name !== undefined) {
              let data1 = data.name;
              const _errs4 = errors;
              const _errs5 = errors;
              let valid1 = false;
              const _errs6 = errors;
              if (typeof data1 !== "string") {
                const err0 = {
                  instancePath: instancePath + "/name",
                  schemaPath: "#/properties/name/anyOf/0/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                };
                if (vErrors === null) {
                  vErrors = [err0];
                } else {
                  vErrors.push(err0);
                }
                errors++;
              }
              var _valid0 = _errs6 === errors;
              valid1 = valid1 || _valid0;
              const _errs8 = errors;
              if (data1 !== null) {
                const err1 = {
                  instancePath: instancePath + "/name",
                  schemaPath: "#/properties/name/anyOf/1/type",
                  keyword: "type",
                  params: { type: "null" },
                  message: "must be null",
                };
                if (vErrors === null) {
                  vErrors = [err1];
                } else {
                  vErrors.push(err1);
                }
                errors++;
              }
              var _valid0 = _errs8 === errors;
              valid1 = valid1 || _valid0;
              if (!valid1) {
                const err2 = {
                  instancePath: instancePath + "/name",
                  schemaPath: "#/properties/name/anyOf",
                  keyword: "anyOf",
                  params: {},
                  message: "must match a schema in anyOf",
                };
                if (vErrors === null) {
                  vErrors = [err2];
                } else {
                  vErrors.push(err2);
                }
                errors++;
                validate35.errors = vErrors;
                return false;
              } else {
                errors = _errs5;
                if (vErrors !== null) {
                  if (_errs5) {
                    vErrors.length = _errs5;
                  } else {
                    vErrors = null;
                  }
                }
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.operation_id !== undefined) {
                const _errs10 = errors;
                if (typeof data.operation_id !== "string") {
                  validate35.errors = [
                    {
                      instancePath: instancePath + "/operation_id",
                      schemaPath: "#/properties/operation_id/type",
                      keyword: "type",
                      params: { type: "string" },
                      message: "must be string",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs10 === errors;
              } else {
                var valid0 = true;
              }
              if (valid0) {
                if (data.path !== undefined) {
                  let data3 = data.path;
                  const _errs12 = errors;
                  if (errors === _errs12) {
                    if (typeof data3 === "string") {
                      if (func2(data3) < 1) {
                        validate35.errors = [
                          {
                            instancePath: instancePath + "/path",
                            schemaPath: "#/properties/path/minLength",
                            keyword: "minLength",
                            params: { limit: 1 },
                            message: "must NOT have fewer than 1 characters",
                          },
                        ];
                        return false;
                      }
                    } else {
                      validate35.errors = [
                        {
                          instancePath: instancePath + "/path",
                          schemaPath: "#/properties/path/type",
                          keyword: "type",
                          params: { type: "string" },
                          message: "must be string",
                        },
                      ];
                      return false;
                    }
                  }
                  var valid0 = _errs12 === errors;
                } else {
                  var valid0 = true;
                }
                if (valid0) {
                  if (data.schema_version !== undefined) {
                    let data4 = data.schema_version;
                    const _errs14 = errors;
                    if (!(
                      typeof data4 == "number" &&
                      !(data4 % 1) &&
                      !isNaN(data4) &&
                      isFinite(data4)
                    )) {
                      validate35.errors = [
                        {
                          instancePath: instancePath + "/schema_version",
                          schemaPath: "#/properties/schema_version/type",
                          keyword: "type",
                          params: { type: "integer" },
                          message: "must be integer",
                        },
                      ];
                      return false;
                    }
                    if (1 !== data4) {
                      validate35.errors = [
                        {
                          instancePath: instancePath + "/schema_version",
                          schemaPath: "#/properties/schema_version/const",
                          keyword: "const",
                          params: { allowedValue: 1 },
                          message: "must be equal to constant",
                        },
                      ];
                      return false;
                    }
                    var valid0 = _errs14 === errors;
                  } else {
                    var valid0 = true;
                  }
                }
              }
            }
          }
        }
      }
    } else {
      validate35.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate35.errors = vErrors;
  return errors === 0;
}
validate35.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateRegistrationDTO = validate23;
exports.validateResourceSummaryDTO = validate36;
function validate36(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:ResourceSummaryDTO" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate36.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.id === undefined && (missing0 = "id")) ||
        (data.name === undefined && (missing0 = "name")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate36.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "id" ||
            key0 === "name" ||
            key0 === "schema_version"
          )) {
            validate36.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.id !== undefined) {
            const _errs2 = errors;
            if (typeof data.id !== "string") {
              validate36.errors = [
                {
                  instancePath: instancePath + "/id",
                  schemaPath: "#/properties/id/type",
                  keyword: "type",
                  params: { type: "string" },
                  message: "must be string",
                },
              ];
              return false;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.name !== undefined) {
              const _errs4 = errors;
              if (typeof data.name !== "string") {
                validate36.errors = [
                  {
                    instancePath: instancePath + "/name",
                    schemaPath: "#/properties/name/type",
                    keyword: "type",
                    params: { type: "string" },
                    message: "must be string",
                  },
                ];
                return false;
              }
              var valid0 = _errs4 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.schema_version !== undefined) {
                let data2 = data.schema_version;
                const _errs6 = errors;
                if (!(
                  typeof data2 == "number" &&
                  !(data2 % 1) &&
                  !isNaN(data2) &&
                  isFinite(data2)
                )) {
                  validate36.errors = [
                    {
                      instancePath: instancePath + "/schema_version",
                      schemaPath: "#/properties/schema_version/type",
                      keyword: "type",
                      params: { type: "integer" },
                      message: "must be integer",
                    },
                  ];
                  return false;
                }
                if (1 !== data2) {
                  validate36.errors = [
                    {
                      instancePath: instancePath + "/schema_version",
                      schemaPath: "#/properties/schema_version/const",
                      keyword: "const",
                      params: { allowedValue: 1 },
                      message: "must be equal to constant",
                    },
                  ];
                  return false;
                }
                var valid0 = _errs6 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate36.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate36.errors = vErrors;
  return errors === 0;
}
validate36.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateSuccess_BootstrapReply_ = validate37;
const schema52 = {
  $id: "urn:deykit:transport:Success_BootstrapReply_",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    data: { $ref: "urn:deykit:transport:BootstrapReply#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
    warnings: {
      default: [],
      items: { $ref: "urn:deykit:transport:ErrorDTO#" },
      title: "Warnings",
      type: "array",
    },
  },
  required: ["data", "schema_version"],
  title: "Success[BootstrapReply]",
  type: "object",
};
function validate37(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Success_BootstrapReply_" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate37.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.data === undefined && (missing0 = "data")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate37.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "data" ||
            key0 === "schema_version" ||
            key0 === "warnings"
          )) {
            validate37.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.data !== undefined) {
            let data0 = data.data;
            const _errs2 = errors;
            const _errs3 = errors;
            if (errors === _errs3) {
              if (data0 && typeof data0 == "object" && !Array.isArray(data0)) {
                let missing1;
                if (
                  (data0.capability === undefined &&
                    (missing1 = "capability")) ||
                  (data0.origin === undefined && (missing1 = "origin"))
                ) {
                  validate37.errors = [
                    {
                      instancePath: instancePath + "/data",
                      schemaPath:
                        "urn:deykit:transport:BootstrapReply#/required",
                      keyword: "required",
                      params: { missingProperty: missing1 },
                      message: "must have required property '" + missing1 + "'",
                    },
                  ];
                  return false;
                } else {
                  const _errs5 = errors;
                  for (const key1 in data0) {
                    if (!(
                      key1 === "api_version" ||
                      key1 === "capability" ||
                      key1 === "origin"
                    )) {
                      validate37.errors = [
                        {
                          instancePath: instancePath + "/data",
                          schemaPath:
                            "urn:deykit:transport:BootstrapReply#/additionalProperties",
                          keyword: "additionalProperties",
                          params: { additionalProperty: key1 },
                          message: "must NOT have additional properties",
                        },
                      ];
                      return false;
                      break;
                    }
                  }
                  if (_errs5 === errors) {
                    if (data0.api_version !== undefined) {
                      let data1 = data0.api_version;
                      const _errs6 = errors;
                      if (!(
                        typeof data1 == "number" &&
                        !(data1 % 1) &&
                        !isNaN(data1) &&
                        isFinite(data1)
                      )) {
                        validate37.errors = [
                          {
                            instancePath: instancePath + "/data/api_version",
                            schemaPath:
                              "urn:deykit:transport:BootstrapReply#/properties/api_version/type",
                            keyword: "type",
                            params: { type: "integer" },
                            message: "must be integer",
                          },
                        ];
                        return false;
                      }
                      if (1 !== data1) {
                        validate37.errors = [
                          {
                            instancePath: instancePath + "/data/api_version",
                            schemaPath:
                              "urn:deykit:transport:BootstrapReply#/properties/api_version/const",
                            keyword: "const",
                            params: { allowedValue: 1 },
                            message: "must be equal to constant",
                          },
                        ];
                        return false;
                      }
                      var valid2 = _errs6 === errors;
                    } else {
                      var valid2 = true;
                    }
                    if (valid2) {
                      if (data0.capability !== undefined) {
                        let data2 = data0.capability;
                        const _errs8 = errors;
                        if (errors === _errs8) {
                          if (typeof data2 === "string") {
                            if (!pattern4.test(data2)) {
                              validate37.errors = [
                                {
                                  instancePath:
                                    instancePath + "/data/capability",
                                  schemaPath:
                                    "urn:deykit:transport:BootstrapReply#/properties/capability/pattern",
                                  keyword: "pattern",
                                  params: { pattern: "^[A-Za-z0-9_-]{43}$" },
                                  message:
                                    'must match pattern "' +
                                    "^[A-Za-z0-9_-]{43}$" +
                                    '"',
                                },
                              ];
                              return false;
                            }
                          } else {
                            validate37.errors = [
                              {
                                instancePath: instancePath + "/data/capability",
                                schemaPath:
                                  "urn:deykit:transport:BootstrapReply#/properties/capability/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                        }
                        var valid2 = _errs8 === errors;
                      } else {
                        var valid2 = true;
                      }
                      if (valid2) {
                        if (data0.origin !== undefined) {
                          const _errs10 = errors;
                          if (typeof data0.origin !== "string") {
                            validate37.errors = [
                              {
                                instancePath: instancePath + "/data/origin",
                                schemaPath:
                                  "urn:deykit:transport:BootstrapReply#/properties/origin/type",
                                keyword: "type",
                                params: { type: "string" },
                                message: "must be string",
                              },
                            ];
                            return false;
                          }
                          var valid2 = _errs10 === errors;
                        } else {
                          var valid2 = true;
                        }
                      }
                    }
                  }
                }
              } else {
                validate37.errors = [
                  {
                    instancePath: instancePath + "/data",
                    schemaPath: "urn:deykit:transport:BootstrapReply#/type",
                    keyword: "type",
                    params: { type: "object" },
                    message: "must be object",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data4 = data.schema_version;
              const _errs12 = errors;
              if (!(
                typeof data4 == "number" &&
                !(data4 % 1) &&
                !isNaN(data4) &&
                isFinite(data4)
              )) {
                validate37.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data4) {
                validate37.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs12 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.warnings !== undefined) {
                let data5 = data.warnings;
                const _errs14 = errors;
                if (errors === _errs14) {
                  if (Array.isArray(data5)) {
                    var valid3 = true;
                    const len0 = data5.length;
                    for (let i0 = 0; i0 < len0; i0++) {
                      let data6 = data5[i0];
                      const _errs16 = errors;
                      const _errs17 = errors;
                      if (errors === _errs17) {
                        if (
                          data6 &&
                          typeof data6 == "object" &&
                          !Array.isArray(data6)
                        ) {
                          let missing2;
                          if (
                            (data6.code === undefined && (missing2 = "code")) ||
                            (data6.message === undefined &&
                              (missing2 = "message")) ||
                            (data6.schema_version === undefined &&
                              (missing2 = "schema_version"))
                          ) {
                            validate37.errors = [
                              {
                                instancePath: instancePath + "/warnings/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/required",
                                keyword: "required",
                                params: { missingProperty: missing2 },
                                message:
                                  "must have required property '" +
                                  missing2 +
                                  "'",
                              },
                            ];
                            return false;
                          } else {
                            const _errs19 = errors;
                            for (const key2 in data6) {
                              if (!(
                                key2 === "code" ||
                                key2 === "correlation_id" ||
                                key2 === "message" ||
                                key2 === "reason" ||
                                key2 === "resource_id" ||
                                key2 === "row" ||
                                key2 === "schema_version"
                              )) {
                                validate37.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/warnings/" + i0,
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/additionalProperties",
                                    keyword: "additionalProperties",
                                    params: { additionalProperty: key2 },
                                    message:
                                      "must NOT have additional properties",
                                  },
                                ];
                                return false;
                                break;
                              }
                            }
                            if (_errs19 === errors) {
                              if (data6.code !== undefined) {
                                const _errs20 = errors;
                                if (typeof data6.code !== "string") {
                                  validate37.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/code",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/code/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid5 = _errs20 === errors;
                              } else {
                                var valid5 = true;
                              }
                              if (valid5) {
                                if (data6.correlation_id !== undefined) {
                                  let data8 = data6.correlation_id;
                                  const _errs22 = errors;
                                  const _errs23 = errors;
                                  let valid6 = false;
                                  const _errs24 = errors;
                                  if (typeof data8 !== "string") {
                                    const err0 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err0];
                                    } else {
                                      vErrors.push(err0);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs24 === errors;
                                  valid6 = valid6 || _valid0;
                                  const _errs26 = errors;
                                  if (data8 !== null) {
                                    const err1 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                                      keyword: "type",
                                      params: { type: "null" },
                                      message: "must be null",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err1];
                                    } else {
                                      vErrors.push(err1);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs26 === errors;
                                  valid6 = valid6 || _valid0;
                                  if (!valid6) {
                                    const err2 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                                      keyword: "anyOf",
                                      params: {},
                                      message: "must match a schema in anyOf",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err2];
                                    } else {
                                      vErrors.push(err2);
                                    }
                                    errors++;
                                    validate37.errors = vErrors;
                                    return false;
                                  } else {
                                    errors = _errs23;
                                    if (vErrors !== null) {
                                      if (_errs23) {
                                        vErrors.length = _errs23;
                                      } else {
                                        vErrors = null;
                                      }
                                    }
                                  }
                                  var valid5 = _errs22 === errors;
                                } else {
                                  var valid5 = true;
                                }
                                if (valid5) {
                                  if (data6.message !== undefined) {
                                    const _errs28 = errors;
                                    if (typeof data6.message !== "string") {
                                      validate37.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/message",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid5 = _errs28 === errors;
                                  } else {
                                    var valid5 = true;
                                  }
                                  if (valid5) {
                                    if (data6.reason !== undefined) {
                                      let data10 = data6.reason;
                                      const _errs30 = errors;
                                      const _errs31 = errors;
                                      let valid7 = false;
                                      const _errs32 = errors;
                                      if (typeof data10 !== "string") {
                                        const err3 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err3];
                                        } else {
                                          vErrors.push(err3);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs32 === errors;
                                      valid7 = valid7 || _valid1;
                                      const _errs34 = errors;
                                      if (data10 !== null) {
                                        const err4 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                          keyword: "type",
                                          params: { type: "null" },
                                          message: "must be null",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err4];
                                        } else {
                                          vErrors.push(err4);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs34 === errors;
                                      valid7 = valid7 || _valid1;
                                      if (!valid7) {
                                        const err5 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                          keyword: "anyOf",
                                          params: {},
                                          message:
                                            "must match a schema in anyOf",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err5];
                                        } else {
                                          vErrors.push(err5);
                                        }
                                        errors++;
                                        validate37.errors = vErrors;
                                        return false;
                                      } else {
                                        errors = _errs31;
                                        if (vErrors !== null) {
                                          if (_errs31) {
                                            vErrors.length = _errs31;
                                          } else {
                                            vErrors = null;
                                          }
                                        }
                                      }
                                      var valid5 = _errs30 === errors;
                                    } else {
                                      var valid5 = true;
                                    }
                                    if (valid5) {
                                      if (data6.resource_id !== undefined) {
                                        let data11 = data6.resource_id;
                                        const _errs36 = errors;
                                        const _errs37 = errors;
                                        let valid8 = false;
                                        const _errs38 = errors;
                                        if (typeof data11 !== "string") {
                                          const err6 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err6];
                                          } else {
                                            vErrors.push(err6);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs38 === errors;
                                        valid8 = valid8 || _valid2;
                                        const _errs40 = errors;
                                        if (data11 !== null) {
                                          const err7 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                            keyword: "type",
                                            params: { type: "null" },
                                            message: "must be null",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err7];
                                          } else {
                                            vErrors.push(err7);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs40 === errors;
                                        valid8 = valid8 || _valid2;
                                        if (!valid8) {
                                          const err8 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                            keyword: "anyOf",
                                            params: {},
                                            message:
                                              "must match a schema in anyOf",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err8];
                                          } else {
                                            vErrors.push(err8);
                                          }
                                          errors++;
                                          validate37.errors = vErrors;
                                          return false;
                                        } else {
                                          errors = _errs37;
                                          if (vErrors !== null) {
                                            if (_errs37) {
                                              vErrors.length = _errs37;
                                            } else {
                                              vErrors = null;
                                            }
                                          }
                                        }
                                        var valid5 = _errs36 === errors;
                                      } else {
                                        var valid5 = true;
                                      }
                                      if (valid5) {
                                        if (data6.row !== undefined) {
                                          let data12 = data6.row;
                                          const _errs42 = errors;
                                          const _errs43 = errors;
                                          let valid9 = false;
                                          const _errs44 = errors;
                                          if (!(
                                            typeof data12 == "number" &&
                                            !(data12 % 1) &&
                                            !isNaN(data12) &&
                                            isFinite(data12)
                                          )) {
                                            const err9 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                              keyword: "type",
                                              params: { type: "integer" },
                                              message: "must be integer",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err9];
                                            } else {
                                              vErrors.push(err9);
                                            }
                                            errors++;
                                          }
                                          if (errors === _errs44) {
                                            if (
                                              typeof data12 == "number" &&
                                              isFinite(data12)
                                            ) {
                                              if (
                                                data12 > 9007199254740991 ||
                                                isNaN(data12)
                                              ) {
                                                const err10 = {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/row",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                                  keyword: "maximum",
                                                  params: {
                                                    comparison: "<=",
                                                    limit: 9007199254740991,
                                                  },
                                                  message:
                                                    "must be <= 9007199254740991",
                                                };
                                                if (vErrors === null) {
                                                  vErrors = [err10];
                                                } else {
                                                  vErrors.push(err10);
                                                }
                                                errors++;
                                              } else {
                                                if (
                                                  data12 < 0 ||
                                                  isNaN(data12)
                                                ) {
                                                  const err11 = {
                                                    instancePath:
                                                      instancePath +
                                                      "/warnings/" +
                                                      i0 +
                                                      "/row",
                                                    schemaPath:
                                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                                    keyword: "minimum",
                                                    params: {
                                                      comparison: ">=",
                                                      limit: 0,
                                                    },
                                                    message: "must be >= 0",
                                                  };
                                                  if (vErrors === null) {
                                                    vErrors = [err11];
                                                  } else {
                                                    vErrors.push(err11);
                                                  }
                                                  errors++;
                                                }
                                              }
                                            }
                                          }
                                          var _valid3 = _errs44 === errors;
                                          valid9 = valid9 || _valid3;
                                          const _errs46 = errors;
                                          if (data12 !== null) {
                                            const err12 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                              keyword: "type",
                                              params: { type: "null" },
                                              message: "must be null",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err12];
                                            } else {
                                              vErrors.push(err12);
                                            }
                                            errors++;
                                          }
                                          var _valid3 = _errs46 === errors;
                                          valid9 = valid9 || _valid3;
                                          if (!valid9) {
                                            const err13 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                              keyword: "anyOf",
                                              params: {},
                                              message:
                                                "must match a schema in anyOf",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err13];
                                            } else {
                                              vErrors.push(err13);
                                            }
                                            errors++;
                                            validate37.errors = vErrors;
                                            return false;
                                          } else {
                                            errors = _errs43;
                                            if (vErrors !== null) {
                                              if (_errs43) {
                                                vErrors.length = _errs43;
                                              } else {
                                                vErrors = null;
                                              }
                                            }
                                          }
                                          var valid5 = _errs42 === errors;
                                        } else {
                                          var valid5 = true;
                                        }
                                        if (valid5) {
                                          if (
                                            data6.schema_version !== undefined
                                          ) {
                                            let data13 = data6.schema_version;
                                            const _errs48 = errors;
                                            if (!(
                                              typeof data13 == "number" &&
                                              !(data13 % 1) &&
                                              !isNaN(data13) &&
                                              isFinite(data13)
                                            )) {
                                              validate37.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                                  keyword: "type",
                                                  params: { type: "integer" },
                                                  message: "must be integer",
                                                },
                                              ];
                                              return false;
                                            }
                                            if (1 !== data13) {
                                              validate37.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                                  keyword: "const",
                                                  params: { allowedValue: 1 },
                                                  message:
                                                    "must be equal to constant",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid5 = _errs48 === errors;
                                          } else {
                                            var valid5 = true;
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        } else {
                          validate37.errors = [
                            {
                              instancePath: instancePath + "/warnings/" + i0,
                              schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                              keyword: "type",
                              params: { type: "object" },
                              message: "must be object",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid3 = _errs16 === errors;
                      if (!valid3) {
                        break;
                      }
                    }
                  } else {
                    validate37.errors = [
                      {
                        instancePath: instancePath + "/warnings",
                        schemaPath: "#/properties/warnings/type",
                        keyword: "type",
                        params: { type: "array" },
                        message: "must be array",
                      },
                    ];
                    return false;
                  }
                }
                var valid0 = _errs14 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate37.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate37.errors = vErrors;
  return errors === 0;
}
validate37.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateSuccess_DemoCreateDTO_ = validate38;
const schema55 = {
  $id: "urn:deykit:transport:Success_DemoCreateDTO_",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    data: { $ref: "urn:deykit:transport:DemoCreateDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
    warnings: {
      default: [],
      items: { $ref: "urn:deykit:transport:ErrorDTO#" },
      title: "Warnings",
      type: "array",
    },
  },
  required: ["data", "schema_version"],
  title: "Success[DemoCreateDTO]",
  type: "object",
};
function validate38(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Success_DemoCreateDTO_" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate38.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.data === undefined && (missing0 = "data")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate38.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "data" ||
            key0 === "schema_version" ||
            key0 === "warnings"
          )) {
            validate38.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.data !== undefined) {
            const _errs2 = errors;
            if (
              !validate22(data.data, {
                instancePath: instancePath + "/data",
                parentData: data,
                parentDataProperty: "data",
                rootData,
                dynamicAnchors,
              })
            ) {
              vErrors =
                vErrors === null
                  ? validate22.errors
                  : vErrors.concat(validate22.errors);
              errors = vErrors.length;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data1 = data.schema_version;
              const _errs3 = errors;
              if (!(
                typeof data1 == "number" &&
                !(data1 % 1) &&
                !isNaN(data1) &&
                isFinite(data1)
              )) {
                validate38.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data1) {
                validate38.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs3 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.warnings !== undefined) {
                let data2 = data.warnings;
                const _errs5 = errors;
                if (errors === _errs5) {
                  if (Array.isArray(data2)) {
                    var valid1 = true;
                    const len0 = data2.length;
                    for (let i0 = 0; i0 < len0; i0++) {
                      let data3 = data2[i0];
                      const _errs7 = errors;
                      const _errs8 = errors;
                      if (errors === _errs8) {
                        if (
                          data3 &&
                          typeof data3 == "object" &&
                          !Array.isArray(data3)
                        ) {
                          let missing1;
                          if (
                            (data3.code === undefined && (missing1 = "code")) ||
                            (data3.message === undefined &&
                              (missing1 = "message")) ||
                            (data3.schema_version === undefined &&
                              (missing1 = "schema_version"))
                          ) {
                            validate38.errors = [
                              {
                                instancePath: instancePath + "/warnings/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/required",
                                keyword: "required",
                                params: { missingProperty: missing1 },
                                message:
                                  "must have required property '" +
                                  missing1 +
                                  "'",
                              },
                            ];
                            return false;
                          } else {
                            const _errs10 = errors;
                            for (const key1 in data3) {
                              if (!(
                                key1 === "code" ||
                                key1 === "correlation_id" ||
                                key1 === "message" ||
                                key1 === "reason" ||
                                key1 === "resource_id" ||
                                key1 === "row" ||
                                key1 === "schema_version"
                              )) {
                                validate38.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/warnings/" + i0,
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/additionalProperties",
                                    keyword: "additionalProperties",
                                    params: { additionalProperty: key1 },
                                    message:
                                      "must NOT have additional properties",
                                  },
                                ];
                                return false;
                                break;
                              }
                            }
                            if (_errs10 === errors) {
                              if (data3.code !== undefined) {
                                const _errs11 = errors;
                                if (typeof data3.code !== "string") {
                                  validate38.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/code",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/code/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid3 = _errs11 === errors;
                              } else {
                                var valid3 = true;
                              }
                              if (valid3) {
                                if (data3.correlation_id !== undefined) {
                                  let data5 = data3.correlation_id;
                                  const _errs13 = errors;
                                  const _errs14 = errors;
                                  let valid4 = false;
                                  const _errs15 = errors;
                                  if (typeof data5 !== "string") {
                                    const err0 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err0];
                                    } else {
                                      vErrors.push(err0);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs15 === errors;
                                  valid4 = valid4 || _valid0;
                                  const _errs17 = errors;
                                  if (data5 !== null) {
                                    const err1 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                                      keyword: "type",
                                      params: { type: "null" },
                                      message: "must be null",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err1];
                                    } else {
                                      vErrors.push(err1);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs17 === errors;
                                  valid4 = valid4 || _valid0;
                                  if (!valid4) {
                                    const err2 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                                      keyword: "anyOf",
                                      params: {},
                                      message: "must match a schema in anyOf",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err2];
                                    } else {
                                      vErrors.push(err2);
                                    }
                                    errors++;
                                    validate38.errors = vErrors;
                                    return false;
                                  } else {
                                    errors = _errs14;
                                    if (vErrors !== null) {
                                      if (_errs14) {
                                        vErrors.length = _errs14;
                                      } else {
                                        vErrors = null;
                                      }
                                    }
                                  }
                                  var valid3 = _errs13 === errors;
                                } else {
                                  var valid3 = true;
                                }
                                if (valid3) {
                                  if (data3.message !== undefined) {
                                    const _errs19 = errors;
                                    if (typeof data3.message !== "string") {
                                      validate38.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/message",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid3 = _errs19 === errors;
                                  } else {
                                    var valid3 = true;
                                  }
                                  if (valid3) {
                                    if (data3.reason !== undefined) {
                                      let data7 = data3.reason;
                                      const _errs21 = errors;
                                      const _errs22 = errors;
                                      let valid5 = false;
                                      const _errs23 = errors;
                                      if (typeof data7 !== "string") {
                                        const err3 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err3];
                                        } else {
                                          vErrors.push(err3);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs23 === errors;
                                      valid5 = valid5 || _valid1;
                                      const _errs25 = errors;
                                      if (data7 !== null) {
                                        const err4 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                          keyword: "type",
                                          params: { type: "null" },
                                          message: "must be null",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err4];
                                        } else {
                                          vErrors.push(err4);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs25 === errors;
                                      valid5 = valid5 || _valid1;
                                      if (!valid5) {
                                        const err5 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                          keyword: "anyOf",
                                          params: {},
                                          message:
                                            "must match a schema in anyOf",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err5];
                                        } else {
                                          vErrors.push(err5);
                                        }
                                        errors++;
                                        validate38.errors = vErrors;
                                        return false;
                                      } else {
                                        errors = _errs22;
                                        if (vErrors !== null) {
                                          if (_errs22) {
                                            vErrors.length = _errs22;
                                          } else {
                                            vErrors = null;
                                          }
                                        }
                                      }
                                      var valid3 = _errs21 === errors;
                                    } else {
                                      var valid3 = true;
                                    }
                                    if (valid3) {
                                      if (data3.resource_id !== undefined) {
                                        let data8 = data3.resource_id;
                                        const _errs27 = errors;
                                        const _errs28 = errors;
                                        let valid6 = false;
                                        const _errs29 = errors;
                                        if (typeof data8 !== "string") {
                                          const err6 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err6];
                                          } else {
                                            vErrors.push(err6);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs29 === errors;
                                        valid6 = valid6 || _valid2;
                                        const _errs31 = errors;
                                        if (data8 !== null) {
                                          const err7 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                            keyword: "type",
                                            params: { type: "null" },
                                            message: "must be null",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err7];
                                          } else {
                                            vErrors.push(err7);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs31 === errors;
                                        valid6 = valid6 || _valid2;
                                        if (!valid6) {
                                          const err8 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                            keyword: "anyOf",
                                            params: {},
                                            message:
                                              "must match a schema in anyOf",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err8];
                                          } else {
                                            vErrors.push(err8);
                                          }
                                          errors++;
                                          validate38.errors = vErrors;
                                          return false;
                                        } else {
                                          errors = _errs28;
                                          if (vErrors !== null) {
                                            if (_errs28) {
                                              vErrors.length = _errs28;
                                            } else {
                                              vErrors = null;
                                            }
                                          }
                                        }
                                        var valid3 = _errs27 === errors;
                                      } else {
                                        var valid3 = true;
                                      }
                                      if (valid3) {
                                        if (data3.row !== undefined) {
                                          let data9 = data3.row;
                                          const _errs33 = errors;
                                          const _errs34 = errors;
                                          let valid7 = false;
                                          const _errs35 = errors;
                                          if (!(
                                            typeof data9 == "number" &&
                                            !(data9 % 1) &&
                                            !isNaN(data9) &&
                                            isFinite(data9)
                                          )) {
                                            const err9 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                              keyword: "type",
                                              params: { type: "integer" },
                                              message: "must be integer",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err9];
                                            } else {
                                              vErrors.push(err9);
                                            }
                                            errors++;
                                          }
                                          if (errors === _errs35) {
                                            if (
                                              typeof data9 == "number" &&
                                              isFinite(data9)
                                            ) {
                                              if (
                                                data9 > 9007199254740991 ||
                                                isNaN(data9)
                                              ) {
                                                const err10 = {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/row",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                                  keyword: "maximum",
                                                  params: {
                                                    comparison: "<=",
                                                    limit: 9007199254740991,
                                                  },
                                                  message:
                                                    "must be <= 9007199254740991",
                                                };
                                                if (vErrors === null) {
                                                  vErrors = [err10];
                                                } else {
                                                  vErrors.push(err10);
                                                }
                                                errors++;
                                              } else {
                                                if (data9 < 0 || isNaN(data9)) {
                                                  const err11 = {
                                                    instancePath:
                                                      instancePath +
                                                      "/warnings/" +
                                                      i0 +
                                                      "/row",
                                                    schemaPath:
                                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                                    keyword: "minimum",
                                                    params: {
                                                      comparison: ">=",
                                                      limit: 0,
                                                    },
                                                    message: "must be >= 0",
                                                  };
                                                  if (vErrors === null) {
                                                    vErrors = [err11];
                                                  } else {
                                                    vErrors.push(err11);
                                                  }
                                                  errors++;
                                                }
                                              }
                                            }
                                          }
                                          var _valid3 = _errs35 === errors;
                                          valid7 = valid7 || _valid3;
                                          const _errs37 = errors;
                                          if (data9 !== null) {
                                            const err12 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                              keyword: "type",
                                              params: { type: "null" },
                                              message: "must be null",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err12];
                                            } else {
                                              vErrors.push(err12);
                                            }
                                            errors++;
                                          }
                                          var _valid3 = _errs37 === errors;
                                          valid7 = valid7 || _valid3;
                                          if (!valid7) {
                                            const err13 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                              keyword: "anyOf",
                                              params: {},
                                              message:
                                                "must match a schema in anyOf",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err13];
                                            } else {
                                              vErrors.push(err13);
                                            }
                                            errors++;
                                            validate38.errors = vErrors;
                                            return false;
                                          } else {
                                            errors = _errs34;
                                            if (vErrors !== null) {
                                              if (_errs34) {
                                                vErrors.length = _errs34;
                                              } else {
                                                vErrors = null;
                                              }
                                            }
                                          }
                                          var valid3 = _errs33 === errors;
                                        } else {
                                          var valid3 = true;
                                        }
                                        if (valid3) {
                                          if (
                                            data3.schema_version !== undefined
                                          ) {
                                            let data10 = data3.schema_version;
                                            const _errs39 = errors;
                                            if (!(
                                              typeof data10 == "number" &&
                                              !(data10 % 1) &&
                                              !isNaN(data10) &&
                                              isFinite(data10)
                                            )) {
                                              validate38.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                                  keyword: "type",
                                                  params: { type: "integer" },
                                                  message: "must be integer",
                                                },
                                              ];
                                              return false;
                                            }
                                            if (1 !== data10) {
                                              validate38.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                                  keyword: "const",
                                                  params: { allowedValue: 1 },
                                                  message:
                                                    "must be equal to constant",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid3 = _errs39 === errors;
                                          } else {
                                            var valid3 = true;
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        } else {
                          validate38.errors = [
                            {
                              instancePath: instancePath + "/warnings/" + i0,
                              schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                              keyword: "type",
                              params: { type: "object" },
                              message: "must be object",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid1 = _errs7 === errors;
                      if (!valid1) {
                        break;
                      }
                    }
                  } else {
                    validate38.errors = [
                      {
                        instancePath: instancePath + "/warnings",
                        schemaPath: "#/properties/warnings/type",
                        keyword: "type",
                        params: { type: "array" },
                        message: "must be array",
                      },
                    ];
                    return false;
                  }
                }
                var valid0 = _errs5 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate38.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate38.errors = vErrors;
  return errors === 0;
}
validate38.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateSuccess_ProjectOverviewDTO_ = validate40;
const schema57 = {
  $id: "urn:deykit:transport:Success_ProjectOverviewDTO_",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    data: { $ref: "urn:deykit:transport:ProjectOverviewDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
    warnings: {
      default: [],
      items: { $ref: "urn:deykit:transport:ErrorDTO#" },
      title: "Warnings",
      type: "array",
    },
  },
  required: ["data", "schema_version"],
  title: "Success[ProjectOverviewDTO]",
  type: "object",
};
function validate40(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Success_ProjectOverviewDTO_" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate40.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.data === undefined && (missing0 = "data")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate40.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "data" ||
            key0 === "schema_version" ||
            key0 === "warnings"
          )) {
            validate40.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.data !== undefined) {
            const _errs2 = errors;
            if (
              !validate29(data.data, {
                instancePath: instancePath + "/data",
                parentData: data,
                parentDataProperty: "data",
                rootData,
                dynamicAnchors,
              })
            ) {
              vErrors =
                vErrors === null
                  ? validate29.errors
                  : vErrors.concat(validate29.errors);
              errors = vErrors.length;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data1 = data.schema_version;
              const _errs3 = errors;
              if (!(
                typeof data1 == "number" &&
                !(data1 % 1) &&
                !isNaN(data1) &&
                isFinite(data1)
              )) {
                validate40.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data1) {
                validate40.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs3 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.warnings !== undefined) {
                let data2 = data.warnings;
                const _errs5 = errors;
                if (errors === _errs5) {
                  if (Array.isArray(data2)) {
                    var valid1 = true;
                    const len0 = data2.length;
                    for (let i0 = 0; i0 < len0; i0++) {
                      let data3 = data2[i0];
                      const _errs7 = errors;
                      const _errs8 = errors;
                      if (errors === _errs8) {
                        if (
                          data3 &&
                          typeof data3 == "object" &&
                          !Array.isArray(data3)
                        ) {
                          let missing1;
                          if (
                            (data3.code === undefined && (missing1 = "code")) ||
                            (data3.message === undefined &&
                              (missing1 = "message")) ||
                            (data3.schema_version === undefined &&
                              (missing1 = "schema_version"))
                          ) {
                            validate40.errors = [
                              {
                                instancePath: instancePath + "/warnings/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/required",
                                keyword: "required",
                                params: { missingProperty: missing1 },
                                message:
                                  "must have required property '" +
                                  missing1 +
                                  "'",
                              },
                            ];
                            return false;
                          } else {
                            const _errs10 = errors;
                            for (const key1 in data3) {
                              if (!(
                                key1 === "code" ||
                                key1 === "correlation_id" ||
                                key1 === "message" ||
                                key1 === "reason" ||
                                key1 === "resource_id" ||
                                key1 === "row" ||
                                key1 === "schema_version"
                              )) {
                                validate40.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/warnings/" + i0,
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/additionalProperties",
                                    keyword: "additionalProperties",
                                    params: { additionalProperty: key1 },
                                    message:
                                      "must NOT have additional properties",
                                  },
                                ];
                                return false;
                                break;
                              }
                            }
                            if (_errs10 === errors) {
                              if (data3.code !== undefined) {
                                const _errs11 = errors;
                                if (typeof data3.code !== "string") {
                                  validate40.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/code",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/code/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid3 = _errs11 === errors;
                              } else {
                                var valid3 = true;
                              }
                              if (valid3) {
                                if (data3.correlation_id !== undefined) {
                                  let data5 = data3.correlation_id;
                                  const _errs13 = errors;
                                  const _errs14 = errors;
                                  let valid4 = false;
                                  const _errs15 = errors;
                                  if (typeof data5 !== "string") {
                                    const err0 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err0];
                                    } else {
                                      vErrors.push(err0);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs15 === errors;
                                  valid4 = valid4 || _valid0;
                                  const _errs17 = errors;
                                  if (data5 !== null) {
                                    const err1 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                                      keyword: "type",
                                      params: { type: "null" },
                                      message: "must be null",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err1];
                                    } else {
                                      vErrors.push(err1);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs17 === errors;
                                  valid4 = valid4 || _valid0;
                                  if (!valid4) {
                                    const err2 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                                      keyword: "anyOf",
                                      params: {},
                                      message: "must match a schema in anyOf",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err2];
                                    } else {
                                      vErrors.push(err2);
                                    }
                                    errors++;
                                    validate40.errors = vErrors;
                                    return false;
                                  } else {
                                    errors = _errs14;
                                    if (vErrors !== null) {
                                      if (_errs14) {
                                        vErrors.length = _errs14;
                                      } else {
                                        vErrors = null;
                                      }
                                    }
                                  }
                                  var valid3 = _errs13 === errors;
                                } else {
                                  var valid3 = true;
                                }
                                if (valid3) {
                                  if (data3.message !== undefined) {
                                    const _errs19 = errors;
                                    if (typeof data3.message !== "string") {
                                      validate40.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/message",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid3 = _errs19 === errors;
                                  } else {
                                    var valid3 = true;
                                  }
                                  if (valid3) {
                                    if (data3.reason !== undefined) {
                                      let data7 = data3.reason;
                                      const _errs21 = errors;
                                      const _errs22 = errors;
                                      let valid5 = false;
                                      const _errs23 = errors;
                                      if (typeof data7 !== "string") {
                                        const err3 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err3];
                                        } else {
                                          vErrors.push(err3);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs23 === errors;
                                      valid5 = valid5 || _valid1;
                                      const _errs25 = errors;
                                      if (data7 !== null) {
                                        const err4 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                          keyword: "type",
                                          params: { type: "null" },
                                          message: "must be null",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err4];
                                        } else {
                                          vErrors.push(err4);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs25 === errors;
                                      valid5 = valid5 || _valid1;
                                      if (!valid5) {
                                        const err5 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                          keyword: "anyOf",
                                          params: {},
                                          message:
                                            "must match a schema in anyOf",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err5];
                                        } else {
                                          vErrors.push(err5);
                                        }
                                        errors++;
                                        validate40.errors = vErrors;
                                        return false;
                                      } else {
                                        errors = _errs22;
                                        if (vErrors !== null) {
                                          if (_errs22) {
                                            vErrors.length = _errs22;
                                          } else {
                                            vErrors = null;
                                          }
                                        }
                                      }
                                      var valid3 = _errs21 === errors;
                                    } else {
                                      var valid3 = true;
                                    }
                                    if (valid3) {
                                      if (data3.resource_id !== undefined) {
                                        let data8 = data3.resource_id;
                                        const _errs27 = errors;
                                        const _errs28 = errors;
                                        let valid6 = false;
                                        const _errs29 = errors;
                                        if (typeof data8 !== "string") {
                                          const err6 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err6];
                                          } else {
                                            vErrors.push(err6);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs29 === errors;
                                        valid6 = valid6 || _valid2;
                                        const _errs31 = errors;
                                        if (data8 !== null) {
                                          const err7 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                            keyword: "type",
                                            params: { type: "null" },
                                            message: "must be null",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err7];
                                          } else {
                                            vErrors.push(err7);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs31 === errors;
                                        valid6 = valid6 || _valid2;
                                        if (!valid6) {
                                          const err8 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                            keyword: "anyOf",
                                            params: {},
                                            message:
                                              "must match a schema in anyOf",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err8];
                                          } else {
                                            vErrors.push(err8);
                                          }
                                          errors++;
                                          validate40.errors = vErrors;
                                          return false;
                                        } else {
                                          errors = _errs28;
                                          if (vErrors !== null) {
                                            if (_errs28) {
                                              vErrors.length = _errs28;
                                            } else {
                                              vErrors = null;
                                            }
                                          }
                                        }
                                        var valid3 = _errs27 === errors;
                                      } else {
                                        var valid3 = true;
                                      }
                                      if (valid3) {
                                        if (data3.row !== undefined) {
                                          let data9 = data3.row;
                                          const _errs33 = errors;
                                          const _errs34 = errors;
                                          let valid7 = false;
                                          const _errs35 = errors;
                                          if (!(
                                            typeof data9 == "number" &&
                                            !(data9 % 1) &&
                                            !isNaN(data9) &&
                                            isFinite(data9)
                                          )) {
                                            const err9 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                              keyword: "type",
                                              params: { type: "integer" },
                                              message: "must be integer",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err9];
                                            } else {
                                              vErrors.push(err9);
                                            }
                                            errors++;
                                          }
                                          if (errors === _errs35) {
                                            if (
                                              typeof data9 == "number" &&
                                              isFinite(data9)
                                            ) {
                                              if (
                                                data9 > 9007199254740991 ||
                                                isNaN(data9)
                                              ) {
                                                const err10 = {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/row",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                                  keyword: "maximum",
                                                  params: {
                                                    comparison: "<=",
                                                    limit: 9007199254740991,
                                                  },
                                                  message:
                                                    "must be <= 9007199254740991",
                                                };
                                                if (vErrors === null) {
                                                  vErrors = [err10];
                                                } else {
                                                  vErrors.push(err10);
                                                }
                                                errors++;
                                              } else {
                                                if (data9 < 0 || isNaN(data9)) {
                                                  const err11 = {
                                                    instancePath:
                                                      instancePath +
                                                      "/warnings/" +
                                                      i0 +
                                                      "/row",
                                                    schemaPath:
                                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                                    keyword: "minimum",
                                                    params: {
                                                      comparison: ">=",
                                                      limit: 0,
                                                    },
                                                    message: "must be >= 0",
                                                  };
                                                  if (vErrors === null) {
                                                    vErrors = [err11];
                                                  } else {
                                                    vErrors.push(err11);
                                                  }
                                                  errors++;
                                                }
                                              }
                                            }
                                          }
                                          var _valid3 = _errs35 === errors;
                                          valid7 = valid7 || _valid3;
                                          const _errs37 = errors;
                                          if (data9 !== null) {
                                            const err12 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                              keyword: "type",
                                              params: { type: "null" },
                                              message: "must be null",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err12];
                                            } else {
                                              vErrors.push(err12);
                                            }
                                            errors++;
                                          }
                                          var _valid3 = _errs37 === errors;
                                          valid7 = valid7 || _valid3;
                                          if (!valid7) {
                                            const err13 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                              keyword: "anyOf",
                                              params: {},
                                              message:
                                                "must match a schema in anyOf",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err13];
                                            } else {
                                              vErrors.push(err13);
                                            }
                                            errors++;
                                            validate40.errors = vErrors;
                                            return false;
                                          } else {
                                            errors = _errs34;
                                            if (vErrors !== null) {
                                              if (_errs34) {
                                                vErrors.length = _errs34;
                                              } else {
                                                vErrors = null;
                                              }
                                            }
                                          }
                                          var valid3 = _errs33 === errors;
                                        } else {
                                          var valid3 = true;
                                        }
                                        if (valid3) {
                                          if (
                                            data3.schema_version !== undefined
                                          ) {
                                            let data10 = data3.schema_version;
                                            const _errs39 = errors;
                                            if (!(
                                              typeof data10 == "number" &&
                                              !(data10 % 1) &&
                                              !isNaN(data10) &&
                                              isFinite(data10)
                                            )) {
                                              validate40.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                                  keyword: "type",
                                                  params: { type: "integer" },
                                                  message: "must be integer",
                                                },
                                              ];
                                              return false;
                                            }
                                            if (1 !== data10) {
                                              validate40.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                                  keyword: "const",
                                                  params: { allowedValue: 1 },
                                                  message:
                                                    "must be equal to constant",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid3 = _errs39 === errors;
                                          } else {
                                            var valid3 = true;
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        } else {
                          validate40.errors = [
                            {
                              instancePath: instancePath + "/warnings/" + i0,
                              schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                              keyword: "type",
                              params: { type: "object" },
                              message: "must be object",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid1 = _errs7 === errors;
                      if (!valid1) {
                        break;
                      }
                    }
                  } else {
                    validate40.errors = [
                      {
                        instancePath: instancePath + "/warnings",
                        schemaPath: "#/properties/warnings/type",
                        keyword: "type",
                        params: { type: "array" },
                        message: "must be array",
                      },
                    ];
                    return false;
                  }
                }
                var valid0 = _errs5 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate40.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate40.errors = vErrors;
  return errors === 0;
}
validate40.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateSuccess_RebuildIndexDTO_ = validate42;
const schema59 = {
  $id: "urn:deykit:transport:Success_RebuildIndexDTO_",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    data: { $ref: "urn:deykit:transport:RebuildIndexDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
    warnings: {
      default: [],
      items: { $ref: "urn:deykit:transport:ErrorDTO#" },
      title: "Warnings",
      type: "array",
    },
  },
  required: ["data", "schema_version"],
  title: "Success[RebuildIndexDTO]",
  type: "object",
};
function validate42(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Success_RebuildIndexDTO_" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate42.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.data === undefined && (missing0 = "data")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate42.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "data" ||
            key0 === "schema_version" ||
            key0 === "warnings"
          )) {
            validate42.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.data !== undefined) {
            let data0 = data.data;
            const _errs2 = errors;
            const _errs3 = errors;
            if (errors === _errs3) {
              if (data0 && typeof data0 == "object" && !Array.isArray(data0)) {
                let missing1;
                if (
                  (data0.record_count === undefined &&
                    (missing1 = "record_count")) ||
                  (data0.schema_version === undefined &&
                    (missing1 = "schema_version"))
                ) {
                  validate42.errors = [
                    {
                      instancePath: instancePath + "/data",
                      schemaPath:
                        "urn:deykit:transport:RebuildIndexDTO#/required",
                      keyword: "required",
                      params: { missingProperty: missing1 },
                      message: "must have required property '" + missing1 + "'",
                    },
                  ];
                  return false;
                } else {
                  const _errs5 = errors;
                  for (const key1 in data0) {
                    if (!(
                      key1 === "record_count" || key1 === "schema_version"
                    )) {
                      validate42.errors = [
                        {
                          instancePath: instancePath + "/data",
                          schemaPath:
                            "urn:deykit:transport:RebuildIndexDTO#/additionalProperties",
                          keyword: "additionalProperties",
                          params: { additionalProperty: key1 },
                          message: "must NOT have additional properties",
                        },
                      ];
                      return false;
                      break;
                    }
                  }
                  if (_errs5 === errors) {
                    if (data0.record_count !== undefined) {
                      let data1 = data0.record_count;
                      const _errs6 = errors;
                      if (errors === _errs6) {
                        if (typeof data1 === "string") {
                          if (!pattern5.test(data1)) {
                            validate42.errors = [
                              {
                                instancePath:
                                  instancePath + "/data/record_count",
                                schemaPath:
                                  "urn:deykit:transport:RebuildIndexDTO#/properties/record_count/pattern",
                                keyword: "pattern",
                                params: { pattern: "^(?:0|[1-9][0-9]*)$" },
                                message:
                                  'must match pattern "' +
                                  "^(?:0|[1-9][0-9]*)$" +
                                  '"',
                              },
                            ];
                            return false;
                          }
                        } else {
                          validate42.errors = [
                            {
                              instancePath: instancePath + "/data/record_count",
                              schemaPath:
                                "urn:deykit:transport:RebuildIndexDTO#/properties/record_count/type",
                              keyword: "type",
                              params: { type: "string" },
                              message: "must be string",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid2 = _errs6 === errors;
                    } else {
                      var valid2 = true;
                    }
                    if (valid2) {
                      if (data0.schema_version !== undefined) {
                        let data2 = data0.schema_version;
                        const _errs8 = errors;
                        if (!(
                          typeof data2 == "number" &&
                          !(data2 % 1) &&
                          !isNaN(data2) &&
                          isFinite(data2)
                        )) {
                          validate42.errors = [
                            {
                              instancePath:
                                instancePath + "/data/schema_version",
                              schemaPath:
                                "urn:deykit:transport:RebuildIndexDTO#/properties/schema_version/type",
                              keyword: "type",
                              params: { type: "integer" },
                              message: "must be integer",
                            },
                          ];
                          return false;
                        }
                        if (1 !== data2) {
                          validate42.errors = [
                            {
                              instancePath:
                                instancePath + "/data/schema_version",
                              schemaPath:
                                "urn:deykit:transport:RebuildIndexDTO#/properties/schema_version/const",
                              keyword: "const",
                              params: { allowedValue: 1 },
                              message: "must be equal to constant",
                            },
                          ];
                          return false;
                        }
                        var valid2 = _errs8 === errors;
                      } else {
                        var valid2 = true;
                      }
                    }
                  }
                }
              } else {
                validate42.errors = [
                  {
                    instancePath: instancePath + "/data",
                    schemaPath: "urn:deykit:transport:RebuildIndexDTO#/type",
                    keyword: "type",
                    params: { type: "object" },
                    message: "must be object",
                  },
                ];
                return false;
              }
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data3 = data.schema_version;
              const _errs10 = errors;
              if (!(
                typeof data3 == "number" &&
                !(data3 % 1) &&
                !isNaN(data3) &&
                isFinite(data3)
              )) {
                validate42.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data3) {
                validate42.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs10 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.warnings !== undefined) {
                let data4 = data.warnings;
                const _errs12 = errors;
                if (errors === _errs12) {
                  if (Array.isArray(data4)) {
                    var valid3 = true;
                    const len0 = data4.length;
                    for (let i0 = 0; i0 < len0; i0++) {
                      let data5 = data4[i0];
                      const _errs14 = errors;
                      const _errs15 = errors;
                      if (errors === _errs15) {
                        if (
                          data5 &&
                          typeof data5 == "object" &&
                          !Array.isArray(data5)
                        ) {
                          let missing2;
                          if (
                            (data5.code === undefined && (missing2 = "code")) ||
                            (data5.message === undefined &&
                              (missing2 = "message")) ||
                            (data5.schema_version === undefined &&
                              (missing2 = "schema_version"))
                          ) {
                            validate42.errors = [
                              {
                                instancePath: instancePath + "/warnings/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/required",
                                keyword: "required",
                                params: { missingProperty: missing2 },
                                message:
                                  "must have required property '" +
                                  missing2 +
                                  "'",
                              },
                            ];
                            return false;
                          } else {
                            const _errs17 = errors;
                            for (const key2 in data5) {
                              if (!(
                                key2 === "code" ||
                                key2 === "correlation_id" ||
                                key2 === "message" ||
                                key2 === "reason" ||
                                key2 === "resource_id" ||
                                key2 === "row" ||
                                key2 === "schema_version"
                              )) {
                                validate42.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/warnings/" + i0,
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/additionalProperties",
                                    keyword: "additionalProperties",
                                    params: { additionalProperty: key2 },
                                    message:
                                      "must NOT have additional properties",
                                  },
                                ];
                                return false;
                                break;
                              }
                            }
                            if (_errs17 === errors) {
                              if (data5.code !== undefined) {
                                const _errs18 = errors;
                                if (typeof data5.code !== "string") {
                                  validate42.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/code",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/code/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid5 = _errs18 === errors;
                              } else {
                                var valid5 = true;
                              }
                              if (valid5) {
                                if (data5.correlation_id !== undefined) {
                                  let data7 = data5.correlation_id;
                                  const _errs20 = errors;
                                  const _errs21 = errors;
                                  let valid6 = false;
                                  const _errs22 = errors;
                                  if (typeof data7 !== "string") {
                                    const err0 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err0];
                                    } else {
                                      vErrors.push(err0);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs22 === errors;
                                  valid6 = valid6 || _valid0;
                                  const _errs24 = errors;
                                  if (data7 !== null) {
                                    const err1 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                                      keyword: "type",
                                      params: { type: "null" },
                                      message: "must be null",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err1];
                                    } else {
                                      vErrors.push(err1);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs24 === errors;
                                  valid6 = valid6 || _valid0;
                                  if (!valid6) {
                                    const err2 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                                      keyword: "anyOf",
                                      params: {},
                                      message: "must match a schema in anyOf",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err2];
                                    } else {
                                      vErrors.push(err2);
                                    }
                                    errors++;
                                    validate42.errors = vErrors;
                                    return false;
                                  } else {
                                    errors = _errs21;
                                    if (vErrors !== null) {
                                      if (_errs21) {
                                        vErrors.length = _errs21;
                                      } else {
                                        vErrors = null;
                                      }
                                    }
                                  }
                                  var valid5 = _errs20 === errors;
                                } else {
                                  var valid5 = true;
                                }
                                if (valid5) {
                                  if (data5.message !== undefined) {
                                    const _errs26 = errors;
                                    if (typeof data5.message !== "string") {
                                      validate42.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/message",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid5 = _errs26 === errors;
                                  } else {
                                    var valid5 = true;
                                  }
                                  if (valid5) {
                                    if (data5.reason !== undefined) {
                                      let data9 = data5.reason;
                                      const _errs28 = errors;
                                      const _errs29 = errors;
                                      let valid7 = false;
                                      const _errs30 = errors;
                                      if (typeof data9 !== "string") {
                                        const err3 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err3];
                                        } else {
                                          vErrors.push(err3);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs30 === errors;
                                      valid7 = valid7 || _valid1;
                                      const _errs32 = errors;
                                      if (data9 !== null) {
                                        const err4 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                          keyword: "type",
                                          params: { type: "null" },
                                          message: "must be null",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err4];
                                        } else {
                                          vErrors.push(err4);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs32 === errors;
                                      valid7 = valid7 || _valid1;
                                      if (!valid7) {
                                        const err5 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                          keyword: "anyOf",
                                          params: {},
                                          message:
                                            "must match a schema in anyOf",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err5];
                                        } else {
                                          vErrors.push(err5);
                                        }
                                        errors++;
                                        validate42.errors = vErrors;
                                        return false;
                                      } else {
                                        errors = _errs29;
                                        if (vErrors !== null) {
                                          if (_errs29) {
                                            vErrors.length = _errs29;
                                          } else {
                                            vErrors = null;
                                          }
                                        }
                                      }
                                      var valid5 = _errs28 === errors;
                                    } else {
                                      var valid5 = true;
                                    }
                                    if (valid5) {
                                      if (data5.resource_id !== undefined) {
                                        let data10 = data5.resource_id;
                                        const _errs34 = errors;
                                        const _errs35 = errors;
                                        let valid8 = false;
                                        const _errs36 = errors;
                                        if (typeof data10 !== "string") {
                                          const err6 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err6];
                                          } else {
                                            vErrors.push(err6);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs36 === errors;
                                        valid8 = valid8 || _valid2;
                                        const _errs38 = errors;
                                        if (data10 !== null) {
                                          const err7 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                            keyword: "type",
                                            params: { type: "null" },
                                            message: "must be null",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err7];
                                          } else {
                                            vErrors.push(err7);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs38 === errors;
                                        valid8 = valid8 || _valid2;
                                        if (!valid8) {
                                          const err8 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                            keyword: "anyOf",
                                            params: {},
                                            message:
                                              "must match a schema in anyOf",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err8];
                                          } else {
                                            vErrors.push(err8);
                                          }
                                          errors++;
                                          validate42.errors = vErrors;
                                          return false;
                                        } else {
                                          errors = _errs35;
                                          if (vErrors !== null) {
                                            if (_errs35) {
                                              vErrors.length = _errs35;
                                            } else {
                                              vErrors = null;
                                            }
                                          }
                                        }
                                        var valid5 = _errs34 === errors;
                                      } else {
                                        var valid5 = true;
                                      }
                                      if (valid5) {
                                        if (data5.row !== undefined) {
                                          let data11 = data5.row;
                                          const _errs40 = errors;
                                          const _errs41 = errors;
                                          let valid9 = false;
                                          const _errs42 = errors;
                                          if (!(
                                            typeof data11 == "number" &&
                                            !(data11 % 1) &&
                                            !isNaN(data11) &&
                                            isFinite(data11)
                                          )) {
                                            const err9 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                              keyword: "type",
                                              params: { type: "integer" },
                                              message: "must be integer",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err9];
                                            } else {
                                              vErrors.push(err9);
                                            }
                                            errors++;
                                          }
                                          if (errors === _errs42) {
                                            if (
                                              typeof data11 == "number" &&
                                              isFinite(data11)
                                            ) {
                                              if (
                                                data11 > 9007199254740991 ||
                                                isNaN(data11)
                                              ) {
                                                const err10 = {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/row",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                                  keyword: "maximum",
                                                  params: {
                                                    comparison: "<=",
                                                    limit: 9007199254740991,
                                                  },
                                                  message:
                                                    "must be <= 9007199254740991",
                                                };
                                                if (vErrors === null) {
                                                  vErrors = [err10];
                                                } else {
                                                  vErrors.push(err10);
                                                }
                                                errors++;
                                              } else {
                                                if (
                                                  data11 < 0 ||
                                                  isNaN(data11)
                                                ) {
                                                  const err11 = {
                                                    instancePath:
                                                      instancePath +
                                                      "/warnings/" +
                                                      i0 +
                                                      "/row",
                                                    schemaPath:
                                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                                    keyword: "minimum",
                                                    params: {
                                                      comparison: ">=",
                                                      limit: 0,
                                                    },
                                                    message: "must be >= 0",
                                                  };
                                                  if (vErrors === null) {
                                                    vErrors = [err11];
                                                  } else {
                                                    vErrors.push(err11);
                                                  }
                                                  errors++;
                                                }
                                              }
                                            }
                                          }
                                          var _valid3 = _errs42 === errors;
                                          valid9 = valid9 || _valid3;
                                          const _errs44 = errors;
                                          if (data11 !== null) {
                                            const err12 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                              keyword: "type",
                                              params: { type: "null" },
                                              message: "must be null",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err12];
                                            } else {
                                              vErrors.push(err12);
                                            }
                                            errors++;
                                          }
                                          var _valid3 = _errs44 === errors;
                                          valid9 = valid9 || _valid3;
                                          if (!valid9) {
                                            const err13 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                              keyword: "anyOf",
                                              params: {},
                                              message:
                                                "must match a schema in anyOf",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err13];
                                            } else {
                                              vErrors.push(err13);
                                            }
                                            errors++;
                                            validate42.errors = vErrors;
                                            return false;
                                          } else {
                                            errors = _errs41;
                                            if (vErrors !== null) {
                                              if (_errs41) {
                                                vErrors.length = _errs41;
                                              } else {
                                                vErrors = null;
                                              }
                                            }
                                          }
                                          var valid5 = _errs40 === errors;
                                        } else {
                                          var valid5 = true;
                                        }
                                        if (valid5) {
                                          if (
                                            data5.schema_version !== undefined
                                          ) {
                                            let data12 = data5.schema_version;
                                            const _errs46 = errors;
                                            if (!(
                                              typeof data12 == "number" &&
                                              !(data12 % 1) &&
                                              !isNaN(data12) &&
                                              isFinite(data12)
                                            )) {
                                              validate42.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                                  keyword: "type",
                                                  params: { type: "integer" },
                                                  message: "must be integer",
                                                },
                                              ];
                                              return false;
                                            }
                                            if (1 !== data12) {
                                              validate42.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                                  keyword: "const",
                                                  params: { allowedValue: 1 },
                                                  message:
                                                    "must be equal to constant",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid5 = _errs46 === errors;
                                          } else {
                                            var valid5 = true;
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        } else {
                          validate42.errors = [
                            {
                              instancePath: instancePath + "/warnings/" + i0,
                              schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                              keyword: "type",
                              params: { type: "object" },
                              message: "must be object",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid3 = _errs14 === errors;
                      if (!valid3) {
                        break;
                      }
                    }
                  } else {
                    validate42.errors = [
                      {
                        instancePath: instancePath + "/warnings",
                        schemaPath: "#/properties/warnings/type",
                        keyword: "type",
                        params: { type: "array" },
                        message: "must be array",
                      },
                    ];
                    return false;
                  }
                }
                var valid0 = _errs12 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate42.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate42.errors = vErrors;
  return errors === 0;
}
validate42.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateSuccess_RecentProjectsDTO_ = validate43;
const schema62 = {
  $id: "urn:deykit:transport:Success_RecentProjectsDTO_",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    data: { $ref: "urn:deykit:transport:RecentProjectsDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
    warnings: {
      default: [],
      items: { $ref: "urn:deykit:transport:ErrorDTO#" },
      title: "Warnings",
      type: "array",
    },
  },
  required: ["data", "schema_version"],
  title: "Success[RecentProjectsDTO]",
  type: "object",
};
function validate43(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Success_RecentProjectsDTO_" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate43.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.data === undefined && (missing0 = "data")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate43.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "data" ||
            key0 === "schema_version" ||
            key0 === "warnings"
          )) {
            validate43.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.data !== undefined) {
            const _errs2 = errors;
            if (
              !validate34(data.data, {
                instancePath: instancePath + "/data",
                parentData: data,
                parentDataProperty: "data",
                rootData,
                dynamicAnchors,
              })
            ) {
              vErrors =
                vErrors === null
                  ? validate34.errors
                  : vErrors.concat(validate34.errors);
              errors = vErrors.length;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data1 = data.schema_version;
              const _errs3 = errors;
              if (!(
                typeof data1 == "number" &&
                !(data1 % 1) &&
                !isNaN(data1) &&
                isFinite(data1)
              )) {
                validate43.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data1) {
                validate43.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs3 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.warnings !== undefined) {
                let data2 = data.warnings;
                const _errs5 = errors;
                if (errors === _errs5) {
                  if (Array.isArray(data2)) {
                    var valid1 = true;
                    const len0 = data2.length;
                    for (let i0 = 0; i0 < len0; i0++) {
                      let data3 = data2[i0];
                      const _errs7 = errors;
                      const _errs8 = errors;
                      if (errors === _errs8) {
                        if (
                          data3 &&
                          typeof data3 == "object" &&
                          !Array.isArray(data3)
                        ) {
                          let missing1;
                          if (
                            (data3.code === undefined && (missing1 = "code")) ||
                            (data3.message === undefined &&
                              (missing1 = "message")) ||
                            (data3.schema_version === undefined &&
                              (missing1 = "schema_version"))
                          ) {
                            validate43.errors = [
                              {
                                instancePath: instancePath + "/warnings/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/required",
                                keyword: "required",
                                params: { missingProperty: missing1 },
                                message:
                                  "must have required property '" +
                                  missing1 +
                                  "'",
                              },
                            ];
                            return false;
                          } else {
                            const _errs10 = errors;
                            for (const key1 in data3) {
                              if (!(
                                key1 === "code" ||
                                key1 === "correlation_id" ||
                                key1 === "message" ||
                                key1 === "reason" ||
                                key1 === "resource_id" ||
                                key1 === "row" ||
                                key1 === "schema_version"
                              )) {
                                validate43.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/warnings/" + i0,
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/additionalProperties",
                                    keyword: "additionalProperties",
                                    params: { additionalProperty: key1 },
                                    message:
                                      "must NOT have additional properties",
                                  },
                                ];
                                return false;
                                break;
                              }
                            }
                            if (_errs10 === errors) {
                              if (data3.code !== undefined) {
                                const _errs11 = errors;
                                if (typeof data3.code !== "string") {
                                  validate43.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/code",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/code/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid3 = _errs11 === errors;
                              } else {
                                var valid3 = true;
                              }
                              if (valid3) {
                                if (data3.correlation_id !== undefined) {
                                  let data5 = data3.correlation_id;
                                  const _errs13 = errors;
                                  const _errs14 = errors;
                                  let valid4 = false;
                                  const _errs15 = errors;
                                  if (typeof data5 !== "string") {
                                    const err0 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err0];
                                    } else {
                                      vErrors.push(err0);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs15 === errors;
                                  valid4 = valid4 || _valid0;
                                  const _errs17 = errors;
                                  if (data5 !== null) {
                                    const err1 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                                      keyword: "type",
                                      params: { type: "null" },
                                      message: "must be null",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err1];
                                    } else {
                                      vErrors.push(err1);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs17 === errors;
                                  valid4 = valid4 || _valid0;
                                  if (!valid4) {
                                    const err2 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                                      keyword: "anyOf",
                                      params: {},
                                      message: "must match a schema in anyOf",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err2];
                                    } else {
                                      vErrors.push(err2);
                                    }
                                    errors++;
                                    validate43.errors = vErrors;
                                    return false;
                                  } else {
                                    errors = _errs14;
                                    if (vErrors !== null) {
                                      if (_errs14) {
                                        vErrors.length = _errs14;
                                      } else {
                                        vErrors = null;
                                      }
                                    }
                                  }
                                  var valid3 = _errs13 === errors;
                                } else {
                                  var valid3 = true;
                                }
                                if (valid3) {
                                  if (data3.message !== undefined) {
                                    const _errs19 = errors;
                                    if (typeof data3.message !== "string") {
                                      validate43.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/message",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid3 = _errs19 === errors;
                                  } else {
                                    var valid3 = true;
                                  }
                                  if (valid3) {
                                    if (data3.reason !== undefined) {
                                      let data7 = data3.reason;
                                      const _errs21 = errors;
                                      const _errs22 = errors;
                                      let valid5 = false;
                                      const _errs23 = errors;
                                      if (typeof data7 !== "string") {
                                        const err3 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err3];
                                        } else {
                                          vErrors.push(err3);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs23 === errors;
                                      valid5 = valid5 || _valid1;
                                      const _errs25 = errors;
                                      if (data7 !== null) {
                                        const err4 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                          keyword: "type",
                                          params: { type: "null" },
                                          message: "must be null",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err4];
                                        } else {
                                          vErrors.push(err4);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs25 === errors;
                                      valid5 = valid5 || _valid1;
                                      if (!valid5) {
                                        const err5 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                          keyword: "anyOf",
                                          params: {},
                                          message:
                                            "must match a schema in anyOf",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err5];
                                        } else {
                                          vErrors.push(err5);
                                        }
                                        errors++;
                                        validate43.errors = vErrors;
                                        return false;
                                      } else {
                                        errors = _errs22;
                                        if (vErrors !== null) {
                                          if (_errs22) {
                                            vErrors.length = _errs22;
                                          } else {
                                            vErrors = null;
                                          }
                                        }
                                      }
                                      var valid3 = _errs21 === errors;
                                    } else {
                                      var valid3 = true;
                                    }
                                    if (valid3) {
                                      if (data3.resource_id !== undefined) {
                                        let data8 = data3.resource_id;
                                        const _errs27 = errors;
                                        const _errs28 = errors;
                                        let valid6 = false;
                                        const _errs29 = errors;
                                        if (typeof data8 !== "string") {
                                          const err6 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err6];
                                          } else {
                                            vErrors.push(err6);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs29 === errors;
                                        valid6 = valid6 || _valid2;
                                        const _errs31 = errors;
                                        if (data8 !== null) {
                                          const err7 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                            keyword: "type",
                                            params: { type: "null" },
                                            message: "must be null",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err7];
                                          } else {
                                            vErrors.push(err7);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs31 === errors;
                                        valid6 = valid6 || _valid2;
                                        if (!valid6) {
                                          const err8 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                            keyword: "anyOf",
                                            params: {},
                                            message:
                                              "must match a schema in anyOf",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err8];
                                          } else {
                                            vErrors.push(err8);
                                          }
                                          errors++;
                                          validate43.errors = vErrors;
                                          return false;
                                        } else {
                                          errors = _errs28;
                                          if (vErrors !== null) {
                                            if (_errs28) {
                                              vErrors.length = _errs28;
                                            } else {
                                              vErrors = null;
                                            }
                                          }
                                        }
                                        var valid3 = _errs27 === errors;
                                      } else {
                                        var valid3 = true;
                                      }
                                      if (valid3) {
                                        if (data3.row !== undefined) {
                                          let data9 = data3.row;
                                          const _errs33 = errors;
                                          const _errs34 = errors;
                                          let valid7 = false;
                                          const _errs35 = errors;
                                          if (!(
                                            typeof data9 == "number" &&
                                            !(data9 % 1) &&
                                            !isNaN(data9) &&
                                            isFinite(data9)
                                          )) {
                                            const err9 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                              keyword: "type",
                                              params: { type: "integer" },
                                              message: "must be integer",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err9];
                                            } else {
                                              vErrors.push(err9);
                                            }
                                            errors++;
                                          }
                                          if (errors === _errs35) {
                                            if (
                                              typeof data9 == "number" &&
                                              isFinite(data9)
                                            ) {
                                              if (
                                                data9 > 9007199254740991 ||
                                                isNaN(data9)
                                              ) {
                                                const err10 = {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/row",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                                  keyword: "maximum",
                                                  params: {
                                                    comparison: "<=",
                                                    limit: 9007199254740991,
                                                  },
                                                  message:
                                                    "must be <= 9007199254740991",
                                                };
                                                if (vErrors === null) {
                                                  vErrors = [err10];
                                                } else {
                                                  vErrors.push(err10);
                                                }
                                                errors++;
                                              } else {
                                                if (data9 < 0 || isNaN(data9)) {
                                                  const err11 = {
                                                    instancePath:
                                                      instancePath +
                                                      "/warnings/" +
                                                      i0 +
                                                      "/row",
                                                    schemaPath:
                                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                                    keyword: "minimum",
                                                    params: {
                                                      comparison: ">=",
                                                      limit: 0,
                                                    },
                                                    message: "must be >= 0",
                                                  };
                                                  if (vErrors === null) {
                                                    vErrors = [err11];
                                                  } else {
                                                    vErrors.push(err11);
                                                  }
                                                  errors++;
                                                }
                                              }
                                            }
                                          }
                                          var _valid3 = _errs35 === errors;
                                          valid7 = valid7 || _valid3;
                                          const _errs37 = errors;
                                          if (data9 !== null) {
                                            const err12 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                              keyword: "type",
                                              params: { type: "null" },
                                              message: "must be null",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err12];
                                            } else {
                                              vErrors.push(err12);
                                            }
                                            errors++;
                                          }
                                          var _valid3 = _errs37 === errors;
                                          valid7 = valid7 || _valid3;
                                          if (!valid7) {
                                            const err13 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                              keyword: "anyOf",
                                              params: {},
                                              message:
                                                "must match a schema in anyOf",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err13];
                                            } else {
                                              vErrors.push(err13);
                                            }
                                            errors++;
                                            validate43.errors = vErrors;
                                            return false;
                                          } else {
                                            errors = _errs34;
                                            if (vErrors !== null) {
                                              if (_errs34) {
                                                vErrors.length = _errs34;
                                              } else {
                                                vErrors = null;
                                              }
                                            }
                                          }
                                          var valid3 = _errs33 === errors;
                                        } else {
                                          var valid3 = true;
                                        }
                                        if (valid3) {
                                          if (
                                            data3.schema_version !== undefined
                                          ) {
                                            let data10 = data3.schema_version;
                                            const _errs39 = errors;
                                            if (!(
                                              typeof data10 == "number" &&
                                              !(data10 % 1) &&
                                              !isNaN(data10) &&
                                              isFinite(data10)
                                            )) {
                                              validate43.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                                  keyword: "type",
                                                  params: { type: "integer" },
                                                  message: "must be integer",
                                                },
                                              ];
                                              return false;
                                            }
                                            if (1 !== data10) {
                                              validate43.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                                  keyword: "const",
                                                  params: { allowedValue: 1 },
                                                  message:
                                                    "must be equal to constant",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid3 = _errs39 === errors;
                                          } else {
                                            var valid3 = true;
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        } else {
                          validate43.errors = [
                            {
                              instancePath: instancePath + "/warnings/" + i0,
                              schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                              keyword: "type",
                              params: { type: "object" },
                              message: "must be object",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid1 = _errs7 === errors;
                      if (!valid1) {
                        break;
                      }
                    }
                  } else {
                    validate43.errors = [
                      {
                        instancePath: instancePath + "/warnings",
                        schemaPath: "#/properties/warnings/type",
                        keyword: "type",
                        params: { type: "array" },
                        message: "must be array",
                      },
                    ];
                    return false;
                  }
                }
                var valid0 = _errs5 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate43.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate43.errors = vErrors;
  return errors === 0;
}
validate43.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateSuccess_RegistrationDTO_ = validate45;
const schema64 = {
  $id: "urn:deykit:transport:Success_RegistrationDTO_",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    data: { $ref: "urn:deykit:transport:RegistrationDTO#" },
    schema_version: {
      const: 1,
      default: 1,
      title: "Schema Version",
      type: "integer",
    },
    warnings: {
      default: [],
      items: { $ref: "urn:deykit:transport:ErrorDTO#" },
      title: "Warnings",
      type: "array",
    },
  },
  required: ["data", "schema_version"],
  title: "Success[RegistrationDTO]",
  type: "object",
};
function validate45(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:Success_RegistrationDTO_" */ let vErrors =
    null;
  let errors = 0;
  const evaluated0 = validate45.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (
        (data.data === undefined && (missing0 = "data")) ||
        (data.schema_version === undefined && (missing0 = "schema_version"))
      ) {
        validate45.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(
            key0 === "data" ||
            key0 === "schema_version" ||
            key0 === "warnings"
          )) {
            validate45.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.data !== undefined) {
            const _errs2 = errors;
            if (
              !validate23(data.data, {
                instancePath: instancePath + "/data",
                parentData: data,
                parentDataProperty: "data",
                rootData,
                dynamicAnchors,
              })
            ) {
              vErrors =
                vErrors === null
                  ? validate23.errors
                  : vErrors.concat(validate23.errors);
              errors = vErrors.length;
            }
            var valid0 = _errs2 === errors;
          } else {
            var valid0 = true;
          }
          if (valid0) {
            if (data.schema_version !== undefined) {
              let data1 = data.schema_version;
              const _errs3 = errors;
              if (!(
                typeof data1 == "number" &&
                !(data1 % 1) &&
                !isNaN(data1) &&
                isFinite(data1)
              )) {
                validate45.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/type",
                    keyword: "type",
                    params: { type: "integer" },
                    message: "must be integer",
                  },
                ];
                return false;
              }
              if (1 !== data1) {
                validate45.errors = [
                  {
                    instancePath: instancePath + "/schema_version",
                    schemaPath: "#/properties/schema_version/const",
                    keyword: "const",
                    params: { allowedValue: 1 },
                    message: "must be equal to constant",
                  },
                ];
                return false;
              }
              var valid0 = _errs3 === errors;
            } else {
              var valid0 = true;
            }
            if (valid0) {
              if (data.warnings !== undefined) {
                let data2 = data.warnings;
                const _errs5 = errors;
                if (errors === _errs5) {
                  if (Array.isArray(data2)) {
                    var valid1 = true;
                    const len0 = data2.length;
                    for (let i0 = 0; i0 < len0; i0++) {
                      let data3 = data2[i0];
                      const _errs7 = errors;
                      const _errs8 = errors;
                      if (errors === _errs8) {
                        if (
                          data3 &&
                          typeof data3 == "object" &&
                          !Array.isArray(data3)
                        ) {
                          let missing1;
                          if (
                            (data3.code === undefined && (missing1 = "code")) ||
                            (data3.message === undefined &&
                              (missing1 = "message")) ||
                            (data3.schema_version === undefined &&
                              (missing1 = "schema_version"))
                          ) {
                            validate45.errors = [
                              {
                                instancePath: instancePath + "/warnings/" + i0,
                                schemaPath:
                                  "urn:deykit:transport:ErrorDTO#/required",
                                keyword: "required",
                                params: { missingProperty: missing1 },
                                message:
                                  "must have required property '" +
                                  missing1 +
                                  "'",
                              },
                            ];
                            return false;
                          } else {
                            const _errs10 = errors;
                            for (const key1 in data3) {
                              if (!(
                                key1 === "code" ||
                                key1 === "correlation_id" ||
                                key1 === "message" ||
                                key1 === "reason" ||
                                key1 === "resource_id" ||
                                key1 === "row" ||
                                key1 === "schema_version"
                              )) {
                                validate45.errors = [
                                  {
                                    instancePath:
                                      instancePath + "/warnings/" + i0,
                                    schemaPath:
                                      "urn:deykit:transport:ErrorDTO#/additionalProperties",
                                    keyword: "additionalProperties",
                                    params: { additionalProperty: key1 },
                                    message:
                                      "must NOT have additional properties",
                                  },
                                ];
                                return false;
                                break;
                              }
                            }
                            if (_errs10 === errors) {
                              if (data3.code !== undefined) {
                                const _errs11 = errors;
                                if (typeof data3.code !== "string") {
                                  validate45.errors = [
                                    {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/code",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/code/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    },
                                  ];
                                  return false;
                                }
                                var valid3 = _errs11 === errors;
                              } else {
                                var valid3 = true;
                              }
                              if (valid3) {
                                if (data3.correlation_id !== undefined) {
                                  let data5 = data3.correlation_id;
                                  const _errs13 = errors;
                                  const _errs14 = errors;
                                  let valid4 = false;
                                  const _errs15 = errors;
                                  if (typeof data5 !== "string") {
                                    const err0 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/0/type",
                                      keyword: "type",
                                      params: { type: "string" },
                                      message: "must be string",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err0];
                                    } else {
                                      vErrors.push(err0);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs15 === errors;
                                  valid4 = valid4 || _valid0;
                                  const _errs17 = errors;
                                  if (data5 !== null) {
                                    const err1 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf/1/type",
                                      keyword: "type",
                                      params: { type: "null" },
                                      message: "must be null",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err1];
                                    } else {
                                      vErrors.push(err1);
                                    }
                                    errors++;
                                  }
                                  var _valid0 = _errs17 === errors;
                                  valid4 = valid4 || _valid0;
                                  if (!valid4) {
                                    const err2 = {
                                      instancePath:
                                        instancePath +
                                        "/warnings/" +
                                        i0 +
                                        "/correlation_id",
                                      schemaPath:
                                        "urn:deykit:transport:ErrorDTO#/properties/correlation_id/anyOf",
                                      keyword: "anyOf",
                                      params: {},
                                      message: "must match a schema in anyOf",
                                    };
                                    if (vErrors === null) {
                                      vErrors = [err2];
                                    } else {
                                      vErrors.push(err2);
                                    }
                                    errors++;
                                    validate45.errors = vErrors;
                                    return false;
                                  } else {
                                    errors = _errs14;
                                    if (vErrors !== null) {
                                      if (_errs14) {
                                        vErrors.length = _errs14;
                                      } else {
                                        vErrors = null;
                                      }
                                    }
                                  }
                                  var valid3 = _errs13 === errors;
                                } else {
                                  var valid3 = true;
                                }
                                if (valid3) {
                                  if (data3.message !== undefined) {
                                    const _errs19 = errors;
                                    if (typeof data3.message !== "string") {
                                      validate45.errors = [
                                        {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/message",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/message/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        },
                                      ];
                                      return false;
                                    }
                                    var valid3 = _errs19 === errors;
                                  } else {
                                    var valid3 = true;
                                  }
                                  if (valid3) {
                                    if (data3.reason !== undefined) {
                                      let data7 = data3.reason;
                                      const _errs21 = errors;
                                      const _errs22 = errors;
                                      let valid5 = false;
                                      const _errs23 = errors;
                                      if (typeof data7 !== "string") {
                                        const err3 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/0/type",
                                          keyword: "type",
                                          params: { type: "string" },
                                          message: "must be string",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err3];
                                        } else {
                                          vErrors.push(err3);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs23 === errors;
                                      valid5 = valid5 || _valid1;
                                      const _errs25 = errors;
                                      if (data7 !== null) {
                                        const err4 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf/1/type",
                                          keyword: "type",
                                          params: { type: "null" },
                                          message: "must be null",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err4];
                                        } else {
                                          vErrors.push(err4);
                                        }
                                        errors++;
                                      }
                                      var _valid1 = _errs25 === errors;
                                      valid5 = valid5 || _valid1;
                                      if (!valid5) {
                                        const err5 = {
                                          instancePath:
                                            instancePath +
                                            "/warnings/" +
                                            i0 +
                                            "/reason",
                                          schemaPath:
                                            "urn:deykit:transport:ErrorDTO#/properties/reason/anyOf",
                                          keyword: "anyOf",
                                          params: {},
                                          message:
                                            "must match a schema in anyOf",
                                        };
                                        if (vErrors === null) {
                                          vErrors = [err5];
                                        } else {
                                          vErrors.push(err5);
                                        }
                                        errors++;
                                        validate45.errors = vErrors;
                                        return false;
                                      } else {
                                        errors = _errs22;
                                        if (vErrors !== null) {
                                          if (_errs22) {
                                            vErrors.length = _errs22;
                                          } else {
                                            vErrors = null;
                                          }
                                        }
                                      }
                                      var valid3 = _errs21 === errors;
                                    } else {
                                      var valid3 = true;
                                    }
                                    if (valid3) {
                                      if (data3.resource_id !== undefined) {
                                        let data8 = data3.resource_id;
                                        const _errs27 = errors;
                                        const _errs28 = errors;
                                        let valid6 = false;
                                        const _errs29 = errors;
                                        if (typeof data8 !== "string") {
                                          const err6 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/0/type",
                                            keyword: "type",
                                            params: { type: "string" },
                                            message: "must be string",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err6];
                                          } else {
                                            vErrors.push(err6);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs29 === errors;
                                        valid6 = valid6 || _valid2;
                                        const _errs31 = errors;
                                        if (data8 !== null) {
                                          const err7 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf/1/type",
                                            keyword: "type",
                                            params: { type: "null" },
                                            message: "must be null",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err7];
                                          } else {
                                            vErrors.push(err7);
                                          }
                                          errors++;
                                        }
                                        var _valid2 = _errs31 === errors;
                                        valid6 = valid6 || _valid2;
                                        if (!valid6) {
                                          const err8 = {
                                            instancePath:
                                              instancePath +
                                              "/warnings/" +
                                              i0 +
                                              "/resource_id",
                                            schemaPath:
                                              "urn:deykit:transport:ErrorDTO#/properties/resource_id/anyOf",
                                            keyword: "anyOf",
                                            params: {},
                                            message:
                                              "must match a schema in anyOf",
                                          };
                                          if (vErrors === null) {
                                            vErrors = [err8];
                                          } else {
                                            vErrors.push(err8);
                                          }
                                          errors++;
                                          validate45.errors = vErrors;
                                          return false;
                                        } else {
                                          errors = _errs28;
                                          if (vErrors !== null) {
                                            if (_errs28) {
                                              vErrors.length = _errs28;
                                            } else {
                                              vErrors = null;
                                            }
                                          }
                                        }
                                        var valid3 = _errs27 === errors;
                                      } else {
                                        var valid3 = true;
                                      }
                                      if (valid3) {
                                        if (data3.row !== undefined) {
                                          let data9 = data3.row;
                                          const _errs33 = errors;
                                          const _errs34 = errors;
                                          let valid7 = false;
                                          const _errs35 = errors;
                                          if (!(
                                            typeof data9 == "number" &&
                                            !(data9 % 1) &&
                                            !isNaN(data9) &&
                                            isFinite(data9)
                                          )) {
                                            const err9 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/type",
                                              keyword: "type",
                                              params: { type: "integer" },
                                              message: "must be integer",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err9];
                                            } else {
                                              vErrors.push(err9);
                                            }
                                            errors++;
                                          }
                                          if (errors === _errs35) {
                                            if (
                                              typeof data9 == "number" &&
                                              isFinite(data9)
                                            ) {
                                              if (
                                                data9 > 9007199254740991 ||
                                                isNaN(data9)
                                              ) {
                                                const err10 = {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/row",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/maximum",
                                                  keyword: "maximum",
                                                  params: {
                                                    comparison: "<=",
                                                    limit: 9007199254740991,
                                                  },
                                                  message:
                                                    "must be <= 9007199254740991",
                                                };
                                                if (vErrors === null) {
                                                  vErrors = [err10];
                                                } else {
                                                  vErrors.push(err10);
                                                }
                                                errors++;
                                              } else {
                                                if (data9 < 0 || isNaN(data9)) {
                                                  const err11 = {
                                                    instancePath:
                                                      instancePath +
                                                      "/warnings/" +
                                                      i0 +
                                                      "/row",
                                                    schemaPath:
                                                      "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/0/minimum",
                                                    keyword: "minimum",
                                                    params: {
                                                      comparison: ">=",
                                                      limit: 0,
                                                    },
                                                    message: "must be >= 0",
                                                  };
                                                  if (vErrors === null) {
                                                    vErrors = [err11];
                                                  } else {
                                                    vErrors.push(err11);
                                                  }
                                                  errors++;
                                                }
                                              }
                                            }
                                          }
                                          var _valid3 = _errs35 === errors;
                                          valid7 = valid7 || _valid3;
                                          const _errs37 = errors;
                                          if (data9 !== null) {
                                            const err12 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf/1/type",
                                              keyword: "type",
                                              params: { type: "null" },
                                              message: "must be null",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err12];
                                            } else {
                                              vErrors.push(err12);
                                            }
                                            errors++;
                                          }
                                          var _valid3 = _errs37 === errors;
                                          valid7 = valid7 || _valid3;
                                          if (!valid7) {
                                            const err13 = {
                                              instancePath:
                                                instancePath +
                                                "/warnings/" +
                                                i0 +
                                                "/row",
                                              schemaPath:
                                                "urn:deykit:transport:ErrorDTO#/properties/row/anyOf",
                                              keyword: "anyOf",
                                              params: {},
                                              message:
                                                "must match a schema in anyOf",
                                            };
                                            if (vErrors === null) {
                                              vErrors = [err13];
                                            } else {
                                              vErrors.push(err13);
                                            }
                                            errors++;
                                            validate45.errors = vErrors;
                                            return false;
                                          } else {
                                            errors = _errs34;
                                            if (vErrors !== null) {
                                              if (_errs34) {
                                                vErrors.length = _errs34;
                                              } else {
                                                vErrors = null;
                                              }
                                            }
                                          }
                                          var valid3 = _errs33 === errors;
                                        } else {
                                          var valid3 = true;
                                        }
                                        if (valid3) {
                                          if (
                                            data3.schema_version !== undefined
                                          ) {
                                            let data10 = data3.schema_version;
                                            const _errs39 = errors;
                                            if (!(
                                              typeof data10 == "number" &&
                                              !(data10 % 1) &&
                                              !isNaN(data10) &&
                                              isFinite(data10)
                                            )) {
                                              validate45.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/type",
                                                  keyword: "type",
                                                  params: { type: "integer" },
                                                  message: "must be integer",
                                                },
                                              ];
                                              return false;
                                            }
                                            if (1 !== data10) {
                                              validate45.errors = [
                                                {
                                                  instancePath:
                                                    instancePath +
                                                    "/warnings/" +
                                                    i0 +
                                                    "/schema_version",
                                                  schemaPath:
                                                    "urn:deykit:transport:ErrorDTO#/properties/schema_version/const",
                                                  keyword: "const",
                                                  params: { allowedValue: 1 },
                                                  message:
                                                    "must be equal to constant",
                                                },
                                              ];
                                              return false;
                                            }
                                            var valid3 = _errs39 === errors;
                                          } else {
                                            var valid3 = true;
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        } else {
                          validate45.errors = [
                            {
                              instancePath: instancePath + "/warnings/" + i0,
                              schemaPath: "urn:deykit:transport:ErrorDTO#/type",
                              keyword: "type",
                              params: { type: "object" },
                              message: "must be object",
                            },
                          ];
                          return false;
                        }
                      }
                      var valid1 = _errs7 === errors;
                      if (!valid1) {
                        break;
                      }
                    }
                  } else {
                    validate45.errors = [
                      {
                        instancePath: instancePath + "/warnings",
                        schemaPath: "#/properties/warnings/type",
                        keyword: "type",
                        params: { type: "array" },
                        message: "must be array",
                      },
                    ];
                    return false;
                  }
                }
                var valid0 = _errs5 === errors;
              } else {
                var valid0 = true;
              }
            }
          }
        }
      }
    } else {
      validate45.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate45.errors = vErrors;
  return errors === 0;
}
validate45.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};
exports.validateVersionRequest = validate47;
const schema66 = {
  $id: "urn:deykit:transport:VersionRequest",
  $schema: "https://json-schema.org/draft/2020-12/schema",
  additionalProperties: false,
  properties: {
    schema_version: { const: 1, title: "Schema Version", type: "integer" },
  },
  required: ["schema_version"],
  title: "VersionRequest",
  type: "object",
};
function validate47(
  data,
  {
    instancePath = "",
    parentData,
    parentDataProperty,
    rootData = data,
    dynamicAnchors = {},
  } = {},
) {
  /*# sourceURL="urn:deykit:transport:VersionRequest" */ let vErrors = null;
  let errors = 0;
  const evaluated0 = validate47.evaluated;
  if (evaluated0.dynamicProps) {
    evaluated0.props = undefined;
  }
  if (evaluated0.dynamicItems) {
    evaluated0.items = undefined;
  }
  if (errors === 0) {
    if (data && typeof data == "object" && !Array.isArray(data)) {
      let missing0;
      if (data.schema_version === undefined && (missing0 = "schema_version")) {
        validate47.errors = [
          {
            instancePath,
            schemaPath: "#/required",
            keyword: "required",
            params: { missingProperty: missing0 },
            message: "must have required property '" + missing0 + "'",
          },
        ];
        return false;
      } else {
        const _errs1 = errors;
        for (const key0 in data) {
          if (!(key0 === "schema_version")) {
            validate47.errors = [
              {
                instancePath,
                schemaPath: "#/additionalProperties",
                keyword: "additionalProperties",
                params: { additionalProperty: key0 },
                message: "must NOT have additional properties",
              },
            ];
            return false;
            break;
          }
        }
        if (_errs1 === errors) {
          if (data.schema_version !== undefined) {
            let data0 = data.schema_version;
            if (!(
              typeof data0 == "number" &&
              !(data0 % 1) &&
              !isNaN(data0) &&
              isFinite(data0)
            )) {
              validate47.errors = [
                {
                  instancePath: instancePath + "/schema_version",
                  schemaPath: "#/properties/schema_version/type",
                  keyword: "type",
                  params: { type: "integer" },
                  message: "must be integer",
                },
              ];
              return false;
            }
            if (1 !== data0) {
              validate47.errors = [
                {
                  instancePath: instancePath + "/schema_version",
                  schemaPath: "#/properties/schema_version/const",
                  keyword: "const",
                  params: { allowedValue: 1 },
                  message: "must be equal to constant",
                },
              ];
              return false;
            }
          }
        }
      }
    } else {
      validate47.errors = [
        {
          instancePath,
          schemaPath: "#/type",
          keyword: "type",
          params: { type: "object" },
          message: "must be object",
        },
      ];
      return false;
    }
  }
  validate47.errors = vErrors;
  return errors === 0;
}
validate47.evaluated = {
  props: true,
  dynamicProps: false,
  dynamicItems: false,
};

export interface paths {
  readonly "/api/v1/projects/{registration_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Show Project */
    readonly get: operations["showRegisteredProject"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/overview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Project Overview */
    readonly get: operations["projectOverview"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/rebuild-index": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Rebuild Index */
    readonly post: operations["rebuildRegisteredProjectIndex"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/validate": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Validate Project */
    readonly post: operations["validateRegisteredProject"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/demo": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Create Demo */
    readonly post: operations["createAuthoredDemo"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/recent": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Recent Projects */
    readonly get: operations["listRecentProjects"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/register": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Register Project */
    readonly post: operations["registerProject"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/session/bootstrap": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Bootstrap */
    readonly post: operations["bootstrapSession"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** BootstrapReply */
    readonly BootstrapReply: {
      /**
       * Api Version
       * @default 1
       * @constant
       */
      readonly api_version?: 1;
      /** Capability */
      readonly capability: string;
      /** Origin */
      readonly origin: string;
    };
    /** BootstrapRequest */
    readonly BootstrapRequest: {
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DemoCreateDTO */
    readonly DemoCreateDTO: {
      readonly demo: components["schemas"]["DemoSummaryDTO"];
      readonly registration: components["schemas"]["RegistrationDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DemoCreateRequest */
    readonly DemoCreateRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /** Path */
      readonly path: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DemoSummaryDTO */
    readonly DemoSummaryDTO: {
      /** Binding Count */
      readonly binding_count: string;
      /** Case Count */
      readonly case_count: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /**
       * Evidence Mode
       * @constant
       */
      readonly evidence_mode: "authored_fixture";
      /** Fixture Set Id */
      readonly fixture_set_id: string;
      /** Label Count */
      readonly label_count: string;
      /** Operation Id */
      readonly operation_id: string;
      /** Profile Id */
      readonly profile_id: string;
      /** Project Id */
      readonly project_id: string;
      /** Replayed */
      readonly replayed: boolean;
      /** Revision Id */
      readonly revision_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ErrorDTO */
    readonly ErrorDTO: {
      /** Code */
      readonly code: string;
      /**
       * Correlation Id
       * @default null
       */
      readonly correlation_id?: string | null;
      /** Message */
      readonly message: string;
      /**
       * Reason
       * @default null
       */
      readonly reason?: string | null;
      /**
       * Resource Id
       * @default null
       */
      readonly resource_id?: string | null;
      /**
       * Row
       * @default null
       */
      readonly row?: number | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** Failure */
    readonly Failure: {
      readonly error: components["schemas"]["ErrorDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ProjectOverviewDTO */
    readonly ProjectOverviewDTO: {
      /** Datasets */
      readonly datasets: readonly components["schemas"]["ResourceSummaryDTO"][];
      /** Decisions */
      readonly decisions: readonly components["schemas"]["ResourceSummaryDTO"][];
      readonly registration: components["schemas"]["RegistrationDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ProjectRecordDTO */
    readonly ProjectRecordDTO: {
      /** Created At */
      readonly created_at: string;
      /** Default Provider Id */
      readonly default_provider_id?: string | null;
      /** Id */
      readonly id: string;
      /** Name */
      readonly name: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RebuildIndexDTO */
    readonly RebuildIndexDTO: {
      /** Record Count */
      readonly record_count: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RecentProjectDTO */
    readonly RecentProjectDTO: {
      /** Id */
      readonly id: string;
      /** Last Opened At */
      readonly last_opened_at: string;
      /** Name */
      readonly name: string;
      /** Path */
      readonly path: string;
      /** Project Id */
      readonly project_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RecentProjectsDTO */
    readonly RecentProjectsDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["RecentProjectDTO"][];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RegisterProjectRequest */
    readonly RegisterProjectRequest: {
      /**
       * Action
       * @enum {string}
       */
      readonly action: "open" | "create";
      /** Name */
      readonly name?: string | null;
      /** Operation Id */
      readonly operation_id: string;
      /** Path */
      readonly path: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RegistrationDTO */
    readonly RegistrationDTO: {
      /** Demo */
      readonly demo?: null;
      /** Execution Active */
      readonly execution_active: boolean;
      /** Path */
      readonly path: string;
      readonly project: components["schemas"]["ProjectRecordDTO"];
      /** Project Etag */
      readonly project_etag: string;
      /** Record Count */
      readonly record_count: string;
      /** Registration Id */
      readonly registration_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ResourceSummaryDTO */
    readonly ResourceSummaryDTO: {
      /** Id */
      readonly id: string;
      /** Name */
      readonly name: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** Success[BootstrapReply] */
    readonly Success_BootstrapReply_: {
      readonly data: components["schemas"]["BootstrapReply"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Warnings
       * @default []
       */
      readonly warnings?: readonly components["schemas"]["ErrorDTO"][];
    };
    /** Success[DemoCreateDTO] */
    readonly Success_DemoCreateDTO_: {
      readonly data: components["schemas"]["DemoCreateDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Warnings
       * @default []
       */
      readonly warnings?: readonly components["schemas"]["ErrorDTO"][];
    };
    /** Success[ProjectOverviewDTO] */
    readonly Success_ProjectOverviewDTO_: {
      readonly data: components["schemas"]["ProjectOverviewDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Warnings
       * @default []
       */
      readonly warnings?: readonly components["schemas"]["ErrorDTO"][];
    };
    /** Success[RebuildIndexDTO] */
    readonly Success_RebuildIndexDTO_: {
      readonly data: components["schemas"]["RebuildIndexDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Warnings
       * @default []
       */
      readonly warnings?: readonly components["schemas"]["ErrorDTO"][];
    };
    /** Success[RecentProjectsDTO] */
    readonly Success_RecentProjectsDTO_: {
      readonly data: components["schemas"]["RecentProjectsDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Warnings
       * @default []
       */
      readonly warnings?: readonly components["schemas"]["ErrorDTO"][];
    };
    /** Success[RegistrationDTO] */
    readonly Success_RegistrationDTO_: {
      readonly data: components["schemas"]["RegistrationDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Warnings
       * @default []
       */
      readonly warnings?: readonly components["schemas"]["ErrorDTO"][];
    };
    /** VersionRequest */
    readonly VersionRequest: {
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  readonly showRegisteredProject: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody?: never;
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RegistrationDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly projectOverview: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody?: never;
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ProjectOverviewDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly rebuildRegisteredProjectIndex: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["VersionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RebuildIndexDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly validateRegisteredProject: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["VersionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RegistrationDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createAuthoredDemo: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DemoCreateRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DemoCreateDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listRecentProjects: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly requestBody?: never;
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RecentProjectsDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly registerProject: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RegisterProjectRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RegistrationDTO_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly bootstrapSession: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["BootstrapRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_BootstrapReply_"];
        };
      };
      /** @description Safe structured failure */
      readonly 400: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 403: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 404: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 405: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 413: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 414: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 415: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 422: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 431: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
      /** @description Safe structured failure */
      readonly 500: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
}

export type ApiOperationId = keyof typeof operationMetadata;
type OperationIdOfKind<
  K extends ApiOperationId,
  Kind extends ApiOperationMetadata["success"]["kind"],
> = {
  [Id in K]: (typeof operationMetadata)[Id]["success"]["kind"] extends Kind
    ? Id
    : never;
}[K];
export type ApiJsonOperationId = OperationIdOfKind<ApiOperationId, "json">;
export type ApiDownloadOperationId = OperationIdOfKind<
  ApiOperationId,
  "report-download"
>;

export interface ApiJsonSuccess {
  readonly kind: "json";
  readonly validators: Readonly<Partial<Record<"200" | "202", string>>>;
}
export interface ApiReportDownloadSuccess {
  readonly kind: "report-download";
  readonly status: 200;
  readonly formatParameter: "format";
  readonly reportIdParameter: "report_id";
  readonly maxBytes: 8388608;
  readonly formats: {
    readonly json: {
      readonly contentType: "application/octet-stream";
      readonly extension: "json";
    };
    readonly markdown: {
      readonly contentType: "text/plain; charset=utf-8";
      readonly extension: "md";
    };
  };
}

export interface ApiOperationMetadata {
  readonly method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD";
  readonly path: string;
  readonly pathParams: readonly string[];
  readonly queryParams: readonly string[];
  readonly bodyValidator: string | null;
  readonly bodyRequired: boolean;
  readonly success: ApiJsonSuccess | ApiReportDownloadSuccess;
}

export const operationMetadata = {
  addAnnotation: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/annotations",
    pathParams: ["registration_id", "run_id"],
    queryParams: [],
    bodyValidator: "validateAddAnnotationRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_AnnotationDTO_",
      },
    },
  },
  addRegression: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateAddRegressionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RegressionDTO_",
      },
    },
  },
  add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases",
    pathParams: ["registration_id", "dataset_id"],
    queryParams: [],
    bodyValidator: "validateCaseInputRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_CaseMutationDTO_",
      },
    },
  },
  archiveDecision: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/archive",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateDecisionETagRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_Versioned_DecisionRecord__",
      },
    },
  },
  archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/archive",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateDatasetChangeRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_DatasetDTO_",
        },
      },
    },
  attachEnvironmentCredential: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-environment",
    pathParams: ["registration_id", "profile_id"],
    queryParams: [],
    bodyValidator: "validateEnvironmentCredentialRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProviderMutationDTO_",
      },
    },
  },
  batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/batch",
      pathParams: ["registration_id", "decision_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateLabelBatchRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_LabelBatchDTO_",
        },
      },
    },
  cancelCheck: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/checks/{group_id}/cancel",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: "validateGroupCancelRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_GroupProgressDTO_",
      },
    },
  },
  cancelChoiceOrder: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/diagnostics/{group_id}/cancel",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: "validateGroupCancelRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_GroupProgressDTO_",
      },
    },
  },
  cancelRun: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/cancel",
    pathParams: ["registration_id", "run_id"],
    queryParams: [],
    bodyValidator: "validateRunCancelRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RunProgressDTO_",
      },
    },
  },
  commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/imports/commit",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateImportCommitRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_ImportCommitDTO_",
        },
      },
    },
  commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/splits/commit",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateSplitCommitRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_SplitCommitDTO_",
        },
      },
    },
  configureProviderProfile: {
    method: "PUT",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}",
    pathParams: ["registration_id", "profile_id"],
    queryParams: [],
    bodyValidator: "validateProviderProfileRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProviderMutationDTO_",
      },
    },
  },
  createAuthoredDemo: {
    method: "POST",
    path: "/api/v1/projects/demo",
    pathParams: [],
    queryParams: [],
    bodyValidator: "validateDemoCreateRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DemoCreateDTO_",
      },
    },
  },
  createComparison: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/comparisons",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateCreateComparisonRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ComparisonDTO_",
      },
    },
  },
  createDataset: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/datasets",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateDatasetCreateRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DatasetDTO_",
      },
    },
  },
  createDecision: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateDecisionCreateRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DecisionDTO_",
      },
    },
  },
  createEvaluation: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/evaluations",
    pathParams: ["registration_id", "run_id"],
    queryParams: [],
    bodyValidator: "validateEvaluateRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_EvaluationDTO_",
      },
    },
  },
  createFixtureSet: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/fixtures",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateFixtureCreateRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_FixtureCreatedDTO_",
      },
    },
  },
  createReport: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/reports",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateCreateReportRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ReportDTO_",
      },
    },
  },
  delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete:
    {
      method: "DELETE",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}",
      pathParams: ["registration_id", "dataset_id", "case_id"],
      queryParams: [],
      bodyValidator: "validateCaseChangeRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_CaseMutationDTO_",
        },
      },
    },
  diffDecisionRevisions: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/diff",
    pathParams: ["registration_id", "decision_id"],
    queryParams: ["after", "before"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DefinitionDiffDTO_",
      },
    },
  },
  downloadReport: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/reports/{report_id}/download",
    pathParams: ["registration_id", "report_id"],
    queryParams: ["format"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "report-download",
      status: 200,
      formatParameter: "format",
      reportIdParameter: "report_id",
      maxBytes: 8388608,
      formats: {
        json: {
          contentType: "application/octet-stream",
          extension: "json",
        },
        markdown: {
          contentType: "text/plain; charset=utf-8",
          extension: "md",
        },
      },
    },
  },
  edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put:
    {
      method: "PUT",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}",
      pathParams: ["registration_id", "dataset_id", "case_id"],
      queryParams: [],
      bodyValidator: "validateCaseEditRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_CaseMutationDTO_",
        },
      },
    },
  encodeTextInput: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/authoring/text-input",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateTextInputRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_EncodedInputV1_",
      },
    },
  },
  forgetProviderCredential: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-forget",
    pathParams: ["registration_id", "profile_id"],
    queryParams: [],
    bodyValidator: "validateProviderETagRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProviderMutationDTO_",
      },
    },
  },
  label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get:
    {
      method: "GET",
      path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/{case_id}/history",
      pathParams: ["registration_id", "decision_id", "dataset_id", "case_id"],
      queryParams: ["question_id"],
      bodyValidator: null,
      bodyRequired: false,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_LabelHistoryDTO_",
        },
      },
    },
  latestDecisionRevision: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/latest-revision",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RevisionDTO_",
      },
    },
  },
  listAnnotations: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/annotations",
    pathParams: ["registration_id", "run_id"],
    queryParams: ["case_id", "cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_AnnotationPageDTO_",
      },
    },
  },
  listCheckSnapshots: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/checks/{group_id}/snapshots",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_tuple_SnapshotMetadataDTO__________",
      },
    },
  },
  listChoiceOrderSnapshots: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/diagnostics/{group_id}/snapshots",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_tuple_SnapshotMetadataDTO__________",
      },
    },
  },
  listComparisons: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/comparisons",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ComparisonPageDTO_",
      },
    },
  },
  listDecisionRevisions: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/revisions",
    pathParams: ["registration_id", "decision_id"],
    queryParams: ["cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RevisionPageDTO_",
      },
    },
  },
  listDecisions: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "include_archived", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DecisionPageDTO_",
      },
    },
  },
  listEvaluations: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/evaluations",
    pathParams: ["registration_id", "run_id"],
    queryParams: ["cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_EvaluationPageDTO_",
      },
    },
  },
  listFixtureSets: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/fixtures",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_FixturePageDTO_",
      },
    },
  },
  listProviderModels: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}/models",
    pathParams: ["registration_id", "profile_id"],
    queryParams: ["timeout_seconds"],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ModelListDTO_",
      },
    },
  },
  listProviderProfiles: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/providers",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProviderPageDTO_",
      },
    },
  },
  listRecentProjects: {
    method: "GET",
    path: "/api/v1/projects/recent",
    pathParams: [],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RecentProjectsDTO_",
      },
    },
  },
  listRegressions: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RegressionPageDTO_",
      },
    },
  },
  listReports: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/reports",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ReportPageDTO_",
      },
    },
  },
  listResults: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/results",
    pathParams: ["registration_id", "run_id"],
    queryParams: [
      "assessment_filter",
      "cursor",
      "evaluation_id",
      "expected_label_snapshot_id",
      "expected_result_snapshot_id",
      "limit",
      "split",
      "status",
      "tag",
    ],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ResultPageDTO_",
      },
    },
  },
  listRuns: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/runs",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "decision_id", "limit", "status"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RunPageDTO_",
      },
    },
  },
  list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get:
    {
      method: "GET",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: ["cursor", "group_id", "limit", "split", "tag"],
      bodyValidator: null,
      bodyRequired: false,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_CasePageDTO_",
        },
      },
    },
  list_datasets_api_v1_projects__registration_id__datasets_get: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/datasets",
    pathParams: ["registration_id"],
    queryParams: ["cursor", "include_archived", "limit"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DatasetPageDTO_",
      },
    },
  },
  list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get:
    {
      method: "GET",
      path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels",
      pathParams: ["registration_id", "decision_id", "dataset_id"],
      queryParams: ["cursor", "limit", "status"],
      bodyValidator: null,
      bodyRequired: false,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_LabelPageDTO_",
        },
      },
    },
  patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch: {
    method: "PATCH",
    path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}",
    pathParams: ["registration_id", "dataset_id"],
    queryParams: [],
    bodyValidator: "validateDatasetPatchRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DatasetDTO_",
      },
    },
  },
  previewCaseSelection: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/selection-preview",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateSelectionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_SelectionDTO_",
      },
    },
  },
  previewCheckResume: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/checks/{group_id}/resume-preview",
    pathParams: ["registration_id", "group_id"],
    queryParams: ["retry_unknown"],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_GroupResumePreviewDTO_",
      },
    },
  },
  previewChoiceOrder: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/diagnostics/choice-order/preview",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateChoiceOrderPreviewRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_GroupPreviewDTO_",
      },
    },
  },
  previewChoiceOrderResume: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/diagnostics/{group_id}/resume-preview",
    pathParams: ["registration_id", "group_id"],
    queryParams: ["retry_unknown"],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_GroupResumePreviewDTO_",
      },
    },
  },
  previewRegressionCheck: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/checks/preview",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateCheckPreviewRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_GroupPreviewDTO_",
      },
    },
  },
  previewRun: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/preview",
    pathParams: ["registration_id"],
    queryParams: ["include_request"],
    bodyValidator: "validateRunPreviewRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RunPreviewDTO_",
      },
    },
  },
  previewRunResume: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/resume-preview",
    pathParams: ["registration_id", "run_id"],
    queryParams: ["max_attempts", "retry_unknown"],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RunResumePreviewDTO_",
      },
    },
  },
  preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/imports/preview",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateImportPreviewRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_ImportPreviewDTO_",
        },
      },
    },
  preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/splits/preview",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateSplitPreviewRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_SplitPreviewDTO_",
        },
      },
    },
  projectCaseInput: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/authoring/case-input-projection",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateCaseInputProjectionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_CaseInputProjectionV1_",
      },
    },
  },
  projectDecisionEditor: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/editor-projection",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateEditorProjectionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_EditorProjectionV1_",
      },
    },
  },
  projectImportMapping: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/authoring/mapping-projection",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateMappingProjectionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_MappingProjectionV1_",
      },
    },
  },
  projectInputSchema: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/authoring/schema-projection",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateSchemaProjectionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_SchemaProjectionV1_",
      },
    },
  },
  projectOverview: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/overview",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProjectOverviewDTO_",
      },
    },
  },
  providerCredentialStatus: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-status",
    pathParams: ["registration_id", "profile_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_CredentialStatusDTO_",
      },
    },
  },
  readAnnotation: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/annotations/{annotation_id}",
    pathParams: ["registration_id", "annotation_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_AnnotationDTO_",
      },
    },
  },
  readCheck: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/checks/{group_id}",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_CheckViewDTO_",
      },
    },
  },
  readCheckSnapshot: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/checks/{group_id}/snapshots/{snapshot_id}",
    pathParams: ["registration_id", "group_id", "snapshot_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_CheckSnapshotDetailDTO_",
      },
    },
  },
  readChoiceOrder: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/diagnostics/{group_id}",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DiagnosticViewDTO_",
      },
    },
  },
  readChoiceOrderSnapshot: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/diagnostics/{group_id}/snapshots/{snapshot_id}",
    pathParams: ["registration_id", "group_id", "snapshot_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DiagnosticSnapshotDetailDTO_",
      },
    },
  },
  readComparison: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/comparisons/{comparison_id}",
    pathParams: ["registration_id", "comparison_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ComparisonDTO_",
      },
    },
  },
  readDecision: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DecisionDTO_",
      },
    },
  },
  readDecisionRevision: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/revisions/{revision_id}",
    pathParams: ["registration_id", "decision_id", "revision_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RevisionDTO_",
      },
    },
  },
  readEvaluation: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/evaluations/{evaluation_id}",
    pathParams: ["registration_id", "evaluation_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_EvaluationDTO_",
      },
    },
  },
  readFixtureSet: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/fixtures/{fixture_set_id}",
    pathParams: ["registration_id", "fixture_set_id"],
    queryParams: ["include_requests"],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_FixtureSummaryDTO_",
      },
    },
  },
  readProviderProfile: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}",
    pathParams: ["registration_id", "profile_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProviderProfileDTO_",
      },
    },
  },
  readReport: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/reports/{report_id}",
    pathParams: ["registration_id", "report_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ReportDTO_",
      },
    },
  },
  readResult: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/results/{case_id}",
    pathParams: ["registration_id", "run_id", "case_id"],
    queryParams: [
      "evaluation_id",
      "expected_label_snapshot_id",
      "expected_result_snapshot_id",
      "include_attempts",
      "include_input",
      "include_request",
      "include_response",
    ],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_CaseDetailDTO_",
      },
    },
  },
  readRun: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}",
    pathParams: ["registration_id", "run_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RunProgressDTO_",
      },
    },
  },
  read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get:
    {
      method: "GET",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}",
      pathParams: ["registration_id", "dataset_id", "case_id"],
      queryParams: [],
      bodyValidator: null,
      bodyRequired: false,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_CaseReadDTO_",
        },
      },
    },
  read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}",
    pathParams: ["registration_id", "dataset_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DatasetDTO_",
      },
    },
  },
  read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get:
    {
      method: "GET",
      path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/{case_id}",
      pathParams: ["registration_id", "decision_id", "dataset_id", "case_id"],
      queryParams: ["question_id"],
      bodyValidator: null,
      bodyRequired: false,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_LabelViewDTO_",
        },
      },
    },
  rebuildRegisteredProjectIndex: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/rebuild-index",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RebuildIndexDTO_",
      },
    },
  },
  reevaluateRun: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/reevaluations",
    pathParams: ["registration_id", "run_id"],
    queryParams: [],
    bodyValidator: "validateReevaluateRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_EvaluationDTO_",
      },
    },
  },
  registerProject: {
    method: "POST",
    path: "/api/v1/projects/register",
    pathParams: [],
    queryParams: [],
    bodyValidator: "validateRegisterProjectRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RegistrationDTO_",
      },
    },
  },
  removeRegression: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions/{regression_id}/remove",
    pathParams: ["registration_id", "decision_id", "regression_id"],
    queryParams: [],
    bodyValidator: "validateRemoveRegressionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RegressionDTO_",
      },
    },
  },
  renameDecision: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/rename",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateRenameDecisionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_Versioned_DecisionRecord__",
      },
    },
  },
  restoreDecision: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/restore",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateDecisionETagRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_Versioned_DecisionRecord__",
      },
    },
  },
  restoreDecisionRevisionToDraft: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/restore-revision",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateRestoreRevisionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_Versioned_DecisionDraft__",
      },
    },
  },
  restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post:
    {
      method: "POST",
      path: "/api/v1/projects/{registration_id}/datasets/{dataset_id}/restore",
      pathParams: ["registration_id", "dataset_id"],
      queryParams: [],
      bodyValidator: "validateDatasetChangeRequest",
      bodyRequired: true,
      success: {
        kind: "json",
        validators: {
          "200": "validateSuccess_DatasetDTO_",
        },
      },
    },
  resumeCheck: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/checks/{group_id}/resume",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: "validateGroupResumeRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "202": "validateSuccess_GroupAcceptedDTO_",
      },
    },
  },
  resumeChoiceOrder: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/diagnostics/{group_id}/resume",
    pathParams: ["registration_id", "group_id"],
    queryParams: [],
    bodyValidator: "validateGroupResumeRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "202": "validateSuccess_GroupAcceptedDTO_",
      },
    },
  },
  resumeRun: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs/{run_id}/resume",
    pathParams: ["registration_id", "run_id"],
    queryParams: [],
    bodyValidator: "validateRunResumeRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "202": "validateSuccess_RunAcceptedDTO_",
      },
    },
  },
  saveDecisionRevision: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/revisions",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateSaveRevisionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RevisionDTO_",
      },
    },
  },
  setOSStoreCredential: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-os-store",
    pathParams: ["registration_id", "profile_id"],
    queryParams: [],
    bodyValidator: "validateOSCredentialRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ProviderMutationDTO_",
      },
    },
  },
  showRegisteredProject: {
    method: "GET",
    path: "/api/v1/projects/{registration_id}",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: null,
    bodyRequired: false,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RegistrationDTO_",
      },
    },
  },
  startChoiceOrder: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/diagnostics/choice-order",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateStartChoiceOrderRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "202": "validateSuccess_GroupAcceptedDTO_",
      },
    },
  },
  startRegressionCheck: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/checks",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateStartCheckRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "202": "validateSuccess_GroupAcceptedDTO_",
      },
    },
  },
  startRun: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/runs",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateStartRunRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "202": "validateSuccess_RunAcceptedDTO_",
      },
    },
  },
  transformDecisionEditor: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/editor-transform",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateEditorTransformRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_DraftTransformReviewDTO_",
      },
    },
  },
  transformImportMapping: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/authoring/mapping-transform",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateMappingTransformRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_MappingTransformV1_",
      },
    },
  },
  updateDecisionDraft: {
    method: "PUT",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/draft",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateDraftRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_Versioned_DecisionDraft__",
      },
    },
  },
  validateDecision: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/decisions/{decision_id}/validate",
    pathParams: ["registration_id", "decision_id"],
    queryParams: [],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_ValidationDTO_",
      },
    },
  },
  validateRegisteredProject: {
    method: "POST",
    path: "/api/v1/projects/{registration_id}/validate",
    pathParams: ["registration_id"],
    queryParams: [],
    bodyValidator: "validateVersionRequest",
    bodyRequired: true,
    success: {
      kind: "json",
      validators: {
        "200": "validateSuccess_RegistrationDTO_",
      },
    },
  },
} as const satisfies Record<string, ApiOperationMetadata>;

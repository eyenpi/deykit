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
  readonly "/api/v1/projects/{registration_id}/annotations/{annotation_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Annotation */
    readonly get: operations["readAnnotation"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/authoring/case-input-projection": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Case Input Projection */
    readonly post: operations["projectCaseInput"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/authoring/mapping-projection": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Mapping Projection */
    readonly post: operations["projectImportMapping"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/authoring/mapping-transform": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Mapping Transform */
    readonly post: operations["transformImportMapping"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/authoring/schema-projection": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Schema Projection */
    readonly post: operations["projectInputSchema"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/authoring/text-input": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Text Input */
    readonly post: operations["encodeTextInput"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/checks": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Start Check */
    readonly post: operations["startRegressionCheck"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/checks/{group_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Check */
    readonly get: operations["readCheck"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/checks/{group_id}/cancel": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Cancel Check */
    readonly post: operations["cancelCheck"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/checks/{group_id}/resume": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Resume Check */
    readonly post: operations["resumeCheck"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/checks/{group_id}/resume-preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Preview Check Resume */
    readonly post: operations["previewCheckResume"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/checks/preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Check Preview */
    readonly post: operations["previewRegressionCheck"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/comparisons": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Comparisons */
    readonly get: operations["listComparisons"];
    readonly put?: never;
    /** Create Comparison */
    readonly post: operations["createComparison"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/comparisons/{comparison_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Comparison */
    readonly get: operations["readComparison"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Datasets */
    readonly get: operations["list_datasets_api_v1_projects__registration_id__datasets_get"];
    readonly put?: never;
    /** Create Dataset */
    readonly post: operations["createDataset"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Dataset */
    readonly get: operations["read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    /** Patch Dataset */
    readonly patch: operations["patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch"];
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/archive": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Archive Dataset */
    readonly post: operations["archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Cases */
    readonly get: operations["list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get"];
    readonly put?: never;
    /** Add Case */
    readonly post: operations["add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Case */
    readonly get: operations["read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get"];
    /** Edit Case */
    readonly put: operations["edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put"];
    readonly post?: never;
    /** Delete Case */
    readonly delete: operations["delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete"];
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/imports/commit": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Commit Import */
    readonly post: operations["commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/imports/preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Preview Import */
    readonly post: operations["preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/restore": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Restore Dataset */
    readonly post: operations["restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/splits/commit": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Commit Split */
    readonly post: operations["commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/datasets/{dataset_id}/splits/preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Preview Split */
    readonly post: operations["preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Decisions */
    readonly get: operations["listDecisions"];
    readonly put?: never;
    /** Create Decision */
    readonly post: operations["createDecision"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Decision */
    readonly get: operations["readDecision"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/archive": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Archive Decision */
    readonly post: operations["archiveDecision"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Labels */
    readonly get: operations["list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/{case_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Label */
    readonly get: operations["read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/{case_id}/history": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Label History */
    readonly get: operations["label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/batch": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Batch Labels */
    readonly post: operations["batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/diff": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Diff Decisions */
    readonly get: operations["diffDecisionRevisions"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/draft": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    /** Update Draft */
    readonly put: operations["updateDecisionDraft"];
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/editor-projection": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Editor Projection */
    readonly post: operations["projectDecisionEditor"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/editor-transform": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Editor Transform */
    readonly post: operations["transformDecisionEditor"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/latest-revision": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Latest Revision */
    readonly get: operations["latestDecisionRevision"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Regressions */
    readonly get: operations["listRegressions"];
    readonly put?: never;
    /** Add Regression */
    readonly post: operations["addRegression"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions/{regression_id}/remove": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Remove Regression */
    readonly post: operations["removeRegression"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/rename": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Rename Decision */
    readonly post: operations["renameDecision"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/restore": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Restore Decision */
    readonly post: operations["restoreDecision"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/restore-revision": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Restore Revision */
    readonly post: operations["restoreDecisionRevisionToDraft"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/revisions": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Revision History */
    readonly get: operations["listDecisionRevisions"];
    readonly put?: never;
    /** Save Revision */
    readonly post: operations["saveDecisionRevision"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/revisions/{revision_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Revision */
    readonly get: operations["readDecisionRevision"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/selection-preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Selection Preview */
    readonly post: operations["previewCaseSelection"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/decisions/{decision_id}/validate": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Validate Decision */
    readonly post: operations["validateDecision"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/diagnostics/{group_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Choice Order */
    readonly get: operations["readChoiceOrder"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/diagnostics/{group_id}/cancel": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Cancel Choice Order */
    readonly post: operations["cancelChoiceOrder"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/diagnostics/{group_id}/resume": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Resume Choice Order */
    readonly post: operations["resumeChoiceOrder"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/diagnostics/{group_id}/resume-preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Preview Choice Order Resume */
    readonly post: operations["previewChoiceOrderResume"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/diagnostics/choice-order": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Start Choice Order */
    readonly post: operations["startChoiceOrder"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/diagnostics/choice-order/preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Choice Order Preview */
    readonly post: operations["previewChoiceOrder"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/evaluations/{evaluation_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Evaluation */
    readonly get: operations["readEvaluation"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/fixtures": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Fixtures */
    readonly get: operations["listFixtureSets"];
    readonly put?: never;
    /** Create Fixture */
    readonly post: operations["createFixtureSet"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/fixtures/{fixture_set_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Fixture */
    readonly get: operations["readFixtureSet"];
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
  readonly "/api/v1/projects/{registration_id}/providers": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Providers */
    readonly get: operations["listProviderProfiles"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/providers/{profile_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Provider */
    readonly get: operations["readProviderProfile"];
    /** Configure Provider */
    readonly put: operations["configureProviderProfile"];
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-environment": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Attach Environment */
    readonly post: operations["attachEnvironmentCredential"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-forget": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Forget Credential */
    readonly post: operations["forgetProviderCredential"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-os-store": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Set Os Credential */
    readonly post: operations["setOSStoreCredential"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/providers/{profile_id}/credential-status": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Credential Status */
    readonly get: operations["providerCredentialStatus"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/providers/{profile_id}/models": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** List Models */
    readonly post: operations["listProviderModels"];
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
  readonly "/api/v1/projects/{registration_id}/reports": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Reports */
    readonly get: operations["listReports"];
    readonly put?: never;
    /** Create Report */
    readonly post: operations["createReport"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/reports/{report_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Report */
    readonly get: operations["readReport"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/reports/{report_id}/download": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Download Report */
    readonly get: operations["downloadReport"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Runs */
    readonly get: operations["listRuns"];
    readonly put?: never;
    /** Start Run */
    readonly post: operations["startRun"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Run */
    readonly get: operations["readRun"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/annotations": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Annotations */
    readonly get: operations["listAnnotations"];
    readonly put?: never;
    /** Add Annotation */
    readonly post: operations["addAnnotation"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/cancel": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Cancel Run */
    readonly post: operations["cancelRun"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/evaluations": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Evaluations */
    readonly get: operations["listEvaluations"];
    readonly put?: never;
    /** Evaluate */
    readonly post: operations["createEvaluation"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/reevaluations": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Reevaluate */
    readonly post: operations["reevaluateRun"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/results": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** List Results */
    readonly get: operations["listResults"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/results/{case_id}": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    /** Read Result */
    readonly get: operations["readResult"];
    readonly put?: never;
    readonly post?: never;
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/resume": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Resume Run */
    readonly post: operations["resumeRun"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/{run_id}/resume-preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Preview Run Resume */
    readonly post: operations["previewRunResume"];
    readonly delete?: never;
    readonly options?: never;
    readonly head?: never;
    readonly patch?: never;
    readonly trace?: never;
  };
  readonly "/api/v1/projects/{registration_id}/runs/preview": {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path?: never;
      readonly cookie?: never;
    };
    readonly get?: never;
    readonly put?: never;
    /** Run Preview */
    readonly post: operations["previewRun"];
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
    /** AddAnnotationRequest */
    readonly AddAnnotationRequest: {
      /** Case Id */
      readonly case_id: string;
      /** Note */
      readonly note: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** AddOption */
    readonly AddOption: {
      /** Description */
      readonly description: string | null;
      /** Id */
      readonly id: string;
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "add_option";
      /** Name */
      readonly name: string;
    };
    /** AddRegressionRequest */
    readonly AddRegressionRequest: {
      /** Acceptable Option Ids */
      readonly acceptable_option_ids: readonly string[];
      /** Case Id */
      readonly case_id: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Provenance
       * @default human
       * @enum {string}
       */
      readonly provenance?:
        "human" | "authored_fixture" | "imported_unknown" | "model_generated";
      /** Reason */
      readonly reason: string;
      /** Result Snapshot Id */
      readonly result_snapshot_id?: string | null;
      /** Run Id */
      readonly run_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** AnnotationDTO */
    readonly AnnotationDTO: {
      /** Annotation Id */
      readonly annotation_id: string;
      /** Case Id */
      readonly case_id: string;
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Note */
      readonly note: string;
      /** Replayed */
      readonly replayed: boolean;
      /** Run Id */
      readonly run_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** AnnotationPageDTO */
    readonly AnnotationPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["AnnotationDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /** Total */
      readonly total: string;
    };
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
    /** CaseChangeRequest */
    readonly CaseChangeRequest: {
      /** Expected Case Etag */
      readonly expected_case_etag: string;
      /** Expected Dataset Etag */
      readonly expected_dataset_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CaseDetailDTO */
    readonly CaseDetailDTO: {
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Source */
      readonly source: {
        readonly [key: string]: unknown;
      };
    };
    /** CaseDTO */
    readonly CaseDTO: {
      /** Etag */
      readonly etag: string;
      readonly record: components["schemas"]["CaseRecord"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CaseEditRequest */
    readonly CaseEditRequest: {
      /**
       * Derived From
       * @default []
       */
      readonly derived_from?: readonly string[];
      /** Expected Case Etag */
      readonly expected_case_etag: string;
      /** Expected Dataset Etag */
      readonly expected_dataset_etag: string;
      /** Group Id */
      readonly group_id?: string | null;
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Source */
      readonly input_source: string;
      /**
       * Metadata Source
       * @default {}
       */
      readonly metadata_source?: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Split
       * @default development
       * @enum {string}
       */
      readonly split?: "development" | "calibration" | "test";
      /**
       * Tags
       * @default []
       */
      readonly tags?: readonly string[];
    };
    /** CaseInputProjectionRequest */
    readonly CaseInputProjectionRequest: {
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Source */
      readonly input_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CaseInputProjectionV1 */
    readonly CaseInputProjectionV1: {
      /** Form Unavailable Reason */
      readonly form_unavailable_reason: string | null;
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Source */
      readonly input_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string | null;
      /** Text Value */
      readonly text_value: string | null;
    };
    /** CaseInputRequest */
    readonly CaseInputRequest: {
      /** Case Id */
      readonly case_id?: string | null;
      /**
       * Derived From
       * @default []
       */
      readonly derived_from?: readonly string[];
      /** Expected Dataset Etag */
      readonly expected_dataset_etag: string;
      /** Group Id */
      readonly group_id?: string | null;
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Source */
      readonly input_source: string;
      /**
       * Metadata Source
       * @default {}
       */
      readonly metadata_source?: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Split
       * @default development
       * @enum {string}
       */
      readonly split?: "development" | "calibration" | "test";
      /**
       * Tags
       * @default []
       */
      readonly tags?: readonly string[];
    };
    /** CaseMutationDTO */
    readonly CaseMutationDTO: {
      readonly case: components["schemas"]["CaseDTO"] | null;
      /** Cleared Label Ids */
      readonly cleared_label_ids: readonly string[];
      readonly dataset: components["schemas"]["DatasetDTO"];
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CasePageDTO */
    readonly CasePageDTO: {
      /** Dataset Etag */
      readonly dataset_etag: string;
      /** Items */
      readonly items: readonly components["schemas"]["CaseDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** CaseReadDTO */
    readonly CaseReadDTO: {
      readonly case: components["schemas"]["CaseDTO"];
      /** Dataset Etag */
      readonly dataset_etag: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CaseRecord */
    readonly CaseRecord: {
      /** Dataset Id */
      readonly dataset_id: string;
      /**
       * Derived From
       * @default []
       */
      readonly derived_from?: readonly string[];
      /** Group Id */
      readonly group_id?: string | null;
      /**
       * Hash Format
       * @default deykit-json-v1
       * @constant
       */
      readonly hash_format?: "deykit-json-v1";
      /** Id */
      readonly id: string;
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Source */
      readonly input_source: string;
      /**
       * Metadata Source
       * @default {}
       */
      readonly metadata_source?: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Split
       * @default development
       * @enum {string}
       */
      readonly split?: "development" | "calibration" | "test";
      /**
       * Tags
       * @default []
       */
      readonly tags?: readonly string[];
    };
    /** CheckPreviewRequest */
    readonly CheckPreviewRequest: {
      readonly request: components["schemas"]["CheckRequestDTO"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CheckRequestDTO */
    readonly CheckRequestDTO: {
      /** Decision Id */
      readonly decision_id: string;
      /** Fixture Set Id */
      readonly fixture_set_id?: string | null;
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      /** Provider Id */
      readonly provider_id?: string | null;
      /**
       * Regression Ids
       * @default []
       */
      readonly regression_ids?: readonly string[];
      /** Revision Id */
      readonly revision_id?: string | null;
      /**
       * @default {
       *       "concurrency": 2,
       *       "deadline_seconds": 600,
       *       "max_attempts": 100,
       *       "max_retries_per_case": 1,
       *       "timeout_seconds": 60
       *     }
       */
      readonly settings?: components["schemas"]["ExecutionSettingsRequestDTO"];
    };
    /** CheckViewDTO */
    readonly CheckViewDTO: {
      /**
       * Baseline Unavailable
       * @constant
       */
      readonly baseline_unavailable: "frozen_regression_selection";
      /** Cases */
      readonly cases: readonly {
        readonly [key: string]: unknown;
      }[];
      /**
       * Exit Code
       * @enum {integer}
       */
      readonly exit_code: 0 | 3 | 4 | 5;
      /** Expectation Failures */
      readonly expectation_failures: string;
      readonly group: components["schemas"]["GroupProgressDTO"];
    };
    /** ChoiceDefinition */
    readonly ChoiceDefinition: {
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Schema Source */
      readonly input_schema_source?: string | null;
      /** Questions */
      readonly questions: readonly components["schemas"]["ChoiceQuestion"][];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Selected Fields
       * @default []
       */
      readonly selected_fields?: readonly string[];
    };
    /** ChoiceOption */
    readonly ChoiceOption: {
      /** Description */
      readonly description?: string | null;
      /** Id */
      readonly id: string;
      /** Name */
      readonly name: string;
    };
    /** ChoiceOrderPreviewRequest */
    readonly ChoiceOrderPreviewRequest: {
      readonly request: components["schemas"]["ChoiceOrderRequestDTO"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ChoiceOrderRequestDTO */
    readonly ChoiceOrderRequestDTO: {
      /**
       * Orders
       * @default 4
       */
      readonly orders?: number;
      readonly run: components["schemas"]["RunRequestDTO"];
      /**
       * Seed
       * @default 0
       */
      readonly seed?: string;
    };
    /** ChoiceQuestion */
    readonly ChoiceQuestion: {
      /** Id */
      readonly id: string;
      /** Instructions */
      readonly instructions: string;
      /**
       * Kind
       * @default choice
       * @constant
       */
      readonly kind?: "choice";
      /** Options */
      readonly options: readonly components["schemas"]["ChoiceOption"][];
    };
    /** ComparisonDTO */
    readonly ComparisonDTO: {
      /** Comparison Id */
      readonly comparison_id: string;
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Left Evaluation Id */
      readonly left_evaluation_id: string;
      /** Left Result Snapshot Id */
      readonly left_result_snapshot_id: string;
      /** Outcomes */
      readonly outcomes: {
        readonly [key: string]: unknown;
      };
      /** Replayed */
      readonly replayed: boolean;
      /** Right Evaluation Id */
      readonly right_evaluation_id: string;
      /** Right Result Snapshot Id */
      readonly right_result_snapshot_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ComparisonPageDTO */
    readonly ComparisonPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["ComparisonDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /** Total */
      readonly total: string;
    };
    /** CreateComparisonRequest */
    readonly CreateComparisonRequest: {
      /** Left Evaluation Id */
      readonly left_evaluation_id: string;
      /** Operation Id */
      readonly operation_id: string;
      /** Right Evaluation Id */
      readonly right_evaluation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** CreateReportRequest */
    readonly CreateReportRequest: {
      /** Evaluation Id */
      readonly evaluation_id?: string | null;
      /** Group Snapshot Id */
      readonly group_snapshot_id?: string | null;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * @default {
       *       "inputs": false,
       *       "requests": false,
       *       "responses": false
       *     }
       */
      readonly raw?: components["schemas"]["RawChoices"];
      /** Result Snapshot Id */
      readonly result_snapshot_id?: string | null;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Target Id */
      readonly target_id: string;
      /** Target Kind */
      readonly target_kind?:
        ("run" | "evaluation" | "comparison" | "diagnostic" | "check") | null;
    };
    /** CredentialStatusDTO */
    readonly CredentialStatusDTO: {
      /** Available */
      readonly available: boolean;
      /** Configured */
      readonly configured: boolean;
      /** Kind */
      readonly kind: ("env" | "keyring") | null;
      /** Profile Id */
      readonly profile_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DatasetChangeRequest */
    readonly DatasetChangeRequest: {
      /** Expected Etag */
      readonly expected_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DatasetCreateRequest */
    readonly DatasetCreateRequest: {
      /** Dataset Id */
      readonly dataset_id?: string | null;
      /**
       * Metadata Source
       * @default {}
       */
      readonly metadata_source?: string;
      /** Name */
      readonly name: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DatasetDTO */
    readonly DatasetDTO: {
      /** Etag */
      readonly etag: string;
      readonly record: components["schemas"]["DatasetRecord"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DatasetPageDTO */
    readonly DatasetPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["DatasetDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** DatasetPatchRequest */
    readonly DatasetPatchRequest: {
      /** Expected Etag */
      readonly expected_etag: string;
      /** Metadata Source */
      readonly metadata_source?: string | null;
      /** Name */
      readonly name?: string | null;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DatasetRecord */
    readonly DatasetRecord: {
      /**
       * Archived
       * @default false
       */
      readonly archived?: boolean;
      /** Created At */
      readonly created_at: string;
      /** Id */
      readonly id: string;
      /**
       * Metadata Source
       * @default {}
       */
      readonly metadata_source?: string;
      /** Name */
      readonly name: string;
      /** Revision Id */
      readonly revision_id?: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DatasetSnapshot */
    readonly DatasetSnapshot: {
      /** Cases */
      readonly cases: readonly components["schemas"]["CaseRecord"][];
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /**
       * Hash Format
       * @default deykit-json-v1
       * @constant
       */
      readonly hash_format?: "deykit-json-v1";
      /** Id */
      readonly id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Selection Source
       * @default {}
       */
      readonly selection_source?: string;
    };
    /** DecisionCreateRequest */
    readonly DecisionCreateRequest: {
      /** Decision Id */
      readonly decision_id: string;
      /** Editor Source */
      readonly editor_source: string;
      /** Name */
      readonly name: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /**
     * DecisionDraft
     * @description Syntax-invalid/incomplete editor content is saved without claiming it is runnable.
     */
    readonly DecisionDraft: {
      /** Base Revision Id */
      readonly base_revision_id?: string | null;
      /** Decision Id */
      readonly decision_id: string;
      /** Editor Source */
      readonly editor_source: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Updated At */
      readonly updated_at: string;
    };
    /** DecisionDTO */
    readonly DecisionDTO: {
      readonly decision: components["schemas"]["Versioned_DecisionRecord_"];
      readonly draft: components["schemas"]["Versioned_DecisionDraft_"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DecisionETagRequest */
    readonly DecisionETagRequest: {
      /** Expected Etag */
      readonly expected_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DecisionPageDTO */
    readonly DecisionPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["DecisionDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** DecisionRecord */
    readonly DecisionRecord: {
      /**
       * Archived
       * @default false
       */
      readonly archived?: boolean;
      /** Id */
      readonly id: string;
      /** Latest Revision Id */
      readonly latest_revision_id?: string | null;
      /** Name */
      readonly name: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DecisionRevision */
    readonly DecisionRevision: {
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Decision Id */
      readonly decision_id: string;
      readonly definition: components["schemas"]["ChoiceDefinition"];
      /**
       * Hash Format
       * @default deykit-json-v1
       * @constant
       */
      readonly hash_format?: "deykit-json-v1";
      /** Id */
      readonly id: string;
      /**
       * Note
       * @default
       */
      readonly note?: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DefinitionDiffDTO */
    readonly DefinitionDiffDTO: {
      /** Added Option Ids */
      readonly added_option_ids: readonly string[];
      /** After Hash */
      readonly after_hash: string;
      /** Before Hash */
      readonly before_hash: string;
      /** Changed Option Ids */
      readonly changed_option_ids: readonly string[];
      /** Incompatible References */
      readonly incompatible_references: readonly components["schemas"]["IncompatibleReference"][];
      /** Input Changed */
      readonly input_changed: boolean;
      /** Option Order Changed */
      readonly option_order_changed: boolean;
      /** Question Changed */
      readonly question_changed: boolean;
      /** Removed Option Ids */
      readonly removed_option_ids: readonly string[];
      /**
       * Schema Version
       * @default 1
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
    /** DescribeOption */
    readonly DescribeOption: {
      /** Description */
      readonly description: string | null;
      /** Id */
      readonly id: string;
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "describe_option";
    };
    /** DiagnosticViewDTO */
    readonly DiagnosticViewDTO: {
      /**
       * Exit Code
       * @enum {integer}
       */
      readonly exit_code: 0 | 3 | 4;
      readonly group: components["schemas"]["GroupProgressDTO"];
      /** Summary */
      readonly summary: {
        readonly [key: string]: unknown;
      } | null;
    };
    /** DraftRequest */
    readonly DraftRequest: {
      /** Editor Source */
      readonly editor_source: string;
      /** Expected Etag */
      readonly expected_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** DraftTransformReviewDTO */
    readonly DraftTransformReviewDTO: {
      /** Incompatible References */
      readonly incompatible_references:
        readonly components["schemas"]["IncompatibleReference"][] | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      readonly transform: components["schemas"]["EditorTransformV1"];
    };
    /** EditorFormV1 */
    readonly EditorFormV1: {
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Schema Source */
      readonly input_schema_source: string | null;
      /** Instructions */
      readonly instructions: string;
      /** Options */
      readonly options: readonly components["schemas"]["EditorOptionV1"][];
      /** Question Id */
      readonly question_id: string;
      /** Selected Fields */
      readonly selected_fields: readonly string[];
    };
    /** EditorOptionV1 */
    readonly EditorOptionV1: {
      /** Description */
      readonly description: string | null;
      /** Id */
      readonly id: string;
      /** Name */
      readonly name: string;
    };
    /** EditorProjectionRequest */
    readonly EditorProjectionRequest: {
      /** Editor Source */
      readonly editor_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** EditorProjectionV1 */
    readonly EditorProjectionV1: {
      /** Editor Source */
      readonly editor_source: string;
      readonly form: components["schemas"]["EditorFormV1"] | null;
      /** Form Unavailable Reason */
      readonly form_unavailable_reason: string | null;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string | null;
      /** Validation Advice */
      readonly validation_advice: readonly components["schemas"]["ValidationAdviceV1"][];
    };
    /** EditorTransformRequest */
    readonly EditorTransformRequest: {
      /** Edit */
      readonly edit:
        | components["schemas"]["SetInstructions"]
        | components["schemas"]["AddOption"]
        | components["schemas"]["RemoveOption"]
        | components["schemas"]["RenameOption"]
        | components["schemas"]["DescribeOption"]
        | components["schemas"]["ReorderOptions"]
        | components["schemas"]["SetInputKind"]
        | components["schemas"]["SetSelectedFields"]
        | components["schemas"]["ReplaceSchema"]
        | components["schemas"]["SchemaField"]
        | components["schemas"]["RemoveSchemaField"];
      /** Editor Source */
      readonly editor_source: string;
      /** Expected Draft Etag */
      readonly expected_draft_etag: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** EditorTransformV1 */
    readonly EditorTransformV1: {
      /** Editor Source */
      readonly editor_source: string;
      /** Original Source Hash */
      readonly original_source_hash: string;
      readonly projection: components["schemas"]["EditorProjectionV1"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string;
      /** Validation Advice */
      readonly validation_advice: readonly components["schemas"]["ValidationAdviceV1"][];
    };
    /** EncodedInputV1 */
    readonly EncodedInputV1: {
      /** Input Source */
      readonly input_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string;
    };
    /** EnvironmentCredentialRequest */
    readonly EnvironmentCredentialRequest: {
      /** Environment Name */
      readonly environment_name: string;
      /** Expected Etag */
      readonly expected_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
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
    /** EvaluateRequest */
    readonly EvaluateRequest: {
      /** Label Snapshot Id */
      readonly label_snapshot_id?: string | null;
      /**
       * Mode
       * @default original
       * @enum {string}
       */
      readonly mode?: "original" | "saved_answer_reevaluation";
      /** Operation Id */
      readonly operation_id: string;
      /** Result Snapshot Id */
      readonly result_snapshot_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** EvaluationDTO */
    readonly EvaluationDTO: {
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Evaluation Id */
      readonly evaluation_id: string;
      /** Execution Operation Id */
      readonly execution_operation_id: string | null;
      /** Label Snapshot Id */
      readonly label_snapshot_id: string;
      /** Metrics */
      readonly metrics: {
        readonly [key: string]: unknown;
      };
      /** Metrics Source */
      readonly metrics_source: string;
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "original" | "saved_answer_reevaluation";
      /** Replayed */
      readonly replayed: boolean;
      /** Result Snapshot Id */
      readonly result_snapshot_id: string;
      /** Run Id */
      readonly run_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** EvaluationPageDTO */
    readonly EvaluationPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["EvaluationDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /** Total */
      readonly total: string;
    };
    /** ExecutionSettingsRequestDTO */
    readonly ExecutionSettingsRequestDTO: {
      /**
       * Concurrency
       * @default 2
       */
      readonly concurrency?: number;
      /**
       * Deadline Seconds
       * @default 600
       */
      readonly deadline_seconds?: number;
      /**
       * Max Attempts
       * @default 100
       */
      readonly max_attempts?: number;
      /**
       * Max Retries Per Case
       * @default 1
       */
      readonly max_retries_per_case?: number;
      /**
       * Timeout Seconds
       * @default 60
       */
      readonly timeout_seconds?: number;
    };
    /** ExecutionSettingsViewDTO */
    readonly ExecutionSettingsViewDTO: {
      /** Concurrency */
      readonly concurrency: string;
      /** Deadline Seconds */
      readonly deadline_seconds: string;
      /** Max Attempts */
      readonly max_attempts: string;
      /** Max Retries Per Case */
      readonly max_retries_per_case: string;
      /** Timeout Seconds */
      readonly timeout_seconds: string;
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
      /** @default null */
      readonly selection?: components["schemas"]["SelectionDetails"] | null;
    };
    /** FixtureBindingDTO */
    readonly FixtureBindingDTO: {
      /** Answer Option Id */
      readonly answer_option_id: string | null;
      /** Answer Question Id */
      readonly answer_question_id: string | null;
      /** Case Id */
      readonly case_id: string;
      /** Compiler */
      readonly compiler: string;
      /** Compiler Version */
      readonly compiler_version: string;
      /** Error Code */
      readonly error_code: string | null;
      /** Error Reason */
      readonly error_reason: string | null;
      /** Id */
      readonly id: string;
      /** Model Identity */
      readonly model_identity: string;
      /** Request Hash */
      readonly request_hash: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** FixtureCreatedDTO */
    readonly FixtureCreatedDTO: {
      readonly fixture: components["schemas"]["FixtureSummaryDTO"];
      /** Operation Id */
      readonly operation_id: string;
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** FixtureCreateRequest */
    readonly FixtureCreateRequest: {
      /** Binding Sources */
      readonly binding_sources: readonly string[];
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Fixture Set Id */
      readonly fixture_set_id: string;
      /** Model Identity */
      readonly model_identity: string;
      /** Name */
      readonly name: string;
      /**
       * Note
       * @default
       */
      readonly note?: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** FixturePageDTO */
    readonly FixturePageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["FixtureSummaryDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** FixtureSummaryDTO */
    readonly FixtureSummaryDTO: {
      /** Binding Count */
      readonly binding_count: string;
      /** Bindings */
      readonly bindings: readonly components["schemas"]["FixtureBindingDTO"][];
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Etag */
      readonly etag?: string | null;
      /** Id */
      readonly id: string;
      /** Model Identity */
      readonly model_identity: string;
      /** Name */
      readonly name: string;
      /** Requests */
      readonly requests: readonly string[];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** GroupAcceptedDTO */
    readonly GroupAcceptedDTO: {
      /** Group Id */
      readonly group_id: string;
      /**
       * Kind
       * @enum {string}
       */
      readonly kind: "choice_order" | "regression_check";
      /** Member Run Ids */
      readonly member_run_ids: readonly string[];
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      /** Operation Id */
      readonly operation_id: string;
      /** Progress Path */
      readonly progress_path: string;
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Segment Id */
      readonly segment_id: string;
    };
    /** GroupCancelRequest */
    readonly GroupCancelRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** GroupMemberPreviewDTO */
    readonly GroupMemberPreviewDTO: {
      readonly identity: components["schemas"]["MemberIdentityDTO"];
      readonly preview: components["schemas"]["RunPreviewSummaryDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** GroupMemberResumePreviewDTO */
    readonly GroupMemberResumePreviewDTO: {
      /** Planned Case Ids */
      readonly planned_case_ids: readonly string[];
      /** Run Id */
      readonly run_id: string;
    };
    /** GroupPreviewDTO */
    readonly GroupPreviewDTO: {
      /** Algorithm */
      readonly algorithm: string | null;
      /** Attempt Limit */
      readonly attempt_limit: string;
      /** Deadline Seconds */
      readonly deadline_seconds: string;
      /** Dry Run */
      readonly dry_run: boolean;
      /** Independent Case Count */
      readonly independent_case_count: string;
      /** Initial Requests */
      readonly initial_requests: string;
      /**
       * Kind
       * @enum {string}
       */
      readonly kind: "choice_order" | "regression_check";
      /** Members */
      readonly members: readonly components["schemas"]["GroupMemberPreviewDTO"][];
      /** Review Context Hash */
      readonly review_context_hash: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Seed */
      readonly seed: string | null;
    };
    /** GroupProgressDTO */
    readonly GroupProgressDTO: {
      /** Algorithm */
      readonly algorithm: string | null;
      /** Attempt Limit */
      readonly attempt_limit: string;
      /** Attempts Remaining */
      readonly attempts_remaining: string;
      /** Attempts Used */
      readonly attempts_used: string;
      /** Group Id */
      readonly group_id: string;
      /** Independent Case Count */
      readonly independent_case_count: string;
      /** Initial Requests */
      readonly initial_requests: string;
      /**
       * Kind
       * @enum {string}
       */
      readonly kind: "choice_order" | "regression_check";
      /** Members */
      readonly members: readonly components["schemas"]["RunProgressDTO"][];
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Seed */
      readonly seed: string | null;
      /** Snapshot Id */
      readonly snapshot_id: string | null;
    };
    /** GroupResumePreviewDTO */
    readonly GroupResumePreviewDTO: {
      /** Dry Run */
      readonly dry_run: boolean;
      readonly group: components["schemas"]["GroupProgressDTO"];
      /** Members */
      readonly members: readonly components["schemas"]["GroupMemberResumePreviewDTO"][];
      /** Proposed Attempt Limit */
      readonly proposed_attempt_limit: string;
      /** Retry Unknown */
      readonly retry_unknown: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Segment Ids */
      readonly segment_ids: readonly string[];
    };
    /** GroupResumeRequest */
    readonly GroupResumeRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Retry Unknown
       * @default false
       */
      readonly retry_unknown?: boolean;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ImportCommitDTO */
    readonly ImportCommitDTO: {
      readonly dataset: components["schemas"]["DatasetDTO"];
      /** Duplicate Rows */
      readonly duplicate_rows: readonly components["schemas"]["ImportRowDTO"][];
      /** Exclusions */
      readonly exclusions: readonly components["schemas"]["ImportRowDTO"][];
      /** Imported Case Ids */
      readonly imported_case_ids: readonly string[];
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ImportCommitRequest */
    readonly ImportCommitRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /** Preview Document Source */
      readonly preview_document_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Skip Invalid
       * @default false
       */
      readonly skip_invalid?: boolean;
    };
    /** ImportMapping */
    readonly ImportMapping: {
      /** Expected Column */
      readonly expected_column?: string | null;
      /**
       * Expected Parse Json
       * @default false
       */
      readonly expected_parse_json?: boolean;
      /**
       * Fields
       * @default []
       */
      readonly fields?: readonly components["schemas"]["InputField"][];
      /** Group Column */
      readonly group_column?: string | null;
      /** Id Column */
      readonly id_column?: string | null;
      /** Input Column */
      readonly input_column?: string | null;
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /**
       * Input Parse Json
       * @default false
       */
      readonly input_parse_json?: boolean;
      /** Metadata Column */
      readonly metadata_column?: string | null;
      /**
       * Metadata Parse Json
       * @default false
       */
      readonly metadata_parse_json?: boolean;
      /**
       * Option Aliases
       * @default []
       */
      readonly option_aliases?: readonly components["schemas"]["OptionAlias"][];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Split Column */
      readonly split_column?: string | null;
      /** Tags Column */
      readonly tags_column?: string | null;
      /**
       * Tags Parse Json
       * @default false
       */
      readonly tags_parse_json?: boolean;
    };
    /** ImportPreviewDTO */
    readonly ImportPreviewDTO: {
      readonly preview: components["schemas"]["ImportPreviewRecordDTO"];
      /** Preview Document Source */
      readonly preview_document_source: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Would Import */
      readonly would_import: string;
    };
    /** ImportPreviewRecordDTO */
    readonly ImportPreviewRecordDTO: {
      /** Context Hash */
      readonly context_hash: string;
      /** Dataset Etag */
      readonly dataset_etag: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string | null;
      /** Decision Selector */
      readonly decision_selector: string;
      /**
       * Format
       * @enum {string}
       */
      readonly format: "csv" | "jsonl";
      readonly mapping: components["schemas"]["ImportMapping"];
      /** Mapping Hash */
      readonly mapping_hash: string;
      /** Preview Hash */
      readonly preview_hash: string;
      /** Question Id */
      readonly question_id: string | null;
      /** Rows */
      readonly rows: readonly components["schemas"]["ImportRowDTO"][];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string;
      /** Source Text */
      readonly source_text: string;
    };
    /** ImportPreviewRequest */
    readonly ImportPreviewRequest: {
      /** Decision Id */
      readonly decision_id?: string | null;
      /**
       * Decision Selector
       * @default draft
       */
      readonly decision_selector?: string;
      /**
       * Format
       * @enum {string}
       */
      readonly format: "csv" | "jsonl";
      /** Mapping Source */
      readonly mapping_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Text */
      readonly source_text: string;
    };
    /** ImportRowDTO */
    readonly ImportRowDTO: {
      /** Acceptable Option Ids */
      readonly acceptable_option_ids: readonly string[];
      readonly case: components["schemas"]["CaseRecord"] | null;
      /** Duplicate Input Ids */
      readonly duplicate_input_ids: readonly string[];
      /** Errors */
      readonly errors: readonly components["schemas"]["ServiceErrorDTO"][];
      /** Row */
      readonly row: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Source Line */
      readonly source_line: string;
    };
    /** IncompatibleReference */
    readonly IncompatibleReference: {
      /** Case Id */
      readonly case_id: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Kind */
      readonly kind: string;
      /** Missing Option Ids */
      readonly missing_option_ids: readonly string[];
      /** Question Id */
      readonly question_id: string;
      /** Resource Id */
      readonly resource_id: string;
    };
    /** InputField */
    readonly InputField: {
      /**
       * Parse Json
       * @default false
       */
      readonly parse_json?: boolean;
      /** Source */
      readonly source: string;
      /** Target */
      readonly target: string;
    };
    /** LabelBatchDTO */
    readonly LabelBatchDTO: {
      /** Changes */
      readonly changes: readonly components["schemas"]["LabelChange"][];
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** LabelBatchRequest */
    readonly LabelBatchRequest: {
      /** Edits */
      readonly edits: readonly components["schemas"]["LabelEditDTO"][];
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** LabelChange */
    readonly LabelChange: {
      /**
       * Action
       * @enum {string}
       */
      readonly action: "set" | "clear" | "dispute" | "resolve";
      /** Case Id */
      readonly case_id: string;
      /** Created At */
      readonly created_at: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Id */
      readonly id: string;
      readonly label: components["schemas"]["LabelRecord"] | null;
      /** Operation Id */
      readonly operation_id: string;
      /** Question Id */
      readonly question_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** LabelEditDTO */
    readonly LabelEditDTO: {
      /**
       * Acceptable Option Ids
       * @default []
       */
      readonly acceptable_option_ids?: readonly string[];
      /**
       * Action
       * @enum {string}
       */
      readonly action: "set" | "clear" | "dispute" | "resolve";
      /** Note */
      readonly note?: string | null;
      /** Provenance */
      readonly provenance?:
        | (
            | "human"
            | "authored_fixture"
            | "imported_unknown"
            | "model_generated"
          )
        | null;
      readonly review: components["schemas"]["LabelReviewDTO"];
    };
    /** LabelHistoryDTO */
    readonly LabelHistoryDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["LabelChange"][];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** LabelPageDTO */
    readonly LabelPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["LabelViewDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** LabelRecord */
    readonly LabelRecord: {
      /** Acceptable Option Ids */
      readonly acceptable_option_ids: readonly string[];
      /** Case Id */
      readonly case_id: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /**
       * Hash Format
       * @default deykit-json-v1
       * @constant
       */
      readonly hash_format?: "deykit-json-v1";
      /** Id */
      readonly id: string;
      /** Input Hash */
      readonly input_hash: string;
      /**
       * Note
       * @default
       */
      readonly note?: string;
      /**
       * Provenance
       * @enum {string}
       */
      readonly provenance:
        "human" | "authored_fixture" | "imported_unknown" | "model_generated";
      /** Question Id */
      readonly question_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Status
       * @default active
       * @enum {string}
       */
      readonly status?: "active" | "disputed";
      /** Updated At */
      readonly updated_at: string;
    };
    /** LabelReviewDTO */
    readonly LabelReviewDTO: {
      /** Case Id */
      readonly case_id: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Etag */
      readonly decision_etag: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Draft Etag */
      readonly draft_etag: string;
      /** Input Hash */
      readonly input_hash: string;
      /** Label Etag */
      readonly label_etag: string | null;
      /** Question Id */
      readonly question_id: string;
    };
    /** LabelViewDTO */
    readonly LabelViewDTO: {
      readonly case: components["schemas"]["CaseRecord"];
      readonly definition: components["schemas"]["ChoiceDefinition"];
      readonly label: components["schemas"]["LabelRecord"] | null;
      /** Missing Option Ids */
      readonly missing_option_ids: readonly string[];
      /** Reasons */
      readonly reasons: readonly ("disputed" | "stale" | "incompatible")[];
      readonly review: components["schemas"]["LabelReviewDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Status
       * @enum {string}
       */
      readonly status: "unlabelled" | "excluded" | "applicable";
    };
    /** MappingAliasFormV1 */
    readonly MappingAliasFormV1: {
      /** Option Id */
      readonly option_id: string;
      /** Value */
      readonly value: string;
    };
    /** MappingFieldFormV1 */
    readonly MappingFieldFormV1: {
      /** Parse Json */
      readonly parse_json: boolean;
      /** Source */
      readonly source: string;
      /** Target */
      readonly target: string;
    };
    /** MappingFormV1 */
    readonly MappingFormV1: {
      /** Expected Column */
      readonly expected_column: string | null;
      /** Expected Parse Json */
      readonly expected_parse_json: boolean;
      /** Fields */
      readonly fields: readonly components["schemas"]["MappingFieldFormV1"][];
      /** Group Column */
      readonly group_column: string | null;
      /** Id Column */
      readonly id_column: string | null;
      /** Input Column */
      readonly input_column: string | null;
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /** Input Parse Json */
      readonly input_parse_json: boolean;
      /** Metadata Column */
      readonly metadata_column: string | null;
      /** Metadata Parse Json */
      readonly metadata_parse_json: boolean;
      /** Option Aliases */
      readonly option_aliases: readonly components["schemas"]["MappingAliasFormV1"][];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Split Column */
      readonly split_column: string | null;
      /** Tags Column */
      readonly tags_column: string | null;
      /** Tags Parse Json */
      readonly tags_parse_json: boolean;
    };
    /** MappingProjectionRequest */
    readonly MappingProjectionRequest: {
      /** Mapping Source */
      readonly mapping_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** MappingProjectionV1 */
    readonly MappingProjectionV1: {
      readonly form: components["schemas"]["MappingFormV1"] | null;
      /** Form Unavailable Reason */
      readonly form_unavailable_reason: string | null;
      /** Mapping Source */
      readonly mapping_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string | null;
      /** Validation Advice */
      readonly validation_advice: readonly components["schemas"]["ValidationAdviceV1"][];
    };
    /** MappingTransformRequest */
    readonly MappingTransformRequest: {
      /** Edit */
      readonly edit:
        | components["schemas"]["SetMappingField"]
        | components["schemas"]["ReplaceMappingFields"]
        | components["schemas"]["ReplaceOptionAliases"];
      /** Mapping Source */
      readonly mapping_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** MappingTransformV1 */
    readonly MappingTransformV1: {
      /** Mapping Source */
      readonly mapping_source: string;
      /** Original Source Hash */
      readonly original_source_hash: string;
      readonly projection: components["schemas"]["MappingProjectionV1"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string;
      /** Validation Advice */
      readonly validation_advice: readonly components["schemas"]["ValidationAdviceV1"][];
    };
    /** MemberIdentityDTO */
    readonly MemberIdentityDTO: {
      /** Option Order */
      readonly option_order: readonly string[] | null;
      /** Requests */
      readonly requests: readonly components["schemas"]["RequestIdentityDTO"][];
      /** Run Id */
      readonly run_id: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ModelDTO */
    readonly ModelDTO: {
      /** Description */
      readonly description: string;
      /** Name */
      readonly name: string;
      /** Release Date */
      readonly release_date: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ModelListDTO */
    readonly ModelListDTO: {
      /**
       * Inference Calls
       * @constant
       */
      readonly inference_calls: 0;
      /** Models */
      readonly models: readonly components["schemas"]["ModelDTO"][];
      /**
       * Network Check
       * @constant
       */
      readonly network_check: true;
      /** Profile Id */
      readonly profile_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** OptionAlias */
    readonly OptionAlias: {
      /** Option Id */
      readonly option_id: string;
      /** Value */
      readonly value: string;
    };
    /** OSCredentialRequest */
    readonly OSCredentialRequest: {
      /** Credential Value */
      readonly credential_value: string;
      /** Expected Etag */
      readonly expected_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
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
    /** ProviderETagRequest */
    readonly ProviderETagRequest: {
      /** Expected Etag */
      readonly expected_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ProviderMutationDTO */
    readonly ProviderMutationDTO: {
      /** Operation Id */
      readonly operation_id: string;
      readonly profile: components["schemas"]["ProviderProfileDTO"];
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ProviderPageDTO */
    readonly ProviderPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["ProviderProfileDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** ProviderProfileDTO */
    readonly ProviderProfileDTO: {
      /** Adapter */
      readonly adapter: string;
      /** Compiler Id */
      readonly compiler_id: string;
      /** Compiler Version */
      readonly compiler_version: string;
      /** Credential Configured */
      readonly credential_configured: boolean;
      /** Credential Kind */
      readonly credential_kind: ("env" | "keyring") | null;
      /** Destination */
      readonly destination: string;
      /** Etag */
      readonly etag: string;
      /**
       * Evidence Mode
       * @enum {string}
       */
      readonly evidence_mode: "authored_fixture" | "live";
      /** Id */
      readonly id: string;
      /** Input Kinds */
      readonly input_kinds: readonly ("text" | "json")[];
      /** Max Options */
      readonly max_options: number;
      /**
       * Question Kind
       * @constant
       */
      readonly question_kind: "choice";
      /** Requested Model */
      readonly requested_model: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ProviderProfileRequest */
    readonly ProviderProfileRequest: {
      /** Adapter */
      readonly adapter: string;
      /** Credential Ref */
      readonly credential_ref?: string | null;
      /** Destination */
      readonly destination: string;
      /** Expected Etag */
      readonly expected_etag?: string | null;
      /** Operation Id */
      readonly operation_id: string;
      /** Profile Id */
      readonly profile_id: string;
      /** Requested Model */
      readonly requested_model: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RawChoices */
    readonly RawChoices: {
      /**
       * Inputs
       * @default false
       */
      readonly inputs?: boolean;
      /**
       * Requests
       * @default false
       */
      readonly requests?: boolean;
      /**
       * Responses
       * @default false
       */
      readonly responses?: boolean;
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
    /** ReevaluateRequest */
    readonly ReevaluateRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /** Result Snapshot Id */
      readonly result_snapshot_id: string;
      /**
       * Schema Version
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
    /** RegressionDTO */
    readonly RegressionDTO: {
      /** Acceptable Option Ids */
      readonly acceptable_option_ids: readonly string[];
      /** Case Id */
      readonly case_id: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Executable */
      readonly executable: boolean;
      /** Input Hash */
      readonly input_hash: string;
      /** Original Split */
      readonly original_split: string;
      /**
       * Provenance
       * @enum {string}
       */
      readonly provenance:
        "human" | "authored_fixture" | "imported_unknown" | "model_generated";
      /** Question Id */
      readonly question_id: string;
      /** Reason */
      readonly reason: string;
      /** Regression Id */
      readonly regression_id: string;
      /** Removed */
      readonly removed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Source Result Snapshot Id */
      readonly source_result_snapshot_id: string;
      /** Source Run Id */
      readonly source_run_id: string;
      /** Unavailable Reason */
      readonly unavailable_reason: string | null;
    };
    /** RegressionPageDTO */
    readonly RegressionPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["RegressionDTO"][];
    };
    /** RemoveOption */
    readonly RemoveOption: {
      /** Id */
      readonly id: string;
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "remove_option";
    };
    /** RemoveRegressionRequest */
    readonly RemoveRegressionRequest: {
      /** Decision Id */
      readonly decision_id: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RemoveSchemaField */
    readonly RemoveSchemaField: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "remove_schema_field";
      /** Name */
      readonly name: string;
    };
    /** RenameDecisionRequest */
    readonly RenameDecisionRequest: {
      /** Expected Etag */
      readonly expected_etag: string;
      /** Name */
      readonly name: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RenameOption */
    readonly RenameOption: {
      /** Id */
      readonly id: string;
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "rename_option";
      /** Name */
      readonly name: string;
    };
    /** ReorderOptions */
    readonly ReorderOptions: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "reorder_options";
      /** Option Ids */
      readonly option_ids: readonly string[];
    };
    /** ReplaceMappingAlias */
    readonly ReplaceMappingAlias: {
      /** Option Id */
      readonly option_id: string;
      /** Value */
      readonly value: string;
    };
    /** ReplaceMappingField */
    readonly ReplaceMappingField: {
      /** Parse Json */
      readonly parse_json: boolean;
      /** Source */
      readonly source: string;
      /** Target */
      readonly target: string;
    };
    /** ReplaceMappingFields */
    readonly ReplaceMappingFields: {
      /** Fields */
      readonly fields: readonly components["schemas"]["ReplaceMappingField"][];
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "replace_fields";
    };
    /** ReplaceOptionAliases */
    readonly ReplaceOptionAliases: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "replace_option_aliases";
      /** Option Aliases */
      readonly option_aliases: readonly components["schemas"]["ReplaceMappingAlias"][];
    };
    /** ReplaceSchema */
    readonly ReplaceSchema: {
      /** Input Schema Source */
      readonly input_schema_source: string | null;
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "replace_schema";
    };
    /** ReportDTO */
    readonly ReportDTO: {
      /** Check Snapshot Id */
      readonly check_snapshot_id: string | null;
      /** Comparison Id */
      readonly comparison_id: string | null;
      /** Content Hash */
      readonly content_hash: string;
      /** Created At */
      readonly created_at: string;
      /** Diagnostic Snapshot Id */
      readonly diagnostic_snapshot_id: string | null;
      /** Evaluation Ids */
      readonly evaluation_ids: readonly string[];
      /** Evidence Modes */
      readonly evidence_modes: readonly string[];
      /** Label Snapshot Ids */
      readonly label_snapshot_ids: readonly string[];
      /** Legacy */
      readonly legacy: boolean;
      /** Nonexportable Reason */
      readonly nonexportable_reason: string | null;
      readonly raw: components["schemas"]["RawChoices"];
      /** Report Id */
      readonly report_id: string;
      /** Result Snapshot Ids */
      readonly result_snapshot_ids: readonly string[];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Target Id */
      readonly target_id: string | null;
      /** Target Kind */
      readonly target_kind:
        ("run" | "evaluation" | "comparison" | "diagnostic" | "check") | null;
    };
    /** ReportPageDTO */
    readonly ReportPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["ReportDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /** Total */
      readonly total: string;
    };
    /** RequestIdentityDTO */
    readonly RequestIdentityDTO: {
      /** Case Id */
      readonly case_id: string;
      /** Compiler */
      readonly compiler: string | null;
      /** Compiler Version */
      readonly compiler_version: string | null;
      /** Input Hash */
      readonly input_hash: string;
      /** Request Hash */
      readonly request_hash: string | null;
      /** Requested Model */
      readonly requested_model: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /**
     * ResourceChoice
     * @description One safe exact-ID alternative, scoped to its owning resource.
     */
    readonly ResourceChoice: {
      /**
       * Kind
       * @enum {string}
       */
      readonly kind:
        | "decision"
        | "revision"
        | "dataset"
        | "case"
        | "provider"
        | "fixture"
        | "run"
        | "result_snapshot"
        | "evaluation"
        | "comparison"
        | "regression"
        | "execution_group"
        | "diagnostic_snapshot"
        | "check_snapshot"
        | "report";
      /** Resource Id */
      readonly resource_id: string;
      /**
       * Scope
       * @default []
       */
      readonly scope?: readonly string[];
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
    /** RestoreRevisionRequest */
    readonly RestoreRevisionRequest: {
      /** Expected Draft Etag */
      readonly expected_draft_etag: string;
      /** Operation Id */
      readonly operation_id: string;
      /** Revision Id */
      readonly revision_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ResultPageDTO */
    readonly ResultPageDTO: {
      /** Evaluation Id */
      readonly evaluation_id: string | null;
      /** Filtered Count */
      readonly filtered_count: string;
      /** Items */
      readonly items: readonly components["schemas"]["ResultRowDTO"][];
      /** Label Snapshot Id */
      readonly label_snapshot_id: string;
      /** Next Cursor */
      readonly next_cursor: string | null;
      /** Result Snapshot Id */
      readonly result_snapshot_id: string;
      /** Run Id */
      readonly run_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Selected Count */
      readonly selected_count: string;
      /** Status Counts */
      readonly status_counts: {
        readonly [key: string]: string;
      };
      /** Summary */
      readonly summary: {
        readonly [key: string]: unknown;
      };
    };
    /** ResultRowDTO */
    readonly ResultRowDTO: {
      /** Source */
      readonly source: {
        readonly [key: string]: unknown;
      };
    };
    /** ReviewSourceRecordDTO */
    readonly ReviewSourceRecordDTO: {
      /** Body Hash */
      readonly body_hash: string;
      /**
       * Collection
       * @enum {string}
       */
      readonly collection:
        | "project"
        | "decisions"
        | "drafts"
        | "revisions"
        | "datasets"
        | "cases"
        | "labels"
        | "label_history"
        | "dataset_snapshots"
        | "label_snapshots"
        | "providers"
        | "fixtures"
        | "runs"
        | "prepared_cases"
        | "run_controls"
        | "segments"
        | "run_events"
        | "attempts"
        | "attempt_events"
        | "result_snapshots"
        | "evaluations"
        | "annotations"
        | "comparisons"
        | "execution_groups"
        | "group_segments"
        | "diagnostic_snapshots"
        | "check_snapshots"
        | "regression_removals"
        | "regressions"
        | "reports";
      /** Etag */
      readonly etag: string;
      /** Resource Id */
      readonly resource_id: string;
      /** Scope */
      readonly scope: readonly string[];
    };
    /** RevisionDTO */
    readonly RevisionDTO: {
      /** Editor Source */
      readonly editor_source: string;
      readonly revision: components["schemas"]["Versioned_DecisionRevision_"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RevisionPageDTO */
    readonly RevisionPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["RevisionDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Total */
      readonly total: string;
    };
    /** RunAcceptedDTO */
    readonly RunAcceptedDTO: {
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      /** Operation Id */
      readonly operation_id: string;
      /** Progress Path */
      readonly progress_path: string;
      /** Replayed */
      readonly replayed: boolean;
      /** Run Id */
      readonly run_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Segment Id */
      readonly segment_id: string | null;
    };
    /** RunAttemptProgressDTO */
    readonly RunAttemptProgressDTO: {
      /** Attempt Id */
      readonly attempt_id: string;
      /** Case Id */
      readonly case_id: string;
      /** Duration Seconds */
      readonly duration_seconds: string | null;
      /** Kind */
      readonly kind: string;
      /** Number */
      readonly number: number;
      /** State */
      readonly state: string;
    };
    /** RunCancelRequest */
    readonly RunCancelRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RunCaseProgressDTO */
    readonly RunCaseProgressDTO: {
      /** Attempt Id */
      readonly attempt_id: string | null;
      /** Case Id */
      readonly case_id: string;
      readonly error: components["schemas"]["ErrorDTO"] | null;
      /** Status */
      readonly status: string;
    };
    /** RunCaseReviewDTO */
    readonly RunCaseReviewDTO: {
      /** Case Id */
      readonly case_id: string;
      /** Compiler */
      readonly compiler: string | null;
      /** Compiler Version */
      readonly compiler_version: string | null;
      readonly input_error: components["schemas"]["ServiceError"] | null;
      /** Input Hash */
      readonly input_hash: string;
      /** Request Hash */
      readonly request_hash: string | null;
      /** Request Source */
      readonly request_source: string | null;
      /** Request Source Redacted */
      readonly request_source_redacted: boolean | null;
      /** Requested Model */
      readonly requested_model: string | null;
    };
    /** RunPageDTO */
    readonly RunPageDTO: {
      /** Items */
      readonly items: readonly components["schemas"]["RunProgressDTO"][];
      /** Next Cursor */
      readonly next_cursor: string | null;
      /** Total */
      readonly total: string;
    };
    /** RunPreviewDTO */
    readonly RunPreviewDTO: {
      /** Case Reviews */
      readonly case_reviews: readonly components["schemas"]["RunCaseReviewDTO"][];
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Development Case Count */
      readonly development_case_count: string;
      /** Dry Run */
      readonly dry_run: boolean;
      /** Fixture Set Id */
      readonly fixture_set_id: string | null;
      /** Initial Requests */
      readonly initial_requests: string;
      /** Invalid Cases */
      readonly invalid_cases: readonly components["schemas"]["ServiceError"][];
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      /** Provider Id */
      readonly provider_id: string;
      /** Requested Model */
      readonly requested_model: string;
      readonly review_context: components["schemas"]["RunReviewContextDTO"];
      /** Review Context Hash */
      readonly review_context_hash: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Selected Case Ids */
      readonly selected_case_ids: readonly string[];
      readonly settings: components["schemas"]["ExecutionSettingsViewDTO"];
    };
    /** RunPreviewRequest */
    readonly RunPreviewRequest: {
      readonly request: components["schemas"]["RunRequestDTO"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RunPreviewSummaryDTO */
    readonly RunPreviewSummaryDTO: {
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Development Case Count */
      readonly development_case_count: string;
      /** Dry Run */
      readonly dry_run: boolean;
      /** Fixture Set Id */
      readonly fixture_set_id: string | null;
      /** Initial Requests */
      readonly initial_requests: string;
      /** Invalid Cases */
      readonly invalid_cases: readonly components["schemas"]["ServiceError"][];
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      /** Provider Id */
      readonly provider_id: string;
      /** Requested Model */
      readonly requested_model: string;
      /** Review Context Hash */
      readonly review_context_hash: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Selected Case Ids */
      readonly selected_case_ids: readonly string[];
      readonly settings: components["schemas"]["ExecutionSettingsViewDTO"];
    };
    /** RunProgressDTO */
    readonly RunProgressDTO: {
      /** Attempt Limit */
      readonly attempt_limit: string;
      /** Attempts */
      readonly attempts: readonly components["schemas"]["RunAttemptProgressDTO"][];
      /** Attempts Remaining */
      readonly attempts_remaining: string;
      /** Attempts Used */
      readonly attempts_used: string;
      /** Cases */
      readonly cases: readonly components["schemas"]["RunCaseProgressDTO"][];
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Execution Active */
      readonly execution_active: boolean;
      /** Execution Group Id */
      readonly execution_group_id: string | null;
      /** Group Attempts Remaining */
      readonly group_attempts_remaining: string | null;
      /** Latest Result Snapshot Id */
      readonly latest_result_snapshot_id: string | null;
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      readonly reason: components["schemas"]["ErrorDTO"] | null;
      /** Replayed */
      readonly replayed: boolean;
      /** Requested Model */
      readonly requested_model: string;
      /** Result Snapshot Ids */
      readonly result_snapshot_ids: readonly string[];
      /** Run Id */
      readonly run_id: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Segment Ids */
      readonly segment_ids: readonly string[];
      /** Segments */
      readonly segments: readonly components["schemas"]["RunSegmentProgressDTO"][];
      readonly settings: components["schemas"]["ExecutionSettingsViewDTO"];
      readonly sources: components["schemas"]["RunSourceReferencesDTO"];
      /** State */
      readonly state: string;
    };
    /** RunRequestDTO */
    readonly RunRequestDTO: {
      /**
       * Case Ids
       * @default []
       */
      readonly case_ids?: readonly string[];
      /** Dataset Id */
      readonly dataset_id: string;
      /** Decision Id */
      readonly decision_id: string;
      /** Fixture Set Id */
      readonly fixture_set_id?: string | null;
      /**
       * Mode
       * @enum {string}
       */
      readonly mode: "fixture" | "live";
      /** Option Order */
      readonly option_order?: readonly string[] | null;
      /** Provider Id */
      readonly provider_id?: string | null;
      /**
       * Regression Ids
       * @default []
       */
      readonly regression_ids?: readonly string[];
      /** Revision Id */
      readonly revision_id?: string | null;
      /**
       * @default {
       *       "concurrency": 2,
       *       "deadline_seconds": 600,
       *       "max_attempts": 100,
       *       "max_retries_per_case": 1,
       *       "timeout_seconds": 60
       *     }
       */
      readonly settings?: components["schemas"]["ExecutionSettingsRequestDTO"];
      /**
       * Split
       * @default all
       * @enum {string}
       */
      readonly split?: "all" | "development" | "calibration" | "test";
    };
    /** RunResumePreviewDTO */
    readonly RunResumePreviewDTO: {
      /** Dry Run */
      readonly dry_run: boolean;
      /** Planned Case Ids */
      readonly planned_case_ids: readonly string[];
      /** Proposed Attempt Limit */
      readonly proposed_attempt_limit: string;
      /** Retry Unknown */
      readonly retry_unknown: boolean;
      readonly run: components["schemas"]["RunProgressDTO"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RunResumeRequest */
    readonly RunResumeRequest: {
      /** Max Attempts */
      readonly max_attempts?: number | null;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Retry Unknown
       * @default false
       */
      readonly retry_unknown?: boolean;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** RunReviewContextDTO */
    readonly RunReviewContextDTO: {
      /** Adapter */
      readonly adapter: string;
      /** Compiler Id */
      readonly compiler_id: string;
      /** Compiler Version */
      readonly compiler_version: string;
      /** Definition Hash */
      readonly definition_hash: string;
      /**
       * Definition Source
       * @enum {string}
       */
      readonly definition_source: "draft" | "revision";
      /** Destination */
      readonly destination: string;
      /** Development Case Ids */
      readonly development_case_ids: readonly string[];
      /** Development Label Count */
      readonly development_label_count: string;
      /** Fixture Set Id */
      readonly fixture_set_id: string | null;
      /** Provider Id */
      readonly provider_id: string;
      /** Requested Model */
      readonly requested_model: string;
      /** Revision Id */
      readonly revision_id: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Source Context Hash */
      readonly source_context_hash: string;
      /** Source Records */
      readonly source_records: readonly components["schemas"]["ReviewSourceRecordDTO"][];
    };
    /** RunSegmentProgressDTO */
    readonly RunSegmentProgressDTO: {
      /** Deadline At */
      readonly deadline_at: string;
      /** Ended At */
      readonly ended_at: string | null;
      /** Retry Unknown */
      readonly retry_unknown: boolean;
      /** Segment Id */
      readonly segment_id: string;
      /** Started At */
      readonly started_at: string;
    };
    /** RunSourceReferencesDTO */
    readonly RunSourceReferencesDTO: {
      /** Adapter */
      readonly adapter?: string | null;
      /** Compiler Id */
      readonly compiler_id?: string | null;
      /** Compiler Id Unavailable Reason */
      readonly compiler_id_unavailable_reason?:
        | (
            | "no_prepared_request"
            | "prepared_compiler_mismatch"
            | "inconsistent_prepared_compiler_identity"
          )
        | null;
      /** Compiler Version */
      readonly compiler_version?: string | null;
      /** Dataset Snapshot Id */
      readonly dataset_snapshot_id: string;
      /** Decision Revision Id */
      readonly decision_revision_id: string;
      /** Development Dataset Snapshot Id */
      readonly development_dataset_snapshot_id: string;
      /** Development Label Snapshot Id */
      readonly development_label_snapshot_id: string;
      /** Evidence Mode */
      readonly evidence_mode?: ("authored_fixture" | "live") | null;
      /** Fixture Set Id */
      readonly fixture_set_id: string | null;
      /** Label Snapshot Id */
      readonly label_snapshot_id: string;
      /** Option Order */
      readonly option_order: readonly string[] | null;
      /** Provider Profile Id */
      readonly provider_profile_id: string;
    };
    /** SaveRevisionRequest */
    readonly SaveRevisionRequest: {
      /** Expected Decision Etag */
      readonly expected_decision_etag: string;
      /** Expected Draft Etag */
      readonly expected_draft_etag: string;
      /**
       * Note
       * @default
       */
      readonly note?: string;
      /** Operation Id */
      readonly operation_id: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** SchemaField */
    readonly SchemaField: {
      /** Field Type */
      readonly field_type: string;
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "schema_field";
      /** Name */
      readonly name: string;
      /** Required */
      readonly required: boolean;
    };
    /** SchemaFieldV1 */
    readonly SchemaFieldV1: {
      /** Advanced Keywords */
      readonly advanced_keywords: readonly string[];
      /** Editable */
      readonly editable: boolean;
      /** Field Type */
      readonly field_type: string | null;
      /** Name */
      readonly name: string;
      /** Required */
      readonly required: boolean;
    };
    /** SchemaProjectionRequest */
    readonly SchemaProjectionRequest: {
      /** Schema Source */
      readonly schema_source: string | null;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** SchemaProjectionV1 */
    readonly SchemaProjectionV1: {
      /** Advanced Keywords */
      readonly advanced_keywords: readonly string[];
      /** Fields */
      readonly fields: readonly components["schemas"]["SchemaFieldV1"][] | null;
      /** Form Unavailable Reason */
      readonly form_unavailable_reason: string | null;
      /** Schema Source */
      readonly schema_source: string | null;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Source Hash */
      readonly source_hash: string | null;
      /** Validation Advice */
      readonly validation_advice: readonly components["schemas"]["ValidationAdviceV1"][];
    };
    /**
     * SelectionDetails
     * @description Alternatives available when a requested resource cannot be selected.
     */
    readonly SelectionDetails: {
      /** Choices */
      readonly choices: readonly components["schemas"]["ResourceChoice"][];
    };
    /** SelectionDTO */
    readonly SelectionDTO: {
      /** Content Hash */
      readonly content_hash: string;
      /** Input Source */
      readonly input_source: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** SelectionRequest */
    readonly SelectionRequest: {
      /** Input Source */
      readonly input_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ServiceError */
    readonly ServiceError: {
      /**
       * Code
       * @enum {string}
       */
      readonly code:
        | "validation_error"
        | "not_found"
        | "conflict"
        | "execution_locked"
        | "incompatible_data"
        | "preflight_failed"
        | "provider_auth"
        | "provider_rejected"
        | "response_invalid"
        | "missing_fixture"
        | "run_incomplete"
        | "expectation_failed"
        | "internal_error";
      /** Reason */
      readonly reason?: string | null;
      /** Resource Id */
      readonly resource_id?: string | null;
      /** Row */
      readonly row?: number | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** ServiceErrorDTO */
    readonly ServiceErrorDTO: {
      /** Code */
      readonly code: string;
      /** Message */
      readonly message: string;
      /** Reason */
      readonly reason?: string | null;
      /** Resource Id */
      readonly resource_id?: string | null;
      /** Row */
      readonly row?: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** SetInputKind */
    readonly SetInputKind: {
      /**
       * Input Kind
       * @enum {string}
       */
      readonly input_kind: "text" | "json";
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "set_input_kind";
    };
    /** SetInstructions */
    readonly SetInstructions: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "set_instructions";
      /** Value */
      readonly value: string;
    };
    /** SetMappingField */
    readonly SetMappingField: {
      /**
       * Field
       * @enum {string}
       */
      readonly field:
        | "input_kind"
        | "input_column"
        | "input_parse_json"
        | "id_column"
        | "expected_column"
        | "expected_parse_json"
        | "group_column"
        | "tags_column"
        | "tags_parse_json"
        | "split_column"
        | "metadata_column"
        | "metadata_parse_json";
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "set";
      /** Value */
      readonly value: string | boolean | null;
    };
    /** SetSelectedFields */
    readonly SetSelectedFields: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      readonly kind: "set_selected_fields";
      /** Selected Fields */
      readonly selected_fields: readonly string[];
    };
    /** SplitCommitDTO */
    readonly SplitCommitDTO: {
      readonly dataset: components["schemas"]["DatasetDTO"];
      /** Replayed */
      readonly replayed: boolean;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      readonly snapshot: components["schemas"]["DatasetSnapshot"];
    };
    /** SplitCommitRequest */
    readonly SplitCommitRequest: {
      /** Operation Id */
      readonly operation_id: string;
      /** Preview Document Source */
      readonly preview_document_source: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** SplitPreviewDTO */
    readonly SplitPreviewDTO: {
      readonly preview: components["schemas"]["SplitPreviewRecordDTO"];
      /** Preview Document Source */
      readonly preview_document_source: string;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** SplitPreviewRecordDTO */
    readonly SplitPreviewRecordDTO: {
      /** Algorithm */
      readonly algorithm: string;
      /** Assignments */
      readonly assignments: readonly (readonly [
        string,
        "development" | "calibration" | "test",
      ])[];
      /** Counts */
      readonly counts: readonly (readonly [
        "development" | "calibration" | "test",
        string,
      ])[];
      /** Dataset Etag */
      readonly dataset_etag: string;
      /** Dataset Id */
      readonly dataset_id: string;
      /** Groups */
      readonly groups: readonly (readonly string[])[];
      /** Input Identity */
      readonly input_identity: string;
      /** Ratios Source */
      readonly ratios_source: string | null;
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
      /** Seed */
      readonly seed: string | null;
    };
    /** SplitPreviewRequest */
    readonly SplitPreviewRequest: {
      /** Assignments */
      readonly assignments?:
        | readonly (readonly [string, "development" | "calibration" | "test"])[]
        | null;
      /**
       * Ratios Source
       * @default {"development":0.8,"test":0.2}
       */
      readonly ratios_source?: string;
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /**
       * Seed
       * @default 0
       */
      readonly seed?: string;
    };
    /** StartCheckRequest */
    readonly StartCheckRequest: {
      /** Expected Review Context Hash */
      readonly expected_review_context_hash: string;
      /** Operation Id */
      readonly operation_id: string;
      readonly request: components["schemas"]["CheckRequestDTO"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** StartChoiceOrderRequest */
    readonly StartChoiceOrderRequest: {
      /** Expected Review Context Hash */
      readonly expected_review_context_hash: string;
      /** Operation Id */
      readonly operation_id: string;
      readonly request: components["schemas"]["ChoiceOrderRequestDTO"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** StartRunRequest */
    readonly StartRunRequest: {
      /** Expected Review Context Hash */
      readonly expected_review_context_hash: string;
      /** Operation Id */
      readonly operation_id: string;
      readonly request: components["schemas"]["RunRequestDTO"];
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
    };
    /** Success[AnnotationDTO] */
    readonly Success_AnnotationDTO_: {
      readonly data: components["schemas"]["AnnotationDTO"];
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
    /** Success[AnnotationPageDTO] */
    readonly Success_AnnotationPageDTO_: {
      readonly data: components["schemas"]["AnnotationPageDTO"];
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
    /** Success[CaseDetailDTO] */
    readonly Success_CaseDetailDTO_: {
      readonly data: components["schemas"]["CaseDetailDTO"];
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
    /** Success[CaseInputProjectionV1] */
    readonly Success_CaseInputProjectionV1_: {
      readonly data: components["schemas"]["CaseInputProjectionV1"];
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
    /** Success[CaseMutationDTO] */
    readonly Success_CaseMutationDTO_: {
      readonly data: components["schemas"]["CaseMutationDTO"];
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
    /** Success[CasePageDTO] */
    readonly Success_CasePageDTO_: {
      readonly data: components["schemas"]["CasePageDTO"];
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
    /** Success[CaseReadDTO] */
    readonly Success_CaseReadDTO_: {
      readonly data: components["schemas"]["CaseReadDTO"];
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
    /** Success[CheckViewDTO] */
    readonly Success_CheckViewDTO_: {
      readonly data: components["schemas"]["CheckViewDTO"];
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
    /** Success[ComparisonDTO] */
    readonly Success_ComparisonDTO_: {
      readonly data: components["schemas"]["ComparisonDTO"];
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
    /** Success[ComparisonPageDTO] */
    readonly Success_ComparisonPageDTO_: {
      readonly data: components["schemas"]["ComparisonPageDTO"];
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
    /** Success[CredentialStatusDTO] */
    readonly Success_CredentialStatusDTO_: {
      readonly data: components["schemas"]["CredentialStatusDTO"];
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
    /** Success[DatasetDTO] */
    readonly Success_DatasetDTO_: {
      readonly data: components["schemas"]["DatasetDTO"];
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
    /** Success[DatasetPageDTO] */
    readonly Success_DatasetPageDTO_: {
      readonly data: components["schemas"]["DatasetPageDTO"];
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
    /** Success[DecisionDTO] */
    readonly Success_DecisionDTO_: {
      readonly data: components["schemas"]["DecisionDTO"];
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
    /** Success[DecisionPageDTO] */
    readonly Success_DecisionPageDTO_: {
      readonly data: components["schemas"]["DecisionPageDTO"];
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
    /** Success[DefinitionDiffDTO] */
    readonly Success_DefinitionDiffDTO_: {
      readonly data: components["schemas"]["DefinitionDiffDTO"];
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
    /** Success[DiagnosticViewDTO] */
    readonly Success_DiagnosticViewDTO_: {
      readonly data: components["schemas"]["DiagnosticViewDTO"];
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
    /** Success[DraftTransformReviewDTO] */
    readonly Success_DraftTransformReviewDTO_: {
      readonly data: components["schemas"]["DraftTransformReviewDTO"];
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
    /** Success[EditorProjectionV1] */
    readonly Success_EditorProjectionV1_: {
      readonly data: components["schemas"]["EditorProjectionV1"];
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
    /** Success[EncodedInputV1] */
    readonly Success_EncodedInputV1_: {
      readonly data: components["schemas"]["EncodedInputV1"];
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
    /** Success[EvaluationDTO] */
    readonly Success_EvaluationDTO_: {
      readonly data: components["schemas"]["EvaluationDTO"];
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
    /** Success[EvaluationPageDTO] */
    readonly Success_EvaluationPageDTO_: {
      readonly data: components["schemas"]["EvaluationPageDTO"];
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
    /** Success[FixtureCreatedDTO] */
    readonly Success_FixtureCreatedDTO_: {
      readonly data: components["schemas"]["FixtureCreatedDTO"];
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
    /** Success[FixturePageDTO] */
    readonly Success_FixturePageDTO_: {
      readonly data: components["schemas"]["FixturePageDTO"];
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
    /** Success[FixtureSummaryDTO] */
    readonly Success_FixtureSummaryDTO_: {
      readonly data: components["schemas"]["FixtureSummaryDTO"];
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
    /** Success[GroupAcceptedDTO] */
    readonly Success_GroupAcceptedDTO_: {
      readonly data: components["schemas"]["GroupAcceptedDTO"];
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
    /** Success[GroupPreviewDTO] */
    readonly Success_GroupPreviewDTO_: {
      readonly data: components["schemas"]["GroupPreviewDTO"];
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
    /** Success[GroupProgressDTO] */
    readonly Success_GroupProgressDTO_: {
      readonly data: components["schemas"]["GroupProgressDTO"];
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
    /** Success[GroupResumePreviewDTO] */
    readonly Success_GroupResumePreviewDTO_: {
      readonly data: components["schemas"]["GroupResumePreviewDTO"];
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
    /** Success[ImportCommitDTO] */
    readonly Success_ImportCommitDTO_: {
      readonly data: components["schemas"]["ImportCommitDTO"];
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
    /** Success[ImportPreviewDTO] */
    readonly Success_ImportPreviewDTO_: {
      readonly data: components["schemas"]["ImportPreviewDTO"];
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
    /** Success[LabelBatchDTO] */
    readonly Success_LabelBatchDTO_: {
      readonly data: components["schemas"]["LabelBatchDTO"];
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
    /** Success[LabelHistoryDTO] */
    readonly Success_LabelHistoryDTO_: {
      readonly data: components["schemas"]["LabelHistoryDTO"];
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
    /** Success[LabelPageDTO] */
    readonly Success_LabelPageDTO_: {
      readonly data: components["schemas"]["LabelPageDTO"];
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
    /** Success[LabelViewDTO] */
    readonly Success_LabelViewDTO_: {
      readonly data: components["schemas"]["LabelViewDTO"];
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
    /** Success[MappingProjectionV1] */
    readonly Success_MappingProjectionV1_: {
      readonly data: components["schemas"]["MappingProjectionV1"];
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
    /** Success[MappingTransformV1] */
    readonly Success_MappingTransformV1_: {
      readonly data: components["schemas"]["MappingTransformV1"];
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
    /** Success[ModelListDTO] */
    readonly Success_ModelListDTO_: {
      readonly data: components["schemas"]["ModelListDTO"];
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
    /** Success[ProviderMutationDTO] */
    readonly Success_ProviderMutationDTO_: {
      readonly data: components["schemas"]["ProviderMutationDTO"];
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
    /** Success[ProviderPageDTO] */
    readonly Success_ProviderPageDTO_: {
      readonly data: components["schemas"]["ProviderPageDTO"];
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
    /** Success[ProviderProfileDTO] */
    readonly Success_ProviderProfileDTO_: {
      readonly data: components["schemas"]["ProviderProfileDTO"];
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
    /** Success[RegressionDTO] */
    readonly Success_RegressionDTO_: {
      readonly data: components["schemas"]["RegressionDTO"];
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
    /** Success[RegressionPageDTO] */
    readonly Success_RegressionPageDTO_: {
      readonly data: components["schemas"]["RegressionPageDTO"];
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
    /** Success[ReportDTO] */
    readonly Success_ReportDTO_: {
      readonly data: components["schemas"]["ReportDTO"];
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
    /** Success[ReportPageDTO] */
    readonly Success_ReportPageDTO_: {
      readonly data: components["schemas"]["ReportPageDTO"];
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
    /** Success[ResultPageDTO] */
    readonly Success_ResultPageDTO_: {
      readonly data: components["schemas"]["ResultPageDTO"];
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
    /** Success[RevisionDTO] */
    readonly Success_RevisionDTO_: {
      readonly data: components["schemas"]["RevisionDTO"];
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
    /** Success[RevisionPageDTO] */
    readonly Success_RevisionPageDTO_: {
      readonly data: components["schemas"]["RevisionPageDTO"];
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
    /** Success[RunAcceptedDTO] */
    readonly Success_RunAcceptedDTO_: {
      readonly data: components["schemas"]["RunAcceptedDTO"];
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
    /** Success[RunPageDTO] */
    readonly Success_RunPageDTO_: {
      readonly data: components["schemas"]["RunPageDTO"];
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
    /** Success[RunPreviewDTO] */
    readonly Success_RunPreviewDTO_: {
      readonly data: components["schemas"]["RunPreviewDTO"];
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
    /** Success[RunProgressDTO] */
    readonly Success_RunProgressDTO_: {
      readonly data: components["schemas"]["RunProgressDTO"];
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
    /** Success[RunResumePreviewDTO] */
    readonly Success_RunResumePreviewDTO_: {
      readonly data: components["schemas"]["RunResumePreviewDTO"];
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
    /** Success[SchemaProjectionV1] */
    readonly Success_SchemaProjectionV1_: {
      readonly data: components["schemas"]["SchemaProjectionV1"];
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
    /** Success[SelectionDTO] */
    readonly Success_SelectionDTO_: {
      readonly data: components["schemas"]["SelectionDTO"];
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
    /** Success[SplitCommitDTO] */
    readonly Success_SplitCommitDTO_: {
      readonly data: components["schemas"]["SplitCommitDTO"];
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
    /** Success[SplitPreviewDTO] */
    readonly Success_SplitPreviewDTO_: {
      readonly data: components["schemas"]["SplitPreviewDTO"];
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
    /** Success[ValidationDTO] */
    readonly Success_ValidationDTO_: {
      readonly data: components["schemas"]["ValidationDTO"];
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
    /** Success[Versioned[DecisionDraft]] */
    readonly Success_Versioned_DecisionDraft__: {
      readonly data: components["schemas"]["Versioned_DecisionDraft_"];
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
    /** Success[Versioned[DecisionRecord]] */
    readonly Success_Versioned_DecisionRecord__: {
      readonly data: components["schemas"]["Versioned_DecisionRecord_"];
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
    /** TextInputRequest */
    readonly TextInputRequest: {
      /**
       * Schema Version
       * @constant
       */
      readonly schema_version: 1;
      /** Text Value */
      readonly text_value: string;
    };
    /** ValidationAdviceV1 */
    readonly ValidationAdviceV1: {
      /** Code */
      readonly code: string;
      /**
       * Kind
       * @enum {string}
       */
      readonly kind: "validation" | "advice";
      /**
       * Path
       * @default []
       */
      readonly path?: readonly string[];
    };
    /** ValidationDTO */
    readonly ValidationDTO: {
      /** Content Hash */
      readonly content_hash: string;
      readonly definition: components["schemas"]["ChoiceDefinition"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      readonly schema_version: 1;
    };
    /** Versioned[DecisionDraft] */
    readonly Versioned_DecisionDraft_: {
      /** Etag */
      readonly etag: string;
      readonly record: components["schemas"]["DecisionDraft"];
    };
    /** Versioned[DecisionRecord] */
    readonly Versioned_DecisionRecord_: {
      /** Etag */
      readonly etag: string;
      readonly record: components["schemas"]["DecisionRecord"];
    };
    /** Versioned[DecisionRevision] */
    readonly Versioned_DecisionRevision_: {
      /** Etag */
      readonly etag: string;
      readonly record: components["schemas"]["DecisionRevision"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readAnnotation: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly annotation_id: string;
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
          readonly "application/json": components["schemas"]["Success_AnnotationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly projectCaseInput: {
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
        readonly "application/json": components["schemas"]["CaseInputProjectionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_CaseInputProjectionV1_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly projectImportMapping: {
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
        readonly "application/json": components["schemas"]["MappingProjectionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_MappingProjectionV1_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly transformImportMapping: {
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
        readonly "application/json": components["schemas"]["MappingTransformRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_MappingTransformV1_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly projectInputSchema: {
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
        readonly "application/json": components["schemas"]["SchemaProjectionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_SchemaProjectionV1_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly encodeTextInput: {
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
        readonly "application/json": components["schemas"]["TextInputRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_EncodedInputV1_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly startRegressionCheck: {
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
        readonly "application/json": components["schemas"]["StartCheckRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 202: {
        headers: {
          readonly Location?: string;
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupAcceptedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readCheck: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
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
          readonly "application/json": components["schemas"]["Success_CheckViewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly cancelCheck: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["GroupCancelRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupProgressDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly resumeCheck: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["GroupResumeRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 202: {
        headers: {
          readonly Location?: string;
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupAcceptedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewCheckResume: {
    readonly parameters: {
      readonly query?: {
        readonly retry_unknown?: "true" | "false";
      };
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
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
          readonly "application/json": components["schemas"]["Success_GroupResumePreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewRegressionCheck: {
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
        readonly "application/json": components["schemas"]["CheckPreviewRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupPreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listComparisons: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: number;
      };
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
          readonly "application/json": components["schemas"]["Success_ComparisonPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createComparison: {
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
        readonly "application/json": components["schemas"]["CreateComparisonRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ComparisonDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readComparison: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly comparison_id: string;
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
          readonly "application/json": components["schemas"]["Success_ComparisonDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly list_datasets_api_v1_projects__registration_id__datasets_get: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly include_archived?: string | null;
        readonly limit?: string | null;
      };
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
          readonly "application/json": components["schemas"]["Success_DatasetPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createDataset: {
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
        readonly "application/json": components["schemas"]["DatasetCreateRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DatasetDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
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
          readonly "application/json": components["schemas"]["Success_DatasetDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DatasetPatchRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DatasetDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DatasetChangeRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DatasetDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly group_id?: string | null;
        readonly limit?: string | null;
        readonly split?: ("development" | "calibration" | "test") | null;
        readonly tag?: string | null;
      };
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
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
          readonly "application/json": components["schemas"]["Success_CasePageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["CaseInputRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_CaseMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly case_id: string;
        readonly dataset_id: string;
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
          readonly "application/json": components["schemas"]["Success_CaseReadDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly case_id: string;
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["CaseEditRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_CaseMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly case_id: string;
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["CaseChangeRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_CaseMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["ImportCommitRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ImportCommitDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["ImportPreviewRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ImportPreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DatasetChangeRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DatasetDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["SplitCommitRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_SplitCommitDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["SplitPreviewRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_SplitPreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listDecisions: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly include_archived?: string;
        readonly limit?: string;
      };
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
          readonly "application/json": components["schemas"]["Success_DecisionPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createDecision: {
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
        readonly "application/json": components["schemas"]["DecisionCreateRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DecisionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readDecision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_DecisionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly archiveDecision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DecisionETagRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_Versioned_DecisionRecord__"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: string | null;
        readonly status?: string | null;
      };
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_LabelPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get: {
    readonly parameters: {
      readonly query?: {
        readonly question_id?: string | null;
      };
      readonly header?: never;
      readonly path: {
        readonly case_id: string;
        readonly dataset_id: string;
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_LabelViewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get: {
    readonly parameters: {
      readonly query?: {
        readonly question_id?: string | null;
      };
      readonly header?: never;
      readonly path: {
        readonly case_id: string;
        readonly dataset_id: string;
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_LabelHistoryDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly dataset_id: string;
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["LabelBatchRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_LabelBatchDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly diffDecisionRevisions: {
    readonly parameters: {
      readonly query: {
        readonly after: string;
        readonly before: string;
      };
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_DefinitionDiffDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly updateDecisionDraft: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DraftRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_Versioned_DecisionDraft__"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly projectDecisionEditor: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["EditorProjectionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_EditorProjectionV1_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly transformDecisionEditor: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["EditorTransformRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_DraftTransformReviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly latestDecisionRevision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_RevisionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listRegressions: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_RegressionPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly addRegression: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["AddRegressionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RegressionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly removeRegression: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
        readonly regression_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RemoveRegressionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RegressionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly renameDecision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RenameDecisionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_Versioned_DecisionRecord__"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly restoreDecision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["DecisionETagRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_Versioned_DecisionRecord__"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly restoreDecisionRevisionToDraft: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RestoreRevisionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_Versioned_DecisionDraft__"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listDecisionRevisions: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: string;
      };
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_RevisionPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly saveDecisionRevision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["SaveRevisionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RevisionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readDecisionRevision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
        readonly revision_id: string;
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
          readonly "application/json": components["schemas"]["Success_RevisionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewCaseSelection: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["SelectionRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_SelectionDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly validateDecision: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly decision_id: string;
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
          readonly "application/json": components["schemas"]["Success_ValidationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readChoiceOrder: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
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
          readonly "application/json": components["schemas"]["Success_DiagnosticViewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly cancelChoiceOrder: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["GroupCancelRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupProgressDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly resumeChoiceOrder: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["GroupResumeRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 202: {
        headers: {
          readonly Location?: string;
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupAcceptedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewChoiceOrderResume: {
    readonly parameters: {
      readonly query?: {
        readonly retry_unknown?: "true" | "false";
      };
      readonly header?: never;
      readonly path: {
        readonly group_id: string;
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
          readonly "application/json": components["schemas"]["Success_GroupResumePreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly startChoiceOrder: {
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
        readonly "application/json": components["schemas"]["StartChoiceOrderRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 202: {
        headers: {
          readonly Location?: string;
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupAcceptedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewChoiceOrder: {
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
        readonly "application/json": components["schemas"]["ChoiceOrderPreviewRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_GroupPreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readEvaluation: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly evaluation_id: string;
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
          readonly "application/json": components["schemas"]["Success_EvaluationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listFixtureSets: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: string;
      };
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
          readonly "application/json": components["schemas"]["Success_FixturePageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createFixtureSet: {
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
        readonly "application/json": components["schemas"]["FixtureCreateRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_FixtureCreatedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readFixtureSet: {
    readonly parameters: {
      readonly query?: {
        readonly include_requests?: string;
      };
      readonly header?: never;
      readonly path: {
        readonly fixture_set_id: string;
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
          readonly "application/json": components["schemas"]["Success_FixtureSummaryDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listProviderProfiles: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: string;
      };
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
          readonly "application/json": components["schemas"]["Success_ProviderPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readProviderProfile: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
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
          readonly "application/json": components["schemas"]["Success_ProviderProfileDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly configureProviderProfile: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["ProviderProfileRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ProviderMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly attachEnvironmentCredential: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["EnvironmentCredentialRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ProviderMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly forgetProviderCredential: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["ProviderETagRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ProviderMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly setOSStoreCredential: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["OSCredentialRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ProviderMutationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly providerCredentialStatus: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
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
          readonly "application/json": components["schemas"]["Success_CredentialStatusDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listProviderModels: {
    readonly parameters: {
      readonly query?: {
        readonly timeout_seconds?: string;
      };
      readonly header?: never;
      readonly path: {
        readonly profile_id: string;
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
          readonly "application/json": components["schemas"]["Success_ModelListDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listReports: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: number;
      };
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
          readonly "application/json": components["schemas"]["Success_ReportPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createReport: {
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
        readonly "application/json": components["schemas"]["CreateReportRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_ReportDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readReport: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly report_id: string;
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
          readonly "application/json": components["schemas"]["Success_ReportDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly downloadReport: {
    readonly parameters: {
      readonly query: {
        readonly format: "json" | "markdown";
      };
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly report_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody?: never;
    readonly responses: {
      /** @description Saved report bytes */
      readonly 200: {
        headers: {
          readonly "Cache-Control"?: "no-store";
          /** @description Fixed attachment name report-{report_id}.{json|md} */
          readonly "Content-Disposition"?: string;
          readonly "X-Content-Type-Options"?: "nosniff";
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/octet-stream": string;
          readonly "text/plain; charset=utf-8": string;
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listRuns: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly decision_id?: string | null;
        readonly limit?: number;
        readonly status?: string | null;
      };
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
          readonly "application/json": components["schemas"]["Success_RunPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly startRun: {
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
        readonly "application/json": components["schemas"]["StartRunRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 202: {
        headers: {
          readonly Location?: string;
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RunAcceptedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readRun: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
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
          readonly "application/json": components["schemas"]["Success_RunProgressDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listAnnotations: {
    readonly parameters: {
      readonly query?: {
        readonly case_id?: string | null;
        readonly cursor?: string | null;
        readonly limit?: number;
      };
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
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
          readonly "application/json": components["schemas"]["Success_AnnotationPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly addAnnotation: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["AddAnnotationRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_AnnotationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly cancelRun: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RunCancelRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RunProgressDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listEvaluations: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly limit?: number;
      };
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
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
          readonly "application/json": components["schemas"]["Success_EvaluationPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly createEvaluation: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["EvaluateRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_EvaluationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly reevaluateRun: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["ReevaluateRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_EvaluationDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly listResults: {
    readonly parameters: {
      readonly query?: {
        readonly cursor?: string | null;
        readonly evaluation_id?: string | null;
        readonly limit?: number;
        readonly split?: ("development" | "calibration" | "test") | null;
        readonly status?: string | null;
        readonly tag?: string | null;
      };
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
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
          readonly "application/json": components["schemas"]["Success_ResultPageDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly readResult: {
    readonly parameters: {
      readonly query?: {
        readonly evaluation_id?: string | null;
        readonly include_attempts?: "true" | "false";
        readonly include_input?: "true" | "false";
        readonly include_request?: "true" | "false";
        readonly include_response?: "true" | "false";
      };
      readonly header?: never;
      readonly path: {
        readonly case_id: string;
        readonly registration_id: string;
        readonly run_id: string;
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
          readonly "application/json": components["schemas"]["Success_CaseDetailDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly resumeRun: {
    readonly parameters: {
      readonly query?: never;
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RunResumeRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 202: {
        headers: {
          readonly Location?: string;
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RunAcceptedDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewRunResume: {
    readonly parameters: {
      readonly query?: {
        readonly max_attempts?: string | null;
        readonly retry_unknown?: "true" | "false";
      };
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
        readonly run_id: string;
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
          readonly "application/json": components["schemas"]["Success_RunResumePreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Failure"];
        };
      };
    };
  };
  readonly previewRun: {
    readonly parameters: {
      readonly query?: {
        readonly include_request?: "true" | "false";
      };
      readonly header?: never;
      readonly path: {
        readonly registration_id: string;
      };
      readonly cookie?: never;
    };
    readonly requestBody: {
      readonly content: {
        readonly "application/json": components["schemas"]["RunPreviewRequest"];
      };
    };
    readonly responses: {
      /** @description Successful Response */
      readonly 200: {
        headers: {
          readonly [name: string]: unknown;
        };
        content: {
          readonly "application/json": components["schemas"]["Success_RunPreviewDTO_"];
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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
      readonly 409: {
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
      /** @description Safe structured failure */
      readonly 502: {
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

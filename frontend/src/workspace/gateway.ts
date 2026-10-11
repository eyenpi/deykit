import { ApiError } from "../api/client";
import type {
  ApiOperationArguments,
  ApiOperationBody,
  ApiOperationData,
  ApiWarning,
} from "../api/client";
import type { ApiResult } from "../api/client";
import type { ApiDownload, ApiDownloadArguments } from "../api/client";
import type {
  ApiJsonOperationId,
  ApiOperationId,
} from "../api/generated/operations";
export interface ResourceSummary {
  id: string;
  name: string;
}
export interface ProjectSummary extends ResourceSummary {
  path: string;
}
export interface RecentProjectsResult {
  items: readonly ProjectSummary[];
  warnings: readonly ApiWarning[];
}
export interface ProjectOverview extends ProjectSummary {
  decisions: readonly ResourceSummary[];
  datasets: readonly ResourceSummary[];
  warnings: readonly ApiWarning[];
}
export type ProjectAction = "create" | "open" | "demo";
export interface ProjectRequest {
  action: ProjectAction;
  path: string;
  name: string;
  operationId: string;
}
/** Presentation port implemented by the local API adapter. */
export interface WorkspaceGateway {
  recentProjects(signal: AbortSignal): Promise<RecentProjectsResult>;
  projectOverview(
    registrationId: string,
    signal: AbortSignal,
  ): Promise<ProjectOverview>;
  openProject(request: ProjectRequest): Promise<ProjectOverview>;
  reconnect(): Promise<void>;
  authoring: AuthoringGateway;
  execution: ExecutionGateway;
  debugging: DebuggingGateway;
}

type OperationResult<K extends ApiJsonOperationId> = Promise<
  ApiResult<ApiOperationData<K>>
>;
type OperationQuery<K extends ApiJsonOperationId> = NonNullable<
  ApiOperationArguments<K>["query"]
>;
type OperationBody<K extends ApiOperationId> = ApiOperationBody<K>;

export type ResourcePath = { registrationId: string; signal?: AbortSignal };
export type DecisionPath = ResourcePath & { decisionId: string };
export type DatasetPath = ResourcePath & { datasetId: string };
export type CasePath = DatasetPath & { caseId: string };
export type LabelPath = DecisionPath & { datasetId: string };
export type ProviderPath = ResourcePath & { profileId: string };
export type RunPath = ResourcePath & { runId: string };
export type RunCasePath = RunPath & { caseId: string };
export type EvaluationPath = ResourcePath & { evaluationId: string };
export type AnnotationPath = ResourcePath & { annotationId: string };
export type ComparisonPath = ResourcePath & { comparisonId: string };
export type ReportPath = ResourcePath & { reportId: string };
export type GroupPath = ResourcePath & { groupId: string };
export type GroupSnapshotPath = GroupPath & { snapshotId: string };

type ReportDownloadQuery = ApiDownloadArguments<"downloadReport">["query"];

export interface DebuggingGateway {
  evaluations: {
    create(
      request: RunPath & { body: OperationBody<"createEvaluation"> },
    ): OperationResult<"createEvaluation">;
    reevaluate(
      request: RunPath & { body: OperationBody<"reevaluateRun"> },
    ): OperationResult<"reevaluateRun">;
  };
  annotations: {
    add(
      request: RunCasePath & { body: OperationBody<"addAnnotation"> },
    ): OperationResult<"addAnnotation">;
    list(
      request: RunPath & { query?: OperationQuery<"listAnnotations"> },
    ): OperationResult<"listAnnotations">;
    read(request: AnnotationPath): OperationResult<"readAnnotation">;
  };
  comparisons: {
    create(
      request: ResourcePath & { body: OperationBody<"createComparison"> },
    ): OperationResult<"createComparison">;
    list(
      request: ResourcePath & { query?: OperationQuery<"listComparisons"> },
    ): OperationResult<"listComparisons">;
    read(
      request: ComparisonPath,
    ): OperationResult<"readComparison">;
  };
  regressions: {
    add(
      request: DecisionPath & { body: OperationBody<"addRegression"> },
    ): OperationResult<"addRegression">;
    list(request: DecisionPath): OperationResult<"listRegressions">;
    remove(
      request: DecisionPath & {
        regressionId: string;
        body: OperationBody<"removeRegression">;
      },
    ): OperationResult<"removeRegression">;
  };
  reports: {
    create(
      request: ResourcePath & { body: OperationBody<"createReport"> },
    ): OperationResult<"createReport">;
    list(
      request: ResourcePath & { query?: OperationQuery<"listReports"> },
    ): OperationResult<"listReports">;
    read(request: ReportPath): OperationResult<"readReport">;
    download(
      request: ReportPath & { query: ReportDownloadQuery },
    ): Promise<ApiDownload>;
  };
  diagnostics: GroupOperations<"diagnostic">;
  checks: GroupOperations<"check">;
}

type GroupOperations<Kind extends "diagnostic" | "check"> = {
  preview(
    request: ResourcePath & {
      body: OperationBody<
        Kind extends "diagnostic" ? "previewChoiceOrder" : "previewRegressionCheck"
      >;
    },
  ): OperationResult<
    Kind extends "diagnostic" ? "previewChoiceOrder" : "previewRegressionCheck"
  >;
  start(
    request: ResourcePath & {
      body: OperationBody<
        Kind extends "diagnostic" ? "startChoiceOrder" : "startRegressionCheck"
      >;
    },
  ): OperationResult<
    Kind extends "diagnostic" ? "startChoiceOrder" : "startRegressionCheck"
  >;
  read(request: GroupPath): OperationResult<
    Kind extends "diagnostic" ? "readChoiceOrder" : "readCheck"
  >;
  cancel(
    request: GroupPath & {
      body: OperationBody<"cancelChoiceOrder" | "cancelCheck">;
    },
  ): OperationResult<
    Kind extends "diagnostic" ? "cancelChoiceOrder" : "cancelCheck"
  >;
  previewResume(
    request: GroupPath & {
      body: OperationBody<
        Kind extends "diagnostic" ? "previewChoiceOrderResume" : "previewCheckResume"
      >;
      query?: OperationQuery<
        Kind extends "diagnostic" ? "previewChoiceOrderResume" : "previewCheckResume"
      >;
    },
  ): OperationResult<
    Kind extends "diagnostic" ? "previewChoiceOrderResume" : "previewCheckResume"
  >;
  resume(
    request: GroupPath & {
      body: OperationBody<
        Kind extends "diagnostic" ? "resumeChoiceOrder" : "resumeCheck"
      >;
    },
  ): OperationResult<
    Kind extends "diagnostic" ? "resumeChoiceOrder" : "resumeCheck"
  >;
  listSnapshots(request: GroupPath): OperationResult<
    Kind extends "diagnostic" ? "listChoiceOrderSnapshots" : "listCheckSnapshots"
  >;
  readSnapshot(request: GroupSnapshotPath): OperationResult<
    Kind extends "diagnostic" ? "readChoiceOrderSnapshot" : "readCheckSnapshot"
  >;
};

export interface DecisionAuthoringOperations {
  list(
    request: ResourcePath & { query?: OperationQuery<"listDecisions"> },
  ): OperationResult<"listDecisions">;
  create(
    request: ResourcePath & { body: OperationBody<"createDecision"> },
  ): OperationResult<"createDecision">;
  read(request: DecisionPath): OperationResult<"readDecision">;
  updateDraft(
    request: DecisionPath & { body: OperationBody<"updateDecisionDraft"> },
  ): OperationResult<"updateDecisionDraft">;
  projectEditor(
    request: DecisionPath & { body: OperationBody<"projectDecisionEditor"> },
  ): OperationResult<"projectDecisionEditor">;
  transformEditor(
    request: DecisionPath & { body: OperationBody<"transformDecisionEditor"> },
  ): OperationResult<"transformDecisionEditor">;
  validate(
    request: DecisionPath & { body: OperationBody<"validateDecision"> },
  ): OperationResult<"validateDecision">;
  saveRevision(
    request: DecisionPath & { body: OperationBody<"saveDecisionRevision"> },
  ): OperationResult<"saveDecisionRevision">;
  revisions(
    request: DecisionPath & { query?: OperationQuery<"listDecisionRevisions"> },
  ): OperationResult<"listDecisionRevisions">;
  latestRevision(
    request: DecisionPath,
  ): OperationResult<"latestDecisionRevision">;
  revision(
    request: DecisionPath & { revisionId: string },
  ): OperationResult<"readDecisionRevision">;
  diff(
    request: DecisionPath & { query: OperationQuery<"diffDecisionRevisions"> },
  ): OperationResult<"diffDecisionRevisions">;
  rename(
    request: DecisionPath & { body: OperationBody<"renameDecision"> },
  ): OperationResult<"renameDecision">;
  archive(
    request: DecisionPath & { body: OperationBody<"archiveDecision"> },
  ): OperationResult<"archiveDecision">;
  restore(
    request: DecisionPath & { body: OperationBody<"restoreDecision"> },
  ): OperationResult<"restoreDecision">;
  restoreRevisionToDraft(
    request: DecisionPath & {
      body: OperationBody<"restoreDecisionRevisionToDraft">;
    },
  ): OperationResult<"restoreDecisionRevisionToDraft">;
}

export interface DatasetAuthoringOperations {
  list(
    request: ResourcePath & {
      query?: OperationQuery<"list_datasets_api_v1_projects__registration_id__datasets_get">;
    },
  ): OperationResult<"list_datasets_api_v1_projects__registration_id__datasets_get">;
  create(
    request: ResourcePath & { body: OperationBody<"createDataset"> },
  ): OperationResult<"createDataset">;
  read(
    request: DatasetPath,
  ): OperationResult<"read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get">;
  update(
    request: DatasetPath & {
      body: OperationBody<"patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch">;
    },
  ): OperationResult<"patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch">;
  archive(
    request: DatasetPath & {
      body: OperationBody<"archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post">;
    },
  ): OperationResult<"archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post">;
  restore(
    request: DatasetPath & {
      body: OperationBody<"restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post">;
    },
  ): OperationResult<"restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post">;
}

export interface ExampleAuthoringOperations {
  listCases(
    request: DatasetPath & {
      query?: OperationQuery<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
    },
  ): OperationResult<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
  readCase(
    request: CasePath,
  ): OperationResult<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">;
  addCase(
    request: DatasetPath & {
      body: OperationBody<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
    },
  ): OperationResult<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
  editCase(
    request: CasePath & {
      body: OperationBody<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
    },
  ): OperationResult<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
  removeCase(
    request: CasePath & {
      body: OperationBody<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;
    },
  ): OperationResult<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;
  listLabels(
    request: LabelPath & {
      query?: OperationQuery<"list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get">;
    },
  ): OperationResult<"list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get">;
  readLabel(
    request: LabelPath & {
      caseId: string;
      query?: OperationQuery<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">;
    },
  ): OperationResult<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">;
  labelHistory(
    request: LabelPath & {
      caseId: string;
      query?: OperationQuery<"label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get">;
    },
  ): OperationResult<"label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get">;
  saveLabels(
    request: LabelPath & {
      body: OperationBody<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
    },
  ): OperationResult<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
  previewImport(
    request: DatasetPath & {
      body: OperationBody<"preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post">;
    },
  ): OperationResult<"preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post">;
  commitImport(
    request: DatasetPath & {
      body: OperationBody<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post">;
    },
  ): OperationResult<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post">;
  previewSplit(
    request: DatasetPath & {
      body: OperationBody<"preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post">;
    },
  ): OperationResult<"preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post">;
  commitSplit(
    request: DatasetPath & {
      body: OperationBody<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post">;
    },
  ): OperationResult<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post">;
}

export interface ProviderAuthoringOperations {
  list(
    request: ResourcePath & { query?: OperationQuery<"listProviderProfiles"> },
  ): OperationResult<"listProviderProfiles">;
  read(request: ProviderPath): OperationResult<"readProviderProfile">;
  configure(
    request: ProviderPath & { body: OperationBody<"configureProviderProfile"> },
  ): OperationResult<"configureProviderProfile">;
  credentialStatus(
    request: ProviderPath,
  ): OperationResult<"providerCredentialStatus">;
  attachEnvironment(
    request: ProviderPath & {
      body: OperationBody<"attachEnvironmentCredential">;
    },
  ): OperationResult<"attachEnvironmentCredential">;
  setOSCredential(
    request: ProviderPath & { body: OperationBody<"setOSStoreCredential"> },
  ): OperationResult<"setOSStoreCredential">;
  forgetCredential(
    request: ProviderPath & { body: OperationBody<"forgetProviderCredential"> },
  ): OperationResult<"forgetProviderCredential">;
  listModels(
    request: ProviderPath & {
      query: OperationQuery<"listProviderModels">;
      body: OperationBody<"listProviderModels">;
    },
  ): OperationResult<"listProviderModels">;
}

export interface FixtureAuthoringOperations {
  list(
    request: ResourcePath & { query?: OperationQuery<"listFixtureSets"> },
  ): OperationResult<"listFixtureSets">;
  read(
    request: ResourcePath & {
      fixtureSetId: string;
      query?: OperationQuery<"readFixtureSet">;
    },
  ): OperationResult<"readFixtureSet">;
  create(
    request: ResourcePath & { body: OperationBody<"createFixtureSet"> },
  ): OperationResult<"createFixtureSet">;
}

export interface SourceAuthoringOperations {
  projectSchema(
    request: ResourcePath & { body: OperationBody<"projectInputSchema"> },
  ): OperationResult<"projectInputSchema">;
  projectCaseInput(
    request: ResourcePath & { body: OperationBody<"projectCaseInput"> },
  ): OperationResult<"projectCaseInput">;
  encodeTextInput(
    request: ResourcePath & { body: OperationBody<"encodeTextInput"> },
  ): OperationResult<"encodeTextInput">;
  projectMapping(
    request: ResourcePath & { body: OperationBody<"projectImportMapping"> },
  ): OperationResult<"projectImportMapping">;
  transformMapping(
    request: ResourcePath & { body: OperationBody<"transformImportMapping"> },
  ): OperationResult<"transformImportMapping">;
}

export interface AuthoringGateway {
  decisions: DecisionAuthoringOperations;
  datasets: DatasetAuthoringOperations;
  examples: ExampleAuthoringOperations;
  providers: ProviderAuthoringOperations;
  fixtures: FixtureAuthoringOperations;
  sources: SourceAuthoringOperations;
}

export interface ExecutionGateway {
  runs: {
    preview(
      request: ResourcePath & {
        body: OperationBody<"previewRun">;
        query?: OperationQuery<"previewRun">;
      },
    ): OperationResult<"previewRun">;
    start(
      request: ResourcePath & { body: OperationBody<"startRun"> },
    ): OperationResult<"startRun">;
    list(
      request: ResourcePath & { query?: OperationQuery<"listRuns"> },
    ): OperationResult<"listRuns">;
    read(request: RunPath): OperationResult<"readRun">;
    cancel(
      request: RunPath & { body: OperationBody<"cancelRun"> },
    ): OperationResult<"cancelRun">;
    previewResume(
      request: RunPath & {
        body: OperationBody<"previewRunResume">;
        query?: OperationQuery<"previewRunResume">;
      },
    ): OperationResult<"previewRunResume">;
    resume(
      request: RunPath & { body: OperationBody<"resumeRun"> },
    ): OperationResult<"resumeRun">;
  };
  inspection: {
    listResults(
      request: RunPath & { query?: OperationQuery<"listResults"> },
    ): OperationResult<"listResults">;
    readResult(
      request: RunCasePath & { query?: OperationQuery<"readResult"> },
    ): OperationResult<"readResult">;
    listEvaluations(
      request: RunPath & { query?: OperationQuery<"listEvaluations"> },
    ): OperationResult<"listEvaluations">;
    readEvaluation(request: EvaluationPath): OperationResult<"readEvaluation">;
  };
}

const pending = () =>
  new ApiError(
    "integration_pending",
    "The local workspace service is not connected in this build. Project folders are unavailable.",
  );
async function disconnectedOperation(): Promise<never> {
  throw pending();
}

function disconnectedAuthoringGroup<Operations extends object>(
  names: readonly (keyof Operations)[],
): Operations {
  return Object.fromEntries(
    names.map((name) => [name, disconnectedOperation]),
  ) as Operations;
}

const disconnectedAuthoring: AuthoringGateway = {
  decisions: disconnectedAuthoringGroup<DecisionAuthoringOperations>([
    "list",
    "create",
    "read",
    "updateDraft",
    "projectEditor",
    "transformEditor",
    "validate",
    "saveRevision",
    "revisions",
    "latestRevision",
    "revision",
    "diff",
    "rename",
    "archive",
    "restore",
    "restoreRevisionToDraft",
  ]),
  datasets: disconnectedAuthoringGroup<DatasetAuthoringOperations>([
    "list",
    "create",
    "read",
    "update",
    "archive",
    "restore",
  ]),
  examples: disconnectedAuthoringGroup<ExampleAuthoringOperations>([
    "listCases",
    "readCase",
    "addCase",
    "editCase",
    "removeCase",
    "listLabels",
    "readLabel",
    "labelHistory",
    "saveLabels",
    "previewImport",
    "commitImport",
    "previewSplit",
    "commitSplit",
  ]),
  providers: disconnectedAuthoringGroup<ProviderAuthoringOperations>([
    "list",
    "read",
    "configure",
    "credentialStatus",
    "attachEnvironment",
    "setOSCredential",
    "forgetCredential",
    "listModels",
  ]),
  fixtures: disconnectedAuthoringGroup<FixtureAuthoringOperations>([
    "list",
    "read",
    "create",
  ]),
  sources: disconnectedAuthoringGroup<SourceAuthoringOperations>([
    "projectSchema",
    "projectCaseInput",
    "encodeTextInput",
    "projectMapping",
    "transformMapping",
  ]),
};

const disconnectedExecution: ExecutionGateway = {
  runs: disconnectedAuthoringGroup<ExecutionGateway["runs"]>([
    "preview",
    "start",
    "list",
    "read",
    "cancel",
    "previewResume",
    "resume",
  ]),
  inspection: disconnectedAuthoringGroup<ExecutionGateway["inspection"]>([
    "listResults",
    "readResult",
    "listEvaluations",
    "readEvaluation",
  ]),
};

const disconnectedDebugging: DebuggingGateway = {
  evaluations: disconnectedAuthoringGroup<DebuggingGateway["evaluations"]>([
    "create",
    "reevaluate",
  ]),
  annotations: disconnectedAuthoringGroup<DebuggingGateway["annotations"]>([
    "add",
    "list",
    "read",
  ]),
  comparisons: disconnectedAuthoringGroup<DebuggingGateway["comparisons"]>([
    "create",
    "list",
    "read",
  ]),
  regressions: disconnectedAuthoringGroup<DebuggingGateway["regressions"]>([
    "add",
    "list",
    "remove",
  ]),
  reports: disconnectedAuthoringGroup<DebuggingGateway["reports"]>([
    "create",
    "list",
    "read",
    "download",
  ]),
  diagnostics: disconnectedAuthoringGroup<DebuggingGateway["diagnostics"]>([
    "preview",
    "start",
    "read",
    "cancel",
    "previewResume",
    "resume",
    "listSnapshots",
    "readSnapshot",
  ]),
  checks: disconnectedAuthoringGroup<DebuggingGateway["checks"]>([
    "preview",
    "start",
    "read",
    "cancel",
    "previewResume",
    "resume",
    "listSnapshots",
    "readSnapshot",
  ]),
};

/** Deliberately no mock successes, filesystem guesses, or speculative API endpoints. */
export const disconnectedWorkspace: WorkspaceGateway = {
  authoring: disconnectedAuthoring,
  execution: disconnectedExecution,
  debugging: disconnectedDebugging,
  async recentProjects() {
    throw pending();
  },
  async openProject() {
    throw pending();
  },
  async projectOverview() {
    throw pending();
  },
  async reconnect() {
    throw pending();
  },
};

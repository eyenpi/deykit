import { ApiError } from "../api/client";
import type {
  ApiOperationArguments,
  ApiOperationBody,
  ApiOperationData,
  ApiWarning,
} from "../api/client";
import type { ApiResult } from "../api/client";
import type { ApiJsonOperationId, ApiOperationId } from "../api/generated/operations";
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
  projectOverview(registrationId: string, signal: AbortSignal): Promise<ProjectOverview>;
  openProject(request: ProjectRequest): Promise<ProjectOverview>;
  reconnect(): Promise<void>;
  authoring: AuthoringGateway;
}

type OperationResult<K extends ApiJsonOperationId> =
  Promise<ApiResult<ApiOperationData<K>>>;
type OperationQuery<K extends ApiJsonOperationId> =
  NonNullable<ApiOperationArguments<K>["query"]>;
type OperationBody<K extends ApiOperationId> =
  ApiOperationBody<K>;

export type ResourcePath = { registrationId: string; signal?: AbortSignal };
export type DecisionPath = ResourcePath & { decisionId: string };
export type DatasetPath = ResourcePath & { datasetId: string };
export type CasePath = DatasetPath & { caseId: string };
export type LabelPath = DecisionPath & { datasetId: string };
export type ProviderPath = ResourcePath & { profileId: string };

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
  latestRevision(request: DecisionPath): OperationResult<"latestDecisionRevision">;
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
    request: ResourcePath & { query?: OperationQuery<"list_datasets_api_v1_projects__registration_id__datasets_get"> },
  ): OperationResult<"list_datasets_api_v1_projects__registration_id__datasets_get">;
  create(
    request: ResourcePath & { body: OperationBody<"createDataset"> },
  ): OperationResult<"createDataset">;
  read(request: DatasetPath): OperationResult<"read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get">;
  update(
    request: DatasetPath & { body: OperationBody<"patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch"> },
  ): OperationResult<"patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch">;
  archive(
    request: DatasetPath & { body: OperationBody<"archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post"> },
  ): OperationResult<"archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post">;
  restore(
    request: DatasetPath & { body: OperationBody<"restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post"> },
  ): OperationResult<"restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post">;
}

export interface ExampleAuthoringOperations {
  listCases(
    request: DatasetPath & { query?: OperationQuery<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get"> },
  ): OperationResult<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
  readCase(
    request: CasePath,
  ): OperationResult<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">;
  addCase(
    request: DatasetPath & { body: OperationBody<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post"> },
  ): OperationResult<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
  editCase(
    request: CasePath & { body: OperationBody<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put"> },
  ): OperationResult<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
  removeCase(
    request: CasePath & { body: OperationBody<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete"> },
  ): OperationResult<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;
  listLabels(
    request: LabelPath & { query?: OperationQuery<"list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get"> },
  ): OperationResult<"list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get">;
  readLabel(
    request: LabelPath & { caseId: string; query?: OperationQuery<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get"> },
  ): OperationResult<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">;
  labelHistory(
    request: LabelPath & { caseId: string; query?: OperationQuery<"label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get"> },
  ): OperationResult<"label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get">;
  saveLabels(
    request: LabelPath & { body: OperationBody<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post"> },
  ): OperationResult<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
  previewImport(
    request: DatasetPath & { body: OperationBody<"preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post"> },
  ): OperationResult<"preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post">;
  commitImport(
    request: DatasetPath & { body: OperationBody<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post"> },
  ): OperationResult<"commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post">;
  previewSplit(
    request: DatasetPath & { body: OperationBody<"preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post"> },
  ): OperationResult<"preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post">;
  commitSplit(
    request: DatasetPath & { body: OperationBody<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post"> },
  ): OperationResult<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post">;
}

export interface ProviderAuthoringOperations {
  list(request: ResourcePath & { query?: OperationQuery<"listProviderProfiles"> }): OperationResult<"listProviderProfiles">;
  read(request: ProviderPath): OperationResult<"readProviderProfile">;
  configure(request: ProviderPath & { body: OperationBody<"configureProviderProfile"> }): OperationResult<"configureProviderProfile">;
  credentialStatus(request: ProviderPath): OperationResult<"providerCredentialStatus">;
  attachEnvironment(request: ProviderPath & { body: OperationBody<"attachEnvironmentCredential"> }): OperationResult<"attachEnvironmentCredential">;
  setOSCredential(request: ProviderPath & { body: OperationBody<"setOSStoreCredential"> }): OperationResult<"setOSStoreCredential">;
  forgetCredential(request: ProviderPath & { body: OperationBody<"forgetProviderCredential"> }): OperationResult<"forgetProviderCredential">;
  listModels(request: ProviderPath & { query: OperationQuery<"listProviderModels">; body: OperationBody<"listProviderModels"> }): OperationResult<"listProviderModels">;
}

export interface FixtureAuthoringOperations {
  list(request: ResourcePath & { query?: OperationQuery<"listFixtureSets"> }): OperationResult<"listFixtureSets">;
  read(request: ResourcePath & { fixtureSetId: string; query?: OperationQuery<"readFixtureSet"> }): OperationResult<"readFixtureSet">;
  create(request: ResourcePath & { body: OperationBody<"createFixtureSet"> }): OperationResult<"createFixtureSet">;
}

export interface SourceAuthoringOperations {
  projectSchema(request: ResourcePath & { body: OperationBody<"projectInputSchema"> }): OperationResult<"projectInputSchema">;
  projectCaseInput(request: ResourcePath & { body: OperationBody<"projectCaseInput"> }): OperationResult<"projectCaseInput">;
  encodeTextInput(request: ResourcePath & { body: OperationBody<"encodeTextInput"> }): OperationResult<"encodeTextInput">;
  projectMapping(request: ResourcePath & { body: OperationBody<"projectImportMapping"> }): OperationResult<"projectImportMapping">;
  transformMapping(request: ResourcePath & { body: OperationBody<"transformImportMapping"> }): OperationResult<"transformImportMapping">;
}

export interface AuthoringGateway {
  decisions: DecisionAuthoringOperations;
  datasets: DatasetAuthoringOperations;
  examples: ExampleAuthoringOperations;
  providers: ProviderAuthoringOperations;
  fixtures: FixtureAuthoringOperations;
  sources: SourceAuthoringOperations;
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
  return Object.fromEntries(names.map((name) => [name, disconnectedOperation])) as Operations;
}

const disconnectedAuthoring: AuthoringGateway = {
  decisions: disconnectedAuthoringGroup<DecisionAuthoringOperations>([
    "list", "create", "read", "updateDraft", "projectEditor", "transformEditor",
    "validate", "saveRevision", "revisions", "latestRevision", "revision", "diff",
    "rename", "archive", "restore", "restoreRevisionToDraft",
  ]),
  datasets: disconnectedAuthoringGroup<DatasetAuthoringOperations>([
    "list", "create", "read", "update", "archive", "restore",
  ]),
  examples: disconnectedAuthoringGroup<ExampleAuthoringOperations>([
    "listCases", "readCase", "addCase", "editCase", "removeCase", "listLabels",
    "readLabel", "labelHistory", "saveLabels", "previewImport", "commitImport",
    "previewSplit", "commitSplit",
  ]),
  providers: disconnectedAuthoringGroup<ProviderAuthoringOperations>([
    "list", "read", "configure", "credentialStatus", "attachEnvironment",
    "setOSCredential", "forgetCredential", "listModels",
  ]),
  fixtures: disconnectedAuthoringGroup<FixtureAuthoringOperations>([
    "list", "read", "create",
  ]),
  sources: disconnectedAuthoringGroup<SourceAuthoringOperations>([
    "projectSchema", "projectCaseInput", "encodeTextInput", "projectMapping",
    "transformMapping",
  ]),
};

/** Deliberately no mock successes, filesystem guesses, or speculative API endpoints. */
export const disconnectedWorkspace: WorkspaceGateway = {
  authoring: disconnectedAuthoring,
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

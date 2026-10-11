import { ApiClient } from "../api/client";
import type {
  ApiOperationArguments,
  ApiOperationBody,
  ApiWarning,
} from "../api/client";
import type { ApiJsonOperationId } from "../api/generated/operations";
import {
  decodeProjectOverview,
  decodeDemoRegistration,
  decodeRecentProjects,
  decodeRegistration,
} from "../api/codecs";
import type { WorkspaceGateway } from "./gateway";
import type { AuthoringGateway } from "./gateway";
import { RegistrationReadSequencer } from "./read-sequencer";

export function createWorkspaceGateway(
  client = new ApiClient(),
): WorkspaceGateway {
  const completedRegistrations = new Map<
    string,
    { signature: string; id: string; warnings: readonly ApiWarning[] }
  >();
  const reads = new RegistrationReadSequencer();
  const read = <T>(
    registrationId: string,
    signal: AbortSignal | undefined,
    perform: () => Promise<T>,
  ) => reads.enqueueRead(registrationId, signal, perform);
  return {
    authoring: createAuthoringGateway(client, reads, read),
    async recentProjects(signal) {
      const result = await client.operation(
        "listRecentProjects",
        { signal },
        decodeRecentProjects,
      );
      return { items: result.data, warnings: result.warnings };
    },
    async projectOverview(registrationId, signal) {
      const overview = await read(registrationId, signal, () =>
        client.operation(
          "projectOverview",
          { path: { registration_id: registrationId } },
          decodeProjectOverview,
        ),
      );
      return { ...overview.data, warnings: overview.warnings };
    },
    async openProject(request) {
      const signature = JSON.stringify({
        action: request.action,
        path: request.path,
        name: request.name,
      });
      const previous = completedRegistrations.get(request.operationId);
      if (previous?.signature === signature) {
        const overview = await read(previous.id, undefined, () =>
          client.operation(
            "projectOverview",
            { path: { registration_id: previous.id } },
            decodeProjectOverview,
          ),
        );
        completedRegistrations.delete(request.operationId);
        return {
          ...overview.data,
          warnings: [...previous.warnings, ...overview.warnings],
        };
      }
      const registration =
        request.action === "demo"
          ? await client.operation(
              "createAuthoredDemo",
              {
                body: {
                  schema_version: 1,
                  operation_id: request.operationId,
                  path: request.path,
                },
              },
              decodeDemoRegistration,
            )
          : await client.operation(
              "registerProject",
              {
                body: {
                  schema_version: 1,
                  operation_id: request.operationId,
                  action: request.action,
                  path: request.path,
                  name: request.action === "create" ? request.name : null,
                } satisfies ApiOperationBody<"registerProject">,
              },
              decodeRegistration,
            );
      completedRegistrations.set(request.operationId, {
        signature,
        id: registration.data,
        warnings: registration.warnings,
      });
      const overview = await read(registration.data, undefined, () =>
        client.operation(
          "projectOverview",
          { path: { registration_id: registration.data } },
          decodeProjectOverview,
        ),
      );
      completedRegistrations.delete(request.operationId);
      return {
        ...overview.data,
        warnings: [...registration.warnings, ...overview.warnings],
      };
    },
    reconnect: () => client.reconnect(),
  };
}

/** Operation-specific presentation ports. ApiClient remains the sole transport. */
function createAuthoringGateway(
  client: ApiClient,
  sequencer: RegistrationReadSequencer,
  read: <T>(
    registrationId: string,
    signal: AbortSignal | undefined,
    perform: () => Promise<T>,
  ) => Promise<T>,
): AuthoringGateway {
  const sourceRead = <K extends ApiJsonOperationId>(
    registrationId: string,
    signal: AbortSignal | undefined,
    operation: K,
    args: ApiOperationArguments<K>,
  ) => {
    const captured = captureOperationArguments(args);
    return read(registrationId, signal, () =>
      client.operation(operation, captured),
    );
  };
  const sourceMutation = <K extends ApiJsonOperationId>(
    registrationId: string,
    signal: AbortSignal | undefined,
    operation: K,
    args: ApiOperationArguments<K>,
  ) => {
    const captured = captureOperationArguments(args);
    return sequencer.enqueueMutation(registrationId, signal, () =>
      client.operation(operation, captured),
    );
  };
  return {
    decisions: {
      list: ({ registrationId, query, signal }) =>
        sourceRead(registrationId, signal, "listDecisions", {
          path: { registration_id: registrationId },
          query,
        }),
      create: ({ registrationId, body, signal }) =>
        sourceMutation(registrationId, signal, "createDecision", {
          path: { registration_id: registrationId },
          body,
        }),
      read: ({ registrationId, decisionId, signal }) =>
        sourceRead(registrationId, signal, "readDecision", {
          path: { registration_id: registrationId, decision_id: decisionId },
        }),
      updateDraft: ({ registrationId, decisionId, body, signal }) =>
        sourceMutation(registrationId, signal, "updateDecisionDraft", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      projectEditor: ({ registrationId, decisionId, body, signal }) =>
        sourceRead(registrationId, signal, "projectDecisionEditor", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      transformEditor: ({ registrationId, decisionId, body, signal }) =>
        sourceRead(registrationId, signal, "transformDecisionEditor", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      validate: ({ registrationId, decisionId, body, signal }) =>
        sourceRead(registrationId, signal, "validateDecision", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      saveRevision: ({ registrationId, decisionId, body, signal }) =>
        sourceMutation(registrationId, signal, "saveDecisionRevision", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      revisions: ({ registrationId, decisionId, query, signal }) =>
        sourceRead(registrationId, signal, "listDecisionRevisions", {
          path: { registration_id: registrationId, decision_id: decisionId },
          query,
        }),
      latestRevision: ({ registrationId, decisionId, signal }) =>
        sourceRead(registrationId, signal, "latestDecisionRevision", {
          path: { registration_id: registrationId, decision_id: decisionId },
        }),
      revision: ({ registrationId, decisionId, revisionId, signal }) =>
        sourceRead(registrationId, signal, "readDecisionRevision", {
          path: {
            registration_id: registrationId,
            decision_id: decisionId,
            revision_id: revisionId,
          },
        }),
      diff: ({ registrationId, decisionId, query, signal }) =>
        sourceRead(registrationId, signal, "diffDecisionRevisions", {
          path: { registration_id: registrationId, decision_id: decisionId },
          query,
        }),
      rename: ({ registrationId, decisionId, body, signal }) =>
        sourceMutation(registrationId, signal, "renameDecision", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      archive: ({ registrationId, decisionId, body, signal }) =>
        sourceMutation(registrationId, signal, "archiveDecision", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      restore: ({ registrationId, decisionId, body, signal }) =>
        sourceMutation(registrationId, signal, "restoreDecision", {
          path: { registration_id: registrationId, decision_id: decisionId },
          body,
        }),
      restoreRevisionToDraft: ({ registrationId, decisionId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "restoreDecisionRevisionToDraft",
          {
            path: { registration_id: registrationId, decision_id: decisionId },
            body,
          },
        ),
    },
    datasets: {
      list: ({ registrationId, query, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "list_datasets_api_v1_projects__registration_id__datasets_get",
          { path: { registration_id: registrationId }, query },
        ),
      create: ({ registrationId, body, signal }) =>
        sourceMutation(registrationId, signal, "createDataset", {
          path: { registration_id: registrationId },
          body,
        }),
      read: ({ registrationId, datasetId, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
          },
        ),
      update: ({ registrationId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "patch_dataset_api_v1_projects__registration_id__datasets__dataset_id__patch",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
      archive: ({ registrationId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "archive_dataset_api_v1_projects__registration_id__datasets__dataset_id__archive_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
      restore: ({ registrationId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "restore_dataset_api_v1_projects__registration_id__datasets__dataset_id__restore_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
    },
    examples: {
      listCases: ({ registrationId, datasetId, query, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            query,
          },
        ),
      readCase: ({ registrationId, datasetId, caseId, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get",
          {
            path: {
              registration_id: registrationId,
              dataset_id: datasetId,
              case_id: caseId,
            },
          },
        ),
      addCase: ({ registrationId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
      editCase: ({ registrationId, datasetId, caseId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put",
          {
            path: {
              registration_id: registrationId,
              dataset_id: datasetId,
              case_id: caseId,
            },
            body,
          },
        ),
      removeCase: ({ registrationId, datasetId, caseId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete",
          {
            path: {
              registration_id: registrationId,
              dataset_id: datasetId,
              case_id: caseId,
            },
            body,
          },
        ),
      listLabels: ({ registrationId, decisionId, datasetId, query, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get",
          {
            path: {
              registration_id: registrationId,
              decision_id: decisionId,
              dataset_id: datasetId,
            },
            query,
          },
        ),
      readLabel: ({
        registrationId,
        decisionId,
        datasetId,
        caseId,
        query,
        signal,
      }) =>
        sourceRead(
          registrationId,
          signal,
          "read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get",
          {
            path: {
              registration_id: registrationId,
              decision_id: decisionId,
              dataset_id: datasetId,
              case_id: caseId,
            },
            query,
          },
        ),
      labelHistory: ({
        registrationId,
        decisionId,
        datasetId,
        caseId,
        query,
        signal,
      }) =>
        sourceRead(
          registrationId,
          signal,
          "label_history_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__history_get",
          {
            path: {
              registration_id: registrationId,
              decision_id: decisionId,
              dataset_id: datasetId,
              case_id: caseId,
            },
            query,
          },
        ),
      saveLabels: ({ registrationId, decisionId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post",
          {
            path: {
              registration_id: registrationId,
              decision_id: decisionId,
              dataset_id: datasetId,
            },
            body,
          },
        ),
      previewImport: ({ registrationId, datasetId, body, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "preview_import_api_v1_projects__registration_id__datasets__dataset_id__imports_preview_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
      commitImport: ({ registrationId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "commit_import_api_v1_projects__registration_id__datasets__dataset_id__imports_commit_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
      previewSplit: ({ registrationId, datasetId, body, signal }) =>
        sourceRead(
          registrationId,
          signal,
          "preview_split_api_v1_projects__registration_id__datasets__dataset_id__splits_preview_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
      commitSplit: ({ registrationId, datasetId, body, signal }) =>
        sourceMutation(
          registrationId,
          signal,
          "commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post",
          {
            path: { registration_id: registrationId, dataset_id: datasetId },
            body,
          },
        ),
    },
    providers: {
      list: ({ registrationId, query, signal }) =>
        sourceRead(registrationId, signal, "listProviderProfiles", {
          path: { registration_id: registrationId },
          query,
        }),
      read: ({ registrationId, profileId, signal }) =>
        sourceRead(registrationId, signal, "readProviderProfile", {
          path: { registration_id: registrationId, profile_id: profileId },
        }),
      configure: ({ registrationId, profileId, body, signal }) =>
        sourceMutation(registrationId, signal, "configureProviderProfile", {
          path: { registration_id: registrationId, profile_id: profileId },
          body,
        }),
      credentialStatus: ({ registrationId, profileId, signal }) =>
        sourceRead(registrationId, signal, "providerCredentialStatus", {
          path: { registration_id: registrationId, profile_id: profileId },
        }),
      attachEnvironment: ({ registrationId, profileId, body, signal }) =>
        sourceMutation(registrationId, signal, "attachEnvironmentCredential", {
          path: { registration_id: registrationId, profile_id: profileId },
          body,
        }),
      setOSCredential: ({ registrationId, profileId, body, signal }) =>
        sourceMutation(registrationId, signal, "setOSStoreCredential", {
          path: { registration_id: registrationId, profile_id: profileId },
          body,
        }),
      forgetCredential: ({ registrationId, profileId, body, signal }) =>
        sourceMutation(registrationId, signal, "forgetProviderCredential", {
          path: { registration_id: registrationId, profile_id: profileId },
          body,
        }),
      listModels: ({ registrationId, profileId, query, body, signal }) =>
        sourceRead(registrationId, signal, "listProviderModels", {
          path: { registration_id: registrationId, profile_id: profileId },
          query,
          body,
        }),
    },
    fixtures: {
      list: ({ registrationId, query, signal }) =>
        sourceRead(registrationId, signal, "listFixtureSets", {
          path: { registration_id: registrationId },
          query,
        }),
      read: ({ registrationId, fixtureSetId, query, signal }) =>
        sourceRead(registrationId, signal, "readFixtureSet", {
          path: {
            registration_id: registrationId,
            fixture_set_id: fixtureSetId,
          },
          query,
        }),
      create: ({ registrationId, body, signal }) =>
        sourceMutation(registrationId, signal, "createFixtureSet", {
          path: { registration_id: registrationId },
          body,
        }),
    },
    sources: {
      projectSchema: ({ registrationId, body, signal }) =>
        client.operation("projectInputSchema", {
          path: { registration_id: registrationId },
          body,
          signal,
        }),
      projectCaseInput: ({ registrationId, body, signal }) =>
        client.operation("projectCaseInput", {
          path: { registration_id: registrationId },
          body,
          signal,
        }),
      encodeTextInput: ({ registrationId, body, signal }) =>
        client.operation("encodeTextInput", {
          path: { registration_id: registrationId },
          body,
          signal,
        }),
      projectMapping: ({ registrationId, body, signal }) =>
        client.operation("projectImportMapping", {
          path: { registration_id: registrationId },
          body,
          signal,
        }),
      transformMapping: ({ registrationId, body, signal }) =>
        client.operation("transformImportMapping", {
          path: { registration_id: registrationId },
          body,
          signal,
        }),
    },
  };
}

function captureOperationArguments<K extends ApiJsonOperationId>(
  args: ApiOperationArguments<K>,
): ApiOperationArguments<K> {
  return structuredClone({ ...args, signal: undefined });
}

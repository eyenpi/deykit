import { ApiClient } from "../api/client";
import type { ApiOperationBody, ApiWarning } from "../api/client";
import {
  decodeProjectOverview,
  decodeDemoRegistration,
  decodeRecentProjects,
  decodeRegistration,
} from "../api/codecs";
import type { WorkspaceGateway } from "./gateway";

export function createWorkspaceGateway(
  client = new ApiClient(),
): WorkspaceGateway {
  const completedRegistrations = new Map<
    string,
    { signature: string; id: string; warnings: readonly ApiWarning[] }
  >();
  return {
    async recentProjects(signal) {
      const result = await client.operation(
        "listRecentProjects",
        { signal },
        decodeRecentProjects,
      );
      return { items: result.data, warnings: result.warnings };
    },
    async openProject(request) {
      const signature = JSON.stringify({
        action: request.action,
        path: request.path,
        name: request.name,
      });
      const previous = completedRegistrations.get(request.operationId);
      if (previous?.signature === signature) {
        const overview = await client.operation(
          "projectOverview",
          { path: { registration_id: previous.id } },
          decodeProjectOverview,
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
      const overview = await client.operation(
        "projectOverview",
        { path: { registration_id: registration.data } },
        decodeProjectOverview,
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

import { ApiClient } from "../api/client";
import type { ApiWarning } from "../api/client";
import {
  decodeProjectOverview,
  decodeDemoRegistration,
  decodeRecentProjects,
  decodeRegistration,
} from "../api/codecs";
import type { RegisterProjectRequest } from "../api/transport-types";
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
      const result = await client.request(
        "/api/v1/projects/recent",
        decodeRecentProjects,
        { signal },
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
        const overview = await client.request(
          `/api/v1/projects/${previous.id}/overview`,
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
          ? await client.request(
              "/api/v1/projects/demo",
              decodeDemoRegistration,
              {
                method: "POST",
                body: {
                  schema_version: 1,
                  operation_id: request.operationId,
                  path: request.path,
                },
              },
            )
          : await client.request(
              "/api/v1/projects/register",
              decodeRegistration,
              {
                method: "POST",
                body: {
                  schema_version: 1,
                  operation_id: request.operationId,
                  action: request.action,
                  path: request.path,
                  name: request.action === "create" ? request.name : null,
                } satisfies RegisterProjectRequest,
              },
            );
      completedRegistrations.set(request.operationId, {
        signature,
        id: registration.data,
        warnings: registration.warnings,
      });
      const overview = await client.request(
        `/api/v1/projects/${registration.data}/overview`,
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

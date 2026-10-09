import { ApiError } from "../api/client";
import type { ApiWarning } from "../api/client";
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
  openProject(request: ProjectRequest): Promise<ProjectOverview>;
  reconnect(): Promise<void>;
}
const pending = () =>
  new ApiError(
    "integration_pending",
    "The local workspace service is not connected in this build. Project folders are unavailable.",
  );
/** Deliberately no mock successes, filesystem guesses, or speculative API endpoints. */
export const disconnectedWorkspace: WorkspaceGateway = {
  async recentProjects() {
    throw pending();
  },
  async openProject() {
    throw pending();
  },
  async reconnect() {
    throw pending();
  },
};

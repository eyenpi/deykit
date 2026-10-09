import { describe, expect, it } from "vitest";
import { WorkspaceNavigation } from "./navigation";
import { routeFromHash, routeToHash } from "./routes";
import type { WorkspaceRoute } from "./routes";

describe("workspace routes", () => {
  it("round-trips only the declared example context keys", () => {
    const route = {
      kind: "examples" as const,
      registrationId: "registration-1",
      decisionId: "decision-1",
      datasetId: "dataset-2",
      caseId: "case-3",
    };
    expect(routeFromHash(routeToHash(route))).toEqual(route);
  });

  it("rejects unsafe IDs, duplicate query keys, and source or credential parameters", () => {
    expect(routeFromHash("#/p/../d/decision-1")).toBeNull();
    expect(routeFromHash("#/p/project/decisions?dataset=a&dataset=b")).toBeNull();
    expect(routeFromHash("#/p/project/examples?source=%7B%7D")).toBeNull();
    expect(routeFromHash("#/p/project/providers?credential=secret")).toBeNull();
  });

  it("does not accept example parameters on unrelated pages", () => {
    expect(routeFromHash("#/p/project?dataset=dataset-1")).toBeNull();
    expect(routeFromHash("#/p/project/d/decision/history?case=case-1")).toBeNull();
  });

  it("restores the admitted URL immediately and serializes captured external targets", async () => {
    const overview: WorkspaceRoute = { kind: "overview", registrationId: "project" };
    const providers: WorkspaceRoute = { kind: "providers", registrationId: "project" };
    const fixtures: WorkspaceRoute = { kind: "fixtures", registrationId: "project" };
    window.history.replaceState(null, "", routeToHash(overview));
    const navigation = new WorkspaceNavigation(window);
    let resolveProviders!: (accepted: boolean) => void;
    let resolveFixtures!: (accepted: boolean) => void;
    const providerGuard = new Promise<boolean>((resolve) => { resolveProviders = resolve; });
    const fixtureGuard = new Promise<boolean>((resolve) => { resolveFixtures = resolve; });
    const seen: WorkspaceRoute[] = [];
    let calls = 0;
    navigation.registerDirtyGuard("dirty-editor", Object.assign(
      (target: WorkspaceRoute) => {
        seen.push(target);
        calls += 1;
        return calls === 1 ? providerGuard : fixtureGuard;
      },
      { isDirty: () => true },
    ));

    window.location.hash = routeToHash(providers);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.location.hash).toBe(routeToHash(overview));
    expect(seen).toEqual([providers]);

    window.location.hash = routeToHash(fixtures);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.location.hash).toBe(routeToHash(overview));
    expect(calls).toBe(1);

    resolveProviders(true);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(seen).toEqual([providers, fixtures]);
    resolveFixtures(true);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(navigation.current).toEqual(fixtures);
    expect(window.location.hash).toBe(routeToHash(fixtures));
    navigation.dispose();
  });
});

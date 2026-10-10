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
    expect(
      routeFromHash("#/p/project/decisions?dataset=a&dataset=b"),
    ).toBeNull();
    expect(routeFromHash("#/p/project/examples?source=%7B%7D")).toBeNull();
    expect(routeFromHash("#/p/project/providers?credential=secret")).toBeNull();
  });

  it("does not accept example parameters on unrelated pages", () => {
    expect(routeFromHash("#/p/project?dataset=dataset-1")).toBeNull();
    expect(
      routeFromHash("#/p/project/d/decision/history?case=case-1"),
    ).toBeNull();
  });

  it("restores the admitted URL immediately and serializes captured external targets", async () => {
    const overview: WorkspaceRoute = {
      kind: "overview",
      registrationId: "project",
    };
    const providers: WorkspaceRoute = {
      kind: "providers",
      registrationId: "project",
    };
    const fixtures: WorkspaceRoute = {
      kind: "fixtures",
      registrationId: "project",
    };
    window.history.replaceState(null, "", routeToHash(overview));
    const navigation = new WorkspaceNavigation(window);
    let resolveProviders!: (accepted: boolean) => void;
    let resolveFixtures!: (accepted: boolean) => void;
    const providerGuard = new Promise<boolean>((resolve) => {
      resolveProviders = resolve;
    });
    const fixtureGuard = new Promise<boolean>((resolve) => {
      resolveFixtures = resolve;
    });
    let reachProviderGuard!: () => void;
    let reachFixtureGuard!: () => void;
    const providerGuardReached = new Promise<void>((resolve) => {
      reachProviderGuard = resolve;
    });
    const fixtureGuardReached = new Promise<void>((resolve) => {
      reachFixtureGuard = resolve;
    });
    const seen: WorkspaceRoute[] = [];
    let calls = 0;
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        (target: WorkspaceRoute) => {
          seen.push(target);
          calls += 1;
          if (calls === 1) {
            reachProviderGuard();
            return providerGuard;
          }
          reachFixtureGuard();
          return fixtureGuard;
        },
        { isDirty: () => true },
      ),
    );

    function dispatchExternalHashChange(target: WorkspaceRoute) {
      const oldURL = window.location.href;
      window.history.pushState(null, "", routeToHash(target));
      window.dispatchEvent(
        new HashChangeEvent("hashchange", {
          oldURL,
          newURL: window.location.href,
        }),
      );
    }

    dispatchExternalHashChange(providers);
    expect(window.location.hash).toBe(routeToHash(overview));
    await providerGuardReached;
    expect(seen).toEqual([providers]);

    dispatchExternalHashChange(fixtures);
    expect(window.location.hash).toBe(routeToHash(overview));
    expect(calls).toBe(1);

    const fixturesAdmitted = new Promise<void>((resolve) => {
      const unsubscribe = navigation.subscribe((route) => {
        if (
          route.kind === fixtures.kind &&
          route.registrationId === fixtures.registrationId
        ) {
          unsubscribe();
          resolve();
        }
      });
    });
    resolveProviders(true);
    await fixtureGuardReached;
    expect(seen).toEqual([providers, fixtures]);
    resolveFixtures(true);
    await fixturesAdmitted;
    expect(navigation.current).toEqual(fixtures);
    expect(window.location.hash).toBe(routeToHash(fixtures));
    navigation.dispose();
  });
});

import { describe, expect, it } from "vitest";
import { WorkspaceNavigation } from "./navigation";
import { routeFromHash, routeToHash } from "./routes";
import type { WorkspaceRoute } from "./routes";

function nativePopstate(target: WorkspaceRoute) {
  const oldURL = window.location.href;
  const newURL = new URL(routeToHash(target), oldURL).toString();
  window.history.pushState(null, "", newURL);
  window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
  return { oldURL, newURL };
}

function nativeHashchange(pair: { oldURL: string; newURL: string }) {
  window.dispatchEvent(new HashChangeEvent("hashchange", pair));
}

function waitForGuard<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function waitForRoute(
  navigation: WorkspaceNavigation,
  target: WorkspaceRoute,
): Promise<void> {
  return new Promise((resolve) => {
    const unsubscribe = navigation.subscribe((route) => {
      if (routeToHash(route) !== routeToHash(target)) return;
      unsubscribe();
      resolve();
    });
  });
}

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

  it("round-trips run routes with only stable inspection IDs", () => {
    const list: WorkspaceRoute = {
      kind: "runs",
      registrationId: "registration-1",
    };
    const detail: WorkspaceRoute = {
      kind: "run",
      registrationId: "registration-1",
      runId: "run-2",
      evaluationId: "evaluation-3",
      caseId: "case-4",
    };
    expect(routeFromHash(routeToHash(list))).toEqual(list);
    expect(routeFromHash(routeToHash(detail))).toEqual(detail);
    expect(
      routeFromHash("#/p/registration-1/runs/run-2?source=%7B%7D"),
    ).toBeNull();
    expect(
      routeFromHash(
        "#/p/registration-1/runs/run-2?evaluation=evaluation-1&evaluation=evaluation-2",
      ),
    ).toBeNull();
    expect(
      routeFromHash("#/p/registration-1/runs/run-2?case=bad%2Fid"),
    ).toBeNull();
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

  it("uses one captured target for the native popstate and hashchange pair", async () => {
    const overview: WorkspaceRoute = {
      kind: "overview",
      registrationId: "project",
    };
    const providers: WorkspaceRoute = {
      kind: "providers",
      registrationId: "project",
    };
    window.history.replaceState(null, "", routeToHash(overview));
    const navigation = new WorkspaceNavigation(window);
    const guardResult = waitForGuard<boolean>();
    const guardReached = waitForGuard<void>();
    const seen: WorkspaceRoute[] = [];
    const published: WorkspaceRoute[] = [];
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        (target: WorkspaceRoute) => {
          seen.push(target);
          guardReached.resolve();
          return guardResult.promise;
        },
        { isDirty: () => true },
      ),
    );
    navigation.subscribe((route) => published.push(route));

    const pair = nativePopstate(providers);
    const providersPublished = waitForRoute(navigation, providers);
    expect(window.location.hash).toBe(routeToHash(overview));
    nativeHashchange(pair);
    await guardReached.promise;
    expect(seen).toEqual([providers]);
    guardResult.resolve(true);
    await providersPublished;

    expect(navigation.current).toEqual(providers);
    expect(window.location.hash).toBe(routeToHash(providers));
    expect(published).toEqual([providers]);
    navigation.dispose();
  });

  it("keeps the newest distinct external target when native companion events arrive late", async () => {
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
    const firstGuard = waitForGuard<boolean>();
    const secondGuard = waitForGuard<boolean>();
    const firstReached = waitForGuard<void>();
    const secondReached = waitForGuard<void>();
    const seen: WorkspaceRoute[] = [];
    const published: WorkspaceRoute[] = [];
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        (target: WorkspaceRoute) => {
          seen.push(target);
          if (seen.length === 1) {
            firstReached.resolve();
            return firstGuard.promise;
          }
          secondReached.resolve();
          return secondGuard.promise;
        },
        { isDirty: () => true },
      ),
    );
    navigation.subscribe((route) => published.push(route));

    const firstPair = nativePopstate(providers);
    await firstReached.promise;
    const secondPair = nativePopstate(fixtures);
    nativeHashchange(firstPair);
    nativeHashchange(secondPair);
    firstGuard.resolve(true);
    await secondReached.promise;
    expect(seen).toEqual([providers, fixtures]);
    const fixturesPublished = waitForRoute(navigation, fixtures);
    secondGuard.resolve(true);
    await fixturesPublished;

    expect(navigation.current).toEqual(fixtures);
    expect(window.location.hash).toBe(routeToHash(fixtures));
    expect(published).toEqual([fixtures]);
    navigation.dispose();
  });

  it("does not let an old native companion revive an in-app destination after fast settlement", async () => {
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
    const pair = nativePopstate(providers);
    await waitForRoute(navigation, providers);
    expect(navigation.current).toEqual(providers);

    expect(await navigation.navigate(fixtures)).toBe(true);
    nativeHashchange(pair);

    expect(navigation.current).toEqual(fixtures);
    expect(window.location.hash).toBe(routeToHash(fixtures));
    navigation.dispose();
  });

  it("prompts again for an intentional same-target retry after Keep editing", async () => {
    const overview: WorkspaceRoute = {
      kind: "overview",
      registrationId: "project",
    };
    const providers: WorkspaceRoute = {
      kind: "providers",
      registrationId: "project",
    };
    window.history.replaceState(null, "", routeToHash(overview));
    const navigation = new WorkspaceNavigation(window);
    const firstGuard = waitForGuard<boolean>();
    const secondGuard = waitForGuard<boolean>();
    const firstReached = waitForGuard<void>();
    const secondReached = waitForGuard<void>();
    let calls = 0;
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        () => {
          calls += 1;
          if (calls === 1) {
            firstReached.resolve();
            return firstGuard.promise;
          }
          secondReached.resolve();
          return secondGuard.promise;
        },
        { isDirty: () => true },
      ),
    );

    const firstOldURL = window.location.href;
    const firstURL = new URL(routeToHash(providers), firstOldURL).toString();
    window.history.pushState(null, "", firstURL);
    window.dispatchEvent(
      new HashChangeEvent("hashchange", {
        oldURL: firstOldURL,
        newURL: firstURL,
      }),
    );
    await firstReached.promise;
    firstGuard.resolve(false);
    await navigation.navigate(overview);

    const retryOldURL = window.location.href;
    const retryURL = new URL(routeToHash(providers), retryOldURL).toString();
    window.history.pushState(null, "", retryURL);
    window.dispatchEvent(
      new HashChangeEvent("hashchange", {
        oldURL: retryOldURL,
        newURL: retryURL,
      }),
    );
    await secondReached.promise;
    expect(calls).toBe(2);
    const providersPublished = waitForRoute(navigation, providers);
    secondGuard.resolve(true);
    await providersPublished;

    expect(navigation.current).toEqual(providers);
    navigation.dispose();
  });

  it("invalidates a pending external route when a distinct invalid hash arrives", async () => {
    const overview: WorkspaceRoute = {
      kind: "overview",
      registrationId: "project",
    };
    const providers: WorkspaceRoute = {
      kind: "providers",
      registrationId: "project",
    };
    window.history.replaceState(null, "", routeToHash(overview));
    const navigation = new WorkspaceNavigation(window);
    const guardResult = waitForGuard<boolean>();
    const guardReached = waitForGuard<void>();
    const published: WorkspaceRoute[] = [];
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        () => {
          guardReached.resolve();
          return guardResult.promise;
        },
        { isDirty: () => true },
      ),
    );
    navigation.subscribe((route) => published.push(route));

    nativePopstate(providers);
    await guardReached.promise;
    const invalidOldURL = window.location.href;
    const invalidURL = new URL(
      "#/invalid/route",
      window.location.href,
    ).toString();
    window.history.pushState(null, "", invalidURL);
    window.dispatchEvent(
      new HashChangeEvent("hashchange", {
        oldURL: invalidOldURL,
        newURL: invalidURL,
      }),
    );
    guardResult.resolve(true);
    await navigation.navigate(overview);

    expect(navigation.current).toEqual(overview);
    expect(published).toEqual([]);
    expect(window.location.hash).toBe(routeToHash(overview));
    navigation.dispose();
  });

  it("does not suppress a new active target after it was superseded by another pending route", async () => {
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
    const firstGuard = waitForGuard<boolean>();
    const secondGuard = waitForGuard<boolean>();
    const firstReached = waitForGuard<void>();
    const secondReached = waitForGuard<void>();
    const seen: WorkspaceRoute[] = [];
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        (target: WorkspaceRoute) => {
          seen.push(target);
          if (seen.length === 1) {
            firstReached.resolve();
            return firstGuard.promise;
          }
          secondReached.resolve();
          return secondGuard.promise;
        },
        { isDirty: () => true },
      ),
    );

    const firstOldURL = window.location.href;
    const firstURL = new URL(routeToHash(providers), firstOldURL).toString();
    window.history.pushState(null, "", firstURL);
    window.dispatchEvent(
      new HashChangeEvent("hashchange", {
        oldURL: firstOldURL,
        newURL: firstURL,
      }),
    );
    await firstReached.promise;

    const distinctOldURL = window.location.href;
    const distinctURL = new URL(
      routeToHash(fixtures),
      distinctOldURL,
    ).toString();
    window.history.pushState(null, "", distinctURL);
    window.dispatchEvent(
      new HashChangeEvent("hashchange", {
        oldURL: distinctOldURL,
        newURL: distinctURL,
      }),
    );
    const retryOldURL = window.location.href;
    const retryURL = new URL(routeToHash(providers), retryOldURL).toString();
    window.history.pushState(null, "", retryURL);
    window.dispatchEvent(
      new HashChangeEvent("hashchange", {
        oldURL: retryOldURL,
        newURL: retryURL,
      }),
    );

    firstGuard.resolve(true);
    await secondReached.promise;
    expect(seen).toEqual([providers, providers]);
    const providersPublished = waitForRoute(navigation, providers);
    secondGuard.resolve(true);
    await providersPublished;
    expect(navigation.current).toEqual(providers);
    navigation.dispose();
  });

  it("suppresses a queued external publication after disposal", async () => {
    const overview: WorkspaceRoute = {
      kind: "overview",
      registrationId: "project",
    };
    const providers: WorkspaceRoute = {
      kind: "providers",
      registrationId: "project",
    };
    window.history.replaceState(null, "", routeToHash(overview));
    const navigation = new WorkspaceNavigation(window);
    const guardResult = waitForGuard<boolean>();
    const guardReached = waitForGuard<void>();
    const published: WorkspaceRoute[] = [];
    navigation.registerDirtyGuard(
      "dirty-editor",
      Object.assign(
        () => {
          guardReached.resolve();
          return guardResult.promise;
        },
        { isDirty: () => true },
      ),
    );
    navigation.subscribe((route) => published.push(route));

    nativePopstate(providers);
    await guardReached.promise;
    const queuedNavigation = navigation.navigate({
      kind: "fixtures",
      registrationId: "project",
    });
    navigation.dispose();
    guardResult.resolve(true);
    await queuedNavigation;

    expect(navigation.current).toEqual(overview);
    expect(published).toEqual([]);
    expect(window.location.hash).toBe(routeToHash(overview));
  });
});

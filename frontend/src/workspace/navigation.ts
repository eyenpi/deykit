import { isValidWorkspaceRoute, routeFromHash, routeToHash } from "./routes";
import type { WorkspaceRoute } from "./routes";

export type DirtyNavigationGuard = ((
  target: WorkspaceRoute,
) => Promise<boolean>) & {
  isDirty: () => boolean;
};

type ExternalIntent = {
  route: WorkspaceRoute;
  hash: string;
  key: string;
  generation: number;
};

type NativeFragmentPair = {
  oldHash: string;
  hash: string;
  key: string;
  generation: number;
};

export interface WorkspaceViewState {
  selectedDatasetId?: string;
  selectedCaseId?: string;
  selectedDecisionId?: string;
  selectedProviderProfileId?: string;
  selectedFixtureId?: string;
  filter?: string;
  scrollTop?: number;
  inspectorOpen?: boolean;
}

/** Session-only view context, keyed by the local registration rather than project ID. */
export class WorkspaceSessionState {
  #byRegistration = new Map<string, WorkspaceViewState>();

  read(registrationId: string): WorkspaceViewState {
    return { ...this.#byRegistration.get(registrationId) };
  }

  update(
    registrationId: string,
    update: Partial<WorkspaceViewState>,
  ): WorkspaceViewState {
    const next = {
      ...this.#byRegistration.get(registrationId),
      ...update,
    };
    this.#byRegistration.set(registrationId, next);
    return { ...next };
  }

  clear(registrationId: string): void {
    this.#byRegistration.delete(registrationId);
  }
}

/**
 * Owns validated hash navigation and asks every dirty editor before changing
 * either the in-app route or a route received from Back/Forward/external links.
 */
export class WorkspaceNavigation {
  #browser: Window;
  #route: WorkspaceRoute;
  #admittedHash: string;
  #listeners = new Set<(route: WorkspaceRoute) => void>();
  #guards = new Map<string, DirtyNavigationGuard>();
  #externalCheckScheduled = false;
  #externalCheckRunning = false;
  #pendingExternal: ExternalIntent | undefined;
  #activeExternal: ExternalIntent | undefined;
  // Changed-fragment traversals are removed by their companion or at disposal.
  #nativeFragmentPairs: NativeFragmentPair[] = [];
  #intentGeneration = 0;
  #disposed = false;
  #transitionTail: Promise<void> = Promise.resolve();
  #onExternalNavigation: (event: Event) => void;
  #onBeforeUnload = (event: BeforeUnloadEvent) => {
    if (![...this.#guards.values()].some((guard) => guard.isDirty())) return;
    event.preventDefault();
    event.returnValue = "";
  };

  constructor(browser: Window = window) {
    this.#browser = browser;
    const parsed = routeFromHash(browser.location.hash);
    this.#route = parsed ?? { kind: "start" };
    this.#admittedHash = parsed
      ? browser.location.hash
      : routeToHash(this.#route);
    if (!parsed) browser.history.replaceState(null, "", this.#admittedHash);
    this.#onExternalNavigation = (event) => {
      const hash = this.#eventHash(event);
      const route = routeFromHash(hash);
      const key = route ? routeToHash(route) : `invalid:${hash}`;
      if (event.type === "hashchange") {
        const oldHash = this.#eventOldHash(event);
        const pairIndex = this.#nativeFragmentPairs.findIndex(
          (pair) =>
            pair.oldHash === oldHash && pair.hash === hash && pair.key === key,
        );
        if (pairIndex >= 0) {
          this.#nativeFragmentPairs.splice(pairIndex, 1);
          return;
        }
      }
      const generation = this.#receiveExternal(route, hash, key);
      if (
        event.type === "popstate" &&
        hash !== this.#admittedHash &&
        generation !== undefined
      ) {
        // Keep this movement's companion identity even if a newer intent starts first.
        this.#nativeFragmentPairs.push({
          oldHash: this.#admittedHash,
          hash,
          key,
          generation,
        });
      }
    };
    browser.addEventListener("hashchange", this.#onExternalNavigation);
    browser.addEventListener("popstate", this.#onExternalNavigation);
    browser.addEventListener("beforeunload", this.#onBeforeUnload);
  }

  get current(): WorkspaceRoute {
    return this.#route;
  }

  subscribe(listener: (route: WorkspaceRoute) => void): () => void {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }

  registerDirtyGuard(key: string, guard: DirtyNavigationGuard): () => void {
    this.#guards.set(key, guard);
    return () => {
      const current = this.#guards.get(key);
      if (current === guard) this.#guards.delete(key);
    };
  }

  async navigate(route: WorkspaceRoute): Promise<boolean> {
    if (this.#disposed || !isValidWorkspaceRoute(route)) return false;
    const generation = ++this.#intentGeneration;
    this.#pendingExternal = undefined;
    return this.#serialize(async () => {
      if (this.#disposed || generation !== this.#intentGeneration) return false;
      if (sameRoute(route, this.#route)) return true;
      if (!(await this.#confirmDirtyEditors(route))) return false;
      if (this.#disposed || generation !== this.#intentGeneration) return false;
      const hash = routeToHash(route);
      this.#browser.history.pushState(null, "", hash);
      this.#admittedHash = hash;
      this.#publish(route);
      return true;
    });
  }

  dispose(): void {
    this.#disposed = true;
    this.#intentGeneration += 1;
    this.#pendingExternal = undefined;
    this.#nativeFragmentPairs = [];
    this.#browser.removeEventListener("hashchange", this.#onExternalNavigation);
    this.#browser.removeEventListener("popstate", this.#onExternalNavigation);
    this.#browser.removeEventListener("beforeunload", this.#onBeforeUnload);
    this.#listeners.clear();
    this.#guards.clear();
  }

  #eventHash(event: Event): string {
    if (event.type !== "hashchange") return this.#browser.location.hash;
    const hashChange = event as HashChangeEvent;
    try {
      return new URL(hashChange.newURL).hash;
    } catch {
      return "";
    }
  }

  #eventOldHash(event: Event): string {
    const hashChange = event as HashChangeEvent;
    try {
      return new URL(hashChange.oldURL).hash;
    } catch {
      return "";
    }
  }

  #receiveExternal(
    route: WorkspaceRoute | null,
    hash: string,
    key: string,
  ): number | undefined {
    if (this.#disposed) return undefined;
    if (!route) {
      this.#intentGeneration += 1;
      this.#pendingExternal = undefined;
      this.#restoreAdmittedHash();
      return this.#intentGeneration;
    }
    if (
      this.#activeExternal?.key === key &&
      this.#activeExternal.generation === this.#intentGeneration
    ) {
      this.#restoreAdmittedHash();
      return this.#activeExternal.generation;
    }
    if (this.#pendingExternal?.key === key) {
      this.#restoreAdmittedHash();
      return this.#pendingExternal.generation;
    }
    const intent: ExternalIntent = {
      route,
      hash,
      key,
      generation: ++this.#intentGeneration,
    };
    this.#pendingExternal = intent;
    this.#restoreAdmittedHash();
    if (this.#externalCheckScheduled) return intent.generation;
    this.#externalCheckScheduled = true;
    queueMicrotask(() => {
      this.#externalCheckScheduled = false;
      void this.#acceptExternalRoute();
    });
    return intent.generation;
  }

  async #acceptExternalRoute(): Promise<void> {
    if (this.#disposed || this.#externalCheckRunning) return;
    this.#externalCheckRunning = true;
    try {
      while (!this.#disposed && this.#pendingExternal) {
        const pending = this.#pendingExternal;
        this.#pendingExternal = undefined;
        this.#activeExternal = pending;
        try {
          await this.#serialize(async () => {
            if (this.#disposed || pending.generation !== this.#intentGeneration)
              return;
            if (sameRoute(pending.route, this.#route)) {
              this.#admittedHash = pending.hash;
              this.#browser.history.replaceState(null, "", pending.hash);
              return;
            }
            if (!(await this.#confirmDirtyEditors(pending.route))) {
              if (
                !this.#disposed &&
                pending.generation === this.#intentGeneration
              )
                this.#restoreAdmittedHash();
              return;
            }
            if (this.#disposed || pending.generation !== this.#intentGeneration)
              return;
            this.#admittedHash = pending.hash;
            this.#browser.history.replaceState(null, "", pending.hash);
            this.#publish(pending.route);
          });
        } finally {
          if (this.#activeExternal === pending)
            this.#activeExternal = undefined;
        }
      }
    } finally {
      this.#externalCheckRunning = false;
      if (
        !this.#disposed &&
        this.#pendingExternal &&
        !this.#externalCheckScheduled
      ) {
        this.#externalCheckScheduled = true;
        queueMicrotask(() => {
          this.#externalCheckScheduled = false;
          void this.#acceptExternalRoute();
        });
      }
    }
  }

  async #confirmDirtyEditors(target: WorkspaceRoute): Promise<boolean> {
    for (const guard of this.#guards.values()) {
      if (guard.isDirty() && !(await guard(target))) return false;
    }
    return true;
  }

  #restoreAdmittedHash(): void {
    this.#browser.history.replaceState(null, "", this.#admittedHash);
  }

  #serialize<T>(transition: () => Promise<T>): Promise<T> {
    const next = this.#transitionTail.then(transition, transition);
    this.#transitionTail = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  }

  #publish(route: WorkspaceRoute): void {
    if (this.#disposed) return;
    this.#route = route;
    for (const listener of this.#listeners) listener(route);
  }
}

function sameRoute(left: WorkspaceRoute, right: WorkspaceRoute): boolean {
  return routeToHash(left) === routeToHash(right);
}

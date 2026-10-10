import { isValidWorkspaceRoute, routeFromHash, routeToHash } from "./routes";
import type { WorkspaceRoute } from "./routes";

export type DirtyNavigationGuard = ((target: WorkspaceRoute) => Promise<boolean>) & {
  isDirty: () => boolean;
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
  #pendingExternal: { route: WorkspaceRoute; hash: string; generation: number } | undefined;
  #intentGeneration = 0;
  #transitionTail: Promise<void> = Promise.resolve();
  #onExternalNavigation: () => void;
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
    this.#onExternalNavigation = () => {
      const hash = browser.location.hash;
      const route = routeFromHash(hash);
      const generation = ++this.#intentGeneration;
      this.#restoreAdmittedHash();
      if (!route) {
        this.#pendingExternal = undefined;
        return;
      }
      this.#pendingExternal = { route, hash, generation };
      if (this.#externalCheckScheduled) return;
      this.#externalCheckScheduled = true;
      queueMicrotask(() => {
        this.#externalCheckScheduled = false;
        void this.#acceptExternalRoute();
      });
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

  registerDirtyGuard(
    key: string,
    guard: DirtyNavigationGuard,
  ): () => void {
    this.#guards.set(key, guard);
    return () => {
      const current = this.#guards.get(key);
      if (current === guard) this.#guards.delete(key);
    };
  }

  async navigate(route: WorkspaceRoute): Promise<boolean> {
    if (!isValidWorkspaceRoute(route)) return false;
    const generation = ++this.#intentGeneration;
    return this.#serialize(async () => {
      if (generation !== this.#intentGeneration) return false;
      if (sameRoute(route, this.#route)) return true;
      if (!(await this.#confirmDirtyEditors(route))) return false;
      if (generation !== this.#intentGeneration) return false;
      const hash = routeToHash(route);
      this.#browser.history.pushState(null, "", hash);
      this.#admittedHash = hash;
      this.#publish(route);
      return true;
    });
  }

  dispose(): void {
    this.#browser.removeEventListener("hashchange", this.#onExternalNavigation);
    this.#browser.removeEventListener("popstate", this.#onExternalNavigation);
    this.#browser.removeEventListener("beforeunload", this.#onBeforeUnload);
    this.#listeners.clear();
    this.#guards.clear();
  }

  async #acceptExternalRoute(): Promise<void> {
    if (this.#externalCheckRunning) return;
    this.#externalCheckRunning = true;
    try {
      while (this.#pendingExternal) {
        const pending = this.#pendingExternal;
        this.#pendingExternal = undefined;
        await this.#serialize(async () => {
          if (pending.generation !== this.#intentGeneration) return;
          if (sameRoute(pending.route, this.#route)) {
            this.#admittedHash = pending.hash;
            this.#browser.history.replaceState(null, "", pending.hash);
            return;
          }
          if (!(await this.#confirmDirtyEditors(pending.route))) {
            if (pending.generation === this.#intentGeneration)
              this.#restoreAdmittedHash();
            return;
          }
          if (pending.generation !== this.#intentGeneration) return;
          this.#admittedHash = pending.hash;
          this.#browser.history.replaceState(null, "", pending.hash);
          this.#publish(pending.route);
        });
      }
    } finally {
      this.#externalCheckRunning = false;
      if (this.#pendingExternal && !this.#externalCheckScheduled) {
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
    this.#transitionTail = next.then(() => undefined, () => undefined);
    return next;
  }

  #publish(route: WorkspaceRoute): void {
    this.#route = route;
    for (const listener of this.#listeners) listener(route);
  }
}

function sameRoute(left: WorkspaceRoute, right: WorkspaceRoute): boolean {
  return routeToHash(left) === routeToHash(right);
}

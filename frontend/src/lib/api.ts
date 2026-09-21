// A thin, typed client for the fleet daemon's HTTP surface (ADR-0009,
// `cuttlefish.fleet.server`). Hand-written types mirroring the Python dataclasses
// that slice adds -- no OpenAPI-codegen machinery for five routes.

export type RoleStatus = "queued" | "working" | "blocked" | "done" | "failed";

export interface RoleDefinition {
  name: string;
  persona: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  root: string;
  secrets_scope: string;
  roles: RoleDefinition[];
  last_team_id: string | null;
  allow: string[][];
  running: boolean;
  status: Record<string, RoleStatus>;
}

export interface RoleStart {
  name: string;
  text: string;
}

export interface EpisodicEventView {
  seq: number;
  ts: string;
  event_type: string;
  payload: Record<string, unknown>;
}

export class FleetApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "FleetApiError";
  }
}

/** Thrown by `FleetClient.request` when `fetch` itself fails (daemon unreachable,
 * wrong base URL) -- distinct from `FleetApiError`, which means the daemon *did*
 * answer, just with an error status. */
export class FleetUnreachableError extends Error {
  constructor(baseUrl: string) {
    super(`couldn't reach the fleet daemon at ${baseUrl}`);
    this.name = "FleetUnreachableError";
  }
}

export class FleetClient {
  constructor(
    public readonly baseUrl: string,
    public readonly token: string,
  ) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          "content-type": "application/json",
          "x-cuttlefish-token": this.token,
          ...init?.headers,
        },
      });
    } catch {
      throw new FleetUnreachableError(this.baseUrl);
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      throw new FleetApiError(response.status, body.detail ?? response.statusText);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  listProjects(): Promise<{ projects: ProjectSummary[] }> {
    return this.request("/api/projects");
  }

  getProject(id: string): Promise<ProjectSummary> {
    return this.request(`/api/projects/${id}`);
  }

  getEvents(id: string): Promise<{ events: EpisodicEventView[] }> {
    return this.request(`/api/projects/${id}/events`);
  }

  registerProject(input: {
    name: string;
    root: string;
    secrets_scope?: string;
    roles: RoleDefinition[];
    allow?: string[][];
  }): Promise<ProjectSummary> {
    return this.request("/api/projects", { method: "POST", body: JSON.stringify(input) });
  }

  updateRoles(id: string, roles: RoleDefinition[]): Promise<ProjectSummary> {
    return this.request(`/api/projects/${id}/roles`, {
      method: "PATCH",
      body: JSON.stringify({ roles }),
    });
  }

  updateAllow(id: string, allow: string[][]): Promise<ProjectSummary> {
    return this.request(`/api/projects/${id}/allow`, {
      method: "PATCH",
      body: JSON.stringify({ allow }),
    });
  }

  deregisterProject(id: string): Promise<void> {
    return this.request(`/api/projects/${id}`, { method: "DELETE" });
  }

  startProject(id: string, roles: RoleStart[]): Promise<{ team_id: string }> {
    return this.request(`/api/projects/${id}/start`, {
      method: "POST",
      body: JSON.stringify({ roles }),
    });
  }

  stopProject(id: string): Promise<{ status: string }> {
    return this.request(`/api/projects/${id}/stop`, { method: "POST" });
  }

  steerProject(id: string, role: string, text: string): Promise<{ status: string }> {
    return this.request(`/api/projects/${id}/steer`, {
      method: "POST",
      body: JSON.stringify({ role, text }),
    });
  }
}

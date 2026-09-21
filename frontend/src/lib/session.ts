// Remembers the last daemon connection (base URL + token) in this browser only --
// a per-viewer convenience, never shared, safe to lose (the operator just
// re-enters it). The token itself never leaves the browser except as a header to
// the daemon it names, which is loopback-only by construction (ADR-0014/ADR-0009).

const STORAGE_KEY = "cuttlefish.fleet.connection";

export interface Connection {
  baseUrl: string;
  token: string;
}

export function loadConnection(): Connection | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed.baseUrl === "string" && typeof parsed.token === "string") {
      return parsed as Connection;
    }
    return null;
  } catch {
    return null;
  }
}

export function saveConnection(connection: Connection): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(connection));
  } catch {
    // A private window or blocked site data just means "don't remember it" --
    // the app still works for this one session, it just asks again next time.
  }
}

export function clearConnection(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // See saveConnection.
  }
}

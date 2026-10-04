/** Thin fetch wrapper: query params, JSON, and errors that carry the API's own message. */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

const BASE: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export function buildUrl(path: string, params?: Params): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") qs.set(key, String(value));
  }
  const query = qs.toString();
  return `${BASE}${path}${query ? `?${query}` : ""}`;
}

/** DRF errors are `{detail: "..."}` or `{field: ["message", ...]}`; flatten either to one readable sentence. */
export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    const parts = Object.entries(record).map(([field, msg]) => `${field}: ${Array.isArray(msg) ? msg.join(", ") : String(msg)}`);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

export async function getJson<T>(path: string, params?: Params, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), { signal, headers: { Accept: "application/json" } });
  } catch (cause) {
    if ((cause as Error).name === "AbortError") throw cause;
    throw new ApiError(0, "Could not reach the API. Is the backend running?");
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* an empty or non-JSON body is handled by the status check below */
  }
  if (!response.ok) throw new ApiError(response.status, errorMessage(body, `Request failed (${response.status})`));
  return body as T;
}

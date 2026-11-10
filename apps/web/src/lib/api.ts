const API_URL = "/backend";

export class ApiError extends Error {
  constructor(public readonly status: number, message = "API request failed") {
    super(message);
  }
}

async function csrfToken(): Promise<string> {
  await fetch(`${API_URL}/api/v1/auth/csrf/`, { credentials: "include" });
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith("csrftoken="))
    ?.split("=")[1] ?? "";
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") {
    headers.set("X-CSRFToken", await csrfToken());
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json() as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Some endpoints intentionally return no JSON body.
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

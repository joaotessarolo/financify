import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./api";

describe("apiFetch", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=test-token";
    vi.restoreAllMocks();
  });

  it("includes credentials without a CSRF round trip for GET requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch<{ ok: boolean }>("/api/v1/example/")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/v1/example/",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("fetches and sends the CSRF token for mutations", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/example/", { method: "POST", body: "{}" });
    const mutation = fetchMock.mock.calls[1];
    const headers = mutation[1]?.headers as Headers;
    expect(headers.get("X-CSRFToken")).toBe("test-token");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("exposes safe API errors to the interface", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Not found." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/v1/missing/")).rejects.toMatchObject({
      status: 404,
      message: "Not found.",
    } satisfies Partial<ApiError>);
  });
});

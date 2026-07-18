import { describe, expect, it, vi } from "vitest";
import { RunrApiError, RunrAssistedApplyApi } from "../../src/auth/browser-ports";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fixed Runr Assisted Apply API client", () => {
  it("uses only fixed endpoints and keeps bearer credentials off public exchange calls", async () => {
    const fetchPort = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ ok: true }),
    );
    const api = new RunrAssistedApplyApi("https://api.userunr.com/v1", fetchPort);

    await api.createConnectionRequest({
      code_challenge: "challenge",
      state: "state",
      installation_id: "installation",
      extension_version: "1.0.0",
    });
    await api.exchangeToken({
      request_id: "request",
      authorization_code: "code",
      code_verifier: "verifier",
    });
    await api.getSession("session-secret");
    await api.updatePreferences("session-secret", {
      permit_sensitive_autofill: true,
      permit_demographic_autofill: false,
    });

    expect(fetchPort.mock.calls.map(([url]) => url)).toEqual([
      "https://api.userunr.com/v1/assisted-apply/extension/connection-requests",
      "https://api.userunr.com/v1/assisted-apply/extension/token",
      "https://api.userunr.com/v1/assisted-apply/extension/session/verify",
      "https://api.userunr.com/v1/assisted-apply/extension/preferences",
    ]);
    const publicHeaders = fetchPort.mock.calls.slice(0, 2).map(([, init]) => new Headers(init?.headers));
    expect(publicHeaders.every((headers) => !headers.has("Authorization"))).toBe(true);
    const protectedHeaders = fetchPort.mock.calls.slice(2).map(([, init]) => new Headers(init?.headers));
    expect(protectedHeaders.every((headers) => headers.get("Authorization") === "Bearer session-secret"))
      .toBe(true);
    for (const [, init] of fetchPort.mock.calls) {
      expect(init).toMatchObject({ cache: "no-store", credentials: "omit", redirect: "error" });
    }
    expect(fetchPort.mock.calls[2]?.[1]).toMatchObject({ method: "POST", body: "{}" });
  });

  it("accepts HTTP only for explicit loopback testing", () => {
    expect(() => new RunrAssistedApplyApi("http://127.0.0.1:4174")).not.toThrow();
    expect(() => new RunrAssistedApplyApi("http://api.userunr.com/v1")).toThrow("HTTPS API");
  });

  it("invokes an injected fetch port without rebinding it to the API instance", async () => {
    let observedThis: unknown = "not-called";
    const fetchPort = function (this: unknown): Promise<Response> {
      observedThis = this;
      return Promise.resolve(jsonResponse({ ok: true }));
    };
    const api = new RunrAssistedApplyApi("https://api.userunr.com/v1", fetchPort);

    await api.createConnectionRequest({
      code_challenge: "challenge",
      state: "state",
      installation_id: "installation",
      extension_version: "1.0.0",
    });

    expect(observedThis).toBeUndefined();
  });

  it("preserves status for revoked-session handling without reflecting oversized server data", async () => {
    const fetchPort = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ error: { message: "Session revoked" } }, 401),
    );
    const api = new RunrAssistedApplyApi("https://api.userunr.com/v1", fetchPort);

    const error = await api.getSession("session-secret").catch((value: unknown) => value);
    expect(error).toBeInstanceOf(RunrApiError);
    expect(error).toMatchObject({ status: 401, message: "Session revoked" });
  });

  it("accepts an empty successful DELETE response", async () => {
    const fetchPort = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(null, { status: 204 }),
    );
    const api = new RunrAssistedApplyApi("https://api.userunr.com/v1", fetchPort);

    await expect(api.deleteSession("session-secret")).resolves.toBeUndefined();
    expect(fetchPort).toHaveBeenCalledWith(
      "https://api.userunr.com/v1/assisted-apply/extension/session",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("downloads a document only through the fixed no-store endpoint and grant header", async () => {
    const bytes = new TextEncoder().encode("%PDF-fixture");
    const fetchPort = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(bytes, {
      status: 200,
      headers: { "content-type": "application/pdf", "cache-control": "no-store" },
    }));
    const api = new RunrAssistedApplyApi("https://api.userunr.com/v1", fetchPort);

    const downloaded = await api.downloadDocument("session-secret", "aadoc-secret");
    expect(Array.from(downloaded)).toEqual(Array.from(bytes));
    const [url, init] = fetchPort.mock.calls[0] ?? [];
    expect(url).toBe("https://api.userunr.com/v1/assisted-apply/extension/document-grants/download");
    expect(init).toMatchObject({ method: "POST", body: "{}", cache: "no-store", credentials: "omit", redirect: "error" });
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer session-secret");
    expect(headers.get("X-Runr-Document-Grant")).toBe("aadoc-secret");
    expect(String(url)).not.toContain("aadoc-secret");
  });

  it("rejects non-PDF document responses before exposing bytes", async () => {
    const api = new RunrAssistedApplyApi("https://api.userunr.com/v1", async () =>
      new Response("secret", { status: 200, headers: { "content-type": "text/plain" } }),
    );
    await expect(api.downloadDocument("session-secret", "aadoc-secret")).rejects.toThrow("MIME");
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AssistedApplyApiPort,
  AuthStoragePort,
  CryptoPort,
  IdentityPort,
  StoredPendingConnection,
  StoredSessionSecret,
} from "../../src/auth/connection-service";
import { ExtensionConnectionService } from "../../src/auth/connection-service";

const NOW = Date.parse("2026-07-17T12:00:00.000Z");
const REQUEST_EXPIRY = "2026-07-17T12:05:00.000Z";
const SESSION_EXPIRY = "2026-07-17T12:15:00.000Z";
const REDIRECT_URI = "https://abcdefghijklmnopabcdefghijklmnop.chromiumapp.org/runr/connect";

function wirePreferences(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    permit_sensitive_autofill: false,
    permit_demographic_autofill: false,
    require_legal_answer_confirmation: true,
    revision: 1,
    updated_at: "2026-07-17T11:55:00.000Z",
    ...overrides,
  };
}

function wireSession(overrides: Record<string, unknown> = {}) {
  return {
    session_id: "ext_session_123",
    user_id: "user_123",
    display_name: "Ada Candidate",
    email: "ada@example.test",
    created_at: "2026-07-17T12:00:00.000Z",
    expires_at: SESSION_EXPIRY,
    ...overrides,
  };
}

function storedSecret(overrides: Partial<StoredSessionSecret> = {}): StoredSessionSecret {
  return {
    schemaVersion: 1,
    sessionToken: "runr_extension_session_token_123456789",
    session: {
      sessionId: "ext_session_123",
      userId: "user_123",
      displayName: "Ada Candidate",
      email: "ada@example.test",
      createdAt: "2026-07-17T12:00:00.000Z",
      expiresAt: SESSION_EXPIRY,
    },
    preferences: {
      schemaVersion: 1,
      permitSensitiveAutofill: false,
      permitDemographicAutofill: false,
      requireLegalAnswerConfirmation: true,
      revision: 1,
      updatedAt: "2026-07-17T11:55:00.000Z",
    },
    ...overrides,
  };
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

class MemoryStorage implements AuthStoragePort {
  pending: unknown;
  sessionSecret: unknown;
  installationId: unknown;
  hardenCount = 0;
  tabClearCount = 0;

  async hardenAccess(): Promise<void> {
    this.hardenCount += 1;
  }
  async readPendingConnection(): Promise<unknown> {
    return this.pending;
  }
  async writePendingConnection(value: StoredPendingConnection): Promise<void> {
    this.pending = structuredClone(value);
  }
  async clearPendingConnection(): Promise<void> {
    this.pending = undefined;
  }
  async readSessionSecret(): Promise<unknown> {
    return this.sessionSecret;
  }
  async writeSessionSecret(value: StoredSessionSecret): Promise<void> {
    this.sessionSecret = structuredClone(value);
  }
  async clearSessionSecret(): Promise<void> {
    this.sessionSecret = undefined;
  }
  async clearAssistedApplyTabState(): Promise<void> {
    this.tabClearCount += 1;
  }
  async readInstallationId(): Promise<unknown> {
    return this.installationId;
  }
  async writeInstallationId(value: string): Promise<void> {
    this.installationId = value;
  }
}

interface Fixture {
  service: ExtensionConnectionService;
  storage: MemoryStorage;
  identity: IdentityPort;
  api: AssistedApplyApiPort;
  crypto: CryptoPort;
  requestState: { value: string };
}

function fixture(
  callback?: (state: string) => string | undefined,
  options: { connectionExpiry?: string; sessionExpiry?: string } = {},
): Fixture {
  const storage = new MemoryStorage();
  const requestState = { value: "" };
  let randomCall = 0;
  const cryptoPort: CryptoPort = {
    randomBytes: vi.fn((length: number) => {
      randomCall += 1;
      return new Uint8Array(length).fill(randomCall);
    }),
    sha256: vi.fn(async () => new Uint8Array(32).fill(9)),
  };
  const api: AssistedApplyApiPort = {
    createConnectionRequest: vi.fn(async (input) => {
      requestState.value = input.state;
      return {
        request_id: "request_123",
        expires_at: options.connectionExpiry || REQUEST_EXPIRY,
      };
    }),
    exchangeToken: vi.fn(async () => ({
      session_token: "runr_extension_session_token_123456789",
      session: wireSession({ expires_at: options.sessionExpiry || SESSION_EXPIRY }),
      preferences: wirePreferences(),
    })),
    getSession: vi.fn(async () => ({
      session: wireSession(),
      preferences: wirePreferences(),
    })),
    deleteSession: vi.fn(async () => undefined),
    updatePreferences: vi.fn(async (_token, input) => ({
      preferences: wirePreferences({
        permit_sensitive_autofill: input.permit_sensitive_autofill,
        permit_demographic_autofill: input.permit_demographic_autofill,
        revision: 2,
      }),
    })),
  };
  const identity: IdentityPort = {
    getRedirectURL: vi.fn(() => REDIRECT_URI),
    launchWebAuthFlow: vi.fn(async () =>
      callback
        ? callback(requestState.value)
        : `${REDIRECT_URI}?request_id=request_123&code=one_time_code&state=${requestState.value}`,
    ),
  };
  const service = new ExtensionConnectionService({
    identity,
    api,
    crypto: cryptoPort,
    storage,
    clock: { now: () => NOW },
    frontendOrigin: "https://app.userunr.com",
    extensionVersion: "0.0.1",
  });
  return { service, storage, identity, api, crypto: cryptoPort, requestState };
}

describe("extension connection service", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("uses a click-driven interactive PKCE exchange and keeps secrets out of the panel result", async () => {
    const { service, storage, identity, api, crypto } = fixture();
    vi.mocked(identity.launchWebAuthFlow).mockImplementation(async (details) => {
      expect(storage.pending).toMatchObject({ requestId: "request_123" });
      expect(details).toEqual({
        interactive: true,
        url: "https://app.userunr.com/settings/assisted-apply?request_id=request_123",
      });
      const state = (storage.pending as StoredPendingConnection).state;
      return `${REDIRECT_URI}?request_id=request_123&code=one_time_code&state=${state}`;
    });

    const result = await service.connect();

    const request = vi.mocked(api.createConnectionRequest).mock.calls[0]?.[0];
    expect(request).toMatchObject({
      installation_id: expect.stringMatching(/^inst_[A-Za-z0-9_-]{43}$/u),
      extension_version: "0.0.1",
      state: expect.stringMatching(/^[A-Za-z0-9_-]{43}$/u),
      code_challenge: expect.stringMatching(/^[A-Za-z0-9_-]{43}$/u),
    });
    expect(vi.mocked(crypto.randomBytes).mock.calls.map(([length]) => length)).toEqual([32, 32, 32]);
    const verifier = vi.mocked(api.exchangeToken).mock.calls[0]?.[0].code_verifier;
    expect(crypto.sha256).toHaveBeenCalledWith(new TextEncoder().encode(verifier));
    expect(request?.code_challenge).toBe(base64Url(new Uint8Array(32).fill(9)));
    expect(identity.getRedirectURL).toHaveBeenCalledWith("runr/connect");
    expect(api.exchangeToken).toHaveBeenCalledWith({
      request_id: "request_123",
      authorization_code: "one_time_code",
      code_verifier: expect.stringMatching(/^[A-Za-z0-9_-]{43}$/u),
    });
    expect(storage.pending).toBeUndefined();
    expect(storage.installationId).toMatch(/^inst_/u);
    expect(storage.sessionSecret).toMatchObject({
      sessionToken: "runr_extension_session_token_123456789",
    });
    expect(result).toMatchObject({
      status: "connected",
      session: { userId: "user_123" },
      preferences: { requireLegalAnswerConfirmation: true },
    });
    expect(result).not.toHaveProperty("sessionToken");
    expect(storage.hardenCount).toBeGreaterThan(0);
  });

  it.each([
    ["missing callback", () => undefined],
    ["wrong state", () => `${REDIRECT_URI}?code=one_time_code&state=wrong`],
    [
      "wrong callback origin",
      (state: string) => `https://evil.example/runr/connect?code=one_time_code&state=${state}`,
    ],
    [
      "duplicate authorization code",
      (state: string) => `${REDIRECT_URI}?code=one&code=two&state=${state}`,
    ],
    [
      "mismatched request id",
      (state: string) => `${REDIRECT_URI}?request_id=other&code=one&state=${state}`,
    ],
    [
      "mixed success and error callback",
      (state: string) => `${REDIRECT_URI}?code=one&state=${state}&error=access_denied`,
    ],
  ])("rejects a %s and clears pending PKCE state", async (_name, callback) => {
    const { service, storage, api } = fixture(callback);
    await expect(service.connect()).rejects.toThrow();
    expect(api.exchangeToken).not.toHaveBeenCalled();
    expect(storage.pending).toBeUndefined();
    expect(storage.sessionSecret).toBeUndefined();
  });

  it("rejects an expired connection request before opening an auth window", async () => {
    const { service, identity, storage } = fixture(undefined, {
      connectionExpiry: "2026-07-17T11:59:59.000Z",
    });
    await expect(service.connect()).rejects.toThrow("expired connection request");
    expect(identity.launchWebAuthFlow).not.toHaveBeenCalled();
    expect(storage.sessionSecret).toBeUndefined();
  });

  it("rejects a chromiumapp suffix that is not an exact Chrome extension callback host", async () => {
    const { service, identity, api } = fixture();
    vi.mocked(identity.getRedirectURL).mockReturnValue(
      "https://evil.example.chromiumapp.org/runr/connect",
    );

    await expect(service.connect()).rejects.toThrow("invalid Runr callback URL");
    expect(api.createConnectionRequest).not.toHaveBeenCalled();
    expect(identity.launchWebAuthFlow).not.toHaveBeenCalled();
  });

  it("rejects a Chromium identity callback with an explicit non-default port", async () => {
    const { service, identity, api } = fixture();
    vi.mocked(identity.getRedirectURL).mockReturnValue(
      "https://abcdefghijklmnopabcdefghijklmnop.chromiumapp.org:444/runr/connect",
    );

    await expect(service.connect()).rejects.toThrow("invalid Runr callback URL");
    expect(api.createConnectionRequest).not.toHaveBeenCalled();
    expect(identity.launchWebAuthFlow).not.toHaveBeenCalled();
  });

  it("rejects malformed stored preference revision metadata", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret({
      preferences: {
        ...storedSecret().preferences,
        revision: 1,
        updatedAt: "",
      },
    });

    await expect(service.getConnection()).resolves.toMatchObject({ status: "disconnected" });
    expect(api.getSession).not.toHaveBeenCalled();
    expect(storage.sessionSecret).toBeUndefined();
  });

  it("coalesces concurrent Connect messages into one authorization exchange", async () => {
    const { service, api, identity } = fixture();

    const [first, second] = await Promise.all([service.connect(), service.connect()]);

    expect(first).toEqual(second);
    expect(api.createConnectionRequest).toHaveBeenCalledTimes(1);
    expect(api.exchangeToken).toHaveBeenCalledTimes(1);
    expect(identity.launchWebAuthFlow).toHaveBeenCalledTimes(1);
  });

  it("rejects an expired session response instead of storing its token", async () => {
    const { service, storage } = fixture(undefined, {
      sessionExpiry: "2026-07-17T11:59:59.000Z",
    });
    await expect(service.connect()).rejects.toThrow("expired extension session");
    expect(storage.sessionSecret).toBeUndefined();
    expect(storage.pending).toBeUndefined();
  });

  it("reconstructs and verifies connection state from storage after a worker restart", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();

    const result = await service.getConnection();

    expect(api.getSession).toHaveBeenCalledWith("runr_extension_session_token_123456789");
    expect(result).toMatchObject({ status: "connected", session: { sessionId: "ext_session_123" } });
  });

  it("clears a revoked remote session", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    vi.mocked(api.getSession).mockRejectedValue(Object.assign(new Error("revoked"), { status: 401 }));

    await expect(service.getConnection()).resolves.toMatchObject({ status: "expired" });
    expect(storage.sessionSecret).toBeUndefined();
  });

  it("preserves the local session when verification is forbidden rather than revoked", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    vi.mocked(api.getSession).mockRejectedValue(Object.assign(new Error("forbidden"), { status: 403 }));

    await expect(service.getConnection()).resolves.toMatchObject({
      status: "connected",
      warning: expect.any(String),
    });
    expect(storage.sessionSecret).toMatchObject({ sessionToken: expect.any(String) });
  });

  it("fails closed when session verification returns a different user", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    vi.mocked(api.getSession).mockResolvedValue({
      session: wireSession({ user_id: "user_other" }),
      preferences: wirePreferences(),
    });

    await expect(service.getConnection()).resolves.toMatchObject({ status: "expired" });
    expect(storage.sessionSecret).toBeUndefined();
  });

  it("rejects malformed stored secrets and does not send them to Runr", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = { sessionToken: "forged" };

    await expect(service.getConnection()).resolves.toMatchObject({ status: "disconnected" });
    expect(api.getSession).not.toHaveBeenCalled();
    expect(storage.sessionSecret).toBeUndefined();
  });

  it("revokes remotely before clearing local session and tab state", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    storage.pending = { stale: true };

    await expect(service.disconnect()).resolves.toMatchObject({ status: "disconnected" });

    expect(api.deleteSession).toHaveBeenCalledWith("runr_extension_session_token_123456789");
    expect(storage.sessionSecret).toBeUndefined();
    expect(storage.pending).toBeUndefined();
    expect(storage.tabClearCount).toBe(1);
  });

  it("does not claim disconnection when backend revocation cannot be confirmed", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    vi.mocked(api.deleteSession).mockRejectedValue(new Error("offline"));

    await expect(service.disconnect()).rejects.toThrow("offline");
    expect(storage.sessionSecret).toMatchObject({ sessionToken: expect.any(String) });
    expect(storage.tabClearCount).toBe(0);
  });

  it("does not treat a forbidden disconnect response as confirmed revocation", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    vi.mocked(api.deleteSession).mockRejectedValue(
      Object.assign(new Error("origin forbidden"), { status: 403 }),
    );

    await expect(service.disconnect()).rejects.toThrow("origin forbidden");
    expect(storage.sessionSecret).toMatchObject({ sessionToken: expect.any(String) });
    expect(storage.tabClearCount).toBe(0);
  });

  it("persists backend-confirmed optional preferences while legal review stays mandatory", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();

    const result = await service.updatePreferences({
      permitSensitiveAutofill: true,
      permitDemographicAutofill: true,
    });

    expect(api.updatePreferences).toHaveBeenCalledWith(
      "runr_extension_session_token_123456789",
      { permit_sensitive_autofill: true, permit_demographic_autofill: true },
    );
    expect(result.preferences).toMatchObject({
      permitSensitiveAutofill: true,
      permitDemographicAutofill: true,
      requireLegalAnswerConfirmation: true,
      revision: 2,
    });
    expect(storage.sessionSecret).toMatchObject({
      preferences: { requireLegalAnswerConfirmation: true },
    });
  });

  it("preserves the session when preference updates are forbidden", async () => {
    const { service, storage, api } = fixture();
    storage.sessionSecret = storedSecret();
    vi.mocked(api.updatePreferences).mockRejectedValue(
      Object.assign(new Error("origin forbidden"), { status: 403 }),
    );

    await expect(
      service.updatePreferences({
        permitSensitiveAutofill: true,
        permitDemographicAutofill: false,
      }),
    ).rejects.toThrow("origin forbidden");
    expect(storage.sessionSecret).toMatchObject({ sessionToken: expect.any(String) });
  });
});

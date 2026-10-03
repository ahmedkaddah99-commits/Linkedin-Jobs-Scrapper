import type {
  AssistedApplyPreferenceUpdate,
  AssistedApplyPreferences,
  ExtensionConnectionState,
  ExtensionSessionSummary,
} from "@runr/extension-messages";
import {
  DEFAULT_ASSISTED_APPLY_PREFERENCES,
  parseConnectionRequestResponse,
  parsePreferencesResponse,
  parseSessionResponse,
  parseSessionTokenResponse,
  type CreateConnectionRequestInput,
  type ExchangeTokenInput,
  type UpdatePreferencesInput,
} from "./protocol";

const AUTH_SCHEMA_VERSION = 1;
const RANDOM_TOKEN_BYTES = 32;
const INSTALLATION_ID_PREFIX = "inst_";
const CHROMIUM_CALLBACK_HOST = /^[a-p]{32}\.chromiumapp\.org$/u;

export interface IdentityPort {
  getRedirectURL(path: string): string;
  launchWebAuthFlow(details: { url: string; interactive: true }): Promise<string | undefined>;
}

export interface AssistedApplyApiPort {
  createConnectionRequest(input: CreateConnectionRequestInput): Promise<unknown>;
  exchangeToken(input: ExchangeTokenInput): Promise<unknown>;
  getSession(sessionToken: string): Promise<unknown>;
  deleteSession(sessionToken: string): Promise<void>;
  updatePreferences(sessionToken: string, input: UpdatePreferencesInput): Promise<unknown>;
}

export interface CryptoPort {
  randomBytes(length: number): Uint8Array;
  sha256(value: Uint8Array): Promise<Uint8Array>;
}

export interface AuthStoragePort {
  hardenAccess(): Promise<void>;
  readPendingConnection(): Promise<unknown>;
  writePendingConnection(value: StoredPendingConnection): Promise<void>;
  clearPendingConnection(): Promise<void>;
  readSessionSecret(): Promise<unknown>;
  writeSessionSecret(value: StoredSessionSecret): Promise<void>;
  clearSessionSecret(): Promise<void>;
  clearAssistedApplyTabState(): Promise<void>;
  readInstallationId(): Promise<unknown>;
  writeInstallationId(value: string): Promise<void>;
}

export interface ClockPort {
  now(): number;
}

export interface ConnectionServiceOptions {
  identity: IdentityPort;
  api: AssistedApplyApiPort;
  crypto: CryptoPort;
  storage: AuthStoragePort;
  clock: ClockPort;
  frontendOrigin: string;
  extensionVersion: string;
}

export interface StoredPendingConnection {
  schemaVersion: 1;
  requestId: string;
  state: string;
  codeVerifier: string;
  redirectUri: string;
  expiresAt: string;
}

export interface StoredSessionSecret {
  schemaVersion: 1;
  sessionToken: string;
  session: ExtensionSessionSummary;
  preferences: AssistedApplyPreferences;
}

interface StatusError extends Error {
  status?: number;
}

function cloneDefaultPreferences(): AssistedApplyPreferences {
  return { ...DEFAULT_ASSISTED_APPLY_PREFERENCES };
}

function disconnected(
  status: "disconnected" | "expired" = "disconnected",
  warning?: string,
): ExtensionConnectionState {
  const connection: ExtensionConnectionState = {
    status,
    session: null,
    preferences: cloneDefaultPreferences(),
  };
  if (warning) connection.warning = warning;
  return connection;
}

function connected(secret: StoredSessionSecret, warning?: string): ExtensionConnectionState {
  const connection: ExtensionConnectionState = {
    status: "connected",
    session: { ...secret.session },
    preferences: { ...secret.preferences },
  };
  if (warning) connection.warning = warning;
  return connection;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && Number.isFinite(Date.parse(value));
}

function isPreferences(value: unknown): value is AssistedApplyPreferences {
  if (!isRecord(value)) return false;
  const revision = value.revision;
  const updatedAt = value.updatedAt;
  return (
    value.schemaVersion === 1 &&
    typeof value.permitSensitiveAutofill === "boolean" &&
    typeof value.permitDemographicAutofill === "boolean" &&
    value.requireLegalAnswerConfirmation === true &&
    typeof revision === "number" &&
    Number.isInteger(revision) &&
    revision >= 0 &&
    (revision === 0 ? updatedAt === "" : isIsoDate(updatedAt))
  );
}

function isSessionSummary(value: unknown): value is ExtensionSessionSummary {
  if (!isRecord(value)) return false;
  return (
    typeof value.sessionId === "string" &&
    value.sessionId.length > 0 &&
    typeof value.userId === "string" &&
    value.userId.length > 0 &&
    isIsoDate(value.expiresAt) &&
    (value.createdAt === undefined || isIsoDate(value.createdAt)) &&
    (value.displayName === undefined || typeof value.displayName === "string") &&
    (value.email === undefined || typeof value.email === "string")
  );
}

export function isStoredPendingConnection(value: unknown): value is StoredPendingConnection {
  if (!isRecord(value)) return false;
  return (
    value.schemaVersion === AUTH_SCHEMA_VERSION &&
    typeof value.requestId === "string" &&
    value.requestId.length > 0 &&
    typeof value.state === "string" &&
    value.state.length >= 43 &&
    typeof value.codeVerifier === "string" &&
    value.codeVerifier.length >= 43 &&
    typeof value.redirectUri === "string" &&
    value.redirectUri.length > 0 &&
    isIsoDate(value.expiresAt)
  );
}

export function isStoredSessionSecret(value: unknown): value is StoredSessionSecret {
  if (!isRecord(value)) return false;
  return (
    value.schemaVersion === AUTH_SCHEMA_VERSION &&
    typeof value.sessionToken === "string" &&
    value.sessionToken.length >= 20 &&
    isSessionSummary(value.session) &&
    isPreferences(value.preferences)
  );
}

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function parseFrontendOrigin(value: string): string {
  const url = new URL(value);
  const localTestingOrigin =
    url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost");
  if (url.protocol !== "https:" && !localTestingOrigin) {
    throw new Error("Runr Assisted Apply requires an HTTPS frontend origin.");
  }
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("Runr Assisted Apply frontend configuration must be an origin.");
  }
  return url.origin;
}

function validateRedirectUri(value: string): URL {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    !CHROMIUM_CALLBACK_HOST.test(url.hostname) ||
    url.pathname !== "/runr/connect" ||
    url.username ||
    url.password ||
    url.port ||
    url.search ||
    url.hash
  ) {
    throw new Error("Chrome returned an invalid Runr callback URL.");
  }
  return url;
}

function parseCallback(
  value: string | undefined,
  expectedRedirectUri: string,
  expectedState: string,
  expectedRequestId: string,
): string {
  if (!value) throw new Error("Runr connection was cancelled before authorization completed.");
  const callback = new URL(value);
  const expected = new URL(expectedRedirectUri);
  if (
    callback.origin !== expected.origin ||
    callback.pathname !== expected.pathname ||
    callback.username ||
    callback.password ||
    callback.hash
  ) {
    throw new Error("Runr returned an unexpected authorization callback.");
  }
  const codes = callback.searchParams.getAll("code");
  const states = callback.searchParams.getAll("state");
  const requestIds = callback.searchParams.getAll("request_id");
  const errors = callback.searchParams.getAll("error");
  if (
    codes.length !== 1 ||
    states.length !== 1 ||
    requestIds.length > 1 ||
    errors.length > 0 ||
    !codes[0] ||
    codes[0].length > 4096 ||
    states[0] !== expectedState ||
    (requestIds.length === 1 && requestIds[0] !== expectedRequestId)
  ) {
    throw new Error("Runr returned an invalid authorization callback.");
  }
  return codes[0];
}

function isSessionGone(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const status = (error as StatusError).status;
  return status === 401;
}

function isInstallationId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    new RegExp(`^${INSTALLATION_ID_PREFIX}[A-Za-z0-9_-]{43}$`, "u").test(value)
  );
}

export class ExtensionConnectionService {
  private readonly identity: IdentityPort;
  private readonly api: AssistedApplyApiPort;
  private readonly crypto: CryptoPort;
  private readonly storage: AuthStoragePort;
  private readonly clock: ClockPort;
  private readonly frontendOrigin: string;
  private readonly extensionVersion: string;
  private connectOperation: Promise<ExtensionConnectionState> | null = null;

  constructor(options: ConnectionServiceOptions) {
    this.identity = options.identity;
    this.api = options.api;
    this.crypto = options.crypto;
    this.storage = options.storage;
    this.clock = options.clock;
    this.frontendOrigin = parseFrontendOrigin(options.frontendOrigin);
    this.extensionVersion = String(options.extensionVersion || "").trim();
    if (!this.extensionVersion || this.extensionVersion.length > 64) {
      throw new Error("The extension version is unavailable.");
    }
  }

  async initialize(): Promise<void> {
    await this.storage.hardenAccess();
  }

  private randomToken(): string {
    const bytes = this.crypto.randomBytes(RANDOM_TOKEN_BYTES);
    if (!(bytes instanceof Uint8Array) || bytes.byteLength !== RANDOM_TOKEN_BYTES) {
      throw new Error("Secure random generation failed.");
    }
    return encodeBase64Url(bytes);
  }

  private async getInstallationId(): Promise<string> {
    const current = await this.storage.readInstallationId();
    if (isInstallationId(current)) return current;
    const installationId = `${INSTALLATION_ID_PREFIX}${this.randomToken()}`;
    await this.storage.writeInstallationId(installationId);
    return installationId;
  }

  private async readValidSession(): Promise<StoredSessionSecret | null> {
    const value = await this.storage.readSessionSecret();
    if (value === undefined || value === null) return null;
    if (!isStoredSessionSecret(value)) {
      await this.storage.clearSessionSecret();
      return null;
    }
    return value;
  }

  async getConnection(): Promise<ExtensionConnectionState> {
    await this.initialize();
    const pending = await this.storage.readPendingConnection();
    if (
      pending !== undefined &&
      (!isStoredPendingConnection(pending) || Date.parse(pending.expiresAt) <= this.clock.now())
    ) {
      await this.storage.clearPendingConnection();
    }

    const secret = await this.readValidSession();
    if (!secret) return disconnected();
    if (Date.parse(secret.session.expiresAt) <= this.clock.now()) {
      await this.storage.clearSessionSecret();
      return disconnected("expired", "Your Runr extension session expired. Connect again to continue.");
    }

    try {
      const refreshed = parseSessionResponse(
        await this.api.getSession(secret.sessionToken),
        this.clock.now(),
      );
      if (
        refreshed.session.sessionId !== secret.session.sessionId ||
        refreshed.session.userId !== secret.session.userId
      ) {
        await this.storage.clearSessionSecret();
        return disconnected(
          "expired",
          "Runr returned a different account for this extension session. Connect again.",
        );
      }
      const nextSecret: StoredSessionSecret = {
        schemaVersion: AUTH_SCHEMA_VERSION,
        sessionToken: secret.sessionToken,
        session: refreshed.session,
        preferences: refreshed.preferences,
      };
      await this.storage.writeSessionSecret(nextSecret);
      return connected(nextSecret);
    } catch (error) {
      if (isSessionGone(error)) {
        await this.storage.clearSessionSecret();
        return disconnected("expired", "This Runr extension session is no longer active.");
      }
      return connected(secret, "Runr could not verify the connection just now.");
    }
  }

  async connect(): Promise<ExtensionConnectionState> {
    if (this.connectOperation) return this.connectOperation;
    const operation = this.connectOnce();
    this.connectOperation = operation;
    try {
      return await operation;
    } finally {
      if (this.connectOperation === operation) this.connectOperation = null;
    }
  }

  private async connectOnce(): Promise<ExtensionConnectionState> {
    await this.initialize();
    const existing = await this.readValidSession();
    if (existing && Date.parse(existing.session.expiresAt) > this.clock.now()) {
      return connected(existing);
    }
    await this.storage.clearSessionSecret();
    await this.storage.clearPendingConnection();

    const state = this.randomToken();
    const codeVerifier = this.randomToken();
    const challengeBytes = await this.crypto.sha256(new TextEncoder().encode(codeVerifier));
    if (!(challengeBytes instanceof Uint8Array) || challengeBytes.byteLength !== 32) {
      throw new Error("PKCE challenge generation failed.");
    }
    const codeChallenge = encodeBase64Url(challengeBytes);
    const redirectUri = this.identity.getRedirectURL("runr/connect");
    validateRedirectUri(redirectUri);
    const installationId = await this.getInstallationId();

    const connectionRequest = parseConnectionRequestResponse(
      await this.api.createConnectionRequest({
        code_challenge: codeChallenge,
        state,
        installation_id: installationId,
        extension_version: this.extensionVersion,
      }),
      this.clock.now(),
    );
    const pending: StoredPendingConnection = {
      schemaVersion: AUTH_SCHEMA_VERSION,
      requestId: connectionRequest.requestId,
      state,
      codeVerifier,
      redirectUri,
      expiresAt: connectionRequest.expiresAt,
    };
    await this.storage.writePendingConnection(pending);

    try {
      const authUrl = new URL("/settings/assisted-apply", this.frontendOrigin);
      authUrl.searchParams.set("request_id", pending.requestId);
      const callback = await this.identity.launchWebAuthFlow({
        url: authUrl.toString(),
        interactive: true,
      });
      if (Date.parse(pending.expiresAt) <= this.clock.now()) {
        throw new Error("The Runr connection request expired before it was completed.");
      }
      const authorizationCode = parseCallback(
        callback,
        pending.redirectUri,
        pending.state,
        pending.requestId,
      );
      const token = parseSessionTokenResponse(
        await this.api.exchangeToken({
          request_id: pending.requestId,
          authorization_code: authorizationCode,
          code_verifier: pending.codeVerifier,
        }),
        this.clock.now(),
      );
      const secret: StoredSessionSecret = {
        schemaVersion: AUTH_SCHEMA_VERSION,
        sessionToken: token.sessionToken,
        session: token.session,
        preferences: token.preferences,
      };
      await this.storage.writeSessionSecret(secret);
      return connected(secret);
    } finally {
      await this.storage.clearPendingConnection();
    }
  }

  async disconnect(): Promise<ExtensionConnectionState> {
    await this.initialize();
    const secret = await this.readValidSession();
    if (secret) {
      try {
        await this.api.deleteSession(secret.sessionToken);
      } catch (error) {
        if (!isSessionGone(error)) throw error;
      }
    }
    await this.storage.clearPendingConnection();
    await this.storage.clearSessionSecret();
    await this.storage.clearAssistedApplyTabState();
    return disconnected();
  }

  async updatePreferences(
    update: AssistedApplyPreferenceUpdate,
  ): Promise<ExtensionConnectionState> {
    await this.initialize();
    const secret = await this.readValidSession();
    if (!secret || Date.parse(secret.session.expiresAt) <= this.clock.now()) {
      await this.storage.clearSessionSecret();
      throw new Error("Connect the extension to Runr before changing these preferences.");
    }
    try {
      const preferences = parsePreferencesResponse(
        await this.api.updatePreferences(secret.sessionToken, {
          permit_sensitive_autofill: update.permitSensitiveAutofill,
          permit_demographic_autofill: update.permitDemographicAutofill,
        }),
      );
      const nextSecret: StoredSessionSecret = { ...secret, preferences };
      await this.storage.writeSessionSecret(nextSecret);
      return connected(nextSecret);
    } catch (error) {
      if (isSessionGone(error)) await this.storage.clearSessionSecret();
      throw error;
    }
  }
}

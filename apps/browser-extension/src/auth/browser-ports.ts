import { browser } from "wxt/browser";
import type {
  AssistedApplyApiPort,
  AuthStoragePort,
  CryptoPort,
  IdentityPort,
  StoredPendingConnection,
  StoredSessionSecret,
} from "./connection-service";
import type {
  CreateConnectionRequestInput,
  ExchangeTokenInput,
  UpdatePreferencesInput,
} from "./protocol";

export const PENDING_CONNECTION_KEY = "runr:assisted-apply:pending:v1";
export const SESSION_SECRET_KEY = "runr:assisted-apply:session:v1";
export const INSTALLATION_ID_KEY = "runr:assisted-apply:installation:v1";
const TAB_STATE_PREFIX = "assisted-apply-tab:";

const CONNECTION_REQUEST_PATH = "/assisted-apply/extension/connection-requests";
const TOKEN_PATH = "/assisted-apply/extension/token";
const SESSION_PATH = "/assisted-apply/extension/session";
const SESSION_VERIFY_PATH = "/assisted-apply/extension/session/verify";
const PREFERENCES_PATH = "/assisted-apply/extension/preferences";

export class RunrApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "RunrApiError";
    this.status = status;
  }
}

type FetchPort = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function normalizeApiBase(value: string): string {
  const url = new URL(value);
  const isLoopback =
    url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost");
  if (url.protocol !== "https:" && !isLoopback) {
    throw new Error("Runr Assisted Apply requires an HTTPS API.");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("Runr Assisted Apply API configuration is invalid.");
  }
  return url.toString().replace(/\/$/u, "");
}

function safeErrorMessage(value: unknown, fallback: string): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return fallback;
  const error = (value as { error?: unknown }).error;
  if (!error || typeof error !== "object" || Array.isArray(error)) return fallback;
  const message = (error as { message?: unknown }).message;
  return typeof message === "string" && message.length > 0 && message.length <= 512
    ? message
    : fallback;
}

export class RunrAssistedApplyApi implements AssistedApplyApiPort {
  private readonly apiBase: string;
  private readonly fetchPort: FetchPort;

  constructor(
    apiBase: string,
    fetchPort: FetchPort = globalThis.fetch.bind(globalThis),
  ) {
    this.apiBase = normalizeApiBase(apiBase);
    this.fetchPort = fetchPort;
  }

  private url(path: string): string {
    return `${this.apiBase}${path}`;
  }

  async request(
    path: string,
    method: "GET" | "POST" | "PUT" | "DELETE",
    body?: unknown,
    sessionToken?: string,
  ): Promise<unknown> {
    const headers = new Headers({ Accept: "application/json" });
    if (body !== undefined) headers.set("Content-Type", "application/json");
    if (sessionToken) headers.set("Authorization", `Bearer ${sessionToken}`);
    const fetchPort = this.fetchPort;
    const response = await fetchPort(this.url(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
    });
    if (response.status === 204) {
      if (!response.ok) throw new RunrApiError("Runr rejected the extension request.", response.status);
      return null;
    }

    let payload: unknown = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.toLowerCase().includes("application/json")) {
      try {
        payload = await response.json();
      } catch {
        throw new RunrApiError("Runr returned an unreadable response.", response.status);
      }
    }
    if (!response.ok) {
      throw new RunrApiError(
        safeErrorMessage(payload, "Runr rejected the extension request."),
        response.status,
      );
    }
    if (payload === null) throw new RunrApiError("Runr returned an invalid response.", response.status);
    return payload;
  }

  createConnectionRequest(input: CreateConnectionRequestInput): Promise<unknown> {
    return this.request(CONNECTION_REQUEST_PATH, "POST", input);
  }

  exchangeToken(input: ExchangeTokenInput): Promise<unknown> {
    return this.request(TOKEN_PATH, "POST", input);
  }

  getSession(sessionToken: string): Promise<unknown> {
    // A body-bearing POST keeps Chrome's browser-controlled extension Origin on
    // the wire after an MV3 worker restart. Privileged extension GET requests
    // can omit Origin, which would make origin-bound session verification unsafe.
    return this.request(SESSION_VERIFY_PATH, "POST", {}, sessionToken);
  }

  getApplicationPackage(sessionToken: string, packageId: string): Promise<unknown> {
    // A body-bearing POST preserves Chrome's extension Origin. A privileged
    // extension GET may omit Origin, which is required for origin-bound
    // package authorization on the API.
    return this.request(
      "/assisted-apply/extension/packages",
      "POST",
      { package_id: packageId },
      sessionToken,
    );
  }

  async deleteSession(sessionToken: string): Promise<void> {
    await this.request(SESSION_PATH, "DELETE", undefined, sessionToken);
  }

  updatePreferences(sessionToken: string, input: UpdatePreferencesInput): Promise<unknown> {
    return this.request(PREFERENCES_PATH, "PUT", input, sessionToken);
  }

  async downloadDocument(
    sessionToken: string,
    grantToken: string,
    expectedMimeType: "application/pdf" | "application/vnd.openxmlformats-officedocument.wordprocessingml.document" = "application/pdf",
  ): Promise<Uint8Array> {
    const response = await this.fetchPort(this.url("/assisted-apply/extension/document-grants/download"), {
      method: "POST",
      headers: new Headers({
        Accept: expectedMimeType,
        Authorization: `Bearer ${sessionToken}`,
        "Content-Type": "application/json",
        "X-Runr-Document-Grant": grantToken,
      }),
      body: "{}",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
    });
    if (!response.ok) {
      throw new RunrApiError("Runr rejected the one-time document download.", response.status);
    }
    if ((response.headers.get("content-type") || "").split(";", 1)[0]?.trim() !== expectedMimeType) {
      throw new RunrApiError("Runr returned an invalid document MIME type.", response.status);
    }
    return new Uint8Array(await response.arrayBuffer());
  }
}

export class BrowserIdentityPort implements IdentityPort {
  getRedirectURL(path: string): string {
    return browser.identity.getRedirectURL(path);
  }

  launchWebAuthFlow(details: { url: string; interactive: true }): Promise<string | undefined> {
    return browser.identity.launchWebAuthFlow(details);
  }
}

export class BrowserCryptoPort implements CryptoPort {
  randomBytes(length: number): Uint8Array {
    return crypto.getRandomValues(new Uint8Array(length));
  }

  async sha256(value: Uint8Array): Promise<Uint8Array> {
    const bytes = new Uint8Array(value.byteLength);
    bytes.set(value);
    const digest = await crypto.subtle.digest("SHA-256", bytes.buffer);
    return new Uint8Array(digest);
  }
}

export class BrowserAuthStorage implements AuthStoragePort {
  private hardening: Promise<void> | null = null;

  hardenAccess(): Promise<void> {
    this.hardening ??= Promise.all([
      browser.storage.session.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }),
      browser.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }),
    ]).then(() => undefined);
    return this.hardening;
  }

  async readPendingConnection(): Promise<unknown> {
    const values = await browser.storage.session.get(PENDING_CONNECTION_KEY);
    return values[PENDING_CONNECTION_KEY];
  }

  writePendingConnection(value: StoredPendingConnection): Promise<void> {
    return browser.storage.session.set({ [PENDING_CONNECTION_KEY]: value });
  }

  clearPendingConnection(): Promise<void> {
    return browser.storage.session.remove(PENDING_CONNECTION_KEY);
  }

  async readSessionSecret(): Promise<unknown> {
    const values = await browser.storage.session.get(SESSION_SECRET_KEY);
    return values[SESSION_SECRET_KEY];
  }

  writeSessionSecret(value: StoredSessionSecret): Promise<void> {
    return browser.storage.session.set({ [SESSION_SECRET_KEY]: value });
  }

  clearSessionSecret(): Promise<void> {
    return browser.storage.session.remove(SESSION_SECRET_KEY);
  }

  async clearAssistedApplyTabState(): Promise<void> {
    const values = await browser.storage.session.get(null);
    const keys = Object.keys(values).filter((key) => key.startsWith(TAB_STATE_PREFIX));
    if (keys.length > 0) await browser.storage.session.remove(keys);
  }

  async readInstallationId(): Promise<unknown> {
    const values = await browser.storage.local.get(INSTALLATION_ID_KEY);
    return values[INSTALLATION_ID_KEY];
  }

  writeInstallationId(value: string): Promise<void> {
    return browser.storage.local.set({ [INSTALLATION_ID_KEY]: value });
  }
}

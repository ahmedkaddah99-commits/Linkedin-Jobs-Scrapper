import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const fixturePath = join(currentDirectory, "fixtures", "greenhouse-application.html");
const extensionOriginPattern = /^chrome-extension:\/\/([a-p]{32})$/u;

const connections = new Map();
const sessions = new Map();
const counters = {
  connectionRequests: 0,
  authorizationVisits: 0,
  tokenExchanges: 0,
  sessionReads: 0,
  preferenceUpdates: 0,
  revocationRequests: 0,
  revocationInFlight: false,
  revocations: 0,
};

function futureIso(milliseconds) {
  return new Date(Date.now() + milliseconds).toISOString();
}

function json(response, status, payload, origin = "") {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "access-control-allow-headers": "Authorization, Content-Type",
    "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS",
    ...(origin ? { "access-control-allow-origin": origin, vary: "Origin" } : {}),
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(body),
    "content-type": "application/json; charset=utf-8",
  });
  response.end(body);
}

function noContent(response, origin = "") {
  response.writeHead(204, {
    "access-control-allow-headers": "Authorization, Content-Type",
    "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS",
    ...(origin ? { "access-control-allow-origin": origin, vary: "Origin" } : {}),
    "cache-control": "no-store",
  });
  response.end();
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8");
  const value = raw ? JSON.parse(raw) : {};
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected a JSON object.");
  }
  return value;
}

function base64UrlSha256(value) {
  return createHash("sha256").update(value, "utf8").digest("base64url");
}

function bearerToken(request) {
  const authorization = String(request.headers.authorization || "");
  return authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
}

function preferences(record) {
  return {
    schema_version: 1,
    permit_sensitive_autofill: record.permitSensitiveAutofill,
    permit_demographic_autofill: record.permitDemographicAutofill,
    require_legal_answer_confirmation: true,
    revision: record.preferenceRevision,
    updated_at: record.preferenceUpdatedAt,
  };
}

function session(record) {
  return {
    session_id: record.requestId,
    user_id: "user_fixture_candidate",
    expires_at: record.sessionExpiresAt,
    created_at: record.activatedAt,
    display_name: "Fixture Candidate",
    email: "fixture.candidate@example.com",
  };
}

function activeRecord(request, response, origin) {
  const token = bearerToken(request);
  const record = sessions.get(token);
  if (!record || record.status !== "active" || record.origin !== origin) {
    json(response, 401, { error: { code: "unauthorized", message: "Session is inactive." } }, origin);
    return null;
  }
  return record;
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", "http://127.0.0.1:4174");
  const origin = String(request.headers.origin || "");

  try {
    if (request.method === "OPTIONS") {
      noContent(response, origin);
      return;
    }

    if (request.method === "GET" && url.pathname === "/greenhouse-application.html") {
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      createReadStream(fixturePath).pipe(response);
      return;
    }

    if (request.method === "GET" && url.pathname === "/__test/state") {
      json(response, 200, {
        ...counters,
        activeSessions: [...sessions.values()].filter((item) => item.status === "active").length,
      });
      return;
    }

    if (
      request.method === "POST" &&
      url.pathname === "/assisted-apply/extension/connection-requests"
    ) {
      const extensionMatch = extensionOriginPattern.exec(origin);
      if (!extensionMatch) {
        json(response, 403, { error: { code: "forbidden", message: "Extension origin required." } });
        return;
      }
      const payload = await readJson(request);
      counters.connectionRequests += 1;
      const requestId = `aareq_fixture_${String(counters.connectionRequests).padStart(4, "0")}`;
      const record = {
        requestId,
        origin,
        extensionId: extensionMatch[1],
        state: String(payload.state || ""),
        challenge: String(payload.code_challenge || ""),
        status: "pending",
        authorizationCode: `aaac_fixture_${requestId}`,
        permitSensitiveAutofill: false,
        permitDemographicAutofill: false,
        preferenceRevision: 1,
        preferenceUpdatedAt: new Date().toISOString(),
      };
      connections.set(requestId, record);
      json(
        response,
        201,
        { request_id: requestId, expires_at: futureIso(10 * 60 * 1000) },
        origin,
      );
      return;
    }

    if (request.method === "GET" && url.pathname === "/settings/assisted-apply") {
      counters.authorizationVisits += 1;
      const requestId = String(url.searchParams.get("request_id") || "");
      const record = connections.get(requestId);
      if (!record || record.status !== "pending") {
        response.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
        response.end("Connection request is unavailable.");
        return;
      }
      record.status = "authorized";
      const callback = new URL(
        `https://${record.extensionId}.chromiumapp.org/runr/connect`,
      );
      callback.searchParams.set("request_id", record.requestId);
      callback.searchParams.set("code", record.authorizationCode);
      callback.searchParams.set("state", record.state);
      response.writeHead(302, { location: callback.toString(), "cache-control": "no-store" });
      response.end();
      return;
    }

    if (request.method === "POST" && url.pathname === "/assisted-apply/extension/token") {
      const payload = await readJson(request);
      const record = connections.get(String(payload.request_id || ""));
      if (
        !record ||
        record.status !== "authorized" ||
        record.origin !== origin ||
        record.authorizationCode !== payload.authorization_code ||
        record.challenge !== base64UrlSha256(String(payload.code_verifier || ""))
      ) {
        json(response, 403, { error: { code: "forbidden", message: "Exchange rejected." } }, origin);
        return;
      }
      counters.tokenExchanges += 1;
      record.status = "active";
      record.activatedAt = new Date().toISOString();
      record.sessionExpiresAt = futureIso(8 * 60 * 60 * 1000);
      record.sessionToken = `aases_fixture_session_${String(counters.tokenExchanges).padStart(8, "0")}`;
      sessions.set(record.sessionToken, record);
      json(
        response,
        200,
        {
          session_token: record.sessionToken,
          session: session(record),
          preferences: preferences(record),
        },
        origin,
      );
      return;
    }

    if (
      url.pathname === "/assisted-apply/extension/session/verify" &&
      request.method === "POST"
    ) {
      await readJson(request);
      const record = activeRecord(request, response, origin);
      if (!record) return;
      counters.sessionReads += 1;
      json(response, 200, { session: session(record), preferences: preferences(record) }, origin);
      return;
    }

    if (url.pathname === "/assisted-apply/extension/preferences" && request.method === "PUT") {
      const record = activeRecord(request, response, origin);
      if (!record) return;
      const payload = await readJson(request);
      if (
        typeof payload.permit_sensitive_autofill !== "boolean" ||
        typeof payload.permit_demographic_autofill !== "boolean"
      ) {
        json(response, 400, { error: { code: "bad_request", message: "Invalid preferences." } }, origin);
        return;
      }
      counters.preferenceUpdates += 1;
      record.permitSensitiveAutofill = payload.permit_sensitive_autofill;
      record.permitDemographicAutofill = payload.permit_demographic_autofill;
      record.preferenceRevision += 1;
      record.preferenceUpdatedAt = new Date().toISOString();
      json(response, 200, { preferences: preferences(record) }, origin);
      return;
    }

    if (url.pathname === "/assisted-apply/extension/session" && request.method === "DELETE") {
      const record = activeRecord(request, response, origin);
      if (!record) return;
      counters.revocationRequests += 1;
      counters.revocationInFlight = true;
      await new Promise((resolve) => setTimeout(resolve, 500));
      counters.revocations += 1;
      record.status = "revoked";
      counters.revocationInFlight = false;
      noContent(response, origin);
      return;
    }

    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
  } catch (error) {
    json(response, 500, {
      error: {
        code: "fixture_error",
        message: error instanceof Error ? error.message : "Fixture server failed.",
      },
    }, origin);
  }
});

server.listen(4174, "127.0.0.1");

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}

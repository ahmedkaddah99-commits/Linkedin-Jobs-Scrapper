import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const fixturePaths = new Map([
  ["/greenhouse-application.html", join(currentDirectory, "fixtures", "greenhouse-application.html")],
  ["/lever-application.html", join(currentDirectory, "fixtures", "lever-application.html")],
  ["/reconciliation-application.html", join(currentDirectory, "fixtures", "reconciliation-application.html")],
  ["/runr-web-launch.html", join(currentDirectory, "fixtures", "runr-web-launch.html")],
  ["/same-origin-frame.html", join(currentDirectory, "fixtures", "same-origin-frame.html")],
  ["/cross-origin-frame.html", join(currentDirectory, "fixtures", "cross-origin-frame.html")],
]);
const extensionOriginPattern = /^chrome-extension:\/\/([a-p]{32})$/u;

const connections = new Map();
const sessions = new Map();
const documentGrants = new Map();
const fixtureCvBytes = Buffer.from("%PDF-1.4\n% Runr AA11 fixture CV\n%%EOF\n", "utf8");
const fixtureDocuments = new Map([
  ["cv_version_7", { documentVersion: 7, documentKind: "cv", fileName: "Candidate CV.pdf", mimeType: "application/pdf", bytes: fixtureCvBytes }],
  ["lever_cv_version_2", { documentVersion: 2, documentKind: "cv", fileName: "Lever CV.pdf", mimeType: "application/pdf", bytes: Buffer.from("%PDF-1.4\n% Lever CV\n%%EOF\n") }],
  ["cover_letter_version_3", { documentVersion: 3, documentKind: "cover_letter", fileName: "Cover Letter.pdf", mimeType: "application/pdf", bytes: Buffer.from("%PDF-1.4\n% Cover letter\n%%EOF\n") }],
  ["supporting_version_4", { documentVersion: 4, documentKind: "supporting_document", fileName: "Certificate.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", bytes: Buffer.from("PK\\x03\\x04 Runr supporting document") }],
]);
const counters = {
  connectionRequests: 0,
  authorizationVisits: 0,
  tokenExchanges: 0,
  sessionReads: 0,
  preferenceUpdates: 0,
  revocationRequests: 0,
  revocationInFlight: false,
  revocations: 0,
  documentGrants: 0,
  documentDownloads: 0,
  telemetryEvents: 0,
  lastTelemetry: null,
  trackerConfirmations: 0,
  lastOutcomePayload: null,
};

function futureIso(milliseconds) {
  return new Date(Date.now() + milliseconds).toISOString();
}

function json(response, status, payload, origin = "") {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "access-control-allow-headers": "Authorization, Content-Type, X-Runr-Document-Grant",
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
    "access-control-allow-headers": "Authorization, Content-Type, X-Runr-Document-Grant",
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

    if (request.method === "GET" && fixturePaths.has(url.pathname)) {
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      createReadStream(fixturePaths.get(url.pathname)).pipe(response);
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

    if (url.pathname === "/assisted-apply/extension/packages/bind" && request.method === "POST") {
      const record = activeRecord(request, response, origin);
      if (!record) return;
      const payload = await readJson(request);
      if (payload.binding_id !== "aapkg_bind_fixture_web_launch") {
        json(response, 403, { error: { code: "forbidden", message: "Binding rejected." } }, origin);
        return;
      }
      json(response, 200, {
        packageId: "aapkg_fixture_web_launch",
        jobId: "job_fixture_web_launch",
        version: 1,
        schemaVersion: 1,
        job: {
          jobId: "job_fixture_web_launch",
          title: "Engineer",
          company: "Acme",
          portal: "greenhouse",
          url: "http://127.0.0.1:4174/greenhouse-application.html",
          location: "Berlin",
        },
        answers: [],
        documents: [],
        warnings: [],
        policy: {
          permitSensitiveAutofill: false,
          permitDemographicAutofill: false,
          requireLegalAnswerConfirmation: true,
        },
      }, origin);
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

    if (url.pathname === "/assisted-apply/extension/document-grants" && request.method === "POST") {
      const record = activeRecord(request, response, origin);
      if (!record) return;
      const payload = await readJson(request);
      const fixtureDocument = fixtureDocuments.get(String(payload.document_id || ""));
      if (!String(payload.package_id || "").startsWith("aapkg_fixture_") || !fixtureDocument) {
        json(response, 400, { error: { code: "bad_request", message: "Unknown fixed document." } }, origin);
        return;
      }
      counters.documentGrants += 1;
      const grantToken = `aadoc_fixture_${String(counters.documentGrants).padStart(8, "0")}`;
      documentGrants.set(grantToken, { sessionToken: record.sessionToken, consumed: false, document: fixtureDocument });
      json(response, 201, {
        grantToken,
        expiresAt: futureIso(60 * 1000),
        file: {
          documentId: payload.document_id,
          documentVersion: fixtureDocument.documentVersion,
          documentKind: fixtureDocument.documentKind,
          fileName: fixtureDocument.fileName,
          mimeType: fixtureDocument.mimeType,
          size: fixtureDocument.bytes.length,
          sha256Hex: createHash("sha256").update(fixtureDocument.bytes).digest("hex"),
        },
      }, origin);
      return;
    }

    if (url.pathname === "/assisted-apply/extension/document-grants/download" && request.method === "POST") {
      const record = activeRecord(request, response, origin);
      if (!record) return;
      await readJson(request);
      const grantToken = String(request.headers["x-runr-document-grant"] || "");
      const grant = documentGrants.get(grantToken);
      if (!grant || grant.consumed || grant.sessionToken !== record.sessionToken) {
        json(response, 403, { error: { code: "forbidden", message: "Grant rejected." } }, origin);
        return;
      }
      grant.consumed = true;
      counters.documentDownloads += 1;
      const fixtureDocument = grant.document;
      response.writeHead(200, {
        "access-control-allow-origin": origin,
        vary: "Origin",
        "cache-control": "no-store",
        "content-disposition": `attachment; filename="${fixtureDocument.fileName}"`,
        "content-length": fixtureDocument.bytes.length,
        "content-type": fixtureDocument.mimeType,
      });
      response.end(fixtureDocument.bytes);
      return;
    }

    if (url.pathname === "/assisted-apply/telemetry/events" && request.method === "POST") {
      const payload = await readJson(request);
      const expectedKeys = ["adapter", "adapterVersion", "aggregateOutcome", "errorCategory", "lifecycleStage", "schemaVersion"];
      if (JSON.stringify(Object.keys(payload).sort()) !== JSON.stringify(expectedKeys)) {
        json(response, 400, { error: { code: "bad_request", message: "Unbounded telemetry." } }, origin);
        return;
      }
      counters.telemetryEvents += 1;
      counters.lastTelemetry = payload;
      json(response, 202, { recorded: true }, origin);
      return;
    }

    if (url.pathname === "/assisted-apply/extension/application-outcomes" && request.method === "POST") {
      const record = activeRecord(request, response, origin);
      if (!record) return;
      const payload = await readJson(request);
      counters.trackerConfirmations += payload.decision === "confirmed" ? 1 : 0;
      counters.lastOutcomePayload = payload;
      json(response, payload.decision === "confirmed" ? 201 : 200, {
        decision: payload.decision,
        created: payload.decision === "confirmed",
        duplicate: false,
        ...(payload.decision === "confirmed" ? { trackerRecordId: "aatrk_fixture_aa14" } : {}),
      }, origin);
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

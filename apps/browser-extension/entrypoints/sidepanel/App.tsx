import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ApplicationCorrectionScope,
  ApplicationPackagePayload,
  AssistedApplyTabState,
  ExtensionConnectionState,
  DocumentUploadMessage,
  PackageExecutionMessage,
  PendingApplicationConfirmation,
  PanelRequest,
  PreparationPanelState,
  TrackerConfirmationResult,
} from "@runr/extension-messages";
import { APPLICATION_CORRECTION_SCOPE_OPTIONS, isPanelResponse } from "@runr/extension-messages";
import { browser } from "wxt/browser";
import { buildReviewPanelModel, type ReviewFieldRow, type DocumentRow } from "../../src/review/panel-model";
import { requestPortalPermissionFromUserGesture } from "../../src/permissions/host-permissions";
import { toCandidateProfile } from "../../src/panel/profile-package";
import ProfileQuickCopy from "../../src/panel/ProfileQuickCopy";
import ApplicationWorkspace from "../../src/panel/ApplicationWorkspace";
import type { CandidateProfile } from "@runr/ats-core/generic-planner";
import { assistedApplyRuntimeConfig } from "../../src/auth/config";
import type { ProfileDetail } from "../../src/panel/profile-details";

async function send(message: PanelRequest) {
  const response: unknown = await browser.runtime.sendMessage(message);
  if (!isPanelResponse(response) || !response.ok) {
    const error = isPanelResponse(response) ? response.error : undefined;
    throw new Error(error || "Runr could not complete the extension request.");
  }
  return response;
}

async function requestTab(message: PanelRequest): Promise<AssistedApplyTabState> {
  const response = await send(message);
  if (!response.state) throw new Error("Runr could not read the active application tab.");
  return response.state;
}

async function requestConnection(message: PanelRequest): Promise<ExtensionConnectionState> {
  const response = await send(message);
  if (!response.connection) throw new Error("Runr returned an invalid connection state.");
  return response.connection;
}

async function requestPackage(message: PanelRequest): Promise<ApplicationPackagePayload> {
  const response = await send(message);
  if (!response.package) throw new Error("Runr returned an invalid application package.");
  return response.package;
}

async function executePackage(message: PanelRequest): Promise<PackageExecutionMessage> {
  const response = await send(message);
  if (!response.packageExecution) throw new Error("Runr returned an invalid fill result.");
  return response.packageExecution;
}

async function uploadDocument(message: PanelRequest): Promise<DocumentUploadMessage> {
  const response = await send(message);
  if (!response.documentUpload) throw new Error("Runr returned an invalid document result.");
  return response.documentUpload;
}

async function requestPendingConfirmation(): Promise<PendingApplicationConfirmation | null> {
  const response = await send({ type: "GET_PENDING_APPLICATION_CONFIRMATION" });
  if (!("pendingConfirmation" in response)) {
    throw new Error("Runr returned an invalid application confirmation state.");
  }
  return response.pendingConfirmation ?? null;
}

function atsLabel(ats: AssistedApplyTabState["ats"]): string {
  if (ats === "greenhouse") return "Greenhouse";
  if (ats === "lever") return "Lever";
  return "Unsupported page";
}

export default function App() {
  const testingFixtureBuild = import.meta.env.MODE === "testing";
  const [state, setState] = useState<AssistedApplyTabState | null>(null);
  const [connection, setConnection] = useState<ExtensionConnectionState | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const [applicationPackage, setApplicationPackage] = useState<ApplicationPackagePayload | null>(null);
  const [packageBusy, setPackageBusy] = useState(false);
  const [packageExecution, setPackageExecution] = useState<PackageExecutionMessage | null>(null);
  const [documentUpload, setDocumentUpload] = useState<DocumentUploadMessage | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingApplicationConfirmation | null>(null);
  const [trackerConfirmation, setTrackerConfirmation] = useState<TrackerConfirmationResult | null>(null);
  const [preparation, setPreparation] = useState<PreparationPanelState | null>(null);
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [profileError, setProfileError] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);
  const [workspaceTab, setWorkspaceTab] = useState<"application" | "profile" | "answers" | "documents">("application");
  const [profileAnswers, setProfileAnswers] = useState<ProfileDetail[]>([]);
  async function refreshProfile(): Promise<void> {
    setProfileLoading(true);
    setProfileError("");
    try {
      const response: unknown = await browser.runtime.sendMessage({ type: "ASSISTED_APPLY_PANEL_PROFILE" });
      const next = isPanelResponse(response) && response.ok ? toCandidateProfile(response.profilePackage) : null;
      setProfile(next);
      setProfileAnswers(next && isPanelResponse(response) && response.profilePackage ? response.profilePackage.answers
        .filter((answer) => Boolean(answer.proposed_value.trim()))
        .map((answer) => ({ section: "Saved answer", label: answer.label, value: answer.proposed_value })) : []);
      if (!next) setProfileError("Couldn't load your profile. Connect Runr, then try again.");
    } catch { setProfile(null); setProfileAnswers([]); setProfileError("Couldn't load your profile. Try again."); }
    finally { setProfileLoading(false); }
  }
  function openRunr(path: "/profile" | "/documents" | "/cv-studio" | "/tracker") {
    void browser.tabs.create({ url: `${assistedApplyRuntimeConfig().frontendOrigin}${path}` });
  }
  const reviewModel = useMemo(
    () => buildReviewPanelModel(applicationPackage, state, documentUpload),
    [applicationPackage, state, documentUpload],
  );

  const load = useCallback(async (refresh = false) => {
    setBusy(true);
    setError("");
    try {
      setState(
        await requestTab({ type: refresh ? "REFRESH_ACTIVE_TAB_STATE" : "GET_ACTIVE_TAB_STATE" }),
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }, []);

  const loadPreparation = useCallback(async () => {
    try {
      const response = await send({ type: "GET_ASSISTED_APPLY_PREPARATION" });
      setPreparation(response.preparation ?? null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    }
  }, []);

  async function connectRunr(): Promise<void> {
    setConnectionBusy(true);
    setConnectionError("");
    try { setConnection(await requestConnection({ type: "CONNECT_RUNR" })); }
    catch (nextError) { setConnectionError(nextError instanceof Error ? nextError.message : "Couldn't connect. Try again."); }
    finally { setConnectionBusy(false); }
  }

  useEffect(() => {
    void load(false);
    setConnectionBusy(true);
    void requestConnection({ type: "GET_EXTENSION_CONNECTION" })
      .then(async (currentConnection) => {
        if (currentConnection.status !== "disconnected") {
          setConnection(currentConnection);
          return currentConnection;
        }
        const connectedConnection = await requestConnection({ type: "CONNECT_RUNR" });
        setConnection(connectedConnection);
        return connectedConnection;
      })
      .catch((nextError: unknown) => {
        setConnectionError(nextError instanceof Error ? nextError.message : String(nextError));
      })
      .finally(() => setConnectionBusy(false));
    setPackageBusy(true);
    void requestPackage({ type: "GET_BOUND_APPLICATION_PACKAGE" })
      .then(setApplicationPackage)
      .catch(() => setApplicationPackage(null))
      .finally(() => setPackageBusy(false));
    void loadPreparation();
  }, [load, loadPreparation]);

  useEffect(() => {
    const interval = window.setInterval(() => void loadPreparation(), 1000);
    return () => window.clearInterval(interval);
  }, [loadPreparation]);

  useEffect(() => {
    if (connection?.status === "connected") void refreshProfile();
    else { setProfile(null); setProfileAnswers([]); }
  }, [connection?.status]);

  useEffect(() => {
    const refresh = () => void requestPendingConfirmation().then(setPendingConfirmation).catch(() => undefined);
    refresh();
    const interval = window.setInterval(refresh, 1000);
    return () => window.clearInterval(interval);
  }, []);

  async function respondToPossibleSuccess(decision: "confirmed" | "declined"): Promise<void> {
    if (!pendingConfirmation) return;
    setPackageBusy(true);
    setError("");
    try {
      const response = await send({
        type: "RESPOND_TO_APPLICATION_CONFIRMATION",
        decision,
        evidence: pendingConfirmation,
      });
      if (!response.trackerConfirmation) throw new Error("Runr returned an invalid Tracker result.");
      setTrackerConfirmation(response.trackerConfirmation);
      setPendingConfirmation(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPackageBusy(false);
    }
  }

  async function runFixture(): Promise<void> {
    setBusy(true);
    setError("");
    try {
      setState(await requestTab({ type: "RUN_GREENHOUSE_FIXTURE_PROOF" }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function fillApplicationPackage(replaceFieldIntents: string[] = []): Promise<void> {
    if (!applicationPackage) return;
    setPackageBusy(true);
    setError("");
    try {
      setPackageExecution(await executePackage({
        type: applicationPackage.job.portal === "lever"
          ? "RUN_LEVER_APPLICATION_PACKAGE" : "RUN_GREENHOUSE_APPLICATION_PACKAGE",
        package: applicationPackage,
        replaceFieldIntents,
      }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPackageBusy(false);
    }
  }

  async function uploadSelectedDocument(documentId: string): Promise<void> {
    if (!applicationPackage) return;
    setPackageBusy(true);
    setError("");
    setDocumentUpload(null);
    try {
      setDocumentUpload(await uploadDocument({
        type: "UPLOAD_SELECTED_DOCUMENT",
        package: applicationPackage,
        documentId,
      }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPackageBusy(false);
    }
  }

  async function preparationAction(message: Extract<PanelRequest, { type: "RETRY_ASSISTED_APPLY_PREPARATION" | "CANCEL_ASSISTED_APPLY_PREPARATION" | "ACTIVATE_ASSISTED_APPLY_PREPARATION" }>): Promise<void> {
    setBusy(true);
    setError("");
    try {
      const response = await send(message);
      setPreparation(response.preparation ?? null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
      await loadPreparation();
    } finally {
      setBusy(false);
    }
  }

  async function grantPreparationPermission(): Promise<void> {
    if (!preparation?.ats) return;
    setBusy(true);
    setError("");
    try {
      const permissionGranted = await requestPortalPermissionFromUserGesture(preparation.ats);
      const response = await send({ type: "REQUEST_PORTAL_PERMISSION", portal: preparation.ats });
      if (!permissionGranted || !response.permissionGranted) {
        throw new Error("Portal access was denied. Preparation remains paused.");
      }
      await loadPreparation();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="panel-shell">
      <header className="panel-header">
        <div className="runr-mark" aria-hidden="true">R</div>
        <div>
          <p className="eyebrow">Runr</p>
          <h1>Assisted Apply</h1>
        </div>
      </header>

      <section className="boundary" aria-label="Application steps">
        <strong>Your application workspace</strong>
        <p>Fill your details, attach your documents, and review the remaining questions.</p>
      </section>

      {pendingConfirmation ? (
        <section className="connection-card" aria-label="Confirm application outcome" data-testid="application-confirmation">
          <p className="eyebrow">Application tracker</p>
          <h2>Did you submit this application?</h2>
          <p>Add this application to your tracker?</p>
          <div className="button-row">
            <button type="button" disabled={packageBusy} onClick={() => void respondToPossibleSuccess("confirmed")}>
              Yes, add to Tracker
            </button>
            <button className="secondary" type="button" disabled={packageBusy}
              onClick={() => void respondToPossibleSuccess("declined")}>
              No, do not add
            </button>
          </div>
        </section>
      ) : trackerConfirmation ? (
        <p className="boundary" role="status" data-testid="tracker-confirmation-result">
          {trackerConfirmation.decision === "confirmed"
            ? trackerConfirmation.duplicate
              ? "This application was already in Tracker."
              : "Application added to Tracker."
            : "Application was not added to Tracker."}
        </p>
      ) : null}

      <section className="connection-card compact-status" aria-busy={connectionBusy}>
        <div className="status-heading">
          <div>
            <p className="eyebrow">Autofill status</p>
            <h2>{connection?.status === "connected" ? "Ready to apply" : connectionBusy ? "Connecting…" : "Connect your account"}</h2>
          </div>
          <span className={`status-chip connection-${connection?.status || "loading"}`} data-testid="connection-status">
            {connection?.status || "loading"}
          </span>
        </div>
        <p className="muted">
          {connection?.status === "connected"
            ? "Your profile is connected. Open an application to get started."
            : "Connect Runr to use your profile and application documents."}
        </p>
        {connectionError ? <p className="error" role="alert">{connectionError}</p> : null}
        {connection?.status !== "connected" ? <button type="button" disabled={connectionBusy} onClick={() => void connectRunr()} data-testid="connect-runr">{connectionBusy ? "Connecting…" : "Connect Runr"}</button> : null}
      </section>

      <nav className="workspace-nav" aria-label="Application tools">
        <button type="button" className="secondary" aria-pressed={workspaceTab === "application"} onClick={() => setWorkspaceTab("application")}>Application</button>
        <button type="button" className="secondary" aria-pressed={workspaceTab === "profile"} onClick={() => setWorkspaceTab("profile")}>Profile</button>
        <button type="button" className="secondary" aria-pressed={workspaceTab === "answers"} onClick={() => setWorkspaceTab("answers")}>Answers</button>
        <button type="button" className="secondary" aria-pressed={workspaceTab === "documents"} onClick={() => setWorkspaceTab("documents")}>Documents</button>
        <button type="button" className="secondary" onClick={() => openRunr("/tracker")}>Tracker</button>
      </nav>
      {workspaceTab === "profile" ? <section className="connection-card" aria-label="Profile quick copy">
        <h2>Your profile</h2><p className="muted">Copy individual details into any application, including forms without autofill.</p>
        {profile ? <ProfileQuickCopy profile={profile} /> : <p className="muted" role="status">{profileLoading ? "Loading your profile…" : profileError || "Connect Runr to use your saved details."}</p>}
        <div className="button-row"><button className="secondary" type="button" disabled={profileLoading} onClick={() => void refreshProfile()}>Refresh profile</button><button className="secondary" type="button" onClick={() => openRunr("/profile")}>Edit profile</button></div>
      </section> : null}

      {workspaceTab === "answers" ? <section className="connection-card" aria-label="Saved answers"><h2>Saved answers</h2><p className="muted">Copy an answer and adjust it for the question you're answering.</p>{profileLoading ? <p className="muted" role="status">Loading your answers…</p> : profile ? <ProfileQuickCopy answers details={profileAnswers} /> : <p className="muted">{profileError || "Connect your profile to see saved answers."}</p>}<button type="button" className="secondary" onClick={() => openRunr("/profile")}>Edit profile answers</button></section> : null}

      <section className="connection-card" hidden={workspaceTab !== "documents"} aria-label="Document workspace">
        <h2>Documents</h2><p className="muted">Create a document here, then attach it from Documents on your application page.</p>
        <ApplicationWorkspace mode="documents" applicationUrl={applicationPackage?.job.url || "runr-sidepanel"} description="" />
        <button type="button" className="secondary" onClick={() => openRunr("/documents")}>Manage documents</button>
      </section>
      <section className="connection-card" hidden={workspaceTab !== "answers"} aria-label="Answer drafting workspace">
        <ApplicationWorkspace mode="answers" applicationUrl={applicationPackage?.job.url || "runr-sidepanel"} description="" />
      </section>
      <div className="application-workspace" hidden={workspaceTab !== "application"}>
      {connection?.status === "connected" && applicationPackage ? (
        <section className="package-card">
          <div className="status-heading">
            <div>
              <p className="eyebrow">Current application</p>
              <h2>{applicationPackage.job.title || "Untitled role"}</h2>
            </div>
            <span className="status-chip status-recognized">v{applicationPackage.version}</span>
          </div>
          <dl>
            <div><dt>Company</dt><dd data-testid="package-company">{applicationPackage.job.company || "Unknown"}</dd></div>
            <div><dt>Application site</dt><dd data-testid="package-portal">{applicationPackage.job.portal || "Unknown"}</dd></div>
            <div><dt>Location</dt><dd>{applicationPackage.job.location || "Not specified"}</dd></div>
            <div><dt>Answers</dt><dd>{applicationPackage.answers.length} ready</dd></div>
            <div><dt>Documents</dt><dd>{applicationPackage.documents.length} available</dd></div>
            {applicationPackage.warnings.length > 0 ? (
              <div><dt>Warnings</dt><dd>{applicationPackage.warnings.join(", ")}</dd></div>
            ) : null}
          </dl>
          {applicationPackage.job.portal === "greenhouse" || applicationPackage.job.portal === "lever" ? (
            <button type="button" data-testid="fill-package" disabled={packageBusy}
              onClick={() => void fillApplicationPackage()}>
              {packageBusy ? "Filling your details…" : "Autofill application"}
            </button>
          ) : null}
        </section>
      ) : connection?.status === "connected" && !applicationPackage ? (
        <section className="package-card muted">
          <p className="eyebrow">Current application</p>
          <p>Launch a job from Runr to review and fill this application.</p>
        </section>
      ) : null}

      {preparation && preparation.status !== "idle" ? (
        <PreparationLifecycleCard
          preparation={preparation}
          busy={busy}
          onGrant={() => void grantPreparationPermission()}
          onRetry={() => void preparationAction({ type: "RETRY_ASSISTED_APPLY_PREPARATION" })}
          onCancel={() => void preparationAction({ type: "CANCEL_ASSISTED_APPLY_PREPARATION" })}
          onReview={() => void preparationAction({ type: "ACTIVATE_ASSISTED_APPLY_PREPARATION" })}
        />
      ) : null}

      {connection?.status === "connected" && applicationPackage ? (
        <section className="review-workspace" aria-label="Application review">
          <div className="progress-summary" aria-label="Application progress">
            {(["verified", "review", "missing", "manual", "documents"] as const).map((key) => (
              <div key={key}><strong>{reviewModel.counts[key]}</strong><span>{key}</span></div>
            ))}
          </div>
          {!reviewModel.enabled ? (
            <p className="warning" role="status" data-testid="review-disabled">
              Open this application's form to review and fill its details.
            </p>
          ) : null}
          {(["ready", "review", "missing", "manual"] as const).map((section) => (
            <section className={`review-section section-${section}`} key={section}>
              <div className="section-title">
                <h2>{section.charAt(0).toUpperCase() + section.slice(1)}</h2>
                <span>{reviewModel.rows[section].length}</span>
              </div>
              {reviewModel.rows[section].length ? (
                <ul>{reviewModel.rows[section].map((row) => (
                  <EvidenceRow
                    row={row}
                    key={row.id}
                    onSave={async (correctedValue, scope) => {
                      if (!applicationPackage) return;
                      setPackageBusy(true);
                      setError("");
                      try {
                        setApplicationPackage(await requestPackage({
                          type: "SAVE_APPLICATION_CORRECTION",
                          package: applicationPackage,
                          fieldIntent: row.fieldIntent,
                          correctedValue,
                          scope,
                        }));
                      } catch (nextError) {
                        setError(nextError instanceof Error ? nextError.message : String(nextError));
                        throw nextError;
                      } finally {
                        setPackageBusy(false);
                      }
                    }}
                  />
                ))}</ul>
              ) : <p className="muted">No fields in this section.</p>}
              {section === "manual" && reviewModel.manualControls.length ? (
                <ul className="manual-controls">
                  <li>Complete the remaining questions on the application form.</li>
                </ul>
              ) : null}
            </section>
          ))}
          <section className="review-section section-documents" aria-label="Documents review">
            <div className="section-title"><h2>Documents</h2><span>{reviewModel.documents.length}</span></div>
            {reviewModel.documents.length ? (
              <ul>{reviewModel.documents.map((document) => (
                <li className="document-row" key={document.documentId || document.documentKind}>
                  <strong>{document.documentKind.replaceAll("_", " ")}</strong>
                  <span>{document.fileName || document.mimeType} &middot; v{document.documentVersion}</span>
                  {(["cv", "cover_letter", "supporting_document"] as const).includes(document.documentKind as any) ? (
                    <button type="button" disabled={packageBusy || document.uploadStatus === "uploaded"}
                      data-testid={`upload-${document.documentKind}`}
                      onClick={() => void uploadSelectedDocument(document.documentId)}
                      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void uploadSelectedDocument(document.documentId); } }}>
                      {document.uploadStatus === "uploading"
                        ? "Uploading and verifying�"
                        : document.uploadStatus === "uploaded"
                          ? "Uploaded"
                          : `Upload selected ${document.documentKind.replaceAll("_", " ")}`}
                    </button>
                  ) : null}
                  {document.uploadStatus !== "idle" && document.uploadStatus !== "uploading" ? (
                    <p role="status" data-testid={`document-upload-status-${document.documentKind}`} className={`upload-status upload-${document.uploadStatus}`}>
                      {document.uploadStatus.replaceAll("_", " ")}
                      {document.reasons.length ? `: ${document.reasons.join(" ")}` : ""}
                    </p>
                  ) : null}
                </li>
              ))}</ul>
            ) : <p className="muted">No documents selected.</p>}
          </section>
        </section>
      ) : null}

      {packageExecution ? (
        <section className="result-card" data-testid="package-execution-result">
          <p className="eyebrow">Autofill results</p>
          <h2>{packageExecution.executions.length} fields checked</h2>
          <ul>{packageExecution.executions.map((result, index) => (
            <li key={`${result.fieldLabel}-${index}`}>
              <strong>{result.fieldLabel}</strong>: {result.status}
              {result.status === "preserved_existing" && result.fieldIntent ? (
                <button type="button" className="secondary replace-answer"
                  data-testid={`replace-${result.fieldIntent}`}
                  disabled={packageBusy}
                  onClick={() => void fillApplicationPackage([result.fieldIntent!])}>
                  Replace with Runr answer
                </button>
              ) : null}
            </li>
          ))}</ul>
        </section>
      ) : null}

      {error ? <p className="error" role="alert">{error}</p> : null}

      <section className="status-card" aria-busy={busy}>
        <div className="status-heading">
          <div>
            <p className="eyebrow">Current page</p>
            <h2 data-testid="ats-name">{state ? atsLabel(state.ats) : "Inspecting���"}</h2>
          </div>
          <span className={`status-chip status-${state?.status || "loading"}`}>
            {state?.status.replaceAll("_", " ") || "loading"}
          </span>
        </div>

        {testingFixtureBuild && state?.fixtureAvailable ? (
          <div className="fixture-proof">
            <p>
              Local AA-01 fixture found. This proof uses the non-production value
              <code>candidate@example.com</code>.
            </p>
            <button
              type="button"
              onClick={() => void runFixture()}
              disabled={busy}
              data-testid="run-fixture"
            >
              {busy ? "Checking���" : "Fill and verify fixture email"}
            </button>
          </div>
        ) : (
          <p className="muted">
            {state?.ats
              ? "Application found. Open a job from Runr to fill your details and attach documents."
              : "Open a supported application page, then refresh this panel."}
          </p>
        )}

        <button
          className="secondary"
          type="button"
          onClick={() => void load(true)}
          disabled={busy}
        >
          Refresh page status
        </button>
      </section>

      {state?.execution ? (
        <section className="result-card" data-testid="execution-result">
          <p className="eyebrow">Verified field result</p>
          <h2>{state.execution.fieldLabel}</h2>
          <dl>
            <div><dt>Status</dt><dd data-testid="execution-status">{state.execution.status}</dd></div>
            <div><dt>Accepted value</dt><dd>{state.execution.acceptedValue || "None"}</dd></div>
            <div><dt>Source</dt><dd>Local verified fixture package</dd></div>
          </dl>
        </section>
      ) : null}

      {state?.manualReasons.length ? (
        <section className="manual-card">
          <p className="eyebrow">Remaining steps</p>
          <p>Some questions need your input. Complete them on the application form.</p>
        </section>
      ) : null}
      </div>

    </main>
  );
}

function PreparationLifecycleCard({
  preparation,
  busy,
  onGrant,
  onRetry,
  onCancel,
  onReview,
}: {
  preparation: PreparationPanelState;
  busy: boolean;
  onGrant: () => void;
  onRetry: () => void;
  onCancel: () => void;
  onReview: () => void;
}) {
  const statusCopy: Record<PreparationPanelState["status"], string> = {
    idle: "No preparation is active.",
    permission_required: "Grant access to the employer portal to continue.",
    queued: "The application page is opening and will be prepared automatically.",
    preparing: "Filling your application details…",
    ready_for_review: "Preparation is complete. Review the filled application before submitting.",
    review_activated: "Your application is ready to review.",
    needs_attention: "Preparation stopped and needs your review.",
    interrupted: "The application page changed or closed. Open it again to continue.",
    retry_required: "Try preparing this application again.",
    auth_lost: "Runr authentication expired. Reconnect before retrying.",
    expired: "Open this job from Runr again to prepare the application.",
    cancelled: "Application preparation cancelled.",
  };
  const canRetry = ["needs_attention", "interrupted", "retry_required", "auth_lost", "expired"].includes(preparation.status);
  return (
    <section className={`preparation-card preparation-${preparation.status}`} aria-label="Assisted Apply preparation" data-testid="preparation-lifecycle">
      <div className="status-heading">
        <div>
          <p className="eyebrow">Preparation</p>
          <h2>Preparation status</h2>
        </div>
        <span className="status-chip">{preparation.ats || "unknown ATS"}</span>
      </div>
      <p className="preparation-copy">{statusCopy[preparation.status]}</p>
      {preparation.reason ? <p className="preparation-reason" role="status">{preparation.reason}</p> : null}
      {preparation.totalCount > 0 ? (
        <div className="preparation-counts" aria-label="Sanitized preparation counts">
          <span><strong>{preparation.completedCount}</strong> filled</span>
          <span><strong>{Math.max(0, preparation.totalCount - preparation.completedCount)}</strong> unresolved</span>
        </div>
      ) : null}
      <div className="button-row preparation-actions">
        {preparation.status === "permission_required" ? <button type="button" onClick={onGrant} disabled={busy}>Grant portal access</button> : null}
        {canRetry ? <button type="button" onClick={onRetry} disabled={busy}>Retry preparation</button> : null}
        {preparation.status === "ready_for_review" ? <button type="button" onClick={onReview} disabled={busy}>Review filled application</button> : null}
        {["queued", "preparing", "ready_for_review", "permission_required", "needs_attention", "interrupted", "retry_required", "auth_lost", "expired"].includes(preparation.status) ? (
          <button className="secondary" type="button" onClick={onCancel} disabled={busy}>Cancel preparation</button>
        ) : null}
      </div>
    </section>
  );
}

function EvidenceRow({
  row,
  onSave,
}: {
  row: ReviewFieldRow;
  onSave: (correctedValue: string, scope: ApplicationCorrectionScope) => Promise<void>;
}) {
  const [reviewed, setReviewed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [correctedValue, setCorrectedValue] = useState(row.proposedValue);
  const [scope, setScope] = useState<ApplicationCorrectionScope>("application");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");

  function handleReviewKeyDown(event: React.KeyboardEvent, action: () => void) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      action();
    }
  }

  return (
    <li className={`evidence-row ${row.requiredAndEmpty ? "required-empty" : ""}`} data-testid={`field-${row.section}`}>
      <div className="field-heading">
        <strong>{row.label || row.fieldIntent}</strong>
        <span className={`acceptance acceptance-${row.liveAcceptance}`}>
          {row.liveAcceptance.replaceAll("_", " ")}
        </span>
      </div>
      <p className="proposed-answer">
        {row.proposedValue || <em className="empty-answer">No answer available</em>}
        {row.requiredAndEmpty ? <span className="required-badge">Required</span> : null}
      </p>
      <details><summary className="muted">Answer details</summary><dl className="field-evidence">
        <div><dt>Source</dt><dd>{row.source.replaceAll("_", " ")}</dd></div>
        <div><dt>Scope</dt><dd>{row.scope.replaceAll("_", " ")}</dd></div>
        <div><dt>Confidence</dt><dd>{Math.round(row.confidence * 100)}%</dd></div>
        <div><dt>Review</dt><dd>{row.requiresReview ? "Required" : "Not required"}</dd></div>
      </dl></details>
      {row.reasons.length ? <p className="field-reason">{row.section === "manual" ? "Complete this question on the application form." : row.section === "missing" ? "Add this detail to your profile or enter it on the form." : "Check this answer for this application."}</p> : null}
      {row.section === "review" ? (
        <div className="field-actions" role="group" aria-label={`Review actions for ${row.label || row.fieldIntent}`}>
          <button
            type="button"
            aria-pressed={reviewed}
            aria-label={reviewed ? "Marked as reviewed" : "Mark answer as reviewed"}
            onClick={() => setReviewed(true)}
            onKeyDown={(event) => handleReviewKeyDown(event, () => setReviewed(true))}
            disabled={reviewed}
          >
            {reviewed ? "Reviewed" : "Review answer"}
          </button>
          <button
            className="secondary"
            type="button"
            aria-label="Clear review status"
            onClick={() => setReviewed(false)}
            onKeyDown={(event) => handleReviewKeyDown(event, () => setReviewed(false))}
            disabled={!reviewed}
          >
            Clear review
          </button>
        </div>
      ) : null}
      <div className="field-actions correction-actions">
        <button className="secondary" type="button" onClick={() => setEditing((value) => !value)}
          aria-expanded={editing} aria-label={editing ? "Cancel correction" : "Correct answer"}>
          {editing ? "Cancel correction" : "Correct answer"}
        </button>
      </div>
      {editing ? (
        <div className="correction-editor" role="form" aria-label="Answer correction">
          <label>
            <span>Corrected answer</span>
            <input value={correctedValue} onChange={(event) => setCorrectedValue(event.currentTarget.value)} />
          </label>
          <label>
            <span>Use this correction for</span>
            <select value={scope} onChange={(event) => setScope(event.currentTarget.value as ApplicationCorrectionScope)}>
              {APPLICATION_CORRECTION_SCOPE_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={saving || !correctedValue.trim()}
            onClick={() => {
              setSaving(true);
              setSaved("");
              void onSave(correctedValue, scope)
                .then(() => {
                  setSaved(scope === "do_not_save" ? "Applied without saving." : "Correction applied at the selected scope.");
                  setEditing(false);
                })
                .catch(() => undefined)
                .finally(() => setSaving(false));
            }}
          >
            {saving ? "Applying�" : "Apply correction"}
          </button>
        </div>
      ) : null}
      {saved ? <p className="correction-saved" role="status">{saved}</p> : null}
    </li>
  );
}







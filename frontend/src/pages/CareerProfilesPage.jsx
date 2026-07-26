import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import CareerProfileSourceSelector from "../components/careerProfile/CareerProfileSourceSelector";
import RebindCompatibilityDialog from "../components/careerProfile/RebindCompatibilityDialog";
import BaselineCVReplacementDialog from "../components/careerProfile/BaselineCVReplacementDialog";

import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";

const STATUS_LABELS = {
  not_started: "Not started",
  extracting_evidence: "Extracting evidence",
  needs_review: "Needs review",
  ready_for_tailoring: "Ready for tailoring",
  unbound: "Unbound",
};

const STATUS_TONES = {
  not_started: "neutral",
  extracting_evidence: "primary",
  needs_review: "warning",
  ready_for_tailoring: "success",
  unbound: "warning",
};

const LANGUAGE_OPTIONS = [
  { value: "en", label: "English" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "es", label: "Spanish" },
  { value: "nl", label: "Dutch" },
  { value: "it", label: "Italian" },
];


export default function CareerProfilesPage() {
  const { user, request } = useSession();
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    description: "",
    preferred_language: "en",
    target_direction: "",
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  // Binding state
  const [bindingProfileId, setBindingProfileId] = useState("");
  const [bindingAction, setBindingAction] = useState("");
  const [bindingError, setBindingError] = useState("");

  // Rebind compatibility state
  const [rebindProfile, setRebindProfile] = useState(null);
  const [rebindReview, setRebindReview] = useState(null);
  const [rebinding, setRebinding] = useState(false);
  const [rebindError, setRebindError] = useState("");

  // Baseline CV replacement state (CP-034)
  const [cvReplaceProfile, setCvReplaceProfile] = useState(null);
  const [cvReplacePreview, setCvReplacePreview] = useState(null);
  const [cvReplacePreviewing, setCvReplacePreviewing] = useState(false);
  const [cvReplaceConfirming, setCvReplaceConfirming] = useState(false);
  const [cvReplaceError, setCvReplaceError] = useState("");



  // Source selection state
  const [sourceProfileId, setSourceProfileId] = useState("");
  const [sourceSaving, setSourceSaving] = useState(false);
  const [sourceError, setSourceError] = useState("");

  // Fetch workspaces for binding UI
  const { data: workspacesData } = useApiResource(
    () => request("/workspaces?limit=100", { timeoutMs: 60000 }),
    [request],
    { cacheKey: "workspaces:list", staleMs: Infinity, backgroundRefresh: false },
  );

  // Fetch documents for baseline CV replacement UI
  const { data: documentsData } = useApiResource(
    () => request("/documents?limit=200", { timeoutMs: 60000 }),
    [request],
    { cacheKey: "documents:list", staleMs: 30000, backgroundRefresh: true },
  );

  const userDocuments = documentsData?.documents || [];



  const workspaceMap = useMemo(() => {
    const map = {};
    for (const ws of workspacesData?.workspaces || []) {
      map[ws.id] = ws.name || ws.id;
    }
    return map;
  }, [workspacesData]);

  const loadProfiles = useCallback(async () => {
    if (!user?.user_id) return;
    try {
      setLoading(true);
      const data = await request("/career-profiles", { method: "GET" }, { rawPath: true });
      setProfiles(Array.isArray(data) ? data : []);
      setError("");
    } catch (err) {
      setError(String(err?.message || "Failed to load career profiles."));
    } finally {
      setLoading(false);
    }
  }, [user?.user_id, request]);

  useEffect(() => { loadProfiles(); }, [loadProfiles]);

  async function handleSaveSourceSelection(selectedAssetIds) {
    if (!sourceProfileId) return;
    setSourceSaving(true);
    setSourceError("");
    try {
      const profile = profiles.find((p) => p.profile_id === sourceProfileId);
      const metadata = { ...(profile?.metadata || {}), source_asset_ids: selectedAssetIds };
      const updated = await request(
        `/career-profiles/${sourceProfileId}`,
        { method: "PUT", body: JSON.stringify({ metadata, status: "extracting_evidence" }) },
        { rawPath: true },
      );
      setProfiles((prev) =>
        prev.map((p) => (p.profile_id === updated.profile_id ? updated : p)),
      );
      setSourceProfileId("");
    } catch (err) {
      setSourceError(String(err?.message || "Failed to save source selection."));
    } finally {
      setSourceSaving(false);
    }
  }

  function handleShowForm() {
    setForm({ name: "", description: "", preferred_language: "en", target_direction: "" });
    setFormError("");
    setShowForm(true);
  }

  function handleCancelForm() { setShowForm(false); }

  function handleFieldChange(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleCreateProfile(e) {
    e.preventDefault();
    const name = form.name.trim();
    if (!name) { setFormError("Profile name is required."); return; }
    try {
      setSaving(true);
      setFormError("");
      const profile = await request(
        "/career-profiles",
        {
          method: "POST",
          body: JSON.stringify({
            name,
            description: form.description.trim(),
            preferred_language: form.preferred_language,
            target_direction: form.target_direction.trim(),
          }),
        },
        { rawPath: true }
      );
      setProfiles((prev) => [profile, ...prev]);
      setShowForm(false);
      navigate(`/workspaces?profile_id=${profile.profile_id}`);
    } catch (err) {
      setFormError(String(err?.message || "Failed to create career profile."));
    } finally {
      setSaving(false);
    }
  }

  // --- Workspace binding helpers ---

  function openBindDialog(profileId, action) {
    setBindingProfileId(profileId);
    setBindingAction(action);
    setBindingError("");
  }

  function closeBindDialog() {
    setBindingProfileId("");
    setBindingAction("");
    setBindingError("");
  }

  async function handleBindWorkspace(workspaceId) {
    if (!bindingProfileId || !workspaceId) return;
    try {
      setBindingError("");
      const updated = await request(
        `/career-profiles/${bindingProfileId}/bind`,
        { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) },
        { rawPath: true }
      );
      setProfiles((prev) => prev.map((p) => (p.profile_id === updated.profile_id ? updated : p)));
      closeBindDialog();
    } catch (err) {
      setBindingError(String(err?.message || "Failed to bind workspace."));
    }
  }

  async function handleUnbindWorkspace(profileId) {
    try {
      setBindingError("");
      const updated = await request(
        `/career-profiles/${profileId}/bind`,
        { method: "DELETE" },
        { rawPath: true }
      );
      setProfiles((prev) => prev.map((p) => (p.profile_id === updated.profile_id ? updated : p)));
    } catch (err) {
      setBindingError(String(err?.message || "Failed to unbind workspace."));
    }
  }

  // --- Rebind compatibility handlers ---

  function openRebindDialog(profile) {
    setRebindProfile(profile);
    setRebindReview(null);
    setRebindError("");
  }

  function closeRebindDialog() {
    setRebindProfile(null);
    setRebindReview(null);
    setRebinding(false);
    setRebindError("");
  }

  async function handleRebindReview(workspaceId) {
    const profileId = rebindProfile?.profile_id;
    if (!profileId) throw new Error("No profile selected.");
    const review = await request(
      `/career-profiles/${profileId}/rebind-review`,
      { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) },
      { rawPath: true }
    );
    setRebindReview(review);
    return review;
  }

  async function handleRebindConfirm({ review_id, confirmed_conflicts }) {
    const profileId = rebindProfile?.profile_id;
    if (!profileId) return;
    try {
      setRebinding(true);
      setRebindError("");
      const updated = await request(
        `/career-profiles/${profileId}/rebind-confirm`,
        {
          method: "POST",
          body: JSON.stringify({
            workspace_id: rebindReview?.workspace_id || "",
            review_id,
            confirmed_conflicts,
          }),
        },
        { rawPath: true }
      );
      setProfiles((prev) => prev.map((p) => (p.profile_id === updated.profile_id ? updated : p)));
      closeRebindDialog();
    } catch (err) {
      setRebindError(String(err?.message || "Failed to rebind profile."));
    } finally {
      setRebinding(false);
    }
  }

  // --- Baseline CV replacement handlers (CP-034) ---

  function openCvReplaceDialog(profile) {
    setCvReplaceProfile(profile);
    setCvReplacePreview(null);
    setCvReplaceError("");
  }

  function closeCvReplaceDialog() {
    setCvReplaceProfile(null);
    setCvReplacePreview(null);
    setCvReplacePreviewing(false);
    setCvReplaceConfirming(false);
    setCvReplaceError("");
  }

  async function handleCvReplacePreview(assetId) {
    const profileId = cvReplaceProfile?.profile_id;
    if (!profileId) throw new Error("No profile selected.");
    setCvReplacePreviewing(true);
    setCvReplaceError("");
    try {
      const preview = await request(
        `/career-profiles/${profileId}/baseline-cv-replacement-preview`,
        { method: "POST", body: JSON.stringify({ asset_id: assetId }) },
        { rawPath: true }
      );
      setCvReplacePreview(preview);
      return preview;
    } catch (err) {
      setCvReplaceError(String(err?.message || "Failed to generate preview."));
      throw err;
    } finally {
      setCvReplacePreviewing(false);
    }
  }

  async function handleCvReplaceConfirm(preview, acceptedActions) {
    const profileId = cvReplaceProfile?.profile_id;
    if (!profileId) return;
    setCvReplaceConfirming(true);
    setCvReplaceError("");
    try {
      const updated = await request(
        `/career-profiles/${profileId}/baseline-cv-replacement-confirm`,
        {
          method: "POST",
          body: JSON.stringify({ preview: preview, accepted_actions: acceptedActions }),
        },
        { rawPath: true }
      );
      setProfiles((prev) => prev.map((p) => (p.profile_id === updated.profile_id ? updated : p)));
      closeCvReplaceDialog();
    } catch (err) {
      setCvReplaceError(String(err?.message || "Failed to replace baseline CV."));
    } finally {
      setCvReplaceConfirming(false);
    }
  }



  function resolveWorkspaceName(workspaceId) {
    return workspaceMap[workspaceId] || workspaceId;
  }

  const userWorkspaces = useMemo(
    () => (workspacesData?.workspaces || []).filter((ws) => {
      const metadata = ws.metadata || {};
      const wsType = String(ws.workspace_type || "").trim().toLowerCase();
      return !(
        wsType === "internal" ||
        wsType === "system" ||
        metadata.internal ||
        metadata.system
      );
    }),
    [workspacesData],
  );

  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-7 shadow-soft">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-4xl">
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              Career Profiles
            </div>
            <h2 className="mt-4 font-headline text-[2.35rem] font-extrabold leading-tight tracking-tight text-on-surface">
              Your Career Profiles
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-on-surface-variant">
              Create a career profile before adding or analysing evidence. Each profile tracks your
              progress from initial setup through evidence extraction, review, and tailoring readiness.
            </p>
          </div>
          <div className="flex w-full flex-col gap-3 xl:max-w-xs">
            <button
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90"
              onClick={handleShowForm} type="button"
            >
              Create career profile
              <span className="material-symbols-outlined text-[18px]">add</span>
            </button>
          </div>
        </div>
      </section>

      {showForm ? (
        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
          <h3 className="font-headline text-xl font-bold text-on-surface">Create career profile</h3>
          <p className="mt-1 text-sm leading-6 text-on-surface-variant">
            Name your profile and set your preferred language and optional target direction.
          </p>
          <form className="mt-6 space-y-5" onSubmit={handleCreateProfile}>
            <div>
              <label className="block text-sm font-semibold text-on-surface" htmlFor="profile-name">
                Profile name <span className="text-error">*</span>
              </label>
              <input
                autoFocus
                className="mt-1.5 w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                id="profile-name" maxLength={200}
                onChange={(e) => handleFieldChange("name", e.target.value)}
                placeholder="e.g. Product Management 2026" required type="text"
                value={form.name}
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-on-surface" htmlFor="profile-description">
                Description (optional)
              </label>
              <textarea
                className="mt-1.5 w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                id="profile-description"
                onChange={(e) => handleFieldChange("description", e.target.value)}
                placeholder="Brief description of your career goals or focus areas..."
                rows={3} value={form.description}
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-on-surface" htmlFor="profile-language">
                Preferred language
              </label>
              <select
                className="mt-1.5 w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                id="profile-language"
                onChange={(e) => handleFieldChange("preferred_language", e.target.value)}
                value={form.preferred_language}
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-on-surface" htmlFor="profile-direction">
                Target direction (optional)
              </label>
              <input
                className="mt-1.5 w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                id="profile-direction" maxLength={200}
                onChange={(e) => handleFieldChange("target_direction", e.target.value)}
                placeholder="e.g. Engineering Manager, Senior SWE" type="text"
                value={form.target_direction}
              />
            </div>
            {formError ? (
              <div className="rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
                {formError}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-3">
              <button
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={saving} type="submit"
              >
                {saving ? "Creating..." : "Create profile"}
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-xl bg-surface-container-low px-5 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                disabled={saving} onClick={handleCancelForm} type="button"
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="space-y-4">
        <h3 className="font-headline text-xl font-bold text-on-surface">
          {profiles.length} profile{profiles.length === 1 ? "" : "s"}
        </h3>
        {loading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div className="h-28 animate-pulse rounded-2xl bg-surface-container" key={i} />
            ))}
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-error/20 bg-surface-container-lowest p-6 text-sm text-error">
            {error}
          </div>
        ) : profiles.length === 0 && !showForm ? (
          <div className="rounded-2xl border border-dashed border-outline-variant/20 bg-surface-container-lowest p-8 text-center">
            <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">person</span>
            <p className="mt-3 text-sm leading-6 text-on-surface-variant">
              No career profiles yet. Create one to start building evidence and tailoring applications.
            </p>
            <button
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90"
              onClick={handleShowForm} type="button"
            >
              Create career profile
              <span className="material-symbols-outlined text-[18px]">add</span>
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {profiles.map((profile) => {
              const isBound = Boolean(profile.bound_workspace_id);
              const workspaceName = isBound ? resolveWorkspaceName(profile.bound_workspace_id) : "";
              return (
                <div
                  className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft transition-colors hover:border-outline-variant/40"
                  key={profile.profile_id}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-headline text-lg font-bold text-on-surface truncate">
                          {profile.name}
                        </h4>
                        <StatusBadge tone={STATUS_TONES[profile.status] || "neutral"}>
                          {STATUS_LABELS[profile.status] || profile.status}
                        </StatusBadge>
                        {isBound ? (
                          <button
                            className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
                            onClick={() => navigate(`/workspaces?workspace_id=${profile.bound_workspace_id}`)}
                            title={`Bound to workspace: ${workspaceName}`}
                            type="button"
                          >
                            <span className="material-symbols-outlined text-[14px]">workspaces</span>
                            {workspaceName}
                          </button>
                        ) : null}
                        {profile.status === "unbound" ? (
                          <span className="inline-flex items-center gap-1 text-xs text-on-surface-variant/70" title={profile.metadata?.unbound_reason || "Profile was unbound"}>
                            <span className="material-symbols-outlined text-[14px]">info</span>
                            Preserved &mdash; workspace deleted
                          </span>
                        ) : null}
                      </div>
                      {profile.description ? (
                        <p className="mt-1 text-sm leading-6 text-on-surface-variant line-clamp-2">
                          {profile.description}
                        </p>
                      ) : null}
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-on-surface-variant">
                        {profile.target_direction ? (
                          <span className="inline-flex items-center gap-1">
                            <span className="material-symbols-outlined text-[14px]">target</span>
                            {profile.target_direction}
                          </span>
                        ) : null}
                        <span className="inline-flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px]">language</span>
                          {profile.preferred_language.toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      {isBound ? (
                        <>
                          <button
                            className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                            onClick={() => openRebindDialog(profile)}
                            type="button"
                          >
                            Rebind
                          </button>
                          <button
                            className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-error-container hover:text-on-error-container"
                            onClick={() => handleUnbindWorkspace(profile.profile_id)}
                            type="button"
                          >
                            Unbind
                          </button>
                        </>
                      ) : (
                        <button
                          className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                          onClick={() => openBindDialog(profile.profile_id, "bind")}
                          type="button"
                        >
                          Bind to workspace
                          <span className="material-symbols-outlined text-[16px]">link</span>
                        </button>
                      )}
                      <button
                        className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                        onClick={() => setSourceProfileId(profile.profile_id)}
                        type="button"
                      >
                        Select sources
                        <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                      </button>
                      <button
                        className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                        onClick={() => openCvReplaceDialog(profile)}
                        type="button"
                      >
                        Replace baseline CV
                        <span className="material-symbols-outlined text-[16px]">swap_horiz</span>
                      </button>

                    </div>
                  </div>
                  <p className="mt-3 text-xs text-on-surface-variant/60">
                    Created {new Date(profile.created_at).toLocaleDateString()}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Source Selection Step */}
      {sourceProfileId ? (
        <>
          {sourceError ? (
            <div className="mb-4 rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
              {sourceError}
            </div>
          ) : null}
          <CareerProfileSourceSelector
          baselineCvAssetId={
            (profiles.find((p) => p.profile_id === sourceProfileId) || {}).baseline_cv_asset_id || ""
          }
          onCancel={() => { setSourceProfileId(""); setSourceError(""); }}
          onSave={handleSaveSourceSelection}
          profileName={
            (profiles.find((p) => p.profile_id === sourceProfileId) || {}).name || "Career Profile"
          }
          saving={sourceSaving}
          selectedAssetIds={
            (profiles.find((p) => p.profile_id === sourceProfileId) || {}).metadata?.source_asset_ids || []
          }
        />
        </>
      ) : null}

      {/* Binding Dialog */}
      {bindingProfileId ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={closeBindDialog}>
          <div
            className="w-full max-w-md rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-headline text-xl font-bold text-on-surface">
              {bindingAction === "rebind" ? "Change Workspace Binding" : "Bind to Workspace"}
            </h3>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              {bindingAction === "rebind"
                ? "Select a different workspace to bind this career profile to."
                : "Select a workspace to connect this career profile to. This profile will be available for CV tailoring, letters, answers, and interview preparation."}
            </p>
            {bindingError ? (
              <div className="mt-3 rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
                {bindingError}
              </div>
            ) : null}
            <div className="mt-4 space-y-2 max-h-64 overflow-y-auto">
              {userWorkspaces.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No workspaces available. Create a workspace first.</p>
              ) : (
                userWorkspaces.map((ws) => (
                  <button
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface px-4 py-3 text-left text-sm font-medium text-on-surface transition-colors hover:border-primary/30 hover:bg-primary/5"
                    key={ws.id}
                    onClick={() => handleBindWorkspace(ws.id)}
                    type="button"
                  >
                    <div className="font-semibold">{ws.name}</div>
                    {ws.description ? (
                      <div className="mt-0.5 text-xs text-on-surface-variant line-clamp-1">{ws.description}</div>
                    ) : null}
                  </button>
                ))
              )}
            </div>
            <div className="mt-4">
              <button
                className="w-full rounded-xl bg-surface-container-low px-4 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                onClick={closeBindDialog}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {/* Rebind Compatibility Dialog */}
      {rebindProfile ? (
        <RebindCompatibilityDialog
          confirming={rebinding}
          error={rebindError}
          onCancel={closeRebindDialog}
          onConfirm={handleRebindConfirm}
          onRequestReview={handleRebindReview}
          profile={rebindProfile}
          review={rebindReview}
          workspaces={userWorkspaces}
        />
      ) : null}

      {/* Baseline CV Replacement Dialog (CP-034) */}
      {cvReplaceProfile ? (
        <BaselineCVReplacementDialog
          confirming={cvReplaceConfirming}
          error={cvReplaceError}
          onCancel={closeCvReplaceDialog}
          onConfirm={handleCvReplaceConfirm}
          onPreview={handleCvReplacePreview}
          preview={cvReplacePreview}
          previewing={cvReplacePreviewing}
          profile={cvReplaceProfile}
          userDocuments={userDocuments}
          workspaces={userWorkspaces}
        />
      ) : null}

    </div>
  );
}

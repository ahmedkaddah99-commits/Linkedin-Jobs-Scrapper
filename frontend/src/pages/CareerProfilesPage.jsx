import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";

const STATUS_LABELS = {
  not_started: "Not started",
  extracting_evidence: "Extracting evidence",
  needs_review: "Needs review",
  ready_for_tailoring: "Ready for tailoring",
};

const STATUS_TONES = {
  not_started: "neutral",
  extracting_evidence: "primary",
  needs_review: "warning",
  ready_for_tailoring: "success",
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
            {profiles.map((profile) => (
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
                    <button
                      className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                      onClick={() => navigate(`/workspaces?profile_id=${profile.profile_id}`)}
                      type="button"
                    >
                      Select sources
                      <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                    </button>
                  </div>
                </div>
                <p className="mt-3 text-xs text-on-surface-variant/60">
                  Created {new Date(profile.created_at).toLocaleDateString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

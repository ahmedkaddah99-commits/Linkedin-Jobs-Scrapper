import { useUser } from "@clerk/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { profilePlaceholderSrc } from "../components/CvExportPreview";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import "../settings.css";

async function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read selected image."));
    reader.readAsDataURL(file);
  });
}

async function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Unable to load selected image."));
    image.src = src;
  });
}

async function cropImageToSquare(file) {
  const dataUrl = await readFileAsDataUrl(file);
  const image = await loadImageElement(dataUrl);
  const size = Math.min(image.width, image.height);
  const startX = Math.floor((image.width - size) / 2);
  const startY = Math.floor((image.height - size) / 2);
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  context.drawImage(image, startX, startY, size, size, 0, 0, 512, 512);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png", 0.95));
  if (!blob) {
    throw new Error("Unable to prepare cropped image.");
  }
  const outputFileName = file.name.replace(/\.[^.]+$/, "") || "profile-photo";
  return new File([blob], `${outputFileName}.png`, { type: "image/png" });
}

function getProfilePhotoSrc(profile = {}) {
  const photoSrc = profile.photo_data_url || profile.avatar_url || "";
  if (photoSrc) return photoSrc;
  return profilePlaceholderSrc(profile.name || "");
}

function initialsFor(profile = {}, account = {}) {
  return String(profile.name || account.display_name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] || "")
    .join("")
    .toUpperCase() || "?";
}

function SectionField({ label, children, hint = "" }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-semibold text-on-surface">{label}</span>
      {children}
      {hint ? <span className="mt-2 block text-xs text-on-surface-variant">{hint}</span> : null}
    </label>
  );
}

function TextInput(props) {
  return (
    <input
      {...props}
      className={[
        "w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm text-on-surface",
        props.className || "",
      ].join(" ")}
    />
  );
}

function ProfileCard({
  account,
  hasProfilePhoto,
  onPhotoRemove,
  onPhotoUpload,
  photoFileInputRef,
  photoUploadState,
  profile,
}) {
  return (
    <section className="relative overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-center shadow-soft">
      <div className="absolute left-0 top-0 h-24 w-full bg-gradient-to-br from-surface-container-low to-surface-container-high" />
      <div className="relative z-10">
        <div className="relative mx-auto w-fit">
          <input
            accept="image/png,image/jpeg"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onPhotoUpload(file);
              event.target.value = "";
            }}
            ref={photoFileInputRef}
            type="file"
          />
          {hasProfilePhoto ? (
            <img
              alt={profile.name || account.display_name}
              className="mx-auto h-28 w-28 rounded-full border-4 border-surface-container-lowest object-cover shadow-sm"
              src={getProfilePhotoSrc(profile)}
            />
          ) : (
            <div className="mx-auto flex h-28 w-28 items-center justify-center rounded-full bg-surface-container-high text-[2.2rem] font-bold text-on-surface-variant/60 shadow-sm">
              {initialsFor(profile, account)}
            </div>
          )}
          <button
            aria-label="Change profile photo"
            className="absolute bottom-0 right-0 rounded-full border border-outline-variant/20 bg-surface-container-lowest p-2 text-on-surface-variant shadow-sm transition-colors hover:text-primary"
            onClick={() => photoFileInputRef.current?.click()}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">edit</span>
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-sm font-medium text-on-surface transition-colors hover:border-primary/30 hover:text-primary"
            onClick={() => photoFileInputRef.current?.click()}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">upload</span>
            {hasProfilePhoto ? "Choose new photo" : "Choose photo"}
          </button>
          {hasProfilePhoto ? (
            <button
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-sm font-medium text-on-surface-variant transition-colors hover:border-error/30 hover:text-error"
              onClick={onPhotoRemove}
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">delete</span>
              Remove photo
            </button>
          ) : null}
        </div>
      </div>

      <h2 className="relative z-10 mt-6 font-headline text-2xl font-bold tracking-tight text-on-surface">
        {profile.name || account.display_name || "Account"}
      </h2>
      <p className="relative z-10 mt-1 text-sm font-medium text-primary">
        {profile.role_title || account.role || "User"}
      </p>

      <div className="relative z-10 mt-5 space-y-3 text-left">
        <div className="flex items-center gap-3 text-sm text-on-surface-variant">
          <span className="material-symbols-outlined text-[18px] text-outline">mail</span>
          {profile.email || account.email || "No email"}
        </div>
        <div className="flex items-center gap-3 text-sm text-on-surface-variant">
          <span className="material-symbols-outlined text-[18px] text-outline">location_on</span>
          {profile.location || "No location configured"}
        </div>
        <div className="flex items-center gap-3 text-sm text-on-surface-variant">
          <span className="material-symbols-outlined text-[18px] text-outline">link</span>
          {profile.website || profile.linkedin_url || "No link configured"}
        </div>
      </div>

      {photoUploadState.message ? (
        <p className="relative z-10 mt-4 rounded-lg bg-primary/10 px-3 py-2 text-xs leading-5 text-primary">
          {photoUploadState.message}
        </p>
      ) : null}
      {photoUploadState.error ? (
        <p className="relative z-10 mt-4 rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
          {photoUploadState.error}
        </p>
      ) : null}
    </section>
  );
}

function PersonalDetailsSection({ account, profile, updateSection }) {
  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">Account</p>
          <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
            Personal Details
          </h2>
        </div>
        <span className="material-symbols-outlined rounded-full bg-surface-container-low p-3 text-2xl text-primary">
          account_circle
        </span>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <SectionField label="Display Name">
          <TextInput
            onChange={(event) => updateSection("account", { display_name: event.target.value })}
            value={account.display_name || ""}
          />
        </SectionField>
        <SectionField label="Account Email">
          <TextInput
            onChange={(event) => updateSection("account", { email: event.target.value })}
            type="email"
            value={account.email || ""}
          />
        </SectionField>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <SectionField label="Profile Name">
          <TextInput
            onChange={(event) => updateSection("profile", { name: event.target.value })}
            value={profile.name || ""}
          />
        </SectionField>
        <SectionField label="Role Title">
          <TextInput
            onChange={(event) => updateSection("profile", { role_title: event.target.value })}
            value={profile.role_title || ""}
          />
        </SectionField>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-3">
        <SectionField label="Industry">
          <TextInput
            onChange={(event) => updateSection("profile", { industry: event.target.value })}
            placeholder="Fintech"
            value={profile.industry || ""}
          />
        </SectionField>
        <SectionField label="Profile Email">
          <TextInput
            onChange={(event) => updateSection("profile", { email: event.target.value })}
            type="email"
            value={profile.email || ""}
          />
        </SectionField>
        <SectionField label="Location">
          <TextInput
            onChange={(event) => updateSection("profile", { location: event.target.value })}
            value={profile.location || ""}
          />
        </SectionField>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-3">
        <SectionField label="Website">
          <TextInput
            onChange={(event) => updateSection("profile", { website: event.target.value })}
            value={profile.website || ""}
          />
        </SectionField>
        <SectionField label="LinkedIn URL">
          <TextInput
            onChange={(event) => updateSection("profile", { linkedin_url: event.target.value })}
            value={profile.linkedin_url || ""}
          />
        </SectionField>
        <SectionField label="GitHub URL">
          <TextInput
            onChange={(event) => updateSection("profile", { github_url: event.target.value })}
            value={profile.github_url || ""}
          />
        </SectionField>
      </div>
    </section>
  );
}

function DeleteAccountSection({
  accountEmail,
  confirmation,
  deleteState,
  onConfirmationChange,
  onDelete,
}) {
  const normalizedConfirmation = String(confirmation || "").trim();
  const canDelete = normalizedConfirmation === "DELETE" || (
    accountEmail && normalizedConfirmation === accountEmail
  );

  return (
    <section className="rounded-xl border border-error/20 bg-error-container/40 p-6 shadow-soft">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-error">Danger Zone</p>
          <h2 className="mt-2 font-headline text-lg font-bold text-on-error-container">
            Delete Account
          </h2>
        </div>
        <span className="material-symbols-outlined rounded-full bg-error/10 p-3 text-2xl text-error">
          delete_forever
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-on-error-container">
        This deactivates your Runr account, cancels local subscription access, and signs you out.
      </p>

      <div className="mt-5 space-y-3">
        <SectionField label={`Type ${accountEmail || "DELETE"} to confirm`}>
          <TextInput
            autoComplete="off"
            onChange={(event) => onConfirmationChange(event.target.value)}
            value={confirmation}
          />
        </SectionField>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-error px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canDelete || deleteState.loading}
          onClick={onDelete}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">delete</span>
          {deleteState.loading ? "Deleting..." : "Delete account"}
        </button>
      </div>

      {deleteState.error ? (
        <p className="mt-4 rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
          {deleteState.error}
        </p>
      ) : null}
    </section>
  );
}

function AssistedApplyConnectionCard() {
  return (
    <section className="rounded-[1.75rem] border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">
            Connected apps
          </p>
          <h2 className="mt-2 font-headline text-xl font-bold text-on-surface">
            Assisted Apply browser connection
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant">
            Review extension sessions, privacy preferences, and the actions that always remain manual.
          </p>
        </div>
        <Link
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-primary/10 px-4 py-2.5 text-sm font-semibold text-primary transition-colors hover:bg-primary/20"
          to="/settings/assisted-apply"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">extension</span>
          Manage connection
        </Link>
      </div>
    </section>
  );
}

export default function SettingsPage({ onClose }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState("subscriptions");
  const dialogRef = useRef(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  const close = () => onClose ? onClose() : navigate("/jobs");
  const { disconnect, getAccessToken, request, resolvePath } = useSession();
  const preferences = useApiResource(() => request("/personalized-jobs/preferences"), [request], { cacheKey: "job-preferences", staleMs: 30000 });
  const { user: clerkUser } = useUser();
  const [draft, setDraft] = useState(null);
  const [saveState, setSaveState] = useState({ message: "", error: "" });
  const [photoUploadState, setPhotoUploadState] = useState({ uploading: false, message: "", error: "" });
  const [billingPortalState, setBillingPortalState] = useState({ loading: false, error: "" });
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteState, setDeleteState] = useState({ loading: false, error: "" });
  const photoFileInputRef = useRef(null);

  const { data, loading, error, refresh } = useApiResource(() => request("/settings"), [request], {
    cacheKey: "settings",
    staleMs: Infinity,
    backgroundRefresh: false,
  });
  const {
    data: subscriptionData,
    loading: usageLoading,
    error: usageError,
    refresh: refreshUsage,
  } = useApiResource(() => request("/billing/subscription"), [request], {
    cacheKey: "billing:subscription",
    staleMs: 300000,
    backgroundRefresh: true,
  });

  useEffect(() => {
    if (data) {
      setDraft(data);
    }
  }, [data]);

  const isDirty = useMemo(() => {
    if (!draft || !data) return false;
    return JSON.stringify(draft) !== JSON.stringify(data);
  }, [data, draft]);

  function updateSection(section, patch) {
    setDraft((current) => ({
      ...current,
      [section]: {
        ...(current?.[section] || {}),
        ...patch,
      },
    }));
  }

  async function handleSave() {
    if (!draft) return;
    setSaveState({ message: "", error: "" });
    try {
      const payload = await request("/settings", {
        method: "PUT",
        body: {
          profile: draft.profile,
          account: draft.account,
        },
      });
      setDraft(payload);
      setSaveState({ message: "Account saved.", error: "" });
      refresh().catch(() => undefined);
    } catch (saveError) {
      setSaveState({ message: "", error: saveError.message || "Unable to save account." });
    }
  }

  async function handlePhotoUpload(file) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setPhotoUploadState({
        uploading: false,
        message: "",
        error: "Profile photo must be 2MB or smaller.",
      });
      return;
    }
    setPhotoUploadState({ uploading: true, message: "", error: "" });
    try {
      const accessToken = await getAccessToken();
      const croppedFile = await cropImageToSquare(file);
      const formData = new FormData();
      formData.append("photo_file", croppedFile, croppedFile.name);
      const res = await fetch(resolvePath("/profile-photo-upload"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        body: formData,
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.error?.message || "Profile photo upload failed");
      }
      setDraft((current) => ({
        ...current,
        profile: {
          ...(current?.profile || {}),
          photo_data_url: json.photo_data_url || "",
          avatar_url: json.photo_data_url || current?.profile?.avatar_url || "",
        },
      }));
      setPhotoUploadState({
        uploading: false,
        message: "Profile photo uploaded.",
        error: "",
      });
      refresh().catch(() => undefined);
    } catch (uploadError) {
      setPhotoUploadState({
        uploading: false,
        message: "",
        error: uploadError.message || "Profile photo upload failed.",
      });
    }
  }

  function handlePhotoRemove() {
    updateSection("profile", {
      photo_data_url: "",
      avatar_url: "",
      photo_path: "",
    });
    setPhotoUploadState({
      uploading: false,
      message: "Profile photo removed. Save account to keep this change.",
      error: "",
    });
  }

  function handleDiscard() {
    if (data) {
      setDraft(data);
      setSaveState({ message: "", error: "" });
    }
  }

  async function handleManageBilling() {
    setBillingPortalState({ loading: true, error: "" });
    try {
      const payload = await request("/billing/portal", {
        method: "POST",
        body: {},
      });
      window.location.assign(payload.portal_url);
    } catch (requestError) {
      setBillingPortalState({
        loading: false,
        error: requestError.message || "Unable to open billing portal.",
      });
    }
  }

  async function handleDeleteAccount() {
    setDeleteState({ loading: true, error: "" });
    try {
      await request("/account", {
        method: "DELETE",
        body: { confirmation: deleteConfirmation },
      });
      try {
        if (typeof clerkUser?.delete === "function") {
          await clerkUser.delete();
        }
      } catch {
        // The backend account is already deactivated. Sign the user out even if Clerk deletion is unavailable.
      }
      await disconnect();
    } catch (deleteError) {
      setDeleteState({
        loading: false,
        error: deleteError.message || "Unable to delete account.",
      });
    }
  }

  const profile = draft?.profile || {};
  const account = draft?.account || {};
  const hasProfilePhoto = Boolean(String(profile.photo_data_url || profile.avatar_url || "").trim());
  const currentPlanId = String(subscriptionData?.plan_id || "free").trim() || "free";
  const currentPlanName = String(subscriptionData?.plan?.display_name || "Free").trim() || "Free";
  const subscriptionDetails = subscriptionData?.subscription || {};
  const hasBillingPortalAccess =
    currentPlanId !== "free" || Boolean(String(subscriptionData?.subscription?.creem_customer_id || "").trim());


  const tabs = [["login", "person", "Login & Security"], ["subscriptions", "account_balance_wallet", "Subscriptions"], ["alerts", "notifications", "Job Alerts Preference"], ["email", "mail", "Email Providers"]];
  const pref = preferences.data?.preferences || preferences.data || {};
  const chips = [pref.target_roles, pref.job_functions, pref.employment_types, pref.work_arrangements, pref.experience_levels, pref.preferred_locations, pref.countries].flat().filter(value => typeof value === "string" && value);
  return <dialog ref={dialogRef} className="runr-settings-dialog" aria-labelledby="settings-title" onCancel={close} onClick={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="runr-settings-layout">
      <nav className="runr-settings-menu" aria-label="Settings sections">
        <div>{tabs.map(([id, icon, label]) => <button key={id} type="button" aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}><span aria-hidden="true" className="material-symbols-outlined">{icon}</span>{label}{id === "email" ? <small>Coming soon</small> : null}</button>)}</div>
        <div className="runr-settings-footer"><a href="https://userunr.com/privacy" target="_blank" rel="noreferrer"><span className="material-symbols-outlined">description</span>Privacy Policy</a><button type="button" onClick={disconnect}><span className="material-symbols-outlined">logout</span>Log Out</button></div>
      </nav>
      <section className="runr-settings-content">
        <header><h1 id="settings-title">{tabs.find(([id]) => id === tab)[2]}</h1><button aria-label="Close settings" type="button" onClick={close}><span className="material-symbols-outlined">close</span></button></header>
        {tab === "subscriptions" ? <>
          <h2>Current Plan</h2>
          {usageLoading ? <p role="status">Loading subscription…</p> : usageError ? <p role="alert">{usageError}</p> : <div className="runr-settings-plan"><div className="runr-settings-plan-heading"><strong>{currentPlanName}</strong><Link to="/pricing" onClick={onClose}>View Detail</Link><a href="https://userunr.com/terms-and-conditions" target="_blank" rel="noreferrer">Terms and Conditions</a></div><div className="runr-settings-plan-action"><p>{currentPlanId === "free" ? "Unlock more features with Runr Pro" : `Subscription status: ${subscriptionDetails.status || "Not available"}`}</p>{hasBillingPortalAccess ? <button type="button" disabled={billingPortalState.loading} onClick={handleManageBilling}>{billingPortalState.loading ? "Opening…" : "Manage subscription"}</button> : <Link to="/pricing" onClick={onClose}>Upgrade Now</Link>}</div></div>}
          {billingPortalState.error ? <p role="alert">{billingPortalState.error}</p> : null}
          <div className="runr-settings-refresh"><h3>Not Seeing Your Updated Subscription?</h3><p>If you’ve completed your payment or changed your subscription but don’t see the latest status, refresh your subscription or contact support for assistance.</p><button type="button" disabled={usageLoading} onClick={() => refreshUsage().catch(() => undefined)}>Refresh Status</button><a href="https://userunr.com/#contact" target="_blank" rel="noreferrer">Contact Support</a></div>
        </> : null}
        {tab === "alerts" ? <><div className="runr-settings-chips">{[...new Set(chips)].map(chip => <span key={chip}>{chip.replaceAll("_", " ")}</span>)}<Link to="/jobs" onClick={onClose}><span className="material-symbols-outlined">edit</span>Filters</Link></div><p className="runr-settings-coming-note">Automatic emails <span className="runr-coming-soon">Coming soon</span></p>{[["Instant Job Alerts", "Be the first to apply — get fresh, tailored job alerts within an hour of posting.", ["Up to 1 alert/day", "Up to 2 alerts/day", "Up to 5 alerts/day", "Unlimited"]], ["Digest Job Alerts", "Receive a curated list of matching job opportunities in a single email, delivered daily or weekly.", ["Daily", "Weekly"]]].map(([title, description, options]) => <section className="runr-settings-alert" key={title}><h2>{title}<span className="runr-coming-soon">Coming soon</span></h2><div><label>Enable {title}<small>{description}</small></label><button type="button" role="switch" aria-label={`Enable ${title}`} aria-checked="false" disabled className="runr-settings-switch"><span /></button></div><div><label htmlFor={title}>Job Alerts Frequency</label><select id={title} disabled defaultValue={options[0]}>{options.map(option => <option key={option}>{option}</option>)}</select></div></section>)}</> : null}
        {tab === "email" ? <><h2>Automatic emails <span className="runr-coming-soon">Coming soon</span></h2><p className="runr-settings-coming-note">Connect an email provider to receive job alerts when this feature becomes available.</p><button type="button" disabled className="runr-settings-provider">Connect email provider</button></> : null}
        {tab === "login" ? <>{loading && !draft ? <p role="status">Loading account…</p> : error && !draft ? <><p role="alert">{error}</p><button type="button" onClick={() => refresh().catch(() => undefined)}>Retry</button></> : draft ? <div className="runr-settings-account"><ProfileCard account={account} profile={profile} hasProfilePhoto={hasProfilePhoto} onPhotoRemove={handlePhotoRemove} onPhotoUpload={handlePhotoUpload} photoFileInputRef={photoFileInputRef} photoUploadState={photoUploadState} /><PersonalDetailsSection account={account} profile={profile} updateSection={updateSection} /><div className="runr-settings-save"><p role="status">{saveState.error || saveState.message}</p><button type="button" onClick={handleDiscard}>Discard Changes</button><button type="button" disabled={!isDirty} onClick={handleSave}>Save Account</button></div><AssistedApplyConnectionCard /><DeleteAccountSection accountEmail={account.email || ""} confirmation={deleteConfirmation} deleteState={deleteState} onConfirmationChange={setDeleteConfirmation} onDelete={handleDeleteAccount} /></div> : null}</> : null}
      </section>
    </div>
  </dialog>;
}

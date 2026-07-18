import { useUser } from "@clerk/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { profilePlaceholderSrc } from "../components/CvExportPreview";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";

const usageLabels = {
  runs_per_month: "Runs",
  applications_per_month: "Applications",
  cv_exports_per_month: "CV exports",
  referral_drafts_per_month: "Referral drafts",
  runner_credits_per_month: "Runner credits",
  workspaces: "Workspaces",
};

function formatUsageLimit(limit) {
  return Number(limit) === -1 ? "Unlimited" : String(limit ?? 0);
}

function formatDateTime(value) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue) return "Not available";
  const parsed = new Date(normalizedValue);
  if (Number.isNaN(parsed.getTime())) return normalizedValue;
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function UsageMetric({ label, quota }) {
  const used = Number(quota?.used || 0);
  const limit = Number(quota?.limit ?? 0);
  const isUnlimited = Boolean(quota?.is_unlimited) || limit === -1;
  const width = isUnlimited
    ? 24
    : Math.max(8, Math.min(100, (used / Math.max(1, limit)) * 100));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4 text-sm">
        <span className="font-medium text-on-surface">{label}</span>
        <span className="text-on-surface-variant">
          {used} / {formatUsageLimit(limit)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-container-high">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

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

function BillingSection({
  billingPortalState,
  currentPlanId,
  currentPlanName,
  hasBillingPortalAccess,
  onManageBilling,
  onRefreshUsage,
  scrapeopsPolicy,
  subscriptionDetails,
  usageError,
  usageLoading,
  usageQuotas,
}) {
  const subscriptionStatus = String(subscriptionDetails.status || "").trim();

  return (
    <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary/80">Billing</p>
          <h2 className="mt-2 font-headline text-2xl font-bold tracking-tight text-on-surface">
            Plan And Consumption
          </h2>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={onRefreshUsage}
          type="button"
        >
          <span className="material-symbols-outlined text-[18px]">refresh</span>
          Refresh
        </button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="rounded-xl border border-outline-variant/10 bg-surface p-5">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-on-surface-variant">
            Current Plan
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <div className="font-headline text-3xl font-bold text-on-surface">{currentPlanName}</div>
            {subscriptionStatus ? (
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-primary">
                {subscriptionStatus}
              </span>
            ) : null}
          </div>
          <p className="mt-3 text-sm leading-6 text-on-surface-variant">
            Period: {formatDateTime(subscriptionDetails.current_period_start)} to{" "}
            {formatDateTime(subscriptionDetails.current_period_end)}.
          </p>

          <div className="mt-5 flex flex-wrap gap-3">
            {hasBillingPortalAccess ? (
              <button
                className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={billingPortalState.loading}
                onClick={onManageBilling}
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">credit_card</span>
                {billingPortalState.loading ? "Opening..." : "Manage billing"}
              </button>
            ) : (
              <Link
                className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                to="/pricing"
              >
                <span className="material-symbols-outlined text-[18px]">diamond</span>
                Choose a plan
              </Link>
            )}
            {currentPlanId !== "none" ? (
              <Link
                className="inline-flex items-center justify-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                to="/pricing"
              >
                Compare plans
              </Link>
            ) : null}
          </div>

          {billingPortalState.error ? (
            <p className="mt-4 rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
              {billingPortalState.error}
            </p>
          ) : null}
        </div>

        <div className="rounded-xl border border-outline-variant/10 bg-surface p-5">
          <div className="mb-5 flex items-center justify-between gap-4">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-on-surface-variant">
              This Month
            </p>
            {usageLoading ? (
              <span className="text-xs font-medium text-on-surface-variant">Loading...</span>
            ) : null}
          </div>

          {usageError ? (
            <p className="mb-4 rounded-lg bg-error-container px-3 py-2 text-xs leading-5 text-on-error-container">
              {usageError}
            </p>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(usageLabels).map(([quotaType, label]) => (
              <UsageMetric
                key={quotaType}
                label={label}
                quota={usageQuotas[quotaType] || { used: 0, limit: 0 }}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 rounded-xl border border-outline-variant/10 bg-surface p-5 text-sm text-on-surface-variant md:grid-cols-2">
        <div>
          <div className="font-semibold text-on-surface">Company sites per run</div>
          <div className="mt-2">
            {Number(scrapeopsPolicy.company_sites_per_run) === -1
              ? "Unlimited"
              : String(scrapeopsPolicy.company_sites_per_run ?? 0)}
          </div>
        </div>
        <div>
          <div className="font-semibold text-on-surface">Runner-credit budget per run</div>
          <div className="mt-2">
            {Number(scrapeopsPolicy.effective_runner_credits_per_run) === -1
              ? "Unlimited"
              : String(scrapeopsPolicy.effective_runner_credits_per_run ?? 0)}
          </div>
        </div>
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

export default function SettingsPage() {
  const { disconnect, getAccessToken, request, resolvePath } = useSession();
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
  const usageQuotas = subscriptionData?.usage?.quotas || {};
  const currentPlanId = String(subscriptionData?.plan_id || "none").trim() || "none";
  const currentPlanName = String(subscriptionData?.plan?.display_name || "No subscription").trim() || "No subscription";
  const subscriptionDetails = subscriptionData?.subscription || {};
  const hasBillingPortalAccess =
    currentPlanId !== "none" || Boolean(String(subscriptionData?.subscription?.creem_customer_id || "").trim());
  const scrapeopsPolicy = subscriptionData?.scrapeops_usage?.policy || {};

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-primary">Account</p>
          <h1 className="mt-3 font-headline text-[2rem] font-extrabold leading-tight tracking-tight text-on-surface">
            Account Settings
          </h1>
        </div>
        <Link
          className="inline-flex w-fit items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          to="/documents"
        >
          <span className="material-symbols-outlined text-[18px]">inventory_2</span>
          Career Assets
        </Link>
      </section>

      {loading && !draft ? (
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8 text-on-surface-variant">
          Loading account...
        </div>
      ) : error && !draft ? (
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-8">
          <p className="text-error">{error}</p>
          <button
            className="mt-4 rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : draft ? (
        <div className="space-y-8">
          <div className="grid grid-cols-1 gap-8 xl:grid-cols-12">
            <div className="flex flex-col gap-8 xl:col-span-4">
              <ProfileCard
                account={account}
                hasProfilePhoto={hasProfilePhoto}
                onPhotoRemove={handlePhotoRemove}
                onPhotoUpload={handlePhotoUpload}
                photoFileInputRef={photoFileInputRef}
                photoUploadState={photoUploadState}
                profile={profile}
              />
            </div>

            <div className="flex flex-col gap-8 xl:col-span-8">
              <PersonalDetailsSection
                account={account}
                profile={profile}
                updateSection={updateSection}
              />
              <BillingSection
                billingPortalState={billingPortalState}
                currentPlanId={currentPlanId}
                currentPlanName={currentPlanName}
                hasBillingPortalAccess={hasBillingPortalAccess}
                onManageBilling={handleManageBilling}
                onRefreshUsage={() => refreshUsage().catch(() => undefined)}
                scrapeopsPolicy={scrapeopsPolicy}
                subscriptionDetails={subscriptionDetails}
                usageError={usageError}
                usageLoading={usageLoading}
                usageQuotas={usageQuotas}
              />
              <AssistedApplyConnectionCard />

              <div className="sticky bottom-8 self-end rounded-xl border border-outline-variant/20 bg-surface-container-lowest/80 p-4 shadow-soft backdrop-blur-[20px]">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <span className="mr-auto text-sm text-on-surface-variant sm:pl-2">
                    {saveState.error
                      ? saveState.error
                      : saveState.message || (isDirty ? "You have unsaved changes" : "Everything is saved")}
                  </span>
                  <button
                    className="rounded px-5 py-2.5 text-sm font-medium text-on-surface-variant transition-colors hover:text-on-surface active:scale-[0.98]"
                    onClick={handleDiscard}
                    type="button"
                  >
                    Discard Changes
                  </button>
                  <button
                    className="flex items-center justify-center gap-2 rounded-lg bg-gradient-to-br from-primary to-primary-container px-6 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:saturate-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={!isDirty}
                    onClick={handleSave}
                    type="button"
                  >
                    <span className="material-symbols-outlined text-[18px]">save</span>
                    Save Account
                  </button>
                </div>
              </div>
            </div>
          </div>

          <DeleteAccountSection
            accountEmail={account.email || ""}
            confirmation={deleteConfirmation}
            deleteState={deleteState}
            onConfirmationChange={setDeleteConfirmation}
            onDelete={handleDeleteAccount}
          />
        </div>
      ) : null}
    </div>
  );
}

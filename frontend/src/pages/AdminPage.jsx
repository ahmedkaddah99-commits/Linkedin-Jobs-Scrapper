import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorMessage } from "../lib/api";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

const tabs = [
  { key: "users", label: "Users", path: "/users", responseKey: "users" },
  { key: "tokens", label: "Tokens", path: "/tokens?include_inactive=true&limit=200", responseKey: "tokens" },
  { key: "secrets", label: "Secrets", path: "/secrets?limit=200", responseKey: "secrets" },
  {
    key: "templates",
    label: "Workflow Templates",
    path: "/workflow-templates?limit=200",
    responseKey: "workflow_templates",
  },
  { key: "workers", label: "Workers", path: "/workers?limit=200", responseKey: "workers" },
  { key: "promoCodes", label: "Promo Codes", path: "/admin/promo-codes?limit=200", responseKey: "promo_codes" },
];

const defaultPromoForm = {
  name: "",
  code: "",
  amount_type: "percent",
  amount: "",
  starts_at: "",
  expires_at: "",
  max_redemptions: "",
};

function renderValue(column, value) {
  if (Array.isArray(value)) {
    return value.join(", ") || "N/A";
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  if (column.endsWith("_at")) {
    return formatDateTime(value);
  }
  return String(value ?? "N/A");
}

function toIsoDateTime(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toISOString();
}

export default function AdminPage() {
  const { request } = useSession();
  const [activeTab, setActiveTab] = useState("users");
  const [showPromoForm, setShowPromoForm] = useState(false);
  const [promoForm, setPromoForm] = useState(defaultPromoForm);
  const [promoState, setPromoState] = useState({
    deletingId: "",
    error: "",
    submitting: false,
    success: "",
  });
  const activeConfig = tabs.find((tab) => tab.key === activeTab) || tabs[0];
  const isPromoCodesTab = activeConfig.key === "promoCodes";

  const { data, loading, error, refresh } = useApiResource(
    () => request(activeConfig.path),
    [request, activeConfig.key],
  );

  const rows = useMemo(() => data?.[activeConfig.responseKey] || [], [activeConfig.responseKey, data]);
  const columns = useMemo(() => {
    if (!rows.length) return [];
    return Object.keys(rows[0]).filter((column) => column !== "metadata");
  }, [rows]);

  function updatePromoField(field, value) {
    setPromoForm((currentValue) => ({
      ...currentValue,
      [field]: value,
    }));
  }

  async function handleCreatePromoCode(event) {
    event.preventDefault();
    setPromoState({
      deletingId: "",
      error: "",
      submitting: true,
      success: "",
    });
    try {
      const payload = await request("/admin/promo-codes", {
        method: "POST",
        body: {
          name: promoForm.name.trim(),
          code: promoForm.code.trim().toUpperCase(),
          amount_type: promoForm.amount_type,
          amount: promoForm.amount.trim(),
          starts_at: toIsoDateTime(promoForm.starts_at),
          expires_at: toIsoDateTime(promoForm.expires_at),
          max_redemptions: promoForm.max_redemptions.trim(),
        },
      });
      setPromoForm(defaultPromoForm);
      setShowPromoForm(false);
      setPromoState({
        deletingId: "",
        error: "",
        submitting: false,
        success: `Created promo code ${String(payload?.promo_code?.code || "").trim() || "successfully"}.`,
      });
      refresh().catch(() => undefined);
    } catch (requestError) {
      setPromoState({
        deletingId: "",
        error: getApiErrorMessage(requestError, "Unable to create the promo code."),
        submitting: false,
        success: "",
      });
    }
  }

  async function handleDeletePromoCode(discountId, code) {
    const normalizedDiscountId = String(discountId || "").trim();
    if (!normalizedDiscountId) {
      return;
    }
    if (!window.confirm(`Delete promo code ${String(code || normalizedDiscountId).trim()}?`)) {
      return;
    }
    setPromoState((currentValue) => ({
      ...currentValue,
      deletingId: normalizedDiscountId,
      error: "",
      success: "",
    }));
    try {
      await request(`/admin/promo-codes/${normalizedDiscountId}`, {
        method: "DELETE",
      });
      setPromoState({
        deletingId: "",
        error: "",
        submitting: false,
        success: `Deleted promo code ${String(code || normalizedDiscountId).trim()}.`,
      });
      refresh().catch(() => undefined);
    } catch (requestError) {
      setPromoState({
        deletingId: "",
        error: getApiErrorMessage(requestError, "Unable to delete the promo code."),
        submitting: false,
        success: "",
      });
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-2">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
            Admin
          </h1>
          <p className="text-sm text-on-surface-variant">
            Internal control room for users, access, secrets, templates, workers, analytics, ScrapeOps operations, and billing promos.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            className="inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90"
            to="/admin/acquisition"
          >
            <span className="material-symbols-outlined text-[18px]">hub</span>
            Acquisition admin
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            to="/admin/job-import"
          >
            <span className="material-symbols-outlined text-[18px]">work_history</span>
            Job Import dashboard
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            to="/admin/scrapeops"
          >
            <span className="material-symbols-outlined text-[18px]">monitoring</span>
            ScrapeOps Dashboard
          </Link>
          <Link
            className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
            to="/admin/events"
          >
            <span className="material-symbols-outlined text-[18px]">timeline</span>
            Event Explorer
          </Link>
        </div>
      </header>

      <section className="flex flex-wrap gap-2 rounded-xl bg-surface-container-low p-2">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={[
              "rounded-md px-4 py-2 text-sm font-medium transition-colors",
              activeTab === tab.key
                ? "bg-surface-container-lowest text-on-surface shadow-soft"
                : "text-on-surface-variant hover:bg-surface-container-high",
            ].join(" ")}
            onClick={() => setActiveTab(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </section>

      {isPromoCodesTab ? (
        <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="font-headline text-xl font-bold text-on-surface">Promo Code Issuance</h2>
              <p className="mt-1 text-sm text-on-surface-variant">
                Codes are created in Creem and limited to the paid Runr plans.
              </p>
            </div>
            <button
              className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm"
              onClick={() => setShowPromoForm((currentValue) => !currentValue)}
              type="button"
            >
              {showPromoForm ? "Hide form" : "Create promo code"}
            </button>
          </div>

          {showPromoForm ? (
            <form className="mt-6 space-y-5" onSubmit={handleCreatePromoCode}>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">Name</span>
                  <input
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface outline-none transition-colors focus:border-primary/40"
                    onChange={(event) => updatePromoField("name", event.target.value)}
                    placeholder="Summer launch"
                    type="text"
                    value={promoForm.name}
                  />
                </label>

                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">Code</span>
                  <input
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 font-mono uppercase text-on-surface outline-none transition-colors focus:border-primary/40"
                    onChange={(event) => updatePromoField("code", event.target.value.toUpperCase())}
                    placeholder="SUMMER10"
                    type="text"
                    value={promoForm.code}
                  />
                </label>

                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">Discount type</span>
                  <select
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface outline-none transition-colors focus:border-primary/40"
                    onChange={(event) => updatePromoField("amount_type", event.target.value)}
                    value={promoForm.amount_type}
                  >
                    <option value="percent">Percent</option>
                    <option value="fixed">Fixed amount</option>
                  </select>
                </label>

                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">
                    {promoForm.amount_type === "fixed" ? "Amount (EUR)" : "Amount (%)"}
                  </span>
                  <input
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface outline-none transition-colors focus:border-primary/40"
                    inputMode="decimal"
                    onChange={(event) => updatePromoField("amount", event.target.value)}
                    placeholder={promoForm.amount_type === "fixed" ? "10.00" : "15"}
                    type="text"
                    value={promoForm.amount}
                  />
                </label>

                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">Starts at</span>
                  <input
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface outline-none transition-colors focus:border-primary/40"
                    onChange={(event) => updatePromoField("starts_at", event.target.value)}
                    type="datetime-local"
                    value={promoForm.starts_at}
                  />
                </label>

                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">Expires at</span>
                  <input
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface outline-none transition-colors focus:border-primary/40"
                    onChange={(event) => updatePromoField("expires_at", event.target.value)}
                    type="datetime-local"
                    value={promoForm.expires_at}
                  />
                </label>

                <label className="space-y-2 text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">Redemption limit</span>
                  <input
                    className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-on-surface outline-none transition-colors focus:border-primary/40"
                    inputMode="numeric"
                    onChange={(event) => updatePromoField("max_redemptions", event.target.value)}
                    placeholder="Leave blank for unlimited"
                    type="text"
                    value={promoForm.max_redemptions}
                  />
                </label>
              </div>

              {promoState.error ? (
                <p className="rounded-2xl bg-error-container px-4 py-3 text-sm text-on-error-container">
                  {promoState.error}
                </p>
              ) : null}

              {promoState.success ? (
                <p className="rounded-2xl bg-primary/10 px-4 py-3 text-sm text-primary">
                  {promoState.success}
                </p>
              ) : null}

              <div className="flex flex-wrap justify-end gap-3">
                <button
                  className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                  onClick={() => {
                    setPromoForm(defaultPromoForm);
                    setPromoState((currentValue) => ({ ...currentValue, error: "", success: "" }));
                  }}
                  type="button"
                >
                  Reset
                </button>
                <button
                  className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={promoState.submitting}
                  type="submit"
                >
                  {promoState.submitting ? "Creating..." : "Save promo code"}
                </button>
              </div>
            </form>
          ) : null}
        </section>
      ) : null}

      {!showPromoForm && isPromoCodesTab && promoState.error ? (
        <div className="rounded-2xl bg-error-container px-4 py-3 text-sm text-on-error-container">
          {promoState.error}
        </div>
      ) : null}

      {!showPromoForm && isPromoCodesTab && promoState.success ? (
        <div className="rounded-2xl bg-primary/10 px-4 py-3 text-sm text-primary">
          {promoState.success}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
        <div className="flex items-center justify-between border-b border-outline-variant/10 px-6 py-4">
          <h2 className="font-headline text-xl font-bold text-on-surface">{activeConfig.label}</h2>
          <div className="flex gap-3">
            <button
              className="rounded bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={() => refresh().catch(() => undefined)}
              type="button"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="px-6 py-4">
                    {labelize(column)}
                  </th>
                ))}
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={columns.length + 1}>
                    Loading {activeConfig.label.toLowerCase()}...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-6 py-10 text-error" colSpan={columns.length + 1}>
                    {error}
                  </td>
                </tr>
              ) : rows.length ? (
                rows.map((row, index) => (
                  <tr key={`${activeTab}-${index}`} className="hover:bg-surface-container-low">
                    {columns.map((column) => (
                      <td key={column} className="px-6 py-4 text-on-surface-variant">
                        {["status", "is_active"].includes(column) ? (
                          <StatusBadge tone={statusTone(row[column])}>
                            {column === "is_active"
                              ? row[column]
                                ? "Active"
                                : "Inactive"
                              : labelize(row[column])}
                          </StatusBadge>
                        ) : (
                          renderValue(column, row[column])
                        )}
                      </td>
                    ))}
                    <td className="px-6 py-4 text-right">
                      {isPromoCodesTab ? (
                        <button
                          className="text-sm font-medium text-error hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={promoState.deletingId === row.discount_id}
                          onClick={() => handleDeletePromoCode(row.discount_id, row.code)}
                          type="button"
                        >
                          {promoState.deletingId === row.discount_id ? "Deleting..." : "Delete"}
                        </button>
                      ) : (
                        <button className="text-sm font-medium text-primary hover:text-primary-container" type="button">
                          Open
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={columns.length + 1}>
                    No {activeConfig.label.toLowerCase()} found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

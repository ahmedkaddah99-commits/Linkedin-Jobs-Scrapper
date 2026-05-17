import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
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
];

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

export default function AdminPage() {
  const { request } = useSession();
  const [activeTab, setActiveTab] = useState("users");
  const activeConfig = tabs.find((tab) => tab.key === activeTab);

  const { data, loading, error, refresh } = useApiResource(
    () => request(activeConfig.path),
    [request, activeConfig.key],
  );

  const rows = useMemo(() => data?.[activeConfig.responseKey] || [], [activeConfig.responseKey, data]);
  const columns = useMemo(() => {
    if (!rows.length) return [];
    return Object.keys(rows[0]).filter((column) => column !== "metadata");
  }, [rows]);

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-2">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
            Admin
          </h1>
          <p className="text-sm text-on-surface-variant">
            Internal control room for users, access, secrets, templates, workers, and analytics events.
          </p>
        </div>
        <Link
          className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15"
          to="/admin/events"
        >
          <span className="material-symbols-outlined text-[18px]">timeline</span>
          Event Explorer
        </Link>
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
            <button className="rounded bg-gradient-to-br from-primary to-primary-container px-4 py-2 text-sm font-medium text-white shadow-sm">
              Create
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
                      <button className="text-sm font-medium text-primary hover:text-primary-container">
                        Open
                      </button>
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

import { useMemo, useState } from "react";
import StatusBadge from "../components/StatusBadge";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { formatDateTime, labelize, statusTone } from "../lib/formatters";

export default function ArtifactsPage() {
  const { request } = useSession();
  const [filters, setFilters] = useState({
    search: "",
    workspaceId: "",
    runId: "",
    artifactType: "",
  });

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", "200");
    if (filters.workspaceId) params.set("workspace_id", filters.workspaceId);
    if (filters.runId) params.set("run_id", filters.runId);
    if (filters.artifactType) params.set("artifact_type", filters.artifactType);
    return params.toString();
  }, [filters]);

  const { data, loading, error, refresh } = useApiResource(
    () => request(`/artifacts?${queryString}`),
    [request, queryString],
  );

  const allArtifacts = data?.artifacts || [];
  const artifacts = useMemo(() => {
    const query = filters.search.trim().toLowerCase();
    if (!query) return allArtifacts;
    return allArtifacts.filter((item) =>
      [item.file_name, item.job_title, item.company, item.workspace_name, item.run_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }, [allArtifacts, filters.search]);

  const workspaceOptions = Array.from(
    new Map(allArtifacts.map((item) => [item.workspace_id, item.workspace_name])).entries(),
  );
  const runOptions = Array.from(new Set(allArtifacts.map((item) => item.run_id)));
  const typeOptions = Array.from(new Set(allArtifacts.map((item) => item.artifact_type)));

  async function downloadArtifact(artifact) {
    const blob = await request(artifact.download_url, { responseType: "blob" });
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = artifact.file_name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(objectUrl);
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Artifacts
        </h1>
        <p className="text-sm text-on-surface-variant">
          Generated file library for CVs, PDFs, trackers, packages, and exports.
        </p>
      </header>

      <section className="rounded-xl bg-surface-container-low p-4">
        <div className="grid gap-4 md:grid-cols-5">
          <input
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm"
            onChange={(event) =>
              setFilters((current) => ({ ...current, search: event.target.value }))
            }
            placeholder="Search file or job"
            type="text"
            value={filters.search}
          />
          <select
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm"
            onChange={(event) =>
              setFilters((current) => ({ ...current, workspaceId: event.target.value }))
            }
            value={filters.workspaceId}
          >
            <option value="">Workspace</option>
            {workspaceOptions.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm"
            onChange={(event) =>
              setFilters((current) => ({ ...current, runId: event.target.value }))
            }
            value={filters.runId}
          >
            <option value="">Run</option>
            {runOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm"
            onChange={(event) =>
              setFilters((current) => ({ ...current, artifactType: event.target.value }))
            }
            value={filters.artifactType}
          >
            <option value="">Artifact Type</option>
            {typeOptions.map((item) => (
              <option key={item} value={item}>
                {labelize(item)}
              </option>
            ))}
          </select>
          <button
            className="rounded border border-outline-variant/20 bg-surface-container-lowest px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
            onClick={() => refresh().catch(() => undefined)}
            type="button"
          >
            Refresh
          </button>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-lowest">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-container-low text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              <tr>
                <th className="px-6 py-4">File</th>
                <th className="px-6 py-4">Job / Company</th>
                <th className="px-6 py-4">Workspace</th>
                <th className="px-6 py-4">Run</th>
                <th className="px-6 py-4">Created</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={7}>
                    Loading artifacts...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-6 py-10 text-error" colSpan={7}>
                    {error}
                  </td>
                </tr>
              ) : artifacts.length ? (
                artifacts.map((artifact) => (
                  <tr key={`${artifact.run_id}-${artifact.artifact_id}`} className="hover:bg-surface-container-low">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-on-surface">{artifact.file_name}</div>
                      <div className="mt-1 text-xs text-on-surface-variant">
                        {labelize(artifact.artifact_type)}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">
                      {[artifact.job_title, artifact.company].filter(Boolean).join(" • ") ||
                        "Run-level export"}
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">{artifact.workspace_name}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{artifact.run_id}</td>
                    <td className="px-6 py-4 text-on-surface-variant">
                      {formatDateTime(artifact.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge tone={statusTone(artifact.status)}>
                        {labelize(artifact.status)}
                      </StatusBadge>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-3">
                        <button
                          className="text-sm font-medium text-primary hover:text-primary-container"
                          onClick={() => downloadArtifact(artifact)}
                          type="button"
                        >
                          Preview
                        </button>
                        <button
                          className="text-sm font-medium text-primary hover:text-primary-container"
                          onClick={() => downloadArtifact(artifact)}
                          type="button"
                        >
                          Download
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-6 py-10 text-on-surface-variant" colSpan={7}>
                    No artifacts are available yet.
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

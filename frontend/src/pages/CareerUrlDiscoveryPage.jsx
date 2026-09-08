import { useState } from "react";
import { useSession } from "../context/SessionContext";

const sourceOptions = [
  {
    id: "regular",
    label: "Regular companies",
    description: "Uses the master company website list.",
  },
  {
    id: "phd",
    label: "Universities / PhD",
    description: "Uses the European university website list.",
  },
];

function scoreLabel(score) {
  const value = Number(score || 0);
  if (value >= 0.8) return "Strong match";
  if (value >= 0.55) return "Good match";
  if (value > 0) return "Needs review";
  return "Not found";
}

function statusLabel(status) {
  if (status === "found") return "Found";
  if (status === "low_confidence") return "Needs review";
  if (status === "homepage_fetch_failed") return "Website did not load";
  if (status === "missing_homepage_or_domain") return "Missing website";
  return "Not found";
}

export default function CareerUrlDiscoveryPage() {
  const { request } = useSession();
  const [source, setSource] = useState("regular");
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [useRenderedFallback, setUseRenderedFallback] = useState(false);
  const [saveMysql, setSaveMysql] = useState(false);
  const [state, setState] = useState({
    busy: false,
    error: "",
    summary: null,
  });

  async function runDiscovery() {
    setState({ busy: true, error: "", summary: null });
    try {
      const payload = await request("/career-url-discovery/run", {
        method: "POST",
        body: {
          source,
          limit,
          offset,
          use_rendered_fallback: useRenderedFallback,
          save_mysql: saveMysql,
        },
      });
      setState({ busy: false, error: "", summary: payload });
    } catch (error) {
      setState({
        busy: false,
        error: error.message || "Unable to run career page search.",
        summary: null,
      });
    }
  }

  const results = state.summary?.results || [];

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
          Find career pages
        </h1>
        <p className="max-w-3xl text-sm leading-6 text-on-surface-variant">
          Check company and university websites, find their most likely careers page, and save the list
          for later job collection. When a workspace uses Company Career Sites, Runr now uses this saved list automatically.
        </p>
      </header>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-5">
          <div className="mb-5 flex items-center gap-3">
            <span className="material-symbols-outlined rounded-lg bg-primary/10 p-2 text-primary">
              travel_explore
            </span>
            <div>
              <h2 className="text-lg font-bold text-on-surface">Search setup</h2>
              <p className="text-sm text-on-surface-variant">Choose the list and how many websites to check.</p>
            </div>
          </div>

          <div className="space-y-5">
            <div>
              <p className="mb-2 text-sm font-semibold text-on-surface">Website list</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {sourceOptions.map((option) => {
                  const active = source === option.id;
                  return (
                    <button
                      className={[
                        "rounded-lg border p-4 text-left transition-colors",
                        active
                          ? "border-primary bg-primary/10 text-on-surface"
                          : "border-outline-variant/20 bg-surface hover:border-primary/50",
                      ].join(" ")}
                      key={option.id}
                      onClick={() => setSource(option.id)}
                      type="button"
                    >
                      <span className="block text-sm font-bold">{option.label}</span>
                      <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
                        {option.description}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-on-surface">How many to check</span>
                <input
                  className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm"
                  max="500"
                  min="1"
                  onChange={(event) => setLimit(Number(event.target.value || 1))}
                  type="number"
                  value={limit}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-on-surface">Start after row</span>
                <input
                  className="w-full rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-sm"
                  min="0"
                  onChange={(event) => setOffset(Number(event.target.value || 0))}
                  type="number"
                  value={offset}
                />
              </label>
            </div>

            <div className="space-y-3">
              <button
                className="flex w-full items-center justify-between gap-4 rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-left"
                onClick={() => setUseRenderedFallback((value) => !value)}
                type="button"
              >
                <span>
                  <span className="block text-sm font-semibold text-on-surface">
                    Try slower loading for difficult websites
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
                    Useful when a careers link appears only after the page fully loads.
                  </span>
                </span>
                <span
                  className={[
                    "relative h-7 w-12 rounded-full transition-colors",
                    useRenderedFallback ? "bg-primary" : "bg-outline-variant/50",
                  ].join(" ")}
                >
                  <span
                    className={[
                      "absolute top-1 h-5 w-5 rounded-full bg-white shadow-sm transition-all",
                      useRenderedFallback ? "left-6" : "left-1",
                    ].join(" ")}
                  />
                </span>
              </button>

              <button
                className="flex w-full items-center justify-between gap-4 rounded-lg border border-outline-variant/20 bg-surface px-4 py-3 text-left"
                onClick={() => setSaveMysql((value) => !value)}
                type="button"
              >
                <span>
                  <span className="block text-sm font-semibold text-on-surface">
                    Also save to the shared database
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-on-surface-variant">
                    Use this only when the database connection has already been set up.
                  </span>
                </span>
                <span
                  className={[
                    "relative h-7 w-12 rounded-full transition-colors",
                    saveMysql ? "bg-primary" : "bg-outline-variant/50",
                  ].join(" ")}
                >
                  <span
                    className={[
                      "absolute top-1 h-5 w-5 rounded-full bg-white shadow-sm transition-all",
                      saveMysql ? "left-6" : "left-1",
                    ].join(" ")}
                  />
                </span>
              </button>
            </div>

            {state.error ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-700">
                {state.error}
              </div>
            ) : null}

            <button
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={state.busy}
              onClick={runDiscovery}
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">
                {state.busy ? "hourglass_top" : "search"}
              </span>
              {state.busy ? "Searching websites..." : "Find career pages"}
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-outline-variant/20 bg-surface p-5">
          <div className="mb-5 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-on-surface">Results</h2>
              <p className="text-sm text-on-surface-variant">
                The best pages are saved for later job collection.
              </p>
            </div>
            {state.summary ? (
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
                {state.summary.found} found
              </span>
            ) : null}
          </div>

          {state.summary ? (
            <div className="mb-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg bg-surface-container-low p-4">
                <p className="text-xs font-semibold text-on-surface-variant">Checked</p>
                <p className="mt-1 text-2xl font-extrabold text-on-surface">{state.summary.processed}</p>
              </div>
              <div className="rounded-lg bg-surface-container-low p-4">
                <p className="text-xs font-semibold text-on-surface-variant">Found</p>
                <p className="mt-1 text-2xl font-extrabold text-on-surface">{state.summary.found}</p>
              </div>
              <div className="rounded-lg bg-surface-container-low p-4">
                <p className="text-xs font-semibold text-on-surface-variant">Needs another pass</p>
                <p className="mt-1 text-2xl font-extrabold text-on-surface">{state.summary.not_found}</p>
              </div>
            </div>
          ) : null}

          {state.summary?.saved_list_path ? (
            <div className="mb-5 rounded-lg border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm">
              <span className="font-semibold text-on-surface">Saved list:</span>{" "}
              <span className="break-all text-on-surface-variant">{state.summary.saved_list_path}</span>
              <p className="mt-2 text-xs leading-5 text-on-surface-variant">
                Next step: enable Company Career Sites in a workspace. If you do not paste a separate list there,
                the workspace run will use these discovered career pages.
              </p>
            </div>
          ) : null}

          <div className="space-y-3">
            {results.length ? (
              results.map((result, index) => (
                <article
                  className="rounded-lg border border-outline-variant/20 bg-surface-container-lowest p-4"
                  key={`${result.company_name}-${result.homepage_url}-${index}`}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-bold text-on-surface">
                        {result.company_name || result.homepage_url || "Unknown website"}
                      </h3>
                      <p className="mt-1 break-all text-xs text-on-surface-variant">
                        {result.homepage_url}
                      </p>
                    </div>
                    <span className="w-fit rounded-full bg-surface-container-high px-3 py-1 text-xs font-bold text-on-surface-variant">
                      {statusLabel(result.crawl_status)}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_10rem]">
                    <div>
                      <p className="text-xs font-semibold text-on-surface-variant">Best careers page</p>
                      {result.primary_career_url ? (
                        <a
                          className="mt-1 block break-all text-sm font-semibold text-primary hover:underline"
                          href={result.primary_career_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {result.primary_career_url}
                        </a>
                      ) : (
                        <p className="mt-1 text-sm text-on-surface-variant">No clear page found.</p>
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-on-surface-variant">Match quality</p>
                      <p className="mt-1 text-sm font-bold text-on-surface">
                        {scoreLabel(result.confidence_score)}
                      </p>
                    </div>
                  </div>

                  {result.ats_type ? (
                    <p className="mt-3 text-xs text-on-surface-variant">
                      Hiring system detected: <span className="font-semibold">{result.ats_type}</span>
                    </p>
                  ) : null}
                </article>
              ))
            ) : (
              <div className="rounded-lg border border-dashed border-outline-variant/40 p-8 text-center">
                <span className="material-symbols-outlined text-3xl text-on-surface-variant">
                  manage_search
                </span>
                <p className="mt-3 text-sm font-semibold text-on-surface">No search has been run yet.</p>
                <p className="mt-1 text-xs text-on-surface-variant">
                  Choose a list, set how many websites to check, then start the search.
                </p>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

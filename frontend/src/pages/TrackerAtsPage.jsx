import { Link, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { labelize } from "../lib/formatters";

function DetailList({ emptyText, items = [] }) {
  return items.length ? (
    <ul className="space-y-2 text-sm text-on-surface-variant">
      {items.map((item) => (
        <li className="rounded-xl bg-surface-container-low px-3 py-2" key={item}>
          {item}
        </li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-on-surface-variant">{emptyText}</p>
  );
}

export default function TrackerAtsPage() {
  const { reviewId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const { request } = useSession();
  const returnTo = searchParams.get("return") || "/tracker";
  const { data, loading, error } = useApiResource(
    () => request(`/tracker/${encodeURIComponent(reviewId)}/ats`),
    [request, reviewId],
  );

  if (loading) {
    return (
      <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface-variant">
        Loading ATS assessment...
      </div>
    );
  }
  if (error || !data) {
    return (
      <section className="rounded-3xl border border-error/20 bg-surface-container-lowest p-8">
        <h1 className="font-headline text-2xl font-bold text-on-surface">ATS assessment unavailable</h1>
        <p className="mt-3 text-sm text-error">{error || "This assessment could not be found."}</p>
        <Link className="mt-5 inline-flex font-semibold text-primary" to={returnTo}>Return to tracker</Link>
      </section>
    );
  }

  const score = data.score || {};
  const identifiers = data.identifiers || {};
  const jobDescription = data.job_description || {};
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-7 shadow-sm">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Read-only ATS assessment</div>
        <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="font-headline text-3xl font-extrabold text-on-surface">
              {data.application?.title || "Application"}{data.application?.company ? ` at ${data.application.company}` : ""}
            </h1>
            <p className="mt-2 text-sm text-on-surface-variant">{data.diagnostic_limitations}</p>
          </div>
          <Link className="rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary" to={returnTo}>
            Return to tracker
          </Link>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-4">
        {[
          ["Best score", `${score.best ?? 0}%`],
          ["Target", `${score.target ?? 90}%`],
          ["Gate", labelize(score.gate_state || "not_started")],
          ["Passes", `${score.attempt_count ?? 0}/${score.max_attempts ?? 3}`],
        ].map(([label, value]) => (
          <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5" key={label}>
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</div>
            <div className="mt-2 text-2xl font-bold text-on-surface">{value}</div>
          </div>
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h2 className="font-headline text-xl font-bold text-on-surface">Missing criteria</h2>
          <div className="mt-4"><DetailList emptyText="No missing criteria were persisted." items={data.criteria?.missing} /></div>
        </section>
        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h2 className="font-headline text-xl font-bold text-on-surface">Present criteria</h2>
          <div className="mt-4"><DetailList emptyText="The legacy assessment did not persist present criteria." items={data.criteria?.present} /></div>
        </section>
      </div>

      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
        <h2 className="font-headline text-xl font-bold text-on-surface">Attempt history</h2>
        <div className="mt-4 space-y-3">
          {(data.attempt_history || []).length ? data.attempt_history.map((attempt, index) => (
            <article className="rounded-2xl border border-outline-variant/15 bg-surface p-4" key={attempt.attempt || index}>
              <div className="flex flex-wrap gap-3 font-semibold text-on-surface">
                <span>Pass {attempt.attempt || index + 1}</span>
                <span>{attempt.score ?? 0}%</span>
              </div>
              {attempt.change_summary ? <p className="mt-2 text-sm text-on-surface-variant">{attempt.change_summary}</p> : null}
              {attempt.rationale ? <p className="mt-2 text-sm text-on-surface-variant">{attempt.rationale}</p> : null}
            </article>
          )) : <p className="text-sm text-on-surface-variant">No attempt history was persisted.</p>}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h2 className="font-headline text-xl font-bold text-on-surface">Identifiers and extraction</h2>
          <dl className="mt-4 space-y-3 text-sm">
            {[
              ["Run", data.application?.run_id],
              ["Job", data.application?.job_id],
              ["CV asset", identifiers.cv_asset_id],
              ["Generated artifact", identifiers.generated_artifact_id],
              ["Job-description state", labelize(jobDescription.state || "unknown")],
              ["Job-description characters", jobDescription.char_count],
              ["Scorer model", data.scorer?.model],
              ["Prompt version", data.scorer?.prompt_version],
            ].map(([label, value]) => (
              <div className="grid grid-cols-[150px_1fr] gap-3" key={label}>
                <dt className="font-semibold text-on-surface">{label}</dt>
                <dd className="break-all text-on-surface-variant">{value || "Not persisted"}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-5"><DetailList emptyText="No extraction or language warnings." items={jobDescription.warnings} /></div>
        </section>
        <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h2 className="font-headline text-xl font-bold text-on-surface">Recommendations</h2>
          <div className="mt-4"><DetailList emptyText="No recommendations were persisted." items={data.recommendations} /></div>
          {score.last_warning ? (
            <p className="mt-5 rounded-2xl bg-error/5 px-4 py-3 text-sm text-error">{score.last_warning}</p>
          ) : null}
        </section>
      </div>
    </div>
  );
}

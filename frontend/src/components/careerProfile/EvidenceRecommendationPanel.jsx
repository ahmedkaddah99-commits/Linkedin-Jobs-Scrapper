import { useCallback, useState } from "react";
import { useSession } from "../../context/SessionContext";

const FACT_TYPE_LABELS = {
  action: "Action",
  tool: "Tool",
  stakeholder: "Stakeholder",
  outcome: "Outcome",
  metric: "Metric",
};

const VERIFICATION_BADGES = {
  verified: { label: "Verified", tone: "success" },
  pending: { label: "Pending", tone: "warning" },
  rejected: { label: "Rejected", tone: "error" },
};

function StatusBadge({ label, tone = "neutral" }) {
  const tones = {
    success: "bg-emerald-100 text-emerald-800 border-emerald-200",
    warning: "bg-amber-100 text-amber-800 border-amber-200",
    error: "bg-red-100 text-red-800 border-red-200",
    neutral: "bg-slate-100 text-slate-600 border-slate-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] ${tones[tone] || tones.neutral}`}
    >
      {label}
    </span>
  );
}

function RequirementGroup({ group, onSetStatus }) {
  return (
    <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-5">
      <div className="mb-4">
        <div className="text-sm font-semibold text-on-surface">
          {group.requirement_label}
        </div>
        {group.requirement_category && (
          <span className="mt-1 inline-block text-[11px] font-medium uppercase tracking-[0.12em] text-on-surface-variant">
            {group.requirement_category}
          </span>
        )}
      </div>
      {group.matches.length === 0 ? (
        <p className="text-xs text-on-surface-variant italic">
          No verified evidence matches this requirement.
        </p>
      ) : (
        <div className="space-y-3">
          {group.matches.map((match) => {
            const factLabel = FACT_TYPE_LABELS[match.fact_type] || match.fact_type || "Fact";
            const verifyBadge = VERIFICATION_BADGES[match.verification_state] || VERIFICATION_BADGES.verified;
            return (
              <div
                key={match.match_id}
                className={`rounded-xl border bg-surface p-4 ${
                  match.include_status === "included"
                    ? "border-emerald-300"
                    : match.include_status === "excluded"
                      ? "border-red-200 opacity-60"
                      : "border-outline-variant/15"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 space-y-2">
                    <p className="text-sm font-medium text-on-surface">
                      {match.evidence_text}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-on-surface-variant">
                      <StatusBadge {...verifyBadge} />
                      <StatusBadge label={factLabel} tone="neutral" />
                      {match.linked_experience && (
                        <span className="truncate">
                          <span className="material-symbols-outlined text-[12px] align-text-bottom">work</span>{" "}
                          {match.linked_experience}
                        </span>
                      )}
                      {match.source_file_name && (
                        <span className="truncate">
                          <span className="material-symbols-outlined text-[12px] align-text-bottom">description</span>{" "}
                          {match.source_file_name}
                        </span>
                      )}
                    </div>
                    {match.match_reason && (
                      <p className="text-[11px] text-on-surface-variant/70">{match.match_reason}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => onSetStatus(match.match_id, "included")}
                      disabled={match.include_status === "included"}
                      className={`rounded-full px-3 py-1.5 text-[11px] font-semibold ${
                        match.include_status === "included"
                          ? "bg-emerald-100 text-emerald-700"
                          : "border border-outline-variant/30 text-on-surface-variant hover:bg-emerald-50 hover:text-emerald-700"
                      }`}
                    >
                      Include
                    </button>
                    <button
                      type="button"
                      onClick={() => onSetStatus(match.match_id, "excluded")}
                      disabled={match.include_status === "excluded"}
                      className={`rounded-full px-3 py-1.5 text-[11px] font-semibold ${
                        match.include_status === "excluded"
                          ? "bg-red-100 text-red-700"
                          : "border border-outline-variant/30 text-on-surface-variant hover:bg-red-50 hover:text-red-700"
                      }`}
                    >
                      Exclude
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function EvidenceRecommendationPanel({
  jobId = "",
  jobTitle = "",
  jobCompany = "",
  profileId = "",
  requirements = [],
  onRecommendationsLoaded,
  onMatchStatusChanged,
}) {
  const { request } = useSession();
  const [recommendation, setRecommendation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generated, setGenerated] = useState(false);

  const generateEvidence = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = {
        job_id: jobId,
        job_title: jobTitle,
        job_company: jobCompany,
        requirements,
      };
      const result = await request(
        `/career-profiles/${profileId}/evidence-recommendations`,
        {
          method: "POST",
          body: JSON.stringify(payload),
          headers: { "Content-Type": "application/json" },
        },
      );
      setRecommendation(result);
      setGenerated(true);
      if (onRecommendationsLoaded) {
        onRecommendationsLoaded(result);
      }
    } catch (err) {
      setError(
        err?.message || err?.error || "Failed to generate evidence recommendations.",
      );
    } finally {
      setLoading(false);
    }
  }, [request, jobId, jobTitle, jobCompany, profileId, requirements, onRecommendationsLoaded]);

  const handleSetStatus = useCallback(
    async (matchId, status) => {
      if (!recommendation) return;
      try {
        const updated = await request(
          `/career-profiles/${profileId}/evidence-recommendations/${recommendation.recommendation_id}/matches/${matchId}`,
          {
            method: "PUT",
            body: JSON.stringify({ include_status: status }),
            headers: { "Content-Type": "application/json" },
          },
        );
        setRecommendation(updated);
        if (onMatchStatusChanged) {
          onMatchStatusChanged(updated);
        }
      } catch (err) {
        console.error("Failed to update match status:", err);
      }
    },
    [request, profileId, recommendation, onMatchStatusChanged],
  );

  if (!generated) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-outline-variant/20 bg-surface p-6">
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-on-surface-variant">
            Evidence Recommendations
          </h3>
          <p className="mt-2 text-sm text-on-surface-variant">
            Match your verified evidence against job requirements before generating
            your tailored application.
          </p>
          <button
            type="button"
            disabled={loading || !requirements.length}
            onClick={generateEvidence}
            className="mt-4 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? (
              <span className="material-symbols-outlined animate-spin text-[16px]">
                progress_activity
              </span>
            ) : null}
            {loading ? "Matching evidence..." : "Recommend Evidence"}
          </button>
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        </div>
      </div>
    );
  }

  if (!recommendation || !recommendation.groups.length) {
    return (
      <div className="rounded-2xl border border-outline-variant/20 bg-surface p-6">
        <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-on-surface-variant">
          Evidence Recommendations
        </h3>
        <p className="mt-3 text-sm text-on-surface-variant">
          No matching evidence found for the provided job requirements.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-outline-variant/20 bg-surface p-5">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-on-surface-variant">
            Evidence Recommendations
          </h3>
          <p className="mt-1 text-xs text-on-surface-variant">
            {recommendation.total_matches} matches across{" "}
            {recommendation.groups.length} requirements &middot;{" "}
            {recommendation.included_count} included &middot;{" "}
            {recommendation.excluded_count} excluded
          </p>
        </div>
        <button
          type="button"
          onClick={generateEvidence}
          className="inline-flex items-center gap-1.5 rounded-full border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface-variant hover:bg-surface-container"
        >
          <span className="material-symbols-outlined text-[14px]">refresh</span>
          Refresh
        </button>
      </div>
      {recommendation.groups.map((group) => (
        <RequirementGroup
          key={group.requirement_id}
          group={group}
          onSetStatus={handleSetStatus}
        />
      ))}
    </div>
  );
}


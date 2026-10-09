import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";

const STATUS_CONFIG = {
  pending: { label: "Pending", css: "bg-amber-100 text-amber-800", icon: "hourglass_empty" },
  verified: { label: "Verified", css: "bg-green-100 text-green-800", icon: "verified" },
  rejected: { label: "Rejected", css: "bg-red-100 text-red-800", icon: "block" },
  deferred: { label: "Deferred", css: "bg-slate-100 text-slate-600", icon: "schedule" },
};

export default function CareerProfileEvidenceReview({ profileId, profileName = "Career Profile" }) {
  const { request } = useSession();
  const [evidence, setEvidence] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState("");
  const [editText, setEditText] = useState("");
  const [actionError, setActionError] = useState("");

  const loadEvidence = useCallback(async () => {
    if (!profileId) return;
    try {
      setLoading(true);
      const data = await request(
        `/career-profiles/${encodeURIComponent(profileId)}/evidence`,
        { method: "GET" }, { rawPath: true },
      );
      setEvidence(Array.isArray(data?.evidence) ? data.evidence : []);
      setCounts(data?.counts || {});
      setError("");
    } catch (err) {
      setError(String(err?.message || "Failed to load evidence."));
    } finally { setLoading(false); }
  }, [profileId, request]);

  useEffect(() => { loadEvidence(); }, [loadEvidence]);

  async function handleAction(evidenceId, action, extra = {}) {
    setActionError("");
    try {
      const path = `/career-profiles/${encodeURIComponent(profileId)}/evidence/${encodeURIComponent(evidenceId)}/${action}`;
      const options = { method: action === "edit" ? "PUT" : "POST" };
      if (action === "edit" && extra.edited_text !== undefined) {
        options.body = JSON.stringify({ edited_text: extra.edited_text });
      }
      const updated = await request(path, options, { rawPath: true });
      setEvidence((prev) => prev.map((e) => (e.evidence_id === evidenceId ? updated : e)));
      setEditingId("");
      const countsData = await request(
        `/career-profiles/${encodeURIComponent(profileId)}/evidence`,
        { method: "GET" }, { rawPath: true },
      );
      setCounts(countsData?.counts || {});
    } catch (err) {
      setActionError(String(err?.message || "Action failed."));
    }
  }

  function startEdit(item) {
    setEditingId(item.evidence_id);
    setEditText(item.effective_text || item.extracted_text);
    setActionError("");
  }
  function cancelEdit() { setEditingId(""); setEditText(""); setActionError(""); }

  if (loading) {
    return (
      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
        <div className="space-y-4">
          <div className="h-7 w-48 animate-pulse rounded-full bg-surface-container" />
          {[1, 2, 3].map((i) => (
            <div className="h-24 animate-pulse rounded-2xl bg-surface-container" key={i} />
          ))}
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-3xl border border-error/20 bg-surface-container-lowest p-6 shadow-soft">
        <p className="text-sm text-error">{error}</p>
      </section>
    );
  }

  const p = counts?.pending || 0;
  const v = counts?.verified || 0;
  const r = counts?.rejected || 0;
  const d = counts?.deferred || 0;

  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-soft">
      <div>
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          Evidence Review
        </div>
        <h2 className="mt-3 font-headline text-xl font-bold text-on-surface">
          Review evidence for {profileName}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-on-surface-variant">
          Verify, edit, reject, or defer each extracted item. Verified evidence is used in generated material.
        </p>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-center">
          <div className="text-2xl font-bold text-amber-800">{p}</div>
          <div className="mt-0.5 text-xs font-semibold text-amber-700">Pending</div>
        </div>
        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-center">
          <div className="text-2xl font-bold text-green-800">{v}</div>
          <div className="mt-0.5 text-xs font-semibold text-green-700">Verified</div>
        </div>
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-center">
          <div className="text-2xl font-bold text-red-800">{r}</div>
          <div className="mt-0.5 text-xs font-semibold text-red-700">Rejected</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center">
          <div className="text-2xl font-bold text-slate-700">{d}</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-600">Deferred</div>
        </div>
      </div>
      {actionError ? (
        <div className="mt-4 rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
          {actionError}
        </div>
      ) : null}
      {evidence.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-outline-variant/20 bg-surface p-8 text-center">
          <span className="material-symbols-outlined text-[2.5rem] text-on-surface-variant">science</span>
          <p className="mt-3 text-sm leading-6 text-on-surface-variant">
            No evidence items extracted yet.
          </p>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          {evidence.map((item) => (
            <EvidenceCard
              editingId={editingId} editText={editText} item={item} key={item.evidence_id}
              onAction={handleAction} onCancelEdit={cancelEdit}
              onEditTextChange={setEditText} onStartEdit={startEdit}
            />
          ))}
        </div>
      )}
    </section>
  );
}

const FIELD_LABELS = {
  experience: "Experience", education: "Education", skill: "Skill",
  certification: "Certification", contact: "Contact", summary: "Summary",
  language: "Language", project: "Project", other: "Other",
};

function EvidenceCard({ editingId, editText, item, onAction, onCancelEdit, onEditTextChange, onStartEdit }) {
  const isEditing = editingId === item.evidence_id;
  const s = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending;
  const f = FIELD_LABELS[item.field_type] || item.field_type;

  return (
    <div className="rounded-2xl border border-outline-variant/15 bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-surface-container-low px-2.5 py-0.5 text-[11px] font-semibold text-on-surface-variant">{f}</span>
        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${s.css}`}>
          <span className="material-symbols-outlined text-[14px]">{s.icon}</span> {s.label}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-on-surface-variant">
        <span className="inline-flex items-center gap-1">
          <span className="material-symbols-outlined text-[14px]">description</span>
          {item.source_name || item.source_id || "Unknown source"}
        </span>
        {item.extraction_reason ? (
          <span className="inline-flex items-center gap-1">
            <span className="material-symbols-outlined text-[14px]">lightbulb</span>
            {item.extraction_reason}
          </span>
        ) : null}
        {item.extraction_confidence > 0 ? (
          <span className="inline-flex items-center gap-1">
            <span className="material-symbols-outlined text-[14px]">psychology</span>
            {Math.round(item.extraction_confidence * 100)}% confidence
          </span>
        ) : null}
      </div>
      {isEditing ? (
        <div className="mt-3">
          <textarea className="w-full rounded-xl border border-primary/30 bg-surface px-4 py-3 text-sm text-on-surface focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            onChange={(e) => onEditTextChange(e.target.value)} rows={4} value={editText} />
          <div className="mt-2 flex flex-wrap gap-2">
            <button className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
              onClick={() => onAction(item.evidence_id, "edit", { edited_text: editText })} type="button">
              <span className="material-symbols-outlined text-[16px]">check</span> Save edit
            </button>
            <button className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
              onClick={onCancelEdit} type="button">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="mt-3">
          {item.is_edited ? (
            <div className="space-y-2">
              <div className="rounded-xl border border-primary/20 bg-primary/5 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-primary">Edited text</div>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-on-surface">{item.edited_text}</p>
              </div>
              <details className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-3">
                <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">Original extracted text</summary>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-on-surface-variant">{item.extracted_text}</p>
              </details>
            </div>
          ) : (
            <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">Extracted text</div>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-on-surface">{item.effective_text || item.extracted_text}</p>
            </div>
          )}
        </div>
      )}
      {item.edit_history?.length > 0 && !isEditing ? (
        <details className="mt-2 rounded-xl border border-outline-variant/10 bg-surface-container-low p-3">
          <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">
            Edit history ({item.edit_history.length} change{item.edit_history.length !== 1 ? "s" : ""})
          </summary>
          <div className="mt-2 space-y-1.5 max-h-32 overflow-y-auto">
            {item.edit_history.map((entry, i) => (
              <div className="border-l-2 border-primary/30 pl-2.5 text-xs text-on-surface-variant" key={i}>
                <span className="font-semibold text-on-surface">{entry.changed_by || "user"}</span>{" "}
                edited {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "unknown"}
              </div>
            ))}
          </div>
        </details>
      ) : null}
      {!isEditing ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="inline-flex items-center gap-1.5 rounded-xl bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
            disabled={item.status === "verified"} onClick={() => onAction(item.evidence_id, "verify")} type="button">
            <span className="material-symbols-outlined text-[16px]">verified</span> Verify
          </button>
          <button className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high"
            onClick={() => onStartEdit(item)} type="button">
            <span className="material-symbols-outlined text-[16px]">edit</span> Edit
          </button>
          <button className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
            disabled={item.status === "rejected"} onClick={() => onAction(item.evidence_id, "reject")} type="button">
            <span className="material-symbols-outlined text-[16px]">block</span> Reject
          </button>
          <button className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-high disabled:opacity-50"
            disabled={item.status === "deferred"} onClick={() => onAction(item.evidence_id, "defer")} type="button">
            <span className="material-symbols-outlined text-[16px]">schedule</span> Ask me later
          </button>
        </div>
      ) : null}
    </div>
  );
}


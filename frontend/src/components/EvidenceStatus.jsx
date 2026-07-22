import { useEffect, useState } from "react";
import { apiGet } from "../lib/api";

const STATE_LABELS = {
  draft: "Draft",
  processing: "Processing",
  needs_review: "Needs Review",
  verified: "Verified",
  rejected: "Rejected",
  ready_for_tailoring: "Ready for Tailoring",
  archived: "Archived",
};

const STATE_COLORS = {
  draft: "#9e9e9e",
  processing: "#2196f3",
  needs_review: "#ff9800",
  verified: "#4caf50",
  rejected: "#f44336",
  ready_for_tailoring: "#00bcd4",
  archived: "#607d8b",
};

const STATE_ORDER = [
  "draft", "processing", "needs_review", "verified",
  "rejected", "ready_for_tailoring", "archived",
];

const KIND_LABELS = {
  source: "Source",
  evidence: "Evidence",
  timeline_mapping: "Timeline",
  generated_output: "Output",
};

export { STATE_LABELS, STATE_COLORS, STATE_ORDER, KIND_LABELS };

// ---------------------------------------------------------------------------
// EvidenceStatusBadge -- compact pill showing state with action tooltip
// ---------------------------------------------------------------------------

export function EvidenceStatusBadge({ state, size = "md", showLabel = true }) {
  const color = STATE_COLORS[state] || "#9e9e9e";
  const label = STATE_LABELS[state] || state;
  const fontSize = size === "sm" ? "10px" : size === "lg" ? "14px" : "12px";
  const padding = size === "sm" ? "2px 7px" : size === "lg" ? "4px 12px" : "3px 9px";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        fontSize,
        fontWeight: 600,
        color: "#fff",
        backgroundColor: color,
        borderRadius: "999px",
        padding,
        lineHeight: 1.4,
        whiteSpace: "nowrap",
      }}
      title={`Status: ${label}`}
    >
      {showLabel ? label : ""}
    </span>
  );


// ---------------------------------------------------------------------------
// EvidenceStateTimeline -- shows the full 7-state progression
// ---------------------------------------------------------------------------

export function EvidenceStateTimeline({ currentState, history = [] }) {
  const currentIdx = STATE_ORDER.indexOf(currentState);
  const historyMap = {};
  for (const entry of history) {
    historyMap[entry.to_state] = entry;
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, flexWrap: "wrap" }}>
      {STATE_ORDER.map((state, idx) => {
        const isPast = idx < currentIdx;
        const isCurrent = idx === currentIdx;
        const hist = historyMap[state];
        const dotColor = isCurrent || isPast
          ? STATE_COLORS[state]
          : "#e0e0e0";
        const dotSize = isCurrent ? "14px" : "10px";

        return (
          <div
            key={state}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "2px",
              opacity: isPast || isCurrent ? 1 : 0.4,
            }}
            title={
              hist
                ? `${STATE_LABELS[state]} at ${new Date(hist.occurred_at).toLocaleString()} - ${hist.reason || ""}`
                : STATE_LABELS[state]
            }
          >
            <span
              style={{
                width: dotSize,
                height: dotSize,
                borderRadius: "50%",
                backgroundColor: dotColor,
                border: isCurrent ? "2px solid #333" : "none",
                display: "inline-block",
                flexShrink: 0,
              }}
            />
            {idx < STATE_ORDER.length - 1 && (
              <span
                style={{
                  width: "16px",
                  height: "2px",
                  backgroundColor: isPast ? STATE_COLORS[state] : "#e0e0e0",
                  display: "inline-block",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );


// ---------------------------------------------------------------------------
// EvidenceActionPrompt -- explains what the user needs to do next
// ---------------------------------------------------------------------------

export function EvidenceActionPrompt({ state }) {
  const actions = {
    draft: "Submit this item for processing to begin.",
    processing: "The system is working on this. No action needed.",
    needs_review: "Review the extracted data and verify or reject it.",
    verified: "This evidence is ready for document tailoring.",
    rejected: "You can re-submit this evidence for processing.",
    ready_for_tailoring: "Generate tailored documents using this evidence.",
    archived: "This item is archived. Restore it to make it active again.",
  };

  const colors = {
    draft: { bg: "#f5f5f5", border: "#e0e0e0" },
    processing: { bg: "#e3f2fd", border: "#90caf9" },
    needs_review: { bg: "#fff3e0", border: "#ffcc80" },
    verified: { bg: "#e8f5e9", border: "#a5d6a7" },
    rejected: { bg: "#ffebee", border: "#ef9a9a" },
    ready_for_tailoring: { bg: "#e0f7fa", border: "#80deea" },
    archived: { bg: "#eceff1", border: "#b0bec5" },
  };

  const c = colors[state] || colors.draft;
  const action = actions[state] || "";

  if (!action) return null;

  return (
    <div
      style={{
        margin: "6px 0",
        padding: "8px 12px",
        fontSize: "13px",
        lineHeight: 1.5,
        backgroundColor: c.bg,
        borderLeft: `3px solid ${c.border}`,
        borderRadius: "4px",
        color: "#333",
      }}
    >
      <strong>Action needed:</strong> {action}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EvidenceStatusHistory -- scrollable state history log
// ---------------------------------------------------------------------------

export function EvidenceStatusHistory({ evidenceId }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!evidenceId) return;
    let cancelled = false;
    setLoading(true);
    apiGet(`/v1/evidence/${evidenceId}/history?limit=50`)
      .then((data) => {
        if (!cancelled) {
          setHistory(data.history || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || "Failed to load history");
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [evidenceId]);

  if (loading) return <p style={{ fontSize: "12px", color: "#888" }}>Loading history...</p>;
  if (error) return <p style={{ fontSize: "12px", color: "#f44336" }}>{error}</p>;
  if (!history.length) return <p style={{ fontSize: "12px", color: "#888" }}>No state history recorded.</p>;

  return (
    <div style={{ maxHeight: "200px", overflowY: "auto", fontSize: "12px" }}>
      {history.map((entry) => (
        <div
          key={entry.history_id}
          style={{
            padding: "4px 0",
            borderBottom: "1px solid #eee",
            display: "flex",
            gap: "8px",
            alignItems: "flex-start",
          }}
        >
          <EvidenceStatusBadge state={entry.to_state} size="sm" />
          <div style={{ flex: 1 }}>
            <div style={{ color: "#555" }}>
              {entry.from_state
                ? `${STATE_LABELS[entry.from_state]} \u2192 ${STATE_LABELS[entry.to_state]}`
                : `Created as ${STATE_LABELS[entry.to_state]}`}
            </div>
            {entry.reason && <div style={{ color: "#888" }}>{entry.reason}</div>}
            <div style={{ color: "#aaa", fontSize: "10px", marginTop: "2px" }}>
              {new Date(entry.occurred_at).toLocaleString()}
              {entry.actor && entry.actor !== "system" ? ` by ${entry.actor}` : ""}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

}

}

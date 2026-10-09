/**
 * AA-217 production reconciliation core, promoted from AA-202.
 *
 * This module deliberately matches only ATS-visible fields. sourceId is
 * provenance metadata for Runr and is never treated as an ATS DOM identifier.
 */

export type ReconciliationKind = "experience" | "education";

export type ReconciliationCandidate = {
  candidateId: string;
  sourceId?: string;
  kind: ReconciliationKind;
  employerOrInstitution: string;
  titleOrDegree: string;
  startDate?: string;
  endDate?: string;
  current?: boolean;
  location?: string;
  content?: string;
  contentHash?: string;
};

export type AtsReconciliationEntry = Omit<ReconciliationCandidate, "candidateId" | "sourceId"> & {
  atsEntryId: string;
};

export type ReconciliationAction =
  | { kind: "update"; candidateId: string; atsEntryId: string; changes: Partial<AtsReconciliationEntry>; score: number; audit: ReconciliationAudit }
  | { kind: "add"; candidateId: string; entry: AtsReconciliationEntry; score: 0 }
  | { kind: "ambiguous"; candidateId: string; atsEntryIds: string[]; reason: string; audit: ReconciliationAudit }
  | { kind: "leave"; candidateId: string; atsEntryId: string; score: number; audit: ReconciliationAudit };

export type ReconciliationAudit = {
  score: number;
  matchedFields: string[];
  reason: "unique_match" | "unchanged" | "ambiguous" | "claimed_by_other_candidate";
};

export type ReconciliationResult = {
  actions: ReconciliationAction[];
  entries: AtsReconciliationEntry[];
};

type Comparable = {
  employerOrInstitution: string;
  titleOrDegree: string;
  startDate?: string;
  endDate?: string;
  current?: boolean;
  location?: string;
  content?: string;
  contentHash?: string;
};

const DATE_PATTERN = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/u;

export function normalizeReconciliationText(value: string | undefined): string {
  return (value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/&/gu, " and ")
    .replace(/[^\p{Letter}\p{Number}]+/gu, " ")
    .trim()
    .replace(/\s+/gu, " ");
}

function monthValue(value: string | undefined, end: boolean): number | null {
  if (!value || value === "present" || value === "current") return end ? 999999 : null;
  const match = DATE_PATTERN.exec(value.trim());
  if (!match) return null;
  return Number(match[1]) * 12 + Number(match[2] || (end ? 12 : 1));
}

function datesOverlap(left: Comparable, right: Comparable): boolean {
  const leftStart = monthValue(left.startDate, false);
  const rightStart = monthValue(right.startDate, false);
  if (leftStart === null || rightStart === null) return false;
  const leftEnd = monthValue(left.endDate, true) ?? (left.current ? 999999 : leftStart);
  const rightEnd = monthValue(right.endDate, true) ?? (right.current ? 999999 : rightStart);
  return leftStart <= rightEnd && rightStart <= leftEnd;
}

function contentOverlap(left: string | undefined, right: string | undefined): boolean {
  const leftWords = new Set(normalizeReconciliationText(left).split(" ").filter(Boolean));
  const rightWords = new Set(normalizeReconciliationText(right).split(" ").filter(Boolean));
  if (!leftWords.size || !rightWords.size) return false;
  let overlap = 0;
  for (const word of leftWords) if (rightWords.has(word)) overlap += 1;
  return overlap >= 2;
}

export function scoreReconciliationCandidate(candidate: ReconciliationCandidate, entry: AtsReconciliationEntry): { score: number; matchedFields: string[] } | null {
  if (candidate.kind !== entry.kind) return null;
  if (normalizeReconciliationText(candidate.employerOrInstitution) !== normalizeReconciliationText(entry.employerOrInstitution)) return null;
  if (normalizeReconciliationText(candidate.titleOrDegree) !== normalizeReconciliationText(entry.titleOrDegree)) return null;

  const dates = datesOverlap(candidate, entry);
  const current = candidate.current !== undefined && entry.current !== undefined && candidate.current === entry.current;
  const location = Boolean(candidate.location && entry.location &&
    normalizeReconciliationText(candidate.location) === normalizeReconciliationText(entry.location));
  const content = contentOverlap(candidate.content, entry.content);
  if (!dates && !current && !content && candidate.contentHash !== entry.contentHash) return null;
  const matchedFields = ["employerOrInstitution", "titleOrDegree"];
  if (dates) matchedFields.push("dates");
  if (current) matchedFields.push("current");
  if (location) matchedFields.push("location");
  if (content) matchedFields.push("content");
  if (candidate.contentHash && candidate.contentHash === entry.contentHash) matchedFields.push("contentHash");
  return {
    score: 5 + (dates ? 3 : 0) + (current ? 1 : 0) + (location ? 1 : 0) + (content ? 1 : 0) +
      (candidate.contentHash === entry.contentHash && candidate.contentHash ? 2 : 0),
    matchedFields,
  };
}

export function verifyApprovedContentHash(candidate: ReconciliationCandidate, entry: AtsReconciliationEntry): boolean {
  return !candidate.contentHash || candidate.contentHash === entry.contentHash;
}

function changesFor(candidate: ReconciliationCandidate, entry: AtsReconciliationEntry): Partial<AtsReconciliationEntry> {
  const changes: Partial<AtsReconciliationEntry> = {};
  if (candidate.startDate !== undefined && candidate.startDate !== entry.startDate) changes.startDate = candidate.startDate;
  if (candidate.endDate !== undefined && candidate.endDate !== entry.endDate) changes.endDate = candidate.endDate;
  if (candidate.current !== undefined && candidate.current !== entry.current) changes.current = candidate.current;
  if (candidate.location !== undefined && candidate.location !== entry.location) changes.location = candidate.location;
  if (candidate.content !== undefined && candidate.content !== entry.content) changes.content = candidate.content;
  if (candidate.contentHash !== undefined && candidate.contentHash !== entry.contentHash) changes.contentHash = candidate.contentHash;
  return changes;
}

/**
 * Plans an idempotent reconciliation. Candidate arrays are indexed by a
 * normalized kind/employer key; every ATS entry remains in the result.
 */
export function reconcileVisibleEntries(
  candidates: ReconciliationCandidate[],
  atsEntries: AtsReconciliationEntry[],
): ReconciliationResult {
  const byEmployer = new Map<string, AtsReconciliationEntry[]>();
  for (const entry of atsEntries) {
    const key = `${entry.kind}:${normalizeReconciliationText(entry.employerOrInstitution)}`;
    const bucket = byEmployer.get(key) || [];
    bucket.push(entry);
    byEmployer.set(key, bucket);
  }

  const actions: ReconciliationAction[] = [];
  const entries = atsEntries.map((entry) => ({ ...entry }));
  const claimedAtsEntryIds = new Set<string>();
  for (const candidate of candidates) {
    const key = `${candidate.kind}:${normalizeReconciliationText(candidate.employerOrInstitution)}`;
    const matches = (byEmployer.get(key) || [])
      .map((entry) => ({ entry, result: scoreReconciliationCandidate(candidate, entry) }))
      .filter((item): item is { entry: AtsReconciliationEntry; result: { score: number; matchedFields: string[] } } => item.result !== null)
      .sort((left, right) => right.result.score - left.result.score || left.entry.atsEntryId.localeCompare(right.entry.atsEntryId));

    const best = matches[0];
    const tied = best && matches[1] && best.result.score === matches[1].result.score;
    if (tied || (best && !verifyApprovedContentHash(candidate, best.entry))) {
      actions.push({
        kind: "ambiguous",
        candidateId: candidate.candidateId,
        atsEntryIds: tied ? matches.filter((item) => item.result.score === best.result.score).map((item) => item.entry.atsEntryId) : [best.entry.atsEntryId],
        reason: tied ? "Top visible ATS entries have the same deterministic score." : "Approved content hash did not match visible ATS content.",
        audit: { score: best.result.score, matchedFields: best.result.matchedFields, reason: "ambiguous" },
      });
      continue;
    }
    if (!matches.length) {
      const entry: AtsReconciliationEntry = {
        atsEntryId: `aa202-added-${candidate.candidateId}`,
        kind: candidate.kind,
        employerOrInstitution: candidate.employerOrInstitution,
        titleOrDegree: candidate.titleOrDegree,
        startDate: candidate.startDate,
        endDate: candidate.endDate,
        current: candidate.current,
        location: candidate.location,
        content: candidate.content,
        ...(candidate.contentHash === undefined ? {} : { contentHash: candidate.contentHash }),
      };
      entries.push(entry);
      const bucket = byEmployer.get(key) || [];
      bucket.push(entry);
      byEmployer.set(key, bucket);
      claimedAtsEntryIds.add(entry.atsEntryId);
      actions.push({ kind: "add", candidateId: candidate.candidateId, entry, score: 0 });
      continue;
    }

    const match = matches[0];
    if (!match) throw new Error("AA-202 internal matching invariant failed.");
    const { entry } = match;
    const score = match.result.score;
    const audit: ReconciliationAudit = { score, matchedFields: match.result.matchedFields, reason: "unique_match" };
    if (claimedAtsEntryIds.has(entry.atsEntryId)) {
      actions.push({
        kind: "ambiguous",
        candidateId: candidate.candidateId,
        atsEntryIds: [entry.atsEntryId],
        reason: "A visible ATS entry is already claimed by another candidate in this run.",
        audit: { ...audit, reason: "claimed_by_other_candidate" },
      });
      continue;
    }
    claimedAtsEntryIds.add(entry.atsEntryId);
    const changes = changesFor(candidate, entry);
    if (!Object.keys(changes).length) actions.push({ kind: "leave", candidateId: candidate.candidateId, atsEntryId: entry.atsEntryId, score, audit: { ...audit, reason: "unchanged" } });
    else {
      const index = entries.findIndex((item) => item.atsEntryId === entry.atsEntryId);
      const existing = entries[index];
      if (existing) entries[index] = { ...existing, ...changes };
      actions.push({ kind: "update", candidateId: candidate.candidateId, atsEntryId: entry.atsEntryId, changes, score, audit });
    }
  }
  return { actions, entries };
}

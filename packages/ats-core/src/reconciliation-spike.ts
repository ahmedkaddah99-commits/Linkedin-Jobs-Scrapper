/**
 * AA-202 disposable reconciliation prototype.
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
};

export type AtsReconciliationEntry = Omit<ReconciliationCandidate, "candidateId" | "sourceId"> & {
  atsEntryId: string;
};

export type ReconciliationAction =
  | { kind: "update"; candidateId: string; atsEntryId: string; changes: Partial<AtsReconciliationEntry>; score: number }
  | { kind: "add"; candidateId: string; entry: AtsReconciliationEntry; score: 0 }
  | { kind: "review_required"; candidateId: string; atsEntryIds: string[]; reason: string }
  | { kind: "noop"; candidateId: string; atsEntryId: string; score: number };

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

function scoreMatch(candidate: ReconciliationCandidate, entry: AtsReconciliationEntry): number | null {
  if (candidate.kind !== entry.kind) return null;
  if (normalizeReconciliationText(candidate.employerOrInstitution) !== normalizeReconciliationText(entry.employerOrInstitution)) return null;
  if (normalizeReconciliationText(candidate.titleOrDegree) !== normalizeReconciliationText(entry.titleOrDegree)) return null;

  const dates = datesOverlap(candidate, entry);
  const current = candidate.current !== undefined && entry.current !== undefined && candidate.current === entry.current;
  const location = Boolean(candidate.location && entry.location &&
    normalizeReconciliationText(candidate.location) === normalizeReconciliationText(entry.location));
  const content = contentOverlap(candidate.content, entry.content);
  if (!dates && !current && !content) return null;
  return 5 + (dates ? 3 : 0) + (current ? 1 : 0) + (location ? 1 : 0) + (content ? 1 : 0);
}

function changesFor(candidate: ReconciliationCandidate, entry: AtsReconciliationEntry): Partial<AtsReconciliationEntry> {
  const changes: Partial<AtsReconciliationEntry> = {};
  if (candidate.startDate !== undefined && candidate.startDate !== entry.startDate) changes.startDate = candidate.startDate;
  if (candidate.endDate !== undefined && candidate.endDate !== entry.endDate) changes.endDate = candidate.endDate;
  if (candidate.current !== undefined && candidate.current !== entry.current) changes.current = candidate.current;
  if (candidate.location !== undefined && candidate.location !== entry.location) changes.location = candidate.location;
  if (candidate.content !== undefined && candidate.content !== entry.content) changes.content = candidate.content;
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
      .map((entry) => ({ entry, score: scoreMatch(candidate, entry) }))
      .filter((item): item is { entry: AtsReconciliationEntry; score: number } => item.score !== null);

    if (matches.length > 1) {
      actions.push({
        kind: "review_required",
        candidateId: candidate.candidateId,
        atsEntryIds: matches.map((item) => item.entry.atsEntryId),
        reason: "Multiple visible ATS entries are plausible matches.",
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
    const { entry, score } = match;
    if (claimedAtsEntryIds.has(entry.atsEntryId)) {
      actions.push({
        kind: "review_required",
        candidateId: candidate.candidateId,
        atsEntryIds: [entry.atsEntryId],
        reason: "A visible ATS entry is already claimed by another candidate in this run.",
      });
      continue;
    }
    claimedAtsEntryIds.add(entry.atsEntryId);
    const changes = changesFor(candidate, entry);
    if (!Object.keys(changes).length) actions.push({ kind: "noop", candidateId: candidate.candidateId, atsEntryId: entry.atsEntryId, score });
    else {
      const index = entries.findIndex((item) => item.atsEntryId === entry.atsEntryId);
      const existing = entries[index];
      if (existing) entries[index] = { ...existing, ...changes };
      actions.push({ kind: "update", candidateId: candidate.candidateId, atsEntryId: entry.atsEntryId, changes, score });
    }
  }
  return { actions, entries };
}

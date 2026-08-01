import { describe, expect, it } from "vitest";
import {
  normalizeReconciliationText,
  reconcileVisibleEntries,
  type AtsReconciliationEntry,
  type ReconciliationCandidate,
} from "../../../../packages/ats-core/src/reconciliation-spike";

const entries: AtsReconciliationEntry[] = [
  { atsEntryId: "exp-acme-senior", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", current: false, location: "Berlin", content: "Built platform foundations." },
  { atsEntryId: "exp-acme-engineer", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Engineer", startDate: "2022-07", current: true, location: "Berlin", content: "Maintained services." },
  { atsEntryId: "exp-beta-engineer", kind: "experience", employerOrInstitution: "Beta Labs", titleOrDegree: "Engineer", startDate: "2021-01", endDate: "2023-12", current: false, location: "Paris", content: "Built data tooling." },
  { atsEntryId: "edu-uni", kind: "education", employerOrInstitution: "University of Example", titleOrDegree: "BSc Computer Science", startDate: "2014-09", endDate: "2018-06", location: "Berlin", content: "Computer science degree." },
];

const candidate = (value: Partial<ReconciliationCandidate> & Pick<ReconciliationCandidate, "candidateId" | "kind" | "employerOrInstitution" | "titleOrDegree">): ReconciliationCandidate => value;

describe("AA-202 reconciliation spike", () => {
  it("normalizes deterministically", () => {
    expect(normalizeReconciliationText(" Acme & Co. ")).toBe("acme and co");
    expect(normalizeReconciliationText("BSc\u00a0Computer-Science")).toBe("bsc computer science");
  });

  it("updates one unique confident match and adds only a missing entry", () => {
    const result = reconcileVisibleEntries([
      candidate({ candidateId: "source-senior", sourceId: "runr-exp-1", kind: "experience", employerOrInstitution: "acme and co", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", location: "Berlin", content: "Built platform foundations and observability." }),
      candidate({ candidateId: "source-new", sourceId: "runr-exp-new", kind: "experience", employerOrInstitution: "Gamma Works", titleOrDegree: "Staff Engineer", startDate: "2023-01", current: true, location: "Remote", content: "Designed systems." }),
    ], entries);
    expect(result.actions.map((action) => action.kind)).toEqual(["update", "add"]);
    expect(result.entries).toHaveLength(entries.length + 1);
    expect(result.entries.find((entry) => entry.atsEntryId === "exp-acme-engineer")).toEqual(entries[1]);
  });

  it("keeps same-employer promotions and overlapping roles distinct", () => {
    const result = reconcileVisibleEntries([
      candidate({ candidateId: "promotion", kind: "experience", employerOrInstitution: "ACME & CO", titleOrDegree: "Engineer", startDate: "2022-07", current: true, location: "Berlin", content: "Maintained services." }),
      candidate({ candidateId: "overlap", kind: "experience", employerOrInstitution: "Beta Labs", titleOrDegree: "Engineer", startDate: "2021-05", endDate: "2022-02", location: "Paris", content: "Built data tooling." }),
    ], entries);
    expect(result.actions.map((action) => action.kind)).toEqual(["noop", "update"]);
    expect(result.actions[1]).toMatchObject({ kind: "update", atsEntryId: "exp-beta-engineer" });
    expect(result.actions.every((action) => action.kind !== "review_required")).toBe(true);
  });

  it("stops on ambiguity without mutating either plausible ATS entry", () => {
    const ambiguousEntries = [
      ...entries,
      { ...entries[2]!, atsEntryId: "exp-beta-engineer-copy", content: "Built data tooling." },
    ];
    const result = reconcileVisibleEntries([
      candidate({ candidateId: "ambiguous", kind: "experience", employerOrInstitution: "Beta Labs", titleOrDegree: "Engineer", startDate: "2021-06", endDate: "2022-02", location: "Paris", content: "Built data tooling." }),
    ], ambiguousEntries);
    expect(result.actions).toEqual([{ kind: "review_required", candidateId: "ambiguous", atsEntryIds: ["exp-beta-engineer", "exp-beta-engineer-copy"], reason: "Multiple visible ATS entries are plausible matches." }]);
    expect(result.entries).toEqual(ambiguousEntries);
  });

  it("preserves unmatched entries and is idempotent on a second run", () => {
    const candidates = [candidate({ candidateId: "edu", kind: "education", employerOrInstitution: "University of Example", titleOrDegree: "BSc Computer Science", startDate: "2014-09", endDate: "2018-06", location: "Berlin", content: "Computer science degree." })];
    const first = reconcileVisibleEntries(candidates, entries);
    const second = reconcileVisibleEntries(candidates, first.entries);
    expect(first.actions[0]?.kind).toBe("noop");
    expect(second.actions[0]?.kind).toBe("noop");
    expect(second.entries).toEqual(first.entries);
  });

  it("stops same-run candidate collisions instead of claiming one ATS entry twice", () => {
    const result = reconcileVisibleEntries([
      candidate({ candidateId: "first", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", content: "Built platform foundations." }),
      candidate({ candidateId: "second", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", content: "Built platform foundations." }),
    ], [entries[0]!]);
    expect(result.actions.map((action) => action.kind)).toEqual(["noop", "review_required"]);
    expect(result.actions[1]).toMatchObject({
      candidateId: "second",
      atsEntryIds: ["exp-acme-senior"],
      reason: "A visible ATS entry is already claimed by another candidate in this run.",
    });
    expect(result.entries).toEqual([entries[0]]);
  });

  it("stops identical unmatched candidates from creating same-run duplicates", () => {
    const candidates = [
      candidate({ candidateId: "new-first", kind: "education", employerOrInstitution: "New University", titleOrDegree: "BA History", startDate: "2010-09", endDate: "2014-06", content: "History degree." }),
      candidate({ candidateId: "new-second", kind: "education", employerOrInstitution: "New University", titleOrDegree: "BA History", startDate: "2010-09", endDate: "2014-06", content: "History degree." }),
    ];
    const result = reconcileVisibleEntries(candidates, []);
    expect(result.actions.map((action) => action.kind)).toEqual(["add", "review_required"]);
    expect(result.entries).toHaveLength(1);
  });
});

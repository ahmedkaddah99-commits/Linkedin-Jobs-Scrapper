import { describe, expect, it } from "vitest";
import {
  normalizeReconciliationText,
  reconcileVisibleEntries,
  type AtsReconciliationEntry,
  type ReconciliationCandidate,
} from "../../../../packages/ats-core/src/reconciliation";

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

  it("uses approved content hashes for verification, never as DOM identity", () => {
    const hashed = { ...entries[0]!, contentHash: "sha256:approved" };
    const candidateWithHash = candidate({ candidateId: "hashed", kind: "experience", employerOrInstitution: hashed.employerOrInstitution, titleOrDegree: hashed.titleOrDegree, startDate: hashed.startDate, endDate: hashed.endDate, contentHash: hashed.contentHash });
    expect(reconcileVisibleEntries([candidateWithHash], [hashed]).actions[0]?.kind).toBe("leave");
    expect(reconcileVisibleEntries([{ ...candidateWithHash, contentHash: "sha256:wrong" }], [hashed]).actions[0]?.kind).toBe("ambiguous");
  });

  it("scores candidates deterministically and records field-level audit without values", () => {
    const result = reconcileVisibleEntries([candidate({ candidateId: "audited", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", location: "Berlin", content: "Built platform foundations." })], entries);
    expect(result.actions[0]).toMatchObject({ kind: "leave", audit: { reason: "unchanged", matchedFields: expect.arrayContaining(["employerOrInstitution", "titleOrDegree", "dates"]) } });
    expect(JSON.stringify(result.actions[0])).not.toContain("Built platform");
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
    expect(result.actions.map((action) => action.kind)).toEqual(["leave", "update"]);
    expect(result.actions[1]).toMatchObject({ kind: "update", atsEntryId: "exp-beta-engineer" });
    expect(result.actions.every((action) => action.kind !== "ambiguous")).toBe(true);
  });

  it("stops on ambiguity without mutating either plausible ATS entry", () => {
    const ambiguousEntries = [
      ...entries,
      { ...entries[2]!, atsEntryId: "exp-beta-engineer-copy", content: "Built data tooling." },
    ];
    const result = reconcileVisibleEntries([
      candidate({ candidateId: "ambiguous", kind: "experience", employerOrInstitution: "Beta Labs", titleOrDegree: "Engineer", startDate: "2021-06", endDate: "2022-02", location: "Paris", content: "Built data tooling." }),
    ], ambiguousEntries);
    expect(result.actions[0]).toMatchObject({ kind: "ambiguous", candidateId: "ambiguous", atsEntryIds: ["exp-beta-engineer", "exp-beta-engineer-copy"] });
    expect(result.entries).toEqual(ambiguousEntries);
  });

  it("preserves unmatched entries and is idempotent on a second run", () => {
    const candidates = [candidate({ candidateId: "edu", kind: "education", employerOrInstitution: "University of Example", titleOrDegree: "BSc Computer Science", startDate: "2014-09", endDate: "2018-06", location: "Berlin", content: "Computer science degree." })];
    const first = reconcileVisibleEntries(candidates, entries);
    const second = reconcileVisibleEntries(candidates, first.entries);
    expect(first.actions[0]?.kind).toBe("leave");
    expect(second.actions[0]?.kind).toBe("leave");
    expect(second.entries).toEqual(first.entries);
  });

  it("stops same-run candidate collisions instead of claiming one ATS entry twice", () => {
    const result = reconcileVisibleEntries([
      candidate({ candidateId: "first", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", content: "Built platform foundations." }),
      candidate({ candidateId: "second", kind: "experience", employerOrInstitution: "Acme & Co.", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", content: "Built platform foundations." }),
    ], [entries[0]!]);
    expect(result.actions.map((action) => action.kind)).toEqual(["leave", "ambiguous"]);
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
    expect(result.actions.map((action) => action.kind)).toEqual(["add", "ambiguous"]);
    expect(result.entries).toHaveLength(1);
  });
});

import { expect, test } from "@playwright/test";
import { reconcileVisibleEntries, type ReconciliationCandidate, type AtsReconciliationEntry } from "../../../../packages/ats-core/src/reconciliation";

declare global {
  interface Window {
    __aa202Fixture: {
      readEntries: () => AtsReconciliationEntry[];
      applyEntries: (entries: AtsReconciliationEntry[]) => void;
      remount: () => void;
      reset: () => void;
    };
  }
}

const fixtureUrl = "http://127.0.0.1:4174/reconciliation-application.html";

async function visibleEntries(page: import("@playwright/test").Page): Promise<AtsReconciliationEntry[]> {
  return page.evaluate(() => window.__aa202Fixture.readEntries());
}

async function applyCandidates(page: import("@playwright/test").Page, candidates: ReconciliationCandidate[]) {
  const result = reconcileVisibleEntries(candidates, await visibleEntries(page));
  await page.evaluate((entries) => window.__aa202Fixture.applyEntries(entries), result.entries);
  return result;
}

const baseCandidates: ReconciliationCandidate[] = [
  { candidateId: "source-senior", sourceId: "runr-exp-1", kind: "experience", employerOrInstitution: "acme and co", titleOrDegree: "Senior Engineer", startDate: "2020-01", endDate: "2022-06", location: "Berlin", content: "Built platform foundations and observability." },
  { candidateId: "source-new", sourceId: "runr-exp-new", kind: "experience", employerOrInstitution: "Gamma Works", titleOrDegree: "Staff Engineer", startDate: "2023-01", current: true, location: "Remote", content: "Designed systems." },
  { candidateId: "source-education", sourceId: "runr-edu-1", kind: "education", employerOrInstitution: "University of Example", titleOrDegree: "BSc Computer Science", startDate: "2014-09", endDate: "2018-06", location: "Berlin", content: "Computer science degree." },
];

test.describe("AA-202 sanitized reconciliation prototype", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(fixtureUrl);
    await page.evaluate(() => window.__aa202Fixture.reset());
  });

  test("adds, updates, preserves unmatched entries, and reruns without duplicates", async ({ page }) => {
    const first = await applyCandidates(page, baseCandidates);
    expect(first.actions.map((action) => action.kind)).toEqual(["update", "add", "leave"]);
    expect(await page.locator("[data-ats-entry-id]").count()).toBe(5);
    expect(await page.locator('[data-ats-entry-id="exp-acme-engineer"]').textContent()).toContain("Engineer");
    expect(await page.locator('[data-ats-entry-id="exp-beta-engineer"]').textContent()).toContain("Beta Labs");

    const second = await applyCandidates(page, baseCandidates);
    expect(second.actions.map((action) => action.kind)).toEqual(["leave", "leave", "leave"]);
    expect(await page.locator("[data-ats-entry-id]").count()).toBe(5);
  });

  test("survives reload and SPA remount without duplicates", async ({ page }) => {
    await applyCandidates(page, baseCandidates);
    await page.reload();
    expect((await applyCandidates(page, baseCandidates)).actions.every((action) => action.kind === "leave")).toBe(true);
    await page.evaluate(() => window.__aa202Fixture.remount());
    expect((await applyCandidates(page, baseCandidates)).actions.every((action) => action.kind === "leave")).toBe(true);
    expect(await page.locator("[data-ats-entry-id]").count()).toBe(5);
    await expect(page.locator("#reconciliation-fixture")).toHaveAttribute("data-aa202-remounts", "1");
  });

  test("keeps same-employer promotions and overlapping roles distinct", async ({ page }) => {
    const result = await applyCandidates(page, [
      { candidateId: "promotion", kind: "experience", employerOrInstitution: "ACME & CO", titleOrDegree: "Engineer", startDate: "2022-07", current: true, location: "Berlin", content: "Maintained services." },
      { candidateId: "overlap", kind: "experience", employerOrInstitution: "Beta Labs", titleOrDegree: "Engineer", startDate: "2021-05", endDate: "2022-02", location: "Paris", content: "Built data tooling." },
    ]);
    expect(result.actions.map((action) => action.kind)).toEqual(["leave", "update"]);
    expect(result.actions[1]).toMatchObject({ kind: "update", atsEntryId: "exp-beta-engineer" });
    await expect(page.locator('[data-kind="experience"]')).toHaveCount(3);
  });

  test("returns review-required and makes no mutation for an ambiguous match", async ({ page }) => {
    const initial = await visibleEntries(page);
    await page.evaluate((entries) => window.__aa202Fixture.applyEntries([...entries, { ...entries[2]!, atsEntryId: "exp-beta-engineer-copy" }]), initial);
    const before = await visibleEntries(page);
    const result = await applyCandidates(page, [{ candidateId: "ambiguous", kind: "experience", employerOrInstitution: "Beta Labs", titleOrDegree: "Engineer", startDate: "2021-06", endDate: "2022-02", location: "Paris", content: "Built data tooling." }]);
    expect(result.actions[0]?.kind).toBe("ambiguous");
    expect(await visibleEntries(page)).toEqual(before);
    await expect(page.locator("[data-ats-entry-id]")).toHaveCount(5);
  });
});

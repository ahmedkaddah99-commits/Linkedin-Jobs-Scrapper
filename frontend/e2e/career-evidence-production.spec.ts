import { expect, test, type Page, type Route } from "playwright/test";

const evidence = {
  evidence_id: "ev_prod_001",
  text: "Automated monthly reporting and reduced preparation time by 40%.",
  status: "needs_review",
  evidence_type: "achievement",
  inferred_employer: "Acme GmbH",
  inferred_role: "Operations Analyst",
  dates: ["2024"],
  source_asset: "baseline-cv.txt",
  source_id: "asset_prod_001",
  source_confidence: 0.96,
  experience_mapping: null,
};

const mapping = {
  experience_id: "exp_prod_001",
  label: "Operations Analyst at Acme GmbH",
  role: "Operations Analyst",
  company: "Acme GmbH",
  confidence: 0.96,
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installProductionApi(page: Page, { failFirstProcessing = false } = {}) {
  const state = {
    selected: [] as string[],
    evidence: null as null | typeof evidence,
    questionPending: false,
    processAttempts: 0,
  };
  const unexpected: string[] = [];

  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    // The synthetic Clerk publishable key has no external host by design; it
    // preserves the component boundary without making auth a test dependency.
    if (text.includes("ERR_NAME_NOT_RESOLVED")) return;
    if (failFirstProcessing && text.includes("504")) return;
    unexpected.push(`console: ${text}`);
  });
  page.on("pageerror", (error) => unexpected.push(`pageerror: ${error.message}`));

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/v1/, "");
    const method = request.method();

    if (method === "GET" && path === "/documents") {
      return json(route, { documents: [{
        document_id: "asset_prod_001",
        asset_id: "asset_prod_001",
        display_name: "baseline-cv.txt",
        source_origin: "upload",
        status: "ready",
      }], groups: [] });
    }
    if (path === "/analytics/events" && method === "POST") {
      return route.fulfill({ status: 204, body: "" });
    }
    if (path === "/settings" && method === "GET") {
      return json(route, { documents: {
        selectedAssetIds: state.selected,
        evidence_items: state.evidence ? [state.evidence] : [],
        pending_questions: state.questionPending ? [{
          question_id: "q_prod_001", evidence_id: evidence.evidence_id,
          resolved: false, dismissed: false,
        }] : [],
      } });
    }
    if (path === "/settings" && method === "PUT") {
      const payload = request.postDataJSON();
      state.selected = payload?.documents?.selectedAssetIds ?? state.selected;
      return json(route, { documents: payload.documents });
    }
    if (path === "/evidence-items/process-sources" && method === "POST") {
      state.processAttempts += 1;
      if (failFirstProcessing && state.processAttempts === 1) {
        return json(route, { error: { code: "source_timeout", message: "Gemini extraction timed out." } }, 504);
      }
      await new Promise((resolve) => setTimeout(resolve, 2500));
      state.evidence = { ...evidence };
      return json(route, {
        status: "completed",
        evidence: [state.evidence],
        state: { state: "completed", extracted_count: 1, retry_allowed: false },
        summary: { total_sources: 1, total_evidence: 1 },
      });
    }
    if (path === "/evidence-items/journey-state" && method === "GET") {
      if (state.questionPending) {
        return json(route, { state: "question", question: {
          question_id: "q_prod_001",
          evidence_id: evidence.evidence_id,
          question: "What measurable outcome did this automation produce?",
        } });
      }
      return json(route, { state: "review", next_review: {
        state: "review", evidence: state.evidence,
        suggested_mapping: mapping, is_ambiguous: false, alternatives: [],
        provenance: { source_asset: "baseline-cv.txt", confidence: 0.96 },
        progress: { cursor: 1, remaining: 1, total: 1 },
      } });
    }
    if (path === "/evidence-items/next-review" && method === "GET") {
      return json(route, { state: "review", evidence: state.evidence, suggested_mapping: mapping,
        is_ambiguous: false, alternatives: [],
        provenance: { source_asset: "baseline-cv.txt", confidence: 0.96 },
        progress: { cursor: 1, remaining: 1, total: 1 } });
    }
    if (path === "/evidence-items/confirm-inspect" && method === "POST") {
      state.evidence = { ...evidence, status: "confirmed", experience_mapping: mapping };
      state.questionPending = true;
      return json(route, { state: "question", evidence: state.evidence, question: {
        question_id: "q_prod_001", evidence_id: evidence.evidence_id,
        question: "What measurable outcome did this automation produce?",
      } });
    }
    if (path === "/evidence-items/answer-enrich" && method === "POST") {
      state.questionPending = false;
      return json(route, { state: "ready", action: "answered", readiness: { is_ready: true } });
    }
    if (path === "/evidence-items/ready-actions" && method === "GET") {
      return json(route, { primary_actions: [
        { action: "cv_bullet", label: "Generate CV Bullet", description: "Grounded CV evidence",
          evidence_ids: [evidence.evidence_id], source: "canonical_evidence" },
        { action: "motivation_letter", label: "Generate Motivation Letter", description: "Grounded letter evidence",
          evidence_ids: [evidence.evidence_id], source: "canonical_evidence" },
      ] });
    }

    unexpected.push(`${method} ${path}`);
    return json(route, { error: { code: "unexpected_e2e_request", message: `${method} ${path}` } }, 500);
  });
  return { state, unexpected };
}

test("visible production journey advances in exact order and survives reload", async ({ page }) => {
  const api = await installProductionApi(page);
  await page.goto("/career-evidence");

  await expect(page.getByRole("heading", { level: 1, name: "Add source evidence" })).toBeVisible();
  await page.getByRole("button", { name: /baseline-cv\.txt/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Processing evidence" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Processing evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Confirm evidence" })).toBeVisible();
  await expect(page.getByText("Operations Analyst at Acme GmbH").first()).toBeVisible();
  await expect(page.getByText("baseline-cv.txt").first()).toBeVisible();

  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("What measurable outcome did this automation produce?")).toBeVisible();
  await page.reload();
  await expect(page.getByText("What measurable outcome did this automation produce?")).toBeVisible();
  await page.getByPlaceholder("Type your answer...").fill("Saved 16 analyst hours every month.");
  await page.getByRole("button", { name: "Answer" }).click();

  const readyHeading = page.getByRole("heading", { level: 1, name: "Ready to use" });
  await expect(readyHeading).toBeVisible();
  await expect(readyHeading).toBeFocused();
  await expect(page.getByText("Generate CV Bullet")).toBeVisible();
  await expect(page.getByText("Generate Motivation Letter")).toBeVisible();
  await expect(page.getByText(/Evidence: 1 items/)).toHaveCount(2);
  expect(api.state.evidence?.experience_mapping?.experience_id).toBe("exp_prod_001");
  expect(api.unexpected).toEqual([]);
});

test("stage-specific timeout exposes Retry and resumes the same operation", async ({ page }) => {
  const api = await installProductionApi(page, { failFirstProcessing: true });
  await page.goto("/career-evidence");
  await page.getByRole("button", { name: /baseline-cv\.txt/ }).click();
  await expect(page.getByText(/Processing failed.*Gemini extraction timed out/i)).toBeVisible();
  await page.getByRole("button", { name: "Retry processing" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Confirm evidence" })).toBeVisible();
  expect(api.state.processAttempts).toBe(2);
  expect(api.unexpected).toEqual([]);
});

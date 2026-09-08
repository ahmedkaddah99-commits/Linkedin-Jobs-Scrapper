export const MASTER_CV_INTRO_STORAGE_KEY = "runr.master-cv.intro-seen";

export function shouldShowMasterCvIntro(storageValue) {
  return storageValue !== "1";
}

export function flattenMasterCvBullets(masterCv) {
  return (masterCv?.sections || []).flatMap((section) =>
    (section.entries || []).flatMap((entry) =>
      (entry.bullets || []).map((bullet) => ({ ...bullet, entryId: entry.id, sectionId: section.id })),
    ),
  );
}

export function visibleMasterCvBullets(entry, view) {
  const bullets = entry?.bullets || [];
  return view === "extra" ? bullets.filter((bullet) => bullet.extra) : bullets;
}

export function countMasterCvExtraEvidence(masterCv) {
  return flattenMasterCvBullets(masterCv).filter((bullet) => bullet.extra).length;
}

export function addMasterCvAchievement(masterCv, entryId, text, nextId = "draft-1") {
  const cleanedText = String(text || "").trim();
  if (!cleanedText) return masterCv;
  const targetExists = (masterCv?.sections || []).some((section) =>
    (section.entries || []).some((entry) => entry.id === entryId),
  );
  if (!targetExists) return masterCv;

  return {
    ...masterCv,
    sections: (masterCv.sections || []).map((section) => ({
      ...section,
      entries: (section.entries || []).map((entry) => entry.id === entryId
        ? {
          ...entry,
          bullets: [
            ...(entry.bullets || []),
            { id: nextId, text: cleanedText, score: 72, extra: true, draft: true },
          ],
        }
        : entry),
    })),
  };
}

export function findMasterCvBullet(masterCv, bulletId) {
  return flattenMasterCvBullets(masterCv).find((bullet) => bullet.id === bulletId) || null;
}

export function getMasterCvGuidance(bullet) {
  if (bullet?.guidance && typeof bullet.guidance === "object") {
    return bullet.guidance;
  }
  const score = Number(bullet?.score || 0);
  const hasMetric = Boolean(bullet?.metric) || /\b\d+%|\b\d+\b/.test(String(bullet?.text || ""));
  const impactStrong = score >= 85 || hasMetric;

  return {
    score,
    title: score >= 85 ? "Strong evidence" : score >= 72 ? "Good foundation" : "Worth developing",
    summary: score >= 85
      ? "This achievement is specific, easy to scan, and clearly connected to your contribution."
      : "This is useful evidence. A little more detail would make your contribution easier to understand.",
    checks: [
      { label: "Clear action", detail: "Starts with a decisive action verb.", state: "pass" },
      { label: "Useful context", detail: "Shows your scope and collaborators.", state: "pass" },
      {
        label: "Demonstrated impact",
        detail: impactStrong ? "Includes a measurable or credible outcome." : "Add what changed because of your work.",
        state: impactStrong ? "pass" : "warn",
      },
    ],
    suggestion: score >= 85
      ? "Already strong. Add the size of the customer group if it strengthens the story."
      : "Connect the work to a decision, deliverable, customer outcome, or other change.",
    use: "When a role asks for discovery, cross-functional leadership, or enterprise work, this can replace a less relevant bullet in a tailored CV.",
  };
}

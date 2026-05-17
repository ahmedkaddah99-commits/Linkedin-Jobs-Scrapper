const DEFAULT_SOURCE = "user_added";

export const CAREER_MEMORY_CATEGORY_META = {
  achievement: {
    label: "Achievement",
    description: "High-impact win or measurable result.",
  },
  project: {
    label: "Project",
    description: "Project, workflow, or initiative worth reusing.",
  },
  motivation: {
    label: "Motivation",
    description: "Why a role, mission, or industry matters to you.",
  },
  challenge: {
    label: "Challenge",
    description: "Constraint, hurdle, or difficult situation you handled.",
  },
  stakeholder_story: {
    label: "Stakeholder Story",
    description: "Cross-team, leadership, or communication example.",
  },
  tool_system_experience: {
    label: "Tool/System Experience",
    description: "Systems, dashboards, templates, or technical workflow experience.",
  },
};

export const CAREER_MEMORY_CATEGORY_OPTIONS = Object.entries(CAREER_MEMORY_CATEGORY_META).map(
  ([value, meta]) => ({
    value,
    label: meta.label,
  }),
);

export const GUIDED_INTERVIEW_OPENING_PROMPT =
  "I reviewed your uploaded documents. They give me the basics, but stronger applications need proof of impact. Think about a task, process, report, spreadsheet, workflow, or communication flow you improved. What was slow, manual, confusing, or error-prone before you worked on it?";

export const INTERVIEW_CHIPS = [
  {
    id: "saved_time",
    label: "Saved time",
    category: "achievement",
    focusPrompt:
      "Think of a recurring task that used to take longer than it should. What steps were repetitive, delayed, or dependent on manual follow-up before you improved it?",
    followUps: [
      "What exactly did you change?",
      "Which tools, templates, or systems were involved?",
      "Who got the time back?",
      "Can you estimate the time saved per week or month?",
      "Would this be stronger as a CV bullet, a cover letter example, or both?",
    ],
    tags: ["efficiency", "process-improvement"],
    cvStarter: "Improved a time-heavy workflow by",
    coverLetterAngle:
      "Use this to show practical ownership, efficiency thinking, and follow-through.",
  },
  {
    id: "automated_something",
    label: "Automated something",
    category: "project",
    focusPrompt:
      "Think of a manual task you reduced or automated. Was there a spreadsheet, tracker, template, script, dashboard, or repeat process that stopped relying on manual work after your change?",
    followUps: [
      "What was manual before?",
      "What did you build or set up?",
      "Which tools, systems, templates, dashboards, or processes did you use?",
      "Who depended on the output?",
      "What was the result in speed, accuracy, or consistency?",
    ],
    tags: ["automation", "systems"],
    cvStarter: "Reduced manual work by",
    coverLetterAngle:
      "Use this to show initiative, systems thinking, and comfort improving operations.",
  },
  {
    id: "improved_reporting",
    label: "Improved reporting",
    category: "tool_system_experience",
    focusPrompt:
      "Think about reporting, dashboards, trackers, or status updates that became easier to trust because of your work. What information was hard to find, slow to update, or unclear before?",
    followUps: [
      "What exactly became easier to report or track?",
      "Which report, dashboard, template, or data source did you improve?",
      "Who used the information after your change?",
      "Did it improve accuracy, visibility, or decision-making?",
      "Could you estimate how often this report was used?",
    ],
    tags: ["reporting", "dashboards", "visibility"],
    cvStarter: "Improved reporting visibility by",
    coverLetterAngle:
      "Use this to show clear communication, detail orientation, and decision support.",
  },
  {
    id: "fixed_messy_data",
    label: "Fixed messy data",
    category: "tool_system_experience",
    focusPrompt:
      "Think of a time data was inconsistent, duplicated, incomplete, or difficult to trust. What was messy before you cleaned it up or structured it better?",
    followUps: [
      "What kinds of errors or gaps were happening?",
      "How did you clean, organize, or standardize the data?",
      "Which files, systems, or records were involved?",
      "Who benefited from cleaner data?",
      "Did it reduce mistakes or rework?",
    ],
    tags: ["data-quality", "cleanup", "accuracy"],
    cvStarter: "Strengthened data accuracy by",
    coverLetterAngle:
      "Use this to show reliability, pattern recognition, and care with operational detail.",
  },
  {
    id: "coordinated_stakeholders",
    label: "Coordinated stakeholders",
    category: "stakeholder_story",
    focusPrompt:
      "Think of a moment you kept people aligned across teams, clients, vendors, or managers. Where were handoffs, expectations, or communication breaking down before you stepped in?",
    followUps: [
      "Who was involved?",
      "What exactly did you coordinate or clarify?",
      "What changed after your intervention?",
      "Did this prevent delays, confusion, or escalation?",
      "Would this help more as a cover letter story, a CV bullet, or both?",
    ],
    tags: ["stakeholders", "coordination", "communication"],
    cvStarter: "Coordinated cross-functional stakeholders to",
    coverLetterAngle:
      "Use this to show communication range, trust-building, and ownership under ambiguity.",
  },
  {
    id: "solved_urgent_issue",
    label: "Solved an urgent issue",
    category: "challenge",
    focusPrompt:
      "Think of an urgent issue, blocker, error, or last-minute problem. What was at risk, and what did you do to stabilize the situation?",
    followUps: [
      "What made the situation urgent?",
      "What steps did you take first?",
      "Who depended on the fix?",
      "What was the outcome once the issue was resolved?",
      "Can you estimate the business, customer, or delivery impact?",
    ],
    tags: ["problem-solving", "urgency", "delivery"],
    cvStarter: "Resolved an urgent operational issue by",
    coverLetterAngle:
      "Use this to show judgment under pressure and steady problem-solving.",
  },
  {
    id: "not_sure",
    label: "Not sure",
    category: "achievement",
    focusPrompt:
      "Start small. Think about a week when people thanked you, asked for your template again, depended on your spreadsheet, or noticed that work became easier after you touched it. What do you remember?",
    followUps: [
      "What task or situation comes to mind first?",
      "Was it about speed, quality, coordination, or fixing a problem?",
      "Which tools or files were involved?",
      "Who noticed the improvement?",
      "What rough result can you estimate, even if it is not exact yet?",
    ],
    tags: ["memory-jogger"],
    cvStarter: "Contributed to a workflow improvement by",
    coverLetterAngle:
      "Use this as a draft memory. You can sharpen the wording once the details come back.",
  },
];

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeStringList(values) {
  const input = Array.isArray(values) ? values : [];
  return Array.from(new Set(input.map((item) => normalizeString(item)).filter(Boolean)));
}

function normalizeTagList(values) {
  if (Array.isArray(values)) {
    return normalizeStringList(values);
  }
  return normalizeStringList(String(values || "").split(","));
}

function createId(prefix = "memory") {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function firstSentence(text) {
  const normalized = normalizeString(text).replace(/\s+/g, " ");
  if (!normalized) {
    return "";
  }
  const sentence = normalized.split(/(?<=[.!?])\s+/)[0] || normalized;
  return sentence.slice(0, 160).trim();
}

function titleFromText(text, fallback) {
  const sentence = firstSentence(text).replace(/[.?!]+$/, "");
  if (!sentence) {
    return fallback;
  }
  const words = sentence.split(" ").slice(0, 10);
  const compact = words.join(" ").trim();
  return compact.length > 72 ? `${compact.slice(0, 69)}...` : compact;
}

function collectTagsFromText(text) {
  const normalized = normalizeString(text).toLowerCase();
  const tags = [];
  const tagRules = [
    ["excel", "excel"],
    ["spreadsheet", "spreadsheets"],
    ["dashboard", "dashboards"],
    ["report", "reporting"],
    ["automation", "automation"],
    ["automated", "automation"],
    ["data", "data"],
    ["stakeholder", "stakeholders"],
    ["client", "client-facing"],
    ["process", "process"],
    ["workflow", "workflow"],
    ["urgent", "urgent"],
    ["template", "templates"],
  ];
  tagRules.forEach(([pattern, tag]) => {
    if (normalized.includes(pattern)) {
      tags.push(tag);
    }
  });
  return normalizeStringList(tags);
}

export function hasMetric(card) {
  return /\d/.test(
    [
      card?.impactMetric,
      card?.rawNote,
      card?.polishedCvBullet,
      card?.coverLetterAngle,
    ]
      .filter(Boolean)
      .join(" "),
  );
}

function buildConfidenceLabel(card) {
  const detailLength = normalizeString(card.rawNote).length;
  if (card.source !== DEFAULT_SOURCE) {
    return "Imported source";
  }
  if (hasMetric(card) && detailLength >= 120) {
    return "High confidence";
  }
  if (detailLength >= 60) {
    return "Good draft";
  }
  return "Needs more detail";
}

function buildSourceLabel(card) {
  if (card.source === "uploaded_document") {
    return "Uploaded document";
  }
  if (card.source === "imported_profile") {
    return "Imported profile";
  }
  return "User added";
}

export function normalizeCareerMemoryCard(card, index = 0) {
  const category = CAREER_MEMORY_CATEGORY_META[card?.category] ? card.category : "achievement";
  const normalized = {
    id: normalizeString(card?.id) || createId(`memory_${index}`),
    title:
      normalizeString(card?.title) ||
      titleFromText(card?.rawNote, `Career memory ${index + 1}`),
    category,
    source: normalizeString(card?.source) || DEFAULT_SOURCE,
    rawNote: normalizeString(card?.rawNote),
    polishedCvBullet: normalizeString(card?.polishedCvBullet),
    coverLetterAngle: normalizeString(card?.coverLetterAngle),
    tags: normalizeTagList(card?.tags),
    confidenceLabel: normalizeString(card?.confidenceLabel),
    sourceLabel: normalizeString(card?.sourceLabel),
    impactMetric: normalizeString(card?.impactMetric),
    useInCv: card?.useInCv !== false,
    useInLetter: Boolean(card?.useInLetter),
    createdAt: normalizeString(card?.createdAt) || new Date().toISOString(),
  };
  if (!normalized.confidenceLabel) {
    normalized.confidenceLabel = buildConfidenceLabel(normalized);
  }
  if (!normalized.sourceLabel) {
    normalized.sourceLabel = buildSourceLabel(normalized);
  }
  return normalized;
}

const normalizeCard = normalizeCareerMemoryCard;

function buildSeedCard(text, category, title, source) {
  const rawNote = normalizeString(text);
  if (!rawNote) {
    return null;
  }
  const card = normalizeCard({
    title,
    category,
    source,
    rawNote,
    polishedCvBullet: firstSentence(rawNote),
    coverLetterAngle: firstSentence(rawNote),
    tags: collectTagsFromText(rawNote),
    useInCv: category !== "motivation",
    useInLetter: category === "motivation" || category === "challenge",
  });
  return card;
}

function seedCardsFromLegacyFields(draft) {
  return [
    buildSeedCard(
      draft.achievementHighlights,
      "achievement",
      "Imported achievement notes",
      "imported_profile",
    ),
    buildSeedCard(
      draft.additionalBulletBank,
      "project",
      "Imported bullet bank",
      "imported_profile",
    ),
    buildSeedCard(
      draft.professionalHurdlesContext,
      "challenge",
      "Imported challenge context",
      "imported_profile",
    ),
    buildSeedCard(
      draft.motivationLetterNotes,
      "motivation",
      "Imported motivation notes",
      "imported_profile",
    ),
  ].filter(Boolean);
}

function renderCardsForLegacyText(cards, { includeCoverAngles = false } = {}) {
  return cards
    .map((card) => {
      const lines = [
        `${card.title} [${CAREER_MEMORY_CATEGORY_META[card.category]?.label || card.category}]`,
        normalizeString(card.rawNote),
        card.impactMetric ? `Impact estimate: ${card.impactMetric}` : "",
        card.polishedCvBullet ? `CV angle: ${card.polishedCvBullet}` : "",
        includeCoverAngles && card.coverLetterAngle
          ? `Letter angle: ${card.coverLetterAngle}`
          : "",
      ].filter(Boolean);
      return lines.join("\n");
    })
    .join("\n\n");
}

function mergeTextSections(sections) {
  return sections
    .map((section) => normalizeString(section))
    .filter(Boolean)
    .join("\n\n");
}

export function buildCareerMemoryDraft(documents = {}) {
  const draft = {
    selectedAssetIds: normalizeStringList(
      documents.selectedAssetIds || documents.ai_canvas_source_asset_ids,
    ),
    masterProfileAssetId: normalizeString(
      documents.masterProfileAssetId || documents.master_career_profile_asset_id,
    ),
    importedCareerContext: normalizeString(
      documents.importedCareerContext || documents.master_career_profile_text,
    ),
    achievementHighlights: normalizeString(
      documents.achievementHighlights || documents.career_highlights_text,
    ),
    additionalBulletBank: normalizeString(
      documents.additionalBulletBank || documents.bullet_bank_text,
    ),
    professionalHurdlesContext: normalizeString(
      documents.professionalHurdlesContext || documents.professional_hurdles_text,
    ),
    motivationLetterNotes: normalizeString(
      documents.motivationLetterNotes || documents.motivation_letter_notes,
    ),
    generatedMemoryCards: Array.isArray(
      documents.generatedMemoryCards || documents.generated_memory_cards,
    )
      ? (documents.generatedMemoryCards || documents.generated_memory_cards).map(normalizeCard)
      : [],
  };
  if (!draft.generatedMemoryCards.length) {
    draft.generatedMemoryCards = seedCardsFromLegacyFields(draft);
  }
  return draft;
}

export function buildCareerMemoryPayload(draft) {
  const cards = (draft.generatedMemoryCards || []).map(normalizeCard);
  const achievementCards = cards.filter((card) =>
    ["achievement", "project", "stakeholder_story", "tool_system_experience"].includes(
      card.category,
    ),
  );
  const challengeCards = cards.filter((card) =>
    ["challenge", "stakeholder_story"].includes(card.category),
  );
  const motivationCards = cards.filter((card) =>
    ["motivation", "challenge", "stakeholder_story"].includes(card.category),
  );

  return {
    master_career_profile_asset_id: normalizeString(draft.masterProfileAssetId),
    master_career_profile_text: normalizeString(draft.importedCareerContext),
    career_highlights_text: mergeTextSections([
      draft.achievementHighlights,
      renderCardsForLegacyText(achievementCards),
    ]),
    bullet_bank_text: mergeTextSections([
      draft.additionalBulletBank,
      achievementCards.map((card) => card.polishedCvBullet).filter(Boolean).join("\n"),
    ]),
    professional_hurdles_text: mergeTextSections([
      draft.professionalHurdlesContext,
      renderCardsForLegacyText(challengeCards),
    ]),
    motivation_letter_notes: mergeTextSections([
      draft.motivationLetterNotes,
      renderCardsForLegacyText(motivationCards, { includeCoverAngles: true }),
    ]),
    ai_canvas_source_asset_ids: normalizeStringList(draft.selectedAssetIds),
    generated_memory_cards: cards,
  };
}

function findChip(chipId) {
  return INTERVIEW_CHIPS.find((chip) => chip.id === chipId) || INTERVIEW_CHIPS[0];
}

function metricSnippet(text) {
  const match = String(text || "").match(/[^.]*\d[^.]*/);
  return match ? normalizeString(match[0]) : "";
}

function buildCvBullet(chip, answer, metric) {
  const compact = firstSentence(answer).replace(/[.?!]+$/, "");
  if (!compact) {
    return chip.cvStarter;
  }
  const suffix = metric ? `, delivering ${metric}` : "";
  return `${chip.cvStarter} ${compact.toLowerCase()}${suffix}.`;
}

export function createInterviewMemoryCard({ answer, chipId, existingCount = 0 }) {
  const chip = findChip(chipId);
  const rawNote = normalizeString(answer);
  const metric = metricSnippet(rawNote);
  return normalizeCard({
    id: createId("interview"),
    title: titleFromText(rawNote, `${chip.label} story ${existingCount + 1}`),
    category: chip.category,
    source: DEFAULT_SOURCE,
    rawNote,
    polishedCvBullet: buildCvBullet(chip, rawNote, metric),
    coverLetterAngle: `${chip.coverLetterAngle} Connect it to the target role's needs and why you care about solving similar problems.`,
    tags: [...chip.tags, ...collectTagsFromText(rawNote)],
    impactMetric: metric,
    useInCv: chip.category !== "motivation",
    useInLetter: chip.category === "motivation" || chip.category === "challenge",
  });
}

export function createBlankMemoryCard({ category = "achievement", title = "" } = {}) {
  return normalizeCard({
    id: createId("manual"),
    title: title || `New ${CAREER_MEMORY_CATEGORY_META[category]?.label || "memory"}`,
    category,
    source: DEFAULT_SOURCE,
    rawNote: "",
    polishedCvBullet: "",
    coverLetterAngle: "",
    tags: [],
    useInCv: true,
    useInLetter: category === "motivation" || category === "challenge",
  });
}

export function filterCardsByCategories(cards, categories) {
  const selectedCategories = new Set(categories);
  return (cards || []).filter((card) => selectedCategories.has(card.category));
}

export function getMissingContextRecommendations(draft) {
  const cards = draft.generatedMemoryCards || [];
  const achievementStories = filterCardsByCategories(cards, ["achievement", "project"]);
  const projectExamples = filterCardsByCategories(cards, ["project", "tool_system_experience"]);
  const stakeholderExamples = filterCardsByCategories(cards, ["stakeholder_story"]);
  const motivationExamples = filterCardsByCategories(cards, ["motivation", "challenge"]);
  const quantifiedExamples = cards.filter((card) => hasMetric(card));

  return [
    {
      id: "achievement_stories",
      title: `Add ${Math.max(0, 3 - achievementStories.length) || 0} achievement stories`,
      targetLabel: `${achievementStories.length}/3 captured`,
      isComplete: achievementStories.length >= 3,
      why: "Specific stories give Runr better proof points for tailored CV bullets and application answers.",
      chipId: "saved_time",
    },
    {
      id: "quantified_outcomes",
      title: "Add quantified outcomes",
      targetLabel: `${quantifiedExamples.length}/2 with metrics`,
      isComplete: quantifiedExamples.length >= 2,
      why: "Numbers make tailoring more credible, even when you only have rough estimates.",
      chipId: "automated_something",
    },
    {
      id: "project_examples",
      title: "Add project examples",
      targetLabel: `${projectExamples.length}/2 captured`,
      isComplete: projectExamples.length >= 2,
      why: "Project examples help Runr swap in stronger evidence for different roles and industries.",
      chipId: "improved_reporting",
    },
    {
      id: "stakeholder_examples",
      title: "Add stakeholder or leadership examples",
      targetLabel: `${stakeholderExamples.length}/1 captured`,
      isComplete: stakeholderExamples.length >= 1,
      why: "Communication and coordination stories often matter as much as technical execution.",
      chipId: "coordinated_stakeholders",
    },
    {
      id: "motivation_notes",
      title: "Add motivation-letter notes",
      targetLabel: motivationExamples.length
        ? `${motivationExamples.length} reusable notes`
        : "No reusable notes yet",
      isComplete:
        motivationExamples.length >= 1 || normalizeString(draft.motivationLetterNotes).length >= 60,
      why: "Motivation context helps cover letters feel specific instead of generic.",
      chipId: "solved_urgent_issue",
    },
  ];
}

export function summarizeReadiness(draft, assetDocuments = []) {
  const cards = draft.generatedMemoryCards || [];
  const baselineCount = assetDocuments.filter(
    (item) => normalizeString(item.asset_kind).toLowerCase() === "workspace_cv",
  ).length;
  const selectedAssetCount = (draft.selectedAssetIds || []).length;
  const missing = getMissingContextRecommendations(draft).filter((item) => !item.isComplete);
  const distinctCategories = new Set(cards.map((card) => card.category)).size;
  const metricsCount = cards.filter((card) => hasMetric(card)).length;

  const basicReady = baselineCount > 0;
  const advancedReady =
    basicReady &&
    Boolean(draft.masterProfileAssetId) &&
    selectedAssetCount > 0 &&
    cards.length >= 4 &&
    distinctCategories >= 3 &&
    metricsCount >= 2 &&
    missing.length === 0;

  return [
    {
      title: "Connected Documents",
      status: advancedReady
        ? "Ready for advanced tailoring"
        : basicReady
          ? "Basic"
          : "Needs more detail",
      value: `${baselineCount} baseline CV${baselineCount === 1 ? "" : "s"} + ${selectedAssetCount} selected source asset${selectedAssetCount === 1 ? "" : "s"}`,
      description: basicReady
        ? "Baseline CV is available. Add selected sources and a master profile to deepen tailoring."
        : "Upload a baseline CV in the Asset Library to unlock tailoring.",
    },
    {
      title: "Memory Strength",
      status:
        cards.length >= 5 && distinctCategories >= 3
          ? "Ready for advanced tailoring"
          : cards.length >= 2
            ? "Basic"
            : "Needs more detail",
      value: `${cards.length} saved memories across ${distinctCategories || 0} categories`,
      description:
        metricsCount > 0
          ? `${metricsCount} memories already include numbers or estimates.`
          : "Add examples with rough metrics so Runr has stronger proof of impact.",
    },
    {
      title: "Missing High-Impact Details",
      status: missing.length ? "Needs more detail" : "Ready for advanced tailoring",
      value: missing.length ? `${missing.length} priority gap${missing.length === 1 ? "" : "s"}` : "No obvious gaps",
      description: missing.length
        ? missing.map((item) => item.title).join(" | ")
        : "You have the main building blocks for stronger CV and cover-letter tailoring.",
    },
    {
      title: "Advanced Tailoring Readiness",
      status: advancedReady ? "Ready for advanced tailoring" : basicReady ? "Basic" : "Needs more detail",
      value: advancedReady
        ? "Runr can personalize beyond the baseline CV."
        : basicReady
          ? "Basic tailoring is ready. Add richer context for stronger customization."
          : "Upload documents first, then add memories that documents do not say.",
      description: advancedReady
        ? "Documents, story coverage, and reusable evidence are all in place."
        : "The guided interview will help fill the missing evidence quickly.",
    },
  ];
}

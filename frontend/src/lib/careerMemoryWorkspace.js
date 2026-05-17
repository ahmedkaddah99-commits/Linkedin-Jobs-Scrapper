const DEFAULT_QUESTION_SET_TYPE = "story_recovery";
const DEFAULT_SOURCE = "user_added";

export const CAREER_MEMORY_CATEGORY_META = {
  achievement: { label: "Achievement" },
  project: { label: "Project" },
  metric: { label: "Metric" },
  stakeholder_story: { label: "Stakeholder story" },
  motivation: { label: "Motivation" },
  challenge: { label: "Challenge" },
  tool_system: { label: "Tools & systems" },
};

export const CAREER_MEMORY_STATUS_META = {
  needs_detail: {
    label: "Needs detail",
    badgeClass: "bg-amber-500/10 text-amber-200 dark:text-amber-100",
  },
  needs_metric: {
    label: "Needs metric",
    badgeClass: "bg-surface-container-low text-on-surface",
  },
  ready_for_tailoring: {
    label: "Ready for tailoring",
    badgeClass: "bg-primary/15 text-primary",
  },
};

export const MEMORY_TRIGGER_CHIPS = [
  { id: "saved_time", label: "Saved time", category: "achievement", tags: ["efficiency", "time-saving"] },
  { id: "automated_something", label: "Automated something", category: "project", tags: ["automation", "systems"] },
  { id: "improved_reporting", label: "Improved reporting", category: "tool_system", tags: ["reporting", "visibility"] },
  { id: "fixed_messy_data", label: "Fixed messy data", category: "tool_system", tags: ["data-quality", "cleanup"] },
  { id: "coordinated_stakeholders", label: "Coordinated stakeholders", category: "stakeholder_story", tags: ["stakeholders", "coordination"] },
  { id: "solved_urgent_issue", label: "Solved urgent issue", category: "challenge", tags: ["problem-solving", "urgency"] },
  { id: "built_a_process", label: "Built a process", category: "project", tags: ["process", "workflow"] },
  { id: "helped_a_team", label: "Helped a team", category: "stakeholder_story", tags: ["team-support", "collaboration"] },
  { id: "not_sure", label: "Not sure", category: "achievement", tags: ["memory-jogger"] },
];

export const MEMORY_BANK_FILTERS = [
  { id: "all", label: "All" },
  { id: "achievement", label: "Achievements" },
  { id: "project", label: "Projects" },
  { id: "metric", label: "Metrics" },
  { id: "stakeholder_story", label: "Stakeholder stories" },
  { id: "motivation", label: "Motivation" },
  { id: "challenge", label: "Challenges" },
  { id: "tool_system", label: "Tools & systems" },
  { id: "needs_detail", label: "Needs detail" },
  { id: "ready_for_tailoring", label: "Ready for tailoring" },
];

export const MEMORY_BUILDER_TABS = [
  { id: "build", label: "Build" },
  { id: "memory_bank", label: "Memory Bank" },
  { id: "sources", label: "Sources" },
  { id: "advanced", label: "Advanced" },
];

export const QUESTION_SET_DEFINITIONS = {
  story_recovery: {
    id: "story_recovery",
    title: "Let's recover one strong career story",
    description:
      "Answer the next useful question. Runr will turn it into a reusable career memory.",
    defaultCategory: "achievement",
    suggestedTrigger: "saved_time",
    steps: [
      {
        id: "before",
        question:
          "Think of a task, report, spreadsheet, process, workflow, or communication flow you improved. What was slow, manual, confusing, or error-prone before you worked on it?",
      },
      {
        id: "change",
        question:
          "What exactly did you change? Mention any tools, templates, dashboards, systems, processes, or communication steps you used.",
      },
      {
        id: "benefit",
        question:
          "Who benefited from your work? For example: your manager, another team, customers, clients, vendors, leadership, auditors, or operations colleagues.",
      },
      {
        id: "outcome",
        question:
          "What became faster, clearer, more accurate, more reliable, less manual, or easier to coordinate after your work?",
      },
      {
        id: "impact",
        question:
          "Can you estimate the impact, even roughly? For example: hours saved, fewer errors, faster reporting, fewer follow-ups, fewer delays, better visibility, smoother handoffs, or reduced escalation.",
      },
    ],
  },
  quantified_outcome: {
    id: "quantified_outcome",
    title: "Let's pin down a measurable outcome",
    description: "Give Runr a rough number or concrete signal it can reuse in tailored applications.",
    defaultCategory: "metric",
    suggestedTrigger: "saved_time",
    steps: [
      {
        id: "result_area",
        question:
          "Think of a result you improved. Could the impact be measured in time saved, errors reduced, reports delivered faster, people supported, cost avoided, or work completed more reliably?",
      },
      {
        id: "change",
        question: "What caused that improvement? What did you change, build, fix, or coordinate?",
      },
      {
        id: "benefit",
        question: "Who saw the benefit or depended on the result?",
      },
      {
        id: "outcome",
        question: "What became noticeably better after your work?",
      },
      {
        id: "impact",
        question: "What rough metric, count, frequency, or before/after estimate can you give?",
      },
    ],
  },
  project_example: {
    id: "project_example",
    title: "Let's capture one project example",
    description: "A stronger project example gives Runr better material for role-specific CV bullets.",
    defaultCategory: "project",
    suggestedTrigger: "built_a_process",
    steps: [
      {
        id: "goal",
        question:
          "Think of a project or initiative that took more than a few days. What was the goal, and why did it matter?",
      },
      {
        id: "ownership",
        question: "What did you personally own or drive inside that project?",
      },
      {
        id: "change",
        question:
          "Which tools, systems, templates, dashboards, workflows, or communication steps were part of the work?",
      },
      {
        id: "benefit",
        question: "Who benefited once the project was in place?",
      },
      {
        id: "impact",
        question: "What changed because of it? Include any rough results, improvements, or lasting effects.",
      },
    ],
  },
  stakeholder_story: {
    id: "stakeholder_story",
    title: "Let's recover a stakeholder story",
    description: "Runr can use stakeholder stories in CVs, letters, outreach, and interview prep.",
    defaultCategory: "stakeholder_story",
    suggestedTrigger: "coordinated_stakeholders",
    steps: [
      {
        id: "before",
        question:
          "Think of a moment you kept people aligned across teams, clients, vendors, or managers. Where were handoffs, expectations, or communication breaking down before you stepped in?",
      },
      {
        id: "change",
        question: "What exactly did you do to align people, clarify ownership, or move the work forward?",
      },
      {
        id: "benefit",
        question: "Who was involved, and who benefited from your coordination?",
      },
      {
        id: "outcome",
        question: "What became smoother, clearer, faster, or less risky because of your involvement?",
      },
      {
        id: "impact",
        question: "Can you give any concrete signal of impact, even if it is only a rough estimate?",
      },
    ],
  },
  motivation_notes: {
    id: "motivation_notes",
    title: "Let's capture one motivation angle",
    description: "Strong motivation notes help cover letters and outreach messages feel specific.",
    defaultCategory: "motivation",
    suggestedTrigger: "helped_a_team",
    steps: [
      {
        id: "interest_area",
        question:
          "What types of companies, industries, missions, or problems genuinely interest you, and why?",
      },
      {
        id: "reason",
        question: "What about that work feels meaningful or energizing to you?",
      },
      {
        id: "evidence",
        question: "What in your background shows this interest is genuine rather than generic?",
      },
      {
        id: "benefit",
        question: "What kinds of teams, environments, or company situations do you think you help most?",
      },
      {
        id: "impact",
        question: "How could Runr turn this into a stronger motivation-letter angle or interview answer?",
      },
    ],
  },
};

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeStringList(value) {
  if (Array.isArray(value)) {
    return Array.from(new Set(value.map((item) => normalizeString(item)).filter(Boolean)));
  }
  return Array.from(
    new Set(
      normalizeString(value)
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function createId(prefix = "memory") {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function firstNonEmpty(values) {
  return values.find((value) => normalizeString(value));
}

function firstSentence(text) {
  const normalized = normalizeString(text).replace(/\s+/g, " ");
  if (!normalized) {
    return "";
  }
  return normalized.split(/(?<=[.!?])\s+/)[0] || normalized;
}

function titleFromAnswers(values, fallback) {
  const base = firstSentence(firstNonEmpty(values) || "").replace(/[.?!]+$/, "");
  if (!base) {
    return fallback;
  }
  const words = base.split(" ").slice(0, 10).join(" ");
  return words.length > 72 ? `${words.slice(0, 69)}...` : words;
}

function collectTags(text) {
  const normalized = normalizeString(text).toLowerCase();
  const matches = [];
  [
    ["excel", "excel"],
    ["spreadsheet", "spreadsheets"],
    ["dashboard", "dashboards"],
    ["report", "reporting"],
    ["template", "templates"],
    ["workflow", "workflow"],
    ["process", "process"],
    ["data", "data"],
    ["stakeholder", "stakeholders"],
    ["client", "client-facing"],
    ["team", "team-support"],
    ["manual", "manual-work"],
    ["automation", "automation"],
    ["error", "accuracy"],
  ].forEach(([pattern, tag]) => {
    if (normalized.includes(pattern)) {
      matches.push(tag);
    }
  });
  return normalizeStringList(matches);
}

function normalizeCategory(category) {
  const normalized = normalizeString(category);
  if (normalized === "tool_system_experience") {
    return "tool_system";
  }
  return CAREER_MEMORY_CATEGORY_META[normalized] ? normalized : "achievement";
}

function sourceLabel(source) {
  if (source === "uploaded_document") return "Uploaded document";
  if (source === "imported_profile") return "Imported profile";
  return "User-added";
}

function normalizeStructuredNotes(structuredNotes) {
  if (!structuredNotes || typeof structuredNotes !== "object") {
    return {};
  }
  const normalized = {};
  Object.entries(structuredNotes).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      const items = normalizeStringList(value);
      if (items.length) {
        normalized[key] = items;
      }
      return;
    }
    const text = normalizeString(value);
    if (text) {
      normalized[key] = text;
    }
  });
  return normalized;
}

function extractImpactText(cardLike) {
  const direct = normalizeString(cardLike?.structuredNotes?.impactEstimate);
  if (direct) {
    return direct;
  }
  const legacy = normalizeString(cardLike?.impactMetric);
  if (legacy) {
    return legacy;
  }
  const merged = [
    cardLike?.rawNote,
    cardLike?.cvBulletSuggestion,
    cardLike?.coverLetterAngle,
  ]
    .filter(Boolean)
    .join(" ");
  const match = merged.match(/[^.]*\d[^.]*/);
  return match ? normalizeString(match[0]) : "";
}

export function hasMetric(cardLike) {
  return Boolean(extractImpactText(cardLike)) || normalizeCategory(cardLike?.category) === "metric";
}

function deriveMissingDetails(card) {
  const notes = card.structuredNotes || {};
  const missing = [];
  if (!normalizeString(card.rawNote)) {
    missing.push("Add a rough note about what happened.");
  }
  if (!normalizeString(notes.change || notes.ownership)) {
    missing.push("Explain what you changed or owned.");
  }
  if (!normalizeString(notes.benefit)) {
    missing.push("Name who benefited from the work.");
  }
  if (!normalizeString(notes.outcome || notes.result_area || notes.reason)) {
    missing.push("Clarify what improved or why it mattered.");
  }
  if (!hasMetric(card) && !["motivation", "challenge"].includes(card.category)) {
    missing.push("Add a rough metric or measurable signal.");
  }
  if (card.category === "motivation" && !normalizeString(notes.interest_area)) {
    missing.push("Explain what type of company, mission, or problem interests you.");
  }
  return missing.slice(0, 4);
}

function deriveStatus(card) {
  const missingDetails = deriveMissingDetails(card);
  if (!missingDetails.length) {
    return "ready_for_tailoring";
  }
  if (
    missingDetails.length === 1 &&
    missingDetails[0] === "Add a rough metric or measurable signal."
  ) {
    return "needs_metric";
  }
  return "needs_detail";
}

function deriveConfidenceLabel(card) {
  if (card.source !== DEFAULT_SOURCE) {
    return sourceLabel(card.source);
  }
  if (card.status === "ready_for_tailoring") {
    return "User-added";
  }
  return "User-added";
}

export function normalizeCareerMemoryCard(card, index = 0) {
  const category = normalizeCategory(card?.category);
  const normalized = {
    id: normalizeString(card?.id) || createId(`memory_${index}`),
    title:
      normalizeString(card?.title) ||
      titleFromAnswers([card?.rawNote, card?.cvBulletSuggestion, card?.polishedCvBullet], `Career memory ${index + 1}`),
    category,
    source: normalizeString(card?.source) || DEFAULT_SOURCE,
    status: normalizeString(card?.status),
    rawNote: normalizeString(card?.rawNote),
    structuredNotes: normalizeStructuredNotes(card?.structuredNotes),
    cvBulletSuggestion: normalizeString(card?.cvBulletSuggestion || card?.polishedCvBullet),
    coverLetterAngle: normalizeString(card?.coverLetterAngle),
    tags: normalizeStringList(card?.tags),
    missingDetails: normalizeStringList(card?.missingDetails),
    confidenceLabel: normalizeString(card?.confidenceLabel),
    createdAt: normalizeString(card?.createdAt) || new Date().toISOString(),
    updatedAt: normalizeString(card?.updatedAt) || new Date().toISOString(),
    useInCv: card?.useInCv !== false,
    useInLetter: Boolean(card?.useInLetter),
  };
  if (!normalized.structuredNotes.impactEstimate) {
    const metric = extractImpactText(card);
    if (metric) {
      normalized.structuredNotes.impactEstimate = metric;
    }
  }
  if (!normalized.missingDetails.length) {
    normalized.missingDetails = deriveMissingDetails(normalized);
  }
  normalized.status =
    CAREER_MEMORY_STATUS_META[normalized.status] ? normalized.status : deriveStatus(normalized);
  if (!normalized.confidenceLabel) {
    normalized.confidenceLabel = deriveConfidenceLabel(normalized);
  }
  return normalized;
}

function buildLegacySeedCard(text, category, title) {
  const rawNote = normalizeString(text);
  if (!rawNote) {
    return null;
  }
  return normalizeCareerMemoryCard({
    title,
    category,
    source: "imported_profile",
    rawNote,
    structuredNotes: {
      change: firstSentence(rawNote),
    },
    cvBulletSuggestion: firstSentence(rawNote),
    coverLetterAngle: firstSentence(rawNote),
    tags: collectTags(rawNote),
  });
}

function seedCardsFromLegacyFields(draft) {
  return [
    buildLegacySeedCard(draft.achievementHighlights, "achievement", "Imported achievement notes"),
    buildLegacySeedCard(draft.additionalBulletBank, "project", "Imported bullet bank"),
    buildLegacySeedCard(
      draft.professionalHurdlesContext,
      "challenge",
      "Imported challenge context",
    ),
    buildLegacySeedCard(draft.motivationLetterNotes, "motivation", "Imported motivation notes"),
  ].filter(Boolean);
}

function mergeTextSections(sections) {
  return sections.map((section) => normalizeString(section)).filter(Boolean).join("\n\n");
}

function renderCardsForLegacyText(cards, { includeLetter = false } = {}) {
  return cards
    .map((card) => {
      const parts = [
        `${card.title} [${CAREER_MEMORY_CATEGORY_META[card.category]?.label || card.category}]`,
        card.rawNote,
        card.structuredNotes.impactEstimate
          ? `Impact estimate: ${card.structuredNotes.impactEstimate}`
          : "",
        card.cvBulletSuggestion ? `CV angle: ${card.cvBulletSuggestion}` : "",
        includeLetter && card.coverLetterAngle ? `Letter angle: ${card.coverLetterAngle}` : "",
      ].filter(Boolean);
      return parts.join("\n");
    })
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
      ? (documents.generatedMemoryCards || documents.generated_memory_cards).map(
          normalizeCareerMemoryCard,
        )
      : [],
  };
  if (!draft.generatedMemoryCards.length) {
    draft.generatedMemoryCards = seedCardsFromLegacyFields(draft);
  }
  return draft;
}

export function buildCareerMemoryPayload(draft) {
  const cards = (draft.generatedMemoryCards || []).map(normalizeCareerMemoryCard);
  const achievementCards = cards.filter((card) =>
    ["achievement", "project", "metric", "stakeholder_story", "tool_system"].includes(
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
      achievementCards
        .filter((card) => card.useInCv)
        .map((card) => card.cvBulletSuggestion)
        .filter(Boolean)
        .join("\n"),
    ]),
    professional_hurdles_text: mergeTextSections([
      draft.professionalHurdlesContext,
      renderCardsForLegacyText(challengeCards),
    ]),
    motivation_letter_notes: mergeTextSections([
      draft.motivationLetterNotes,
      renderCardsForLegacyText(motivationCards, { includeLetter: true }),
    ]),
    ai_canvas_source_asset_ids: normalizeStringList(draft.selectedAssetIds),
    generated_memory_cards: cards,
  };
}

export function getQuestionSetDefinition(questionSetType) {
  return (
    QUESTION_SET_DEFINITIONS[normalizeString(questionSetType)] ||
    QUESTION_SET_DEFINITIONS[DEFAULT_QUESTION_SET_TYPE]
  );
}

export function createInterviewState(questionSetType = DEFAULT_QUESTION_SET_TYPE) {
  const definition = getQuestionSetDefinition(questionSetType);
  return {
    activeQuestionSet: definition.id,
    currentStepIndex: 0,
    answers: {},
    selectedTrigger: definition.suggestedTrigger,
    draftMemoryCard: null,
    isReviewingDraft: false,
  };
}

export function getTriggerById(triggerId) {
  return (
    MEMORY_TRIGGER_CHIPS.find((trigger) => trigger.id === normalizeString(triggerId)) ||
    MEMORY_TRIGGER_CHIPS[0]
  );
}

function buildStructuredNotes(questionSetType, answers, selectedTrigger) {
  const definition = getQuestionSetDefinition(questionSetType);
  const structuredNotes = {
    questionSetType: definition.id,
    trigger: selectedTrigger || definition.suggestedTrigger,
  };
  definition.steps.forEach((step) => {
    const value = normalizeString(answers?.[step.id]);
    if (value) {
      structuredNotes[step.id] = value;
    }
  });
  const impact = normalizeString(answers?.impact);
  if (impact) {
    structuredNotes.impactEstimate = impact;
  }
  return structuredNotes;
}

function buildRawNote(questionSetType, structuredNotes) {
  const definition = getQuestionSetDefinition(questionSetType);
  return definition.steps
    .map((step) => {
      const answer = structuredNotes[step.id];
      return answer ? `${step.question} ${answer}` : "";
    })
    .filter(Boolean)
    .join("\n\n");
}

function buildCardTitle(questionSetType, structuredNotes, existingCount) {
  const trigger = getTriggerById(structuredNotes.trigger);
  const definition = getQuestionSetDefinition(questionSetType);
  const anchorValues = [
    structuredNotes.goal,
    structuredNotes.result_area,
    structuredNotes.before,
    structuredNotes.interest_area,
    structuredNotes.change,
  ];
  return titleFromAnswers(anchorValues, `${trigger.label} memory ${existingCount + 1 || 1}`);
}

function buildCvBulletSuggestion(questionSetType, structuredNotes) {
  const change = normalizeString(structuredNotes.change || structuredNotes.ownership);
  const benefit = normalizeString(structuredNotes.benefit);
  const outcome = normalizeString(structuredNotes.outcome || structuredNotes.result_area);
  const impact = normalizeString(structuredNotes.impactEstimate);
  const openers = {
    story_recovery: "Improved an inefficient workflow by",
    quantified_outcome: "Delivered a measurable improvement by",
    project_example: "Owned a project initiative that",
    stakeholder_story: "Aligned stakeholders to",
    motivation_notes: "Brings a clear motivation for work that",
  };
  const opener = openers[questionSetType] || "Delivered impact by";
  const segments = [
    change ? `${opener} ${change.toLowerCase()}` : opener,
    benefit ? `for ${benefit}` : "",
    outcome ? `which made work ${outcome.toLowerCase()}` : "",
    impact ? `and ${impact.toLowerCase()}` : "",
  ]
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  return segments ? `${segments}.` : "";
}

function buildCoverLetterAngle(questionSetType, structuredNotes) {
  const benefit = normalizeString(structuredNotes.benefit);
  const outcome = normalizeString(structuredNotes.outcome || structuredNotes.reason);
  const angleBySet = {
    story_recovery:
      "Use this story to show practical ownership and how you improve messy work without waiting for perfect conditions.",
    quantified_outcome:
      "Use this to prove impact with a concrete signal instead of a generic claim.",
    project_example:
      "Use this to show initiative, ownership, and the ability to move work across multiple steps.",
    stakeholder_story:
      "Use this to show communication range, trust-building, and how you reduce friction across people.",
    motivation_notes:
      "Use this to explain genuine interest and why your application is specific to this kind of work.",
  };
  const details = [benefit ? `Highlight who benefited: ${benefit}.` : "", outcome ? `Connect it to ${outcome}.` : ""]
    .filter(Boolean)
    .join(" ");
  return `${angleBySet[questionSetType] || ""} ${details}`.trim();
}

export function generateDraftMemoryCard({
  questionSetType = DEFAULT_QUESTION_SET_TYPE,
  answers = {},
  selectedTrigger = "",
  existingCount = 0,
}) {
  const definition = getQuestionSetDefinition(questionSetType);
  const trigger = getTriggerById(selectedTrigger || definition.suggestedTrigger);
  const structuredNotes = buildStructuredNotes(definition.id, answers, trigger.id);
  return normalizeCareerMemoryCard({
    id: createId("draft"),
    title: buildCardTitle(definition.id, structuredNotes, existingCount),
    category: trigger.category || definition.defaultCategory,
    source: DEFAULT_SOURCE,
    rawNote: buildRawNote(definition.id, structuredNotes),
    structuredNotes,
    cvBulletSuggestion: buildCvBulletSuggestion(definition.id, structuredNotes),
    coverLetterAngle: buildCoverLetterAngle(definition.id, structuredNotes),
    tags: normalizeStringList([...trigger.tags, ...collectTags(JSON.stringify(structuredNotes))]),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
}

export function createManualMemoryCard({ category = "achievement" } = {}) {
  return normalizeCareerMemoryCard({
    id: createId("manual"),
    title: `New ${CAREER_MEMORY_CATEGORY_META[normalizeCategory(category)]?.label || "memory"}`,
    category: normalizeCategory(category),
    source: DEFAULT_SOURCE,
    rawNote: "",
    structuredNotes: {},
    cvBulletSuggestion: "",
    coverLetterAngle: "",
    tags: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
}

export function getSourceSummary(draft, assetDocuments) {
  const documentsAvailable = assetDocuments.length;
  const selectedForTailoring = (draft.selectedAssetIds || []).length;
  const masterProfileLinked = Boolean(draft.masterProfileAssetId);
  return {
    documentsAvailable,
    selectedForTailoring,
    masterProfileLinked,
  };
}

export function buildTailoringChecklist(draft, assetDocuments = []) {
  const cards = (draft.generatedMemoryCards || []).map(normalizeCareerMemoryCard);
  const baselineConnected = assetDocuments.some(
    (item) => normalizeString(item.asset_kind).toLowerCase() === "workspace_cv",
  );
  const achievementStories = cards.filter((card) =>
    ["achievement", "project"].includes(card.category),
  ).length;
  const metrics = cards.filter((card) => hasMetric(card)).length;
  const projects = cards.filter((card) => card.category === "project").length;
  const motivation = cards.filter((card) => card.category === "motivation").length;
  const items = [
    {
      id: "baseline",
      label: "Baseline CV connected",
      complete: baselineConnected,
      progressLabel: baselineConnected ? "Connected" : "Missing",
    },
    {
      id: "achievement_stories",
      label: "Add 3 achievement stories",
      complete: achievementStories >= 3,
      progressLabel: `${achievementStories}/3`,
    },
    {
      id: "metrics",
      label: "Add 2 metrics",
      complete: metrics >= 2,
      progressLabel: `${metrics}/2`,
    },
    {
      id: "projects",
      label: "Add 1 project example",
      complete: projects >= 1,
      progressLabel: `${projects}/1`,
    },
    {
      id: "motivation",
      label: "Add motivation notes",
      complete: motivation >= 1 || normalizeString(draft.motivationLetterNotes).length >= 60,
      progressLabel:
        motivation >= 1 || normalizeString(draft.motivationLetterNotes).length >= 60
          ? "Added"
          : "Missing",
    },
  ];
  const completedCount = items.filter((item) => item.complete).length;
  const level = !baselineConnected
    ? "Basic"
    : completedCount >= 4
      ? "Strong"
      : completedCount >= 2
        ? "Improving"
        : "Basic";
  const summary = baselineConnected
    ? "Basic tailoring is ready because a baseline CV is connected."
    : "Upload a baseline CV in Asset Library to unlock tailoring.";
  return {
    items,
    completedCount,
    totalCount: items.length,
    level,
    summary,
    missingCount: items.filter((item) => !item.complete).length,
  };
}

export function getTopStatusBarItems(draft, assetDocuments = []) {
  const checklist = buildTailoringChecklist(draft, assetDocuments);
  return [
    {
      id: "documents",
      label: "Documents",
      value: `${assetDocuments.length} connected`,
    },
    {
      id: "memories",
      label: "Memories",
      value: `${(draft.generatedMemoryCards || []).length} saved`,
    },
    {
      id: "tailoring_level",
      label: "Tailoring level",
      value: checklist.level,
    },
    {
      id: "missing",
      label: "Missing",
      value: `${checklist.missingCount} items`,
    },
  ];
}

export function getNextBestActions(draft, assetDocuments = []) {
  const checklist = buildTailoringChecklist(draft, assetDocuments);
  const items = [
    {
      id: "metrics",
      label: "Add quantified outcome",
      reason: "Numbers make tailored CV bullets and answers more credible.",
      progress: checklist.items.find((item) => item.id === "metrics")?.progressLabel || "0/2",
      questionSetType: "quantified_outcome",
    },
    {
      id: "projects",
      label: "Add project example",
      reason: "Project examples help Runr swap in stronger evidence for different roles.",
      progress: checklist.items.find((item) => item.id === "projects")?.progressLabel || "0/1",
      questionSetType: "project_example",
    },
    {
      id: "stakeholder",
      label: "Add stakeholder or leadership story",
      reason: "Stakeholder stories strengthen cover letters, outreach, and interviews.",
      progress: `${
        (draft.generatedMemoryCards || []).filter((card) => card.category === "stakeholder_story").length
      }/1`,
      questionSetType: "stakeholder_story",
    },
    {
      id: "motivation",
      label: "Add motivation notes",
      reason: "Specific motivation makes applications feel intentional rather than generic.",
      progress: checklist.items.find((item) => item.id === "motivation")?.progressLabel || "Missing",
      questionSetType: "motivation_notes",
    },
  ];
  return items;
}

export function sortMemoryCards(cards = []) {
  return [...cards].sort((left, right) =>
    String(right.updatedAt || right.createdAt || "").localeCompare(
      String(left.updatedAt || left.createdAt || ""),
    ),
  );
}

export function filterMemoryCards(cards = [], query = "", filterId = "all") {
  const normalizedQuery = normalizeString(query).toLowerCase();
  return sortMemoryCards(cards).filter((cardLike) => {
    const card = normalizeCareerMemoryCard(cardLike);
    const matchesQuery =
      !normalizedQuery ||
      [
        card.title,
        card.rawNote,
        card.cvBulletSuggestion,
        card.coverLetterAngle,
        card.tags.join(" "),
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);
    if (!matchesQuery) {
      return false;
    }
    if (filterId === "all") {
      return true;
    }
    if (CAREER_MEMORY_CATEGORY_META[filterId]) {
      return card.category === filterId;
    }
    if (CAREER_MEMORY_STATUS_META[filterId]) {
      return card.status === filterId;
    }
    return true;
  });
}

export function getLatestMemoryCard(cards = []) {
  return sortMemoryCards(cards)[0] || null;
}

export function updateCardCollection(cards = [], cardId, updates) {
  return cards.map((cardLike) =>
    cardLike.id === cardId
      ? normalizeCareerMemoryCard({
          ...cardLike,
          ...updates,
          updatedAt: new Date().toISOString(),
        })
      : cardLike,
  );
}

export function getStatusLabel(status) {
  return CAREER_MEMORY_STATUS_META[status]?.label || "Needs detail";
}

export function getCategoryLabel(category) {
  return CAREER_MEMORY_CATEGORY_META[normalizeCategory(category)]?.label || "Achievement";
}

export function getQuestionStepAnswer(answers, stepId) {
  return normalizeString(answers?.[stepId]);
}

export function createDraftReviewWarnings(card) {
  return normalizeCareerMemoryCard(card).missingDetails;
}

export function getSourceLabel(source) {
  return sourceLabel(source);
}


export const userProfile = {
  name: "Elena Rostova",
  role: "Senior Product Designer",
  email: "elena.rostova@example.com",
  location: "San Francisco, CA",
  website: "portfolio.rostova.design",
  avatar:
    "https://lh3.googleusercontent.com/aida-public/AB6AXuCEbDDRgu4_REnkpR4gbSify0khawEFxHuQHLBm7Xbd6BmM7LDM-dlp8wOKL0QkSDuiFg7g9UDpYPZnV2uV8Qmu5cxn1MBriXeVmXUz8EGMsgieO36lJEpcY5FCDph2ooQGzwpKRq5qwQluOCY4JB_gfySIUY2T0ozlVp3DEmdnT9aCfADFkC1BXeteFPTxYhtUsABzZLWUOD6fNpuVFVFLjuxpQaEgkpVd_bvuz61H_FfJkq5V_4CESVQjz3tEa3rwtGfzcKHXwJE",
};

export const shellUser = {
  name: "Alex Mercer",
  subtitle: "alex@runr.com",
  avatar:
    "https://lh3.googleusercontent.com/aida-public/AB6AXuDeh_GwQ1tyaiUiDvT71g8HFsHEJ5gVS679pFkoWXtNfLFzoFMzeRd4HMomF0XAuq8mfaec3nzeharFzxat1NNtR0s1NGQ8OmsZwjVfuKfX6PFUGr0duTgyC5ItHvMrLbUKmVICPFeD-iyiVRX9E4uWBHxGmGTQWtgvLOpUORp77hhc30XrStvTwhM64ft7fw0EhK8zMcSjQubBgd6isZ-HmuKrN7-OkTq3cDe4ub5eT-F6nWziFtgteycj_e7n3xQafjsJUdJbHiU",
};

export const settingsTabs = [
  "Profile",
  "Defaults",
  "Documents",
  "Review Preferences",
  "Account",
];

export const competencies = [
  "Design Systems",
  "Prototyping",
  "User Research",
  "Figma",
  "HTML/CSS",
  "Agile Methodology",
];

export const experiences = [
  { title: "Senior Product Designer", company: "TechFlow Inc.", period: "2020 - Present" },
  { title: "UX Designer", company: "Creative Synergies", period: "2017 - 2020" },
];

export const stageTimeline = [
  {
    name: "Acquire Jobs",
    description: "Scraped data from 3 primary sources.",
    time: "14:32:00",
    duration: "2m 14s",
    type: "success",
    metrics: [
      { label: "Jobs Found", value: "1,240" },
      { label: "Sources", value: "3" },
    ],
  },
  {
    name: "Enrich",
    description: "Appended company data and salary estimates.",
    time: "14:34:14",
    duration: "12m 05s",
    type: "success",
    metrics: [
      { label: "Enriched", value: "1,198" },
      { label: "API Calls", value: "3.5k" },
    ],
  },
  {
    name: "Filter & Rank",
    description: "Applied ML models for relevance scoring.",
    time: "14:46:19",
    duration: "18m 30s",
    type: "warning",
    warning:
      "Warning: 42 items skipped due to missing critical fields during ranking calculation. Proceeded with remainder.",
    metrics: [
      { label: "Retained", value: "450" },
      { label: "Avg Score", value: "84.2" },
    ],
  },
  {
    name: "Generate & Export",
    description: "Created final summaries and pushed to DB.",
    time: "15:04:49",
    duration: "12m 23s",
    type: "success",
    metrics: [],
  },
];

export const runArtifacts = [
  { name: "final_results.csv", description: "4.2 MB • 450 rows", icon: "description" },
  { name: "enrichment_logs.json", description: "1.1 MB", icon: "data_object" },
  { name: "run_report.pdf", description: "856 KB", icon: "assessment" },
];

export const systemMetrics = [
  { label: "Peak Memory", value: "4.2", unit: "GB" },
  { label: "Compute Cost", value: "$1.42" },
];

export const reviewRows = [
  {
    title: "Senior Frontend Engineer",
    company: "TechNova Solutions",
    workspace: "Engineering Q3",
    run: "Run #4092",
    source: "LinkedIn",
    status: "Waiting Review",
    artifactStatus: "Artifact Ready",
  },
  {
    title: "Director of Product Marketing",
    company: "Stellar Dynamics",
    workspace: "Marketing Execs",
    run: "Run #4088",
    source: "Company Site",
    status: "Waiting Review",
    artifactStatus: "Artifact Ready",
  },
];

export const placeholderCards = {
  Dashboard: [
    { label: "Queued Runs", value: "6" },
    { label: "Running Workers", value: "2" },
    { label: "Jobs Awaiting Review", value: "18" },
  ],
  Workspaces: [
    { label: "Active Workspaces", value: "4" },
    { label: "Enabled Sources", value: "7" },
    { label: "Prompt Families", value: "3" },
  ],
  Artifacts: [
    { label: "Generated Files", value: "1,284" },
    { label: "Tracker Exports", value: "38" },
    { label: "Pending Downloads", value: "12" },
  ],
  Admin: [
    { label: "Users", value: "9" },
    { label: "Active Tokens", value: "14" },
    { label: "Workspace Templates", value: "4" },
  ],
};

export const dashboardCards = [
  { label: "Queued Runs", value: "6" },
  { label: "Running Workers", value: "2" },
  { label: "Jobs Waiting Review", value: "18" },
  { label: "Completed Today", value: "11" },
];

export const dashboardRuns = [
  { id: "Run-1042B", workspace: "Alpha", status: "Completed", stage: "Exported", attempts: "1/2" },
  { id: "Run-1043C", workspace: "Blue Collar DE", status: "Running", stage: "Classify", attempts: "1/1" },
  { id: "Run-1038A", workspace: "Manual URLs", status: "Queued", stage: "Waiting", attempts: "0/1" },
];

export const workspaces = [
  {
    name: "White-Collar LinkedIn",
    type: "white_collar",
    description: "LinkedIn discovery with enrichment, filtering, ranking, and document generation.",
    profile: "Professional CV v3",
    promptFamily: "white_collar_default",
    sources: ["LinkedIn Search"],
  },
  {
    name: "White-Collar Manual URLs",
    type: "manual_url",
    description: "Manual URL ingestion with filtering bypass and direct document production.",
    profile: "Professional CV v3",
    promptFamily: "manual_curated",
    sources: ["Manual URLs"],
  },
  {
    name: "Blue-Collar Germany",
    type: "blue_collar",
    description: "Multi-portal blue-collar acquisition with role classification and packaging.",
    profile: "Blue Collar Baseline",
    promptFamily: "blue_collar_default",
    sources: ["Indeed", "LinkedIn", "StepStone"],
  },
];

export const artifactLibrary = [
  {
    name: "frontend_engineer_cv.pdf",
    type: "PDF",
    job: "Senior Frontend Engineer",
    company: "TechNova Solutions",
    workspace: "Engineering Q3",
    run: "Run-1042B",
    createdAt: "Apr 17, 2026 13:04",
    status: "Approved",
  },
  {
    name: "marketing_director_cv.docx",
    type: "DOCX",
    job: "Director of Product Marketing",
    company: "Stellar Dynamics",
    workspace: "Marketing Execs",
    run: "Run-1041A",
    createdAt: "Apr 17, 2026 12:18",
    status: "Waiting Review",
  },
  {
    name: "run_1042_tracker.xlsx",
    type: "XLSX",
    job: "Tracker Export",
    company: "Multiple",
    workspace: "Engineering Q3",
    run: "Run-1042B",
    createdAt: "Apr 17, 2026 13:06",
    status: "Ready",
  },
];

export const adminCollections = {
  users: [
    { name: "Alex Mercer", email: "alex@runr.com", role: "admin", workspaces: "All", status: "Active" },
    { name: "Elena Rostova", email: "elena@example.com", role: "editor", workspaces: "Design, Marketing", status: "Active" },
  ],
  tokens: [
    { name: "bootstrap-admin", owner: "Alex Mercer", scopes: "admin", lastUsed: "2m ago", status: "Active" },
    { name: "review-bot", owner: "Elena Rostova", scopes: "runs:read, reviews:write", lastUsed: "1h ago", status: "Active" },
  ],
  secrets: [
    { name: "openai_api_key", provider: "stored", scope: "global", valueState: "Value present" },
    { name: "scrapeops_api_key", provider: "env", scope: "white_collar_linkedin", valueState: "ENV backed" },
  ],
  templates: [
    { name: "white_collar_linkedin_v1", stages: "4", defaultMode: "queued" },
    { name: "blue_collar_default_v1", stages: "5", defaultMode: "queued" },
  ],
  workers: [
    { id: "worker_service_a", status: "running", currentRun: "Run-1043C", heartbeat: "just now" },
    { id: "worker_service_b", status: "idle", currentRun: "-", heartbeat: "14s ago" },
  ],
};

const masterCvFixture = {
  profile: {
    name: "Ahmed Kaddah",
    headline: "Product Manager",
    location: "Berlin, Germany",
    email: "ahmed@email.com",
    linkedin: "linkedin.com/in/ahmedkaddah",
  },
  status: {
    depth: 78,
    extraEvidenceCount: 12,
    experienceCount: 4,
  },
  sections: [
    {
      id: "experience",
      label: "Experience",
      entries: [
        {
          id: "northstar-senior-pm",
          kind: "work",
          title: "Senior Product Manager",
          organisation: "Northstar Labs · Berlin",
          dates: "2023 — Present",
          bullets: [
            {
              id: "northstar-onboarding",
              text: "Led the redesign of the candidate onboarding journey across product, design and engineering, reducing time-to-first-application by 34%.",
              score: 92,
              metric: "34% faster activation",
            },
            {
              id: "northstar-insights",
              text: "Built a weekly customer-insight practice with Sales and Support that shaped three roadmap priorities and improved trial conversion.",
              score: 81,
            },
            {
              id: "northstar-workshops",
              text: "Facilitated discovery workshops with enterprise customers across Germany and the Netherlands.",
              score: 67,
              extra: true,
            },
          ],
        },
        {
          id: "orbit-pm",
          kind: "work",
          title: "Product Manager",
          organisation: "Orbit Digital · Hamburg",
          dates: "2020 — 2023",
          collapsed: true,
          bullets: [
            {
              id: "orbit-platform",
              text: "Owned the platform roadmap across design, engineering and operations, taking two workflow improvements from discovery to launch.",
              score: 86,
            },
            {
              id: "orbit-enablement",
              text: "Created a qualitative customer feedback loop that helped the team prioritise a clearer self-serve setup experience.",
              score: 78,
            },
            {
              id: "orbit-research",
              text: "Partnered with account teams on research interviews that clarified the needs of growing digital businesses.",
              score: 72,
              extra: true,
            },
            {
              id: "orbit-mentoring",
              text: "Mentored two associate product managers through their first discovery and delivery cycles.",
              score: 74,
              extra: true,
            },
          ],
        },
      ],
    },
    {
      id: "projects",
      label: "Projects",
      entries: [
        {
          id: "talent-marketplace",
          kind: "project",
          title: "Internal Talent Marketplace",
          organisation: "Northstar Labs · Product lead",
          dates: "2024",
          bullets: [
            {
              id: "talent-prototype",
              text: "Designed and launched an internal opportunity-matching prototype, synthesising 28 interviews into a testable product direction in four weeks.",
              score: 88,
            },
            {
              id: "talent-sponsorship",
              text: "Presented the business case to senior leadership and secured sponsorship for a six-month pilot.",
              score: 74,
              extra: true,
            },
          ],
        },
      ],
    },
  ],
};

export function createMasterCvFixture() {
  return JSON.parse(JSON.stringify(masterCvFixture));
}

export default masterCvFixture;

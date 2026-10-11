// Anonymized, curated example. Never substituted for a customer's uploaded CV.
export const SAMPLE_JOB = {
  id: 'cv-strategy-sample-v1', version: '1', title: 'Associate, Corporate Strategy', company: 'Nutanix',
  years: 1, experienceNote: '1–3 years overall; 1+ year in strategy consulting, investment banking, private equity OR corporate strategy. Specialized duration needs confirmation.',
  industries: ['Information technology', 'Enterprise software', 'AI infrastructure', 'Data center', 'Virtualization'],
  roleTerms: ['strategy', 'business transformation', 'strategic planning'],
  priorities: ['strategic planning', 'business insights', 'stakeholder', 'operational'],
  keywords: [
    { label: 'Corporate strategy', aliases: [], source: '1+ year in strategy consulting, investment banking, private equity or corporate strategy. Confirm specific corporate-strategy experience before adding this term.' },
    { label: 'Strategy consulting', aliases: [], source: 'Alternative strategy or finance experience.', evidence: 'Delivered AI and cloud consulting through use case analysis and solution design.', section: 'experience', entry: 0 },
    { label: 'Investment banking', aliases: [], source: 'One of the alternative backgrounds; not required alongside strategy.' },
    { label: 'Private equity', aliases: [], source: 'One of the alternative backgrounds; not required alongside strategy.' },
    { label: 'Enterprise software / SaaS', aliases: ['enterprise software', 'SaaS'], source: 'Strong focus on enterprise software / SaaS preferred.', evidence: 'Developed market positioning and client acquisition strategy for an ERP consulting partner.', section: 'projects', entry: 1 },
    { label: 'Strategic thinking', aliases: [], source: 'Strategic thinker with problem-solving and analytical skills.', evidence: 'Designed market positioning and business development strategies.', section: 'projects', entry: 1 },
  ],
};

export const SAMPLE_CV = {
  name: 'Alex Morgan', headline: 'Business Transformation & AI Specialist', location: 'Munich, Germany', email: 'alex@example.com', phone: '', linkedin_url: '', website: '',
  summary: 'Business Transformation & AI Specialist with experience in IT strategy, AI adoption, and process optimization. Skilled in aligning business needs with technical solutions to deliver measurable results in digital transformation and SDLC optimization.',
  experience: [
    { company: 'Technology Services Group', title: 'Technology Transformation and Strategy Consultant', period: 'May 2025 - Sep 2025', bullets: [
      'Contributed to an AI initiative, embedding AI across the SDLC to drive measurable productivity gains.',
      'Delivered AI and cloud consulting through use case analysis and solution design.',
      'Assisted in data strategy for migration and transition projects, integrating business units into future cloud platforms.',
      'Designed an Enterprise Architecture Operating Model to standardize architecture data, improving stakeholder alignment.',
    ] },
    { company: 'Insurance Group', title: 'GenAI Associate for Business Transformation', period: 'Nov 2024 - Apr 2025', bullets: [
      'Conducted AI business analysis and stakeholder consultations to identify automation use cases.',
      'Co-developed and evaluated Proof-of-Concept AI tools, measuring impact through automated KPI assessments.',
      'Designed Agentic AI MVPs for project management and process optimization.',
      'Built an AI-driven Jira enhancement tool, bridging business requirements with implementation.',
    ] },
    { company: 'Shared Mobility GmbH', title: 'Contractor', period: 'Dec 2023 - Jul 2024', bullets: [
      'Managed shared e-scooter operations across 7 cities in Germany, overseeing a fleet of 1,600+ vehicles.',
      'Recruited, trained, and managed a team of 15 ground operators.',
      'Secured financing for 7 transporter vehicles without traditional bank support.',
      'Developed operational strategies projecting a 5% increase in revenue and efficiency.',
    ] },
    { company: 'Urban Mobility GmbH', title: 'Operations Lead and Co-Founder', period: 'Dec 2020 - Oct 2024', bullets: [
      'Directed operations in Freiburg, managing teams and coordinating with city authorities and thousands of customers.',
      'Negotiated business development agreements with 5 partners.',
      'Pitched mobility solutions for 50 major European capitals, increasing parking utilization by 4x.',
      'Reduced operational costs by 50% while increasing revenue by 25%.',
      'Achieved #1 Fastest Action Time and #1 Customer Satisfaction in the city.',
    ] },
  ],
  projects: [
    { title: 'AI-Driven Job Application Automation Pipeline', company: '', period: '2026', bullets: ['Designed an end-to-end automation system for job discovery, screening, and document generation.', 'Automated referral discovery, CV personalization and document enrichment.', 'Integrated semantic AI evaluation to assess profile-job fit.', 'Developed modular orchestration with configurable settings and checkpoint-based execution.'] },
    { title: 'ERP Growth Strategy for an Implementation Partner', company: '', period: '2026', bullets: ['Developed market positioning and client acquisition strategy for an ERP consulting partner.', 'Designed niche-based differentiation aligned with partner tier dynamics and lead distribution.', 'Structured a revenue model covering implementation margins, custom development, and recurring support.', 'Built a client acquisition framework combining consultative selling and content positioning.'] },
    { title: 'AI-Powered Learning Platform', company: '', period: '2025', bullets: ['Conceived an AI-enabled platform transforming video content into interactive learning workflows.', 'Defined product vision, target users, MVP scope, and feature prioritization.', 'Designed user journeys integrating video, transcripts, and contextual explanations.', 'Conducted market and competitor analysis.', 'Collaborated with engineering on feasibility and iterative development.'] },
    { title: 'Heated Razor Innovation', company: 'Consumer Product Venture', period: 'Oct 2023 - Feb 2024', bullets: ['Led the development and business concept of a heated razor with replaceable blades, pitching to five established German entrepreneurs.'] },
    { title: 'Open Innovation Challenge — 1st Place', company: 'Consumer Brand', period: 'Apr 2023 - Jul 2023', bullets: ['Won first place among 12 university teams by developing a product strategy, financial plan, marketing strategy, and go-to-market roadmap.'] },
    { title: 'E-Commerce Growth Strategy', company: 'Retail Platform', period: 'Apr 2023 - Jul 2023', bullets: ['Tested three MVPs and developed strategic recommendations and digital tutorials to strengthen e-commerce positioning and vendor performance.'] },
  ],
  skills: ['Office 365', 'Azure', 'Celonis', 'Jira', 'Confluence', 'Power BI', 'Miro', 'SDLC', 'API Integration', 'GenAI Tools', 'Project Management', 'Agile/Scrum', 'Product Lifecycle', 'Requirements Engineering', 'Process Improvement', 'Data Analysis', 'Strategic Planning', 'Stakeholder Management', 'Business Model Design'],
  education: [{ title: 'M.A., Entrepreneurship and Innovation', company: 'University in Bavaria', period: '', bullets: [] }, { title: 'B.Sc., Business Administration and Management', company: 'European University', period: '', bullets: [] }],
  languages: ['Arabic (Native)', 'English (C1)', 'German (B1/B2)'],
  custom: [], order: ['summary', 'experience', 'projects', 'skills', 'education', 'languages'],
};

export const SAMPLE_ENHANCEMENTS = {
  summary: 'Business transformation and strategy professional with experience in AI adoption, strategic planning and operational improvement. Turned use-case analysis into business insights, designed operating models and strengthened stakeholder alignment. As an operations co-founder, reduced costs by 50% and increased revenue by 25%.',
  experience: [
    [
      'Embedded AI across the SDLC to support productivity and operational efficiency.',
      'Delivered AI and cloud consulting through use-case analysis and solution design, translating business needs into technology recommendations.',
      'Supported data strategy for migration and transition projects, aligning business units with future cloud platforms.',
      'Designed an Enterprise Architecture Operating Model to standardize architecture data and strengthen stakeholder alignment.',
    ],
    ['Identified automation opportunities through AI business analysis and stakeholder consultations.', 'Co-developed and evaluated AI proofs of concept using automated KPI assessments.', 'Designed agentic AI MVPs for project management and process optimization.', 'Built an AI-driven Jira enhancement tool connecting business requirements with implementation.'],
    ['Oversaw a 1,600+ vehicle fleet across 7 German cities.', 'Recruited, trained and managed 15 ground operators.', 'Secured financing for 7 transporter vehicles without traditional bank support.', 'Developed operational strategies projecting a 5% improvement in revenue and efficiency.'],
    ['Led operations in Freiburg, coordinating teams, city authorities and thousands of customers.', 'Negotiated business development agreements with 5 partners.', 'Pitched mobility solutions for 50 European capitals and increased parking utilization fourfold.', 'Cut operational costs by 50% and increased revenue by 25%.', 'Achieved the city’s #1 Fastest Action Time and #1 Customer Satisfaction.'],
  ],
  projects: [
    'Designed an end-to-end job application system spanning discovery, screening and document generation.',
    'Developed market positioning and a client acquisition strategy for an ERP consulting partner, connecting differentiation with implementation and recurring support revenue.',
    'Defined the vision and MVP for an AI learning platform, using market and competitor analysis to prioritize interactive learning workflows.',
    'Led the product concept and development of a heated razor with replaceable blades; pitched to five German entrepreneurs.',
    'Won first place among 12 teams with an integrated product, financial, marketing and go-to-market strategy.',
    'Tested three MVPs and translated findings into strategic recommendations and digital tutorials for e-commerce growth.',
  ],
};

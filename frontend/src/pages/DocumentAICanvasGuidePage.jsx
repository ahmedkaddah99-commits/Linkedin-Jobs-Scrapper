import { Link } from "react-router-dom";

const steps = [
  {
    title: "Upload reusable source files in Career Assets",
    body: "Start with the files you already own: your baseline CV, old CV versions, certifications, recommendation letters, project summaries, or other supporting documents.",
    path: "Career Assets > Asset Library",
  },
  {
    title: "Add your detailed CV as the Master Career Profile",
    body: "Upload the long-form version of your career history so Runr can see the bullet points, projects, and context that do not fit in a short application CV.",
    path: "Career Assets > Career Memory Builder > Upload Detailed CV",
  },
  {
    title: "Select which assets AI is allowed to use",
    body: "Choose the specific uploaded files that can support tailoring when a workspace is set to use selected assets.",
    path: "Career Memory Builder > Source documents",
  },
  {
    title: "Fill in wins, extra bullets, and career context",
    body: "Use the Achievement Bank and Story & Letter Notes to capture quantified results, alternate bullet points, transitions, and motivation-letter material.",
    path: "Career Memory Builder > Achievement Bank + Motivation & Story Bank",
  },
  {
    title: "Set the workspace Personalization Scope",
    body: "Each workspace decides whether it should use only the baseline CV, selected assets, or the full career profile.",
    path: "Workspaces > Personalization Scope",
  },
  {
    title: "Generate documents with broader evidence",
    body: "When tailoring runs, Runr can swap in stronger bullet points and more relevant supporting details instead of being limited to the short baseline CV.",
    path: "Workspace runs > tailored CVs and letters",
  },
];

const sourceTypes = [
  [
    "Baseline CVs",
    "The short CVs you already send today. These remain the default source when you want stricter control.",
  ],
  [
    "Master Career Profile",
    "Your detailed CV or long-form career document. Use it for extra bullet points, full project history, and richer context.",
  ],
  [
    "Certifications and licenses",
    "Useful when a role has hard requirements or when you want the AI to surface relevant credentials quickly.",
  ],
  [
    "Recommendation letters",
    "Helpful for extracting themes about leadership, collaboration, trust, or client impact.",
  ],
  [
    "Achievement bank entries",
    "Alternate bullets, quantified wins, and role-specific outcomes that should not be lost just because they did not fit on a one-page CV.",
  ],
  [
    "Story and motivation notes",
    "Career pivots, difficult situations, and reasons you care about certain industries or missions. This is especially useful for motivation letters.",
  ],
];

const scopes = [
  [
    "Baseline CV only",
    "Use this when you want the safest, most constrained behavior or when the broader profile is not ready yet.",
  ],
  [
    "Baseline + selected assets",
    "Recommended default. Use this when you want the AI to consult chosen certifications, letters, or supporting files without opening the entire career profile.",
  ],
  [
    "Full career profile",
    "Use this when your Master Career Profile and notes are complete and you want maximum tailoring across different job types.",
  ],
];

const useCases = [
  "Replace weaker job bullets with stronger bullets from your detailed career history when they fit the target role better.",
  "Surface certifications or recommendation evidence for applications that have strict requirements or credibility gaps.",
  "Write more personal motivation letters from reusable notes instead of starting from a blank page every time.",
  "Support different CV variants across roles without maintaining a separate short CV for every direction you might apply to.",
];

export default function DocumentAICanvasGuidePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <Link
          className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-container"
          to="/career-evidence"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          Back to Career Memory Builder
        </Link>
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          Career Memory Guide
        </div>
        <h1 className="mt-4 font-headline text-[2.5rem] font-extrabold leading-tight tracking-tight text-on-surface">
          Turn documents plus extra career memories into a stronger tailoring base
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-on-surface-variant">
          Career Memory Builder lets Runr tailor CVs and letters from more than one short baseline
          CV. You upload source evidence, add the context documents miss, and let each workspace
          decide how much of that material it is allowed to use.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          ["Grounded personalization", "Career Memory should be fed with real documents and factual notes, not guessed claims."],
          ["Multiple CV directions", "Use it when one baseline CV is too narrow for the range of roles you want to target."],
          ["Workspace control", "Every workspace still decides whether to use only the baseline CV, selected assets, or the full profile."],
        ].map(([title, body]) => (
          <div
            className="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-5"
            key={title}
          >
            <h2 className="text-sm font-semibold text-on-surface">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">{body}</p>
          </div>
        ))}
      </section>

      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
        <h2 className="font-headline text-2xl font-bold text-on-surface">Step by step</h2>
        <div className="mt-6 space-y-4">
          {steps.map((step, index) => (
            <div
              className="grid gap-4 rounded-2xl border border-outline-variant/10 bg-surface p-5 md:grid-cols-[44px_1fr]"
              key={step.title}
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
                {index + 1}
              </div>
              <div>
                <h3 className="text-base font-semibold text-on-surface">{step.title}</h3>
                <p className="mt-1 text-sm leading-6 text-on-surface-variant">{step.body}</p>
                <div className="mt-3 rounded-xl bg-surface-container-low px-3 py-2 text-xs font-medium text-on-surface-variant">
                  {step.path}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h2 className="font-headline text-xl font-bold text-on-surface">What to add to Career Memory</h2>
          <div className="mt-4 space-y-4">
            {sourceTypes.map(([title, body]) => (
              <div className="rounded-2xl border border-outline-variant/10 bg-surface p-4" key={title}>
                <h3 className="text-sm font-semibold text-on-surface">{title}</h3>
                <p className="mt-1 text-sm leading-6 text-on-surface-variant">{body}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
            <h2 className="font-headline text-xl font-bold text-on-surface">Best use cases</h2>
            <div className="mt-4 space-y-3">
              {useCases.map((item) => (
                <div
                  className="rounded-2xl border border-outline-variant/10 bg-surface px-4 py-3 text-sm leading-6 text-on-surface-variant"
                  key={item}
                >
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
            <h2 className="font-headline text-xl font-bold text-on-surface">
              When each personalization scope makes sense
            </h2>
            <div className="mt-4 space-y-4">
              {scopes.map(([title, body]) => (
                <div className="rounded-2xl border border-outline-variant/10 bg-surface p-4" key={title}>
                  <h3 className="text-sm font-semibold text-on-surface">{title}</h3>
                  <p className="mt-1 text-sm leading-6 text-on-surface-variant">{body}</p>
                </div>
              ))}
            </div>
            <Link
              className="mt-5 inline-flex items-center gap-2 rounded bg-primary px-4 py-2.5 text-sm font-medium text-white hover:opacity-90"
              to="/workspaces?focus=documents"
            >
              Review workspace personalization
              <span className="material-symbols-outlined text-[16px]">tune</span>
            </Link>
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
        <h2 className="font-headline text-xl font-bold text-on-surface">Important constraint</h2>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-on-surface-variant">
          Career Memory is most valuable when every claim can be traced back to a real document, a
          real bullet point, or a factual note you provided. It should expand what Runr can reuse,
          not encourage invented experience.
        </p>
        <Link
          className="mt-5 inline-flex items-center gap-2 rounded bg-primary px-4 py-2.5 text-sm font-medium text-white hover:opacity-90"
          to="/career-evidence"
        >
          Open Career Memory Builder
          <span className="material-symbols-outlined text-[16px]">dashboard_customize</span>
        </Link>
      </section>
    </div>
  );
}

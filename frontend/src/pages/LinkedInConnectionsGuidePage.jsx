import { Link } from "react-router-dom";

const steps = [
  {
    title: "Open LinkedIn on desktop",
    body: "Sign in to LinkedIn in the same browser where you use Runr.",
    path: "LinkedIn > Sign in",
  },
  {
    title: "Open your LinkedIn connections",
    body: "The recommended path is to stay signed in to LinkedIn and leave your connections page open while you sync from Runr.",
    path: "LinkedIn > My Network > Connections",
  },
  {
    title: "Install the Runr extension",
    body: "Runr uses the extension only after you click Sync network. Your LinkedIn credentials never leave the browser.",
    path: "Runr Referrals > LinkedIn Connections > Install extension",
  },
  {
    title: "Sync your network",
    body: "Return to the Referrals page and click Sync network. Runr imports the visible connections and updates your referral matches automatically.",
    path: "Runr > Referrals > LinkedIn Connections > Sync network",
  },
];

const acceptedColumns = [
  "First Name",
  "Last Name",
  "URL",
  "Email Address",
  "Company",
  "Position",
  "Connected On",
];

export default function LinkedInConnectionsGuidePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <Link
          className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-container"
          to="/referrals"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          Back to Referrals
        </Link>
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          LinkedIn connection sync guide
        </div>
        <h1 className="mt-4 font-headline text-[2.5rem] font-extrabold leading-tight tracking-tight text-on-surface">
          Sync your LinkedIn connections for referral matching
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-on-surface-variant">
          Keep LinkedIn open in the same browser, install the Runr extension, and sync your network
          directly. Runr uses company names to show possible referral contacts on matching jobs.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          ["Your login stays private", "Runr reads the open LinkedIn tab through the extension."],
          ["No manual cleanup", "Runr normalizes the connection data before matching."],
          ["Current source of truth", "Each sync updates, adds, and removes old LinkedIn contacts."],
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
          <h2 className="font-headline text-xl font-bold text-on-surface">What Runr imports</h2>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">
            The sync accepts normal LinkedIn connection data, including missing emails, commas in
            names, special characters, profile URLs, job titles, and connected dates. A Connections.csv
            export remains available as a fallback on the Referrals page.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {acceptedColumns.map((column) => (
              <span
                className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary"
                key={column}
              >
                {column}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h2 className="font-headline text-xl font-bold text-on-surface">How referral matching works</h2>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">
            Runr first checks exact company matches, then safe close matches. For example, Stripe can
            match Stripe Inc. or Stripe Payments Europe. It avoids risky substring matches like Meta
            matching Metabolic Health GmbH.
          </p>
          <Link
            className="mt-5 inline-flex items-center gap-2 rounded bg-primary px-4 py-2.5 text-sm font-medium text-white hover:opacity-90"
            to="/referrals"
          >
            Open LinkedIn Connections
            <span className="material-symbols-outlined text-[16px]">sync</span>
          </Link>
        </div>
      </section>
    </div>
  );
}

import { SignIn, SignUp } from "@clerk/clerk-react";

const clerkAppearance = {
  elements: {
    card: "shadow-none border border-outline-variant/20 rounded-[2rem] bg-surface-container-lowest",
    headerTitle: "font-headline text-3xl font-extrabold tracking-tight text-on-surface",
    headerSubtitle: "text-sm leading-6 text-on-surface-variant",
    socialButtonsBlockButton:
      "border border-outline-variant/20 bg-surface-container-low text-on-surface hover:bg-surface-container-high",
    formButtonPrimary:
      "bg-primary text-white hover:opacity-90 shadow-none",
    formFieldInput:
      "border border-outline-variant/20 bg-surface text-on-surface focus:border-primary focus:ring-primary/20",
    footerActionLink: "text-primary hover:text-primary",
  },
  variables: {
    colorPrimary: "rgb(var(--color-primary))",
    colorBackground: "rgb(var(--color-surface-container-lowest))",
    colorInputBackground: "rgb(var(--color-surface))",
    colorInputText: "rgb(var(--color-on-surface))",
    borderRadius: "1rem",
  },
};

export default function ConnectionPanel({ mode = "sign-in" }) {
  const isSignUp = mode === "sign-up";

  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative overflow-hidden rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft md:p-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(var(--color-primary),0.18),transparent_45%),radial-gradient(circle_at_bottom_right,rgba(var(--color-tertiary),0.18),transparent_40%)]" />
        <div className="relative z-10">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-primary">Runr Access</p>
          <h1 className="mt-4 font-headline text-4xl font-extrabold tracking-tight text-on-surface md:text-5xl">
            Sign in to manage runs, quotas, and billing.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-on-surface-variant">
            Clerk now handles authentication and identity. Once you sign in, the app will attach
            your Clerk session token to every backend request automatically.
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
              <p className="text-sm font-semibold text-on-surface">Protected routes</p>
              <p className="mt-2 text-xs leading-5 text-on-surface-variant">
                Signed-in sessions now gate the entire workspace app.
              </p>
            </div>
            <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
              <p className="text-sm font-semibold text-on-surface">Plan-aware access</p>
              <p className="mt-2 text-xs leading-5 text-on-surface-variant">
                Your role and plan metadata travel with the JWT used by the backend.
              </p>
            </div>
            <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
              <p className="text-sm font-semibold text-on-surface">Billing ready</p>
              <p className="mt-2 text-xs leading-5 text-on-surface-variant">
                LemonSqueezy checkout and subscription management unlock after sign-in.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center">
        {isSignUp ? (
          <SignUp
            appearance={clerkAppearance}
            fallbackRedirectUrl="/"
            path="/sign-up"
            routing="path"
            signInUrl="/sign-in"
          />
        ) : (
          <SignIn
            appearance={clerkAppearance}
            fallbackRedirectUrl="/"
            path="/sign-in"
            routing="path"
            signUpUrl="/sign-up"
          />
        )}
      </section>
    </div>
  );
}

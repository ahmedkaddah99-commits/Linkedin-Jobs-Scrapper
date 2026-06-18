import { SignIn, SignUp } from "@clerk/react";

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
    <div className="mx-auto flex max-w-4xl justify-center px-4 py-10">
      <section className="flex w-full items-center justify-center">
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

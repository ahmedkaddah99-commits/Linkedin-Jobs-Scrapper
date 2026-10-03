import { ClerkProvider } from "@clerk/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { BrowserTestSessionProvider } from "./context/SessionContext";
import { ThemeProvider } from "./context/ThemeContext";
import "./styles.css";

const clerkPublishableKey = String(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "").trim();
const browserTestMode = import.meta.env.VITE_E2E_AUTH === "1";
const appSubdomain = window.location.hostname === "app.userunr.com";
const publicMarketingPaths = new Set([
  "/",
  "/how-it-works",
  "/pricing",
  "/security",
  "/terms",
  "/terms-and-conditions",
  "/user-agreement",
  "/privacy",
]);
const canRenderPublicMarketing = !appSubdomain && publicMarketingPaths.has(window.location.pathname);

function AppFrame() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </BrowserRouter>
  );
}

function ClerkConfigurationMessage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-3xl items-center px-6 py-12">
      <div className="w-full rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft">
        <h1 className="font-headline text-3xl font-extrabold tracking-tight text-on-surface">
          Clerk Configuration Missing
        </h1>
        <p className="mt-3 text-sm leading-7 text-on-surface-variant">
          Set `VITE_CLERK_PUBLISHABLE_KEY` in `frontend/.env.local` before starting the frontend.
        </p>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    {browserTestMode ? (
      <ClerkProvider publishableKey="pk_test_Y2xlcmsuZXhhbXBsZS5jb20k">
        <BrowserTestSessionProvider>
          <AppFrame />
        </BrowserTestSessionProvider>
      </ClerkProvider>
    ) : clerkPublishableKey ? (
      <ClerkProvider afterSignOutUrl="/sign-in">
        <AppFrame />
      </ClerkProvider>
    ) : canRenderPublicMarketing ? (
      <AppFrame />
    ) : (
      <ClerkConfigurationMessage />
    )}
  </StrictMode>,
);

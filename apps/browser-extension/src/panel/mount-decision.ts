import type { ApplicationPageDetection } from "@runr/ats-core/application-context";

export interface PanelMountPreferences {
  /** When false the user has opted out of the panel appearing by itself. */
  autoOpenOnApplicationPage: boolean;
}

export const DEFAULT_PANEL_MOUNT_PREFERENCES: PanelMountPreferences = {
  autoOpenOnApplicationPage: true,
};

export interface PanelMountDecision {
  mount: boolean;
  reason: string;
}

/**
 * The single rule that governs automatic display.
 *
 * Only a page classified as an application form may raise the panel. A posting
 * page, a sign-in step, and an unrecognised page must all leave the page
 * untouched — this is the behavior observed in the Simplify reference captures,
 * where the panel is present on the application step and absent on both the job
 * detail page and the login step.
 *
 * The user may still open the panel deliberately from the toolbar; that path
 * does not come through here.
 */
export function shouldMountPanel(
  detection: ApplicationPageDetection,
  preferences: PanelMountPreferences = DEFAULT_PANEL_MOUNT_PREFERENCES,
): PanelMountDecision {
  if (!preferences.autoOpenOnApplicationPage) {
    return { mount: false, reason: "Automatic display is turned off in Runr settings." };
  }
  if (detection.kind === "job_detail") {
    return { mount: false, reason: "This is a job posting, not an application form." };
  }
  if (detection.kind === "application_gateway") {
    return { mount: false, reason: "This is a sign-in step, not an application form." };
  }
  if (detection.kind === "unsupported") {
    return { mount: false, reason: "No application fields were found on this page." };
  }
  if (detection.fillableFieldCount === 0) {
    return { mount: false, reason: "The application form has no fillable controls yet." };
  }
  return { mount: true, reason: `Application form detected with ${detection.fillableFieldCount} fillable controls.` };
}

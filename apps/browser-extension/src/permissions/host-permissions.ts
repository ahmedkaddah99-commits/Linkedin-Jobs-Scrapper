import { browser } from "wxt/browser";

/**
 * The set of optional host permission patterns the extension may request
 * after an explicit user action (e.g. "Connect" or "Fill").
 *
 * These are additive to the mandatory first-party API host permission
 * declared in the manifest. Portal-specific access is optional so users
 * can grant site access only when they actively use Assisted Apply.
 */
export const OPTIONAL_HOST_PERMISSION_PATTERNS: ReadonlyArray<string> = [
  "https://boards.greenhouse.io/*",
  "https://*.lever.co/*",
];

export type SupportedPortal = "greenhouse" | "lever";

/**
 * Returns the origin portion of a URL, or the full URL if it matches
 * a known portal pattern, for display in permission prompts.
 */
export function permissionOrigin(portal: SupportedPortal): string {
  if (portal === "greenhouse") return "https://boards.greenhouse.io";
  if (portal === "lever") return "https://*.lever.co";
  return "unknown";
}

/**
 * Checks whether *all* optional host permission patterns are currently
 * granted.  Returns `true` when the extension already has every pattern
 * it may need.
 */
export async function hasAllOptionalHostPermissions(): Promise<boolean> {
  const granted = await browser.permissions.contains({
    origins: [...OPTIONAL_HOST_PERMISSION_PATTERNS],
  });
  return granted;
}

/**
 * Checks whether the specific origin-based patterns needed for a
 * particular portal are currently granted.
 */
export async function hasPortalPermission(
  portal: SupportedPortal,
): Promise<boolean> {
  const patterns = portalPermissionPatterns(portal);
  if (patterns.length === 0) return false;
  return browser.permissions.contains({ origins: patterns });
}

/**
 * Returns the optional host permission patterns that are *needed* for
 * a given portal.  An empty array means no optional permissions are
 * required for that portal.
 */
export function portalPermissionPatterns(
  portal: SupportedPortal,
): string[] {
  if (portal === "greenhouse") {
    return ["https://boards.greenhouse.io/*"];
  }
  if (portal === "lever") {
    return ["https://*.lever.co/*"];
  }
  return [];
}

/**
 * Requests optional host permission patterns for a supported portal.
 * Must be called from a user gesture (click handler).
 *
 * Returns `true` if the user granted the permissions, `false` if they
 * denied the request.
 */
export async function requestPortalPermission(
  portal: SupportedPortal,
): Promise<boolean> {
  const patterns = portalPermissionPatterns(portal);
  if (patterns.length === 0) return true; // Nothing to request
  const already = await browser.permissions.contains({ origins: patterns });
  if (already) return true;

  const granted = await browser.permissions.request({ origins: patterns });
  return granted;
}

/**
 * Requests *all* optional host permission patterns at once.  Returns
 * `true` if all were granted, `false` if any was denied.
 */
export async function requestAllOptionalHostPermissions(): Promise<boolean> {
  const already = await hasAllOptionalHostPermissions();
  if (already) return true;

  return browser.permissions.request({
    origins: [...OPTIONAL_HOST_PERMISSION_PATTERNS],
  });
}

/**
 * Returns a list of portal origins that are known to be supported but
 * for which the extension does not currently have host permissions.
 * Used to show the user which sites need approval.
 */
export async function missingPortalPermissions(): Promise<
  Array<{ portal: SupportedPortal; origin: string }>
> {
  const missing: Array<{ portal: SupportedPortal; origin: string }> = [];
  for (const portal of ["greenhouse", "lever"] as const) {
    const has = await hasPortalPermission(portal);
    if (!has) {
      missing.push({ portal, origin: permissionOrigin(portal) });
    }
  }
  return missing;
}

/**
 * Handles the case where a permission was previously granted but has
 * since been revoked by the user.  Returns `true` if re-granted.
 */
export async function recoverRevokedPermission(
  portal: SupportedPortal,
): Promise<boolean> {
  return requestPortalPermission(portal);
}

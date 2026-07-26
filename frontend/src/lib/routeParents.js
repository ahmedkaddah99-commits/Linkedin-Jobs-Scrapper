const TRACKER_ROOT = "/tracker";

function safeTrackerReturnPath(value) {
  const path = String(value || "").trim();
  return path === TRACKER_ROOT || path.startsWith(`${TRACKER_ROOT}?`) || path.startsWith(`${TRACKER_ROOT}#`)
    ? path
    : TRACKER_ROOT;
}

export function resolveRouteParent({ pathname = "", search = "" } = {}) {
  const normalizedPath = String(pathname || "").replace(/\/+$/, "") || "/";
  const params = new URLSearchParams(search);

  if (normalizedPath === "/career-evidence") return "";
  if (normalizedPath === "/career-memory") return "/career-evidence";
  if (normalizedPath === "/career-memory/guide") return "/career-evidence";
  if (normalizedPath === "/documents" && params.get("view") === "memory") return "/career-evidence";
  if (normalizedPath === "/documents") return "/career-evidence";
  if (normalizedPath === "/cv-studio") return "/career-evidence";
  if (/^\/tracker\/job-descriptions\/[^/]+$/.test(normalizedPath)) return TRACKER_ROOT;
  if (/^\/tracker\/[^/]+\/ats$/.test(normalizedPath)) {
    return safeTrackerReturnPath(params.get("return"));
  }
  if (normalizedPath === "/settings/assisted-apply") return "/settings";
  if (/^\/job-workspaces\/[^/]+\/[^/]+$/.test(normalizedPath)) return "/workspaces";
  if (/^\/runs\/[^/]+$/.test(normalizedPath)) return "/runs";
  return "";
}

export function requestRouteNavigation(to) {
  if (typeof window === "undefined") return true;
  return window.dispatchEvent(
    new CustomEvent("runr:before-navigation", {
      cancelable: true,
      detail: { to: String(to || "") },
    }),
  );
}

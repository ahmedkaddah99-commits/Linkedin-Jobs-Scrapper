export function isAdminUser(user) {
  return String(user?.role || "").trim().toLowerCase() === "admin";
}

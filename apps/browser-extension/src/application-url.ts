export function comparableApplicationUrl(value: string): string {
  const parsed = new URL(value);
  parsed.hash = "";
  return parsed.href;
}

export function preparedApplicationUrlMatches(prepared: unknown, requested: string): boolean {
  if (typeof prepared !== "string") return false;
  try {
    return comparableApplicationUrl(prepared) === comparableApplicationUrl(requested);
  } catch {
    return false;
  }
}

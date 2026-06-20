export async function loadTrackerShell(request) {
  const [tracker, integration] = await Promise.all([
    request("/tracker"),
    request("/tracker/email-integration"),
  ]);
  return { tracker, integration };
}

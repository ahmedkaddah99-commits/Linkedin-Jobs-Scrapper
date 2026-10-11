import { logEvent } from "./analytics.js";
import { buildPersonalizedEventProperties } from "./personalizedAnalyticsPayload.js";

export { buildPersonalizedEventProperties } from "./personalizedAnalyticsPayload.js";

export function logPersonalizedEvent(eventName, context = {}) {
  logEvent(eventName, buildPersonalizedEventProperties(context));
}

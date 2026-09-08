import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeTrackerDescription,
  trackerDescriptionForItem,
} from "./trackerDescription.js";

test("returns the complete stored multi-paragraph tracker description", () => {
  const description = [
    "About the role",
    "",
    "You will:",
    "- Lead discovery with customers",
    "- Coordinate delivery across teams",
    "",
    "Requirements",
    "- Product management experience",
  ].join("\r\n");

  assert.equal(
    trackerDescriptionForItem({
      full_description: description,
      title: "This teaser must not be copied",
    }),
    description.replaceAll("\r\n", "\n"),
  );
});

test("restores persisted escaped line breaks without flattening list structure", () => {
  assert.equal(
    normalizeTrackerDescription("Summary\\n\\nResponsibilities\\n- First\\n- Second"),
    "Summary\n\nResponsibilities\n- First\n- Second",
  );
});

test("does not fall back to titles or teaser fields when the stored description is absent", () => {
  assert.equal(
    trackerDescriptionForItem({
      title: "Product Manager",
      description_excerpt: "One-line teaser",
    }),
    "",
  );
});

import { describe, expect, it } from "vitest";
import { preparedApplicationUrlMatches } from "../../src/application-url";

describe("prepared application URL binding", () => {
  it("matches the immutable prepared URL and ignores only the fragment", () => {
    expect(preparedApplicationUrlMatches(
      "https://jobs.example.test/apply/123#prepared",
      "https://jobs.example.test/apply/123#opened",
    )).toBe(true);
  });

  it("rejects a different application path or missing prepared URL", () => {
    expect(preparedApplicationUrlMatches(
      "https://jobs.example.test/apply/123",
      "https://jobs.example.test/apply/456",
    )).toBe(false);
    expect(preparedApplicationUrlMatches(undefined, "https://jobs.example.test/apply/123")).toBe(false);
  });
});

// CP-039R: Tests for source processing polling with backoff.

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { pollProcessingState, readFileAsBase64 } from "./sourceProcessingPolling.js";

describe("pollProcessingState", () => {
  it("returns terminal state immediately when completed", async () => {
    let calls = 0;
    const checkFn = async () => {
      calls += 1;
      return { state: "completed", extracted_count: 5 };
    };
    const result = await pollProcessingState(checkFn, {
      timeoutMs: 5000,
      initialDelayMs: 100,
    });
    assert.equal(result.state, "completed");
    assert.equal(result.extracted_count, 5);
    assert.equal(calls, 1);
  });

  it("polls until terminal state with backoff", async () => {
    let attempt = 0;
    const checkFn = async () => {
      attempt += 1;
      if (attempt < 3) return { state: "processing" };
      return { state: "completed", extracted_count: 3 };
    };
    const result = await pollProcessingState(checkFn, {
      timeoutMs: 5000,
      initialDelayMs: 10,
      maxDelayMs: 50,
    });
    assert.equal(result.state, "completed");
    assert.equal(attempt, 3);
  });

  it("returns timeout after deadline", async () => {
    const checkFn = async () => ({ state: "processing" });
    const result = await pollProcessingState(checkFn, {
      timeoutMs: 100,
      initialDelayMs: 20,
      maxDelayMs: 40,
    });
    assert.equal(result.state, "timeout");
    assert.equal(result.retry_allowed, true);
  });

  it("returns failed state when checkFn returns failed", async () => {
    const checkFn = async () => ({ state: "failed", error: "Extraction failed." });
    const result = await pollProcessingState(checkFn, {
      timeoutMs: 5000,
      initialDelayMs: 10,
    });
    assert.equal(result.state, "failed");
    assert.equal(result.error, "Extraction failed.");
  });

  it("returns empty state when checkFn returns empty", async () => {
    const checkFn = async () => ({ state: "empty", error: "No content." });
    const result = await pollProcessingState(checkFn, {
      timeoutMs: 5000,
      initialDelayMs: 10,
    });
    assert.equal(result.state, "empty");
  });

  it("calls onTick callback after each poll", async () => {
    const ticks = [];
    let attempt = 0;
    const checkFn = async () => {
      attempt += 1;
      if (attempt < 2) return { state: "processing" };
      return { state: "completed" };
    };
    await pollProcessingState(checkFn, {
      timeoutMs: 5000,
      initialDelayMs: 10,
      maxDelayMs: 50,
      onTick: (s) => ticks.push(s.state),
    });
    assert.deepEqual(ticks, ["processing", "completed"]);
  });

  it("retries on network errors", async () => {
    let attempt = 0;
    const checkFn = async () => {
      attempt += 1;
      if (attempt < 2) throw new Error("Network error");
      return { state: "completed", extracted_count: 1 };
    };
    const result = await pollProcessingState(checkFn, {
      timeoutMs: 5000,
      initialDelayMs: 10,
      maxDelayMs: 50,
    });
    assert.equal(result.state, "completed");
    assert.equal(attempt, 2);
  });
});

describe("readFileAsBase64", () => {
  it("reads a Blob as base64", async () => {
    const blob = new Blob(["test content"], { type: "text/plain" });
    const result = await readFileAsBase64(blob);
    assert.ok(typeof result === "string");
    assert.ok(result.length > 0);
  });
});

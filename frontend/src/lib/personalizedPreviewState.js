import { useCallback, useEffect, useState } from "react";
import {
  DISPOSITION_STORAGE_KEY,
  ONBOARDING_STORAGE_KEY,
  UPGRADE_DISMISSALS_STORAGE_KEY,
} from "./personalizedJobs.js";

function readJson(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || "null");
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  if (typeof window !== "undefined") window.localStorage.setItem(key, JSON.stringify(value));
}

export const EMPTY_DISPOSITIONS = Object.freeze({ hidden: {}, restored: {}, saved: {} });

export function loadOnboardingState() {
  return readJson(ONBOARDING_STORAGE_KEY, { step: 0, answers: {}, completed: false });
}

export function saveOnboardingState(state) {
  const nextState = {
    step: Number.isInteger(state?.step) ? state.step : 0,
    answers: state?.answers && typeof state.answers === "object" ? state.answers : {},
    completed: Boolean(state?.completed),
  };
  writeJson(ONBOARDING_STORAGE_KEY, nextState);
  return nextState;
}

export function loadDispositions() {
  const stored = readJson(DISPOSITION_STORAGE_KEY, EMPTY_DISPOSITIONS);
  return {
    hidden: { ...(stored.hidden || {}) },
    restored: { ...(stored.restored || {}) },
    saved: { ...(stored.saved || {}) },
  };
}

export function saveDispositions(dispositions) {
  const next = {
    hidden: { ...(dispositions?.hidden || {}) },
    restored: { ...(dispositions?.restored || {}) },
    saved: { ...(dispositions?.saved || {}) },
  };
  writeJson(DISPOSITION_STORAGE_KEY, next);
  return next;
}

export function restorePreviewDisposition(dispositions, jobId) {
  const current = dispositions || EMPTY_DISPOSITIONS;
  const hidden = { ...(current.hidden || {}) };
  delete hidden[jobId];
  return {
    hidden,
    restored: { ...(current.restored || {}), [jobId]: true },
    saved: { ...(current.saved || {}) },
  };
}

export function loadUpgradeDismissals() {
  return readJson(UPGRADE_DISMISSALS_STORAGE_KEY, {});
}

export function saveUpgradeDismissal(featureKey) {
  const next = { ...loadUpgradeDismissals(), [featureKey]: true };
  writeJson(UPGRADE_DISMISSALS_STORAGE_KEY, next);
  return next;
}

export function usePreviewDispositions() {
  const [dispositions, setDispositions] = useState(loadDispositions);
  const update = useCallback((updater) => {
    setDispositions((current) => {
      const next = typeof updater === "function" ? updater(current) : updater;
      saveDispositions(next);
      return next;
    });
  }, []);
  const toggleSaved = useCallback((jobId, currentValue) => {
    update((current) => ({ ...current, saved: { ...current.saved, [jobId]: !Boolean(currentValue ?? current.saved[jobId]) } }));
  }, [update]);
  const hideJob = useCallback((jobId) => {
    update((current) => ({ ...current, hidden: { ...current.hidden, [jobId]: true } }));
  }, [update]);
  const restoreJob = useCallback((jobId) => {
    update((current) => restorePreviewDisposition(current, jobId));
  }, [update]);
  return { dispositions, toggleSaved, hideJob, restoreJob };
}

export function usePersistedOnboarding() {
  const [state, setState] = useState(loadOnboardingState);
  useEffect(() => { saveOnboardingState(state); }, [state]);
  const update = useCallback((updater) => setState((current) => (typeof updater === "function" ? updater(current) : updater)), []);
  return { state, setState, update };
}

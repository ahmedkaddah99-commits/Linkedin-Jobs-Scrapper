import { useCallback, useEffect, useState } from "react";
import {
  DISPOSITION_STORAGE_KEY,
  ONBOARDING_STORAGE_KEY,
  POST_ONBOARDING_OFFER_STORAGE_KEY,
  UPGRADE_DISMISSALS_STORAGE_KEY,
} from "./personalizedJobs.js";

export const EMPTY_POST_ONBOARDING_OFFER_STATE = Object.freeze({
  eligible: false,
  offerShown: false,
  offerDismissed: false,
  upgradeCtaSelected: false,
  alreadySubscribed: false,
  notificationDismissed: false,
  completed: false,
});

function storageKey(key, userId = "") {
  const normalizedUserId = String(userId || "").trim();
  return normalizedUserId ? `${key}:${encodeURIComponent(normalizedUserId)}` : key;
}

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
  return readJson(ONBOARDING_STORAGE_KEY, { step: 0, answers: {}, cv: {}, completed: false });
}

export function loadUserOnboardingState(userId = "") {
  return readJson(storageKey(ONBOARDING_STORAGE_KEY, userId), loadOnboardingState());
}

export function saveOnboardingState(state) {
  const nextState = {
    step: Number.isInteger(state?.step) ? state.step : 0,
    answers: state?.answers && typeof state.answers === "object" ? state.answers : {},
    cv: state?.cv && typeof state.cv === "object"
      ? {
        status: String(state.cv.status || ""),
        selected: Boolean(state.cv.selected),
        assetId: String(state.cv.assetId || ""),
        showcaseScene: Number.isInteger(state.cv.showcaseScene) ? state.cv.showcaseScene : 0,
        showcaseVisited: Boolean(state.cv.showcaseVisited),
        showcaseSkipped: Boolean(state.cv.showcaseSkipped),
        showcaseCompleted: Boolean(state.cv.showcaseCompleted),
      }
      : {},
    completed: Boolean(state?.completed),
  };
  writeJson(ONBOARDING_STORAGE_KEY, nextState);
  return nextState;
}

export function saveUserOnboardingState(state, userId = "") {
  const nextState = saveOnboardingState(state);
  writeJson(storageKey(ONBOARDING_STORAGE_KEY, userId), nextState);
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

export function loadPostOnboardingOfferState(userId = "") {
  return {
    ...EMPTY_POST_ONBOARDING_OFFER_STATE,
    ...readJson(storageKey(POST_ONBOARDING_OFFER_STORAGE_KEY, userId), {}),
  };
}

export function savePostOnboardingOfferState(state, userId = "") {
  const nextState = { ...EMPTY_POST_ONBOARDING_OFFER_STATE, ...(state || {}) };
  writeJson(storageKey(POST_ONBOARDING_OFFER_STORAGE_KEY, userId), nextState);
  return nextState;
}

export function markPostOnboardingEligible(userId = "") {
  return savePostOnboardingOfferState(
    { ...loadPostOnboardingOfferState(userId), eligible: true },
    userId,
  );
}

export function updatePostOnboardingOfferState(updater, userId = "") {
  const current = loadPostOnboardingOfferState(userId);
  const next = typeof updater === "function" ? updater(current) : updater;
  return savePostOnboardingOfferState(next, userId);
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

export function usePersistedOnboarding(userId = "") {
  const [state, setState] = useState(() => loadUserOnboardingState(userId));
  useEffect(() => { saveUserOnboardingState(state, userId); }, [state, userId]);
  const update = useCallback((updater) => setState((current) => (typeof updater === "function" ? updater(current) : updater)), []);
  return { state, setState, update };
}

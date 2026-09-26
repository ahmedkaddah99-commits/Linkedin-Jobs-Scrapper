import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCountryByCode, hasCityDataset, loadCityOptions } from "../lib/locationOptions";

const EMPTY_CITY_OPTIONS_STATE = {
  loading: false,
  options: [],
  selectedCountryCode: "",
  missingDataset: false,
};

function parseDelimitedList(value) {
  const rawValues = Array.isArray(value) ? value : [value];
  const tokens = [];
  const seen = new Set();
  for (const rawValue of rawValues) {
    for (const item of String(rawValue || "").split(/[\r\n,]+/)) {
      const normalized = item.trim();
      if (!normalized) continue;
      const dedupeKey = normalized.toLowerCase();
      if (seen.has(dedupeKey)) continue;
      tokens.push(normalized);
      seen.add(dedupeKey);
    }
  }
  return tokens;
}

export function useWorkspaceCityOptions({
  builderOpen,
  currentCities,
  onCitiesChange,
  selectedCountryCode,
  selectedCountryCodes,
}) {
  const [cityOptionsState, setCityOptionsState] = useState(EMPTY_CITY_OPTIONS_STATE);
  const cityRequestRef = useRef(0);
  const cityScopeRef = useRef("");

  const selectedCountry = useMemo(
    () => (selectedCountryCode ? getCountryByCode(selectedCountryCode) : null),
    [selectedCountryCode],
  );

  const cityHelperText = useMemo(() => {
    if (!selectedCountryCodes.length) {
      return "Select a target country first to enable city suggestions.";
    }
    const fallbackCityLabel = selectedCountry?.capital || "the selected country capital";
    if (cityOptionsState.missingDataset) {
      return `No packaged city list is available for ${
        selectedCountry?.label || "this country"
      } yet. Leave this blank and Runr will use ${fallbackCityLabel}.`;
    }
    if (!cityOptionsState.loading && !cityOptionsState.options.length) {
      return `No city suggestions loaded for ${
        selectedCountry?.label || "this country"
      }. Leave this blank and Runr will use ${fallbackCityLabel}.`;
    }
    return "";
  }, [
    cityOptionsState.loading,
    cityOptionsState.missingDataset,
    cityOptionsState.options.length,
    selectedCountry,
    selectedCountryCodes.length,
  ]);

  const resetCityOptions = useCallback(() => {
    cityScopeRef.current = "";
    cityRequestRef.current += 1;
    setCityOptionsState(EMPTY_CITY_OPTIONS_STATE);
  }, []);

  useEffect(() => {
    if (!builderOpen) {
      return;
    }
    const nextScopeKey = selectedCountryCodes.join(",");
    if (!cityScopeRef.current) {
      cityScopeRef.current = nextScopeKey;
      return;
    }
    if (cityScopeRef.current === nextScopeKey) {
      return;
    }
    cityScopeRef.current = nextScopeKey;
    if (parseDelimitedList(currentCities).length) {
      onCitiesChange([]);
    }
  }, [builderOpen, currentCities, onCitiesChange, selectedCountryCodes]);

  useEffect(() => {
    if (!builderOpen) {
      cityScopeRef.current = "";
      cityRequestRef.current += 1;
      setCityOptionsState({
        ...EMPTY_CITY_OPTIONS_STATE,
        selectedCountryCode,
      });
      return;
    }
    if (!selectedCountryCode) {
      cityRequestRef.current += 1;
      setCityOptionsState({
        ...EMPTY_CITY_OPTIONS_STATE,
        selectedCountryCode,
      });
      return;
    }
    if (!hasCityDataset(selectedCountryCode)) {
      setCityOptionsState({
        loading: false,
        options: [],
        selectedCountryCode,
        missingDataset: true,
      });
      return;
    }

    const requestId = cityRequestRef.current + 1;
    cityRequestRef.current = requestId;
    setCityOptionsState({
      loading: true,
      options: [],
      selectedCountryCode,
      missingDataset: false,
    });

    loadCityOptions(selectedCountryCode)
      .then((options) => {
        if (cityRequestRef.current !== requestId) {
          return;
        }
        setCityOptionsState({
          loading: false,
          options,
          selectedCountryCode,
          missingDataset: false,
        });
      })
      .catch(() => {
        if (cityRequestRef.current !== requestId) {
          return;
        }
        setCityOptionsState({
          loading: false,
          options: [],
          selectedCountryCode,
          missingDataset: true,
        });
      });
  }, [builderOpen, selectedCountryCode]);

  return {
    cityHelperText,
    cityOptionsState,
    resetCityOptions,
    selectedCountry,
  };
}

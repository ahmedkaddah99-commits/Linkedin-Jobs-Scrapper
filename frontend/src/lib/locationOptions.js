import rawCountries from "@tansuasici/country-state-city/data/countries.json";

const COUNTRY_LABEL_OVERRIDES = {
  PS: "Palestine",
};

const collator = new Intl.Collator("en", { sensitivity: "base" });

const cityFileUrlLoaders = import.meta.glob(
  "../../node_modules/@tansuasici/country-state-city/data/cities/*.json",
  {
    query: "?url",
    import: "default",
  },
);

const countryOptions = (Array.isArray(rawCountries) ? rawCountries : [])
  .map((country) => {
    const value = String(country?.iso2 || "").trim().toUpperCase();
    if (!value) {
      return null;
    }
    return {
      value,
      label: COUNTRY_LABEL_OVERRIDES[value] || String(country?.name || value).trim(),
      capital: String(country?.capital || "").trim(),
      iso3: String(country?.iso3 || "").trim(),
      region: String(country?.region || "").trim(),
      subregion: String(country?.subregion || "").trim(),
    };
  })
  .filter(Boolean)
  .sort((left, right) => collator.compare(left.label, right.label));

const countryByCode = new Map(countryOptions.map((country) => [country.value, country]));

const cityLoaderByCountryCode = new Map(
  Object.entries(cityFileUrlLoaders)
    .map(([path, loader]) => {
      const match = path.match(/\/([a-z]{2})\.json$/i);
      if (!match) {
        return null;
      }
      return [match[1].toUpperCase(), loader];
    })
    .filter(Boolean),
);

function normalizeCountryCodes(countryCodes) {
  const rawValues =
    typeof countryCodes === "string"
      ? countryCodes.split(/[,\r\n]+/)
      : Array.isArray(countryCodes)
        ? countryCodes
        : [];
  return [...new Set(
    rawValues
      .map((item) => String(item || "").trim().toUpperCase())
      .filter(Boolean),
  )];
}

export function getAllCountryOptions() {
  return countryOptions;
}

export function getCountryByCode(countryCode) {
  return countryByCode.get(String(countryCode || "").trim().toUpperCase()) || null;
}

export function hasCityDataset(countryCode) {
  return cityLoaderByCountryCode.has(String(countryCode || "").trim().toUpperCase());
}

export function deriveDefaultCities(countryCodes, limit = 8) {
  const cities = [];
  const seen = new Set();

  for (const countryCode of normalizeCountryCodes(countryCodes)) {
    const capital = String(getCountryByCode(countryCode)?.capital || "").trim();
    if (!capital) {
      continue;
    }
    const dedupeKey = capital.toLowerCase();
    if (seen.has(dedupeKey)) {
      continue;
    }
    cities.push(capital);
    seen.add(dedupeKey);
    if (cities.length >= limit) {
      break;
    }
  }

  return cities;
}

export async function loadCityOptions(countryCode) {
  const normalizedCountryCode = String(countryCode || "").trim().toUpperCase();
  const loader = cityLoaderByCountryCode.get(normalizedCountryCode);
  if (!loader) {
    return [];
  }

  const cityFileUrl = await loader();
  const response = await fetch(cityFileUrl);
  if (!response.ok) {
    return [];
  }
  const rawCities = await response.json();
  const seen = new Set();
  const options = [];

  for (const city of Array.isArray(rawCities) ? rawCities : []) {
    const label = String(city?.n || city?.name || "").trim();
    if (!label) {
      continue;
    }
    const dedupeKey = label.toLowerCase();
    if (seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    options.push(label);
  }

  return options.sort((left, right) => collator.compare(left, right));
}

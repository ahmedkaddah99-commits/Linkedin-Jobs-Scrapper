"""Choice values shared by customer controls and catalog queries."""
import json
from pathlib import Path

CHOICES = json.loads(Path(__file__).with_name("job_filter_choices.json").read_text(encoding="utf-8"))
COUNTRIES = json.loads(Path(__file__).with_name("job_filter_countries.json").read_text(encoding="utf-8"))
COUNTRY_ALIASES = {
    name.casefold(): [name.casefold(), code.casefold()]
    for name, code in COUNTRIES.items()
}
COUNTRY_ALIASES.update({code.casefold(): COUNTRY_ALIASES[name.casefold()] for name, code in COUNTRIES.items()})
for name, aliases in {"Germany": ["deutschland", "deu"], "United States": ["usa", "us", "united states of america"], "United Kingdom": ["uk", "gbr"]}.items():
    for alias in aliases:
        COUNTRY_ALIASES[alias] = COUNTRY_ALIASES[name.casefold()]
    COUNTRY_ALIASES[name.casefold()].extend(aliases)
ENUM_FIELDS = {
    "employment_type": "employmentType", "work_arrangement": "workArrangement",
    "experience_level": "experienceLevel", "company_stage": "companyStage",
}

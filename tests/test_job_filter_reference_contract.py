import unittest
import pytest
from backend.application.personalized_jobs_service import normalize_filters
from tests import test_phase_c_personalized_jobs as fixtures


def test_fractional_experience_survives_normalization_and_invalid_ranges_fail():
    assert normalize_filters({"required_experience_min": "2.5", "required_experience_max": "3.5"}) == {"required_experience_min": 2.5, "required_experience_max": 3.5}
    for filters in ({"required_experience_min": 5, "required_experience_max": 2}, {"salary_min": "nan"}, {"salary_min": -1}):
        with pytest.raises(ValueError):
            normalize_filters(filters)


class ReferenceFilterTests(unittest.TestCase):
    _backend = fixtures.PhaseCPersonalizedJobsTests._backend

    def test_annual_salary_converts_months_and_keeps_currency_and_unknowns_explicit(self):
        app = self._backend()
        fixtures._seed_catalog(app, payload_overrides={"job-a": {"salary": {"min": 5000, "currency": "EUR", "period": "month"}}, "job-b": {"salary": {"max": 100000, "currency": "USD", "period": "hour"}}})
        page = app.get_personalized_jobs("user-a", filters={"salary_min": 60000, "salary_currency": "EUR"})
        self.assertEqual([job["canonical_job_id"] for job in page["jobs"]], ["job-a"])
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"salary_min": 60001})["total"], 0)
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"salary_min": 60000, "salary_currency": "USD"})["total"], 0)

    def test_country_codes_and_multiple_cities_filter_before_pagination(self):
        app = self._backend()
        fixtures._seed_catalog(app, payload_overrides={"job-a": {"country_code": "DE"}, "job-b": {"country_code": "US"}})
        page = app.get_personalized_jobs("user-a", filters={"country": "Germany", "location": ["Berlin", "Hamburg"]}, limit=1)
        self.assertEqual([job["canonical_job_id"] for job in page["jobs"]], ["job-a"])
        self.assertEqual(page["total"], 1)
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"country": "United States"})["total"], 1)

    def test_experience_is_exact_and_arrays_allow_multiple_levels(self):
        app = self._backend()
        fixtures._seed_catalog(app, payload_overrides={"job-a": {"experience_level": ["entry", "mid"]}, "job-b": {"experience_level": "internship"}})
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"experience_level": ["entry", "senior"]})["total"], 1)
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"experience_level": "intern"})["total"], 0)

    def test_fractional_experience_and_unknowns(self):
        app = self._backend()
        fixtures._seed_catalog(app, payload_overrides={"job-a": {"experience_years_min": 2.5}})
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"required_experience_min": "2.5", "required_experience_max": "2.5"})["total"], 1)
        self.assertEqual(app.get_personalized_jobs("user-a", filters={"required_experience_min": "2.6"})["total"], 0)
        self.assertEqual(app.get_personalized_jobs("user-a", filters={})["total"], 2)
        saved = app.save_personalized_filter_set("user-a", {"name": "Local", "filters": {"location": ["Berlin", "Hamburg"], "required_experience_min": "2.5"}})
        self.assertEqual(saved["filters"]["location"], ["Berlin", "Hamburg"])
        self.assertEqual(saved["filters"]["required_experience_min"], 2.5)

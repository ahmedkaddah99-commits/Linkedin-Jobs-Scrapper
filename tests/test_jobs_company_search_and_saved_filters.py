import unittest

import test_phase_c_personalized_jobs as fixtures


class CompanySearchAndSavedFiltersTests(unittest.TestCase):
    _backend = fixtures.PhaseCPersonalizedJobsTests._backend

    def test_company_search_only_lists_current_published_employers(self):
        app = self._backend()
        fixtures._seed_catalog(app)
        results = app.search_personalized_companies("user-a", "acme")
        self.assertEqual([(r["company_id"], r["name"]) for r in results], [("company-a", "Acme Labs")])
        self.assertEqual(app.search_personalized_companies("user-a", "%"), [])
        app.repositories.acquisition_store._run_transaction(
            lambda c: c.execute("DELETE FROM acquisition_publication_jobs WHERE canonical_job_id='job-a'")
        )
        self.assertEqual(app.search_personalized_companies("user-a", "acme"), [])

    def test_company_id_search_does_not_require_or_inherit_job_filters(self):
        app = self._backend()
        fixtures._seed_catalog(app)
        app.save_personalized_preferences("user-a", {"target_roles": ["Finance Analyst"], "target_locations": ["Munich"]})
        page = app.get_personalized_jobs("user-a", filters={"company_id": "company-a"}, require_role_selection=True, card_view=True)
        self.assertEqual([j["canonical_job_id"] for j in page["jobs"]], ["job-a"])
        self.assertEqual(page["total"], 1)
        self.assertFalse(page.get("selection_required", False))
        missing = app.get_personalized_jobs("user-a", filters={"company_id": "missing"}, require_role_selection=True)
        self.assertEqual(missing["jobs"], [])
        self.assertEqual(missing["total"], 0)
        app.save_personalized_filter_set("user-a", {"name": "Acme", "filters": {"company_id": "company-a"}})
        restored = app.get_personalized_jobs("user-a", require_role_selection=True, card_view=True)
        self.assertEqual([j["canonical_job_id"] for j in restored["jobs"]], ["job-a"])

    def test_company_id_is_opaque_and_case_sensitive(self):
        app = self._backend()
        fixtures._seed_catalog(app)
        app.repositories.acquisition_store._run_transaction(lambda c: (
            c.execute("UPDATE canonical_companies SET company_id='Company-A' WHERE company_id='company-a'"),
            c.execute("UPDATE canonical_jobs SET company_id='Company-A' WHERE company_id='company-a'"),
        ))
        page = app.get_personalized_jobs("user-a", filters={"company_id": "Company-A"}, require_role_selection=True)
        self.assertEqual([j["canonical_job_id"] for j in page["jobs"]], ["job-a"])

    def test_save_activate_edit_and_delete_restore_account_owned_filter(self):
        app = self._backend()
        first = app.save_personalized_filter_set("user-a", {"name": "Berlin analyst", "filters": {"role": ["Data Analyst"], "location": "Berlin", "sort": "least_competitive"}})
        second = app.save_personalized_filter_set("user-a", {"name": "Acme", "filters": {"company_id": "company-a", "company_label": "Acme Labs"}})
        self.assertEqual(app.get_personalized_saved_search("user-a")["active_filter_set_id"], second["filter_set_id"])
        app.activate_personalized_filter_set("user-a", first["filter_set_id"])
        saved = app.get_personalized_saved_search("user-a")
        self.assertEqual(saved["active_filter_set_id"], first["filter_set_id"])
        self.assertEqual(saved["filters"]["sort"], "least_competitive")
        with self.assertRaises(ValueError):
            app.activate_personalized_filter_set("user-b", first["filter_set_id"])
        app.save_personalized_filter_set("user-a", {**first, "name": "Updated", "filters": {"role": ["Business Analyst"]}})
        self.assertEqual(app.get_personalized_saved_search("user-a")["name"], "Updated")
        self.assertFalse(app.delete_personalized_filter_set("user-b", first["filter_set_id"]))
        self.assertEqual(app.get_personalized_saved_search("user-a")["name"], "Updated")
        self.assertTrue(app.delete_personalized_filter_set("user-a", first["filter_set_id"]))
        self.assertIsNone(app.get_personalized_saved_search("user-a"))


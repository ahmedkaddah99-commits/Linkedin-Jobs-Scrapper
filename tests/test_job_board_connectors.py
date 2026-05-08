import unittest

from backend.capabilities.reusable_packages import support as reusable_support
from backend.connectors.job_boards import (
    collect_jobs_from_portals,
    compact_whitespace,
    get_portal_strategy,
    list_portal_strategy_ids,
)


class JobBoardConnectorTests(unittest.TestCase):
    def test_backend_connector_registry_contains_expected_portals(self):
        self.assertEqual(
            list_portal_strategy_ids(),
            ["arbeitsagentur", "indeed", "linkedin", "stepstone"],
        )

    def test_additional_board_ids_resolve_to_fetchers(self):
        for portal_id in [
            "glassdoor",
            "ziprecruiter",
            "monster",
            "careerbuilder",
            "careerjet",
            "reed",
            "totaljobs",
            "jobsdb",
        ]:
            with self.subTest(portal_id=portal_id):
                self.assertEqual(get_portal_strategy(portal_id).portal_id, portal_id)

    def test_support_module_uses_generic_job_board_connectors(self):
        self.assertIs(reusable_support.collect_jobs_from_portals, collect_jobs_from_portals)
        self.assertIs(reusable_support.compact_whitespace, compact_whitespace)


if __name__ == "__main__":
    unittest.main()

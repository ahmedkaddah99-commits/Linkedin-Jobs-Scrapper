import unittest

import bc_automation.blue_collar_portals as legacy_blue_collar_portals

from backend.capabilities.blue_collar import support as blue_support
from backend.connectors.blue_collar import (
    collect_jobs_from_portals,
    compact_whitespace,
    list_portal_strategy_ids,
)


class BlueCollarConnectorTests(unittest.TestCase):
    def test_backend_connector_registry_contains_expected_portals(self):
        self.assertEqual(
            list_portal_strategy_ids(),
            ["arbeitsagentur", "indeed", "linkedin", "stepstone"],
        )

    def test_support_and_legacy_wrapper_use_backend_connectors(self):
        self.assertIs(blue_support.collect_jobs_from_portals, collect_jobs_from_portals)
        self.assertIs(blue_support.compact_whitespace, compact_whitespace)
        self.assertIs(legacy_blue_collar_portals.collect_jobs_from_portals, collect_jobs_from_portals)
        self.assertIs(legacy_blue_collar_portals.compact_whitespace, compact_whitespace)


if __name__ == "__main__":
    unittest.main()

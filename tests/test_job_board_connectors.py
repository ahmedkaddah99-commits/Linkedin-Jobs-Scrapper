import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from backend.capabilities.reusable_packages import support as reusable_support
from backend.connectors.job_boards import (
    collect_jobs_from_portals,
    compact_whitespace,
    get_portal_strategy,
    list_portal_strategy_ids,
)
from backend.connectors.job_boards import strategies
from backend.repositories.sqlite_backed import SqliteAnalyticsStore


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

    def test_board_proxy_fallback_records_actual_scrapeops_credits(self):
        db_path = Path(".backend_test_tmp") / "board_proxy_ledger" / "backend.sqlite3"
        if db_path.parent.exists():
            shutil.rmtree(db_path.parent, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(db_path.parent, ignore_errors=True))
        ledger = SqliteAnalyticsStore(db_path)

        def record_usage(event):
            ledger.record_scrapeops_usage(ledger_id="board_proxy_usage", payload=event)

        response = requests.Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content = json.dumps(
            {
                "body": "&lt;html&gt;jobs&lt;/html&gt;",
                "content_type": "text/html",
                "status_code": 200,
                "sops_api_credits": 13,
            }
        ).encode("utf-8")

        with (
            patch.object(strategies, "SCRAPEOPS_API_KEY", "test-key"),
            patch("backend.integrations.scrapeops.require_scrapeops_proxy_health"),
            patch("backend.connectors.job_boards.strategies.requests.Session") as session_class,
        ):
            session_class.return_value.get.return_value = response
            strategies.reset_scrapeops_proxy_health_gate(usage_callback=record_usage)
            strategies.set_scrapeops_proxy_source("stepstone")
            fetched = strategies._proxy_get(
                "https://www.stepstone.de/jobs",
                {"ke": "analyst"},
                timeout_seconds=10,
            )

        rows = ledger.query_rows(
            "SELECT source_id, billed_credits_actual, request_mode FROM scrapeops_usage_ledger",
        )
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.text, "<html>jobs</html>")
        self.assertEqual(
            rows,
            [{"source_id": "stepstone", "billed_credits_actual": 13, "request_mode": "residential"}],
        )


if __name__ == "__main__":
    unittest.main()

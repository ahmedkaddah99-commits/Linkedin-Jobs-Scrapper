import json
import unittest
from unittest.mock import patch

import requests

from backend.integrations.scrapeops import (
    SCRAPEOPS_HEALTH_TARGET_URL,
    SCRAPEOPS_PROXY_ENDPOINT,
    build_proxy_params,
    build_proxy_usage_record,
    check_scrapeops_proxy_health,
    parse_proxy_response_envelope,
)


def _response(status_code: int, payload: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(payload).encode("utf-8")
    response.encoding = "utf-8"
    return response


class ScrapeOpsIntegrationTests(unittest.TestCase):
    def test_proxy_params_always_request_json_response_metadata(self):
        params = build_proxy_params(
            api_key="test-key",
            url="https://careers.example.com/jobs",
            mode="render_js_cheap",
            country_code="DE",
        )

        self.assertEqual(params["json_response"], "true")
        self.assertEqual(params["render_js_cheap"], "true")
        self.assertEqual(params["country"], "de")

    def test_proxy_envelope_exposes_actual_credits_and_target_body(self):
        envelope = parse_proxy_response_envelope(
            _response(
                200,
                {
                    "body": "&lt;html&gt;careers&lt;/html&gt;",
                    "content_type": "text/html; charset=UTF-8",
                    "status_code": 404,
                    "sops_api_credits": 35,
                },
            )
        )

        self.assertEqual(envelope.provider_status_code, 200)
        self.assertEqual(envelope.target_status_code, 404)
        self.assertEqual(envelope.body, "<html>careers</html>")
        self.assertEqual(envelope.billed_credits_actual, 35)

    def test_usage_record_retains_actual_and_estimated_credits(self):
        record = build_proxy_usage_record(
            source_id="careers.example.com",
            target_url="https://careers.example.com/jobs",
            request_mode="basic",
            target_status_code=200,
            provider_status_code=200,
            latency_ms=72,
            billed_credits_actual=35,
            billed_credits_estimated=1,
            usable_job_count=4,
        )

        self.assertEqual(record["method"], "scrapeops_proxy")
        self.assertEqual(record["billed_credits_actual"], 35)
        self.assertEqual(record["billed_credits_estimated"], 1)
        self.assertEqual(record["usable_job_count"], 4)
        self.assertIn("recorded_at", record)

    @patch("backend.integrations.scrapeops.requests.get")
    def test_proxy_health_returns_healthy_for_billed_success(self, mock_get):
        mock_get.return_value = _response(200, {"status_code": 200, "sops_api_credits": 1})
        events = []

        result = check_scrapeops_proxy_health("test-key", usage_callback=events.append)

        self.assertEqual(
            result,
            {"healthy": True, "reason": "healthy", "credits_remaining": None},
        )
        mock_get.assert_called_once_with(
            SCRAPEOPS_PROXY_ENDPOINT,
            params={
                "api_key": "test-key",
                "url": SCRAPEOPS_HEALTH_TARGET_URL,
                "json_response": "true",
            },
            timeout=5,
        )
        self.assertEqual(events[0]["source_id"], "scrapeops_health_check")
        self.assertEqual(events[0]["billed_credits_actual"], 1)

    @patch("backend.integrations.scrapeops.requests.get")
    def test_proxy_health_returns_healthy_for_billed_target_not_found(self, mock_get):
        mock_get.return_value = _response(404, {"status_code": 404, "sops_api_credits": 1})

        result = check_scrapeops_proxy_health("test-key")

        self.assertTrue(result["healthy"])
        self.assertEqual(result["reason"], "healthy")

    @patch("backend.integrations.scrapeops.requests.get")
    def test_proxy_health_returns_banned_account_failure(self, mock_get):
        mock_get.return_value = _response(403, {"error": "Banned Account"})

        result = check_scrapeops_proxy_health("test-key")

        self.assertFalse(result["healthy"])
        self.assertIn("banned", result["reason"])
        self.assertIsNone(result["credits_remaining"])

    @patch("backend.integrations.scrapeops.requests.get")
    def test_proxy_health_returns_insufficient_credits_for_zero_remaining_balance(self, mock_get):
        mock_get.return_value = _response(
            200,
            {
                "status_code": 200,
                "sops_api_credits": 1,
                "credits_remaining": 0,
            },
        )

        result = check_scrapeops_proxy_health("test-key")

        self.assertFalse(result["healthy"])
        self.assertIn("credits", result["reason"])
        self.assertEqual(result["credits_remaining"], 0)

    @patch("backend.integrations.scrapeops.requests.get")
    def test_proxy_health_returns_insufficient_credits_for_provider_401(self, mock_get):
        mock_get.return_value = _response(401, {"error": "No API credits available"})

        result = check_scrapeops_proxy_health("test-key")

        self.assertFalse(result["healthy"])
        self.assertEqual(result["reason"], "insufficient_credits")


if __name__ == "__main__":
    unittest.main()

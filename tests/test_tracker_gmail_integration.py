import io
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from backend.capabilities.tracker.email_integration import GmailMailboxClient, _gmail_query_for_scan_window
from backend.capabilities.tracker.google_oauth import _google_json_request, tracker_google_oauth_metadata


class TrackerGmailIntegrationTests(unittest.TestCase):
    def test_google_oauth_metadata_does_not_override_runtime_environment(self):
        with patch("backend.capabilities.tracker.google_oauth.load_project_dotenv") as load_dotenv:
            tracker_google_oauth_metadata()

        load_dotenv.assert_called_once_with(override=False)

    def test_gmail_scan_window_uses_safe_newer_than_query(self):
        query_suffix = "{application interview recruiter recruiting candidate career hiring offer rejection bewerbung angebot absage}"
        self.assertEqual(_gmail_query_for_scan_window("now"), f"newer_than:1d {query_suffix}")
        self.assertEqual(_gmail_query_for_scan_window("last_1_month"), f"newer_than:30d {query_suffix}")
        self.assertEqual(_gmail_query_for_scan_window("last_2_months"), f"newer_than:60d {query_suffix}")
        self.assertEqual(_gmail_query_for_scan_window("last_3_months"), f"newer_than:90d {query_suffix}")

    def test_google_error_message_includes_oauth_error_description(self):
        payload_stream = io.BytesIO(b'{"error":"invalid_grant","error_description":"Token has been expired or revoked."}')
        error = HTTPError(
            "https://oauth2.googleapis.com/token",
            400,
            "Bad Request",
            hdrs={},
            fp=payload_stream,
        )

        try:
            with patch("backend.capabilities.tracker.google_oauth.urlopen", side_effect=error):
                with self.assertRaisesRegex(ValueError, "Token has been expired or revoked"):
                    _google_json_request("https://oauth2.googleapis.com/token", method="POST", body=b"")
        finally:
            payload_stream.close()

    def test_gmail_message_list_retries_without_query_when_google_rejects_query(self):
        with patch(
            "backend.capabilities.tracker.email_integration.list_google_gmail_messages",
            side_effect=[ValueError("Google API request failed with HTTP 400."), {"messages": []}],
        ) as list_messages:
            messages, history_id = GmailMailboxClient(access_token="token").fetch_recent_messages(
                limit=40,
                scan_window="last_1_month",
            )

        self.assertEqual(messages, [])
        self.assertEqual(history_id, "")
        self.assertEqual(list_messages.call_count, 2)
        self.assertEqual(
            list_messages.call_args_list[0].kwargs["query_text"],
            "newer_than:30d {application interview recruiter recruiting candidate career hiring offer rejection bewerbung angebot absage}",
        )
        self.assertEqual(list_messages.call_args_list[1].kwargs["query_text"], "")


if __name__ == "__main__":
    unittest.main()

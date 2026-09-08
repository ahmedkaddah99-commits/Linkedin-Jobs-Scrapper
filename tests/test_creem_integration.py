import unittest
import hashlib
from unittest.mock import patch

from backend.integrations.creem import get_checkout_url, verify_redirect_signature


class CreemIntegrationTests(unittest.TestCase):
    def test_checkout_payload_omits_customer_name(self):
        with patch("backend.integrations.creem._creem_request", return_value={"checkout_url": "https://checkout.example/session"}) as request_mock:
            checkout_url = get_checkout_url(
                "user_123",
                "prod_123",
                "user@example.com",
                name="Example User",
                discount_code="SUMMER10",
                custom_data={"plan_id": "momentum"},
                redirect_url="https://app.userunr.com/pricing?checkout=success&plan_id=momentum",
            )

        self.assertEqual(checkout_url, "https://checkout.example/session")
        request_mock.assert_called_once()
        method, path = request_mock.call_args.args
        payload = request_mock.call_args.kwargs["payload"]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/checkouts")
        self.assertEqual(payload["customer"], {"email": "user@example.com"})
        self.assertNotIn("name", payload["customer"])
        self.assertEqual(payload["discount_code"], "SUMMER10")
        self.assertEqual(payload["metadata"]["user_id"], "user_123")
        self.assertEqual(payload["metadata"]["plan_id"], "momentum")

    def test_redirect_signature_accepts_success_url_ui_params(self):
        creem_query = (
            "request_id=runr_user_123_abcd&checkout_id=ch_123&subscription_id=sub_123&"
            "product_id=prod_123&customer_id=cust_123"
        )
        signed_payload = creem_query.replace("&", "|")
        signature = hashlib.sha256(f"{signed_payload}|salt=creem_test_secret".encode("utf-8")).hexdigest()
        full_query = f"checkout=success&plan_id=momentum&{creem_query}&signature={signature}"

        verify_redirect_signature(full_query, api_key="creem_test_secret")


if __name__ == "__main__":
    unittest.main()

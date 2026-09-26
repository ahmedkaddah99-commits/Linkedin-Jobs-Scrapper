from runr_automation.redaction import redact, redact_text


def test_redaction_removes_sensitive_values_from_payloads_and_text() -> None:
    payload = {
        "issue": "RUN-42",
        "token": "example-linear-token",
        "nested": {"api_key": "example-provider-key"},
        "items": [{"authorization": "Bearer example-bearer-token"}],
    }

    redacted_payload = redact(payload)
    redacted_text = redact_text(
        "Authorization: Bearer example-bearer-token OPENROUTER_API_KEY=example-openrouter-key"
    )

    assert redacted_payload["issue"] == "RUN-42"
    assert redacted_payload["token"] == "[REDACTED]"
    assert redacted_payload["nested"]["api_key"] == "[REDACTED]"
    assert redacted_payload["items"][0]["authorization"] == "[REDACTED]"
    assert "example-bearer-token" not in redacted_text
    assert "example-openrouter-key" not in redacted_text

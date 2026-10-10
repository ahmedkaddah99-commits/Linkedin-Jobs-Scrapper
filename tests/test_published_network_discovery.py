from unittest.mock import Mock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.capabilities.networking.email_lookup import find_work_email
from scripts.process_published_network_discovery import discover
from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore


def test_one_pass_accepts_only_profiles_present_in_web_results():
    html = '''<div class="result"><a class="result__a" href="https://www.linkedin.com/in/alex-example">Alex Example - Acme</a><div class="result__snippet">Engineering Manager at Acme</div></div>'''
    response = Mock(status_code=200, text=html)
    response.raise_for_status.return_value = None
    with patch("scripts.process_published_network_discovery.requests.Session") as session:
        session.return_value.get.return_value = response
        generate = Mock(return_value={"people": [
            {"name": "Alex Example", "role": "Engineering Manager", "linkedin_url": "https://www.linkedin.com/in/alex-example"},
            {"name": "Invented Person", "role": "Hiring Manager", "linkedin_url": "https://www.linkedin.com/in/invented"},
        ]})
        result = discover({"company": "Acme", "title": "Engineer", "location": "Berlin"}, generate,
                          proxy_url="http://proxy.invalid:80")
    assert result["state"] == "available"
    assert [person["name"] for person in result["candidates"]] == ["Alex Example"]
    assert session.return_value.get.call_count == 1
    assert generate.call_count == 1


def test_email_lookup_uses_linkedin_handle_only_and_never_guesses(monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "example")
    with patch("backend.capabilities.networking.email_lookup.requests.get") as get:
        get.return_value.json.return_value = {"data": {"email": None}}
        get.return_value.raise_for_status.return_value = None
        assert find_work_email("https://www.linkedin.com/in/alex-example/")["state"] == "not_found"
        assert get.call_args.kwargs["params"]["linkedin_handle"] == "alex-example"
        assert get.call_args.args[0].endswith("/email-finder/found")
    with pytest.raises(ValueError):
        find_work_email("https://example.com/in/alex-example")


def test_email_lookups_are_user_scoped_cached_and_limited():
    with TemporaryDirectory() as directory:
        store = SqlitePersonalizedJobsStore(Path(directory) / "runr.db")
        assert store.reserve_email_lookup("user-a", "alex") == {"state": "reserved"}
        store.complete_email_lookup("user-a", "alex", "found", "alex@example.com")
        assert store.reserve_email_lookup("user-a", "alex") == {"state": "found", "email": "alex@example.com"}
        assert store.reserve_email_lookup("user-a", "sam") == {"state": "reserved"}
        assert store.reserve_email_lookup("user-a", "third") == {"state": "limit_reached"}
        assert store.reserve_email_lookup("user-b", "third") == {"state": "reserved"}

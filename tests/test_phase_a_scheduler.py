import tempfile
import unittest
from pathlib import Path

from backend.bootstrap import create_backend


class _Response:
    def __init__(self, *, url, status_code=200, payload=None, text=""):
        self.url = url
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._payload


class PhaseASchedulerTests(unittest.TestCase):
    def test_worker_owned_cycle_records_connector_fixture_and_bounded_probes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.phase_a.global_enabled", True)
            app.repositories.config_store.set_value("acquisition.phase_a.connector_validation_enabled", True)
            app.repositories.config_store.set_value("acquisition.phase_a.scheduler_enabled", True)
            app.repositories.config_store.set_value("acquisition.phase_a.publication_enabled", True)
            for target_id in ("siemens", "basf", "bosch", "dhl", "adidas", "n26_greenhouse", "qonto_lever"):
                app.repositories.config_store.set_value(f"acquisition.phase_a.target.{target_id}.enabled", True)
            requests = []

            def requester(url, **kwargs):
                requests.append((url, kwargs))
                if "greenhouse.io" in url:
                    return _Response(
                        url=url,
                        payload={
                            "jobs": [
                                {
                                    "id": 101,
                                    "title": "Operations Analyst",
                                    "absolute_url": "https://boards.greenhouse.io/n26/jobs/101",
                                    "location": {"name": "Berlin"},
                                    "updated_at": "2026-08-01T00:00:00Z",
                                    "content": "Own operational reporting.",
                                }
                            ]
                        },
                    )
                if "lever.co" in url:
                    return _Response(
                        url=url,
                        payload=[
                            {
                                "id": "q-1",
                                "text": "Operations Specialist",
                                "hostedUrl": "https://jobs.lever.co/qonto/q-1",
                                "categories": {"location": "Paris"},
                                "descriptionPlain": "Improve operations.",
                            }
                        ],
                    )
                return _Response(url=url, text="Careers and jobs opportunities")

            app._acquisition_scheduler.requester = requester
            report = app.run_due_acquisition()

            self.assertIsNotNone(report)
            self.assertEqual(report["cycle"]["status"], "completed")
            self.assertEqual(len(requests), 7)
            self.assertEqual(
                [request[0] for request in requests[:2]],
                [
                    "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true",
                    "https://api.lever.co/v0/postings/qonto?mode=json",
                ],
            )
            self.assertEqual(
                {request[0] for request in requests},
                {
                    "https://www.siemens.com/en-us/company/jobs",
                    "https://basf.jobs/",
                    "https://jobs.bosch.de/",
                    "https://careers.dhl.com/eu/de",
                    "https://careers.adidas-group.com/",
                    "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true",
                    "https://api.lever.co/v0/postings/qonto?mode=json",
                },
            )
            self.assertEqual(report["publication"]["published"], False)
            catalog = app.get_public_acquisition_catalog()
            self.assertEqual(catalog["jobs"], [])
            self.assertEqual(catalog["freshness"], "unpublished")
            target_report = {item["target_id"]: item for item in report["targets"]}
            self.assertEqual(target_report["n26_greenhouse"]["maturity_state"], "productive")
            self.assertEqual(target_report["qonto_lever"]["maturity_state"], "productive")
            self.assertEqual(target_report["siemens"]["maturity_state"], "candidate")
            self.assertEqual(target_report["n26_greenhouse"]["requests"][0]["status"], "completed")
            self.assertEqual(target_report["n26_greenhouse"]["task"]["jobs_new"], 1)
            self.assertIsNone(app.run_due_acquisition())


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.acquisition.manifest import (
    PHASE_A_TARGETS,
    canonicalize_target_url,
    load_phase_a_manifest,
)


class PhaseAAcquisitionManifestTests(unittest.TestCase):
    def test_manifest_contains_resolved_employer_pilot_and_connector_fixtures(self):
        manifest = load_phase_a_manifest()
        targets = {item["target_id"]: item for item in manifest}

        self.assertEqual(
            {targets[name]["display_name"] for name in ("siemens", "basf", "bosch", "dhl", "adidas")},
            {
                "Siemens Industry Software",
                "BASF",
                "Bosch",
                "Deutsche Post/DHL",
                "adidas",
            },
        )
        self.assertEqual(targets["bosch"]["canonical_target_url"], "https://jobs.bosch.de/")
        self.assertEqual(targets["bosch"]["provenance_url"], "https://www.bosch.de/karriere/")
        self.assertEqual(targets["basf"]["canonical_target_url"], "https://basf.jobs/")
        self.assertEqual(
            targets["n26_greenhouse"]["request_url"], "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true"
        )
        self.assertEqual(targets["qonto_lever"]["request_url"], "https://api.lever.co/v0/postings/qonto?mode=json")
        self.assertFalse(any(item["target_id"] in {"abb", "continental", "infineon"} for item in manifest))

    def test_canonicalize_target_url_strips_tracking_parameters_but_preserves_locale(self):
        self.assertEqual(
            canonicalize_target_url("https://basf.jobs/?locale=en_US&utm_source=careersite&utm_medium=global_en"),
            "https://basf.jobs/?locale=en_US",
        )
        self.assertEqual(canonicalize_target_url("https://jobs.bosch.de/?utm_campaign=pilot"), "https://jobs.bosch.de/")


if __name__ == "__main__":
    unittest.main()

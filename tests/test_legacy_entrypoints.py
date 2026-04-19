import unittest

import bc_automation.orchestrator_blue_collar as blue_orchestrator
import cv_profile
import job_dedupe
import job_models
import job_seeker_config
import main
import orchestrator
from backend.compat import run_blue_collar_orchestrator, run_legacy_main, run_root_orchestrator
from backend.config.job_seeker import cfg_str, load_job_seeker_config
from backend.domain.job_identity import canonicalize_url, dedupe_job_records
from backend.domain.pipeline_jobs import PipelineJob, normalize_job_record, stable_manual_job_id
from backend.profiles.cv_text import load_cv_text


class LegacyEntrypointTests(unittest.TestCase):
    def test_root_compatibility_entrypoints_delegate_to_backend(self):
        self.assertIs(main.main, run_legacy_main)
        self.assertIs(orchestrator.main, run_root_orchestrator)
        self.assertIs(blue_orchestrator.main, run_blue_collar_orchestrator)

    def test_shared_root_wrappers_delegate_to_backend_modules(self):
        self.assertIs(cv_profile.load_cv_text, load_cv_text)
        self.assertIs(job_models.PipelineJob, PipelineJob)
        self.assertIs(job_models.normalize_job_record, normalize_job_record)
        self.assertIs(job_models.stable_manual_job_id, stable_manual_job_id)
        self.assertIs(job_dedupe.canonicalize_url, canonicalize_url)
        self.assertIs(job_dedupe.dedupe_job_records, dedupe_job_records)
        self.assertIs(job_seeker_config.load_job_seeker_config, load_job_seeker_config)
        self.assertIs(job_seeker_config.cfg_str, cfg_str)


if __name__ == "__main__":
    unittest.main()

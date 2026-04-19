import shutil
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

from backend.capabilities.reusable_packages import filtering as stage2_module
from backend.capabilities.reusable_packages import packaging as stage5_module
from backend.capabilities.reusable_packages import reusable_profiles as stage4_module
from backend.capabilities.reusable_packages.support import load_blue_collar_config


class BlueCollarServiceTests(unittest.TestCase):
    def _workspace_tempdir(self, name: str) -> Path:
        path = REPO_ROOT / ".backend_test_tmp" / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_stage2_pipeline_runs_in_memory(self):
        config = load_blue_collar_config()
        temp_dir = self._workspace_tempdir("blue_stage2_service")
        args = stage2_module.build_stage2_args(
            config,
            overrides={
                "output": str(temp_dir / "approved.json"),
                "rejected": str(temp_dir / "rejected.json"),
                "cities": ["Erlangen"],
            },
        )
        jobs = [
            {
                "job_id": "job_1",
                "title": "Warehouse Helper",
                "location_raw": "Erlangen",
                "description": "",
                "snippet": "",
            },
            {
                "job_id": "job_2",
                "title": "Delivery Driver",
                "location_raw": "Munich",
                "description": "",
                "snippet": "",
            },
        ]

        result = stage2_module.run_stage2_pipeline(args, config=config, jobs=jobs)

        self.assertEqual(len(result["approved_jobs"]), 1)
        self.assertEqual(len(result["rejected_jobs"]), 1)
        self.assertTrue((temp_dir / "approved.json").exists())
        self.assertTrue((temp_dir / "rejected.json").exists())

    def test_stage4_and_stage5_run_in_memory(self):
        config = load_blue_collar_config()
        temp_dir = self._workspace_tempdir("blue_stage45_service")
        jobs = [
            {
                "job_id": "job_warehouse_1",
                "title": "Lagerhelfer",
                "company": "ACME Logistics",
                "location_raw": "Erlangen",
                "portal": "indeed",
                "link": "https://example.com/job/1",
                "apply_link": "https://example.com/apply/1",
                "role_category_id": "warehouse_logistics",
                "role_category_name": "Warehouse / Logistics",
                "classification_source": "test",
            }
        ]

        stage4_args = stage4_module.build_stage4_args(
            config,
            overrides={
                "role_cv_output_dir": str(temp_dir / "role_cvs"),
                "role_cv_index_json": str(temp_dir / "stage4_role_cvs.json"),
            },
        )
        stage4_result = stage4_module.run_stage4_pipeline(stage4_args, config=config, jobs=jobs)

        self.assertGreater(len(stage4_result["role_cv_records"]), 0)
        self.assertTrue((temp_dir / "stage4_role_cvs.json").exists())

        stage5_args = stage5_module.build_stage5_args(
            config,
            overrides={
                "output_json": str(temp_dir / "stage5_packages.json"),
                "output_xlsx": str(temp_dir / "stage5_packages.xlsx"),
                "docs_dir": str(temp_dir / "generated_docs"),
                "run_date": "2026-04-16",
            },
        )
        stage5_result = stage5_module.run_stage5_pipeline(
            stage5_args,
            config=config,
            jobs=jobs,
            role_index_payload=stage4_result["role_cv_index"],
        )

        self.assertEqual(len(stage5_result["records"]), 1)
        self.assertTrue((temp_dir / "stage5_packages.json").exists())
        self.assertTrue((temp_dir / "stage5_packages.xlsx").exists())

        record = stage5_result["records"][0]
        self.assertTrue(Path(record["assigned_cv_txt"]).exists())
        self.assertTrue(Path(record["email_draft_path"]).exists())


if __name__ == "__main__":
    unittest.main()

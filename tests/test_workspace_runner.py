import unittest

from workspace_runner import _runtime_worker_id


class WorkspaceRunnerTests(unittest.TestCase):
    def test_production_worker_identity_is_scoped_to_runtime_host(self):
        first_worker_id = _runtime_worker_id(
            "render_worker",
            default_prefix="cli_worker",
            runtime_environment="production",
            host_name="runr-worker-instance-a",
        )
        second_worker_id = _runtime_worker_id(
            "render_worker",
            default_prefix="cli_worker",
            runtime_environment="production",
            host_name="runr-worker-instance-b",
        )

        self.assertEqual(first_worker_id, "render_worker_runr-worker-instance-a")
        self.assertEqual(second_worker_id, "render_worker_runr-worker-instance-b")
        self.assertNotEqual(first_worker_id, second_worker_id)

    def test_non_production_worker_identity_preserves_configured_id(self):
        self.assertEqual(
            _runtime_worker_id(
                "local_worker",
                default_prefix="cli_worker",
                runtime_environment="development",
                host_name="developer-laptop",
            ),
            "local_worker",
        )

    def test_unconfigured_worker_identity_remains_unique_without_host_suffix(self):
        first_worker_id = _runtime_worker_id(
            "",
            default_prefix="cli_worker",
            runtime_environment="production",
            host_name="runr-worker-instance-a",
        )
        second_worker_id = _runtime_worker_id(
            "",
            default_prefix="cli_worker",
            runtime_environment="production",
            host_name="runr-worker-instance-a",
        )

        self.assertRegex(first_worker_id, r"^cli_worker_[0-9a-f]{8}$")
        self.assertRegex(second_worker_id, r"^cli_worker_[0-9a-f]{8}$")
        self.assertNotEqual(first_worker_id, second_worker_id)


if __name__ == "__main__":
    unittest.main()

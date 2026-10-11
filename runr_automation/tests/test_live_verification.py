import json
import os
import subprocess
import sys
from pathlib import Path


def test_verify_provider_runs_controller_subprocess_and_is_restart_safe(tmp_path: Path) -> None:
    local_app_data = tmp_path / "local"
    config_dir = local_app_data / "RunrAutomation"
    config_dir.mkdir(parents=True)
    provider_script = tmp_path / "fake_provider.py"
    calls = tmp_path / "provider-calls.txt"
    provider_script.write_text(
        """from pathlib import Path
import sys
worktree = Path(sys.argv[1])
target = worktree / 'src' / 'result.txt'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('Runr codex controller smoke passed.\\n', encoding='utf-8')
with Path(sys.argv[2]).open('a', encoding='utf-8') as stream:
    stream.write('called\\n')
print('session id: fake-session')
""",
        encoding="utf-8",
    )
    command = [sys.executable, str(provider_script), "{cwd}", str(calls)]
    (config_dir / "config.yaml").write_text(
        "providers:\n"
        "  order: [codex]\n"
        "  codex:\n"
        f"    command: {json.dumps(command)}\n"
        "    model: fake-model\n",
        encoding="utf-8",
    )
    package_src = Path(__file__).parents[1] / "src"
    environment = {
        **os.environ,
        "LOCALAPPDATA": str(local_app_data),
        "PYTHONPATH": str(package_src),
    }
    args = [
        sys.executable,
        "-m",
        "runr_automation.cli",
        "--repo-root",
        str(tmp_path),
        "verify-provider",
        "codex",
        "--run-id",
        "subprocess-e2e",
    ]

    first = subprocess.run(args, env=environment, capture_output=True, text=True, check=False)
    second = subprocess.run(args, env=environment, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_report = json.loads(first.stdout)
    second_report = json.loads(second.stdout)
    assert first_report["status"] == "awaiting_approval"
    assert first_report["tests_passed"] is True
    assert first_report["clean_worktree"] is True
    assert second_report["processed_jobs"] == 0
    assert calls.read_text(encoding="utf-8").splitlines() == ["called"]
    assert Path(first_report["runtime_root"]).is_relative_to(config_dir)

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"


def _read_unit(name: str) -> str:
    return (SYSTEMD / name).read_text(encoding="utf-8")


def test_runtime_contract_selects_systemd_and_keeps_unmeasured_values_explicit() -> None:
    contract = json.loads((ROOT / "deploy" / "vps-runtime-contract.json").read_text(encoding="utf-8"))

    assert contract["schema_version"] == "runr.vps-runtime.v1"
    assert contract["primary_mechanism"] == "systemd"
    assert contract["release"]["compatibility_contract"] == "runr-contract-v1"
    assert contract["host_policy"]["python_version"] == "3.12.7"
    assert contract["host_policy"]["public_scraper_api"] is False
    assert contract["host_policy"]["inbound_ports"] == []
    assert contract["resource_policy"]["ram_headroom_percent"] == 25
    assert contract["resource_policy"]["monthly_price_eur"] is None
    assert contract["resource_policy"]["provider_limits"] is None


def test_acquisition_role_has_a_separate_environment_boundary() -> None:
    acquisition = _read_unit("runr-acquisition-worker.service")
    example = (ROOT / "deploy" / "acquisition.env.example").read_text(encoding="utf-8")

    assert "EnvironmentFile=/opt/runr/.env.acquisition" in acquisition
    assert "User=runr-acquisition" in acquisition
    assert "Group=runr-acquisition" in acquisition
    assert "Environment=WORKER_ROLE=acquisition" in acquisition
    assert "Environment=WORKER_ID=vps_acquisition_worker" in acquisition
    assert "Environment=RUNR_SKIP_PROJECT_DOTENV=1" in acquisition
    assert "EnvironmentFile=/opt/runr/.env\n" not in acquisition
    assert "CLERK_" not in example
    assert "CREEM_" not in example
    assert "TRACKER_GOOGLE_OAUTH_" not in example
    assert "DEEPSEEK_" not in example


def test_systemd_units_use_non_root_runtime_and_bounded_resources() -> None:
    for name in ("runr-api.service", "runr-worker.service", "runr-frontend.service"):
        unit = _read_unit(name)
        assert "User=runr" in unit
        assert "Group=runr" in unit
        assert "UMask=0077" in unit
        assert "NoNewPrivileges=true" in unit
        assert "ProtectSystem=strict" in unit
        assert "ProtectHome=true" in unit
        assert "TasksMax=" in unit

    acquisition = _read_unit("runr-acquisition-worker.service")
    assert "User=runr-acquisition" in acquisition
    assert "Group=runr-acquisition" in acquisition
    assert "User=root" not in acquisition
    assert "CPUQuota=300%" in acquisition
    assert "MemoryHigh=6G" in acquisition
    assert "MemoryMax=9G" in acquisition
    assert "ReadWritePaths=/var/lib/runr /srv/runr/state /srv/runr/exports /srv/runr/backups /var/log/runr/acquisition" in acquisition
    assert "Environment=RUNR_WORKER_LOG_DIR=/var/log/runr/acquisition" in acquisition

    customer = _read_unit("runr-worker.service")
    assert "Environment=RUNR_WORKER_LOG_DIR=/var/log/runr/customer" in customer
    assert "ReadWritePaths=/var/lib/runr /var/log/runr/customer" in customer


def test_runtime_setup_pins_python_and_installs_all_role_units() -> None:
    setup = (ROOT / "deploy" / "setup.sh").read_text(encoding="utf-8")
    deploy = (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    start = (ROOT / "deploy" / "start.sh").read_text(encoding="utf-8")

    assert 'EXPECTED_PYTHON_VERSION="Python 3.12.7"' in setup
    assert 'python3.12-venv' in setup
    assert '"$INSTALL_DIR/.venv/bin/python" -m pip install' in setup
    assert 'sudo "$python_bin" -m pip install' in deploy
    for script in (setup, deploy):
        assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in script
        assert "-m playwright install --with-deps chromium" in script
    assert "Environment=PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in _read_unit("runr-acquisition-worker.service")
    assert 'runr-acquisition-worker.service' in setup
    assert 'runr-journald.conf' in setup
    assert '/var/log/runr/customer' in setup
    assert '/var/log/runr/acquisition' in setup
    assert 'RUNR_API_HOST:-0.0.0.0' in start


def test_logs_are_bounded_and_application_target_includes_independent_acquisition_timers() -> None:
    journald = _read_unit("runr-journald.conf")
    target = _read_unit("runr.target")

    assert "SystemMaxUse=1G" in journald
    assert "RuntimeMaxUse=256M" in journald
    assert "MaxRetentionSec=14day" in journald
    # The legacy acquisition worker is intentionally outside the target (C6).
    assert "runr-acquisition-worker.service" not in target
    for timer in (
        "runr-acquisition-linkedin.timer",
        "runr-acquisition-employer.timer",
        "runr-acquisition-publisher.timer",
    ):
        assert timer in target


def test_scheduled_backup_unit_is_hardened_non_root_and_uploads_before_prune() -> None:
    unit = _read_unit("runr-acquisition-backup.service")

    assert "Type=oneshot" in unit
    assert "User=runr-acquisition" in unit
    assert "Group=runr-acquisition" in unit
    assert "User=root" not in unit
    assert "EnvironmentFile=/opt/runr/.env.acquisition" in unit
    assert "UMask=0077" in unit
    assert "NoNewPrivileges=true" in unit
    assert "PrivateTmp=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ProtectHome=true" in unit
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in unit
    assert "ReadWritePaths=/srv/runr/state /srv/runr/backups" in unit
    assert "scripts/acquisition_state_backup.py scheduled-backup" in unit
    assert unit.count("scheduled-backup --role linkedin") == 1
    assert unit.count("scheduled-backup --role employer") == 1
    assert "--upload" in unit
    assert "TimeoutStartSec=4h" in unit


def test_backup_timer_is_a_bounded_daily_schedule() -> None:
    timer = _read_unit("runr-acquisition-backup.timer")

    assert "OnCalendar=*-*-* 05:00:00" in timer
    assert "Persistent=true" in timer
    assert "RandomizedDelaySec=300" in timer
    assert "Unit=runr-acquisition-backup.service" in timer
    assert "WantedBy=timers.target" in timer


def test_setup_installs_and_enables_the_backup_schedule() -> None:
    setup = (ROOT / "deploy" / "setup.sh").read_text(encoding="utf-8")

    assert "runr-acquisition-backup.service" in setup
    assert "runr-acquisition-backup.timer" in setup
    assert "sudo systemctl enable --now runr-acquisition-backup.timer" in setup


def test_runtime_contract_owns_the_backup_schedule_and_retention() -> None:
    contract = json.loads((ROOT / "deploy" / "vps-runtime-contract.json").read_text(encoding="utf-8"))
    acquisition = contract["roles"]["acquisition"]

    assert acquisition["backup_unit"] == "runr-acquisition-backup.service"
    assert acquisition["backup_timer"] == "runr-acquisition-backup.timer"
    assert "scripts/acquisition_state_backup.py" in acquisition["backup_entrypoint"]
    assert contract["retention"]["backup_local_generations_min"] >= 2
    assert contract["retention"]["backup_remote_generations_min"] >= 2
    assert contract["retention"]["backup_prune_requires_verified_off_host_receipt"] is True
    assert contract["retention"]["backup_object_prefix"] == "runr/acquisition/checkpoints"


def test_acquisition_env_example_declares_backup_configuration_without_secret_drift() -> None:
    example = (ROOT / "deploy" / "acquisition.env.example").read_text(encoding="utf-8")

    assert "RUNR_ACQUISITION_BACKUP_ROOT=/srv/runr/backups" in example
    assert "RUNR_ACQUISITION_BACKUP_REMOTE_PREFIX=runr/acquisition/checkpoints" in example
    assert "RUNR_ACQUISITION_BACKUP_LOCAL_KEEP=3" in example
    assert "RUNR_ACQUISITION_BACKUP_REMOTE_KEEP=7" in example
    assert "CLERK_" not in example
    assert "CREEM_" not in example
    assert "TRACKER_GOOGLE_OAUTH_" not in example
    assert "DEEPSEEK_" not in example
def test_vps_acquisition_units_run_as_dedicated_user_with_hardening() -> None:
    for name in (
        "runr-acquisition-linkedin.service",
        "runr-acquisition-employer.service",
        "runr-acquisition-publisher.service",
    ):
        unit = _read_unit(name)
        assert "User=runr-acquisition" in unit
        assert "Group=runr-acquisition" in unit
        assert "UMask=0077" in unit
        assert "NoNewPrivileges=true" in unit
        assert "PrivateTmp=true" in unit
        assert "ProtectSystem=strict" in unit
        assert "ProtectHome=true" in unit
        assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in unit
        assert "ReadWritePaths=/var/lib/runr /srv/runr/state /srv/runr/exports /srv/runr/backups" in unit


def test_vps_acquisition_producer_command_lines_and_timer_ownership() -> None:
    linkedin = _read_unit("runr-acquisition-linkedin.service")
    employer = _read_unit("runr-acquisition-employer.service")
    publisher = _read_unit("runr-acquisition-publisher.service")

    assert "ExecStart=/opt/runr/deploy/run-acquisition-source.sh linkedin" in linkedin
    assert "ExecStart=/opt/runr/deploy/run-acquisition-source.sh employer" in employer
    assert "ExecStart=/opt/runr/deploy/run-acquisition-publisher.sh" in publisher

    for unit in (linkedin, employer, publisher):
        assert "PartOf=runr.target" in unit
        assert "WantedBy=multi-user.target" in unit[-100:]

    timers = {
        "runr-acquisition-linkedin.timer": ("Unit=runr-acquisition-linkedin.service", "OnCalendar=*-*-* 02:00:00"),
        "runr-acquisition-employer.timer": ("Unit=runr-acquisition-employer.service", "OnCalendar=*-*-* 02:30:00"),
        "runr-acquisition-publisher.timer": ("Unit=runr-acquisition-publisher.service", "OnCalendar=*-*-* 04:00:00"),
    }
    for name, (unit_line, schedule) in timers.items():
        timer = _read_unit(name)
        assert unit_line in timer
        assert schedule in timer
        assert "Persistent=true" in timer
        assert "RandomizedDelaySec=300" in timer


def test_vps_acquisition_units_load_acquisition_env_boundary() -> None:
    for name in (
        "runr-acquisition-linkedin.service",
        "runr-acquisition-employer.service",
        "runr-acquisition-publisher.service",
    ):
        unit = _read_unit(name)
        assert "EnvironmentFile=/opt/runr/.env.acquisition" in unit
        assert "EnvironmentFile=/opt/runr/.env\n" not in unit
        assert "CLERK_" not in unit
        assert "CREEM_" not in unit

    linkedin = _read_unit("runr-acquisition-linkedin.service")
    employer = _read_unit("runr-acquisition-employer.service")
    assert "EnvironmentFile=-/opt/runr/.env.acquisition.provider" in linkedin
    assert "EnvironmentFile=-/opt/runr/.env.acquisition.provider" in employer

    # Live-network override is hard-coded in the producer units (C4); the
    # .env.acquisition default remains the fail-closed value.
    assert "Environment=RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=true" in linkedin
    assert "Environment=RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=true" in employer


def test_vps_acquisition_env_intends_turso_and_source_version_placeholder() -> None:
    example = (ROOT / "deploy" / "acquisition.env.example").read_text(encoding="utf-8")
    assert "DATABASE_BACKEND=turso" in example
    assert "TURSO_DATABASE_URL=replace-with-secret-store-reference" in example
    assert "TURSO_AUTH_TOKEN=replace-with-secret-store-reference" in example
    assert "RUNR_SOURCE_VERSION=replace-with-deployed-git-sha" in example


def test_render_customer_plane_intends_turso_and_release_branch() -> None:
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    # Each Render service must target the same release branch/contract.
    assert render.count("key: RUNR_RELEASE_BRANCH") == 3
    assert render.count("value: deployment/render-turso-r2") == 3
    assert render.count("key: RUNR_RELEASE_CONTRACT_VERSION") == 3
    assert render.count("value: runr-contract-v1") == 3
    # Both API and worker bind to the shared Turso catalog.
    assert render.count("key: DATABASE_BACKEND") == 2
    assert render.count("value: turso") == 2
    assert render.count("key: RUNR_STORAGE_BACKEND") == 2
    assert render.count("value: sqlite") == 2
    # Acquisition must never run on Render.
    assert render.count('RUNR_ACQUISITION_LIVE_NETWORK_ENABLED\n        value: "false"') == 2
    assert render.count('RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY\n        value: "false"') == 2
    assert render.count('RUNR_COMPANY_ENRICHMENT_ENABLED\n        value: "0"') == 2


def test_target_declares_one_owner_per_acquisition_schedule() -> None:
    target = _read_unit("runr.target")
    manifest = _schedule_manifest()

    assert manifest["schema_version"] == "runr.acquisition.schedule-manifest.v1"
    schedules = manifest["schedules"]
    assert isinstance(schedules, dict)
    assert set(schedules) == {"linkedin", "employer", "publisher"}
    assert len({schedule["owner_timer"] for schedule in schedules.values()}) == 3
    assert len({schedule["owner_service"] for schedule in schedules.values()}) == 3
    assert manifest["runtime_contract"]["overlap"]["exit_code"] == 75
    assert manifest["runtime_contract"]["timeout"]["source_seconds"] == 900

    wants = next(line for line in target.splitlines() if line.startswith("Wants="))
    for schedule in schedules.values():
        assert schedule["owner_timer"] in wants
        timer = _read_unit(schedule["owner_timer"])
        assert f"Unit={schedule['owner_service']}" in timer
        assert f"OnCalendar={schedule['calendar']}" in timer


def test_target_explicitly_disables_stale_acquisition_units() -> None:
    target = _read_unit("runr.target")
    manifest = _schedule_manifest()
    expected = {
        "runr-acquisition-cycle.service",
        "runr-acquisition-cycle.timer",
        "runr-acquisition-export.service",
        "runr-acquisition-export.timer",
        "runr-acquisition-worker.service",
    }
    assert set(manifest["disabled_units"]) == expected
    conflicts = next(line for line in target.splitlines() if line.startswith("Conflicts="))
    assert set(conflicts.removeprefix("Conflicts=").split()) == expected
    wants = next(line for line in target.splitlines() if line.startswith("Wants="))
    assert not expected.intersection(wants.split())


def test_acquisition_units_encode_overlap_and_failure_contract() -> None:
    for name in (
        "runr-acquisition-linkedin.service",
        "runr-acquisition-employer.service",
        "runr-acquisition-publisher.service",
    ):
        unit = _read_unit(name)
        assert "SuccessExitStatus=75" in unit
        assert "TimeoutStartSec=" in unit

    source = (ROOT / "deploy" / "run-acquisition-source.sh").read_text(encoding="utf-8")
    publisher = (ROOT / "deploy" / "run-acquisition-publisher.sh").read_text(encoding="utf-8")
    assert 'lock_file="$lock_root/$source_name.lock"' in source
    assert 'timeout --foreground "$run_timeout"' in source
    assert "exit 75" in source
    assert 'exec 7>"$lock_root/linkedin.lock"' in publisher
    assert 'exec 8>"$lock_root/employer.lock"' in publisher
    assert 'timeout --foreground "$run_timeout" "$python_bin" scripts/publish_producer_states.py' in publisher
    assert "exit 75" in publisher
    assert 'run_timeout="${RUNR_SOURCE_RUN_TIMEOUT_SECONDS:-900}"' in source
    assert 'run_timeout="${RUNR_PUBLISHER_RUN_TIMEOUT_SECONDS:-900}"' in publisher

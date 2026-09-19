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


def test_logs_are_bounded_and_application_target_includes_acquisition_worker() -> None:
    journald = _read_unit("runr-journald.conf")
    target = _read_unit("runr.target")

    assert "SystemMaxUse=1G" in journald
    assert "RuntimeMaxUse=256M" in journald
    assert "MaxRetentionSec=14day" in journald
    assert "runr-acquisition-worker.service" in target


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

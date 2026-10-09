from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_source_and_publisher_timers_repeat_after_completion():
    for path, interval in (
        ("deploy/systemd/runr-acquisition-linkedin.timer.d/continuous.conf", "OnUnitInactiveSec=10min"),
        ("deploy/systemd/runr-acquisition-employer.timer.d/continuous.conf", "OnUnitInactiveSec=10min"),
        ("deploy/systemd/runr-acquisition-publisher.timer.d/continuous.conf", "OnUnitInactiveSec=1min"),
    ):
        text = (ROOT / path).read_text()
        assert "OnCalendar=" in text
        assert interval in text


def test_manifest_refresh_is_atomic_and_recurring():
    wrapper = (ROOT / "deploy/refresh-acquisition-manifest.sh").read_text()
    assert 'ln -s "$generation" "$active.new"' in wrapper
    assert 'mv -Tf "$active.new" "$active"' in wrapper
    assert "load_manifest" in wrapper
    timer = (ROOT / "deploy/systemd/runr-acquisition-manifest-refresh.timer").read_text()
    assert "OnUnitInactiveSec=6h" in timer


def test_lock_contention_is_retry_and_employer_batch_is_bounded():
    linkedin = (ROOT / "deploy/systemd/runr-acquisition-linkedin.service.d/lock-retry.conf").read_text()
    employer = (ROOT / "deploy/systemd/runr-acquisition-employer.service.d/continuous-bounds.conf").read_text()
    assert "SuccessExitStatus=75" in linkedin
    assert "SuccessExitStatus=75" in employer
    assert "RUNR_EMPLOYER_MAX_COMPANIES=10" in employer

import pytest

from runr_automation.lock import ControllerLock, LockUnavailable


def test_controller_lock_allows_one_owner(tmp_path) -> None:
    lock_path = tmp_path / "controller.lock"
    first = ControllerLock(lock_path)
    second = ControllerLock(lock_path)

    with first:
        with pytest.raises(LockUnavailable):
            second.acquire()

    second.acquire()
    second.release()

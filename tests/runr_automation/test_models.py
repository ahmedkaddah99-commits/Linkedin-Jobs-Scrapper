from tools.runr_automation.models import JobRecord, JobStatus


def test_job_record_has_durable_lease_defaults() -> None:
    job = JobRecord(
        job_id="job-1",
        job_type="normalize",
        issue_id="linear-1",
        desired_state_fingerprint="fingerprint-1",
    )

    assert job.status is JobStatus.QUEUED
    assert job.priority == 0
    assert job.attempt_count == 0
    assert job.lease_owner is None
    assert job.lease_expires_at is None

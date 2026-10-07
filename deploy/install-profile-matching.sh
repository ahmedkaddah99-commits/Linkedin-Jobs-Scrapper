#!/usr/bin/env bash
set -euo pipefail
artifact=${1:?archive path required}
commit=${2:?commit required}
digest=${3:?archive SHA256 required}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || exit 64
[[ "$digest" =~ ^[0-9a-f]{64}$ ]] || exit 64
[[ "$(/opt/runr/.venv/bin/python --version)" == "Python 3.12.7" ]] || exit 65
[[ "$(sha256sum "$artifact" | cut -d ' ' -f1)" == "$digest" ]] || exit 66
release="/opt/runr-profile-matching/releases/$commit"
mkdir -p "$release"
tar -xf "$artifact" -C "$release"
printf '%s\n' "$commit" > "$release/RELEASE_COMMIT"
chmod -R a+rX "$release"
ln -sfn "$release" /opt/runr-profile-matching/current
install -m 0644 "$release/deploy/systemd/runr-profile-job-facts.service" /etc/systemd/system/
install -m 0644 "$release/deploy/systemd/runr-profile-job-facts.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now runr-profile-job-facts.timer
systemctl start --no-block runr-profile-job-facts.service
systemctl is-enabled runr-profile-job-facts.timer
systemctl is-active runr-profile-job-facts.timer
sha256sum "$release/backend/application/profile_job_matching.py" "$release/scripts/process_profile_job_facts.py"

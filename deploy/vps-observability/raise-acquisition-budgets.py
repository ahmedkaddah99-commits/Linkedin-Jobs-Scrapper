"""Safely raise the owner's finite acquisition limits without exposing env secrets."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PATH = Path('/opt/runr/.env.acquisition')
EXPECTED = {
    'RUNR_LINKEDIN_MAX_REQUESTS': '100',
    'RUNR_LINKEDIN_MAX_COMPANIES': '25',
    'RUNR_EMPLOYER_MAX_REQUESTS': '10',
    'RUNR_EMPLOYER_MAX_COMPANIES': '10',
    'RUNR_ACQUISITION_MAX_REQUESTS': '110',
    'RUNR_SOURCE_RUN_TIMEOUT_SECONDS': '900',
}
TARGET = {
    'RUNR_LINKEDIN_MAX_REQUESTS': '1000',
    'RUNR_LINKEDIN_MAX_COMPANIES': '200',
    'RUNR_EMPLOYER_MAX_REQUESTS': '200',
    'RUNR_EMPLOYER_MAX_COMPANIES': '10',
    'RUNR_ACQUISITION_MAX_REQUESTS': '1200',
    'RUNR_SOURCE_RUN_TIMEOUT_SECONDS': '900',
}


def rewrite(text):
    rows = text.splitlines(keepends=True)
    found = {}
    result = []
    for row in rows:
        key = row.split('=', 1)[0].strip() if '=' in row else ''
        if key not in TARGET or row.lstrip().startswith('#'):
            result.append(row)
            continue
        if key in found:
            raise ValueError('duplicate_budget_key:' + key)
        current = row.split('=', 1)[1].strip().strip('"\'')
        allowed = {EXPECTED[key], TARGET[key]}
        if key == 'RUNR_EMPLOYER_MAX_COMPANIES':
            allowed.add('100')  # superseded live setting that timed out
        if key == 'RUNR_SOURCE_RUN_TIMEOUT_SECONDS':
            allowed.add('3600')  # superseded live setting that delayed recovery
        if current not in allowed:
            raise ValueError('unexpected_budget_value:' + key)
        found[key] = current
        result.append(key + '=' + TARGET[key] + ('\n' if row.endswith('\n') else ''))
    missing = TARGET.keys() - found.keys()
    if missing:
        raise ValueError('missing_budget_keys:' + ','.join(sorted(missing)))
    return ''.join(result)


def main():
    if sys.platform != 'linux' or not PATH.is_file():
        raise SystemExit('VPS budget file not found')
    units = ('runr-acquisition-linkedin.service', 'runr-acquisition-employer.service')
    for unit in units:
        state = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True, check=False).stdout.strip()
        if state in {'active', 'activating'}:
            raise SystemExit('Acquisition source running: ' + unit)
    old = PATH.read_text()
    new = rewrite(old)
    if new == old:
        print('Finite acquisition budgets already at target')
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = PATH.with_name(PATH.name + '.before-budget-' + stamp)
    shutil.copy2(PATH, backup)
    stat = PATH.stat()
    fd, tmpname = tempfile.mkstemp(prefix='.acquisition-budget-', dir=PATH.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(new)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(tmpname, stat.st_mode)
        os.chown(tmpname, stat.st_uid, stat.st_gid)
        os.replace(tmpname, PATH)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)
    print('Budget keys raised: ' + ','.join(TARGET) + '; backup=' + str(backup))


if __name__ == '__main__':
    main()

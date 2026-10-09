"""Copy this operation's receipts/backups locally through SSH without text conversion."""
import subprocess
import sys
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'data/audit/blue_employer_cleanup_2026-10-09'
allowed=('policy-installation.json','policy-verification.json','producer-cleanup.json','linkedin-deleted-jobs.jsonl.gz','employer-deleted-jobs.jsonl.gz')
for name in sys.argv[1:] or allowed:
    assert name in allowed
    data=subprocess.check_output(['ssh','runr-vps','sudo -n cat /srv/runr/ops/blue-employer-cleanup-2026-10-09/'+name],timeout=60)
    (OUT/name).write_bytes(data)
    print(name, len(data))

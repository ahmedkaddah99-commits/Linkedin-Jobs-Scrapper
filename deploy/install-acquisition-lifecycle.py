"""Install one SQLite acquisition release; leave timers paused for acceptance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from dotenv import dotenv_values

release = Path(sys.argv[1]).resolve(strict=True)
commit = sys.argv[2]
assert release.parent == Path('/srv/runr/releases')
sys.path.insert(0, str(release))
from backend.repositories.sqlite_migrations import current_migration_head

evidence = Path('/srv/runr/ops/acquisition-lifecycle') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
evidence.mkdir(parents=True, exist_ok=False)
evidence.chmod(0o700)
values = {}
for filename in ('/etc/runr/description.env','/etc/runr/nemo-enrichment.env','/etc/runr/publisher-sqlite.env'):
    values.update({k:v for k,v in dotenv_values(filename).items() if v is not None})
values.update(DATABASE_BACKEND='sqlite', RUNR_ENV='production',
              SQLITE_DATABASE_PATH='/var/lib/runr/customer-candidate-db/backend.sqlite3',
              TURSO_DATABASE_URL='', TURSO_AUTH_TOKEN='', RUNR_SKIP_PROJECT_DOTENV='1',
              RUNR_MIGRATION_HEAD=current_migration_head(), RUNR_PROJECT_DIR=str(release),
              RUNR_RELEASE_COMMIT=commit, RUNR_SOURCE_VERSION=commit,
              RUNR_RELEASE_BRANCH='implementation/acquisition-lifecycle-2026-10-11',
              RENDER_GIT_BRANCH='', RENDER_GIT_COMMIT='',
              RUNR_PYTHON_BIN='/opt/runr/.venv/bin/python',
              RUNR_ACQUISITION_STATE_ROOT='/srv/runr/state/active',
              RUNR_ACQUISITION_LOCK_ROOT='/srv/runr/state/locks',
              RUNR_EMPLOYER_EXCLUSION_POLICY='/etc/runr/employer-exclusions.json',
              RUNR_ACQUISITION_DATA_MANIFEST=str(release / 'deploy/acquisition-data-manifest.json'))
env_path = Path('/etc/runr/acquisition-lifecycle.env')
if env_path.exists(): shutil.copy2(env_path, evidence / 'environment-before.env')
env_path.write_text(''.join(k+'='+json.dumps(v)+'\n' for k,v in values.items()))
env_path.chmod(0o640)
shutil.chown(env_path, user='root', group='runr-acquisition')
os.environ.update(values)
from backend.database.connection import connect_database
with connect_database(Path(values['SQLITE_DATABASE_PATH'])) as db:
    assert db.execute('SELECT migration_id FROM schema_migrations ORDER BY rowid DESC LIMIT 1').fetchone()[0] == current_migration_head()
assert values.get('OPENROUTER_API_KEY'), 'OpenRouter configuration missing'

commands = {
    'runr-acquisition-linkedin': '/bin/sh '+str(release / 'deploy/run-acquisition-source.sh')+' linkedin',
    'runr-acquisition-employer': '/bin/sh '+str(release / 'deploy/run-acquisition-source.sh')+' employer',
    'runr-acquisition-publisher': '/bin/sh '+str(release / 'deploy/run-acquisition-publisher.sh'),
    'runr-acquisition-manifest-refresh': '/bin/sh '+str(release / 'deploy/refresh-acquisition-manifest.sh'),
    'runr-catalog-publication': '/usr/bin/flock -E 75 -n /srv/runr/state/locks/publisher.lock /opt/runr/.venv/bin/python scripts/process_catalog_publication.py --max-seconds 120 --batch-size 500',
    'runr-job-descriptions': '/usr/bin/flock -E 75 -n /srv/runr/state/description-worker.lock /opt/runr/.venv/bin/python scripts/process_catalog_enrichment.py --workers 16 --max-jobs 4096 --runtime-seconds 1800 --daily-budget 10',
    'runr-job-descriptions-rules': '/usr/bin/flock -E 75 -n /srv/runr/state/description-worker.lock /opt/runr/.venv/bin/python scripts/backfill_published_job_descriptions_rules.py --limit 2000 --page-size 5 --cursor-file /srv/runr/state/description-rules-cursor.json',
    'runr-profile-job-facts': '/usr/bin/flock -E 75 -n /srv/runr/state/profile-job-facts.lock /opt/runr/.venv/bin/python scripts/process_profile_job_facts.py --max-jobs 4096 --runtime-seconds 180',
    'runr-catalog-storage-maintenance': '/bin/sh '+str(release / 'deploy/run-catalog-storage-maintenance.sh'),
}
for unit, command in commands.items():
    destination = Path('/etc/systemd/system') / (unit+'.service.d') / 'zzzzzz-acquisition-lifecycle.conf'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists(): shutil.copy2(destination, evidence / (unit+'.conf'))
    destination.write_text('[Service]\nWorkingDirectory='+str(release)+'\nExecStart=\nExecStart='+command+
        '\nEnvironmentFile='+str(env_path)+'\nSupplementaryGroups=runr-database\nUMask=0007\n'
        'ReadWritePaths=/var/lib/runr /srv/runr/state /srv/runr/exports /srv/runr/backups\nSuccessExitStatus=75\n')
    if unit == 'runr-acquisition-publisher':
        timer_dropin=Path('/etc/systemd/system/runr-acquisition-publisher.timer.d/continuous.conf')
        timer_dropin.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(release / 'deploy/systemd/runr-acquisition-publisher.timer.d/continuous.conf',timer_dropin)
for name in ('runr-job-descriptions.timer','runr-profile-job-facts.timer','runr-job-descriptions-rules.timer'):
    destination = Path('/etc/systemd/system') / name
    if not destination.exists(): shutil.copy2(release / 'deploy/systemd' / name, destination)
unit = Path('/etc/systemd/system/runr-job-lifecycle.service')
unit.write_text('[Unit]\nDescription=Runr rolling thirty-day job retention\n[Service]\nType=oneshot\nUser=runr-acquisition\nGroup=runr-acquisition\nSupplementaryGroups=runr-database\nUMask=0007\nWorkingDirectory='+str(release)+'\nEnvironmentFile='+str(env_path)+
    '\nExecStart=/usr/bin/flock -E 75 -n /srv/runr/state/locks/publisher.lock /opt/runr/.venv/bin/python scripts/maintain_job_lifecycle.py --apply --batch-size 500 --max-batches 1000 --max-seconds 120 --receipt /srv/runr/exports/receipts/job-lifecycle-latest.json\nSuccessExitStatus=75\nTimeoutStartSec=180\nMemoryMax=1G\nCPUQuota=100%\n')
Path('/etc/systemd/system/runr-job-lifecycle.timer').write_text('[Unit]\nDescription=Runr job lifecycle maintenance\n[Timer]\nOnBootSec=2min\nOnUnitInactiveSec=15min\n[Install]\nWantedBy=timers.target\n')
Path('/etc/systemd/system/runr-producer-retention.service').write_text('[Unit]\nDescription=Runr source job payload retention\n[Service]\nType=oneshot\nUser=runr-acquisition\nGroup=runr-acquisition\nUMask=0007\nWorkingDirectory='+str(release)+'\nEnvironmentFile='+str(env_path)+'\nExecStart=/opt/runr/.venv/bin/python scripts/maintain_producer_jobs.py --apply --state-root /srv/runr/state/active --lock-root /srv/runr/state/locks --max-seconds 120 --receipt /srv/runr/exports/receipts/producer-retention-latest.json\nSuccessExitStatus=75\nTimeoutStartSec=300\nMemoryMax=1G\nCPUQuota=100%\n')
Path('/etc/systemd/system/runr-producer-retention.timer').write_text('[Unit]\nDescription=Runr source payload retention schedule\n[Timer]\nOnBootSec=3min\nOnUnitInactiveSec=1h\n[Install]\nWantedBy=timers.target\n')
subprocess.run(['systemctl','daemon-reload'], check=True)
print(json.dumps({'installed':str(release),'commit':commit,'evidence':str(evidence),'timers_resumed':False,'storage':'r2'}))




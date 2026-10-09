"""Run as root on the VPS: isolated policy overlays, preserving existing services."""
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import signal
from pathlib import Path

STAGE = Path('/tmp/runr-blue-employer-policy')
OUT = Path('/srv/runr/ops/blue-employer-cleanup-2026-10-09')


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    # Isolated release preparation leaves running processes on their loaded code.
    # Producer deletion takes source/publisher locks separately.
    signal.alarm(600)
    locks = []
    for name in ('employer-policy-deploy',):
        stream = open(f'/srv/runr/state/locks/{name}.lock','a')
        fcntl.flock(stream, fcntl.LOCK_EX)
        locks.append(stream)
        print(json.dumps({'maintenance_lock_acquired':name}),flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    policy = STAGE/'employer-exclusions.json'
    assert len(json.loads(policy.read_text())['selected_company_ids']) == 555
    policy_target = Path('/etc/runr/employer-exclusions.json')
    if policy_target.exists():
        assert policy_target.read_bytes() == policy.read_bytes(), 'Existing different policy requires reconciliation'
    else:
        shutil.copy2(policy,policy_target)
        policy_target.chmod(0o644)
    receipt = {'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),'services':{}}
    for source in ('linkedin','employer','publisher','catalog-publication'):
        unit = f'runr-acquisition-{source}.service' if source!='catalog-publication' else 'runr-catalog-publication.service'
        old = Path(command('systemctl','show',unit,'-p','WorkingDirectory','--value'))
        suffix='-blue-policy-20261009-v2'
        new = old if old.name.endswith(suffix) else old.with_name(old.name.removesuffix('-blue-policy-20261009')+suffix)
        if not new.exists(): shutil.copytree(old,new,symlinks=True)
        shutil.copy2(STAGE/'employer_acquisition_policy.py',new/'backend/application/employer_acquisition_policy.py')
        module = new/'backend/application/source_eligibility_manifest.py'
        text = module.read_text()
        if 'excluded_company_ids' not in text:
            needle = '    selected: list[dict[str, Any]] = []\n    seen: set[str] = set()\n'
            assert text.count(needle)==1
            text = text.replace(needle,needle+'    from backend.application.employer_acquisition_policy import excluded_company_ids\n    excluded = excluded_company_ids()\n')
            needle = '        seen.add(task_key)\n        selected.append(task)'
            assert text.count(needle)==1
            text = text.replace(needle,'        seen.add(task_key)\n        if canonical_id in excluded:\n            continue\n        selected.append(task)')
            module.write_text(text)
        publisher = new/'scripts/publish_producer_states.py'
        text = publisher.read_text()
        if 'if company_id in excluded_company_ids():' not in text:
            needle = '        company_id = _text(resolve_company_identity(identity_payload, crosswalk or {})) or original_company_id\n'
            assert text.count(needle)==1
            text = text.replace(needle,needle+'        from backend.application.employer_acquisition_policy import excluded_company_ids\n        if company_id in excluded_company_ids():\n            continue\n')
            publisher.write_text(text)
        repository=new/'backend/repositories/sqlite_acquisition.py'
        text=repository.read_text()
        if 'owner_excluded_employer' not in text:
            start=text.index('    def _publication_rows_with_completeness(')
            end=text.index('    @staticmethod',start)
            body=text[start:end]
            needle='        rejected: list[dict[str, Any]] = []\n'
            assert body.count(needle)==1
            body=body.replace(needle,needle+'        from backend.application.employer_acquisition_policy import excluded_company_ids\n        excluded = excluded_company_ids()\n')
            needle='            row = _dict_row(raw_row) if hasattr(raw_row, "keys") else dict(raw_row)\n'
            assert body.count(needle)==1
            body=body.replace(needle,needle+'''            if str(row.get("company_id") or "") in excluded:
                rejected.append({
                    "canonical_job_id": str(row.get("canonical_job_id") or ""),
                    "external_job_id": str(row.get("source_job_id") or ""),
                    "title": str(row.get("title") or ""),
                    "target_id": str(row.get("source_target_id") or "publication"),
                    "task_id": str(row.get("source_task_id") or "publication"),
                    "reasons": [{"code": "owner_excluded_employer", "fields": ["canonical_company_id"]}],
                    "status": "rejected",
                })
                continue
''')
            repository.write_text(text[:start]+body+text[end:])
        check = 'from backend.application.employer_acquisition_policy import excluded_company_ids; from backend.application.source_eligibility_manifest import load_manifest,validate_manifest_for_source; import json; p=load_manifest("/srv/runr/shared/inputs/manifest-generations/active/SOURCE_ELIGIBILITY_MANIFEST.json"); b=excluded_company_ids(); tasks=[t for s in ("linkedin","employer_site") for t in validate_manifest_for_source(p,s,pilot_only=False)]; assert not any(t["canonical_company_id"] in b for t in tasks); print(json.dumps({"excluded_ids":len(b),"remaining_tasks":len(tasks)}))'
        validation = subprocess.check_output([str(new/'.venv/bin/python'),'-c',check],cwd=new,text=True).strip()
        argv = re.search(r'argv\[\]=(.*?) ; ignore_errors=',command('systemctl','show',unit,'-p','ExecStart','--value')).group(1)
        assert str(old) in argv or source=='catalog-publication'
        replacement = argv.replace(str(old),str(new))
        dropin = Path('/etc/systemd/system')/(unit+'.d')/'zzzz-owner-employer-exclusions.conf'
        dropin.parent.mkdir(parents=True,exist_ok=True)
        before=OUT/(source+'-before-unit.txt')
        if not before.exists(): before.write_text(command('systemctl','cat',unit))
        dropin.write_text('[Service]\nWorkingDirectory='+str(new)+'\nExecStart=\nExecStart='+replacement+'\nEnvironment=RUNR_EMPLOYER_EXCLUSION_POLICY=/etc/runr/employer-exclusions.json\n')
        receipt['services'][source] = {'old_release':str(old),'new_release':str(new),'validation':json.loads(validation)}
    command('systemctl','daemon-reload')
    for source in ('linkedin','employer','publisher','catalog-publication'):
        unit=f'runr-acquisition-{source}.service' if source!='catalog-publication' else 'runr-catalog-publication.service'
        assert command('systemctl','show',unit,'-p','WorkingDirectory','--value')==receipt['services'][source]['new_release']
        if source=='catalog-publication': continue
        assert command('systemctl','is-enabled',f'runr-acquisition-{source}.timer')=='enabled'
        assert command('systemctl','is-active',f'runr-acquisition-{source}.timer')=='active'
    (OUT/'policy-installation.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))

if __name__ == '__main__': main()

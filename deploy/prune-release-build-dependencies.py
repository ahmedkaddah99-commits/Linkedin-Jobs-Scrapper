"""Remove reproducible frontend build dependencies from inactive releases only.

Preserves code, lockfiles, built assets, current process releases and three newest
builds. Dry run unless --apply. Does not touch customer data or backups.
"""
import argparse
import json
from pathlib import Path
import shutil

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply',action='store_true')
args=parser.parse_args()
root=Path('/srv/runr/releases').resolve()
active=set()
for process in Path('/proc').glob('[0-9]*'):
    for link in ('cwd','exe'):
        try:
            value=(process/link).resolve(strict=True)
            if value.is_relative_to(root):active.add(root/value.relative_to(root).parts[0])
        except (OSError,RuntimeError):pass
    try:
        command=(process/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        for release in root.iterdir():
            if str(release) in command:active.add(release)
    except OSError:pass
candidates=sorted(root.glob('*/frontend/node_modules'),key=lambda p:p.stat().st_mtime,reverse=True)
protected={p.parents[1] for p in candidates[:3]}|active
removed=[]
for path in candidates:
    release=path.parents[1]
    if release in protected or path.is_symlink():continue
    if not (path.parent/'package-lock.json').is_file() or not (path.parent/'dist/index.html').is_file():continue
    resolved=path.resolve(strict=True)
    assert resolved.is_relative_to(root) and resolved.name=='node_modules' and resolved.parent.name=='frontend'
    removed.append(str(resolved))
    if args.apply:shutil.rmtree(resolved)
print(json.dumps({'applied':args.apply,'build_dependency_directories':removed,'preserved_active_releases':[str(p) for p in sorted(active)],'free_bytes':shutil.disk_usage(root).free}))

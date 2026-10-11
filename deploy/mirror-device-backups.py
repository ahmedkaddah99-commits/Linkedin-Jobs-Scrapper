"""Download a VPS-generated signed manifest. Never deletes remote objects."""
import concurrent.futures
import hashlib
import json
import msvcrt
import shutil
from pathlib import Path, PurePosixPath
import sys
import time
import urllib.request

if sys.version_info[:3] != (3, 12, 7):
    raise RuntimeError('Requires project Python 3.12.7')
root = Path.home() / 'Runr-Historical-Archives' / 'backups'
root.mkdir(parents=True, exist_ok=True)
lock = (root / 'mirror.lock').open('a+b')
lock.seek(0)
if not lock.read(1):
    lock.write(b'0')
    lock.flush()
lock.seek(0)
try:
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
except OSError:
    print('A device backup copy is already running; skipped overlapping run.', flush=True)
    sys.exit(0)
manifest = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
receipt_path = root / 'latest-verified.json'
previous = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {'objects': []}
required = sum(item['bytes'] for item in manifest['objects'])
if shutil.disk_usage(root).free < required + 10 * 1024**3:
    raise RuntimeError('Insufficient device storage for backup set and 10 GiB reserve')

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def download(item):
    relative = PurePosixPath(item['key'])
    if not item['key'].startswith(('runr/acquisition/', 'private/customer-database/backups/', 'private/catalog/backups/')):
        raise ValueError('Object is outside backup prefixes')
    if relative.is_absolute() or '..' in relative.parts or any(':' in part for part in relative.parts):
        raise ValueError('Unsafe object path')
    target = root.joinpath(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    if item['bytes'] == 0:
        if item['sha256'] != hashlib.sha256(b'').hexdigest():
            raise ValueError('Invalid empty object digest')
        target.write_bytes(b'')
        return item['key']
    if target.exists() and target.stat().st_size == item['bytes'] and digest(target) == item['sha256']:
        return item['key']
    partial = target.with_name(target.name + '.partial')
    for attempt in range(8):
        saved = partial.stat().st_size if partial.exists() else 0
        if saved > item['bytes']:
            partial.unlink()
            saved = 0
        if saved == item['bytes']:
            if digest(partial) == item['sha256']:
                partial.replace(target)
                return item['key']
            partial.unlink()
            continue
        try:
            while saved < item['bytes']:
                end = min(saved + 8 * 1024**2, item['bytes']) - 1
                request = urllib.request.Request(item['url'], headers={'Range': f'bytes={saved}-{end}'})
                with urllib.request.urlopen(request, timeout=90) as response:
                    expected = f"bytes {saved}-{end}/{item['bytes']}"
                    if response.status != 206 or response.headers.get('Content-Range') != expected:
                        raise RuntimeError('Unexpected range response')
                    with partial.open('ab') as output:
                        while block := response.read(1024**2):
                            output.write(block)
                observed = partial.stat().st_size
                if observed != end + 1:
                    raise RuntimeError('Incomplete range response')
                saved = observed
        except Exception as error:
            print(f"Retry {attempt + 1}: {item['key']} ({type(error).__name__})", flush=True)
            if attempt == 7:
                raise RuntimeError('Download incomplete: ' + item['key']) from None
            time.sleep(3)
    if not partial.exists() or partial.stat().st_size != item['bytes'] or digest(partial) != item['sha256']:
        raise RuntimeError('Backup verification failed: ' + item['key'])
    partial.replace(target)
    return item['key']

with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    verified = list(pool.map(download, manifest['objects']))
receipt = {'verified_at': time.time(), 'objects': [
    {k: obj[k] for k in ('key', 'bytes', 'sha256')} for obj in manifest['objects']]}
def family_generation(key):
    parts = PurePosixPath(key).parts
    if len(parts) >= 6 and parts[:3] == ('runr', 'acquisition', 'checkpoints') and parts[3] in ('linkedin', 'employer'):
        return '/'.join(parts[:4]), parts[4]
    if len(parts) >= 5 and parts[:3] == ('private', 'customer-database', 'backups'):
        return '/'.join(parts[:3]), parts[3]
    return None

current_keys = {item['key'] for item in receipt['objects']}
generations = {}
for key in current_keys:
    pair = family_generation(key)
    if pair:
        generations.setdefault(pair[0], set()).add(pair[1])
retained = {item['key']: item for item in receipt['objects']}
for item in previous.get('retained_objects', previous['objects']):
    key = item['key']
    pair = family_generation(key)
    if key not in current_keys and pair and len(generations.get(pair[0], ())) >= 7:
        old = root.joinpath(*PurePosixPath(key).parts).resolve()
        if not old.is_relative_to(root.resolve()):
            raise ValueError('Unsafe retained object path')
        if old.exists() and digest(old) == item['sha256']:
            old.unlink()
    elif key not in current_keys:
        retained[key] = item
receipt['retained_objects'] = list(retained.values())
temporary_receipt = receipt_path.with_suffix('.json.tmp')
temporary_receipt.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
temporary_receipt.replace(receipt_path)
print(f'Verified {len(verified)} backup objects locally; remote objects preserved.', flush=True)

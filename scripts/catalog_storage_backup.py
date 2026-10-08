"""Stream a private consistent SQL dump to gzip before catalog maintenance."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values


def write_compressed_dump(source, destination: Path, *, progress=None):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('Backup destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.part')
    if partial.exists():
        raise FileExistsError('Unfinished backup exists; inspect before restarting')
    total = 0
    prefix = b''
    tail = b''
    started = time.monotonic()
    reported = started
    with partial.open('xb') as file, gzip.GzipFile(fileobj=file, mode='wb', mtime=0, compresslevel=3) as compressed:
        os.chmod(partial, 0o600)
        while chunk := source.read(1024 * 1024):
            prefix = (prefix + chunk)[:512]
            tail = (tail + chunk)[-1024:]
            compressed.write(chunk)
            total += len(chunk)
            if progress and time.monotonic() - reported >= 20:
                progress({'phase': 'dump', 'sql_bytes': total, 'seconds': round(time.monotonic()-started)})
                reported = time.monotonic()
        if not (prefix.startswith(b'PRAGMA') or prefix.startswith(b'BEGIN')) or b'COMMIT;' not in tail:
            raise ValueError('Incomplete or invalid SQL dump; partial backup retained')
    digest = hashlib.sha256()
    with partial.open('rb') as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    partial.rename(destination)
    return {'path': str(destination), 'sql_bytes': total, 'compressed_bytes': destination.stat().st_size,
            'sha256': digest.hexdigest(), 'seconds': round(time.monotonic()-started)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', default='user_config/.env')
    parser.add_argument('--overlay')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    env = dict(dotenv_values(args.env))
    if args.overlay:
        env.update(dotenv_values(args.overlay))
    url = str(env.get('TURSO_DATABASE_URL') or '').replace('libsql://', 'https://').rstrip('/')
    token = str(env.get('TURSO_AUTH_TOKEN') or '')
    if not url.startswith('https://') or not token:
        parser.error('Remote database URL and token are required')
    request = Request(url + '/dump', headers={'Authorization': 'Bearer '+token, 'Accept-Encoding': 'identity'})
    with urlopen(request, timeout=60) as response:
        receipt = write_compressed_dump(response, args.output,
            progress=lambda item: print(json.dumps(item), flush=True))
    receipt['database_identity'] = hashlib.sha256(str(env['TURSO_DATABASE_URL']).encode()).hexdigest()
    args.output.with_suffix(args.output.suffix+'.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({'phase':'backup_complete', **receipt}), flush=True)


if __name__ == '__main__':
    main()

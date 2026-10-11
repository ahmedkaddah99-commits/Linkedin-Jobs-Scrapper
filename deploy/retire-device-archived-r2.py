"""Retire historical recovery objects after the device verifies its whole copy."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

receipt = json.load(sys.stdin)
if not isinstance(receipt.get('verified_at'), (int, float)) or not receipt.get('objects'):
    raise RuntimeError('Verified device copy receipt required')
client = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
    aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
    region_name=os.environ.get('S3_REGION', 'auto'),
    config=Config(connect_timeout=15, read_timeout=90))
bucket = os.environ['S3_BUCKET']
selected = []
for item in receipt['objects']:
    key = item['key']
    # Live checkpoint generations and customer backups are deliberately excluded.
    if not key.startswith(('runr/acquisition/checkpoints/recovery/', 'private/catalog/backups/')):
        continue
    if not re.fullmatch('[a-f0-9]{64}', item['sha256']):
        raise RuntimeError('Invalid verification digest')
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound'):
            continue
        raise
    digest = head.get('Metadata', {}).get('sha256', '')
    if not re.fullmatch('[a-fA-F0-9]{64}', digest):
        if head['ContentLength'] > 16 * 1024**2:
            raise RuntimeError('Historical object lacks digest metadata; preserved')
        body = client.get_object(Bucket=bucket, Key=key)['Body']
        try:
            digest = hashlib.sha256(body.read()).hexdigest()
        finally:
            body.close()
    if head['ContentLength'] != item['bytes'] or digest.lower() != item['sha256']:
        raise RuntimeError('Historical object changed since copying; preserved')
    selected.append(item)
for item in selected:
    client.delete_object(Bucket=bucket, Key=item['key'])
    try:
        client.head_object(Bucket=bucket, Key=item['key'])
    except ClientError as error:
        if error.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
            raise
    else:
        raise RuntimeError('Historical object still exists after deletion')
result = {'completed_at': time.time(), 'device_verified_at': receipt['verified_at'],
          'retired_objects': selected, 'retired_bytes': sum(item['bytes'] for item in selected)}
if selected:
    os.umask(0o077)
    root = Path('/srv/runr/ops/device-history-retirement')
    root.mkdir(parents=True, exist_ok=True)
    (root / 'latest.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))

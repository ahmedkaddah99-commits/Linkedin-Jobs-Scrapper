"""Remove one historical catalog blob only after verified off-host archival."""
import hashlib
import json
import os
from pathlib import Path
import time
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

root = Path('/srv/runr/ops/history-archive-20261011')
archive_sha = 'fbef3a29c7656fa3334ecfc16e88996424e56a5f6961e30964b306f32e58c3f3'
if f'Verified off-host SHA256: {archive_sha}' not in (root / 'finalized.txt').read_text():
    raise RuntimeError('Verified local archive cleanup receipt required')
payload_sha = '29d32d776e7e60ee78745c00f63f16efb334b1c402caae0b412931dce19a0864'
key = ('private/catalog/backups/'
       '387ee209fb0cf5623d04a2864becf791865b81c52b5dcdbcfb8aefad73eca98a/'
       + payload_sha + '/before.sql.gz')
client = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
    aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
    region_name=os.environ.get('S3_REGION', 'auto'),
    config=Config(connect_timeout=15, read_timeout=90))
bucket = os.environ['S3_BUCKET']
try:
    head = client.head_object(Bucket=bucket, Key=key)
except ClientError as error:
    if error.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
        raise
    receipt = {'status': 'already_absent', 'key': key, 'archive_sha256': archive_sha}
else:
    if head['ContentLength'] != 4046598196:
        raise RuntimeError('Historical object size changed; preserve it')
    body = client.get_object(Bucket=bucket, Key=key)['Body']
    digest = hashlib.sha256()
    length = 0
    try:
        for block in body.iter_chunks(chunk_size=8 * 1024**2):
            digest.update(block)
            length += len(block)
    finally:
        body.close()
    if digest.hexdigest() != payload_sha or length != head['ContentLength']:
        raise RuntimeError('Historical object content changed; preserve it')
    client.delete_object(Bucket=bucket, Key=key)
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
            raise
    else:
        raise RuntimeError('Deletion did not remove the historical object')
    receipt = {'status': 'removed_after_verified_local_archival', 'key': key,
        'bytes': length, 'payload_sha256': payload_sha, 'archive_sha256': archive_sha}
receipt['completed_at'] = time.time()
(root / 'historical-r2-retirement.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))

"""Run on VPS with its existing EnvironmentFiles; output short-lived download URLs."""
import hashlib
import json
import os
import re
import boto3
from botocore.config import Config

client = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
    aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
    region_name=os.environ.get('S3_REGION', 'auto'),
    config=Config(signature_version='s3v4', connect_timeout=15, read_timeout=90))
bucket = os.environ['S3_BUCKET']
prefixes = ['runr/acquisition/checkpoints/', 'private/customer-database/backups/',
            'private/catalog/backups/']
configured = os.environ.get('RUNR_ACQUISITION_BACKUP_REMOTE_PREFIX', '').strip('/')
if configured:
    if not configured.startswith('runr/acquisition/'):
        raise RuntimeError('Unexpected acquisition backup prefix')
    prefixes[0] = configured + '/'
objects = []
for prefix in prefixes:
    for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get('Contents', []):
            key = item['Key']
            head = client.head_object(Bucket=bucket, Key=key)
            digest = head.get('Metadata', {}).get('sha256', '')
            if not re.fullmatch('[a-fA-F0-9]{64}', digest):
                if item['Size'] > 16 * 1024**2:
                    raise RuntimeError('Large backup lacks SHA256 metadata: ' + key)
                body = client.get_object(Bucket=bucket, Key=key)['Body']
                try:
                    digest = hashlib.sha256(body.read()).hexdigest()
                finally:
                    body.close()
            objects.append({'key': key, 'bytes': item['Size'], 'sha256': digest.lower(),
                'url': client.generate_presigned_url('get_object',
                    Params={'Bucket': bucket, 'Key': key}, ExpiresIn=604800)})
print(json.dumps({'objects': objects}))

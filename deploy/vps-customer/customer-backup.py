"""Consistent SQLite backup to R2; no retained local database generations."""
import fcntl,gzip,hashlib,json,os,shutil,sqlite3,time
from pathlib import Path
import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
root=Path('/var/lib/runr/customer-backups');root.mkdir(mode=0o700,exist_ok=True)
lock=(root/'backup.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
db=Path(os.environ['SQLITE_DATABASE_PATH']);snapshot=root/'snapshot.sqlite3';archive=root/'snapshot.sqlite3.gz'
assert shutil.disk_usage(root).free > db.stat().st_size+8*1024**3, 'Insufficient backup headroom'
if snapshot.exists() or archive.exists(): raise RuntimeError('Previous temporary backup needs inspection')
started=time.time();stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
print(json.dumps({'phase':'snapshot','started':stamp}),flush=True)
with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=30) as src:
 # Pin the WAL read snapshot so concurrent heartbeats cannot restart the copy.
 src.execute('BEGIN')
 src.execute('SELECT migration_id FROM schema_migrations LIMIT 1').fetchone()
 last_progress=[0.0]
 def progress(status,remaining,total):
  now=time.monotonic()
  if now-last_progress[0]>=15 or remaining==0:
   print(json.dumps({'phase':'snapshot','percent':round(100*(total-remaining)/total,1) if total else 0}),flush=True)
   last_progress[0]=now
 with sqlite3.connect(snapshot) as dst: src.backup(dst,pages=2048,sleep=0.05,progress=progress)
 src.rollback()
with sqlite3.connect(snapshot) as c:
 assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
 assert c.execute('PRAGMA foreign_key_check').fetchone() is None
 head=c.execute('SELECT max(migration_id) FROM schema_migrations').fetchone()[0]
with snapshot.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
size=snapshot.stat().st_size
print(json.dumps({'phase':'compress','database_bytes':size}),flush=True)
with snapshot.open('rb') as src,gzip.open(archive,'wb',compresslevel=1) as dst: shutil.copyfileobj(src,dst,8*1024*1024)
with gzip.open(archive,'rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==sha
s=boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT_URL'],aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],region_name=os.environ.get('S3_REGION','auto'),config=Config(connect_timeout=10,read_timeout=90,retries={'max_attempts':3}))
bucket=os.environ['S3_BUCKET'];prefix='private/customer-database/backups/';key=prefix+stamp+'/database.sqlite3.gz'
with archive.open('rb') as f: compressed_sha=hashlib.file_digest(f,'sha256').hexdigest()
print(json.dumps({'phase':'upload','compressed_bytes':archive.stat().st_size}),flush=True)
s.upload_file(str(archive),bucket,key,ExtraArgs={'Metadata':{'sha256':compressed_sha,'sqlite-sha256':sha}},Config=TransferConfig(max_concurrency=2,multipart_chunksize=32*1024*1024))
h=hashlib.sha256();n=0
body=s.get_object(Bucket=bucket,Key=key)['Body']
for chunk in body.iter_chunks(chunk_size=8*1024*1024):h.update(chunk);n+=len(chunk)
body.close();assert n==archive.stat().st_size and h.hexdigest()==compressed_sha
receipt={'completed_at':time.time(),'object_key':key,'database_bytes':size,'compressed_bytes':n,'sha256':sha,'compressed_sha256':compressed_sha,'migration_head':head,'integrity_check':'ok','foreign_key_violations':0,'gzip_restore_hash_verified':True,'full_offhost_readback_verified':True,'elapsed_seconds':round(time.time()-started)}
s.put_object(Bucket=bucket,Key=prefix+stamp+'/receipt.json',Body=json.dumps(receipt).encode(),ContentType='application/json')
(root/'latest.json.tmp').write_text(json.dumps(receipt,indent=2));(root/'latest.json.tmp').replace(root/'latest.json')
snapshot.unlink();archive.unlink()
# Retain seven verified generations. Delete only objects owned by this prefix.
receipts=[]
for page in s.get_paginator('list_objects_v2').paginate(Bucket=bucket,Prefix=prefix):
 receipts.extend(o['Key'] for o in page.get('Contents',[]) if o['Key'].endswith('/receipt.json'))
for old in sorted(receipts,reverse=True)[7:]:
 generation=old.rsplit('/',1)[0]+'/'
 assert generation.startswith(prefix)
 s.delete_object(Bucket=bucket,Key=generation+'database.sqlite3.gz');s.delete_object(Bucket=bucket,Key=old)
print(json.dumps({'phase':'complete',**receipt}),flush=True)

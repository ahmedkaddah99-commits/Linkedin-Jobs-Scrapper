import os,json,subprocess,time,urllib.request,sqlite3
from pathlib import Path
lines=['runr_customer_observer_timestamp_seconds '+str(time.time())]
for role,unit in [('api','runr-api-candidate'),('worker','runr-worker-candidate')]:
 result=subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','MemoryCurrent','-p','CPUUsageNSec','-p','NRestarts'],capture_output=True,text=True,timeout=5)
 props=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
 active=props.get('ActiveState')=='active'; lines.append(f'runr_customer_service_up{{service="{role}",stage="production"}} {int(active)}')
 for prop,metric,scale in [('MemoryCurrent','memory_bytes',1),('CPUUsageNSec','cpu_seconds_total',1e9),('NRestarts','restarts_total',1)]:
  value=props.get(prop,'')
  if value.isdigit(): lines.append(f'runr_customer_service_{metric}{{service="{role}",stage="production"}} {int(value)/scale}')
ready=0
try:
 with urllib.request.urlopen('http://127.0.0.1:18000/health/ready',timeout=5) as r: ready=int(r.status==200)
except Exception: pass
lines.append('runr_customer_api_ready '+str(ready)); ok=0
try:
 c=sqlite3.connect(Path(os.environ['SQLITE_DATABASE_PATH']).as_uri()+'?mode=ro',uri=True,timeout=5)
 counts=dict(c.execute('SELECT state,count(*) FROM customer_tasks GROUP BY state').fetchall())
 for state in ['queued','running','completed','failed']: lines.append(f'runr_customer_tasks{{state="{state}",stage="production"}} {counts.get(state,0)}')
 age=c.execute("SELECT coalesce(max(0,strftime('%s','now')-strftime('%s',min(created_at))),0) FROM customer_tasks WHERE state='queued'").fetchone()[0]
 lines.append('runr_customer_oldest_queued_task_age_seconds '+str(age)); c.close(); ok=1
except Exception: pass
lines.append('runr_customer_queue_query_ok '+str(ok))
lines.append('runr_customer_service_up{service="database",stage="production"} '+str(ok))
for suffix,label in [('', 'database'),('-wal','wal')]:
 dbfile=Path(os.environ['SQLITE_DATABASE_PATH']+suffix)
 lines.append(f'runr_customer_sqlite_bytes{{file="{label}"}} '+str(dbfile.stat().st_size if dbfile.exists() else 0))
backup_ok=0; backup_timestamp=0
try:
 receipt=json.loads(Path('/var/lib/runr/customer-backups/latest.json').read_text())
 backup_ok=int(receipt.get('full_offhost_readback_verified') is True and receipt.get('gzip_restore_hash_verified') is True)
 backup_timestamp=float(receipt['completed_at'])
except Exception: pass
lines.append('runr_customer_backup_verified '+str(backup_ok))
lines.append('runr_customer_backup_timestamp_seconds '+str(backup_timestamp))
p=Path('/var/lib/runr/observability/customer.prom'); tmp=p.with_suffix('.tmp'); tmp.write_text('\n'.join(lines)+'\n'); tmp.chmod(0o644); tmp.replace(p)
print(json.dumps({'event':'runr_customer_observation','api_ready':bool(ready),'queue_query_ok':bool(ok),'stage':'production'}))

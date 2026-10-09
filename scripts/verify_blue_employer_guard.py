"""Read-only verification after an uncertain write response."""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from scripts.snapshot_title_collar_audit import query
load_dotenv(ROOT/'user_config/.env')
tables=query("SELECT name FROM sqlite_master WHERE name='employer_acquisition_exclusions'")
result={'table_exists':bool(tables)}
if tables:
    result['rows']=query('SELECT COUNT(*) AS n FROM employer_acquisition_exclusions')[0]['n']
    result['triggers']=query("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'owner_excluded_%'")
print(json.dumps(result))

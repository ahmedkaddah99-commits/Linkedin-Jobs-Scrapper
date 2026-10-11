"""Populate one saved account profile from its selected, already parsed CV."""
from pathlib import Path
import argparse,json,re,sys
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import load_project_dotenv
from scripts.process_catalog_enrichment import execute
from backend.api.server import _merge_profile_metadata
from backend.domain.models import UserRecord,utc_now_iso

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--email',required=True)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    load_project_dotenv()
    rows=execute('SELECT user_id,payload_json FROM users WHERE lower(email)=?',[args.email.casefold()])
    if len(rows)!=1:raise RuntimeError('Account must exist uniquely')
    user=UserRecord.from_dict(json.loads(rows[0]['payload_json']))
    document_id=user.metadata.get('cv_document_id')
    source=execute("SELECT a.payload_json FROM candidate_documents d JOIN candidate_assets a ON a.asset_id=d.asset_id AND a.user_id=d.user_id WHERE d.user_id=? AND d.document_id=? AND a.asset_kind='workspace_cv'",[user.user_id,document_id])
    if len(source)!=1:raise RuntimeError('Selected CV is not ready')
    asset=json.loads(source[0]['payload_json'])
    parsed=asset.get('metadata',{}).get('parsed_profile') or {}
    if not parsed:raise RuntimeError('Selected CV has no parsed profile')
    imported={k:parsed[k] for k in ['name','role_title','summary','competencies','languages','recent_experience','education','projects','industry'] if parsed.get(k)}
    for item in imported.get('recent_experience',[]):
        dates=re.findall(r'([A-Za-z]+)\s+(20\d{2})',item.get('period',''))
        if len(dates)==2:
            for key,value in zip(['start_date','end_date'],dates):
                for fmt in ['%b %Y','%B %Y']:
                    try:item[key]=datetime.strptime(' '.join(value),fmt).strftime('%Y-%m');break
                    except ValueError:pass
    old=user.metadata.get('profile') or {}
    profile=_merge_profile_metadata(old,imported,user)
    if not args.dry_run:
        backup=Path('.backend_data/operator_backups') / ('profile_matching_'+user.user_id+'_before.json')
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():backup.write_text(json.dumps({'user_id':user.user_id,'profile':old},ensure_ascii=False),encoding='utf-8')
        execute("UPDATE users SET payload_json=json_set(payload_json,'$.metadata.profile',json(?)),updated_at=? WHERE user_id=? AND json_extract(payload_json,'$.metadata.cv_document_id')=?",[json.dumps(profile,ensure_ascii=False),utc_now_iso(),user.user_id,document_id])
        saved=json.loads(execute("SELECT json_extract(payload_json,'$.metadata.profile') AS profile FROM users WHERE user_id=?",[user.user_id])[0]['profile'])
        if saved['role_title']!=profile['role_title']:raise RuntimeError('Saved profile verification failed')
    print(json.dumps({'saved':not args.dry_run,'cv_name':asset['display_name'],'role':profile['role_title'],'skills':len(profile['competencies']),'experiences':len(profile['recent_experience']),'dated_experiences':sum(bool(x.get('start_date') and x.get('end_date')) for x in profile['recent_experience']),'education':len(profile['education']),'industry_established':bool(profile.get('industry'))}))

if __name__=='__main__':main()

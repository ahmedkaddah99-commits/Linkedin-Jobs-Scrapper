from backend.application.enrichment_field_pass import supplement, missing_fields


def test_extra_pass_fills_only_missing_values_with_source_evidence():
 row={'canonical_job_id':'job','current_version_id':'v','content_hash':'h','title':'Data Analyst',
      'description':'Build monthly reports and analyze business data. We offer 30 vacation days.'}
 filters={'roles':['Data Analyst'],'collar':'white','employment_type':'part_time'}
 summary={'responsibilities':[{'text':'Preserve this description.'}]}
 structured={'location':{'value':'Berlin'}}
 calls=[]
 def generate(prompt):
  calls.append(prompt)
  return {'filters':{'jobs':[]},'description':{'items':[{'section':'benefits','text':'30 vacation days.',
          'source_ids':['p1'],'source_quote':'30 vacation days.'}],'header_candidates':{}}}
 output,gaps=supplement(row,filters,summary,structured,generate)
 assert len(calls)==1
 assert output['description']['summary']['responsibilities']==summary['responsibilities']
 assert output['description']['summary']['benefits'][0]['text']=='30 vacation days.'
 assert output['description']['structured_description']['location']==structured['location']
 assert 'summary.benefits' not in gaps
 assert 'structured.salary' in gaps
 assert 'filters' not in output


def test_unsupported_fields_stay_missing_after_one_pass():
 row={'canonical_job_id':'job','current_version_id':'v','content_hash':'h','title':'Data Analyst','description':''}
 output,gaps=supplement(row,{'roles':['Data Analyst']},{},{},lambda _: {'filters':{'jobs':[]},'description':{'items':[],'header_candidates':{}}})
 assert output=={}
 assert 'structured.salary' in gaps
 assert 'summary.responsibilities' in gaps


def test_zero_is_populated_not_a_missing_experience_value():
 assert 'filters.required_experience_years' not in missing_fields({'required_experience_years':0},{},{})

from backend.application.catalog_enrichment import enrich_version

def row(**overrides):
 return {'canonical_job_id':'job','current_version_id':'v','content_hash':'h','title':'Data Analyst','description':'Build reports.','filters_ready':False,'description_ready':False,**overrides}

def test_enrichment_reuses_completed_stages():
 calls=[]
 assert enrich_version(row(filters_ready=True,description_ready=True),lambda p:calls.append(p)) == {}
 assert not calls

def test_missing_source_is_explicit_and_does_not_call_model():
 import pytest
 with pytest.raises(ValueError,match='source_missing'):
  enrich_version(row(description=''),lambda _: (_ for _ in ()).throw(AssertionError('model should not run')))

def test_filters_and_description_are_validated_before_save():
 def generate(prompt):
  if 'Classify each' in prompt:
   return {'jobs':[{'id':'job','collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}]}
  return {'items':[{'section':'responsibilities','text':'Build reports.','source_ids':['p1']}],'header_candidates':{},'_runr_model':'mistralai/mistral-nemo'}
 value=enrich_version(row(),generate)
 assert value['filters']['roles']==['Data Analyst']
 assert value['description']['model']=='mistralai/mistral-nemo'
 assert value['description']['content_hash']=='h'

from backend.application.catalog_enrichment import enrich_version

def row(**overrides):
 return {'canonical_job_id':'job','current_version_id':'v','content_hash':'h','title':'Data Analyst','description':'Build reports. Analyze operational data and create monthly financial dashboards for the business team.','filters_ready':False,'description_ready':False,**overrides}

def test_enrichment_reuses_completed_stages():
 calls=[]
 assert enrich_version(row(filters_ready=True,description_ready=True),lambda p:calls.append(p)) == {}
 assert not calls

def test_missing_source_is_explicit_and_does_not_call_model():
 import pytest
 with pytest.raises(ValueError,match='source_missing'):
  enrich_version(row(description='',filters_ready=True),lambda _: (_ for _ in ()).throw(AssertionError('model should not run')))

def test_known_title_can_supply_function_when_description_is_missing():
 value=enrich_version(row(description='',description_ready=True),lambda _: {
  'jobs':[{'id':'job','collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}]})
 assert value['filters']['roles']==['Data Analyst']
 assert value['filters'].get('required_experience_years') is None
 assert 'description' not in value

def test_filters_and_description_are_validated_before_save():
 def generate(prompt):
  if 'Classify each' in prompt:
   return {'jobs':[{'id':'job','collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}], 'items':[{'section':'responsibilities','text':'Build reports.','source_ids':['p1'],'source_quote':'Build reports.'}], 'header_candidates':{}}
  return {'items':[{'section':'responsibilities','text':'Build reports.','source_ids':['p1'],'source_quote':'Build reports.'}],'header_candidates':{},'_runr_model':'mistralai/mistral-nemo'}
 value=enrich_version(row(),generate)
 assert value['filters']['roles']==['Data Analyst']
 assert value['description']['model']=='mistralai/mistral-nemo'
 assert value['description']['content_hash']=='h'


def test_incomplete_source_does_not_generate_description():
 import pytest
 with pytest.raises(ValueError,match='source_incomplete'):
  enrich_version(row(description='Company: Example GmbH',filters_ready=True),lambda _: (_ for _ in ()).throw(AssertionError('model should not run')))

def test_unquoted_model_facts_are_rejected():
 import pytest
 with pytest.raises(ValueError,match='description_has_no_supported_facts'):
  enrich_version(row(filters_ready=True),lambda _: {'items':[{'section':'responsibilities','text':'Manage a team.','source_ids':['p1'],'source_quote':'Manage a team.'}],'header_candidates':{}})

def test_one_request_produces_filters_and_english_description():
 calls=[]
 def generate(prompt):
  calls.append(prompt)
  return {'jobs':[{'id':'job','collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}], 'items':[{'section':'responsibilities','text':'Build reports.','source_ids':['p1'],'source_quote':'Build reports.'}],'header_candidates':{}}
 result=enrich_version(row(),generate)
 assert len(calls)==1
 assert result['filters']['roles']==['Data Analyst']
 assert result['description']['summary']['responsibilities']

def test_obvious_manual_work_is_classified_without_paid_request():
 result=enrich_version(row(title='Truck Driver'),lambda _: (_ for _ in ()).throw(AssertionError('paid request')))
 assert result['filters']['collar']=='blue'
 assert 'description' not in result

def test_separate_experience_requirements_keep_all_levels_and_quotes():
 from backend.application.catalog_job_filters import validate_classification
 source='Data Analyst. 2 years consulting experience required. 4 years product experience required.'
 requirements=[{'years':2,'evidence':'2 years consulting experience required.'},{'years':4,'evidence':'4 years product experience required.'}]
 result=validate_classification({'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst','experience_requirements':requirements},source,'Data Analyst')
 assert result['experience_level']==['entry','mid']
 assert result['experience_requirements']==requirements

def test_untranslated_output_is_not_accepted_as_english_description():
 import pytest
 german='Sie entwickeln moderne Anwendungen und arbeiten gemeinsam mit unserem erfahrenen Team an neuen technischen Lösungen.'
 with pytest.raises(ValueError,match='description_output_not_english'):
  enrich_version(row(description=german,filters_ready=True),lambda _: {'items':[{'section':'responsibilities','text':german,'source_ids':['p1'],'source_quote':german}],'header_candidates':{}})

def test_invalid_separate_experience_evidence_does_not_create_levels():
 from backend.application.catalog_job_filters import validate_classification
 source='Data Analyst. Ideally 8 years consulting experience. 2 years product experience required.'
 result=validate_classification({'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst','experience_requirements':[{'years':8,'evidence':'Ideally 8 years consulting experience.'},{'years':10,'evidence':'10 years experience required.'}]},source,'Data Analyst')
 assert result['experience_requirements']==[]
 assert result['experience_level']==[]


def test_bounded_repairs_preserve_original_evidence_and_translate_summary():
 calls=[]
 german='Sie entwickeln moderne Anwendungen und arbeiten gemeinsam mit unserem erfahrenen Team an neuen technischen Lösungen.'
 def generate(prompt):
  return {'jobs':[{'id':'job','collar':'white','roles':['Invented Role'],'evidence':'Data Analyst'}],
          'items':[{'section':'responsibilities','text':german,'source_ids':['p1'],'source_quote':german}],'header_candidates':{}}
 def stage(name,prompt):
  calls.append(name)
  if name=='classification_v1':
   return {'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}
  return {'items':[{'section':'responsibilities','text':'Develop modern applications and collaborate with the experienced team on new technical solutions.',
                    'source_ids':['p1'],'source_quote':german}],'header_candidates':{}}
 generate.for_stage=stage
 result=enrich_version(row(description=german),generate)
 assert calls==['classification_v1','description_v1']
 assert result['filters']['roles']==['Data Analyst']
 fact=result['description']['summary']['responsibilities'][0]
 assert fact['text'].startswith('Develop modern')
 assert fact['source_quote']==german


def test_description_failure_retains_valid_classification():
 import pytest
 from backend.application.catalog_enrichment import EnrichmentStageError
 def generate(prompt):
  return {'jobs':[{'id':'job','collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}],
          'items':[{'section':'responsibilities','text':'Invented duty','source_ids':['p1'],'source_quote':'Not present in source'}]}
 with pytest.raises(EnrichmentStageError) as error:
  enrich_version(row(),generate)
 assert error.value.partial['filters']['roles']==['Data Analyst']

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

def test_original_german_is_accepted_without_translation():
 german='Sie entwickeln moderne Anwendungen und arbeiten gemeinsam mit unserem erfahrenen Team an neuen technischen L?sungen.'
 result=enrich_version(row(description=german,filters_ready=True),lambda _: {'items':[{'section':'responsibilities','text':german,'source_ids':['p1'],'source_quote':german}],'header_candidates':{}})
 assert result['description']['summary']['responsibilities'][0]['text']==german

def test_invalid_separate_experience_evidence_does_not_create_levels():
 from backend.application.catalog_job_filters import validate_classification
 source='Data Analyst. Ideally 8 years consulting experience. 2 years product experience required.'
 result=validate_classification({'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst','experience_requirements':[{'years':8,'evidence':'Ideally 8 years consulting experience.'},{'years':10,'evidence':'10 years experience required.'}]},source,'Data Analyst')
 assert result['experience_requirements']==[]
 assert result['experience_level']==[]


def test_bounded_repairs_preserve_original_language():
 calls=[]
 german='Sie entwickeln moderne Anwendungen und arbeiten gemeinsam mit unserem erfahrenen Team an neuen technischen Lösungen.'
 def generate(prompt):
  return {'jobs':[{'id':'job','collar':'white','roles':['Invented Role'],'evidence':'Data Analyst'}],
          'items':[{'section':'responsibilities','text':german,'source_ids':['p1'],'source_quote':german}],'header_candidates':{}}
 def stage(name,prompt):
  calls.append(name)
  if name=='classification_v2':
   from backend.application.catalog_job_filters import ROLES
   return {'collar':'white','role_ids':[ROLES.index('Data Analyst')],'evidence':'Data Analyst'}
  if name.startswith('description_english_v1_'):
   return {'items':[{'id':0,'text':'Develop modern applications and collaborate with the experienced team on new technical solutions.'}]}
  return {'items':[{'section':'responsibilities','text':'Develop modern applications and collaborate with the experienced team on new technical solutions.',
                    'source_ids':['p1'],'source_quote':german}],'header_candidates':{}}
 generate.for_stage=stage
 result=enrich_version(row(description=german),generate)
 assert calls[0]=='classification_v2'
 assert calls==['classification_v2']
 assert result['filters']['roles']==['Data Analyst']
 fact=result['description']['summary']['responsibilities'][0]
 assert fact['text']==german
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


def test_original_quote_preserves_numbers_despite_bad_model_paraphrase():
 german='Sie haben mindestens 3 Jahre Erfahrung mit der Entwicklung moderner Anwendungen und technischen Systeme.'
 result=enrich_version(row(description=german,filters_ready=True),lambda _: {'items':[{'section':'required_qualifications','text':'You need 5 years experience.','source_ids':['p1'],'source_quote':german}],'header_candidates':{}})
 assert result['description']['summary']['required_qualifications'][0]['text']==german


def test_contiguous_quote_across_passages_is_reanchored_without_inventing_evidence():
 from backend.application.vps_job_descriptions import _quoted_passage_ids,build_pilot_description
 source='Technical support for complex automation\nand control systems in international customer service.'
 result=build_pilot_description(row(description=source),lambda _: {'items':[{
  'section':'responsibilities','text':'Support complex automation and control systems in international customer service.',
  'source_ids':['p9'],'source_quote':source}],'header_candidates':{}},require_source_quotes=True)
 fact=result['summary']['responsibilities'][0]
 assert fact['source_ids']==['p1','p2']
 assert fact['source_quote']==source
 assert _quoted_passage_ids('first third',{'p1':'first','p2':'second','p3':'third'})==[]

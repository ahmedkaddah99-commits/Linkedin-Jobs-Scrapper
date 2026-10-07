import importlib

def test_experience_prompts_select_highest_separate_required_minimum():
    from backend.application.catalog_job_filters import classification_prompt, metadata_prompt
    row = {'id': 'job', 'title': 'Analyst', 'description': 'Requirements: 5 years experience. 2 years SQL experience.'}
    for prompt in (classification_prompt([row]), metadata_prompt(row)):
        assert 'highest minimum across separate mandatory experience requirements' in prompt
        assert 'JSON number' in prompt


def test_all_current_functions_reach_both_nemo_classification_prompts():
    import json
    from backend.application.catalog_job_filters import ROLES, FUNCTION_SELECTION_RULES, classification_prompt, function_prompt
    row = {'id': 'job', 'title': 'Python Engineer', 'description': 'Build Python backend services.'}
    for prompt, marker, end in ((classification_prompt([row]), 'Allowed roles: ', '\nPostings: '),
                                (function_prompt(row), 'Allowed functions: ', '\nPosting: ')):
        assert json.loads(prompt.split(marker, 1)[1].split(end, 1)[0]) == list(ROLES)
        assert FUNCTION_SELECTION_RULES in prompt


def test_primary_function_preserves_the_ranked_specific_selection():
    from backend.application.catalog_job_filters import validate_classification
    source = 'Python Engineer. Build Python backend services and SQL data pipelines.'
    result = validate_classification({'collar': 'white', 'roles': ['Python Engineer', 'Data Engineer'],
                                      'evidence': 'Build Python backend services'}, source, 'Python Engineer')
    assert result['roles'] == ['Python Engineer', 'Data Engineer']
    assert result['role'] == 'Python Engineer'


def test_catalog_classification_rejects_missing_roles_for_white_collar():
    module = importlib.import_module('backend.application.catalog_job_filters')
    assert module.validate_classification({'collar': 'white', 'roles': [], 'evidence': 'analysis'}, 'analysis') is None


def test_catalog_classification_accepts_multiple_functions_and_numeric_experience():
    module = importlib.import_module('backend.application.catalog_job_filters')
    source = 'Analyze data using SQL. At least 3 years of professional experience required.'
    result = module.validate_classification({'collar': 'white', 'roles': ['Data Analyst', 'Business Analyst'],
        'evidence': 'Analyze data', 'required_experience_years': 3, 'experience_evidence': 'At least 3 years of professional experience required.',
        'skills': ['SQL'], 'work_arrangement': None}, source)
    assert result['roles'] == ['Data Analyst', 'Business Analyst']
    assert result['required_experience_years'] == 3


def test_catalog_classification_hides_text_experience_and_rejects_unquoted_blue_collar():
    module = importlib.import_module('backend.application.catalog_job_filters')
    result = module.validate_classification({'collar': 'white', 'roles': ['Data Analyst'],
        'evidence': 'Analyze data', 'required_experience_years': '3', 'skills': []}, 'Analyze data')
    assert result['required_experience_years'] is None
    assert module.validate_classification({'collar': 'blue', 'roles': [], 'evidence': 'repair vehicles'}, 'Analyze data') is None


def test_collaboration_and_mentions_of_interns_do_not_change_contract_or_management():
    module = importlib.import_module('backend.application.catalog_job_filters')
    source = 'Data Analyst full time. Help interns and working students learn SQL. Team collaboration expected.'
    result = module.validate_classification({'collar': 'white', 'roles': ['Data Analyst'], 'evidence': 'Data Analyst',
        'employment_type': 'full_time', 'employment_evidence': 'full time',
        'role_type': 'manager', 'role_type_evidence': 'Team collaboration expected.'}, source)
    assert result['employment_type'] == 'full_time'
    assert result['role_type'] is None


def test_scraped_aliases_take_precedence_over_model_defaults():
    from backend.application.personalized_jobs_service import _payload_for_row, _job_card_projection
    row = {'version_payload_json': {'job_type':'part_time','seniority':'senior','experience_years_min':7},
           'filter_json': {'employment_type':'full_time','experience_level':['entry','mid'],'required_experience_years':2}}
    payload = _payload_for_row(row)
    assert payload['employment_type'] == 'part_time'
    assert payload['experience_level'] == 'senior'
    assert payload['experience_years_min'] == 7
    row['version_payload_json'] = {}
    card = _job_card_projection(row, None, evaluation_state='pending', evaluation_status='pending')
    assert card['experience_level'] == 'mid'
    assert card['experience_levels'] == ['entry','mid']


def test_written_source_numbers_are_allowed_but_output_must_remain_numeric():
    module = importlib.import_module('backend.application.catalog_job_filters')
    source = 'Data Analyst. Minimum one year of professional experience required.'
    raw = {'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst',
           'required_experience_years':1,'experience_evidence':'Minimum one year of professional experience required.'}
    assert module.validate_classification(raw,source)['required_experience_years'] == 1
    raw['required_experience_years']='one'
    assert module.validate_classification(raw,source)['required_experience_years'] is None


def test_only_adjacent_seniority_levels_display_together():
    from backend.application.personalized_jobs_service import _experience_levels
    assert _experience_levels(['entry','mid']) == ['entry','mid']
    assert _experience_levels(['intern','lead']) == ['lead']
    assert _experience_levels(['mid','senior','lead']) == ['lead']


def test_profession_rules_correct_nursing_and_retail_without_matching_employer_advertising():
    from backend.application.catalog_job_filters import validate_classification
    title = 'Gesundheits- und Krankenpfleger Onkologie'
    raw = {'collar':'blue','roles':[], 'evidence':title}
    assert validate_classification(raw,title+' Qualifizierte Patientenversorgung.',title)['roles'] == ['Nursing Professional']
    title = 'Sales Associate Retail'
    raw = {'collar':'blue','roles':[], 'evidence':title}
    assert validate_classification(raw,title+' Advise customers and sell products.',title)['roles'] == ['Retail Sales']
    title = 'Data Analyst'
    raw = {'collar':'white','roles':['Healthcare Data Analyst'],'evidence':title}
    assert validate_classification(raw,title+' Analyze healthcare data for nurses.',title)['roles'] == ['Healthcare Data Analyst']


def test_restaurant_hosts_are_excluded_but_office_reception_is_retained():
    from backend.application.catalog_job_filters import validate_classification
    title = 'Host / Hostess'
    source = title+' Restaurant: greet diners and seat guests at tables.'
    assert validate_classification({'collar':'white','roles':['Receptionist'],'evidence':title},source,title)['collar'] == 'blue'
    title = 'Receptionist'
    source = title+' Office reception and scheduling appointments.'
    assert validate_classification({'collar':'white','roles':['Receptionist'],'evidence':title},source,title)['collar'] == 'white'


def test_taxonomy_copy_and_nonsoftware_engineering_labels_are_rejected():
    from backend.application.catalog_job_filters import validate_classification, ROLES
    title = 'Berechnungsingenieur EMV Antennen'
    source = title+' CST and ANSYS electromagnetic simulation.'
    assert validate_classification({'collar':'white','roles':list(ROLES),'evidence':title},source,title) is None
    assert validate_classification({'collar':'white','roles':['Backend Engineer'],'evidence':title},source,title)['roles'] == ['Electrical Engineer']


def test_months_are_not_accepted_as_years():
    from backend.application.catalog_job_filters import validate_classification
    source = 'Data Analyst. Minimum 6 months of professional experience.'
    result = validate_classification({'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst',
        'required_experience_years':6,'experience_evidence':'Minimum 6 months of professional experience.'},source)
    assert result['required_experience_years'] is None


def test_direct_clinical_titles_are_not_research_or_video_functions():
    from backend.application.catalog_job_filters import validate_classification
    for title, role in [('Physiotherapeut','Therapist'),('Tierarzt / Tierärztin','Medical Professional'),
                        ('Hebamme','Medical Professional'),('Apotheker','Medical Professional'),
                        ('Pflegehelfer mit 1 oder 2-jähriger Ausbildung','Nursing Professional'),
                        ('Pflegefachkraft Gynäkologie & Geburtshilfe','Nursing Professional')]:
        result = validate_classification({'collar':'white','roles':['Video Editor'],'evidence':title},title,title)
        assert result['roles'] == [role]
    title='Clinical Research Scientist'
    result=validate_classification({'collar':'white','roles':[title],'evidence':title},title+' Research clinical interventions.',title)
    assert result['roles'] == [title]


def test_evidence_matches_decoded_html_and_short_occupational_titles():
    from backend.application.catalog_job_filters import validate_classification
    title = 'Learning &amp; Adoption Lead'
    result = validate_classification({'collar':'white','roles':['Corporate Training and Development'],
        'evidence':'Learning & Adoption Lead'},title,title)
    assert result['roles'] == ['Corporate Training and Development']
    assert validate_classification({'collar':'white','roles':['Nursing Professional'],'evidence':'LVN'},'LVN','LVN')['roles'] == ['Nursing Professional']


def test_education_and_bookkeeping_have_appropriate_functions():
    from backend.application.catalog_job_filters import validate_classification
    for title,source,role in [('Erzieher','Kinderbildung in unserer Kita','Early Childhood Educator'),
                              ('Nachhilfelehrer','Schulkinder unterstützen','K-12 Teaching'),
                              ('Finanzbuchhalter','Jahresabschlüsse und Buchhaltung','Accountant')]:
        result=validate_classification({'collar':'white','roles':['Translator'],'evidence':title},title+' '+source,title)
        assert result['roles'] == [role]


def test_indefinite_employment_is_not_fixed_term_contract():
    from backend.application.catalog_job_filters import validate_classification
    title='Data Analyst unbefristet'
    raw={'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst',
         'employment_type':'contract','employment_evidence':'unbefristet'}
    assert validate_classification(raw,title,title)['employment_type'] == 'full_time'


def test_manual_driver_and_trade_titles_do_not_enter_engineering_filters():
    from backend.application.catalog_job_filters import validate_classification
    for title in ('Triebfahrzeugführer Velten','Elektroniker','Kommissionierer','Reinigungskraft'):
        result=validate_classification({'collar':'white','roles':['Engineering Manager'],'evidence':title},title,title)
        assert result['collar']=='blue'
        assert result['roles']==[]
    title='Elektroingenieur'
    assert validate_classification({'collar':'white','roles':['Electrical Engineer'],'evidence':title},title,title)['collar']=='white'
    title='Sachbearbeiterin Netzanschlüsse (Elektrofachkraft)'
    assert validate_classification({'collar':'blue','roles':[],'evidence':title},title,title)['roles']==['Administrative Specialist']


def test_reviewed_actual_duties_can_override_a_conflicting_trade_title():
    from backend.application.catalog_job_filters import validate_classification
    title='Elektroniker für Geräte und Systeme'
    source=title+' Planning and executing product launches. Developing product strategies.'
    raw={'collar':'white','roles':['Product Manager'],'evidence':'Planning and executing product launches'}
    assert validate_classification(raw,source,title,reviewed=True)['roles']==['Product Manager']
    raw['reviewed']=True  # Model output cannot enable the trusted review path itself.
    assert validate_classification(raw,source,title)['collar']=='blue'
    title='Maschinen- und Anlagenführer pharmazeutische Entwicklung'
    assert validate_classification({'collar':'white','roles':['Medical Professional'],'evidence':title},title,title)['collar']=='blue'

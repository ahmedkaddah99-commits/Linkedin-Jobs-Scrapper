import importlib


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

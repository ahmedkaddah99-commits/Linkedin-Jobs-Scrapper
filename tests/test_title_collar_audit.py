import pytest

from scripts.audit_title_collars import classify_titles, deduplicate, employer_summary
from scripts.audit_title_collars import run_audit


@pytest.mark.parametrize('title,expected', [
    ('Augenoptikermeister (m/w/d)', 'blue'),
    ('Haustechniker', 'blue'),
    ('Saisonkraft Reifenwechsel', 'blue'),
    ('Spezialist Baufinanzierung', 'white'),
    ('Einzelhandelskaufmann', 'white'),
    ('Arbeitsvorbereiter', 'white'),
    ('Rettungsschwimmer', 'blue'),
    ('HSE Manager', 'white'),
])
def test_enriched_explicit_occupations(title, expected):
    assert classify_titles([title])['collar'] == expected


def test_official_dictionary_supplies_missing_scientific_occupations():
    for title in ('Senior Astronomer (m/w/d)', 'Geologe'):
        result = classify_titles([title])
        assert result['collar'] == 'white'
        assert result['reason'] == 'official_occupation_alias'
        assert result['white_matches'][0]['references']


def test_dictionary_preserves_ambiguous_alias_and_word_boundaries():
    assert classify_titles(['Production Assistant'])['reason'] == 'conflicting_dictionary_aliases'
    assert classify_titles(['Astronomerxyz'])['collar'] == 'unresolved'


@pytest.mark.parametrize('title,expected', [
    ('Business Analyst (m/w/d)', 'white'),
    ('Geschäftsanalystin', 'white'),
    ('Senior Software Engineer', 'white'),
    ('Entwicklungsingenieur Elektrotechnik', 'white'),
    ('Sachbearbeiterin Logistik', 'white'),
    ('Registered Nurse / Pflegefachkraft', 'white'),
    ('Retail Sales Associate', 'white'),
    ('Elektroniker:in für Betriebstechnik', 'blue'),
    ('Mechatroniker (m/w/d)', 'blue'),
    ('Warehouse Picker', 'blue'),
    ('LKW-Fahrer', 'blue'),
    ('Reinigungskräfte', 'blue'),
    ('Ausbildung zum Elektriker', 'blue'),
    ('Duales Studium Informatik', 'white'),
    ('Chef de Partie', 'blue'),
    ('Chief Financial Officer', 'white'),
    ('Leiter Softwareentwicklung', 'white'),
    ('Bauleiter', 'white'),
    ('Vorarbeiter Reinigung', 'blue'),
    ('Teamleiter Produktion', 'unresolved'),
    ('Service Technician', 'blue'),
    ('Service Engineer', 'unresolved'),
    ('Field Service Engineer', 'unresolved'),
    ('Manager', 'unresolved'),
    ('Working Student', 'unresolved'),
    ('Assistant', 'unresolved'),
    ('Engineer', 'unresolved'),
    ('Driver Software Engineer', 'blue'),
    ('Developer / Warehouse Picker', 'blue'),
    ('Random unknown job', 'unresolved'),
    ('', 'unresolved'),
    ('Bäcker/in', 'blue'),
    ('Kaufmännische Mitarbeiterin', 'white'),
    ('Warehouse Management Software Developer', 'white'),
    ('Cleaning Validation Scientist', 'white'),
    ('Executive Chef', 'blue'),
    ('Sous Chef', 'blue'),
    ('Office Cleaner', 'blue'),
    ('Mechanical Engineer', 'white'),
    ('Chefarzt Innere Medizin', 'white'),
    ('Vehicle Mechanic', 'blue'),
    ('Chef de Projet', 'unresolved'),
    ('Handelsfachwirt (m/w/d)', 'white'),
    ('Immobilienmakler', 'white'),
    ('Pflegedienstleitung', 'white'),
    ('Ausbildungsbegleitendes Studium Bank- und Versicherungsmanagement', 'white'),
    ('Verkäufer Bäckerei', 'white'),
    ('Fachverkäuferin Backstube', 'white'),
    ('Fahrzeuglackierer', 'blue'),
    ('Betriebselektriker', 'blue'),
    ('Baumaschinenmechatroniker', 'blue'),
    ('Barbier', 'blue'),
    ('Haushaltshilfe', 'blue'),
    ('Küchenkraft', 'blue'),
    ('Sachbearbeiter Fleischereibüro', 'white'),
    ('Bank- und Versicherungsmanagement', 'white'),
    ('Polier Ingenieurbau', 'blue'),
    ('Aushilfe auf geringfügiger Beschäftigungsbasis', 'blue'),
    ('Aushilfskraft Buchhaltung', 'blue'),
    ('Servicetechniker (m/w/d)', 'blue'),
    ('Servicetechniker / Elektriker', 'blue'),
    ('Stellenangebote', 'blue'),
    ('Aktuelle Stellenangebote', 'blue'),
    ('Jobtitel-Platzhalter (m/w/d)', 'blue'),
    ('Search Jobs', 'blue'),
    ('505', 'blue'),
])
def test_title_policy(title, expected):
    assert classify_titles([title])['collar'] == expected


def test_owner_policy_marks_conflicting_titles_blue_and_preserves_both_quotes():
    result = classify_titles(['Business Analyst', 'Lagerarbeiter'])
    assert result['collar'] == 'blue'
    assert result['reason'] == 'owner_policy_conflicting_occupation_terms'
    assert result['white_matches'] and result['blue_matches']


def test_gender_umlaut_and_dash_normalization_retains_evidence():
    result = classify_titles(['ELEKTRONIKER:IN — Betriebstechnik (w/m/d)'])
    assert result['collar'] == 'blue'
    assert result['blue_matches'][0]['title'] == 'ELEKTRONIKER:IN — Betriebstechnik (w/m/d)'


def test_title_substrings_are_not_treated_as_baker_or_courier_occupations():
    assert classify_titles(['Kaufmann für Kurier-, Express- und Postdienstleistungen'])['collar'] == 'white'


def test_exact_url_merges_sources_but_not_different_vacancies():
    rows = [
        {'id':'c1','source':'catalog','company_id':'co','title':'Business Analyst','url':'https://example.com/jobs/1','published':True},
        {'id':'e1','source':'employer','company_id':'co','title':'Business Analyst','url':'https://example.com/jobs/1','published':False},
        {'id':'e2','source':'employer','company_id':'co','title':'Business Analyst','url':'https://example.com/jobs/2','published':False},
    ]
    jobs = deduplicate(rows)
    assert len(jobs) == 2
    assert sorted(len(job['records']) for job in jobs) == [1, 2]
    assert sum(job['published'] for job in jobs) == 1


def test_title_similarity_does_not_merge_jobs_or_unrelated_companies():
    rows = [
        {'id':'1','source':'employer','company_id':'a','title':'Analyst','url':''},
        {'id':'2','source':'employer','company_id':'a','title':'Analyst','url':''},
        {'id':'3','source':'employer','company_id':'b','title':'Analyst','url':'https://shared.example/job'},
        {'id':'4','source':'employer','company_id':'a','title':'Analyst','url':'https://shared.example/job'},
    ]
    assert len(deduplicate(rows)) == 4


def test_unresolved_and_inactive_jobs_do_not_make_employer_exclusion_candidates():
    jobs = [
        {'company_id':'co','company':'Employer','lifecycle':'active','collar':'blue'},
        {'company_id':'co','company':'Employer','lifecycle':'active','collar':'unresolved'},
        {'company_id':'co','company':'Employer','lifecycle':'inactive','collar':'white'},
    ]
    result = employer_summary(jobs)[0]
    assert result['blue'] == 1 and result['unresolved'] == 1
    assert result['inactive_or_unknown'] == 1
    assert result['classified_fraction'] == 0.5
    assert result['recommendation'] == 'insufficient_evidence'


def test_placeholder_policy_does_not_establish_an_employers_occupational_mix():
    jobs=[{'company_id':'co','company':'Employer','lifecycle':'active','collar':'blue',
           'reason':'owner_policy_placeholder'} for _ in range(30)]
    jobs.append({'company_id':'co','company':'Employer','lifecycle':'active','collar':'white',
                 'reason':'explicit_white_occupation'})
    result=employer_summary(jobs)[0]
    assert result['placeholder_exclusions']==30
    assert result['active_jobs']==1 and result['white']==1 and result['blue']==0
    assert result['recommendation']=='retain_mixed_employer'


def test_conflict_override_is_recorded_as_policy():
    result=classify_titles(['Electrician / Electrical Engineer'])
    assert result['collar'] == 'blue'
    assert result['reason'].startswith('owner_policy_')


def test_placeholder_is_policy_exclusion_not_invented_manual_occupation():
    result=classify_titles(['Stellenangebote'])
    assert result['collar']=='blue'
    assert result['reason']=='owner_policy_placeholder'
    assert result['policy_matches'][0]['term']=='stellenangebote'
    assert not result['blue_matches']


def test_other_unspecified_professional_titles_remain_unresolved():
    for title in ('Manager','Assistant','Working Student'):
        assert classify_titles([title])['collar']=='unresolved'


def test_url_query_is_part_of_vacancy_identity():
    rows = [{'source':'employer','id':str(i),'company_id':'co','title':'Analyst',
             'url':f'https://example.com/job?id={i}'} for i in (1,2)]
    assert len(deduplicate(rows)) == 2


def test_canonical_inactive_wins_over_old_producer_active():
    rows = [
        {'source':'catalog','id':'j','canonical_job_id':'j','company_id':'co', 'title':'Warehouse Picker',
         'url':'https://example.com/job','lifecycle':'inactive'},
        {'source':'employer','id':'e','company_id':'co','title':'Warehouse Picker',
         'url':'https://example.com/job','lifecycle':'active'},
    ]
    jobs = deduplicate(rows)
    assert len(jobs) == 1
    assert jobs[0]['lifecycle'] == 'inactive'
    assert employer_summary(jobs)[0]['blue'] == 0


def test_audit_covers_published_unpublished_unknown_and_untouched_employers(tmp_path):
    import json
    records = [
        {'kind':'manifest','counts':{'employer_tasks':2},'employer_tasks':[
            {'company_id':'new','company':'Employer'}, {'company_id':'untouched','company':'Untouched'}]},
        {'kind':'identity','source_identity_key':'old-company:old','winner_company_id':'new'},
        {'kind':'job','source':'catalog','id':'j','canonical_job_id':'j','company_id':'new',
         'company':'Employer','title':'Business Analyst','url':'https://example.com/1','lifecycle':'active','published':True},
        {'kind':'job','source':'employer','id':'e','company_id':'old','company':'Employer',
         'title':'Business Analyst','url':'https://example.com/1','lifecycle':'unknown'},
        {'kind':'job','source':'linkedin','id':'l','company_id':'new','company':'Employer',
         'title':'Warehouse Picker','url':'https://example.com/2','lifecycle':'active'},
        {'kind':'job','source':'linkedin_search','id':'s','company_id':'new','company':'Employer',
         'title':'Specialist','url':'https://example.com/3','lifecycle':'unknown'},
        {'kind':'coverage','company_id':'new','classification':'partial','outcome':'partial'},
    ]
    snapshot = tmp_path/'snapshot.jsonl'
    snapshot.write_text('\n'.join(json.dumps(r) for r in records),encoding='utf-8')
    summary = run_audit([snapshot],tmp_path/'output')
    import hashlib
    assert hashlib.sha256((tmp_path / 'output/rules.json').read_bytes()).hexdigest() == summary['rules_sha256']
    assert summary['input_records'] == 4
    assert summary['unique_jobs'] == 3
    assert summary['scopes']['published'] == {'white':1}
    assert summary['scopes']['active_not_in_publication'] == {'blue':1}
    assert summary['untouched_employers'] == 1
    assert summary['ai_calls'] == 0 and summary['production_changes'] is False
    assert (tmp_path/'output'/'unresolved_jobs.csv').exists()


def test_recorded_producer_external_id_merges_without_url_or_title_similarity(tmp_path):
    import json
    records = [
        {'kind':'external_id','source_id':'producer_linkedin_co','external_job_id':'123','canonical_job_id':'j'},
        {'kind':'job','source':'catalog','id':'j','canonical_job_id':'j','company_id':'co',
         'company':'Employer','title':'Business Analyst','url':'','lifecycle':'active','published':True},
        {'kind':'job','source':'linkedin','id':'123','linkedin_job_id':'123','company_id':'co',
         'company':'Employer','title':'Business Analyst','url':'','lifecycle':'active'},
    ]
    snapshot=tmp_path/'snapshot.jsonl'
    snapshot.write_text('\n'.join(json.dumps(r) for r in records),encoding='utf-8')
    summary=run_audit([snapshot],tmp_path/'output')
    assert summary['unique_jobs']==1
    assert summary['merged_duplicate_records']==1

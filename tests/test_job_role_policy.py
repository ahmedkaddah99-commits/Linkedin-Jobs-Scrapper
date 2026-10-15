import pytest
from backend.acquisition.job_role_policy import title_matches,exceeds_experience_limit
@pytest.mark.parametrize('title',['Business Analyst','Junior Business Analyst','Projektmanager Digitalisierung','Produktmanager','Prozessoptimierung Spezialist','Unternehmensberater','Gesch\u00e4ftsentwicklung','Eink\u00e4ufer','Customer Success Manager','Account Executive','IT-Berater','Junior SAP Consultant'])
def test_business_variants(title): assert title_matches(title)
@pytest.mark.parametrize('title',['Senior Business Analyst','Finance Analyst','Recruiting Coordinator','Marketing Manager','Software Engineer','Pflegefachkraft','Finanzanalyst','Personalreferent'])
def test_non_target(title): assert not title_matches(title)
@pytest.mark.parametrize('text',['At least three years of professional experience required','Mehr als zwei Jahre Berufserfahrung erforderlich','Mindestens 3-j\u00e4hrige Berufserfahrung','5+ years of full-time experience','Berufserfahrung: mindestens vier Jahre','3 bis 5 Jahre Erfahrung','Experience of over 2 years required'])
def test_required_experience(text): assert exceeds_experience_limit(text)
@pytest.mark.parametrize('text',['2 years of professional experience','2-3 years of experience','3 years of experience preferred','For over 10 years our company has served clients. No experience required.','Three years university degree. No experience required.','3 years of internship experience preferred'])
def test_other_numbers(text): assert not exceeds_experience_limit(text)

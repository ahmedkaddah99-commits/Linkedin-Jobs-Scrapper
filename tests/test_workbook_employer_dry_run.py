import json

import requests
import pytest

from scripts.workbook_employer_dry_run import collect, extract, normalized, same_listing_scope, deduplicate
from scripts.workbook_employer_dry_run import blue_collar_evidence, filter_saved_jobs
from scripts.workbook_employer_dry_run import atomic_json, saved_json, pending_resume_rows, Transport
from scripts.workbook_employer_dry_run import employer_link_allowed
from scripts.workbook_employer_dry_run import db_jobpostings
from bs4 import BeautifulSoup


def puma_detail_html(uid):
    schema={'@context':'https://schema.org','@type':'JobPosting','title':f'Product Manager {uid}',
            'description':'Brand introduction only.',
            'jobLocation':{'address':{'addressCountry':'Germany','addressLocality':'Herzogenaurach'}}}
    return f'''<script type="application/ld+json">{json.dumps(schema)}</script>
      <article class="job"><div class="row"><h2 class="js-job-additional">Your mission</h2>
      <div class="text">Manage product launches with international partners and own the product roadmap.</div></div>
      <div class="row"><h2 class="js-job-talent">Your talent</h2>
      <div class="text">Two years of product experience and strong English communication skills are required.</div></div></article>
      <a href="https://puma.wd502.myworkdayjobs.com/Jobs_at_Puma/job/Herzo/Role_R{uid}/apply">Apply now</a>
      <section class="job__related">Unrelated jobs and navigation</section>'''


def test_puma_paginates_exact_ui_filters_and_keeps_full_details(tmp_path):
    calls=[]
    class FakeTransport:
        def request(self,url,**kw):
            calls.append((url,kw))
            if url.endswith('/dd_job_search'):
                body=kw['json'];offset=body['from']
                assert body['area']=='corporate' and body['location']==['298']
                return response(url,{'hits':{'total':{'value':23,'relation':'eq'},'hits':[
                    {'_source':{'title':f'Product Manager {i}','url':f'/en/jobs/product-manager-r{i}',
                                'location_tids':['298'],'is_retail':0}} for i in range(offset,min(offset+10,23))]}})
            if '/en/jobs/' in url:return response(url,puma_detail_html(url.rsplit('r',1)[1]))
            return response(url,'<div id="dd-job-search"></div>')
    row={**company(),'career_url':'https://about.puma.com/en/careers/job-openings?area=corporate&location=298',
         'api_endpoint':'https://about.puma.com/dd_job_search','source_platform':'puma_public_search'}
    result,jobs=collect(row,FakeTransport(),tmp_path)
    assert result['status']=='complete'
    assert result['source_reported_count']==result['unique_listings_seen']==len(jobs)==23
    assert [kw['json']['from'] for url,kw in calls if url.endswith('/dd_job_search')]==[0,10,20]
    assert all(j['country']=='Germany' and j['job_id'].startswith('R') for j in jobs)
    assert all('product roadmap' in j['description'] and 'Two years' in j['description'] for j in jobs)
    assert all('Unrelated jobs' not in j['description'] for j in jobs)
    assert all(j['application_url'].endswith('/apply') for j in jobs)


def test_puma_does_not_treat_brand_intro_as_full_job_description(tmp_path):
    class FakeTransport:
        def request(self,url,**kw):
            if url.endswith('/dd_job_search'):
                return response(url,{'hits':{'total':{'value':1,'relation':'eq'},'hits':[
                    {'_source':{'title':'Product Manager','url':'/en/jobs/product-manager-r1','is_retail':0,'location_tids':['298']}}]}})
            return response(url,'<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':'Product Manager','description':'Brand introduction only. '*20})+'</script>')
    row={**company(),'career_url':'https://about.puma.com/en/careers/job-openings?area=corporate&location=298',
         'api_endpoint':'https://about.puma.com/dd_job_search'}
    result,jobs=collect(row,FakeTransport(),tmp_path)
    assert not jobs and result['details_failed']==1 and result['status']!='complete'


def test_siemens_listing_discovery_ignores_share_widgets():
    from scripts.workbook_employer_dry_run import crawl_extract
    url = 'https://jobs.siemens.com/en_US/externaljobs/SearchJobs/'
    detail = 'https://jobs.siemens.com/en_US/externaljobs/JobDetail/123'
    share = 'https://jobs.siemens.com/en_US/externaljobs/wechat/ShareJob?url=' + detail
    _, links = crawl_extract(f'<a href="{detail}">Project Manager</a><a href="{share}">WeChat</a>', url)
    assert {link['target'] for link in links} == {detail}


def test_adidas_detail_keeps_explicit_country_and_only_vacancy_body(tmp_path):
    url = 'https://jobs.adidas-group.com/job/Herzogenaurach-Project-Manager/123/'
    description = 'Manage wholesale design projects with regional stakeholders. ' * 5
    html = f'''<h1>Senior Project Manager</h1><nav>Navigation and unrelated jobs</nav>
    <span class="jobdescription">{description}</span>
    <span data-careersite-propertyid="city">Herzogenaurach</span>
    <span data-careersite-propertyid="country">DE</span>
    <a class="apply" href="/talentcommunity/apply/123/?locale=en_US">Apply now</a>'''
    _, jobs = extract(html, url)
    assert len(jobs) == 1
    job, raw, method = jobs[0]
    result = normalized(company(), job, raw, method, url, tmp_path)
    assert result['country'] == 'DE'
    assert result['city'] == 'Herzogenaurach'
    assert result['job_id'] == '123'
    assert 'regional stakeholders' in result['description']
    assert 'Navigation' not in result['description']
    assert raw['applicationUrl'] == 'https://jobs.adidas-group.com/talentcommunity/apply/123/?locale=en_US'


def response(url, payload):
    r = requests.Response()
    r.status_code = 200
    r.url = url
    r._content = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
    r.encoding = "utf-8"
    return r


@pytest.mark.parametrize("damaged", ["", '{"status":', "null", "{}"])
def test_resume_preserves_bad_receipt_and_queues_company(tmp_path, damaged):
    folder = tmp_path / "companies"
    folder.mkdir()
    bad = folder / "1.json"
    bad.write_text(damaged, encoding="utf-8")
    valid = {**company(), "rank": "2"}
    atomic_json(
        folder / "2.json", {"status": {"rank": "2", "collection_scope": "supplied_listing_all_countries"}, "jobs": []}
    )
    assert pending_resume_rows([company(), valid], tmp_path) == [company()]
    assert not bad.exists()
    assert next(folder.glob("1.json.corrupt-*")).read_text(encoding="utf-8") == damaged
    assert saved_json(folder / "2.json", "receipt")["status"]["rank"] == "2"


def test_failed_atomic_replace_preserves_previous_complete_file(tmp_path, monkeypatch):
    import scripts.workbook_employer_dry_run as runner

    path = tmp_path / "receipt.json"
    atomic_json(path, {"old": True})

    def fail(*args):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(runner.os, "replace", fail)
    with pytest.raises(OSError):
        atomic_json(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}
    assert list(tmp_path.glob("*.tmp")) == []


def test_resume_requeues_receipt_with_corrupt_raw_and_parser_rebuilds_raw(tmp_path):
    raw = {"description": "source wording"}
    job = {"title": "Engineer", "url": "https://example.org/job/1"}
    first = normalized(company(), job, raw, "json_ld", job["url"], tmp_path)
    rawpath = tmp_path / first["raw_record_file"]
    rawpath.write_text("", encoding="utf-8")
    atomic_json(
        tmp_path / "companies/1.json",
        {
            "status": {"rank": "1", "collection_scope": "supplied_listing_all_countries"},
            "jobs": [first],
        },
    )
    assert pending_resume_rows([company()], tmp_path) == [company()]
    assert list(rawpath.parent.glob(rawpath.name + ".corrupt-*"))
    normalized(company(), job, raw, "json_ld", job["url"], tmp_path)
    assert saved_json(rawpath) == raw


@pytest.mark.parametrize(
    "prior",
    [
        "",
        '{"url":',
        json.dumps({"url": "https://example.org/jobs", "status": 0, "body": "", "error": "ConnectionError"}),
    ],
)
def test_transport_recovers_bad_cache_and_retries_cached_network_failure(tmp_path, monkeypatch, prior):
    import hashlib
    import scripts.workbook_employer_dry_run as runner

    url = "https://example.org/jobs"
    transport = Transport(tmp_path)
    path = transport.cache / (hashlib.sha256(("GET" + url + "null").encode()).hexdigest() + ".json")
    path.write_text(prior, encoding="utf-8")
    calls = []

    class Session:
        def request(self, method, target, **kwargs):
            calls.append(target)
            return response(target, "restored public listing")

    monkeypatch.setattr(runner.requests, "Session", Session)
    assert transport.request(url).text == "restored public listing"
    assert transport.request(url).text == "restored public listing"
    assert calls == [url]
    assert saved_json(path, "cache")["status"] == 200


def company():
    return dict(
        company_name="Example AG",
        rank="1",
        batch="01",
        company_website="https://example.org",
        career_url="https://example.wd3.myworkdayjobs.com/External",
        source_platform="workday",
        scope_notes="",
        evidence_url="",
        api_endpoint="https://example.wd3.myworkdayjobs.com/wday/cxs/example/External/jobs",
        api_request_body='{"appliedFacets":{},"searchText":"Germany"}',
    )


def test_workday_walks_past_first_page_and_fetches_all_details(tmp_path):
    calls = []

    class Transport:
        def request(self, url, **kw):
            calls.append((url, kw))
            if "json" in kw:
                offset = kw["json"]["offset"]
                size = 20 if offset in (0, 20) else 5 if offset == 40 else 0
                return response(
                    url,
                    {
                        "total": 45 if offset == 0 else 0,
                        "jobPostings": [
                            {"externalPath": f"/job/Berlin/Role_R{i}"} for i in range(offset, offset + size)
                        ],
                    },
                )
            if "/wday/cxs/" in url:
                uid = url.rsplit("_", 1)[-1]
                return response(
                    url,
                    {
                        "jobPostingInfo": {
                            "title": "Engineer",
                            "jobReqId": uid,
                            "jobDescription": "An actual source description",
                            "externalUrl": url.replace("/wday/cxs/example", ""),
                            "country": {"descriptor": "Germany"},
                        },
                        "hiringOrganization": {"name": "Example AG"},
                    },
                )
            return response(url, "<html></html>")

    status, jobs = collect(company(), Transport(), tmp_path)
    assert status["pagination_complete"] is True
    assert status["status"] == "complete"
    assert len(jobs) == 45
    assert {j["job_id"] for j in jobs} == {f"R{i}" for i in range(45)}
    assert [kw["json"]["offset"] for _, kw in calls if "json" in kw] == [0, 20, 40]
    assert all(not kw["json"]["searchText"] and not kw["json"]["appliedFacets"] for _, kw in calls if "json" in kw)


def test_repeated_workday_page_is_partial_not_complete(tmp_path):
    class Transport:
        def request(self, url, **kw):
            if "json" in kw:
                return response(url, {"total": 2, "jobPostings": [{"externalPath": "/job/Berlin/Role_R1"}]})
            if "/wday/cxs/" in url:
                return response(
                    url,
                    {
                        "jobPostingInfo": {
                            "title": "Role",
                            "jobReqId": "R1",
                            "externalUrl": "https://example.org/job/R1",
                        }
                    },
                )
            return response(url, "<html></html>")

    status, jobs = collect(company(), Transport(), tmp_path)
    assert status["status"] == "partial"
    assert not status["pagination_complete"]
    assert "repeated_page" in status["error"]


def test_html_listing_cannot_inherit_unrelated_application_link():
    html = (
        "<h1>Stellenangebote</h1><main>"
        + ("Information about working here. " * 30)
        + '</main><a href="/apply">Jetzt bewerben</a>'
    )
    _, jobs = extract(html, "https://example.org/jobs/search")
    assert jobs == []


def test_missing_id_uses_url_and_does_not_invent_employer(tmp_path):
    j = normalized(
        company(),
        {"title": "Role", "url": "https://example.org/job/123"},
        {},
        "json_ld",
        "https://example.org",
        tmp_path,
    )
    assert j["job_id"] == ""
    assert j["deduplication_basis"] == "canonical_url_fallback"
    assert j["legal_employer"] == ""


def test_datafeed_envelope_count_is_verified(tmp_path):
    row = company()
    row["api_endpoint"] = "https://example.org/jobs.feed.json"
    raw = {
        "@type": "JobPosting",
        "title": "Role",
        "url": "https://example.org/jobs/123",
        "identifier": {"value": "123"},
    }

    class Transport:
        def request(self, url, **kw):
            return (
                response(url, {"numberOfItems": 1, "dataFeedElement": [{"item": raw}]})
                if "feed" in url
                else response(url, "<html></html>")
            )

    status, jobs = collect(row, Transport(), tmp_path)
    assert status["status"] == "complete"
    assert len(jobs) == 1


def test_pagination_does_not_branch_into_filter_combinations():
    assert same_listing_scope(
        "https://example.org/jobs?country=DE&page=2", "https://example.org/jobs?country=DE&page=1"
    )
    assert not same_listing_scope(
        "https://example.org/jobs?country=FR&page=2", "https://example.org/jobs?country=DE&page=1"
    )


def test_microdata_preserves_explicit_source_fields():
    html = (
        """<div itemscope itemtype="https://schema.org/JobPosting">
    <h1 itemprop="title">Ingenieur</h1><meta itemprop="identifier" content="REQ-9">
    <div itemprop="description">"""
        + ("Source job description. " * 8)
        + """</div>
    <span itemprop="addressLocality">Berlin</span><meta itemprop="addressCountry" content="DE">
    <div itemprop="hiringOrganization"><span itemprop="name">Example AG</span></div></div>"""
    )
    _, jobs = extract(html, "https://example.org/job/REQ-9")
    assert jobs[0][0]["job_id"] == "REQ-9"
    assert jobs[0][0]["company"] == "Example AG"
    assert jobs[0][1]["jobLocation"]["address"]["addressLocality"] == "Berlin"


def test_stable_id_and_url_fallback_for_same_job_merge(tmp_path):
    first = normalized(
        company(),
        {"title": "Engineer", "job_id": "R123", "url": "https://example.org/job/R123", "location": "Berlin"},
        {},
        "json_ld",
        "https://example.org",
        tmp_path,
    )
    second = normalized(
        company(),
        {"title": "Engineer", "url": "https://example.org/job/R123"},
        {},
        "embedded_json",
        "https://example.org",
        tmp_path,
    )
    records, removed = deduplicate([second, first])
    assert len(records) == 1
    assert removed == 1
    assert records[0]["job_id"] == "R123"
    assert records[0]["location"] == "Berlin"


def test_organization_identifier_name_is_not_a_job_id(tmp_path):
    j = normalized(
        company(),
        {"title": "Role", "url": "https://example.org/job/123"},
        {"identifier": {"name": "Employer AG"}},
        "json_ld",
        "https://example.org",
        tmp_path,
    )
    assert j["job_id"] == ""


def test_workday_source_dates_are_not_inferred_posting_dates(tmp_path):
    raw = {"startDate": "2026-11-01", "endDate": "2027-01-01", "postedOn": "Posted 30+ Days Ago"}
    j = normalized(
        company(),
        {"title": "Engineer", "url": "https://example.org/job/R1", "source_posted_at": "2026-11-01"},
        raw,
        "workday_cxs",
        "https://example.org",
        tmp_path,
    )
    assert j["date_posted"] == ""
    assert j["date_posted_raw"] == "Posted 30+ Days Ago"
    assert j["source_start_date"] == "2026-11-01"
    assert j["source_end_date"] == "2027-01-01"
    assert j["application_deadline"] == ""


@pytest.mark.parametrize(
    "title",
    [
        "Warehouse Picker",
        "LKW-Fahrer",
        "Reinigungskraft",
        "Elektriker",
        "Kassierer",
        "Verkäufer / Kassierer",
        "Verkäufer mit Kassiertätigkeit",
        "Mitarbeiter Warenverräumung",
        "Aushilfe im Verkauf",
    ],
)
def test_blue_collar_filter_uses_explicit_occupations(title):
    assert blue_collar_evidence(title)


@pytest.mark.parametrize(
    "title",
    [
        "Mechanical Engineer",
        "Warehouse Management Software Developer",
        "Driver Software Engineer",
        "Teamleiter Produktion",
        "Sachbearbeiter Logistik",
        "Working Student",
        "Random unknown job",
        "Aushilfe Buchhaltung",
        "Teamleiter Kasse",
        "Softwareentwickler Kassensysteme",
    ],
)
def test_blue_collar_filter_retains_professional_and_ambiguous_titles(title):
    assert blue_collar_evidence(title) is None


def test_filtered_workday_paginates_all_listings_but_skips_blue_details(tmp_path):
    details = []

    class Transport:
        def request(self, url, **kw):
            if "json" in kw:
                offset = kw["json"]["offset"]
                return response(
                    url,
                    {
                        "total": 2 if offset == 0 else 0,
                        "jobPostings": [
                            {
                                "title": "Warehouse Picker" if offset == 0 else "Software Engineer",
                                "externalPath": f"/job/Role_R{offset}",
                            }
                        ],
                    },
                )
            if "/wday/cxs/" in url:
                details.append(url)
                return response(
                    url,
                    {
                        "jobPostingInfo": {
                            "title": "Software Engineer",
                            "jobReqId": "R1",
                            "externalUrl": "https://example.org/job/R1",
                        }
                    },
                )
            return response(url, "<html></html>")

    status, jobs = collect(company(), Transport(), tmp_path, exclude_blue_collar=True)
    assert status["status"] == "complete"
    assert status["source_reported_count"] == 2
    assert status["blue_collar_excluded"] == 1
    assert len(jobs) == len(details) == 1
    assert details[0].endswith("Role_R1")
    assert json.loads((tmp_path / "companies/1.json").read_text())["exclusions"][0]["stage"] == "api_listing"


def test_html_blue_anchor_skips_detail_even_with_duplicate_generic_link(tmp_path):
    row = {**company(), "career_url": "https://example.org/careers", "api_endpoint": "", "source_platform": "custom"}
    calls = []

    class Transport:
        def request(self, url, **kw):
            calls.append(url)
            if url == row["career_url"]:
                return response(
                    url,
                    '<a href="/job/blue">Warehouse Picker</a><a href="/job/blue">Read more</a><a href="/job/white">Software Engineer</a>',
                )
            assert url.endswith("/white")
            return response(
                url,
                '<script type="application/ld+json">'
                + json.dumps(
                    {
                        "@type": "JobPosting",
                        "title": "Software Engineer",
                        "url": url,
                        "description": "Source description " * 20,
                    }
                )
                + "</script>",
            )

    status, jobs = collect(row, Transport(), tmp_path, exclude_blue_collar=True)
    assert status["blue_collar_excluded"] == 1
    assert len(jobs) == 1
    assert not any(url.endswith("/blue") for url in calls)


def test_saved_receipt_filter_preserves_audit_and_is_idempotent():
    data = {
        "status": {},
        "jobs": [
            {"title": "Warehouse Picker", "job_detail_url": "https://example.org/job/1"},
            {"title": "Engineer", "job_detail_url": "https://example.org/job/2"},
        ],
    }
    filter_saved_jobs(data)
    filter_saved_jobs(data)
    assert len(data["jobs"]) == 1
    assert len(data["exclusions"]) == 1
    assert data["status"]["jobs_collected"] == 1
    assert data["status"]["blue_collar_excluded"] == 1


@pytest.mark.parametrize(
    "title",
    [
        "Verkäufer (m/w/d)",
        "Verkäuferin",
        "Store Sales Assistant",
        "Retail Sales Associate",
        "Praktikum Schüler Verkauf (m/w/d)",
        "Ausbildung Verkäufer / Kaufmann im Einzelhandel 2027",
        "Fachverkäufer Bedientheke",
        "Filialmitarbeiter",
        "Ausbildung Kaufmann im Einzelhandel",
    ],
)
def test_owner_excludes_frontline_retail_including_store_training(title):
    assert blue_collar_evidence(title)


@pytest.mark.parametrize(
    "title",
    [
        "Filialleiter Verkauf",
        "Store Assistant Manager",
        "Marktleitung",
        "Office Sales Assistant",
        "Sachbearbeiter Verkauf",
        "Verkäufer Innendienst",
        "Nachwuchsführungskraft Verkauf",
        "Duales Studium BWL Verkauf",
        "Ausbildung Kaufmann für Büromanagement",
        "Regional Sales Manager",
        "Software Engineer Retail",
        "Data Warehouse Engineer",
        "Assistant",
        "Sales Assistant",
        "Management Trainee Verkauf",
        "Retail Sales Associate Team Lead",
        "1",
        "2",
        "10",
        "Jobs",
        "Stellenangebote",
    ],
)
def test_retail_exclusion_preserves_managers_office_and_unresolved_roles(title):
    assert blue_collar_evidence(title) is None


def test_numeric_pagination_is_followed_despite_placeholder_audit_rule(tmp_path):
    row = {**company(), "career_url": "https://example.org/jobs", "api_endpoint": "", "source_platform": "custom"}
    calls = []

    class Transport:
        def request(self, url, **kw):
            calls.append(url)
            if url == row["career_url"]:
                return response(url, '<a href="/job/blue">Warehouse Picker</a><a href="/jobs/page/2">2</a>')
            if url.endswith("/page/2"):
                return response(url, '<a href="/job/white">Software Engineer</a>')
            assert url.endswith("/white")
            return response(
                url,
                '<script type="application/ld+json">'
                + json.dumps(
                    {
                        "@type": "JobPosting",
                        "title": "Software Engineer",
                        "url": url,
                        "description": "Source description " * 20,
                    }
                )
                + "</script>",
            )

    status, jobs = collect(row, Transport(), tmp_path, exclude_blue_collar=True)
    assert status["blue_collar_excluded"] == 1
    assert len(jobs) == 1
    assert "https://example.org/jobs/page/2" in calls


def test_employer_crawl_never_follows_job_board_footer_links(tmp_path):
    row = {**company(), "career_url": "https://example.org/careers", "api_endpoint": "", "source_platform": "custom"}
    calls = []

    class Transport:
        def request(self, url, **kw):
            calls.append(url)
            assert "xing.com" not in url
            return response(url, '<a href="https://www.xing.com/jobs/software-developer-99">Jobs</a>')

    status, jobs = collect(row, Transport(), tmp_path)
    assert jobs == []
    assert status["external_links_skipped"] == 1
    assert calls == [row["career_url"]]
    assert employer_link_allowed("https://example.org/job/1", [row["career_url"]])
    assert employer_link_allowed("https://example.wd3.myworkdayjobs.com/job/1", [row["career_url"]])
    assert not employer_link_allowed("https://unrelated.org/job/1", [row["career_url"]])


def test_db_uses_real_page_cursor_and_skips_manual_details(tmp_path):
    row = {
        **company(),
        "career_url": "https://db.jobs/service/search/de-de/5441588?country=Deutschland",
        "api_endpoint": "",
        "source_platform": "custom",
    }
    calls = []

    class Transport:
        def request(self, url, **kw):
            calls.append(url)
            if "/service/search/" in url:
                index = 1 if "pageNum=1" in url else 0
                titles = ["Warehouse Picker", "Software Engineer"] if index == 0 else ["Project Manager"]
                cards = "".join(
                    f'<a data-job-id="{index * 2 + i}" href="/de-de/Suche/role?jobId={index * 2 + i}"><span class="m-search-hit__title-text">{title}</span></a>'
                    for i, title in enumerate(titles)
                )
                return response(
                    url,
                    '<div id="resultItems" data-hits="3">'
                    + cards
                    + '</div><a href="https://www.xing.com/jobs/foo">Jobs</a>',
                )
            uid = url.rsplit("=", 1)[-1]
            assert uid != "0"
            return response(
                url,
                '<script type="application/ld+json">'
                + json.dumps(
                    {
                        "@type": "JobPosting",
                        "title": "Software Engineer" if uid == "1" else "Project Manager",
                        "url": url,
                        "description": "Original source text " * 20,
                    }
                )
                + "</script>",
            )

    status, jobs = collect(row, Transport(), tmp_path, exclude_blue_collar=True)
    assert status["status"] == "complete"
    assert status["unique_listings_seen"] == 3
    assert status["blue_collar_excluded"] == 1
    assert len(jobs) == 2
    assert all("xing.com" not in u for u in calls)
    assert any("pageNum=1" in u for u in calls)


def test_db_literal_newline_in_description_is_preserved():
    html = '<script type="application/ld+json">{"@type":"JobPosting","title":"Engineer","description":"Source line one\nSource line two"}</script>'
    raw = db_jobpostings(BeautifulSoup(html, "lxml"))
    assert raw[0]["description"] == "Source line one\nSource line two"


def test_rail_manual_titles_excluded_while_professional_context_retained():
    assert blue_collar_evidence("Streckenlokführer im bundesweiten Güterverkehr")
    assert blue_collar_evidence("Ausbildung Lokrangierführer:in im Güterverkehr")
    assert blue_collar_evidence("Softwareentwickler Rangierbegleiter") is None


def test_db_malformed_json_uses_only_explicit_job_text_and_metadata():
    from scripts.workbook_employer_dry_run import db_html_jobposting

    soup = BeautifulSoup(
        """<h1>IT Lead</h1><script>var digitalData = {
        "jobCompany": "Source Employer", "jobCity": "Schkopau"};</script>
        <nav>Unrelated navigation</nav><div class="o-jobad__text">Actual tasks and qualifications</div>
        <footer>Unrelated footer</footer>""",
        "lxml",
    )
    raw = db_html_jobposting(soup, "https://db.jobs/de-de/Suche/example")
    assert raw["hiringOrganization"]["name"] == "Source Employer"
    assert raw["jobLocation"]["address"]["addressLocality"] == "Schkopau"
    assert "Actual tasks" in raw["description"]
    assert "Unrelated" not in raw["description"]
    assert db_html_jobposting(soup, "https://other.example/job") is None

"""Deterministic German/English title audit. Offline; no model or database writes.

Inputs are title-only JSONL snapshots. Classification never reads descriptions,
employer industry or previous AI classifications. Unknowns remain unresolved.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

RULE_VERSION = 'runr_title_collar_de_en_v3_web_enriched'

# Owner instruction in annotation 1: these exclusions take precedence over
# occupational matches. A heading is an exclusion policy, not proof of a trade.
OWNER_BLUE_RULES = {
    'confirmed_manual_occupations': r'\b(?:augenoptiker\w*|optician\w*|haustechniker\w*|reifenwechsel\w*)\b',
    'aushilfe': r'\b\w*aushilf\w*\b|\btemporary helper\w*\b',
    'service_technician': r'\b\w*servicetechniker\w*\b|\b(?:field )?service technician\w*\b',
    'placeholder': r'\bstellenangebote\b|\bjobtitel platzhalter\b|^(?:search jobs|job listings|job vacancies|current vacancies|current jobs|vacancies|careers|jobs|job title|jobtitel|\d+)$',
}
OWNER_POLICY = {'source': 'User annotation 1', 'annotation_index': 1,
                'blue_title_overrides': OWNER_BLUE_RULES,
                'white_blue_conflict_resolution': 'blue'}

# Explicit occupations, not a blacklist of employer sectors or broad context
# words such as office, warehouse, production, construction or cleaning.
WHITE_RULES = {
    'commercial_occupations_de': r'\b(?:handelsfachwirt\w*|fachwirt\w*|immobilienmakler\w*|immobilienkauf\w*|immobilienfachwirt\w*|fachverkaeufer\w*|buchhaendler\w*|versicherungsmanagement|bankmanagement|aussendienstmitarbeiter\w*|serviceberater\w*|filialleitung|filialverantwortlich\w*|marktleiter\w*|marktleitung)\b',
    'professional_care_leadership': r'\b(?:pflegedienstleitung|pflegedienstleiter\w*|wohnbereichsleitung|wohnbereichsleiter\w*|pflegeleitung|wundmanager\w*)\b',
    'hospitality_administration': r'\b(?:front office (?:agent|manager)|hotel (?:receptionist|manager)|hotelkauf\w*)\b',
    'occupational_safety': r'\b(?:fachkraft fuer arbeitssicherheit|health and safety (?:manager|officer|specialist)|health safety (?:manager|officer|specialist)|sicherheitsingenieur\w*)\b',
    'analysis': r'\b(?:analyst\w*|analytiker\w*|geschaeftsanalyst\w*|business intelligence|business analysis|datenanalys\w*|data analytics)\b',
    'software': r'\b(?:software\w*|developer\w*|entwickler\w*|softwareentwickler\w*|programmierer\w*|programmer\w*|webentwickler\w*|anwendungsentwickler\w*|applikationsentwickler\w*|full ?stack|front ?end|back ?end|devops|devsecops|site reliability|sre|scrum master|agile coach|product owner|test automation|qa automation)\b',
    'engineering_de': r'\b\w*ingenieur(?:in|innen|e|en|s)?\b|\bingenieurwesen\b',
    'engineering_en': r'\b(?:software|hardware|systems?|electrical|electronics?|mechanical|civil|structural|design|development|process|quality|production|manufacturing|industrial|chemical|biomedical|aerospace|automotive|network|security|cloud|data|ai|machine learning|application|applications|project|sales|solutions?|platform|test|validation|verification|research|r ?and ?d|robotics|embedded|controls?|automation|simulation|reliability|environmental|energy|rf|radio|commissioning|optical|optics|firmware|digital|semiconductor) (?:\w+ ){0,2}engineer\w*\b',
    'data_science': r'\b(?:data scientist\w*|data science|datenwissenschaft\w*|statistician\w*|statistiker\w*|biostatistician\w*|mathematiker\w*|mathematician\w*|physiker\w*|physicist\w*|economist\w*|oekonom\w*)\b',
    'research': r'\b(?:scientist\w*|wissenschaftler\w*|wissenschaftlich\w*|researcher\w*|research (?:associate|assistant|fellow|scientist|manager)|forsch\w*ingenieur\w*|forscher\w*|postdoc\w*|doktorand\w*|phd|chemiker\w*|biolog\w*|microbiologist\w*|mikrobiolog\w*|chemist\w*|pharmazeut\w*|pharmacist\w*|apotheker\w*)\b',
    'information_technology': r'\b(?:informatik\w*|informatiker\w*|fachinformatiker\w*|wirtschaftsinformatik\w*|it|ict|edv|cybersecurity|cyber security|information security|sap|salesforce|servicenow|erp|database administrator|datenbankadministrator\w*|systemadministrator\w*|system administration|system admin|network administrator|netzwerkadministrator\w*|cloud architect|solution architect|enterprise architect|penetration tester|help ?desk|desktop support)\b',
    'accounting_finance': r'\b(?:accountant\w*|accounting|bookkeep\w*|buchhalt\w*|bilanzbuchhalt\w*|finanzbuchhalt\w*|controller\w*|controlling|financial\w*|finance|finanz\w*|treasury|treasurer|auditor\w*|audit\w*|revisor\w*|revision|tax|steuerfach\w*|steuerberater\w*|steuerberatung|payroll|lohn\w*buchhalt\w*|gehaltsabrechn\w*|actuary|actuarial|aktuar\w*|underwriter\w*|versicherungskauf\w*|bankkauf\w*|investment|portfolio manager|wealth manager|kredit\w*|risk manager|risk management|compliance\w*)\b',
    'business_administration': r'\b(?:sachbearbeiter\w*|sachbearbeitung|kaufmaennisch\w*|kaufmann|kauffrau|kaufleute|industriekauf\w*|buerokauf\w*|bueromanagement|bueromitarbeiter\w*|bueroassist\w*|betriebswirt\w*|business administrat\w*|administrative (?:assistant|specialist|officer)|administration specialist|office (?:manager|administrator|assistant|coordinator)|executive assistant|management assistant|geschaeftsfuehrungsassist\w*|assist\w* der geschaeftsfuehrung|sekretaer\w*|secretar\w*|empfangsmitarbeiter\w*|receptionist\w*|disponent\w*|disposition|dispatcher\w*|supply chain|logistikplaner\w*|logistikmanager\w*|logistics (?:planner|manager|coordinator|specialist)|purchas\w*|procurement|buyer\w*|einkaeufer\w*|einkauf|beschaffung\w*|export manager|import manager|order management|auftragsabwicklung)\b',
    'sales_marketing': r'\b(?:sales\w*|vertrieb\w*|vertriebs\w*|verkaeufer\w*|verkauf\w*|kundenberater\w*|kundenberatung|kundenbetreuer\w*|kundenbetreuung|customer (?:success|service|support|care|experience)|account (?:manager|executive|specialist)|key account|business develop\w*|geschaeftsentwicklung|marketing\w*|market research|marktforsch\w*|brand manager|growth manager|social media|seo|sem|copywriter\w*|texter\w*|content (?:writer|manager|creator|editor|specialist)|kommunikationsmanager\w*|communications? (?:manager|specialist|officer)|public relations|fundrais\w*|merchandis\w*|retail sales)\b',
    'human_resources': r'\b(?:recruit\w*|rekrut\w*|talent acquisition|talent management|human resources|hr|people (?:partner|operations|manager)|personalreferent\w*|personal\w*management|personal\w*entwicklung|personalsachbearbeiter\w*|personalberater\w*|personalbetreuer\w*|personalleiter\w*|arbeitsvermittler\w*|hr business partner)\b',
    'consulting': r'\b(?:consultant\w*|consulting|berater\w*|beratung|unternehmensberater\w*|advis[oe]r\w*|advisory|consult\w*|strategy|strateg\w*)\b',
    'legal': r'\b(?:lawyer\w*|attorney\w*|legal\w*|paralegal\w*|jurist\w*|rechtsanw\w*|rechtsreferendar\w*|rechtsfach\w*|notar\w*|patent\w*|datenschutz\w*)\b',
    'clinical_professional': r'\b(?:arzt\w*|aerzt\w*|facharzt\w*|assisten zarzt|assistenzarzt\w*|oberarzt\w*|chefarzt\w*|zahnarzt\w*|zahnaerzt\w*|physician\w*|doctor\w*|surgeon\w*|chirurg\w*|medical (?:professional|doctor|officer)|registered nurse|nurse\w*|nursing|pflegefach\w*|gesundheits\w*pfleger\w*|krankenpfleger\w*|altenpfleger\w*|heilerziehungspfleger\w*|therapeut\w*|therapist\w*|physiotherap\w*|ergotherap\w*|psycholog\w*|psychotherap\w*|logopaed\w*|hebamme\w*|midwi\w*|radiolog\w*|medizinisch\w* fachangestellte\w*|zahnmedizinisch\w* fachangestellte\w*|mfa|zfa|mta|mtr|mtra|pta|clinical research)\b',
    'education_care': r'\b(?:teacher\w*|lehrer\w*|lehrkraft\w*|dozent\w*|lecturer\w*|professor\w*|erzieher\w*|paedagog\w*|sozialpaedagog\w*|sozialarbeiter\w*|social worker|educator\w*|education specialist|ausbilder\w*|trainer\w*|tutor\w*|schulbegleiter\w*|lernbegleiter\w*|heilpaedagog\w*|studienberater\w*)\b',
    'design_architecture': r'\b(?:designer\w*|design\w*|ux|ui|grafiker\w*|grafikdesign\w*|graphic\w*|architekt\w*|architect\w*|konstrukteur\w*|konstruktion\w*|technisch\w* zeichner\w*|technisch\w* systemplaner\w*|bauzeichner\w*|technical writer|technisch\w* redakteur\w*|redakteur\w*|editor\w*|journalist\w*|uebersetzer\w*|translator\w*|dolmetscher\w*)\b',
    'planning_project': r'\b(?:projekt\w*|project\w*|program manager|programme manager|program management|programmmanager\w*|product manager|produktmanager\w*|produktmanagement|product management|planer\w*|planung\w*|stadtplan\w*|verkehrsplan\w*|bauleiter\w*|bauleitung|construction manager|construction management|quantity surveyor|kalkulator\w*|kalkulation|estimato[rn]\w*)\b',
    'professional_leadership': r'\b(?:chief (?:executive|financial|technology|technical|operating|information|marketing|people|digital|scientific|commercial) officer|ceo|cfo|cto|coo|cio|cmo|cdo|geschaeftsfuehrer\w*|geschaeftsfuehrung|vorstand\w*|managing director|vice president|vp|director\w*|direktor\w*|head of|bereichsleiter\w*|bereichsleitung|abteilungsleiter\w*|abteilungsleitung|betriebsleiter\w*|betriebsleitung|niederlassungsleiter\w*|filialleiter\w*|store manager|branch manager)\b',
    'dual_degree': r'\b(?:dual\w* studium|dual\w* student\w*|bachelor|master of (?:science|arts|engineering)|mba|b eng|b sc|b a)\b',
}

BLUE_RULES = {
    'compound_manual_occupations_de': r'\b\w*(?:elektriker|elektroniker|mechatroniker|mechaniker|lackierer|schweisser|monteur|maschinenfuehrer|anlagenfuehrer|staplerfahrer)(?:in|innen|meister\w*)?\b',
    'manual_services_de': r'\b(?:barbier\w*|haushaltshilfe\w*|hauswirtschaftskraft\w*|hauswirtschaftshelfer\w*|kuechenkraft\w*|karosseriebauer\w*|karosserie und fahrzeugbaumechaniker\w*|reifenmonteur\w*)\b',
    'electrical_trades': r'\b(?:elektriker\w*|elektroniker\w*|elektroinstallateur\w*|electrician\w*|electrical installer\w*|elektromonteur\w*)\b',
    'mechanical_trades': r'\b(?:mechatroniker\w*|mechatronics technician\w*|mechaniker\w*|mechanic(?:s)?|industriemechaniker\w*|anlagenmechaniker\w*|kfz\w*mechaniker\w*|kfz\w*mechatroniker\w*|schlosser\w*|metallbauer\w*|werkzeugmacher\w*|werkzeugmechaniker\w*|zerspanungsmechaniker\w*|dreher\w*|fraeser\w*|welder\w*|schweisser\w*|metalworker\w*|millwright\w*|machinist\w*|toolmaker\w*|fitte[rn]\w*|monteur\w*|montagehelfer\w*|montagemitarbeiter\w*)\b',
    'construction_trades': r'\b(?:dachdecker\w*|roofer\w*|zimmerer\w*|zimmermann|carpenter\w*|tischler\w*|schreiner\w*|joiner\w*|maurer\w*|bricklayer\w*|betonbauer\w*|strassenbauer\w*|tiefbauer\w*|bauarbeiter\w*|bauhelfer\w*|construction worker\w*|construction labor\w*|geruestbauer\w*|scaffolder\w*|trockenbauer\w*|stuckateur\w*|fliesenleger\w*|tiler\w*|bodenleger\w*|maler\w*|lackierer\w*|painter\w*|plumber\w*|klempner\w*|sanitaerinstallateur\w*|heizungsinstallateur\w*|isolie rer|isolierer\w*|glaser\w*)\b',
    'production_operators': r'\b(?:maschinenbediener\w*|maschinenfuehrer\w*|anlagenbediener\w*|anlagenfuehrer\w*|machine operator\w*|production operator\w*|manufacturing operator\w*|plant operator\w*|process operator\w*|produktionsmitarbeiter\w*|produktionshelfer\w*|produktionsarbeiter\w*|fertigungsmitarbeiter\w*|fertigungshelfer\w*|production worker\w*|factory worker\w*|assembly worker\w*|assembly operator\w*|assembler\w*|montierer\w*|cnc (?:operator|machinist)|cnc dreher\w*|cnc fraeser\w*|packaging operator\w*|abfueller\w*|drucker\w*|printer operator\w*|drucktechnolog\w*|giesser\w*|verfahrensmechaniker\w*|oberflaechenbeschichter\w*)\b',
    'warehouse_handling': r'\b(?:lagerarbeiter\w*|lagerhelfer\w*|lagermitarbeiter\w*|lagerist\w*|fachlagerist\w*|kommissionierer\w*|komisjoner\w*|staplerfahrer\w*|gabelstaplerfahrer\w*|forklift (?:driver|operator)|warehouse (?:worker|picker|operative|associate|operator)|order picker\w*|picker\w*|packer\w*|verpacker\w*|paketsortierer\w*|paketabfertiger\w*|sortiermitarbeiter\w*|package handler\w*|material handler\w*|fachkraft fuer lagerlogistik|lager und transportarbeiter\w*|belader\w*|verlader\w*)\b',
    'driving': r'\b(?:fahrer\w*|kraftfahrer\w*|berufskraftfahrer\w*|lkw fahrer\w*|busfahrer\w*|taxifahrer\w*|lieferfahrer\w*|delivery driver\w*|truck driver\w*|bus driver\w*|driver\w*|lokfuehrer\w*|triebfahrzeugfuehrer\w*|train driver\w*|zugbegleiter\w*|rangierer\w*|zusteller\w*|paketzusteller\w*|postbote\w*|kurier(?:in|innen|e|en)?(?! express und postdienstleistungen)|courier\w*|auslieferungsfahrer\w*|fahrzeugfuehrer\w*|kranfuehrer\w*|baggerfahrer\w*)\b',
    'cleaning': r'\b(?:reinigungskraft\w*|reinigungskraeft\w*|reinigungsmitarbeiter\w*|gebaeudereiniger\w*|cleaner\w*|cleaning operative\w*|janitor\w*|hausmeister\w*|hauswart\w*|caretaker\w*|housekeep\w*|zimmermaedchen\w*|room attendant\w*|muellwerker\w*|entsorgungshelfer\w*)\b',
    'food_hospitality': r'\b(?:koch\w*|koech\w*|cook\w*|chef(?:s)?|kuechenhilfe\w*|kuechenmitarbeiter\w*|kuechenchef\w*|kitchen (?:assistant|helper|porter)|spueler\w*|spuelkraft\w*|dishwasher\w*|kellner\w*|waiter\w*|waitress\w*|waiting staff|servicekraft\w*|servicemitarbeiter\w*|restaurant server|bartender\w*|barkeeper\w*|barista\w*|baecker(?:in|innen|meister\w*)?|baker\w*|konditor\w*|pastry chef|fleischer(?:in|innen|meister\w*)?|metzger\w*|butcher\w*|food preparation worker\w*)\b',
    'personal_manual_services': r'\b(?:friseur\w*|frisoer\w*|hairdresser\w*|barber\w*|kosmetiker\w*|beautician\w*|schneider\w*|tailor\w*|naeher\w*|seamstress\w*|sewer|gaertner\w*|gardener\w*|landscaper\w*|gruenpfleger\w*|landwirt\w*|farmer\w*|forstwirt\w*|forstarbeiter\w*|erntehelfer\w*|farm worker\w*|stallhelfer\w*)\b',
    'manual_supervision': r'\b(?:vorarbeiter\w*|foreman\w*|polier\w*|obermonteur\w*|werkpolier\w*)\b',
    'manual_support': r'\b(?:pflegehelfer\w*|pflegehilfskraft\w*|pflegeassistent\w*|nursing assistant|healthcare assistant|care assistant|altenpflegehelfer\w*|sicherheitsmitarbeiter\w*|security guard\w*|wachmann|wachpersonal|pfoertner\w*|cashier\w*|kassierer\w*|regalauffueller\w*|shelf stacker\w*|warenverraeumer\w*|aushilfe warenverraeumung)\b',
}

# Title-only evidence cannot distinguish these hands-on/professional boundaries.
AMBIGUOUS_RULES = {
    'non_culinary_chef': r'\bchef de (?:projet|project|produit|service|mission)\b',
    'service_engineering': r'\b(?:field service|service|maintenance|facility|facilities) engineer\w*\b|\bservicetechniker\w*\b|\bservice technician\w*\b',
    'operational_team_lead': r'\b(?:teamleiter\w*|teamleitung|schichtleiter\w*|schichtleitung|shift (?:leader|manager|supervisor)|team (?:leader|lead)|supervisor)\b.*\b(?:produktion\w*|production|fertigung\w*|lager\w*|warehouse|reinigung\w*|cleaning|montage\w*|assembly|logistik\w*|logistics)\b',
}

WHITE_RULES.update({
    'commercial_compounds': r'\b\w*(?:kaufmann|kauffrau|kaufleute|kaufmaenner|kauffrauen)\b|\bbaufinanzierung\w*\b',
    'professional_compounds_de': r'\b\w*(?:buchhalter|kundenberater|finanzierungsberater|konstrukteur|paedagoge|lehrer|betriebswirt|logistikkoordinator)(?:in|innen)?\b|\b(?:steuerassistent\w*|teamassistenz|verwaltungsfachkraft\w*|risikomanager\w*|call center agent|partner manager|standortleitung|standortdaten spezialist|mobile mapping operator|pflegekraft\w*|kinderpfleger\w*|pflegepaedagog\w*)\b',
    'retail_leadership': r'\b(?:teamleiter\w*|teamleitung)\b.{0,30}\beinzelhandel\b|\b(?:filialbetreuer\w*|visual commercial|leiter nachhilfe institut)\b',
    'technical_professionals': r'\b(?:arbeitsvorbereiter\w*|arbeitsvorbereitung|elektrotechniker\w*|prozessautomatisierung|ki integration|praxisanleit\w*|hse (?:manager|coordinator)|health safety coordinator|brandschutzbeauftragter\w*|sicherheitsfachkraft\w*|sifa|arbeitssicherheit|technisch\w* produktdesigner\w*|qualitaetsmanagement|qualitaetssicherung|qualitaetspruefer\w*)\b',
})
BLUE_RULES.update({
    'site_security_recreation': r'\b(?:badeaufsicht\w*|rettungsschwimmer\w*|lifeguard\w*|sicherheitskraft\w*|kaufhausdetektiv\w*|installationstechniker\w*|platzfahrer\w*|teiledienstmitarbeiter\w*|regalservice\w*|frischespezialist\w*)\b',
    'additional_manual_compounds': r'\b\w*(?:schlosser|baecker|heizungsbauer|kaeltetechniker|fahrzeugaufbereiter|baugeraetefuehrer|tiefbaufacharbeiter)(?:in|innen|meister\w*)?\b|\b(?:kommissionierung|spielhallenaufsicht\w*|alltagsbegleiter\w*|betreuungskraft\w*|barmitarbeiter\w*|servicehelfer\w*|salonleitung|mitarbeiter(?: in)? (?:im lager|produktion|kueche|werkstatt)|fachkraft fuer nachtbereitschaft)\b',
})


def normalize_title(title):
    text = unicodedata.normalize('NFKC', html.unescape(str(title or ''))).casefold()
    text = text.replace('\u00ad', '').replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    text = re.sub(r'(?<=\w)[:*/_]innen\b', 'innen', text)
    text = re.sub(r'(?<=\w)[:*/_]in\b', 'in', text)
    return re.sub(r'[^\w]+', ' ', text).strip()


COMPILED = {category: [(name, re.compile(pattern)) for name, pattern in rules.items()]
            for category, rules in [('white', WHITE_RULES), ('blue', BLUE_RULES),
                                    ('ambiguous', AMBIGUOUS_RULES), ('policy', OWNER_BLUE_RULES)]}

DICTIONARY_PATH = Path(__file__).with_name('title_occupation_dictionary.json')
OCCUPATION_DICTIONARY = json.loads(DICTIONARY_PATH.read_text(encoding='utf-8')) if DICTIONARY_PATH.exists() else {}
OCCUPATION_TERMS = OCCUPATION_DICTIONARY.get('terms', {})
MAX_OCCUPATION_WORDS = max((len(t.split()) for t in OCCUPATION_TERMS), default=0)


def dictionary_matches(title):
    words = normalize_title(title).split()
    found = []
    for start in range(len(words)):
        for size in range(1, min(MAX_OCCUPATION_WORDS, len(words) - start) + 1):
            term = ' '.join(words[start:start + size])
            if term in OCCUPATION_TERMS:
                found.append({'rule': 'official_occupation_alias', 'term': term, 'title': title,
                              **OCCUPATION_TERMS[term]})
    # Longer occupation phrases provide more specific evidence than aliases
    # nested within them (e.g. a technician within an engineering title).
    return [m for m in found if not any(m['term'] != n['term'] and
            (' ' + m['term'] + ' ') in (' ' + n['term'] + ' ') for n in found)]


@lru_cache(maxsize=200000)
def _matches(title):
    text = normalize_title(title)
    result = {}
    for category, rules in COMPILED.items():
        result[category] = [{'rule': name, 'term': match.group(), 'title': title}
                            for name, pattern in rules for match in pattern.finditer(text)]
    return result


def classify_titles(titles):
    titles = list(dict.fromkeys(str(t).strip() for t in titles if t and str(t).strip()))
    matches = {category: [m for title in titles for m in _matches(title)[category]]
               for category in COMPILED}
    white, blue = bool(matches['white']), bool(matches['blue'])
    if matches['policy']:
        collar, reason = 'blue', 'owner_policy_' + matches['policy'][0]['rule']
    elif white and blue:
        collar, reason = 'blue', 'owner_policy_conflicting_occupation_terms'
    elif matches['ambiguous']:
        collar, reason = 'unresolved', 'ambiguous_occupation'
    elif white:
        collar, reason = 'white', 'explicit_white_occupation'
    elif blue:
        collar, reason = 'blue', 'explicit_blue_occupation'
    else:
        aliases = [m for title in titles for m in dictionary_matches(title)]
        categories = {m['collar'] for m in aliases}
        if len(categories) == 1 and 'unresolved' not in categories:
            collar, reason = next(iter(categories)), 'official_occupation_alias'
            matches[collar].extend(aliases)
        else:
            collar, reason = 'unresolved', ('conflicting_dictionary_aliases' if aliases else 'no_occupation_match') if titles else 'missing_title'
            matches['ambiguous'].extend(aliases)
    return {'collar': collar, 'reason': reason, 'white_matches': matches['white'],
            'blue_matches': matches['blue'], 'ambiguous_matches': matches['ambiguous'],
            'policy_matches': matches['policy']}


def unresolved_blocker(job):
    reason = job['reason']
    if reason == 'conflicting_dictionary_aliases':
        return 'conflicting_official_aliases', 'Official aliases map to different Runr categories or the same alias belongs to both categories; title-only evidence cannot choose.'
    if reason == 'missing_title':
        return 'missing_source_title', 'No recorded title is available.'
    if reason == 'ambiguous_occupation':
        return 'remaining_boundary_requires_policy', 'A remaining boundary rule needs an explicit white/blue policy; annotation 1 does not cover it.'
    text = normalize_title(job.get('title', ''))
    if re.search(r'\b(?:\w*praktik\w*|\w*student\w*|studierend\w*|schueler\w*|ausbildung\w*|abiprogramm|intern\w*|apprentice\w*|minijob\w*|freiwillig\w*|fsj|bfd|volunteer\w*)\b', text):
        return 'work_relationship_without_occupation', 'The title describes training, study, temporary work or volunteering without a matched occupation.'
    if re.search(r'\b(?:\w*leiter\w*|\w*leitung|manager\w*|supervisor\w*|specialist\w*|spezialist\w*|assistant\w*|assistenz\w*|engineer\w*|technician\w*|techniker\w*|fachkraft\w*)\b', text):
        return 'generic_or_unmapped_role', 'A role label is present, but its occupational field has no decisive retained rule.'
    return 'occupation_not_in_dictionary', 'The recorded title does not match the current German/English occupation dictionary; an explicit term rule is missing.'


def url_key(url):
    try:
        parts = urlsplit(str(url or '').strip())
        if not parts.hostname or parts.scheme not in ('http', 'https'):
            return ''
        # Preserve query arguments: ATS vacancy identity often lives there.
        return urlunsplit(('https', parts.netloc.casefold(), parts.path.rstrip('/'), parts.query, ''))
    except ValueError:
        return ''


def deduplicate(rows):
    """Merge only same-employer exact canonical IDs, URLs or LinkedIn IDs.

    Title/location similarity is never identity evidence. Unknown employers are
    partitioned by source organization ID, never guessed from company names.
    """
    parents, groups, keys = [], [], {}

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for row in rows:
        i = len(parents)
        parents.append(i)
        groups.append(row)
        company = row.get('company_id') or ('linkedin:' + str(row['linkedin_company_id'])
                  if row.get('linkedin_company_id') else 'unknown:' + row['source'] + ':' + row['id'])
        tokens = [('record', row['source'], row['id'])]
        if row.get('canonical_job_id'):
            tokens.append(('canonical', company, row['canonical_job_id']))
        for url in [row.get('url', ''), *row.get('aliases', [])]:
            normalized = url_key(url)
            if normalized:
                tokens.append(('url', company, normalized))
                match = re.search(r'linkedin\.com/jobs/view/(?:[^/?]*-)?(\d+)', normalized)
                if match:
                    tokens.append(('linkedin_id', company, match.group(1)))
        if row.get('linkedin_job_id'):
            tokens.append(('linkedin_id', company, str(row['linkedin_job_id'])))
        for token in tokens:
            if token in keys:
                parents[root(i)] = root(keys[token])
            else:
                keys[token] = i
    merged = defaultdict(list)
    for i, row in enumerate(groups):
        merged[root(i)].append(row)
    result = []
    for records in merged.values():
        records.sort(key=lambda r: (r['source'] != 'catalog', r['id']))
        main = records[0]
        titles = list(dict.fromkeys(t for r in records for t in
                     [r.get('title', ''), *r.get('other_titles', [])] if t))
        sources = sorted({r['source'] for r in records})
        lifecycle = main.get('lifecycle', 'unknown').casefold()
        # Canonical lifecycle wins over historical producer evidence.
        if main['source'] != 'catalog':
            states = {r.get('lifecycle', 'unknown').casefold() for r in records}
            lifecycle = 'active' if states == {'active'} else ('inactive' if states == {'inactive'} else 'unknown')
        result.append({**main, 'records': records, 'titles': titles, 'sources': sources,
                       'published': any(r.get('published') for r in records), 'lifecycle': lifecycle,
                       **classify_titles(titles)})
    return result


def employer_summary(jobs):
    employers = {}
    for job in jobs:
        company_id = job.get('company_id')
        if not company_id:
            continue
        record = employers.setdefault(company_id, {'company_id': company_id,
            'company': job.get('company', ''), 'white': 0, 'blue': 0, 'unresolved': 0,
            'inactive_or_unknown': 0, 'published': 0, 'placeholder_exclusions': 0})
        record['published'] += bool(job.get('published'))
        if job.get('reason') == 'owner_policy_placeholder':
            record['placeholder_exclusions'] += 1
            continue
        if job.get('lifecycle') == 'active':
            record[job['collar']] += 1
        else:
            record['inactive_or_unknown'] += 1
    for record in employers.values():
        total = record['white'] + record['blue'] + record['unresolved']
        classified = record['white'] + record['blue']
        record['active_jobs'] = total
        record['classified_fraction'] = round(classified / total, 4) if total else 0
        record['blue_fraction_classified'] = round(record['blue'] / classified, 4) if classified else 0
        record['blue_fraction_all_active'] = round(record['blue'] / total, 4) if total else 0
        record['recommendation'] = ('review_for_deprioritization' if total >= 20
            and record['classified_fraction'] >= .9 and record['blue_fraction_all_active'] >= .95
            else 'retain_mixed_employer' if record['white'] else 'insufficient_evidence')
    return sorted(employers.values(), key=lambda r: (-r['blue_fraction_all_active'], -r['active_jobs'], r['company_id']))


def read_jsonl(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items() if k in fields})


def run_audit(inputs, output):
    output.mkdir(parents=True, exist_ok=True)
    rows, metadata, companies, mappings, aliases, external_ids, coverage, manifest = [], [], {}, {}, defaultdict(list), {}, {}, None
    for path in inputs:
        for item in read_jsonl(path):
            kind = item.pop('kind')
            if kind == 'job': rows.append(item)
            elif kind == 'company': companies[item['company_id']] = item['company']
            elif kind == 'identity': mappings[item['source_identity_key']] = item['winner_company_id']
            elif kind == 'url_alias': aliases[item['canonical_job_id']].append(item['url'])
            elif kind == 'external_id':
                external_ids[(item['source_id'], str(item['external_job_id']))] = item['canonical_job_id']
            elif kind == 'coverage': coverage[item['company_id']] = item
            elif kind == 'manifest': manifest = item
            else: metadata.append({'kind': kind, **item})
        print(json.dumps({'phase': 'input_loaded', 'file': path.name, 'job_records': len(rows)}), flush=True)
    catalog = {r['canonical_job_id']: r for r in rows if r['source'] == 'catalog'}
    for row in rows:
        original = str(row.get('company_id', ''))
        if original in ('//', 'null', 'None', 'nan'):
            original = ''
        row['original_company_id'] = original
        row['company_id'] = mappings.get('old-company:' + original, mappings.get('canonical:' + original, mappings.get(original, original)))
        if row['source'].startswith('linkedin'):
            external_id = str(row.get('linkedin_job_id', ''))
            mapped = external_ids.get(('producer_linkedin_' + row['company_id'], external_id))
            if not mapped:
                mapped = external_ids.get(('linkedin', external_id))
            if mapped and mapped in catalog and row['company_id'] == catalog[mapped]['company_id']:
                row['canonical_job_id'] = mapped
        if row.get('canonical_job_id') in catalog:
            row['aliases'] = aliases[row['canonical_job_id']]
        row['company'] = companies.get(row['company_id'], row.get('company', ''))
    jobs = deduplicate(rows)
    print(json.dumps({'phase': 'classified_and_deduplicated', 'unique_jobs': len(jobs)}), flush=True)
    employers = employer_summary(jobs)
    for employer in employers:
        evidence = coverage.get(employer['company_id'], {})
        employer['scan_classification'] = evidence.get('classification', 'unknown')
        employer['scan_outcome'] = evidence.get('outcome', '')
        employer['browser_deferred'] = evidence.get('browser_deferred', False)
        employer['scan_updated_at'] = evidence.get('updated_at', '')
        if employer['recommendation'] == 'review_for_deprioritization' and employer['scan_classification'] != 'confirmed_complete':
            employer['recommendation'] = 'review_blue_heavy_incomplete_coverage'
    scope_counts = {scope: dict(Counter(j['collar'] for j in jobs if predicate(j))) for scope, predicate in {
        'all_unique_jobs': lambda j: True,
        'published': lambda j: j['published'],
        'not_in_publication': lambda j: not j['published'],
        'active_not_in_publication': lambda j: not j['published'] and j['lifecycle'] == 'active',
        'inactive_or_unknown': lambda j: j['lifecycle'] != 'active',
    }.items()}
    source_counts = {source: dict(Counter(classify_titles([r.get('title'), *r.get('other_titles', [])])['collar']
                      for r in rows if r['source'] == source)) for source in sorted({r['source'] for r in rows})}
    coverage_rows = []
    if manifest:
        for task in manifest['employer_tasks']:
            company_id = task['company_id']
            evidence = coverage.get(company_id, {})
            coverage_rows.append({**task, 'company': companies.get(company_id, task.get('company', '')),
                'attempted': company_id in coverage, 'classification': evidence.get('classification', 'untouched'),
                'outcome': evidence.get('outcome', ''), 'browser_deferred': evidence.get('browser_deferred', False),
                'updated_at': evidence.get('updated_at', '')})
    fields = ['source','id','canonical_job_id','company_id','company','title','titles','url','location',
              'published','lifecycle','sources','collar','reason','white_matches','blue_matches','ambiguous_matches','policy_matches','version_id','content_hash']
    write_csv(output / 'jobs.csv', jobs, fields)
    write_csv(output / 'blue_jobs.csv', (j for j in jobs if j['collar'] == 'blue'), fields)
    write_csv(output / 'unresolved_jobs.csv', (j for j in jobs if j['collar'] == 'unresolved'), fields)
    write_csv(output / 'published_blue_jobs.csv', (j for j in jobs if j['published'] and j['collar'] == 'blue'), fields)
    write_csv(output / 'employers.csv', employers, list(employers[0]) if employers else ['company_id'])
    candidates = [e for e in employers if e['recommendation'].startswith('review_')]
    write_csv(output / 'employer_review_candidates.csv', candidates, list(employers[0]) if employers else ['company_id'])
    write_csv(output / 'employer_coverage.csv', coverage_rows, ['company_id','company','website','attempted','classification','outcome','browser_deferred','updated_at'])
    unresolved_titles = Counter(t for j in jobs if j['collar'] == 'unresolved' for t in j['titles'])
    write_csv(output / 'unresolved_title_frequency.csv', [{'title': t, 'jobs': n} for t,n in unresolved_titles.most_common()], ['title','jobs'])
    unresolved_groups = Counter()
    unresolved_blockers = Counter()
    for job in jobs:
        if job['collar'] == 'unresolved':
            blocker, explanation = unresolved_blocker(job)
            unresolved_blockers[blocker] += 1
            unresolved_groups[(job.get('title',''), job['reason'], blocker, explanation)] += 1
    blocker_rows = [{'title': title, 'jobs': n, 'reason': reason, 'blocker': blocker, 'explanation': explanation}
                    for (title, reason, blocker, explanation), n in unresolved_groups.most_common()]
    write_csv(output / 'unresolved_title_blockers.csv', blocker_rows,
              ['title','jobs','reason','blocker','explanation'])
    disagreements = [j for j in jobs if j.get('existing_collar') in ('white','blue') and j['collar'] in ('white','blue') and j['existing_collar'] != j['collar']]
    write_csv(output / 'existing_classification_disagreements.csv', disagreements, fields + ['existing_collar'])
    rules = {'version': RULE_VERSION, 'white': WHITE_RULES, 'blue': BLUE_RULES,
             'ambiguous': AMBIGUOUS_RULES, 'owner_policy': OWNER_POLICY,
             'occupation_dictionary': OCCUPATION_DICTIONARY}
    encoded_rules = json.dumps(rules, ensure_ascii=False, sort_keys=True, indent=2)
    (output / 'rules.json').write_text(encoded_rules, encoding='utf-8', newline='\n')
    summary = {'rule_version': RULE_VERSION, 'rules_sha256': hashlib.sha256(encoded_rules.encode()).hexdigest(),
        'generated_at': datetime.now(timezone.utc).isoformat(), 'input_records': len(rows), 'unique_jobs': len(jobs),
        'merged_duplicate_records': len(rows)-len(jobs), 'scopes': scope_counts, 'sources': source_counts,
        'reasons': dict(Counter(j['reason'] for j in jobs)), 'employers_with_job_evidence': len(employers),
        'unresolved_blockers': dict(unresolved_blockers),
        'owner_policy': OWNER_POLICY,
        'owner_policy_counts': dict(Counter(j['reason'] for j in jobs if j['reason'].startswith('owner_policy_'))),
        'employer_recommendations': dict(Counter(e['recommendation'] for e in employers)),
        'employer_placeholder_exclusions': sum(e['placeholder_exclusions'] for e in employers),
        'employer_coverage': dict(Counter(r['classification'] for r in coverage_rows)),
        'eligible_employer_tasks': len(coverage_rows), 'untouched_employers': sum(not r['attempted'] for r in coverage_rows),
        'employers_browser_deferred': sum(r['browser_deferred'] for r in coverage_rows),
        'existing_classification_disagreements': len(disagreements), 'manifest_counts': manifest.get('counts', {}) if manifest else {},
        'snapshot_metadata': metadata,
        'input_files': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],
        'production_changes': False, 'ai_calls': 0}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# German/English title-only collar audit', '',
        'Deterministic occupation rules; **zero AI calls and no production changes**. Each input record was evaluated. '
        'Annotation 1 marks Aushilfe, service technicians, placeholder headings and white/blue conflicts blue by owner policy. '
        'Other unmatched or ambiguous titles remain unresolved. Only recorded titles are used; no translations are generated.', '',
        '| Scope | White | Blue | Unresolved | Total |','|---|---:|---:|---:|---:|']
    for scope, counts in scope_counts.items():
        lines.append(f"| {scope} | {counts.get('white',0):,} | {counts.get('blue',0):,} | {counts.get('unresolved',0):,} | {sum(counts.values()):,} |")
    lines += ['',f"Input job records: {len(rows):,}; exact-identity merged duplicate records: {len(rows)-len(jobs):,}.",
        '', '## Employer coverage', '', f"Eligible employer tasks in the pinned manifest: {len(coverage_rows):,}; without a recorded employer checkpoint: {summary['untouched_employers']:,}.",
        '', '| Classification | Employers |', '|---|---:|']
    lines += [f'| {key} | {count:,} |' for key, count in sorted(summary['employer_coverage'].items())]
    lines += ['', f"Browser fallback explicitly deferred in latest checkpoints: {summary['employers_browser_deferred']:,}. This is not a count of all hard sites.",
        '', '## Employer job mix', '',
        'Employer percentages use explicitly active unique jobs with occupational title evidence only. Placeholder headings are excluded from employer occupation percentages and counted separately. Inactive or unknown-lifecycle records are reported separately. '
        'Candidates require at least 20 active jobs, at least 90% classified and at least 95% blue among all active jobs. '
        'These are review thresholds, not automatic exclusion rules; incomplete scans cannot establish a complete employer mix.', '',
        '| Employer | Active white | Active blue | Unresolved | Placeholder exclusions | Scan | Recommendation |','|---|---:|---:|---:|---:|---|---|']
    lines += [f"| {e['company'].replace('|','/')} | {e['white']} | {e['blue']} | {e['unresolved']} | {e['placeholder_exclusions']} | {e['scan_classification']} | {e['recommendation']} |" for e in candidates[:30]]
    lines += ['', '## Policy and limitations', '',
        f"- The review list contains {len(candidates)} employer identities and {len({e['company'] for e in candidates})} distinct display names. Repeated names under different canonical IDs are retained; employer identity must be resolved before any whole-company removal.",
        '- Professional healthcare, education, retail sales and administrative work follow the existing Runr inclusion policy. Manual trades, driving, picking, cleaning, cooking and table service are blue.',
        '- Bare manager, engineer, technician, specialist, assistant, apprentice and working-student labels do not establish an occupation. Explicit operational supervision and service-engineering boundaries remain unresolved.',
        '- Annotation 1 explicitly resolves white/blue conflicts to blue and overrides Aushilfe, service technicians and placeholder headings to blue. Original occupational matches remain available; placeholder exclusions do not establish a manual occupation.',
        '- Deduplication uses recorded canonical IDs, same-employer exact posting URL aliases and LinkedIn IDs. Different URLs with similar titles remain separate; unlinked cross-source duplicates may remain.',
        '- Current canonical lifecycle takes precedence over producer history. Producer-only active state is source-reported, not proof the vacancy is still open. Unknown employer identity is not guessed from its name.',
        '- Published means membership in the pinned publication, before existing customer visibility filters. Not-in-publication includes historical, rejected, closed and pending records; it is not exclusively a pending queue.',
        '- Databases remain running. Producer SQLite snapshots are pinned per database. Turso is captured in bounded pages over a read window, with publication IDs and source timestamps recorded in summary.json.',
        '- Existing AI-derived classifications are exported only for comparison and never used to decide the title-only result.',
        '- No employer was removed, no job deleted or hidden, no timer changed, and no scraper/model provider called by this audit.', '',
        '## Artifacts', '',
        '`jobs.csv`, `blue_jobs.csv`, `published_blue_jobs.csv`, `unresolved_jobs.csv`, '
        '`unresolved_title_frequency.csv`, `employers.csv`, `employer_review_candidates.csv`, '
        '`unresolved_title_blockers.csv`, `employer_coverage.csv`, `existing_classification_disagreements.csv`, `rules.json`, `summary.json`.', '',
        f'Rule version: `{RULE_VERSION}`. Rules SHA-256: `{summary["rules_sha256"]}`.']
    lines += ['', '## Remaining unresolved blockers', '',
              '| Blocker | Unique jobs |', '|---|---:|']
    lines += [f'| {blocker} | {n:,} |' for blocker, n in unresolved_blockers.most_common()]
    lines += ['', '| Recorded title | Unique jobs | Blocker |', '|---|---:|---|']
    lines += [f"| {r['title'].replace('|','/')} | {r['jobs']:,} | {r['blocker']} |" for r in blocker_rows[:30]]
    (output / 'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('snapshot_metadata','input_files')}, ensure_ascii=False), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run_audit(args.input, args.output)

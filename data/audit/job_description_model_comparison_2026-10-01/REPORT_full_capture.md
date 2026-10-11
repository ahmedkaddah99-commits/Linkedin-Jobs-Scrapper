# Runr job description model comparison: complete source and output record

Date: 2026-10-01. This report records the four published posting versions used in the English-only model comparison. It contains the full preserved description available to the test, the offline English translation, the exact rendered prompt, and the complete model text from a capture replay. No generated description was published to Runr.

## How to read this record

- **Original run**: the first English-only comparison, summarized in [`initial_run_results.json`](initial_run_results.json). That run saved parsed items and checks but not full raw responses.
- **Capture replay**: the twenty subsequent calls using the same prompt and request settings, with full response text and token usage saved in [`responses/`](responses/). Model output may differ between calls despite `temperature: 0`. The verbatim outputs below are from this capture replay.
- German postings were translated locally with Argos Translate 1.11.0 and the German→English package version 1.3. English postings were passed through unchanged. Passage IDs map translated text back to the original source passage. Translation was not charged by an API.
- `response_format` was `json_object`, `provider.require_parameters` was `true`, `temperature` was `0`, and `max_tokens` was `5500`. GPT-OSS used `reasoning.effort: low`; Ling used `reasoning.effort: none`.
- This is a four-posting sample. These outputs are evidence for comparison, not a catalog-wide accuracy guarantee.

## Posting index

| Label | Title | Version | Source |
|---|---|---|---|
| `german_typical` | Karosserie- und Fahrzeugbaumechaniker (m/w/d) | `posting_version_14e4a7d95f3041e1ae57985c0ecfe126` | [posting](https://linkedin.com/jobs/view/4403743865) |
| `english_typical` | IT Governance Manager (m/f/d) | `posting_version_80b0cec022bb46a29e8687d926cae279` | [posting](https://linkedin.com/jobs/view/4458080709) |
| `german` | Head of Controlling / FP&A (m/w/d) | `posting_version_79adb669147643e8b899839519645404` | [posting](https://linkedin.com/jobs/view/4453643322) |
| `preferred` | Marketing COE Lead | `posting_version_b737755a330344bf899ef021439087e4` | [posting](https://jobs.eastman.com/job/Kingsport-Marketing-COE-Lead-TN-37660/1377487500) |

## Exact prompt

The text under **Exact rendered prompt** in each posting section is the complete user message sent to every model for that posting. The corresponding plain-text files in [`prompts/`](prompts/) hold the same bytes. The posting title and original-language source were **not** included in the model message; the model received only the translated or unchanged English passages.

## Original-run and replay outcome overview

| Posting | Model | Initial structural check | Replay finish | Replay cost (USD) | Replay response |
|---|---|---|---|---:|---|
| `german_typical` | `mistralai/mistral-nemo` | pass | `stop` | 0.00003442 | JSON parsed |
| `german_typical` | `openai/gpt-oss-20b` | fail | `stop` | 0.00006512 | JSON parsed |
| `german_typical` | `inclusionai/ling-3.0-flash-vl-20260910` | pass | `stop` | 0.00014575 | JSON parsed |
| `german_typical` | `openai/gpt-oss-120b` | pass | `stop` | 0.00007333 | JSON parsed |
| `german_typical` | `google/gemini-2.5-flash-lite` | pass | `stop` | 0.00033540 | JSON parsed |
| `english_typical` | `mistralai/mistral-nemo` | pass | `stop` | 0.00005881 | JSON parsed |
| `english_typical` | `openai/gpt-oss-20b` | pass | `stop` | 0.00010051 | JSON parsed |
| `english_typical` | `inclusionai/ling-3.0-flash-vl-20260910` | pass | `stop` | 0.00025087 | JSON parsed |
| `english_typical` | `openai/gpt-oss-120b` | fail | `stop` | 0.00024321 | JSON parsed |
| `english_typical` | `google/gemini-2.5-flash-lite` | pass | `stop` | 0.00052050 | JSON parsed |
| `german` | `mistralai/mistral-nemo` | fail | `stop` | 0.00010290 | JSON parsed |
| `german` | `openai/gpt-oss-20b` | fail | `length` | 0.00084473 | raw text, invalid JSON |
| `german` | `inclusionai/ling-3.0-flash-vl-20260910` | fail | `stop` | 0.00039972 | JSON parsed |
| `german` | `openai/gpt-oss-120b` | pass | `stop` | 0.00038761 | JSON parsed |
| `german` | `google/gemini-2.5-flash-lite` | fail: JSONDecodeError: Unterminated string starting at: line 1 col | `stop` | 0.00078470 | JSON parsed |
| `preferred` | `mistralai/mistral-nemo` | fail | `stop` | 0.00016735 | JSON parsed |
| `preferred` | `openai/gpt-oss-20b` | fail | `stop` | 0.00013790 | JSON parsed |
| `preferred` | `inclusionai/ling-3.0-flash-vl-20260910` | fail | `stop` | 0.00055272 | JSON parsed |
| `preferred` | `openai/gpt-oss-120b` | fail | `stop` | 0.00123960 | JSON parsed |
| `preferred` | `google/gemini-2.5-flash-lite` | fail | `stop` | 0.00113270 | JSON parsed |

## german_typical: Karosserie- und Fahrzeugbaumechaniker (m/w/d)

- Canonical job ID: `canonical_job_0002249a82eb4ea0b03cb779bef5f410`
- Posting version: `posting_version_14e4a7d95f3041e1ae57985c0ecfe126`
- Source URL: https://linkedin.com/jobs/view/4403743865
- Translation runtime on the local Windows machine: 16.02 seconds

### Original preserved job posting

[Download original text](german_typical__original.txt)

``````text
Die IRS Group 🚗 Werde Teil der IRS Group – Deutschlands Experten für Karosserie & Lack! Mit über 60 Standorten bundesweit und rund 1.800 Kolleg:innen sorgen wir täglich für glänzende Ergebnisse in der Unfallinstandsetzung, Autolackierung & Fahrzeugaufbereitung. Der Standort ist ein Vorreiter in Sachen Qualität. Der moderne und professionelle Betrieb ist sowohl Partnerwerkstatt von Versicherungen und Schadensteuerern als auch Partner seiner privaten Kunden. Seit über 80 Jahren werden hier Service, Qualität, Freundlichkeit und pünktliche Lieferung großgeschrieben. 💪Aufgrund unseres weiteren stabilen Wachstums suchen wir Dich als Karosserie- und Fahrzeugbaumechaniker (m/w/d) bei IRS Meyer in Ronnenberg bei Hannover. Was wir Dir bieten 🌟 Ein starkes Team & familiäres Betriebsklima Umfassende Einarbeitung & langfristige Arbeitsplatzsicherheit Entwicklungsmöglichkeiten in einem starken Handwerkskonzern Hochmoderne Arbeitsmittel & hochwertige Arbeitskleidung Faires Gehalt 1.000 € Empfehlungsbonus für neue Kolleg:innen durch Dich Corporate Benefits – bis zu 50 % Rabatt bei über 1.500 Marken Deine Aufgaben 💼 Hier kannst Du in allen Bereichen Deiner Kunst zeigen, was in Dir steckt: Feststellen und Einschätzen von Beschädigungen und Mängeln an Karosserien sowie Anbauteilen Beurteilung des Schadens und Anwendung des geeigneten Reparaturverfahrens Ausbeultechniken, Schweißungen, Richtbankarbeit und passgenaues Fügen bilden den Kern der Arbeit Du traust Dir auch Aluminium- und Kunststoffinstandsetzungen zu Die Montage und Demontage von Anbauteilen, Reifen und Scheiben sowie die elektronische Fahrzeugvermessung runden Dein Tätigkeitsfeld ab Dein Profil ⭐ Du bringst Leidenschaft, Herzblut und Freude am Handwerk bei der Behebung von Schäden an Fahrzeugen mit. Darüber hinaus wünschen wir uns: Eine abgeschlossene Ausbildung als Karosserie- und Fahrzeugbaumechaniker (m/w/d) oder als Kfz-Mechaniker/ Mechatroniker (m/w/d) mit Berufserfahrung im Bereich "Karosseriebau/ Unfallinstandsetzung" Du besitzt den Führerschein Klasse B (3) und gute Deutschkenntnisse Du arbeitest gewissenhaft, zuverlässig und handelst dabei immer serviceorientiert Bewirb Dich jetzt 🚀 Interessiert? Dann freuen wir uns auf Deine Bewerbung! 📧 Einfach über den Button "Online bewerben" 📱 oder in nur 2 Minuten per WhatsApp. 👉 Werde Teil unseres Teams – wir freuen uns auf Dich! IRS Schadenszentrum IRS Meyer In der Beschen 4 30952 Ronnenberg Dein Kontakt vor Ort: Stephan Salzer Telefon +49 151 1199 1710
``````

### English text supplied to models

[Download English passages](german_typical__english.txt)

``````text
[p1] The IRS Group 🚗 Become part of the IRS Group – Germany’s experts in body & paint!

[p2] With more than 60 locations nationwide and around 1,800 colleagues, we ensure brilliant results in the repair of accidents, car painting and vehicle processing every day.

[p3] The location is a pioneer in terms of quality.

[p4] The modern and professional company is both a partner workshop of insurance companies and property controllers as well as a partner of its private customers.

[p5] For more than 80 years, service, quality, friendliness and punctual delivery have been a priority here.

[p6] Due to our continued stable growth, we are looking for you as body and vehicle construction mechanic (m/f/d) at IRS Meyer in Ronnenberg near Hanover.

[p7] What we offer you adresse A strong team & family working atmosphere Comprehensive training & long-term job security Development opportunities in a strong crafts group High-modern work equipment & high-quality workwear Fair salary 1,000 € recommendation bonus for new colleagues: women through you Corporate Benefits – up to 50% discount on over 1,500 brands Your tasks 💼 Here you can show what is inside you in all areas of your art: Determination and assessment of damages and defects on bodies as well as add-on parts Assessment of the damage and application of the appropriate repair process buckling techniques, welds, bench work and fitting form the core of the work You trust The assembly and disassembly of add-on parts, tires and panes as well as the electronic vehicle measurement round off your field of activity your profile ⭐ You bring passion, passion and pleasure in the craft when repairing damage to vehicles.

[p8] In addition, we would like to: Complete training as body and vehicle construction mechanic (m/f/d) or as automotive mechanic/mechatronics technician (m/f/d) with professional experience in the field of "bodywork / accident repair" You have the driving license class B (3) and good knowledge of German You work conscientiously, reliably and always act service-oriented Apply now 🚀 Interested?

[p9] We look forward to your application!

[p10] 📧 Simply use the "Apply online" button or in just 2 minutes via WhatsApp.

[p11] 👉 Become part of our team – we look forward to seeing you!

[p12] IRS claims center IRS Meyer In the Beschen 4 30952 Ronnenberg your contact on site: Stephan Salzer telephone +49 151 1199 1710
``````

### Exact rendered prompt

[Download exact prompt](prompts/german_typical.txt)

``````text
Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "The IRS Group 🚗 Become part of the IRS Group – Germany’s experts in body & paint!"}, {"id": "p2", "text": "With more than 60 locations nationwide and around 1,800 colleagues, we ensure brilliant results in the repair of accidents, car painting and vehicle processing every day."}, {"id": "p3", "text": "The location is a pioneer in terms of quality."}, {"id": "p4", "text": "The modern and professional company is both a partner workshop of insurance companies and property controllers as well as a partner of its private customers."}, {"id": "p5", "text": "For more than 80 years, service, quality, friendliness and punctual delivery have been a priority here."}, {"id": "p6", "text": "Due to our continued stable growth, we are looking for you as body and vehicle construction mechanic (m/f/d) at IRS Meyer in Ronnenberg near Hanover."}, {"id": "p7", "text": "What we offer you adresse A strong team & family working atmosphere Comprehensive training & long-term job security Development opportunities in a strong crafts group High-modern work equipment & high-quality workwear Fair salary 1,000 € recommendation bonus for new colleagues: women through you Corporate Benefits – up to 50% discount on over 1,500 brands Your tasks 💼 Here you can show what is inside you in all areas of your art: Determination and assessment of damages and defects on bodies as well as add-on parts Assessment of the damage and application of the appropriate repair process buckling techniques, welds, bench work and fitting form the core of the work You trust The assembly and disassembly of add-on parts, tires and panes as well as the electronic vehicle measurement round off your field of activity your profile ⭐ You bring passion, passion and pleasure in the craft when repairing damage to vehicles."}, {"id": "p8", "text": "In addition, we would like to: Complete training as body and vehicle construction mechanic (m/f/d) or as automotive mechanic/mechatronics technician (m/f/d) with professional experience in the field of \"bodywork / accident repair\" You have the driving license class B (3) and good knowledge of German You work conscientiously, reliably and always act service-oriented Apply now 🚀 Interested?"}, {"id": "p9", "text": "We look forward to your application!"}, {"id": "p10", "text": "📧 Simply use the \"Apply online\" button or in just 2 minutes via WhatsApp."}, {"id": "p11", "text": "👉 Become part of our team – we look forward to seeing you!"}, {"id": "p12", "text": "IRS claims center IRS Meyer In the Beschen 4 30952 Ronnenberg your contact on site: Stephan Salzer telephone +49 151 1199 1710"}]}
``````

### Model output: `mistralai/mistral-nemo`

- [Full response record](responses/german_typical__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 36.83 seconds; input tokens: 942; output tokens: 582; billed cost: $3.4416e-05.

``````text
{
  "overview": "Join IRS Group as a Body and Vehicle Construction Mechanic in Ronnenberg near Hanover.",
  "items": [
    {
      "passage_id": "p7",
      "section": "responsibilities",
      "text": "Assess damages and defects on vehicle bodies and add-on parts. Apply appropriate repair processes, including buckling techniques, welds, bench work, and fitting. Assemble and disassemble add-on parts, tires, and panes. Perform electronic vehicle measurements."
    },
    {
      "passage_id": "p7",
      "section": "required_qualifications",
      "text": "Passion and pleasure in vehicle repair craft."
    },
    {
      "passage_id": "p8",
      "section": "required_qualifications",
      "text": "Completed training as a Body and Vehicle Construction Mechanic or Automotive Mechanic/Mechatronics Technician."
    },
    {
      "passage_id": "p8",
      "section": "required_qualifications",
      "text": "Professional experience in 'bodywork / accident repair'."
    },
    {
      "passage_id": "p8",
      "section": "required_qualifications",
      "text": "Driving license class B (3)."
    },
    {
      "passage_id": "p8",
      "section": "required_qualifications",
      "text": "Good knowledge of German."
    },
    {
      "passage_id": "p8",
      "section": "required_qualifications",
      "text": "Conscientious, reliable, and service-oriented work."
    },
    {
      "passage_id": "p7",
      "section": "preferred_qualifications",
      "text": "Experience in the field of vehicle construction."
    },
    {
      "passage_id": "p7",
      "section": "benefits",
      "text": "Strong team and family working atmosphere. Comprehensive training and long-term job security. Development opportunities in a strong crafts group. High-modern work equipment and high-quality workwear. Fair salary. 1,000 € recommendation bonus for new colleagues: women through you. Corporate Benefits – up to 50% discount on over 1,500 brands."
    },
    {
      "passage_id": "p10",
      "section": "application_details",
      "text": "Apply online or via WhatsApp in just 2 minutes."
    }
  ],
  "ignored_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p9", "p11", "p12"]
}
``````

### Model output: `openai/gpt-oss-20b`

- [Full response record](responses/german_typical__openai_gpt-oss-20b.json)
- Finish reason: `stop`; elapsed: 9.98 seconds; input tokens: 1008; output tokens: 522; billed cost: $6.5124e-05.

``````text
{"overview":"Body and vehicle construction mechanic needed at IRS Meyer in Ronnenberg.","items":[{"passage_id":"p7","section":"responsibilities","text":"Assess damages, perform repair processes, assemble/disassemble add‑on parts, and conduct electronic vehicle measurements."},{"passage_id":"p8","section":"required_qualifications","text":"Complete training as body and vehicle construction mechanic or automotive mechanic/mechatronics technician with professional experience in bodywork/accident repair."},{"passage_id":"p8","section":"required_qualifications","text":"Driving licence class B (3) and good knowledge of German."},{"passage_id":"p7","section":"benefits","text":"Strong team atmosphere, comprehensive training, long‑term job security, development opportunities, high‑modern equipment, fair salary, 1,000 € recommendation bonus for new female colleagues, up to 50% discount on 1,500+ brands."},{"passage_id":"p10","section":"application_details","text":"Apply online or via WhatsApp in just 2 minutes."}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p9","p11","p12"]}
``````

### Model output: `inclusionai/ling-3.0-flash-vl-20260910`

- [Full response record](responses/german_typical__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 8.52 seconds; input tokens: 939; output tokens: 565; billed cost: $0.000145752.

``````text
{"overview":"IRS Group is hiring a body and vehicle construction mechanic at IRS Meyer in Ronnenberg near Hanover.","items":[{"passage_id":"p6","section":"responsibilities","text":"IRS Meyer in Ronnenberg near Hanover is hiring a body and vehicle construction mechanic (m/f/d)."},{"passage_id":"p7","section":"responsibilities","text":"Determine and assess damages and defects on bodies and add-on parts."},{"passage_id":"p7","section":"responsibilities","text":"Assess damage and apply the appropriate repair process; buckling techniques, welds, bench work and fitting form the core of the work."},{"passage_id":"p7","section":"responsibilities","text":"Assemble and disassemble add-on parts, tires and panes."},{"passage_id":"p7","section":"responsibilities","text":"Perform electronic vehicle measurement."},{"passage_id":"p7","section":"benefits","text":"Strong team and family working atmosphere."},{"passage_id":"p7","section":"benefits","text":"Comprehensive training and long-term job security."},{"passage_id":"p7","section":"benefits","text":"Development opportunities in a strong crafts group."},{"passage_id":"p7","section":"benefits","text":"High-modern work equipment and high-quality workwear."},{"passage_id":"p7","section":"benefits","text":"Fair salary."},{"passage_id":"p7","section":"benefits","text":"1,000 € recommendation bonus for new colleagues introduced by women."},{"passage_id":"p7","section":"benefits","text":"Corporate Benefits with up to 50% discount on over 1,500 brands."},{"passage_id":"p8","section":"preferred_qualifications","text":"Complete training as body and vehicle construction mechanic (m/f/d) or as automotive mechanic/mechatronics technician (m/f/d) with professional experience in bodywork/accident repair."},{"passage_id":"p8","section":"required_qualifications","text":"Driving license class B (3)."},{"passage_id":"p8","section":"required_qualifications","text":"Good knowledge of German."},{"passage_id":"p8","section":"preferred_qualifications","text":"Work conscientiously, reliably and always act service-oriented."},{"passage_id":"p10","section":"application_details","text":"Apply online or via WhatsApp in just 2 minutes."}],"ignored_ids":["p1","p2","p3","p4","p5","p9","p11","p12"]}
``````

### Model output: `openai/gpt-oss-120b`

- [Full response record](responses/german_typical__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 8.7 seconds; input tokens: 954; output tokens: 263; billed cost: $7.333e-05.

``````text
{
  "overview": "Body and vehicle construction mechanic position at IRS Meyer in Ronnenberg.",
  "items": [
    {
      "passage_id": "p6",
      "section": "responsibilities",
      "text": "Perform body and vehicle construction tasks at IRS Meyer."
    },
    {
      "passage_id": "p7",
      "section": "responsibilities",
      "text": "Assess damage and determine appropriate repair processes."
    },
    {
      "passage_id": "p7",
      "section": "responsibilities",
      "text": "Execute buckling, welding, bench work, and fitting."
    },
    {
      "passur... (truncated) ..."
    
  



 





 





  
  

  
  

  
  

  
 





  

  
 

  
 

  
 

  
 

  

  
 

  
 

  
 

  
 

  

  
 

  
 
  
 
 

  
 

 

  
 

  
 

  
 

  
 

  
 

  
 

  
 

  
 
 

  
 

  
 
 

  
 

  
 

  
 

  
 

  
 
 

  
 

  
 

  
 
 
 

  
 

  
 
 
  

 
 

  
 

  
 
 


  : 

[{
} 
] }
]}
``````

### Model output: `google/gemini-2.5-flash-lite`

- [Full response record](responses/german_typical__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 2.33 seconds; input tokens: 910; output tokens: 611; billed cost: $0.0003354.

``````text
{"overview":"The IRS Group is seeking a skilled Body and Vehicle Construction Mechanic (m/f/d) for their IRS Meyer location in Ronnenberg near Hanover, offering a strong team environment, comprehensive training, and development opportunities.","items":[{"passage_id":"p7","section":"responsibilities","text":"Determine and assess damages and defects on bodies and add-on parts."},{"passage_id":"p7","section":"responsibilities","text":"Assess damage and apply appropriate repair processes, including buckling techniques, welding, bench work, and fitting."},{"passage_id":"p7","section":"responsibilities","text":"Assemble and disassemble add-on parts, tires, and panes."},{"passage_id":"p7","section":"responsibilities","text":"Perform electronic vehicle measurements."},{"passage_id":"p8","section":"required_qualifications","text":"Completed training as a body and vehicle construction mechanic (m/f/d) or as an automotive mechanic/mechatronics technician (m/f/d) with professional experience in \"bodywork / accident repair\"."},{"passage_id":"p8","section":"required_qualifications","text":"Possess driving license class B (3)."},{"passage_id":"p8","section":"required_qualifications","text":"Have good knowledge of German."},{"passage_id":"p7","section":"required_qualifications","text":"Demonstrate passion, dedication, and enjoyment in repairing vehicle damage."},{"passage_id":"p8","section":"required_qualifications","text":"Work conscientiously, reliably, and in a service-oriented manner."},{"passage_id":"p7","section":"benefits","text":"A strong team and family working atmosphere."},{"passage_id":"p7","section":"benefits","text":"Comprehensive training and long-term job security."},{"passage_id":"p7","section":"benefits","text":"Development opportunities within a strong crafts group."},{"passage_id":"p7","section":"benefits","text":"Modern work equipment and high-quality workwear."},{"passage_id":"p7","section":"benefits","text":"Fair salary."},{"passage_id":"p7","section":"benefits","text":"1,000 € recommendation bonus for new colleagues."},{"passage_id":"p7","section":"benefits","text":"Corporate Benefits offering up to 50% discount on over 1,500 brands."},{"passage_id":"p10","section":"application_details","text":"Apply online via the \"Apply online\" button or via WhatsApp in 2 minutes."},{"passage_id":"p12","section":"application_details","text":"Contact person on site: Stephan Salzer, telephone +49 151 1199 1710."}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p9","p11"]}
``````

## english_typical: IT Governance Manager (m/f/d)

- Canonical job ID: `canonical_job_009b66b298c84a3a9df6273a04c510d1`
- Posting version: `posting_version_80b0cec022bb46a29e8687d926cae279`
- Source URL: https://linkedin.com/jobs/view/4458080709
- Translation runtime on the local Windows machine: 0.0 seconds

### Original preserved job posting

[Download original text](english_typical__original.txt)

``````text
Role Purpose Founded in 1921, OLDENDORFF CARRIERS combines its history as a German shipowner with the network of one of the world's leading drybulk operators. We currently control some 750 chartered and owned vessels of 67 mio tdw, and we carry around 330 mio tons of raw materials and semi-finished products across the seven seas each year. Our customers can expect 100% performance. All the way. As part of our ongoing journey towards a modern and innovative Technology organization, we are looking to further strengthen our IT Governance Team. We are searching for an IT Governance Manager who will play an integral part in shaping Oldendorff’s digital future. Job Responsibilities: Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels, ensuring traceable conformity with legal and regulatory requirements, internal policies, contractual obligations, audit expectations, and recognized good-practice frameworks. Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services. Strengthening governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT (operational technology) interfaces, and integrated maritime applications, and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards. Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting. Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments to ensure clear ownership, accountability, and traceability, and drive audit readiness by managing findings, supporting root-cause analysis, defining sustainable remediation actions, and tracking implementation. Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations. Establish and maintain quality and process management principles for IT governance, ensuring that processes are practical, measurable, and scalable for a decentralized global organization. Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency. What You Bring Along University degree in computer science, information systems, business administration, or a comparable IT-focused qualification. Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline. Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation. Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting. Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, and comfortable collaborating across cultures, time zones, functions, and levels of seniority. A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs. A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism. Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities. Fluency in written and spoken English. Nice-to-have Experience with IT strategy, organizational development, internal control systems, audit management, or risk management. Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments. German language skills. What we offer A collaborative, international working environment with flat hierarchies. Fast decision-making and a strong culture of ownership. Plenty of room for initiative, new ideas, and personal growth.
``````

### English text supplied to models

[Download English passages](english_typical__english.txt)

``````text
[p1] Role Purpose Founded in 1921, OLDENDORFF CARRIERS combines its history as a German shipowner with the network of one of the world's leading drybulk operators.

[p2] We currently control some 750 chartered and owned vessels of 67 mio tdw, and we carry around 330 mio tons of raw materials and semi-finished products across the seven seas each year.

[p3] Our customers can expect 100% performance.

[p4] All the way.

[p5] As part of our ongoing journey towards a modern and innovative Technology organization, we are looking to further strengthen our IT Governance Team.

[p6] We are searching for an IT Governance Manager who will play an integral part in shaping Oldendorff’s digital future.

[p7] Job Responsibilities: Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels, ensuring traceable conformity with legal and regulatory requirements, internal policies, contractual obligations, audit expectations, and recognized good-practice frameworks.

[p8] Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services.

[p9] Strengthening governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT (operational technology) interfaces, and integrated maritime applications, and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards.

[p10] Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting.

[p11] Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments to ensure clear ownership, accountability, and traceability, and drive audit readiness by managing findings, supporting root-cause analysis, defining sustainable remediation actions, and tracking implementation.

[p12] Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations.

[p13] Establish and maintain quality and process management principles for IT governance, ensuring that processes are practical, measurable, and scalable for a decentralized global organization.

[p14] Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency.

[p15] What You Bring Along University degree in computer science, information systems, business administration, or a comparable IT-focused qualification.

[p16] Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline.

[p17] Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation.

[p18] Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting.

[p19] Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, and comfortable collaborating across cultures, time zones, functions, and levels of seniority.

[p20] A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs.

[p21] A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism.

[p22] Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities.

[p23] Fluency in written and spoken English.

[p24] Nice-to-have Experience with IT strategy, organizational development, internal control systems, audit management, or risk management.

[p25] Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments.

[p26] German language skills.

[p27] What we offer A collaborative, international working environment with flat hierarchies.

[p28] Fast decision-making and a strong culture of ownership.

[p29] Plenty of room for initiative, new ideas, and personal growth.
``````

### Exact rendered prompt

[Download exact prompt](prompts/english_typical.txt)

``````text
Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "Role Purpose Founded in 1921, OLDENDORFF CARRIERS combines its history as a German shipowner with the network of one of the world's leading drybulk operators."}, {"id": "p2", "text": "We currently control some 750 chartered and owned vessels of 67 mio tdw, and we carry around 330 mio tons of raw materials and semi-finished products across the seven seas each year."}, {"id": "p3", "text": "Our customers can expect 100% performance."}, {"id": "p4", "text": "All the way."}, {"id": "p5", "text": "As part of our ongoing journey towards a modern and innovative Technology organization, we are looking to further strengthen our IT Governance Team."}, {"id": "p6", "text": "We are searching for an IT Governance Manager who will play an integral part in shaping Oldendorff’s digital future."}, {"id": "p7", "text": "Job Responsibilities: Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels, ensuring traceable conformity with legal and regulatory requirements, internal policies, contractual obligations, audit expectations, and recognized good-practice frameworks."}, {"id": "p8", "text": "Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services."}, {"id": "p9", "text": "Strengthening governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT (operational technology) interfaces, and integrated maritime applications, and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards."}, {"id": "p10", "text": "Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting."}, {"id": "p11", "text": "Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments to ensure clear ownership, accountability, and traceability, and drive audit readiness by managing findings, supporting root-cause analysis, defining sustainable remediation actions, and tracking implementation."}, {"id": "p12", "text": "Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations."}, {"id": "p13", "text": "Establish and maintain quality and process management principles for IT governance, ensuring that processes are practical, measurable, and scalable for a decentralized global organization."}, {"id": "p14", "text": "Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency."}, {"id": "p15", "text": "What You Bring Along University degree in computer science, information systems, business administration, or a comparable IT-focused qualification."}, {"id": "p16", "text": "Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline."}, {"id": "p17", "text": "Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation."}, {"id": "p18", "text": "Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting."}, {"id": "p19", "text": "Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, and comfortable collaborating across cultures, time zones, functions, and levels of seniority."}, {"id": "p20", "text": "A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs."}, {"id": "p21", "text": "A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism."}, {"id": "p22", "text": "Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities."}, {"id": "p23", "text": "Fluency in written and spoken English."}, {"id": "p24", "text": "Nice-to-have Experience with IT strategy, organizational development, internal control systems, audit management, or risk management."}, {"id": "p25", "text": "Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments."}, {"id": "p26", "text": "German language skills."}, {"id": "p27", "text": "What we offer A collaborative, international working environment with flat hierarchies."}, {"id": "p28", "text": "Fast decision-making and a strong culture of ownership."}, {"id": "p29", "text": "Plenty of room for initiative, new ideas, and personal growth."}]}
``````

### Model output: `mistralai/mistral-nemo`

- [Full response record](responses/english_typical__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 111.59 seconds; input tokens: 1427; output tokens: 1104; billed cost: $5.8806e-05.

``````text
{
  "overview": "Oldendorff Carriers seeks an IT Governance Manager to shape their digital future.",
  "items": [
    {
      "passage_id": "p7",
      "section": "responsibilities",
      "text": "Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels."
    },
    {
      "passage_id": "p8",
      "section": "responsibilities",
      "text": "Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services."
    },
    {
      "passage_id": "p9",
      "section": "responsibilities",
      "text": "Strengthen governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT interfaces, and integrated maritime applications."
    },
    {
      "passage_id": "p10",
      "section": "responsibilities",
      "text": "Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting."
    },
    {
      "passage_id": "p11",
      "section": "responsibilities",
      "text": "Coordinate IT risk, compliance, and control activities with relevant departments to ensure clear ownership, accountability, and traceability."
    },
    {
      "passage_id": "p12",
      "section": "responsibilities",
      "text": "Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations."
    },
    {
      "passage_id": "p13",
      "section": "responsibilities",
      "text": "Establish and maintain quality and process management principles for IT governance, ensuring processes are practical, measurable, and scalable for a decentralized global organization."
    },
    {
      "passage_id": "p14",
      "section": "responsibilities",
      "text": "Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency."
    },
    {
      "passage_id": "p15",
      "section": "required_qualifications",
      "text": "University degree in computer science, information systems, business administration, or a comparable IT-focused qualification."
    },
    {
      "passage_id": "p16",
      "section": "required_qualifications",
      "text": "Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline."
    },
    {
      "passage_id": "p17",
      "section": "required_qualifications",
      "text": "Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation."
    },
    {
      "passage_id": "p18",
      "section": "required_qualifications",
      "text": "Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting."
    },
    {
      "passage_id": "p19",
      "section": "required_qualifications",
      "text": "Confident communicator able to explain governance requirements clearly to various stakeholders."
    },
    {
      "passage_id": "p20",
      "section": "required_qualifications",
      "text": "A structured, analytical, and solution-oriented working style."
    },
    {
      "passage_id": "p21",
      "section": "required_qualifications",
      "text": "A proactive team player able to work independently and drive topics forward."
    },
    {
      "passage_id": "p22",
      "section": "required_qualifications",
      "text": "Willingness to occasionally travel internationally or visit vessels."
    },
    {
      "passage_id": "p23",
      "section": "required_qualifications",
      "text": "Fluency in written and spoken English."
    },
    {
      "passage_id": "p24",
      "section": "preferred_qualifications",
      "text": "Experience with IT strategy, organizational development, internal control systems, audit management, or risk management."
    },
    {
      "passage_id": "p25",
      "section": "preferred_qualifications",
      "text": "Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments."
    },
    {
      "passage_id": "p26",
      "section": "preferred_qualifications",
      "text": "German language skills."
    }
  ],
  "ignored_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p27", "p28", "p29"]
}
``````

### Model output: `openai/gpt-oss-20b`

- [Full response record](responses/english_typical__openai_gpt-oss-20b.json)
- Finish reason: `stop`; elapsed: 16.67 seconds; input tokens: 1489; output tokens: 819; billed cost: $0.000100512.

``````text
{"overview":"IT Governance Manager to shape Oldendorff’s digital future","items":[{"passage_id":"p7","section":"responsibilities","text":"Develop, maintain, and monitor a fit‑for‑purpose IT governance framework aligned with business strategy and regulatory expectations"},{"passage_id":"p8","section":"responsibilities","text":"Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements"},{"passage_id":"p9","section":"responsibilities","text":"Strengthen governance over digital transformation initiatives including cloud, data platforms, AI, vessel connectivity, OT interfaces, and maritime applications"},{"passage_id":"p10","section":"responsibilities","text":"Operate the internal IT control system covering policy management, control design, performance monitoring, evidence collection, remediation tracking, and reporting"},{"passage_id":"p11","section":"responsibilities","text":"Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operations to drive audit readiness"},{"passage_id":"p12","section":"responsibilities","text":"Support operational implementation of IT governance through guidance, training, and coaching for IT teams and stakeholders"},{"passage_id":"p13","section":"responsibilities","text":"Establish and maintain quality and process management principles for IT governance in a decentralized global organization"},{"passage_id":"p14","section":"responsibilities","text":"Collaborate with IT departments, fleet stakeholders, and corporate functions to balance compliance, efficiency, innovation, and risk transparency"},{"passage_id":"p15","section":"required_qualifications","text":"University degree in computer science, information systems, business administration, or a comparable IT‑focused qualification"},{"passage_id":"p16","section":"required_qualifications","text":"Practical experience in IT governance, controls, compliance, quality management, or process management"},{"passage_id":"p17","section":"required_qualifications","text":"Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit‑ready documentation"},{"passage_id":"p18","section":"required_qualifications","text":"Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting"},{"passage_id":"p19","section":"required_qualifications","text":"Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties"},{"passage_id":"p20","section":"required_qualifications","text":"Structured, analytical, and solution‑oriented working style balancing governance with practical business needs"},{"passage_id":"p21","section":"required_qualifications","text":"Proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism"},{"passage_id":"p22","section":"required_qualifications","text":"Willingness to occasionally travel internationally or visit vessels"},{"passage_id":"p23","section":"required_qualifications","text":"Fluency in written and spoken English"},{"passage_id":"p24","section":"preferred_qualifications","text":"Experience with IT strategy, organizational development, internal control systems, audit management, or risk management"},{"passage_id":"p25","section":"preferred_qualifications","text":"Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments"},{"passage_id":"p26","section":"preferred_qualifications","text":"German language skills"}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p27","p28","p29"]}
``````

### Model output: `inclusionai/ling-3.0-flash-vl-20260910`

- [Full response record](responses/english_typical__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 17.69 seconds; input tokens: 1416; output tokens: 990; billed cost: $0.000250872.

``````text
{"overview":"OLDENDORFF CARRIERS is hiring an IT Governance Manager to strengthen its IT Governance Team in a modern, innovative technology organization.","items":[{"passage_id":"p7","section":"responsibilities","text":"Further develop, maintain, and monitor an IT governance framework aligned with business strategy, regulatory expectations, cyber resilience, and operational realities across shore-based offices and vessels."},{"passage_id":"p8","section":"responsibilities","text":"Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services."},{"passage_id":"p9","section":"responsibilities","text":"Strengthen governance over digital transformation initiatives including cloud services, data platforms, automation, AI, vessel connectivity, OT interfaces, and maritime applications, advising on IT operating models, decision rights, and tool governance."},{"passage_id":"p10","section":"responsibilities","text":"Develop and operate the internal IT control system covering policy management, control design, performance monitoring, evidence collection, remediation tracking, and management reporting."},{"passage_id":"p11","section":"responsibilities","text":"Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments, driving audit readiness and managing remediation actions."},{"passage_id":"p12","section":"responsibilities","text":"Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations."},{"passage_id":"p13","section":"responsibilities","text":"Establish and maintain quality and process management principles for IT governance, ensuring processes are practical, measurable, and scalable for a decentralized global organization."},{"passage_id":"p14","section":"responsibilities","text":"Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency."},{"passage_id":"p15","section":"required_qualifications","text":"University degree in computer science, information systems, business administration, or a comparable IT-focused qualification."},{"passage_id":"p16","section":"required_qualifications","text":"Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline."},{"passage_id":"p17","section":"required_qualifications","text":"Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation."},{"passage_id":"p18","section":"required_qualifications","text":"Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting."},{"passage_id":"p19","section":"required_qualifications","text":"Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, comfortable collaborating across cultures, time zones, functions, and seniority levels."},{"passage_id":"p20","section":"required_qualifications","text":"A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs."},{"passage_id":"p21","section":"required_qualifications","text":"A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism."},{"passage_id":"p22","section":"required_qualifications","text":"Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities."},{"passage_id":"p23","section":"required_qualifications","text":"Fluency in written and spoken English."},{"passage_id":"p24","section":"preferred_qualifications","text":"Experience with IT strategy, organizational development, internal control systems, audit management, or risk management."},{"passage_id":"p25","section":"preferred_qualifications","text":"Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments."},{"passage_id":"p26","section":"preferred_qualifications","text":"German language skills."},{"passage_id":"p27","section":"benefits","text":"A collaborative, international working environment with flat hierarchies."},{"passage_id":"p28","section":"benefits","text":"Fast decision-making and a strong culture of ownership."},{"passage_id":"p29","section":"benefits","text":"Plenty of room for initiative, new ideas, and personal growth."}],"ignored_ids":["p1","p2","p3","p4","p5","p6"]}
``````

### Model output: `openai/gpt-oss-120b`

- [Full response record](responses/english_typical__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 70.47 seconds; input tokens: 1435; output tokens: 1112; billed cost: $0.00024321.

``````text
{
  "overview": "IT Governance Manager role at Oldendorff Carriers overseeing governance frameworks and controls.",
  "items": [
    {
      "passage_id": "p7",
      "section": "responsibilities",
      "text": "Develop and monitor an IT governance framework aligned with strategy, regulations, cyber resilience, and operations."
    },
    {
      "passage_id": "p8",
      "section": "responsibilities",
      "text": "Define, implement and improve IT policies, standards, procedures, control objectives, KPIs and evidence requirements."
    },
    {
      "passage_id": "p9",
      "section": "responsibilities",
      "text": "Govern digital transformation initiatives such as cloud, data platforms, AI, vessel connectivity and OT interfaces."
    },
    {
      "passage_id": "p10",
      "section": "responsibilities",
      "text": "Develop and operate the internal IT control system, including policy management, control design and remediation tracking."
    },
    {
      "passage_id": "p11",
      "section": "responsibilities",
      "text": "Coordinate IT risk, compliance and control activities with security, legal, data protection, finance and operations."
    },
    {
      "passage_id": "p12",
      "section": "responsibilities",
      "text": "Provide guidance, training and coaching to IT teams and business stakeholders worldwide."
    },
    {
      "passage_id": "p13",
      "section": "responsibilities",
      "text": "Establish quality and process management principles for scalable IT governance."
    },
    {
      "passage_id": "p14",
      "section": "responsibilities",
      "text": "Collaborate with IT, fleet and corporate functions to balance compliance, efficiency, innovation and risk transparency."
    },
    {
      "passage_id": "p15",
      "section": "required_qualifications",
      "text": "University degree in computer science, information systems, business administration or comparable IT qualification."
    },
    {
      "passage_id": "p16",
      "section": "required_qualifications",
      "text": "Practical experience in IT governance, controls, compliance, quality or process management."
    },
    {
      "passage_id": "p17",
      "section": "required_qualifications",
      "text": "Good understanding of IT governance principles, policy management, control design and audit documentation."
    },
    {
      "passage_id": "p18",
      "section": "required_qualifications",
      "text": "Ability to translate regulatory, audit and policy requirements into practical processes and reporting."
    },
    {
      "passage_id": "p19",
      "section": "required_qualifications",
      "text": "Confident communicator able to explain governance requirements to diverse stakeholders."
    },
    {
      "passage_id": "p20",
      "section": "required_qualifications",
      "text": "Structured, analytical and solution‑oriented working style."
    },
    {
      "passage_id": "p21",
      "section": "required_qualifications",
      "text": "Proactive team player who can work independently and drive topics forward."
    },
    {
      "passage_id": "p22",
      "section": "required_qualifications",
      "text": "Willingness to travel internationally or visit vessels occasionally."
    },
    {
      "passage_id": "p23",
      "section": "required_qualifications",
      "text": "Fluency in written and spoken English."
    },
    {
      "passage_id": "p24",
      "section": "preferred_qualifications",
      "text": "Experience with IT strategy, organizational development, internal control systems, audit or risk management."
    },
    {
      "passage_id": "p25",
      "section": "preferred_qualifications",
      "text": "Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services or maritime IT."
    },
    {
      "passage_id": "p26",
      "section": "preferred_qualifications",
      "text": "German language skills."
    },
    {
      "passage_id": "p27",
      "section": "benefits",
      "text": "Collaborative international environment with flat hierarchies."
    },
    {
      "passage_id": "p28",
      "section": "benefits",
      "text": "Fast decision‑making and strong culture of ownership."
    },
    {
      "passage_id": "p29",
      "section": "benefits",
      "text": "Plenty of room for initiative, new ideas and personal growth."
    }
  ],
  "ignored_ids": []
}
``````

### Model output: `google/gemini-2.5-flash-lite`

- [Full response record](responses/english_typical__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 2.77 seconds; input tokens: 1369; output tokens: 959; billed cost: $0.0005205.

``````text
{"overview":"OLDENDORFF CARRIERS is seeking an IT Governance Manager to shape its digital future by developing and maintaining an IT governance framework, policies, and controls.","items":[{"passage_id":"p7","section":"responsibilities","text":"Develop, maintain, and monitor an IT governance framework aligned with business strategy, regulatory expectations, cyber resilience, and operational realities for shore-based offices and vessels."},{"passage_id":"p8","section":"responsibilities","text":"Define, implement, and improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements for IT processes, organization, people, technology, data, and third-party services."},{"passage_id":"p9","section":"responsibilities","text":"Strengthen governance over digital transformation initiatives (cloud, data platforms, AI, vessel connectivity, OT, maritime applications) and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards."},{"passage_id":"p10","section":"responsibilities","text":"Develop and operate the internal IT control system, including policy management, control design, performance monitoring, evidence collection, remediation tracking, and management reporting."},{"passage_id":"p11","section":"responsibilities","text":"Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments, and manage audit readiness by addressing findings and tracking remediation."},{"passage_id":"p12","section":"responsibilities","text":"Support the operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders globally."},{"passage_id":"p13","section":"responsibilities","text":"Establish and maintain quality and process management principles for IT governance, ensuring processes are practical, measurable, and scalable for a decentralized global organization."},{"passage_id":"p14","section":"responsibilities","text":"Collaborate with IT departments, fleet stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and risk transparency."},{"passage_id":"p15","section":"required_qualifications","text":"University degree in computer science, information systems, business administration, or a comparable IT-focused qualification."},{"passage_id":"p16","section":"required_qualifications","text":"Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline."},{"passage_id":"p17","section":"required_qualifications","text":"Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation."},{"passage_id":"p18","section":"required_qualifications","text":"Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting."},{"passage_id":"p19","section":"required_qualifications","text":"Confident communicator able to explain governance requirements clearly to various stakeholders and collaborate across cultures, time zones, functions, and seniority levels."},{"passage_id":"p20","section":"required_qualifications","text":"A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs."},{"passage_id":"p21","section":"required_qualifications","text":"A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism."},{"passage_id":"p22","section":"required_qualifications","text":"Willingness to occasionally travel internationally or visit vessels for global IT governance activities."},{"passage_id":"p23","section":"required_qualifications","text":"Fluency in written and spoken English."},{"passage_id":"p24","section":"preferred_qualifications","text":"Experience with IT strategy, organizational development, internal control systems, audit management, or risk management."},{"passage_id":"p25","section":"preferred_qualifications","text":"Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments."},{"passage_id":"p26","section":"preferred_qualifications","text":"German language skills."},{"passage_id":"p27","section":"benefits","text":"A collaborative, international working environment with flat hierarchies."},{"passage_id":"p28","section":"benefits","text":"Fast decision-making and a strong culture of ownership."},{"passage_id":"p29","section":"benefits","text":"Plenty of room for initiative, new ideas, and personal growth."}],"ignored_ids":["p1","p2","p3","p4","p5","p6"]}
``````

## german: Head of Controlling / FP&A (m/w/d)

- Canonical job ID: `canonical_job_eee793a0d69c4198a72217848eac77b3`
- Posting version: `posting_version_79adb669147643e8b899839519645404`
- Source URL: https://linkedin.com/jobs/view/4453643322
- Translation runtime on the local Windows machine: 84.53 seconds

### Original preserved job posting

[Download original text](german__original.txt)

``````text
Unsere Mission ist es, mit Innovationskraft und Nachhaltigkeit die industrielle Transformation voranzutreiben. Ob bei der Optimierung von Rechenzentren, der Weiterentwicklung der Wasserstoffproduktion oder der Neugestaltung von Kühl- und Klimatechniksystemen – unsere thermischen Schlüsseltechnologien stärken zahlreiche Branchen weltweit. Als „One Kelvion“ arbeiten wir kontinuierlich an Lösungen, die unsere Kunden noch erfolgreicher machen und gleichzeitig zu einer nachhaltigeren Zukunft beitragen.Wir gestalten Zukunft – gemeinsam Sie sind eine strategisch geprägte Finance-Persönlichkeit mit ausgeprägtem Steuerungsanspruch und möchten die finanzielle Performance eines international tätigen Industrieunternehmens maßgeblich mitgestalten? Bei Kelvion übernehmen Sie eine exponierte Rolle an der Schnittstelle von Unternehmenssteuerung, strategischer Planung und operativer Performance-Verbesserung. In einem zunehmend kapitalmarktorientierten Umfeld leisten Sie einen wesentlichen Beitrag zu Transparenz, Forecast-Qualität, finanzieller Resilienz und nachhaltiger Wertsteigerung für Management, Investoren und weitere Stakeholder. Ihre Aufgaben Gesamtverantwortung für den konzernweiten Budget-, Forecast- und Mittelfristplanungsprozess inklusive Ableitung belastbarer Steering-Impulse für Vorstand, Geschäftsführung und Senior Management Weiterentwicklung einer integrierten Unternehmensplanung über GuV, Bilanz, Cashflow, Liquidität, Opex und Capex hinweg – mit Fokus auf Transparenz, Szenarioplanung und wertorientierte Steuerung Steuerung und Kommentierung der Monats-, Quartals- und Jahresabschlüsse in enger Zusammenarbeit mit Accounting, Treasury und den Business Units sowie Ableitung entscheidungsrelevanter Maßnahmen zur Ergebnisverbesserung Erstellung hochwertiger Management- und Board-Reports sowie adressatengerechter Unterlagen für Gesellschafter, Finanzierungspartner und weitere kapitalmarktnahe Stakeholder Mitwirkung an finanzwirtschaftlich relevanten Themen eines kapitalmarktorientierten Umfelds, insbesondere Performance-Dialogen, Refinanzierungs- und Finanzierungsfragestellungen, Covenant-Monitoring sowie Cash- und Liquiditätssteuerung Sparringspartner für CEO, CFO und Geschäftsleitung bei strategischen Fragestellungen, Investitionsentscheidungen, Portfolio-Priorisierung, Business Cases und Transformationsinitiativen Frühzeitige Identifikation von Chancen, Risiken und Abweichungen sowie Entwicklung von Handlungsoptionen, um Unternehmensziele und finanzielle Zielkorridore abzusichern Weiterentwicklung von Reporting-, Controlling- und Planungsprozessen, einschließlich KPI-Framework, Standardisierung, Automatisierung und Nutzung moderner BI- und EPM-Lösungen Fachliche und disziplinarische Führung sowie gezielte Weiterentwicklung des FP&A-/Controlling-Teams mit dem Anspruch, eine leistungsstarke, analytisch geprägte und businessnahe Steuerungsfunktion weiter auszubauen Enge Zusammenarbeit mit internationalen Funktionen und Regionen, um einheitliche Governance-, Reporting- und Performance-Standards im Konzern sicherzustellen Ihr Profil Erfolgreich abgeschlossenes Studium der Betriebswirtschaftslehre, Wirtschaftswissenschaften, Finance oder eines vergleichbaren Fachgebiets; zusätzliche Qualifikationen wie CFA, CMA, CPA oder Bilanzbuchhalter (IHK) sind von Vorteil Mehrjährige einschlägige Berufserfahrung (typischerweise 8–12 Jahre) in FP&A, Controlling oder Corporate Finance, idealerweise in einem international tätigen, kapitalmarktorientierten oder Private-Equity-geprägten Industrieunternehmen Führungserfahrung von internationalen Teams Fundierte Expertise in integrierter Finanzplanung, Performance Management, Cash- und Liquiditätssteuerung sowie im Aufbau belastbarer Entscheidungsgrundlagen für Top-Management-Gremien Sehr gutes Verständnis für Anforderungen eines kapitalmarktnahen Umfelds, z. B. in Bezug auf Governance, Transparenz, Stakeholder-Kommunikation, Refinanzierung, Covenants und finanzielle Steuerungslogiken Ausgeprägte analytische, konzeptionelle und strategische Fähigkeiten sowie hohe Sicherheit im Umgang mit komplexen Datenmodellen, Business Cases und Szenarioanalysen Überzeugende Kommunikations- und Präsentationsstärke mit der Fähigkeit, komplexe finanzielle Zusammenhänge klar, präzise und adressatengerecht bis auf Executive-Ebene darzustellen Sehr gute Kenntnisse in modernen Finance- und Reporting-Systemen, insbesondere Excel, Power BI, , SAP BW/BI, SAP S/4HANA sowie idealerweise Konsolidierungs- und Planungslösungen idealerweise Tagetik Hohes Maß an Eigeninitiative, Umsetzungsstärke und Veränderungskompetenz sowie die Fähigkeit, in einem anspruchsvollen und internationalen Umfeld nachhaltige Verbesserungen voranzutreiben Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift Was wir bieten Eine Schlüsselposition mit hoher strategischer Relevanz und direkter Sichtbarkeit im Top-Management Die Möglichkeit, die Finance-Organisation und Steuerungsinstrumente eines international aufgestellten Unternehmens aktiv weiterzuentwickeln Ein innovatives, wachstumsorientiertes Umfeld an der Schnittstelle von Industrie, Nachhaltigkeit und Transformation Ein kollaboratives, internationales Arbeitsumfeld im Sinne von „One Kelvion“ mit kurzen Entscheidungswegen und hoher Gestaltungsmöglichkeit Flexible Arbeitsmodelle und ein modernes Arbeitsumfeld, das Zusammenarbeit, Eigenverantwortung und Weiterentwicklung fördert Attraktive Vergütung sowie zusätzliche Benefits entsprechend Funktion und Verantwortung Unser Erfolg basiert auf Zusammenarbeit – wir fördern vielfältiges Denken, hören einander zu und schätzen jede einzelne Stimme. Kreativität entfaltet sich bei Kelvion dort, wo Menschen gehört, ihre Ideen willkommen geheißen und ihre Beiträge anerkannt werden. Mit einem flexiblen Arbeitsansatz stellen wir das Wohlbefinden und die Zufriedenheit unserer Mitarbeitenden in den Mittelpunkt. Dies stärkt die Bereitschaft sich einzubringen und eröffnet damit neue Karrierechancen Wir ermutigen engagierte Persönlichkeiten ihre Entwicklung selbst in die Hand zu nehmen, neue Wege zu gehen und gemeinsam mit uns Zukunft zu gestalten. Wir gestalten Zukunft – gemeinsam Apply now Head of Controlling / FP&A (m/f/d) Are you a strategically minded finance professional with a strong performance management mindset who is eager to play a key role in shaping the financial performance of an internationally operating industrial company? At Kelvion, you will take on a highly visible position at the intersection of corporate performance management, strategic planning, and operational performance improvement. In an increasingly capital market-oriented environment, you will make a significant contribution to transparency, forecast quality, financial resilience, and sustainable value creation for management, investors, and other stakeholders. Your Responsibilities Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management. Further development of an integrated business planning approach across P&L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management. Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance. Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders. Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management. Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives. Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors. Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions. Functional and disciplinary leadership as well as targeted development of the FP&A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organization. Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group. Your Profile Successfully completed degree in Business Administration, Economics, Finance, or a comparable field; additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage. Several years of relevant professional experience (typically 8–12 years) in FP&A, Controlling, or Corporate Finance, ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company. Leadership experience in managing international teams. Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies. Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms. Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses. Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level. Very good knowledge of modern finance and reporting systems, particularly Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik. High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment. Fluent German and English language skills, both written and spoken. What We Offer A key position with high strategic relevance and direct visibility to top management. The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company. An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation. A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact. Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development. Attractive compensation and additional benefits aligned with the scope and responsibility of the role. At Kelvion we thrive on collaboration, embracing diversity of thought, and valuing every voice. Within Kelvion creativity shines because people are listened to, their contributions recognised, and their ideas welcomed. Our flexible approach to the way we work places people’s health and satisfaction as a priority, enhancing engagement and fostering career opportunities. We empower engaged individuals to grow, progress and carve their own paths within the company. Together, We Shape the Future Apply now
``````

### English text supplied to models

[Download English passages](german__english.txt)

``````text
[p1] Our mission is to drive industrial transformation with innovation and sustainability.

[p2] Whether in the optimization of data centers, the further development of hydrogen production or the redesign of cooling and air conditioning systems – our key thermal technologies strengthen numerous industries worldwide.

[p3] As “One Kelvion”, we are continuously working on solutions that make our customers even more successful and at the same time contribute to a more sustainable future.We are shaping the future – together you are a strategically shaped finance personality with a pronounced management requirement and want to play a decisive role in shaping the financial performance of an internationally active industrial company?

[p4] At Kelvion, you take on an exposed role at the interface of corporate management, strategic planning and operational performance improvement.

[p5] In an increasingly capital market-oriented environment, you make a significant contribution to transparency, forecast quality, financial resilience and sustainable value creation for management, investors and other stakeholders.

[p6] Your tasks overall responsibility for the Group-wide budget, forecast and medium-term planning process including derivation of robust steering impulses for management, management and senior management Further development of integrated corporate planning across GuV, balance sheet, cash flow, liquidity, Opex and Capex – with focus on transparency, scenario planning and value-oriented control control and commentary on the monthly, quarterly and annual accounts in close cooperation with accounting, treasury and business units as well as derivation of decision-relevant measures for improving results Creation of high-quality management and board reports as well as address-oriented documents for shareholders, financing partners and further capital market-oriented stakeholders Participation in financially relevant topics of a capital market-oriented environment, in particular performance dialogues, refinancing and financing issues, covenant monitoring as well as cash and liquidity management sparring partners for CEOs, CFOs and management in strategic issues, investment decisions, portfolio prioritization, business cases and transformation initiatives Early identification of opportunities, controlling and planning options to secure corporate goals and financial target corridors Further development of reporting, controlling and planning processes, including KPI framework, standardization, Additional qualifications such as CFA, CMA, CPA or balance sheet accountants (IHK) are advantageous for several years of relevant professional experience (typically 8-12 years) in FP&A, controlling or corporate finance, ideally in an internationally active, capital market-oriented or private equity-oriented industrial company management experience of international teams In-depth expertise in integrated financial planning, performance management, cash and liquidity management as well as in building reliable decision-making basis for top management bodies Very good understanding of the requirements of a capital market-oriented environment, e.g.

[p7] B.

[p8] in terms of governance, transparency, stakeholder communication, refinancing, covenants and financial control logics Strong analytical, conceptual and strategic skills as well as high security in dealing with complex data models, business cases and scenario analyses Convincing communication and presentation strength with the ability to present complex financial contexts clearly, precisely and address-oriented up to the executive level Very good knowledge in modern finance and reporting systems, in particular Excel, Power BI, , SAP BW/BI, SAP S/4HANA as well as ideal consolidation and planning solutions ideal Tagetik High degree of initiative, implementation strength and change competence as well as the ability to drive forward sustainable improvements in a demanding and international environment Negotiation-secure knowledge of German and English in word and writing What we offer A key position with high strategic relevance and direct visibility in top management The opportunity to actively develop the finance organization and control instruments of an internationally positioned company An innovative, growth-oriented environment in the sense of "One Kelvion" with short decision-making paths and high design possibility Flexible working models and a modern working environment that promotes cooperation, self-responsibility and

[p9] At Kelvion, creativity unfolds where people are heard, their ideas welcomed and their contributions acknowledged.

[p10] With a flexible approach, we focus on the well-being and satisfaction of our employees.

[p11] This strengthens the willingness to participate and thus opens up new career opportunities We encourage committed personalities to take their development into their own hands, to break new ground and to shape the future together with us.

[p12] Are you a strategically minded finance professional with a strong performance management mindset who is eager to play a key role in shaping the financial performance of an internationally operating industrial company?

[p13] At Kelvion, you will take on a highly visible position at the intersection of corporate performance management, strategic planning, and operational performance improvement.

[p14] In an increasingly capital market-oriented environment, you will make a significant contribution to transparency, forecast quality, financial resilience, and sustainable value creation for management, investors, and other stakeholders.

[p15] Your Responsibilities Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management.

[p16] Further development of an integrated business planning approach across P&L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management.

[p17] Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance.

[p18] Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders.

[p19] Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management.

[p20] Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives.

[p21] Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors.

[p22] Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions.

[p23] Functional and disciplinary leadership as well as targeted development of the FP&A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organisation.

[p24] Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group.

[p25] Your Profile Successfully completed degree in Business Administration, Economics, Finance, or a comparable field; additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage.

[p26] Several years of relevant professional experience (typically 8–12 years) in FP&A, Controlling, or Corporate Finance, ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company.

[p27] Leadership experience in managing international teams.

[p28] Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies.

[p29] Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms.

[p30] Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses.

[p31] Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level.

[p32] Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik.

[p33] High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment.

[p34] Fluent German and English language skills, both written and spoken.

[p35] What We Offer A key position with high strategic relevance and direct visibility to top management.

[p36] The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company.

[p37] An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation.

[p38] A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact.

[p39] Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development.

[p40] Attractive compensation and additional benefits aligned with the scope and responsibility of the role.

[p41] At Kelvion we thrive on collaboration, embracing diversity of thought, and valuing every voice.

[p42] Within Kelvion creativity shines because people are listened to, their contributions recognised, and their ideas welcomed.

[p43] Our flexible approach to the way we work places people’s health and satisfaction as a priority, enhancing engagement and fostering career opportunities.

[p44] We empower engaged individuals to grow, progress and carve their own paths within the company.

[p45] Together, We Shape the Future Apply Now
``````

### Exact rendered prompt

[Download exact prompt](prompts/german.txt)

``````text
Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "Our mission is to drive industrial transformation with innovation and sustainability."}, {"id": "p2", "text": "Whether in the optimization of data centers, the further development of hydrogen production or the redesign of cooling and air conditioning systems – our key thermal technologies strengthen numerous industries worldwide."}, {"id": "p3", "text": "As “One Kelvion”, we are continuously working on solutions that make our customers even more successful and at the same time contribute to a more sustainable future.We are shaping the future – together you are a strategically shaped finance personality with a pronounced management requirement and want to play a decisive role in shaping the financial performance of an internationally active industrial company?"}, {"id": "p4", "text": "At Kelvion, you take on an exposed role at the interface of corporate management, strategic planning and operational performance improvement."}, {"id": "p5", "text": "In an increasingly capital market-oriented environment, you make a significant contribution to transparency, forecast quality, financial resilience and sustainable value creation for management, investors and other stakeholders."}, {"id": "p6", "text": "Your tasks overall responsibility for the Group-wide budget, forecast and medium-term planning process including derivation of robust steering impulses for management, management and senior management Further development of integrated corporate planning across GuV, balance sheet, cash flow, liquidity, Opex and Capex – with focus on transparency, scenario planning and value-oriented control control and commentary on the monthly, quarterly and annual accounts in close cooperation with accounting, treasury and business units as well as derivation of decision-relevant measures for improving results Creation of high-quality management and board reports as well as address-oriented documents for shareholders, financing partners and further capital market-oriented stakeholders Participation in financially relevant topics of a capital market-oriented environment, in particular performance dialogues, refinancing and financing issues, covenant monitoring as well as cash and liquidity management sparring partners for CEOs, CFOs and management in strategic issues, investment decisions, portfolio prioritization, business cases and transformation initiatives Early identification of opportunities, controlling and planning options to secure corporate goals and financial target corridors Further development of reporting, controlling and planning processes, including KPI framework, standardization, Additional qualifications such as CFA, CMA, CPA or balance sheet accountants (IHK) are advantageous for several years of relevant professional experience (typically 8-12 years) in FP&A, controlling or corporate finance, ideally in an internationally active, capital market-oriented or private equity-oriented industrial company management experience of international teams In-depth expertise in integrated financial planning, performance management, cash and liquidity management as well as in building reliable decision-making basis for top management bodies Very good understanding of the requirements of a capital market-oriented environment, e.g."}, {"id": "p7", "text": "B."}, {"id": "p8", "text": "in terms of governance, transparency, stakeholder communication, refinancing, covenants and financial control logics Strong analytical, conceptual and strategic skills as well as high security in dealing with complex data models, business cases and scenario analyses Convincing communication and presentation strength with the ability to present complex financial contexts clearly, precisely and address-oriented up to the executive level Very good knowledge in modern finance and reporting systems, in particular Excel, Power BI, , SAP BW/BI, SAP S/4HANA as well as ideal consolidation and planning solutions ideal Tagetik High degree of initiative, implementation strength and change competence as well as the ability to drive forward sustainable improvements in a demanding and international environment Negotiation-secure knowledge of German and English in word and writing What we offer A key position with high strategic relevance and direct visibility in top management The opportunity to actively develop the finance organization and control instruments of an internationally positioned company An innovative, growth-oriented environment in the sense of \"One Kelvion\" with short decision-making paths and high design possibility Flexible working models and a modern working environment that promotes cooperation, self-responsibility and"}, {"id": "p9", "text": "At Kelvion, creativity unfolds where people are heard, their ideas welcomed and their contributions acknowledged."}, {"id": "p10", "text": "With a flexible approach, we focus on the well-being and satisfaction of our employees."}, {"id": "p11", "text": "This strengthens the willingness to participate and thus opens up new career opportunities We encourage committed personalities to take their development into their own hands, to break new ground and to shape the future together with us."}, {"id": "p12", "text": "Are you a strategically minded finance professional with a strong performance management mindset who is eager to play a key role in shaping the financial performance of an internationally operating industrial company?"}, {"id": "p13", "text": "At Kelvion, you will take on a highly visible position at the intersection of corporate performance management, strategic planning, and operational performance improvement."}, {"id": "p14", "text": "In an increasingly capital market-oriented environment, you will make a significant contribution to transparency, forecast quality, financial resilience, and sustainable value creation for management, investors, and other stakeholders."}, {"id": "p15", "text": "Your Responsibilities Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management."}, {"id": "p16", "text": "Further development of an integrated business planning approach across P&L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management."}, {"id": "p17", "text": "Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance."}, {"id": "p18", "text": "Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders."}, {"id": "p19", "text": "Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management."}, {"id": "p20", "text": "Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives."}, {"id": "p21", "text": "Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors."}, {"id": "p22", "text": "Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions."}, {"id": "p23", "text": "Functional and disciplinary leadership as well as targeted development of the FP&A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organisation."}, {"id": "p24", "text": "Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group."}, {"id": "p25", "text": "Your Profile Successfully completed degree in Business Administration, Economics, Finance, or a comparable field; additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage."}, {"id": "p26", "text": "Several years of relevant professional experience (typically 8–12 years) in FP&A, Controlling, or Corporate Finance, ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company."}, {"id": "p27", "text": "Leadership experience in managing international teams."}, {"id": "p28", "text": "Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies."}, {"id": "p29", "text": "Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms."}, {"id": "p30", "text": "Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses."}, {"id": "p31", "text": "Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level."}, {"id": "p32", "text": "Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik."}, {"id": "p33", "text": "High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment."}, {"id": "p34", "text": "Fluent German and English language skills, both written and spoken."}, {"id": "p35", "text": "What We Offer A key position with high strategic relevance and direct visibility to top management."}, {"id": "p36", "text": "The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company."}, {"id": "p37", "text": "An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation."}, {"id": "p38", "text": "A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact."}, {"id": "p39", "text": "Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development."}, {"id": "p40", "text": "Attractive compensation and additional benefits aligned with the scope and responsibility of the role."}, {"id": "p41", "text": "At Kelvion we thrive on collaboration, embracing diversity of thought, and valuing every voice."}, {"id": "p42", "text": "Within Kelvion creativity shines because people are listened to, their contributions recognised, and their ideas welcomed."}, {"id": "p43", "text": "Our flexible approach to the way we work places people’s health and satisfaction as a priority, enhancing engagement and fostering career opportunities."}, {"id": "p44", "text": "We empower engaged individuals to grow, progress and carve their own paths within the company."}, {"id": "p45", "text": "Together, We Shape the Future Apply Now"}]}
``````

### Model output: `mistralai/mistral-nemo`

- [Full response record](responses/german__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 72.34 seconds; input tokens: 2610; output tokens: 1777; billed cost: $0.0001029.

``````text
{
  "overview": "Join Kelvion as a strategic finance professional to drive financial performance and sustainability in an international industrial setting.",
  "items": [
    {
      "passage_id": "p15",
      "section": "responsibilities",
      "text": "Overall responsibility for group-wide budgeting, forecasting, and mid-term planning, including deriving reliable steering impulses for top management."
    },
    {
      "passage_id": "p16",
      "section": "responsibilities",
      "text": "Further develop integrated business planning across P&L, balance sheet, cash flow, liquidity, Opex, and Capex, focusing on transparency and value-based management."
    },
    {
      "passage_id": "p17",
      "section": "responsibilities",
      "text": "Steer and comment on monthly, quarterly, and annual financial statements, collaborating with accounting, treasury, and business units to improve performance."
    },
    {
      "passage_id": "p18",
      "section": "responsibilities",
      "text": "Prepare high-quality management and board reports, as well as materials for shareholders and other stakeholders."
    },
    {
      "passage_id": "p19",
      "section": "responsibilities",
      "text": "Contribute to finance-related topics in a capital market-oriented environment, such as performance dialogues and refinancing matters."
    },
    {
      "passage_id": "p20",
      "section": "responsibilities",
      "text": "Act as a sparring partner for the CEO, CFO, and executive management on strategic matters, investment decisions, and transformation initiatives."
    },
    {
      "passage_id": "p21",
      "section": "responsibilities",
      "text": "Early identification of opportunities, risks, and deviations, developing action plans to safeguard corporate objectives and financial target corridors."
    },
    {
      "passage_id": "p22",
      "section": "responsibilities",
      "text": "Further develop reporting, controlling, and planning processes, including KPI frameworks and the use of modern BI and EPM solutions."
    },
    {
      "passage_id": "p23",
      "section": "responsibilities",
      "text": "Functional and disciplinary leadership of the FP&A/Controlling team, aiming to strengthen a high-performing, analytical, and business-oriented finance organization."
    },
    {
      "passage_id": "p24",
      "section": "responsibilities",
      "text": "Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the group."
    },
    {
      "passage_id": "p25",
      "section": "required_qualifications",
      "text": "Successfully completed degree in Business Administration, Economics, Finance, or a comparable field."
    },
    {
      "passage_id": "p26",
      "section": "required_qualifications",
      "text": "Several years of relevant professional experience (typically 8–12 years) in FP&A, Controlling, or Corporate Finance, ideally in an internationally operating, capital market-oriented, or private equity-backed industrial company."
    },
    {
      "passage_id": "p27",
      "section": "required_qualifications",
      "text": "Leadership experience in managing international teams."
    },
    {
      "passage_id": "p28",
      "section": "required_qualifications",
      "text": "Strong expertise in integrated financial planning, performance management, cash and liquidity management, and decision-making foundations for top management bodies."
    },
    {
      "passage_id": "p29",
      "section": "required_qualifications",
      "text": "Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms."
    },
    {
      "passage_id": "p30",
      "section": "required_qualifications",
      "text": "Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses."
    },
    {
      "passage_id": "p31",
      "section": "required_qualifications",
      "text": "Excellent communication and presentation skills, explaining complex financial matters clearly and effectively up to executive level."
    },
    {
      "passage_id": "p32",
      "section": "required_qualifications",
      "text": "Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik."
    },
    {
      "passage_id": "p33",
      "section": "required_qualifications",
      "text": "High level of initiative, execution capability, and change management skills, driving sustainable improvements in a demanding and international environment."
    },
    {
      "passage_id": "p34",
      "section": "required_qualifications",
      "text": "Fluent German and English language skills, both written and spoken."
    },
    {
      "passage_id": "p35",
      "section": "benefits",
      "text": "A key position with high strategic relevance and direct visibility to top management."
    },
    {
      "passage_id": "p36",
      "section": "benefits",
      "text": "The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company."
    },
    {
      "passage_id": "p37",
      "section": "benefits",
      "text": "An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation."
    },
    {
      "passage_id": "p38",
      "section": "benefits",
      "text": "A collaborative, international working environment with short decision-making paths and extensive opportunities to make an impact."
    },
    {
      "passage_id": "p39",
      "section": "benefits",
      "text": "Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development."
    },
    {
      "passage_id": "p40",
      "section": "benefits",
      "text": "Attractive compensation and additional benefits aligned with the scope and responsibility of the role."
    },
    {
      "passage_id": "p41",
      "section": "benefits",
      "text": "At Kelvion, we thrive on collaboration, embracing diversity of thought, and valuing every voice."
    },
    {
      "passage_id": "p42",
      "section": "benefits",
      "text": "Within Kelvion, creativity shines because people are listened to, their contributions recognized, and their ideas welcomed."
    },
    {
      "passage_id": "p43",
      "section": "benefits",
      "text": "Our flexible approach to work prioritizes people’s health and satisfaction, enhancing engagement and fostering career opportunities."
    },
    {
      "passage_id": "p44",
      "section": "benefits",
      "text": "We empower engaged individuals to grow, progress, and carve their own paths within the company."
    }
  ],
  "ignored_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p25", "p26", "p27", "p28", "p29", "p30", "p31", "p32", "p33", "p34", "p35", "p36", "p37", "p38", "p39", "p40", "p41", "p42", "p43", "p44", "p45"]
}
``````

### Model output: `openai/gpt-oss-20b`

- [Full response record](responses/german__openai_gpt-oss-20b.json)
- Finish reason: `length`; elapsed: 242.36 seconds; input tokens: 2577; output tokens: 5500; billed cost: $0.000844733.

``````text
{"final{"

 		

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

   

 	

 	  

 	

 	

 	

 	

 	

 	

 	

 	

 	

   

 	  

   

 	  

   

  



 	  

 	  

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

  
``````

### Model output: `inclusionai/ling-3.0-flash-vl-20260910`

- [Full response record](responses/german__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 20.56 seconds; input tokens: 2567; output tokens: 1365; billed cost: $0.00039972.

``````text
{"overview":"Senior finance leadership role at Kelvion responsible for group-wide planning, reporting, performance management, and strategic financial steering in a capital market-oriented environment.","items":[{"passage_id":"p15","section":"responsibilities","text":"Overall responsibility for group-wide budgeting, forecasting, and mid-term planning, including derivation of steering impulses for the Board of Management, Executive Leadership, and Senior Management."},{"passage_id":"p16","section":"responsibilities","text":"Further develop integrated business planning across P&L, balance sheet, cash flow, liquidity, Opex, and Capex, focusing on transparency, scenario planning, and value-based management."},{"passage_id":"p17","section":"responsibilities","text":"Steer and comment on monthly, quarterly, and annual financial statements with Accounting, Treasury, and Business Units, deriving decision-relevant measures to improve performance."},{"passage_id":"p18","section":"responsibilities","text":"Prepare high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders."},{"passage_id":"p19","section":"responsibilities","text":"Contribute to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, and cash and liquidity management."},{"passage_id":"p20","section":"responsibilities","text":"Act as sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives."},{"passage_id":"p21","section":"responsibilities","text":"Early identification of opportunities, risks, and deviations, and develop action plans to safeguard corporate objectives and financial target corridors."},{"passage_id":"p22","section":"responsibilities","text":"Further develop reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and modern BI and EPM solutions."},{"passage_id":"p23","section":"responsibilities","text":"Provide functional and disciplinary leadership and targeted development of the FP&A/Controlling team to strengthen a high-performing, analytical, and business-oriented finance organization."},{"passage_id":"p24","section":"responsibilities","text":"Collaborate closely with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group."},{"passage_id":"p25","section":"required_qualifications","text":"Successfully completed degree in Business Administration, Economics, Finance, or a comparable field."},{"passage_id":"p26","section":"required_qualifications","text":"Several years of relevant professional experience, typically 8–12 years, in FP&A, Controlling, or Corporate Finance."},{"passage_id":"p27","section":"required_qualifications","text":"Leadership experience in managing international teams."},{"passage_id":"p28","section":"required_qualifications","text":"Strong expertise in integrated financial planning, performance management, cash and liquidity management, and developing reliable decision-making foundations for top management bodies."},{"passage_id":"p29","section":"required_qualifications","text":"Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms."},{"passage_id":"p30","section":"required_qualifications","text":"Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses."},{"passage_id":"p31","section":"required_qualifications","text":"Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level."},{"passage_id":"p32","section":"required_qualifications","text":"Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions."},{"passage_id":"p33","section":"required_qualifications","text":"High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment."},{"passage_id":"p34","section":"required_qualifications","text":"Fluent German and English language skills, both written and spoken."},{"passage_id":"p6","section":"preferred_qualifications","text":"Additional qualifications such as CFA, CMA, CPA, or balance sheet accountants (IHK) are advantageous."},{"passage_id":"p26","section":"preferred_qualifications","text":"Experience ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company."},{"passage_id":"p32","section":"preferred_qualifications","text":"Ideal consolidation and planning solutions, preferably Tagetik."},{"passage_id":"p25","section":"preferred_qualifications","text":"Additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage."},{"passage_id":"p35","section":"benefits","text":"A key position with high strategic relevance and direct visibility to top management."},{"passage_id":"p36","section":"benefits","text":"The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company."},{"passage_id":"p37","section":"benefits","text":"An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation."},{"passage_id":"p38","section":"benefits","text":"A collaborative, international working environment in line with the One Kelvion philosophy, featuring short decision-making paths and extensive opportunities to make an impact."},{"passage_id":"p39","section":"benefits","text":"Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development."},{"passage_id":"p40","section":"benefits","text":"Attractive compensation and additional benefits aligned with the scope and responsibility of the role."},{"passage_id":"p45","section":"application_details","text":"Apply Now."}],"ignored_ids":["p1","p2","p3","p4","p5","p7","p8","p9","p10","p11","p12","p13","p14","p41","p42","p43","p44"]}
``````

### Model output: `openai/gpt-oss-120b`

- [Full response record](responses/german__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 44.12 seconds; input tokens: 2564; output tokens: 1722; billed cost: $0.000387608.

``````text
{
  "overview": "Strategic finance leader responsible for group budgeting, forecasting, planning and performance improvement in a capital‑market‑oriented industrial company.",
  "items": [
    {
      "passage_id": "p15",
      "section": "responsibilities",
      "text": "Overall responsibility for group‑wide budgeting, forecasting and medium‑term planning."
    },
    {
      "passage_id": "p16",
      "section": "responsibilities",
      "text": "Develop integrated business planning across P&L, balance sheet, cash flow, liquidity, Opex and Capex with focus on transparency and scenario planning."
    },
    {
      "passage_id": "p17",
      "section": "responsibilities",
      "text": "Steer and comment on monthly, quarterly and annual financial statements together with accounting, treasury and business units."
    },
    {
      "passage_id": "p18",
      "section": "responsibilities",
      "text": "Prepare high‑quality management and board reports and stakeholder‑specific materials."
    },
    {
      "passage_id": "p19",
      "section": "responsibilities",
      "text": "Contribute to finance topics such as performance dialogues, refinancing, covenant monitoring and cash‑liquidity management."
    },
    {
      "passage_id": "p20",
      "section": "responsibilities",
      "text": "Act as sparring partner for CEO, CFO and executive management on strategy, investments and transformation initiatives."
    },
    {
      "passage_id": "p21",
      "section": "responsibilities",
      "text": "Identify opportunities, risks and deviations early and develop action plans to protect financial targets."
    },
    {
      "passage_id": "p22",
      "section": "responsibilities",
      "text": "Further develop reporting, controlling and planning processes, KPI framework, standardisation and automation using modern BI/EPM tools."
    },
    {
      "passage_id": "p23",
      "section": "responsibilities",
      "text": "Lead and develop the FP&A/Controlling team to build a high‑performing finance organisation."
    },
    {
      "passage_id": "p24",
      "section": "responsibilities",
      "text": "Collaborate with international functions and regions to ensure consistent governance, reporting and performance standards."
    },
    {
      "passage_id": "p25",
      "section": "required_qualifications",
      "text": "Degree in Business Administration, Economics, Finance or comparable field."
    },
    {
      "passage_id": "p27",
      "section": "required_qualifications",
      "text": "Leadership experience managing international teams."
    },
    {
      "passage_id": "p28",
      "section": "required_qualifications",
      "text": "Strong expertise in integrated financial planning, performance management, cash and liquidity management."
    },
    {
      "passage_id": "p29",
      "section": "required_qualifications",
      "text": "Solid understanding of capital‑market‑oriented environment requirements (governance, transparency, stakeholder communication, refinancing, covenants)."
    },
    {
      "passage_id": "p30",
      "section": "required_qualifications",
      "text": "Strong analytical, conceptual and strategic skills; confidence with complex data models, business cases and scenario analyses."
    },
    {
      "passage_id": "p31",
      "section": "required_qualifications",
      "text": "Excellent communication and presentation abilities up to executive level."
    },
    {
      "passage_id": "p32",
      "section": "required_qualifications",
      "text": "Very good knowledge of modern finance and reporting systems (Excel, Power BI, SAP BW/BI, SAP S/4HANA)."
    },
    {
      "passage_id": "p34",
      "section": "required_qualifications",
      "text": "Fluent German and English, both written and spoken."
    },
    {
      "passage_id": "p26",
      "section": "preferred_qualifications",
      "text": "Experience preferably within an internationally operating, capital‑market‑oriented or private‑equity‑backed industrial company."
    },
    {
      "passage_id": "p25",
      "section": "preferred_qualifications",
      "text": "Additional qualifications such as CFA, CMA, CPA or Certified Management Accountant are advantageous."
    },
    {
      "passage_id": "p32",
      "section": "preferred_qualifications",
      "text": "Familiarity with consolidation and planning solutions, preferably Tagetik."
    },
    {
      "passage_id": "p33",
      "section": "preferred_qualifications",
      "text": "High initiative, execution capability and change‑management skills to drive sustainable improvements."
    },
    {
      "passage_id": "p35",
      "section": "benefits",
      "text": "Key position with high strategic relevance and direct visibility to top management."
    },
    {
      "passage_id": "p36",
      "section": "benefits",
      "text": "Opportunity to shape and further develop the finance organisation and performance‑management tools."
    },
    {
      "passage_id": "p37",
      "section": "benefits",
      "text": "Innovative, growth‑oriented environment at the intersection of industry, sustainability and transformation."
    },
    {
      "passage_id": "p38",
      "section": "benefits",
      "text": "Collaborative international working environment with short decision‑making paths."
    },
    {
      "passage_id": "p39",
      "section": "benefits",
      "text": "Flexible working models and modern workplace promoting collaboration, ownership and development."
    },
    {
      "passage_id": "p40",
      "section": "benefits",
      "text": "Attractive compensation and additional benefits aligned with role scope and responsibility."
    },
    {
      "passage_id": "p45",
      "section": "application_details",
      "text": "Apply now."
    }
  ],
  "ignored_ids": [
    "p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p11","p12","p13","p14","p41","p42","p43","p44"
  ]
}
``````

### Model output: `google/gemini-2.5-flash-lite`

- [Full response record](responses/german__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 3.56 seconds; input tokens: 2527; output tokens: 1330; billed cost: $0.0007847.

``````text
{"overview":"Lead financial planning and analysis for an international industrial company, driving strategic decision-making and financial performance.","items":[{"passage_id":"p15","section":"responsibilities","text":"Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management."},{"passage_id":"p16","section":"responsibilities","text":"Further development of an integrated business planning approach across P&L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management."},{"passage_id":"p17","section":"responsibilities","text":"Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance."},{"passage_id":"p18","section":"responsibilities","text":"Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders."},{"passage_id":"p19","section":"responsibilities","text":"Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management."},{"passage_id":"p20","section":"responsibilities","text":"Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives."},{"passage_id":"p21","section":"responsibilities","text":"Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors."},{"passage_id":"p22","section":"responsibilities","text":"Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions."},{"passage_id":"p23","section":"responsibilities","text":"Functional and disciplinary leadership as well as targeted development of the FP&A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organisation."},{"passage_id":"p24","section":"responsibilities","text":"Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group."},{"passage_id":"p25","section":"required_qualifications","text":"Successfully completed degree in Business Administration, Economics, Finance, or a comparable field."},{"passage_id":"p26","section":"required_qualifications","text":"Several years of relevant professional experience (typically 8–12 years) in FP&A, Controlling, or Corporate Finance."},{"passage_id":"p27","section":"required_qualifications","text":"Leadership experience in managing international teams."},{"passage_id":"p28","section":"required_qualifications","text":"Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies."},{"passage_id":"p29","section":"required_qualifications","text":"Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms."},{"passage_id":"p30","section":"required_qualifications","text":"Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses."},{"passage_id":"p31","section":"required_qualifications","text":"Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level."},{"passage_id":"p32","section":"required_qualifications","text":"Very good knowledge in modern finance and reporting systems, in particular Excel, Power BI, SAP BW/BI, SAP S/4HANA."},{"passage_id":"p33","section":"required_qualifications","text":"High degree of initiative, implementation strength and change competence as well as the ability to drive forward sustainable improvements in a demanding and international environment."},{"passage_id":"p34","section":"required_qualifications","text":"Fluent German and English language skills, both written and spoken."},{"passage_id":"p25","section":"preferred_qualifications","text":"Additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage."},{"passage_id":"p26","section":"preferred_qualifications","text":"Ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company."},{"passage_id":"p32","section":"preferred_qualifications","text":"Ideally consolidation and planning solutions, preferably Tagetik."},{"passage_id":"p35","section":"benefits","text":"A key position with high strategic relevance and direct visibility to top management."},{"passage_id":"p36","section":"benefits","text":"The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company."},{"passage_id":"p37","section":"benefits","text":"An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation."},{"passage_id":"p38","section":"benefits","text":"A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact."},{"passage_id":"p39","section":"benefits","text":"Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development."},{"passage_id":"p40","section":"benefits","text":"Attractive compensation and additional benefits aligned with the scope and responsibility of the role."},{"passage_id":"p45","section":"application_details","text":"Apply Now"}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p11","p12","p13","p14","p37","p38","p39","p41","p42","p43","p44"]}
``````

## preferred: Marketing COE Lead

- Canonical job ID: `canonical_job_45953610e2414f0d8a05a692b560c72b`
- Posting version: `posting_version_b737755a330344bf899ef021439087e4`
- Source URL: https://jobs.eastman.com/job/Kingsport-Marketing-COE-Lead-TN-37660/1377487500
- Translation runtime on the local Windows machine: 0.0 seconds

### Original preserved job posting

[Download original text](preferred__original.txt)

``````text
Marketing COE Lead Job Details | Eastman This site uses cookies to store information on your computer. Some are essential to make our site work; others help us improve the user experience. By using the site, you consent to the placement of these cookies. Read our Privacy Notice to learn more. Accept Close Skip to main content Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Language Deutsch (Deutschland) English (United States) Español (España) Français (France) Nederlands (Nederland) Português (Brasil) View Profile Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Select how often (in days) to receive an alert: Create Alert × Select how often (in days) to receive an alert: Apply now » Marketing COE Lead Job Requisition ID: 55990 Founded in 1920, Eastman is a global specialty materials company that produces a broad range of products found in items people use every day. With the purpose of enhancing the quality of life in a material way, Eastman works with customers to deliver innovative products and solutions while maintaining a commitment to safety and sustainability. The company’s innovation-driven growth model takes advantage of world-class technology platforms, deep customer engagement, and differentiated application development to grow its leading positions in attractive end markets such as transportation, building and construction, and consumables. As a globally inclusive company, Eastman employs approximately 13,000 people around the world and serves customers in more than 100 countries. The company had 2025 revenue of approximately $8.8 billion and is headquartered in Kingsport, Tennessee, USA. For more information, visit www.eastman.com . Description The Global Commercial Excellence organization is responsible for building world class commercial capability within Eastman. This includes continuously upgrading the capabilities and improving the performance of our people, processes, and systems. As a Marketing Excellence Center of Excellence (COE) Leader, you lead the central COE and co-lead the Marketing COE Leadership Team along with key business leaders. You are responsible for building world-class marketing capabilities and driving commercial results. You will accomplish this through partnering with marketing and commercial leadership to: Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience (strategic, digital, brand, marcom, channel marketing, etc) —facilitating strategic discussions, co-creating and prioritizing initiatives in annual scorecard and our transformation roadmap, driving timely, data-informed decisions, and ensuring shared accountability for execution and results. Ensure convergence and commitment across businesses to common marketing processes and best practices. Develop, implement, and execute COE global & regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise. Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles. Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way. Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics. Partner with businesses leaders to support the transformation journey of Marketing Excellence. Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing. While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions. Responsibilities Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT. Develop co-created solutions with senior marketing leaders on key priorities. Drive implementation, with and through COE LT leaders, on key initiatives. Create and manage ongoing COE LT agenda. Ensure active tracking, monitoring, adjustments and actions on key initiatives. Work actively with other functional leaders (e.g. HR) to drive change management and enable the implementation (e.g. with training, communication, tool deployment, etc.). Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed. Lead support for COE LT: Oversee central COE staff to support COE LT activities. Provide support analysis. Conduct direct training, communication, coaching, and change management. Support special projects where necessary. Consistently identify and evaluate external best practices in the marketing space. Share best practices globally. Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts. Drive Marketing Tools Implementation: Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection. Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results. Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs. Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews. Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement. Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact. Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement. Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps. Develop and implement plans to close gaps. Serve as an expert coach in marketing processes. Conduct leader and train the trainer coaching. Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders. Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards. Qualifications Bachelors, from an accredited college or university is required. Masters or MBA preferred. Min. 10 years of commercial experience; minimum 5 years marketing experience required. Experience developing and executing Commercial Excellence Capabilities with cross business team members. Demonstrated experience and success leading teams and influencing without authority. US-based location preferred. Benefits Your total rewards go far beyond a competitive salary. When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career. Compensation & Incentives • Base pay plus performance-based incentive opportunities that let you share in our success. Health & Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future. • A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life. • Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling. Retirement & Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings. Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments. Growth & Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career. At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of. Eastman Chemical Company is an equal opportunity employer. All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law. Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day. Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing Opens in a new tab. Opens in a new tab. Opens in a new tab. Opens in a new tab. Eastman.com Privacy Policy View All Jobs Supply Chain Responsibility Legal Contact Us © 2020 Eastman Chemical Company or its subsidiaries. All rights reserved. As used herein, ® denotes registered trademark status in the U.S. only. Thank you for your interest in careers at Eastman. Eastman Chemical Company is an equal opportunity employer. All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law. Eastman is committed to creating a highly engaged workplace, where everyone can contribute to their fullest potential each day. As part of our recruiting and hiring process, Eastman will not ask for fees, payments or credit card information. If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com.
``````

### English text supplied to models

[Download English passages](preferred__english.txt)

``````text
[p1] Marketing COE Lead Job Details | Eastman This site uses cookies to store information on your computer.

[p2] Some are essential to make our site work; others help us improve the user experience.

[p3] By using the site, you consent to the placement of these cookies.

[p4] Read our Privacy Notice to learn more.

[p5] Accept Close Skip to main content Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Language Deutsch (Deutschland) English (United States) Español (España) Français (France) Nederlands (Nederland) Português (Brasil) View Profile Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Select how often (in days) to receive an alert: Create Alert × Select how often (in days) to receive an alert: Apply now » Marketing COE Lead Job Requisition ID: 55990 Founded in 1920, Eastman is a global specialty materials company that produces a broad range of products found in items people use every day.

[p6] With the purpose of enhancing the quality of life in a material way, Eastman works with customers to deliver innovative products and solutions while maintaining a commitment to safety and sustainability.

[p7] The company’s innovation-driven growth model takes advantage of world-class technology platforms, deep customer engagement, and differentiated application development to grow its leading positions in attractive end markets such as transportation, building and construction, and consumables.

[p8] As a globally inclusive company, Eastman employs approximately 13,000 people around the world and serves customers in more than 100 countries.

[p9] The company had 2025 revenue of approximately $8.8 billion and is headquartered in Kingsport, Tennessee, USA.

[p10] For more information, visit www.eastman.com .

[p11] Description The Global Commercial Excellence organization is responsible for building world class commercial capability within Eastman.

[p12] This includes continuously upgrading the capabilities and improving the performance of our people, processes, and systems.

[p13] As a Marketing Excellence Center of Excellence (COE) Leader, you lead the central COE and co-lead the Marketing COE Leadership Team along with key business leaders.

[p14] You are responsible for building world-class marketing capabilities and driving commercial results.

[p15] You will accomplish this through partnering with marketing and commercial leadership to: Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience (strategic, digital, brand, marcom, channel marketing, etc) —facilitating strategic discussions, co-creating and prioritizing initiatives in annual scorecard and our transformation roadmap, driving timely, data-informed decisions, and ensuring shared accountability for execution and results.

[p16] Ensure convergence and commitment across businesses to common marketing processes and best practices.

[p17] Develop, implement, and execute COE global & regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise.

[p18] Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles.

[p19] Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way.

[p20] Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics.

[p21] Partner with businesses leaders to support the transformation journey of Marketing Excellence.

[p22] Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing.

[p23] While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions.

[p24] Responsibilities Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT.

[p25] Develop co-created solutions with senior marketing leaders on key priorities.

[p26] Drive implementation, with and through COE LT leaders, on key initiatives.

[p27] Create and manage ongoing COE LT agenda.

[p28] Ensure active tracking, monitoring, adjustments and actions on key initiatives.

[p29] Work actively with other functional leaders (e.g.

[p30] HR) to drive change management and enable the implementation (e.g.

[p31] with training, communication, tool deployment, etc.).

[p32] Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed.

[p33] Lead support for COE LT: Oversee central COE staff to support COE LT activities.

[p34] Provide support analysis.

[p35] Conduct direct training, communication, coaching, and change management.

[p36] Support special projects where necessary.

[p37] Consistently identify and evaluate external best practices in the marketing space.

[p38] Share best practices globally.

[p39] Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts.

[p40] Drive Marketing Tools Implementation: Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection.

[p41] Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results.

[p42] Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs.

[p43] Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews.

[p44] Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement.

[p45] Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact.

[p46] Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement.

[p47] Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps.

[p48] Develop and implement plans to close gaps.

[p49] Serve as an expert coach in marketing processes.

[p50] Conduct leader and train the trainer coaching.

[p51] Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders.

[p52] Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards.

[p53] Qualifications Bachelors, from an accredited college or university is required.

[p54] Masters or MBA preferred.

[p55] Min.

[p56] 10 years of commercial experience; minimum 5 years marketing experience required.

[p57] Experience developing and executing Commercial Excellence Capabilities with cross business team members.

[p58] Demonstrated experience and success leading teams and influencing without authority.

[p59] US-based location preferred.

[p60] Benefits Your total rewards go far beyond a competitive salary.

[p61] When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career.

[p62] Compensation & Incentives • Base pay plus performance-based incentive opportunities that let you share in our success.

[p63] Health & Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future.

[p64] • A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life.

[p65] • Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling.

[p66] Retirement & Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings.

[p67] Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments.

[p68] Growth & Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career.

[p69] At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of.

[p70] Eastman Chemical Company is an equal opportunity employer.

[p71] All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law.

[p72] Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day.

[p73] Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing Opens in a new tab.

[p74] Opens in a new tab.

[p75] Opens in a new tab.

[p76] Opens in a new tab.

[p77] Eastman.com Privacy Policy View All Jobs Supply Chain Responsibility Legal Contact Us © 2020 Eastman Chemical Company or its subsidiaries.

[p78] All rights reserved.

[p79] As used herein, ® denotes registered trademark status in the U.S.

[p80] only.

[p81] Thank you for your interest in careers at Eastman.

[p82] Eastman Chemical Company is an equal opportunity employer.

[p83] All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law.

[p84] Eastman is committed to creating a highly engaged workplace, where everyone can contribute to their fullest potential each day.

[p85] As part of our recruiting and hiring process, Eastman will not ask for fees, payments or credit card information.

[p86] If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com.
``````

### Exact rendered prompt

[Download exact prompt](prompts/preferred.txt)

``````text
Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "Marketing COE Lead Job Details | Eastman This site uses cookies to store information on your computer."}, {"id": "p2", "text": "Some are essential to make our site work; others help us improve the user experience."}, {"id": "p3", "text": "By using the site, you consent to the placement of these cookies."}, {"id": "p4", "text": "Read our Privacy Notice to learn more."}, {"id": "p5", "text": "Accept Close Skip to main content Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Language Deutsch (Deutschland) English (United States) Español (España) Français (France) Nederlands (Nederland) Português (Brasil) View Profile Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Select how often (in days) to receive an alert: Create Alert × Select how often (in days) to receive an alert: Apply now » Marketing COE Lead Job Requisition ID: 55990 Founded in 1920, Eastman is a global specialty materials company that produces a broad range of products found in items people use every day."}, {"id": "p6", "text": "With the purpose of enhancing the quality of life in a material way, Eastman works with customers to deliver innovative products and solutions while maintaining a commitment to safety and sustainability."}, {"id": "p7", "text": "The company’s innovation-driven growth model takes advantage of world-class technology platforms, deep customer engagement, and differentiated application development to grow its leading positions in attractive end markets such as transportation, building and construction, and consumables."}, {"id": "p8", "text": "As a globally inclusive company, Eastman employs approximately 13,000 people around the world and serves customers in more than 100 countries."}, {"id": "p9", "text": "The company had 2025 revenue of approximately $8.8 billion and is headquartered in Kingsport, Tennessee, USA."}, {"id": "p10", "text": "For more information, visit www.eastman.com ."}, {"id": "p11", "text": "Description The Global Commercial Excellence organization is responsible for building world class commercial capability within Eastman."}, {"id": "p12", "text": "This includes continuously upgrading the capabilities and improving the performance of our people, processes, and systems."}, {"id": "p13", "text": "As a Marketing Excellence Center of Excellence (COE) Leader, you lead the central COE and co-lead the Marketing COE Leadership Team along with key business leaders."}, {"id": "p14", "text": "You are responsible for building world-class marketing capabilities and driving commercial results."}, {"id": "p15", "text": "You will accomplish this through partnering with marketing and commercial leadership to: Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience (strategic, digital, brand, marcom, channel marketing, etc) —facilitating strategic discussions, co-creating and prioritizing initiatives in annual scorecard and our transformation roadmap, driving timely, data-informed decisions, and ensuring shared accountability for execution and results."}, {"id": "p16", "text": "Ensure convergence and commitment across businesses to common marketing processes and best practices."}, {"id": "p17", "text": "Develop, implement, and execute COE global & regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise."}, {"id": "p18", "text": "Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles."}, {"id": "p19", "text": "Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way."}, {"id": "p20", "text": "Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics."}, {"id": "p21", "text": "Partner with businesses leaders to support the transformation journey of Marketing Excellence."}, {"id": "p22", "text": "Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing."}, {"id": "p23", "text": "While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions."}, {"id": "p24", "text": "Responsibilities Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT."}, {"id": "p25", "text": "Develop co-created solutions with senior marketing leaders on key priorities."}, {"id": "p26", "text": "Drive implementation, with and through COE LT leaders, on key initiatives."}, {"id": "p27", "text": "Create and manage ongoing COE LT agenda."}, {"id": "p28", "text": "Ensure active tracking, monitoring, adjustments and actions on key initiatives."}, {"id": "p29", "text": "Work actively with other functional leaders (e.g."}, {"id": "p30", "text": "HR) to drive change management and enable the implementation (e.g."}, {"id": "p31", "text": "with training, communication, tool deployment, etc.)."}, {"id": "p32", "text": "Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed."}, {"id": "p33", "text": "Lead support for COE LT: Oversee central COE staff to support COE LT activities."}, {"id": "p34", "text": "Provide support analysis."}, {"id": "p35", "text": "Conduct direct training, communication, coaching, and change management."}, {"id": "p36", "text": "Support special projects where necessary."}, {"id": "p37", "text": "Consistently identify and evaluate external best practices in the marketing space."}, {"id": "p38", "text": "Share best practices globally."}, {"id": "p39", "text": "Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts."}, {"id": "p40", "text": "Drive Marketing Tools Implementation: Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection."}, {"id": "p41", "text": "Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results."}, {"id": "p42", "text": "Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs."}, {"id": "p43", "text": "Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews."}, {"id": "p44", "text": "Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement."}, {"id": "p45", "text": "Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact."}, {"id": "p46", "text": "Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement."}, {"id": "p47", "text": "Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps."}, {"id": "p48", "text": "Develop and implement plans to close gaps."}, {"id": "p49", "text": "Serve as an expert coach in marketing processes."}, {"id": "p50", "text": "Conduct leader and train the trainer coaching."}, {"id": "p51", "text": "Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders."}, {"id": "p52", "text": "Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards."}, {"id": "p53", "text": "Qualifications Bachelors, from an accredited college or university is required."}, {"id": "p54", "text": "Masters or MBA preferred."}, {"id": "p55", "text": "Min."}, {"id": "p56", "text": "10 years of commercial experience; minimum 5 years marketing experience required."}, {"id": "p57", "text": "Experience developing and executing Commercial Excellence Capabilities with cross business team members."}, {"id": "p58", "text": "Demonstrated experience and success leading teams and influencing without authority."}, {"id": "p59", "text": "US-based location preferred."}, {"id": "p60", "text": "Benefits Your total rewards go far beyond a competitive salary."}, {"id": "p61", "text": "When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career."}, {"id": "p62", "text": "Compensation & Incentives • Base pay plus performance-based incentive opportunities that let you share in our success."}, {"id": "p63", "text": "Health & Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future."}, {"id": "p64", "text": "• A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life."}, {"id": "p65", "text": "• Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling."}, {"id": "p66", "text": "Retirement & Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings."}, {"id": "p67", "text": "Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments."}, {"id": "p68", "text": "Growth & Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career."}, {"id": "p69", "text": "At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of."}, {"id": "p70", "text": "Eastman Chemical Company is an equal opportunity employer."}, {"id": "p71", "text": "All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law."}, {"id": "p72", "text": "Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day."}, {"id": "p73", "text": "Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing Opens in a new tab."}, {"id": "p74", "text": "Opens in a new tab."}, {"id": "p75", "text": "Opens in a new tab."}, {"id": "p76", "text": "Opens in a new tab."}, {"id": "p77", "text": "Eastman.com Privacy Policy View All Jobs Supply Chain Responsibility Legal Contact Us © 2020 Eastman Chemical Company or its subsidiaries."}, {"id": "p78", "text": "All rights reserved."}, {"id": "p79", "text": "As used herein, ® denotes registered trademark status in the U.S."}, {"id": "p80", "text": "only."}, {"id": "p81", "text": "Thank you for your interest in careers at Eastman."}, {"id": "p82", "text": "Eastman Chemical Company is an equal opportunity employer."}, {"id": "p83", "text": "All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law."}, {"id": "p84", "text": "Eastman is committed to creating a highly engaged workplace, where everyone can contribute to their fullest potential each day."}, {"id": "p85", "text": "As part of our recruiting and hiring process, Eastman will not ask for fees, payments or credit card information."}, {"id": "p86", "text": "If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com."}]}
``````

### Model output: `mistralai/mistral-nemo`

- [Full response record](responses/preferred__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 140.64 seconds; input tokens: 3599; output tokens: 3299; billed cost: $0.000167351.

``````text
{
  "overview": "Lead the Marketing Center of Excellence (COE) to build world-class marketing capabilities and drive commercial results.",
  "items": [
    {
      "passage_id": "p15",
      "section": "responsibilities",
      "text": "Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi-sub-marketing disciplinary experience."
    },
    {
      "passage_id": "p16",
      "section": "responsibilities",
      "text": "Ensure convergence and commitment across businesses to common marketing processes and best practices."
    },
    {
      "passage_id": "p17",
      "section": "responsibilities",
      "text": "Develop, implement, and execute COE global & regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise."
    },
    {
      "passage_id": "p18",
      "section": "responsibilities",
      "text": "Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles."
    },
    {
      "passage_id": "p19",
      "section": "responsibilities",
      "text": "Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data-driven way."
    },
    {
      "passage_id": "p20",
      "section": "responsibilities",
      "text": "Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics."
    },
    {
      "passage_id": "p21",
      "section": "responsibilities",
      "text": "Partner with businesses leaders to support the transformation journey of Marketing Excellence."
    },
    {
      "passage_id": "p22",
      "section": "responsibilities",
      "text": "Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing."
    },
    {
      "passage_id": "p23",
      "section": "responsibilities",
      "text": "While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions."
    },
    {
      "passage_id": "p24",
      "section": "responsibilities",
      "text": "Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT."
    },
    {
      "passage_id": "p25",
      "section": "responsibilities",
      "text": "Develop co-created solutions with senior marketing leaders on key priorities."
    },
    {
      "passage_id": "p26",
      "section": "responsibilities",
      "text": "Drive implementation, with and through COE LT leaders, on key initiatives."
    },
    {
      "passage_id": "p27",
      "section": "responsibilities",
      "text": "Create and manage ongoing COE LT agenda."
    },
    {
      "passage_id": "p28",
      "section": "responsibilities",
      "text": "Ensure active tracking, monitoring, adjustments and actions on key initiatives."
    },
    {
      "passage_id": "p29",
      "section": "responsibilities",
      "text": "Work actively with other functional leaders (e.g. HR) to drive change management and enable the implementation (e.g. with training, communication, tool deployment, etc.)."
    },
    {
      "passage_id": "p30",
      "section": "responsibilities",
      "text": "Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed."
    },
    {
      "passage_id": "p31",
      "section": "responsibilities",
      "text": "Lead support for COE LT: Oversee central COE staff to support COE LT activities."
    },
    {
      "passage_id": "p32",
      "section": "responsibilities",
      "text": "Provide support analysis."
    },
    {
      "passage_id": "p33",
      "section": "responsibilities",
      "text": "Conduct direct training, communication, coaching, and change management."
    },
    {
      "passage_id": "p34",
      "section": "responsibilities",
      "text": "Support special projects where necessary."
    },
    {
      "passage_id": "p35",
      "section": "responsibilities",
      "text": "Consistently identify and evaluate external best practices in the marketing space."
    },
    {
      "passage_id": "p36",
      "section": "responsibilities",
      "text": "Share best practices globally."
    },
    {
      "passage_id": "p37",
      "section": "responsibilities",
      "text": "Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts."
    },
    {
      "passage_id": "p38",
      "section": "responsibilities",
      "text": "Drive Marketing Tools Implementation: Serve as the global subject-matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection."
    },
    {
      "passage_id": "p39",
      "section": "responsibilities",
      "text": "Co-create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results."
    },
    {
      "passage_id": "p40",
      "section": "responsibilities",
      "text": "Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs."
    },
    {
      "passage_id": "p41",
      "section": "responsibilities",
      "text": "Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews."
    },
    {
      "passage_id": "p42",
      "section": "responsibilities",
      "text": "Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement."
    },
    {
      "passage_id": "p43",
      "section": "responsibilities",
      "text": "Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact."
    },
    {
      "passage_id": "p44",
      "section": "responsibilities",
      "text": "Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement."
    },
    {
      "passage_id": "p45",
      "section": "responsibilities",
      "text": "Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps."
    },
    {
      "passage_id": "p46",
      "section": "responsibilities",
      "text": "Develop and implement plans to close gaps."
    },
    {
      "passage_id": "p47",
      "section": "responsibilities",
      "text": "Serve as an expert coach in marketing processes."
    },
    {
      "passage_id": "p48",
      "section": "responsibilities",
      "text": "Conduct leader and train the trainer coaching."
    },
    {
      "passage_id": "p49",
      "section": "responsibilities",
      "text": "Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders."
    },
    {
      "passage_id": "p50",
      "section": "responsibilities",
      "text": "Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards."
    },
    {
      "passage_id": "p53",
      "section": "required_qualifications",
      "text": "Bachelors, from an accredited college or university is required."
    },
    {
      "passage_id": "p54",
      "section": "preferred_qualifications",
      "text": "Masters or MBA preferred."
    },
    {
      "passage_id": "p56",
      "section": "required_qualifications",
      "text": "Min. 10 years of commercial experience; minimum 5 years marketing experience required."
    },
    {
      "passage_id": "p57",
      "section": "required_qualifications",
      "text": "Experience developing and executing Commercial Excellence Capabilities with cross business team members."
    },
    {
      "passage_id": "p58",
      "section": "required_qualifications",
      "text": "Demonstrated experience and success leading teams and influencing without authority."
    },
    {
      "passage_id": "p59",
      "section": "preferred_qualifications",
      "text": "US-based location preferred."
    },
    {
      "passage_id": "p60",
      "section": "benefits",
      "text": "Your total rewards go far beyond a competitive salary."
    },
    {
      "passage_id": "p61",
      "section": "benefits",
      "text": "When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career."
    },
    {
      "passage_id": "p62",
      "section": "benefits",
      "text": "Compensation & Incentives • Base pay plus performance-based incentive opportunities that let you share in our success."
    },
    {
      "passage_id": "p63",
      "section": "benefits",
      "text": "Health & Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future."
    },
    {
      "passage_id": "p64",
      "section": "benefits",
      "text": "• A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life."
    },
    {
      "passage_id": "p65",
      "section": "benefits",
      "text": "• Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling."
    },
    {
      "passage_id": "p66",
      "section": "benefits",
      "text": "Retirement & Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings."
    },
    {
      "passage_id": "p67",
      "section": "benefits",
      "text": "Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments."
    },
    {
      "passage_id": "p68",
      "section": "benefits",
      "text": "Growth & Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career."
    },
    {
      "passage_id": "p69",
      "section": "benefits",
      "text": "At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of."
    },
    {
      "passage_id": "p70",
      "section": "application_details",
      "text": "Eastman Chemical Company is an equal opportunity employer."
    },
    {
      "passage_id": "p71",
      "section": "application_details",
      "text": "All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law."
    },
    {
      "passage_id": "p72",
      "section": "application_details",
      "text": "Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day."
    },
    {
      "passage_id": "p73",
      "section": "application_details",
      "text": "Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing"
    }
  ],
  "ignored_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p29", "p30", "p31", "p32", "p33", "p34", "p35", "p36", "p37", "p38", "p39", "p40", "p41", "p42", "p43", "p44", "p45", "p46", "p47", "p48", "p49", "p50", "p51", "p52", "p55", "p59", "p60", "p61", "p62", "p63", "p64", "p65", "p66", "p67", "p68", "p69", "p70", "p71", "p72", "p73", "p74", "p75", "p76", "p77", "p78", "p79", "p80", "p81", "p82", "p83", "p84", "p85", "p86"]
}
``````

### Model output: `openai/gpt-oss-20b`

- [Full response record](responses/preferred__openai_gpt-oss-20b.json)
- Finish reason: `stop`; elapsed: 15.73 seconds; input tokens: 3516; output tokens: 829; billed cost: $0.000137898.

``````text
{"overview":"Lead the global Marketing COE to build world‑class marketing capabilities and drive commercial results.","items":[{"passage_id":"p24","section":"responsibilities","text":"Lead the Marketing COE Leadership Team and co‑create a multi‑year roadmap for 2026."},{"passage_id":"p24","section":"responsibilities","text":"Drive implementation of key initiatives and ensure active tracking and adjustments."},{"passage_id":"p24","section":"responsibilities","text":"Serve as the global subject‑matter lead for marketing processes, tools, and systems."},{"passage_id":"p24","section":"responsibilities","text":"Coach senior marketing leaders on analytics, dashboards, and continuous improvement."},{"passage_id":"p53","section":"required_qualifications","text":"Bachelor’s degree from an accredited college or university."},{"passage_id":"p56","section":"required_qualifications","text":"10 years of commercial experience, including a minimum of 5 years in marketing."},{"passage_id":"p57","section":"required_qualifications","text":"Experience developing and executing Commercial Excellence capabilities with cross‑business teams."},{"passage_id":"p58","section":"required_qualifications","text":"Demonstrated success leading teams and influencing without authority."},{"passage_id":"p54","section":"preferred_qualifications","text":"Master’s or MBA degree."},{"passage_id":"p59","section":"preferred_qualifications","text":"US‑based location."},{"passage_id":"p60","section":"benefits","text":"Competitive base pay plus performance‑based incentives, comprehensive medical, dental, vision, and wellness programs, 401(k) with company match, paid holidays, personal day, paid time off, and career development resources."}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p11","p12","p13","p14","p15","p16","p17","p18","p19","p20","p21","p22","p23","p25","p26","p27","p28","p29","p30","p31","p32","p33","p34","p35","p36","p37","p38","p39","p40","p41","p42","p43","p44","p45","p46","p47","p48","p49","p50","p51","p52","p53","p54","p55","p56","p57","p58","p59","p60","p61","p62","p63","p64","p65","p66","p67","p68","p69","p70","p71","p72","p73","p74","p75","p76","p77","p78","p79","p80","p81","p82","p83","p84","p85","p86"]}
``````

### Model output: `inclusionai/ling-3.0-flash-vl-20260910`

- [Full response record](responses/preferred__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 31.55 seconds; input tokens: 3527; output tokens: 1895; billed cost: $0.00055272.

``````text
{"overview":"Lead the global Marketing Center of Excellence, driving marketing capability, tools, analytics, and talent development in partnership with commercial leadership.","items":[{"passage_id":"p13","section":"responsibilities","text":"Lead the central Marketing COE and co-lead the Marketing COE Leadership Team with key business leaders."},{"passage_id":"p14","section":"responsibilities","text":"Build world-class marketing capabilities and drive commercial results."},{"passage_id":"p15","section":"responsibilities","text":"Lead the global Marketing COE Leadership Team, facilitating strategic discussions and prioritizing initiatives across multi-disciplinary marketing functions."},{"passage_id":"p16","section":"responsibilities","text":"Ensure convergence and commitment across businesses to common marketing processes and best practices."},{"passage_id":"p17","section":"responsibilities","text":"Develop and execute global and regional marketing initiatives and best practices across the enterprise."},{"passage_id":"p18","section":"responsibilities","text":"Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles."},{"passage_id":"p19","section":"responsibilities","text":"Work with IT to identify technological solutions for marketers to assess market dynamics and customer segments."},{"passage_id":"p20","section":"responsibilities","text":"Accelerate the shift to disciplined marketing processes, metrics, and analytics."},{"passage_id":"p21","section":"responsibilities","text":"Partner with business leaders to support the transformation journey of Marketing Excellence."},{"passage_id":"p22","section":"responsibilities","text":"Become a trusted advisor and business partner to commercial leadership in marketing."},{"passage_id":"p23","section":"responsibilities","text":"Serve as a key liaison with Sales, Product and Pricing, IT, and other functions for marketing capability solutions."},{"passage_id":"p24","section":"responsibilities","text":"Co-lead the primary decision-making body for marketing excellence, developing a multi-year roadmap and gaining enterprise alignment."},{"passage_id":"p25","section":"responsibilities","text":"Develop co-created solutions with senior marketing leaders on key priorities."},{"passage_id":"p26","section":"responsibilities","text":"Drive implementation of key initiatives through COE Leadership Team leaders."},{"passage_id":"p27","section":"responsibilities","text":"Create and manage the ongoing COE Leadership Team agenda."},{"passage_id":"p28","section":"responsibilities","text":"Ensure active tracking, monitoring, adjustments, and actions on key initiatives."},{"passage_id":"p31","section":"responsibilities","text":"Work with functional leaders such as HR to drive change management and enable implementation through training, communication, and tool deployment."},{"passage_id":"p32","section":"responsibilities","text":"Develop resourcing options and recommendations to accelerate progress and close gaps."},{"passage_id":"p33","section":"responsibilities","text":"Oversee central COE staff to support COE Leadership Team activities."},{"passage_id":"p34","section":"responsibilities","text":"Provide support analysis for COE activities."},{"passage_id":"p35","section":"responsibilities","text":"Conduct direct training, communication, coaching, and change management."},{"passage_id":"p36","section":"responsibilities","text":"Support special projects where necessary."},{"passage_id":"p37","section":"responsibilities","text":"Consistently identify and evaluate external best practices in the marketing space."},{"passage_id":"p38","section":"responsibilities","text":"Share best practices globally."},{"passage_id":"p39","section":"responsibilities","text":"Proactively identify improvement opportunities in existing marketing tools or needs for alternate tools."},{"passage_id":"p40","section":"responsibilities","text":"Serve as global subject-matter lead for marketing processes, tools, methodologies, and systems, owning lifecycle decisions and advising on tool selection."},{"passage_id":"p41","section":"responsibilities","text":"Co-create and maintain the global Marketing Excellence roadmap, prioritizing initiatives by impact and feasibility."},{"passage_id":"p42","section":"responsibilities","text":"Partner with IT and vendors to define requirements, coordinate implementations, and ensure solutions meet global business needs."},{"passage_id":"p43","section":"responsibilities","text":"Define and govern marketing metrics and dashboards, overseeing adoption KPIs, target setting, and performance reviews."},{"passage_id":"p44","section":"responsibilities","text":"Coach senior marketing leaders on using analytics and dashboards to drive decisions and continuous improvement."},{"passage_id":"p45","section":"responsibilities","text":"Design and run global change and adoption strategies for sustained tool use and business impact."},{"passage_id":"p46","section":"responsibilities","text":"Support global development and implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement."},{"passage_id":"p47","section":"responsibilities","text":"Work with commercial leadership on fact-based assessment and prioritization of seller and marketing leader capability gaps."},{"passage_id":"p48","section":"responsibilities","text":"Develop and implement plans to close capability gaps."},{"passage_id":"p49","section":"responsibilities","text":"Serve as an expert coach in marketing processes."},{"passage_id":"p50","section":"responsibilities","text":"Conduct leader and train-the-trainer coaching."},{"passage_id":"p51","section":"responsibilities","text":"Execute, facilitate, and support marketing training sessions in coordination with marketing leaders."},{"passion_id":"p52","section":"responsibilities","text":"Develop and execute best practices for recruiting and retaining marketing talent."},{"passage_id":"p53","section":"responsibilities","text":"Define global marketing competencies, curriculum, onboarding, and ongoing development standards."},{"passage_id":"p53","section":"required_qualifications","text":"Bachelor's degree from an accredited college or university is required."},{"passage_id":"p56","section":"required_qualifications","text":"Minimum 10 years of commercial experience with a minimum of 5 years marketing experience required."},{"passage_id":"p57","section":"required_qualifications","text":"Demonstrated experience developing and executing Commercial Excellence Capabilities with cross-business team members."},{"passage_id":"p58","section":"required_qualifications","text":"Demonstrated experience and success leading teams and influencing without authority."},{"passage_id":"p54","section":"preferred_qualifications","text":"Master's degree or MBA preferred."},{"passage_id":"p59","section":"preferred_qualifications","text":"US-based location preferred."},{"passage_id":"p62","section":"benefits","text":"Base pay plus performance-based incentive opportunities."},{"passage_id":"p63","section":"benefits","text":"Comprehensive medical, prescription-drug, and dental coverage with a Health Savings Account option."},{"passage_id":"p64","section":"benefits","text":"Voluntary benefits including vision, optional life, and critical-illness protection."},{"passage_id":"p65","section":"benefits","text":"Holistic wellness support including financial-planning tools, family-building assistance, parental leave, and Employee Assistance Program counseling."},{"passage_id":"p66","section":"benefits","text":"401(k) with company match plus an additional annual retirement contribution from Eastman."},{"passage_id":"p67","section":"benefits","text":"Eleven paid holidays, one personal day, paid time off, and paid vacation."},{"passage_id":"p68","section":"benefits","text":"Access to mentorship, learning resources, and leadership programs."},{"passage_id":"p70","section":"application_details","text":"Eastman Chemical Company is an equal opportunity employer; all qualified applicants receive consideration without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status, or any other protected classes."},{"passage_id":"p85","section":"application_details","text":"Eastman will not ask for fees, payments, or credit card information during the recruiting and hiring process."}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p71","p72","p73","p74","p75","p76","p77","p78","p79","p80","p81","p82","p83","p84","p86"]}
``````

### Model output: `openai/gpt-oss-120b`

- [Full response record](responses/preferred__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 14.08 seconds; input tokens: 3486; output tokens: 1782; billed cost: $0.0012396.

``````text
{
  "overview": "Lead the global Marketing COE, build capabilities, and drive commercial results at Eastman.",
  "items": [
    {
      "passage_id": "p24",
      "section": "responsibilities",
      "text": "Lead Marketing COE Leadership Team and develop a multi-year roadmap with enterprise alignment."
    },
    {
      "passage_id": "p25",
      "section": "responsibilities",
      "text": "Co‑create solutions with senior marketing leaders on key priorities."
    },
    {
      "passage_id": "p26",
      "section": "responsibilities",
      "text": "Drive implementation of key initiatives through COE LT leaders."
    },
    {
      "passage_id": "p27",
      "section": "responsibilities",
      "text": "Create and manage ongoing COE LT agenda."
    },
    {
      "passage_id": "p28",
      "section": "responsibilities",
      "text": "Track, monitor, and adjust key initiatives."
    },
    {
      "passage_id": "p30",
      "section": "responsibilities",
      "text": "Partner with functional leaders (e.g., HR) for change management, training, and communication."
    },
    {
      "passage_id": "p32",
      "section": "responsibilities",
      "text": "Develop resourcing options to accelerate progress or close gaps."
    },
    {
      "passage_id": "p33",
      "section": "responsibilities",
      "text": "Oversee central COE staff supporting COE LT activities."
    },
    {
      "passage_id": "p34",
      "section": "responsibilities",
      "text": "Provide support analysis."
    },
    {
      "passage_id": "p35",
      "section": "responsibilities",
      "text": "Conduct training, communication, coaching, and change management."
    },
    {
      "passage_id": "p37",
      "section": "responsibilities",
      "text": "Identify and evaluate external marketing best practices."
    },
    {
      "passage_id": "p38",
      "section": "responsibilities",
      "text": "Share best practices globally."
    },
    {
      "passage_id": "p39",
      "section": "responsibilities",
      "text": "Identify improvement opportunities in marketing tools and recommend enhancements."
    },
    {
      "passage_id": "p40",
      "section": "responsibilities",
      "text": "Serve as global subject‑matter lead for marketing processes, tools, methodologies, and systems."
    },
    {
      "passage_id": "p41",
      "section": "responsibilities",
      "text": "Co‑create and maintain the global Marketing Excellence roadmap, prioritizing initiatives."
    },
    {
      "passage_id": "p42",
      "section": "responsibilities",
      "text": "Partner with IT and vendors to define requirements and ensure solutions meet global needs."
    },
    {
      "passage_id": "p43",
      "section": "responsibilities",
      "text": "Define and govern marketing metrics, dashboards, adoption KPIs, and performance reviews."
    },
    {
      "passage_id": "p44",
      "section": "responsibilities",
      "text": "Coach senior marketing leaders on using analytics for decisions and continuous improvement."
    },
    {
      "passage_id": "p45",
      "section": "responsibilities",
      "text": "Design and run global change and adoption strategies for sustained tool usage."
    },
    {
      "passage_id": "p46",
      "section": "responsibilities",
      "text": "Support global development and implementation of marketing capability efforts."
    },
    {
      "passage_id": "p47",
      "section": "responsibilities",
      "text": "Assess and prioritize seller and marketing leader capability gaps."
    },
    {
      "passage_id": "p48",
      "section": "responsibilities",
      "text": "Develop and implement plans to close capability gaps."
    },
    {
      "passage_id": "p49",
      "section": "responsibilities",
      "text": "Serve as expert coach in marketing processes."
    },
    {
      "passage_id": "p50",
      "section": "responsibilities",
      "text": "Conduct leader and train‑the‑trainer coaching."
    },
    {
      "passage_id": "p51",
      "section": "responsibilities",
      "text": "Facilitate marketing training sessions with marketing leaders."
    },
    {
      "passage_id": "p52",
      "section": "responsibilities",
      "text": "Develop best practices for recruiting and retaining marketing talent and define competencies."
    },
    {
      "passage_id": "p53",
      "section": "required_qualifications",
      "text": "Bachelor's degree from an accredited college or university."
    },
    {
      "passage_id": "p56",
      "section": "required_qualifications",
      "text": "Minimum 10 years of commercial experience, including at least 5 years of marketing experience."
    },
    {
      "passage_id": "p57",
      "section": "required_qualifications",
      "text": "Experience developing and executing Commercial Excellence capabilities with cross‑business teams."
    },
    {
      "passage_id": "p58",
      "section": "required_qualifications",
      "text": "Proven ability to lead teams and influence without authority."
    },
    {
      "passage_id": "p54",
      "section": "preferred_qualifications",
      "text": "Master's degree or MBA preferred."
    },
    {
      "passage_id": "p59",
      "section": "preferred_qualifications",
      "text": "US‑based location preferred."
    },
    {
      "passage_id": "p60",
      "section": "benefits",
      "text": "Competitive salary with performance‑based incentive opportunities."
    },
    {
      "passage_id": "p63",
      "section": "benefits",
      "text": "Comprehensive medical, prescription‑drug, and dental coverage with HSA option."
    },
    {
      "passage_id": "p64",
      "section": "benefits",
      "text": "Voluntary benefits including vision, optional life, and critical‑illness protection."
    },
    {
      "passage_id": "p65",
      "section": "benefits",
      "text": "Holistic wellness support: financial‑planning tools, family‑building assistance, parental leave, and EAP counseling."
    },
    {
      "passage_id": "p66",
      "section": "benefits",
      "text": "401(k) with company match plus additional annual retirement contribution."
    },
    {
      "passage_id": "p67",
      "section": "benefits",
      "text": "Paid time off including 11 holidays, one personal day, vacation, and PTO."
    },
    {
      "passage_id": "p68",
      "section": "benefits",
      "text": "Access to mentorship, learning resources, and leadership development programs."
    }
  ],
  "ignored_ids": [
    "p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p11","p12","p13","p14","p15","p16","p17","p18","p19","p20","p21","p22","p23","p29","p31","p32","p36","p70","p71","p72","p73","p74","p75","p76","p77","p78","p79","p80","p81","p82","p83","p84","p85","p86"
  ]
}
``````

### Model output: `google/gemini-2.5-flash-lite`

- [Full response record](responses/preferred__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 5.09 seconds; input tokens: 3399; output tokens: 1982; billed cost: $0.0011327.

``````text
{"overview":"Lead the Global Commercial Excellence organization to build world-class marketing capabilities and drive commercial results.","items":[{"passage_id":"p15","section":"responsibilities","text":"Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience."},{"passage_id":"p16","section":"responsibilities","text":"Ensure convergence and commitment across businesses to common marketing processes and best practices."},{"passage_id":"p17","section":"responsibilities","text":"Develop, implement, and execute COE global & regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise."},{"passage_id":"p18","section":"responsibilities","text":"Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles."},{"passage_id":"p19","section":"responsibilities","text":"Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way."},{"passage_id":"p20","section":"responsibilities","text":"Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics."},{"passage_id":"p21","section":"responsibilities","text":"Partner with businesses leaders to support the transformation journey of Marketing Excellence."},{"passage_id":"p22","section":"responsibilities","text":"Serve as a trusted advisor and business partner to commercial leadership in the field of marketing."},{"passage_id":"p23","section":"responsibilities","text":"Serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions."},{"passage_id":"p24","section":"responsibilities","text":"Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT."},{"passage_id":"p25","section":"responsibilities","text":"Develop co-created solutions with senior marketing leaders on key priorities."},{"passage_id":"p26","section":"responsibilities","text":"Drive implementation, with and through COE LT leaders, on key initiatives."},{"passage_id":"p27","section":"responsibilities","text":"Create and manage ongoing COE LT agenda."},{"passage_id":"p28","section":"responsibilities","text":"Ensure active tracking, monitoring, adjustments and actions on key initiatives."},{"passage_id":"p30","section":"responsibilities","text":"Drive change management and enable implementation with HR, including training, communication, and tool deployment."},{"passage_id":"p32","section":"responsibilities","text":"Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed."},{"passage_id":"p33","section":"responsibilities","text":"Oversee central COE staff to support COE LT activities."},{"passage_id":"p34","section":"responsibilities","text":"Provide support analysis."},{"passage_id":"p35","section":"responsibilities","text":"Conduct direct training, communication, coaching, and change management."},{"passage_id":"p36","section":"responsibilities","text":"Support special projects where necessary."},{"passage_id":"p37","section":"responsibilities","text":"Consistently identify and evaluate external best practices in the marketing space."},{"passage_id":"p38","section":"responsibilities","text":"Share best practices globally."},{"passage_id":"p39","section":"responsibilities","text":"Proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts."},{"passage_id":"p40","section":"responsibilities","text":"Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection."},{"passage_id":"p41","section":"responsibilities","text":"Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results."},{"passage_id":"p42","section":"responsibilities","text":"Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs."},{"passage_id":"p43","section":"responsibilities","text":"Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews."},{"passage_id":"p44","section":"responsibilities","text":"Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement."},{"passage_id":"p45","section":"responsibilities","text":"Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact."},{"passage_id":"p46","section":"responsibilities","text":"Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement."},{"passage_id":"p47","section":"responsibilities","text":"Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps."},{"passage_id":"p48","section":"responsibilities","text":"Develop and implement plans to close gaps."},{"passage_id":"p49","section":"responsibilities","text":"Serve as an expert coach in marketing processes."},{"passage_id":"p50","section":"responsibilities","text":"Conduct leader and train the trainer coaching."},{"passage_id":"p51","section":"responsibilities","text":"Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders."},{"passage_id":"p52","section":"responsibilities","text":"Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards."},{"passage_id":"p53","section":"required_qualifications","text":"Bachelors, from an accredited college or university is required."},{"passage_id":"p56","section":"required_qualifications","text":"Minimum 10 years of commercial experience."},{"passage_id":"p56","section":"required_qualifications","text":"Minimum 5 years marketing experience required."},{"passage_id":"p57","section":"required_qualifications","text":"Experience developing and executing Commercial Excellence Capabilities with cross business team members."},{"passage_id":"p58","section":"required_qualifications","text":"Demonstrated experience and success leading teams and influencing without authority."},{"passage_id":"p54","section":"preferred_qualifications","text":"Masters or MBA preferred."},{"passage_id":"p59","section":"preferred_qualifications","text":"US-based location preferred."},{"passage_id":"p60","section":"benefits","text":"Compensation & Incentives: Base pay plus performance-based incentive opportunities."},{"passage_id":"p63","section":"benefits","text":"Health & Wellness: Comprehensive medical, prescription-drug, and dental coverage, with a Health Savings Account option."},{"passage_id":"p64","section":"benefits","text":"Health & Wellness: Robust menu of voluntary benefits including vision, optional life, and critical-illness protection."},{"passage_id":"p65","section":"benefits","text":"Health & Wellness: Holistic wellness support including financial-planning tools, family-building assistance, parental leave, and confidential Employee Assistance Program counseling."},{"passage_id":"p66","section":"benefits","text":"Retirement & Financial Strategies: 401(k) with a company match and an additional annual retirement contribution from Eastman."},{"passage_id":"p67","section":"benefits","text":"Time Away: Eleven paid holidays, one personal day, paid time off, and paid vacation."},{"passage_id":"p68","section":"benefits","text":"Growth & Development: Access to mentorship, learning resources, and leadership programs."},{"passage_id":"p85","section":"application_details","text":"Eastman will not ask for fees, payments or credit card information as part of its recruiting and hiring process."},{"passage_id":"p86","section":"application_details","text":"If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com."}],"ignored_ids":["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p11","p12","p13","p14","p29","p31","p37","p38","p39","p40","p41","p42","p43","p44","p45","p46","p47","p48","p49","p50","p51","p52","p55","p61","p62","p69","p70","p71","p72","p73","p74","p75","p76","p77","p78","p79","p80","p81","p82","p83","p84"]}
``````

## Scope and limits

The source postings and translations above are the exact inputs of the capture replay. The initial run used the same four translated passage sets and prompt construction, but its raw model message text was not retained. This replay therefore provides full inspectable output without claiming byte-for-byte identity with the initial responses. Translation quality and model classification need separate validation before publication.

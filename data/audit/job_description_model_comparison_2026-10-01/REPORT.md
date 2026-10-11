# Runr job description model comparison: complete source and output record

Date: 2026-10-01. This report records the four published posting versions used in the English-only model comparison. It contains the full preserved description available to the test, the offline English translation, the exact rendered prompt, and the complete model text from a capture replay. No generated description was published to Runr.

## How to read this record

- **Original run**: the first English-only comparison, summarized in [`initial_run_results.json`](initial_run_results.json). That run saved parsed items and checks but not full raw responses.
- **Capture replay**: the twenty subsequent calls using the same prompt and request settings, with full response text and token usage saved in [`responses/`](responses/). Model output may differ between calls despite `temperature: 0`. The readable sections below use the capture replay.
- German postings were translated locally with Argos Translate 1.11.0 and the German→English package version 1.3. English postings were passed through unchanged. Passage IDs map translated text back to the original source passage. Translation was not charged by an API.
- `response_format` was `json_object`, `provider.require_parameters` was `true`, `temperature` was `0`, and `max_tokens` was `5500`. GPT-OSS used `reasoning.effort: low`; Ling used `reasoning.effort: none`.
- This is a four-posting sample. These outputs are evidence for comparison, not a catalog-wide accuracy guarantee.
- [`REPORT_full_capture.md`](REPORT_full_capture.md) preserves the previous report exactly, including its verbatim response blocks.

## Posting index

These are four real jobs chosen as test examples. The IDs in the first column are names I assigned to the examples; they are not labels shown to Runr users. The version is Runr's saved posting version, and **Original ad** opens the source listing. The saved original text remains available in each section below even if a source listing changes or disappears.

- `german_typical`: shorter German trade job.
- `english_typical`: English IT job with distinct qualifications and benefits.
- `german`: long controlling job containing both German and English text.
- `preferred`: English marketing job that explicitly says a master's degree or MBA is preferred.

| Test ID | Job title | Runr posting version | Original ad |
|---|---|---|---|
| `german_typical` | Karosserie- und Fahrzeugbaumechaniker (m/w/d) | `posting_version_14e4a7d95f3041e1ae57985c0ecfe126` | [original ad](https://linkedin.com/jobs/view/4403743865) |
| `english_typical` | IT Governance Manager (m/f/d) | `posting_version_80b0cec022bb46a29e8687d926cae279` | [original ad](https://linkedin.com/jobs/view/4458080709) |
| `german` | Head of Controlling / FP&A (m/w/d) | `posting_version_79adb669147643e8b899839519645404` | [original ad](https://linkedin.com/jobs/view/4453643322) |
| `preferred` | Marketing COE Lead | `posting_version_b737755a330344bf899ef021439087e4` | [original ad](https://jobs.eastman.com/job/Kingsport-Marketing-COE-Lead-TN-37660/1377487500) |

## Original-run and replay outcome overview

This table records **two separate calls** for each job and model. The first run supplied the format check; the later replay supplied the response status and cost. It is a processing log, not a model quality score.

- **First run format check — pass:** the JSON had the requested shape and accounted for every numbered passage. It does **not** mean the facts, translation, or Required/Preferred labels were correct.
- **First run format check — fail:** the response had an invalid shape or left passage IDs unaccounted for, marked an ID both used and ignored, or could not be parsed. Useful job text may still be present.
- **Second run status — `stop`:** the model finished normally. **`length`:** it reached the output limit and may be incomplete.
- **Second run JSON — “JSON parsed”:** the response was readable as JSON. This says nothing about its factual accuracy.
- **Cost:** the charge for that one replay call in US dollars.

| Test ID | Model | First run format check | Second run status | Second run cost (USD) | Second run JSON |
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

## How to interpret Mistral's results

Your reading is fair: much of Mistral's output is useful. Calling the model simply “failed” overstated what this table measured.

- In the **first run**, Mistral passed the format check for `german_typical` and `english_typical`. It failed that check for `german` because four passage IDs were unaccounted for and eleven were both used and marked ignored. It failed for `preferred` because two passage IDs were unaccounted for. Those are bookkeeping failures, not proof that every generated sentence is wrong.
- In the **captured replay**, Mistral correctly separated the Marketing COE Lead's required bachelor's degree from its preferred master's degree or MBA. Its JSON is useful to read and compare with the source.
- A substantive error remains in the vehicle mechanic example: the employer introduces several qualifications with “Darüber hinaus wünschen wir uns” (“In addition, we would like”), but the replay places training, experience, driving licence, and German skills under **Required**. The report keeps the employer text beside that output so you can judge it directly.
- In the IT Governance Manager example, Mistral returned no benefits even though the posting contains an offer section. This is an omission, not a JSON-format failure.

The distinction is **valid format**, **useful writing**, and **correct coverage/classification**. The table only tests the first. The complete responses below let you assess the other two.

## german_typical: Karosserie- und Fahrzeugbaumechaniker (m/w/d)

- Canonical job ID: `canonical_job_0002249a82eb4ea0b03cb779bef5f410`
- Posting version: `posting_version_14e4a7d95f3041e1ae57985c0ecfe126`
- Source URL: https://linkedin.com/jobs/view/4403743865
- Translation runtime on the local Windows machine: 16.02 seconds

[Original text](german_typical__original.txt) · [English passages](german_typical__english.txt) · [Exact prompt](prompts/german_typical.txt)

<details>
<summary>Original preserved job posting</summary>

<p>Die IRS Group 🚗 Werde Teil der IRS Group – Deutschlands Experten für Karosserie &amp; Lack! Mit über 60 Standorten bundesweit und rund 1.800 Kolleg:innen sorgen wir täglich für glänzende Ergebnisse in der Unfallinstandsetzung, Autolackierung &amp; Fahrzeugaufbereitung. Der Standort ist ein Vorreiter in Sachen Qualität. Der moderne und professionelle Betrieb ist sowohl Partnerwerkstatt von Versicherungen und Schadensteuerern als auch Partner seiner privaten Kunden. Seit über 80 Jahren werden hier Service, Qualität, Freundlichkeit und pünktliche Lieferung großgeschrieben. 💪Aufgrund unseres weiteren stabilen Wachstums suchen wir Dich als Karosserie- und Fahrzeugbaumechaniker (m/w/d) bei IRS Meyer in Ronnenberg bei Hannover. Was wir Dir bieten 🌟 Ein starkes Team &amp; familiäres Betriebsklima Umfassende Einarbeitung &amp; langfristige Arbeitsplatzsicherheit Entwicklungsmöglichkeiten in einem starken Handwerkskonzern Hochmoderne Arbeitsmittel &amp; hochwertige Arbeitskleidung Faires Gehalt 1.000 € Empfehlungsbonus für neue Kolleg:innen durch Dich Corporate Benefits – bis zu 50 % Rabatt bei über 1.500 Marken Deine Aufgaben 💼 Hier kannst Du in allen Bereichen Deiner Kunst zeigen, was in Dir steckt: Feststellen und Einschätzen von Beschädigungen und Mängeln an Karosserien sowie Anbauteilen Beurteilung des Schadens und Anwendung des geeigneten Reparaturverfahrens Ausbeultechniken, Schweißungen, Richtbankarbeit und passgenaues Fügen bilden den Kern der Arbeit Du traust Dir auch Aluminium- und Kunststoffinstandsetzungen zu Die Montage und Demontage von Anbauteilen, Reifen und Scheiben sowie die elektronische Fahrzeugvermessung runden Dein Tätigkeitsfeld ab Dein Profil ⭐ Du bringst Leidenschaft, Herzblut und Freude am Handwerk bei der Behebung von Schäden an Fahrzeugen mit. Darüber hinaus wünschen wir uns: Eine abgeschlossene Ausbildung als Karosserie- und Fahrzeugbaumechaniker (m/w/d) oder als Kfz-Mechaniker/ Mechatroniker (m/w/d) mit Berufserfahrung im Bereich "Karosseriebau/ Unfallinstandsetzung" Du besitzt den Führerschein Klasse B (3) und gute Deutschkenntnisse Du arbeitest gewissenhaft, zuverlässig und handelst dabei immer serviceorientiert Bewirb Dich jetzt 🚀 Interessiert? Dann freuen wir uns auf Deine Bewerbung! 📧 Einfach über den Button "Online bewerben" 📱 oder in nur 2 Minuten per WhatsApp. 👉 Werde Teil unseres Teams – wir freuen uns auf Dich! IRS Schadenszentrum IRS Meyer In der Beschen 4 30952 Ronnenberg Dein Kontakt vor Ort: Stephan Salzer Telefon +49 151 1199 1710</p>

</details>

<details>
<summary>English text supplied to models</summary>

<p><strong>p1</strong> The IRS Group 🚗 Become part of the IRS Group – Germany’s experts in body &amp; paint!</p>
<p><strong>p2</strong> With more than 60 locations nationwide and around 1,800 colleagues, we ensure brilliant results in the repair of accidents, car painting and vehicle processing every day.</p>
<p><strong>p3</strong> The location is a pioneer in terms of quality.</p>
<p><strong>p4</strong> The modern and professional company is both a partner workshop of insurance companies and property controllers as well as a partner of its private customers.</p>
<p><strong>p5</strong> For more than 80 years, service, quality, friendliness and punctual delivery have been a priority here.</p>
<p><strong>p6</strong> Due to our continued stable growth, we are looking for you as body and vehicle construction mechanic (m/f/d) at IRS Meyer in Ronnenberg near Hanover.</p>
<p><strong>p7</strong> What we offer you adresse A strong team &amp; family working atmosphere Comprehensive training &amp; long-term job security Development opportunities in a strong crafts group High-modern work equipment &amp; high-quality workwear Fair salary 1,000 € recommendation bonus for new colleagues: women through you Corporate Benefits – up to 50% discount on over 1,500 brands Your tasks 💼 Here you can show what is inside you in all areas of your art: Determination and assessment of damages and defects on bodies as well as add-on parts Assessment of the damage and application of the appropriate repair process buckling techniques, welds, bench work and fitting form the core of the work You trust The assembly and disassembly of add-on parts, tires and panes as well as the electronic vehicle measurement round off your field of activity your profile ⭐ You bring passion, passion and pleasure in the craft when repairing damage to vehicles.</p>
<p><strong>p8</strong> In addition, we would like to: Complete training as body and vehicle construction mechanic (m/f/d) or as automotive mechanic/mechatronics technician (m/f/d) with professional experience in the field of "bodywork / accident repair" You have the driving license class B (3) and good knowledge of German You work conscientiously, reliably and always act service-oriented Apply now 🚀 Interested?</p>
<p><strong>p9</strong> We look forward to your application!</p>
<p><strong>p10</strong> 📧 Simply use the "Apply online" button or in just 2 minutes via WhatsApp.</p>
<p><strong>p11</strong> 👉 Become part of our team – we look forward to seeing you!</p>
<p><strong>p12</strong> IRS claims center IRS Meyer In the Beschen 4 30952 Ronnenberg your contact on site: Stephan Salzer telephone +49 151 1199 1710</p>

</details>

<details>
<summary>Exact rendered prompt</summary>

<p>Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "The IRS Group 🚗 Become part of the IRS Group – Germany’s experts in body &amp; paint!"}, {"id": "p2", "text": "With more than 60 locations nationwide and around 1,800 colleagues, we ensure brilliant results in the repair of accidents, car painting and vehicle processing every day."}, {"id": "p3", "text": "The location is a pioneer in terms of quality."}, {"id": "p4", "text": "The modern and professional company is both a partner workshop of insurance companies and property controllers as well as a partner of its private customers."}, {"id": "p5", "text": "For more than 80 years, service, quality, friendliness and punctual delivery have been a priority here."}, {"id": "p6", "text": "Due to our continued stable growth, we are looking for you as body and vehicle construction mechanic (m/f/d) at IRS Meyer in Ronnenberg near Hanover."}, {"id": "p7", "text": "What we offer you adresse A strong team &amp; family working atmosphere Comprehensive training &amp; long-term job security Development opportunities in a strong crafts group High-modern work equipment &amp; high-quality workwear Fair salary 1,000 € recommendation bonus for new colleagues: women through you Corporate Benefits – up to 50% discount on over 1,500 brands Your tasks 💼 Here you can show what is inside you in all areas of your art: Determination and assessment of damages and defects on bodies as well as add-on parts Assessment of the damage and application of the appropriate repair process buckling techniques, welds, bench work and fitting form the core of the work You trust The assembly and disassembly of add-on parts, tires and panes as well as the electronic vehicle measurement round off your field of activity your profile ⭐ You bring passion, passion and pleasure in the craft when repairing damage to vehicles."}, {"id": "p8", "text": "In addition, we would like to: Complete training as body and vehicle construction mechanic (m/f/d) or as automotive mechanic/mechatronics technician (m/f/d) with professional experience in the field of \"bodywork / accident repair\" You have the driving license class B (3) and good knowledge of German You work conscientiously, reliably and always act service-oriented Apply now 🚀 Interested?"}, {"id": "p9", "text": "We look forward to your application!"}, {"id": "p10", "text": "📧 Simply use the \"Apply online\" button or in just 2 minutes via WhatsApp."}, {"id": "p11", "text": "👉 Become part of our team – we look forward to seeing you!"}, {"id": "p12", "text": "IRS claims center IRS Meyer In the Beschen 4 30952 Ronnenberg your contact on site: Stephan Salzer telephone +49 151 1199 1710"}]}</p>

</details>

### Model output: mistralai/mistral-nemo

[Exact raw response and usage](responses/german_typical__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 36.83 seconds; input tokens: 942; output tokens: 582; billed cost: $3.4416e-05.

<details>
<summary>Read Model output: mistralai/mistral-nemo</summary>

<p><strong>Overview:</strong> Join IRS Group as a Body and Vehicle Construction Mechanic in Ronnenberg near Hanover.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Assess damages and defects on vehicle bodies and add-on parts. Apply appropriate repair processes, including buckling techniques, welds, bench work, and fitting. Assemble and disassemble add-on parts, tires, and panes. Perform electronic vehicle measurements.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p7</strong> Passion and pleasure in vehicle repair craft.</li>
<li><strong>p8</strong> Completed training as a Body and Vehicle Construction Mechanic or Automotive Mechanic/Mechatronics Technician.</li>
<li><strong>p8</strong> Professional experience in 'bodywork / accident repair'.</li>
<li><strong>p8</strong> Driving license class B (3).</li>
<li><strong>p8</strong> Good knowledge of German.</li>
<li><strong>p8</strong> Conscientious, reliable, and service-oriented work.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p7</strong> Experience in the field of vehicle construction.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p7</strong> Strong team and family working atmosphere. Comprehensive training and long-term job security. Development opportunities in a strong crafts group. High-modern work equipment and high-quality workwear. Fair salary. 1,000 € recommendation bonus for new colleagues: women through you. Corporate Benefits – up to 50% discount on over 1,500 brands.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p10</strong> Apply online or via WhatsApp in just 2 minutes.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p9", "p11", "p12"]</p>

</details>

### Model output: openai/gpt-oss-20b

[Exact raw response and usage](responses/german_typical__openai_gpt-oss-20b.json)
- Finish reason: `stop`; elapsed: 9.98 seconds; input tokens: 1008; output tokens: 522; billed cost: $6.5124e-05.

<details>
<summary>Read Model output: openai/gpt-oss-20b</summary>

<p><strong>Overview:</strong> Body and vehicle construction mechanic needed at IRS Meyer in Ronnenberg.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Assess damages, perform repair processes, assemble/disassemble add‑on parts, and conduct electronic vehicle measurements.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p8</strong> Complete training as body and vehicle construction mechanic or automotive mechanic/mechatronics technician with professional experience in bodywork/accident repair.</li>
<li><strong>p8</strong> Driving licence class B (3) and good knowledge of German.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p7</strong> Strong team atmosphere, comprehensive training, long‑term job security, development opportunities, high‑modern equipment, fair salary, 1,000 € recommendation bonus for new female colleagues, up to 50% discount on 1,500+ brands.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p10</strong> Apply online or via WhatsApp in just 2 minutes.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p9", "p11", "p12"]</p>

</details>

### Model output: inclusionai/ling-3.0-flash-vl-20260910

[Exact raw response and usage](responses/german_typical__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 8.52 seconds; input tokens: 939; output tokens: 565; billed cost: $0.000145752.

<details>
<summary>Read Model output: inclusionai/ling-3.0-flash-vl-20260910</summary>

<p><strong>Overview:</strong> IRS Group is hiring a body and vehicle construction mechanic at IRS Meyer in Ronnenberg near Hanover.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p6</strong> IRS Meyer in Ronnenberg near Hanover is hiring a body and vehicle construction mechanic (m/f/d).</li>
<li><strong>p7</strong> Determine and assess damages and defects on bodies and add-on parts.</li>
<li><strong>p7</strong> Assess damage and apply the appropriate repair process; buckling techniques, welds, bench work and fitting form the core of the work.</li>
<li><strong>p7</strong> Assemble and disassemble add-on parts, tires and panes.</li>
<li><strong>p7</strong> Perform electronic vehicle measurement.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p8</strong> Driving license class B (3).</li>
<li><strong>p8</strong> Good knowledge of German.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p8</strong> Complete training as body and vehicle construction mechanic (m/f/d) or as automotive mechanic/mechatronics technician (m/f/d) with professional experience in bodywork/accident repair.</li>
<li><strong>p8</strong> Work conscientiously, reliably and always act service-oriented.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p7</strong> Strong team and family working atmosphere.</li>
<li><strong>p7</strong> Comprehensive training and long-term job security.</li>
<li><strong>p7</strong> Development opportunities in a strong crafts group.</li>
<li><strong>p7</strong> High-modern work equipment and high-quality workwear.</li>
<li><strong>p7</strong> Fair salary.</li>
<li><strong>p7</strong> 1,000 € recommendation bonus for new colleagues introduced by women.</li>
<li><strong>p7</strong> Corporate Benefits with up to 50% discount on over 1,500 brands.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p10</strong> Apply online or via WhatsApp in just 2 minutes.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p9", "p11", "p12"]</p>

</details>

### Model output: openai/gpt-oss-120b

[Exact raw response and usage](responses/german_typical__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 8.7 seconds; input tokens: 954; output tokens: 263; billed cost: $7.333e-05.

<details>
<summary>Read Model output: openai/gpt-oss-120b</summary>

<p><strong>Overview:</strong> Body and vehicle construction mechanic position at IRS Meyer in Ronnenberg.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p6</strong> Perform body and vehicle construction tasks at IRS Meyer.</li>
<li><strong>p7</strong> Assess damage and determine appropriate repair processes.</li>
<li><strong>p7</strong> Execute buckling, welding, bench work, and fitting.</li>
</ul>
<p><strong>Other items:</strong> [{"passur... (truncated) ...": [{}]}]</p>

</details>

### Model output: google/gemini-2.5-flash-lite

[Exact raw response and usage](responses/german_typical__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 2.33 seconds; input tokens: 910; output tokens: 611; billed cost: $0.0003354.

<details>
<summary>Read Model output: google/gemini-2.5-flash-lite</summary>

<p><strong>Overview:</strong> The IRS Group is seeking a skilled Body and Vehicle Construction Mechanic (m/f/d) for their IRS Meyer location in Ronnenberg near Hanover, offering a strong team environment, comprehensive training, and development opportunities.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Determine and assess damages and defects on bodies and add-on parts.</li>
<li><strong>p7</strong> Assess damage and apply appropriate repair processes, including buckling techniques, welding, bench work, and fitting.</li>
<li><strong>p7</strong> Assemble and disassemble add-on parts, tires, and panes.</li>
<li><strong>p7</strong> Perform electronic vehicle measurements.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p8</strong> Completed training as a body and vehicle construction mechanic (m/f/d) or as an automotive mechanic/mechatronics technician (m/f/d) with professional experience in "bodywork / accident repair".</li>
<li><strong>p8</strong> Possess driving license class B (3).</li>
<li><strong>p8</strong> Have good knowledge of German.</li>
<li><strong>p7</strong> Demonstrate passion, dedication, and enjoyment in repairing vehicle damage.</li>
<li><strong>p8</strong> Work conscientiously, reliably, and in a service-oriented manner.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p7</strong> A strong team and family working atmosphere.</li>
<li><strong>p7</strong> Comprehensive training and long-term job security.</li>
<li><strong>p7</strong> Development opportunities within a strong crafts group.</li>
<li><strong>p7</strong> Modern work equipment and high-quality workwear.</li>
<li><strong>p7</strong> Fair salary.</li>
<li><strong>p7</strong> 1,000 € recommendation bonus for new colleagues.</li>
<li><strong>p7</strong> Corporate Benefits offering up to 50% discount on over 1,500 brands.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p10</strong> Apply online via the "Apply online" button or via WhatsApp in 2 minutes.</li>
<li><strong>p12</strong> Contact person on site: Stephan Salzer, telephone +49 151 1199 1710.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p9", "p11"]</p>

</details>

## english_typical: IT Governance Manager (m/f/d)

- Canonical job ID: `canonical_job_009b66b298c84a3a9df6273a04c510d1`
- Posting version: `posting_version_80b0cec022bb46a29e8687d926cae279`
- Source URL: https://linkedin.com/jobs/view/4458080709
- Translation runtime on the local Windows machine: 0.0 seconds

[Original text](english_typical__original.txt) · [English passages](english_typical__english.txt) · [Exact prompt](prompts/english_typical.txt)

<details>
<summary>Original preserved job posting</summary>

<p>Role Purpose Founded in 1921, OLDENDORFF CARRIERS combines its history as a German shipowner with the network of one of the world's leading drybulk operators. We currently control some 750 chartered and owned vessels of 67 mio tdw, and we carry around 330 mio tons of raw materials and semi-finished products across the seven seas each year. Our customers can expect 100% performance. All the way. As part of our ongoing journey towards a modern and innovative Technology organization, we are looking to further strengthen our IT Governance Team. We are searching for an IT Governance Manager who will play an integral part in shaping Oldendorff’s digital future. Job Responsibilities: Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels, ensuring traceable conformity with legal and regulatory requirements, internal policies, contractual obligations, audit expectations, and recognized good-practice frameworks. Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services. Strengthening governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT (operational technology) interfaces, and integrated maritime applications, and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards. Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting. Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments to ensure clear ownership, accountability, and traceability, and drive audit readiness by managing findings, supporting root-cause analysis, defining sustainable remediation actions, and tracking implementation. Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations. Establish and maintain quality and process management principles for IT governance, ensuring that processes are practical, measurable, and scalable for a decentralized global organization. Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency. What You Bring Along University degree in computer science, information systems, business administration, or a comparable IT-focused qualification. Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline. Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation. Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting. Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, and comfortable collaborating across cultures, time zones, functions, and levels of seniority. A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs. A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism. Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities. Fluency in written and spoken English. Nice-to-have Experience with IT strategy, organizational development, internal control systems, audit management, or risk management. Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments. German language skills. What we offer A collaborative, international working environment with flat hierarchies. Fast decision-making and a strong culture of ownership. Plenty of room for initiative, new ideas, and personal growth.</p>

</details>

<details>
<summary>English text supplied to models</summary>

<p><strong>p1</strong> Role Purpose Founded in 1921, OLDENDORFF CARRIERS combines its history as a German shipowner with the network of one of the world's leading drybulk operators.</p>
<p><strong>p2</strong> We currently control some 750 chartered and owned vessels of 67 mio tdw, and we carry around 330 mio tons of raw materials and semi-finished products across the seven seas each year.</p>
<p><strong>p3</strong> Our customers can expect 100% performance.</p>
<p><strong>p4</strong> All the way.</p>
<p><strong>p5</strong> As part of our ongoing journey towards a modern and innovative Technology organization, we are looking to further strengthen our IT Governance Team.</p>
<p><strong>p6</strong> We are searching for an IT Governance Manager who will play an integral part in shaping Oldendorff’s digital future.</p>
<p><strong>p7</strong> Job Responsibilities: Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels, ensuring traceable conformity with legal and regulatory requirements, internal policies, contractual obligations, audit expectations, and recognized good-practice frameworks.</p>
<p><strong>p8</strong> Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services.</p>
<p><strong>p9</strong> Strengthening governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT (operational technology) interfaces, and integrated maritime applications, and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards.</p>
<p><strong>p10</strong> Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting.</p>
<p><strong>p11</strong> Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments to ensure clear ownership, accountability, and traceability, and drive audit readiness by managing findings, supporting root-cause analysis, defining sustainable remediation actions, and tracking implementation.</p>
<p><strong>p12</strong> Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations.</p>
<p><strong>p13</strong> Establish and maintain quality and process management principles for IT governance, ensuring that processes are practical, measurable, and scalable for a decentralized global organization.</p>
<p><strong>p14</strong> Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency.</p>
<p><strong>p15</strong> What You Bring Along University degree in computer science, information systems, business administration, or a comparable IT-focused qualification.</p>
<p><strong>p16</strong> Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline.</p>
<p><strong>p17</strong> Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation.</p>
<p><strong>p18</strong> Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting.</p>
<p><strong>p19</strong> Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, and comfortable collaborating across cultures, time zones, functions, and levels of seniority.</p>
<p><strong>p20</strong> A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs.</p>
<p><strong>p21</strong> A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism.</p>
<p><strong>p22</strong> Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities.</p>
<p><strong>p23</strong> Fluency in written and spoken English.</p>
<p><strong>p24</strong> Nice-to-have Experience with IT strategy, organizational development, internal control systems, audit management, or risk management.</p>
<p><strong>p25</strong> Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments.</p>
<p><strong>p26</strong> German language skills.</p>
<p><strong>p27</strong> What we offer A collaborative, international working environment with flat hierarchies.</p>
<p><strong>p28</strong> Fast decision-making and a strong culture of ownership.</p>
<p><strong>p29</strong> Plenty of room for initiative, new ideas, and personal growth.</p>

</details>

<details>
<summary>Exact rendered prompt</summary>

<p>Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "Role Purpose Founded in 1921, OLDENDORFF CARRIERS combines its history as a German shipowner with the network of one of the world's leading drybulk operators."}, {"id": "p2", "text": "We currently control some 750 chartered and owned vessels of 67 mio tdw, and we carry around 330 mio tons of raw materials and semi-finished products across the seven seas each year."}, {"id": "p3", "text": "Our customers can expect 100% performance."}, {"id": "p4", "text": "All the way."}, {"id": "p5", "text": "As part of our ongoing journey towards a modern and innovative Technology organization, we are looking to further strengthen our IT Governance Team."}, {"id": "p6", "text": "We are searching for an IT Governance Manager who will play an integral part in shaping Oldendorff’s digital future."}, {"id": "p7", "text": "Job Responsibilities: Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels, ensuring traceable conformity with legal and regulatory requirements, internal policies, contractual obligations, audit expectations, and recognized good-practice frameworks."}, {"id": "p8", "text": "Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services."}, {"id": "p9", "text": "Strengthening governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT (operational technology) interfaces, and integrated maritime applications, and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards."}, {"id": "p10", "text": "Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting."}, {"id": "p11", "text": "Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments to ensure clear ownership, accountability, and traceability, and drive audit readiness by managing findings, supporting root-cause analysis, defining sustainable remediation actions, and tracking implementation."}, {"id": "p12", "text": "Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations."}, {"id": "p13", "text": "Establish and maintain quality and process management principles for IT governance, ensuring that processes are practical, measurable, and scalable for a decentralized global organization."}, {"id": "p14", "text": "Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency."}, {"id": "p15", "text": "What You Bring Along University degree in computer science, information systems, business administration, or a comparable IT-focused qualification."}, {"id": "p16", "text": "Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline."}, {"id": "p17", "text": "Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation."}, {"id": "p18", "text": "Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting."}, {"id": "p19", "text": "Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, and comfortable collaborating across cultures, time zones, functions, and levels of seniority."}, {"id": "p20", "text": "A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs."}, {"id": "p21", "text": "A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism."}, {"id": "p22", "text": "Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities."}, {"id": "p23", "text": "Fluency in written and spoken English."}, {"id": "p24", "text": "Nice-to-have Experience with IT strategy, organizational development, internal control systems, audit management, or risk management."}, {"id": "p25", "text": "Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments."}, {"id": "p26", "text": "German language skills."}, {"id": "p27", "text": "What we offer A collaborative, international working environment with flat hierarchies."}, {"id": "p28", "text": "Fast decision-making and a strong culture of ownership."}, {"id": "p29", "text": "Plenty of room for initiative, new ideas, and personal growth."}]}</p>

</details>

### Model output: mistralai/mistral-nemo

[Exact raw response and usage](responses/english_typical__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 111.59 seconds; input tokens: 1427; output tokens: 1104; billed cost: $5.8806e-05.

<details>
<summary>Read Model output: mistralai/mistral-nemo</summary>

<p><strong>Overview:</strong> Oldendorff Carriers seeks an IT Governance Manager to shape their digital future.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Further develop, maintain, and monitor a fit-for-purpose IT governance framework aligned with business strategy, regulatory expectations, cyber resilience requirements, and operational realities across shore-based offices and vessels.</li>
<li><strong>p8</strong> Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services.</li>
<li><strong>p9</strong> Strengthen governance over digital transformation initiatives, including cloud services, data platforms, automation, AI, vessel connectivity, OT interfaces, and integrated maritime applications.</li>
<li><strong>p10</strong> Develop and operate the internal IT control system, covering policy and guideline management, control design, control performance monitoring, evidence collection, remediation tracking, and management reporting.</li>
<li><strong>p11</strong> Coordinate IT risk, compliance, and control activities with relevant departments to ensure clear ownership, accountability, and traceability.</li>
<li><strong>p12</strong> Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations.</li>
<li><strong>p13</strong> Establish and maintain quality and process management principles for IT governance, ensuring processes are practical, measurable, and scalable for a decentralized global organization.</li>
<li><strong>p14</strong> Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p15</strong> University degree in computer science, information systems, business administration, or a comparable IT-focused qualification.</li>
<li><strong>p16</strong> Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline.</li>
<li><strong>p17</strong> Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation.</li>
<li><strong>p18</strong> Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting.</li>
<li><strong>p19</strong> Confident communicator able to explain governance requirements clearly to various stakeholders.</li>
<li><strong>p20</strong> A structured, analytical, and solution-oriented working style.</li>
<li><strong>p21</strong> A proactive team player able to work independently and drive topics forward.</li>
<li><strong>p22</strong> Willingness to occasionally travel internationally or visit vessels.</li>
<li><strong>p23</strong> Fluency in written and spoken English.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p24</strong> Experience with IT strategy, organizational development, internal control systems, audit management, or risk management.</li>
<li><strong>p25</strong> Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments.</li>
<li><strong>p26</strong> German language skills.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p27", "p28", "p29"]</p>

</details>

### Model output: openai/gpt-oss-20b

[Exact raw response and usage](responses/english_typical__openai_gpt-oss-20b.json)
- Finish reason: `stop`; elapsed: 16.67 seconds; input tokens: 1489; output tokens: 819; billed cost: $0.000100512.

<details>
<summary>Read Model output: openai/gpt-oss-20b</summary>

<p><strong>Overview:</strong> IT Governance Manager to shape Oldendorff’s digital future</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Develop, maintain, and monitor a fit‑for‑purpose IT governance framework aligned with business strategy and regulatory expectations</li>
<li><strong>p8</strong> Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements</li>
<li><strong>p9</strong> Strengthen governance over digital transformation initiatives including cloud, data platforms, AI, vessel connectivity, OT interfaces, and maritime applications</li>
<li><strong>p10</strong> Operate the internal IT control system covering policy management, control design, performance monitoring, evidence collection, remediation tracking, and reporting</li>
<li><strong>p11</strong> Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operations to drive audit readiness</li>
<li><strong>p12</strong> Support operational implementation of IT governance through guidance, training, and coaching for IT teams and stakeholders</li>
<li><strong>p13</strong> Establish and maintain quality and process management principles for IT governance in a decentralized global organization</li>
<li><strong>p14</strong> Collaborate with IT departments, fleet stakeholders, and corporate functions to balance compliance, efficiency, innovation, and risk transparency</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p15</strong> University degree in computer science, information systems, business administration, or a comparable IT‑focused qualification</li>
<li><strong>p16</strong> Practical experience in IT governance, controls, compliance, quality management, or process management</li>
<li><strong>p17</strong> Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit‑ready documentation</li>
<li><strong>p18</strong> Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting</li>
<li><strong>p19</strong> Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties</li>
<li><strong>p20</strong> Structured, analytical, and solution‑oriented working style balancing governance with practical business needs</li>
<li><strong>p21</strong> Proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism</li>
<li><strong>p22</strong> Willingness to occasionally travel internationally or visit vessels</li>
<li><strong>p23</strong> Fluency in written and spoken English</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p24</strong> Experience with IT strategy, organizational development, internal control systems, audit management, or risk management</li>
<li><strong>p25</strong> Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments</li>
<li><strong>p26</strong> German language skills</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p27", "p28", "p29"]</p>

</details>

### Model output: inclusionai/ling-3.0-flash-vl-20260910

[Exact raw response and usage](responses/english_typical__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 17.69 seconds; input tokens: 1416; output tokens: 990; billed cost: $0.000250872.

<details>
<summary>Read Model output: inclusionai/ling-3.0-flash-vl-20260910</summary>

<p><strong>Overview:</strong> OLDENDORFF CARRIERS is hiring an IT Governance Manager to strengthen its IT Governance Team in a modern, innovative technology organization.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Further develop, maintain, and monitor an IT governance framework aligned with business strategy, regulatory expectations, cyber resilience, and operational realities across shore-based offices and vessels.</li>
<li><strong>p8</strong> Define, implement, and continuously improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements covering IT processes, organization, people, technology, data, and third-party services.</li>
<li><strong>p9</strong> Strengthen governance over digital transformation initiatives including cloud services, data platforms, automation, AI, vessel connectivity, OT interfaces, and maritime applications, advising on IT operating models, decision rights, and tool governance.</li>
<li><strong>p10</strong> Develop and operate the internal IT control system covering policy management, control design, performance monitoring, evidence collection, remediation tracking, and management reporting.</li>
<li><strong>p11</strong> Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments, driving audit readiness and managing remediation actions.</li>
<li><strong>p12</strong> Support operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders in international locations.</li>
<li><strong>p13</strong> Establish and maintain quality and process management principles for IT governance, ensuring processes are practical, measurable, and scalable for a decentralized global organization.</li>
<li><strong>p14</strong> Collaborate with IT departments, fleet-related stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and residual risk transparency.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p15</strong> University degree in computer science, information systems, business administration, or a comparable IT-focused qualification.</li>
<li><strong>p16</strong> Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline.</li>
<li><strong>p17</strong> Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation.</li>
<li><strong>p18</strong> Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting.</li>
<li><strong>p19</strong> Confident communicator able to explain governance requirements clearly to IT teams, business stakeholders, management, and external parties, comfortable collaborating across cultures, time zones, functions, and seniority levels.</li>
<li><strong>p20</strong> A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs.</li>
<li><strong>p21</strong> A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism.</li>
<li><strong>p22</strong> Willingness to occasionally travel internationally or visit vessels as part of global IT governance activities.</li>
<li><strong>p23</strong> Fluency in written and spoken English.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p24</strong> Experience with IT strategy, organizational development, internal control systems, audit management, or risk management.</li>
<li><strong>p25</strong> Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments.</li>
<li><strong>p26</strong> German language skills.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p27</strong> A collaborative, international working environment with flat hierarchies.</li>
<li><strong>p28</strong> Fast decision-making and a strong culture of ownership.</li>
<li><strong>p29</strong> Plenty of room for initiative, new ideas, and personal growth.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6"]</p>

</details>

### Model output: openai/gpt-oss-120b

[Exact raw response and usage](responses/english_typical__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 70.47 seconds; input tokens: 1435; output tokens: 1112; billed cost: $0.00024321.

<details>
<summary>Read Model output: openai/gpt-oss-120b</summary>

<p><strong>Overview:</strong> IT Governance Manager role at Oldendorff Carriers overseeing governance frameworks and controls.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Develop and monitor an IT governance framework aligned with strategy, regulations, cyber resilience, and operations.</li>
<li><strong>p8</strong> Define, implement and improve IT policies, standards, procedures, control objectives, KPIs and evidence requirements.</li>
<li><strong>p9</strong> Govern digital transformation initiatives such as cloud, data platforms, AI, vessel connectivity and OT interfaces.</li>
<li><strong>p10</strong> Develop and operate the internal IT control system, including policy management, control design and remediation tracking.</li>
<li><strong>p11</strong> Coordinate IT risk, compliance and control activities with security, legal, data protection, finance and operations.</li>
<li><strong>p12</strong> Provide guidance, training and coaching to IT teams and business stakeholders worldwide.</li>
<li><strong>p13</strong> Establish quality and process management principles for scalable IT governance.</li>
<li><strong>p14</strong> Collaborate with IT, fleet and corporate functions to balance compliance, efficiency, innovation and risk transparency.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p15</strong> University degree in computer science, information systems, business administration or comparable IT qualification.</li>
<li><strong>p16</strong> Practical experience in IT governance, controls, compliance, quality or process management.</li>
<li><strong>p17</strong> Good understanding of IT governance principles, policy management, control design and audit documentation.</li>
<li><strong>p18</strong> Ability to translate regulatory, audit and policy requirements into practical processes and reporting.</li>
<li><strong>p19</strong> Confident communicator able to explain governance requirements to diverse stakeholders.</li>
<li><strong>p20</strong> Structured, analytical and solution‑oriented working style.</li>
<li><strong>p21</strong> Proactive team player who can work independently and drive topics forward.</li>
<li><strong>p22</strong> Willingness to travel internationally or visit vessels occasionally.</li>
<li><strong>p23</strong> Fluency in written and spoken English.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p24</strong> Experience with IT strategy, organizational development, internal control systems, audit or risk management.</li>
<li><strong>p25</strong> Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services or maritime IT.</li>
<li><strong>p26</strong> German language skills.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p27</strong> Collaborative international environment with flat hierarchies.</li>
<li><strong>p28</strong> Fast decision‑making and strong culture of ownership.</li>
<li><strong>p29</strong> Plenty of room for initiative, new ideas and personal growth.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> []</p>

</details>

### Model output: google/gemini-2.5-flash-lite

[Exact raw response and usage](responses/english_typical__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 2.77 seconds; input tokens: 1369; output tokens: 959; billed cost: $0.0005205.

<details>
<summary>Read Model output: google/gemini-2.5-flash-lite</summary>

<p><strong>Overview:</strong> OLDENDORFF CARRIERS is seeking an IT Governance Manager to shape its digital future by developing and maintaining an IT governance framework, policies, and controls.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p7</strong> Develop, maintain, and monitor an IT governance framework aligned with business strategy, regulatory expectations, cyber resilience, and operational realities for shore-based offices and vessels.</li>
<li><strong>p8</strong> Define, implement, and improve IT policies, standards, procedures, control objectives, KPIs, and evidence requirements for IT processes, organization, people, technology, data, and third-party services.</li>
<li><strong>p9</strong> Strengthen governance over digital transformation initiatives (cloud, data platforms, AI, vessel connectivity, OT, maritime applications) and advise on IT operating models, decision rights, process ownership, service management, tool governance, and documentation standards.</li>
<li><strong>p10</strong> Develop and operate the internal IT control system, including policy management, control design, performance monitoring, evidence collection, remediation tracking, and management reporting.</li>
<li><strong>p11</strong> Coordinate IT risk, compliance, and control activities with Information Security, Legal, Data Protection, Finance, and operational departments, and manage audit readiness by addressing findings and tracking remediation.</li>
<li><strong>p12</strong> Support the operational implementation of IT governance through guidance, training, and coaching for IT teams and business stakeholders globally.</li>
<li><strong>p13</strong> Establish and maintain quality and process management principles for IT governance, ensuring processes are practical, measurable, and scalable for a decentralized global organization.</li>
<li><strong>p14</strong> Collaborate with IT departments, fleet stakeholders, and corporate functions to balance regulatory compliance, operational efficiency, innovation, and risk transparency.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p15</strong> University degree in computer science, information systems, business administration, or a comparable IT-focused qualification.</li>
<li><strong>p16</strong> Practical experience in IT governance, controls, compliance, quality management, process management, or a related discipline.</li>
<li><strong>p17</strong> Good understanding of IT governance principles, policy management, control design, evidence requirements, and audit-ready documentation.</li>
<li><strong>p18</strong> Ability to translate regulatory, audit, and internal policy requirements into practical processes, controls, guidance, and reporting.</li>
<li><strong>p19</strong> Confident communicator able to explain governance requirements clearly to various stakeholders and collaborate across cultures, time zones, functions, and seniority levels.</li>
<li><strong>p20</strong> A structured, analytical, and solution-oriented working style, balancing governance requirements with practical business needs.</li>
<li><strong>p21</strong> A proactive team player able to work independently, drive topics forward, and follow up on actions with persistence and professionalism.</li>
<li><strong>p22</strong> Willingness to occasionally travel internationally or visit vessels for global IT governance activities.</li>
<li><strong>p23</strong> Fluency in written and spoken English.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p24</strong> Experience with IT strategy, organizational development, internal control systems, audit management, or risk management.</li>
<li><strong>p25</strong> Familiarity with cyber resilience, data protection, supplier governance, AI, cloud services, or maritime IT environments.</li>
<li><strong>p26</strong> German language skills.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p27</strong> A collaborative, international working environment with flat hierarchies.</li>
<li><strong>p28</strong> Fast decision-making and a strong culture of ownership.</li>
<li><strong>p29</strong> Plenty of room for initiative, new ideas, and personal growth.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6"]</p>

</details>

## german: Head of Controlling / FP&A (m/w/d)

- Canonical job ID: `canonical_job_eee793a0d69c4198a72217848eac77b3`
- Posting version: `posting_version_79adb669147643e8b899839519645404`
- Source URL: https://linkedin.com/jobs/view/4453643322
- Translation runtime on the local Windows machine: 84.53 seconds

[Original text](german__original.txt) · [English passages](german__english.txt) · [Exact prompt](prompts/german.txt)

<details>
<summary>Original preserved job posting</summary>

<p>Unsere Mission ist es, mit Innovationskraft und Nachhaltigkeit die industrielle Transformation voranzutreiben. Ob bei der Optimierung von Rechenzentren, der Weiterentwicklung der Wasserstoffproduktion oder der Neugestaltung von Kühl- und Klimatechniksystemen – unsere thermischen Schlüsseltechnologien stärken zahlreiche Branchen weltweit. Als „One Kelvion“ arbeiten wir kontinuierlich an Lösungen, die unsere Kunden noch erfolgreicher machen und gleichzeitig zu einer nachhaltigeren Zukunft beitragen.Wir gestalten Zukunft – gemeinsam Sie sind eine strategisch geprägte Finance-Persönlichkeit mit ausgeprägtem Steuerungsanspruch und möchten die finanzielle Performance eines international tätigen Industrieunternehmens maßgeblich mitgestalten? Bei Kelvion übernehmen Sie eine exponierte Rolle an der Schnittstelle von Unternehmenssteuerung, strategischer Planung und operativer Performance-Verbesserung. In einem zunehmend kapitalmarktorientierten Umfeld leisten Sie einen wesentlichen Beitrag zu Transparenz, Forecast-Qualität, finanzieller Resilienz und nachhaltiger Wertsteigerung für Management, Investoren und weitere Stakeholder. Ihre Aufgaben Gesamtverantwortung für den konzernweiten Budget-, Forecast- und Mittelfristplanungsprozess inklusive Ableitung belastbarer Steering-Impulse für Vorstand, Geschäftsführung und Senior Management Weiterentwicklung einer integrierten Unternehmensplanung über GuV, Bilanz, Cashflow, Liquidität, Opex und Capex hinweg – mit Fokus auf Transparenz, Szenarioplanung und wertorientierte Steuerung Steuerung und Kommentierung der Monats-, Quartals- und Jahresabschlüsse in enger Zusammenarbeit mit Accounting, Treasury und den Business Units sowie Ableitung entscheidungsrelevanter Maßnahmen zur Ergebnisverbesserung Erstellung hochwertiger Management- und Board-Reports sowie adressatengerechter Unterlagen für Gesellschafter, Finanzierungspartner und weitere kapitalmarktnahe Stakeholder Mitwirkung an finanzwirtschaftlich relevanten Themen eines kapitalmarktorientierten Umfelds, insbesondere Performance-Dialogen, Refinanzierungs- und Finanzierungsfragestellungen, Covenant-Monitoring sowie Cash- und Liquiditätssteuerung Sparringspartner für CEO, CFO und Geschäftsleitung bei strategischen Fragestellungen, Investitionsentscheidungen, Portfolio-Priorisierung, Business Cases und Transformationsinitiativen Frühzeitige Identifikation von Chancen, Risiken und Abweichungen sowie Entwicklung von Handlungsoptionen, um Unternehmensziele und finanzielle Zielkorridore abzusichern Weiterentwicklung von Reporting-, Controlling- und Planungsprozessen, einschließlich KPI-Framework, Standardisierung, Automatisierung und Nutzung moderner BI- und EPM-Lösungen Fachliche und disziplinarische Führung sowie gezielte Weiterentwicklung des FP&amp;A-/Controlling-Teams mit dem Anspruch, eine leistungsstarke, analytisch geprägte und businessnahe Steuerungsfunktion weiter auszubauen Enge Zusammenarbeit mit internationalen Funktionen und Regionen, um einheitliche Governance-, Reporting- und Performance-Standards im Konzern sicherzustellen Ihr Profil Erfolgreich abgeschlossenes Studium der Betriebswirtschaftslehre, Wirtschaftswissenschaften, Finance oder eines vergleichbaren Fachgebiets; zusätzliche Qualifikationen wie CFA, CMA, CPA oder Bilanzbuchhalter (IHK) sind von Vorteil Mehrjährige einschlägige Berufserfahrung (typischerweise 8–12 Jahre) in FP&amp;A, Controlling oder Corporate Finance, idealerweise in einem international tätigen, kapitalmarktorientierten oder Private-Equity-geprägten Industrieunternehmen Führungserfahrung von internationalen Teams Fundierte Expertise in integrierter Finanzplanung, Performance Management, Cash- und Liquiditätssteuerung sowie im Aufbau belastbarer Entscheidungsgrundlagen für Top-Management-Gremien Sehr gutes Verständnis für Anforderungen eines kapitalmarktnahen Umfelds, z. B. in Bezug auf Governance, Transparenz, Stakeholder-Kommunikation, Refinanzierung, Covenants und finanzielle Steuerungslogiken Ausgeprägte analytische, konzeptionelle und strategische Fähigkeiten sowie hohe Sicherheit im Umgang mit komplexen Datenmodellen, Business Cases und Szenarioanalysen Überzeugende Kommunikations- und Präsentationsstärke mit der Fähigkeit, komplexe finanzielle Zusammenhänge klar, präzise und adressatengerecht bis auf Executive-Ebene darzustellen Sehr gute Kenntnisse in modernen Finance- und Reporting-Systemen, insbesondere Excel, Power BI, , SAP BW/BI, SAP S/4HANA sowie idealerweise Konsolidierungs- und Planungslösungen idealerweise Tagetik Hohes Maß an Eigeninitiative, Umsetzungsstärke und Veränderungskompetenz sowie die Fähigkeit, in einem anspruchsvollen und internationalen Umfeld nachhaltige Verbesserungen voranzutreiben Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift Was wir bieten Eine Schlüsselposition mit hoher strategischer Relevanz und direkter Sichtbarkeit im Top-Management Die Möglichkeit, die Finance-Organisation und Steuerungsinstrumente eines international aufgestellten Unternehmens aktiv weiterzuentwickeln Ein innovatives, wachstumsorientiertes Umfeld an der Schnittstelle von Industrie, Nachhaltigkeit und Transformation Ein kollaboratives, internationales Arbeitsumfeld im Sinne von „One Kelvion“ mit kurzen Entscheidungswegen und hoher Gestaltungsmöglichkeit Flexible Arbeitsmodelle und ein modernes Arbeitsumfeld, das Zusammenarbeit, Eigenverantwortung und Weiterentwicklung fördert Attraktive Vergütung sowie zusätzliche Benefits entsprechend Funktion und Verantwortung Unser Erfolg basiert auf Zusammenarbeit – wir fördern vielfältiges Denken, hören einander zu und schätzen jede einzelne Stimme. Kreativität entfaltet sich bei Kelvion dort, wo Menschen gehört, ihre Ideen willkommen geheißen und ihre Beiträge anerkannt werden. Mit einem flexiblen Arbeitsansatz stellen wir das Wohlbefinden und die Zufriedenheit unserer Mitarbeitenden in den Mittelpunkt. Dies stärkt die Bereitschaft sich einzubringen und eröffnet damit neue Karrierechancen Wir ermutigen engagierte Persönlichkeiten ihre Entwicklung selbst in die Hand zu nehmen, neue Wege zu gehen und gemeinsam mit uns Zukunft zu gestalten. Wir gestalten Zukunft – gemeinsam Apply now Head of Controlling / FP&amp;A (m/f/d) Are you a strategically minded finance professional with a strong performance management mindset who is eager to play a key role in shaping the financial performance of an internationally operating industrial company? At Kelvion, you will take on a highly visible position at the intersection of corporate performance management, strategic planning, and operational performance improvement. In an increasingly capital market-oriented environment, you will make a significant contribution to transparency, forecast quality, financial resilience, and sustainable value creation for management, investors, and other stakeholders. Your Responsibilities Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management. Further development of an integrated business planning approach across P&amp;L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management. Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance. Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders. Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management. Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives. Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors. Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions. Functional and disciplinary leadership as well as targeted development of the FP&amp;A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organization. Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group. Your Profile Successfully completed degree in Business Administration, Economics, Finance, or a comparable field; additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage. Several years of relevant professional experience (typically 8–12 years) in FP&amp;A, Controlling, or Corporate Finance, ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company. Leadership experience in managing international teams. Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies. Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms. Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses. Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level. Very good knowledge of modern finance and reporting systems, particularly Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik. High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment. Fluent German and English language skills, both written and spoken. What We Offer A key position with high strategic relevance and direct visibility to top management. The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company. An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation. A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact. Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development. Attractive compensation and additional benefits aligned with the scope and responsibility of the role. At Kelvion we thrive on collaboration, embracing diversity of thought, and valuing every voice. Within Kelvion creativity shines because people are listened to, their contributions recognised, and their ideas welcomed. Our flexible approach to the way we work places people’s health and satisfaction as a priority, enhancing engagement and fostering career opportunities. We empower engaged individuals to grow, progress and carve their own paths within the company. Together, We Shape the Future Apply now</p>

</details>

<details>
<summary>English text supplied to models</summary>

<p><strong>p1</strong> Our mission is to drive industrial transformation with innovation and sustainability.</p>
<p><strong>p2</strong> Whether in the optimization of data centers, the further development of hydrogen production or the redesign of cooling and air conditioning systems – our key thermal technologies strengthen numerous industries worldwide.</p>
<p><strong>p3</strong> As “One Kelvion”, we are continuously working on solutions that make our customers even more successful and at the same time contribute to a more sustainable future.We are shaping the future – together you are a strategically shaped finance personality with a pronounced management requirement and want to play a decisive role in shaping the financial performance of an internationally active industrial company?</p>
<p><strong>p4</strong> At Kelvion, you take on an exposed role at the interface of corporate management, strategic planning and operational performance improvement.</p>
<p><strong>p5</strong> In an increasingly capital market-oriented environment, you make a significant contribution to transparency, forecast quality, financial resilience and sustainable value creation for management, investors and other stakeholders.</p>
<p><strong>p6</strong> Your tasks overall responsibility for the Group-wide budget, forecast and medium-term planning process including derivation of robust steering impulses for management, management and senior management Further development of integrated corporate planning across GuV, balance sheet, cash flow, liquidity, Opex and Capex – with focus on transparency, scenario planning and value-oriented control control and commentary on the monthly, quarterly and annual accounts in close cooperation with accounting, treasury and business units as well as derivation of decision-relevant measures for improving results Creation of high-quality management and board reports as well as address-oriented documents for shareholders, financing partners and further capital market-oriented stakeholders Participation in financially relevant topics of a capital market-oriented environment, in particular performance dialogues, refinancing and financing issues, covenant monitoring as well as cash and liquidity management sparring partners for CEOs, CFOs and management in strategic issues, investment decisions, portfolio prioritization, business cases and transformation initiatives Early identification of opportunities, controlling and planning options to secure corporate goals and financial target corridors Further development of reporting, controlling and planning processes, including KPI framework, standardization, Additional qualifications such as CFA, CMA, CPA or balance sheet accountants (IHK) are advantageous for several years of relevant professional experience (typically 8-12 years) in FP&amp;A, controlling or corporate finance, ideally in an internationally active, capital market-oriented or private equity-oriented industrial company management experience of international teams In-depth expertise in integrated financial planning, performance management, cash and liquidity management as well as in building reliable decision-making basis for top management bodies Very good understanding of the requirements of a capital market-oriented environment, e.g.</p>
<p><strong>p7</strong> B.</p>
<p><strong>p8</strong> in terms of governance, transparency, stakeholder communication, refinancing, covenants and financial control logics Strong analytical, conceptual and strategic skills as well as high security in dealing with complex data models, business cases and scenario analyses Convincing communication and presentation strength with the ability to present complex financial contexts clearly, precisely and address-oriented up to the executive level Very good knowledge in modern finance and reporting systems, in particular Excel, Power BI, , SAP BW/BI, SAP S/4HANA as well as ideal consolidation and planning solutions ideal Tagetik High degree of initiative, implementation strength and change competence as well as the ability to drive forward sustainable improvements in a demanding and international environment Negotiation-secure knowledge of German and English in word and writing What we offer A key position with high strategic relevance and direct visibility in top management The opportunity to actively develop the finance organization and control instruments of an internationally positioned company An innovative, growth-oriented environment in the sense of "One Kelvion" with short decision-making paths and high design possibility Flexible working models and a modern working environment that promotes cooperation, self-responsibility and</p>
<p><strong>p9</strong> At Kelvion, creativity unfolds where people are heard, their ideas welcomed and their contributions acknowledged.</p>
<p><strong>p10</strong> With a flexible approach, we focus on the well-being and satisfaction of our employees.</p>
<p><strong>p11</strong> This strengthens the willingness to participate and thus opens up new career opportunities We encourage committed personalities to take their development into their own hands, to break new ground and to shape the future together with us.</p>
<p><strong>p12</strong> Are you a strategically minded finance professional with a strong performance management mindset who is eager to play a key role in shaping the financial performance of an internationally operating industrial company?</p>
<p><strong>p13</strong> At Kelvion, you will take on a highly visible position at the intersection of corporate performance management, strategic planning, and operational performance improvement.</p>
<p><strong>p14</strong> In an increasingly capital market-oriented environment, you will make a significant contribution to transparency, forecast quality, financial resilience, and sustainable value creation for management, investors, and other stakeholders.</p>
<p><strong>p15</strong> Your Responsibilities Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management.</p>
<p><strong>p16</strong> Further development of an integrated business planning approach across P&amp;L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management.</p>
<p><strong>p17</strong> Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance.</p>
<p><strong>p18</strong> Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders.</p>
<p><strong>p19</strong> Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management.</p>
<p><strong>p20</strong> Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives.</p>
<p><strong>p21</strong> Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors.</p>
<p><strong>p22</strong> Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions.</p>
<p><strong>p23</strong> Functional and disciplinary leadership as well as targeted development of the FP&amp;A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organisation.</p>
<p><strong>p24</strong> Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group.</p>
<p><strong>p25</strong> Your Profile Successfully completed degree in Business Administration, Economics, Finance, or a comparable field; additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage.</p>
<p><strong>p26</strong> Several years of relevant professional experience (typically 8–12 years) in FP&amp;A, Controlling, or Corporate Finance, ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company.</p>
<p><strong>p27</strong> Leadership experience in managing international teams.</p>
<p><strong>p28</strong> Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies.</p>
<p><strong>p29</strong> Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms.</p>
<p><strong>p30</strong> Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses.</p>
<p><strong>p31</strong> Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level.</p>
<p><strong>p32</strong> Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik.</p>
<p><strong>p33</strong> High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment.</p>
<p><strong>p34</strong> Fluent German and English language skills, both written and spoken.</p>
<p><strong>p35</strong> What We Offer A key position with high strategic relevance and direct visibility to top management.</p>
<p><strong>p36</strong> The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company.</p>
<p><strong>p37</strong> An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation.</p>
<p><strong>p38</strong> A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact.</p>
<p><strong>p39</strong> Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development.</p>
<p><strong>p40</strong> Attractive compensation and additional benefits aligned with the scope and responsibility of the role.</p>
<p><strong>p41</strong> At Kelvion we thrive on collaboration, embracing diversity of thought, and valuing every voice.</p>
<p><strong>p42</strong> Within Kelvion creativity shines because people are listened to, their contributions recognised, and their ideas welcomed.</p>
<p><strong>p43</strong> Our flexible approach to the way we work places people’s health and satisfaction as a priority, enhancing engagement and fostering career opportunities.</p>
<p><strong>p44</strong> We empower engaged individuals to grow, progress and carve their own paths within the company.</p>
<p><strong>p45</strong> Together, We Shape the Future Apply Now</p>

</details>

<details>
<summary>Exact rendered prompt</summary>

<p>Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "Our mission is to drive industrial transformation with innovation and sustainability."}, {"id": "p2", "text": "Whether in the optimization of data centers, the further development of hydrogen production or the redesign of cooling and air conditioning systems – our key thermal technologies strengthen numerous industries worldwide."}, {"id": "p3", "text": "As “One Kelvion”, we are continuously working on solutions that make our customers even more successful and at the same time contribute to a more sustainable future.We are shaping the future – together you are a strategically shaped finance personality with a pronounced management requirement and want to play a decisive role in shaping the financial performance of an internationally active industrial company?"}, {"id": "p4", "text": "At Kelvion, you take on an exposed role at the interface of corporate management, strategic planning and operational performance improvement."}, {"id": "p5", "text": "In an increasingly capital market-oriented environment, you make a significant contribution to transparency, forecast quality, financial resilience and sustainable value creation for management, investors and other stakeholders."}, {"id": "p6", "text": "Your tasks overall responsibility for the Group-wide budget, forecast and medium-term planning process including derivation of robust steering impulses for management, management and senior management Further development of integrated corporate planning across GuV, balance sheet, cash flow, liquidity, Opex and Capex – with focus on transparency, scenario planning and value-oriented control control and commentary on the monthly, quarterly and annual accounts in close cooperation with accounting, treasury and business units as well as derivation of decision-relevant measures for improving results Creation of high-quality management and board reports as well as address-oriented documents for shareholders, financing partners and further capital market-oriented stakeholders Participation in financially relevant topics of a capital market-oriented environment, in particular performance dialogues, refinancing and financing issues, covenant monitoring as well as cash and liquidity management sparring partners for CEOs, CFOs and management in strategic issues, investment decisions, portfolio prioritization, business cases and transformation initiatives Early identification of opportunities, controlling and planning options to secure corporate goals and financial target corridors Further development of reporting, controlling and planning processes, including KPI framework, standardization, Additional qualifications such as CFA, CMA, CPA or balance sheet accountants (IHK) are advantageous for several years of relevant professional experience (typically 8-12 years) in FP&amp;A, controlling or corporate finance, ideally in an internationally active, capital market-oriented or private equity-oriented industrial company management experience of international teams In-depth expertise in integrated financial planning, performance management, cash and liquidity management as well as in building reliable decision-making basis for top management bodies Very good understanding of the requirements of a capital market-oriented environment, e.g."}, {"id": "p7", "text": "B."}, {"id": "p8", "text": "in terms of governance, transparency, stakeholder communication, refinancing, covenants and financial control logics Strong analytical, conceptual and strategic skills as well as high security in dealing with complex data models, business cases and scenario analyses Convincing communication and presentation strength with the ability to present complex financial contexts clearly, precisely and address-oriented up to the executive level Very good knowledge in modern finance and reporting systems, in particular Excel, Power BI, , SAP BW/BI, SAP S/4HANA as well as ideal consolidation and planning solutions ideal Tagetik High degree of initiative, implementation strength and change competence as well as the ability to drive forward sustainable improvements in a demanding and international environment Negotiation-secure knowledge of German and English in word and writing What we offer A key position with high strategic relevance and direct visibility in top management The opportunity to actively develop the finance organization and control instruments of an internationally positioned company An innovative, growth-oriented environment in the sense of \"One Kelvion\" with short decision-making paths and high design possibility Flexible working models and a modern working environment that promotes cooperation, self-responsibility and"}, {"id": "p9", "text": "At Kelvion, creativity unfolds where people are heard, their ideas welcomed and their contributions acknowledged."}, {"id": "p10", "text": "With a flexible approach, we focus on the well-being and satisfaction of our employees."}, {"id": "p11", "text": "This strengthens the willingness to participate and thus opens up new career opportunities We encourage committed personalities to take their development into their own hands, to break new ground and to shape the future together with us."}, {"id": "p12", "text": "Are you a strategically minded finance professional with a strong performance management mindset who is eager to play a key role in shaping the financial performance of an internationally operating industrial company?"}, {"id": "p13", "text": "At Kelvion, you will take on a highly visible position at the intersection of corporate performance management, strategic planning, and operational performance improvement."}, {"id": "p14", "text": "In an increasingly capital market-oriented environment, you will make a significant contribution to transparency, forecast quality, financial resilience, and sustainable value creation for management, investors, and other stakeholders."}, {"id": "p15", "text": "Your Responsibilities Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management."}, {"id": "p16", "text": "Further development of an integrated business planning approach across P&amp;L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management."}, {"id": "p17", "text": "Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance."}, {"id": "p18", "text": "Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders."}, {"id": "p19", "text": "Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management."}, {"id": "p20", "text": "Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives."}, {"id": "p21", "text": "Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors."}, {"id": "p22", "text": "Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions."}, {"id": "p23", "text": "Functional and disciplinary leadership as well as targeted development of the FP&amp;A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organisation."}, {"id": "p24", "text": "Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group."}, {"id": "p25", "text": "Your Profile Successfully completed degree in Business Administration, Economics, Finance, or a comparable field; additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage."}, {"id": "p26", "text": "Several years of relevant professional experience (typically 8–12 years) in FP&amp;A, Controlling, or Corporate Finance, ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company."}, {"id": "p27", "text": "Leadership experience in managing international teams."}, {"id": "p28", "text": "Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies."}, {"id": "p29", "text": "Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms."}, {"id": "p30", "text": "Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses."}, {"id": "p31", "text": "Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level."}, {"id": "p32", "text": "Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik."}, {"id": "p33", "text": "High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment."}, {"id": "p34", "text": "Fluent German and English language skills, both written and spoken."}, {"id": "p35", "text": "What We Offer A key position with high strategic relevance and direct visibility to top management."}, {"id": "p36", "text": "The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company."}, {"id": "p37", "text": "An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation."}, {"id": "p38", "text": "A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact."}, {"id": "p39", "text": "Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development."}, {"id": "p40", "text": "Attractive compensation and additional benefits aligned with the scope and responsibility of the role."}, {"id": "p41", "text": "At Kelvion we thrive on collaboration, embracing diversity of thought, and valuing every voice."}, {"id": "p42", "text": "Within Kelvion creativity shines because people are listened to, their contributions recognised, and their ideas welcomed."}, {"id": "p43", "text": "Our flexible approach to the way we work places people’s health and satisfaction as a priority, enhancing engagement and fostering career opportunities."}, {"id": "p44", "text": "We empower engaged individuals to grow, progress and carve their own paths within the company."}, {"id": "p45", "text": "Together, We Shape the Future Apply Now"}]}</p>

</details>

### Model output: mistralai/mistral-nemo

[Exact raw response and usage](responses/german__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 72.34 seconds; input tokens: 2610; output tokens: 1777; billed cost: $0.0001029.

<details>
<summary>Read Model output: mistralai/mistral-nemo</summary>

<p><strong>Overview:</strong> Join Kelvion as a strategic finance professional to drive financial performance and sustainability in an international industrial setting.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p15</strong> Overall responsibility for group-wide budgeting, forecasting, and mid-term planning, including deriving reliable steering impulses for top management.</li>
<li><strong>p16</strong> Further develop integrated business planning across P&amp;L, balance sheet, cash flow, liquidity, Opex, and Capex, focusing on transparency and value-based management.</li>
<li><strong>p17</strong> Steer and comment on monthly, quarterly, and annual financial statements, collaborating with accounting, treasury, and business units to improve performance.</li>
<li><strong>p18</strong> Prepare high-quality management and board reports, as well as materials for shareholders and other stakeholders.</li>
<li><strong>p19</strong> Contribute to finance-related topics in a capital market-oriented environment, such as performance dialogues and refinancing matters.</li>
<li><strong>p20</strong> Act as a sparring partner for the CEO, CFO, and executive management on strategic matters, investment decisions, and transformation initiatives.</li>
<li><strong>p21</strong> Early identification of opportunities, risks, and deviations, developing action plans to safeguard corporate objectives and financial target corridors.</li>
<li><strong>p22</strong> Further develop reporting, controlling, and planning processes, including KPI frameworks and the use of modern BI and EPM solutions.</li>
<li><strong>p23</strong> Functional and disciplinary leadership of the FP&amp;A/Controlling team, aiming to strengthen a high-performing, analytical, and business-oriented finance organization.</li>
<li><strong>p24</strong> Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the group.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p25</strong> Successfully completed degree in Business Administration, Economics, Finance, or a comparable field.</li>
<li><strong>p26</strong> Several years of relevant professional experience (typically 8–12 years) in FP&amp;A, Controlling, or Corporate Finance, ideally in an internationally operating, capital market-oriented, or private equity-backed industrial company.</li>
<li><strong>p27</strong> Leadership experience in managing international teams.</li>
<li><strong>p28</strong> Strong expertise in integrated financial planning, performance management, cash and liquidity management, and decision-making foundations for top management bodies.</li>
<li><strong>p29</strong> Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms.</li>
<li><strong>p30</strong> Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses.</li>
<li><strong>p31</strong> Excellent communication and presentation skills, explaining complex financial matters clearly and effectively up to executive level.</li>
<li><strong>p32</strong> Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions, preferably Tagetik.</li>
<li><strong>p33</strong> High level of initiative, execution capability, and change management skills, driving sustainable improvements in a demanding and international environment.</li>
<li><strong>p34</strong> Fluent German and English language skills, both written and spoken.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p35</strong> A key position with high strategic relevance and direct visibility to top management.</li>
<li><strong>p36</strong> The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company.</li>
<li><strong>p37</strong> An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation.</li>
<li><strong>p38</strong> A collaborative, international working environment with short decision-making paths and extensive opportunities to make an impact.</li>
<li><strong>p39</strong> Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development.</li>
<li><strong>p40</strong> Attractive compensation and additional benefits aligned with the scope and responsibility of the role.</li>
<li><strong>p41</strong> At Kelvion, we thrive on collaboration, embracing diversity of thought, and valuing every voice.</li>
<li><strong>p42</strong> Within Kelvion, creativity shines because people are listened to, their contributions recognized, and their ideas welcomed.</li>
<li><strong>p43</strong> Our flexible approach to work prioritizes people’s health and satisfaction, enhancing engagement and fostering career opportunities.</li>
<li><strong>p44</strong> We empower engaged individuals to grow, progress, and carve their own paths within the company.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p25", "p26", "p27", "p28", "p29", "p30", "p31", "p32", "p33", "p34", "p35", "p36", "p37", "p38", "p39", "p40", "p41", "p42", "p43", "p44", "p45"]</p>

</details>

### Model output: openai/gpt-oss-20b

[Exact raw response and usage](responses/german__openai_gpt-oss-20b.json)
- Finish reason: `length`; elapsed: 242.36 seconds; input tokens: 2577; output tokens: 5500; billed cost: $0.000844733.

<details>
<summary>Read Model output: openai/gpt-oss-20b</summary>

<p>{"final{"

 		

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

 	  

   

 	

 	  

 	

 	

 	

 	

 	

 	

 	

 	

 	

   

 	  

   

 	  

   

  



 	  

 	  

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

  </p>

</details>

### Model output: inclusionai/ling-3.0-flash-vl-20260910

[Exact raw response and usage](responses/german__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 20.56 seconds; input tokens: 2567; output tokens: 1365; billed cost: $0.00039972.

<details>
<summary>Read Model output: inclusionai/ling-3.0-flash-vl-20260910</summary>

<p><strong>Overview:</strong> Senior finance leadership role at Kelvion responsible for group-wide planning, reporting, performance management, and strategic financial steering in a capital market-oriented environment.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p15</strong> Overall responsibility for group-wide budgeting, forecasting, and mid-term planning, including derivation of steering impulses for the Board of Management, Executive Leadership, and Senior Management.</li>
<li><strong>p16</strong> Further develop integrated business planning across P&amp;L, balance sheet, cash flow, liquidity, Opex, and Capex, focusing on transparency, scenario planning, and value-based management.</li>
<li><strong>p17</strong> Steer and comment on monthly, quarterly, and annual financial statements with Accounting, Treasury, and Business Units, deriving decision-relevant measures to improve performance.</li>
<li><strong>p18</strong> Prepare high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders.</li>
<li><strong>p19</strong> Contribute to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, and cash and liquidity management.</li>
<li><strong>p20</strong> Act as sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives.</li>
<li><strong>p21</strong> Early identification of opportunities, risks, and deviations, and develop action plans to safeguard corporate objectives and financial target corridors.</li>
<li><strong>p22</strong> Further develop reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and modern BI and EPM solutions.</li>
<li><strong>p23</strong> Provide functional and disciplinary leadership and targeted development of the FP&amp;A/Controlling team to strengthen a high-performing, analytical, and business-oriented finance organization.</li>
<li><strong>p24</strong> Collaborate closely with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p25</strong> Successfully completed degree in Business Administration, Economics, Finance, or a comparable field.</li>
<li><strong>p26</strong> Several years of relevant professional experience, typically 8–12 years, in FP&amp;A, Controlling, or Corporate Finance.</li>
<li><strong>p27</strong> Leadership experience in managing international teams.</li>
<li><strong>p28</strong> Strong expertise in integrated financial planning, performance management, cash and liquidity management, and developing reliable decision-making foundations for top management bodies.</li>
<li><strong>p29</strong> Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms.</li>
<li><strong>p30</strong> Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses.</li>
<li><strong>p31</strong> Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level.</li>
<li><strong>p32</strong> Very good knowledge of modern finance and reporting systems, especially Excel, Power BI, SAP BW/BI, SAP S/4HANA, and ideally consolidation and planning solutions.</li>
<li><strong>p33</strong> High level of initiative, execution capability, and change management skills, as well as the ability to drive sustainable improvements in a demanding and international environment.</li>
<li><strong>p34</strong> Fluent German and English language skills, both written and spoken.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p6</strong> Additional qualifications such as CFA, CMA, CPA, or balance sheet accountants (IHK) are advantageous.</li>
<li><strong>p26</strong> Experience ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company.</li>
<li><strong>p32</strong> Ideal consolidation and planning solutions, preferably Tagetik.</li>
<li><strong>p25</strong> Additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p35</strong> A key position with high strategic relevance and direct visibility to top management.</li>
<li><strong>p36</strong> The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company.</li>
<li><strong>p37</strong> An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation.</li>
<li><strong>p38</strong> A collaborative, international working environment in line with the One Kelvion philosophy, featuring short decision-making paths and extensive opportunities to make an impact.</li>
<li><strong>p39</strong> Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development.</li>
<li><strong>p40</strong> Attractive compensation and additional benefits aligned with the scope and responsibility of the role.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p45</strong> Apply Now.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p41", "p42", "p43", "p44"]</p>

</details>

### Model output: openai/gpt-oss-120b

[Exact raw response and usage](responses/german__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 44.12 seconds; input tokens: 2564; output tokens: 1722; billed cost: $0.000387608.

<details>
<summary>Read Model output: openai/gpt-oss-120b</summary>

<p><strong>Overview:</strong> Strategic finance leader responsible for group budgeting, forecasting, planning and performance improvement in a capital‑market‑oriented industrial company.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p15</strong> Overall responsibility for group‑wide budgeting, forecasting and medium‑term planning.</li>
<li><strong>p16</strong> Develop integrated business planning across P&amp;L, balance sheet, cash flow, liquidity, Opex and Capex with focus on transparency and scenario planning.</li>
<li><strong>p17</strong> Steer and comment on monthly, quarterly and annual financial statements together with accounting, treasury and business units.</li>
<li><strong>p18</strong> Prepare high‑quality management and board reports and stakeholder‑specific materials.</li>
<li><strong>p19</strong> Contribute to finance topics such as performance dialogues, refinancing, covenant monitoring and cash‑liquidity management.</li>
<li><strong>p20</strong> Act as sparring partner for CEO, CFO and executive management on strategy, investments and transformation initiatives.</li>
<li><strong>p21</strong> Identify opportunities, risks and deviations early and develop action plans to protect financial targets.</li>
<li><strong>p22</strong> Further develop reporting, controlling and planning processes, KPI framework, standardisation and automation using modern BI/EPM tools.</li>
<li><strong>p23</strong> Lead and develop the FP&amp;A/Controlling team to build a high‑performing finance organisation.</li>
<li><strong>p24</strong> Collaborate with international functions and regions to ensure consistent governance, reporting and performance standards.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p25</strong> Degree in Business Administration, Economics, Finance or comparable field.</li>
<li><strong>p27</strong> Leadership experience managing international teams.</li>
<li><strong>p28</strong> Strong expertise in integrated financial planning, performance management, cash and liquidity management.</li>
<li><strong>p29</strong> Solid understanding of capital‑market‑oriented environment requirements (governance, transparency, stakeholder communication, refinancing, covenants).</li>
<li><strong>p30</strong> Strong analytical, conceptual and strategic skills; confidence with complex data models, business cases and scenario analyses.</li>
<li><strong>p31</strong> Excellent communication and presentation abilities up to executive level.</li>
<li><strong>p32</strong> Very good knowledge of modern finance and reporting systems (Excel, Power BI, SAP BW/BI, SAP S/4HANA).</li>
<li><strong>p34</strong> Fluent German and English, both written and spoken.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p26</strong> Experience preferably within an internationally operating, capital‑market‑oriented or private‑equity‑backed industrial company.</li>
<li><strong>p25</strong> Additional qualifications such as CFA, CMA, CPA or Certified Management Accountant are advantageous.</li>
<li><strong>p32</strong> Familiarity with consolidation and planning solutions, preferably Tagetik.</li>
<li><strong>p33</strong> High initiative, execution capability and change‑management skills to drive sustainable improvements.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p35</strong> Key position with high strategic relevance and direct visibility to top management.</li>
<li><strong>p36</strong> Opportunity to shape and further develop the finance organisation and performance‑management tools.</li>
<li><strong>p37</strong> Innovative, growth‑oriented environment at the intersection of industry, sustainability and transformation.</li>
<li><strong>p38</strong> Collaborative international working environment with short decision‑making paths.</li>
<li><strong>p39</strong> Flexible working models and modern workplace promoting collaboration, ownership and development.</li>
<li><strong>p40</strong> Attractive compensation and additional benefits aligned with role scope and responsibility.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p45</strong> Apply now.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p41", "p42", "p43", "p44"]</p>

</details>

### Model output: google/gemini-2.5-flash-lite

[Exact raw response and usage](responses/german__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 3.56 seconds; input tokens: 2527; output tokens: 1330; billed cost: $0.0007847.

<details>
<summary>Read Model output: google/gemini-2.5-flash-lite</summary>

<p><strong>Overview:</strong> Lead financial planning and analysis for an international industrial company, driving strategic decision-making and financial performance.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p15</strong> Overall responsibility for the group-wide budgeting, forecasting, and mid-term planning process, including the derivation of reliable steering impulses for the Board of Management, Executive Leadership, and Senior Management.</li>
<li><strong>p16</strong> Further development of an integrated business planning approach across P&amp;L, balance sheet, cash flow, liquidity, Opex, and Capex, with a focus on transparency, scenario planning, and value-based management.</li>
<li><strong>p17</strong> Steering and commentary of monthly, quarterly, and annual financial statements in close collaboration with Accounting, Treasury, and the Business Units, as well as deriving decision-relevant measures to improve business performance.</li>
<li><strong>p18</strong> Preparation of high-quality management and board reports as well as audience-specific materials for shareholders, financing partners, and other capital market-related stakeholders.</li>
<li><strong>p19</strong> Contributing to finance-related topics in a capital market-oriented environment, particularly performance dialogues, refinancing and financing matters, covenant monitoring, as well as cash and liquidity management.</li>
<li><strong>p20</strong> Acting as a sparring partner for the CEO, CFO, and Executive Management on strategic matters, investment decisions, portfolio prioritization, business cases, and transformation initiatives.</li>
<li><strong>p21</strong> Early identification of opportunities, risks, and deviations, along with developing action plans to safeguard corporate objectives and financial target corridors.</li>
<li><strong>p22</strong> Further development of reporting, controlling, and planning processes, including KPI frameworks, standardization, automation, and the use of modern BI and EPM solutions.</li>
<li><strong>p23</strong> Functional and disciplinary leadership as well as targeted development of the FP&amp;A/Controlling team, with the ambition to further strengthen a high-performing, analytical, and business-oriented finance organisation.</li>
<li><strong>p24</strong> Close collaboration with international functions and regions to ensure consistent governance, reporting, and performance standards throughout the Group.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p25</strong> Successfully completed degree in Business Administration, Economics, Finance, or a comparable field.</li>
<li><strong>p26</strong> Several years of relevant professional experience (typically 8–12 years) in FP&amp;A, Controlling, or Corporate Finance.</li>
<li><strong>p27</strong> Leadership experience in managing international teams.</li>
<li><strong>p28</strong> Strong expertise in integrated financial planning, performance management, cash and liquidity management, and the development of reliable decision-making foundations for top management bodies.</li>
<li><strong>p29</strong> Sound understanding of the requirements of a capital market-oriented environment, particularly regarding governance, transparency, stakeholder communication, refinancing, covenants, and financial steering mechanisms.</li>
<li><strong>p30</strong> Strong analytical, conceptual, and strategic capabilities, combined with confidence in working with complex data models, business cases, and scenario analyses.</li>
<li><strong>p31</strong> Excellent communication and presentation skills, with the ability to explain complex financial matters clearly, accurately, and effectively up to executive level.</li>
<li><strong>p32</strong> Very good knowledge in modern finance and reporting systems, in particular Excel, Power BI, SAP BW/BI, SAP S/4HANA.</li>
<li><strong>p33</strong> High degree of initiative, implementation strength and change competence as well as the ability to drive forward sustainable improvements in a demanding and international environment.</li>
<li><strong>p34</strong> Fluent German and English language skills, both written and spoken.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p25</strong> Additional qualifications such as CFA, CMA, CPA, or Certified Management Accountant are an advantage.</li>
<li><strong>p26</strong> Ideally within an internationally operating, capital market-oriented, or private equity-backed industrial company.</li>
<li><strong>p32</strong> Ideally consolidation and planning solutions, preferably Tagetik.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p35</strong> A key position with high strategic relevance and direct visibility to top management.</li>
<li><strong>p36</strong> The opportunity to actively shape and further develop the finance organization and performance management tools of an internationally operating company.</li>
<li><strong>p37</strong> An innovative, growth-oriented environment at the intersection of industry, sustainability, and transformation.</li>
<li><strong>p38</strong> A collaborative, international working environment in line with our “One Kelvion” philosophy, featuring short decision-making paths and extensive opportunities to make an impact.</li>
<li><strong>p39</strong> Flexible working models and a modern workplace that promotes collaboration, ownership, and professional development.</li>
<li><strong>p40</strong> Attractive compensation and additional benefits aligned with the scope and responsibility of the role.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p45</strong> Apply Now</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p37", "p38", "p39", "p41", "p42", "p43", "p44"]</p>

</details>

## preferred: Marketing COE Lead

- Canonical job ID: `canonical_job_45953610e2414f0d8a05a692b560c72b`
- Posting version: `posting_version_b737755a330344bf899ef021439087e4`
- Source URL: https://jobs.eastman.com/job/Kingsport-Marketing-COE-Lead-TN-37660/1377487500
- Translation runtime on the local Windows machine: 0.0 seconds

[Original text](preferred__original.txt) · [English passages](preferred__english.txt) · [Exact prompt](prompts/preferred.txt)

<details>
<summary>Original preserved job posting</summary>

<p>Marketing COE Lead Job Details | Eastman This site uses cookies to store information on your computer. Some are essential to make our site work; others help us improve the user experience. By using the site, you consent to the placement of these cookies. Read our Privacy Notice to learn more. Accept Close Skip to main content Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Language Deutsch (Deutschland) English (United States) Español (España) Français (France) Nederlands (Nederland) Português (Brasil) View Profile Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Select how often (in days) to receive an alert: Create Alert × Select how often (in days) to receive an alert: Apply now » Marketing COE Lead Job Requisition ID: 55990 Founded in 1920, Eastman is a global specialty materials company that produces a broad range of products found in items people use every day. With the purpose of enhancing the quality of life in a material way, Eastman works with customers to deliver innovative products and solutions while maintaining a commitment to safety and sustainability. The company’s innovation-driven growth model takes advantage of world-class technology platforms, deep customer engagement, and differentiated application development to grow its leading positions in attractive end markets such as transportation, building and construction, and consumables. As a globally inclusive company, Eastman employs approximately 13,000 people around the world and serves customers in more than 100 countries. The company had 2025 revenue of approximately $8.8 billion and is headquartered in Kingsport, Tennessee, USA. For more information, visit www.eastman.com . Description The Global Commercial Excellence organization is responsible for building world class commercial capability within Eastman. This includes continuously upgrading the capabilities and improving the performance of our people, processes, and systems. As a Marketing Excellence Center of Excellence (COE) Leader, you lead the central COE and co-lead the Marketing COE Leadership Team along with key business leaders. You are responsible for building world-class marketing capabilities and driving commercial results. You will accomplish this through partnering with marketing and commercial leadership to: Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience (strategic, digital, brand, marcom, channel marketing, etc) —facilitating strategic discussions, co-creating and prioritizing initiatives in annual scorecard and our transformation roadmap, driving timely, data-informed decisions, and ensuring shared accountability for execution and results. Ensure convergence and commitment across businesses to common marketing processes and best practices. Develop, implement, and execute COE global &amp; regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise. Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles. Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way. Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics. Partner with businesses leaders to support the transformation journey of Marketing Excellence. Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing. While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions. Responsibilities Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT. Develop co-created solutions with senior marketing leaders on key priorities. Drive implementation, with and through COE LT leaders, on key initiatives. Create and manage ongoing COE LT agenda. Ensure active tracking, monitoring, adjustments and actions on key initiatives. Work actively with other functional leaders (e.g. HR) to drive change management and enable the implementation (e.g. with training, communication, tool deployment, etc.). Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed. Lead support for COE LT: Oversee central COE staff to support COE LT activities. Provide support analysis. Conduct direct training, communication, coaching, and change management. Support special projects where necessary. Consistently identify and evaluate external best practices in the marketing space. Share best practices globally. Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts. Drive Marketing Tools Implementation: Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection. Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results. Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs. Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews. Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement. Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact. Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement. Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps. Develop and implement plans to close gaps. Serve as an expert coach in marketing processes. Conduct leader and train the trainer coaching. Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders. Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards. Qualifications Bachelors, from an accredited college or university is required. Masters or MBA preferred. Min. 10 years of commercial experience; minimum 5 years marketing experience required. Experience developing and executing Commercial Excellence Capabilities with cross business team members. Demonstrated experience and success leading teams and influencing without authority. US-based location preferred. Benefits Your total rewards go far beyond a competitive salary. When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career. Compensation &amp; Incentives • Base pay plus performance-based incentive opportunities that let you share in our success. Health &amp; Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future. • A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life. • Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling. Retirement &amp; Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings. Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments. Growth &amp; Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career. At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of. Eastman Chemical Company is an equal opportunity employer. All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law. Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day. Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing Opens in a new tab. Opens in a new tab. Opens in a new tab. Opens in a new tab. Eastman.com Privacy Policy View All Jobs Supply Chain Responsibility Legal Contact Us © 2020 Eastman Chemical Company or its subsidiaries. All rights reserved. As used herein, ® denotes registered trademark status in the U.S. only. Thank you for your interest in careers at Eastman. Eastman Chemical Company is an equal opportunity employer. All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law. Eastman is committed to creating a highly engaged workplace, where everyone can contribute to their fullest potential each day. As part of our recruiting and hiring process, Eastman will not ask for fees, payments or credit card information. If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com.</p>

</details>

<details>
<summary>English text supplied to models</summary>

<p><strong>p1</strong> Marketing COE Lead Job Details | Eastman This site uses cookies to store information on your computer.</p>
<p><strong>p2</strong> Some are essential to make our site work; others help us improve the user experience.</p>
<p><strong>p3</strong> By using the site, you consent to the placement of these cookies.</p>
<p><strong>p4</strong> Read our Privacy Notice to learn more.</p>
<p><strong>p5</strong> Accept Close Skip to main content Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Language Deutsch (Deutschland) English (United States) Español (España) Français (France) Nederlands (Nederland) Português (Brasil) View Profile Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Select how often (in days) to receive an alert: Create Alert × Select how often (in days) to receive an alert: Apply now » Marketing COE Lead Job Requisition ID: 55990 Founded in 1920, Eastman is a global specialty materials company that produces a broad range of products found in items people use every day.</p>
<p><strong>p6</strong> With the purpose of enhancing the quality of life in a material way, Eastman works with customers to deliver innovative products and solutions while maintaining a commitment to safety and sustainability.</p>
<p><strong>p7</strong> The company’s innovation-driven growth model takes advantage of world-class technology platforms, deep customer engagement, and differentiated application development to grow its leading positions in attractive end markets such as transportation, building and construction, and consumables.</p>
<p><strong>p8</strong> As a globally inclusive company, Eastman employs approximately 13,000 people around the world and serves customers in more than 100 countries.</p>
<p><strong>p9</strong> The company had 2025 revenue of approximately $8.8 billion and is headquartered in Kingsport, Tennessee, USA.</p>
<p><strong>p10</strong> For more information, visit www.eastman.com .</p>
<p><strong>p11</strong> Description The Global Commercial Excellence organization is responsible for building world class commercial capability within Eastman.</p>
<p><strong>p12</strong> This includes continuously upgrading the capabilities and improving the performance of our people, processes, and systems.</p>
<p><strong>p13</strong> As a Marketing Excellence Center of Excellence (COE) Leader, you lead the central COE and co-lead the Marketing COE Leadership Team along with key business leaders.</p>
<p><strong>p14</strong> You are responsible for building world-class marketing capabilities and driving commercial results.</p>
<p><strong>p15</strong> You will accomplish this through partnering with marketing and commercial leadership to: Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience (strategic, digital, brand, marcom, channel marketing, etc) —facilitating strategic discussions, co-creating and prioritizing initiatives in annual scorecard and our transformation roadmap, driving timely, data-informed decisions, and ensuring shared accountability for execution and results.</p>
<p><strong>p16</strong> Ensure convergence and commitment across businesses to common marketing processes and best practices.</p>
<p><strong>p17</strong> Develop, implement, and execute COE global &amp; regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise.</p>
<p><strong>p18</strong> Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles.</p>
<p><strong>p19</strong> Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way.</p>
<p><strong>p20</strong> Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics.</p>
<p><strong>p21</strong> Partner with businesses leaders to support the transformation journey of Marketing Excellence.</p>
<p><strong>p22</strong> Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing.</p>
<p><strong>p23</strong> While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions.</p>
<p><strong>p24</strong> Responsibilities Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT.</p>
<p><strong>p25</strong> Develop co-created solutions with senior marketing leaders on key priorities.</p>
<p><strong>p26</strong> Drive implementation, with and through COE LT leaders, on key initiatives.</p>
<p><strong>p27</strong> Create and manage ongoing COE LT agenda.</p>
<p><strong>p28</strong> Ensure active tracking, monitoring, adjustments and actions on key initiatives.</p>
<p><strong>p29</strong> Work actively with other functional leaders (e.g.</p>
<p><strong>p30</strong> HR) to drive change management and enable the implementation (e.g.</p>
<p><strong>p31</strong> with training, communication, tool deployment, etc.).</p>
<p><strong>p32</strong> Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed.</p>
<p><strong>p33</strong> Lead support for COE LT: Oversee central COE staff to support COE LT activities.</p>
<p><strong>p34</strong> Provide support analysis.</p>
<p><strong>p35</strong> Conduct direct training, communication, coaching, and change management.</p>
<p><strong>p36</strong> Support special projects where necessary.</p>
<p><strong>p37</strong> Consistently identify and evaluate external best practices in the marketing space.</p>
<p><strong>p38</strong> Share best practices globally.</p>
<p><strong>p39</strong> Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts.</p>
<p><strong>p40</strong> Drive Marketing Tools Implementation: Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection.</p>
<p><strong>p41</strong> Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results.</p>
<p><strong>p42</strong> Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs.</p>
<p><strong>p43</strong> Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews.</p>
<p><strong>p44</strong> Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement.</p>
<p><strong>p45</strong> Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact.</p>
<p><strong>p46</strong> Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement.</p>
<p><strong>p47</strong> Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps.</p>
<p><strong>p48</strong> Develop and implement plans to close gaps.</p>
<p><strong>p49</strong> Serve as an expert coach in marketing processes.</p>
<p><strong>p50</strong> Conduct leader and train the trainer coaching.</p>
<p><strong>p51</strong> Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders.</p>
<p><strong>p52</strong> Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards.</p>
<p><strong>p53</strong> Qualifications Bachelors, from an accredited college or university is required.</p>
<p><strong>p54</strong> Masters or MBA preferred.</p>
<p><strong>p55</strong> Min.</p>
<p><strong>p56</strong> 10 years of commercial experience; minimum 5 years marketing experience required.</p>
<p><strong>p57</strong> Experience developing and executing Commercial Excellence Capabilities with cross business team members.</p>
<p><strong>p58</strong> Demonstrated experience and success leading teams and influencing without authority.</p>
<p><strong>p59</strong> US-based location preferred.</p>
<p><strong>p60</strong> Benefits Your total rewards go far beyond a competitive salary.</p>
<p><strong>p61</strong> When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career.</p>
<p><strong>p62</strong> Compensation &amp; Incentives • Base pay plus performance-based incentive opportunities that let you share in our success.</p>
<p><strong>p63</strong> Health &amp; Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future.</p>
<p><strong>p64</strong> • A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life.</p>
<p><strong>p65</strong> • Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling.</p>
<p><strong>p66</strong> Retirement &amp; Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings.</p>
<p><strong>p67</strong> Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments.</p>
<p><strong>p68</strong> Growth &amp; Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career.</p>
<p><strong>p69</strong> At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of.</p>
<p><strong>p70</strong> Eastman Chemical Company is an equal opportunity employer.</p>
<p><strong>p71</strong> All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law.</p>
<p><strong>p72</strong> Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day.</p>
<p><strong>p73</strong> Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing Opens in a new tab.</p>
<p><strong>p74</strong> Opens in a new tab.</p>
<p><strong>p75</strong> Opens in a new tab.</p>
<p><strong>p76</strong> Opens in a new tab.</p>
<p><strong>p77</strong> Eastman.com Privacy Policy View All Jobs Supply Chain Responsibility Legal Contact Us © 2020 Eastman Chemical Company or its subsidiaries.</p>
<p><strong>p78</strong> All rights reserved.</p>
<p><strong>p79</strong> As used herein, ® denotes registered trademark status in the U.S.</p>
<p><strong>p80</strong> only.</p>
<p><strong>p81</strong> Thank you for your interest in careers at Eastman.</p>
<p><strong>p82</strong> Eastman Chemical Company is an equal opportunity employer.</p>
<p><strong>p83</strong> All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law.</p>
<p><strong>p84</strong> Eastman is committed to creating a highly engaged workplace, where everyone can contribute to their fullest potential each day.</p>
<p><strong>p85</strong> As part of our recruiting and hiring process, Eastman will not ask for fees, payments or credit card information.</p>
<p><strong>p86</strong> If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com.</p>

</details>

<details>
<summary>Exact rendered prompt</summary>

<p>Read this ONE job posting in English and return a clear English description as JSON only. Return {"overview":"short English sentence", "items":[{"passage_id":"p1","section":"responsibilities","text":"one concise English fact"}],"ignored_ids":["p2"]}. The five section names are: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. Every passage ID must occur in items or ignored_ids; an ID may support multiple items. Do not repeat source quotes; the application copies passages itself. Keep all stated numbers, licences, languages and application conditions. Do not invent facts or omit qualifications. Split mixed qualifications into separate items: "8 years in finance, ideally in manufacturing" means required 8 years in finance and preferred manufacturing experience. Required means explicitly required or unqualified statements in a qualifications/profile section. "In addition, we would like", "nice to have", "preferred", "advantage", "ideally", and "preferably" indicate preference for the associated qualification; when such wording introduces a list, the whole following list stays preferred until another section. Do not place any preferred detail inside a required item. Make each item independently readable and keep it short. Ignore only headings, employer advertising, duplicates or irrelevant boilerplate. Posting: {"passages": [{"id": "p1", "text": "Marketing COE Lead Job Details | Eastman This site uses cookies to store information on your computer."}, {"id": "p2", "text": "Some are essential to make our site work; others help us improve the user experience."}, {"id": "p3", "text": "By using the site, you consent to the placement of these cookies."}, {"id": "p4", "text": "Read our Privacy Notice to learn more."}, {"id": "p5", "text": "Accept Close Skip to main content Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Featured Jobs Administrative Support Circular Economy Commercial Sales, Marketing and Pricing Engineering Finance Human Resources Information Technology Legal Manufacturing Procurement Research and Development Supply Chain University Relations Join Our Talent Community Join Our Talent Community View All Jobs Return to Eastman Careers Language Deutsch (Deutschland) English (United States) Español (España) Français (France) Nederlands (Nederland) Português (Brasil) View Profile Search by Keyword Search by Location Search by Postal Code Search by Location Search by Postal Code Distance 2 mi 5 mi 10 mi 30 mi 50 mi Search by Postal Code Search by Location Clear Select how often (in days) to receive an alert: Create Alert × Select how often (in days) to receive an alert: Apply now » Marketing COE Lead Job Requisition ID: 55990 Founded in 1920, Eastman is a global specialty materials company that produces a broad range of products found in items people use every day."}, {"id": "p6", "text": "With the purpose of enhancing the quality of life in a material way, Eastman works with customers to deliver innovative products and solutions while maintaining a commitment to safety and sustainability."}, {"id": "p7", "text": "The company’s innovation-driven growth model takes advantage of world-class technology platforms, deep customer engagement, and differentiated application development to grow its leading positions in attractive end markets such as transportation, building and construction, and consumables."}, {"id": "p8", "text": "As a globally inclusive company, Eastman employs approximately 13,000 people around the world and serves customers in more than 100 countries."}, {"id": "p9", "text": "The company had 2025 revenue of approximately $8.8 billion and is headquartered in Kingsport, Tennessee, USA."}, {"id": "p10", "text": "For more information, visit www.eastman.com ."}, {"id": "p11", "text": "Description The Global Commercial Excellence organization is responsible for building world class commercial capability within Eastman."}, {"id": "p12", "text": "This includes continuously upgrading the capabilities and improving the performance of our people, processes, and systems."}, {"id": "p13", "text": "As a Marketing Excellence Center of Excellence (COE) Leader, you lead the central COE and co-lead the Marketing COE Leadership Team along with key business leaders."}, {"id": "p14", "text": "You are responsible for building world-class marketing capabilities and driving commercial results."}, {"id": "p15", "text": "You will accomplish this through partnering with marketing and commercial leadership to: Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience (strategic, digital, brand, marcom, channel marketing, etc) —facilitating strategic discussions, co-creating and prioritizing initiatives in annual scorecard and our transformation roadmap, driving timely, data-informed decisions, and ensuring shared accountability for execution and results."}, {"id": "p16", "text": "Ensure convergence and commitment across businesses to common marketing processes and best practices."}, {"id": "p17", "text": "Develop, implement, and execute COE global &amp; regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise."}, {"id": "p18", "text": "Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles."}, {"id": "p19", "text": "Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way."}, {"id": "p20", "text": "Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics."}, {"id": "p21", "text": "Partner with businesses leaders to support the transformation journey of Marketing Excellence."}, {"id": "p22", "text": "Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing."}, {"id": "p23", "text": "While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions."}, {"id": "p24", "text": "Responsibilities Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT."}, {"id": "p25", "text": "Develop co-created solutions with senior marketing leaders on key priorities."}, {"id": "p26", "text": "Drive implementation, with and through COE LT leaders, on key initiatives."}, {"id": "p27", "text": "Create and manage ongoing COE LT agenda."}, {"id": "p28", "text": "Ensure active tracking, monitoring, adjustments and actions on key initiatives."}, {"id": "p29", "text": "Work actively with other functional leaders (e.g."}, {"id": "p30", "text": "HR) to drive change management and enable the implementation (e.g."}, {"id": "p31", "text": "with training, communication, tool deployment, etc.)."}, {"id": "p32", "text": "Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed."}, {"id": "p33", "text": "Lead support for COE LT: Oversee central COE staff to support COE LT activities."}, {"id": "p34", "text": "Provide support analysis."}, {"id": "p35", "text": "Conduct direct training, communication, coaching, and change management."}, {"id": "p36", "text": "Support special projects where necessary."}, {"id": "p37", "text": "Consistently identify and evaluate external best practices in the marketing space."}, {"id": "p38", "text": "Share best practices globally."}, {"id": "p39", "text": "Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts."}, {"id": "p40", "text": "Drive Marketing Tools Implementation: Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection."}, {"id": "p41", "text": "Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results."}, {"id": "p42", "text": "Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs."}, {"id": "p43", "text": "Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews."}, {"id": "p44", "text": "Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement."}, {"id": "p45", "text": "Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact."}, {"id": "p46", "text": "Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement."}, {"id": "p47", "text": "Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps."}, {"id": "p48", "text": "Develop and implement plans to close gaps."}, {"id": "p49", "text": "Serve as an expert coach in marketing processes."}, {"id": "p50", "text": "Conduct leader and train the trainer coaching."}, {"id": "p51", "text": "Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders."}, {"id": "p52", "text": "Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards."}, {"id": "p53", "text": "Qualifications Bachelors, from an accredited college or university is required."}, {"id": "p54", "text": "Masters or MBA preferred."}, {"id": "p55", "text": "Min."}, {"id": "p56", "text": "10 years of commercial experience; minimum 5 years marketing experience required."}, {"id": "p57", "text": "Experience developing and executing Commercial Excellence Capabilities with cross business team members."}, {"id": "p58", "text": "Demonstrated experience and success leading teams and influencing without authority."}, {"id": "p59", "text": "US-based location preferred."}, {"id": "p60", "text": "Benefits Your total rewards go far beyond a competitive salary."}, {"id": "p61", "text": "When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career."}, {"id": "p62", "text": "Compensation &amp; Incentives • Base pay plus performance-based incentive opportunities that let you share in our success."}, {"id": "p63", "text": "Health &amp; Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future."}, {"id": "p64", "text": "• A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life."}, {"id": "p65", "text": "• Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling."}, {"id": "p66", "text": "Retirement &amp; Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings."}, {"id": "p67", "text": "Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments."}, {"id": "p68", "text": "Growth &amp; Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career."}, {"id": "p69", "text": "At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of."}, {"id": "p70", "text": "Eastman Chemical Company is an equal opportunity employer."}, {"id": "p71", "text": "All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law."}, {"id": "p72", "text": "Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day."}, {"id": "p73", "text": "Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing Opens in a new tab."}, {"id": "p74", "text": "Opens in a new tab."}, {"id": "p75", "text": "Opens in a new tab."}, {"id": "p76", "text": "Opens in a new tab."}, {"id": "p77", "text": "Eastman.com Privacy Policy View All Jobs Supply Chain Responsibility Legal Contact Us © 2020 Eastman Chemical Company or its subsidiaries."}, {"id": "p78", "text": "All rights reserved."}, {"id": "p79", "text": "As used herein, ® denotes registered trademark status in the U.S."}, {"id": "p80", "text": "only."}, {"id": "p81", "text": "Thank you for your interest in careers at Eastman."}, {"id": "p82", "text": "Eastman Chemical Company is an equal opportunity employer."}, {"id": "p83", "text": "All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law."}, {"id": "p84", "text": "Eastman is committed to creating a highly engaged workplace, where everyone can contribute to their fullest potential each day."}, {"id": "p85", "text": "As part of our recruiting and hiring process, Eastman will not ask for fees, payments or credit card information."}, {"id": "p86", "text": "If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com."}]}</p>

</details>

### Model output: mistralai/mistral-nemo

[Exact raw response and usage](responses/preferred__mistralai_mistral-nemo.json)
- Finish reason: `stop`; elapsed: 140.64 seconds; input tokens: 3599; output tokens: 3299; billed cost: $0.000167351.

<details>
<summary>Read Model output: mistralai/mistral-nemo</summary>

<p><strong>Overview:</strong> Lead the Marketing Center of Excellence (COE) to build world-class marketing capabilities and drive commercial results.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p15</strong> Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi-sub-marketing disciplinary experience.</li>
<li><strong>p16</strong> Ensure convergence and commitment across businesses to common marketing processes and best practices.</li>
<li><strong>p17</strong> Develop, implement, and execute COE global &amp; regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise.</li>
<li><strong>p18</strong> Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles.</li>
<li><strong>p19</strong> Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data-driven way.</li>
<li><strong>p20</strong> Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics.</li>
<li><strong>p21</strong> Partner with businesses leaders to support the transformation journey of Marketing Excellence.</li>
<li><strong>p22</strong> Overall, you will become a trusted advisor and business partner to commercial leadership in the field of marketing.</li>
<li><strong>p23</strong> While your focus is marketing, you will serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions.</li>
<li><strong>p24</strong> Lead Marketing COE Leadership Team (LT) Work actively with the SLT champion and designated COE business leader to co-lead the primary decision-making body, and implementation channel, for marketing excellence: Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT.</li>
<li><strong>p25</strong> Develop co-created solutions with senior marketing leaders on key priorities.</li>
<li><strong>p26</strong> Drive implementation, with and through COE LT leaders, on key initiatives.</li>
<li><strong>p27</strong> Create and manage ongoing COE LT agenda.</li>
<li><strong>p28</strong> Ensure active tracking, monitoring, adjustments and actions on key initiatives.</li>
<li><strong>p29</strong> Work actively with other functional leaders (e.g. HR) to drive change management and enable the implementation (e.g. with training, communication, tool deployment, etc.).</li>
<li><strong>p30</strong> Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed.</li>
<li><strong>p31</strong> Lead support for COE LT: Oversee central COE staff to support COE LT activities.</li>
<li><strong>p32</strong> Provide support analysis.</li>
<li><strong>p33</strong> Conduct direct training, communication, coaching, and change management.</li>
<li><strong>p34</strong> Support special projects where necessary.</li>
<li><strong>p35</strong> Consistently identify and evaluate external best practices in the marketing space.</li>
<li><strong>p36</strong> Share best practices globally.</li>
<li><strong>p37</strong> Work with the marketing leadership teams and marketing organizations to proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts.</li>
<li><strong>p38</strong> Drive Marketing Tools Implementation: Serve as the global subject-matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection.</li>
<li><strong>p39</strong> Co-create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results.</li>
<li><strong>p40</strong> Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs.</li>
<li><strong>p41</strong> Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews.</li>
<li><strong>p42</strong> Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement.</li>
<li><strong>p43</strong> Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact.</li>
<li><strong>p44</strong> Enhance Marketing Skills: Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement.</li>
<li><strong>p45</strong> Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps.</li>
<li><strong>p46</strong> Develop and implement plans to close gaps.</li>
<li><strong>p47</strong> Serve as an expert coach in marketing processes.</li>
<li><strong>p48</strong> Conduct leader and train the trainer coaching.</li>
<li><strong>p49</strong> Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders.</li>
<li><strong>p50</strong> Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p53</strong> Bachelors, from an accredited college or university is required.</li>
<li><strong>p56</strong> Min. 10 years of commercial experience; minimum 5 years marketing experience required.</li>
<li><strong>p57</strong> Experience developing and executing Commercial Excellence Capabilities with cross business team members.</li>
<li><strong>p58</strong> Demonstrated experience and success leading teams and influencing without authority.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p54</strong> Masters or MBA preferred.</li>
<li><strong>p59</strong> US-based location preferred.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p60</strong> Your total rewards go far beyond a competitive salary.</li>
<li><strong>p61</strong> When you join Eastman, you gain access to an exceptional suite of programs designed to protect your health, grow your wealth, and fuel your career.</li>
<li><strong>p62</strong> Compensation &amp; Incentives • Base pay plus performance-based incentive opportunities that let you share in our success.</li>
<li><strong>p63</strong> Health &amp; Wellness • Comprehensive medical, prescription-drug, and dental coverage—paired with a Health Savings Account option to help you save tax-free dollars for care today or in the future.</li>
<li><strong>p64</strong> • A robust menu of voluntary benefits—including vision, optional life, critical-illness protection, and more—so you can tailor coverage to fit your life.</li>
<li><strong>p65</strong> • Holistic wellness support: financial-planning tools, family-building assistance (adoption, pregnancy, and fertility resources), parental leave, and confidential Employee Assistance Program counseling.</li>
<li><strong>p66</strong> Retirement &amp; Financial Strategies • 401(k) with a company match—plus an additional annual retirement contribution from Eastman to accelerate your long-term savings.</li>
<li><strong>p67</strong> Time Away • Eleven paid holidays, one personal day, paid time off, and paid vacation to recharge, celebrate, or handle life’s moments.</li>
<li><strong>p68</strong> Growth &amp; Development • Access to mentorship, learning resources, and leadership programs that empower you to thrive in your current role and chart the next steps in your career.</li>
<li><strong>p69</strong> At Eastman, we invest in the whole you—so you can bring your best self to work every day and build a future you’re proud of.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p70</strong> Eastman Chemical Company is an equal opportunity employer.</li>
<li><strong>p71</strong> All qualified applicants will receive consideration for employment without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status or any other protected classes as designated by law.</li>
<li><strong>p72</strong> Eastman is committed to creating a powerfully engaged workplace, where everyone can contribute to their fullest potential each day.</li>
<li><strong>p73</strong> Nearest Major Market: Asheville Nearest Secondary Market: Knoxville Job Segment: Marketing MBA, Recruiting, Curriculum, Channel Marketing, Marketing, Human Resources, Education Apply now » Find similar jobs: Ventes commerciales, Marketing et Pricing, Ventas Comerciales, Marketing y Precios, Commerciële verkoop, marketing en prijsstelling, Commercial Sales, Marketing and Pricing</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p29", "p30", "p31", "p32", "p33", "p34", "p35", "p36", "p37", "p38", "p39", "p40", "p41", "p42", "p43", "p44", "p45", "p46", "p47", "p48", "p49", "p50", "p51", "p52", "p55", "p59", "p60", "p61", "p62", "p63", "p64", "p65", "p66", "p67", "p68", "p69", "p70", "p71", "p72", "p73", "p74", "p75", "p76", "p77", "p78", "p79", "p80", "p81", "p82", "p83", "p84", "p85", "p86"]</p>

</details>

### Model output: openai/gpt-oss-20b

[Exact raw response and usage](responses/preferred__openai_gpt-oss-20b.json)
- Finish reason: `stop`; elapsed: 15.73 seconds; input tokens: 3516; output tokens: 829; billed cost: $0.000137898.

<details>
<summary>Read Model output: openai/gpt-oss-20b</summary>

<p><strong>Overview:</strong> Lead the global Marketing COE to build world‑class marketing capabilities and drive commercial results.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p24</strong> Lead the Marketing COE Leadership Team and co‑create a multi‑year roadmap for 2026.</li>
<li><strong>p24</strong> Drive implementation of key initiatives and ensure active tracking and adjustments.</li>
<li><strong>p24</strong> Serve as the global subject‑matter lead for marketing processes, tools, and systems.</li>
<li><strong>p24</strong> Coach senior marketing leaders on analytics, dashboards, and continuous improvement.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p53</strong> Bachelor’s degree from an accredited college or university.</li>
<li><strong>p56</strong> 10 years of commercial experience, including a minimum of 5 years in marketing.</li>
<li><strong>p57</strong> Experience developing and executing Commercial Excellence capabilities with cross‑business teams.</li>
<li><strong>p58</strong> Demonstrated success leading teams and influencing without authority.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p54</strong> Master’s or MBA degree.</li>
<li><strong>p59</strong> US‑based location.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p60</strong> Competitive base pay plus performance‑based incentives, comprehensive medical, dental, vision, and wellness programs, 401(k) with company match, paid holidays, personal day, paid time off, and career development resources.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p15", "p16", "p17", "p18", "p19", "p20", "p21", "p22", "p23", "p25", "p26", "p27", "p28", "p29", "p30", "p31", "p32", "p33", "p34", "p35", "p36", "p37", "p38", "p39", "p40", "p41", "p42", "p43", "p44", "p45", "p46", "p47", "p48", "p49", "p50", "p51", "p52", "p53", "p54", "p55", "p56", "p57", "p58", "p59", "p60", "p61", "p62", "p63", "p64", "p65", "p66", "p67", "p68", "p69", "p70", "p71", "p72", "p73", "p74", "p75", "p76", "p77", "p78", "p79", "p80", "p81", "p82", "p83", "p84", "p85", "p86"]</p>

</details>

### Model output: inclusionai/ling-3.0-flash-vl-20260910

[Exact raw response and usage](responses/preferred__inclusionai_ling-3.0-flash-vl-20260910.json)
- Finish reason: `stop`; elapsed: 31.55 seconds; input tokens: 3527; output tokens: 1895; billed cost: $0.00055272.

<details>
<summary>Read Model output: inclusionai/ling-3.0-flash-vl-20260910</summary>

<p><strong>Overview:</strong> Lead the global Marketing Center of Excellence, driving marketing capability, tools, analytics, and talent development in partnership with commercial leadership.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p13</strong> Lead the central Marketing COE and co-lead the Marketing COE Leadership Team with key business leaders.</li>
<li><strong>p14</strong> Build world-class marketing capabilities and drive commercial results.</li>
<li><strong>p15</strong> Lead the global Marketing COE Leadership Team, facilitating strategic discussions and prioritizing initiatives across multi-disciplinary marketing functions.</li>
<li><strong>p16</strong> Ensure convergence and commitment across businesses to common marketing processes and best practices.</li>
<li><strong>p17</strong> Develop and execute global and regional marketing initiatives and best practices across the enterprise.</li>
<li><strong>p18</strong> Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles.</li>
<li><strong>p19</strong> Work with IT to identify technological solutions for marketers to assess market dynamics and customer segments.</li>
<li><strong>p20</strong> Accelerate the shift to disciplined marketing processes, metrics, and analytics.</li>
<li><strong>p21</strong> Partner with business leaders to support the transformation journey of Marketing Excellence.</li>
<li><strong>p22</strong> Become a trusted advisor and business partner to commercial leadership in marketing.</li>
<li><strong>p23</strong> Serve as a key liaison with Sales, Product and Pricing, IT, and other functions for marketing capability solutions.</li>
<li><strong>p24</strong> Co-lead the primary decision-making body for marketing excellence, developing a multi-year roadmap and gaining enterprise alignment.</li>
<li><strong>p25</strong> Develop co-created solutions with senior marketing leaders on key priorities.</li>
<li><strong>p26</strong> Drive implementation of key initiatives through COE Leadership Team leaders.</li>
<li><strong>p27</strong> Create and manage the ongoing COE Leadership Team agenda.</li>
<li><strong>p28</strong> Ensure active tracking, monitoring, adjustments, and actions on key initiatives.</li>
<li><strong>p31</strong> Work with functional leaders such as HR to drive change management and enable implementation through training, communication, and tool deployment.</li>
<li><strong>p32</strong> Develop resourcing options and recommendations to accelerate progress and close gaps.</li>
<li><strong>p33</strong> Oversee central COE staff to support COE Leadership Team activities.</li>
<li><strong>p34</strong> Provide support analysis for COE activities.</li>
<li><strong>p35</strong> Conduct direct training, communication, coaching, and change management.</li>
<li><strong>p36</strong> Support special projects where necessary.</li>
<li><strong>p37</strong> Consistently identify and evaluate external best practices in the marketing space.</li>
<li><strong>p38</strong> Share best practices globally.</li>
<li><strong>p39</strong> Proactively identify improvement opportunities in existing marketing tools or needs for alternate tools.</li>
<li><strong>p40</strong> Serve as global subject-matter lead for marketing processes, tools, methodologies, and systems, owning lifecycle decisions and advising on tool selection.</li>
<li><strong>p41</strong> Co-create and maintain the global Marketing Excellence roadmap, prioritizing initiatives by impact and feasibility.</li>
<li><strong>p42</strong> Partner with IT and vendors to define requirements, coordinate implementations, and ensure solutions meet global business needs.</li>
<li><strong>p43</strong> Define and govern marketing metrics and dashboards, overseeing adoption KPIs, target setting, and performance reviews.</li>
<li><strong>p44</strong> Coach senior marketing leaders on using analytics and dashboards to drive decisions and continuous improvement.</li>
<li><strong>p45</strong> Design and run global change and adoption strategies for sustained tool use and business impact.</li>
<li><strong>p46</strong> Support global development and implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement.</li>
<li><strong>p47</strong> Work with commercial leadership on fact-based assessment and prioritization of seller and marketing leader capability gaps.</li>
<li><strong>p48</strong> Develop and implement plans to close capability gaps.</li>
<li><strong>p49</strong> Serve as an expert coach in marketing processes.</li>
<li><strong>p50</strong> Conduct leader and train-the-trainer coaching.</li>
<li><strong>p51</strong> Execute, facilitate, and support marketing training sessions in coordination with marketing leaders.</li>
<li><strong>?</strong> Develop and execute best practices for recruiting and retaining marketing talent.</li>
<li><strong>p53</strong> Define global marketing competencies, curriculum, onboarding, and ongoing development standards.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p53</strong> Bachelor's degree from an accredited college or university is required.</li>
<li><strong>p56</strong> Minimum 10 years of commercial experience with a minimum of 5 years marketing experience required.</li>
<li><strong>p57</strong> Demonstrated experience developing and executing Commercial Excellence Capabilities with cross-business team members.</li>
<li><strong>p58</strong> Demonstrated experience and success leading teams and influencing without authority.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p54</strong> Master's degree or MBA preferred.</li>
<li><strong>p59</strong> US-based location preferred.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p62</strong> Base pay plus performance-based incentive opportunities.</li>
<li><strong>p63</strong> Comprehensive medical, prescription-drug, and dental coverage with a Health Savings Account option.</li>
<li><strong>p64</strong> Voluntary benefits including vision, optional life, and critical-illness protection.</li>
<li><strong>p65</strong> Holistic wellness support including financial-planning tools, family-building assistance, parental leave, and Employee Assistance Program counseling.</li>
<li><strong>p66</strong> 401(k) with company match plus an additional annual retirement contribution from Eastman.</li>
<li><strong>p67</strong> Eleven paid holidays, one personal day, paid time off, and paid vacation.</li>
<li><strong>p68</strong> Access to mentorship, learning resources, and leadership programs.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p70</strong> Eastman Chemical Company is an equal opportunity employer; all qualified applicants receive consideration without regard to age, race, color, religion, sex, sexual orientation, gender identity, national origin, disability, pregnancy, veteran status, or any other protected classes.</li>
<li><strong>p85</strong> Eastman will not ask for fees, payments, or credit card information during the recruiting and hiring process.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p71", "p72", "p73", "p74", "p75", "p76", "p77", "p78", "p79", "p80", "p81", "p82", "p83", "p84", "p86"]</p>

</details>

### Model output: openai/gpt-oss-120b

[Exact raw response and usage](responses/preferred__openai_gpt-oss-120b.json)
- Finish reason: `stop`; elapsed: 14.08 seconds; input tokens: 3486; output tokens: 1782; billed cost: $0.0012396.

<details>
<summary>Read Model output: openai/gpt-oss-120b</summary>

<p><strong>Overview:</strong> Lead the global Marketing COE, build capabilities, and drive commercial results at Eastman.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p24</strong> Lead Marketing COE Leadership Team and develop a multi-year roadmap with enterprise alignment.</li>
<li><strong>p25</strong> Co‑create solutions with senior marketing leaders on key priorities.</li>
<li><strong>p26</strong> Drive implementation of key initiatives through COE LT leaders.</li>
<li><strong>p27</strong> Create and manage ongoing COE LT agenda.</li>
<li><strong>p28</strong> Track, monitor, and adjust key initiatives.</li>
<li><strong>p30</strong> Partner with functional leaders (e.g., HR) for change management, training, and communication.</li>
<li><strong>p32</strong> Develop resourcing options to accelerate progress or close gaps.</li>
<li><strong>p33</strong> Oversee central COE staff supporting COE LT activities.</li>
<li><strong>p34</strong> Provide support analysis.</li>
<li><strong>p35</strong> Conduct training, communication, coaching, and change management.</li>
<li><strong>p37</strong> Identify and evaluate external marketing best practices.</li>
<li><strong>p38</strong> Share best practices globally.</li>
<li><strong>p39</strong> Identify improvement opportunities in marketing tools and recommend enhancements.</li>
<li><strong>p40</strong> Serve as global subject‑matter lead for marketing processes, tools, methodologies, and systems.</li>
<li><strong>p41</strong> Co‑create and maintain the global Marketing Excellence roadmap, prioritizing initiatives.</li>
<li><strong>p42</strong> Partner with IT and vendors to define requirements and ensure solutions meet global needs.</li>
<li><strong>p43</strong> Define and govern marketing metrics, dashboards, adoption KPIs, and performance reviews.</li>
<li><strong>p44</strong> Coach senior marketing leaders on using analytics for decisions and continuous improvement.</li>
<li><strong>p45</strong> Design and run global change and adoption strategies for sustained tool usage.</li>
<li><strong>p46</strong> Support global development and implementation of marketing capability efforts.</li>
<li><strong>p47</strong> Assess and prioritize seller and marketing leader capability gaps.</li>
<li><strong>p48</strong> Develop and implement plans to close capability gaps.</li>
<li><strong>p49</strong> Serve as expert coach in marketing processes.</li>
<li><strong>p50</strong> Conduct leader and train‑the‑trainer coaching.</li>
<li><strong>p51</strong> Facilitate marketing training sessions with marketing leaders.</li>
<li><strong>p52</strong> Develop best practices for recruiting and retaining marketing talent and define competencies.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p53</strong> Bachelor's degree from an accredited college or university.</li>
<li><strong>p56</strong> Minimum 10 years of commercial experience, including at least 5 years of marketing experience.</li>
<li><strong>p57</strong> Experience developing and executing Commercial Excellence capabilities with cross‑business teams.</li>
<li><strong>p58</strong> Proven ability to lead teams and influence without authority.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p54</strong> Master's degree or MBA preferred.</li>
<li><strong>p59</strong> US‑based location preferred.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p60</strong> Competitive salary with performance‑based incentive opportunities.</li>
<li><strong>p63</strong> Comprehensive medical, prescription‑drug, and dental coverage with HSA option.</li>
<li><strong>p64</strong> Voluntary benefits including vision, optional life, and critical‑illness protection.</li>
<li><strong>p65</strong> Holistic wellness support: financial‑planning tools, family‑building assistance, parental leave, and EAP counseling.</li>
<li><strong>p66</strong> 401(k) with company match plus additional annual retirement contribution.</li>
<li><strong>p67</strong> Paid time off including 11 holidays, one personal day, vacation, and PTO.</li>
<li><strong>p68</strong> Access to mentorship, learning resources, and leadership development programs.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p15", "p16", "p17", "p18", "p19", "p20", "p21", "p22", "p23", "p29", "p31", "p32", "p36", "p70", "p71", "p72", "p73", "p74", "p75", "p76", "p77", "p78", "p79", "p80", "p81", "p82", "p83", "p84", "p85", "p86"]</p>

</details>

### Model output: google/gemini-2.5-flash-lite

[Exact raw response and usage](responses/preferred__google_gemini-2.5-flash-lite.json)
- Finish reason: `stop`; elapsed: 5.09 seconds; input tokens: 3399; output tokens: 1982; billed cost: $0.0011327.

<details>
<summary>Read Model output: google/gemini-2.5-flash-lite</summary>

<p><strong>Overview:</strong> Lead the Global Commercial Excellence organization to build world-class marketing capabilities and drive commercial results.</p>
<p><strong>Responsibilities</strong></p>
<ul>
<li><strong>p15</strong> Lead the global Marketing COE Leadership Team in close collaboration with senior marketing and commercial leaders from each business with multi sub-marketing disciplinary experience.</li>
<li><strong>p16</strong> Ensure convergence and commitment across businesses to common marketing processes and best practices.</li>
<li><strong>p17</strong> Develop, implement, and execute COE global &amp; regional marketing initiatives and/or select best practices within businesses to implement across the Enterprise.</li>
<li><strong>p18</strong> Set standards and expectations for talent acquisition, development, engagement, and retention in marketing roles.</li>
<li><strong>p19</strong> Work with IT to identify technological solutions to enable Eastman’s marketers to better assess external market and competitive dynamics, strength of our offerings, to win with prioritized customer segments in a more efficient and data driven way.</li>
<li><strong>p20</strong> Accelerate shift to a disciplined approach to marketing processes, metrics, and analytics.</li>
<li><strong>p21</strong> Partner with businesses leaders to support the transformation journey of Marketing Excellence.</li>
<li><strong>p22</strong> Serve as a trusted advisor and business partner to commercial leadership in the field of marketing.</li>
<li><strong>p23</strong> Serve as a key liaison with Sales, Product and Pricing, IT and other functions to develop, deliver and support marketing capability solutions.</li>
<li><strong>p24</strong> Develop a multi-year roadmap and priorities for 2026, and gain enterprise alignment on priorities through the COE LT.</li>
<li><strong>p25</strong> Develop co-created solutions with senior marketing leaders on key priorities.</li>
<li><strong>p26</strong> Drive implementation, with and through COE LT leaders, on key initiatives.</li>
<li><strong>p27</strong> Create and manage ongoing COE LT agenda.</li>
<li><strong>p28</strong> Ensure active tracking, monitoring, adjustments and actions on key initiatives.</li>
<li><strong>p30</strong> Drive change management and enable implementation with HR, including training, communication, and tool deployment.</li>
<li><strong>p32</strong> Develop resourcing options and recommendations to accelerate progress and/or close gaps when needed.</li>
<li><strong>p33</strong> Oversee central COE staff to support COE LT activities.</li>
<li><strong>p34</strong> Provide support analysis.</li>
<li><strong>p35</strong> Conduct direct training, communication, coaching, and change management.</li>
<li><strong>p36</strong> Support special projects where necessary.</li>
<li><strong>p37</strong> Consistently identify and evaluate external best practices in the marketing space.</li>
<li><strong>p38</strong> Share best practices globally.</li>
<li><strong>p39</strong> Proactively identify improvement opportunities in existing tools or needs for alternate tools to enhance the effectiveness and efficiency of marketing efforts.</li>
<li><strong>p40</strong> Serve as the global subject‑matter lead for marketing processes, tools, methodologies and systems — set standards, own lifecycle decisions, and advise on tool selection.</li>
<li><strong>p41</strong> Co‑create and maintain the global Marketing Excellence roadmap with the Marketing COE LT; prioritize initiatives by impact and feasibility and ensure clear owners, timelines, and expected measurable results.</li>
<li><strong>p42</strong> Partner with IT and vendors to define requirements, coordinate implementations and integrations, and ensure solutions meet global business needs.</li>
<li><strong>p43</strong> Define and govern marketing metrics and dashboards; oversee adoption KPIs, target setting, and regular performance reviews.</li>
<li><strong>p44</strong> Coach senior marketing leaders on using analytics and dashboards to drive decisions, performance conversations, and continuous improvement.</li>
<li><strong>p45</strong> Design and run global change and adoption strategies (communications, sponsorship, training, measurement) to ensure sustained use and business impact.</li>
<li><strong>p46</strong> Support global development and drive global implementation of marketing capability efforts, including competencies, curriculum, hiring, onboarding, and ongoing measurement.</li>
<li><strong>p47</strong> Work with commercial leadership in fact-based assessment and prioritization of seller and marketing leader capability gaps.</li>
<li><strong>p48</strong> Develop and implement plans to close gaps.</li>
<li><strong>p49</strong> Serve as an expert coach in marketing processes.</li>
<li><strong>p50</strong> Conduct leader and train the trainer coaching.</li>
<li><strong>p51</strong> Execute, facilitate, and/or support marketing training sessions in coordination with marketing leaders.</li>
<li><strong>p52</strong> Develop and execute best practices for recruiting and keeping marketing talent Define global marketing competencies, curriculum, onboarding and ongoing development standards.</li>
</ul>
<p><strong>Required qualifications</strong></p>
<ul>
<li><strong>p53</strong> Bachelors, from an accredited college or university is required.</li>
<li><strong>p56</strong> Minimum 10 years of commercial experience.</li>
<li><strong>p56</strong> Minimum 5 years marketing experience required.</li>
<li><strong>p57</strong> Experience developing and executing Commercial Excellence Capabilities with cross business team members.</li>
<li><strong>p58</strong> Demonstrated experience and success leading teams and influencing without authority.</li>
</ul>
<p><strong>Preferred qualifications</strong></p>
<ul>
<li><strong>p54</strong> Masters or MBA preferred.</li>
<li><strong>p59</strong> US-based location preferred.</li>
</ul>
<p><strong>Benefits</strong></p>
<ul>
<li><strong>p60</strong> Compensation &amp; Incentives: Base pay plus performance-based incentive opportunities.</li>
<li><strong>p63</strong> Health &amp; Wellness: Comprehensive medical, prescription-drug, and dental coverage, with a Health Savings Account option.</li>
<li><strong>p64</strong> Health &amp; Wellness: Robust menu of voluntary benefits including vision, optional life, and critical-illness protection.</li>
<li><strong>p65</strong> Health &amp; Wellness: Holistic wellness support including financial-planning tools, family-building assistance, parental leave, and confidential Employee Assistance Program counseling.</li>
<li><strong>p66</strong> Retirement &amp; Financial Strategies: 401(k) with a company match and an additional annual retirement contribution from Eastman.</li>
<li><strong>p67</strong> Time Away: Eleven paid holidays, one personal day, paid time off, and paid vacation.</li>
<li><strong>p68</strong> Growth &amp; Development: Access to mentorship, learning resources, and leadership programs.</li>
</ul>
<p><strong>Application details</strong></p>
<ul>
<li><strong>p85</strong> Eastman will not ask for fees, payments or credit card information as part of its recruiting and hiring process.</li>
<li><strong>p86</strong> If any person requests this during the recruitment process or as part of an employment offer or you have doubts regarding the legitimacy of information you’ve received, please contact us directly via eastman.com.</li>
</ul>
<p><strong>Ignored passage IDs:</strong> ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12", "p13", "p14", "p29", "p31", "p37", "p38", "p39", "p40", "p41", "p42", "p43", "p44", "p45", "p46", "p47", "p48", "p49", "p50", "p51", "p52", "p55", "p61", "p62", "p69", "p70", "p71", "p72", "p73", "p74", "p75", "p76", "p77", "p78", "p79", "p80", "p81", "p82", "p83", "p84"]</p>

</details>

## Scope and limits

The source postings and translations above are the exact inputs of the capture replay. The initial run used the same four translated passage sets and prompt construction, but its raw model message text was not retained. This replay therefore provides full inspectable output without claiming byte-for-byte identity with the initial responses. Translation quality and model classification need separate validation before publication.

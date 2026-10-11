import { useState } from 'react';
import { Help } from './CvAssessment.jsx';
import { keywordEvidence } from '../../lib/cvCustomization.js';

const SECTIONS = [
  ['summary', 'Summary', 'Refine your summary to express the strengths and achievements most relevant to this role.'],
  ['skills', 'Skills', 'Include selected, supported job keywords in your skills section. Selection alone does not change the score.'],
  ['experience', 'Work experience', 'Improve the wording of relevant responsibilities and achievements. Keep employers, job titles, dates and results accurate.'],
  ['projects', 'Projects', 'Highlight project achievements and practical impact, keeping projects separate from paid employment.'],
];
export default function CvEnhancements({ cv, job, assessment, options, onChange, sample }) {
  const [confirming, setConfirming] = useState(''), [example, setExample] = useState('');
  const patch = value => onChange({ ...options, ...value });
  const toggle = (key, value) => patch({ [key]: options[key].includes(value) ? options[key].filter(v => v !== value) : [...options[key], value] });
  const eligible = assessment.keywords.missing.filter(t => keywordEvidence(cv, t, options.confirmations));
  function confirm() {
    if (!example.trim()) return;
    patch({ confirmations: { ...options.confirmations, [confirming]: { confirmed: true, example: example.trim() } }, keywords: [...new Set([...options.keywords, confirming])] });
    setConfirming(''); setExample('');
  }
  return <div className="cv-enhancements"><section><h3>1. Choose sections to enhance</h3>{SECTIONS.map(([key, title, help]) => <div className="cv-enhancement" key={key}><div><label><input type="checkbox" checked={options.sections.includes(key)} onChange={() => toggle('sections', key)} />{title}</label><Help label={title}>{help}</Help></div>{key === 'experience' && options.sections.includes(key) ? <fieldset><legend className="sr-only">Experience editing scope</legend><label><input type="radio" name="cv-scope" checked={options.scope === 'quick'} onChange={() => patch({ scope: 'quick' })} />Quick edit · two key experiences</label><label><input type="radio" name="cv-scope" checked={options.scope === 'full'} onChange={() => patch({ scope: 'full' })} />Full edit · all experiences</label><small>{options.scope === 'quick' ? cv.experience.slice(0, 2).map(e => `${e.title} at ${e.company}`).join(' · ') : `${cv.experience.length} experiences`}</small></fieldset> : null}</div>)}<p className="cv-footnote">Your original CV stays unchanged. Unselected sections are preserved.</p>{!sample ? <p className="cv-notice">Live AI generation is not connected yet. You can assess your uploaded CV and edit a separate draft, or try the complete working sample.</p> : <p className="cv-footnote">Sample generation uses curated, source-grounded rewrites.</p>}</section>
    <section><div className="cv-keywords-heading"><h3>2. Add missing ATS keywords <small>({options.keywords.length}/{assessment.keywords.missing.length})</small></h3><button type="button" className="cv-link" onClick={() => patch({ keywords: eligible.map(t => t.label) })}>Select supported</button></div><p className="cv-footnote">These terms come from the job. Select only experience you actually have.</p>
      <div className="cv-keyword-options">{assessment.keywords.missing.length ? assessment.keywords.missing.map(t => { const evidence = keywordEvidence(cv, t, options.confirmations); return <div key={t.label}><label><input type="checkbox" checked={options.keywords.includes(t.label)} disabled={!evidence} onChange={() => toggle('keywords', t.label)} />{t.label}</label><details><summary>Why this keyword?</summary><p><strong>Job:</strong> {t.source}</p><p><strong>Your evidence:</strong> {evidence || 'Not found in this CV. Do not add it unless you have this experience.'}</p>{!evidence ? <button type="button" className="cv-link" onClick={() => { setConfirming(t.label); setExample(''); }}>I have this experience</button> : <button type="button" className="cv-link" onClick={() => patch({ confirmations: { ...options.confirmations, [t.label]: { confirmed: false } }, keywords: options.keywords.filter(k => k !== t.label) })}>This does not reflect my experience</button>}</details></div>; }) : <p>No missing terms in the available job requirements.</p>}</div>
      {confirming ? <div className="cv-confirm-experience"><strong>Confirm {confirming}</strong><label>Describe where you used this skill<textarea value={example} onChange={event => setExample(event.target.value)} maxLength={1500} /></label><button type="button" className="cv-primary" disabled={!example.trim()} onClick={confirm}>Confirm experience</button><button type="button" className="cv-link" onClick={() => setConfirming('')}>Cancel</button></div> : null}
      {assessment.keywords.matched.length ? <><h4>Already in your CV</h4><div className="cv-chips">{assessment.keywords.matched.map(t => <span className="is-matched" key={t.label}>✓ {t.label}</span>)}</div></> : null}
    </section></div>;
}

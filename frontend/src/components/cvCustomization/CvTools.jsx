import { useState } from 'react';
import { requirementsForJob } from '../../lib/cvCustomization.js';
import './cvCustomization.css';

export function CvTools({ onCustomize, onAnalyze }) {
  return <aside className="cv-tools-rail" aria-label="AI Tools"><h2>AI Tools</h2><button type="button" className="cv-tool-primary" aria-label="Customize CV" onClick={onCustomize}><span className="material-symbols-outlined">auto_awesome</span><strong>Customize CV</strong><small>Bring your relevant experience forward</small><span className="cv-tool-arrow">↗</span></button><button type="button" onClick={onAnalyze}><span className="material-symbols-outlined">query_stats</span><strong>Analyze your fit</strong><small>Review your saved-profile match</small></button><div className="cv-tool-coming"><span className="material-symbols-outlined">mail</span><strong>Build cover letter</strong><small>Coming next</small></div></aside>;
}
export function QualificationTags({ job, confirmations, onChange }) {
  const terms = requirementsForJob(job).keywords;
  const [editing, setEditing] = useState(''), [example, setExample] = useState('');
  if (!terms.length) return null;
  return <div className="cv-job-qualifications"><p>Select skills you have. Confirmations are separate from keywords present in your CV.</p><div className="cv-chips">{terms.map(t => <button type="button" key={t.label} aria-pressed={Boolean(confirmations[t.label]?.confirmed)} title={t.source} onClick={() => {
    if (confirmations[t.label]?.confirmed) onChange({ ...confirmations, [t.label]: { confirmed: false } });
    else { setEditing(t.label); setExample(''); }
  }}>{confirmations[t.label]?.confirmed ? '✓ ' : '+ '}{t.label}</button>)}</div>{editing ? <div className="cv-confirm-experience"><label>Where have you used {editing}?<textarea value={example} onChange={e => setExample(e.target.value)} maxLength={1500} /></label><button type="button" className="cv-primary" disabled={!example.trim()} onClick={() => { onChange({ ...confirmations, [editing]: { confirmed: true, example: example.trim() } }); setEditing(''); }}>Confirm experience</button><button type="button" className="cv-link" onClick={() => setEditing('')}>Cancel</button></div> : null}</div>;
}

import { useState } from 'react';
import { SECTION_LABELS } from '../../lib/cvCustomization.js';

export default function CvSideEditor({ cv, onChange }) {
  const [section, setSection] = useState('summary');
  const update = value => onChange({ ...cv, [section]: value });
  return <div className="cv-side-editor"><label>Edit section<select value={section} onChange={e => setSection(e.target.value)}>{cv.order.map(key => <option value={key} key={key}>{SECTION_LABELS[key]}</option>)}</select></label>
    {section === 'summary' ? <label>Professional summary<textarea value={cv.summary} onChange={e => update(e.target.value)} /></label>
      : ['skills', 'languages'].includes(section) ? <label>One item per line<textarea value={cv[section].join('\n')} onChange={e => update(e.target.value.split('\n'))} /></label>
        : cv[section].map((entry, index) => <fieldset key={index}><legend>{entry.company || entry.title || `Entry ${index + 1}`}</legend>{['title', 'company', 'period'].map(key => <label key={key}>{key === 'period' ? 'Dates' : key === 'company' ? 'Organization' : 'Title'}<input value={entry[key]} onChange={e => update(cv[section].map((v, i) => i === index ? { ...v, [key]: e.target.value } : v))} /></label>)}<label>Achievements · one per line<textarea value={entry.bullets.join('\n')} onChange={e => update(cv[section].map((v, i) => i === index ? { ...v, bullets: e.target.value.split('\n') } : v))} /></label></fieldset>)}
  </div>;
}

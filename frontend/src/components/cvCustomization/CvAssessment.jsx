import { useId, useState } from 'react';
import { cvText, termsIn } from '../../lib/cvCustomization.js';

export function Help({ label, children }) {
  const [pinned, setPinned] = useState(false), [hovered, setHovered] = useState(false), id = useId();
  const [position, setPosition] = useState({});
  const locate = event => { const r = event.currentTarget.getBoundingClientRect(); setPosition({ left: Math.max(12, Math.min(r.left - 60, window.innerWidth - 292)), top: window.innerHeight - r.bottom > 190 ? r.bottom + 9 : undefined, bottom: window.innerHeight - r.bottom > 190 ? undefined : window.innerHeight - r.top + 9, maxHeight: Math.max(90, window.innerHeight - r.bottom > 190 ? window.innerHeight - r.bottom - 24 : r.top - 24) }); };
  const open = pinned || hovered;
  return <span className="cv-help"><button type="button" aria-label={`${label} help`} aria-expanded={open} aria-describedby={open ? id : undefined} onMouseEnter={e => { locate(e); setHovered(true); }} onMouseLeave={() => setHovered(false)} onFocus={locate} onClick={e => { locate(e); setPinned(value => !value); setHovered(false); }} onBlur={() => { setPinned(false); setHovered(false); }}>?</button>{open ? <span id={id} role="tooltip" style={position}>{children}</span> : null}</span>;
}
export function Score({ assessment, small = false }) {
  return <div className={`cv-score ${small ? 'cv-score--small' : ''}`} style={{ '--score': `${(assessment.score || 0) * 10}%` }}><div><strong>{assessment.score == null ? '—' : assessment.score.toFixed(1)}</strong><span>/ 10</span></div><small>CV alignment</small></div>;
}
export default function CvAssessment({ cv, job, assessment }) {
  return <section className="cv-assessment">
    <header><div><p className="cv-eyebrow"><span className="material-symbols-outlined">auto_awesome</span> Your experience, in focus</p><h3>{assessment.score == null ? 'Reading the role requirements' : assessment.score >= 8 ? 'Your CV is well aligned with this role' : 'Make your relevant experience stand out'}</h3><p>See where you fit. Bring your strongest evidence forward.</p><p>{assessment.completeness} of 5 dimensions assessed <Help label="CV alignment">Runr’s content alignment estimate, not an employer ATS score or hiring probability. We compare role relevance (20%), experience (20%), industries (15%), keywords (30%) and summary (15%). Benchmarks inferred from responsibilities or seniority are labeled. Scores reflect document coverage, not proof of expertise.</Help></p></div><Score assessment={assessment} /></header>
    <div className="cv-comparison-head"><span>Compare</span><div><strong>{job.title || 'Selected job'}</strong><small>{job.company}</small></div><div><strong>{cv.name || 'Your CV'}</strong><small>{cv.headline || 'Selected baseline'}</small></div></div>
    {assessment.dimensions.map(d => <div className="cv-comparison-row" key={d.key}><div className="cv-dimension"><strong><span>{d.title}</span><small className={`cv-dimension-score cv-status--${d.status}`}>{d.value == null ? 'Analyzing' : `${Math.round(d.value * 100)}% alignment`}</small></strong><Help label={d.title}>{d.explanation}</Help></div>
      <div className="cv-dimension-content">{d.key === 'title' ? <div className="cv-two-values"><span>{job.title || 'Not specified'}</span><span>{cv.experience?.slice(0, 2).map(e => e.title).join(' / ') || cv.headline || 'Not provided'}</span></div>
        : d.key === 'years' ? <><div className="cv-two-values"><span>{job.years == null ? 'Analyzing seniority' : `${job.years}+ years`}<small>{job.yearsBasis === 'inferred' ? 'Inferred seniority benchmark' : 'From the job requirements'}</small></span><span>{assessment.years == null ? 'Add dates to assess experience' : `${assessment.years} years overall`}</span></div>{job.experienceNote ? <small>{job.experienceNote}</small> : null}</>
          : d.key === 'industry' ? <><div className="cv-chips">{job.industries?.length ? job.industries.map(t => <span className={termsIn(cvText(cv), [{ label: t }]).length ? 'is-matched' : ''} key={t}>{termsIn(cvText(cv), [{ label: t }]).length ? '✓ ' : ''}{t}</span>) : <span>Analyzing the role’s industry context</span>}</div><small>{job.industryBasis === 'inferred' ? 'Inferred from the role’s responsibilities. ' : ''}{job.industryNote}</small></>
            : d.key === 'keywords' ? <><small>{assessment.keywords.matched.length}/{job.keywords.length} present in the CV</small><div className="cv-chips">{job.keywords.map(t => <span className={assessment.keywords.matched.includes(t) ? 'is-matched' : ''} key={t.label}>{assessment.keywords.matched.includes(t) ? '✓ ' : ''}{t.label}</span>)}</div></>
              : <><p>{cv.summary || 'No professional summary yet.'}</p><small>{d.explanation}</small></>}</div>
    </div>)}
    <p className="cv-footnote">CV edits affect this document’s alignment. Your saved-profile job match stays unchanged.</p>
  </section>;
}

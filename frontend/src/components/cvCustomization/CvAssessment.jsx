import { useId, useState } from 'react';
import { cvText, termsIn } from '../../lib/cvCustomization.js';

export function Help({ label, children }) {
  const [pinned, setPinned] = useState(false), [hovered, setHovered] = useState(false), id = useId();
  const open = pinned || hovered;
  return <span className="cv-help"><button type="button" aria-label={`${label} help`} aria-expanded={open} aria-describedby={open ? id : undefined} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onClick={() => { setPinned(value => !value); setHovered(false); }} onBlur={() => { setPinned(false); setHovered(false); }}>?</button>{open ? <span id={id} role="tooltip">{children}</span> : null}</span>;
}
export function Score({ assessment, small = false }) {
  return <div className={`cv-score ${small ? 'cv-score--small' : ''}`} style={{ '--score': `${(assessment.score || 0) * 10}%` }}><div><strong>{assessment.score == null ? '—' : assessment.score.toFixed(1)}</strong><span>/ 10</span></div><small>CV alignment</small></div>;
}
export default function CvAssessment({ cv, job, assessment }) {
  return <section className="cv-assessment">
    <header><div><p className="cv-eyebrow">Your starting point</p><h3>{assessment.score == null ? 'More detail needed to assess this CV' : assessment.score >= 8 ? 'Your CV is well aligned with this role' : 'Make your relevant experience stand out'}</h3><p>{assessment.completeness} of 5 dimensions assessed <Help label="CV alignment">Runr’s transparent content heuristic, not an employer ATS score or hiring probability. We compare role relevance (20%), experience (20%), industries (15%), keywords (30%) and summary (15%). Unspecified requirements are excluded.</Help></p></div><Score assessment={assessment} /></header>
    <div className="cv-comparison-head"><span>Compare</span><div><strong>{job.title || 'Selected job'}</strong><small>{job.company}</small></div><div><strong>{cv.name || 'Your CV'}</strong><small>{cv.headline || 'Selected baseline'}</small></div></div>
    {assessment.dimensions.map(d => <div className="cv-comparison-row" key={d.key}><div className="cv-dimension"><strong>{d.title}</strong><span className={`cv-status cv-status--${d.status}`} aria-label={d.status}>{({ matched: '✓', partial: '◐', missing: '×', unknown: '—' })[d.status]}</span><Help label={d.title}>{d.explanation}</Help></div>
      <div className="cv-dimension-content">{d.key === 'title' ? <div className="cv-two-values"><span>{job.title || 'Not specified'}</span><span>{cv.experience?.slice(0, 2).map(e => e.title).join(' / ') || cv.headline || 'Not provided'}</span></div>
        : d.key === 'years' ? <><div className="cv-two-values"><span>{job.years == null ? 'Not specified' : `${job.years}+ years`}</span><span>{assessment.years == null ? 'No dated experience' : `${assessment.years} years overall`}</span></div>{job.experienceNote ? <small>{job.experienceNote}</small> : null}</>
          : d.key === 'industry' ? <div className="cv-chips">{job.industries?.length ? job.industries.map(t => <span className={termsIn(cvText(cv), [{ label: t }]).length ? 'is-matched' : ''} key={t}>{termsIn(cvText(cv), [{ label: t }]).length ? '✓ ' : ''}{t}</span>) : <span>No explicit requirements available</span>}</div>
            : d.key === 'keywords' ? <><small>{assessment.keywords.matched.length}/{job.keywords.length} present in the CV</small><div className="cv-chips">{job.keywords.map(t => <span className={assessment.keywords.matched.includes(t) ? 'is-matched' : ''} key={t.label}>{assessment.keywords.matched.includes(t) ? '✓ ' : ''}{t.label}</span>)}</div></>
              : <><p>{cv.summary || 'No professional summary yet.'}</p><small>{d.explanation}</small></>}</div>
    </div>)}
    <p className="cv-footnote">CV edits affect this document’s alignment. Your saved-profile job match stays unchanged.</p>
  </section>;
}

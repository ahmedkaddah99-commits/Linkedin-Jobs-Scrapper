import { useEffect, useRef, useState } from 'react';
import { SECTION_LABELS } from '../../lib/cvCustomization.js';

function Editable({ value, label, onChange, as: Tag = 'span', className = '' }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current && ref.current.textContent !== String(value || '')) ref.current.textContent = value || ''; }, [value]);
  return <Tag ref={ref} className={`cv-inline ${className}`} contentEditable suppressContentEditableWarning role="textbox" aria-label={label} tabIndex={0} data-placeholder={label}
    onPaste={event => { event.preventDefault(); const text = event.clipboardData.getData('text/plain'); const selection = window.getSelection(); if (!selection?.rangeCount) return; const range = selection.getRangeAt(0); range.deleteContents(); const node = document.createTextNode(text); range.insertNode(node); range.setStartAfter(node); range.collapse(true); selection.removeAllRanges(); selection.addRange(range); }}
    onBlur={event => { const text = event.currentTarget.textContent.trim(); if (text !== String(value || '')) onChange(text); }} />;
}

function MoveButtons({ index, total, onMove, onRemove, label }) {
  return <span className="cv-inline-tools"><button type="button" title="Move up" aria-label={`Move ${label} up`} disabled={index === 0} onClick={() => onMove(-1)}>↑</button><button type="button" title="Move down" aria-label={`Move ${label} down`} disabled={index === total - 1} onClick={() => onMove(1)}>↓</button><button type="button" title="Remove" aria-label={`Remove ${label}`} onClick={onRemove}>×</button></span>;
}

export default function CvDocument({ cv, onChange, style }) {
  const [pendingRemoval, setPendingRemoval] = useState(null);
  const replace = (key, value) => onChange({ ...cv, [key]: value });
  const updateEntry = (key, index, patch) => replace(key, cv[key].map((e, i) => i === index ? { ...e, ...patch } : e));
  const move = (items, index, delta) => { const next = [...items]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; return next; };
  const removeEntry = (key, index) => { replace(key, cv[key].filter((_, i) => i !== index)); setPendingRemoval(null); };
  return <article className={`cv-paper cv-paper--${style.font}`} style={{ '--cv-accent': style.accent }} aria-label="Editable CV">
    <Editable as="h1" value={cv.name} label="Full name" onChange={value => replace('name', value)} />
    <Editable as="p" className="cv-paper-headline" value={cv.headline} label="Headline" onChange={value => replace('headline', value)} />
    <div className="cv-paper-contact">{['location', 'email', 'phone', 'linkedin_url', 'website', 'github_url'].map(key => <Editable key={key} value={cv[key]} label={{ linkedin_url: 'LinkedIn URL', github_url: 'GitHub URL' }[key] || key[0].toUpperCase() + key.slice(1)} onChange={value => replace(key, value)} />)}</div>
    {(cv.order || Object.keys(SECTION_LABELS)).map((key, sectionIndex) => <section id={`cv-section-${key}`} className="cv-paper-section" key={key}>
      <header className="cv-section-heading"><h2>{SECTION_LABELS[key]}</h2><MoveButtons index={sectionIndex} total={cv.order.length} label={`${SECTION_LABELS[key]} section`} onMove={delta => replace('order', move(cv.order, sectionIndex, delta))} onRemove={() => replace('order', cv.order.filter(k => k !== key))} /></header>
      {key === 'summary' ? <Editable as="p" value={cv.summary} label="Professional summary" onChange={value => replace(key, value)} />
        : ['skills', 'languages'].includes(key) ? <Editable as="p" value={(cv[key] || []).join(' · ')} label={SECTION_LABELS[key]} onChange={value => replace(key, value.split(/\s*[·;\n]\s*/).filter(Boolean))} />
          : <>{(cv[key] || []).map((entry, i) => <div className="cv-paper-entry" key={`${key}-${i}`}>
            <div className="cv-entry-heading"><Editable as="strong" value={entry.company} label={`${SECTION_LABELS[key]} ${i + 1} organization`} onChange={value => updateEntry(key, i, { company: value })} /><Editable value={entry.period} label={`${SECTION_LABELS[key]} ${i + 1} dates`} onChange={value => updateEntry(key, i, { period: value })} /><MoveButtons index={i} total={cv[key].length} label={`${key} ${i + 1}`} onMove={delta => replace(key, move(cv[key], i, delta))} onRemove={() => setPendingRemoval({ key, index: i })} /></div>
            <Editable as="p" className="cv-paper-role" value={entry.title} label={`${SECTION_LABELS[key]} ${i + 1} title`} onChange={value => updateEntry(key, i, { title: value })} />
            {pendingRemoval?.key === key && pendingRemoval.index === i ? <div className="cv-remove-confirm">Remove this entry?<button type="button" onClick={() => removeEntry(key, i)}>Remove</button><button type="button" onClick={() => setPendingRemoval(null)}>Cancel</button></div> : null}
            <ul>{entry.bullets.map((bullet, bi) => <li key={bi}><Editable value={bullet} label={`${key} ${i + 1} bullet ${bi + 1}`} onChange={value => updateEntry(key, i, { bullets: entry.bullets.map((b, index) => index === bi ? value : b) })} /><MoveButtons index={bi} total={entry.bullets.length} label={`${key} ${i + 1} bullet ${bi + 1}`} onMove={delta => updateEntry(key, i, { bullets: move(entry.bullets, bi, delta) })} onRemove={() => updateEntry(key, i, { bullets: entry.bullets.filter((_, index) => index !== bi) })} /></li>)}</ul>
            <button type="button" className="cv-add-inline" onClick={() => updateEntry(key, i, { bullets: [...entry.bullets, ''] })}>+ Bullet</button>
          </div>)}<button type="button" className="cv-add-inline" onClick={() => replace(key, [...(cv[key] || []), { title: '', company: '', period: '', bullets: [''] }])}>+ Add {key === 'experience' ? 'experience' : key === 'education' ? 'education' : key === 'projects' ? 'project' : 'section'}</button></>}
    </section>)}
    {Object.keys(SECTION_LABELS).some(key => !cv.order.includes(key)) ? <label className="cv-restore-section">Add section<select aria-label="Add CV section" value="" onChange={event => { if (event.target.value) replace('order', [...cv.order, event.target.value]); }}><option value="">Choose section</option>{Object.keys(SECTION_LABELS).filter(key => !cv.order.includes(key)).map(key => <option value={key} key={key}>{SECTION_LABELS[key]}</option>)}</select></label> : null}
  </article>;
}

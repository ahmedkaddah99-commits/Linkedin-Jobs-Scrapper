import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal, flushSync } from 'react-dom';
import { SAMPLE_CV, SAMPLE_JOB } from '../../data/cvCustomizationSample.js';
import { assessCv, buildCvExport, draftKey, generateSampleCv, keywordEvidence, normalizeCv, readDraft, requirementsForJob, saveDraft, SECTION_LABELS } from '../../lib/cvCustomization.js';
import CvAssessment, { Score } from './CvAssessment.jsx';
import CvEnhancements from './CvEnhancements.jsx';
import CvDocument from './CvDocument.jsx';
import CvSideEditor from './CvSideEditor.jsx';
import './cvCustomization.css';

const readableSection = value => typeof value === 'string' ? value : value.map(item => typeof item === 'string' ? item : [item.title, ...item.bullets].join('\n')).join('\n\n');
const initialOptions = () => ({ sections: ['summary', 'skills', 'experience', 'projects'], keywords: [], scope: 'quick', confirmations: {} });
export default function CvCustomization({ job, userId, request, onClose, initialConfirmations = {} }) {
  const modal = useRef(null), generation = useRef(0);
  const [assets, setAssets] = useState([]), [assetId, setAssetId] = useState(''), [source, setSource] = useState(null), [sourceRevision, setSourceRevision] = useState(0);
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [sample, setSample] = useState(false);
  const [aiRequirements, setAiRequirements] = useState(null), [analyzing, setAnalyzing] = useState(false), [generating, setGenerating] = useState(false);
  const [step, setStep] = useState(0), [draft, setDraft] = useState(null), [history, setHistory] = useState([]), [options, setOptions] = useState(initialOptions);
  const [style, setStyle] = useState({ font: 'sans', accent: '#164e63' }), [saved, setSaved] = useState(true), [reviewTab, setReviewTab] = useState('changes');
  const requirements = useMemo(() => sample ? SAMPLE_JOB : { ...requirementsForJob(job), ...aiRequirements }, [sample, job, aiRequirements]);
  const baseline = useMemo(() => source ? assessCv(source, requirements) : null, [source, requirements]);
  const assessment = useMemo(() => draft ? assessCv(draft, requirements) : null, [draft, requirements]);
  // Include the originating job even when the sample scenario is used.
  const key = draftKey(userId, requirementsForJob(job), sample ? 'sample-v1' : assetId, sourceRevision);
  function close() {
    // Commit a focused text field before unmounting its editor (including Escape).
    flushSync(() => document.activeElement?.blur());
    onClose();
  }

  useEffect(() => {
    const previous = document.activeElement, bodyOverflow = document.body.style.overflow;
    const siblings = [...document.body.children].filter(node => node !== modal.current?.parentElement && node.tagName !== 'SCRIPT');
    const inertBefore = siblings.map(node => node.inert);
    siblings.forEach(node => { node.inert = true; });
    document.body.style.overflow = 'hidden';
    modal.current?.querySelector('button')?.focus();
    function keyboard(event) {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab') return;
      const focusable = [...modal.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),textarea,select,[tabindex="0"],summary')].filter(el => el.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener('keydown', keyboard);
    return () => { generation.current++; document.removeEventListener('keydown', keyboard); document.body.style.overflow = bodyOverflow; siblings.forEach((node, i) => { node.inert = inertBefore[i]; }); previous?.focus(); };
  }, []);

  useEffect(() => {
    let active = true;
    request('/documents?limit=500&include_preview_profile=false', { timeoutMs: 30000 }).then(result => {
      if (active) setAssets((result.documents || []).filter(item => item.asset_id && (item.asset_kind === 'workspace_cv' || /cv|resume/i.test(item.document_type || ''))));
    }).catch(e => { if (active) setError(e.message || 'Unable to load your CVs.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [request]);

  useEffect(() => {
    if (!source) return;
    setSaved(saveDraft(key, { draft, options, history: history.slice(-25), style, step }));
  }, [key, source, draft, options, history, style, step]);

  function installSource(cv, id, revision, isSample) {
    const identity = draftKey(userId, requirementsForJob(job), isSample ? 'sample-v1' : id, revision);
    const restored = readDraft(identity);
    setSource(cv); setAssetId(id); setSourceRevision(revision); setSample(isSample);
    const req = isSample ? SAMPLE_JOB : requirementsForJob(job);
    const next = initialOptions();
    next.confirmations = isSample ? {} : initialConfirmations;
    next.keywords = assessCv(cv, req).keywords.missing.filter(t => keywordEvidence(cv, t, next.confirmations)).map(t => t.label);
    setOptions(restored?.options || next); setDraft(restored?.draft || null); setHistory(restored?.history || []);
    setStyle(restored?.style || { font: 'sans', accent: '#164e63' }); setStep(restored?.draft ? 2 : 0); setError('');
  }
  async function selectAsset(id) {
    const sequence = ++generation.current;
    setLoading(true); setError(''); setSource(null); setDraft(null); setAssetId(id); setSample(false); setAiRequirements(null); setAnalyzing(false); setGenerating(false);
    try {
      const result = await request(`/documents/assets/${encodeURIComponent(id)}/editor`, { timeoutMs: 60000 });
      if (sequence !== generation.current) return;
      if (!result.editor?.profile) throw new Error('This CV has no readable profile yet. Finish extraction in Documents.');
      installSource(normalizeCv(result.editor.profile), id, result.editor.revision || 0, false);
      setLoading(false); setAnalyzing(true);
      const analysis = await request('/cv-customization/analyze', { method: 'POST', body: { asset_id: id, job_id: job.id, revision: result.editor.revision || 0 }, timeoutMs: 120000 });
      if (sequence !== generation.current) return;
      if (!analysis.requirements) throw new Error('We could not analyze this job. Select the CV again to retry.');
      setAiRequirements(analysis.requirements);
    } catch (e) { if (sequence === generation.current) setError(e.message || 'Unable to read this CV.'); }
    finally { if (sequence === generation.current) { setLoading(false); setAnalyzing(false); } }
  }
  function openSample() { generation.current++; setLoading(false); setAnalyzing(false); setGenerating(false); setAiRequirements(null); installSource(JSON.parse(JSON.stringify(SAMPLE_CV)), 'sample-v1', 1, true); }
  function edit(next) { setHistory(previous => [...previous.slice(-24), draft]); setDraft(next); }
  async function generate() {
    const sequence = ++generation.current;
    setGenerating(true); setError('');
    try {
      const result = sample ? { draft: generateSampleCv(source, requirements, options) } : await request('/cv-customization/generate', { method: 'POST', body: { asset_id: assetId, job_id: job.id, revision: sourceRevision, options }, timeoutMs: 120000 });
      if (sequence !== generation.current) return;
      if (!result.draft) throw new Error('Your CV could not be generated. Please retry.');
      if (draft) setHistory(previous => [...previous.slice(-24), draft]);
      setDraft(result.draft); setStep(2);
      if (result.requirements) setAiRequirements(result.requirements);
    } catch (e) { if (sequence === generation.current) setError(e.message || 'Generation failed. Please retry.'); }
    finally { if (sequence === generation.current) setGenerating(false); }
  }
  function exportCv(print) {
    const html = buildCvExport(draft, style);
    if (print) {
      const tab = window.open('', '_blank');
      if (!tab) { setError('Allow pop-ups to open the print preview.'); return; }
      tab.opener = null; tab.document.open(); tab.document.write(html); tab.document.close(); tab.focus(); tab.setTimeout(() => tab.print(), 400);
    } else {
      const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${(draft.name || 'Candidate').replace(/[^a-z0-9]+/gi, '-')}-CV.html`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }
  const changed = draft && source ? Object.keys(SECTION_LABELS).filter(k => JSON.stringify(draft[k]) !== JSON.stringify(source[k])) : [];
  return createPortal(<div className="cv-overlay" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}><section className={`cv-drawer ${step === 2 ? 'cv-drawer--review' : ''}`} ref={modal} role="dialog" aria-modal="true" aria-labelledby="cv-customize-title">
    <header className="cv-drawer-header"><button type="button" className="cv-close" aria-label="Close customization" onClick={close}>×</button><div><h2 id="cv-customize-title">Customize CV</h2><small>{requirements.title} · {requirements.company}</small></div>{sample ? <span className="cv-sample-label">Working sample · anonymized CV</span> : null}</header>
    <nav className="cv-steps" aria-label="Customization steps">{['Compare your CV', 'Choose enhancements', 'Review your CV'].map((title, i) => <button type="button" key={title} aria-current={step === i ? 'step' : undefined} disabled={!source || (i === 2 && !draft)} onClick={() => setStep(i)}><span>{i + 1}</span>{title}</button>)}</nav>
    <div className="cv-source-bar"><label>Baseline CV<select aria-label="Baseline CV" value={sample ? 'sample-v1' : assetId} onChange={event => event.target.value === 'sample-v1' ? openSample() : event.target.value && selectAsset(event.target.value)}><option value="">Select your CV</option>{assets.map(asset => <option key={asset.asset_id} value={asset.asset_id}>{asset.filename || asset.name || asset.display_name || 'Uploaded CV'}</option>)}{sample ? <option value="sample-v1">Working sample — Alex Morgan</option> : null}</select></label><button type="button" className="cv-link" onClick={openSample}>Try working sample</button><a href="/documents">Upload / manage CVs</a>{source ? <span role="status">{saved ? 'Saved on this device' : 'Device storage unavailable — download to keep edits'}</span> : null}</div>
    {error ? <p role="alert" className="cv-error">{error}</p> : null}
    {analyzing || generating ? <div className="cv-ai-progress" role="status"><span className="material-symbols-outlined">auto_awesome</span><div><strong>{generating ? 'Tailoring your CV to this role' : 'Reading the full role and your experience'}</strong><small>{generating ? 'Refining your selected sections using your career evidence…' : 'Identifying requirements, seniority and supported keywords…'}</small></div><span className="cv-progress-dots">•••</span></div> : null}
    <div className="cv-drawer-body">{loading ? <p className="cv-empty" role="status">Reading your CVs…</p> : !source ? <div className="cv-empty"><span className="material-symbols-outlined">description</span><h3>Start with your experience</h3><p>Select an uploaded CV to compare it with this job, or explore the complete working sample.</p><button className="cv-primary" type="button" onClick={openSample}>Explore sample CV</button></div>
      : step === 0 ? <CvAssessment cv={source} job={requirements} assessment={baseline} />
        : step === 1 ? <CvEnhancements cv={source} job={requirements} assessment={baseline} options={options} onChange={setOptions} sample={sample} />
          : <div className="cv-review-layout"><aside className="cv-review-sidebar"><div className="cv-review-tabs">{[['changes', 'Changes'], ['edit', 'Edit'], ['sections', 'Sections'], ['style', 'Style']].map(([id, title]) => <button type="button" key={id} aria-pressed={reviewTab === id} onClick={() => setReviewTab(id)}>{title}</button>)}</div>
            {reviewTab === 'changes' ? <><Score assessment={assessment} /><p className="cv-score-change">{baseline.score?.toFixed(1) ?? '—'} → {assessment.score?.toFixed(1) ?? '—'} <small>Baseline → current CV</small></p><h3>What changed</h3>{changed.length ? <div>{changed.map(key => <details className="cv-change-detail" key={key}><summary>{SECTION_LABELS[key]} updated</summary><p><strong>Original</strong><br /><del>{readableSection(source[key])}</del></p><p><strong>Current CV</strong><br /><ins>{readableSection(draft[key])}</ins></p></details>)}</div> : <p>No content changes yet.</p>}<h3>Still worth reviewing</h3><div className="cv-chips">{assessment.keywords.missing.map(t => <span key={t.label}>{t.label}</span>)}</div><p className="cv-footnote">Missing keywords are not automatically missing experience. Keep only truthful claims.</p><button type="button" className="cv-link" onClick={() => setStep(1)}>Adjust enhancements</button></>
              : reviewTab === 'edit' ? <CvSideEditor cv={draft} onChange={edit} /> : reviewTab === 'sections' ? <nav aria-label="CV sections">{draft.order.map(key => <a href={`#cv-section-${key}`} key={key}>{SECTION_LABELS[key]}</a>)}</nav>
                : <div className="cv-style-controls"><label>Typography<select value={style.font} onChange={e => setStyle({ ...style, font: e.target.value })}><option value="sans">Modern sans</option><option value="serif">Classic serif</option></select></label><label>Accent color<input type="color" value={style.accent} onChange={e => setStyle({ ...style, accent: e.target.value })} /></label></div>}
            <p className="cv-footnote">Click text on the CV to edit. Your baseline stays unchanged.</p><button type="button" className="cv-secondary" disabled={!history.length} onClick={() => { setDraft(history.at(-1)); setHistory(history.slice(0, -1)); }}>Undo edit</button>
          </aside><div className="cv-paper-stage"><CvDocument cv={draft} onChange={edit} style={style} /></div></div>}
    </div>
    {source ? <footer className="cv-drawer-footer">{step > 0 ? <button type="button" className="cv-secondary" disabled={generating} onClick={() => setStep(step - 1)}>← Back</button> : <span className="cv-footnote">A stronger CV starts with truthful evidence.</span>}{step === 0 ? <button type="button" className="cv-primary" disabled={analyzing} onClick={() => setStep(1)}>Customize this CV</button> : step === 1 ? <button type="button" className="cv-primary" disabled={generating || analyzing || !options.sections.length} onClick={generate}>{generating ? 'Generating your CV…' : sample ? 'Generate sample CV' : 'Generate tailored CV'}</button> : <div><button type="button" className="cv-secondary" onClick={() => exportCv(false)}>Download CV</button><button type="button" className="cv-primary" onClick={() => exportCv(true)}>Print / Save PDF</button></div>}</footer> : null}
  </section></div>, document.body);
}

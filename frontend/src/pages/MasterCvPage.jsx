import { useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import {
  countMasterCvExtraEvidence,
  findMasterCvBullet,
  getMasterCvGuidance,
  shouldShowMasterCvIntro,
  visibleMasterCvBullets,
  MASTER_CV_INTRO_STORAGE_KEY,
} from "../lib/masterCv";

function Icon({ children, className = "" }) {
  return <span className={["material-symbols-outlined", className].join(" ")}>{children}</span>;
}

function Score({ value }) {
  const tone = value >= 85 ? "strong" : value >= 72 ? "good" : "develop";
  return <span className={["master-cv-score", `master-cv-score--${tone}`].join(" ")}>{value}</span>;
}

function BulletRow({ bullet, isSelected, onSelect }) {
  return (
    <button
      aria-label={`Select achievement: ${bullet.text}`}
      className={["master-cv-bullet-row", bullet.extra ? "is-extra" : "", isSelected ? "is-selected" : ""].join(" ")}
      onClick={() => onSelect(bullet.id)}
      type="button"
    >
      <span aria-hidden="true" className="master-cv-bullet-dot" />
      <span className="master-cv-bullet-copy">{bullet.text}</span>
      <span className="master-cv-bullet-meta">
        {bullet.extra ? <span className="master-cv-extra-label">Extra evidence</span> : null}
        <Score value={bullet.score} />
      </span>
    </button>
  );
}

function AchievementComposer({ label, busy, onCancel, onSave }) {
  const [value, setValue] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    if (!value.trim() || busy) return;
    onSave(value.trim());
  }

  return (
    <form className="master-cv-composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor={`master-cv-composer-${label}`}>{label}</label>
      <textarea
        autoFocus
        disabled={busy}
        id={`master-cv-composer-${label}`}
        onChange={(event) => setValue(event.target.value)}
        placeholder="What did you do? Who did it help? What changed as a result?"
        value={value}
      />
      <div className="master-cv-composer__footer">
        <span>Try: action + context + outcome</span>
        <button className="master-cv-text-button" disabled={busy} onClick={onCancel} type="button">Cancel</button>
        <button className="master-cv-primary master-cv-primary--small" disabled={busy || !value.trim()} type="submit">
          {busy ? "Saving..." : "Add to Master CV"}
        </button>
      </div>
    </form>
  );
}

function Entry({
  composerEntryId,
  entry,
  expanded,
  mutationEntryId,
  onAdd,
  onCancelComposer,
  onOpenComposer,
  onSelectBullet,
  onToggleExpanded,
  selectedBulletId,
  view,
}) {
  const isCollapsed = Boolean(entry.collapsed && !expanded);
  const visibleBullets = isCollapsed ? [] : visibleMasterCvBullets(entry, view);
  const extraCount = (entry.bullets || []).filter((bullet) => bullet.extra).length;
  const composerLabel = entry.kind === "project"
    ? "Add project achievement"
    : view === "extra"
      ? "Add extra evidence"
      : "Add another achievement";

  return (
    <div className={["master-cv-entry", isCollapsed ? "is-collapsed" : ""].join(" ")}>
      <div className="master-cv-entry__head">
        <div>
          <h4>{entry.title}</h4>
          <p>{entry.organisation || "Independent experience"}</p>
        </div>
        <span>{entry.dates}</span>
      </div>

      {isCollapsed ? (
        <p className="master-cv-collapsed-copy">
          {(entry.bullets || []).length} achievements · {extraCount} extra evidence point{extraCount === 1 ? "" : "s"}
        </p>
      ) : (
        <div className="master-cv-bullets">
          {visibleBullets.map((bullet) => (
            <BulletRow
              bullet={bullet}
              isSelected={selectedBulletId === bullet.id}
              key={bullet.id}
              onSelect={onSelectBullet}
            />
          ))}
          {!visibleBullets.length ? <p className="master-cv-empty-copy">No extra evidence here yet. Add one while the details are fresh.</p> : null}
        </div>
      )}

      {composerEntryId === entry.id ? (
        <AchievementComposer
          busy={mutationEntryId === entry.id}
          label={composerLabel}
          onCancel={onCancelComposer}
          onSave={(text) => onAdd(entry.id, text)}
        />
      ) : (
        <button className="master-cv-add-bullet" onClick={() => onOpenComposer(entry)} type="button">
          <span aria-hidden="true">+</span> {composerLabel}
        </button>
      )}

      {entry.collapsed ? (
        <button className="master-cv-expand-button" onClick={() => onToggleExpanded(entry.id)} type="button">
          {expanded ? "Hide experience" : "Show experience"} <span aria-hidden="true">{expanded ? "⌃" : "⌄"}</span>
        </button>
      ) : null}
    </div>
  );
}

function WritingGuidance({ bullet, busy, onImprove, onTailor, notice }) {
  if (!bullet) {
    return (
      <aside aria-label="Runr writing guidance" className="master-cv-coach-panel">
        <span className="master-cv-eyebrow">Runr writing guidance</span>
        <h3>Select an achievement</h3>
        <p className="master-cv-coach-summary">Select a bullet to see guidance on action, context, and impact.</p>
      </aside>
    );
  }
  const guidance = bullet.guidance || getMasterCvGuidance(bullet);

  return (
    <aside aria-label="Runr writing guidance" className="master-cv-coach-panel">
      <div className="master-cv-coach-title">
        <div>
          <span className="master-cv-eyebrow">Runr writing guidance</span>
          <h3>{guidance.title}</h3>
        </div>
        <Score value={guidance.score} />
      </div>
      <p className="master-cv-coach-summary">{guidance.summary}</p>
      <div className="master-cv-quality-list">
        {guidance.checks.map((check) => (
          <div key={check.label}>
            <span className={check.state === "pass" ? "master-cv-check" : "master-cv-warn"}>{check.state === "pass" ? "✓" : "!"}</span>
            <p><b>{check.label}</b><br />{check.detail}</p>
          </div>
        ))}
      </div>
      <div className="master-cv-rewrite-card">
        <span>One way to make it sharper</span>
        <p>{guidance.suggestion}</p>
        <button disabled={busy} onClick={onImprove} type="button">{busy ? "Reviewing..." : "Improve with Runr"}</button>
      </div>
      {notice ? <p className="master-cv-coach-notice" role="status">{notice}</p> : null}
      <div className="master-cv-match-note">
        <Icon>target</Icon>
        <p><b>How Runr will use this</b><br />{guidance.use}<br /><button className="master-cv-inline-action" onClick={onTailor} type="button">Find relevant material</button></p>
      </div>
    </aside>
  );
}

function TailorDialog({ busy, onClose, onSearch, result }) {
  const [targetText, setTargetText] = useState("");
  function submit(event) {
    event.preventDefault();
    if (!targetText.trim() || busy) return;
    onSearch(targetText.trim());
  }
  return (
    <div className="master-cv-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <form aria-labelledby="master-cv-tailor-title" aria-modal="true" className="master-cv-intro-modal master-cv-tailor-modal" onSubmit={submit} role="dialog">
        <button aria-label="Close tailoring" className="master-cv-close" disabled={busy} onClick={onClose} type="button"><Icon>close</Icon></button>
        <div className="master-cv-eyebrow">Grounded tailoring</div>
        <h2 id="master-cv-tailor-title">Find relevant material</h2>
        <p className="master-cv-modal-lead">Paste a job description or opportunity notes. Runr will rank matching Master CV bullets without inventing experience.</p>
        <textarea autoFocus className="master-cv-tailor-input" disabled={busy} onChange={(event) => setTargetText(event.target.value)} placeholder="Paste the role requirements or opportunity context..." value={targetText} />
        <button className="master-cv-primary master-cv-modal-action" disabled={busy || !targetText.trim()} type="submit">{busy ? "Finding matches..." : "Find matches"}</button>
        {result ? <div className="master-cv-tailor-results"><b>{result.total_matches} matching bullet{result.total_matches === 1 ? "" : "s"}</b>{result.matches.length ? result.matches.map((match) => <div key={match.bullet.id}><span>{match.entry_title}</span><p>{match.bullet.text}</p><small>{match.matched_terms.join(", ")} · {match.relevance_score}% relevant</small></div>) : <p>No matching Master CV material was found.</p>}</div> : null}
      </form>
    </div>
  );
}

function IntroDialog({ onClose }) {
  return (
    <div className="master-cv-modal-backdrop">
      <div aria-labelledby="master-cv-intro-title" aria-modal="true" className="master-cv-intro-modal" role="dialog">
        <button aria-label="Close introduction" className="master-cv-close" onClick={onClose} type="button"><Icon>close</Icon></button>
        <div aria-hidden="true" className="master-cv-modal-badge"><Icon>auto_awesome</Icon></div>
        <div className="master-cv-eyebrow">Introducing your Master CV</div>
        <h2 id="master-cv-intro-title">Your career is bigger than one CV.</h2>
        <p className="master-cv-modal-lead">A standard CV only has room for a few highlights. Your Master CV keeps the valuable work that would otherwise be left out.</p>
        <div className="master-cv-benefit-grid">
          <div><span>01</span><p><b>Capture the full picture</b><br />Keep the projects, collaborations, responsibilities and outcomes that your job title does not show.</p></div>
          <div><span>02</span><p><b>Build on what you already have</b><br />Add extra achievements beneath every role or project without changing your uploaded CV.</p></div>
          <div><span>03</span><p><b>Tailor without starting again</b><br />Runr can select the strongest relevant Master CV material for an opportunity.</p></div>
          <div><span>04</span><p><b>Write with confidence</b><br />Get guidance on clarity, contribution, and impact while you write.</p></div>
        </div>
        <div className="master-cv-modal-example" aria-label="CV bullet becomes stronger tailored CV">
          <span>Your CV bullet</span><b>+</b><span className="is-extra">Relevant extra evidence</span><b>→</b><strong>A stronger tailored CV</strong>
        </div>
        <button className="master-cv-primary master-cv-modal-action" onClick={onClose} type="button">Explore my Master CV</button>
        <button className="master-cv-quiet-button" onClick={onClose} type="button">I'll do this later</button>
      </div>
    </div>
  );
}

function ExperienceDialog({ busy, onClose, onSave }) {
  const [form, setForm] = useState({ kind: "work", title: "", organisation: "", dates: "" });
  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }
  function submit(event) {
    event.preventDefault();
    if (!form.title.trim() || busy) return;
    onSave(form);
  }
  return (
    <div className="master-cv-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <form aria-labelledby="master-cv-add-title" aria-modal="true" className="master-cv-intro-modal master-cv-experience-modal" onSubmit={submit} role="dialog">
        <button aria-label="Close add experience" className="master-cv-close" disabled={busy} onClick={onClose} type="button"><Icon>close</Icon></button>
        <div className="master-cv-eyebrow">Grow your career record</div>
        <h2 id="master-cv-add-title">Add experience</h2>
        <p className="master-cv-modal-lead">Add the role or project now, then capture achievements underneath it.</p>
        <label>Type<select disabled={busy} onChange={(event) => update("kind", event.target.value)} value={form.kind}><option value="work">Work experience</option><option value="project">Project</option></select></label>
        <label>Title<input autoFocus disabled={busy} onChange={(event) => update("title", event.target.value)} placeholder="Product Manager" value={form.title} /></label>
        <label>Organisation<input disabled={busy} onChange={(event) => update("organisation", event.target.value)} placeholder="Company or independent work" value={form.organisation} /></label>
        <label>Dates<input disabled={busy} onChange={(event) => update("dates", event.target.value)} placeholder="2024 - Present" value={form.dates} /></label>
        <button className="master-cv-primary master-cv-modal-action" disabled={busy || !form.title.trim()} type="submit">{busy ? "Saving..." : "Add to Master CV"}</button>
      </form>
    </div>
  );
}

function closeIntroStorage() {
  try {
    window.sessionStorage.setItem(MASTER_CV_INTRO_STORAGE_KEY, "1");
  } catch {
    // Session storage is optional; the dialog still closes for this render.
  }
}

function shouldShowIntro() {
  if (typeof window === "undefined") return true;
  try {
    return shouldShowMasterCvIntro(window.sessionStorage.getItem(MASTER_CV_INTRO_STORAGE_KEY));
  } catch {
    return true;
  }
}

function savedLabel(updatedAt) {
  if (!updatedAt) return "Not saved";
  const timestamp = Date.parse(updatedAt);
  if (!Number.isFinite(timestamp)) return "Saved";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  return seconds < 60 ? "Saved just now" : `Saved ${new Date(timestamp).toLocaleString()}`;
}

export default function MasterCvPage() {
  const { isConnected, request } = useSession();
  const [masterCv, setMasterCv] = useState(null);
  const [showIntro, setShowIntro] = useState(shouldShowIntro);
  const [view, setView] = useState("all");
  const [selectedBulletId, setSelectedBulletId] = useState("");
  const [expandedEntryIds, setExpandedEntryIds] = useState([]);
  const [composerEntryId, setComposerEntryId] = useState("");
  const [experienceDialogOpen, setExperienceDialogOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mutationEntryId, setMutationEntryId] = useState("");
  const [experienceSaving, setExperienceSaving] = useState(false);
  const [coachNotice, setCoachNotice] = useState("");
  const [improveBusy, setImproveBusy] = useState(false);
  const [tailorOpen, setTailorOpen] = useState(false);
  const [tailorBusy, setTailorBusy] = useState(false);
  const [tailorResult, setTailorResult] = useState(null);
  const [pageNotice, setPageNotice] = useState("");

  async function loadMasterCv() {
    setLoading(true);
    try {
      const response = await request("/master-cv");
      setMasterCv(response);
      setError("");
    } catch (requestError) {
      setError(String(requestError?.message || "Unable to load your Master CV."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isConnected) loadMasterCv();
  }, [isConnected, request]);

  const allBullets = useMemo(() => (masterCv?.sections || []).flatMap((section) =>
    (section.entries || []).flatMap((entry) => entry.bullets || [])), [masterCv]);
  const selectedBullet = useMemo(
    () => findMasterCvBullet(masterCv, selectedBulletId),
    [masterCv, selectedBulletId],
  );
  const extraEvidenceCount = countMasterCvExtraEvidence(masterCv);

  useEffect(() => {
    if (!selectedBullet && allBullets[0]) setSelectedBulletId(allBullets[0].id);
    if (selectedBullet && !allBullets.some((bullet) => bullet.id === selectedBullet.id)) setSelectedBulletId(allBullets[0]?.id || "");
  }, [allBullets, selectedBullet]);

  useEffect(() => {
    if (!pageNotice) return undefined;
    const timeoutId = window.setTimeout(() => setPageNotice(""), 4200);
    return () => window.clearTimeout(timeoutId);
  }, [pageNotice]);

  function closeIntro() {
    closeIntroStorage();
    setShowIntro(false);
  }

  function openComposer(entry) {
    setComposerEntryId(entry.id);
    setCoachNotice("");
    if (entry.collapsed) setExpandedEntryIds((current) => [...new Set([...current, entry.id])]);
  }

  async function addAchievement(entryId, text) {
    setMutationEntryId(entryId);
    try {
      const response = await request(`/master-cv/entries/${encodeURIComponent(entryId)}/bullets`, { method: "POST", body: { text } });
      setMasterCv(response);
      setComposerEntryId("");
      setPageNotice("Added as extra evidence. Your uploaded CV was not changed.");
    } catch (requestError) {
      setPageNotice(String(requestError?.message || "Unable to save this achievement."));
    } finally {
      setMutationEntryId("");
    }
  }

  async function addExperience(form) {
    setExperienceSaving(true);
    try {
      const response = await request("/master-cv/entries", {
        method: "POST",
        body: { ...form, section_id: form.kind === "project" ? "projects" : "experience" },
      });
      setMasterCv(response);
      setExperienceDialogOpen(false);
      setPageNotice("Added to your Master CV. Add achievements to capture the details.");
    } catch (requestError) {
      setPageNotice(String(requestError?.message || "Unable to add this experience."));
    } finally {
      setExperienceSaving(false);
    }
  }

  async function improveSelectedBullet() {
    if (!selectedBullet) return;
    setImproveBusy(true);
    try {
      const response = await request(`/master-cv/bullets/${encodeURIComponent(selectedBullet.id)}/improve`, { method: "POST" });
      setCoachNotice(`Runr suggestion: ${response.suggested_text}`);
    } catch (requestError) {
      setCoachNotice(String(requestError?.message || "Unable to prepare a suggestion."));
    } finally {
      setImproveBusy(false);
    }
  }

  async function exportMasterCv(format) {
    setExportOpen(false);
    try {
      const response = await request(`/master-cv/export?format=${encodeURIComponent(format)}`);
      const blob = new Blob([response.content], { type: format === "json" ? "application/json" : "text/plain" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setPageNotice(`Downloaded ${response.filename}.`);
    } catch (requestError) {
      setPageNotice(String(requestError?.message || "Unable to export your Master CV."));
    }
  }

  async function tailorMasterCv(targetText) {
    setTailorBusy(true);
    try {
      const response = await request("/master-cv/tailor", { method: "POST", body: { target_text: targetText } });
      setTailorResult(response);
    } catch (requestError) {
      setPageNotice(String(requestError?.message || "Unable to find relevant Master CV material."));
    } finally {
      setTailorBusy(false);
    }
  }

  if (loading) return <div className="master-cv-page"><div className="master-cv-state">Loading your Master CV...</div></div>;
  if (error) return <div className="master-cv-page"><div className="master-cv-state master-cv-state--error"><h1>Master CV unavailable</h1><p>{error}</p><button className="master-cv-primary" onClick={loadMasterCv} type="button">Try again</button></div></div>;
  if (!masterCv) return null;

  return (
    <div className="master-cv-page">
      <div className="master-cv-workspace">
        <aside className="master-cv-sidebar">
          <NavLink className="master-cv-back-link" to="/documents"><Icon>arrow_back</Icon><span>My Documents</span></NavLink>
          <div className="master-cv-side-heading">Documents</div>
          <NavLink className="master-cv-side-link" to="/documents"><Icon>description</Icon><span>Resumes</span></NavLink>
          <NavLink className="master-cv-side-link" to="/documents?tab=cover_letters"><Icon>article</Icon><span>Cover letters</span></NavLink>
          <NavLink className="master-cv-side-link is-active" to="/master-cv"><Icon>auto_awesome</Icon><span>Master CV</span><em>New</em></NavLink>
          <div className="master-cv-side-note"><Icon>auto_awesome</Icon><p><b>{extraEvidenceCount} extra evidence point{extraEvidenceCount === 1 ? "" : "s"}</b><br />Saved in your Master CV</p></div>
        </aside>

        <main className="master-cv-main-area">
          <header className="master-cv-page-heading">
            <div>
              <div className="master-cv-eyebrow">Your complete career record</div>
              <h1>Master CV</h1>
              <p>A living record of everything you have done - ready to tailor for every opportunity.</p>
            </div>
            <div className="master-cv-heading-actions">
              <button className="master-cv-secondary" onClick={() => setShowIntro(true)} type="button">How it works</button>
              <button className="master-cv-primary" onClick={() => setExperienceDialogOpen(true)} type="button"><span aria-hidden="true">+</span> Add experience</button>
            </div>
          </header>

          <section aria-label="Master CV status" className="master-cv-status-strip">
            <div className="master-cv-status-copy"><span aria-hidden="true" className="master-cv-status-icon">{masterCv.status.ready ? "✓" : "!"}</span><p><b>{masterCv.status.label}</b><span>{extraEvidenceCount} extra evidence point{extraEvidenceCount === 1 ? "" : "s"} across {masterCv.status.experienceCount} experiences</span></p></div>
            <div className="master-cv-progress-wrap"><span>Profile depth</span><div className="master-cv-progress"><i style={{ width: `${masterCv.status.depth}%` }} /></div><b>{masterCv.status.depth}%</b></div>
          </section>

          <section aria-label="Master CV editor" className="master-cv-canvas-shell">
            <div className="master-cv-canvas-toolbar">
              <div className="master-cv-view-toggle" role="group" aria-label="Master CV view">
                <button className={view === "all" ? "is-on" : ""} onClick={() => setView("all")} type="button">Full Master CV</button>
                <button className={view === "extra" ? "is-on" : ""} onClick={() => setView("extra")} type="button">Extra evidence only</button>
              </div>
              <div className="master-cv-toolbar-right">
                <span>{savedLabel(masterCv.updated_at)}</span>
                <div className="master-cv-actions-menu">
                  <button aria-expanded={exportOpen} aria-label="More Master CV actions" onClick={() => setExportOpen((current) => !current)} type="button">•••</button>
                  {exportOpen ? <div className="master-cv-actions-popover" role="menu"><button onClick={() => exportMasterCv("json")} type="button">Download JSON</button><button onClick={() => exportMasterCv("text")} type="button">Download text</button><button onClick={() => { setExportOpen(false); loadMasterCv(); }} type="button">Refresh</button></div> : null}
                </div>
              </div>
            </div>

            <div className="master-cv-editor-layout">
              <article aria-label="Master CV canvas" className="master-cv-canvas">
                <section className="master-cv-identity">
                  <h2>{masterCv.profile.name || "Your name"}</h2>
                  {masterCv.profile.headline ? <p>{masterCv.profile.headline}{masterCv.profile.location ? ` · ${masterCv.profile.location}` : ""}</p> : <p>Add a headline in your profile settings.</p>}
                  <div>{masterCv.profile.email || "Add your email"}{masterCv.profile.linkedin ? <><span> · </span>{masterCv.profile.linkedin}</> : null}</div>
                </section>

                {masterCv.sections.map((section) => (
                  <section className={["master-cv-section", section.id === "projects" ? "is-projects" : ""].join(" ")} key={section.id}>
                    <h3>{section.label}</h3>
                    {section.entries.map((entry) => (
                      <Entry
                        composerEntryId={composerEntryId}
                        entry={entry}
                        expanded={expandedEntryIds.includes(entry.id)}
                        key={entry.id}
                        mutationEntryId={mutationEntryId}
                        onAdd={addAchievement}
                        onCancelComposer={() => setComposerEntryId("")}
                        onOpenComposer={openComposer}
                        onSelectBullet={(bulletId) => { setSelectedBulletId(bulletId); setCoachNotice(""); }}
                        onToggleExpanded={(entryId) => setExpandedEntryIds((current) => current.includes(entryId) ? current.filter((id) => id !== entryId) : [...current, entryId])}
                        selectedBulletId={selectedBulletId}
                        view={view}
                      />
                    ))}
                    {!section.entries.length ? <p className="master-cv-empty-copy">Nothing here yet. Add an experience or project to start building your record.</p> : null}
                  </section>
                ))}
              </article>

              <WritingGuidance busy={improveBusy} bullet={selectedBullet} notice={coachNotice} onImprove={improveSelectedBullet} onTailor={() => { setTailorResult(null); setTailorOpen(true); }} />
            </div>
          </section>
          {pageNotice ? <p className="master-cv-page-notice" role="status">{pageNotice}</p> : null}
        </main>
      </div>
      {showIntro ? <IntroDialog onClose={closeIntro} /> : null}
      {experienceDialogOpen ? <ExperienceDialog busy={experienceSaving} onClose={() => setExperienceDialogOpen(false)} onSave={addExperience} /> : null}
      {tailorOpen ? <TailorDialog busy={tailorBusy} onClose={() => setTailorOpen(false)} onSearch={tailorMasterCv} result={tailorResult} /> : null}
    </div>
  );
}

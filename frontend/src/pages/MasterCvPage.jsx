import { useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import { createMasterCvFixture } from "../data/masterCvFixture";
import {
  addMasterCvAchievement,
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

function AchievementComposer({ label, onCancel, onSave }) {
  const [value, setValue] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    if (!value.trim()) return;
    onSave(value);
  }

  return (
    <form className="master-cv-composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor={`master-cv-composer-${label}`}>{label}</label>
      <textarea
        autoFocus
        id={`master-cv-composer-${label}`}
        onChange={(event) => setValue(event.target.value)}
        placeholder="What did you do? Who did it help? What changed as a result?"
        value={value}
      />
      <div className="master-cv-composer__footer">
        <span>Try: action + context + outcome</span>
        <button className="master-cv-text-button" onClick={onCancel} type="button">Cancel</button>
        <button className="master-cv-primary master-cv-primary--small" disabled={!value.trim()} type="submit">Add to Master CV</button>
      </div>
    </form>
  );
}

function Entry({
  composerEntryId,
  entry,
  expanded,
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
          <p>{entry.organisation}</p>
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
          label={composerLabel}
          onCancel={onCancelComposer}
          onSave={(text) => onAdd(entry.id, text)}
        />
      ) : (
        <button className="master-cv-add-bullet" onClick={() => onOpenComposer(entry)} type="button">
          <span aria-hidden="true">＋</span> {composerLabel}
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

function WritingGuidance({ bullet, onImprove, notice }) {
  if (!bullet) return null;
  const guidance = getMasterCvGuidance(bullet);

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
        <button onClick={onImprove} type="button">Improve with Runr</button>
      </div>
      {notice ? <p className="master-cv-coach-notice" role="status">{notice}</p> : null}
      <div className="master-cv-match-note">
        <Icon>target</Icon>
        <p><b>How Runr will use this</b><br />{guidance.use}</p>
      </div>
    </aside>
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
          <div><span>02</span><p><b>Build on what you already have</b><br />Add extra achievements beneath every role and project—without changing your current CV.</p></div>
          <div><span>03</span><p><b>Tailor without starting again</b><br />When an employer needs a specific skill, Runr can surface the strongest relevant evidence.</p></div>
          <div><span>04</span><p><b>Write with confidence</b><br />Get immediate guidance on clarity, contribution and impact while you write.</p></div>
        </div>
        <div className="master-cv-modal-example" aria-label="CV bullet becomes stronger tailored CV">
          <span>Your CV bullet</span><b>＋</b><span className="is-extra">Relevant extra evidence</span><b>→</b><strong>A stronger tailored CV</strong>
        </div>
        <button className="master-cv-primary master-cv-modal-action" onClick={onClose} type="button">Explore my Master CV</button>
        <button className="master-cv-quiet-button" onClick={onClose} type="button">I’ll do this later</button>
      </div>
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

export default function MasterCvPage() {
  const [masterCv, setMasterCv] = useState(() => createMasterCvFixture());
  const [showIntro, setShowIntro] = useState(shouldShowIntro);
  const [view, setView] = useState("all");
  const [selectedBulletId, setSelectedBulletId] = useState("northstar-onboarding");
  const [expandedEntryIds, setExpandedEntryIds] = useState([]);
  const [composerEntryId, setComposerEntryId] = useState("");
  const [nextDraftId, setNextDraftId] = useState(1);
  const [saveLabel, setSaveLabel] = useState("Saved just now");
  const [coachNotice, setCoachNotice] = useState("");
  const [pageNotice, setPageNotice] = useState("");

  const selectedBullet = useMemo(
    () => findMasterCvBullet(masterCv, selectedBulletId),
    [masterCv, selectedBulletId],
  );
  const extraEvidenceCount = masterCv.status.extraEvidenceCount + masterCv.sections
    .flatMap((section) => section.entries)
    .flatMap((entry) => entry.bullets)
    .filter((bullet) => bullet.draft && bullet.extra).length;

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
    if (entry.collapsed) {
      setExpandedEntryIds((current) => [...new Set([...current, entry.id])]);
    }
  }

  function addAchievement(entryId, text) {
    setMasterCv((current) => addMasterCvAchievement(current, entryId, text, `draft-${nextDraftId}`));
    setNextDraftId((current) => current + 1);
    setComposerEntryId("");
    setSaveLabel("Saved just now");
    setPageNotice("Added as extra evidence. It will not change your uploaded CV.");
  }

  function toggleExpanded(entryId) {
    setExpandedEntryIds((current) => current.includes(entryId)
      ? current.filter((id) => id !== entryId)
      : [...current, entryId]);
  }

  function handleSelectBullet(bulletId) {
    setSelectedBulletId(bulletId);
    setCoachNotice("");
  }

  return (
    <div className="master-cv-page">
      <div className="master-cv-workspace">
        <aside className="master-cv-sidebar">
          <NavLink className="master-cv-back-link" to="/documents"><Icon>arrow_back</Icon><span>My Documents</span></NavLink>
          <div className="master-cv-side-heading">Documents</div>
          <NavLink className="master-cv-side-link" to="/documents"><Icon>description</Icon><span>Resumes</span></NavLink>
          <NavLink className="master-cv-side-link" to="/documents?tab=cover_letters"><Icon>article</Icon><span>Cover letters</span></NavLink>
          <NavLink className="master-cv-side-link is-active" to="/master-cv"><Icon>auto_awesome</Icon><span>Master CV</span><em>New</em></NavLink>
          <div className="master-cv-side-note"><Icon>auto_awesome</Icon><p><b>1 new suggestion</b><br />From your uploaded CV</p></div>
        </aside>

        <main className="master-cv-main-area">
          <header className="master-cv-page-heading">
            <div>
              <div className="master-cv-eyebrow">Your complete career record</div>
              <h1>Master CV</h1>
              <p>A living record of everything you have done—ready to tailor for every opportunity.</p>
            </div>
            <div className="master-cv-heading-actions">
              <button className="master-cv-secondary" onClick={() => setShowIntro(true)} type="button">How it works</button>
              <button className="master-cv-primary" onClick={() => setPageNotice("Experience creation will connect to Career Evidence after frontend approval.")} type="button"><span aria-hidden="true">＋</span> Add experience</button>
            </div>
          </header>

          <section aria-label="Master CV status" className="master-cv-status-strip">
            <div className="master-cv-status-copy"><span aria-hidden="true" className="master-cv-status-icon">✓</span><p><b>Master CV is ready</b><span>{extraEvidenceCount} extra evidence points across {masterCv.status.experienceCount} experiences</span></p></div>
            <div className="master-cv-progress-wrap"><span>Profile depth</span><div className="master-cv-progress"><i style={{ width: `${masterCv.status.depth}%` }} /></div><b>{masterCv.status.depth}%</b></div>
          </section>

          <section aria-label="Master CV editor" className="master-cv-canvas-shell">
            <div className="master-cv-canvas-toolbar">
              <div className="master-cv-view-toggle" role="group" aria-label="Master CV view">
                <button className={view === "all" ? "is-on" : ""} onClick={() => setView("all")} type="button">Full Master CV</button>
                <button className={view === "extra" ? "is-on" : ""} onClick={() => setView("extra")} type="button">Extra evidence only</button>
              </div>
              <div className="master-cv-toolbar-right"><span>{saveLabel}</span><button aria-label="More Master CV actions" onClick={() => setPageNotice("Export and sharing will be connected after the frontend review.")} type="button">•••</button></div>
            </div>

            <div className="master-cv-editor-layout">
              <article aria-label="Master CV canvas" className="master-cv-canvas">
                <section className="master-cv-identity">
                  <h2>{masterCv.profile.name}</h2>
                  <p>{masterCv.profile.headline} · {masterCv.profile.location}</p>
                  <div>{masterCv.profile.email} <span>·</span> {masterCv.profile.linkedin}</div>
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
                        onAdd={addAchievement}
                        onCancelComposer={() => setComposerEntryId("")}
                        onOpenComposer={openComposer}
                        onSelectBullet={handleSelectBullet}
                        onToggleExpanded={toggleExpanded}
                        selectedBulletId={selectedBulletId}
                        view={view}
                      />
                    ))}
                  </section>
                ))}
              </article>

              <WritingGuidance
                bullet={selectedBullet}
                notice={coachNotice}
                onImprove={() => setCoachNotice("Writing improvement is guidance-only in this frontend preview.")}
              />
            </div>
          </section>
          {pageNotice ? <p className="master-cv-page-notice" role="status">{pageNotice}</p> : null}
        </main>
      </div>
      {showIntro ? <IntroDialog onClose={closeIntro} /> : null}
    </div>
  );
}

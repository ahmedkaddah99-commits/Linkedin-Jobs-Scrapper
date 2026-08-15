import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";

const EMPTY_PROFILE = {
  name: "",
  role_title: "",
  industry: "",
  email: "",
  location: "",
  website: "",
  linkedin_url: "",
  github_url: "",
  summary: "",
  competencies: [],
  languages: [],
  recent_experience: [],
  education: [],
  projects: [],
  custom_sections: [],
};

function Icon({ children, className = "" }) {
  return <span className={`material-symbols-outlined ${className}`}>{children}</span>;
}

function text(value) {
  return String(value || "").trim();
}

function lines(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeProfile(raw = {}) {
  const source = raw && typeof raw === "object" ? raw : {};
  return {
    ...EMPTY_PROFILE,
    ...Object.fromEntries(
      ["name", "role_title", "industry", "email", "location", "website", "linkedin_url", "github_url", "summary"]
        .map((key) => [key, text(source[key])]),
    ),
    competencies: Array.isArray(source.competencies) ? source.competencies.map(text).filter(Boolean) : [],
    languages: Array.isArray(source.languages) ? source.languages.map(text).filter(Boolean) : [],
    recent_experience: Array.isArray(source.recent_experience)
      ? source.recent_experience.map((item) => ({
        title: text(item?.title || item?.role),
        company: text(item?.company),
        period: text(item?.period),
        bullets: Array.isArray(item?.bullets) ? item.bullets.map(text).filter(Boolean) : lines(item?.bulletsText),
      }))
      : [],
    education: Array.isArray(source.education)
      ? source.education.map((item) => ({
        degree_title: text(item?.degree_title || item?.degree || item?.title),
        institution: text(item?.institution || item?.school),
        period: text(item?.period),
        details: Array.isArray(item?.details) ? item.details.map(text).filter(Boolean) : lines(item?.detailsText),
      }))
      : [],
    projects: Array.isArray(source.projects)
      ? source.projects.map((item) => ({
        title: text(item?.title || item?.name),
        period: text(item?.period || item?.date || item?.year),
        bullets: Array.isArray(item?.bullets) ? item.bullets.map(text).filter(Boolean) : lines(item?.bulletsText),
      }))
      : [],
    custom_sections: Array.isArray(source.custom_sections)
      ? source.custom_sections.map((item) => ({
        section_id: text(item?.section_id || item?.id),
        heading: text(item?.heading || item?.title || item?.label),
        lines: Array.isArray(item?.lines) ? item.lines.map(text).filter(Boolean) : lines(item?.content || item?.text),
      }))
      : [],
  };
}

function makeExperience() {
  return { title: "", company: "", period: "", bullets: [] };
}

function makeEducation() {
  return { degree_title: "", institution: "", period: "", details: [] };
}

function makeProject() {
  return { title: "", period: "", bullets: [] };
}

function makeCustomSection() {
  return { section_id: `custom_${Date.now()}`, heading: "", lines: [] };
}

function Field({ label, className = "", ...props }) {
  return (
    <label className={`grid gap-2 ${className}`}>
      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-on-surface-variant">{label}</span>
      <input
        {...props}
        className="w-full rounded-xl border border-outline-variant/25 bg-surface px-3.5 py-3 text-sm text-on-surface outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
      />
    </label>
  );
}

function TextField({ label, className = "", ...props }) {
  return (
    <label className={`grid gap-2 ${className}`}>
      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-on-surface-variant">{label}</span>
      <textarea
        {...props}
        className="min-h-24 w-full resize-y rounded-xl border border-outline-variant/25 bg-surface px-3.5 py-3 text-sm leading-6 text-on-surface outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
      />
    </label>
  );
}

function EditorCard({ action, children, description, icon, title }) {
  return (
    <section className="rounded-3xl border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
            <Icon>{icon}</Icon>
          </span>
          <div>
            <h2 className="font-headline text-lg font-bold text-on-surface">{title}</h2>
            {description ? <p className="mt-1 text-sm leading-6 text-on-surface-variant">{description}</p> : null}
          </div>
        </div>
        {action}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function AddButton({ children, onClick }) {
  return (
    <button
      className="inline-flex items-center gap-1.5 rounded-xl bg-surface-container-low px-3 py-2 text-sm font-semibold text-primary transition hover:bg-primary/10"
      onClick={onClick}
      type="button"
    >
      <Icon className="text-[18px]">add</Icon>
      {children}
    </button>
  );
}

function RemoveButton({ onClick }) {
  return (
    <button
      aria-label="Remove section"
      className="rounded-full p-2 text-on-surface-variant transition hover:bg-red-50 hover:text-red-700"
      onClick={onClick}
      type="button"
    >
      <Icon className="text-[19px]">delete_outline</Icon>
    </button>
  );
}

function PreviewSection({ children, title }) {
  return (
    <section className="mt-5 first:mt-0">
      <h3 className="border-b border-slate-200 pb-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-teal-700">{title}</h3>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

function CvPreview({ profile }) {
  const contacts = [profile.email, profile.location, profile.website, profile.linkedin_url, profile.github_url].filter(Boolean);
  return (
    <article className="mx-auto min-h-[52rem] max-w-[43rem] bg-white p-7 text-[11px] leading-[1.55] text-slate-700 shadow-xl shadow-slate-900/10 sm:p-10">
      <header className="border-b-2 border-teal-600 pb-4 text-center">
        <h2 className="font-headline text-3xl font-extrabold tracking-tight text-[#17324d]">{profile.name || "Your name"}</h2>
        <p className="mt-1 text-sm font-medium text-teal-700">{profile.role_title || "Professional headline"}</p>
        {contacts.length ? <p className="mt-2 text-[9px] text-slate-500">{contacts.join("  ·  ")}</p> : null}
      </header>

      {profile.summary ? <PreviewSection title="Summary"><p>{profile.summary}</p></PreviewSection> : null}

      {profile.recent_experience.length ? (
        <PreviewSection title="Experience">
          <div className="space-y-3">
            {profile.recent_experience.map((item, index) => (
              <div key={`${item.title}-${index}`}>
                <div className="flex items-baseline justify-between gap-3">
                  <strong className="text-[12px] text-[#17324d]">{item.title || "Role"}</strong>
                  <span className="shrink-0 text-[9px] text-slate-500">{item.period}</span>
                </div>
                {item.company ? <p className="text-[10px] font-medium text-teal-700">{item.company}</p> : null}
                {item.bullets.length ? <ul className="mt-1 list-disc space-y-0.5 pl-4">{item.bullets.map((bullet, bulletIndex) => <li key={`${bullet}-${bulletIndex}`}>{bullet}</li>)}</ul> : null}
              </div>
            ))}
          </div>
        </PreviewSection>
      ) : null}

      {profile.projects.length ? (
        <PreviewSection title="Projects">
          <div className="space-y-3">
            {profile.projects.map((item, index) => (
              <div key={`${item.title}-${index}`}>
                <div className="flex items-baseline justify-between gap-3"><strong className="text-[12px] text-[#17324d]">{item.title || "Project"}</strong><span className="shrink-0 text-[9px] text-slate-500">{item.period}</span></div>
                {item.bullets.length ? <ul className="mt-1 list-disc space-y-0.5 pl-4">{item.bullets.map((bullet, bulletIndex) => <li key={`${bullet}-${bulletIndex}`}>{bullet}</li>)}</ul> : null}
              </div>
            ))}
          </div>
        </PreviewSection>
      ) : null}

      {profile.education.length ? (
        <PreviewSection title="Education">
          <div className="space-y-2.5">
            {profile.education.map((item, index) => <div key={`${item.degree_title}-${index}`}><div className="flex items-baseline justify-between gap-3"><strong className="text-[12px] text-[#17324d]">{item.degree_title || "Education"}</strong><span className="shrink-0 text-[9px] text-slate-500">{item.period}</span></div><p className="text-[10px] text-teal-700">{item.institution}</p>{item.details.length ? <ul className="mt-1 list-disc space-y-0.5 pl-4">{item.details.map((detail, detailIndex) => <li key={`${detail}-${detailIndex}`}>{detail}</li>)}</ul> : null}</div>)}
          </div>
        </PreviewSection>
      ) : null}

      {profile.competencies.length ? <PreviewSection title="Skills"><div className="flex flex-wrap gap-1.5">{profile.competencies.map((item) => <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-medium text-slate-700" key={item}>{item}</span>)}</div></PreviewSection> : null}
      {profile.languages.length ? <PreviewSection title="Languages"><p>{profile.languages.join("  ·  ")}</p></PreviewSection> : null}
      {profile.custom_sections.map((section, index) => section.heading || section.lines.length ? <PreviewSection key={`${section.section_id || section.heading}-${index}`} title={section.heading || "Additional information"}><ul className="list-disc space-y-0.5 pl-4">{section.lines.map((line, lineIndex) => <li key={`${line}-${lineIndex}`}>{line}</li>)}</ul></PreviewSection> : null)}

      {!profile.summary && !profile.recent_experience.length && !profile.projects.length && !profile.education.length && !profile.competencies.length ? <div className="mt-16 rounded-2xl border border-dashed border-slate-300 p-6 text-center text-slate-400">Your live CV preview will appear here as you add content.</div> : null}
    </article>
  );
}

export default function CvEditorPage() {
  const { request } = useSession();
  const navigate = useNavigate();
  const { assetId } = useParams();
  const [document, setDocument] = useState(null);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState({ saving: false, message: "", error: "" });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    request(`/documents/assets/${encodeURIComponent(assetId || "")}/editor`, { timeoutMs: 60000 })
      .then((payload) => {
        if (cancelled) return;
        setDocument(payload.document || null);
        setProfile(normalizeProfile(payload.editor?.profile));
        setRevision(Number(payload.editor?.revision || 0));
        setDirty(false);
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message || "Unable to load this CV.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [assetId, request]);

  useEffect(() => {
    if (!dirty) return undefined;
    function confirmUnload(event) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", confirmUnload);
    return () => window.removeEventListener("beforeunload", confirmUnload);
  }, [dirty]);

  function updateProfileField(field, value) {
    setProfile((current) => ({ ...current, [field]: value }));
    setDirty(true);
    setSaveState({ saving: false, message: "", error: "" });
  }

  function updateCollectionItem(collection, index, patch) {
    setProfile((current) => ({ ...current, [collection]: current[collection].map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) }));
    setDirty(true);
    setSaveState({ saving: false, message: "", error: "" });
  }

  function updateCollectionLines(collection, index, field, value) {
    updateCollectionItem(collection, index, { [field]: lines(value) });
  }

  function addCollectionItem(collection, item) {
    setProfile((current) => ({ ...current, [collection]: [...current[collection], item] }));
    setDirty(true);
  }

  function removeCollectionItem(collection, index) {
    setProfile((current) => ({ ...current, [collection]: current[collection].filter((_, itemIndex) => itemIndex !== index) }));
    setDirty(true);
  }

  async function save() {
    if (saveState.saving || !dirty) return;
    setSaveState({ saving: true, message: "", error: "" });
    try {
      const payload = await request(`/documents/assets/${encodeURIComponent(assetId || "")}/editor`, {
        method: "PUT",
        body: { base_revision: revision, profile },
      });
      setDocument(payload.document || document);
      setProfile(normalizeProfile(payload.editor?.profile || profile));
      setRevision(Number(payload.editor?.revision || revision + 1));
      setDirty(false);
      setSaveState({ saving: false, message: "Saved to your Documents library.", error: "" });
    } catch (error) {
      setSaveState({ saving: false, message: "", error: error.message || "Unable to save this CV." });
    }
  }

  async function download() {
    if (!document?.download_url) return;
    try {
      const blob = await request(document.download_url, { responseType: "blob" });
      const url = window.URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = document.display_name || "edited-cv.docx";
      window.document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setSaveState({ saving: false, message: "", error: error.message || "Unable to download this CV." });
    }
  }

  const completion = useMemo(() => {
    const checks = [profile.name, profile.role_title, profile.summary, profile.recent_experience.length, profile.education.length, profile.competencies.length];
    return Math.round(checks.filter(Boolean).length / checks.length * 100);
  }, [profile]);

  if (loading) {
    return <div className="space-y-5"><div className="h-8 w-64 animate-pulse rounded-full bg-surface-container" /><div className="grid gap-6 xl:grid-cols-2"><div className="h-[42rem] animate-pulse rounded-3xl bg-surface-container" /><div className="h-[42rem] animate-pulse rounded-3xl bg-surface-container" /></div></div>;
  }

  if (loadError) {
    return <section className="rounded-3xl border border-error/20 bg-surface-container-lowest p-8 shadow-soft"><Icon className="text-4xl text-error">error</Icon><h1 className="mt-3 font-headline text-2xl font-bold text-on-surface">CV editor unavailable</h1><p className="mt-2 max-w-xl text-sm leading-6 text-on-surface-variant">{loadError}</p><button className="mt-6 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-container" onClick={() => navigate("/documents")} type="button">Back to Documents</button></section>;
  }

  return (
    <div className="space-y-6 pb-10">
      <header className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <Link className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary transition hover:text-primary-container" to="/documents"><Icon className="text-[18px]">arrow_back</Icon>Documents</Link>
          <div className="mt-4 flex items-start gap-3">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary"><Icon className="text-2xl">edit_document</Icon></span>
            <div className="min-w-0"><h1 className="truncate font-headline text-3xl font-extrabold tracking-tight text-on-surface md:text-4xl">Edit your CV</h1><p className="mt-1 truncate text-sm text-on-surface-variant">{document?.display_name || "Workspace CV"} · revision {revision || 1}</p></div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-semibold ${dirty ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-700"}`}><span className={`h-1.5 w-1.5 rounded-full ${dirty ? "bg-amber-500" : "bg-emerald-500"}`} />{dirty ? "Unsaved changes" : "All changes saved"}</span>
          <button className="inline-flex items-center gap-2 rounded-xl border border-outline-variant/25 bg-surface-container-low px-4 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50" disabled={!document?.download_url} onClick={() => void download()} type="button"><Icon className="text-[18px]">download</Icon>Download DOCX</button>
          <button className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-primary to-primary-container px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50" disabled={!dirty || saveState.saving} onClick={() => void save()} type="button"><Icon className="text-[18px]">save</Icon>{saveState.saving ? "Saving..." : "Save changes"}</button>
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/15 bg-primary/5 px-4 py-3 text-sm text-on-surface-variant">
        <span><strong className="text-on-surface">Make it yours.</strong> Update the content below and watch the document preview respond instantly.</span>
        <span className="font-semibold text-primary">{completion}% complete</span>
      </div>

      {saveState.message ? <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800" role="status">{saveState.message}</div> : null}
      {saveState.error ? <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800" role="alert">{saveState.error}</div> : null}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(30rem,0.95fr)]">
        <div className="space-y-5">
          <EditorCard description="The details employers see first." icon="person" title="Identity and contact">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Full name" onChange={(event) => updateProfileField("name", event.target.value)} value={profile.name} />
              <Field label="Headline" onChange={(event) => updateProfileField("role_title", event.target.value)} value={profile.role_title} />
              <Field label="Industry" onChange={(event) => updateProfileField("industry", event.target.value)} value={profile.industry} />
              <Field label="Email" onChange={(event) => updateProfileField("email", event.target.value)} type="email" value={profile.email} />
              <Field label="Location" onChange={(event) => updateProfileField("location", event.target.value)} value={profile.location} />
              <Field label="LinkedIn" onChange={(event) => updateProfileField("linkedin_url", event.target.value)} value={profile.linkedin_url} />
              <Field label="Website" onChange={(event) => updateProfileField("website", event.target.value)} value={profile.website} />
              <Field label="GitHub" onChange={(event) => updateProfileField("github_url", event.target.value)} value={profile.github_url} />
            </div>
          </EditorCard>

          <EditorCard description="A focused introduction that connects your experience to the role." icon="short_text" title="Professional summary">
            <TextField label="Summary" onChange={(event) => updateProfileField("summary", event.target.value)} placeholder="Describe your strongest professional value in two or three sentences." value={profile.summary} />
          </EditorCard>

          <EditorCard action={<AddButton onClick={() => addCollectionItem("recent_experience", makeExperience())}>Add role</AddButton>} description="Show the work, scope, and outcomes you want to be remembered for." icon="work_history" title="Experience">
            <div className="space-y-4">
              {profile.recent_experience.map((item, index) => <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4" key={`experience-${index}`}><div className="mb-4 flex items-center justify-between gap-3"><span className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Role {index + 1}</span><RemoveButton onClick={() => removeCollectionItem("recent_experience", index)} /></div><div className="grid gap-4 sm:grid-cols-2"><Field label="Role title" onChange={(event) => updateCollectionItem("recent_experience", index, { title: event.target.value })} value={item.title} /><Field label="Company" onChange={(event) => updateCollectionItem("recent_experience", index, { company: event.target.value })} value={item.company} /><Field className="sm:col-span-2" label="Dates" onChange={(event) => updateCollectionItem("recent_experience", index, { period: event.target.value })} placeholder="2022 — Present" value={item.period} /><TextField className="sm:col-span-2" label="Achievements · one per line" onChange={(event) => updateCollectionLines("recent_experience", index, "bullets", event.target.value)} placeholder="Built...\nImproved..." value={item.bullets.join("\n")} /></div></div>)}
              {!profile.recent_experience.length ? <div className="rounded-2xl border border-dashed border-outline-variant/25 p-6 text-center text-sm text-on-surface-variant">No experience added yet. Start with the role most relevant to your next opportunity.</div> : null}
            </div>
          </EditorCard>

          <EditorCard action={<AddButton onClick={() => addCollectionItem("projects", makeProject())}>Add project</AddButton>} description="Keep selected work that proves your capabilities beyond job titles." icon="rocket_launch" title="Projects">
            <div className="space-y-4">{profile.projects.map((item, index) => <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4" key={`project-${index}`}><div className="mb-4 flex items-center justify-between gap-3"><span className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Project {index + 1}</span><RemoveButton onClick={() => removeCollectionItem("projects", index)} /></div><div className="grid gap-4 sm:grid-cols-2"><Field label="Project name" onChange={(event) => updateCollectionItem("projects", index, { title: event.target.value })} value={item.title} /><Field label="Date or period" onChange={(event) => updateCollectionItem("projects", index, { period: event.target.value })} value={item.period} /><TextField className="sm:col-span-2" label="Highlights · one per line" onChange={(event) => updateCollectionLines("projects", index, "bullets", event.target.value)} value={item.bullets.join("\n")} /></div></div>)}{!profile.projects.length ? <div className="rounded-2xl border border-dashed border-outline-variant/25 p-6 text-center text-sm text-on-surface-variant">Projects are optional. Add one when it strengthens your story.</div> : null}</div>
          </EditorCard>

          <EditorCard action={<AddButton onClick={() => addCollectionItem("education", makeEducation())}>Add education</AddButton>} description="Add the qualifications that are relevant to your target roles." icon="school" title="Education">
            <div className="space-y-4">{profile.education.map((item, index) => <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4" key={`education-${index}`}><div className="mb-4 flex items-center justify-between gap-3"><span className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Education {index + 1}</span><RemoveButton onClick={() => removeCollectionItem("education", index)} /></div><div className="grid gap-4 sm:grid-cols-2"><Field label="Degree or qualification" onChange={(event) => updateCollectionItem("education", index, { degree_title: event.target.value })} value={item.degree_title} /><Field label="Institution" onChange={(event) => updateCollectionItem("education", index, { institution: event.target.value })} value={item.institution} /><Field className="sm:col-span-2" label="Dates" onChange={(event) => updateCollectionItem("education", index, { period: event.target.value })} value={item.period} /><TextField className="sm:col-span-2" label="Details · one per line" onChange={(event) => updateCollectionLines("education", index, "details", event.target.value)} value={item.details.join("\n")} /></div></div>)}{!profile.education.length ? <div className="rounded-2xl border border-dashed border-outline-variant/25 p-6 text-center text-sm text-on-surface-variant">No education entries added yet.</div> : null}</div>
          </EditorCard>

          <EditorCard description="Use one line per skill or language. These are rendered as compact, scannable lists." icon="auto_awesome" title="Skills and languages">
            <div className="grid gap-4 sm:grid-cols-2"><TextField label="Skills · one per line" onChange={(event) => updateProfileField("competencies", lines(event.target.value))} value={profile.competencies.join("\n")} /><TextField label="Languages · one per line" onChange={(event) => updateProfileField("languages", lines(event.target.value))} value={profile.languages.join("\n")} /></div>
          </EditorCard>

          <EditorCard action={<AddButton onClick={() => addCollectionItem("custom_sections", makeCustomSection())}>Add section</AddButton>} description="Preserve publications, awards, certifications, or other evidence from your original CV." icon="widgets" title="Additional sections">
            <div className="space-y-4">{profile.custom_sections.map((item, index) => <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4" key={`custom-${index}`}><div className="mb-4 flex items-center justify-between gap-3"><span className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Additional section {index + 1}</span><RemoveButton onClick={() => removeCollectionItem("custom_sections", index)} /></div><div className="grid gap-4"><Field label="Section title" onChange={(event) => updateCollectionItem("custom_sections", index, { heading: event.target.value })} value={item.heading} /><TextField label="Content - one per line" onChange={(event) => updateCollectionLines("custom_sections", index, "lines", event.target.value)} value={item.lines.join("\n")} /></div></div>)}{!profile.custom_sections.length ? <div className="rounded-2xl border border-dashed border-outline-variant/25 p-6 text-center text-sm text-on-surface-variant">Nothing extra to add? That is okay - the core sections are enough.</div> : null}</div>
          </EditorCard>
        </div>

        <aside className="xl:sticky xl:top-24">
          <div className="overflow-hidden rounded-3xl border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
            <div className="flex items-center justify-between gap-3 border-b border-outline-variant/15 px-5 py-4 sm:px-6"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Live preview</p><h2 className="mt-1 font-headline text-lg font-bold text-on-surface">Your finished CV</h2></div><span className="inline-flex items-center gap-1.5 rounded-full bg-surface-container-low px-2.5 py-1.5 text-[11px] font-semibold text-on-surface-variant"><Icon className="text-[15px]">visibility</Icon>Updates live</span></div>
            <div className="max-h-[calc(100vh-11rem)] overflow-auto bg-slate-100 p-4 sm:p-6"><CvPreview profile={profile} /></div>
          </div>
          <div className="mt-4 rounded-2xl border border-outline-variant/15 bg-surface-container-low px-4 py-3 text-xs leading-5 text-on-surface-variant"><Icon className="mr-1 align-middle text-[16px] text-primary">info</Icon>Saving creates a new CV version in your private Documents library. Your previous version remains recoverable.</div>
        </aside>
      </div>
    </div>
  );
}

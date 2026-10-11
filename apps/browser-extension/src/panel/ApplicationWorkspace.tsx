import { useEffect, useState } from "react";
import type { DocumentRole } from "@runr/ats-core/generic-upload";
import { workspaceRequest, type Library, type LibraryDocument } from "./workspace";

interface Props {
  mode: "documents" | "answers";
  applicationUrl: string;
  description: string;
  onAttach?: (role: DocumentRole, file: File, replace: boolean) => Promise<string>;
}

export default function ApplicationWorkspace({ mode, applicationUrl, description, onAttach }: Props) {
  const [library, setLibrary] = useState<Library>({ documents: [], answers: [] });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const [replace, setReplace] = useState(false);
  const [kind, setKind] = useState<"cv" | "cover_letter">("cv");
  const [jobText, setJobText] = useState(description);
  const [question, setQuestion] = useState("");
  const [instructions, setInstructions] = useState("");
  const [draft, setDraft] = useState("");
  const [draftKind, setDraftKind] = useState<"cv" | "cover_letter" | "answer">("cv");
  const [draftQuestion, setDraftQuestion] = useState("");
  const [name, setName] = useState("Application resume");
  const selectionKey = `runr-document:${applicationUrl}`;
  function rememberSelection(id: string) {
    setSelected(id);
    try { sessionStorage.setItem(selectionKey, id); } catch { /* The selected document still works when site storage is disabled. */ }
  }

  async function refresh() {
    setLoading(true); setError("");
    try {
      const result = await workspaceRequest<Library>("library");
      setLibrary(result);
      let prior: string | null = null;
      try { prior = sessionStorage.getItem(selectionKey); } catch { /* Site storage may be disabled. */ }
      if (prior && result.documents.some((doc) => doc.id === prior)) setSelected(prior);
    } catch (error) { setError(error instanceof Error ? error.message : "Couldn't load your library."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, [applicationUrl]);
  useEffect(() => { if (description) setJobText(description); }, [description]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(""); setStatus("");
    try { await action(); } catch (error) { setError(error instanceof Error ? error.message : "Couldn't complete this action."); }
    finally { setBusy(false); }
  }
  async function attach(doc: LibraryDocument) {
    const data = await workspaceRequest<{ name: string; base64: string }>("document", { document_id: doc.id });
    if (window.location.href !== applicationUrl) throw new Error("The application changed. Open Documents on the current page.");
    if (data.base64.length > 28 * 1024 * 1024) throw new Error("Choose a document smaller than 20 MB.");
    const bytes = Uint8Array.from(atob(data.base64), (value) => value.charCodeAt(0));
    const file = new File([bytes], data.name, { type: data.name.toLowerCase().endsWith(".pdf") ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    setStatus(await onAttach?.(doc.role, file, replace) || "Choose a file on the application form.");
  }
  const visible = library.documents.filter((doc) => doc.name.toLowerCase().includes(search.toLowerCase()));
  const chosen = library.documents.find((doc) => doc.id === selected);

  return <section className="workspace-tools" aria-label={mode === "documents" ? "Saved documents and drafts" : "Answer drafts"}>
    <p className="section-title">{mode === "documents" ? "Your saved documents" : "Your reviewed answers"}</p>
    <button type="button" className="icon-button" disabled={loading || busy} onClick={() => void refresh()}>Refresh library</button>
    {loading ? <p className="job-meta">Loading library…</p> : mode === "documents" ? <>
      <label className="section-title" htmlFor="runr-library-search">Find a document</label>
      <input id="runr-library-search" className="profile-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by filename" />
      <select aria-label="Saved application document" className="profile-search" value={selected} onChange={(event) => rememberSelection(event.target.value)}>
        <option value="">Choose a saved version</option>{visible.map((doc) => <option key={doc.id} value={doc.id}>{doc.role === "cv" ? "Resume" : "Cover letter"} · {doc.name}</option>)}
      </select>
      {!library.documents.length ? <p className="job-meta">No saved documents yet. Generate one below or upload a local file.</p> : null}
      {chosen ? <p className="job-meta">Selected: {chosen.name}</p> : null}
      <label className="job-meta"><input type="checkbox" checked={replace} onChange={(event) => setReplace(event.target.checked)} /> Replace an existing attachment</label>
      {onAttach ? <button type="button" className="primary" disabled={!chosen || busy} onClick={() => chosen && void run(() => attach(chosen))}>Attach selected version</button> : null}
    </> : <><label className="section-title">Find a reviewed answer<input className="profile-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by question" /></label><ul className="field-list">{library.answers.filter((answer) => answer.question.toLowerCase().includes(search.toLowerCase())).map((answer) => <li key={answer.question} className="document-item"><strong>{answer.question}</strong><span className="profile-value">{answer.text}</span><button className="icon-button" type="button" onClick={() => void run(async () => { await navigator.clipboard.writeText(answer.text); setStatus("Answer copied."); })}>Copy answer</button></li>)}</ul></>}
    <details><summary className="section-title">{mode === "documents" ? "Generate a tailored document" : "Draft an answer"}</summary>
      {mode === "documents" ? <label className="section-title">Document type<select className="profile-search" value={kind} onChange={(event) => setKind(event.target.value as "cv" | "cover_letter")}><option value="cv">Resume</option><option value="cover_letter">Cover letter</option></select></label> : <label className="section-title">Application question<textarea className="profile-search" rows={3} maxLength={3000} value={question} onChange={(event) => setQuestion(event.target.value)} /></label>}
      <label className="section-title">Job description<textarea className="profile-search" rows={5} maxLength={50000} value={jobText} onChange={(event) => setJobText(event.target.value)} placeholder="Paste the job description" /></label>
      <label className="section-title">Writing preferences (optional)<textarea className="profile-search" rows={2} maxLength={2000} value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="Language, length, or points to emphasize" /></label>
      <button type="button" className="primary" disabled={busy || !jobText.trim() || (mode === "answers" && !question.trim())} onClick={() => void run(async () => {
        const requestedKind = mode === "answers" ? "answer" : kind;
        const result = await workspaceRequest<{ text: string }>("draft", { kind: requestedKind, description: jobText, question, instructions });
        setDraft(result.text); setDraftKind(requestedKind); setDraftQuestion(question); setName(requestedKind === "cv" ? "Application resume" : "Application cover letter");
        setStatus("Draft ready. Review and edit it below.");
      })}>{busy ? "Working…" : "Generate draft"}</button>
    </details>
    {draft ? <div className="draft-preview"><label className="section-title">Review and edit draft<textarea aria-label="Draft preview" className="profile-search" rows={12} maxLength={draftKind === "answer" ? 10000 : 30000} value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
      {draftKind !== "answer" ? <label className="section-title">Save as<input className="profile-search" value={name} maxLength={150} onChange={(event) => setName(event.target.value)} /></label> : <p className="job-meta">{draftQuestion}</p>}
      <button type="button" className="primary" disabled={busy || !draft.trim() || (draftKind !== "answer" && !name.trim())} onClick={() => void run(async () => {
        if (draftKind === "answer") {
          await workspaceRequest("save-answer", { question: draftQuestion, text: draft });
          await refresh(); setStatus("Reviewed answer saved. Copy it from your library.");
        } else {
          const result = await workspaceRequest<{ document: LibraryDocument }>("save-document", { kind: draftKind, name, text: draft });
          await refresh(); rememberSelection(result.document.id); setStatus("Document saved. Attach the selected version when ready.");
        }
      })}>{draftKind === "answer" ? "Save reviewed answer" : "Save reviewed document"}</button>
      <button className="icon-button" type="button" onClick={() => void run(async () => { await navigator.clipboard.writeText(draft); setStatus("Draft copied."); })}>Copy draft</button>
      <button className="icon-button" type="button" disabled={busy} onClick={() => setDraft("")}>Discard draft</button>
    </div> : null}
    {error ? <p className="job-meta" role="alert">{error}</p> : null}{busy || status ? <p className="job-meta" role="status">{busy ? "Working…" : status}</p> : null}
  </section>;
}

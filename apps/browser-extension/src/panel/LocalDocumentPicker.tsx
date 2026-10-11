import { useState } from "react";
import type { DocumentRole } from "@runr/ats-core/generic-upload";

export default function LocalDocumentPicker({ role, onAttach }: {
  role: DocumentRole;
  onAttach: (role: DocumentRole, file: File, replace: boolean) => Promise<string>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const label = role === "cv" ? "Resume" : "Cover letter";
  async function attach() {
    if (!file || busy) return;
    setBusy(true); setStatus("");
    try { setStatus(await onAttach(role, file, replace)); }
    catch { setStatus("Couldn't attach this file. Upload it on the application form."); }
    finally { setBusy(false); }
  }
  return <div className="document-item" data-testid={`runr-local-document-${role}`}>
    <label className="section-title" htmlFor={`runr-file-${role}`}>{label} from your computer</label>
    <input className="local-file" id={`runr-file-${role}`} type="file" accept=".pdf,.docx" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setStatus(""); setReplace(false); }} />
    {file ? <>
      <span className="profile-value">{file.name} · {Math.ceil(file.size / 1024)} KB</span>
      <label className="replace-file"><input type="checkbox" checked={replace} disabled={busy} onChange={(event) => setReplace(event.target.checked)} />Replace the file already attached to this field</label>
      <button type="button" className="primary" disabled={busy} onClick={() => void attach()}>{busy ? "Attaching…" : `Attach ${label.toLowerCase()}`}</button>
    </> : null}
    {status ? <p className="job-meta" role="status">{status}</p> : null}
  </div>;
}

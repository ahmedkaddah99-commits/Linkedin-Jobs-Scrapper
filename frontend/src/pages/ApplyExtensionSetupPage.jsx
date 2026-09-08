import { Link } from "react-router-dom";

const EXTENSION_URL = "https://chromewebstore.google.com/detail/runr-assisted-apply/najcdfohhfgbjpbokhmmekkahghfhegp";

export default function ApplyExtensionSetupPage() {
  return <div className="setup-flow-page">
    <Link className="setup-flow-back" to="/"><span className="material-symbols-outlined">arrow_back</span>Back to Home</Link>
    <header><span className="setup-flow-icon material-symbols-outlined">extension</span><span className="runr-eyebrow">Runr Apply</span><h1>Set up the Apply extension</h1><p>Install once, then use Runr to fill applications from your profile.</p></header>
    <section className="setup-flow-steps">
      <article><span>1</span><div><h2>Install the extension</h2><p>Add Runr Apply to this browser.</p></div><a href={EXTENSION_URL} rel="noreferrer" target="_blank">Install extension<span className="material-symbols-outlined">open_in_new</span></a></article>
      <article><span>2</span><div><h2>Connect Runr</h2><p>Open the extension and choose <b>Connect to Runr</b>.</p></div></article>
      <article><span>3</span><div><h2>Apply from a job page</h2><p>Runr prepares the application; you review before submitting.</p></div><Link to="/jobs">Find jobs<span className="material-symbols-outlined">arrow_forward</span></Link></article>
    </section>
    <div className="setup-flow-note"><span className="material-symbols-outlined">lock</span><p>Runr never submits an application without your review.</p><Link to="/settings/assisted-apply">Connection settings</Link></div>
  </div>;
}

import { Link } from "react-router-dom";

const EXTENSION_URL = "https://chromewebstore.google.com/detail/runr-assisted-apply/najcdfohhfgbjpbokhmmekkahghfhegp";
const LINKEDIN_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/";

export default function LinkedInConnectionsGuidePage() {
  return <div className="setup-flow-page">
    <Link className="setup-flow-back" to="/"><span className="material-symbols-outlined">arrow_back</span>Back to Home</Link>
    <header><span className="setup-flow-icon material-symbols-outlined">group_add</span><span className="runr-eyebrow">Referrals</span><h1>Connect your LinkedIn network</h1><p>Install the extension, keep LinkedIn open, then sync.</p></header>
    <section className="setup-flow-steps">
      <article><span>1</span><div><h2>Install the Runr extension</h2><p>The extension must be connected before the first sync.</p></div><a href={EXTENSION_URL} rel="noreferrer" target="_blank">Install extension<span className="material-symbols-outlined">open_in_new</span></a></article>
      <article><span>2</span><div><h2>Open LinkedIn connections</h2><p>Sign in and leave this tab open in the same browser.</p></div><a href={LINKEDIN_CONNECTIONS_URL} rel="noreferrer" target="_blank">Open LinkedIn<span className="material-symbols-outlined">open_in_new</span></a></article>
      <article><span>3</span><div><h2>Sync connections</h2><p>Return to Runr and start the sync.</p></div><Link to="/refer?section=linkedin">Sync in Runr<span className="material-symbols-outlined">arrow_forward</span></Link></article>
    </section>
    <div className="setup-flow-note"><span className="material-symbols-outlined">lock</span><p>Runr reads the LinkedIn tab only when you start a sync.</p></div>
  </div>;
}

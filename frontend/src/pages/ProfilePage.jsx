import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import ProfileOverview from "../components/profile/ProfileOverview";
import ProfileEditor from "../components/profile/ProfileEditor";
import { profileWithResumeDefaults } from "../lib/profileEditor";
import "../components/profile/profile.css";

export default function ProfilePage({ completionFlow = false, editor = false, initialSection = "personal", onSaved, onBusy } = {}) {
  const { request } = useSession();
  const settings = useApiResource(() => request("/settings"), [], { cacheKey: "settings", staleMs: 30000, immediate: !editor && !completionFlow });
  const prefs = useApiResource(() => request("/personalized-jobs/preferences"), [], { cacheKey: "job-preferences", staleMs: 30000, immediate: !editor && !completionFlow });
  if (editor || completionFlow) return <ProfileEditor completionFlow={completionFlow} initialSection={initialSection} onSaved={onSaved} onBusy={onBusy} />;
  if (!settings.data || !prefs.data) return <div className="profile-editor-state" role="status">{settings.error || prefs.error || "Loading profile..."}{settings.error || prefs.error ? <button onClick={() => { settings.refresh().catch(() => {}); prefs.refresh().catch(() => {}); }} type="button">Retry</button> : null}</div>;
  return <ProfileOverview settings={{ ...settings.data, profile: profileWithResumeDefaults(settings.data) }} preferences={prefs.data.preferences || prefs.data} onSaved={(saved, preferences) => { settings.setData(saved); prefs.setData(preferences); }} />;
}

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getPreviewEntitlement } from "../../lib/personalizedJobs";
import { saveUpgradeDismissal } from "../../lib/personalizedPreviewState";
import { logPersonalizedEvent } from "../../lib/personalizedAnalytics";

export default function PreviewUpgradeModal({ featureKey, onClose }) {
  const navigate = useNavigate();
  const entitlement = getPreviewEntitlement(featureKey);

  useEffect(() => {
    if (!featureKey) return undefined;
    logPersonalizedEvent("upgrade_prompt_shown", { featureKey });
    return undefined;
  }, [featureKey]);

  if (!featureKey) return null;

  function dismiss() {
    saveUpgradeDismissal(featureKey);
    logPersonalizedEvent("upgrade_prompt_dismissed", { featureKey });
    onClose();
  }

  function seePro() {
    logPersonalizedEvent("upgrade_cta_clicked", { featureKey });
    onClose();
    navigate("/pricing");
  }

  return (
    <div
      aria-label="Upgrade preview"
      aria-modal="true"
      className="preview-modal-backdrop"
      onKeyDown={(event) => {
        if (event.key === "Escape") dismiss();
      }}
      role="dialog"
    >
      <div className="preview-upgrade-modal">
        <div className="preview-upgrade-modal__icon">
          <span className="material-symbols-outlined">auto_awesome</span>
        </div>
        <p className="preview-eyebrow">Runr Pro</p>
        <h2>Stop reviewing jobs you cannot apply for</h2>
        <p className="preview-upgrade-modal__body">{entitlement.explanation}</p>
        <div className="preview-upgrade-modal__example">
          <span className="material-symbols-outlined">check_circle</span>
          <span>
            <strong>What you would get</strong>
            <br />
            A clearer next step for every job, before you spend time preparing an application.
          </span>
        </div>
        <div className="preview-upgrade-modal__actions">
          <button className="preview-button preview-button--quiet" onClick={dismiss} type="button">
            Maybe later
          </button>
          <button className="preview-button preview-button--primary" onClick={seePro} type="button">
            See Runr Pro
            <span className="material-symbols-outlined text-[17px]">arrow_forward</span>
          </button>
        </div>
        <p className="preview-modal-footnote">Preview only — no plan change happens from this screen.</p>
      </div>
    </div>
  );
}


import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getPreviewEntitlement, getPreviewUpgradeCopy } from "../../lib/personalizedJobs";
import { saveUpgradeDismissal } from "../../lib/personalizedPreviewState";
import { logPersonalizedEvent } from "../../lib/personalizedAnalytics";

export default function PreviewUpgradeModal({ featureKey, onClose }) {
  const navigate = useNavigate();
  const entitlement = getPreviewEntitlement(featureKey);
  const copy = getPreviewUpgradeCopy(featureKey);

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
      aria-labelledby="preview-upgrade-title"
      aria-modal="true"
      className="preview-modal-backdrop"
      onKeyDown={(event) => {
        if (event.key === "Escape") dismiss();
      }}
      role="dialog"
    >
      <div className="preview-upgrade-modal">
        <button aria-label="Close upgrade message" className="preview-modal-close" onClick={dismiss} type="button">
          <span className="material-symbols-outlined">close</span>
        </button>
        <div className="preview-upgrade-modal__icon">
          <span className="material-symbols-outlined">auto_awesome</span>
        </div>
        <p className="preview-eyebrow">Runr Pro</p>
        <h2 id="preview-upgrade-title">{copy.title}</h2>
        <p className="preview-upgrade-modal__body">{copy.body}</p>
        <div className="preview-upgrade-modal__example">
          <span className="material-symbols-outlined">check_circle</span>
          <span>
            <strong>What you would get</strong>
            <br />
            {entitlement.explanation}
          </span>
        </div>
        <div className="preview-upgrade-modal__actions">
          <button className="preview-button preview-button--quiet" onClick={dismiss} type="button">
            Maybe later
          </button>
          <button className="preview-button preview-button--primary" onClick={seePro} type="button">
            {copy.cta}
            <span className="material-symbols-outlined text-[17px]">arrow_forward</span>
          </button>
        </div>
        <p className="preview-modal-footnote">Preview only — no plan change happens from this screen.</p>
      </div>
    </div>
  );
}

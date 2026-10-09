import assert from "node:assert/strict";
import test from "node:test";

import {
  selectedWorkspaceCvMissingFromPayload,
  toWorkspaceCvAssetOption,
} from "./workspaceCvAssetState.js";

test("selected workspace CV is not missing while processing", () => {
  const payload = {
    documents: [
      {
        asset_id: "asset_processing",
        asset_kind: "workspace_cv",
        display_name: "Resume.docx",
        display_status: "processing",
      },
    ],
  };

  assert.equal(selectedWorkspaceCvMissingFromPayload(payload, "asset_processing"), false);
  assert.equal(selectedWorkspaceCvMissingFromPayload(payload, "asset_other"), true);
});

test("processing workspace CV remains visible in selector options", () => {
  assert.deepEqual(
    toWorkspaceCvAssetOption({
      asset_id: "asset_processing",
      asset_kind: "workspace_cv",
      display_name: "Resume.docx",
      display_status: "processing",
    }),
    {
      value: "asset_processing",
      label: "Resume.docx (processing)",
      assetId: "asset_processing",
      createdAt: undefined,
      downloadUrl: undefined,
      sourceOrigin: undefined,
      status: "processing",
      previewProfile: null,
    },
  );
});

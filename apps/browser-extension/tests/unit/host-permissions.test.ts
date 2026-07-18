import { beforeEach, describe, expect, it, vi } from "vitest";
import { fakeBrowser } from "wxt/testing/fake-browser";
import {
  OPTIONAL_HOST_PERMISSION_PATTERNS,
  permissionOrigin,
  hasAllOptionalHostPermissions,
  hasPortalPermission,
  portalPermissionPatterns,
  requestPortalPermission,
  requestAllOptionalHostPermissions,
  missingPortalPermissions,
  recoverRevokedPermission,
} from "../../src/permissions/host-permissions";

describe("host permission module", () => {
  beforeEach(() => {
    fakeBrowser.reset();
    vi.restoreAllMocks();
  });

  describe("constants", () => {
    it("declares Greenhouse and Lever as optional host permission patterns", () => {
      expect(OPTIONAL_HOST_PERMISSION_PATTERNS).toEqual([
        "https://boards.greenhouse.io/*",
        "https://*.lever.co/*",
      ]);
    });
  });

  describe("permissionOrigin", () => {
    it("returns the correct origin for Greenhouse", () => {
      expect(permissionOrigin("greenhouse")).toBe("https://boards.greenhouse.io");
    });

    it("returns the correct origin for Lever", () => {
      expect(permissionOrigin("lever")).toBe("https://*.lever.co");
    });
  });

  describe("portalPermissionPatterns", () => {
    it("returns the Greenhouse pattern", () => {
      expect(portalPermissionPatterns("greenhouse")).toEqual([
        "https://boards.greenhouse.io/*",
      ]);
    });

    it("returns the Lever pattern", () => {
      expect(portalPermissionPatterns("lever")).toEqual([
        "https://*.lever.co/*",
      ]);
    });
  });

  describe("hasPortalPermission", () => {
    it("returns true when the extension already has the Greenhouse permission", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(true);
      await expect(hasPortalPermission("greenhouse")).resolves.toBe(true);
      expect(fakeBrowser.permissions.contains).toHaveBeenCalledWith({
        origins: ["https://boards.greenhouse.io/*"],
      });
    });

    it("returns false when the extension does not have the Lever permission", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(false);
      await expect(hasPortalPermission("lever")).resolves.toBe(false);
      expect(fakeBrowser.permissions.contains).toHaveBeenCalledWith({
        origins: ["https://*.lever.co/*"],
      });
    });
  });

  describe("hasAllOptionalHostPermissions", () => {
    it("returns true when all patterns are granted", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(true);
      await expect(hasAllOptionalHostPermissions()).resolves.toBe(true);
      expect(fakeBrowser.permissions.contains).toHaveBeenCalledWith({
        origins: OPTIONAL_HOST_PERMISSION_PATTERNS,
      });
    });

    it("returns false when some patterns are missing", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(false);
      await expect(hasAllOptionalHostPermissions()).resolves.toBe(false);
    });
  });

  describe("requestPortalPermission", () => {
    it("does not request already-granted permissions", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(true);
      const result = await requestPortalPermission("greenhouse");
      expect(result).toBe(true);
      expect(fakeBrowser.permissions.request).not.toHaveBeenCalled();
    });

    it("requests and returns true when the user grants", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(false);
      vi.mocked(fakeBrowser.permissions.request).mockResolvedValue(true);
      const result = await requestPortalPermission("lever");
      expect(result).toBe(true);
      expect(fakeBrowser.permissions.request).toHaveBeenCalledWith({
        origins: ["https://*.lever.co/*"],
      });
    });

    it("returns false when the user denies", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(false);
      vi.mocked(fakeBrowser.permissions.request).mockResolvedValue(false);
      const result = await requestPortalPermission("greenhouse");
      expect(result).toBe(false);
    });
  });

  describe("requestAllOptionalHostPermissions", () => {
    it("skips the request when all permissions are already granted", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(true);
      const result = await requestAllOptionalHostPermissions();
      expect(result).toBe(true);
      expect(fakeBrowser.permissions.request).not.toHaveBeenCalled();
    });

    it("requests all patterns at once", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(false);
      vi.mocked(fakeBrowser.permissions.request).mockResolvedValue(true);
      const result = await requestAllOptionalHostPermissions();
      expect(result).toBe(true);
      expect(fakeBrowser.permissions.request).toHaveBeenCalledWith({
        origins: OPTIONAL_HOST_PERMISSION_PATTERNS,
      });
    });
  });

  describe("missingPortalPermissions", () => {
    it("returns an empty list when all permissions are granted", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(true);
      const missing = await missingPortalPermissions();
      expect(missing).toEqual([]);
    });

    it("lists missing permission origins", async () => {
      vi.mocked(fakeBrowser.permissions.contains)
        .mockResolvedValueOnce(false)
        .mockResolvedValueOnce(true);
      const missing = await missingPortalPermissions();
      expect(missing).toEqual([
        { portal: "greenhouse", origin: "https://boards.greenhouse.io" },
      ]);
    });
  });

  describe("recoverRevokedPermission", () => {
    it("re-requests a revoked permission", async () => {
      vi.mocked(fakeBrowser.permissions.contains).mockResolvedValue(false);
      vi.mocked(fakeBrowser.permissions.request).mockResolvedValue(true);
      const result = await recoverRevokedPermission("greenhouse");
      expect(result).toBe(true);
      expect(fakeBrowser.permissions.request).toHaveBeenCalledWith({
        origins: ["https://boards.greenhouse.io/*"],
      });
    });
  });
});

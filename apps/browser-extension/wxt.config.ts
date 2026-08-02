import { defineConfig } from "wxt";

export default defineConfig({
  manifestVersion: 3,
  modules: ["@wxt-dev/module-react"],
  manifest: ({ mode, browser }) => ({
    name: "Runr Assisted Apply",
    description:
      "Review-first assistance for supported job applications. Runr never submits an application for you.",
    version: "0.2.2",
    ...(browser === "chrome"
      ? {
          key: "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA9vfcDQbZcLIkeK0Y9Ddx89ViTTdSQIOvRIprwztytepFOdyw6AZdGK9wpR3Fo47XiP+0F6OZshp4JQXXPDLWCU1VKPs6CXl7Sh8j7VrdEn9ptLHbFYRPOUjgriR3ZxM5Ad+sEMuF84lMDb8YFDHeqUFjRsit37f97sQuL+1Tl+tGv1uK2CqA3h+t6+MSWj658BVIYWRla9bwhpoGQFgLxIeh4/pbBfaXS8AvcZ9R8UQnieDg6kIqyXZd+JV62UyxagQaLaLiZAmNcKznqMwvDKMxZ24bmQ1A8VKGKFWHGw7bM46SBFQ4yisTkb/xwDbXbyHhLpddlyQULifvr3z3wwIDAQAB",
          minimum_chrome_version: "116",
        }
      : {
          minimum_edge_version: "120",
        }),
    icons: {
      16: "icons/runr-16.png",
      32: "icons/runr-32.png",
      48: "icons/runr-48.png",
      128: "icons/runr-128.png",
    },
    action: {
      default_title: "Open Runr Assisted Apply",
      default_icon: {
        16: "icons/runr-16.png",
        32: "icons/runr-32.png",
        48: "icons/runr-48.png",
        128: "icons/runr-128.png",
      },
    },
    side_panel: { default_path: "sidepanel.html" },
    permissions: ["activeTab", "identity", "scripting", "sidePanel", "storage"],
    host_permissions:
      mode === "testing" ? ["http://127.0.0.1/*"] : ["https://runr-api.onrender.com/*"],
    optional_host_permissions:
      mode === "testing"
        ? ["http://127.0.0.1/*"]
        : ["https://boards.greenhouse.io/*", "https://*.lever.co/*"],
    externally_connectable: {
      matches: mode === "testing" ? ["http://127.0.0.1/*"] : ["https://app.userunr.com/*"],
    },
  }),
});

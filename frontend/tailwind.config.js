export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#14B8A6", "primary-container": "#14b8a6", "primary-fixed-dim": "#4fdbc8", "primary-fixed": "#71f8e4",
        "on-primary": "#ffffff", "on-primary-container": "#00423b", "on-primary-fixed": "#00201c", "on-primary-fixed-variant": "#005048",
        secondary: "#545f73", "secondary-container": "#d5e0f8", "secondary-fixed": "#d8e3fb", "secondary-fixed-dim": "#bcc7de",
        "on-secondary": "#ffffff", "on-secondary-container": "#586377", "on-secondary-fixed": "#111c2d", "on-secondary-fixed-variant": "#3c475a",
        tertiary: "#9b4426", "tertiary-container": "#f38764", "tertiary-fixed": "#ffdbd0", "tertiary-fixed-dim": "#ffb59e",
        "on-tertiary": "#ffffff", "on-tertiary-container": "#6c2106", "on-tertiary-fixed": "#3a0b00", "on-tertiary-fixed-variant": "#7c2d11",
        error: "#ba1a1a", "error-container": "#ffdad6", "on-error": "#ffffff", "on-error-container": "#93000a",
        background: "#f8f9ff", "on-background": "#0b1c30", surface: "#f8f9ff", "surface-dim": "#cbdbf5", "surface-bright": "#f8f9ff",
        "surface-container-lowest": "#ffffff", "surface-container-low": "#eff4ff", "surface-container": "#e5eeff", "surface-container-high": "#dce9ff",
        "surface-container-highest": "#d3e4fe", "surface-variant": "#d3e4fe", "surface-tint": "#14B8A6", "on-surface": "#0b1c30",
        "on-surface-variant": "#3c4947", outline: "#6c7a77", "outline-variant": "#bbcac6", "inverse-surface": "#213145", "inverse-on-surface": "#eaf1ff", "inverse-primary": "#4fdbc8",
      },
      fontFamily: { headline: ["Plus Jakarta Sans", "sans-serif"], body: ["Plus Jakarta Sans", "sans-serif"], label: ["Plus Jakarta Sans", "sans-serif"] },
      borderRadius: { DEFAULT: "0.25rem", lg: "0.5rem", xl: "0.75rem", full: "9999px" },
      boxShadow: { soft: "0px 12px 32px rgba(11,28,48,0.06)" },
    },
  },
};

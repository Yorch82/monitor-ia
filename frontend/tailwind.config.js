/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#05070d",
          900: "#0a0e18",
          850: "#0d1220",
          800: "#111827",
          700: "#1a2333",
        },
        accent: {
          cyan: "#22d3ee",
          blue: "#3b82f6",
          emerald: "#34d399",
          amber: "#fbbf24",
          red: "#f87171",
          violet: "#a78bfa",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.7)",
        glow: "0 0 18px -4px rgba(34,211,238,0.35)",
      },
      keyframes: {
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "live-pulse": "pulse 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

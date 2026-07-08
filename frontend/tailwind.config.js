/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Calm indigo accent + neutral surfaces (light, airy palette).
        brand: {
          50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc",
          400: "#818cf8", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca",
        },
        ink: {
          50: "#f7f8fa", 100: "#eef0f4", 200: "#e2e5ec", 300: "#cbd0da",
          400: "#9aa2b1", 500: "#6b7280", 600: "#4b5563", 700: "#374151",
          800: "#1f2937", 900: "#111827",
        },
        ok: "#16a34a",
        warn: "#d97706",
        bad: "#dc2626",
      },
      fontFamily: {
        sans: ["'Plus Jakarta Sans'", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Sora", "'Plus Jakarta Sans'", "ui-sans-serif", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
        card: "0 1px 3px rgba(16,24,40,0.06), 0 4px 12px rgba(16,24,40,0.05)",
      },
      borderRadius: { xl: "0.875rem", "2xl": "1.125rem" },
    },
  },
  plugins: [],
};

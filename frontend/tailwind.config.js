/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Deep maroon/burgundy - the primary "official seal" brand color,
        // deliberately distinct from typical AI-chat orange/cream palettes.
        maroon: {
          50: "#faf1f2",
          100: "#f0dadd",
          400: "#a8394a",
          500: "#7a1f2b",
          600: "#631822",
          700: "#4c121a",
          800: "#390d13",
          900: "#26080d",
        },
        charcoal: {
          50: "#f4f5f6",
          100: "#e4e6e9",
          200: "#c7cbd1",
          300: "#9aa1ab",
          400: "#6b7280",
          500: "#454b56",
          600: "#2f333c",
          700: "#20232a",
          800: "#16181d",
          900: "#0d0e11",
        },
        gold: {
          50: "#faf6e9",
          100: "#f0e4bd",
          400: "#c9a53f",
          500: "#a9822a",
          600: "#8a6a20",
        },
        paper: {
          DEFAULT: "#eef0f1",
          100: "#f7f8f8",
          200: "#eef0f1",
          300: "#e2e5e7",
        },
      },
      fontFamily: {
        serif: ["'Source Serif 4'", "Georgia", "serif"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(13,14,17,0.06), 0 1px 1px rgba(13,14,17,0.04)",
      },
    },
  },
  plugins: [],
}

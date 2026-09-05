/**
 * DORMANT until Node is installed. The colours below mirror the hand-written
 * values in src/popup/popup.css and src/shared/presentation.js, so switching
 * to Tailwind is a cosmetic change rather than a redesign.
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ["./src/**/*.{html,js,ts}"],
  theme: {
    extend: {
      colors: {
        sentinel: {
          ink: "#0f172a",
          accent: "#38bdf8",
          low: "#15803d",
          lowSurface: "#dcfce7",
          medium: "#a16207",
          mediumSurface: "#fef9c3",
          high: "#b91c1c",
          highSurface: "#fee2e2",
          unknown: "#475569",
        },
      },
    },
  },
  plugins: [],
};

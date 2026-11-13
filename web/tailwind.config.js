import animate from "tailwindcss-animate";

/** NADI console design tokens (docs/design/DIRECTION.md): neutral greys, brand purple for the frame and controls,
 *  signal teal for what the sensors measure, and colour for status. */
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Inter Variable"', "Inter", "Segoe UI", "system-ui", "sans-serif"] },
      fontSize: {
        // 14 px is the smallest text in the console: the small steps exist only so library classes land on it
        "2xs": ["14px", "20px"], xs: ["14px", "20px"], sm: ["14px", "20px"], base: ["14px", "20px"],
        md: ["15px", "22px"], lg: ["17px", "24px"], xl: ["20px", "28px"], "2xl": ["24px", "32px"],
      },
      borderRadius: { lg: "10px", md: "6px", sm: "4px" },
      colors: {
        border: "hsl(var(--border) / <alpha-value>)", input: "hsl(var(--input) / <alpha-value>)", ring: "hsl(var(--ring) / <alpha-value>)",
        background: "hsl(var(--background) / <alpha-value>)", foreground: "hsl(var(--foreground) / <alpha-value>)",
        primary: { DEFAULT: "hsl(var(--primary) / <alpha-value>)", foreground: "hsl(var(--primary-foreground) / <alpha-value>)", soft: "hsl(var(--primary-soft) / <alpha-value>)" },
        secondary: { DEFAULT: "hsl(var(--secondary) / <alpha-value>)", foreground: "hsl(var(--secondary-foreground) / <alpha-value>)" },
        destructive: { DEFAULT: "hsl(var(--destructive) / <alpha-value>)", foreground: "hsl(var(--destructive-foreground) / <alpha-value>)" },
        muted: { DEFAULT: "hsl(var(--muted) / <alpha-value>)", foreground: "hsl(var(--muted-foreground) / <alpha-value>)" },
        accent: { DEFAULT: "hsl(var(--accent) / <alpha-value>)", foreground: "hsl(var(--accent-foreground) / <alpha-value>)" },
        popover: { DEFAULT: "hsl(var(--popover) / <alpha-value>)", foreground: "hsl(var(--popover-foreground) / <alpha-value>)" },
        card: { DEFAULT: "hsl(var(--card) / <alpha-value>)", foreground: "hsl(var(--card-foreground) / <alpha-value>)" },
        sidebar: { DEFAULT: "hsl(var(--sidebar) / <alpha-value>)", foreground: "hsl(var(--sidebar-foreground) / <alpha-value>)" },
        ok: { DEFAULT: "hsl(var(--ok) / <alpha-value>)", soft: "hsl(var(--ok-soft) / <alpha-value>)" },
        warn: { DEFAULT: "hsl(var(--warn) / <alpha-value>)", soft: "hsl(var(--warn-soft) / <alpha-value>)" },
        crit: { DEFAULT: "hsl(var(--crit) / <alpha-value>)", soft: "hsl(var(--crit-soft) / <alpha-value>)" },
        off: { DEFAULT: "hsl(var(--off) / <alpha-value>)", soft: "hsl(var(--off-soft) / <alpha-value>)" },
        brand: { DEFAULT: "hsl(var(--brand) / <alpha-value>)", light: "hsl(var(--brand-light) / <alpha-value>)", deep: "hsl(var(--brand-deep) / <alpha-value>)", grey: "hsl(var(--brand-grey) / <alpha-value>)" },
        heading: "hsl(var(--heading) / <alpha-value>)",
        "nav-active": "hsl(var(--nav-active) / <alpha-value>)",
        plan: { wall: "hsl(var(--plan-wall) / <alpha-value>)", floor: "hsl(var(--plan-floor) / <alpha-value>)", line: "hsl(var(--plan-line) / <alpha-value>)" },
      },
      boxShadow: { panel: "0 1px 2px 0 rgb(16 24 32 / 0.04)", pop: "0 4px 16px -2px rgb(16 24 32 / 0.12)" },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
      },
      animation: { "accordion-down": "accordion-down 0.2s ease-out", "accordion-up": "accordion-up 0.2s ease-out" },
    },
  },
  plugins: [animate],
};

import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: {
        DEFAULT: "1rem",
        sm: "1.25rem",
        lg: "1.5rem",
      },
      screens: {
        "2xl": "1200px",
      },
    },
    extend: {
      colors: {
        background: "hsl(35 46% 97%)",
        foreground: "hsl(20 18% 14%)",
        card: "hsl(0 0% 100%)",
        "card-foreground": "hsl(20 18% 14%)",
        popover: "hsl(0 0% 100%)",
        "popover-foreground": "hsl(20 18% 14%)",
        primary: "hsl(16 80% 52%)",
        "primary-foreground": "hsl(35 60% 98%)",
        secondary: "hsl(40 45% 92%)",
        "secondary-foreground": "hsl(20 18% 14%)",
        muted: "hsl(40 28% 92%)",
        "muted-foreground": "hsl(24 10% 40%)",
        accent: "hsl(174 39% 90%)",
        "accent-foreground": "hsl(176 41% 22%)",
        destructive: "hsl(4 70% 54%)",
        "destructive-foreground": "hsl(35 60% 98%)",
        border: "hsl(22 28% 84%)",
        input: "hsl(22 28% 84%)",
        ring: "hsl(16 80% 52%)",
      },
      borderRadius: {
        lg: "1rem",
        md: "0.875rem",
        sm: "0.75rem",
      },
      boxShadow: {
        panel: "0 24px 60px rgba(109, 72, 42, 0.12)",
      },
      backgroundImage: {
        hero: "linear-gradient(135deg, rgba(255,248,241,0.98), rgba(255,239,222,0.9))",
      },
    },
  },
  plugins: [],
} satisfies Config;

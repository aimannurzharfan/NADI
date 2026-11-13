// Per-browser preferences: light/dark theme and whether the sidebar is open (localStorage, best effort).
import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";
/** open: icons and names. rail: icons only. */
export type Sidebar = "open" | "rail";
type Settings = {
  theme: Theme; setTheme: (t: Theme) => void;
  sidebar: Sidebar; setSidebar: (s: Sidebar) => void;
};

const Ctx = createContext<Settings | null>(null);

/** From this width the sidebar starts open; below it, as an icon rail. The viewer's own choice wins once made. */
export const SIDEBAR_OPEN_FROM_PX = 1440;

function load<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* not kept: private mode */
  }
}

const sidebarByWidth = (): Sidebar => (typeof window !== "undefined" && window.innerWidth >= SIDEBAR_OPEN_FROM_PX ? "open" : "rail");

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => load("nadiTheme", ["light", "dark"] as const, "light"));
  const [sidebar, setSidebarState] = useState<Sidebar>(() => load("nadiSidebar", ["open", "rail"] as const, sidebarByWidth()));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    // the browser's own bar takes the colour of the header
    const header = getComputedStyle(document.documentElement).getPropertyValue("--card").trim();
    if (header) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", `hsl(${header})`);
  }, [theme]);
  const value: Settings = {
    theme, sidebar,
    setTheme: (t) => { setThemeState(t); save("nadiTheme", t); },
    setSidebar: (s) => { setSidebarState(s); save("nadiSidebar", s); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSettings() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSettings outside SettingsProvider");
  return v;
}

// The frame around every page (docs/design/DIRECTION.md):
//   header   hamburger and logo, the "Ask NADI" box in the middle, then alerts, language, theme, admin and the
//            button that starts emergency mode (always there)
//   sidebar  building, navigation, calibration; folds to an icon rail, the choice is remembered in the browser
//   main     the page, under the demo and offline banners
import {
  Bell, Cpu, Gauge, KeyRound, Languages, LayoutGrid, LogOut, Map, Menu, MessageSquareText, Moon,
  PanelRightOpen, Siren, Sun, Table2, Zap, type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useMatch } from "react-router-dom";

import { SignInDialog } from "@/components/admin";
import { DemoBanner, OfflineBanner } from "@/components/banners";
import { ChatPanel } from "@/components/chat-panel";
import { StartEmergencyDialog } from "@/components/emergency";
import { SiteSwitcher } from "@/components/site-switcher";
import { NadiLogo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { setAdminToken, setViewerToken, useMe, useRefreshAdmin, useRooms, viewerToken } from "@/lib/api";
import { LANG, T, otherLangHref } from "@/lib/i18n";
import { useSettings } from "@/lib/settings";
import { cn } from "@/lib/utils";

export const NAV = [
  { to: "/", key: "nav.overview", icon: LayoutGrid },
  { to: "/floor", key: "nav.floor", icon: Map },
  { to: "/rooms", key: "nav.rooms", icon: Table2 },
  { to: "/sensors", key: "nav.sensors", icon: Cpu },
  { to: "/energy", key: "nav.energy", icon: Zap },
  { to: "/alerts", key: "nav.alerts", icon: Bell },
] as const;

/** Alerts that still want a person: not acknowledged, not just information, from the last 24 hours. */
function useOpenAlerts(): number {
  const { data } = useRooms();
  return (data?.alerts ?? []).filter((a) => a.severity !== "info" && !a.ack && Date.now() / 1000 - a.ts < 86400).length;
}

/** True from the `lg` breakpoint: the sidebar is part of the page. Below it, the hamburger opens it over the page. */
function useWide(): boolean {
  const query = "(min-width: 1024px)";
  const read = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
  const [wide, setWide] = useState(read);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return wide;
}

/** One navigation row. Open: a pill with icon, name and (for alerts) the count on the right. Rail: the icon alone,
 *  with the name as a tooltip and for screen readers, and the count as a small badge on the icon. */
function NavItem({ to, label, icon: Icon, rail, count, end, onNavigate }: {
  to: string; label: string; icon: LucideIcon; rail: boolean; count?: number; end?: boolean; onNavigate?: () => void;
}) {
  // the class is a plain string, not NavLink's function form: the tooltip trigger merges class names as text
  const isActive = !!useMatch({ path: to, end: !!end });
  const link = (
    <NavLink to={to} end={end} onClick={onNavigate} aria-label={rail ? (count ? T("nav.alerts_count", { label, n: count }) : label) : undefined}
      className={cn(
        "relative flex h-10 items-center rounded-full text-base text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
        rail ? "mx-auto w-12 justify-center" : "gap-3 px-3.5",
        isActive && "bg-nav-active font-medium text-heading hover:bg-nav-active hover:text-heading")}>
      <Icon className="size-[18px] shrink-0" aria-hidden />
      {!rail && <span className="flex-1 truncate">{label}</span>}
      {!!count && (rail
        ? <span aria-hidden className="absolute right-1 top-0.5 min-w-5 rounded-full bg-[#B8352A] px-1 text-center text-base font-semibold leading-5 text-white">{count}</span>
        : <span className="rounded-full bg-crit-soft px-2 text-base font-semibold text-crit"><span className="sr-only">{T("nav.open_alerts")}: </span>{count}</span>)}
    </NavLink>
  );
  if (!rail) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

function SidebarBody({ rail, onNavigate }: { rail: boolean; onNavigate?: () => void }) {
  const open = useOpenAlerts();
  const me = useMe();
  return (
    <>
      <div className={cn("pb-2 pt-3", rail ? "px-0" : "px-3")}><SiteSwitcher rail={rail} /></div>
      <nav className={cn("flex flex-1 flex-col gap-1 py-1", rail ? "px-0" : "px-3")} aria-label={T("nav.label")}>
        {NAV.map(({ to, key, icon }) => (
          <NavItem key={to} to={to} end={to === "/"} label={T(key)} icon={icon} rail={rail} onNavigate={onNavigate}
            count={to === "/alerts" ? open : undefined} />
        ))}
        {/* labelling and the detector: for the project team, so only an admin is offered it */}
        {me.data?.admin && (
          <div className="mt-auto border-t pb-2 pt-2">
            <NavItem to="/calibration" label={T("nav.label_page")} icon={Gauge} rail={rail} onNavigate={onNavigate} />
          </div>
        )}
      </nav>
    </>
  );
}

function AdminStatus() {
  const me = useMe();
  const refresh = useRefreshAdmin();
  const [open, setOpen] = useState(false);
  if (!me.data) return null;
  if (me.data.admin) {
    const local = me.data.who === "localhost";
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="sm" className="h-9 gap-1.5 px-2 text-base" data-admin
            onClick={() => { if (!local) { setAdminToken(""); refresh(); } }}
            aria-label={local ? T("admin.signed_in_local") : T("admin.sign_out")}>
            <KeyRound className="size-[18px] text-ok" aria-hidden />
            <span className="hidden whitespace-nowrap 2xl:inline">{local ? T("admin.signed_in_local") : T("admin.signed_in_as", { who: me.data.who ?? "" })}</span>
            {!local && <LogOut className="size-4" aria-hidden />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{local ? T("admin.local_hint") : T("admin.sign_out")}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <>
      <Button variant="ghost" size="sm" className="h-9 gap-1.5 px-2 text-base" onClick={() => setOpen(true)} aria-label={T("admin.sign_in")}
        disabled={me.data.rule !== "token"} title={me.data.rule === "localhost" ? T("admin.needed_localhost") : undefined}>
        <KeyRound className="size-[18px]" aria-hidden /><span className="hidden xl:inline">{T("admin.sign_in")}</span>
      </Button>
      {me.data.viewer_required && viewerToken() && (
        <Button variant="ghost" size="icon" className="size-9" onClick={() => { setViewerToken(""); refresh(); }} aria-label={T("viewer.sign_out")}>
          <LogOut className="size-[18px]" aria-hidden />
        </Button>
      )}
      <SignInDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

/** The box in the middle of the header. Type a question and press Enter: the side panel opens and answers it. The
 *  button at its end (or Enter on an empty box) opens the panel with its suggested questions. "/" jumps to the box. */
function AskBox({ boxRef, onAsk, onOpen }: {
  boxRef: React.RefObject<HTMLInputElement>; onAsk: (question: string) => void; onOpen: () => void;
}) {
  const [q, setQ] = useState("");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      if (e.key !== "/" || typing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;  // a dialog has the keyboard
      e.preventDefault();
      boxRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [boxRef]);
  return (
    <>
      <form role="search" aria-label={T("chat.title")} data-ask-box
        className="mx-auto hidden h-11 min-w-0 max-w-2xl flex-1 items-center gap-2 rounded-full border bg-background pl-4 pr-1.5 focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/25 md:flex"
        onSubmit={(e) => { e.preventDefault(); if (q.trim()) onAsk(q.trim()); else onOpen(); setQ(""); }}>
        <MessageSquareText className="size-[18px] shrink-0 text-primary" aria-hidden />
        <input ref={boxRef} name="question" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} autoComplete="off" enterKeyHint="send"
          placeholder={T("ask.placeholder")} aria-label={T("ask.label")} aria-keyshortcuts="/"
          className="h-full min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground" />
        <kbd aria-hidden className="hidden rounded border px-1.5 text-base text-muted-foreground xl:block">/</kbd>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="icon" className="size-8 rounded-full" onClick={onOpen} aria-label={T("ask.open")} data-ask-open>
              <PanelRightOpen className="size-[18px]" aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{T("ask.open")}</TooltipContent>
        </Tooltip>
      </form>
      {/* on a phone there is no room for the box: one clear button opens the same panel */}
      <Button variant="outline" size="sm" className="ml-auto h-9 gap-1.5 rounded-full px-3 text-base md:hidden" onClick={onOpen}>
        <MessageSquareText className="size-[18px] text-primary" aria-hidden />{T("chat.title")}
      </Button>
    </>
  );
}

function Header({ menuOpen, wide, onMenu, boxRef, onAsk, onOpenChat }: {
  menuOpen: boolean; wide: boolean; onMenu: () => void; boxRef: React.RefObject<HTMLInputElement>; onAsk: (q: string) => void; onOpenChat: () => void;
}) {
  const { theme, setTheme } = useSettings();
  const open = useOpenAlerts();
  const [startOpen, setStartOpen] = useState(false);
  return (
    <header className="no-print flex h-[64px] shrink-0 items-center gap-2 border-b bg-card px-2 sm:gap-3 sm:px-3">
      {/* as wide as the open sidebar, so the box starts where the page starts */}
      <div className="flex shrink-0 items-center gap-2 lg:w-[224px]">
        <Button variant="ghost" size="icon" className="size-10 rounded-full" onClick={onMenu} data-menu
          aria-label={T(menuOpen ? "nav.collapse" : "nav.expand")} aria-expanded={menuOpen}
          {...(wide ? { "aria-controls": "sidebar" } : { "aria-haspopup": "dialog" as const })}>
          <Menu className="size-5" aria-hidden />
        </Button>
        <Link to="/" className="rounded-md px-1 py-1" aria-label={T("ui.home")} translate="no"><NadiLogo /></Link>
      </div>
      <AskBox boxRef={boxRef} onAsk={onAsk} onOpen={onOpenChat} />
      <div className="flex shrink-0 items-center gap-0.5 sm:gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="relative size-9" asChild>
              <Link to="/alerts" data-bell aria-label={open ? T("nav.alerts_count", { label: T("nav.alerts"), n: open }) : T("nav.alerts")}>
                <Bell className="size-[18px]" aria-hidden />
                {open > 0 && <span aria-hidden className="absolute -right-0.5 -top-0.5 min-w-5 rounded-full bg-[#B8352A] px-1 text-center text-base font-semibold leading-5 text-white">{open}</span>}
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{open ? T("nav.alerts_count", { label: T("nav.alerts"), n: open }) : T("nav.alerts")}</TooltipContent>
        </Tooltip>
        <Button variant="ghost" size="sm" className="hidden h-9 gap-1.5 px-2 text-base sm:inline-flex" asChild>
          <a href={otherLangHref()} lang={LANG === "ms" ? "en" : "ms"} aria-label={T("top.other_lang")}>
            <Languages className="size-[18px]" aria-hidden /><span className="hidden 2xl:inline">{T("top.other_lang")}</span>
          </a>
        </Button>
        <Button variant="ghost" size="icon" className="size-9" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={T(theme === "dark" ? "top.theme_light" : "top.theme_dark")}>
          {theme === "dark" ? <Sun className="size-[18px]" aria-hidden /> : <Moon className="size-[18px]" aria-hidden />}
        </Button>
        <AdminStatus />
        <Button size="sm" variant="outline" data-start-emergency
          className="ml-1 h-9 gap-1.5 border-crit bg-card px-3 text-base font-medium text-crit hover:bg-crit-soft hover:text-crit"
          onClick={() => setStartOpen(true)} aria-label={T("ui.start_emergency")}>
          <Siren className="size-[18px]" aria-hidden /><span className="hidden whitespace-nowrap lg:inline">{T("ui.start_emergency")}</span>
        </Button>
      </div>
      <StartEmergencyDialog open={startOpen} onOpenChange={setStartOpen} />
    </header>
  );
}

/** fill: the page lays itself out to fill the window (the overview); other pages scroll. */
export function AppShell({ children, fill }: { children: React.ReactNode; fill?: boolean }) {
  const { sidebar, setSidebar } = useSettings();
  const wide = useWide();
  const [drawer, setDrawer] = useState(false);  // below `lg` the sidebar opens over the page
  const [chat, setChat] = useState<{ open: boolean; ask: string | null }>({ open: false, ask: null });
  const boxRef = useRef<HTMLInputElement>(null);
  const rail = sidebar === "rail";
  const menuOpen = wide ? !rail : drawer;
  useEffect(() => { if (wide) setDrawer(false); }, [wide]);  // a window made wider has the sidebar in the page again
  return (
    <div className="flex h-screen min-h-0 flex-col bg-background">
      <a href="#main" className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:left-3 focus:top-3">
        {T("nav.skip")}
      </a>
      <Header menuOpen={menuOpen} wide={wide} onMenu={() => (wide ? setSidebar(rail ? "open" : "rail") : setDrawer(true))} boxRef={boxRef}
        onAsk={(q) => setChat({ open: true, ask: q })} onOpenChat={() => setChat({ open: true, ask: null })} />
      <div className="flex min-h-0 flex-1">
        <aside id="sidebar" data-sidebar={rail ? "rail" : "open"}
          className={cn("no-print hidden shrink-0 flex-col overflow-y-auto border-r bg-sidebar lg:flex", rail ? "w-[72px]" : "w-[240px]")}>
          <SidebarBody rail={rail} />
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <DemoBanner />
          <OfflineBanner />
          <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto outline-none">
            <div className={cn("flex flex-col gap-4 p-4 lg:p-5", fill && "xl:h-full xl:p-4")}>
              {children}
            </div>
          </main>
        </div>
      </div>
      <Sheet open={drawer && !wide} onOpenChange={setDrawer}>
        <SheetContent side="left" className="flex w-72 flex-col gap-0 p-0">
          <SheetTitle className="border-b px-4 py-4"><NadiLogo /><span className="sr-only">{T("nav.label")}</span></SheetTitle>
          <SheetDescription className="sr-only">{T("nav.label")}</SheetDescription>
          <SidebarBody rail={false} onNavigate={() => setDrawer(false)} />
        </SheetContent>
      </Sheet>
      <ChatPanel open={chat.open} onOpenChange={(open) => setChat((c) => ({ ...c, open }))} ask={chat.ask}
        onAsked={() => setChat((c) => ({ ...c, ask: null }))} returnFocus={boxRef} />
    </div>
  );
}

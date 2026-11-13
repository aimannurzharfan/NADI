import { KeyRound, LockKeyhole } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { adminToken, getJSON, setAdminToken, setViewerToken, useMe, useRefreshAdmin, viewerToken } from "@/lib/api";
import { T } from "@/lib/i18n";
import type { Me } from "@/lib/types";

/** Asks for the admin token, checks it with /api/me, and keeps it for this browser tab only. */
export function SignInDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useRefreshAdmin();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const before = adminToken();
    setAdminToken(token);
    try {
      const me = await getJSON<Me>("/api/me");
      if (me.admin) {
        refresh();
        setToken("");
        setError("");
        onOpenChange(false);
      } else {
        setAdminToken(before);
        setError(me.status === 429 ? T("api.locked_out", { minutes: 15 }) : T("admin.wrong_token"));
      }
    } catch (err) {
      setAdminToken(before);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{T("admin.sign_in_title")}</DialogTitle>
            <DialogDescription>{T("admin.sign_in_body")}</DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-2">
            <label htmlFor="admin-token" className="text-sm font-medium">{T("admin.token_label")}</label>
            <Input id="admin-token" type="password" autoComplete="current-password" value={token} autoFocus
              onChange={(e) => setToken(e.target.value)} />
            {error && <p role="alert" className="text-sm text-crit">{error}</p>}
          </div>
          <DialogFooter className="mt-5">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>{T("start.cancel")}</Button>
            <Button type="submit" disabled={!token || busy}>{T("admin.sign_in")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** VIEWER_TOKEN set on the server: the whole console needs the viewer token (or an admin token) first. */
export function ViewerGate({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const refresh = useRefreshAdmin();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (me.isLoading) return null;
  if (!me.data || me.data.viewer) return <>{children}</>;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const before = viewerToken();
    setViewerToken(token);
    try {
      const next = await getJSON<Me>("/api/me");
      if (next.viewer) {
        refresh();
        await me.refetch();
      } else {
        setViewerToken(before);
        setError(next.status === 429 ? T("api.locked_out", { minutes: 15 }) : T("admin.wrong_token"));
      }
    } catch (err) {
      setViewerToken(before);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-lg border bg-card p-6 shadow-panel">
        <div className="flex items-center gap-2">
          <LockKeyhole className="size-5 text-muted-foreground" aria-hidden />
          <h1 className="text-lg font-semibold">{T("viewer.title")}</h1>
        </div>
        <p className="text-sm text-muted-foreground">{T("viewer.body")}</p>
        <div className="space-y-2">
          <label htmlFor="viewer-token" className="text-sm font-medium">{T("viewer.token_label")}</label>
          <Input id="viewer-token" type="password" autoComplete="current-password" value={token} autoFocus
            onChange={(e) => setToken(e.target.value)} />
          {error && <p role="alert" className="text-sm text-crit">{error}</p>}
        </div>
        <Button type="submit" className="w-full" disabled={!token || busy}>{T("admin.sign_in")}</Button>
      </form>
    </main>
  );
}

/** Admin-only content. Others see why it is hidden and how to sign in; on the server computer no token is needed. */
export function AdminGate({ children, what }: { children: React.ReactNode; what: string }) {
  const me = useMe();
  const [open, setOpen] = useState(false);
  if (me.isLoading) return null;
  if (me.data?.admin) return <>{children}</>;
  const rule = me.data?.rule;
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-card px-6 py-10 text-center">
      <LockKeyhole className="size-6 text-muted-foreground" aria-hidden />
      <div>
        <p className="font-semibold">{T("admin.needed_title")}</p>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          {T("admin.needed_body", { what })} {rule === "localhost" ? T("admin.needed_localhost") : rule === "refused" ? T("admin.needed_refused") : ""}
        </p>
      </div>
      {rule !== "refused" && rule !== "localhost" && (
        <Button size="sm" onClick={() => setOpen(true)}><KeyRound className="size-4" />{T("admin.sign_in")}</Button>
      )}
      <SignInDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

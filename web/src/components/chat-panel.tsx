// Ask NADI: the same rules as before. Answers are worked out on the server from the live counts; a language model may
// only rephrase a checked answer, and the "which room first" list is never rephrased. The panel opens from the box in
// the header; while it is empty it offers three questions that send on click. Words only: no emoji, no pictures.
import { CornerDownLeft, Lock, MessageSquareText, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ApiError, postJSON, useInfo, useRooms } from "@/lib/api";
import { LANG, T } from "@/lib/i18n";
import { useSite } from "@/lib/site";
import type { ChatAnswer } from "@/lib/types";
import { cn } from "@/lib/utils";

type Line = { id: number; who: "q" | "a"; text: string; error?: boolean; model?: string; source?: string };
const KEEP = 40;
/** The suggested questions: two in English, one in Malay, whatever the language of the console, because the chat
 *  answers in the language of the question. Each is answered by a rule from the live counts. */
export const SUGGESTED: [string, "en" | "ms"][] = [["chat.q_total", "en"], ["chat.q_waste_which", "en"], ["chat.q_occupied", "ms"]];

export function ChatPanel({ open, onOpenChange, ask: asked, onAsked, returnFocus }: {
  open: boolean; onOpenChange: (v: boolean) => void;
  /** a question typed in the header box: sent once when the panel opens */
  ask?: string | null; onAsked?: () => void;
  /** where the keyboard focus goes when the panel closes (the header box) */
  returnFocus?: React.RefObject<HTMLElement>;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: info } = useInfo();
  // the scope: the floor chosen in the switcher, or the whole building; an emergency or drill locks the whole building
  const { floorId, floor } = useSite();
  const { data: live } = useRooms();
  const [whole, setWhole] = useState(false);
  const em = live?.emergency;
  const locked = !!em?.on;
  const floorName = floor?.name ?? info?.level ?? "";
  const end = useRef<HTMLDivElement>(null);
  const seq = useRef(0);
  const busyRef = useRef(false);

  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [lines, busy]);

  async function ask(question: string) {
    question = question.trim();
    if (!question || busyRef.current) return;
    busyRef.current = true;
    const qid = ++seq.current, aid = ++seq.current;
    setLines((l) => [...l, { id: qid, who: "q" as const, text: question }].slice(-KEEP));
    setQ("");
    setBusy(true);
    try {
      const res = await postJSON<ChatAnswer>("/api/chat", { question, lang: LANG, floor: whole || locked ? null : floorId }, 15000);
      setLines((l) => [...l, { id: aid, who: "a" as const, text: res.answer, model: res.model, source: res.source }].slice(-KEEP));
    } catch (e) {
      const detail = e instanceof ApiError && (e.status === 401 || e.status === 403) ? T("chat.admin_needed") : e instanceof Error ? e.message : String(e);
      setLines((l) => [...l, { id: aid, who: "a" as const, text: T("chat.not_answered", { detail }), error: true }].slice(-KEEP));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  // the question typed in the header: sent once, when the panel opens with it
  // (a question that arrives while another is being answered waits its turn; it is never dropped)
  useEffect(() => {
    if (!open || !asked || busy || busyRef.current) return;
    onAsked?.();
    void ask(asked);
  }, [open, asked, busy]);

  // The footer says where the numbers come from and who worded the reply: after an answer, that answer's own
  // source; before the first one, what the server says would answer now.
  const last = [...lines].reverse().find((l) => l.source);
  const worded = last ? (last.source !== "fallback" ? last.model : null)
    : info && info.chat_source && info.chat_source !== "rules" ? info.chat_model : null;
  const foot = !last && !info ? "" : worded ? T("chat.foot_model", { model: worded }) : T("chat.foot_rules");
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" data-ask-panel className="flex w-full flex-col gap-0 p-0 sm:max-w-md"
        onCloseAutoFocus={(e) => { if (returnFocus?.current) { e.preventDefault(); returnFocus.current.focus(); } }}>
        <SheetHeader className="border-b px-5 py-4 text-left">
          <SheetTitle className="flex items-center gap-2 text-lg text-heading">
            <MessageSquareText className="size-5 text-primary" aria-hidden />{T("chat.title")}
          </SheetTitle>
          <SheetDescription className="text-base">{T("chat.intro")}</SheetDescription>
        </SheetHeader>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-5 py-2.5 text-base" data-chat-scope={locked ? "locked" : whole ? "building" : "floor"}>
          {locked ? (
            <>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-crit/40 bg-crit-soft px-3 py-1 font-medium text-crit">
                <Lock className="size-4" aria-hidden />{T("scope.whole")}
              </span>
              <span className="text-muted-foreground">{T(em?.drill ? "scope.locked_drill" : "scope.locked_emergency")}</span>
            </>
          ) : (
            <div role="radiogroup" aria-label={T("scope.label")} className="flex overflow-hidden rounded-full border">
              {[[false, T("scope.this_floor", { floor: floorName })], [true, T("scope.whole")]].map(([w, label]) => (
                <button key={String(w)} type="button" role="radio" aria-checked={whole === w} onClick={() => setWhole(w as boolean)}
                  className={cn("px-3 py-1 font-medium", whole === w ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{label as string}</button>
              ))}
            </div>
          )}
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto overscroll-contain px-5 py-4 text-base" aria-live="polite">
          {!lines.length && !busy && (
            <div data-suggestions>
              <p className="font-medium">{T("chat.try")}</p>
              <p className="mt-0.5 text-muted-foreground">{T("chat.languages")}</p>
              <ul className="mt-3 space-y-2">
                {SUGGESTED.map(([key, lang]) => (
                  <li key={key}>
                    <button type="button" lang={lang} onClick={() => ask(T(key, undefined, lang))}
                      className="flex w-full items-center justify-between gap-3 rounded-full border bg-card px-4 py-2.5 text-left font-medium hover:border-primary hover:bg-primary-soft">
                      {T(key, undefined, lang)}<CornerDownLeft className="size-[18px] shrink-0 text-muted-foreground" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {lines.map((l) => (
            <div key={l.id} data-line={l.who} className={cn("max-w-[90%] rounded-lg px-3.5 py-2.5",
              l.who === "q" ? "ml-auto bg-primary text-primary-foreground" : "border bg-card", l.error && "border-crit/40 text-crit")}>
              <span className="sr-only">{T(l.who === "q" ? "chat.you" : "chat.nadi")}: </span>{l.text}
            </div>
          ))}
          {busy && <div className="w-fit rounded-lg border px-3.5 py-2.5 text-muted-foreground">{T("chat.waiting")}</div>}
          <div ref={end} />
        </div>
        <form className="flex gap-2 border-t px-5 py-3" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <Input name="question" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} placeholder={T("chat.placeholder")}
            aria-label={T("chat.question_label")} autoComplete="off" className="h-10 text-base" />
          <Button type="submit" size="icon" className="size-10 shrink-0" disabled={busy || !q.trim()} aria-label={T("chat.ask")}><Send className="size-[18px]" aria-hidden /></Button>
        </form>
        <p data-chat-foot className="px-5 pb-3 text-base text-muted-foreground">{foot}</p>
      </SheetContent>
    </Sheet>
  );
}

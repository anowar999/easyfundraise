"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, CalendarDays, Check, Send, Sparkles, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { errText, useToast } from "./ui";

type Action = { id: string; type: string; label: string; state: "pending" | "applied"; href?: string };
type Msg = { id: string; role: "user" | "assistant"; text: string; actions: Action[]; created_at: string };
type History = { items: Msg[]; ai: boolean; calendar?: boolean; agent_name: string };

const PROMPTS = [
  "How is my raise going?",
  "Find angels actively investing in healthcare, $250K–$500K cheques",
  "Is my data room complete? Write the Why now section for me",
  "Do I have any investor meetings this week?",
  "Email Jane from my tracker",
  "Update my signature to: Sam, CEO DocAI",
];

/** AGT-05 "Your Raise Agent": side panel on desktop, full screen on phones. It can act across the site;
 *  card moves, drafts and publishing wait for a tap, and nothing is ever sent from chat. */
export const ASK_EVENT = "raise-agent:ask";

/** Opens Your Raise Agent with a question, from anywhere on the page. */
export const askAgent = (text: string) => window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: text }));

/** Opens the chat panel without sending anything (e.g. "Continue in chat" from the tracker's agent bar). */
export const openAgent = () => window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: "" }));

export function AgentChat() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const end = useRef<HTMLDivElement>(null);
  const q = useQuery<History>({ queryKey: ["chat"], queryFn: () => api("/agent/chat"), enabled: open });
  const send = useMutation({
    mutationFn: (t: string) => api<Msg>("/agent/chat", { method: "POST", json: { text: t } }),
    onMutate: (t) => {
      setText("");
      qc.setQueryData<History>(["chat"], (h) => h && { ...h, items: [...h.items, { id: "tmp", role: "user", text: t, actions: [], created_at: "" }] });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["chat"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: ["funnel"] });
      qc.invalidateQueries({ queryKey: ["card"] });
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const apply = useMutation({
    mutationFn: ({ m, a }: { m: string; a: string }) => api<{ sequence_id?: string; card_id?: string }>(`/agent/chat/${m}/actions/${a}`, { method: "POST" }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["chat"] });
      qc.invalidateQueries({ queryKey: ["funnel"] });
      if (r.card_id) qc.invalidateQueries({ queryKey: ["card", r.card_id] });
      qc.invalidateQueries({ queryKey: ["room"] });
      if (r.sequence_id) {
        setOpen(false);
        router.push(`/app/sequences/${r.sequence_id}?new=1`);
      } else toast("Done");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const clear = useMutation({ mutationFn: () => api("/agent/chat", { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["chat"] }) });

  // The home page's "How can I help?" box hands its question over to this chat.
  useEffect(() => {
    const onAsk = (e: Event) => {
      const t = (e as CustomEvent<string>).detail?.trim();
      setOpen(true);
      if (t) send.mutate(t);
    };
    window.addEventListener(ASK_EVENT, onAsk);
    return () => window.removeEventListener(ASK_EVENT, onAsk);
  }, [send.mutate]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [q.data, open, send.isPending]);

  const name = q.data?.agent_name && !["Raise", "Raise Agent"].includes(q.data.agent_name) ? q.data.agent_name : "Your Raise Agent";
  const submit = () => {
    if (text.trim() && !send.isPending) send.mutate(text.trim());
  };
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={clsx("fixed z-30 right-4 md:right-6 bottom-[calc(76px_+_env(safe-area-inset-bottom))] md:bottom-6 h-12 rounded-full bg-brand text-white shadow-lg px-4 flex items-center gap-2 text-sm font-medium", open && "hidden")}
        aria-label="Open your Raise Agent"
      >
        <Sparkles size={18} /> <span className="hidden sm:inline">Your Raise Agent</span>
      </button>
      {open && (
        <div className="fixed z-50 inset-0 md:inset-auto md:right-4 md:bottom-4 md:top-4 md:w-[440px] bg-card md:rounded-2xl md:border border-line shadow-2xl flex flex-col" role="dialog" aria-label="Agent chat">
          <div className="flex items-center justify-between px-4 min-h-14 border-b border-line shrink-0 safe-top">
            <div className="flex items-center gap-2 font-semibold">
              <Sparkles size={18} className="text-brand" /> {name}
            </div>
            <div className="flex items-center gap-1">
              <button className="p-2 text-muted" onClick={() => clear.mutate()} aria-label="Clear chat">
                <Trash2 size={18} />
              </button>
              <button className="p-2 text-muted" onClick={() => setOpen(false)} aria-label="Close">
                <X size={20} />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {q.data && q.data.items.length === 0 && (
              <div className="space-y-3">
                <p className="text-sm text-ink/80">
                  I run your raise with you: find and research investors, manage your shortlist and tracker, fill your data room, update settings and draft emails. Nothing is ever sent without your confirmation.
                  {!q.data.ai && " AI isn't set up on this server yet, so I handle the common asks only."}
                </p>
                {!q.data.calendar && (
                  <a href="/api/gmail/connect?calendar=1&next=/app" className="flex items-center gap-2 rounded-xl border border-line px-3 py-2.5 text-sm hover:bg-surface">
                    <CalendarDays size={16} className="text-brand" />
                    <span className="flex-1">Connect Google Calendar so I can spot investor meetings</span>
                    <ArrowRight size={14} className="text-muted" />
                  </a>
                )}
                <div className="flex flex-col gap-2">
                  {PROMPTS.map((p) => (
                    <button key={p} className="text-left text-sm rounded-lg border border-line px-3 py-2 hover:bg-surface" onClick={() => send.mutate(p)}>
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {q.data?.items.map((m) => (
              <div key={m.id} className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className={clsx("max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap break-words", m.role === "user" ? "bg-brand text-white rounded-br-sm" : "bg-surface rounded-bl-sm")}>
                  {m.text}
                  {m.actions.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      {m.actions.map((a) => (
                        <div key={a.id} className="flex items-center gap-2 rounded-lg bg-card border border-line px-2.5 py-2 text-ink">
                          <span className="flex-1 text-xs">{a.label}</span>
                          {a.href ? (
                            <Link href={a.href} className="btn-ghost btn-sm" onClick={() => setOpen(false)}>
                              {a.type === "open_sequence" ? "Review" : a.type === "tracker_filter" ? "Show" : "Open"}
                            </Link>
                          ) : a.state === "pending" ? (
                            <button className="btn-primary btn-sm" disabled={apply.isPending} onClick={() => apply.mutate({ m: m.id, a: a.id })}>
                              Apply
                            </button>
                          ) : (
                            <span className="text-xs text-green-600 flex items-center gap-1">
                              <Check size={12} /> Done
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {send.isPending && <div className="text-sm text-muted">{name} is thinking…</div>}
            <div ref={end} />
          </div>
          <form
            className="p-3 border-t border-line shrink-0 safe-bottom"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="rounded-2xl border border-line bg-card focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/15">
              <textarea
                className="block w-full resize-none bg-transparent px-3.5 pt-3 text-[15px] outline-none focus-visible:outline-none placeholder:text-muted min-h-[72px] max-h-48"
                rows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    submit();
                  }
                }}
                placeholder="Ask anything about your raise, or tell me what to do…"
                aria-label="Message"
              />
              <div className="flex items-center justify-between px-3 pb-2">
                <span className="text-[11px] text-muted">Enter to send · Shift+Enter for a new line</span>
                <button className="btn-primary btn-sm" disabled={!text.trim() || send.isPending} aria-label="Send">
                  <Send size={15} />
                </button>
              </div>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

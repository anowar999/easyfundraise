"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, Send, Sparkles, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { errText, useToast } from "./ui";

type Action = { id: string; type: string; label: string; state: "pending" | "applied" };
type Msg = { id: string; role: "user" | "assistant"; text: string; actions: Action[]; created_at: string };
type History = { items: Msg[]; ai: boolean; agent_name: string };

const PROMPTS = ["Who should I follow up with today?", "Find seed investors in digital health in London", "I'm meeting Jane from Acme on Thursday", "Remind me to send the deck to Sam tomorrow"];

/** AGT-05: side panel on desktop, full screen on phones. Changes are proposals the founder applies with a tap. */
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
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const apply = useMutation({
    mutationFn: ({ m, a }: { m: string; a: string }) => api<{ sequence_id?: string; card_id?: string }>(`/agent/chat/${m}/actions/${a}`, { method: "POST" }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["chat"] });
      qc.invalidateQueries({ queryKey: ["funnel"] });
      if (r.card_id) qc.invalidateQueries({ queryKey: ["card", r.card_id] });
      if (r.sequence_id) {
        setOpen(false);
        router.push(`/app/sequences/${r.sequence_id}`);
      } else toast("Done");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const clear = useMutation({ mutationFn: () => api("/agent/chat", { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["chat"] }) });

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [q.data, open, send.isPending]);

  const name = q.data?.agent_name ?? "Raise";
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={clsx("fixed z-30 right-4 md:right-6 bottom-[calc(76px_+_env(safe-area-inset-bottom))] md:bottom-6 h-12 rounded-full bg-brand text-white shadow-lg px-4 flex items-center gap-2 text-sm font-medium", open && "hidden")}
        aria-label="Ask your agent"
      >
        <Sparkles size={18} /> <span className="hidden sm:inline">Ask your agent</span>
      </button>
      {open && (
        <div className="fixed z-50 inset-0 md:inset-auto md:right-4 md:bottom-4 md:top-4 md:w-[400px] bg-card md:rounded-2xl md:border border-line shadow-2xl flex flex-col" role="dialog" aria-label="Agent chat">
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
                <p className="text-sm text-muted">
                  I can search investors, look at your funnel, set reminders and draft emails. Anything that changes a card waits for your tap.
                  {!q.data.ai && " On your plan I answer with your funnel data and handle reminders; full chat comes with AI drafting."}
                </p>
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
                          {a.state === "pending" ? (
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
            className="p-3 border-t border-line flex gap-2 shrink-0 safe-bottom"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) send.mutate(text.trim());
            }}
          >
            <input className="input flex-1" value={text} onChange={(e) => setText(e.target.value)} placeholder={`Ask ${name}…`} aria-label="Message" />
            <button className="btn-primary px-3" disabled={!text.trim() || send.isPending} aria-label="Send">
              <Send size={18} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}

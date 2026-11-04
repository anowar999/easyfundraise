"use client";

import { ChatMarkdown } from "@/lib/markdown";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, MessageSquare, SendHorizontal, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { openAgent } from "@/components/AgentChat";
import { errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card } from "@/lib/types";

export type AgentFilter = {
  statuses?: string[];
  overdue?: boolean;
  due_today?: boolean;
  needs_action?: boolean;
  starred?: boolean;
  stale?: boolean;
  stage?: number;
  priority?: string;
  query?: string;
  numbers?: number[];
};

type Action = { id: string; type: string; label: string; state: "pending" | "applied"; href?: string; args?: AgentFilter };
type Msg = { id: string; text: string; actions: Action[] };

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** The same rules the agent's show_tracker tool uses on the server. */
export function matchesAgent(c: Card, f: AgentFilter): boolean {
  const t = today();
  const next = c.next_contact_date ? String(c.next_contact_date).slice(0, 10) : "";
  if (f.statuses?.length && !f.statuses.includes(c.status)) return false;
  if (f.overdue && !(next && next < t)) return false;
  if (f.due_today && next !== t) return false;
  if (f.needs_action && !(next && next <= t)) return false;
  if (f.starred && !c.starred) return false;
  if (f.stale && !c.stale) return false;
  if (f.stage && c.stage !== f.stage) return false;
  if (f.priority && c.priority !== f.priority) return false;
  if (f.numbers?.length && !f.numbers.includes(c.number)) return false;
  if (f.query) {
    const q = f.query.toLowerCase();
    if (!c.name.toLowerCase().includes(q) && !(c.firm || "").toLowerCase().includes(q)) return false;
  }
  return true;
}

/** "Ask your Raise Agent" bar on top of the investor tracker: questions, filtered views and quick changes by
 *  investor number or name. Shares its history with the full Raise Agent chat. */
export function TrackerAgent({ cards, onFilter }: { cards: Card[]; onFilter: (f: AgentFilter, label: string) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const [reply, setReply] = useState<Msg | null>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => setNarrow(window.innerWidth < 640), []);
  const first = cards.find((c) => c.number > 0);
  const examples = [
    "Show me only active investors",
    "Which ones are overdue?",
    first ? `Set a follow-up for #${first.number} on 02/Nov` : "Set a follow-up for #1 on 02/Nov",
    first ? `Add note on ${first.name}: "Sent the updated deck"` : 'Add note on #1: "Sent the updated deck"',
  ];

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["funnel"] });
    qc.invalidateQueries({ queryKey: ["card"] });
    qc.invalidateQueries({ queryKey: ["chat"] });
    qc.invalidateQueries({ queryKey: ["home"] });
  };
  const ask = useMutation({
    mutationFn: (t: string) => api<Msg>("/agent/chat", { method: "POST", json: { text: t } }),
    onSuccess: (m) => {
      setReply(m);
      setText("");
      const f = m.actions.filter((a) => a.type === "tracker_filter").pop();
      if (f?.args) onFilter(f.args, f.label.replace(/^Tracker: /, ""));
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const apply = useMutation({
    mutationFn: (a: Action) => api(`/agent/chat/${reply!.id}/actions/${a.id}`, { method: "POST" }),
    onSuccess: (_r, a) => {
      setReply((m) => m && { ...m, actions: m.actions.map((x) => (x.id === a.id ? { ...x, state: "applied" } : x)) });
      refresh();
      toast("Done");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const submit = (t: string) => {
    if (t.trim() && !ask.isPending) ask.mutate(t.trim());
  };

  return (
    <div className="mb-4 rounded-2xl border border-brand/25 bg-gradient-to-r from-brand/[0.06] to-transparent p-2.5 sm:p-3">
      <label htmlFor="tracker-agent" className="flex items-center gap-1.5 px-1 pb-1.5 text-xs font-semibold text-brand">
        <Sparkles size={14} className="shrink-0" /> Raise Agent
      </label>
      {/* A real text field (border, white background, focus ring, send button) so it reads as somewhere to type. */}
      <form
        className="flex items-center gap-2 rounded-xl border border-line bg-card pl-3.5 pr-1.5 py-1.5 shadow-sm cursor-text transition hover:border-brand/50 focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/15"
        onClick={(e) => e.currentTarget.querySelector("input")?.focus()}
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <input
          id="tracker-agent"
          className="flex-1 min-w-0 bg-transparent text-[15px] sm:text-sm text-ink outline-none placeholder:text-[#8a94a8] py-1.5"
          placeholder={narrow ? "Type a question or a change…" : "Type a question or a change, e.g. show overdue, follow up #10 on 02/Nov, add a note…"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Ask your Raise Agent about your tracker"
        />
        <button className="btn-primary btn-sm shrink-0" disabled={!text.trim() || ask.isPending} aria-label="Ask your Raise Agent">
          {ask.isPending ? <Loader2 size={14} className="animate-spin" /> : <SendHorizontal size={14} />}
          <span className="hidden sm:inline">{ask.isPending ? "Thinking…" : "Ask"}</span>
        </button>
      </form>

      {!reply && !ask.isPending && (
        <div className="mt-2 flex gap-1.5 overflow-x-auto scrollbar-none sm:flex-wrap">
          {examples.map((x) => (
            <button key={x} type="button" className="chip whitespace-nowrap px-2.5 py-1 text-xs bg-card hover:border-brand" onClick={() => submit(x)}>
              {x}
            </button>
          ))}
        </div>
      )}

      {reply && (
        <div className="mt-2.5 rounded-xl bg-card border border-line p-3">
          <div className="flex items-start gap-2">
            <ChatMarkdown source={reply.text} className="flex-1 min-w-0 text-sm" />
            <button className="p-1 -m-1 text-muted hover:text-ink" onClick={() => setReply(null)} aria-label="Close answer">
              <X size={16} />
            </button>
          </div>
          {reply.actions.filter((a) => a.type !== "tracker_filter").length > 0 && (
            <div className="mt-2 space-y-1.5">
              {reply.actions
                .filter((a) => a.type !== "tracker_filter")
                .map((a) => (
                  <div key={a.id} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5">
                    <span className="flex-1 text-xs">{a.label}</span>
                    {a.state === "pending" ? (
                      <button className="btn-primary btn-sm" disabled={apply.isPending} onClick={() => apply.mutate(a)}>
                        Apply
                      </button>
                    ) : a.href ? (
                      <Link href={a.href} className="text-xs text-brand hover:underline">
                        Open
                      </Link>
                    ) : (
                      <span className="text-xs text-green-600 flex items-center gap-1">
                        <Check size={12} /> Done
                      </span>
                    )}
                  </div>
                ))}
            </div>
          )}
          <button type="button" className="mt-2 text-xs text-muted hover:text-brand inline-flex items-center gap-1" onClick={openAgent}>
            <MessageSquare size={12} /> Continue in chat
          </button>
        </div>
      )}
    </div>
  );
}

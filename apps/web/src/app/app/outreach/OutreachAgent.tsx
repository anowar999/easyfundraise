"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, MessageSquare, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { openAgent } from "@/components/AgentChat";
import { errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

type Action = { id: string; type: string; label: string; state: "pending" | "applied"; href?: string };
type Msg = { id: string; text: string; actions: Action[] };

const EXAMPLES = [
  "Email 1 should be problem focused: 230m people ask ChatGPT health questions every week…",
  "Use this line in one email: we were selected by EWOR",
  "Quick update: we just signed our third hospital partner",
  "Who in my outreach list hasn't been sent anything yet?",
];

/** "Ask your Raise Agent" bar on top of Outreach: set what emails 1-3 focus on, add a quick update, redraft drafts,
 *  or ask about the outreach list. Nothing is ever sent from here. Shares its history with the full chat. */
export function OutreachAgent() {
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const [reply, setReply] = useState<Msg | null>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => setNarrow(window.innerWidth < 640), []);
  const examples = EXAMPLES;

  const refresh = () => {
    for (const k of ["playbook", "sequences", "sequence", "outreach-stats", "chat"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const ask = useMutation({
    mutationFn: (t: string) => api<Msg>("/agent/chat", { method: "POST", json: { text: t } }),
    onSuccess: (m) => {
      setReply(m);
      setText("");
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
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <Sparkles size={18} className="text-brand shrink-0 ml-1" />
        <input
          className="flex-1 min-w-0 bg-transparent text-[15px] outline-none placeholder:text-muted py-1.5"
          placeholder={narrow ? "Tell your outreach agent…" : "Tell your outreach agent: what email 1, 2, 3 should say, a quick update, who to redraft…"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Ask your Raise Agent about outreach"
        />
        <button className="btn-primary btn-sm shrink-0" disabled={!text.trim() || ask.isPending}>
          {ask.isPending ? "Thinking…" : "Ask"} <ArrowRight size={14} className="hidden sm:inline" />
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
            <p className="flex-1 text-sm whitespace-pre-wrap break-words">{reply.text}</p>
            <button className="p-1 -m-1 text-muted hover:text-ink" onClick={() => setReply(null)} aria-label="Close answer">
              <X size={16} />
            </button>
          </div>
          {reply.actions.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {reply.actions.map((a) => (
                  <div key={a.id} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5">
                    <span className="flex-1 text-xs">{a.label}</span>
                    {a.state === "pending" ? (
                      <button className="btn-primary btn-sm" disabled={apply.isPending} onClick={() => apply.mutate(a)}>
                        {a.type === "redraft" ? "Redraft" : "Apply"}
                      </button>
                    ) : a.href && a.type !== "playbook" ? (
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

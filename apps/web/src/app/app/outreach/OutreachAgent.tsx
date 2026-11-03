"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, MessageSquare, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { openAgent } from "@/components/AgentChat";
import { errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

type Action = { id: string; type: string; label: string; state: "pending" | "applied"; href?: string };
type Msg = { id: string; text: string; actions: Action[] };

/** The Outreach Agent on top of Outreach: it can do anything on this page (results, emails 1-3, rewriting or
 *  redrafting emails, round updates, pausing). Sending only ever happens on a confirm screen. Enter adds a new line;
 *  the Ask button (or Cmd/Ctrl+Enter) sends. Shares its history with the full chat. */
export function OutreachAgent() {
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const [reply, setReply] = useState<Msg | null>(null);

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
    <div className="mb-4 card p-3 sm:p-4">
      <label htmlFor="outreach-agent" className="flex items-center gap-2 font-semibold text-sm mb-2">
        <Sparkles size={16} className="text-brand shrink-0" /> I am your Outreach Agent. How can I help you?
      </label>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <textarea
          id="outreach-agent"
          rows={2}
          className="textarea resize-y min-h-[4.25rem]"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit(text);
            }
          }}
        />
        <div className="mt-2 flex items-center justify-end gap-3">
          <span className="hidden sm:inline text-xs text-muted">Enter for a new line · ⌘/Ctrl + Enter to ask</span>
          <button className="btn-primary btn-sm" disabled={!text.trim() || ask.isPending}>
            {ask.isPending ? "Thinking…" : "Ask"} <ArrowRight size={14} />
          </button>
        </div>
      </form>

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

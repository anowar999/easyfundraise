"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Clock, Mail, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ListSkeleton, Sheet, errText, useToast } from "./ui";
import { api, fmtDate } from "@/lib/api";

type Msg = { id: string; from: string; to: string; cc: string; subject: string; text: string; at: string | null; mine: boolean };
type MailState = { to: string; connected: boolean; from: string; signature: string; thread: Msg[]; thread_id: string; reply_to: string; reply_all: { to: string[]; cc: string[] }; subject: string };

const who = (from: string) => from.replace(/<.*>/, "").replace(/"/g, "").trim() || from;

/** Email on a tracker card: shows the latest Gmail thread with this investor, drafts an update on top of it,
 * and sends it as a reply in that thread now or at a set time. Every send is logged on the card. */
export function CardMail({ cardId, name, open, onClose }: { cardId: string; name: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<MailState>({ queryKey: ["card-mail", cardId], queryFn: () => api(`/funnel/${cardId}/mail`), enabled: open });
  const [ask, setAsk] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sig, setSig] = useState(false);
  const [later, setLater] = useState(false);
  const [at, setAt] = useState("");

  useEffect(() => {
    if (q.data && !subject) setSubject(q.data.subject || (q.data.thread.at(-1)?.subject ?? ""));
  }, [q.data, subject]);

  const draft = useMutation({
    mutationFn: () => api<{ subject: string; body: string }>(`/funnel/${cardId}/mail/draft`, { method: "POST", json: { ask } }),
    onSuccess: (r) => {
      if (!q.data?.thread_id) setSubject(r.subject);
      setBody(r.body);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const send = useMutation({
    mutationFn: () =>
      api<{ status: string; scheduled_for: string | null; error: string }>(`/funnel/${cardId}/mail/send`, {
        method: "POST",
        json: { subject: q.data?.thread_id ? "" : subject, body, add_signature: sig, thread_id: q.data?.thread_id ?? "", reply_to: q.data?.reply_to ?? "", send_at: later && at ? new Date(at).toISOString() : null },
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["card", cardId] });
      qc.invalidateQueries({ queryKey: ["card-mail", cardId] });
      qc.invalidateQueries({ queryKey: ["funnel"] });
      if (r.status === "sent") toast(`Sent to ${name}${q.data?.thread_id ? " in your existing thread" : ""}. Logged on their card.`);
      else if (r.status === "scheduled") toast(`Scheduled for ${fmtDate(r.scheduled_for, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}. It goes from your Gmail then.`);
      else toast(r.error || "Not sent", "err");
      if (r.status === "sent" || r.status === "scheduled") {
        setBody("");
        setAsk("");
        onClose();
      }
    },
    onError: (e) => toast(errText(e), "err"),
  });

  const d = q.data;
  return (
    <Sheet open={open} onClose={onClose} title={`Email ${name}`} wide>
      {q.isLoading && <ListSkeleton rows={3} />}
      {d && !d.connected && (
        <div className="text-sm space-y-3">
          <p>Connect your Gmail so I can read your latest conversation with {name} and send replies from your own mailbox.</p>
          <Link className="btn-primary" href="/app/settings#gmail">
            <Mail size={16} /> Connect Gmail
          </Link>
        </div>
      )}
      {d && d.connected && !d.to && <p className="text-sm">Add {name}&apos;s email address in Details (the pencil on this card) first, or reveal it on their investor profile.</p>}
      {d && d.connected && d.to && (
        <div className="space-y-4">
          <div>
            <div className="text-xs font-medium text-muted mb-1.5">{d.thread.length ? `Latest conversation, newest first (${d.thread.length} message${d.thread.length > 1 ? "s" : ""})` : "Latest conversation"}</div>
            {d.thread.length === 0 ? (
              <p className="text-sm text-muted rounded-xl border border-line p-3">No emails with {d.to} in your Gmail yet. This will start a new conversation.</p>
            ) : (
              <div className="max-h-64 overflow-y-auto space-y-2 rounded-xl border border-line bg-surface/60 p-2">
                {[...d.thread].reverse().map((m, i) => (
                  <div key={m.id} className={clsx("rounded-lg p-3 text-sm", m.mine ? "bg-brand/5 border border-brand/15 ml-6" : "bg-card border border-line mr-6", i === 0 && "ring-2 ring-brand/40")}>
                    <div className="flex justify-between gap-2 text-xs text-muted mb-1">
                      <span className="font-medium text-ink">
                        {m.mine ? "You" : who(m.from)}
                        {i === 0 && <span className="ml-2 rounded-full bg-brand/10 px-2 py-0.5 text-[11px] font-medium text-brand">Replying to this</span>}
                      </span>
                      <span>{fmtDate(m.at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                    </div>
                    <div className="whitespace-pre-wrap break-words">{m.text}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-line bg-card">
            <div className="px-3 py-2 border-b border-line text-sm space-y-0.5">
              {d.thread_id ? (
                <>
                  <div className="text-xs font-medium text-brand">Reply all · same thread</div>
                  <div className="truncate">
                    <span className="text-muted">To</span> <b>{d.reply_all.to.join(", ")}</b>
                  </div>
                  {d.reply_all.cc.length > 0 && (
                    <div className="truncate">
                      <span className="text-muted">Cc</span> {d.reply_all.cc.join(", ")}
                    </div>
                  )}
                  <div className="truncate text-muted">{d.subject}</div>
                </>
              ) : (
                <>
                  <div className="truncate">
                    <span className="text-muted">From</span> <b>{d.from}</b> <span className="text-muted ml-3">To</span> <b>{d.to}</b>
                  </div>
                  <input className="input mt-1.5 font-medium" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject" aria-label="Subject" />
                </>
              )}
            </div>
            <textarea className="textarea min-h-48 leading-relaxed border-0 rounded-none focus:ring-0" value={body} onChange={(e) => setBody(e.target.value)} placeholder={`Write to ${name}, or press Write update with AI below`} aria-label="Email" />
            <div className="flex flex-col sm:flex-row gap-2 p-2 border-t border-line bg-surface/60 rounded-b-xl">
              <input className="input flex-1 h-9 text-sm" value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="Optional: what to cover, e.g. answer their MRR question" aria-label="What to cover" />
              <button className="btn-ghost btn-sm h-9" disabled={draft.isPending} onClick={() => draft.mutate()}>
                <Sparkles size={15} className="text-brand" /> {draft.isPending ? "Writing…" : body ? "Rewrite with AI" : "Write update with AI"}
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-[var(--brand)]" checked={sig} onChange={(e) => setSig(e.target.checked)} />
              Add my signature
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-[var(--brand)]" checked={later} onChange={(e) => setLater(e.target.checked)} />
              <Clock size={15} /> Send later
            </label>
            {later && <input className="input w-auto h-9" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} aria-label="Send at" />}
            <button className="btn-primary ml-auto" disabled={(!d.thread_id && !subject.trim()) || !body.trim() || send.isPending || (later && !at)} onClick={() => send.mutate()}>
              {later ? <Clock size={16} /> : <Send size={16} />} {later ? "Schedule" : "Send now"}
            </button>
          </div>
          {sig && (d.signature ? <p className="-mt-2 text-xs text-muted whitespace-pre-line">{d.signature}</p> : <Link href="/app/settings#account" className="-mt-2 block text-xs text-brand">Set your signature in Settings</Link>)}
          <p className="text-xs text-muted">Sent from your Gmail, so it appears in your Sent folder and in the same conversation. It&apos;s logged on {name}&apos;s card.</p>
        </div>
      )}
    </Sheet>
  );
}

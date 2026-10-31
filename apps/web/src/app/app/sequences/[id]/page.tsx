"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CalendarCheck, Eye, Info, Mail, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, ListSkeleton, errText, useToast } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";

type Email = { id: string; step: number; hook: string; subject: string; body: string; facts: { text: string; source: string }[]; status: string; scheduled_for: string | null; sent_at: string | null; opened: number; reply: string; error: string; issues: string[] };
type Seq = { id: string; investor_id: string; card_id: string | null; status: string; persona: string; engine: string; investor: { name: string; firm: string }; emails: Email[] };
const PERSONAS = [
  ["momentum", "Momentum"],
  ["warm-intro", "Warm intro"],
  ["technical-founder", "Technical founder"],
  ["humble-expert", "Humble expert"],
];
const STATUS_TEXT: Record<string, string> = { draft: "Draft", scheduled: "Scheduled", sending: "Sending", sent: "Sent", cancelled: "Cancelled", failed: "Failed" };
const LIMITS: Record<number, number> = { 1: 120, 2: 80, 3: 60 };
const words = (s: string) => (s.match(/\b[\w'’-]+\b/g) ?? []).length;

function EmailEditor({ seqId, e, disabled }: { seqId: string; e: Email; disabled: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [subject, setSubject] = useState(e.subject);
  const [body, setBody] = useState(e.body);
  const [issues, setIssues] = useState(e.issues);
  useEffect(() => {
    setSubject(e.subject);
    setBody(e.body);
    setIssues(e.issues);
  }, [e]);
  const save = useMutation({
    mutationFn: () => api<{ issues: string[] }>(`/sequences/${seqId}/emails/${e.id}`, { method: "PATCH", json: { subject, body } }),
    onSuccess: (r) => {
      setIssues(r.issues);
      qc.invalidateQueries({ queryKey: ["sequence", seqId] });
      toast("Saved");
    },
    onError: (err) => toast(errText(err), "err"),
  });
  const dirty = subject !== e.subject || body !== e.body;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold text-sm">
          Email {e.step} <span className="text-muted font-normal">· {e.hook.replace(/-/g, " ")}</span>
        </div>
        <span className={words(body) > LIMITS[e.step] + 40 ? "text-xs text-danger" : "text-xs text-muted"}>
          {e.sent_at
            ? `Sent ${fmtDate(e.sent_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
            : e.scheduled_for && e.status === "scheduled"
              ? `Scheduled ${fmtDate(e.scheduled_for, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
              : e.status !== "draft"
                ? STATUS_TEXT[e.status] ?? e.status
                : `limit ${LIMITS[e.step]} words`}
        </span>
      </div>
      {(e.opened > 0 || e.reply || e.error) && (
        <div className="flex flex-wrap gap-1.5 mb-2 text-xs">
          {e.opened > 0 && (
            <span className="chip">
              <Eye size={11} /> opened {e.opened}×
            </span>
          )}
          {e.reply && (
            <span className="chip bg-green-500/10 text-green-700 border-green-600/30">
              <Mail size={11} /> reply: {e.reply.replace("_", " ")}
            </span>
          )}
          {e.error && e.status !== "sent" && <span className="chip text-warn">{e.error}</span>}
        </div>
      )}
      <input className="input mb-2 font-medium" value={subject} onChange={(x) => setSubject(x.target.value)} disabled={disabled} aria-label="Subject" />
      <textarea className="textarea min-h-56 font-[inherit] leading-relaxed" value={body} onChange={(x) => setBody(x.target.value)} disabled={disabled} aria-label="Body" />
      {issues.length > 0 && (
        <ul className="mt-2 space-y-1">
          {issues.map((i) => (
            <li key={i} className="text-xs text-warn flex gap-1.5">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" /> {i}
            </li>
          ))}
        </ul>
      )}
      {e.facts.length > 0 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted flex items-center gap-1">
            <Info size={12} /> Why I wrote this
          </summary>
          <ul className="mt-2 space-y-1">
            {e.facts.map((f) => (
              <li key={f.text}>
                {f.text}{" "}
                {f.source?.startsWith("http") ? (
                  <a href={f.source} target="_blank" rel="noreferrer" className="text-brand">
                    source
                  </a>
                ) : (
                  <span className="text-muted">({f.source})</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="flex items-center justify-between mt-2">
        <Feedback id={e.id} />
        {!disabled && (
          <button className="btn-ghost btn-sm" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            Save edit
          </button>
        )}
      </div>
    </div>
  );
}

function Feedback({ id }: { id: string }) {
  const [v, setV] = useState(0);
  const send = (rating: number) => {
    setV(rating);
    api("/agent/feedback", { method: "POST", json: { target: "email", target_id: id, rating } }).catch(() => {});
  };
  return (
    <div className="flex gap-1 text-muted" aria-label="Rate this draft">
      <button className={v === 1 ? "text-green-600 p-1" : "p-1"} onClick={() => send(1)} aria-label="Good draft">
        <ThumbsUp size={14} />
      </button>
      <button className={v === -1 ? "text-danger p-1" : "p-1"} onClick={() => send(-1)} aria-label="Bad draft">
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}

export default function SequencePage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery<Seq>({ queryKey: ["sequence", id], queryFn: () => api(`/sequences/${id}`) });
  const approve = useMutation({
    mutationFn: () => api<Seq>(`/sequences/${id}/approve`, { method: "POST" }),
    onSuccess: (s) => {
      qc.setQueryData(["sequence", id], s);
      toast("Approved and scheduled in the investor's local send window");
    },
    onError: (e) => {
      if (e instanceof ApiError && (e.problem.needs_signature || e.problem.needs_reveal || e.problem.needs_gmail)) setBlocker(e.problem);
      else toast(errText(e), "err");
    },
  });
  const [blocker, setBlocker] = useState<Record<string, unknown> | null>(null);
  const [persona, setPersona] = useState("");
  const regen = useMutation({
    mutationFn: (p: string) => api<Seq>(`/sequences/${id}/regenerate`, { method: "POST", json: { persona: p } }),
    onSuccess: (s) => {
      qc.setQueryData(["sequence", id], s);
      toast("Redrafted");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const stop = useMutation({
    mutationFn: () => api(`/sequences/${id}/stop`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sequence", id] }),
  });
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const s = q.data!;
  const locked = s.status !== "draft";
  return (
    <div className="max-w-3xl">
      <Link href={`/app/investors/${s.investor_id}`} className="text-sm text-muted flex items-center gap-1 mb-3">
        <ArrowLeft size={16} /> {s.investor.name}
      </Link>
      <h1 className="text-xl font-semibold">Sequence for {s.investor.name}</h1>
      <p className="text-sm text-muted mb-3">
        {s.investor.firm} · status: <b>{s.status}</b> · written by {s.engine === "template" ? "the template engine" : "Claude"}
      </p>
      {!locked ? (
        <div className="card p-3 mb-4 flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted">Change the approach</span>
          <select className="input h-9 w-auto text-sm" value={persona || s.persona} onChange={(e) => setPersona(e.target.value)} aria-label="Persona">
            {PERSONAS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <button className="btn-ghost btn-sm" onClick={() => regen.mutate(persona || s.persona)} disabled={regen.isPending}>
            <RefreshCw size={14} /> Redraft
          </button>
        </div>
      ) : (
        s.status === "approved" && (
          <button className="btn-ghost btn-sm mb-4" onClick={() => stop.mutate()}>
            Stop sequence
          </button>
        )
      )}
      {blocker && (
        <div className="card p-4 mb-4 border-warn/40 bg-amber-500/5 text-sm space-y-2" role="alert">
          {Boolean(blocker.needs_signature) && <p>Add your email signature first. It goes at the end of every email.</p>}
          {Boolean(blocker.needs_reveal) && <p>We need {s.investor.name}&apos;s email. Reveal it on their profile (uses one credit) or add it on the funnel card.</p>}
          {Boolean(blocker.needs_gmail) && <p>Connect your Gmail. Emails go out from your own mailbox so replies land in your inbox.</p>}
          <div className="flex gap-2">
            {Boolean(blocker.needs_signature) && <Link className="btn-primary btn-sm" href="/app/settings#account">Add signature</Link>}
            {Boolean(blocker.needs_reveal) && <Link className="btn-primary btn-sm" href={`/app/investors/${s.investor_id}`}>Open profile</Link>}
            {Boolean(blocker.needs_gmail) && <Link className="btn-primary btn-sm" href="/app/settings#gmail">Connect Gmail</Link>}
          </div>
        </div>
      )}
      <div className="space-y-4">
        {s.emails.map((e) => (
          <EmailEditor key={e.id} seqId={s.id} e={e} disabled={locked} />
        ))}
      </div>
      {!locked && (
        <div className="sticky bottom-[calc(64px_+_env(safe-area-inset-bottom))] md:bottom-4 mt-4">
          <button className="btn-primary w-full h-12 shadow-lg" onClick={() => approve.mutate()} disabled={approve.isPending}>
            <CalendarCheck size={18} /> Approve &amp; schedule
          </button>
          <p className="text-xs text-muted text-center mt-1 bg-surface/80">Sends from your Gmail in their local send window · stops on any reply.</p>
        </div>
      )}
    </div>
  );
}

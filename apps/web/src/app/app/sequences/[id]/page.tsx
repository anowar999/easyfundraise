"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CalendarCheck, Info } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, ListSkeleton, errText, useToast } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";

type Email = { id: string; step: number; hook: string; subject: string; body: string; facts: { text: string; source: string }[]; status: string; scheduled_for: string | null; issues: string[] };
type Seq = { id: string; investor_id: string; status: string; persona: string; investor: { name: string; firm: string }; emails: Email[] };
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
          {e.scheduled_for ? `Scheduled ${fmtDate(e.scheduled_for, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : `limit ${LIMITS[e.step]} words`}
        </span>
      </div>
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
      {!disabled && (
        <div className="flex justify-end mt-2">
          <button className="btn-ghost btn-sm" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            Save edit
          </button>
        </div>
      )}
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
      if (e instanceof ApiError && e.problem.needs_signature) toast("Add your email signature in Settings first", "err");
      else toast(errText(e), "err");
    },
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
      <p className="text-sm text-muted mb-4">
        {s.investor.firm} · persona: {s.persona} · status: <b>{s.status}</b>
      </p>
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
          <p className="text-xs text-muted text-center mt-1">Sends from your Gmail once connected · max 20/day · stops on any reply.</p>
        </div>
      )}
    </div>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ConfirmSend, type SendPreview } from "@/components/ConfirmSend";
import { ErrorState, ListSkeleton, errText, useToast } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";

type E = { id: string; card_id: string | null; to: string; step: number; subject: string; body: string; status: string; scheduled_for: string | null; sent_at: string | null; opened: number; reply: string };
type B = { id: string; kind: string; title: string; status: string; follow_up: boolean; recipients: number; sent: number; opened: number; replied: number; emails: E[] };
type Eng = { items: { name: string; opened: number; replied: boolean; quiet: boolean }[] };

function EmailRow({ bid, e, editable }: { bid: string; e: E; editable: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [subject, setSubject] = useState(e.subject);
  const [body, setBody] = useState(e.body);
  useEffect(() => {
    setSubject(e.subject);
    setBody(e.body);
  }, [e]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["broadcast", bid] });
  const save = useMutation({ mutationFn: () => api(`/broadcasts/${bid}/emails/${e.id}`, { method: "PATCH", json: { subject, body } }), onSuccess: () => { refresh(); toast("Saved"); }, onError: (x) => toast(errText(x), "err") });
  const remove = useMutation({ mutationFn: () => api(`/broadcasts/${bid}/emails/${e.id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <details className="card">
      <summary className="p-3 flex items-center gap-2 cursor-pointer list-none">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">
            {e.to} {e.step > 1 && <span className="text-muted font-normal">· follow-up</span>}
          </div>
          <div className="text-xs text-muted truncate">{e.subject}</div>
        </div>
        <div className="text-xs text-right shrink-0">
          {e.reply ? <span className="text-green-600 font-medium">replied</span> : e.opened > 0 ? <span>opened {e.opened}×</span> : <span className="text-muted capitalize">{e.status}</span>}
          <div className="text-muted">{fmtDate(e.sent_at ?? e.scheduled_for, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
        </div>
      </summary>
      <div className="px-3 pb-3 space-y-2">
        <input className="input font-medium" value={subject} onChange={(x) => setSubject(x.target.value)} disabled={!editable} aria-label="Subject" />
        <textarea className="textarea min-h-48 leading-relaxed" value={body} onChange={(x) => setBody(x.target.value)} disabled={!editable} aria-label="Body" />
        {editable && (
          <div className="flex justify-between">
            <button className="btn-ghost btn-sm text-danger" onClick={() => remove.mutate()}>
              <Trash2 size={14} /> Don&apos;t send to them
            </button>
            <button className="btn-ghost btn-sm" disabled={(subject === e.subject && body === e.body) || save.isPending} onClick={() => save.mutate()}>
              Save edit
            </button>
          </div>
        )}
      </div>
    </details>
  );
}

export default function UpdatePage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<B>({ queryKey: ["broadcast", id], queryFn: () => api(`/broadcasts/${id}`) });
  const eng = useQuery<Eng>({ queryKey: ["broadcast-eng", id], queryFn: () => api(`/broadcasts/${id}/engagement`), enabled: !!q.data && q.data.sent > 0 });
  const [needsGmail, setNeedsGmail] = useState(false);
  const [preview, setPreview] = useState<SendPreview | null>(null);
  const approve = useMutation({
    mutationFn: (confirm: boolean) => api<B>(`/broadcasts/${id}/approve`, { method: "POST", json: { confirm } }),
    onSuccess: (b) => {
      setPreview(null);
      qc.setQueryData(["broadcast", id], b);
      qc.invalidateQueries({ queryKey: ["broadcasts"] });
      toast("Approved. Emails go out spaced over the next hours.");
    },
    onError: (e) => {
      if (e instanceof ApiError && e.problem.needs_confirm) setPreview(e.problem.preview as SendPreview);
      else if (e instanceof ApiError && e.problem.needs_gmail) setNeedsGmail(true);
      else toast(errText(e), "err");
    },
  });
  const cancel = useMutation({ mutationFn: () => api(`/broadcasts/${id}/cancel`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["broadcast", id] }) });
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const b = q.data!;
  const editable = b.status === "draft";
  const firsts = b.emails.filter((e) => e.step === 1);
  return (
    <div className="max-w-3xl">
      <Link href="/app/updates" className="text-sm text-muted flex items-center gap-1 mb-3">
        <ArrowLeft size={16} /> Updates
      </Link>
      <h1 className="text-xl font-semibold">{b.title}</h1>
      <p className="text-sm text-muted mb-4">
        {b.recipients} recipient{b.recipients === 1 ? "" : "s"} · status: <b>{b.status}</b>
        {b.sent > 0 && ` · ${b.opened} opened · ${b.replied} replied`}
      </p>
      {needsGmail && (
        <div className="card p-4 mb-4 border-warn/40 bg-amber-500/5 text-sm flex items-center gap-3" role="alert">
          <span className="flex-1">Connect your Gmail first. Updates go out from your own mailbox.</span>
          <Link className="btn-primary btn-sm" href="/app/settings#gmail">
            Connect Gmail
          </Link>
        </div>
      )}
      {eng.data && eng.data.items.length > 0 && (
        <div className="card p-4 mb-4">
          <h2 className="font-semibold text-sm mb-2">Who engaged</h2>
          <div className="flex flex-wrap gap-1.5 text-xs">
            {eng.data.items.map((x) => (
              <span key={x.name} className={`chip ${x.replied ? "bg-green-500/10 text-green-700 border-green-600/30" : x.quiet ? "text-muted" : ""}`}>
                {x.name} · {x.replied ? "replied" : x.opened ? `opened ${x.opened}×` : "not opened"}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="space-y-2">
        {(editable ? firsts : b.emails).map((e) => (
          <EmailRow key={e.id} bid={b.id} e={e} editable={editable} />
        ))}
      </div>
      {editable ? (
        <div className="sticky bottom-[calc(64px_+_env(safe-area-inset-bottom))] md:bottom-4 mt-4">
          <button className="btn-primary w-full h-12 shadow-lg" disabled={approve.isPending || firsts.length === 0} onClick={() => approve.mutate(false)}>
            <CalendarCheck size={18} /> Approve &amp; send to {firsts.length}
          </button>
          <ConfirmSend preview={preview} busy={approve.isPending} onCancel={() => setPreview(null)} onConfirm={() => approve.mutate(true)} />
          <p className="text-xs text-muted text-center mt-1 bg-surface/80">Each email is personal and sent from your Gmail, a few minutes apart.</p>
        </div>
      ) : (
        b.status === "scheduled" && (
          <button className="btn-ghost mt-4" onClick={() => confirm("Stop the emails that haven't gone out yet?") && cancel.mutate()}>
            Stop unsent emails
          </button>
        )
      )}
    </div>
  );
}

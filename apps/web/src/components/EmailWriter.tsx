"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Copy, ExternalLink, Info, PenLine, RefreshCw, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmSend, type SendPreview } from "./ConfirmSend";
import { errText, useToast } from "./ui";
import { api, ApiError } from "@/lib/api";

type Written = { subject: string; subjects: string[]; body: string; facts: { text: string; source: string }[]; engine: string; to: string };

/** Writes one email personalised to this investor. Copy it into Gmail, open it in Gmail, or send it through outreach. */
export function EmailWriter({ investorId, name, excluded }: { investorId: string; name: string; excluded?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const [angle, setAngle] = useState("");
  const [w, setW] = useState<Written | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<SendPreview | null>(null);
  const [seqId, setSeqId] = useState<string | null>(null);

  const write = useMutation({
    mutationFn: () => api<Written>(`/investors/${investorId}/write-email`, { method: "POST", json: { angle } }),
    onSuccess: (r) => {
      setW(r);
      setSubject(r.subject);
      setBody(r.body);
      setSeqId(null);
    },
    onError: (e) => toast(errText(e), "err"),
  });

  const approve = useMutation({
    mutationFn: ({ id, confirm }: { id: string; confirm: boolean }) => api(`/sequences/${id}/approve`, { method: "POST", json: { confirm } }),
    onSuccess: () => {
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      toast(`Scheduled. ${name} gets this email in their local send window. Follow-ups stop if they reply.`);
    },
    onError: (e, v) => {
      if (e instanceof ApiError && e.problem.needs_confirm) setPreview(e.problem.preview as SendPreview);
      else {
        toast(`${errText(e)}. Your email is saved in Outreach.`, "err");
        router.push(`/app/sequences/${v.id}`);
      }
    },
  });

  const send = useMutation({
    mutationFn: () => api<{ id: string; status: string }>("/sequences", { method: "POST", json: { investor_id: investorId, first_email: { subject, body } } }),
    onSuccess: (s) => {
      setSeqId(s.id);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      if (s.status === "approved") toast(`Auto-send is on, so this is scheduled for ${name}.`);
      else approve.mutate({ id: s.id, confirm: false });
    },
    onError: (e) => toast(e instanceof ApiError && e.problem.upgrade ? "You've used your sample drafts. Upgrade to send more." : errText(e), "err"),
  });

  const copy = async (text: string, what: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast(`${what} copied`);
    } catch {
      toast("Couldn't copy. Select the text and copy it instead.", "err");
    }
  };
  const gmail = `https://mail.google.com/mail/?view=cm&fs=1${w?.to ? `&to=${encodeURIComponent(w.to)}` : ""}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  if (!w)
    return (
      <div className="card p-4 md:p-5">
        <h2 className="font-semibold flex items-center gap-2">
          <PenLine size={18} className="text-brand" /> Write an email to {name}
        </h2>
        <p className="text-sm text-muted mt-1">Personalised from their thesis, portfolio, recent deals and news, plus your company profile. You can edit it, then copy it into Gmail or send it from here.</p>
        <input className="input mt-3" value={angle} onChange={(e) => setAngle(e.target.value)} placeholder="Optional: anything to lead with, e.g. our new hospital pilot" aria-label="What to lead with" />
        <button className="btn-primary mt-3" disabled={write.isPending || excluded} onClick={() => write.mutate()}>
          <PenLine size={16} /> {write.isPending ? "Writing…" : "Write email"}
        </button>
        {excluded && <p className="text-xs text-warn mt-2">This investor is on your exclusion list.</p>}
      </div>
    );

  return (
    <div className="card p-4 md:p-5 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold flex items-center gap-2">
          <PenLine size={18} className="text-brand" /> Email to {name}
        </h2>
        <button className="btn-ghost btn-sm" disabled={write.isPending} onClick={() => write.mutate()}>
          <RefreshCw size={14} className={clsx(write.isPending && "animate-spin")} /> Rewrite
        </button>
      </div>
      {w.to && (
        <div className="text-sm">
          <span className="text-muted">To</span> <b>{w.to}</b>
        </div>
      )}
      <div>
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-muted" htmlFor="ew-subject">
            Subject
          </label>
          <button className="text-xs text-brand inline-flex items-center gap-1" onClick={() => copy(subject, "Subject")}>
            <Copy size={12} /> Copy
          </button>
        </div>
        <input id="ew-subject" className="input mt-1 font-medium" value={subject} onChange={(e) => setSubject(e.target.value)} />
        {w.subjects.length > 1 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            <span className="text-xs text-muted self-center">Ideas:</span>
            {w.subjects.map((s) => (
              <button key={s} onClick={() => setSubject(s)} className={clsx("chip text-xs", s === subject ? "border-brand text-brand" : "hover:border-brand")}>
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
      <div>
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-muted" htmlFor="ew-body">
            Email
          </label>
          <button className="text-xs text-brand inline-flex items-center gap-1" onClick={() => copy(body, "Email")}>
            <Copy size={12} /> Copy
          </button>
        </div>
        <textarea id="ew-body" className="textarea mt-1 min-h-64 leading-relaxed" value={body} onChange={(e) => setBody(e.target.value)} />
      </div>
      {w.facts.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted inline-flex items-center gap-1">
            <Info size={12} /> Why I wrote this
          </summary>
          <ul className="mt-2 space-y-1">
            {w.facts.map((f) => (
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
      <div className="flex flex-wrap gap-2 pt-1">
        <button className="btn-ghost" onClick={() => copy(`Subject: ${subject}\n\n${body}`, "Subject and email")}>
          <Copy size={16} /> Copy all
        </button>
        <a className="btn-ghost" href={gmail} target="_blank" rel="noreferrer">
          <ExternalLink size={16} /> Open in Gmail
        </a>
        <button className="btn-primary" disabled={!subject.trim() || !body.trim() || send.isPending || approve.isPending || Boolean(seqId)} onClick={() => send.mutate()}>
          <Send size={16} /> {seqId ? "Added to outreach" : "Send via outreach"}
        </button>
      </div>
      <p className="text-xs text-muted">Send via outreach adds {name} to your outreach list with this as the first email and two short follow-ups. You confirm before anything goes out, and follow-ups stop if they reply.</p>
      <ConfirmSend preview={preview} busy={approve.isPending} onCancel={() => setPreview(null)} onConfirm={() => seqId && approve.mutate({ id: seqId, confirm: true })} />
    </div>
  );
}

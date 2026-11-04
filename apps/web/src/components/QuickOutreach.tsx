"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarClock, FileText, Loader2, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { SpamChip } from "@/app/app/outreach/SpamChip";
import { ConfirmSend, type SendPreview } from "./ConfirmSend";
import { Sheet, errText, useToast } from "./ui";
import { api, ApiError } from "@/lib/api";

type Mail = { id: string; step: number; subject: string; body: string; spam?: { score: number; level: "good" | "warn" | "high"; reasons: string[] } };
type Seq = { id: string; status: string; drafting?: boolean; investor: { name: string; firm: string } | null; emails: Mail[] };

const first = (name: string) => name.trim().split(/\s+/)[0] ?? "";
const fill = (t: string, name: string) => t.replace(/\{\{?\s*first[ _]?name\s*\}?\}/gi, first(name));

/** The quick look after the mail icon: the 3 drafted emails, then Send now, Schedule for their morning, or keep
 *  as a draft in Outreach. Nothing goes without the confirm screen, whatever the auto-send setting. */
export function QuickOutreach({ seqId, name, onClose, onDropped }: { seqId: string; name: string; onClose: () => void; onDropped?: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState(1);
  const [preview, setPreview] = useState<SendPreview | null>(null);
  const [mode, setMode] = useState<"window" | "now">("window");
  const q = useQuery<Seq>({
    queryKey: ["sequence", seqId],
    queryFn: () => api(`/sequences/${seqId}`),
    refetchInterval: (query) => (query.state.data?.drafting ? 2000 : false),
  });
  const refresh = () => {
    for (const k of ["sequences", "upcoming", "outreach-stats", "nav-counts", "investors", "investor", "home"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const approve = useMutation({
    mutationFn: ({ confirm, at }: { confirm: boolean; at: "window" | "now" }) =>
      api(`/sequences/${seqId}/approve`, { method: "POST", json: { confirm, first_at: at } }),
    onSuccess: (_, v) => {
      setPreview(null);
      refresh();
      toast(v.at === "now" ? `Sending email 1 to ${name} now. Follow-ups go 2 working days apart and stop on any reply.` : `Scheduled for ${name}: email 1 goes in their morning send window.`);
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.problem.needs_confirm) setPreview(e.problem.preview as SendPreview);
      else toast(errText(e), "err");
    },
  });
  const drop = useMutation({
    mutationFn: () => api(`/sequences/${seqId}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      toast(`${name} not added to outreach.`);
      onDropped?.();
      onClose();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const ask = (at: "window" | "now") => {
    setMode(at);
    approve.mutate({ confirm: false, at });
  };

  const s = q.data;
  const em = s?.emails.find((e) => e.step === step);
  const writing = !s || s.drafting;
  return (
    <>
      <Sheet open onClose={onClose} title={`Email outreach to ${name}`} wide>
        <div className="flex items-center gap-1.5 mb-3" role="tablist" aria-label="Emails in the sequence">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              role="tab"
              aria-selected={step === n}
              onClick={() => setStep(n)}
              className={clsx("rounded-full border px-3 py-1 text-xs", step === n ? "border-brand bg-brand/10 text-brand font-medium" : "border-line text-muted hover:border-brand/50")}
            >
              Email {n}
              {n > 1 && <span className="hidden sm:inline"> · follow-up</span>}
            </button>
          ))}
          {writing && (
            <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted">
              <Loader2 size={13} className="animate-spin" /> Writing personalised emails…
            </span>
          )}
        </div>
        <div className="rounded-xl border border-line bg-surface/50 p-3 min-h-48">
          {em ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-medium flex-1 min-w-0">{step > 1 ? `Re: ${fill(s!.emails.find((e) => e.step === 1)?.subject ?? "", name)}` : fill(em.subject, name)}</div>
                {em.spam && <SpamChip spam={em.spam} compact />}
              </div>
              <div className={clsx("text-sm whitespace-pre-wrap mt-2 leading-relaxed", writing && "opacity-60")}>{fill(em.body, name)}</div>
              {step > 1 && <p className="mt-3 text-xs text-muted">Sent as a reply in the same thread, 2 working days after the email before, only if they haven&apos;t replied.</p>}
            </>
          ) : (
            <div className="h-40 grid place-items-center text-sm text-muted">
              <Loader2 size={18} className="animate-spin" />
            </div>
          )}
        </div>
        <div className="mt-4 grid sm:grid-cols-3 gap-2">
          <button className="btn-primary" disabled={writing || approve.isPending} onClick={() => ask("window")}>
            <CalendarClock size={15} /> Schedule for their morning
          </button>
          <button className="btn-ghost border border-line" disabled={writing || approve.isPending} onClick={() => ask("now")}>
            <Send size={15} /> Send now
          </button>
          <button
            className="btn-ghost border border-line"
            onClick={() => {
              refresh();
              toast(`${name} is in Outreach as a draft. Filter by Draft to review and send later.`);
              onClose();
            }}
          >
            <FileText size={15} /> Keep as draft
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span>This choice is just for {first(name)}; your auto-send setting doesn&apos;t change.</span>
          <Link href={`/app/sequences/${seqId}?from=outreach`} className="hover:text-brand underline">Edit the emails</Link>
          <button className="inline-flex items-center gap-1 hover:text-warn" disabled={drop.isPending} onClick={() => drop.mutate()}>
            <Trash2 size={12} /> Don&apos;t add
          </button>
        </div>
      </Sheet>
      <ConfirmSend preview={preview} busy={approve.isPending} onCancel={() => setPreview(null)} onConfirm={() => approve.mutate({ confirm: true, at: mode })} />
    </>
  );
}

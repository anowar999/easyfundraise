"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarClock, FileText, Loader2, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { SpamChip } from "@/app/app/outreach/SpamChip";
import type { SendPreview } from "./ConfirmSend";
import { Sheet, errText, useToast } from "./ui";
import { api, ApiError } from "@/lib/api";
import { allowanceNote } from "@/lib/allowance";

type Mail = { id: string; step: number; subject: string; body: string; spam?: { score: number; level: "good" | "warn" | "high"; reasons: string[] } };
type Seq = { id: string; status: string; drafting?: boolean; investor: { name: string; firm: string } | null; emails: Mail[] };

const first = (name: string) => name.trim().split(/\s+/)[0] ?? "";
const fill = (t: string, name: string) => t.replace(/\{\{?\s*first[ _]?name\s*\}?\}/gi, first(name));

/** The quick look after the mail icon: the 3 drafted emails, then Send now, Schedule for their morning, or keep
 *  as a draft in Outreach. The planned times, sender and recipient are shown right here, and nothing goes until
 *  the founder ticks "I've reviewed these emails", whatever the auto-send setting. */
export function QuickOutreach({ seqId, name, onClose, onDropped }: { seqId: string; name: string; onClose: () => void; onDropped?: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState(1);
  const [ok, setOk] = useState(false);
  const q = useQuery<Seq>({
    queryKey: ["sequence", seqId],
    queryFn: () => api(`/sequences/${seqId}`),
    refetchInterval: (query) => (query.state.data?.drafting ? 2000 : false),
  });
  // The plan for "their morning": a dry run of approve (confirm=false schedules nothing and spends no credit)
  const plan = useQuery<SendPreview>({
    queryKey: ["send-preview", seqId],
    enabled: !!q.data,
    retry: false,
    queryFn: async () => {
      try {
        await api(`/sequences/${seqId}/approve`, { method: "POST", json: { confirm: false, first_at: "window" } });
        throw new Error("Couldn't load the send plan");
      } catch (e) {
        if (e instanceof ApiError && e.problem.needs_confirm) return e.problem.preview as SendPreview;
        throw e;
      }
    },
  });
  const refresh = () => {
    for (const k of ["sequences", "upcoming", "outreach-stats", "nav-counts", "investors", "investor", "home"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const approve = useMutation({
    mutationFn: ({ at }: { at: "window" | "now" }) =>
      api(`/sequences/${seqId}/approve`, { method: "POST", json: { confirm: true, first_at: at } }),
    onSuccess: (_, v) => {
      refresh();
      toast(
        plan.data?.allowance?.moved
          ? `Added ${name}. ${allowanceNote(plan.data.allowance)}`
          : v.at === "now"
            ? `Sending email 1 to ${name} now. Follow-ups go 2 working days apart and stop on any reply.`
            : `Scheduled for ${name}: email 1 goes in their morning send window.`,
      );
      onClose();
    },
    onError: (e) => toast(errText(e), "err"),
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
  const ask = (at: "window" | "now") => approve.mutate({ at });

  const s = q.data;
  const em = s?.emails.find((e) => e.step === step);
  const writing = !s || s.drafting;
  const p = plan.data;
  const tz = p?.timezone;
  const at = (n: number) => p?.emails?.find((e) => e.step === n)?.scheduled_for;
  const when = (iso: string) =>
    new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", ...(tz ? { timeZone: tz } : {}) });
  const to = Array.isArray(p?.to) ? p?.to.join(", ") : p?.to;
  const canSend = !!s && !!p && ok && !approve.isPending;
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
              {at(n) ? <span className="hidden sm:inline"> · {when(at(n)!)}</span> : n > 1 && <span className="hidden sm:inline"> · follow-up</span>}
            </button>
          ))}
          {writing && (
            <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted">
              <Loader2 size={13} className="animate-spin" /> Personalising with AI…
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
              <div className="text-sm whitespace-pre-wrap mt-2 leading-relaxed">{fill(em.body, name)}</div>
              {writing && (
                <p className="mt-3 text-xs text-muted">
                  This is your template version. The AI-personalised one replaces it here in a few seconds, and it&apos;s the one that gets sent, so you can choose now.
                </p>
              )}
              {step > 1 && <p className="mt-3 text-xs text-muted">Sent as a reply in the same thread, 2 working days after the email before, only if they haven&apos;t replied.</p>}
            </>
          ) : (
            <div className="h-40 grid place-items-center text-sm text-muted">
              <Loader2 size={18} className="animate-spin" />
            </div>
          )}
        </div>
        {p?.emails && (
          <ol className="mt-3 grid sm:grid-cols-3 gap-2 text-xs">
            {p.emails.map((e) => (
              <li key={e.step} className={clsx("rounded-lg border px-2.5 py-1.5", e.step === step ? "border-brand/50" : "border-line")}>
                <span className="text-muted">Email {e.step} · their morning</span>
                <div className="font-medium">{when(e.scheduled_for)}</div>
              </li>
            ))}
          </ol>
        )}
        {p?.emails && <p className="mt-1.5 text-xs text-muted">Times are {first(name)}&apos;s local time{tz ? ` (${tz})` : ""}. With Send now, email 1 goes in about a minute and the follow-ups keep their 2 working day gaps. Follow-ups stop on any reply.</p>}
        {p?.allowance && allowanceNote(p.allowance) && (
          <p className={clsx("mt-2 rounded-lg px-3 py-2 text-xs", p.allowance.moved ? "border border-amber-500/40 bg-amber-500/5 text-ink" : "text-muted px-0 py-0")}>{allowanceNote(p.allowance)}</p>
        )}
        {plan.isError && <p className="mt-3 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-warn">{errText(plan.error)}</p>}
        <label className={clsx("mt-3 flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm cursor-pointer", ok ? "border-brand/50 bg-brand/5" : "border-line")}>
          <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--brand,#4f46e5)]" checked={ok} disabled={!p} onChange={(e) => setOk(e.target.checked)} />
          <span>
            I&apos;ve reviewed these emails.
            {p && <span className="text-muted"> They go from {p.from} to {to}.</span>}
          </span>
        </label>
        <div className="mt-3 grid sm:grid-cols-3 gap-2">
          <button className="btn-primary" disabled={!canSend} onClick={() => ask("window")}>
            <CalendarClock size={15} /> Schedule for their morning
          </button>
          <button className="btn-ghost border border-line" disabled={!canSend} onClick={() => ask("now")}>
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
    </>
  );
}

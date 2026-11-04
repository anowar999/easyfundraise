"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, FileText, Loader2, Send, X } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { allowanceNote, type Allowance } from "@/lib/allowance";
import { Sheet, errText, useToast } from "./ui";

type Action = "window" | "now" | "draft";
type Plan = {
  needs_confirm?: boolean;
  action: Action;
  from: string;
  count: number;
  investors: { id: string; name: string; firm: string }[];
  skipped: { id: string; name: string; reason: string }[];
  terms: string;
  allowance?: Allowance;
};
type Done = { allowance?: Allowance; scheduled: number; drafts: { id: string; name: string; reason?: string }[]; skipped: { name: string; reason: string }[]; action: Action };

const LABEL: Record<Action, string> = { window: "Schedule all for their morning", now: "Send all now", draft: "Add all as drafts" };

/** The bar that appears when investors are ticked in a list: AI-personalised 3-email sequences for each, then
 *  scheduled for each investor's local morning, sent now, or kept as drafts. Schedule and Send now show one
 *  confirm screen with an "I agree" tick; the acceptance is kept in the audit log. */
export function BulkOutreachBar({ ids, onClear }: { ids: string[]; onClear: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [agree, setAgree] = useState(false);
  const run = useMutation({
    mutationFn: ({ action, confirm }: { action: Action; confirm: boolean }) =>
      api<Plan & Done>("/sequences/bulk-add", { method: "POST", json: { investor_ids: ids, action, confirm } }),
    onSuccess: (r) => {
      if (r.needs_confirm) {
        setAgree(false);
        setPlan(r);
        return;
      }
      setPlan(null);
      for (const k of ["sequences", "investors", "shortlist", "nav-counts", "outreach-stats", "upcoming", "home"]) qc.invalidateQueries({ queryKey: [k] });
      onClear();
      const held = r.drafts.filter((d) => d.reason);
      const parts =
        r.action === "draft"
          ? [`Added ${r.drafts.length} to Outreach as drafts. AI is personalising their emails now.`]
          : [
              r.scheduled
                ? `${r.scheduled} ${r.action === "now" ? "sending in the next few minutes" : "scheduled for their morning"}, with follow-ups 2 working days apart.`
                : "Nothing was scheduled.",
              held.length ? `${held.length} kept as drafts (${held[0].reason}).` : "",
            ];
      if (r.action !== "draft" && r.allowance?.moved) parts.push(allowanceNote(r.allowance));
      if (r.skipped.length) parts.push(`${r.skipped.length} skipped: ${r.skipped[0].name ? `${r.skipped[0].name}, ` : ""}${r.skipped[0].reason.toLowerCase()}.`);
      toast(parts.filter(Boolean).join(" "), r.scheduled || r.drafts.length ? "ok" : "err");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const busy = run.isPending;
  const go = (action: Action) => run.mutate({ action, confirm: false });
  if (!ids.length && !plan) return null;
  return (
    <>
      {ids.length > 0 && (
        <div className="sticky top-2 z-20 card p-2.5 flex flex-wrap items-center gap-2 border-brand/40 shadow-lg">
          <span className="text-sm font-medium px-1">{ids.length} selected</span>
          <button className="btn-primary btn-sm" disabled={busy} onClick={() => go("window")}>
            <CalendarClock size={14} /> {LABEL.window} ({ids.length})
          </button>
          <button className="btn-ghost btn-sm border border-line" disabled={busy} onClick={() => go("now")}>
            <Send size={14} /> {LABEL.now} ({ids.length})
          </button>
          <button className="btn-ghost btn-sm border border-line" disabled={busy} onClick={() => go("draft")}>
            <FileText size={14} /> {LABEL.draft} ({ids.length})
          </button>
          {busy && (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted">
              <Loader2 size={13} className="animate-spin" /> Working…
            </span>
          )}
          <button className="ml-auto p-1.5 text-muted hover:text-ink" aria-label="Clear selection" onClick={onClear}>
            <X size={16} />
          </button>
        </div>
      )}
      {plan && (
        <Sheet open onClose={() => setPlan(null)} title={plan.action === "now" ? `Send now to ${plan.count} investors` : `Schedule ${plan.count} investors for their morning`}>
          <div className="space-y-3 text-sm">
            <p>{plan.terms}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted">From</dt>
              <dd className="font-medium break-all">{plan.from} <span className="text-muted font-normal">(your Gmail)</span></dd>
              <dt className="text-muted">To</dt>
              <dd className="font-medium">
                {plan.investors.slice(0, 6).map((i) => i.name).join(", ")}
                {plan.count > 6 ? ` and ${plan.count - 6} more` : ""}
              </dd>
            </dl>
            {allowanceNote(plan.allowance) && (
              <p className={`rounded-lg px-3 py-2 ${plan.allowance?.moved ? "border border-amber-500/40 bg-amber-500/5" : "text-muted text-xs px-0 py-0"}`}>{allowanceNote(plan.allowance)}</p>
            )}
            {plan.skipped.length > 0 && (
              <div className="rounded-lg border border-line px-3 py-2 text-xs text-muted">
                <div className="font-medium text-ink mb-1">{plan.skipped.length} not included</div>
                {plan.skipped.slice(0, 5).map((s) => (
                  <div key={s.id}>
                    {s.name || "Unknown"}: {s.reason}
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-muted">
              Anyone who can&apos;t be emailed yet (no email revealed, spam warning) stays in Outreach as a draft for you to fix. You can pause or cancel any scheduled email from Outreach.
            </p>
            <label className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 cursor-pointer ${agree ? "border-brand/50 bg-brand/5" : "border-line"}`}>
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--brand)]" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              <span>I agree. Send these emails from my Gmail as described above.</span>
            </label>
            <div className="flex flex-wrap justify-end gap-2 pt-1">
              <button className="btn-ghost" onClick={() => setPlan(null)}>
                Cancel
              </button>
              <button className="btn-primary" disabled={!agree || busy || plan.count === 0} onClick={() => run.mutate({ action: plan.action, confirm: true })}>
                {busy ? <Loader2 size={15} className="animate-spin" /> : plan.action === "now" ? <Send size={15} /> : <CalendarClock size={15} />}
                {plan.action === "now" ? `Send to ${plan.count}` : `Schedule ${plan.count}`}
              </button>
            </div>
          </div>
        </Sheet>
      )}
    </>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lightbulb, RefreshCw } from "lucide-react";
import { useState } from "react";
import { errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

type Finding = { kind: "subject" | "angle"; step: number; text: string };
type Insights = { sent: number; need: number; enough: boolean; findings: Finding[]; pending: number; opens_counted: boolean };

/** What's working in the founder's own outreach. New drafts already use it; emails not sent yet can be rewritten
 *  with it on the founder's tap (one investor per request, like the email templates update). */
export function InsightsBox() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<Insights>({ queryKey: ["outreach-insights"], queryFn: () => api("/outreach/insights"), refetchInterval: 120_000 });
  const [asking, setAsking] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: async () => {
      type R = { redrafted: number; left: number; done_ids: string[] };
      let done: string[] = [];
      let n = 0;
      const total = q.data?.pending ?? 0;
      for (let i = 0; i < 200; i++) {
        setProgress(`Updating ${Math.min(n + 1, total)} of ${total}…`);
        const r = await api<R>("/outreach/playbook/redraft", { method: "POST", json: { skip: done, batch: 1 } });
        n += r.redrafted;
        done = [...done, ...r.done_ids];
        if (!r.left || !r.redrafted) break;
      }
      return n;
    },
    onSuccess: (n) => {
      setProgress(null);
      setAsking(false);
      for (const k of ["sequences", "upcoming", "outreach-insights", "playbook"]) qc.invalidateQueries({ queryKey: [k] });
      toast(`Updated ${n} investor${n === 1 ? "" : "s"}' emails with what's working. Scheduled times stay the same.`);
    },
    onError: (e) => {
      setProgress(null);
      toast(errText(e), "err");
    },
  });
  const d = q.data;
  if (!d) return null;
  return (
    <div className="mt-3 pt-3 border-t border-line text-xs">
      <div className="flex items-center gap-1.5 font-semibold text-sm mb-1">
        <Lightbulb size={14} className="text-brand" /> What&apos;s working
      </div>
      {!d.enough ? (
        <p className="text-muted">
          Your agent learns which subjects and angles get replies{d.opens_counted ? " and opens" : ""} once {d.need} emails have gone out ({d.sent} so far). New drafts then lean towards what works.
        </p>
      ) : d.findings.length === 0 ? (
        <p className="text-muted">No clear winner yet across {d.sent} emails. Your agent keeps varying subjects and angles and checks again as results come in.</p>
      ) : (
        <>
          <ul className="space-y-1">
            {d.findings.map((f) => (
              <li key={`${f.kind}-${f.step}`}>{f.text}.</li>
            ))}
          </ul>
          <p className="text-muted mt-1">New drafts already lean towards this.</p>
          {d.pending > 0 &&
            (asking ? (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span>Rewrite {d.pending} investor{d.pending === 1 ? "'s" : "s'"} emails that haven&apos;t gone out?</span>
                <button className="btn-primary btn-sm" disabled={run.isPending} onClick={() => run.mutate()}>
                  {run.isPending ? <><RefreshCw size={12} className="animate-spin" /> {progress}</> : "Yes, update"}
                </button>
                {!run.isPending && <button className="btn-ghost btn-sm" onClick={() => setAsking(false)}>No</button>}
              </div>
            ) : (
              <button className="btn-ghost btn-sm mt-2" onClick={() => setAsking(true)}>
                Use it in {d.pending} email{d.pending === 1 ? "" : "s"} not sent yet
              </button>
            ))}
        </>
      )}
    </div>
  );
}

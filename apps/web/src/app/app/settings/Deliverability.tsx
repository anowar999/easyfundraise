"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { api } from "@/lib/api";

type Check = { name: string; ok: boolean; detail: string };
type D = { connected: boolean; email?: string; domain?: string; ok?: boolean; managed?: boolean; checks?: Check[] };

/** SPF / DKIM / DMARC for the sending domain: the records Gmail and Outlook check before trusting cold email. */
export function Deliverability() {
  const q = useQuery<D>({ queryKey: ["deliverability"], queryFn: () => api("/gmail/deliverability"), staleTime: 10 * 60_000 });
  const d = q.data;
  if (!d?.connected || !d.checks) return null;
  return (
    <div className="mt-4 rounded-xl border border-line p-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <ShieldCheck size={15} className={d.ok ? "text-emerald-600" : "text-warn"} /> Sending domain: {d.domain}
        <span className="text-xs font-normal text-muted">{d.ok ? "set up for inbox delivery" : "fix these so emails don't land in spam"}</span>
      </div>
      <ul className="mt-2 space-y-1 text-xs">
        {d.checks.map((c) => (
          <li key={c.name} className="flex gap-2">
            {c.ok ? <CheckCircle2 size={13} className="text-emerald-600 shrink-0 mt-0.5" /> : <XCircle size={13} className="text-warn shrink-0 mt-0.5" />}
            <span className="font-medium w-12 shrink-0">{c.name}</span>
            <span className="text-muted">{c.detail}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-muted">
        Also built in: a 20 a day limit, a slow warm-up for new mailboxes, spaced-out sending, a per-firm limit, a spam score on every email, and every sequence stops on a reply or bounce.
      </p>
    </div>
  );
}

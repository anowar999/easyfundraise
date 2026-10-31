"use client";

import { Lock, Send } from "lucide-react";
import { useState } from "react";
import { Sheet } from "./ui";

export type SendPreview = {
  from: string;
  to?: string | string[];
  count?: number;
  investor?: string;
  timezone?: string;
  emails?: { step: number; subject: string; scheduled_for: string }[];
};

const when = (iso: string, tz?: string) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", ...(tz ? { timeZone: tz } : {}) });

/** The last step before anything leaves the founder's Gmail: who, from which mailbox, and when. */
export function ConfirmSend({ preview, onCancel, onConfirm, busy }: { preview: SendPreview | null; onCancel: () => void; onConfirm: () => void; busy: boolean }) {
  const [ok, setOk] = useState(false);
  if (!preview) return null;
  const to = Array.isArray(preview.to) ? preview.to : preview.to ? [preview.to] : [];
  const many = (preview.emails?.length ?? preview.count ?? to.length) > 1;
  return (
    <Sheet open onClose={onCancel} title="Confirm before sending">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted">From</dt>
        <dd className="font-medium break-all">{preview.from} <span className="text-muted font-normal">(your Gmail)</span></dd>
        <dt className="text-muted">To</dt>
        <dd className="font-medium break-all">
          {preview.investor ? `${preview.investor} · ` : ""}
          {to.join(", ")}
          {preview.count && preview.count > to.length ? ` and ${preview.count - to.length} more` : ""}
        </dd>
      </dl>
      {preview.emails && (
        <ol className="mt-4 divide-y divide-line rounded-xl border border-line">
          {preview.emails.map((e) => (
            <li key={e.step} className="flex items-start gap-3 p-3 text-sm">
              <span className="grid place-items-center w-6 h-6 rounded-full bg-brand/10 text-brand text-xs font-semibold shrink-0">{e.step}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium truncate">{e.subject}</span>
                <span className="text-muted">
                  {when(e.scheduled_for, preview.timezone)} their time · {when(e.scheduled_for)} yours
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-4 text-sm text-muted">
        {preview.emails ? "Follow-ups only go if they haven't replied. Stop the sequence any time before a send." : "Each email goes a few minutes apart. You can stop unsent emails any time."}
      </p>
      <label className="mt-4 flex items-start gap-2.5 text-sm cursor-pointer">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[#0f62fe]" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        <span>I&apos;ve reviewed {many ? "these emails" : "this email"} and want EasyFundraise to send {many ? "them" : "it"} from my Gmail.</span>
      </label>
      <div className="mt-5 flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
        <button className="btn-ghost h-11" onClick={onCancel}>Not yet</button>
        <button className="btn-primary h-11" disabled={!ok || busy} onClick={onConfirm}>
          <Send size={16} /> {busy ? "Scheduling…" : "Yes, send from my Gmail"}
        </button>
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
        <Lock size={12} /> Sent through Google from your own mailbox. We never send without this confirmation.
      </p>
    </Sheet>
  );
}

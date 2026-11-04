"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CheckCircle2, Eye, EyeOff, Megaphone, RefreshCw, Send, X } from "lucide-react";
import { useState } from "react";
import { ListSearch, matches } from "@/components/ListSearch";
import { from } from "@/components/Crumbs";
import Link from "next/link";
import { Empty, ErrorState, IconBtn, ListSkeleton, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

export type Upcoming = {
  email_id: string;
  sequence_id: string | null;
  card_id?: string | null;
  kind: "sequence" | "update";
  step: number;
  subject: string;
  body: string;
  to: string;
  scheduled_for: string;
  investor: string;
  firm: string;
  timezone: string;
  can_send_now: boolean;
  spam?: { score: number; level: "good" | "warn" | "high"; reasons: string[] };
  send_now_from: string | null;
  sending: boolean;
};

function at(iso: string, tz?: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", ...(tz ? { timeZone: tz } : {}) });
  } catch {
    return new Date(iso).toLocaleString();
  }
}

export function useUpcoming() {
  return useQuery<{ items: Upcoming[] }>({
    queryKey: ["upcoming"],
    queryFn: () => api("/sequences/scheduled"),
    refetchInterval: (q) => (q.state.data?.items.some((u) => u.sending) ? 2_000 : 60_000),
  });
}

/** Every email waiting to go out, soonest first: the investor's local time (when it lands) and yours. */
export function UpcomingList() {
  const q = useUpcoming();
  const qc = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState<{ id: string; what: "send" | "cancel" } | null>(null);  // waiting for "Yes"
  const [going, setGoing] = useState<Record<string, string>>({});  // email id -> investor, sent with Send now
  const now = useMutation({
    mutationFn: (u: Upcoming) => api(`/sequences/scheduled/${u.email_id}/send-now`, { method: "POST", json: { anyway: !u.can_send_now } }),
    onMutate: (u) => {
      setAsking(null);
      setGoing((g) => ({ ...g, [u.email_id]: u.investor }));
    },  // the button goes at once: no second tap
    onSuccess: (_, u) => {
      for (const k of ["upcoming", "outreach-stats", "sequences", "sequence"]) qc.invalidateQueries({ queryKey: [k] });
      toast(`${u.kind === "update" ? "The update" : `Email ${u.step}`} to ${u.investor} is on its way. It'll show in your Gmail Sent within a minute.`);
    },
    onError: (e, u) => {
      setGoing((g) => {
        const { [u.email_id]: _, ...rest } = g;
        return rest;
      });
      toast(errText(e), "err");
    },
  });
  const [find, setFind] = useState("");
  const [open, setOpen] = useState<string | null>(null);  // previewed email

  const cancel = useMutation({
    mutationFn: (u: Upcoming) => api<{ back_to_draft: boolean }>(`/sequences/scheduled/${u.email_id}/cancel`, { method: "POST" }),
    onSuccess: (r, u) => {
      setAsking(null);
      for (const k of ["upcoming", "outreach-stats", "sequences", "sequence"]) qc.invalidateQueries({ queryKey: [k] });
      toast(r.back_to_draft ? `Cancelled. ${u.investor}'s emails are back in drafts; approve them again to reschedule.` : `Cancelled. ${u.kind === "update" ? "The update" : `Email ${u.step}`} to ${u.investor} won't be sent.`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const all = q.data!.items;
  const items = all.filter((u) => matches(find, u.investor, u.firm, u.to));
  const listed = new Set(all.map((u) => u.email_id));
  const done = Object.entries(going).filter(([id]) => !listed.has(id));  // sent since: gone from the list
  if (!all.length && !done.length)
    return <Empty icon={<CalendarClock />} title="Nothing scheduled" body="Approved emails wait here until their send time, in each investor's local morning window." />;
  const mine = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return (
    <div className="card divide-y divide-line">
      <p className="px-4 py-2.5 text-xs text-muted">
        Scheduled emails go out from your Gmail at these times and only appear in Gmail Sent once they&apos;re sent. Follow-ups and updates reply in email 1&apos;s thread.
      </p>
      <div className="px-4 py-2">
        <ListSearch value={find} onChange={setFind} className="max-w-xs" />
      </div>
      {find && items.length === 0 && <p className="px-4 py-6 text-sm text-muted text-center">No scheduled email matches &ldquo;{find}&rdquo;.</p>}
      {done.map(([id, who]) => (
        <div key={id} role="status" className="flex items-center gap-2 px-4 py-2.5 text-sm text-green-700 bg-green-600/5">
          <CheckCircle2 size={15} /> Sent to {who}. It&apos;s in your Gmail Sent.
        </div>
      ))}
      {items.map((u) => {
        const onWay = u.sending || !!going[u.email_id];
        const href = u.sequence_id ? from(`/app/sequences/${u.sequence_id}`, "outreach-scheduled") : u.card_id ? from(`/app/funnel/${u.card_id}`, "outreach-scheduled") : null;
        const label = (
          <>
            <div className="text-sm font-medium truncate">
              {u.investor}
              {u.firm ? <span className="text-muted font-normal">, {u.firm}</span> : null}
              <span className="text-muted font-normal"> · {u.kind === "update" ? "progress update" : `email ${u.step}`}</span>
            </div>
            <div className="text-xs text-muted truncate">{u.subject}</div>
          </>
        );
        const what = u.kind === "update" ? "this update" : `email ${u.step}`;
        return (
          <div key={u.email_id} className="px-4 py-3">
            <div className="flex items-center gap-3">
              {u.kind === "update" && <Megaphone size={15} className="text-brand shrink-0" />}
              {href ? <Link href={href} className="flex-1 min-w-0">{label}</Link> : <div className="flex-1 min-w-0">{label}</div>}
              <div className="text-right text-xs shrink-0">
                <div className="font-medium">{at(u.scheduled_for, u.timezone)} their time</div>
                {u.timezone !== mine && <div className="text-muted">{at(u.scheduled_for)} yours</div>}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <IconBtn label={open === u.email_id ? "Hide the email" : "Preview the email"} active={open === u.email_id} onClick={() => setOpen(open === u.email_id ? null : u.email_id)}>
                {open === u.email_id ? <EyeOff size={14} /> : <Eye size={14} />}
              </IconBtn>
              {u.spam && u.spam.level !== "good" && (
                <span className={u.spam.level === "high" ? "chip text-red-600" : "chip text-warn"} title={u.spam.reasons.join("; ")}>
                  Spam risk {u.spam.score}
                </span>
              )}
              {onWay ? (
                <span className="chip inline-flex items-center gap-1 text-green-700">
                  <RefreshCw size={12} className="animate-spin" /> Sending
                </span>
              ) : (
                (() => {
                  const ask = asking?.id === u.email_id ? asking.what : null;
                  if (ask === "send")
                    return (
                      <span className="inline-flex flex-wrap items-center gap-1.5 text-xs">
                        <span>
                          {u.can_send_now ? `Send ${what} to ${u.investor} now?` : `It's less than a day since the last email to ${u.investor}. Send ${what} anyway?`}
                        </span>
                        <button className="btn-primary btn-sm" disabled={now.isPending} onClick={() => now.mutate(u)}>
                          <Send size={13} /> Yes, send
                        </button>
                        <button className="btn-ghost btn-sm" onClick={() => setAsking(null)}>No</button>
                      </span>
                    );
                  if (ask === "cancel")
                    return (
                      <span className="inline-flex flex-wrap items-center gap-1.5 text-xs">
                        <span>{u.kind === "sequence" && u.step === 1 ? "Cancel email 1? Its follow-ups go back to drafts too." : `Cancel ${what}?`}</span>
                        <button className="btn-ghost btn-sm text-warn" disabled={cancel.isPending} onClick={() => cancel.mutate(u)}>
                          {cancel.isPending ? "Cancelling…" : "Yes, cancel"}
                        </button>
                        <button className="btn-ghost btn-sm" onClick={() => setAsking(null)}>No</button>
                      </span>
                    );
                  return (
                    <>
                      {(u.can_send_now || u.send_now_from) && (
                        <IconBtn
                          label={u.can_send_now ? "Send now instead of at its scheduled time" : `Send now (it's less than a day since the last email; normally from ${u.send_now_from ? at(u.send_now_from) : "later"})`}
                          tone="brand"
                          onClick={() => setAsking({ id: u.email_id, what: "send" })}
                        >
                          <Send size={14} />
                        </IconBtn>
                      )}
                      <IconBtn label="Cancel send" tone="danger" onClick={() => setAsking({ id: u.email_id, what: "cancel" })}>
                        <X size={14} />
                      </IconBtn>
                    </>
                  );
                })()
              )}
            </div>
            {open === u.email_id && (
              <div className="mt-2 rounded-xl border border-line bg-surface/50 p-3">
                <div className="text-xs text-muted">To {u.to}</div>
                <div className="text-sm font-medium mt-1">{u.subject}</div>
                <div className="text-sm whitespace-pre-wrap mt-2 leading-relaxed">{u.body}</div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

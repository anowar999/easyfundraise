"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CheckCircle2, Megaphone, RefreshCw, Send } from "lucide-react";
import { useState } from "react";
import { from } from "@/components/Crumbs";
import Link from "next/link";
import { Empty, ErrorState, ListSkeleton, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

export type Upcoming = {
  email_id: string;
  sequence_id: string | null;
  card_id?: string | null;
  kind: "sequence" | "update";
  step: number;
  subject: string;
  to: string;
  scheduled_for: string;
  investor: string;
  firm: string;
  timezone: string;
  can_send_now: boolean;
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
    refetchInterval: (q) => (q.state.data?.items.some((u) => u.sending) ? 5_000 : 60_000),
  });
}

/** Every email waiting to go out, soonest first: the investor's local time (when it lands) and yours. */
export function UpcomingList() {
  const q = useUpcoming();
  const qc = useQueryClient();
  const toast = useToast();
  const [going, setGoing] = useState<Record<string, string>>({});  // email id -> investor, sent with Send now
  const now = useMutation({
    mutationFn: (u: Upcoming) => api(`/sequences/${u.sequence_id}/emails/${u.email_id}/send-now`, { method: "POST" }),
    onMutate: (u) => setGoing((g) => ({ ...g, [u.email_id]: u.investor })),  // the button goes at once: no second tap
    onSuccess: (_, u) => {
      for (const k of ["upcoming", "outreach-stats", "sequences", "sequence"]) qc.invalidateQueries({ queryKey: [k] });
      toast(`Email ${u.step} to ${u.investor} is on its way. It'll show in your Gmail Sent within a minute.`);
    },
    onError: (e, u) => {
      setGoing((g) => {
        const { [u.email_id]: _, ...rest } = g;
        return rest;
      });
      toast(errText(e), "err");
    },
  });
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const items = q.data!.items;
  const listed = new Set(items.map((u) => u.email_id));
  const done = Object.entries(going).filter(([id]) => !listed.has(id));  // sent since: gone from the list
  if (!items.length && !done.length)
    return <Empty icon={<CalendarClock />} title="Nothing scheduled" body="Approved emails wait here until their send time, in each investor's local morning window." />;
  const mine = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return (
    <div className="card divide-y divide-line">
      <p className="px-4 py-2.5 text-xs text-muted">
        Scheduled emails go out from your Gmail at these times and only appear in Gmail Sent once they&apos;re sent. Follow-ups and updates reply in email 1&apos;s thread.
      </p>
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
        return (
          <div key={u.email_id} className="flex items-center gap-3 px-4 py-3">
            {u.kind === "update" && <Megaphone size={15} className="text-brand shrink-0" />}
            {href ? <Link href={href} className="flex-1 min-w-0">{label}</Link> : <div className="flex-1 min-w-0">{label}</div>}
            <div className="text-right text-xs shrink-0">
              <div className="font-medium">{at(u.scheduled_for, u.timezone)} their time</div>
              {u.timezone !== mine && <div className="text-muted">{at(u.scheduled_for)} yours</div>}
            </div>
            {onWay ? (
              <span className="chip shrink-0 inline-flex items-center gap-1 text-green-700">
                <RefreshCw size={12} className="animate-spin" /> Sending
              </span>
            ) : u.can_send_now ? (
              <button className="btn-ghost btn-sm shrink-0" disabled={now.isPending} onClick={() => now.mutate(u)} title="Send this email now instead of at its scheduled time">
                <Send size={13} /> Send now
              </button>
            ) : u.send_now_from ? (
              <span className="text-[11px] text-muted shrink-0 w-24 text-right" title="Follow-ups wait at least a day after the email before them">
                Send now from {at(u.send_now_from)}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

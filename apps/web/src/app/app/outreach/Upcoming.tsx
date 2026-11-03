"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Send } from "lucide-react";
import { from } from "@/components/Crumbs";
import Link from "next/link";
import { Empty, ErrorState, ListSkeleton, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

export type Upcoming = {
  email_id: string;
  sequence_id: string;
  step: number;
  subject: string;
  to: string;
  scheduled_for: string;
  investor: string;
  firm: string;
  timezone: string;
  can_send_now: boolean;
};

function at(iso: string, tz?: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", ...(tz ? { timeZone: tz } : {}) });
  } catch {
    return new Date(iso).toLocaleString();
  }
}

export function useUpcoming() {
  return useQuery<{ items: Upcoming[] }>({ queryKey: ["upcoming"], queryFn: () => api("/sequences/scheduled"), refetchInterval: 60_000 });
}

/** Every email waiting to go out, soonest first: the investor's local time (when it lands) and yours. */
export function UpcomingList() {
  const q = useUpcoming();
  const qc = useQueryClient();
  const toast = useToast();
  const now = useMutation({
    mutationFn: (u: Upcoming) => api(`/sequences/${u.sequence_id}/emails/${u.email_id}/send-now`, { method: "POST" }),
    onSuccess: (_, u) => {
      for (const k of ["upcoming", "outreach-stats", "sequences", "sequence"]) qc.invalidateQueries({ queryKey: [k] });
      toast(`Email ${u.step} to ${u.investor} goes out within a minute. It'll show in Gmail Sent then.`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const items = q.data!.items;
  if (!items.length)
    return <Empty icon={<CalendarClock />} title="Nothing scheduled" body="Approved emails wait here until their send time, in each investor's local morning window." />;
  const mine = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return (
    <div className="card divide-y divide-line">
      <p className="px-4 py-2.5 text-xs text-muted">
        Scheduled emails go out from your Gmail at these times and only appear in Gmail Sent once they&apos;re sent. Follow-ups reply in email 1&apos;s thread.
      </p>
      {items.map((u) => (
        <div key={u.email_id} className="flex items-center gap-3 px-4 py-3">
          <Link href={from(`/app/sequences/${u.sequence_id}`, "outreach-scheduled")} className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">
              {u.investor}
              {u.firm ? <span className="text-muted font-normal">, {u.firm}</span> : null}
              <span className="text-muted font-normal"> · email {u.step}</span>
            </div>
            <div className="text-xs text-muted truncate">{u.subject}</div>
          </Link>
          <div className="text-right text-xs shrink-0">
            <div className="font-medium">{at(u.scheduled_for, u.timezone)} their time</div>
            {u.timezone !== mine && <div className="text-muted">{at(u.scheduled_for)} yours</div>}
          </div>
          {u.can_send_now && (
            <button className="btn-ghost btn-sm" disabled={now.isPending} onClick={() => now.mutate(u)} title="Send this email now instead of at its scheduled time">
              <Send size={13} /> Send now
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

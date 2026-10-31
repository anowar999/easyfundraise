"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarClock, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import type { Card } from "@/lib/types";

/** AI read-out at the top of a card: where this investor stands and the founder's next step. */
export function CardSummary({ card }: { card: Card }) {
  const q = useQuery<{ headline: string; next_step: string; engine: string }>({
    queryKey: ["card-summary", card.id, card.last_activity_at, card.updated_at],
    queryFn: () => api(`/funnel/${card.id}/summary`),
    staleTime: 60_000,
  });
  const upcoming = card.call_at && new Date(card.call_at).getTime() > Date.now() ? card.call_at : null;
  return (
    <div className="space-y-3">
      {upcoming && (
        <div className="flex items-center gap-3 rounded-2xl bg-orange-50 border border-orange-300/70 px-4 py-3">
          <CalendarClock size={22} className="text-orange-600 shrink-0" />
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-orange-700">Upcoming meeting</div>
            <div className="font-semibold">{fmtDate(upcoming, { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</div>
          </div>
        </div>
      )}
      <div className="card p-4 border-brand/25 bg-gradient-to-br from-brand/[0.06] to-transparent">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand">
          <Sparkles size={14} /> Where this stands
        </div>
        {q.isLoading ? (
          <div className="space-y-2 mt-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : q.data ? (
          <>
            <p className="mt-1.5 text-[15px] leading-snug">{q.data.headline}</p>
            <div className="mt-3 flex items-start gap-2 rounded-xl bg-brand text-white px-3.5 py-2.5">
              <ArrowRight size={18} className="shrink-0 mt-0.5" />
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide opacity-80">Next step</div>
                <div className="font-medium">{q.data.next_step}</div>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

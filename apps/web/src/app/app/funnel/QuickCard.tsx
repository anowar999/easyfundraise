"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ExternalLink, Star } from "lucide-react";
import Link from "next/link";
import { Avatar, Sheet, StatusBadge, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card, FunnelMeta } from "@/lib/types";
import { CardSummary } from "./CardSummary";
import { UpdatePanel } from "./UpdatePanel";

/** Pop-up for a tracker card: where it stands, then stage/status/priority/next contact and a note, saved together. */
export function QuickCard({ card, meta, onClose }: { card: Card | null; meta?: FunnelMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const star = useMutation({
    mutationFn: (starred: boolean) => api(`/funnel/${card!.id}`, { method: "PATCH", json: { starred } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["funnel"] }),
    onError: (e) => toast(errText(e), "err"),
  });
  if (!card) return null;
  return (
    <Sheet open onClose={onClose} title="Investor" wide>
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <Avatar name={card.name} size={48} />
          <div className="flex-1 min-w-0">
            <div className="text-lg font-semibold leading-tight truncate">{card.name}</div>
            <div className="text-sm text-muted truncate">{card.firm || "—"}</div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="chip text-xs">{card.stage_label}</span>
              <StatusBadge status={card.status} />
              <span className="chip text-xs">{card.priority}</span>
              {card.stale && (
                <span className="chip text-xs border-amber-300 bg-amber-50 text-amber-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> quiet {card.days_since_update} days
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => star.mutate(!card.starred)}
            className={clsx("p-2 rounded-full border transition-colors", card.starred ? "border-amber-300 bg-amber-50" : "border-line hover:border-amber-300")}
            aria-pressed={card.starred}
            title={card.starred ? `Star investor${card.star_reason ? `: ${card.star_reason}` : ""}` : "Mark as star investor"}
          >
            <Star size={18} className={card.starred ? "fill-amber-400 text-amber-500" : "text-muted"} />
          </button>
        </div>

        <CardSummary card={card} />

        <div className="rounded-2xl border border-line p-4">
          <UpdatePanel card={card} meta={meta} onSaved={(closing) => closing && onClose()} />
        </div>

        <div className="flex justify-end">
          <Link href={`/app/funnel/${card.id}`} className="btn-ghost btn-sm">
            <ExternalLink size={15} /> Open full card
          </Link>
        </div>
      </div>
    </Sheet>
  );
}

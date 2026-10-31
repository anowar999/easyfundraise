"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { EyeOff, ExternalLink } from "lucide-react";
import Link from "next/link";
import { Sheet, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card, FunnelMeta } from "@/lib/types";

const PRIORITY_HINT: Record<string, string> = { P1: "Top", P2: "High", P3: "Normal", P4: "Low" };

/** Pop-up for a tracker card: change stage, status or priority in a tap, or hide it by marking it inactive. */
export function QuickCard({ card, meta, onClose }: { card: Card | null; meta?: FunnelMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const save = useMutation({
    mutationFn: (patch: Partial<Pick<Card, "stage" | "status" | "priority">>) => api<Card>(`/funnel/${card!.id}`, { method: "PATCH", json: patch }),
    onSuccess: (_, patch) => {
      qc.invalidateQueries({ queryKey: ["funnel"] });
      qc.invalidateQueries({ queryKey: ["card", card!.id] });
      qc.invalidateQueries({ queryKey: ["home"] });
      if (patch.status === "Inactive" || patch.status === "Rejection") {
        toast(`${card!.name} marked ${patch.status === "Inactive" ? "inactive" : "rejected"} and hidden from your tracker`);
        onClose();
      } else toast("Saved");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  if (!card) return null;
  const pill = (active: boolean) => clsx("chip px-3 py-1.5 text-sm", active ? "bg-brand text-white border-brand" : "hover:border-brand");
  return (
    <Sheet open onClose={onClose} title={card.name}>
      <div className="space-y-4">
        {card.firm && <p className="text-sm text-muted -mt-2">{card.firm}</p>}
        <div>
          <label className="text-xs font-medium text-muted" htmlFor="qc-stage">
            Stage
          </label>
          <select id="qc-stage" className="input mt-1" value={card.stage} disabled={save.isPending} onChange={(e) => save.mutate({ stage: Number(e.target.value) })}>
            {meta?.stages.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-xs font-medium text-muted mb-1.5">Status</div>
          <div className="flex flex-wrap gap-1.5">
            {(meta?.statuses ?? ["Active", "Inactive", "Rejection", "Ghosting"]).map((s) => (
              <button key={s} className={pill(card.status === s)} disabled={save.isPending} onClick={() => card.status !== s && save.mutate({ status: s })}>
                {s === "Rejection" ? "Rejected" : s}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs font-medium text-muted mb-1.5">Priority</div>
          <div className="flex flex-wrap gap-1.5">
            {["P1", "P2", "P3", "P4"].map((p) => (
              <button key={p} className={pill(card.priority === p)} disabled={save.isPending} onClick={() => card.priority !== p && save.mutate({ priority: p })}>
                {p} <span className="opacity-70">· {PRIORITY_HINT[p]}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pt-2 border-t border-line">
          {card.status !== "Inactive" && (
            <button className="btn-ghost" disabled={save.isPending} onClick={() => save.mutate({ status: "Inactive" })}>
              <EyeOff size={16} /> Hide (mark inactive)
            </button>
          )}
          <Link href={`/app/funnel/${card.id}`} className="btn-primary">
            <ExternalLink size={16} /> Open full card
          </Link>
        </div>
      </div>
    </Sheet>
  );
}

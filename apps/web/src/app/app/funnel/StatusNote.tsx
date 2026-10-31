"use client";

import clsx from "clsx";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Card } from "@/lib/types";

export const REJECTION_REASONS = ["Not our stage", "Not our sector", "Too early on traction", "Market too small", "Team concerns",
  "Valuation / terms", "Fund timing", "Competitive conflict", "No reason given"];

type Change = Partial<Pick<Card, "stage" | "status" | "priority" | "starred" | "star_reason" | "next_contact_date">>;

/** Note box shown with every status change; a rejection also asks for the reason so patterns show up over time. */
export function StatusNote({ status, note, setNote, reason, setReason }: { status: string; note: string; setNote: (v: string) => void; reason: string; setReason: (v: string) => void }) {
  const rejected = status === "Rejection";
  return (
    <div className={clsx("rounded-xl border p-3 space-y-2", rejected ? "border-red-300/70 bg-red-50/50" : "border-line bg-surface/60")}>
      {rejected && (
        <>
          <div className="text-sm font-medium">Why did they pass?</div>
          <p className="text-xs text-muted -mt-1">Logging the reason helps you spot rejection patterns across your raise.</p>
          <div className="flex flex-wrap gap-1.5">
            {REJECTION_REASONS.map((r) => (
              <button key={r} type="button" onClick={() => setReason(reason === r ? "" : r)} className={clsx("chip text-xs", reason === r ? "bg-red-600 text-white border-red-600" : "hover:border-red-400")}>
                {r}
              </button>
            ))}
          </div>
        </>
      )}
      <textarea
        className="textarea min-h-16 text-sm bg-card"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={rejected ? "Anything they said, in their words (optional)" : "Add a note about this change (optional)"}
        aria-label="Note"
      />
    </div>
  );
}

/** Saves a set of changes plus an optional note (with the rejection reason first) in one go. */
export function useCardChange(cardId: string | undefined, onDone: (c: Change) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ change, note, reason }: { change: Change; note: string; reason: string }) => {
      if (Object.keys(change).length) await api(`/funnel/${cardId}`, { method: "PATCH", json: change });
      const text = [reason && `Rejection reason: ${reason}.`, note.trim()].filter(Boolean).join(" ");
      if (text) await api(`/funnel/${cardId}/notes`, { method: "POST", json: { body: text } });
      return change;
    },
    onSuccess: (change) => {
      qc.invalidateQueries({ queryKey: ["funnel"] });
      qc.invalidateQueries({ queryKey: ["card", cardId] });
      qc.invalidateQueries({ queryKey: ["home"] });
      onDone(change);
    },
  });
}

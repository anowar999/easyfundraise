"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

type Action = "send" | "regenerate" | "remove";
type Skip = { id: string; name: string; reason: string };
type Result = { done?: number; queued?: number; skipped?: Skip[]; kept_history?: boolean };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Actions for the ticked rows. Each id list is already narrowed to the rows the action applies to. */
export function BulkBar({ ids, onClear, onRegenerated, busy = false }: { ids: { send: string[]; regenerate: string[]; remove: string[] }; onClear: () => void; onRegenerated: (ids: string[]) => void; busy?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState<Action | null>(null);
  const m = useMutation({
    mutationFn: (action: Action) => api<Result>("/sequences/bulk", { method: "POST", json: { action, ids: ids[action], confirm: true } }),
    onSuccess: (r, action) => {
      const skipped = r.skipped?.length ?? 0;
      const skip = skipped ? ` ${plural(skipped, "was", "were")} skipped${r.skipped?.[0] ? ` (e.g. ${r.skipped[0].name}: ${r.skipped[0].reason})` : ""}.` : "";
      if (action === "send") toast(`Scheduled outreach to ${plural(r.done ?? 0, "investor")}. Emails go in their local send window and stop on any reply.${skip}`);
      if (action === "regenerate") {
        toast(`Rewriting drafts for ${plural(r.queued ?? 0, "investor")}. Each row unlocks as soon as its new emails are ready.${skip}`);
        onRegenerated(ids.regenerate.filter((id) => !r.skipped?.some((s) => s.id === id)));
      }
      if (action === "remove") toast(`Removed ${plural(r.done ?? 0, "investor")} from outreach.${r.kept_history ? " Sent emails stay in Activity." : ""}`);
      setAsking(null);
      onClear();
      for (const k of ["sequences", "upcoming", "outreach-stats", "nav-counts", "investors", "investor"]) qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => toast(errText(e), "err"),
  });

  const total = ids.remove.length;
  const question: Record<Action, string> = {
    send: `Schedule outreach to ${plural(ids.send.length, "investor")}? Emails go from your Gmail in their send window.`,
    regenerate: `Redraft emails for ${plural(ids.regenerate.length, "investor")}? Your edits to those drafts are replaced.`,
    remove: `Remove ${plural(ids.remove.length, "investor")} from outreach? Unsent emails are cancelled; sent ones stay in Activity.`,
  };
  const yes: Record<Action, string> = { send: "Yes, schedule", regenerate: "Yes, redraft", remove: "Yes, remove" };

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-line bg-brand/5 text-sm">
      {asking ? (
        <>
          <span className="flex-1 min-w-[12rem]">{question[asking]}</span>
          <button className={asking === "remove" ? "btn-ghost btn-sm text-warn" : "btn-primary btn-sm"} disabled={m.isPending} onClick={() => m.mutate(asking)}>
            {m.isPending ? "Working…" : yes[asking]}
          </button>
          <button className="btn-ghost btn-sm" disabled={m.isPending} onClick={() => setAsking(null)}>
            No
          </button>
        </>
      ) : (
        <>
          <span className="font-medium mr-auto">{total} selected</span>
          <button className="btn-primary btn-sm" disabled={busy || !ids.send.length} onClick={() => setAsking("send")}>
            <Send size={14} /> Send ({ids.send.length})
          </button>
          <button className="btn-ghost btn-sm" disabled={busy || !ids.regenerate.length} onClick={() => setAsking("regenerate")}>
            <RefreshCw size={14} /> Regenerate ({ids.regenerate.length})
          </button>
          <button className="btn-ghost btn-sm text-warn" disabled={busy || !total} onClick={() => setAsking("remove")}>
            <Trash2 size={14} /> Remove ({total})
          </button>
          <button type="button" className="text-xs text-muted hover:text-brand underline" onClick={onClear}>
            Clear
          </button>
        </>
      )}
    </div>
  );
}

"use client";

import clsx from "clsx";
import { EyeOff, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Sheet, errText, useToast } from "@/components/ui";
import type { Card, FunnelMeta } from "@/lib/types";
import { StarPicker } from "./StarPicker";
import { StatusNote, useCardChange } from "./StatusNote";

const PRIORITY_HINT: Record<string, string> = { P1: "Top", P2: "High", P3: "Normal", P4: "Low" };

/** Pop-up for a tracker card. Pick a new stage, status or priority, add a note, then press Save. */
export function QuickCard({ card, meta, onClose }: { card: Card | null; meta?: FunnelMeta; onClose: () => void }) {
  const toast = useToast();
  const [stage, setStage] = useState(0);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [star, setStar] = useState({ starred: false, star_reason: "" });
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  useEffect(() => {
    if (!card) return;
    setStage(card.stage);
    setStatus(card.status);
    setPriority(card.priority);
    setStar({ starred: card.starred, star_reason: card.star_reason });
    setNote("");
    setReason("");
  }, [card?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useCardChange(card?.id, (ch) => {
    toast(ch.status === "Inactive" || ch.status === "Rejection" ? `${card!.name} marked ${ch.status === "Inactive" ? "inactive" : "rejected"} and hidden from your tracker` : "Saved");
    onClose();
  });
  if (!card) return null;

  const change = {
    ...(stage !== card.stage ? { stage } : {}),
    ...(status !== card.status ? { status } : {}),
    ...(priority !== card.priority ? { priority } : {}),
    ...(star.starred !== card.starred || star.star_reason !== card.star_reason ? star : {}),
  };
  const dirty = Object.keys(change).length > 0 || note.trim() !== "" || reason !== "";
  const submit = () => save.mutate({ change, note, reason: status === "Rejection" ? reason : "" }, { onError: (e) => toast(errText(e), "err") });
  const pill = (active: boolean, was: boolean) => clsx("chip px-3 py-1.5 text-sm", active ? "bg-brand text-white border-brand" : was ? "border-brand/40 border-dashed" : "hover:border-brand");

  return (
    <Sheet open onClose={onClose} title={card.name}>
      <div className="space-y-4">
        {card.firm && <p className="text-sm text-muted -mt-2">{card.firm}</p>}
        {card.stale && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-300/60 px-3 py-2 text-sm text-amber-900">
            <span className="w-2 h-2 rounded-full bg-amber-400" /> No update for {card.days_since_update} days. Add a note or set a next contact date.
          </div>
        )}
        <StarPicker starred={star.starred} reason={star.star_reason} onSave={setStar} />
        <div>
          <label className="text-xs font-medium text-muted" htmlFor="qc-stage">
            Stage
          </label>
          <select id="qc-stage" className="input mt-1" value={stage} onChange={(e) => setStage(Number(e.target.value))}>
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
              <button key={s} type="button" className={pill(status === s, card.status === s)} onClick={() => setStatus(s)}>
                {s === "Rejection" ? "Rejected" : s}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs font-medium text-muted mb-1.5">Priority</div>
          <div className="flex flex-wrap gap-1.5">
            {["P1", "P2", "P3", "P4"].map((p) => (
              <button key={p} type="button" className={pill(priority === p, card.priority === p)} onClick={() => setPriority(p)}>
                {p} <span className="opacity-70">· {PRIORITY_HINT[p]}</span>
              </button>
            ))}
          </div>
        </div>
        <StatusNote status={status} note={note} setNote={setNote} reason={reason} setReason={setReason} />
        {status === "Rejection" && card.status !== "Rejection" && !reason && <p className="text-xs text-danger -mt-2">Pick a reason if you can. It makes the pattern report useful.</p>}
        <div className="flex flex-wrap gap-2 pt-2 border-t border-line">
          <button className="btn-primary" disabled={!dirty || save.isPending} onClick={submit}>
            {save.isPending ? "Saving…" : "Save changes"}
          </button>
          {card.status !== "Inactive" && status !== "Inactive" && (
            <button className="btn-ghost" onClick={() => setStatus("Inactive")} title="Select Inactive, then Save">
              <EyeOff size={16} /> Hide (mark inactive)
            </button>
          )}
          <Link href={`/app/funnel/${card.id}`} className="btn-ghost ml-auto">
            <ExternalLink size={16} /> Open full card
          </Link>
        </div>
      </div>
    </Sheet>
  );
}

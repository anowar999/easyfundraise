"use client";

import clsx from "clsx";
import { Star } from "lucide-react";
import { useState } from "react";

export const STAR_REASONS = ["Can lead", "Great communicator", "Great introducer", "Strategic value", "Fast decision maker"];

/** Star an investor as key to the round, with a reason (pick one or type your own). */
export function StarPicker({ starred, reason, busy, onSave }: { starred: boolean; reason: string; busy?: boolean; onSave: (v: { starred: boolean; star_reason: string }) => void }) {
  const [custom, setCustom] = useState("");
  return (
    <div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onSave({ starred: !starred, star_reason: starred ? "" : reason })}
          className={clsx("chip px-3 py-1.5 text-sm", starred ? "bg-amber-400 text-white border-amber-400" : "hover:border-amber-400")}
          aria-pressed={starred}
        >
          <Star size={14} className={starred ? "fill-white" : "text-amber-500"} /> {starred ? "Star investor" : "Mark as star investor"}
        </button>
        {starred && reason && <span className="text-sm text-muted truncate">{reason}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {STAR_REASONS.map((r) => (
          <button key={r} type="button" disabled={busy} onClick={() => onSave({ starred: true, star_reason: r })} className={clsx("chip text-xs", starred && reason === r ? "border-amber-400 text-amber-700 bg-amber-50" : "hover:border-amber-400")}>
            {r}
          </button>
        ))}
        <form
          className="inline-flex"
          onSubmit={(e) => {
            e.preventDefault();
            if (custom.trim()) onSave({ starred: true, star_reason: custom.trim() });
            setCustom("");
          }}
        >
          <input className="chip text-xs w-36 bg-transparent focus-visible:outline-none" placeholder="Other reason…" value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={200} />
        </form>
      </div>
    </div>
  );
}

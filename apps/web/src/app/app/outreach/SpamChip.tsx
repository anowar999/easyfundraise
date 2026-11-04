"use client";

import clsx from "clsx";
import { Tip } from "@/components/ui";

export type Spam = { score: number; level: "good" | "warn" | "high"; reasons: string[] };

const TIP = "Lower is better. 0 is clean; 60 or more can't be scheduled.";

function levelOf(s: Spam): "good" | "warn" | "high" {
  if (s.level) return s.level;
  return s.score >= 60 ? "high" : s.score >= 30 ? "warn" : "good";
}

/** Spam risk shown as Low / Medium / High with a green-to-red bar, so it reads the right way round. */
export function SpamChip({ spam, compact }: { spam: Spam; compact?: boolean }) {
  const level = levelOf(spam);
  const word = level === "good" ? "Low" : level === "warn" ? "Medium" : "High";
  const score = Math.max(0, Math.min(100, Math.round(spam.score)));
  const tip = spam.reasons?.length && level !== "good" ? `${TIP} ${spam.reasons.slice(0, 3).join("; ")}` : TIP;
  return (
    <Tip text={tip} align="center">
      <span
        tabIndex={0}
        aria-label={`Spam risk ${word}, ${score} out of 100. ${TIP}`}
        className={clsx(
          "chip inline-flex items-center gap-2 text-xs",
          level === "good" && "text-emerald-700 border-emerald-600/30",
          level === "warn" && "text-warn border-amber-500/40",
          level === "high" && "text-red-600 border-red-500/40",
        )}
      >
        <span className={clsx("relative inline-block h-1.5 rounded-full shrink-0", compact ? "w-12" : "w-20")} style={{ background: "linear-gradient(90deg,#16a34a,#eab308 50%,#dc2626)" }} aria-hidden>
          <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#0b1220] ring-2 ring-white" style={{ left: `${score}%` }} />
        </span>
        {compact ? (
          <span>Spam: {word}</span>
        ) : (
          <span>
            Spam risk: {word} · {score}/100
          </span>
        )}
      </span>
    </Tip>
  );
}

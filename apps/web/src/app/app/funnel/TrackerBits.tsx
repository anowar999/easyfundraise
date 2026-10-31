"use client";

import clsx from "clsx";
import { AlertCircle, Bell, CalendarClock, ChevronDown, Clock, Star } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fmtDate } from "@/lib/api";
import type { Card } from "@/lib/types";

export const DEFAULT_STATUSES = ["Active", "Ghosting"]; // Inactive and Rejection are hidden until picked
const LABEL: Record<string, string> = { Rejection: "Rejected" };

/** Status filter: tick any combination. */
export function StatusMulti({ all, value, onChange }: { all: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const label = value.length === all.length ? "All statuses" : value.length ? value.map((s) => LABEL[s] ?? s).join(", ") : "No status";
  return (
    <div className="relative" ref={ref}>
      <button type="button" className="input w-auto flex items-center gap-2 pr-3" onClick={() => setOpen((x) => !x)} aria-expanded={open} aria-label="Filter by status">
        <span className="text-muted">Status:</span> <span className="max-w-48 truncate">{label}</span> <ChevronDown size={15} className="text-muted" />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-56 rounded-xl border border-line bg-card shadow-lg p-1.5">
          {all.map((s) => (
            <label key={s} className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-surface cursor-pointer">
              <input type="checkbox" className="accent-[var(--brand)]" checked={value.includes(s)} onChange={(e) => onChange(e.target.checked ? [...value, s] : value.filter((x) => x !== s))} />
              {LABEL[s] ?? s}
            </label>
          ))}
          <div className="flex justify-between border-t border-line mt-1 pt-1.5 px-1 text-xs">
            <button className="text-brand" onClick={() => onChange(all)}>
              Select all
            </button>
            <button className="text-muted" onClick={() => onChange(DEFAULT_STATUSES)}>
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Small yellow dot on open investors with no update for 7+ days. */
export function StaleDot({ c }: { c: Card }) {
  if (!c.stale) return null;
  return <span className="inline-block w-2 h-2 rounded-full bg-amber-400 ring-2 ring-amber-100 shrink-0" title={`No update for ${c.days_since_update} days`} aria-label={`No update for ${c.days_since_update} days`} />;
}

export function StarMark({ c }: { c: Card }) {
  if (!c.starred) return null;
  return <Star size={13} className="fill-amber-400 text-amber-500 shrink-0" aria-label={`Star investor${c.star_reason ? `: ${c.star_reason}` : ""}`} />;
}

type Todo = { card: Card; kind: "overdue" | "today" | "call" | "stale"; text: string };

function todos(cards: Card[]): Todo[] {
  const soon = Date.now() + 2 * 864e5;
  const out: Todo[] = [];
  for (const c of cards) {
    if (c.status === "Inactive" || c.status === "Rejection") continue;
    if (c.overdue) out.push({ card: c, kind: "overdue", text: `Follow-up was due ${fmtDate(c.next_contact_date)}` });
    else if (c.due_today) out.push({ card: c, kind: "today", text: "Follow up today" });
    if (c.call_at && new Date(c.call_at).getTime() > Date.now() && new Date(c.call_at).getTime() < soon)
      out.push({ card: c, kind: "call", text: `Call ${fmtDate(c.call_at, { weekday: "short", hour: "2-digit", minute: "2-digit" })}: prep your brief` });
    if (c.stale && !c.overdue && !c.due_today) out.push({ card: c, kind: "stale", text: `No update for ${c.days_since_update} days` });
  }
  const rank = { overdue: 0, call: 1, today: 2, stale: 3 };
  return out.sort((a, b) => rank[a.kind] - rank[b.kind] || Number(b.card.starred) - Number(a.card.starred));
}

const ICON = {
  overdue: <AlertCircle size={15} className="text-danger" />,
  today: <Clock size={15} className="text-brand" />,
  call: <CalendarClock size={15} className="text-orange-500" />,
  stale: <span className="w-2 h-2 rounded-full bg-amber-400 mx-[3.5px]" />,
};

/** "What needs you" tray at the top of the tracker. Each line opens that investor. */
export function ActionTray({ cards, onOpen }: { cards: Card[]; onOpen: (id: string) => void }) {
  const items = todos(cards);
  const [open, setOpen] = useState<boolean | null>(null); // null = automatic: open only when 3 or fewer
  const expanded = open ?? items.length <= 3;
  if (!items.length)
    return (
      <div className="card px-4 py-3 mb-4 text-sm text-muted flex items-center gap-2">
        <Bell size={16} /> Nothing needs you right now.
      </div>
    );
  const shown = expanded ? items : [];
  return (
    <div className="card mb-4 overflow-hidden border-amber-300/60">
      <button className="w-full flex items-center gap-2 px-4 py-3 text-sm bg-amber-50/70" onClick={() => setOpen(!expanded)} aria-expanded={expanded}>
        <Bell size={16} className="text-amber-600" />
        <b>
          {items.length} thing{items.length > 1 ? "s" : ""} need{items.length > 1 ? "" : "s"} you
        </b>
        <span className="text-muted hidden sm:inline">
          · {["overdue", "call", "today", "stale"].map((k) => [k, items.filter((i) => i.kind === k).length] as const).filter(([, n]) => n).map(([k, n]) => `${n} ${k === "stale" ? "quiet 7+ days" : k === "call" ? "calls soon" : k === "today" ? "due today" : "overdue"}`).join(" · ")}
        </span>
        <ChevronDown size={16} className={clsx("ml-auto text-muted transition-transform", expanded && "rotate-180")} />
      </button>
      {shown.length > 0 && (
        <ul className="divide-y divide-line max-h-72 overflow-y-auto">
          {shown.map((t) => (
            <li key={t.card.id + t.kind}>
              <button className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left hover:bg-surface" onClick={() => onOpen(t.card.id)}>
                {ICON[t.kind]}
                <span className="font-medium truncate">{t.card.name}</span>
                <StarMark c={t.card} />
                <span className="text-muted truncate hidden sm:inline">{t.card.firm}</span>
                <span className={clsx("ml-auto shrink-0 text-xs", t.kind === "overdue" ? "text-danger" : "text-muted")}>{t.text}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

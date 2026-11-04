"use client";

import clsx from "clsx";
import { Activity, ArrowLeft, ArrowRight, BarChart3, Check, CalendarClock, ListChecks, Mail, PenLine, Reply, UserPlus, Zap, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Sheet } from "@/components/ui";

const SEEN_KEY = "ef-outreach-guide-seen";

const SLIDES: { icon: LucideIcon; title: string; body: string[] }[] = [
  {
    icon: UserPlus,
    title: "Add investors",
    body: [
      "From Investors or your Shortlist, add someone to outreach.",
      "Your agent drafts a 3-email sequence, personalised from their profile and your company.",
    ],
  },
  {
    icon: PenLine,
    title: "Review the drafts",
    body: [
      "Open an investor to read and edit their emails.",
      "Every email gets a spam risk check: lower is better, and 60 or more can't be scheduled.",
      "Not quite right? Regenerate it with another approach.",
    ],
  },
  {
    icon: CalendarClock,
    title: "Send or schedule",
    body: [
      "Emails go from your own Gmail. Email 1 goes Tuesday to Thursday morning in the investor's own time zone, and follow-ups go 2 working days apart.",
      "You confirm before anything is scheduled, or use Send now.",
    ],
  },
  {
    icon: Zap,
    title: "One by one or Auto-send",
    body: [
      "One by one (the default): you review each investor's emails and press Send, or send all the ready ones at once.",
      "Auto-send: every investor you add is emailed automatically from your Gmail, in their send window, without a review step.",
      "Switch at the top of the Outreach list. Your daily limit and the spam check apply either way.",
    ],
  },
  {
    icon: Reply,
    title: "Follow-ups stop on a reply",
    body: [
      "When an investor replies, even with a no, the rest of their sequence is cancelled.",
      "Bounces and opt-outs stop the sequence too.",
    ],
  },
  {
    icon: Activity,
    title: "Scheduled emails & Activity",
    body: [
      "The menu on the right shows what's queued: preview it, send it now or cancel it.",
      "Activity shows what happened: sent, seen, replied or cancelled.",
    ],
  },
  {
    icon: ListChecks,
    title: "Work in bulk",
    body: [
      "Filter the list by status or country.",
      "Tick investors, then Send, Regenerate or Remove them together.",
    ],
  },
  {
    icon: BarChart3,
    title: "Learn and update",
    body: [
      "Results and insights show which subjects and angles get replies.",
      "Email templates set your style. Round & progress update shares news with everyone you've emailed, as a reply in the same thread.",
    ],
  },
];

function GuideSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);
  const last = i === SLIDES.length - 1;
  useEffect(() => {
    if (open) setI(0);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "ArrowRight") setI((n) => Math.min(n + 1, SLIDES.length - 1));
      else if (e.key === "ArrowLeft") setI((n) => Math.max(n - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const s = SLIDES[i];
  const Icon = s.icon;
  return (
    <Sheet open={open} onClose={onClose} title="How outreach works">
      <div className="min-h-[220px]" aria-live="polite">
        <div className="text-xs text-muted">
          Slide {i + 1} of {SLIDES.length}
        </div>
        <div className="mt-3 w-11 h-11 rounded-xl bg-brand/10 text-brand grid place-items-center">
          <Icon size={22} />
        </div>
        <h3 className="mt-3 text-lg font-semibold">{s.title}</h3>
        <div className="mt-2 space-y-2 text-sm text-muted leading-relaxed">
          {s.body.map((p, k) => (
            <p key={k}>{p}</p>
          ))}
        </div>
      </div>
      <div className="mt-5 flex items-center justify-between gap-3">
        <button className="btn-ghost btn-sm" onClick={() => setI((n) => n - 1)} disabled={i === 0}>
          <ArrowLeft size={13} /> Back
        </button>
        <div className="flex items-center gap-1.5" role="tablist" aria-label="Slides">
          {SLIDES.map((sl, k) => (
            <button
              key={k}
              role="tab"
              aria-selected={k === i}
              aria-label={`Slide ${k + 1}: ${sl.title}`}
              onClick={() => setI(k)}
              className={clsx("h-1.5 rounded-full transition-all", k === i ? "w-4 bg-brand" : "w-1.5 bg-line hover:bg-muted")}
            />
          ))}
        </div>
        {last ? (
          <button className="btn-primary btn-sm" onClick={onClose}>
            <Check size={13} /> Done
          </button>
        ) : (
          <button className="btn-primary btn-sm" onClick={() => setI((n) => n + 1)}>
            Next <ArrowRight size={13} />
          </button>
        )}
      </div>
    </Sheet>
  );
}

/** Small card in the Outreach right column that opens a 8-slide guide. Shows a "New" dot until opened once. */
export function OutreachGuideCard() {
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(true);
  useEffect(() => {
    try {
      setSeen(localStorage.getItem(SEEN_KEY) === "1");
    } catch {}
  }, []);
  const read = () => {
    setOpen(true);
    setSeen(true);
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {}
  };
  return (
    <div className="card p-3 md:p-4">
      <div className="flex items-center gap-2">
        <Mail size={16} className="text-brand shrink-0" />
        <span className="font-semibold text-sm flex-1 flex items-center gap-1.5">
          How outreach works
          {!seen && <span className="w-2 h-2 rounded-full bg-brand" aria-label="New" title="New" />}
        </span>
        <button className="btn-ghost btn-sm" onClick={read}>
          Read
        </button>
      </div>
      <p className="mt-1.5 text-xs text-muted">From adding investors to replies and follow-ups, in 8 short steps.</p>
      <GuideSheet open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

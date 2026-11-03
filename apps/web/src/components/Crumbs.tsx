"use client";

import { ArrowLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Crumb = { label: string; href: string };

/** Where a detail page was opened from (?from=...), so the breadcrumb leads back there. */
const FROM: Record<string, Crumb[]> = {
  home: [{ label: "Home", href: "/app" }],
  outreach: [{ label: "Outreach", href: "/app/outreach" }],
  "outreach-activity": [{ label: "Outreach", href: "/app/outreach" }, { label: "Activity", href: "/app/outreach?tab=activity" }],
  "outreach-scheduled": [{ label: "Outreach", href: "/app/outreach" }, { label: "Scheduled", href: "/app/outreach?tab=scheduled" }],
  tracker: [{ label: "Investor tracker", href: "/app/funnel" }],
  shortlist: [{ label: "Shortlist", href: "/app/shortlist" }],
  investors: [{ label: "Investors", href: "/app/investors" }],
  alerts: [{ label: "Alerts", href: "/app/notifications" }],
  "data-room": [{ label: "Data room", href: "/app/data-room" }],
};

/** Appends ?from=<key> to a detail link so its page can show the way back. */
export const from = (href: string, key: keyof typeof FROM | string) => `${href}${href.includes("?") ? "&" : "?"}from=${key}`;

/** A breadcrumb at the top of a detail page: the page it was opened from (or `fallback`), then this page. */
export function Crumbs({ fallback, current, back }: { fallback: Crumb[]; current?: string; back?: boolean }) {
  const router = useRouter();
  const [trail, setTrail] = useState<Crumb[]>(fallback);
  const [known, setKnown] = useState(false);
  useEffect(() => {
    const key = new URLSearchParams(window.location.search).get("from") || "";
    if (FROM[key]) {
      setTrail(FROM[key]);
      setKnown(true);
    }
  }, []);
  if (back && !known)  // opened from a list with filters: going back keeps them
    return (
      <nav aria-label="Breadcrumb" className="text-sm text-muted flex items-center gap-2 mb-3">
        <button onClick={() => (window.history.length > 1 ? router.back() : router.push(fallback[0].href))} className="flex items-center gap-1 hover:text-brand">
          <ArrowLeft size={16} /> Back
        </button>
        {current && <span className="text-ink truncate max-w-[60vw]">· {current}</span>}
      </nav>
    );
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-muted flex items-center flex-wrap gap-1 mb-3">
      {trail.map((c) => (
        <span key={c.href} className="flex items-center gap-1">
          <Link href={c.href} className="hover:text-brand">
            {c.label}
          </Link>
          <ChevronRight size={14} />
        </span>
      ))}
      {current && <span className="text-ink truncate max-w-[60vw]">{current}</span>}
    </nav>
  );
}

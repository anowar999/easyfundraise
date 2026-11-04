"use client";

import clsx from "clsx";
import { ArrowUpRight, Building2, FileText, Gift, Rocket, Search, Sprout } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/** The founder resource library: public pitch decks, YC applications, perks and programs. Static seed data in
 *  src/lib/resources, so it works for every workspace without an API call. */
export const RESOURCE_PAGES = [
  { href: "/app/resources/pitch-decks", label: "Pitch decks", icon: FileText },
  { href: "/app/resources/ai-perks", label: "AI perks", icon: Gift },
  { href: "/app/resources/yc-applications", label: "YC applications", icon: Rocket },
  { href: "/app/resources/incubators", label: "Incubators", icon: Sprout },
  { href: "/app/resources/accelerators", label: "VCs & accelerators", icon: Building2 },
];

/** Tab row across the resource pages (the sidebar shows the same list on desktop) */
export function ResourceTabs() {
  const path = usePathname();
  return (
    <nav aria-label="Resources" className="flex gap-1.5 overflow-x-auto scrollbar-none -mx-4 px-4 mb-4 md:mb-5">
      {RESOURCE_PAGES.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className={clsx(
            "shrink-0 inline-flex items-center gap-1.5 rounded-full border px-3 h-9 text-sm font-medium transition",
            path.startsWith(href) ? "border-brand bg-brand text-white" : "border-line bg-card text-ink hover:border-brand/40",
          )}
        >
          <Icon size={15} /> {label}
        </Link>
      ))}
    </nav>
  );
}

export function ResourceSearch({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="relative block flex-1 min-w-[200px]">
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
      <input className="input pl-9" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
    </label>
  );
}

/** Pill filters with counts */
export function FilterPills<K extends string>({ options, value, onChange }: { options: { key: K; label: string; count: number }[]; value: K; onChange: (k: K) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="tablist">
      {options.map((o) => (
        <button
          key={o.key}
          role="tab"
          aria-selected={value === o.key}
          onClick={() => onChange(o.key)}
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-full border px-3 h-8 text-[13px] font-medium transition",
            value === o.key ? "border-ink bg-ink text-white" : "border-line bg-card text-ink hover:border-[#c6d0e0]",
          )}
        >
          {o.label}
          <span className={clsx("tabular-nums text-[11px]", value === o.key ? "text-white/70" : "text-muted")}>{o.count}</span>
        </button>
      ))}
    </div>
  );
}

export function OpenLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
      {children} <ArrowUpRight size={14} />
    </a>
  );
}

export function SourceNote({ children }: { children: ReactNode }) {
  return <p className="text-xs text-muted mt-6 leading-relaxed max-w-3xl">{children}</p>;
}

/** "a b c" matches if every word appears somewhere in the haystack */
export function matches(q: string, ...fields: (string | number | undefined)[]) {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = fields.filter((f) => f !== undefined).join(" ").toLowerCase();
  return words.every((w) => hay.includes(w));
}

export function fmtUsd(n: number) {
  if (n >= 1e9) return `$${+(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${+(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
}

export function NoMatches({ onClear }: { onClear: () => void }) {
  return (
    <div className="card p-8 text-center">
      <div className="font-semibold">Nothing matches</div>
      <button className="btn-ghost btn-sm mt-3" onClick={onClear}>Clear filters</button>
    </div>
  );
}

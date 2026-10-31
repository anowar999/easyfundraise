"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BadgeCheck, Check, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { flag, SHORT } from "@/lib/countries";
import type { InvestorCard } from "@/lib/types";
import { Avatar, Badge, FitScore, useToast } from "./ui";

/** Plus / tick button that saves an investor to the shortlist (and removes it again). */
export function ShortlistButton({ inv, size = "md" }: { inv: Pick<InvestorCard, "id" | "name" | "in_shortlist">; size?: "md" | "lg" }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [on, setOn] = useState(inv.in_shortlist);
  const m = useMutation({
    mutationFn: (add: boolean) => api(`/shortlist/${inv.id}`, { method: add ? "PUT" : "DELETE" }),
    onMutate: (add) => setOn(add),
    onSuccess: (_, add) => {
      qc.invalidateQueries({ queryKey: ["shortlist"] });
      toast(add ? `${inv.name} added to your shortlist` : `Removed ${inv.name} from your shortlist`);
    },
    onError: (_, add) => setOn(!add),
  });
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        m.mutate(!on);
      }}
      aria-pressed={on}
      aria-label={on ? `Remove ${inv.name} from shortlist` : `Add ${inv.name} to shortlist`}
      title={on ? "On your shortlist" : "Add to shortlist"}
      className={clsx(
        "grid place-items-center rounded-full border transition-colors shrink-0",
        size === "lg" ? "w-10 h-10" : "w-9 h-9",
        on ? "bg-brand border-brand text-white" : "border-line bg-card text-brand hover:border-brand hover:bg-brand/5",
      )}
    >
      {on ? <Check size={18} /> : <Plus size={18} />}
    </button>
  );
}

export function CountryTag({ country, location }: { country?: string; location?: string }) {
  const name = country || location?.split(",").slice(-1)[0].trim();
  if (!name) return null;
  const f = flag(country);
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted whitespace-nowrap" title={location || name}>
      {f && <span className="text-[13px] leading-none" aria-hidden>{f}</span>}
      {SHORT[name] ?? name}
    </span>
  );
}

export function InvestorRow({ inv }: { inv: InvestorCard }) {
  return (
    <div className="card p-4 flex gap-3 hover:border-brand/60 transition-colors">
      <Link href={`/app/investors/${inv.id}`} className="flex gap-3 flex-1 min-w-0">
        <Avatar name={inv.name} src={inv.photo_url} logoDomain={inv.firm_domain} size={48} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="font-medium truncate flex items-center gap-1.5">
                {inv.name}
                {inv.identity_confidence && inv.identity_confidence !== "high" && (
                  <span title="We couldn't fully confirm this person's current role or email. Check before reaching out.">
                    <Badge tone="amber">unverified</Badge>
                  </span>
                )}
              </div>
              <div className="text-sm text-muted truncate">
                {inv.title}
                {inv.firm ? ` · ${inv.firm}` : ""}
              </div>
            </div>
            {inv.fit && <FitScore score={inv.fit.score} />}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <Badge tone={inv.seed_fit === false ? "red" : inv.seed_fit ? "green" : "default"}>{inv.investor_type_label}</Badge>
            {inv.verified_recent_deal && (
              <Badge tone="green">
                <BadgeCheck size={12} /> recent deal
              </Badge>
            )}
            {inv.in_funnel && <Badge tone="blue">in tracker</Badge>}
            <CountryTag country={inv.country} location={inv.location} />
            {inv.industries.slice(0, 2).map((i) => (
              <span key={i} className="chip text-muted hidden sm:inline-flex">
                {i}
              </span>
            ))}
          </div>
          {inv.fit && inv.fit.reasons.length > 0 && <p className="mt-2 text-xs text-muted line-clamp-1">{inv.fit.reasons.join(" · ")}</p>}
        </div>
      </Link>
      <ShortlistButton inv={inv} />
    </div>
  );
}

import { BadgeCheck, MapPin } from "lucide-react";
import Link from "next/link";
import type { InvestorCard } from "@/lib/types";
import { Avatar, Badge, FitScore } from "./ui";

export function InvestorRow({ inv }: { inv: InvestorCard }) {
  return (
    <Link href={`/app/investors/${inv.id}`} className="card p-4 flex gap-3 hover:border-brand transition-colors">
      <Avatar name={inv.name} src={inv.photo_url} size={44} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-medium truncate flex items-center gap-1.5">
              {inv.name}
              {inv.identity_confidence && inv.identity_confidence !== "high" && <Badge tone="amber">needs verification</Badge>}
            </div>
            <div className="text-sm text-muted truncate">
              {inv.title}
              {inv.firm ? ` · ${inv.firm}` : ""}
            </div>
          </div>
          {inv.fit && <FitScore score={inv.fit.score} />}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Badge tone={inv.seed_fit === false ? "red" : inv.seed_fit ? "green" : "default"}>{inv.investor_type_label}</Badge>
          {inv.verified_recent_deal && (
            <Badge tone="green">
              <BadgeCheck size={12} /> recent deal
            </Badge>
          )}
          {inv.in_funnel && <Badge tone="blue">in funnel</Badge>}
          {inv.location && (
            <span className="chip text-muted">
              <MapPin size={11} /> {inv.location.split(",").slice(-1)[0].trim()}
            </span>
          )}
          {inv.industries.slice(0, 2).map((i) => (
            <span key={i} className="chip text-muted hidden sm:inline-flex">
              {i}
            </span>
          ))}
        </div>
        {inv.fit && inv.fit.reasons.length > 0 && <p className="mt-2 text-xs text-muted line-clamp-1">{inv.fit.reasons.join(" · ")}</p>}
        {inv.fit && inv.fit.warnings.length > 0 && <p className="mt-1 text-xs text-warn line-clamp-1">{inv.fit.warnings[0]}</p>}
      </div>
    </Link>
  );
}

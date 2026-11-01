"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BadgeCheck, Check, Heart, MailPlus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { flag, SHORT } from "@/lib/countries";
import type { InvestorCard } from "@/lib/types";
import { Avatar, Badge, FitScore, Tip, errText, useToast } from "./ui";

const iconBtn = (size: "md" | "lg") =>
  clsx(
    "grid place-items-center rounded-full border transition-colors shrink-0",
    size === "lg" ? "w-10 h-10" : "w-9 h-9",
  );

/** Heart button that saves an investor to the shortlist, your favourites (and removes it again). */
export function ShortlistButton({
  inv,
  size = "md",
}: {
  inv: Pick<InvestorCard, "id" | "name" | "in_shortlist">;
  size?: "md" | "lg";
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [on, setOn] = useState(inv.in_shortlist);
  const m = useMutation({
    mutationFn: (add: boolean) =>
      api(`/shortlist/${inv.id}`, { method: add ? "PUT" : "DELETE" }),
    onMutate: (add) => setOn(add),
    onSuccess: (_, add) => {
      qc.invalidateQueries({ queryKey: ["shortlist"] });
      toast(
        add
          ? `${inv.name} added to your shortlist`
          : `Removed ${inv.name} from your shortlist`,
      );
    },
    onError: (_, add) => setOn(!add),
  });
  return (
    <Tip
      text={
        on
          ? "On your shortlist of favourites. Click to remove"
          : "Shortlist this investor to your favourites"
      }
    >
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          m.mutate(!on);
        }}
        aria-pressed={on}
        aria-label={
          on
            ? `Remove ${inv.name} from your shortlist`
            : `Shortlist ${inv.name} to your favourites`
        }
        className={clsx(
          "grid place-items-center rounded-full border transition-colors shrink-0",
          size === "lg" ? "w-10 h-10" : "w-9 h-9",
          on
            ? "bg-rose-500 border-rose-500 text-white"
            : "border-line bg-card text-rose-500 hover:border-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10",
        )}
      >
        <Heart size={18} className={clsx(on && "fill-current")} />
      </button>
    </Tip>
  );
}

/** Adds the investor to outreach: drafts a personalised 3-email sequence in the background. Nothing is sent from here. */
export function OutreachButton({
  inv,
  size = "md",
}: {
  inv: Pick<InvestorCard, "id" | "name" | "in_outreach">;
  size?: "md" | "lg";
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [on, setOn] = useState(Boolean(inv.in_outreach));
  const m = useMutation({
    mutationFn: () =>
      api<{ id: string; auto: { scheduled: boolean; reason: string } | null }>(
        "/sequences",
        { method: "POST", json: { investor_id: inv.id } },
      ),
    onSuccess: (r) => {
      setOn(true);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      toast(
        r.auto?.scheduled
          ? `${inv.name} added to outreach. Auto-send is on, so their emails are scheduled.`
          : r.auto
            ? `${inv.name} added to outreach. Not sent yet: ${r.auto.reason.toLowerCase()}.`
            : `${inv.name} added to outreach. Emails drafted for you to review before anything is sent.`,
      );
    },
    onError: (e) =>
      toast(
        e instanceof ApiError && e.problem.upgrade
          ? "You've used your sample drafts. Upgrade to draft more."
          : errText(e),
        "err",
      ),
  });
  if (on)
    return (
      <Tip text="In your email outreach list. Open Outreach">
        <Link
          href="/app/outreach"
          onClick={(e) => e.stopPropagation()}
          aria-label={`${inv.name} is in your outreach list`}
          className={clsx(
            iconBtn(size),
            "bg-emerald-600 border-emerald-600 text-white",
          )}
        >
          <Check size={17} />
        </Link>
      </Tip>
    );
  return (
    <Tip text="Add to email outreach list">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          m.mutate();
        }}
        disabled={m.isPending}
        aria-label={`Add ${inv.name} to your email outreach list`}
        className={clsx(
          iconBtn(size),
          "border-line bg-card text-ink hover:border-brand hover:text-brand hover:bg-brand/5",
          m.isPending && "animate-pulse",
        )}
      >
        <MailPlus size={17} />
      </button>
    </Tip>
  );
}

/** Shortlist and outreach icons for investor lists. */
export function InvestorActions({
  inv,
  size = "md",
}: {
  inv: Pick<InvestorCard, "id" | "name" | "in_shortlist" | "in_outreach">;
  size?: "md" | "lg";
}) {
  return (
    <div className="flex items-center gap-1.5">
      <ShortlistButton inv={inv} size={size} />
      <OutreachButton inv={inv} size={size} />
    </div>
  );
}

export function CountryTag({
  country,
  location,
}: {
  country?: string;
  location?: string;
}) {
  const name = country || location?.split(",").slice(-1)[0].trim();
  if (!name) return null;
  const f = flag(country);
  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-muted whitespace-nowrap"
      title={location || name}
    >
      {f && (
        <span className="text-[13px] leading-none" aria-hidden>
          {f}
        </span>
      )}
      {SHORT[name] ?? name}
    </span>
  );
}

export function InvestorRow({ inv }: { inv: InvestorCard }) {
  return (
    <div className="card p-4 flex gap-3 hover:border-brand/60 transition-colors">
      <Link
        href={`/app/investors/${inv.id}`}
        className="flex gap-3 flex-1 min-w-0"
      >
        <Avatar
          name={inv.name}
          src={inv.photo_url}
          logoDomain={inv.firm_domain}
          size={48}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="font-medium truncate flex items-center gap-1.5">
                {inv.name}
                {inv.identity_confidence &&
                  inv.identity_confidence !== "high" && (
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
            <Badge
              tone={
                inv.seed_fit === false
                  ? "red"
                  : inv.seed_fit
                    ? "green"
                    : "default"
              }
            >
              {inv.investor_type_label}
            </Badge>
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
          {inv.fit && inv.fit.reasons.length > 0 && (
            <p className="mt-2 text-xs text-muted line-clamp-1">
              {inv.fit.reasons.join(" · ")}
            </p>
          )}
        </div>
      </Link>
      <div className="flex flex-col sm:flex-row items-start gap-1.5">
        <ShortlistButton inv={inv} />
        <OutreachButton inv={inv} />
      </div>
    </div>
  );
}

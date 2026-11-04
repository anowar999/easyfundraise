"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BadgeCheck, Heart, MailCheck, MailPlus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { flag, SHORT } from "@/lib/countries";
import type { InvestorCard } from "@/lib/types";
import { TicketChip } from "./InvestorChips";
import { QuickOutreach } from "./QuickOutreach";
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

/** Adds the investor to the email outreach list as a draft and opens a quick preview of the 3 emails, with Send
 *  now, Schedule for their morning, or Keep as draft. Nothing is sent without the confirm screen. */
export function OutreachButton({ inv, size = "md" }: { inv: Pick<InvestorCard, "id" | "name" | "in_outreach">; size?: "md" | "lg" }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [on, setOn] = useState(Boolean(inv.in_outreach));
  useEffect(() => {
    if (inv.in_outreach) setOn(true);  // added elsewhere (e.g. "Add all to outreach")
  }, [inv.in_outreach]);
  const [quick, setQuick] = useState<string | null>(null);  // the sequence shown in the quick preview
  const m = useMutation({
    // Draft only (hold): the quick preview decides Send now / Schedule / Keep as draft, whatever auto-send says.
    mutationFn: () => api<{ id: string }>("/sequences", { method: "POST", json: { investor_id: inv.id, hold: true } }),
    onMutate: () => setOn(true),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["sequences"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      setQuick(r.id);
    },
    onError: (e) => {
      setOn(false);
      toast(e instanceof ApiError && e.problem.upgrade ? "You've used your sample drafts. Upgrade to draft more." : errText(e), "err");
    },
  });
  // Rows are links to the profile: keep clicks inside the (portalled) sheet from bubbling up to them.
  const sheet = quick ? (
    <span onClick={(e) => e.stopPropagation()}>
      <QuickOutreach seqId={quick} name={inv.name} onClose={() => setQuick(null)} onDropped={() => setOn(false)} />
    </span>
  ) : null;
  if (on)
    return (
      <>
      <Tip text={m.isPending ? "Adding to your email outreach list…" : "In your email outreach list. Open Outreach"}>
        <Link
          href="/app/outreach"
          onClick={(e) => {
            e.stopPropagation();
            if (m.isPending) e.preventDefault();
          }}
          aria-label={`${inv.name} is in your email outreach list`}
          aria-busy={m.isPending}
          className={clsx(iconBtn(size), "relative bg-emerald-600 border-emerald-600 text-white")}
        >
          <MailCheck size={17} className={clsx(m.isPending && "opacity-40")} />
          {m.isPending && <span className="absolute inset-0 rounded-full border-2 border-white/80 border-t-transparent animate-spin" aria-hidden />}
        </Link>
      </Tip>
      {sheet}
      </>
    );
  return (
    <>
    <Tip text="Add to email outreach list">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          m.mutate();
        }}
        aria-label={`Add ${inv.name} to your email outreach list`}
        className={clsx(iconBtn(size), "border-line bg-card text-ink hover:border-emerald-500 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-500/10")}
      >
        <MailPlus size={17} />
      </button>
    </Tip>
    {sheet}
    </>
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

export function InvestorRow({ inv, picked, onPick }: { inv: InvestorCard; picked?: boolean; onPick?: () => void }) {
  return (
    <div className={clsx("card p-4 flex gap-3 hover:border-brand/60 transition-colors", picked && "border-brand/60 bg-brand/5")}>
      {onPick && (
        <input
          type="checkbox"
          className="mt-3.5 h-4 w-4 shrink-0 accent-[var(--brand)] disabled:opacity-40"
          checked={Boolean(picked)}
          disabled={inv.in_outreach}
          title={inv.in_outreach ? "Already in your outreach list" : `Select ${inv.name}`}
          aria-label={`Select ${inv.name}`}
          onChange={onPick}
        />
      )}
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
            <TicketChip t={inv} />
            {inv.verified_recent_deal && (
              <Badge tone="green">
                <BadgeCheck size={12} /> recent deal
              </Badge>
            )}
            {inv.is_test && <Badge tone="amber">test investor</Badge>}
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

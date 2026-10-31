"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, BadgeCheck, ExternalLink, Flag, KanbanSquare, Lock, Mail, MapPin, Sparkles, Unlock } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { InvestorRow } from "@/components/InvestorRow";
import { Avatar, Badge, ErrorState, FitScore, ListSkeleton, Locked, errText, useToast } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Fit, InvestorCard } from "@/lib/types";

type News = { headline?: string; title?: string; date?: string; source?: string; url?: string; summary?: string; key_point?: string };
type Deal = { company: string; date?: string; round?: string; role?: string; source_url?: string };
type Profile = InvestorCard & {
  fit: Fit;
  funnel_card_id: string | null;
  excluded: boolean;
  about: string;
  investment_thesis: string;
  focus_sectors: string;
  focus_stages: string;
  geography_focus: string;
  typical_check_size: string;
  fund_size_or_aum: string;
  leads_rounds: string;
  instrument_preference: string;
  investments_per_year_estimate: string;
  decision_speed: string;
  value_add: string;
  notable_portfolio: string[] | string;
  more_portfolio: number;
  recent_investments_12mo: Deal[];
  recent_news: News[];
  public_content: News[];
  personalization_hooks: string[];
  best_email_angle: string;
  sources: string[];
  notes: string;
  firm_website: string;
  firm_type: string;
  timezone: string;
  directory_tags: { stages: string; check_size: string };
  revealed: boolean;
  contacts: { email: string; linkedin: string; x: string } | null;
  contacts_locked: boolean;
};

const TABS = ["Fit", "Thesis & portfolio", "News", "How to pitch", "Similar"] as const;

function KV({ k, v }: { k: string; v?: string | null }) {
  if (!v || v === "unknown") return null;
  return (
    <div className="py-2 border-b border-line last:border-0">
      <div className="text-xs text-muted">{k}</div>
      <div className="text-sm mt-0.5">{v}</div>
    </div>
  );
}

export default function InvestorProfile() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Fit");
  const q = useQuery<Profile>({ queryKey: ["investor", id], queryFn: () => api(`/investors/${id}`) });
  const similar = useQuery<{ items: InvestorCard[] }>({ queryKey: ["similar", id], queryFn: () => api(`/investors/${id}/similar`), enabled: tab === "Similar" });

  const reveal = useMutation({
    mutationFn: () => api(`/investors/${id}/reveal`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["investor", id] }),
    onError: (e) => toast(errText(e), "err"),
  });
  const addToFunnel = useMutation({
    mutationFn: () => api<{ id: string }>("/funnel", { method: "POST", json: { investor_id: id } }),
    onSuccess: (c) => {
      toast("Added to your funnel");
      qc.invalidateQueries({ queryKey: ["investor", id] });
      qc.invalidateQueries({ queryKey: ["funnel"] });
      router.push(`/app/funnel/${c.id}`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const draft = useMutation({
    mutationFn: () => api<{ id: string }>("/sequences", { method: "POST", json: { investor_id: id } }),
    onSuccess: (s) => router.push(`/app/sequences/${s.id}`),
    onError: (e) => {
      if (e instanceof ApiError && e.problem.upgrade) toast("You've used your sample drafts. Upgrade to draft more.", "err");
      else toast(errText(e), "err");
    },
  });

  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const p = q.data!;
  const portfolio = Array.isArray(p.notable_portfolio) ? p.notable_portfolio : String(p.notable_portfolio || "").split(";").map((x) => x.trim()).filter(Boolean);

  return (
    <div className="pb-20 md:pb-0">
      <button onClick={() => router.back()} className="text-sm text-muted flex items-center gap-1 mb-3">
        <ArrowLeft size={16} /> Back
      </button>
      <div className="card p-4 md:p-6">
        <div className="flex gap-4">
          <Avatar name={p.name} src={p.photo_url} size={64} />
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-xl font-semibold">{p.name}</h1>
                <div className="text-sm text-muted">
                  {p.title}
                  {p.firm && ` · ${p.firm}`}
                </div>
                {p.listed_company && p.firm && p.listed_company !== p.firm && <div className="text-xs text-muted">Listed as {p.listed_company}</div>}
              </div>
              <FitScore score={p.fit.score} />
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge tone={p.seed_fit === false ? "red" : p.seed_fit ? "green" : "default"}>{p.investor_type_label}{p.seed_fit === false && " · not early-stage"}</Badge>
              {p.verified_recent_deal && (
                <Badge tone="green">
                  <BadgeCheck size={12} /> Activity: verified recent deal
                </Badge>
              )}
              {p.identity_confidence && p.identity_confidence !== "high" && <Badge tone="amber">Needs verification</Badge>}
              {!p.enriched && <Badge>Directory profile</Badge>}
              {p.excluded && <Badge tone="red">Excluded</Badge>}
              {p.location && (
                <span className="chip text-muted">
                  <MapPin size={11} /> {p.location}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-line p-3 flex flex-wrap items-center gap-3">
          {p.contacts ? (
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm no-select">
              {p.contacts.email && (
                <a href={`mailto:${p.contacts.email}`} className="flex items-center gap-1.5 text-brand">
                  <Mail size={14} /> {p.contacts.email}
                </a>
              )}
              {p.contacts.linkedin && (
                <a href={p.contacts.linkedin} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-brand">
                  <ExternalLink size={14} /> LinkedIn
                </a>
              )}
            </div>
          ) : p.contacts_locked ? (
            <>
              <Locked label="Contact locked on your plan" />
              <Link href="/app/settings#plan" className="text-sm text-brand ml-auto">
                Unlock contacts
              </Link>
            </>
          ) : (
            <button className="btn-ghost btn-sm" onClick={() => reveal.mutate()} disabled={reveal.isPending}>
              <Unlock size={14} /> Reveal contact (1 credit)
            </button>
          )}
        </div>

        {/* Desktop actions */}
        <div className="hidden md:flex gap-2 mt-4">
          {p.funnel_card_id ? (
            <Link href={`/app/funnel/${p.funnel_card_id}`} className="btn-ghost">
              <KanbanSquare size={16} /> Open in funnel
            </Link>
          ) : (
            <button className="btn-ghost" onClick={() => addToFunnel.mutate()} disabled={addToFunnel.isPending}>
              <KanbanSquare size={16} /> Add to funnel
            </button>
          )}
          <button className="btn-primary" onClick={() => draft.mutate()} disabled={draft.isPending || p.excluded}>
            <Sparkles size={16} /> Draft 3-email sequence
          </button>
        </div>
      </div>

      <div className="mt-4 flex gap-1 overflow-x-auto scrollbar-none border-b border-line" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={clsx("px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px", tab === t ? "border-brand text-brand font-medium" : "border-transparent text-muted")}>
            {t}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "Fit" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card p-4">
              <h2 className="font-semibold mb-2">Why they fit</h2>
              {p.fit.reasons.length ? (
                <ul className="space-y-1.5 text-sm">
                  {p.fit.reasons.map((r) => (
                    <li key={r} className="flex gap-2">
                      <span className="text-accent">✓</span> {r}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">
                  Add your company profile in <Link className="text-brand" href="/app/settings#company">Settings</Link> to see why this investor fits.
                </p>
              )}
              {p.fit.warnings.map((w) => (
                <p key={w} className="text-sm text-warn mt-2 flex gap-2">
                  <Flag size={14} className="mt-0.5 shrink-0" /> {w}
                </p>
              ))}
            </div>
            <div className="card p-4">
              <KV k="Stages (researched)" v={p.focus_stages} />
              <KV k="Sectors (researched)" v={p.focus_sectors} />
              <KV k="Geography" v={p.geography_focus} />
              <KV k="Typical check" v={p.typical_check_size} />
              <KV k="Leads rounds" v={p.leads_rounds} />
              <KV k="Instrument" v={p.instrument_preference} />
              {!p.enriched && (
                <>
                  <KV k="Stages (directory tag, unverified)" v={p.directory_tags.stages} />
                  <KV k="Check size (directory tag, unverified)" v={p.directory_tags.check_size} />
                </>
              )}
              <KV k="Sectors listed" v={p.industries.join(", ")} />
            </div>
          </div>
        )}
        {tab === "Thesis & portfolio" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card p-4 space-y-3">
              {p.investment_thesis && (
                <div>
                  <h2 className="font-semibold">Thesis</h2>
                  <p className="text-sm mt-1">{p.investment_thesis}</p>
                </div>
              )}
              {p.about && (
                <div>
                  <h2 className="font-semibold">About</h2>
                  <p className="text-sm mt-1 text-muted">{p.about}</p>
                </div>
              )}
              <KV k="Fund size / AUM" v={p.fund_size_or_aum} />
              <KV k="Firm type" v={p.firm_type} />
              {p.firm_website && (
                <a href={p.firm_website} target="_blank" rel="noreferrer" className="text-sm text-brand flex items-center gap-1">
                  {p.firm_website} <ExternalLink size={12} />
                </a>
              )}
            </div>
            <div className="card p-4">
              <h2 className="font-semibold mb-2">Portfolio</h2>
              <div className="flex flex-wrap gap-1.5">
                {portfolio.map((c) => (
                  <span key={c} className="chip">
                    {c}
                  </span>
                ))}
                {p.more_portfolio > 0 && <span className="chip text-muted">+{p.more_portfolio} more</span>}
              </div>
              {p.recent_investments_12mo.length > 0 && (
                <>
                  <h3 className="font-semibold mt-4 mb-2 text-sm">Recent deals (12 months)</h3>
                  {p.recent_investments_12mo.map((d) => (
                    <div key={d.company + d.date} className="text-sm py-1.5 border-b border-line last:border-0">
                      <span className="font-medium">{d.company}</span> {d.round && <span className="text-muted">· {d.round}</span>} {d.date && <span className="text-muted">· {d.date}</span>}
                      {d.source_url && (
                        <a href={d.source_url} target="_blank" rel="noreferrer" className="ml-1 text-brand text-xs">
                          source
                        </a>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        )}
        {tab === "News" && (
          <div className="space-y-2">
            {[...p.recent_news, ...p.public_content].length === 0 && <p className="text-sm text-muted card p-4">No dated news or public content on file yet.</p>}
            {[...p.recent_news, ...p.public_content].map((n, i) => (
              <a key={i} href={n.url} target="_blank" rel="noreferrer" className="card p-4 block hover:border-brand">
                <div className="text-sm font-medium">{n.headline ?? n.title}</div>
                <div className="text-xs text-muted mt-0.5">{[n.source, n.date].filter(Boolean).join(" · ")}</div>
                {(n.summary ?? n.key_point) && <p className="text-sm text-muted mt-1">{n.summary ?? n.key_point}</p>}
              </a>
            ))}
          </div>
        )}
        {tab === "How to pitch" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card p-4">
              <h2 className="font-semibold mb-2">Best angle</h2>
              <p className="text-sm">{p.best_email_angle || "Not researched yet."}</p>
              {p.personalization_hooks.length > 0 && (
                <>
                  <h3 className="font-semibold text-sm mt-4 mb-1">Personalisation hooks</h3>
                  <ul className="text-sm space-y-1 list-disc pl-5">
                    {p.personalization_hooks.map((h) => (
                      <li key={h}>{h}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
            <div className="card p-4">
              <KV k="Value-add" v={p.value_add} />
              <KV k="Decision speed" v={p.decision_speed} />
              <KV k="Investments per year" v={p.investments_per_year_estimate} />
              <KV k="Research notes" v={p.notes} />
              {p.sources.length > 0 && (
                <div className="pt-2">
                  <div className="text-xs text-muted mb-1">Sources</div>
                  {p.sources.map((s) => (
                    <a key={s} href={s} target="_blank" rel="noreferrer" className="block text-xs text-brand truncate">
                      {s}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        {tab === "Similar" && (
          <div className="space-y-2">
            {similar.isLoading && <ListSkeleton rows={3} />}
            {similar.data?.items.map((i) => (
              <InvestorRow key={i.id} inv={i} />
            ))}
            {similar.data?.items.length === 0 && <p className="text-sm text-muted">No similar investors found.</p>}
          </div>
        )}
      </div>

      {/* Mobile sticky actions */}
      <div className="md:hidden fixed bottom-[calc(56px_+_env(safe-area-inset-bottom))] inset-x-0 z-20 bg-card/95 backdrop-blur border-t border-line p-3 flex gap-2">
        {p.funnel_card_id ? (
          <Link href={`/app/funnel/${p.funnel_card_id}`} className="btn-ghost flex-1">
            <KanbanSquare size={16} /> In funnel
          </Link>
        ) : (
          <button className="btn-ghost flex-1" onClick={() => addToFunnel.mutate()} disabled={addToFunnel.isPending}>
            <KanbanSquare size={16} /> Add to funnel
          </button>
        )}
        <button className="btn-primary flex-1" onClick={() => draft.mutate()} disabled={draft.isPending || p.excluded}>
          {p.contacts_locked ? <Lock size={14} /> : <Sparkles size={16} />} Draft emails
        </button>
      </div>
    </div>
  );
}

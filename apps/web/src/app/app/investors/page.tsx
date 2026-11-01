"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, Building2, Heart, ChevronDown, ChevronLeft, ChevronRight, Lock, SlidersHorizontal, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { InvestorRow } from "@/components/InvestorRow";
import { Empty, ErrorState, ListSkeleton, Sheet } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { flag } from "@/lib/countries";
import type { InvestorCard } from "@/lib/types";

type Result = { total: number; all_total?: number; page: number; page_size: number; items: InvestorCard[]; searches_used: number; searches_limit: number | null; contacts_locked: boolean };
type Opt = { value: string; label?: string; count: number };
type Facets = { sectors: Opt[]; investor_types: Opt[]; stages: Opt[]; countries: Opt[] };
type Parsed = Partial<Filters> & { summary?: string; engine?: string };

const TOGGLES: [keyof Filters, string][] = [
  ["active", "Recent deal"],
  ["leads", "Leads rounds"],
  ["decision_maker", "Decision-makers"],
  ["seed_fit", "Early-stage"],
  ["has_email", "Has email"],
  ["enriched", "Researched"],
  ["not_in_funnel", "Not in tracker"],
];
const CHEQUES: { label: string; min?: number; max?: number }[] = [
  { label: "Any size" },
  { label: "Up to $100K", max: 100_000 },
  { label: "$100K – $500K", min: 100_000, max: 500_000 },
  { label: "$500K – $2M", min: 500_000, max: 2_000_000 },
  { label: "$2M+", min: 2_000_000 },
];
const EXAMPLES = ["Angels actively investing in healthcare", "Seed VCs in the UK writing $500K cheques", "Pre-seed fintech investors in Europe that lead"];

type Filters = {
  q: string; sector: string[]; stage: string; geo: string; country: string; investor_type: string[];
  check_min: number | null; check_max: number | null;
  seed_fit: boolean; decision_maker: boolean; active: boolean; leads: boolean; has_email: boolean; enriched: boolean; not_in_funnel: boolean;
};
const EMPTY: Filters = { q: "", sector: [], stage: "", geo: "", country: "", investor_type: [], check_min: null, check_max: null, seed_fit: false, decision_maker: false, active: false, leads: false, has_email: false, enriched: false, not_in_funnel: false };
const num = (v: string | null) => (v ? Number(v) : null);
const usd = (n: number) => (n >= 1_000_000 ? `$${+(n / 1_000_000).toFixed(1)}M` : `$${Math.round(n / 1000)}K`);

function fromParams(p: URLSearchParams): Filters {
  const f: Filters = { ...EMPTY, q: p.get("q") ?? "", stage: p.get("stage") ?? "", geo: p.get("geo") ?? "", country: p.get("country") ?? "", sector: p.getAll("sector"), investor_type: p.getAll("investor_type"), check_min: num(p.get("check_min")), check_max: num(p.get("check_max")) };
  for (const [k] of TOGGLES) (f as any)[k] = p.get(k) === "true";
  return f;
}

function Section({ title, count, open = true, children }: { title: string; count?: number; open?: boolean; children: React.ReactNode }) {
  return (
    <details open={open} className="group border-b border-line last:border-0 py-3">
      <summary className="flex items-center justify-between cursor-pointer list-none text-sm font-medium select-none">
        <span>
          {title}
          {count ? <span className="ml-1.5 rounded-full bg-brand text-white text-[10px] px-1.5 py-0.5">{count}</span> : null}
        </span>
        <ChevronDown size={16} className="text-muted transition-transform group-open:rotate-180" />
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  );
}

const pill = (on: boolean) => clsx("chip px-2.5 py-1 text-[13px] transition-colors", on ? "bg-brand text-white border-brand" : "hover:border-brand/50");

function SearchInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [f, setF] = useState<Filters>(() => fromParams(params));
  const [ask, setAsk] = useState(params.get("ask") ?? f.q);
  const [summary, setSummary] = useState("");
  const [open, setOpen] = useState(false);
  const [allSectors, setAllSectors] = useState(false);
  const [tab, setTab] = useState<"recommended" | "search">(params.toString() ? "search" : "recommended");

  useEffect(() => {
    if (tab === "search") router.replace(`/app/investors${qs(f)}`, { scroll: false });
  }, [f, tab, router]);

  const facets = useQuery<Facets>({ queryKey: ["facets"], queryFn: () => api("/investors/facets"), staleTime: 600_000 });
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [f, tab]);
  const res = useQuery<Result>({
    queryKey: ["investors", f, page],
    queryFn: () => api(`/investors${qs({ ...f, page })}`),
    placeholderData: keepPreviousData,
    enabled: tab === "search",
    retry: false,
  });
  const rec = useQuery<{ items: InvestorCard[]; needs_profile: boolean }>({
    queryKey: ["recommended"],
    queryFn: () => api("/investors/recommended"),
    enabled: tab === "recommended",
  });
  const shortlist = useQuery<{ items: InvestorCard[] }>({ queryKey: ["shortlist"], queryFn: () => api("/shortlist") });

  const set = (patch: Partial<Filters>) => {
    setF((x) => ({ ...x, ...patch }));
    setTab("search");
  };
  const reset = () => {
    setF(EMPTY);
    setSummary("");
    setAsk("");
  };
  const aiSearch = useMutation({
    mutationFn: (q: string) => api<Parsed>("/investors/ai-search", { method: "POST", json: { q } }),
    onSuccess: (p) => {
      setF({ ...EMPTY, ...Object.fromEntries(Object.entries(p).filter(([k]) => k in EMPTY)) } as Filters);
      setSummary(p.summary || "");
      setTab("search");
    },
  });

  const first = res.data;
  const recAll = rec.data?.items ?? [];
  const items = tab === "search" ? first?.items ?? [] : recAll.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const pageCount = tab === "search" ? (first ? Math.ceil(first.total / first.page_size) : 0) : Math.ceil(recAll.length / PER_PAGE);
  const go = (n: number) => {
    setPage(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const loading = tab === "search" ? res.isLoading : rec.isLoading;
  const error = tab === "search" ? res.error : rec.error;
  const chequeIdx = CHEQUES.findIndex((c) => (c.min ?? null) === f.check_min && (c.max ?? null) === f.check_max);
  const activeCount = f.sector.length + f.investor_type.length + (f.stage ? 1 : 0) + (f.country || f.geo ? 1 : 0) + (f.check_min || f.check_max ? 1 : 0) + TOGGLES.filter(([k]) => f[k]).length;
  const sectors = facets.data?.sectors ?? [];

  const filterPanel = (
    <div>
      <Section title="Stage" count={f.stage ? 1 : 0}>
        <div className="flex flex-wrap gap-1.5">
          {(facets.data?.stages ?? []).map((s) => (
            <button key={s.value} onClick={() => set({ stage: f.stage === s.value ? "" : s.value })} className={pill(f.stage === s.value)}>
              {s.label}
            </button>
          ))}
        </div>
      </Section>
      <Section title="Investor type" count={f.investor_type.length}>
        <div className="flex flex-wrap gap-1.5">
          {(facets.data?.investor_types ?? []).map((t) => {
            const on = f.investor_type.includes(t.value);
            return (
              <button key={t.value} onClick={() => set({ investor_type: on ? f.investor_type.filter((x) => x !== t.value) : [...f.investor_type, t.value] })} className={pill(on)}>
                {t.label}
              </button>
            );
          })}
        </div>
      </Section>
      <Section title="Location and cheque" count={(f.country || f.geo ? 1 : 0) + (f.check_min || f.check_max ? 1 : 0)}>
        <div className="space-y-2">
          <select className="input h-9" aria-label="Country" value={f.country} onChange={(e) => set({ country: e.target.value, geo: "" })}>
            <option value="">Any country</option>
            {(facets.data?.countries ?? []).map((c) => (
              <option key={c.value} value={c.value}>
                {flag(c.value)} {c.value} ({c.count.toLocaleString()})
              </option>
            ))}
          </select>
          <select
            className="input h-9"
            aria-label="Cheque size"
            value={chequeIdx < 0 ? "custom" : String(chequeIdx)}
            onChange={(e) => {
              const c = CHEQUES[Number(e.target.value)];
              if (c) set({ check_min: c.min ?? null, check_max: c.max ?? null });
            }}
          >
            {chequeIdx < 0 && <option value="custom">{`${f.check_min ? usd(f.check_min) : "$0"} – ${f.check_max ? usd(f.check_max) : "any"}`}</option>}
            {CHEQUES.map((c, i) => (
              <option key={c.label} value={i}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      </Section>
      <Section title="Sectors" count={f.sector.length} open={f.sector.length > 0}>
        <div className="flex flex-wrap gap-1.5">
          {(allSectors ? sectors : sectors.slice(0, 10)).map((s) => {
            const on = f.sector.includes(s.value);
            return (
              <button key={s.value} onClick={() => set({ sector: on ? f.sector.filter((x) => x !== s.value) : [...f.sector, s.value] })} className={pill(on)}>
                {s.value}
              </button>
            );
          })}
        </div>
        {sectors.length > 10 && (
          <button className="mt-2 text-xs text-brand" onClick={() => setAllSectors((v) => !v)}>
            {allSectors ? "Show fewer" : `Show all ${sectors.length} sectors`}
          </button>
        )}
      </Section>
      <Section title="More" count={TOGGLES.filter(([k]) => f[k]).length} open={TOGGLES.some(([k]) => f[k])}>
        <div className="flex flex-wrap gap-1.5">
          {TOGGLES.map(([k, label]) => (
            <button key={k} onClick={() => set({ [k]: !f[k] } as Partial<Filters>)} className={pill(f[k] as boolean)}>
              {label}
            </button>
          ))}
        </div>
      </Section>
      {activeCount > 0 && (
        <button className="btn-ghost w-full mt-3" onClick={reset}>
          Clear all filters
        </button>
      )}
    </div>
  );

  return (
    <>
      <PageHeader
        title="Investors"
        sub={
          first?.searches_limit && tab === "search" ? (
            <span>
              {first.searches_used} of {first.searches_limit} searches used{first.searches_limit <= 10 ? " in your trial" : " this month"}
            </span>
          ) : (
            "Find the investors that fit your raise."
          )
        }
      />

      {/* Ask in plain language */}
      <form
        className="relative rounded-2xl border border-brand/30 bg-card shadow-[0_8px_30px_-12px_rgba(15,98,254,0.35)] focus-within:border-brand"
        onSubmit={(e) => {
          e.preventDefault();
          if (ask.trim().length > 1) aiSearch.mutate(ask.trim());
        }}
      >
        <Sparkles size={20} className="absolute left-4 top-4 text-brand" />
        <textarea
          rows={1}
          className="w-full resize-none bg-transparent pl-12 pr-32 py-3.5 text-[15px] outline-none placeholder:text-muted min-h-[52px] max-h-40"
          placeholder="Ask your agent: angels actively investing in healthcare, $500K cheques"
          value={ask}
          onChange={(e) => {
            setAsk(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          aria-label="Describe the investors you want"
        />
        <button className="btn-primary absolute right-2 top-2 h-9" disabled={aiSearch.isPending || ask.trim().length < 2}>
          {aiSearch.isPending ? "Thinking…" : "Search"} <ArrowRight size={15} />
        </button>
      </form>
      <div className="mt-2 mb-4 flex items-center gap-2 overflow-x-auto scrollbar-none text-xs">
        {summary ? (
          <>
            <span className="text-muted whitespace-nowrap">Showing</span>
            <span className="chip px-2.5 py-1 bg-brand/10 text-brand border-brand/30 whitespace-nowrap">
              <Sparkles size={12} /> {summary}
            </span>
            <button className="text-muted hover:text-ink whitespace-nowrap flex items-center gap-1" onClick={reset}>
              <X size={12} /> Clear
            </button>
          </>
        ) : (
          <>
            <span className="text-muted whitespace-nowrap">Try</span>
            {EXAMPLES.map((x) => (
              <button
                key={x}
                type="button"
                className="chip px-2.5 py-1 whitespace-nowrap hover:border-brand/50"
                onClick={() => {
                  setAsk(x);
                  aiSearch.mutate(x);
                }}
              >
                {x}
              </button>
            ))}
          </>
        )}
      </div>

      <div className="flex gap-2 mb-4 overflow-x-auto scrollbar-none">
        <button onClick={() => setTab("recommended")} className={clsx("chip px-3 py-1.5 text-sm whitespace-nowrap", tab === "recommended" && "bg-ink text-surface border-ink")}>
          Best match for you
        </button>
        <button onClick={() => setTab("search")} className={clsx("chip px-3 py-1.5 text-sm whitespace-nowrap", tab === "search" && "bg-ink text-surface border-ink")}>
          All investors{first && tab === "search" ? ` · ${first.total.toLocaleString()}` : ""}
        </button>
        <Link href="/app/shortlist" className="chip px-3 py-1.5 text-sm whitespace-nowrap">
          <Heart size={14} className="text-rose-500" /> Shortlist{shortlist.data?.items.length ? ` · ${shortlist.data.items.length}` : ""}
        </Link>
        <Link href="/app/investors/lookup" className="chip px-3 py-1.5 text-sm whitespace-nowrap">
          <Building2 size={14} /> Who invested in…
        </Link>
        <button type="button" className="chip px-3 py-1.5 text-sm whitespace-nowrap lg:hidden ml-auto" onClick={() => setOpen(true)}>
          <SlidersHorizontal size={14} /> Filters{activeCount ? ` · ${activeCount}` : ""}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_290px] gap-6">
        <div className="space-y-2 min-w-0">
          {tab === "search" && first?.contacts_locked && (
            <div className="card p-3 text-sm flex items-center gap-2 bg-amber-500/5 border-amber-500/30">
              <Lock size={16} className="text-warn shrink-0" /> Emails and LinkedIn unlock on Starter and above.
              <Link href="/app/settings#plan" className="ml-auto text-brand font-medium whitespace-nowrap">
                See plans
              </Link>
            </div>
          )}
          {loading && <ListSkeleton />}
          {error && <ErrorState error={error} retry={() => (tab === "search" ? res.refetch() : rec.refetch())} />}
          {tab === "recommended" && rec.data?.needs_profile && (
            <Empty title="Tell us about your company" body="Answer a few questions or upload your deck and we'll rank investors by how well they match, with the reasons." action={<Link className="btn-primary" href="/onboarding">Set up my company</Link>} />
          )}
          {!loading && !error && items.length === 0 && !(tab === "recommended" && rec.data?.needs_profile) && (
            <Empty title="No investors match" body="Try fewer filters or describe what you need in the box above." action={<button className="btn-ghost" onClick={reset}>Clear filters</button>} />
          )}
          {items.map((inv) => (
            <InvestorRow key={inv.id} inv={inv} />
          ))}
          {pageCount > 1 && <Pager page={page} count={pageCount} onGo={go} />}
          {tab === "search" && first && first.all_total !== undefined && first.all_total > first.total && page === pageCount && (
            <p className="pt-2 text-center text-sm text-muted">
              Showing the top {first.total} of {first.all_total.toLocaleString()} matches.{" "}
              <Link href="/app/settings#plan" className="text-brand font-medium">
                Upgrade to see every investor
              </Link>
            </p>
          )}
        </div>
        <aside className="hidden lg:block">
          <div className="card px-4 py-1 sticky top-6 max-h-[calc(100dvh-3rem)] overflow-y-auto">
            <div className="flex items-center justify-between gap-2 pt-3 pb-2 border-b border-line">
              <h2 className="flex items-center gap-2 font-semibold">
                <SlidersHorizontal size={17} className="text-brand" /> Filters
                {activeCount > 0 && <span className="rounded-full bg-brand/10 text-brand text-xs px-2 py-0.5">{activeCount}</span>}
              </h2>
              {activeCount > 0 && (
                <button className="text-xs text-muted hover:text-brand" onClick={reset}>
                  Clear all
                </button>
              )}
            </div>
            {filterPanel}
          </div>
        </aside>
      </div>
      <Sheet open={open} onClose={() => setOpen(false)} title="Filters">
        {filterPanel}
        <button className="btn-primary w-full mt-4" onClick={() => setOpen(false)}>
          Show {first?.total?.toLocaleString() ?? ""} investors
        </button>
      </Sheet>
    </>
  );
}

const PER_PAGE = 10;

/** Numbered pages: 1 … 4 5 6 … 20, with previous / next. */
function Pager({ page, count, onGo }: { page: number; count: number; onGo: (n: number) => void }) {
  const nums: (number | "…")[] = [];
  for (let n = 1; n <= count; n++) {
    if (n === 1 || n === count || Math.abs(n - page) <= 1) nums.push(n);
    else if (nums[nums.length - 1] !== "…") nums.push("…");
  }
  return (
    <nav className="flex items-center justify-center gap-1 pt-4" aria-label="Pages">
      <button className="btn-ghost btn-sm" disabled={page <= 1} onClick={() => onGo(page - 1)} aria-label="Previous page">
        <ChevronLeft size={15} /> <span className="hidden sm:inline">Previous</span>
      </button>
      {nums.map((n, i) =>
        n === "…" ? (
          <span key={`gap${i}`} className="px-1.5 text-muted">…</span>
        ) : (
          <button
            key={n}
            onClick={() => onGo(n)}
            aria-current={n === page ? "page" : undefined}
            className={clsx("h-8 min-w-8 rounded-lg px-2 text-sm font-semibold", n === page ? "bg-brand text-white" : "text-ink hover:bg-card hover:shadow-sm")}
          >
            {n}
          </button>
        ),
      )}
      <button className="btn-ghost btn-sm" disabled={page >= count} onClick={() => onGo(page + 1)} aria-label="Next page">
        <span className="hidden sm:inline">Next</span> <ChevronRight size={15} />
      </button>
    </nav>
  );
}

export default function InvestorsPage() {
  return (
    <Suspense fallback={<ListSkeleton />}>
      <SearchInner />
    </Suspense>
  );
}

"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, ChevronLeft, ChevronRight, Lock, Search, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { InvestorRow } from "@/components/InvestorRow";
import { Empty, ErrorState, ListSkeleton, Sheet } from "@/components/ui";
import { api, qs } from "@/lib/api";
import type { InvestorCard } from "@/lib/types";

type Result = { total: number; page: number; page_size: number; items: InvestorCard[]; searches_used: number; searches_limit: number | null; contacts_locked: boolean };
type Facets = { sectors: { value: string; count: number }[]; investor_types: { value: string; label: string }[]; stages: string[] };

const TOGGLES: [keyof Filters, string][] = [
  ["seed_fit", "Early-stage check-writers"],
  ["decision_maker", "Decision-makers only"],
  ["active", "Verified recent deal"],
  ["leads", "Leads rounds"],
  ["has_email", "Has email"],
  ["enriched", "Researched profiles"],
  ["not_in_funnel", "Not in my funnel"],
];

type Filters = {
  q: string; sector: string[]; stage: string; geo: string; investor_type: string[];
  seed_fit: boolean; decision_maker: boolean; active: boolean; leads: boolean; has_email: boolean; enriched: boolean; not_in_funnel: boolean;
};
const EMPTY: Filters = { q: "", sector: [], stage: "", geo: "", investor_type: [], seed_fit: false, decision_maker: false, active: false, leads: false, has_email: false, enriched: false, not_in_funnel: false };

function fromParams(p: URLSearchParams): Filters {
  const f = { ...EMPTY, q: p.get("q") ?? "", stage: p.get("stage") ?? "", geo: p.get("geo") ?? "", sector: p.getAll("sector"), investor_type: p.getAll("investor_type") };
  for (const [k] of TOGGLES) (f as any)[k] = p.get(k) === "true";
  return f;
}

function SearchInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [f, setF] = useState<Filters>(() => fromParams(params));
  const [q, setQ] = useState(f.q);
  const [page, setPage] = useState(Number(params.get("page") ?? 1));
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"recommended" | "search">(params.toString() ? "search" : "recommended");

  useEffect(() => {
    if (tab === "search") router.replace(`/app/investors${qs({ ...f, page: page > 1 ? page : undefined })}`, { scroll: false });
  }, [f, page, tab, router]);

  const facets = useQuery<Facets>({ queryKey: ["facets"], queryFn: () => api("/investors/facets"), staleTime: 600_000 });
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

  const set = (patch: Partial<Filters>) => {
    setF((x) => ({ ...x, ...patch }));
    setPage(1);
    setTab("search");
  };
  const activeCount = f.sector.length + f.investor_type.length + (f.stage ? 1 : 0) + (f.geo ? 1 : 0) + TOGGLES.filter(([k]) => f[k]).length;

  const filterPanel = (
    <div className="space-y-5">
      <div>
        <div className="label">Stage</div>
        <div className="flex flex-wrap gap-2">
          {(facets.data?.stages ?? []).map((s) => (
            <button key={s} onClick={() => set({ stage: f.stage === s ? "" : s })} className={clsx("chip px-3 py-1.5 text-sm", f.stage === s && "bg-brand text-white border-brand")}>
              {s}
            </button>
          ))}
        </div>
      </div>
      <div>
        <div className="label">Investor type</div>
        <div className="flex flex-wrap gap-2">
          {(facets.data?.investor_types ?? []).map((t) => {
            const on = f.investor_type.includes(t.value);
            return (
              <button key={t.value} onClick={() => set({ investor_type: on ? f.investor_type.filter((x) => x !== t.value) : [...f.investor_type, t.value] })} className={clsx("chip px-3 py-1.5 text-sm", on && "bg-brand text-white border-brand")}>
                {t.label}
              </button>
            );
          })}
        </div>
      </div>
      <label className="block">
        <span className="label">Geography</span>
        <input className="input" placeholder="e.g. United Kingdom, Berlin, Europe" value={f.geo} onChange={(e) => set({ geo: e.target.value })} />
      </label>
      <div className="space-y-2">
        {TOGGLES.map(([k, label]) => (
          <label key={k} className="flex items-center justify-between gap-3 text-sm">
            {label}
            <input type="checkbox" className="w-5 h-5 accent-[var(--brand)]" checked={f[k] as boolean} onChange={(e) => set({ [k]: e.target.checked } as Partial<Filters>)} />
          </label>
        ))}
      </div>
      <div>
        <div className="label">Sectors</div>
        <div className="flex flex-wrap gap-2 max-h-64 overflow-y-auto">
          {(facets.data?.sectors ?? []).map((s) => {
            const on = f.sector.includes(s.value);
            return (
              <button key={s.value} onClick={() => set({ sector: on ? f.sector.filter((x) => x !== s.value) : [...f.sector, s.value] })} className={clsx("chip px-2.5 py-1 text-xs", on && "bg-brand text-white border-brand")}>
                {s.value} <span className="opacity-60">{s.count}</span>
              </button>
            );
          })}
        </div>
      </div>
      {activeCount > 0 && (
        <button className="btn-ghost w-full" onClick={() => set(EMPTY)}>
          Clear filters
        </button>
      )}
    </div>
  );

  const data = tab === "search" ? res : rec;
  const items = (tab === "search" ? res.data?.items : rec.data?.items) ?? [];

  return (
    <>
      <PageHeader
        title="Investors"
        sub={
          res.data?.searches_limit && tab === "search" ? (
            <span>
              {res.data.searches_used} of {res.data.searches_limit} searches used{res.data.searches_limit <= 3 ? " in your trial" : " this month"}
            </span>
          ) : (
            "Find the investors that fit your raise."
          )
        }
      />
      <form
        className="flex gap-2 mb-3"
        onSubmit={(e) => {
          e.preventDefault();
          set({ q });
        }}
      >
        <div className="relative flex-1">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input className="input pl-10 h-11" placeholder="Name, firm, thesis… e.g. clinical AI Europe" value={q} onChange={(e) => setQ(e.target.value)} enterKeyHint="search" />
        </div>
        <button type="button" className="btn-ghost h-11 lg:hidden relative" onClick={() => setOpen(true)} aria-label="Filters">
          <SlidersHorizontal size={18} />
          {activeCount > 0 && <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-brand text-white text-[11px] grid place-items-center">{activeCount}</span>}
        </button>
      </form>
      <div className="flex gap-2 mb-4 overflow-x-auto scrollbar-none">
        <button onClick={() => setTab("recommended")} className={clsx("chip px-3 py-1.5 text-sm whitespace-nowrap", tab === "recommended" && "bg-ink text-surface border-ink")}>
          Best fit for you
        </button>
        <button onClick={() => setTab("search")} className={clsx("chip px-3 py-1.5 text-sm whitespace-nowrap", tab === "search" && "bg-ink text-surface border-ink")}>
          All investors{res.data && tab === "search" ? ` · ${res.data.total.toLocaleString()}` : ""}
        </button>
        <Link href="/app/investors/lookup" className="chip px-3 py-1.5 text-sm whitespace-nowrap">
          <Building2 size={14} /> Who invested in…
        </Link>
        {f.sector.map((s) => (
          <button key={s} className="chip px-3 py-1.5 text-sm whitespace-nowrap bg-brand/10 text-brand border-brand/30" onClick={() => set({ sector: f.sector.filter((x) => x !== s) })}>
            {s} <X size={12} />
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6">
        <div className="space-y-2 min-w-0">
          {(tab === "search" ? res.data?.contacts_locked : false) && (
            <div className="card p-3 text-sm flex items-center gap-2 bg-amber-500/5 border-amber-500/30">
              <Lock size={16} className="text-warn shrink-0" /> Emails and LinkedIn unlock on Starter and above.
              <Link href="/app/settings#plan" className="ml-auto text-brand whitespace-nowrap">
                See plans
              </Link>
            </div>
          )}
          {data.isLoading && <ListSkeleton />}
          {data.error && <ErrorState error={data.error} retry={() => data.refetch()} />}
          {tab === "recommended" && rec.data?.needs_profile && (
            <Empty title="Tell us about your company" body="Add your sectors and stage (or upload your deck) and we'll rank investors by fit, with the reasons." action={<Link className="btn-primary" href="/app/settings#company">Set up company profile</Link>} />
          )}
          {!data.isLoading && !data.error && items.length === 0 && !(tab === "recommended" && rec.data?.needs_profile) && (
            <Empty title="No investors match" body="Try fewer filters or a broader search." action={<button className="btn-ghost" onClick={() => set(EMPTY)}>Clear filters</button>} />
          )}
          {items.map((inv) => (
            <InvestorRow key={inv.id} inv={inv} />
          ))}
          {tab === "search" && res.data && res.data.total > res.data.page_size && (
            <div className="flex items-center justify-between pt-2">
              <button className="btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft size={14} /> Prev
              </button>
              <span className="text-xs text-muted">
                Page {page} of {Math.ceil(res.data.total / res.data.page_size)}
              </span>
              <button className="btn-ghost btn-sm" disabled={page * res.data.page_size >= res.data.total} onClick={() => setPage((p) => p + 1)}>
                Next <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
        <aside className="hidden lg:block">
          <div className="card p-4 sticky top-6">{filterPanel}</div>
        </aside>
      </div>
      <Sheet open={open} onClose={() => setOpen(false)} title="Filters">
        {filterPanel}
        <button className="btn-primary w-full mt-4" onClick={() => setOpen(false)}>
          Show {res.data?.total?.toLocaleString() ?? ""} investors
        </button>
      </Sheet>
    </>
  );
}

export default function InvestorsPage() {
  return (
    <Suspense fallback={<ListSkeleton />}>
      <SearchInner />
    </Suspense>
  );
}

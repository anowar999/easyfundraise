"use client";

import clsx from "clsx";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { FilterPills, NoMatches, OpenLink, ResourceSearch, ResourceTabs, SourceNote, fmtUsd, matches } from "@/components/Resources";
import { DECK_STAGES, PITCH_DECKS, type DeckStage, type PitchDeck } from "@/lib/resources/pitchDecks";

type StageFilter = DeckStage | "all";
type Sort = "amount" | "year" | "name";

const STAGE_LABEL = Object.fromEntries(DECK_STAGES.map((s) => [s.key, s.label])) as Record<DeckStage, string>;
const STAGE_TONE: Record<DeckStage, string> = {
  "pre-seed": "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-300",
  seed: "bg-green-500/10 text-green-700 border-green-600/30 dark:text-green-300",
  "series-a": "bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-300",
};

function median(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** How much each stage raised: range and median across the decks we list */
function StageSummary({ stage, active, onPick }: { stage: (typeof DECK_STAGES)[number]; active: boolean; onPick: () => void }) {
  const amounts = PITCH_DECKS.filter((d) => d.stage === stage.key).map((d) => d.usd);
  return (
    <button onClick={onPick} className={clsx("card p-4 text-left transition hover:border-brand/40", active && "border-brand ring-4 ring-brand/10")}>
      <div className="flex items-center justify-between gap-2">
        <span className={clsx("chip", STAGE_TONE[stage.key])}>{stage.label}</span>
        <span className="text-xs text-muted">{amounts.length} decks</span>
      </div>
      <div className="mt-3 text-2xl font-bold tracking-tight text-ink tabular-nums">{fmtUsd(median(amounts))}</div>
      <div className="text-xs text-muted">median raise · range {fmtUsd(Math.min(...amounts))} to {fmtUsd(Math.max(...amounts))}</div>
      <p className="hidden sm:block text-[13px] text-muted mt-2 leading-relaxed">{stage.blurb}</p>
    </button>
  );
}

function DeckCard({ d }: { d: PitchDeck }) {
  return (
    <article className="card p-4 flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-ink truncate">{d.company}</h3>
          <div className="text-xs text-muted mt-0.5">{d.sector} · {d.year}</div>
        </div>
        <span className={clsx("chip shrink-0", STAGE_TONE[d.stage])}>{STAGE_LABEL[d.stage]}</span>
      </div>
      <div className="mt-3">
        <span className="text-[22px] font-bold tracking-tight text-ink tabular-nums">{d.amount}</span>
        <span className="text-xs text-muted ml-1.5">raised</span>
      </div>
      <p className="text-sm text-muted mt-1.5 flex-1">{d.what}</p>
      <div className="flex items-center justify-between gap-2 mt-3 pt-3 border-t border-line">
        <OpenLink href={d.url}>View deck</OpenLink>
        <span className="text-[11px] text-muted truncate">{d.source}</span>
      </div>
    </article>
  );
}

export default function PitchDecksPage() {
  const [stage, setStage] = useState<StageFilter>("all");
  const [sector, setSector] = useState("all");
  const [sort, setSort] = useState<Sort>("amount");
  const [q, setQ] = useState("");

  const sectors = useMemo(() => [...new Set(PITCH_DECKS.map((d) => d.sector))].sort(), []);
  const searched = PITCH_DECKS.filter((d) => (sector === "all" || d.sector === sector) && matches(q, d.company, d.sector, d.what, d.amount, d.year));
  const shown = searched
    .filter((d) => stage === "all" || d.stage === stage)
    .sort((a, b) => (sort === "amount" ? b.usd - a.usd : sort === "year" ? b.year - a.year : a.company.localeCompare(b.company)));
  const clear = () => { setStage("all"); setSector("all"); setQ(""); };

  return (
    <>
      <PageHeader title="Pitch decks" sub="Real decks from startups that raised, grouped by stage, with how much each one raised." />
      <ResourceTabs />

      <div className="grid gap-3 sm:grid-cols-3 mb-5">
        {DECK_STAGES.map((s) => (
          <StageSummary key={s.key} stage={s} active={stage === s.key} onPick={() => setStage(stage === s.key ? "all" : s.key)} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <ResourceSearch value={q} onChange={setQ} placeholder="Search company, sector or idea" />
        <select className="input w-auto" value={sector} onChange={(e) => setSector(e.target.value)} aria-label="Sector">
          <option value="all">All sectors</option>
          {sectors.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select className="input w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
          <option value="amount">Largest raise</option>
          <option value="year">Newest</option>
          <option value="name">A to Z</option>
        </select>
      </div>
      <div className="mb-4">
        <FilterPills<StageFilter>
          value={stage}
          onChange={setStage}
          options={[
            { key: "all", label: "All stages", count: searched.length },
            ...DECK_STAGES.map((s) => ({ key: s.key, label: s.label, count: searched.filter((d) => d.stage === s.key).length })),
          ]}
        />
      </div>

      {shown.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((d) => <DeckCard key={d.company + d.stage} d={d} />)}
        </div>
      ) : (
        <NoMatches onClear={clear} />
      )}

      <SourceNote>
        Decks open where their founders or a publisher shared them (TechCrunch, SlideShare, Best Pitch Deck, Failory). Amounts and years are as
        those sources report them, and the median uses the decks listed here, not the whole market. Euro amounts are converted only for sorting.
      </SourceNote>
    </>
  );
}

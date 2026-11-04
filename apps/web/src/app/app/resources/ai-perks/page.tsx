"use client";

import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { FilterPills, NoMatches, OpenLink, ResourceSearch, ResourceTabs, SourceNote, matches } from "@/components/Resources";
import { PERKS, PERKS_CHECKED, PERK_KINDS, type PerkKind } from "@/lib/resources/aiPerks";

type KindFilter = PerkKind | "all";

export default function AiPerksPage() {
  const [kind, setKind] = useState<KindFilter>("all");
  const [q, setQ] = useState("");
  const searched = PERKS.filter((p) => matches(q, p.name, p.provider, p.value, p.who));
  const shown = searched.filter((p) => kind === "all" || p.kind === kind);
  const label = Object.fromEntries(PERK_KINDS.map((k) => [k.key, k.label])) as Record<PerkKind, string>;

  return (
    <>
      <PageHeader title="AI perks" sub="Free credits and discounts startups can claim, from AI models and GPUs to cloud and tools." />
      <ResourceTabs />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <ResourceSearch value={q} onChange={setQ} placeholder="Search a provider or perk" />
      </div>
      <div className="mb-4">
        <FilterPills<KindFilter>
          value={kind}
          onChange={setKind}
          options={[{ key: "all", label: "All", count: searched.length }, ...PERK_KINDS.map((k) => ({ key: k.key, label: k.label, count: searched.filter((p) => p.kind === k.key).length }))]}
        />
      </div>
      {shown.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((p) => (
            <article key={p.name} className="card p-4 flex flex-col">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-semibold text-ink">{p.name}</h3>
                  <div className="text-xs text-muted mt-0.5">{p.provider}</div>
                </div>
                <span className="chip shrink-0">{label[p.kind]}</span>
              </div>
              <div className="mt-3 text-[15px] font-semibold text-ink">{p.value}</div>
              <p className="text-sm text-muted mt-1.5 flex-1"><span className="font-medium text-ink/80">Who qualifies: </span>{p.who}</p>
              <div className="mt-3 pt-3 border-t border-line">
                <OpenLink href={p.url}>Apply</OpenLink>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <NoMatches onClear={() => { setKind("all"); setQ(""); }} />
      )}
      <SourceNote>
        Amounts and rules are what each program published as of {PERKS_CHECKED}. They change often, so check the official page before you apply.
        Many of the largest tiers need a referral from your investor or accelerator, so ask them for their partner codes.
      </SourceNote>
    </>
  );
}

"use client";

import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { FilterPills, NoMatches, OpenLink, ResourceSearch, ResourceTabs, SourceNote, matches } from "@/components/Resources";
import { PROGRAMS, PROGRAMS_CHECKED, type ProgramKind } from "@/lib/resources/programs";

function Term({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="flex gap-2 text-sm">
      <dt className="text-muted w-16 shrink-0">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}

/** Incubators and VCs & accelerators share one layout, filtered by kind and by model */
export function ProgramList({ kind, title, sub }: { kind: ProgramKind; title: string; sub: string }) {
  const [model, setModel] = useState("all");
  const [q, setQ] = useState("");
  const all = PROGRAMS.filter((p) => p.kind === kind);
  const searched = all.filter((p) => matches(q, p.name, p.model, p.where, p.note, p.invest));
  const shown = searched.filter((p) => model === "all" || p.model === model);
  const models = [...new Set(all.map((p) => p.model))];

  return (
    <>
      <PageHeader title={title} sub={sub} />
      <ResourceTabs />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <ResourceSearch value={q} onChange={setQ} placeholder="Search a program or city" />
      </div>
      <div className="mb-4">
        <FilterPills
          value={model}
          onChange={setModel}
          options={[{ key: "all", label: "All", count: searched.length }, ...models.map((m) => ({ key: m, label: m, count: searched.filter((p) => p.model === m).length }))]}
        />
      </div>
      {shown.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((p) => (
            <article key={p.name} className="card p-4 flex flex-col">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold text-ink min-w-0">{p.name}</h3>
                <span className="chip shrink-0">{p.model}</span>
              </div>
              <dl className="mt-3 space-y-1">
                <Term label="Invests" value={p.invest} />
                <Term label="Equity" value={p.equity} />
                <Term label="Where" value={p.where} />
              </dl>
              <p className="text-sm text-muted mt-2 flex-1">{p.note}</p>
              <div className="mt-3 pt-3 border-t border-line">
                <OpenLink href={p.url}>Visit site</OpenLink>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <NoMatches onClear={() => { setModel("all"); setQ(""); }} />
      )}
      <SourceNote>
        Terms are each program's published standard deal as of {PROGRAMS_CHECKED}. They change between cohorts and sometimes by country, so confirm on the
        program's site before you apply.
      </SourceNote>
    </>
  );
}

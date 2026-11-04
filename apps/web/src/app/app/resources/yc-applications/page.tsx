"use client";

import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { NoMatches, OpenLink, ResourceSearch, ResourceTabs, SourceNote, matches } from "@/components/Resources";
import { YC_APPS, YC_GUIDES } from "@/lib/resources/ycApplications";

export default function YcApplicationsPage() {
  const [q, setQ] = useState("");
  const shown = YC_APPS.filter((a) => matches(q, a.company, a.batch, a.sector, a.what, a.outcome)).sort((a, b) => b.year - a.year);

  return (
    <>
      <PageHeader title="YC applications" sub="Applications that got into Y Combinator, published by the founders who wrote them." />
      <ResourceTabs />
      <div className="grid gap-3 sm:grid-cols-2 mb-5">
        {YC_GUIDES.map((g) => (
          <div key={g.url} className="card p-4 bg-brand/[0.03] border-brand/25">
            <OpenLink href={g.url}>{g.title}</OpenLink>
            <p className="text-sm text-muted mt-1">{g.note}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <ResourceSearch value={q} onChange={setQ} placeholder="Search company, batch or sector" />
      </div>
      {shown.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((a) => (
            <article key={a.company} className="card p-4 flex flex-col">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-semibold text-ink">{a.company}</h3>
                  <div className="text-xs text-muted mt-0.5">{a.sector}</div>
                </div>
                <span className="chip shrink-0 bg-orange-500/10 text-orange-700 border-orange-500/30 dark:text-orange-300">YC {a.batch}</span>
              </div>
              <p className="text-sm text-muted mt-3 flex-1">{a.what}</p>
              {a.outcome && <div className="text-xs font-medium text-ink mt-2">{a.outcome}</div>}
              <div className="flex items-center justify-between gap-2 mt-3 pt-3 border-t border-line">
                <OpenLink href={a.url}>Read application</OpenLink>
                <span className="text-[11px] text-muted truncate">{a.source}</span>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <NoMatches onClear={() => setQ("")} />
      )}
      <SourceNote>
        Each application opens where it was published. YC's questions have changed over the years, so use these for how founders explain their idea,
        traction and team, not as a copy of today's form.
      </SourceNote>
    </>
  );
}

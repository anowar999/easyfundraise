"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { InvestorRow } from "@/components/InvestorRow";
import { Empty, ErrorState, ListSkeleton } from "@/components/ui";
import { api, qs } from "@/lib/api";
import type { InvestorCard } from "@/lib/types";

type Res = { company: string; investors: (InvestorCard & { evidence: { company: string; round?: string; date?: string; source_url?: string; source?: string } })[]; similar: InvestorCard[] };

export default function Lookup() {
  const [input, setInput] = useState("");
  const [name, setName] = useState("");
  const q = useQuery<Res>({ queryKey: ["lookup", name], queryFn: () => api(`/investors/lookup/company${qs({ name })}`), enabled: name.length >= 2 });
  return (
    <>
      <PageHeader title="Who invested in…" sub="Find investors behind a company, then others like them." />
      <form className="flex gap-2 mb-4" onSubmit={(e) => { e.preventDefault(); setName(input.trim()); }}>
        <input className="input h-11" placeholder="Company name or website" value={input} onChange={(e) => setInput(e.target.value)} />
        <button className="btn-primary h-11">Search</button>
      </form>
      {q.isLoading && <ListSkeleton />}
      {q.error && <ErrorState error={q.error} retry={() => q.refetch()} />}
      {q.data && q.data.investors.length === 0 && <Empty icon={<Building2 />} title={`No investors on file for ${q.data.company}`} body="We match against researched portfolios and recent deals." />}
      {q.data && q.data.investors.length > 0 && (
        <div className="space-y-6">
          <section className="space-y-2">
            <h2 className="font-semibold">{q.data.investors.length} investor{q.data.investors.length > 1 ? "s" : ""} in {q.data.company}</h2>
            {q.data.investors.map((i) => (
              <div key={i.id}>
                <InvestorRow inv={i} />
                <p className="text-xs text-muted px-4 py-1">
                  Evidence: {i.evidence.company}
                  {i.evidence.round && ` · ${i.evidence.round}`}
                  {i.evidence.date && ` · ${i.evidence.date}`}
                  {i.evidence.source_url && (
                    <a className="text-brand ml-1" href={i.evidence.source_url} target="_blank" rel="noreferrer">source</a>
                  )}
                </p>
              </div>
            ))}
          </section>
          {q.data.similar.length > 0 && (
            <section className="space-y-2">
              <h2 className="font-semibold">Similar investors ideal for you</h2>
              {q.data.similar.map((i) => <InvestorRow key={i.id} inv={i} />)}
            </section>
          )}
        </div>
      )}
    </>
  );
}

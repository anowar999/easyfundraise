"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ChevronRight, Flame, Snowflake, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { PageHeader, useMe } from "@/components/AppShell";
import { ErrorState, ListSkeleton } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";

type Brief = { id: string; name: string; firm: string; stage_label: string; next_contact_date: string | null; call_at: string | null; last_contacted_at: string | null; status: string };
type Home = {
  agent_name: string;
  stage_counts: { stage: number; label: string; count: number }[];
  total: number;
  committed: number;
  due: Brief[];
  going_cold: Brief[];
  calls: Brief[];
  actions: { title: string; link: string }[];
};

function Row({ b, right }: { b: Brief; right: string }) {
  return (
    <Link href={`/app/funnel/${b.id}`} className="flex items-center gap-3 py-3 border-b border-line last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{b.name}</div>
        <div className="text-xs text-muted truncate">
          {b.firm || "—"} · {b.stage_label}
        </div>
      </div>
      <span className="text-xs text-muted whitespace-nowrap">{right}</span>
      <ChevronRight size={16} className="text-muted" />
    </Link>
  );
}

export default function HomePage() {
  const me = useMe();
  const q = useQuery<Home>({ queryKey: ["home"], queryFn: () => api("/home") });
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <>
      <PageHeader title={`${greet}${me.data ? `, ${me.data.name.split(" ")[0]}` : ""}`} sub="Here's where your raise stands today." />
      {q.isLoading && <ListSkeleton rows={3} />}
      {q.error && <ErrorState error={q.error} retry={() => q.refetch()} />}
      {q.data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <section className="lg:col-span-2 space-y-4">
            <div className="card p-4 border-brand/30 bg-brand/[0.03]">
              <div className="flex items-center gap-2 text-sm font-medium text-brand">
                <Sparkles size={16} /> {q.data.agent_name} suggests
              </div>
              {q.data.actions.length === 0 ? (
                <p className="text-sm text-muted mt-2">You're on top of everything. Nice.</p>
              ) : (
                <div className="mt-2 flex flex-col gap-2">
                  {q.data.actions.map((a) => (
                    <Link key={a.title} href={a.link} className="flex items-center justify-between rounded-lg bg-card border border-line px-3 py-2.5 text-sm hover:border-brand">
                      {a.title}
                      <ChevronRight size={16} className="text-muted" />
                    </Link>
                  ))}
                </div>
              )}
            </div>

            <div className="card p-4">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold flex items-center gap-2">
                  <CalendarClock size={18} className="text-brand" /> Follow-ups due
                </h2>
                <Link href="/app/funnel?needs_action=1" className="text-xs text-brand">
                  See all
                </Link>
              </div>
              {q.data.due.length === 0 ? (
                <p className="text-sm text-muted py-3">Nothing due. Set next-contact dates on your funnel cards to get reminders.</p>
              ) : (
                q.data.due.map((b) => <Row key={b.id} b={b} right={fmtDate(b.next_contact_date)} />)
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="card p-4">
                <h2 className="font-semibold flex items-center gap-2">
                  <Flame size={18} className="text-orange-500" /> Calls this week
                </h2>
                {q.data.calls.length === 0 ? <p className="text-sm text-muted py-3">No calls booked.</p> : q.data.calls.map((b) => <Row key={b.id} b={b} right={fmtDate(b.call_at, { weekday: "short", hour: "2-digit", minute: "2-digit" })} />)}
              </div>
              <div className="card p-4">
                <h2 className="font-semibold flex items-center gap-2">
                  <Snowflake size={18} className="text-sky-500" /> Going cold
                </h2>
                {q.data.going_cold.length === 0 ? <p className="text-sm text-muted py-3">No one is going cold.</p> : q.data.going_cold.map((b) => <Row key={b.id} b={b} right={fmtDate(b.last_contacted_at)} />)}
              </div>
            </div>
          </section>

          <aside className="space-y-4">
            <div className="card p-4">
              <div className="flex items-baseline justify-between">
                <h2 className="font-semibold">Funnel</h2>
                <span className="text-sm text-muted">{q.data.total} investors</span>
              </div>
              <div className="mt-3 space-y-1.5">
                {q.data.stage_counts.map((s) => {
                  const max = Math.max(1, ...q.data.stage_counts.map((x) => x.count));
                  return (
                    <Link key={s.stage} href={`/app/funnel?stage=${s.stage}`} className="flex items-center gap-2 text-xs group">
                      <span className="w-36 truncate text-muted group-hover:text-ink">{s.label}</span>
                      <span className="flex-1 h-2 rounded-full bg-line overflow-hidden">
                        <span className="block h-full bg-brand rounded-full" style={{ width: `${(s.count / max) * 100}%` }} />
                      </span>
                      <span className="w-6 text-right font-mono">{s.count}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
            {q.data.total === 0 && (
              <Link href="/app/funnel/import" className="card p-4 flex items-center gap-3 hover:border-brand">
                <Upload className="text-brand" />
                <div>
                  <div className="font-medium text-sm">Import your tracker</div>
                  <div className="text-xs text-muted">Excel or CSV. We map the columns for you.</div>
                </div>
              </Link>
            )}
          </aside>
        </div>
      )}
    </>
  );
}

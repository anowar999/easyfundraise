"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ArrowUp, Bot, CalendarClock, CalendarDays, ChevronRight, FileText, Flame, Snowflake, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { askAgent } from "@/components/AgentChat";
import { PageHeader, useMe } from "@/components/AppShell";
import { TopTasks } from "@/components/FounderTasks";
import { CountryTag, InvestorActions } from "@/components/InvestorRow";
import { Avatar, ErrorState, FitScore, ListSkeleton } from "@/components/ui";
import type { InvestorCard } from "@/lib/types";
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
  profile_complete: boolean;
  data_room_pct: number;
  calendar_connected: boolean;
  meetings: { title: string; start: string; link?: string; tracker_card: { card_id: string; name: string; firm: string } | null }[];
};

const ASK_IDEAS = ["How many investors are in my outreach?", "Find 10 seed investors in my sector", "What's missing from my data room?"];

/** Your Raise Agent, front and centre: type anything and it does it across the site. */
function AgentBox({ name }: { name: string }) {
  const [text, setText] = useState("");
  const go = (t: string) => {
    if (!t.trim()) return;
    askAgent(t.trim());
    setText("");
  };
  return (
    <div className="card p-4 md:p-5 mb-4 border-brand/30 bg-gradient-to-br from-brand/[0.06] to-transparent">
      <div className="flex items-center gap-2 font-semibold">
        <span className="grid place-items-center w-8 h-8 rounded-full bg-brand text-white">
          <Bot size={17} />
        </span>
        {name}
      </div>
      <form
        className="mt-3 flex items-end gap-2 rounded-2xl border border-line bg-card px-3 py-2 focus-within:border-brand"
        onSubmit={(e) => {
          e.preventDefault();
          go(text);
        }}
      >
        <textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              go(text);
            }
          }}
          placeholder="Tell me how I can help you"
          aria-label={`Ask ${name}`}
          className="flex-1 resize-none bg-transparent py-1.5 text-[15px] focus-visible:outline-none"
        />
        <button type="submit" disabled={!text.trim()} aria-label="Send" className="grid place-items-center w-9 h-9 rounded-full bg-brand text-white disabled:opacity-40">
          <ArrowUp size={18} />
        </button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {ASK_IDEAS.map((t) => (
          <button key={t} type="button" onClick={() => go(t)} className="chip text-xs hover:border-brand hover:text-brand">
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Best matches for the company profile, as cards. Shown once the profile (or deck) is in. */
function Matches() {
  const q = useQuery<{ items: InvestorCard[]; needs_profile: boolean }>({ queryKey: ["recommended"], queryFn: () => api("/investors/recommended") });
  if (q.isLoading) return <ListSkeleton rows={2} />;
  const items = q.data?.items.slice(0, 6) ?? [];
  if (!items.length) return null;
  return (
    <div className="card p-4 md:p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-[17px]">Your best investor matches</h2>
        <Link href="/app/investors" className="text-sm font-medium text-brand inline-flex items-center gap-1">
          See all <ArrowRight size={14} />
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {items.map((i) => (
          <div key={i.id} className="rounded-2xl border border-line bg-card p-4 flex flex-col hover:border-brand/60 hover:shadow-md transition">
            <div className="flex items-start justify-between gap-2">
              <Avatar name={i.name} src={i.photo_url} logoDomain={i.firm_domain} size={44} />
              <InvestorActions inv={i} />
            </div>
            <Link href={`/app/investors/${i.id}`} className="mt-3 flex-1 min-w-0">
              <div className="font-semibold truncate">{i.name}</div>
              <div className="text-sm text-muted truncate">{i.firm || i.title}</div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <CountryTag country={i.country} location={i.location} />
                {i.fit && <FitScore score={i.fit.score} />}
              </div>
              {i.fit?.reasons?.[0] && <p className="mt-2 text-xs text-muted line-clamp-2">{i.fit.reasons[0]}</p>}
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}

function SetupCard() {
  return (
    <Link href="/onboarding" className="card p-5 md:p-6 flex flex-col sm:flex-row sm:items-center gap-4 bg-gradient-to-br from-brand/10 via-card to-card border-brand/30 hover:shadow-md transition">
      <span className="grid place-items-center w-12 h-12 rounded-2xl bg-brand text-white shrink-0">
        <Sparkles size={22} />
      </span>
      <div className="flex-1">
        <div className="font-semibold text-[17px]">See which investors match you</div>
        <p className="text-sm text-muted mt-0.5">Upload your deck or answer a few questions. We rank 14,000+ investors for you and personalise every email.</p>
      </div>
      <span className="btn-primary shrink-0">
        Set up my profile <ArrowRight size={16} />
      </span>
    </Link>
  );
}

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
      <AgentBox name={q.data?.agent_name && !["Raise", "Raise Agent"].includes(q.data.agent_name) ? q.data.agent_name : "Your Raise Agent"} />
      {q.data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <section className="lg:col-span-2 space-y-4">
            <TopTasks />
            {q.data.profile_complete ? <Matches /> : <SetupCard />}
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
                <p className="text-sm text-muted py-3">Nothing due. Set next-contact dates in your investor tracker to get reminders.</p>
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
            <Link href="/app/data-room" className="card p-4 flex items-center gap-3 hover:border-brand/60">
              <FileText className="text-brand shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm">Data room {q.data.data_room_pct}% complete</div>
                <div className="mt-1.5 h-1.5 rounded-full bg-surface overflow-hidden">
                  <div className={`h-full ${q.data.data_room_pct >= 80 ? "bg-emerald-500" : q.data.data_room_pct >= 50 ? "bg-brand" : "bg-amber-500"}`} style={{ width: `${q.data.data_room_pct}%` }} />
                </div>
              </div>
              <ChevronRight size={16} className="text-muted" />
            </Link>
            <div className="card p-4">
              <h2 className="font-semibold flex items-center gap-2">
                <CalendarDays size={18} className="text-brand" /> Investor meetings
              </h2>
              {!q.data.calendar_connected ? (
                <a href="/api/gmail/connect?calendar=1&next=/app" className="mt-2 block text-sm text-brand font-medium">
                  Connect Google Calendar to see them here →
                </a>
              ) : q.data.meetings.length === 0 ? (
                <p className="text-sm text-muted py-2">No investor meetings in the next 7 days.</p>
              ) : (
                q.data.meetings.map((m) => (
                  <Link key={m.title + m.start} href={m.tracker_card ? `/app/funnel/${m.tracker_card.card_id}` : "/app/funnel"} className="flex items-center gap-3 py-2.5 border-b border-line last:border-0">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{m.title}</div>
                      <div className="text-xs text-muted">{fmtDate(m.start, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
                    </div>
                    <ChevronRight size={16} className="text-muted" />
                  </Link>
                ))
              )}
            </div>
            <div className="card p-4">
              <div className="flex items-baseline justify-between">
                <h2 className="font-semibold">Investor tracker</h2>
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

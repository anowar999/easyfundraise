"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Activity, BookOpen, CalendarClock, ChevronRight, ListChecks, Mail, PenLine, Send } from "lucide-react";
import { from } from "@/components/Crumbs";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { PlaybookSheet, usePlaybook } from "@/components/EmailPlaybook";
import { ProgressUpdateCard } from "@/components/ProgressUpdate";
import { Empty, ErrorState, ListSkeleton } from "@/components/ui";
import { OutreachAgent } from "./OutreachAgent";
import { OutreachList } from "./OutreachList";
import { UpcomingList, useUpcoming } from "./Upcoming";
import { api, fmtDate } from "@/lib/api";

type Row = { key: string; sent: number; opened: number; replied: number; positive: number; bounced: number; open_rate: number; reply_rate: number };
type Recent = { id: string; to: string; card_id: string | null; subject: string; step: number; status: string; sent_at: string | null; scheduled_for: string | null; opened: number; reply: string; error: string };
type Stats = { total: Row; queued: number; tracking?: { enabled: boolean; public: boolean }; by_step: Row[]; by_hook: Row[]; by_persona: Row[]; by_hour: Row[]; recent: Recent[] };
type Gmail = { connected: boolean; email?: string; sent_today?: number; daily_cap?: number };

const pct = (x: number) => `${Math.round(x * 100)}%`;

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg bg-surface p-2.5">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-lg font-semibold leading-tight mt-0.5">{value}</div>
      {sub && <div className="text-[11px] text-muted truncate">{sub}</div>}
    </div>
  );
}

function Breakdown({ title, rows, label }: { title: string; rows: Row[]; label: (k: string) => string }) {
  if (!rows.length) return null;
  const best = Math.max(...rows.map((r) => r.reply_rate));
  return (
    <div className="card p-4">
      <h2 className="font-semibold mb-2 text-sm">{title}</h2>
      <table className="w-full text-sm">
        <thead className="text-xs text-muted text-left">
          <tr>
            <th className="font-normal py-1"></th>
            <th className="font-normal text-right">Sent</th>
            <th className="font-normal text-right">Opened</th>
            <th className="font-normal text-right">Replied</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-line">
              <td className="py-1.5 capitalize">{label(r.key)}</td>
              <td className="text-right font-mono">{r.sent}</td>
              <td className="text-right font-mono">{pct(r.open_rate)}</td>
              <td className={clsx("text-right font-mono", r.reply_rate === best && best > 0 && "text-green-600 font-semibold")}>{pct(r.reply_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STATUS: Record<string, string> = { sent: "Sent", scheduled: "Scheduled", failed: "Not sent" };

/** Email templates 1-3 at a glance, a button to review and change them, and the round & progress update. Opens on
 *  the first visit when they've never been set up (and on ?playbook=1). */
function PlaybookCard() {
  const q = usePlaybook();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const ask = new URLSearchParams(window.location.search);
    if (ask.get("playbook") || ask.get("setup")) setOpen(true);
  }, []);
  useEffect(() => {
    if (!q.data || q.data.saved_at) return;
    let seen = false;
    try {
      seen = localStorage.getItem("ef-playbook-intro") === "1";
      localStorage.setItem("ef-playbook-intro", "1");
    } catch {}
    if (!seen) setOpen(true);
  }, [q.data]);
  const pb = q.data;
  return (
    <div className="card p-3 md:p-4">
      <div className="flex items-center gap-2">
        <BookOpen size={16} className="text-brand shrink-0" />
        <span className="font-semibold text-sm flex-1">Email templates</span>
        <button className={pb?.saved_at ? "btn-ghost btn-sm" : "btn-primary btn-sm"} onClick={() => setOpen(true)}>
          <PenLine size={13} /> {pb?.saved_at ? "Edit" : "Set up"}
        </button>
      </div>
      {pb?.saved_at ? (
        <ol className="mt-2 space-y-1 text-sm">
          {pb.emails.map((e, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-muted shrink-0">Email {i + 1}</span>
              <span className="truncate">{e.focus}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-2 text-xs text-muted">Set what emails 1, 2 and 3 focus on. Your agent fills them from your data room.</p>
      )}
      <PlaybookSheet open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

type Tab = "list" | "scheduled" | "activity";
const TAB_NAME: Record<Tab, string> = { list: "Outreach list", scheduled: "Scheduled emails", activity: "Activity" };

export default function Outreach() {
  const [tab, setTab] = useState<Tab>("list");
  const up = useUpcoming();
  useEffect(() => {  // ?tab=scheduled / ?tab=activity (breadcrumbs lead back to a tab)
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t === "scheduled" || t === "activity") setTab(t);
  }, []);
  const s = useQuery<Stats>({ queryKey: ["outreach-stats"], queryFn: () => api("/outreach/stats") });
  const g = useQuery<Gmail>({ queryKey: ["gmail"], queryFn: () => api("/gmail") });
  const pb = usePlaybook();
  if (s.isLoading) return <ListSkeleton rows={4} />;
  if (s.error) return <ErrorState error={s.error} retry={() => s.refetch()} />;
  const d = s.data!;
  const nUp = up.data?.items.length ?? 0;
  const go = (t: Tab) => {
    setTab(t);
    try {
      const u = new URL(window.location.href);
      if (t === "list") u.searchParams.delete("tab");
      else u.searchParams.set("tab", t);
      window.history.replaceState(null, "", u.toString());
    } catch {}
  };
  const nav: { t: Tab; icon: ReactNode; count?: number }[] = [
    { t: "list", icon: <ListChecks size={16} /> },
    { t: "scheduled", icon: <CalendarClock size={16} />, count: nUp },
    { t: "activity", icon: <Activity size={16} /> },
  ];
  return (
    <>
      <PageHeader
        title="Outreach"
        sub={g.data?.connected ? `Sending from ${g.data.email} · ${g.data.sent_today} of ${g.data.daily_cap} today` : undefined}
        actions={
          !g.data?.connected && (
            <Link className="btn-primary" href="/app/settings#gmail">
              <Mail size={16} /> Connect Gmail
            </Link>
          )
        }
      />
      <div className="grid lg:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
        <div className="min-w-0 space-y-4">
          <OutreachAgent />
          {tab !== "list" && (
            <div className="flex items-center gap-1 text-sm">
              <button className="text-muted hover:text-brand" onClick={() => go("list")}>Outreach list</button>
              <ChevronRight size={14} className="text-muted" />
              <span className="font-medium">{TAB_NAME[tab]}</span>
            </div>
          )}
          {tab === "list" ? (
            <OutreachList />
          ) : tab === "scheduled" ? (
            <UpcomingList />
          ) : (
            <div className="space-y-4">
              <div className="card divide-y divide-line">
                {d.recent.length === 0 && <Empty icon={<Send />} title="No emails yet" body="Add investors to outreach and approve their emails. Sent and scheduled emails show up here." />}
                {d.recent.map((e) => {
                  const inner = (
                    <div className="p-3 flex gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">
                          {e.to} <span className="text-muted font-normal">· email {e.step}</span>
                        </div>
                        <div className="text-xs text-muted truncate">{e.subject}</div>
                        {e.error && e.status === "failed" && <div className="text-xs text-warn">{e.error}</div>}
                      </div>
                      <div className="text-right shrink-0 text-xs">
                        <div className={e.status === "failed" ? "text-warn" : "text-muted"}>{STATUS[e.status] ?? e.status}</div>
                        <div className="text-muted">{fmtDate(e.sent_at ?? e.scheduled_for, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
                        {e.reply ? <div className="text-green-600 font-medium">replied</div> : e.opened > 0 && <div>opened {e.opened}×</div>}
                      </div>
                    </div>
                  );
                  return e.card_id ? (
                    <Link key={e.id} href={from(`/app/funnel/${e.card_id}`, "outreach-activity")} className="block hover:bg-surface">
                      {inner}
                    </Link>
                  ) : (
                    <div key={e.id}>{inner}</div>
                  );
                })}
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <Breakdown title="By email in the sequence" rows={d.by_step} label={(k) => (k === "update" ? "Updates" : `Email ${k}`)} />
                <Breakdown title="By angle" rows={d.by_hook} label={(k) => (k.startsWith("playbook-") ? `Email ${k.slice(9)}: ${pb.data?.emails[Number(k.slice(9)) - 1]?.focus ?? ""}` : k.replace(/-/g, " "))} />
                <Breakdown title="By approach" rows={d.by_persona} label={(k) => k.replace(/-/g, " ")} />
              </div>
            </div>
          )}
        </div>
        <aside className="space-y-4 lg:sticky lg:top-4">
          <nav className="card p-1.5">
            {nav.map(({ t, icon, count }) => (
              <button
                key={t}
                onClick={() => go(t)}
                className={clsx("w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-sm text-left", tab === t ? "bg-surface font-medium text-brand" : "hover:bg-surface")}
              >
                {icon}
                <span className="flex-1">{TAB_NAME[t]}</span>
                {!!count && <span className="chip">{count}</span>}
              </button>
            ))}
          </nav>
          <div className="card p-3 md:p-4">
            <div className="text-sm font-semibold mb-2">Results <span className="text-xs text-muted font-normal">· last 90 days</span></div>
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Sent" value={d.total.sent} sub={`${d.queued} scheduled`} />
              <Stat label="Open rate" value={d.tracking && !d.tracking.public ? "n/a" : pct(d.total.open_rate)} sub={d.tracking && !d.tracking.public ? "needs a public address" : "a hint, not proof"} />
              <Stat label="Reply rate" value={pct(d.total.reply_rate)} sub={`${d.total.replied} replies`} />
              <Stat label="Interested" value={d.total.positive} sub={d.total.bounced ? `${d.total.bounced} bounced` : "positive replies"} />
            </div>
            {d.tracking && !d.tracking.public && (
              <p className="mt-2 text-[11px] text-muted leading-snug">
                Opens can&apos;t be counted while the app runs only on your computer: Gmail loads the tracking image from Google&apos;s servers, which can&apos;t reach it. They work on the live site. Replies are tracked either way.
              </p>
            )}
          </div>
          <ProgressUpdateCard />
          <PlaybookCard />
        </aside>
      </div>
    </>
  );
}

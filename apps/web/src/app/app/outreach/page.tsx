"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Mail, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Empty, ErrorState, ListSkeleton } from "@/components/ui";
import { OutreachList } from "./OutreachList";
import { api, fmtDate } from "@/lib/api";

type Row = { key: string; sent: number; opened: number; replied: number; positive: number; bounced: number; open_rate: number; reply_rate: number };
type Recent = { id: string; to: string; card_id: string | null; subject: string; step: number; status: string; sent_at: string | null; scheduled_for: string | null; opened: number; reply: string; error: string };
type Stats = { total: Row; queued: number; by_step: Row[]; by_hook: Row[]; by_persona: Row[]; by_hour: Row[]; recent: Recent[] };
type Gmail = { connected: boolean; email?: string; sent_today?: number; daily_cap?: number };

const pct = (x: number) => `${Math.round(x * 100)}%`;

function Tile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card p-3 md:p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-xl md:text-2xl font-semibold mt-0.5">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
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

export default function Outreach() {
  const [tab, setTab] = useState<"list" | "activity">("list");
  const s = useQuery<Stats>({ queryKey: ["outreach-stats"], queryFn: () => api("/outreach/stats") });
  const g = useQuery<Gmail>({ queryKey: ["gmail"], queryFn: () => api("/gmail") });
  if (s.isLoading) return <ListSkeleton rows={4} />;
  if (s.error) return <ErrorState error={s.error} retry={() => s.refetch()} />;
  const d = s.data!;
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Tile label="Sent (90 days)" value={d.total.sent} sub={`${d.queued} scheduled`} />
        <Tile label="Open rate" value={pct(d.total.open_rate)} sub="a hint, not proof" />
        <Tile label="Reply rate" value={pct(d.total.reply_rate)} sub={`${d.total.replied} replies`} />
        <Tile label="Interested" value={d.total.positive} sub={d.total.bounced ? `${d.total.bounced} bounced` : "positive replies"} />
      </div>
      <div className="flex gap-1 mb-3 border-b border-line">
        {(["list", "activity"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={clsx("px-3 py-2 text-sm -mb-px border-b-2", tab === t ? "border-brand font-medium" : "border-transparent text-muted")}>
            {t === "activity" ? "Activity" : "Outreach list"}
          </button>
        ))}
      </div>
      {tab === "list" ? (
        <OutreachList />
      ) : (
        <div className="grid md:grid-cols-[1fr_340px] gap-4">
          <div className="card divide-y divide-line">
            {d.recent.length === 0 && <Empty icon={<Send />} title="No emails yet" body="Draft a sequence from any investor profile. Approved emails show up here." />}
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
                <Link key={e.id} href={`/app/funnel/${e.card_id}`} className="block hover:bg-surface">
                  {inner}
                </Link>
              ) : (
                <div key={e.id}>{inner}</div>
              );
            })}
          </div>
          <div className="space-y-4">
            <Breakdown title="By email in the sequence" rows={d.by_step} label={(k) => (k === "update" ? "Updates" : `Email ${k}`)} />
            <Breakdown title="By opening hook" rows={d.by_hook} label={(k) => k.replace(/-/g, " ")} />
            <Breakdown title="By approach" rows={d.by_persona} label={(k) => k.replace(/-/g, " ")} />
          </div>
        </div>
      )}
    </>
  );
}

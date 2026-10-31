"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Bell, CheckCheck, Clock } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { Empty, ErrorState, ListSkeleton } from "@/components/ui";
import { api, fmtDate, timeAgo } from "@/lib/api";

type N = { id: string; kind: string; title: string; body: string; link: string; read: boolean; created_at: string };
type R = { id: string; title: string; due_at: string; card_id: string | null; card_name: string | null; overdue: boolean };

export default function Notifications() {
  const qc = useQueryClient();
  const n = useQuery<{ items: N[]; unread: number }>({ queryKey: ["notifications"], queryFn: () => api("/notifications") });
  const r = useQuery<{ items: R[] }>({ queryKey: ["reminders"], queryFn: () => api("/reminders") });
  const readAll = useMutation({
    mutationFn: (ids?: string[]) => api("/notifications/read", { method: "POST", json: ids ?? null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "done" | "snooze" }) => api(`/reminders/${id}`, { method: "POST", json: { action, days: 1 } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reminders"] }),
  });

  return (
    <>
      <PageHeader
        title="Alerts"
        sub={n.data ? `${n.data.unread} unread` : undefined}
        actions={
          n.data && n.data.unread > 0 ? (
            <button className="btn-ghost btn-sm" onClick={() => readAll.mutate(undefined)}>
              <CheckCheck size={14} /> Mark all read
            </button>
          ) : null
        }
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section>
          <h2 className="font-semibold mb-2 flex items-center gap-2">
            <Bell size={16} /> Notifications
          </h2>
          {n.isLoading && <ListSkeleton rows={3} />}
          {n.error && <ErrorState error={n.error} retry={() => n.refetch()} />}
          {n.data?.items.length === 0 && <Empty title="No notifications yet" body="Reminders, replies and import results show up here." />}
          <div className="space-y-2">
            {n.data?.items.map((x) => (
              <Link
                key={x.id}
                href={x.link || "#"}
                onClick={() => !x.read && readAll.mutate([x.id])}
                className={clsx("card p-3 flex gap-3", !x.read && "border-brand/40 bg-brand/[0.03]")}
              >
                <span className={clsx("mt-1.5 w-2 h-2 rounded-full shrink-0", x.read ? "bg-transparent" : "bg-brand")} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{x.title}</div>
                  {x.body && <div className="text-xs text-muted mt-0.5">{x.body}</div>}
                </div>
                <span className="text-xs text-muted whitespace-nowrap">{timeAgo(x.created_at)}</span>
              </Link>
            ))}
          </div>
        </section>
        <section>
          <h2 className="font-semibold mb-2 flex items-center gap-2">
            <Clock size={16} /> Upcoming reminders
          </h2>
          {r.isLoading && <ListSkeleton rows={3} />}
          {r.data?.items.length === 0 && <Empty title="No reminders" body="Set a next-contact date or write a note like “follow up Thursday”." />}
          <div className="space-y-2">
            {r.data?.items.map((x) => (
              <div key={x.id} className={clsx("card p-3", x.overdue && "border-danger/40")}>
                <Link href={x.card_id ? `/app/funnel/${x.card_id}` : "#"} className="block">
                  <div className="text-sm font-medium">{x.title}</div>
                  <div className={clsx("text-xs", x.overdue ? "text-danger" : "text-muted")}>
                    {x.overdue ? "Overdue · " : ""}
                    {fmtDate(x.due_at, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </div>
                </Link>
                <div className="flex gap-2 mt-2">
                  {x.card_id && (
                    <Link href={`/app/funnel/${x.card_id}`} className="btn-primary btn-sm">
                      Do it now
                    </Link>
                  )}
                  <button className="btn-ghost btn-sm" onClick={() => act.mutate({ id: x.id, action: "snooze" })}>
                    Snooze 1 day
                  </button>
                  <button className="btn-ghost btn-sm" onClick={() => act.mutate({ id: x.id, action: "done" })}>
                    Done
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}

"use client";

import clsx from "clsx";
import { Check, ChevronDown, ChevronUp, ListTodo, Pin } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { shortDate, useTasks, useUpdateTask } from "@/lib/tasks";

/** Home: the founder's top 3 open tasks (urgent, then P1, then nearest deadline). */
export function TopTasks() {
  const q = useTasks();
  const update = useUpdateTask();
  const top = q.data?.top ?? [];
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold flex items-center gap-2">
          <ListTodo size={18} className="text-brand" /> My top 3
          {!!q.data?.due_today && <span className="rounded-full bg-pink-600 text-white text-[11px] px-2 py-0.5">{q.data.due_today} due today</span>}
        </h2>
        <Link href="/app/tasks" className="text-xs text-brand">
          All tasks
        </Link>
      </div>
      {q.data && top.length === 0 && (
        <p className="text-sm text-muted py-3">
          No open tasks. <Link href="/app/tasks" className="text-brand">Add your priorities</Link>.
        </p>
      )}
      <div className="mt-2 space-y-2">
        {top.map((t) => (
          <div
            key={t.id}
            className={clsx(
              "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm",
              t.priority === 1 ? "border-orange-300 bg-orange-50 dark:bg-orange-500/10" : "border-line bg-card",
              t.due_today && "ring-2 ring-pink-500",
              t.overdue && "ring-2 ring-red-500",
            )}
          >
            <button className="w-5 h-5 shrink-0 rounded-full border-2 border-emerald-500 grid place-items-center hover:bg-emerald-500 hover:text-white text-transparent" aria-label={`Mark ${t.title} done`} onClick={() => update.mutate({ id: t.id, status: "done", progress: 100, urgent: false })}>
              <Check size={12} />
            </button>
            <Link href="/app/tasks" className="flex-1 min-w-0">
              <div className="font-medium truncate">
                {t.urgent && <Pin size={12} className="inline text-red-600 mr-1" />}
                {t.title}
              </div>
              <div className="text-xs text-muted">
                {[t.priority === 1 ? "P1" : `P${t.priority}`, t.status === "doing" ? `${t.progress}% done` : "To do", t.deadline && `due ${shortDate(t.deadline)}`, t.owner].filter(Boolean).join(" · ")}
              </div>
            </Link>
            {t.due_today && <span className="text-[11px] rounded-full bg-pink-600 text-white px-2 py-0.5 shrink-0">Today</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Pinned on every screen while any task is marked urgent and not done. */
export function UrgentPin() {
  const path = usePathname();
  const q = useTasks();
  const update = useUpdateTask();
  const [open, setOpen] = useState(false);
  const urgent = (q.data?.items ?? []).filter((t) => t.urgent && (t.status === "todo" || t.status === "doing"));
  if (!urgent.length || path.startsWith("/app/tasks")) return null;
  return (
    <div className="fixed z-40 left-3 bottom-[calc(76px_+_env(safe-area-inset-bottom))] md:left-[17rem] md:bottom-4 w-[min(320px,calc(100vw-1.5rem))]">
      <div className="rounded-2xl border border-red-300 bg-red-50 text-red-950 shadow-lg dark:bg-red-950 dark:text-red-50 dark:border-red-500/50">
        <button className="w-full flex items-center gap-2 px-3 py-2 text-sm font-semibold" onClick={() => setOpen(!open)} aria-expanded={open}>
          <Pin size={15} className="text-red-600" />
          <span className="flex-1 text-left truncate">{urgent.length === 1 ? urgent[0].title : `${urgent.length} urgent tasks`}</span>
          {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
        {open && (
          <div className="px-2 pb-2 space-y-1">
            {urgent.map((t) => (
              <div key={t.id} className="flex items-center gap-2 rounded-lg bg-white/70 dark:bg-white/10 px-2 py-1.5 text-sm">
                <button className="w-5 h-5 shrink-0 rounded-full border-2 border-emerald-600 grid place-items-center text-transparent hover:bg-emerald-600 hover:text-white" aria-label={`Mark ${t.title} done`} onClick={() => update.mutate({ id: t.id, status: "done", progress: 100, urgent: false })}>
                  <Check size={12} />
                </button>
                <span className="flex-1 min-w-0 truncate">{t.title}</span>
                {t.deadline && <span className="text-xs opacity-70">{shortDate(t.deadline)}</span>}
              </div>
            ))}
            <Link href="/app/tasks" className="block text-center text-xs font-medium text-red-700 dark:text-red-200 pt-1">
              Open tasks
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

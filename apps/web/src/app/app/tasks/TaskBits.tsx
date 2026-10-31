"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Archive, ArrowRight, CalendarClock, Check, Flag, Link2, Pin, Plus, Trash2, User, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Field, Sheet, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { COLUMNS, PRIORITY_LABEL, isoToday, shortDate, useUpdateTask, type Task, type TaskStatus } from "@/lib/tasks";

/** Sticky-note colours: P1 warm and loud, P2 classic yellow, P3 quiet. Due today gets a pink ring on top. */
const NOTE = {
  1: "bg-orange-100 border-orange-300 dark:bg-orange-500/15 dark:border-orange-400/40",
  2: "bg-yellow-50 border-yellow-200 dark:bg-yellow-500/10 dark:border-yellow-400/30",
  3: "bg-slate-50 border-slate-200 dark:bg-white/5 dark:border-white/10",
} as const;

export function TaskNote({ t, onOpen, dragging }: { t: Task; onOpen?: () => void; dragging?: boolean }) {
  const update = useUpdateTask();
  const next: Record<string, TaskStatus> = { todo: "doing", doing: "done" };
  const done = t.status === "done";
  return (
    <div
      onClick={onOpen}
      className={clsx(
        "relative rounded-lg border p-3 text-sm shadow-[0_1px_0_rgba(0,0,0,0.04),0_4px_10px_-6px_rgba(0,0,0,0.25)] cursor-pointer select-none",
        NOTE[t.priority],
        t.due_today && !done && "ring-2 ring-pink-500",
        t.overdue && "ring-2 ring-red-500",
        done && "opacity-70",
        dragging && "rotate-1 shadow-xl",
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className={clsx("font-semibold leading-snug break-words", done && "line-through")}>{t.title}</div>
          {t.description && <div className="text-xs text-ink/70 mt-0.5 line-clamp-2 break-words">{t.description}</div>}
        </div>
        {t.urgent && <Pin size={14} className="text-red-600 shrink-0 mt-0.5" aria-label="Urgent" />}
      </div>
      <div className="flex flex-wrap gap-1 mt-2 text-[11px]">
        {t.priority === 1 && <span className="rounded-full bg-orange-500 text-white px-1.5 py-0.5 font-semibold">P1</span>}
        {t.due_today && !done && <span className="rounded-full bg-pink-600 text-white px-1.5 py-0.5 font-semibold">Due today</span>}
        {t.overdue && <span className="rounded-full bg-red-600 text-white px-1.5 py-0.5 font-semibold">Overdue</span>}
        {t.deadline && !t.overdue && !(t.due_today && t.deadline === isoToday()) && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-black/5 px-1.5 py-0.5">
            <Flag size={10} /> {shortDate(t.deadline)}
          </span>
        )}
        {t.next_follow_up && !done && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-black/5 px-1.5 py-0.5" title="Next follow-up">
            <CalendarClock size={10} /> {shortDate(t.next_follow_up)}
          </span>
        )}
        {t.owner && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-black/5 px-1.5 py-0.5">
            <User size={10} /> {t.owner}
          </span>
        )}
        {t.depends_on && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-black/5 px-1.5 py-0.5 max-w-full truncate" title={`Depends on: ${t.depends_on}`}>
            <Link2 size={10} /> {t.depends_on}
          </span>
        )}
      </div>
      {(t.progress > 0 || t.status === "doing") && (
        <div className="flex items-center gap-2 mt-2">
          <div className="h-1.5 flex-1 rounded-full bg-black/10 overflow-hidden">
            <div className="h-full bg-emerald-500" style={{ width: `${t.progress}%` }} />
          </div>
          <span className="text-[11px] font-medium tabular-nums">{t.progress}%</span>
        </div>
      )}
      {next[t.status] && (
        <button
          className="absolute bottom-1.5 right-1.5 rounded-md p-1 text-ink/50 hover:bg-black/5 hover:text-ink"
          title={t.status === "todo" ? "Start" : "Mark done"}
          aria-label={t.status === "todo" ? "Start" : "Mark done"}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            update.mutate({ id: t.id, status: next[t.status], ...(next[t.status] === "done" ? { progress: 100, urgent: false } : {}) });
          }}
        >
          {t.status === "todo" ? <ArrowRight size={14} /> : <Check size={14} />}
        </button>
      )}
    </div>
  );
}

export function QuickAdd({ status = "todo", autoFocus }: { status?: TaskStatus; autoFocus?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<1 | 2 | 3>(2);
  const add = useMutation({
    mutationFn: () => api<Task>("/tasks", { method: "POST", json: { title, priority, status } }),
    onSuccess: () => {
      setTitle("");
      setPriority(2);
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <form
      className="flex gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) add.mutate();
      }}
    >
      <input className="input h-9 flex-1 text-sm" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a task, press Enter" aria-label="New task" autoFocus={autoFocus} />
      <select className="input h-9 w-auto text-sm px-2" value={priority} onChange={(e) => setPriority(Number(e.target.value) as 1 | 2 | 3)} aria-label="Priority">
        <option value={1}>P1</option>
        <option value={2}>P2</option>
        <option value={3}>P3</option>
      </select>
      <button className="btn-primary btn-sm h-9" disabled={!title.trim() || add.isPending} aria-label="Add task">
        <Plus size={16} />
      </button>
    </form>
  );
}

export function TaskEditor({ task, onClose }: { task: Task | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<Task | null>(task);
  const [newDate, setNewDate] = useState("");
  useEffect(() => {
    setF(task);
    setNewDate("");
  }, [task]);
  const save = useMutation({
    mutationFn: (body: Partial<Task>) => api<Task>(`/tasks/${task!.id}`, { method: "PATCH", json: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      onClose();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const del = useMutation({
    mutationFn: () => api(`/tasks/${task!.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      onClose();
    },
  });
  if (!task || !f) return null;
  const set = <K extends keyof Task>(k: K, v: Task[K]) => setF({ ...f, [k]: v });
  const body = {
    title: f.title,
    description: f.description,
    status: f.status,
    priority: f.priority,
    urgent: f.urgent,
    progress: f.progress,
    deadline: f.deadline || null,
    follow_ups: f.follow_ups,
    owner: f.owner,
    depends_on: f.depends_on,
  };
  return (
    <Sheet open onClose={onClose} title="Task">
      <div className="space-y-3">
        <input className="input text-base font-semibold" value={f.title} onChange={(e) => set("title", e.target.value)} aria-label="Title" />
        <textarea className="textarea min-h-20 text-sm" value={f.description} onChange={(e) => set("description", e.target.value)} placeholder="Short description" aria-label="Description" />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Field label="Status">
            <select className="input" value={f.status} onChange={(e) => set("status", e.target.value as TaskStatus)}>
              {COLUMNS.map((c) => (
                <option key={c.status} value={c.status}>
                  {c.label}
                </option>
              ))}
              <option value="archived">Archived</option>
            </select>
          </Field>
          <Field label="Priority">
            <select className="input" value={f.priority} onChange={(e) => set("priority", Number(e.target.value) as 1 | 2 | 3)}>
              {[1, 2, 3].map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABEL[p]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Deadline">
            <input className="input" type="date" value={f.deadline ?? ""} onChange={(e) => set("deadline", e.target.value || null)} />
          </Field>
          <Field label="Responsible">
            <input className="input" value={f.owner} onChange={(e) => set("owner", e.target.value)} placeholder="e.g. Me, Sam" />
          </Field>
          <div className="col-span-2">
            <Field label="Depends on">
              <input className="input" value={f.depends_on} onChange={(e) => set("depends_on", e.target.value)} placeholder="e.g. Lawyer's term sheet comments" />
            </Field>
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between text-sm mb-1">
            <span className="font-medium">Done</span>
            <span className="tabular-nums font-semibold">{f.progress}%</span>
          </div>
          <input type="range" min={0} max={100} step={5} value={f.progress} onChange={(e) => set("progress", Number(e.target.value))} className="w-full accent-emerald-600" aria-label="Percent done" />
        </div>
        <div>
          <div className="text-sm font-medium mb-1">Follow-up dates</div>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {f.follow_ups.length === 0 && <span className="text-xs text-muted">None yet</span>}
            {f.follow_ups.map((d) => (
              <span key={d} className={clsx("chip", d === isoToday() && "bg-pink-50 border-pink-300 text-pink-800")}>
                <CalendarClock size={12} /> {shortDate(d)}
                <button
                  aria-label={`Remove ${d}`}
                  onClick={() =>
                    set(
                      "follow_ups",
                      f.follow_ups.filter((x) => x !== d),
                    )
                  }
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input className="input w-auto" type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} aria-label="Add follow-up date" />
            <button
              className="btn-ghost btn-sm"
              disabled={!newDate}
              onClick={() => {
                set("follow_ups", [...new Set([...f.follow_ups, newDate])].sort());
                setNewDate("");
              }}
            >
              <Plus size={14} /> Add date
            </button>
          </div>
        </div>
        <label className={clsx("flex items-start gap-2 rounded-xl border p-3 text-sm", f.urgent ? "border-red-300 bg-red-50 text-red-900" : "border-line")}>
          <input type="checkbox" className="mt-0.5 accent-red-600" checked={f.urgent} onChange={(e) => set("urgent", e.target.checked)} />
          <span>
            <b className="inline-flex items-center gap-1">
              <Pin size={13} /> Urgent
            </b>
            <span className="block text-xs opacity-80">Stays pinned on every screen until it&apos;s done.</span>
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button className="btn-primary" disabled={!f.title.trim() || save.isPending} onClick={() => save.mutate(body)}>
            Save
          </button>
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <span className="flex-1" />
          {task.status !== "archived" && (
            <button className="btn-ghost btn-sm" onClick={() => save.mutate({ ...body, status: "archived", urgent: false })}>
              <Archive size={14} /> Archive
            </button>
          )}
          <button className="btn-ghost btn-sm text-danger" onClick={() => confirm("Delete this task?") && del.mutate()} aria-label="Delete task">
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </Sheet>
  );
}

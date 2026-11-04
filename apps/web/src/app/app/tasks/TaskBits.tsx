"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Archive, ArrowRight, CalendarClock, Check, Flag, Link2, Pin, Plus, Trash2, User, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Field, Sheet, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { COLUMNS, PRIORITY_LABEL, isoToday, shortDate, useUpdateTask, type Task, type TaskStatus } from "@/lib/tasks";

/**
 * Sticky-note paper colours (stay pastel in dark mode, just dimmed a touch):
 * done -> faded green, overdue/urgent -> pink, in progress -> blue, P1 to-do -> peach,
 * other to-do -> classic yellow, archived -> grey.
 */
const PAPER = {
  todo: "#fff3a3",
  p1: "#ffd9a8",
  doing: "#cfe8ff",
  hot: "#ffc9de",
  done: "#d9f2d0",
  archived: "#e8e6df",
} as const;

function paperFor(t: Task): string {
  if (t.status === "archived") return PAPER.archived;
  if (t.status === "done") return PAPER.done;
  if (t.overdue || t.urgent) return PAPER.hot;
  if (t.status === "doing") return PAPER.doing;
  if (t.priority === 1) return PAPER.p1;
  return PAPER.todo;
}

/** Stable pseudo-random tilt between -2deg and 2deg derived from the task id. */
function tiltFor(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.round((((h >>> 0) % 401) / 100 - 2) * 100) / 100;
}

const HAND_FONT = '"Segoe Print", "Bradley Hand", "Chalkboard SE", "Comic Sans MS", cursive';
const CHIP = "inline-flex items-center gap-0.5 rounded-full bg-black/[0.07] px-1.5 py-0.5";

export function TaskNote({ t, onOpen, dragging }: { t: Task; onOpen?: () => void; dragging?: boolean }) {
  const update = useUpdateTask();
  const next: Record<string, TaskStatus> = { todo: "doing", doing: "done" };
  const done = t.status === "done";
  const tilt = dragging ? 3 : tiltFor(t.id);
  return (
    <div
      onClick={onOpen}
      style={{ backgroundColor: paperFor(t), ["--rot" as string]: `${tilt}deg` }}
      className={clsx(
        "group relative flex flex-col min-h-[150px] rounded-[2px] px-3.5 pt-5 pb-3 text-sm text-[#2b2b2b] cursor-pointer select-none",
        "[transform:rotate(var(--rot))] transition-[transform,box-shadow,filter,opacity] duration-200 ease-out",
        "shadow-[0_1px_1px_rgba(0,0,0,0.12),0_8px_14px_-8px_rgba(0,0,0,0.35),10px_14px_14px_-12px_rgba(0,0,0,0.4)]",
        "hover:[transform:rotate(0deg)_translateY(-4px)_scale(1.02)] hover:shadow-[0_2px_3px_rgba(0,0,0,0.12),0_18px_26px_-10px_rgba(0,0,0,0.4),14px_22px_22px_-14px_rgba(0,0,0,0.45)] hover:z-10",
        "dark:brightness-[0.88] dark:hover:brightness-95",
        done && "opacity-75 saturate-[0.7] hover:opacity-100",
        dragging && "[transform:rotate(var(--rot))_scale(1.04)] shadow-[0_24px_36px_-12px_rgba(0,0,0,0.5)]",
      )}
    >
      {/* Tape strip */}
      <span
        aria-hidden
        className="pointer-events-none absolute -top-2.5 left-1/2 h-5 w-16 -translate-x-1/2 -rotate-2 rounded-[1px] bg-white/55 shadow-[0_1px_2px_rgba(0,0,0,0.12)] ring-1 ring-black/5 backdrop-blur-[1px]"
      />
      {/* Paper curl: soft darkening towards the bottom-right corner */}
      <span
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-10 w-10 rounded-br-[2px]"
        style={{ background: "linear-gradient(135deg, transparent 55%, rgba(0,0,0,0.06) 75%, rgba(0,0,0,0.12) 100%)" }}
      />
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div
            className={clsx("text-[15px] font-bold leading-snug break-words text-[#1f1f1f]", done && "line-through decoration-2 decoration-black/50")}
            style={{ fontFamily: HAND_FONT }}
          >
            {t.title}
          </div>
          {t.description && <div className="text-xs text-black/65 mt-1 line-clamp-3 break-words">{t.description}</div>}
        </div>
        {t.urgent && <Pin size={14} className="text-red-600 shrink-0 mt-0.5" aria-label="Urgent" />}
      </div>
      <div className="flex-1" />
      <div className="flex flex-wrap gap-1 mt-2 pr-6 text-[11px]">
        {t.priority === 1 && <span className="rounded-full bg-orange-500 text-white px-1.5 py-0.5 font-semibold">P1</span>}
        {t.due_today && !done && <span className="rounded-full bg-pink-600 text-white px-1.5 py-0.5 font-semibold">Due today</span>}
        {t.overdue && <span className="rounded-full bg-red-600 text-white px-1.5 py-0.5 font-semibold">Overdue</span>}
        {t.deadline && !t.overdue && !(t.due_today && t.deadline === isoToday()) && (
          <span className={CHIP}>
            <Flag size={10} /> {shortDate(t.deadline)}
          </span>
        )}
        {t.next_follow_up && !done && (
          <span className={CHIP} title="Next follow-up">
            <CalendarClock size={10} /> {shortDate(t.next_follow_up)}
          </span>
        )}
        {t.owner && (
          <span className={CHIP}>
            <User size={10} /> {t.owner}
          </span>
        )}
        {t.depends_on && (
          <span className={clsx(CHIP, "max-w-full truncate")} title={`Depends on: ${t.depends_on}`}>
            <Link2 size={10} /> {t.depends_on}
          </span>
        )}
      </div>
      {(t.progress > 0 || t.status === "doing") && (
        <div className="flex items-center gap-2 mt-2 pr-6">
          <div className="h-1.5 flex-1 rounded-full bg-black/10 overflow-hidden">
            <div className="h-full bg-emerald-600" style={{ width: `${t.progress}%` }} />
          </div>
          <span className="text-[11px] font-medium tabular-nums">{t.progress}%</span>
        </div>
      )}
      {next[t.status] && (
        <button
          className="absolute bottom-1.5 right-1.5 z-[1] rounded-md p-1 text-black/50 hover:bg-black/10 hover:text-black"
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

const STATUS_PILL: Record<TaskStatus, string> = {
  todo: "bg-slate-500",
  doing: "bg-amber-500",
  done: "bg-emerald-600",
  archived: "bg-zinc-400",
};
const GROUP_BAR: Record<string, string> = { todo: "border-l-slate-400", doing: "border-l-amber-500", done: "border-l-emerald-600" };

function OwnerCell({ t }: { t: Task }) {
  const update = useUpdateTask();
  const [v, setV] = useState(t.owner);
  useEffect(() => setV(t.owner), [t.owner]);
  return (
    <input
      className="w-full bg-transparent rounded px-1.5 py-1 text-sm hover:bg-black/5 focus:bg-card focus:outline-none focus:ring-2 focus:ring-brand/40"
      value={v}
      placeholder="Me"
      aria-label={`Owner of ${t.title}`}
      onChange={(e) => setV(e.target.value)}
      onBlur={() => v !== t.owner && update.mutate({ id: t.id, owner: v.trim() || "Me" })}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
    />
  );
}

/** Monday-style table: Task, Owner, Status, Priority, Deadline, Done. Everything edits in place. */
export function TaskTable({ items, onOpen }: { items: Task[]; onOpen: (t: Task) => void }) {
  const update = useUpdateTask();
  return (
    <div className="space-y-6">
      {COLUMNS.map((g) => {
        const rows = items.filter((t) => t.status === g.status).sort((a, b) => a.position - b.position);
        return (
          <section key={g.status}>
            <div className="flex items-center gap-2 mb-2">
              <span className={clsx("w-2.5 h-2.5 rounded-full", STATUS_PILL[g.status])} />
              <h2 className="font-semibold">{g.label}</h2>
              <span className="text-xs text-muted">{rows.length}</span>
            </div>
            <div className={clsx("card overflow-hidden border-l-4", GROUP_BAR[g.status])}>
              <div className="hidden md:grid grid-cols-[minmax(0,1fr)_140px_140px_110px_130px_120px] gap-2 px-3 py-2 text-xs font-medium text-muted border-b border-line bg-surface/60">
                <span>Task</span>
                <span>Owner</span>
                <span>Status</span>
                <span>Priority</span>
                <span>Deadline</span>
                <span>Done</span>
              </div>
              {rows.map((t) => (
                <div
                  key={t.id}
                  className={clsx(
                    "grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1fr)_140px_140px_110px_130px_120px] gap-x-2 gap-y-1 items-center px-3 py-2 border-b border-line last:border-0 text-sm",
                    t.priority === 1 && t.status !== "done" && "bg-orange-50/70 dark:bg-orange-500/10",
                    t.due_today && "shadow-[inset_3px_0_0_#db2777]",
                    t.overdue && "shadow-[inset_3px_0_0_#dc2626]",
                  )}
                >
                  <button className="text-left min-w-0" onClick={() => onOpen(t)}>
                    <span className={clsx("font-medium break-words", t.status === "done" && "line-through text-muted")}>
                      {t.urgent && <Pin size={12} className="inline text-red-600 mr-1" />}
                      {t.title}
                    </span>
                    {t.due_today && t.status !== "done" && <span className="ml-2 inline-block whitespace-nowrap rounded-full bg-pink-600 text-white text-[10px] px-1.5 py-0.5 align-middle">Due today</span>}
                    {t.overdue && <span className="ml-2 inline-block whitespace-nowrap rounded-full bg-red-600 text-white text-[10px] px-1.5 py-0.5 align-middle">Overdue</span>}
                    {t.depends_on && <span className="block text-xs text-muted truncate">Depends on: {t.depends_on}</span>}
                    <span className="md:hidden block text-xs text-muted truncate">
                      {[t.owner, `P${t.priority}`, t.deadline && `due ${shortDate(t.deadline)}`, t.progress ? `${t.progress}%` : ""].filter(Boolean).join(" · ")}
                    </span>
                  </button>
                  <div className="hidden md:block md:order-none">
                    <OwnerCell t={t} />
                  </div>
                  <select
                    className={clsx("rounded-md text-white text-xs font-semibold h-8 px-2 border-0 cursor-pointer w-28 md:w-full", STATUS_PILL[t.status])}
                    value={t.status}
                    aria-label={`Status of ${t.title}`}
                    onChange={(e) => {
                      const s = e.target.value as TaskStatus;
                      update.mutate({ id: t.id, status: s, ...(s === "done" ? { progress: 100, urgent: false } : {}) });
                    }}
                  >
                    {COLUMNS.map((c) => (
                      <option key={c.status} value={c.status}>
                        {c.label}
                      </option>
                    ))}
                    <option value="archived">Archive</option>
                  </select>
                  <select
                    className={clsx("hidden md:block input h-8 text-xs px-2", t.priority === 1 && "border-orange-400 text-orange-700 font-semibold")}
                    value={t.priority}
                    aria-label={`Priority of ${t.title}`}
                    onChange={(e) => update.mutate({ id: t.id, priority: Number(e.target.value) as 1 | 2 | 3 })}
                  >
                    {[1, 2, 3].map((p) => (
                      <option key={p} value={p}>
                        P{p}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    className={clsx("hidden md:block input h-8 text-xs px-2", t.overdue && "border-red-400 text-red-700")}
                    value={t.deadline ?? ""}
                    aria-label={`Deadline of ${t.title}`}
                    onChange={(e) => update.mutate({ id: t.id, deadline: e.target.value || null })}
                  />
                  <div className="hidden md:flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-black/10 overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: `${t.progress}%` }} />
                    </div>
                    <span className="text-xs tabular-nums w-8 text-right">{t.progress}%</span>
                  </div>
                </div>
              ))}
              {g.status === "todo" && (
                <div className="px-3 py-2 bg-surface/40">
                  <QuickAdd />
                </div>
              )}
              {rows.length === 0 && g.status !== "todo" && <div className="px-3 py-4 text-xs text-muted">Nothing here yet.</div>}
            </div>
          </section>
        );
      })}
    </div>
  );
}

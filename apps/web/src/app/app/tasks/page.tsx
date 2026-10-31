"use client";

import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, TouchSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import clsx from "clsx";
import { Archive, CalendarCheck, Undo2 } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorState, ListSkeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { COLUMNS, useTasks, useUpdateTask, type Task, type TaskStatus } from "@/lib/tasks";
import { QuickAdd, TaskEditor, TaskNote } from "./TaskBits";

function DraggableNote({ t, onOpen }: { t: Task; onOpen: () => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: t.id });
  const drop = useDroppable({ id: `task:${t.id}`, data: { status: t.status, beforeId: t.id } });
  return (
    <div ref={drop.setNodeRef} className={clsx(drop.isOver && "pt-1 border-t-2 border-brand rounded")}>
      <div ref={setNodeRef} {...listeners} {...attributes} className={clsx(isDragging && "opacity-30")}>
        <TaskNote t={t} onOpen={onOpen} />
      </div>
    </div>
  );
}

function Column({ status, label, tasks, onOpen, className }: { status: TaskStatus; label: string; tasks: Task[]; onOpen: (t: Task) => void; className?: string }) {
  const { setNodeRef, isOver } = useDroppable({ id: `col:${status}`, data: { status } });
  return (
    <div ref={setNodeRef} className={clsx("rounded-2xl bg-line/30 p-2.5 flex flex-col gap-2 min-h-40", isOver && "ring-2 ring-brand", className)}>
      <div className="flex items-center justify-between px-1">
        <span className="font-semibold text-sm">{label}</span>
        <span className="text-xs text-muted tabular-nums">{tasks.length}</span>
      </div>
      {status === "todo" && <QuickAdd />}
      {tasks.map((t) => (
        <DraggableNote key={t.id} t={t} onOpen={() => onOpen(t)} />
      ))}
      {tasks.length === 0 && <div className="text-xs text-muted text-center py-6 border border-dashed border-line rounded-lg">Drop tasks here</div>}
    </div>
  );
}

function ArchivedList({ onOpen }: { onOpen: (t: Task) => void }) {
  const q = useQuery<{ items: Task[] }>({ queryKey: ["tasks", "archived"], queryFn: () => api("/tasks?archived=true") });
  const update = useUpdateTask();
  if (!q.data) return <ListSkeleton rows={2} />;
  if (!q.data.items.length) return <p className="text-sm text-muted">Nothing archived.</p>;
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
      {q.data.items.map((t) => (
        <div key={t.id} className="relative">
          <TaskNote t={t} onOpen={() => onOpen(t)} />
          <button className="absolute top-2 right-2 btn-ghost btn-sm h-7 bg-card" onClick={() => update.mutate({ id: t.id, status: "todo" }, { onSuccess: () => q.refetch() })}>
            <Undo2 size={13} /> Restore
          </button>
        </div>
      ))}
    </div>
  );
}

export default function TasksPage() {
  const q = useTasks();
  const update = useUpdateTask();
  const [open, setOpen] = useState<Task | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [tab, setTab] = useState<TaskStatus>("todo"); // phones show one column at a time
  const [archived, setArchived] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }),
    useSensor(KeyboardSensor),
  );
  if (q.isLoading) return <ListSkeleton rows={4} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const items = q.data!.items;
  const col = (s: TaskStatus) => items.filter((t) => t.status === s).sort((a, b) => a.position - b.position);
  const dueToday = items.filter((t) => t.due_today);

  const onDragEnd = (e: DragEndEvent) => {
    setDragId(null);
    const data = e.over?.data.current as { status: TaskStatus; beforeId?: string } | undefined;
    if (!data) return;
    const id = String(e.active.id);
    if (data.beforeId === id) return;
    const list = col(data.status).filter((t) => t.id !== id);
    let position: number;
    if (data.beforeId) {
      const i = list.findIndex((t) => t.id === data.beforeId);
      const after = list[i]?.position ?? 0;
      position = i > 0 ? (list[i - 1].position + after) / 2 : after - 1;
    } else {
      position = list.length ? list[list.length - 1].position + 1 : 0;
    }
    update.mutate({ id, status: data.status, position, ...(data.status === "done" ? { progress: 100, urgent: false } : {}) });
  };

  return (
    <>
      <PageHeader
        title="Founder tasks"
        sub="Your priorities. Drag notes between columns; P1 and urgent come first on your home page."
        actions={
          <button className={clsx("btn-ghost btn-sm sm:h-10 sm:text-sm", archived && "border-brand text-brand")} onClick={() => setArchived(!archived)}>
            <Archive size={16} /> {archived ? "Back to board" : "Archive"}
          </button>
        }
      />
      {archived ? (
        <ArchivedList onOpen={setOpen} />
      ) : (
        <>
          {dueToday.length > 0 && (
            <div className="mb-4 rounded-2xl border border-pink-300 bg-pink-50 p-3 text-pink-900 dark:bg-pink-500/10 dark:text-pink-100">
              <div className="flex items-center gap-2 font-semibold text-sm mb-2">
                <CalendarCheck size={16} /> Due today ({dueToday.length})
              </div>
              <div className="flex flex-wrap gap-2">
                {dueToday.map((t) => (
                  <button key={t.id} className="rounded-full bg-white/80 dark:bg-white/10 border border-pink-300 px-3 py-1 text-sm hover:border-pink-500" onClick={() => setOpen(t)}>
                    {t.priority === 1 && <b className="text-orange-600">P1 </b>}
                    {t.title}
                  </button>
                ))}
              </div>
            </div>
          )}
          {/* Phones: one column at a time */}
          <div className="md:hidden grid grid-cols-3 gap-1 rounded-xl bg-line/40 p-1 mb-3">
            {COLUMNS.map((c) => (
              <button key={c.status} className={clsx("rounded-lg py-2 text-sm font-medium", tab === c.status ? "bg-card shadow text-ink" : "text-muted")} onClick={() => setTab(c.status)}>
                {c.label} <span className="text-xs text-muted">{col(c.status).length}</span>
              </button>
            ))}
          </div>
          <DndContext sensors={sensors} onDragStart={(e) => setDragId(String(e.active.id))} onDragEnd={onDragEnd} onDragCancel={() => setDragId(null)}>
            <div className="grid md:grid-cols-3 gap-3 items-start">
              {COLUMNS.map((c) => (
                <Column key={c.status} status={c.status} label={c.label} tasks={col(c.status)} onOpen={setOpen} className={clsx(tab !== c.status && "hidden md:flex")} />
              ))}
            </div>
            <DragOverlay>{dragId ? <TaskNote t={items.find((t) => t.id === dragId)!} dragging /> : null}</DragOverlay>
          </DndContext>
        </>
      )}
      <TaskEditor task={open} onClose={() => setOpen(null)} />
    </>
  );
}

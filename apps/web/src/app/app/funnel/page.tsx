"use client";

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertCircle, ArrowRightLeft, Check, Download, Flame, LayoutGrid, Plus, Rows3, Search, Snowflake, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Empty, ErrorState, Field, ListSkeleton, Sheet, StatusBadge, errText, useToast } from "@/components/ui";
import { api, fmtDate, qs } from "@/lib/api";
import type { Card, FunnelMeta } from "@/lib/types";
import { QuickCard } from "./QuickCard";

const SHORT = ["Not started", "Intro req.", "In contact", "First call", "Deck req.", "Deep dive", "Term sheet", "Signed", "Paid"];

function HeatIcon({ heat }: { heat: Card["heat"] }) {
  if (heat === "hot") return <Flame size={14} className="text-orange-500" aria-label="Hot" />;
  if (heat === "cold") return <Snowflake size={14} className="text-sky-500/70" aria-label="Cold" />;
  return null;
}

function CardBody({ c }: { c: Card }) {
  return (
    <>
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{c.name}</div>
          <div className="text-xs text-muted truncate">{c.firm || "—"}</div>
        </div>
        <span className="text-[10px] font-mono text-muted border border-line rounded px-1">{c.priority}</span>
      </div>
      <div className="mt-2 flex items-center gap-1.5 flex-wrap">
        <StatusBadge status={c.status} />
        <HeatIcon heat={c.heat} />
        {c.overdue && (
          <span className="chip text-danger border-danger/30">
            <AlertCircle size={11} /> overdue
          </span>
        )}
        {c.due_today && <span className="chip text-brand border-brand/30">due today</span>}
        {c.ticket_size && <span className="text-xs text-muted">{c.ticket_size}</span>}
      </div>
    </>
  );
}

function DraggableCard({ c, onOpen }: { c: Card; onOpen: () => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: c.id, data: { card: c } });
  const drop = useDroppable({ id: `card:${c.id}`, data: { stage: c.stage, beforeId: c.id } });
  return (
    <div ref={drop.setNodeRef} className={clsx("rounded-lg", drop.isOver && "pt-1 border-t-2 border-brand")}>
      <div
        ref={setNodeRef}
        {...listeners}
        {...attributes}
        onClick={onOpen}
        className={clsx("card p-3 cursor-grab active:cursor-grabbing hover:border-brand", isDragging && "opacity-40")}
      >
        <CardBody c={c} />
      </div>
    </div>
  );
}

function Column({ stage, label, cards, onOpen }: { stage: number; label: string; cards: Card[]; onOpen: (id: string) => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: `col:${stage}`, data: { stage } });
  return (
    <div ref={setNodeRef} className={clsx("w-64 shrink-0 rounded-xl bg-line/30 p-2 flex flex-col", isOver && "ring-2 ring-brand")}>
      <div className="flex items-center justify-between px-1 pb-2">
        <span className="text-xs font-semibold">{label}</span>
        <span className="text-xs text-muted">{cards.length}</span>
      </div>
      <div className="flex flex-col gap-2 min-h-24">
        {cards.map((c) => (
          <DraggableCard key={c.id} c={c} onOpen={() => onOpen(c.id)} />
        ))}
      </div>
    </div>
  );
}

function FunnelInner() {
  const params = useSearchParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [view, setView] = useState<"board" | "table">("board");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(OPEN); // default: hide inactive and rejected investors
  const [needsAction, setNeedsAction] = useState(params.get("needs_action") === "1");
  const [mobileStage, setMobileStage] = useState<number>(Number(params.get("stage") ?? 0));
  const [moving, setMoving] = useState<Card | null>(null);
  const [adding, setAdding] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const meta = useQuery<FunnelMeta>({ queryKey: ["funnel-meta"], queryFn: () => api("/funnel/meta"), staleTime: Infinity });
  const filters = { q: search, status: status === OPEN || status === "all" ? "" : status, needs_action: needsAction };
  const list = useQuery<{ items: Card[] }>({ queryKey: ["funnel", filters], queryFn: () => api(`/funnel${qs(filters)}`) });
  const all = list.data?.items ?? [];
  const cards = status === OPEN ? all.filter((c) => !CLOSED.includes(c.status)) : all;
  const hidden = all.length - cards.length;
  const byStage = useMemo(() => {
    const m: Record<number, Card[]> = {};
    for (let i = 1; i <= 9; i++) m[i] = [];
    cards.forEach((c) => m[c.stage].push(c));
    return m;
  }, [cards]);

  const move = useMutation({
    mutationFn: ({ id, stage, before_id }: { id: string; stage: number; before_id?: string }) => api(`/funnel/${id}/move`, { method: "POST", json: { stage, before_id } }),
    onMutate: async ({ id, stage }) => {
      await qc.cancelQueries({ queryKey: ["funnel", filters] });
      const prev = qc.getQueryData<{ items: Card[] }>(["funnel", filters]);
      qc.setQueryData<{ items: Card[] }>(["funnel", filters], (d) => d && { items: d.items.map((c) => (c.id === id ? { ...c, stage } : c)) });
      return { prev };
    },
    onError: (e, _v, ctx) => {
      qc.setQueryData(["funnel", filters], ctx?.prev);
      toast(errText(e), "err");
    },
    onSuccess: (_d, v) => {
      if (v.stage === 4) toast("First call arranged. Set the call date on the card to get a prep reminder.");
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["funnel"] });
      qc.invalidateQueries({ queryKey: ["home"] });
    },
  });

  const contacted = useMutation({
    mutationFn: (id: string) => api(`/funnel/${id}/contacted`, { method: "POST", json: { method: "Email" } }),
    onSuccess: () => {
      toast("Logged as contacted today");
      qc.invalidateQueries({ queryKey: ["funnel"] });
    },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }),
    useSensor(KeyboardSensor),
  );
  const onDragEnd = (e: DragEndEvent) => {
    setDragId(null);
    const data = e.over?.data.current as { stage: number; beforeId?: string } | undefined;
    if (!data || !e.active) return;
    const id = String(e.active.id);
    if (data.beforeId === id) return;
    const card = cards.find((c) => c.id === id);
    if (card && card.stage === data.stage && !data.beforeId) return;
    move.mutate({ id, stage: data.stage, before_id: data.beforeId });
  };

  const stages = meta.data?.stages ?? [];
  const visibleMobile = mobileStage ? byStage[mobileStage] ?? [] : cards;

  return (
    <>
      <PageHeader
        title="Investor tracker"
        sub={`${cards.length} investors`}
        actions={
          <>
            <Link href="/app/funnel/import" className="btn-ghost btn-sm sm:h-10 sm:text-sm">
              <Upload size={16} /> <span className="hidden sm:inline">Import</span>
            </Link>
            <a href="/api/funnel/export/csv" className="btn-ghost btn-sm sm:h-10 sm:text-sm hidden sm:inline-flex">
              <Download size={16} /> Export
            </a>
            <button className="btn-primary btn-sm sm:h-10 sm:text-sm" onClick={() => setAdding(true)}>
              <Plus size={16} /> Add
            </button>
          </>
        }
      />
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative flex-1 min-w-48">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input className="input pl-9" placeholder="Search name or firm" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value={OPEN}>Hide inactive &amp; rejected</option>
          <option value="all">All statuses</option>
          {meta.data?.statuses.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <button className={clsx("chip px-3 py-2 text-sm", needsAction && "bg-brand text-white border-brand")} onClick={() => setNeedsAction((x) => !x)}>
          Needs action
        </button>
        {hidden > 0 && (
          <button className="text-sm text-brand" onClick={() => setStatus("all")}>
            Show {hidden} hidden
          </button>
        )}
        <div className="hidden md:flex ml-auto border border-line rounded-lg overflow-hidden">
          <button className={clsx("px-3 py-2", view === "board" && "bg-brand/10 text-brand")} onClick={() => setView("board")} aria-label="Board view">
            <LayoutGrid size={16} />
          </button>
          <button className={clsx("px-3 py-2", view === "table" && "bg-brand/10 text-brand")} onClick={() => setView("table")} aria-label="Table view">
            <Rows3 size={16} />
          </button>
        </div>
      </div>

      {list.isLoading && <ListSkeleton />}
      {list.error && <ErrorState error={list.error} retry={() => list.refetch()} />}
      {list.data && all.length === 0 && !search && status === OPEN && !needsAction && (
        <Empty
          title="Your investor tracker is empty"
          body="Import your existing tracker, add investors from the database, or add someone manually."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link href="/app/funnel/import" className="btn-primary">
                <Upload size={16} /> Import spreadsheet
              </Link>
              <Link href="/app/investors" className="btn-ghost">
                Find investors
              </Link>
            </div>
          }
        />
      )}

      {/* Mobile: stage pills + list with quick actions */}
      {list.data && cards.length > 0 && (
        <div className="md:hidden">
          <div className="flex gap-2 overflow-x-auto scrollbar-none -mx-4 px-4 pb-3">
            <button className={clsx("chip px-3 py-1.5 text-sm whitespace-nowrap", !mobileStage && "bg-ink text-surface border-ink")} onClick={() => setMobileStage(0)}>
              All {cards.length}
            </button>
            {stages.map((s) => (
              <button key={s.value} className={clsx("chip px-3 py-1.5 text-sm whitespace-nowrap", mobileStage === s.value && "bg-ink text-surface border-ink")} onClick={() => setMobileStage(s.value)}>
                {SHORT[s.value - 1]} {byStage[s.value]?.length ?? 0}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            {visibleMobile.length === 0 && <p className="text-sm text-muted text-center py-8">No investors in this stage.</p>}
            {visibleMobile.map((c) => (
              <div key={c.id} className="card">
                <button type="button" onClick={() => setOpenId(c.id)} className="block w-full text-left p-3">
                  <CardBody c={c} />
                  <div className="text-xs text-muted mt-1.5">
                    {c.stage_label}
                    {c.next_contact_date && ` · next ${fmtDate(c.next_contact_date)}`}
                  </div>
                </button>
                <div className="flex border-t border-line divide-x divide-line">
                  <button className="flex-1 py-2.5 text-sm text-brand flex items-center justify-center gap-1.5" onClick={() => setMoving(c)}>
                    <ArrowRightLeft size={15} /> Move stage
                  </button>
                  <button className="flex-1 py-2.5 text-sm text-muted flex items-center justify-center gap-1.5" onClick={() => contacted.mutate(c.id)}>
                    <Check size={15} /> Contacted
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Desktop board */}
      {list.data && cards.length > 0 && view === "board" && (
        <div className="hidden md:block -mx-4 px-4 overflow-x-auto pb-4">
          <DndContext sensors={sensors} onDragStart={(e) => setDragId(String(e.active.id))} onDragEnd={onDragEnd} onDragCancel={() => setDragId(null)}>
            <div className="flex gap-3 items-start">
              {stages.map((s) => (
                <Column key={s.value} stage={s.value} label={s.label} cards={byStage[s.value] ?? []} onOpen={(id) => setOpenId(id)} />
              ))}
            </div>
            <DragOverlay>{dragId ? <div className="card p-3 w-60 shadow-xl rotate-2"><CardBody c={cards.find((c) => c.id === dragId)!} /></div> : null}</DragOverlay>
          </DndContext>
        </div>
      )}

      {/* Desktop table */}
      {list.data && cards.length > 0 && view === "table" && (
        <div className="hidden md:block card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted text-left border-b border-line">
              <tr>
                {["Name", "Firm", "Type", "Prio", "Status", "Stage", "Ticket", "Can lead", "Referrer", "Last contacted", "Next contact"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => (
                <tr key={c.id} className="border-b border-line last:border-0 hover:bg-surface cursor-pointer" onClick={() => setOpenId(c.id)}>
                  <td className="px-3 py-2 font-medium whitespace-nowrap">{c.name}</td>
                  <td className="px-3 py-2 text-muted">{c.firm}</td>
                  <td className="px-3 py-2 text-muted whitespace-nowrap">{c.investor_type}</td>
                  <td className="px-3 py-2 font-mono text-xs">{c.priority}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{c.stage_label}</td>
                  <td className="px-3 py-2">{c.ticket_size}</td>
                  <td className="px-3 py-2">{c.can_lead}</td>
                  <td className="px-3 py-2 text-muted">{c.referrer}</td>
                  <td className="px-3 py-2 text-muted whitespace-nowrap">{fmtDate(c.last_contacted_at)}</td>
                  <td className={clsx("px-3 py-2 whitespace-nowrap", c.overdue ? "text-danger" : "text-muted")}>{fmtDate(c.next_contact_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Sheet open={!!moving} onClose={() => setMoving(null)} title={moving ? `Move ${moving.name}` : ""}>
        <div className="flex flex-col gap-1.5">
          {stages.map((s) => (
            <button
              key={s.value}
              className={clsx("text-left rounded-lg border px-3 py-3 text-sm", moving?.stage === s.value ? "border-brand bg-brand/5 text-brand font-medium" : "border-line")}
              onClick={() => {
                if (moving) move.mutate({ id: moving.id, stage: s.value });
                setMoving(null);
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </Sheet>

      <AddCard open={adding} onClose={() => setAdding(false)} meta={meta.data} />
      <QuickCard card={all.find((c) => c.id === openId) ?? null} meta={meta.data} onClose={() => setOpenId(null)} />
    </>
  );
}

function AddCard({ open, onClose, meta }: { open: boolean; onClose: () => void; meta?: FunnelMeta }) {
  const qc = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", firm: "", email: "", stage: 1, investor_type: "", priority: "P3" });
  const create = useMutation({
    mutationFn: () => api<Card>("/funnel", { method: "POST", json: { ...form, investor_type: form.investor_type || undefined } }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["funnel"] });
      setForm({ name: "", firm: "", email: "", stage: 1, investor_type: "", priority: "P3" });
      onClose();
      router.push(`/app/funnel/${c.id}`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <Sheet open={open} onClose={onClose} title="Add investor">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Name *">
          <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus />
        </Field>
        <Field label="Firm">
          <input className="input" value={form.firm} onChange={(e) => setForm({ ...form, firm: e.target.value })} />
        </Field>
        <Field label="Email">
          <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Stage">
            <select className="input" value={form.stage} onChange={(e) => setForm({ ...form, stage: Number(e.target.value) })}>
              {meta?.stages.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Priority">
            <select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {meta?.priorities.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Investor type">
          <select className="input" value={form.investor_type} onChange={(e) => setForm({ ...form, investor_type: e.target.value })}>
            <option value="">—</option>
            {meta?.types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </Field>
        <button className="btn-primary w-full" disabled={create.isPending}>
          Add to tracker
        </button>
      </form>
    </Sheet>
  );
}

const OPEN = "open";
const CLOSED = ["Inactive", "Rejection"];

export default function FunnelPage() {
  return (
    <Suspense fallback={<ListSkeleton />}>
      <FunnelInner />
    </Suspense>
  );
}

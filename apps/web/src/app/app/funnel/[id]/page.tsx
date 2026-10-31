"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Bell, Check, Copy, ExternalLink, MessageCircle, Phone, Send, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { MeetingBrief, RoomActivity } from "@/components/CardExtras";
import { ErrorState, Field, ListSkeleton, Sheet, StatusBadge, errText, useToast } from "@/components/ui";
import { api, fmtDate, timeAgo } from "@/lib/api";
import type { Card, FunnelMeta } from "@/lib/types";

type Event = { id: string; kind: string; body: string; meta: Record<string, unknown>; created_at: string };
type Detail = Card & { events: Event[]; reminders: { id: string; title: string; due_at: string }[] };
type Suggestion = { field: string; value: string | number; reason: string };

const EDITABLE = ["name", "firm", "investor_type", "priority", "status", "stage", "can_lead", "ticket_size", "agreed_size", "instrument", "contact_method", "email", "referrer", "next_contact_date", "call_at", "investor_timezone", "shareable"] as const;

function toLocalInput(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function CardPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const meta = useQuery<FunnelMeta>({ queryKey: ["funnel-meta"], queryFn: () => api("/funnel/meta"), staleTime: Infinity });
  const q = useQuery<Detail>({ queryKey: ["card", id], queryFn: () => api(`/funnel/${id}`) });
  const [form, setForm] = useState<Partial<Card>>({});
  const [note, setNote] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [nudgeOpen, setNudgeOpen] = useState(false);
  const [callPrompt, setCallPrompt] = useState(false);
  const [callAt, setCallAt] = useState("");

  useEffect(() => {
    if (q.data) setForm(Object.fromEntries(EDITABLE.map((k) => [k, q.data[k]])) as Partial<Card>);
  }, [q.data]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["card", id] });
    qc.invalidateQueries({ queryKey: ["funnel"] });
    qc.invalidateQueries({ queryKey: ["home"] });
  };
  const patch = useMutation({
    mutationFn: (body: Partial<Card>) => api<Card>(`/funnel/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => {
      toast("Saved");
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const addNote = useMutation({
    mutationFn: () => api<{ reminder_date: string | null; suggestions: Suggestion[] }>(`/funnel/${id}/notes`, { method: "POST", json: { body: note } }),
    onSuccess: (r) => {
      setNote("");
      setSuggestions(r.suggestions);
      if (r.reminder_date) toast(`Reminder set for ${fmtDate(r.reminder_date)}`);
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const contacted = useMutation({
    mutationFn: (method: string) => api(`/funnel/${id}/contacted`, { method: "POST", json: { method } }),
    onSuccess: () => {
      toast("Logged as contacted");
      refresh();
    },
  });
  const del = useMutation({
    mutationFn: () => api(`/funnel/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["funnel"] });
      router.push("/app/funnel");
    },
  });
  const nudge = useQuery<{ whatsapp: string; linkedin: string }>({ queryKey: ["nudge", id], queryFn: () => api(`/sequences/nudge/${id}`), enabled: nudgeOpen });
  const reminderAct = useMutation({
    mutationFn: ({ rid, action }: { rid: string; action: "done" | "snooze" }) => api(`/reminders/${rid}`, { method: "POST", json: { action, days: 1 } }),
    onSuccess: refresh,
  });

  if (q.isLoading) return <ListSkeleton rows={4} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const c = q.data!;
  const set = (k: keyof Card, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const dirty = EDITABLE.some((k) => (form[k] ?? "") !== (c[k] ?? ""));

  const setStage = (stage: number) => {
    if (stage === 4 && !c.call_at) setCallPrompt(true);
    patch.mutate({ stage });
  };

  const applySuggestion = (s: Suggestion) => {
    patch.mutate({ [s.field]: s.value } as Partial<Card>);
    setSuggestions((x) => x.filter((y) => y !== s));
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied");
    } catch {
      toast("Couldn't copy", "err");
    }
  };

  return (
    <div className="pb-6">
      <Link href="/app/funnel" className="text-sm text-muted flex items-center gap-1 mb-3">
        <ArrowLeft size={16} /> Funnel
      </Link>
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold truncate">{c.name}</h1>
          <div className="text-sm text-muted">{c.firm || "—"}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <StatusBadge status={c.status} />
            <span className="chip">{c.priority}</span>
            {c.tags.map((t) => (
              <span key={t} className="chip text-muted">
                {t}
              </span>
            ))}
            {c.investor_id && (
              <Link href={`/app/investors/${c.investor_id}`} className="chip text-brand border-brand/30">
                Profile <ExternalLink size={11} />
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Stage stepper (scrollable on phones) */}
      <div className="card p-3 mb-4">
        <div className="label">Stage</div>
        <div className="flex gap-1.5 overflow-x-auto scrollbar-none -mx-1 px-1">
          {meta.data?.stages.map((s) => (
            <button
              key={s.value}
              onClick={() => setStage(s.value)}
              className={clsx("chip whitespace-nowrap px-3 py-1.5 text-sm", c.stage === s.value ? "bg-brand text-white border-brand" : s.value < c.stage ? "bg-brand/10 text-brand border-brand/20" : "")}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        <button className="card py-3 flex flex-col items-center gap-1 text-xs" onClick={() => contacted.mutate(c.contact_method || "Email")}>
          <Check size={18} className="text-brand" /> Contacted
        </button>
        <button className="card py-3 flex flex-col items-center gap-1 text-xs" onClick={() => setNudgeOpen(true)}>
          <MessageCircle size={18} className="text-brand" /> Nudge
        </button>
        <button className="card py-3 flex flex-col items-center gap-1 text-xs" onClick={() => setCallPrompt(true)}>
          <Phone size={18} className="text-brand" /> Call date
        </button>
        {c.investor_id ? (
          <button
            className="card py-3 flex flex-col items-center gap-1 text-xs"
            onClick={async () => {
              try {
                const s = await api<{ id: string }>("/sequences", { method: "POST", json: { investor_id: c.investor_id } });
                router.push(`/app/sequences/${s.id}`);
              } catch (e) {
                toast(errText(e), "err");
              }
            }}
          >
            <Sparkles size={18} className="text-brand" /> Draft
          </button>
        ) : (
          <a className="card py-3 flex flex-col items-center gap-1 text-xs" href={c.email ? `mailto:${c.email}` : undefined} aria-disabled={!c.email}>
            <Send size={18} className={c.email ? "text-brand" : "text-muted"} /> Email
          </a>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4">
        <div className="space-y-4">
          {/* Notes */}
          <div className="card p-4">
            <h2 className="font-semibold mb-2">Add a note</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (note.trim()) addNote.mutate();
              }}
              className="space-y-2"
            >
              <textarea className="textarea min-h-20" placeholder='e.g. "Asked for the deck, follow up Thursday. Intro via Sam"' value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted">Dates become reminders automatically.</span>
                <button className="btn-primary btn-sm" disabled={!note.trim() || addNote.isPending}>
                  Save note
                </button>
              </div>
            </form>
            {suggestions.length > 0 && (
              <div className="mt-3 space-y-2">
                {suggestions.map((s) => (
                  <div key={s.field + s.value} className="flex items-center gap-2 rounded-lg border border-brand/30 bg-brand/5 p-2.5 text-sm">
                    <Sparkles size={14} className="text-brand shrink-0" />
                    <span className="flex-1">
                      {s.reason}: set {s.field.replace(/_/g, " ")} to <b>{s.field === "stage" ? meta.data?.stages[Number(s.value) - 1]?.label : String(s.value)}</b>?
                    </span>
                    <button className="btn-primary btn-sm" onClick={() => applySuggestion(s)}>
                      Apply
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {(c.stage >= 3 || c.call_at) && <MeetingBrief cardId={c.id} />}
          <RoomActivity cardId={c.id} />

          {c.reminders.length > 0 && (
            <div className="card p-4">
              <h2 className="font-semibold mb-2 flex items-center gap-2">
                <Bell size={16} /> Reminders
              </h2>
              {c.reminders.map((r) => (
                <div key={r.id} className="flex items-center gap-2 py-2 border-b border-line last:border-0 text-sm">
                  <div className="flex-1 min-w-0">
                    <div className="truncate">{r.title}</div>
                    <div className="text-xs text-muted">{fmtDate(r.due_at, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
                  </div>
                  <button className="btn-ghost btn-sm" onClick={() => reminderAct.mutate({ rid: r.id, action: "snooze" })}>
                    Snooze
                  </button>
                  <button className="btn-ghost btn-sm" onClick={() => reminderAct.mutate({ rid: r.id, action: "done" })}>
                    Done
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="card p-4">
            <h2 className="font-semibold mb-2">Timeline</h2>
            <ol className="space-y-3">
              {c.events.map((e) => (
                <li key={e.id} className="flex gap-3">
                  <span className={clsx("mt-1.5 w-2 h-2 rounded-full shrink-0", e.kind === "note" ? "bg-brand" : e.kind === "reply" ? "bg-green-500" : "bg-line")} />
                  <div className="min-w-0">
                    <div className={clsx("text-sm whitespace-pre-wrap break-words", e.kind !== "note" && e.kind !== "reply" && "text-muted")}>
                      {e.kind === "reply" && <b className="text-green-700 dark:text-green-400">Reply: </b>}
                      {e.body}
                    </div>
                    <div className="text-xs text-muted">{timeAgo(e.created_at)}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>

        {/* Fields */}
        <form
          className="card p-4 space-y-3 h-fit"
          onSubmit={(e) => {
            e.preventDefault();
            const body = Object.fromEntries(EDITABLE.filter((k) => (form[k] ?? "") !== (c[k] ?? "")).map((k) => [k, form[k] === "" && (k === "next_contact_date" || k === "call_at") ? null : form[k]]));
            patch.mutate(body);
          }}
        >
          <h2 className="font-semibold">Details</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name">
              <input className="input" value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="Firm">
              <input className="input" value={form.firm ?? ""} onChange={(e) => set("firm", e.target.value)} />
            </Field>
            <Field label="Status">
              <select className="input" value={form.status ?? ""} onChange={(e) => set("status", e.target.value)}>
                {meta.data?.statuses.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Priority">
              <select className="input" value={form.priority ?? ""} onChange={(e) => set("priority", e.target.value)}>
                {meta.data?.priorities.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Investor type">
              <select className="input" value={form.investor_type ?? ""} onChange={(e) => set("investor_type", e.target.value)}>
                <option value="">—</option>
                {meta.data?.types.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Can lead?">
              <select className="input" value={form.can_lead ?? ""} onChange={(e) => set("can_lead", e.target.value)}>
                <option value="">—</option>
                {meta.data?.can_lead.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Ticket size">
              <input className="input" value={form.ticket_size ?? ""} onChange={(e) => set("ticket_size", e.target.value)} placeholder="$50K" />
            </Field>
            <Field label="Agreed size">
              <input className="input" value={form.agreed_size ?? ""} onChange={(e) => set("agreed_size", e.target.value)} />
            </Field>
            <Field label="Instrument">
              <select className="input" value={form.instrument ?? ""} onChange={(e) => set("instrument", e.target.value)}>
                <option value="">—</option>
                {meta.data?.instruments.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Contact method">
              <select className="input" value={form.contact_method ?? ""} onChange={(e) => set("contact_method", e.target.value)}>
                <option value="">—</option>
                {meta.data?.contact_methods.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Email">
            <input className="input" type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label="Referrer / who is introducing">
            <input className="input" value={form.referrer ?? ""} onChange={(e) => set("referrer", e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Next contact date">
              <input className="input" type="date" value={form.next_contact_date ?? ""} onChange={(e) => set("next_contact_date", e.target.value)} />
            </Field>
            <Field label="Last contacted">
              <input className="input" disabled value={fmtDate(c.last_contacted_at, { day: "numeric", month: "short", year: "numeric" }) || "—"} />
            </Field>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 accent-[var(--brand)]" checked={Boolean(form.shareable)} onChange={(e) => setForm((f) => ({ ...f, shareable: e.target.checked }))} />
            <span>
              OK to name in round updates <span className="text-muted block text-xs">Only tick this once they have agreed to be named publicly.</span>
            </span>
          </label>
          <div className="flex gap-2 pt-1">
            <button className="btn-primary flex-1" disabled={!dirty || patch.isPending}>
              Save changes
            </button>
            <button
              type="button"
              className="btn-ghost text-danger"
              aria-label="Delete card"
              onClick={() => {
                if (confirm(`Remove ${c.name} from your funnel?`)) del.mutate();
              }}
            >
              <Trash2 size={16} />
            </button>
          </div>
        </form>
      </div>

      <Sheet open={nudgeOpen} onClose={() => setNudgeOpen(false)} title="Short message">
        {nudge.isLoading && <ListSkeleton rows={2} />}
        {nudge.data && (
          <div className="space-y-4">
            {(["whatsapp", "linkedin"] as const).map((k) => (
              <div key={k}>
                <div className="label">{k === "whatsapp" ? "WhatsApp / SMS" : "LinkedIn DM"}</div>
                <div className="rounded-lg border border-line p-3 text-sm">{nudge.data[k]}</div>
                <div className="flex gap-2 mt-2">
                  <button className="btn-ghost btn-sm" onClick={() => copy(nudge.data[k])}>
                    <Copy size={14} /> Copy
                  </button>
                  <button
                    className="btn-primary btn-sm"
                    onClick={() => {
                      contacted.mutate(k === "whatsapp" ? "WhatsApp" : "LinkedIn");
                      setNudgeOpen(false);
                    }}
                  >
                    <Check size={14} /> Mark as sent
                  </button>
                </div>
              </div>
            ))}
            <p className="text-xs text-muted">We don't send WhatsApp or LinkedIn messages for you. Copy, send from your phone, then mark as sent.</p>
          </div>
        )}
      </Sheet>

      <Sheet open={callPrompt} onClose={() => setCallPrompt(false)} title="When is the call?">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (callAt) patch.mutate({ call_at: new Date(callAt).toISOString(), ...(c.stage < 4 ? { stage: 4 } : {}) });
            setCallPrompt(false);
          }}
        >
          <input className="input" type="datetime-local" value={callAt || toLocalInput(c.call_at)} onChange={(e) => setCallAt(e.target.value)} required />
          <p className="text-xs text-muted">We'll remind you 24 hours before with time to prep.</p>
          <button className="btn-primary w-full">Save call</button>
        </form>
      </Sheet>
    </div>
  );
}

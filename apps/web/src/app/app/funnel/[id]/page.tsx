"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Bell, Check, Copy, ExternalLink, MessageCircle, Pencil, Phone, Send, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useEffect, useState } from "react";
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
  const [editing, setEditing] = useState(false);
  const [allActivity, setAllActivity] = useState(false);

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
  const pill = (active: boolean) => clsx("chip px-3 py-1.5 text-sm", active ? "bg-brand text-white border-brand" : "hover:border-brand");
  const timeline = [...c.events]
    .filter((e) => allActivity || e.kind === "note" || e.kind === "reply")
    .sort((x, y) => y.created_at.localeCompare(x.created_at));

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
        <ArrowLeft size={16} /> Investor tracker
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

      {/* Quick update: the things that change after every touch */}
      <div className="card p-4 mb-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[auto_auto_1fr] gap-4 md:gap-6">
          <div>
            <div className="label">Status</div>
            <div className="flex flex-wrap gap-1.5">
              {meta.data?.statuses.map((s) => (
                <button key={s} type="button" className={pill(c.status === s)} disabled={patch.isPending} onClick={() => c.status !== s && patch.mutate({ status: s })}>
                  {s === "Rejection" ? "Rejected" : s}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="label">Priority</div>
            <div className="flex flex-wrap gap-1.5">
              {meta.data?.priorities.map((p) => (
                <button key={p} type="button" className={pill(c.priority === p)} disabled={patch.isPending} onClick={() => c.priority !== p && patch.mutate({ priority: p })}>
                  {p}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="label" htmlFor="next-contact">
              Next contact
            </label>
            <div className="flex items-center gap-2">
              <input
                id="next-contact"
                className="input w-auto"
                type="date"
                value={c.next_contact_date ?? ""}
                onChange={(e) => patch.mutate({ next_contact_date: e.target.value || null })}
              />
              <span className="text-xs text-muted">Last contacted {c.last_contacted_at ? timeAgo(c.last_contacted_at) : "never"}</span>
            </div>
          </div>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (note.trim()) addNote.mutate();
          }}
        >
          <label className="label" htmlFor="note">
            Add a note
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <textarea id="note" className="textarea min-h-16 flex-1" placeholder='e.g. "Asked for the deck, follow up Thursday. Intro via Sam"' value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="btn-primary sm:self-end" disabled={!note.trim() || addNote.isPending}>
              Save note
            </button>
          </div>
          <span className="text-xs text-muted">Dates in a note become reminders automatically.</span>
        </form>
        {suggestions.length > 0 && (
          <div className="space-y-2">
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
        <div className="flex flex-wrap gap-2 pt-3 border-t border-line">
          <button className="btn-ghost btn-sm" onClick={() => contacted.mutate(c.contact_method || "Email")}>
            <Check size={15} className="text-brand" /> Mark contacted
          </button>
          <button className="btn-ghost btn-sm" onClick={() => setNudgeOpen(true)}>
            <MessageCircle size={15} className="text-brand" /> Nudge
          </button>
          <button className="btn-ghost btn-sm" onClick={() => setCallPrompt(true)}>
            <Phone size={15} className="text-brand" /> {c.call_at ? `Call ${fmtDate(c.call_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : "Set call date"}
          </button>
          {c.investor_id ? (
            <button
              className="btn-ghost btn-sm"
              onClick={async () => {
                try {
                  const s = await api<{ id: string }>("/sequences", { method: "POST", json: { investor_id: c.investor_id } });
                  router.push(`/app/sequences/${s.id}?new=1`);
                } catch (e) {
                  toast(errText(e), "err");
                }
              }}
            >
              <Sparkles size={15} className="text-brand" /> Draft emails
            </button>
          ) : (
            c.email && (
              <a className="btn-ghost btn-sm" href={`mailto:${c.email}`}>
                <Send size={15} className="text-brand" /> Email
              </a>
            )
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-4">
        <div className="space-y-4 order-2 lg:order-1">
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
        </div>

        <div className="flex flex-col gap-4 order-1 lg:order-2">
          {/* Details: read-only until the pencil is pressed */}
          {!editing ? (
            <div className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold">Details</h2>
                <button className="p-1.5 rounded-lg text-muted hover:text-brand hover:bg-brand/5" aria-label="Edit details" title="Edit details" onClick={() => setEditing(true)}>
                  <Pencil size={16} />
                </button>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                {[
                  ["Name", c.name],
                  ["Firm", c.firm],
                  ["Investor type", c.investor_type],
                  ["Email", c.email],
                  ["Contact method", c.contact_method],
                  ["Can lead", c.can_lead],
                  ["Ticket size", c.ticket_size],
                  ["Agreed size", c.agreed_size],
                  ["Instrument", c.instrument],
                  ["Introduced by", c.referrer],
                  ["Named in updates", c.shareable ? "Yes" : "No"],
                ].map(([k, v]) => (
                  <Fragment key={k}>
                    <dt className="text-muted">{k}</dt>
                    <dd className="min-w-0 break-words">{v || <span className="text-muted">—</span>}</dd>
                  </Fragment>
                ))}
              </dl>
            </div>
          ) : (
            <form
              className="card p-4 space-y-3 h-fit"
              onSubmit={(e) => {
                e.preventDefault();
                const body = Object.fromEntries(EDITABLE.filter((k) => (form[k] ?? "") !== (c[k] ?? "")).map((k) => [k, form[k] === "" && (k === "next_contact_date" || k === "call_at") ? null : form[k]]));
                patch.mutate(body, { onSuccess: () => setEditing(false) });
              }}
            >
              <h2 className="font-semibold">Edit details</h2>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Name">
                  <input className="input" value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} />
                </Field>
                <Field label="Firm">
                  <input className="input" value={form.firm ?? ""} onChange={(e) => set("firm", e.target.value)} />
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
                  className="btn-ghost"
                  onClick={() => {
                    setForm(Object.fromEntries(EDITABLE.map((k) => [k, c[k]])) as Partial<Card>);
                    setEditing(false);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn-ghost text-danger"
                  aria-label="Delete card"
                  onClick={() => {
                    if (confirm(`Remove ${c.name} from your investor tracker?`)) del.mutate();
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </form>
          )}

          {/* Timeline: notes first, newest at the top (shown above the details) */}
          <div className="card p-4 order-first">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">Timeline</h2>
              <button className="text-xs text-brand" onClick={() => setAllActivity((x) => !x)}>
                {allActivity ? "Notes only" : "Show all activity"}
              </button>
            </div>
            {timeline.length === 0 ? (
              <p className="text-sm text-muted">No notes yet. Add one above after each conversation.</p>
            ) : (
              <ol className="relative border-l border-line ml-1 space-y-4">
                {timeline.map((e) => (
                  <li key={e.id} className="pl-4 relative">
                    <span className={clsx("absolute -left-[5px] top-1.5 w-2.5 h-2.5 rounded-full ring-2 ring-card", e.kind === "note" ? "bg-brand" : e.kind === "reply" ? "bg-green-500" : "bg-line")} />
                    <div className="text-xs text-muted">{fmtDate(e.created_at, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</div>
                    <div className={clsx("text-sm whitespace-pre-wrap break-words mt-0.5", e.kind !== "note" && e.kind !== "reply" && "text-muted")}>
                      {e.kind === "reply" && <b className="text-green-700">Reply: </b>}
                      {e.body}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
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

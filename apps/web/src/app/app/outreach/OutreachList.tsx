"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check, CheckCircle2, Eye, MailPlus, RefreshCw, Search, Send, Trash2, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { from } from "@/components/Crumbs";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ListSearch, matches } from "@/components/ListSearch";
import { ConfirmSend, type SendPreview } from "@/components/ConfirmSend";
import { Empty, IconBtn, ListSkeleton, Sheet, errText, useToast } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";
import { BulkBar } from "./BulkBar";

/** A draft with nothing blocking it. Falls back to "draft without a blocker" if the API hasn't sent `ready`. */
const isReady = (x: Item) => x.ready ?? (x.status === "draft" && !x.blocker);

const STATUS_FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "draft", label: "Draft", test: (x: Item) => x.status === "draft" && !isReady(x) },
  { key: "ready", label: "Ready to send", test: isReady },
  { key: "scheduled", label: "Scheduled", test: (x: Item) => Boolean(x.next_at) },
  { key: "seen", label: "Seen", test: (x: Item) => Boolean(x.seen) },
  { key: "replied", label: "Replied", test: (x: Item) => Boolean(x.replied) },
] as const;
type StatusKey = (typeof STATUS_FILTERS)[number]["key"];
const UNKNOWN = "__unknown";

type Item = {
  id: string;
  status: string;
  blocker: string | null;
  sent: number;
  next_at: string | null;
  created_at: string;
  email?: string;
  investor: { id: string; name: string; firm: string };
  country?: string;
  seen?: boolean;
  replied?: boolean;
  ready?: boolean;
  drafting?: boolean;
};
type List = { auto_send: boolean; auto_send_when?: "window" | "now"; items: Item[] };
type Bulk = { needs_confirm: true; from: string; ready: { id: string; name: string; to: string }[]; skipped: { id: string; name: string; reason: string }[] };

function statusText(x: Item) {
  if (x.status === "draft") return x.blocker ? "Needs attention" : "Ready to send";
  if (x.status === "stopped") return "Stopped";
  if (x.next_at) return `${x.sent} of 3 sent · next ${fmtDate(x.next_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
  return x.sent ? `${x.sent} of 3 sent` : "Scheduled";
}

/** One-by-one send: the same confirm screen as the sequence page. */
function SendOne({ x }: { x: Item }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [preview, setPreview] = useState<SendPreview | null>(null);
  const m = useMutation({
    mutationFn: (confirm: boolean) => api(`/sequences/${x.id}/approve`, { method: "POST", json: { confirm } }),
    onSuccess: () => {
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      qc.invalidateQueries({ queryKey: ["outreach-stats"] });
      toast(`Scheduled for ${x.investor.name}. Sends in their local send window and stops on any reply.`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.problem.needs_confirm) setPreview(e.problem.preview as SendPreview);
      else toast(errText(e), "err");
    },
  });
  return (
    <>
      <IconBtn label="Send: check sender, recipient and times, then confirm" tone="brand" disabled={m.isPending} onClick={() => m.mutate(false)}>
        <Send size={14} />
      </IconBtn>
      <ConfirmSend preview={preview} busy={m.isPending} onCancel={() => setPreview(null)} onConfirm={() => m.mutate(true)} />
    </>
  );
}

function AutoSend({ on, when = "window" }: { on: boolean; when?: "window" | "now" }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const save = useMutation({
    mutationFn: (v: boolean) => api("/workspace", { method: "PATCH", json: { auto_send: v } }),
    onSuccess: (_, v) => {
      setAsking(false);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      toast(v ? "Auto-send is on" : "Back to sending one by one");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const timing = useMutation({
    mutationFn: (v: "window" | "now") => api("/workspace", { method: "PATCH", json: { auto_send_when: v } }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["sequences"] });
      toast(v === "now" ? "Auto-send now emails new investors as soon as they're added" : "Auto-send now uses each investor's morning send window");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const opt = (active: boolean, title: string, body: string, onClick: () => void, icon: React.ReactNode) => (
    <button type="button" onClick={onClick} className={clsx("flex-1 text-left rounded-xl border p-3 transition-colors", active ? "border-brand bg-brand/5" : "border-line hover:border-brand/50")}>
      <div className="flex items-center gap-2 font-semibold text-sm">
        {icon} {title}
        {active && <CheckCircle2 size={15} className="text-brand ml-auto" />}
      </div>
      <p className="text-xs text-muted mt-1">{body}</p>
    </button>
  );
  return (
    <div className="card p-4 mb-4">
      <div className="font-semibold mb-2">How should emails go out?</div>
      <div className="flex flex-col sm:flex-row gap-2">
        {opt(!on, "One by one", "You review each investor's emails and press Send, or send all ready ones at once.", () => on && save.mutate(false), <Send size={15} />)}
        {opt(on, "Auto-send", when === "now" ? "Every investor you add to outreach is emailed automatically from your Gmail, a couple of minutes after you add them." : "Every investor you add to outreach is emailed automatically from your Gmail, in their send window.", () => !on && setAsking(true), <Zap size={15} />)}
      </div>
      {on && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm" role="radiogroup" aria-label="When auto-send sends email 1">
          <span className="text-xs text-muted">Email 1 goes</span>
          {([
            ["window", "In their morning send window", "Tue–Thu morning, investor's local time (recommended)"],
            ["now", "As soon as added", "About 2 minutes after you add them, any day and time"],
          ] as const).map(([k, t, sub]) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={when === k}
              title={sub}
              disabled={timing.isPending}
              onClick={() => when !== k && timing.mutate(k)}
              className={clsx("rounded-full border px-3 py-1 text-xs", when === k ? "border-brand bg-brand/10 text-brand font-medium" : "border-line text-muted hover:border-brand/50")}
            >
              {t}
            </button>
          ))}
          <span className="text-[11px] text-muted basis-full">Follow-ups go 2 working days apart either way, and every sequence stops on a reply.</span>
        </div>
      )}
      <Sheet open={asking} onClose={() => setAsking(false)} title="Turn on auto-send?">
        <ul className="text-sm space-y-2 list-disc pl-5">
          <li>From now on, when you add an investor to outreach, their 3 emails are drafted and scheduled straight away. You won&apos;t review them first.</li>
          <li>Emails go from your connected Gmail, within your daily limit. Email 1 goes in the investor&apos;s local morning send window by default; you can switch to &ldquo;As soon as added&rdquo; after turning it on.</li>
          <li>Each sequence stops as soon as the investor replies. Drafts already on your list are not sent; use Send all for those.</li>
        </ul>
        <div className="flex gap-2 mt-4">
          <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate(true)}>
            <Zap size={16} /> Turn on auto-send
          </button>
          <button className="btn-ghost" onClick={() => setAsking(false)}>
            Cancel
          </button>
        </div>
      </Sheet>
    </div>
  );
}

export function OutreachList() {
  const qc = useQueryClient();
  const toast = useToast();
  // After a bulk regenerate, poll for ~60s so the rewritten drafts show up without a reload.
  const pollUntil = useRef(0);
  const q = useQuery<List>({
    queryKey: ["sequences"],
    queryFn: () => api("/sequences"),
    // While drafts are being rewritten, refresh every few seconds so each row comes back as soon as it's done.
    refetchInterval: (query) => (query.state.data?.items.some((x) => x.drafting) || Date.now() < pollUntil.current ? 2500 : false),
  });
  // Bulk regenerate progress: the rows queued in this batch, and the ones that have finished since.
  const [regen, setRegen] = useState<string[]>([]);
  const drafting = (q.data?.items ?? []).filter((x) => x.drafting);
  const regenDone = regen.filter((id) => !drafting.some((x) => x.id === id));
  useEffect(() => {
    if (regen.length && regenDone.length === regen.length) {
      toast(`All ${regen.length} draft${regen.length === 1 ? "" : "s"} rewritten. Preview and Send are ready.`);
      setRegen([]);
    }
  }, [regen, regenDone.length, toast]);
  const [find, setFind] = useState("");
  const [status, setStatus] = useState<StatusKey>("all");
  const [country, setCountry] = useState("all");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const allRef = useRef<HTMLInputElement>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const router = useRouter();
  const remove = useMutation({
    mutationFn: (x: Item) => api<{ kept_history: boolean }>(`/sequences/${x.id}`, { method: "DELETE" }),
    onSuccess: (r, x) => {
      setRemoving(null);
      for (const k of ["sequences", "upcoming", "outreach-stats", "investors", "investor"]) qc.invalidateQueries({ queryKey: [k] });
      toast(r.kept_history ? `${x.investor.name} removed. Sent emails stay in Activity.` : `${x.investor.name} removed from outreach.`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const [bulk, setBulk] = useState<Bulk | null>(null);
  const preview = useMutation({
    mutationFn: () => api<Bulk>("/sequences/send-all", { method: "POST", json: { confirm: false } }),
    onSuccess: setBulk,
    onError: (e) => toast(errText(e), "err"),
  });
  const sendAll = useMutation({
    mutationFn: () => api<{ scheduled: number; skipped: unknown[] }>("/sequences/send-all", { method: "POST", json: { confirm: true } }),
    onSuccess: (r) => {
      setBulk(null);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      qc.invalidateQueries({ queryKey: ["outreach-stats"] });
      toast(`Scheduled ${r.scheduled} investor${r.scheduled === 1 ? "" : "s"}${r.skipped.length ? `. ${r.skipped.length} still need attention` : ""}.`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  // The outreach agent's "send all" button lands here with ?send_all=1: open the same confirm screen.
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current || !q.data) return;
    if (new URLSearchParams(window.location.search).get("send_all")) {
      asked.current = true;
      preview.mutate();
    }
  }, [q.data, preview]);
  const items = useMemo(() => (q.data?.items ?? []).filter((x) => x.status !== "stopped"), [q.data]);
  const statusCounts = useMemo(() => Object.fromEntries(STATUS_FILTERS.map((f) => [f.key, items.filter(f.test).length])) as Record<StatusKey, number>, [items]);
  const countries = useMemo(() => {
    const n = new Map<string, number>();
    for (const x of items) {
      const c = x.country?.trim() || UNKNOWN;
      n.set(c, (n.get(c) ?? 0) + 1);
    }
    const known = [...n.entries()].filter(([c]) => c !== UNKNOWN).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return { known, unknown: n.get(UNKNOWN) ?? 0 };
  }, [items]);
  const statusTest = STATUS_FILTERS.find((f) => f.key === status)?.test ?? (() => true);
  const shown = items.filter(
    (x) => matches(find, x.investor.name, x.investor.firm, x.email) && statusTest(x) && (country === "all" || (x.country?.trim() || UNKNOWN) === country),
  );
  const selected = items.filter((x) => picked.has(x.id));
  const pickedShown = shown.filter((x) => picked.has(x.id)).length;
  const allShown = shown.length > 0 && pickedShown === shown.length;
  useEffect(() => {
    if (allRef.current) allRef.current.indeterminate = pickedShown > 0 && !allShown;
  });
  const toggle = (id: string) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const toggleAll = () =>
    setPicked((p) => {
      const n = new Set(p);
      for (const x of shown) {
        if (allShown) n.delete(x.id);
        else n.add(x.id);
      }
      return n;
    });
  const filtered = Boolean(find) || status !== "all" || country !== "all";
  if (q.isLoading) return <ListSkeleton rows={4} />;
  const drafts = items.filter((x) => x.status === "draft");
  const ready = drafts.filter((x) => !x.blocker).length;
  return (
    <>
      <AutoSend on={Boolean(q.data?.auto_send)} when={q.data?.auto_send_when} />
      {items.length === 0 ? (
        <Empty
          icon={<MailPlus size={28} />}
          title="Your outreach list is empty"
          body="Tap the envelope icon on any investor to add them. Their emails are drafted for you."
          action={
            <Link href="/app/investors" className="btn-primary">
              <Search size={16} /> Find investors
            </Link>
          }
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 px-4 py-3 bg-surface/60 border-b border-line">
            <div className="text-sm flex-1">
              <b>{items.length}</b> in outreach · {drafts.length} not sent yet{drafts.length > ready ? ` · ${drafts.length - ready} need attention` : ""}
            </div>
            {drafts.length > 0 && (
              <button className="btn-primary btn-sm" disabled={!ready || preview.isPending} onClick={() => preview.mutate()}>
                <Send size={14} /> Send all ready ({ready})
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-line">
            <input
              ref={allRef}
              type="checkbox"
              className="h-4 w-4 accent-[var(--brand)] shrink-0"
              checked={allShown}
              disabled={!shown.length}
              onChange={toggleAll}
              aria-label={allShown ? "Unselect all shown" : "Select all shown"}
            />
            <ListSearch value={find} onChange={setFind} className="flex-1 min-w-[10rem] max-w-xs" />
            <select className="input h-8 text-sm w-auto py-0" value={status} onChange={(e) => setStatus(e.target.value as StatusKey)} aria-label="Filter by status">
              {STATUS_FILTERS.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label} ({statusCounts[f.key]})
                </option>
              ))}
            </select>
            {(countries.known.length > 0 || country !== "all") && (
              <select className="input h-8 text-sm w-auto py-0" value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Filter by country">
                <option value="all">All countries ({items.length})</option>
                {countries.known.map(([c, n]) => (
                  <option key={c} value={c}>
                    {c} ({n})
                  </option>
                ))}
                {countries.unknown > 0 && <option value={UNKNOWN}>Unknown ({countries.unknown})</option>}
              </select>
            )}
          </div>
          {selected.length > 0 && (
            <BulkBar
              ids={{
                send: selected.filter(isReady).map((x) => x.id),
                regenerate: selected.filter((x) => x.status === "draft").map((x) => x.id),
                remove: selected.map((x) => x.id),
              }}
              onClear={() => setPicked(new Set())}
              busy={drafting.length > 0}
              onRegenerated={(ids) => {
                pollUntil.current = Date.now() + 10_000;
                setRegen(ids);
                q.refetch();
              }}
            />
          )}
          {drafting.length > 0 && (
            <div className="px-4 py-2.5 border-b border-line bg-brand/5 text-sm" role="status" aria-live="polite">
              <div className="flex items-center gap-2">
                <RefreshCw size={14} className="animate-spin text-brand" />
                <span className="flex-1">
                  {regen.length
                    ? `Rewriting drafts: ${regenDone.length} of ${regen.length} done`
                    : `Rewriting ${drafting.length} draft${drafting.length === 1 ? "" : "s"}…`}
                </span>
                <span className="text-xs text-muted hidden sm:inline">Each row unlocks when its new emails are ready</span>
              </div>
              {regen.length > 0 && (
                <div className="mt-2 h-1.5 rounded-full bg-line overflow-hidden">
                  <div className="h-full bg-brand transition-all duration-500" style={{ width: `${Math.round((regenDone.length / regen.length) * 100)}%` }} />
                </div>
              )}
            </div>
          )}
          <div className="divide-y divide-line">
            {filtered && shown.length === 0 && (
              <p className="px-4 py-6 text-sm text-muted text-center">
                {find ? <>No one on your outreach list matches &ldquo;{find}&rdquo; with these filters.</> : "No one on your outreach list matches these filters."}
              </p>
            )}
            {shown.map((x) => (
              <div key={x.id} className="flex items-center gap-3 px-4 py-3">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[var(--brand)] shrink-0"
                  checked={picked.has(x.id)}
                  disabled={x.drafting}
                  onChange={() => toggle(x.id)}
                  aria-label={`Select ${x.investor.name}`}
                />
                <Link href={from(`/app/sequences/${x.id}`, "outreach")} className="flex-1 min-w-0">
                  <div className="font-medium truncate">{x.investor.name}</div>
                  <div className="text-xs text-muted truncate">{x.investor.firm}</div>
                  {x.blocker && (
                    <div className="text-xs text-warn flex items-center gap-1 mt-0.5">
                      <AlertTriangle size={12} /> {x.blocker}
                    </div>
                  )}
                </Link>
                {x.drafting ? (
                  <span className="chip text-xs text-brand border-brand/40 inline-flex items-center gap-1">
                    <RefreshCw size={12} className="animate-spin" /> Rewriting…
                  </span>
                ) : regen.includes(x.id) ? (
                  <span className="chip text-xs text-emerald-700 border-emerald-600/30 inline-flex items-center gap-1">
                    <Check size={12} /> New draft ready
                  </span>
                ) : (
                  <span className={clsx("chip text-xs hidden sm:inline-flex", x.status === "draft" && !x.blocker && "text-brand border-brand/40", x.status !== "draft" && "text-emerald-700 border-emerald-600/30")}>{statusText(x)}</span>
                )}
                {x.drafting ? (
                  <span className="inline-flex items-center gap-1.5 opacity-50" aria-hidden>
                    <IconBtn label="Being rewritten" disabled onClick={() => {}}>
                      <Eye size={14} />
                    </IconBtn>
                    <IconBtn label="Being rewritten" disabled onClick={() => {}}>
                      <Trash2 size={14} />
                    </IconBtn>
                  </span>
                ) : removing === x.id ? (
                  <span className="inline-flex flex-wrap items-center gap-1.5 text-xs">
                    <span>{x.sent ? `Remove ${x.investor.name}? Unsent emails are cancelled; sent ones stay in Activity.` : `Remove ${x.investor.name} from outreach?`}</span>
                    <button className="btn-ghost btn-sm text-warn" disabled={remove.isPending} onClick={() => remove.mutate(x)}>
                      {remove.isPending ? "Removing…" : "Yes, remove"}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => setRemoving(null)}>No</button>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5">
                    <IconBtn label="Review and edit the emails" onClick={() => router.push(from(`/app/sequences/${x.id}`, "outreach"))}>
                      <Eye size={14} />
                    </IconBtn>
                    {x.status === "draft" && !x.blocker && <SendOne x={x} />}
                    <IconBtn label="Remove from outreach" tone="danger" onClick={() => setRemoving(x.id)}>
                      <Trash2 size={14} />
                    </IconBtn>
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      <Sheet open={Boolean(bulk)} onClose={() => setBulk(null)} title="Send to everyone ready?">
        {bulk && (
          <div className="text-sm space-y-3">
            <p>
              From <b>{bulk.from}</b> (your Gmail). Each investor gets 3 emails in their local send window. Each sequence stops on any reply.
            </p>
            <div>
              <div className="font-semibold mb-1">Will be scheduled ({bulk.ready.length})</div>
              <ul className="space-y-0.5">
                {bulk.ready.map((r) => (
                  <li key={r.id}>
                    {r.name} <span className="text-muted">· {r.to}</span>
                  </li>
                ))}
              </ul>
            </div>
            {bulk.skipped.length > 0 && (
              <div>
                <div className="font-semibold mb-1">Skipped ({bulk.skipped.length})</div>
                <ul className="space-y-0.5 text-muted">
                  {bulk.skipped.map((r) => (
                    <li key={r.id}>
                      {r.name}: {r.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex gap-2 pt-1">
              <button className="btn-primary" disabled={!bulk.ready.length || sendAll.isPending} onClick={() => sendAll.mutate()}>
                <Send size={16} /> Confirm and schedule {bulk.ready.length}
              </button>
              <button className="btn-ghost" onClick={() => setBulk(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </Sheet>
    </>
  );
}

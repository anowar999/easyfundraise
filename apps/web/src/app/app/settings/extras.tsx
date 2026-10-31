"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Copy, Laptop, Mail, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useMe } from "@/components/AppShell";
import { Field, ListSkeleton, errText, useToast } from "@/components/ui";
import { api, fmtDate, setWorkspace } from "@/lib/api";

type Gmail = { connected: boolean; status?: string; email?: string; mode?: string; sent_today?: number; daily_cap?: number; fake_available: boolean; calendar?: boolean };

/** GML-01: progressive consent. We only ask for Gmail when the founder wants to send. */
export function GmailSection() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<Gmail>({ queryKey: ["gmail"], queryFn: () => api("/gmail") });
  const off = useMutation({
    mutationFn: () => api("/gmail", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gmail"] }),
    onError: (e) => toast(errText(e), "err"),
  });
  if (!q.data) return <ListSkeleton rows={1} />;
  const g = q.data;
  if (!g.connected)
    return (
      <div className="space-y-2 text-sm">
        {g.status === "revoked" && <p className="text-warn">Gmail access was removed. Reconnect to keep sending.</p>}
        <p className="text-muted">Emails go out from your own Gmail, so replies land in your inbox. We ask to send and to read replies to emails we sent, nothing else.</p>
        <a className="btn-primary" href="/api/gmail/connect">
          <Mail size={16} /> Connect Gmail{g.fake_available ? " (test mailbox)" : ""}
        </a>
      </div>
    );
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip bg-green-500/10 text-green-700 border-green-600/30">Connected</span>
        <b>{g.email}</b>
        {g.mode === "fake" && <span className="chip">test mailbox</span>}
      </div>
      <p className="text-muted">
        Sent today: {g.sent_today} of {g.daily_cap}. New mailboxes warm up over 10 days, and we send at most 3 a day to any one firm.
      </p>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
        <CalendarDays size={16} className="text-brand" />
        <span className="flex-1 min-w-48">
          <b>Google Calendar</b>
          <span className="block text-muted">Read-only. Your Raise Agent spots investor meetings and preps you for them.</span>
        </span>
        {g.calendar ? (
          <span className="chip bg-green-500/10 text-green-700 border-green-600/30">Connected</span>
        ) : (
          <a className="btn-ghost btn-sm" href="/api/gmail/connect?calendar=1&next=/app/settings">
            Connect calendar
          </a>
        )}
      </div>
      <button className="btn-ghost btn-sm text-danger" onClick={() => confirm("Disconnect Gmail? Scheduled emails will wait until you reconnect.") && off.mutate()}>
        Disconnect
      </button>
    </div>
  );
}

type WsSettings = { tracking_enabled: boolean; consent_level: string; automations: Record<string, boolean>; ai: boolean };
const AUTOMATION_TEXT: Record<string, string> = {
  positive_reply: "Move a card to Engaged when an investor replies with interest",
  rejection_suggestion: "Suggest marking a card as rejected when the reply is a pass",
  ghosting_suggestion: "Remind me a week after the last follow-up gets no reply",
  call_brief: "Prepare a meeting brief the day before a call",
};

export function OutreachSettings() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<WsSettings>({ queryKey: ["workspace"], queryFn: () => api("/workspace") });
  const save = useMutation({
    mutationFn: (body: Partial<WsSettings>) => api("/workspace", { method: "PATCH", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspace"] }),
    onError: (e) => toast(errText(e), "err"),
  });
  if (!q.data) return <ListSkeleton rows={2} />;
  const w = q.data;
  return (
    <div className="space-y-4 text-sm">
      <label className="flex items-start gap-2">
        <input type="checkbox" className="mt-0.5 accent-[var(--brand)]" checked={w.tracking_enabled} onChange={(e) => save.mutate({ tracking_enabled: e.target.checked })} />
        <span>
          Track opens <span className="block text-xs text-muted">Adds a tiny image to each email. Opens are a hint, not proof: some mail apps load images automatically.</span>
        </span>
      </label>
      <Field label="When emails need my approval">
        <select className="input" value={w.consent_level} onChange={(e) => save.mutate({ consent_level: e.target.value })}>
          <option value="approved_sequences">Approve each sequence once, then follow-ups go automatically</option>
          <option value="ask_every_send">Ask me before every single email</option>
        </select>
      </Field>
      <div className="space-y-2">
        <div className="label">Automations</div>
        {Object.entries(AUTOMATION_TEXT).map(([k, label]) => (
          <label key={k} className="flex items-start gap-2">
            <input type="checkbox" className="mt-0.5 accent-[var(--brand)]" checked={w.automations[k] !== false} onChange={(e) => save.mutate({ automations: { [k]: e.target.checked } })} />
            <span>{label}</span>
          </label>
        ))}
      </div>
      {!w.ai && <p className="text-xs text-muted">Drafts and briefs use templates on this plan or server. AI drafting turns on with a higher plan.</p>}
    </div>
  );
}

const NOTIFY_KINDS: [string, string][] = [
  ["reply", "Investor replies"],
  ["hot", "An investor opens your email several times"],
  ["data_room", "Someone views your data room"],
  ["reminder", "Follow-up reminders"],
  ["daily_brief", "Morning brief"],
  ["bounce", "Bounced emails"],
  ["cap_warning", "Close to the daily send limit"],
];

export function NotificationPrefs() {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const save = useMutation({
    mutationFn: (prefs: Record<string, { in_app: boolean }>) => api("/workspace/me", { method: "PATCH", json: { notify_prefs: prefs } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
    onError: (e) => toast(errText(e), "err"),
  });
  if (!me.data) return <ListSkeleton rows={2} />;
  const prefs = me.data.notify_prefs ?? {};
  return (
    <div className="space-y-2 text-sm">
      {NOTIFY_KINDS.map(([k, label]) => (
        <label key={k} className="flex items-center gap-2">
          <input type="checkbox" className="accent-[var(--brand)]" checked={prefs[k]?.in_app !== false} onChange={(e) => save.mutate({ [k]: { in_app: e.target.checked } })} />
          {label}
        </label>
      ))}
    </div>
  );
}

type Members = { items: { id: string; name: string; email: string; role: string; you: boolean }[]; invites: { id: string; email: string; role: string; expires_at: string }[]; seats: number | null };

export function Team() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<Members>({ queryKey: ["members"], queryFn: () => api("/workspace/members") });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [link, setLink] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["members"] });
  const invite = useMutation({
    mutationFn: () => api<{ url: string }>("/workspace/invites", { method: "POST", json: { email, role } }),
    onSuccess: (r) => {
      setLink(r.url);
      setEmail("");
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const act = useMutation({
    mutationFn: ({ path, method, json }: { path: string; method: string; json?: unknown }) => api(path, { method, json }),
    onSuccess: refresh,
    onError: (e) => toast(errText(e), "err"),
  });
  if (!q.data) return <ListSkeleton rows={2} />;
  const owner = q.data.items.find((m) => m.you)?.role === "owner";
  return (
    <div className="space-y-4 text-sm">
      <ul className="divide-y divide-line">
        {q.data.items.map((m) => (
          <li key={m.id} className="py-2 flex items-center gap-2">
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">
                {m.name || m.email} {m.you && <span className="text-muted font-normal">(you)</span>}
              </div>
              <div className="text-xs text-muted truncate">{m.email}</div>
            </div>
            {owner && m.role !== "owner" ? (
              <>
                <select className="input h-9 w-28" value={m.role} onChange={(e) => act.mutate({ path: `/workspace/members/${m.id}`, method: "PATCH", json: { role: e.target.value } })} aria-label={`Role for ${m.email}`}>
                  <option value="editor">Editor</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button className="p-2 text-muted" aria-label={`Remove ${m.email}`} onClick={() => confirm(`Remove ${m.email}?`) && act.mutate({ path: `/workspace/members/${m.id}`, method: "DELETE" })}>
                  <Trash2 size={16} />
                </button>
              </>
            ) : (
              <span className="chip capitalize">{m.role}</span>
            )}
          </li>
        ))}
        {q.data.invites.map((i) => (
          <li key={i.id} className="py-2 flex items-center gap-2 text-muted">
            <div className="flex-1 truncate">
              {i.email} · invited as {i.role}
            </div>
            {owner && (
              <button className="btn-ghost btn-sm" onClick={() => act.mutate({ path: `/workspace/invites/${i.id}`, method: "DELETE" })}>
                Cancel
              </button>
            )}
          </li>
        ))}
      </ul>
      {owner && (
        <form className="flex flex-col sm:flex-row gap-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
          <input className="input flex-1" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="cofounder@company.com" aria-label="Invite email" />
          <select className="input sm:w-32" value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
            <option value="editor">Editor</option>
            <option value="viewer">Viewer</option>
          </select>
          <button className="btn-primary" disabled={invite.isPending}>
            Invite
          </button>
        </form>
      )}
      {link && (
        <div className="rounded-lg border border-line p-3 space-y-2">
          <p>Send this link to them. It works once and expires in 7 days.</p>
          <div className="flex gap-2">
            <input className="input flex-1 font-mono text-xs" readOnly value={link} aria-label="Invite link" />
            <button className="btn-ghost" onClick={() => navigator.clipboard.writeText(link).then(() => toast("Copied"))}>
              <Copy size={14} />
            </button>
          </div>
        </div>
      )}
      <p className="text-xs text-muted">{q.data.seats == null ? "Unlimited seats" : `${q.data.seats} seat${q.data.seats === 1 ? "" : "s"} on your plan`}</p>
    </div>
  );
}

export function NewWorkspace() {
  const toast = useToast();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api<{ id: string }>("/workspaces", { method: "POST", json: { name } }),
    onSuccess: (r) => {
      setWorkspace(r.id);
      location.href = "/app";
    },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <input className="input flex-1" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Second company or raise" aria-label="Workspace name" />
      <button className="btn-ghost" disabled={create.isPending}>
        <Plus size={16} /> Create
      </button>
    </form>
  );
}

type Sess = { id: string; device: string; ip: string; created_at: string; last_seen_at: string | null; current: boolean };

const deviceName = (ua: string) => {
  const os = /iPhone|iPad/.test(ua) ? "iPhone/iPad" : /Android/.test(ua) ? "Android" : /Mac OS/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "Device";
  const br = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  return `${br} on ${os}`;
};

export function Devices() {
  const qc = useQueryClient();
  const q = useQuery<{ items: Sess[] }>({ queryKey: ["sessions"], queryFn: () => api("/auth/sessions") });
  const out = useMutation({ mutationFn: (id: string) => api(`/auth/sessions/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }) });
  if (!q.data) return <ListSkeleton rows={2} />;
  return (
    <ul className="divide-y divide-line text-sm">
      {q.data.items.map((s) => (
        <li key={s.id} className="py-2 flex items-center gap-3">
          <Laptop size={18} className="text-muted shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="font-medium">
              {deviceName(s.device)} {s.current && <span className="text-green-600 font-normal">· this device</span>}
            </div>
            <div className="text-xs text-muted">
              {s.ip || "unknown IP"} · last active {fmtDate(s.last_seen_at ?? s.created_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </div>
          </div>
          {!s.current && (
            <button className="btn-ghost btn-sm" onClick={() => out.mutate(s.id)}>
              Sign out
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

type Mem = { id: string; kind: string; text: string; source: string };

export function AgentMemoryList() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ items: Mem[] }>({ queryKey: ["memory"], queryFn: () => api("/agent/memory") });
  const [text, setText] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["memory"] });
  const add = useMutation({
    mutationFn: () => api("/agent/memory", { method: "POST", json: { text, kind: "fact" } }),
    onSuccess: () => {
      setText("");
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const del = useMutation({ mutationFn: (id: string) => api(`/agent/memory/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <div className="space-y-3 text-sm">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <input className="input flex-1" value={text} onChange={(e) => setText(e.target.value)} minLength={2} required placeholder="We closed a pilot with NHS Leeds in October" aria-label="New memory" />
        <button className="btn-primary">Add</button>
      </form>
      <ul className="space-y-1.5">
        {q.data?.items.map((m) => (
          <li key={m.id} className="flex items-start gap-2 rounded-lg border border-line px-3 py-2">
            <span className="flex-1">
              {m.text} <span className="text-xs text-muted">· {m.source === "manual" ? "added by you" : "learned in chat"}</span>
            </span>
            <button className="text-muted" aria-label="Forget" onClick={() => del.mutate(m.id)}>
              <Trash2 size={14} />
            </button>
          </li>
        ))}
        {q.data?.items.length === 0 && <li className="text-muted">Nothing yet. Tell your agent things in chat, or add them here.</li>}
      </ul>
    </div>
  );
}

type Pos = { needs_profile: boolean; matches?: number; advice?: string[]; gaps?: string[] };

export function Positioning() {
  const q = useQuery<Pos>({ queryKey: ["positioning"], queryFn: () => api("/agent/positioning"), staleTime: 300_000 });
  if (!q.data) return <ListSkeleton rows={1} />;
  if (q.data.needs_profile) return <p className="text-sm text-muted">Fill in your sectors above to get positioning advice.</p>;
  return (
    <ul className="text-sm space-y-1.5 list-disc pl-5">
      {q.data.advice?.map((a) => <li key={a}>{a}</li>)}
      {q.data.gaps?.map((a) => (
        <li key={a} className="text-warn">
          {a}
        </li>
      ))}
    </ul>
  );
}

type Billing = { enabled: boolean; current: string; subscription: { status: string; interval: string; tier: string; current_period_end: string } | null; tiers: { code: string; name: string; price_monthly: number; price_annual: number; purchasable: boolean; limits: Record<string, number> }[] };

export function BillingPlans() {
  const toast = useToast();
  const q = useQuery<Billing>({ queryKey: ["billing"], queryFn: () => api("/billing") });
  const [interval, setInterval] = useState<"month" | "year">("month");
  const go = useMutation({
    mutationFn: ({ path, json }: { path: string; json?: unknown }) => api<{ url: string }>(path, { method: "POST", json }),
    onSuccess: (r) => (location.href = r.url),
    onError: (e) => toast(errText(e), "err"),
  });
  if (!q.data) return <ListSkeleton rows={1} />;
  const b = q.data;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {b.subscription && (
          <>
            <span className="text-muted">
              Subscription {b.subscription.status} · renews {fmtDate(b.subscription.current_period_end, { day: "numeric", month: "short", year: "numeric" })}
            </span>
            <button className="btn-ghost btn-sm" onClick={() => go.mutate({ path: "/billing/portal" })}>
              Manage billing
            </button>
          </>
        )}
        <div className="ml-auto flex rounded-lg border border-line p-0.5" role="group" aria-label="Billing interval">
          {(["month", "year"] as const).map((i) => (
            <button key={i} className={`px-3 py-1 rounded-md text-xs ${interval === i ? "bg-brand text-white" : ""}`} onClick={() => setInterval(i)}>
              {i === "month" ? "Monthly" : "Annual"}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {b.tiers.map((t) => {
          const price = interval === "year" && t.price_annual ? t.price_annual / 12 : t.price_monthly;
          return (
            <div key={t.code} className={`rounded-lg border p-4 ${t.code === b.current ? "border-brand" : "border-line"}`}>
              <div className="font-semibold">{t.name}</div>
              <div className="text-2xl font-bold mt-1">
                ${(price / 100).toFixed(0)}
                <span className="text-sm font-normal text-muted">/mo</span>
              </div>
              <ul className="text-xs text-muted mt-2 space-y-0.5">
                <li>{t.limits.reveals_month} contact reveals / month</li>
                <li>{t.limits.emails_day} emails / day</li>
                <li>
                  {t.limits.workspaces} workspace{t.limits.workspaces > 1 ? "s" : ""} · {t.limits.seats ?? 1} seat{(t.limits.seats ?? 1) > 1 ? "s" : ""}
                </li>
              </ul>
              {t.code === b.current ? (
                <div className="btn-ghost btn-sm w-full mt-3 pointer-events-none">Current plan</div>
              ) : b.enabled && t.purchasable ? (
                <button className="btn-primary btn-sm w-full mt-3" disabled={go.isPending} onClick={() => go.mutate({ path: "/billing/checkout", json: { tier: t.code, interval } })}>
                  Choose {t.name}
                </button>
              ) : (
                <a className="btn-ghost btn-sm w-full mt-3" href={`mailto:hello@easyfundraise.com?subject=Upgrade to ${t.name}`}>
                  Request upgrade
                </a>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

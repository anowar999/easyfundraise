"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorState, ListSkeleton, errText, useToast } from "@/components/ui";
import { api, ApiError, qs, timeAgo } from "@/lib/api";

const TABS = ["Overview", "Users", "Packages", "Errors", "Tasks", "Investor requests", "Audit log"] as const;

function Overview() {
  const q = useQuery<Record<string, any>>({ queryKey: ["admin", "overview"], queryFn: () => api("/admin/overview") });
  if (q.isLoading) return <ListSkeleton rows={2} />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data!;
  const tiles: [string, unknown][] = [
    ["Users", d.users], ["Signups (7d)", d.signups_7d], ["Investors", d.investors], ["Researched", d.investors_enriched],
    ["Funnel cards", d.funnel_cards], ["Searches (7d)", d.searches_7d], ["Reveals (7d)", d.reveals_7d], ["Open errors", d.open_errors],
    ["Removal requests", d.open_removal_requests], ["Emails sent (7d)", d.emails_sent_7d], ["Replies (7d)", d.replies_7d],
    ["Gmail connected", d.gmail_connected], ["AI tokens (month)", d.ai_tokens_month], ["MRR", `$${((d.mrr_cents ?? 0) / 100).toFixed(0)}`],
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tiles.map(([k, v]) => (
          <div key={k} className="card p-4">
            <div className="text-xs text-muted">{k}</div>
            <div className="text-2xl font-semibold font-mono">{String(v ?? 0)}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card p-4">
          <h3 className="font-semibold mb-2">Workspaces by tier</h3>
          {Object.entries(d.workspaces_by_tier ?? {}).map(([t, n]) => (
            <div key={t} className="flex justify-between text-sm py-1"><span>{t}</span><span className="font-mono">{String(n)}</span></div>
          ))}
        </div>
        <div className="card p-4">
          <h3 className="font-semibold mb-2">Top revealers (7d)</h3>
          {d.top_revealers_7d?.length ? d.top_revealers_7d.map((r: any) => (
            <div key={r.user} className="flex justify-between text-sm py-1"><span className="truncate">{r.user}</span><span className="font-mono">{r.count}</span></div>
          )) : <p className="text-sm text-muted">No reveals yet.</p>}
        </div>
      </div>
    </div>
  );
}

function Users() {
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const users = useQuery<{ items: any[] }>({ queryKey: ["admin", "users", q], queryFn: () => api(`/admin/users${qs({ q })}`) });
  const tiers = useQuery<{ items: any[] }>({ queryKey: ["admin", "tiers"], queryFn: () => api("/admin/tiers") });
  const patchUser = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) => api(`/admin/users/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
    onError: (e) => toast(errText(e), "err"),
  });
  const patchWs = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) => api(`/admin/workspaces/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => { toast("Updated"); qc.invalidateQueries({ queryKey: ["admin", "users"] }); },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <div className="space-y-3">
      <input className="input" placeholder="Search users" value={q} onChange={(e) => setQ(e.target.value)} />
      {users.data?.items.map((u) => (
        <div key={u.id} className="card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">{u.name} {u.is_admin && <span className="chip text-brand">admin</span>} {u.suspended && <span className="chip text-danger">suspended</span>}</div>
              <div className="text-xs text-muted">{u.email} · joined {timeAgo(u.created_at)}</div>
            </div>
            <button className="btn-ghost btn-sm" onClick={() => patchUser.mutate({ id: u.id, body: { suspended: !u.suspended } })}>{u.suspended ? "Unsuspend" : "Suspend"}</button>
            <button className="btn-ghost btn-sm" onClick={() => patchUser.mutate({ id: u.id, body: { is_admin: !u.is_admin } })}>{u.is_admin ? "Remove admin" : "Make admin"}</button>
          </div>
          {u.workspaces.map((w: any) => (
            <div key={w.id} className="mt-3 flex flex-wrap items-center gap-2 text-sm border-t border-line pt-3">
              <span className="flex-1">{w.name}</span>
              <select className="input w-40 h-8" value={w.tier} onChange={(e) => patchWs.mutate({ id: w.id, body: { tier_code: e.target.value } })}>
                {tiers.data?.items.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
              <button className="btn-ghost btn-sm" onClick={() => patchWs.mutate({ id: w.id, body: { extend_trial_days: 7 } })}>+7 trial days</button>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Packages() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ items: any[] }>({ queryKey: ["admin", "tiers"], queryFn: () => api("/admin/tiers") });
  const [edit, setEdit] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: ({ code, body }: { code: string; body: object }) => api(`/admin/tiers/${code}`, { method: "PUT", json: body }),
    onSuccess: () => { toast("Package saved. Applies immediately, no deploy needed."); qc.invalidateQueries({ queryKey: ["admin", "tiers"] }); },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {q.data?.items.map((t) => {
        const key = t.code;
        const text = edit[key] ?? JSON.stringify({ name: t.name, price_monthly: t.price_monthly, price_annual: t.price_annual, stripe_price_monthly: t.stripe_price_monthly ?? "", stripe_price_annual: t.stripe_price_annual ?? "", limits: t.limits, features: t.features, sort: t.sort, visible: t.visible }, null, 2);
        return (
          <div key={key} className="card p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold">{t.name} <span className="text-xs text-muted font-mono">{t.code} · v{t.version}</span></div>
            </div>
            <textarea className="textarea font-mono text-xs min-h-72" value={text} onChange={(e) => setEdit({ ...edit, [key]: e.target.value })} spellCheck={false} />
            <button
              className="btn-primary btn-sm mt-2"
              onClick={() => {
                try {
                  save.mutate({ code: key, body: JSON.parse(text) });
                } catch {
                  toast("Invalid JSON", "err");
                }
              }}
            >
              Save {t.name}
            </button>
          </div>
        );
      })}
    </div>
  );
}

function Errors() {
  const qc = useQueryClient();
  const q = useQuery<{ items: any[] }>({ queryKey: ["admin", "errors"], queryFn: () => api("/admin/errors") });
  const act = useMutation({
    mutationFn: ({ fp, body }: { fp: string; body: object }) => api(`/admin/errors/${fp}`, { method: "PATCH", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }),
  });
  if (q.data?.items.length === 0) return <p className="text-sm text-muted card p-4">No errors recorded. 🎉</p>;
  return (
    <div className="space-y-2">
      {q.data?.items.map((e) => (
        <details key={e.fingerprint} className="card p-4">
          <summary className="cursor-pointer flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs chip">{e.status}</span>
            <span className="font-medium">{e.type}</span>
            <span className="text-sm text-muted truncate flex-1">{e.path} · {e.message}</span>
            <span className="text-xs text-muted">{e.count}× · {e.users_affected} users · {timeAgo(e.last_seen)}</span>
          </summary>
          <pre className="mt-3 text-xs overflow-x-auto bg-surface p-3 rounded-lg max-h-64">{e.stack}</pre>
          <div className="flex gap-2 mt-2">
            {!e.task_id && <button className="btn-primary btn-sm" onClick={() => act.mutate({ fp: e.fingerprint, body: { create_task: true } })}>Create engineering task</button>}
            {["triaged", "fixed", "muted"].map((s) => (
              <button key={s} className="btn-ghost btn-sm" onClick={() => act.mutate({ fp: e.fingerprint, body: { status: s } })}>Mark {s}</button>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function Tasks() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ states: string[]; items: any[] }>({ queryKey: ["admin", "tasks"], queryFn: () => api("/admin/tasks") });
  const [title, setTitle] = useState("");
  const create = useMutation({
    mutationFn: () => api("/admin/tasks", { method: "POST", json: { title, type: "feature" } }),
    onSuccess: () => { setTitle(""); qc.invalidateQueries({ queryKey: ["admin", "tasks"] }); },
    onError: (e) => toast(errText(e), "err"),
  });
  const patch = useMutation({
    mutationFn: ({ id, state }: { id: string; state: string }) => api(`/admin/tasks/${id}`, { method: "PATCH", json: { state } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "tasks"] }),
  });
  const states = q.data?.states ?? [];
  return (
    <div className="space-y-4">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title.trim()) create.mutate(); }}>
        <input className="input" placeholder="New idea or task" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button className="btn-primary">Add</button>
      </form>
      <div className="flex gap-3 overflow-x-auto pb-3">
        {states.map((s) => {
          const items = q.data!.items.filter((t) => t.state === s);
          if (!items.length && !["Idea", "Approved", "In development", "Done"].includes(s)) return null;
          return (
            <div key={s} className="w-64 shrink-0 rounded-xl bg-line/30 p-2">
              <div className="text-xs font-semibold px-1 pb-2">{s} <span className="text-muted">{items.length}</span></div>
              <div className="space-y-2">
                {items.map((t) => (
                  <div key={t.id} className="card p-3">
                    <div className="text-sm font-medium">{t.title}</div>
                    <div className="text-xs text-muted mt-0.5">{t.type} · {t.priority} · {t.source}</div>
                    <select className="input h-8 mt-2 text-xs" value={t.state} onChange={(e) => patch.mutate({ id: t.id, state: e.target.value })}>
                      {states.map((x) => <option key={x}>{x}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Requests() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ items: any[] }>({ queryKey: ["admin", "requests"], queryFn: () => api("/admin/removal-requests") });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => api(`/admin/removal-requests/${id}`, { method: "POST", json: { action } }),
    onSuccess: () => { toast("Done"); qc.invalidateQueries({ queryKey: ["admin"] }); },
    onError: (e) => toast(errText(e), "err"),
  });
  if (q.data?.items.length === 0) return <p className="text-sm text-muted card p-4">No requests.</p>;
  return (
    <div className="space-y-2">
      {q.data?.items.map((r) => (
        <div key={r.id} className="card p-4 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="font-medium">{r.name} <span className="chip">{r.kind}</span> <span className="chip">{r.status}</span></div>
            <div className="text-xs text-muted">{r.email} {r.linkedin} · {timeAgo(r.created_at)}</div>
            {r.message && <p className="text-sm mt-1">{r.message}</p>}
          </div>
          {r.status === "open" && (
            <>
              <button className="btn-primary btn-sm" onClick={() => act.mutate({ id: r.id, action: "approve" })}>Approve</button>
              <button className="btn-ghost btn-sm" onClick={() => act.mutate({ id: r.id, action: "reject" })}>Reject</button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function Audit() {
  const q = useQuery<{ items: any[] }>({ queryKey: ["admin", "audit"], queryFn: () => api("/admin/audit") });
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs text-muted text-left border-b border-line">
          <tr>{["When", "Actor", "Action", "Target", "IP"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {q.data?.items.map((a) => (
            <tr key={a.id} className="border-b border-line last:border-0">
              <td className="px-3 py-2 whitespace-nowrap text-muted">{timeAgo(a.created_at)}</td>
              <td className="px-3 py-2">{a.actor}</td>
              <td className="px-3 py-2 font-mono text-xs">{a.action}</td>
              <td className="px-3 py-2 text-muted truncate max-w-64">{a.target}</td>
              <td className="px-3 py-2 text-muted font-mono text-xs">{a.ip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** AUTH-08: admin pages need a fresh two-factor check. */
function MfaGate({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const [setup, setSetup] = useState<{ secret: string; otpauth: string } | null>(null);
  const [code, setCode] = useState("");
  const start = useMutation({
    mutationFn: () => api<{ secret: string; otpauth: string }>("/auth/mfa/setup", { method: "POST" }),
    onSuccess: setSetup,
    onError: (e) => toast(errText(e), "err"),
  });
  const verify = useMutation({
    mutationFn: () => api("/auth/mfa/verify", { method: "POST", json: { code } }),
    onSuccess: onDone,
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <div className="card p-6 max-w-sm space-y-3">
      <h2 className="font-semibold">Two-factor check</h2>
      <p className="text-sm text-muted">Enter the 6-digit code from your authenticator app. First time here? Set it up first.</p>
      {setup && (
        <div className="text-xs rounded-lg border border-line p-3 break-all">
          Add this key to your authenticator app: <b className="font-mono">{setup.secret}</b>
          <a className="block text-brand mt-1" href={setup.otpauth}>Open in authenticator</a>
        </div>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
        <input className="input flex-1 font-mono tracking-widest" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} aria-label="Code" />
        <button className="btn-primary" disabled={code.length !== 6 || verify.isPending}>Verify</button>
      </form>
      {!setup && <button className="btn-ghost btn-sm" onClick={() => start.mutate()}>Set up two-factor</button>}
    </div>
  );
}

export default function Admin() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const qc = useQueryClient();
  const gate = useQuery<Record<string, any>>({ queryKey: ["admin", "overview"], queryFn: () => api("/admin/overview"), retry: false });
  if (gate.error instanceof ApiError && gate.error.problem.mfa)
    return (
      <>
        <PageHeader title="Admin" />
        <MfaGate onDone={() => qc.invalidateQueries({ queryKey: ["admin"] })} />
      </>
    );
  return (
    <>
      <PageHeader title="Admin" sub="Configure the platform without a deploy." />
      <div className="flex gap-1 overflow-x-auto scrollbar-none border-b border-line mb-4" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={clsx("px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px", tab === t ? "border-brand text-brand font-medium" : "border-transparent text-muted")}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <Overview />}
      {tab === "Users" && <Users />}
      {tab === "Packages" && <Packages />}
      {tab === "Errors" && <Errors />}
      {tab === "Tasks" && <Tasks />}
      {tab === "Investor requests" && <Requests />}
      {tab === "Audit log" && <Audit />}
    </>
  );
}

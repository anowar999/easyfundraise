"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PageHeader, useMe } from "@/components/AppShell";
import { Field, ListSkeleton, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { AgentMemoryList, BillingPlans, Devices, GmailSection, NewWorkspace, NotificationPrefs, OutreachSettings, Positioning, SignInMethods, Team } from "./extras";

type Profile = { company_name: string; one_liner: string; sectors: string[]; stage: string; geography: string; round_size: string; instrument: string; traction: string; business_model: string; investor_types: string[]; looking_for: string; shareable: Record<string, boolean>; deck_filename: string };
type WS = { name: string; agent_name: string; tier: { code: string; name: string; limits: Record<string, number> }; trial_ends_at: string | null; trial_expired: boolean; usage: Record<string, number> };

function Section({ id, title, sub, children }: { id: string; title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="card p-4 md:p-6 scroll-mt-20">
      <h2 className="font-semibold">{title}</h2>
      {sub && <p className="text-sm text-muted mt-0.5">{sub}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function CompanyProfile() {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery<Profile>({ queryKey: ["profile"], queryFn: () => api("/workspace/profile") });
  const facets = useQuery<{ sectors: { value: string }[] }>({ queryKey: ["facets"], queryFn: () => api("/investors/facets"), staleTime: 600_000 });
  const [p, setP] = useState<Profile | null>(null);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (q.data) setP(q.data);
  }, [q.data]);
  const save = useMutation({
    mutationFn: (body: Profile) => api("/workspace/profile", { method: "PUT", json: body }),
    onSuccess: () => {
      toast("Company profile saved. Matches updated.");
      qc.invalidateQueries({ queryKey: ["recommended"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const upload = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api<{ suggested: Partial<Profile> }>("/workspace/deck", { method: "POST", body: fd });
      setP((x) => x && {
        ...x,
        deck_filename: f.name,
        sectors: x.sectors.length ? x.sectors : r.suggested.sectors ?? [],
        stage: x.stage || r.suggested.stage || "",
        round_size: x.round_size || r.suggested.round_size || "",
        traction: x.traction || r.suggested.traction || "",
        one_liner: x.one_liner || r.suggested.one_liner || "",
      });
      toast("Deck read. Review the suggested fields and save.");
    } catch (e) {
      toast(errText(e), "err");
    }
  };
  if (!p) return <ListSkeleton rows={2} />;
  const share = (k: string) => p.shareable[k] !== false;
  const toggleShare = (k: string) => setP({ ...p, shareable: { ...p.shareable, [k]: !share(k) } });
  const ShareToggle = ({ k }: { k: string }) => (
    <label className="text-xs text-muted flex items-center gap-1 mt-1">
      <input type="checkbox" checked={share(k)} onChange={() => toggleShare(k)} className="accent-[var(--brand)]" /> OK to use in emails
    </label>
  );
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(p); }}>
      <div className="rounded-lg border border-dashed border-line p-3 flex items-center gap-3">
        <FileUp className="text-brand shrink-0" />
        <div className="flex-1 min-w-0 text-sm">
          {p.deck_filename ? <span className="truncate block">{p.deck_filename}</span> : <span className="text-muted">Upload your deck (PDF) and we'll pre-fill this profile.</span>}
        </div>
        <button type="button" className="btn-ghost btn-sm" onClick={() => file.current?.click()}>
          {p.deck_filename ? "Replace" : "Upload"}
        </button>
        <input ref={file} type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Company name">
          <input className="input" value={p.company_name} onChange={(e) => setP({ ...p, company_name: e.target.value })} />
          <ShareToggle k="company_name" />
        </Field>
        <Field label="Stage">
          <select className="input" value={p.stage} onChange={(e) => setP({ ...p, stage: e.target.value })}>
            <option value="">—</option>
            <option value="pre-seed">Pre-seed</option>
            <option value="seed">Seed</option>
            <option value="series-a">Series A</option>
            <option value="series-b">Series B</option>
          </select>
        </Field>
      </div>
      <Field label="One-liner">
        <input className="input" value={p.one_liner} onChange={(e) => setP({ ...p, one_liner: e.target.value })} placeholder="AI triage for primary-care clinics" />
        <ShareToggle k="one_liner" />
      </Field>
      <Field label="Sectors">
        <div className="flex flex-wrap gap-1.5">
          {(facets.data?.sectors ?? []).slice(0, 46).map((s) => {
            const on = p.sectors.includes(s.value);
            return (
              <button type="button" key={s.value} onClick={() => setP({ ...p, sectors: on ? p.sectors.filter((x) => x !== s.value) : [...p.sectors, s.value].slice(0, 10) })} className={`chip px-2.5 py-1 ${on ? "bg-brand text-white border-brand" : ""}`}>
                {s.value}
              </button>
            );
          })}
        </div>
      </Field>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Field label="Geography">
          <select className="input" value={p.geography} onChange={(e) => setP({ ...p, geography: e.target.value })}>
            <option value="">—</option>
            {["us", "uk", "europe", "india", "sea", "global"].map((g) => <option key={g} value={g}>{g.toUpperCase()}</option>)}
          </select>
        </Field>
        <Field label="Round size">
          <input className="input" value={p.round_size} onChange={(e) => setP({ ...p, round_size: e.target.value })} placeholder="$1.5M" />
          <ShareToggle k="round_size" />
        </Field>
        <Field label="Instrument">
          <select className="input" value={p.instrument} onChange={(e) => setP({ ...p, instrument: e.target.value })}>
            <option value="">—</option>
            <option>SAFE</option>
            <option>Note</option>
            <option>Equity</option>
          </select>
        </Field>
      </div>
      <Field label="Traction (one line)">
        <input className="input" value={p.traction} onChange={(e) => setP({ ...p, traction: e.target.value })} placeholder="40 clinics live, 12% MoM growth" />
        <ShareToggle k="traction" />
      </Field>
      <Field label="Business model">
        <input className="input" value={p.business_model} onChange={(e) => setP({ ...p, business_model: e.target.value })} placeholder="B2B SaaS, per-clinic subscription" />
      </Field>
      <Field label="Raising from">
        <div className="flex flex-wrap gap-1.5">
          {[["angel", "Angels"], ["vc", "VC funds"], ["syndicate", "Syndicates"], ["family_office", "Family offices"], ["cvc", "Corporate VCs"], ["accelerator", "Accelerators"]].map(([v, l]) => {
            const types = p.investor_types ?? [];
            const on = types.includes(v);
            return (
              <button type="button" key={v} onClick={() => setP({ ...p, investor_types: on ? types.filter((x) => x !== v) : [...types, v] })} className={`chip px-2.5 py-1 ${on ? "bg-brand text-white border-brand" : ""}`}>
                {l}
              </button>
            );
          })}
        </div>
      </Field>
      <Field label="What you're looking for in an investor">
        <textarea className="textarea min-h-20" value={p.looking_for ?? ""} onChange={(e) => setP({ ...p, looking_for: e.target.value })} placeholder="A lead angel with clinical networks, $100K–$500K cheques" />
      </Field>
      <button className="btn-primary" disabled={save.isPending}>Save company profile</button>
    </form>
  );
}

function AgentInstructions() {
  const toast = useToast();
  const q = useQuery<{ text: string; version: number }>({ queryKey: ["agent-instructions"], queryFn: () => api("/workspace/agent-instructions") });
  const [text, setText] = useState("");
  const [summary, setSummary] = useState<string[]>([]);
  useEffect(() => {
    if (q.data) setText(q.data.text);
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<{ summary: string[] }>("/workspace/agent-instructions", { method: "PUT", json: { text } }),
    onSuccess: (r) => {
      setSummary(r.summary);
      toast("Instructions saved");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <div className="space-y-3">
      <textarea className="textarea min-h-28" value={text} onChange={(e) => setText(e.target.value)} placeholder="Only target US/UK. Never pitch PE. Mention our FDA clearance. Keep emails under 90 words." />
      <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>Save instructions</button>
      {summary.length > 0 && (
        <ul className="text-sm text-muted list-disc pl-5">
          {summary.map((s) => <li key={s}>{s}</li>)}
        </ul>
      )}
    </div>
  );
}

function Exclusions() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ id: string; kind: string; value: string }[]>({ queryKey: ["exclusions"], queryFn: () => api("/workspace/exclusions") });
  const [kind, setKind] = useState("domain");
  const [value, setValue] = useState("");
  const add = useMutation({
    mutationFn: () => api("/workspace/exclusions", { method: "POST", json: { kind, value } }),
    onSuccess: () => { setValue(""); qc.invalidateQueries({ queryKey: ["exclusions"] }); },
    onError: (e) => toast(errText(e), "err"),
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/workspace/exclusions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exclusions"] }),
  });
  return (
    <div className="space-y-3">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <select className="input w-32" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="domain">Domain</option>
          <option value="email">Email</option>
          <option value="firm">Firm</option>
          <option value="linkedin">LinkedIn</option>
        </select>
        <input className="input flex-1" value={value} onChange={(e) => setValue(e.target.value)} placeholder="sequoiacap.com" required minLength={2} />
        <button className="btn-primary">Add</button>
      </form>
      <div className="flex flex-wrap gap-2">
        {q.data?.map((x) => (
          <span key={x.id} className="chip">
            <span className="text-muted">{x.kind}:</span> {x.value}
            <button onClick={() => del.mutate(x.id)} aria-label={`Remove ${x.value}`}>
              <Trash2 size={12} />
            </button>
          </span>
        ))}
        {q.data?.length === 0 && <span className="text-sm text-muted">No exclusions yet.</span>}
      </div>
    </div>
  );
}

function Account() {
  const me = useMe();
  const toast = useToast();
  const qc = useQueryClient();
  const [sig, setSig] = useState("");
  const [tz, setTz] = useState("");
  useEffect(() => {
    if (me.data) {
      setSig(me.data.signature);
      setTz(me.data.timezone);
    }
  }, [me.data]);
  const save = useMutation({
    mutationFn: () => api("/workspace/me", { method: "PATCH", json: { signature: sig, timezone: tz } }),
    onSuccess: () => { toast("Saved"); qc.invalidateQueries({ queryKey: ["me"] }); },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <div className="space-y-3">
      <Field label="Email signature (added to every outreach email)">
        <textarea className="textarea min-h-24" value={sig} onChange={(e) => setSig(e.target.value)} placeholder={"Sam Lee\nCEO, DocAI · docai.com\n123 Main St, London"} />
      </Field>
      <Field label="Your timezone (reminders fire at 09:00 local)">
        <div className="flex gap-2">
          <input className="input" value={tz} onChange={(e) => setTz(e.target.value)} />
          <button type="button" className="btn-ghost" onClick={() => setTz(Intl.DateTimeFormat().resolvedOptions().timeZone)}>Detect</button>
        </div>
      </Field>
      <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>Save</button>
    </div>
  );
}

function Plan() {
  const ws = useQuery<WS>({ queryKey: ["workspace"], queryFn: () => api("/workspace") });
  if (!ws.data) return <ListSkeleton rows={1} />;
  const u = ws.data.usage;
  const l = ws.data.tier.limits;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 text-sm">
        <span className="chip px-3 py-1 bg-brand/10 text-brand border-brand/30">{ws.data.tier.name}</span>
        {ws.data.trial_ends_at && ws.data.tier.code === "trial" && (
          <span className={ws.data.trial_expired ? "text-danger" : "text-muted"}>
            {ws.data.trial_expired ? "Trial ended" : `Trial ends ${new Date(ws.data.trial_ends_at).toLocaleDateString()}`}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
        <div className="rounded-lg border border-line p-3">
          <div className="text-xs text-muted">Searches</div>
          <div className="font-mono">{l.searches_total ? `${u.searches_total} / ${l.searches_total}` : `${u.searches_month} / ${l.searches_month ?? "∞"}`}</div>
        </div>
        <div className="rounded-lg border border-line p-3">
          <div className="text-xs text-muted">Contact reveals this month</div>
          <div className="font-mono">{u.reveals_month} / {l.reveals_month ?? 0}</div>
        </div>
        <div className="rounded-lg border border-line p-3">
          <div className="text-xs text-muted">Emails per day</div>
          <div className="font-mono">{l.emails_day ?? 0}</div>
        </div>
      </div>
      <BillingPlans />
    </div>
  );
}

export default function Settings() {
  return (
    <>
      <PageHeader title="Settings" />
      <div className="space-y-4 max-w-3xl">
        <Section id="company" title="Company profile" sub="Used to rank investors by fit and to personalise emails. Only fields marked OK are used in emails.">
          <CompanyProfile />
        </Section>
        <Section id="agent" title="Instructions for your agent" sub="Top-priority rules for every draft and suggestion.">
          <AgentInstructions />
        </Section>
        <Section id="exclusions" title="Exclusion list" sub="We never draft or send to these.">
          <Exclusions />
        </Section>
        <Section id="account" title="Signature & timezone">
          <Account />
        </Section>
        <Section id="gmail" title="Gmail" sub="Outreach sends from your own mailbox.">
          <GmailSection />
        </Section>
        <Section id="outreach" title="Sending & automations">
          <OutreachSettings />
        </Section>
        <Section id="positioning" title="Positioning advice" sub="What your best-matched investors look for.">
          <Positioning />
        </Section>
        <Section id="memory" title="What your agent remembers" sub="Facts it uses in drafts and briefs. Remove anything that's out of date.">
          <AgentMemoryList />
        </Section>
        <Section id="notifications" title="Notifications" sub="What shows up in your alerts.">
          <NotificationPrefs />
        </Section>
        <Section id="team" title="Team" sub="Invite a cofounder or advisor to this workspace.">
          <Team />
        </Section>
        <Section id="workspaces" title="Another company or raise" sub="Each workspace has its own investor tracker, data room and emails.">
          <NewWorkspace />
        </Section>
        <Section id="signin" title="Sign-in & password" sub="Keep Google and Gmail connected, and also sign in with your email and a password.">
          <SignInMethods />
        </Section>
        <Section id="devices" title="Signed-in devices">
          <Devices />
        </Section>
        <Section id="plan" title="Plan & usage">
          <Plan />
        </Section>
      </div>
    </>
  );
}

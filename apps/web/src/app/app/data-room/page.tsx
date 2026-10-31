"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Copy, ExternalLink, FileUp, Globe, Link2, Lock, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorState, Field, ListSkeleton, errText, useToast } from "@/components/ui";
import { api, fmtDate, timeAgo } from "@/lib/api";
import type { RoomContent, RoomSection } from "@/components/RoomView";

type Room = {
  slug: string; published: boolean; access: string; has_password: boolean; indexable: boolean; content: RoomContent; url: string;
  versions: { at: string }[];
  docs: { id: string; label: string; filename: string; size: number; gated: boolean }[];
  links: { id: string; label: string; card_id: string | null; url: string; expires_at: string | null; revoked: boolean }[];
  completeness: { pct: number; missing: { id: string; label: string }[]; has_docs: boolean };
};
type Views = { items: { id: string; viewer: string; card_id: string | null; seconds: number; sections: Record<string, number>; downloads: { doc: string }[]; started_at: string }[] };

const TYPES: [RoomSection["type"], string][] = [
  ["problem", "Problem"], ["solution", "Solution"], ["product", "Product"], ["traction", "Traction"],
  ["market", "Market opportunity"], ["why_now", "Why now"], ["business_model", "Business model"], ["team", "Team"],
  ["ask", "The ask"], ["use_of_funds", "Use of funds"], ["faq", "FAQ"], ["text", "Free text"],
];

function SectionEditor({ s, onChange }: { s: RoomSection; onChange: (s: RoomSection) => void }) {
  const toast = useToast();
  const polish = useMutation({
    mutationFn: () => api<{ text: string }>("/data-room/polish", { method: "POST", json: { text: s.body, section: s.type } }),
    onSuccess: (r) => {
      onChange({ ...s, body: r.text });
      toast("Polished. Check it still says what you mean.");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const rows = <K extends "metrics" | "people" | "items" | "links">(key: K, blank: Record<string, string>, fields: [string, string][]) => {
    const list = ((s[key] as Record<string, string>[] | undefined) ?? []);
    const upd = (i: number, f: string, v: string) => onChange({ ...s, [key]: list.map((x, j) => (j === i ? { ...x, [f]: v } : x)) });
    return (
      <div className="space-y-1.5">
        {list.map((x, i) => (
          <div key={i} className="flex gap-2">
            {fields.map(([f, ph]) => (
              <input key={f} className="input flex-1 min-w-0" placeholder={ph} value={x[f] ?? ""} onChange={(e) => upd(i, f, e.target.value)} />
            ))}
            <button type="button" className="text-muted px-1" aria-label="Remove row" onClick={() => onChange({ ...s, [key]: list.filter((_, j) => j !== i) })}>
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button type="button" className="btn-ghost btn-sm" onClick={() => onChange({ ...s, [key]: [...list, blank] })}>
          <Plus size={14} /> Add
        </button>
      </div>
    );
  };
  return (
    <div className="space-y-2">
      <input className="input font-medium" value={s.title} onChange={(e) => onChange({ ...s, title: e.target.value })} aria-label="Section title" />
      {s.type !== "faq" && (
        <>
          <textarea className="textarea min-h-24" value={s.body ?? ""} onChange={(e) => onChange({ ...s, body: e.target.value })} aria-label="Section text" />
          {(s.body ?? "").length >= 10 && (
            <button type="button" className="btn-ghost btn-sm" disabled={polish.isPending} onClick={() => polish.mutate()}>
              <Sparkles size={14} /> {polish.isPending ? "Polishing…" : "Polish this"}
            </button>
          )}
        </>
      )}
      {s.type === "product" && (
        <>
          <p className="text-xs text-muted">Add a demo video (YouTube, Vimeo or Loom plays on the page), a live demo or app store link.</p>
          {rows("links", { label: "", url: "" }, [["label", "Watch the demo"], ["url", "https://youtu.be/…"]])}
        </>
      )}
      {s.type === "traction" && rows("metrics", { label: "", value: "" }, [["label", "MRR"], ["value", "$42K"]])}
      {s.type === "market" && rows("metrics", { label: "", value: "" }, [["label", "TAM"], ["value", "$12B"]])}
      {s.type === "ask" && rows("metrics", { label: "", value: "" }, [["label", "Raising"], ["value", "$1.5M"]])}
      {s.type === "team" && rows("people", { name: "", role: "", link: "" }, [["name", "Name"], ["role", "CEO, ex-Babylon"], ["link", "LinkedIn URL"]])}
      {s.type === "use_of_funds" && rows("items", { label: "", pct: "" }, [["label", "Engineering"], ["pct", "%"]])}
      {s.type === "faq" && rows("items", { q: "", a: "" }, [["q", "Question"], ["a", "Answer"]])}
    </div>
  );
}

function Docs({ room }: { room: Room }) {
  const qc = useQueryClient();
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["room"] });
  const upload = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    try {
      await api(`/data-room/docs?label=${encodeURIComponent(f.name.replace(/\.[^.]+$/, ""))}&gated=true`, { method: "POST", body: fd });
      refresh();
    } catch (e) {
      toast(errText(e), "err");
    }
  };
  const del = useMutation({ mutationFn: (id: string) => api(`/data-room/docs/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <div className="space-y-2 text-sm">
      {room.docs.map((d) => (
        <div key={d.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2">
          <span className="flex-1 truncate">{d.label}</span>
          <span className="text-xs text-muted">{(d.size / 1024 / 1024).toFixed(1)} MB</span>
          <button className="text-muted" aria-label={`Delete ${d.label}`} onClick={() => confirm(`Delete ${d.label}?`) && del.mutate(d.id)}>
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      <button className="btn-ghost btn-sm" onClick={() => file.current?.click()}>
        <FileUp size={14} /> Add document
      </button>
      <input ref={file} type="file" className="hidden" accept="application/pdf,image/*,.csv,.xlsx,.xls" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      <p className="text-xs text-muted">Documents download only for viewers we can identify: a personal link or an email.</p>
    </div>
  );
}

function Links({ room }: { room: Room }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["room"] });
  const make = useMutation({
    mutationFn: () => api<{ url: string }>("/data-room/links", { method: "POST", json: { label } }),
    onSuccess: (r) => {
      setLabel("");
      navigator.clipboard?.writeText(r.url).catch(() => {});
      toast("Link created and copied");
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api(`/data-room/links/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const live = room.links.filter((l) => !l.revoked);
  return (
    <div className="space-y-2 text-sm">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); make.mutate(); }}>
        <input className="input flex-1" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Who is it for? e.g. Angel syndicate" aria-label="Link label" />
        <button className="btn-ghost" disabled={make.isPending}>
          <Link2 size={14} /> New link
        </button>
      </form>
      {live.map((l) => (
        <div key={l.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2">
          <span className="flex-1 truncate">{l.label}</span>
          <button className="text-muted" aria-label="Copy link" onClick={() => navigator.clipboard.writeText(l.url).then(() => toast("Copied"))}>
            <Copy size={14} />
          </button>
          <button className="text-xs text-danger" onClick={() => revoke.mutate(l.id)}>
            Revoke
          </button>
        </div>
      ))}
      <p className="text-xs text-muted">Each investor tracker card can also copy its own personal link, so you see exactly who viewed what.</p>
    </div>
  );
}

function ViewsList() {
  const q = useQuery<Views>({ queryKey: ["room-views"], queryFn: () => api("/data-room/views") });
  if (!q.data) return <ListSkeleton rows={2} />;
  if (q.data.items.length === 0) return <p className="text-sm text-muted">No views yet.</p>;
  return (
    <ul className="divide-y divide-line text-sm">
      {q.data.items.slice(0, 30).map((v) => {
        const top = Object.entries(v.sections ?? {}).sort((a, b) => b[1] - a[1])[0];
        return (
          <li key={v.id} className="py-2 flex gap-2">
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">{v.card_id ? <a className="text-brand" href={`/app/funnel/${v.card_id}`}>{v.viewer}</a> : v.viewer}</div>
              <div className="text-xs text-muted">
                {Math.round(v.seconds / 60) || "<1"} min{top ? ` · most time on ${top[0].replace(/_/g, " ")}` : ""}
                {v.downloads?.length ? ` · downloaded ${v.downloads.map((d) => d.doc).join(", ")}` : ""}
              </div>
            </div>
            <span className="text-xs text-muted shrink-0">{timeAgo(v.started_at)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Completeness({ r }: { r: Room }) {
  const qc = useQueryClient();
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const { pct, missing } = r.completeness;
  const fromDeck = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    setBusy(true);
    try {
      const res = await api<{ data_room: { filled: string[] } }>("/workspace/deck", { method: "POST", body: fd });
      const n = res.data_room.filled.length;
      toast(n ? `Drafted ${n} section${n > 1 ? "s" : ""} from your deck. Check them over.` : "Your sections already have text, so nothing was replaced.");
      qc.invalidateQueries({ queryKey: ["room"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
    } catch (e) {
      toast(errText(e), "err");
    } finally {
      setBusy(false);
    }
  };
  const tone = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-brand" : "bg-amber-500";
  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative grid place-items-center w-16 h-16 shrink-0">
          <svg viewBox="0 0 36 36" className="w-16 h-16 -rotate-90">
            <circle cx="18" cy="18" r="15.5" fill="none" strokeWidth="4" className="stroke-line" />
            <circle cx="18" cy="18" r="15.5" fill="none" strokeWidth="4" strokeLinecap="round" className={pct >= 80 ? "stroke-emerald-500" : pct >= 50 ? "stroke-brand" : "stroke-amber-500"} strokeDasharray={`${(pct / 100) * 97.4} 97.4`} />
          </svg>
          <span className="absolute text-sm font-bold">{pct}%</span>
        </div>
        <div className="flex-1 min-w-52">
          <h2 className="font-semibold text-[17px]">{pct >= 100 ? "Your data room is investor-ready" : `Your data room is ${pct}% complete`}</h2>
          <p className="text-sm text-muted mt-0.5">
            {pct >= 100 ? "Share the link in your emails so investors can dig in." : "Investors who open a complete data room are far more likely to take a call. Fill the gaps below."}
          </p>
        </div>
        <button className="btn-ghost" disabled={busy} onClick={() => file.current?.click()}>
          <Wand2 size={15} /> {busy ? "Reading your deck…" : "Draft from my deck"}
        </button>
        <input ref={file} type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && fromDeck(e.target.files[0])} />
      </div>
      <div className="mt-4 h-2 rounded-full bg-surface overflow-hidden">
        <div className={`h-full ${tone} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      {missing.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {missing.map((m) => (
            <a key={m.id} href={`#sec-${m.id}`} className="chip px-2.5 py-1 hover:border-brand">
              <Plus size={12} /> {m.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function PublicLink({ r, put }: { r: Room; put: (b: Record<string, unknown>) => void }) {
  const toast = useToast();
  const isPublic = r.published && r.access === "public";
  return (
    <div className="card p-4 space-y-3 text-sm">
      <h2 className="font-semibold flex items-center gap-2">
        <Globe size={16} className="text-brand" /> Public link
      </h2>
      {isPublic ? (
        <>
          <div className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2">
            <span className="flex-1 truncate font-medium">{r.url.replace(/^https?:\/\//, "")}</span>
            <button className="text-brand" aria-label="Copy public link" onClick={() => navigator.clipboard.writeText(r.url).then(() => toast("Link copied"))}>
              <Copy size={15} />
            </button>
            <a href={r.url} target="_blank" rel="noreferrer" className="text-muted" aria-label="Open public page">
              <ExternalLink size={15} />
            </a>
          </div>
          <p className="text-xs text-muted">Anyone with this link can view your data room. Documents still need an email to download.</p>
          <button className="btn-ghost btn-sm" onClick={() => put({ access: "magic" })}>
            <Lock size={14} /> Make private again
          </button>
        </>
      ) : (
        <>
          <p className="text-muted">One link you can paste into emails, LinkedIn or your deck. Turn it off any time.</p>
          <button className="btn-primary w-full" onClick={() => put({ published: true, access: "public" })}>
            <Globe size={15} /> Create public link
          </button>
        </>
      )}
    </div>
  );
}

export default function DataRoomPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<Room>({ queryKey: ["room"], queryFn: () => api("/data-room") });
  const [c, setC] = useState<RoomContent | null>(null);
  const [password, setPassword] = useState("");
  useEffect(() => {
    if (q.data) setC(q.data.content);
  }, [q.data]);
  const put = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Room>("/data-room", { method: "PUT", json: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["room"] });
      setPassword("");
      toast("Saved");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const restore = useMutation({ mutationFn: (i: number) => api(`/data-room/restore/${i}`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["room"] }) });
  if (q.isLoading || (q.data && !c)) return <ListSkeleton rows={4} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const r = q.data!;
  const content = c!;
  const dirty = JSON.stringify(content) !== JSON.stringify(r.content);
  const setSec = (i: number, s: RoomSection) => setC({ ...content, sections: content.sections.map((x, j) => (j === i ? s : x)) });
  const move = (i: number, d: number) => {
    const s = [...content.sections];
    [s[i], s[i + d]] = [s[i + d], s[i]];
    setC({ ...content, sections: s });
  };
  const hero = content.hero;
  return (
    <>
      <PageHeader
        title="Data room"
        sub={
          <a href={r.url} target="_blank" rel="noreferrer" className="text-brand inline-flex items-center gap-1 break-all">
            {r.url.replace(/^https?:\/\//, "")} <ExternalLink size={12} />
          </a>
        }
        actions={
          <button className={r.published ? "btn-ghost" : "btn-primary"} onClick={() => put.mutate({ published: !r.published })}>
            {r.published ? "Unpublish" : "Publish"}
          </button>
        }
      />
      <div className="grid lg:grid-cols-[1fr_360px] gap-4 pb-24">
        <div className="space-y-4">
          <Completeness r={r} />
          <div className="card p-4 space-y-3">
            <h2 className="font-semibold">Top of the page</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label="Company">
                <input className="input" value={hero.title} onChange={(e) => setC({ ...content, hero: { ...hero, title: e.target.value } })} />
              </Field>
              <Field label="Raising">
                <input className="input" value={hero.round ?? ""} onChange={(e) => setC({ ...content, hero: { ...hero, round: e.target.value } })} placeholder="$1.5M seed" />
              </Field>
            </div>
            <Field label="One-liner">
              <input className="input" value={hero.one_liner ?? ""} onChange={(e) => setC({ ...content, hero: { ...hero, one_liner: e.target.value } })} />
            </Field>
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label="Button label">
                <input className="input" value={hero.cta_label ?? ""} onChange={(e) => setC({ ...content, hero: { ...hero, cta_label: e.target.value } })} />
              </Field>
              <Field label="Button link (Calendly, email…)">
                <input className="input" value={hero.cta_url ?? ""} onChange={(e) => setC({ ...content, hero: { ...hero, cta_url: e.target.value } })} placeholder="https://cal.com/you" />
              </Field>
            </div>
          </div>
          {content.sections.map((s, i) => (
            <div key={s.id} id={`sec-${s.id}`} className="card p-4 scroll-mt-20">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs uppercase tracking-wide text-muted">{TYPES.find((t) => t[0] === s.type)?.[1]}</span>
                <div className="flex gap-1 text-muted">
                  <button className="p-1" disabled={i === 0} aria-label="Move up" onClick={() => move(i, -1)}>
                    <ArrowUp size={14} />
                  </button>
                  <button className="p-1" disabled={i === content.sections.length - 1} aria-label="Move down" onClick={() => move(i, 1)}>
                    <ArrowDown size={14} />
                  </button>
                  <button className="p-1" aria-label="Delete section" onClick={() => setC({ ...content, sections: content.sections.filter((_, j) => j !== i) })}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <SectionEditor s={s} onChange={(x) => setSec(i, x)} />
            </div>
          ))}
          <div className="flex flex-wrap gap-1.5">
            {TYPES.map(([t, l]) => (
              <button key={t} className="chip px-2.5 py-1" onClick={() => setC({ ...content, sections: [...content.sections, { id: `${t}-${Date.now().toString(36)}`, type: t, title: l, body: "" }] })}>
                <Plus size={12} /> {l}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <PublicLink r={r} put={(b) => put.mutate(b)} />
          <div className="card p-4 space-y-3 text-sm">
            <h2 className="font-semibold">Who can see it</h2>
            <select className="input" value={r.access} onChange={(e) => (e.target.value !== "password" || r.has_password) && put.mutate({ access: e.target.value })} aria-label="Access">
              <option value="public">Anyone with the address</option>
              <option value="email">Anyone who enters their email</option>
              <option value="password">Anyone with the password</option>
              <option value="magic">Only people with a personal link</option>
            </select>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); put.mutate({ password, access: "password" }); }}>
              <input className="input flex-1" type="password" minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={r.has_password ? "Change password" : "Set a password"} aria-label="Password" />
              <button className="btn-ghost" disabled={password.length < 6}>
                Set
              </button>
            </form>
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-0.5 accent-[var(--brand)]" checked={r.indexable} onChange={(e) => put.mutate({ indexable: e.target.checked })} />
              <span>
                Let search engines list it <span className="block text-xs text-muted">Off by default. Only applies when anyone can see it.</span>
              </span>
            </label>
          </div>
          <div className="card p-4">
            <h2 className="font-semibold mb-2">Documents</h2>
            <Docs room={r} />
          </div>
          <div className="card p-4">
            <h2 className="font-semibold mb-2">Share links</h2>
            <Links room={r} />
          </div>
          <div className="card p-4">
            <h2 className="font-semibold mb-2">Who viewed it</h2>
            <ViewsList />
          </div>
          {r.versions.length > 0 && (
            <div className="card p-4 text-sm">
              <h2 className="font-semibold mb-2">Earlier versions</h2>
              <ul className="space-y-1">
                {r.versions.map((v, i) => (
                  <li key={v.at} className="flex items-center justify-between">
                    <span className="text-muted">{fmtDate(v.at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                    <button className="text-brand text-xs" onClick={() => confirm("Restore this version? Your current page is kept as a version too.") && restore.mutate(i)}>
                      Restore
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      {dirty && (
        <div className="fixed left-0 right-0 md:left-auto md:right-6 bottom-[calc(64px_+_env(safe-area-inset-bottom))] md:bottom-20 z-20 px-4 md:px-0">
          <div className="card shadow-lg p-2 flex gap-2 md:w-80">
            <button className="btn-ghost flex-1" onClick={() => setC(r.content)}>
              Discard
            </button>
            <button className="btn-primary flex-1" disabled={put.isPending} onClick={() => put.mutate({ content })}>
              Save page
            </button>
          </div>
        </div>
      )}
    </>
  );
}

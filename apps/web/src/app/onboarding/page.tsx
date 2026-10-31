"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight, Check, FileUp, Loader2, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LogoMark } from "@/components/landing/LogoMark";
import { api, ApiError } from "@/lib/api";

type Profile = {
  company_name: string; one_liner: string; sectors: string[]; stage: string; geography: string; round_size: string;
  instrument: string; traction: string; business_model: string; investor_types: string[]; looking_for: string;
  shareable: Record<string, boolean>; deck_filename: string;
};

const STAGES = [["pre-seed", "Pre-seed"], ["seed", "Seed"], ["series-a", "Series A"], ["series-b", "Series B"]];
const TYPES = [["angel", "Angels"], ["vc", "VC funds"], ["syndicate", "Syndicates"], ["family_office", "Family offices"], ["cvc", "Corporate VCs"], ["accelerator", "Accelerators"]];
const GEOS = [["uk", "UK"], ["us", "US"], ["europe", "Europe"], ["india", "India"], ["sea", "South-East Asia"], ["global", "Global"]];
const MODELS = ["B2B SaaS", "Marketplace", "Consumer subscription", "Transactional / fees", "Hardware", "Services", "Other"];

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "rounded-full border px-3.5 py-1.5 text-sm font-medium transition",
        on ? "border-[#0f62fe] bg-[#0f62fe] text-white shadow-sm" : "border-[#d5dbe6] bg-white text-[#1c2740] hover:border-[#9fb3d9]",
      )}
    >
      {on && <Check size={13} className="inline -mt-0.5 mr-1" />}
      {children}
    </button>
  );
}

function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-2">
      <div className="text-[15px] font-semibold text-[#0b1220]">{children}</div>
      {hint && <div className="text-sm text-[#5b6680]">{hint}</div>}
    </div>
  );
}

const input = "w-full rounded-xl border border-[#d5dbe6] bg-white px-4 py-3 text-[15px] text-[#0b1220] placeholder:text-[#9aa3b5] outline-none focus:border-[#0f62fe] focus:ring-4 focus:ring-[#0f62fe]/15";

function Onboarding() {
  const q = useQuery<Profile>({ queryKey: ["profile"], queryFn: () => api("/workspace/profile") });
  const facets = useQuery<{ sectors: { value: string; count: number }[] }>({ queryKey: ["facets"], queryFn: () => api("/investors/facets") });
  const [p, setP] = useState<Profile | null>(null);
  const [step, setStep] = useState<"deck" | "form">("deck");
  const [reading, setReading] = useState(false);
  const [deckNote, setDeckNote] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (q.data && !p) setP({ ...q.data, investor_types: q.data.investor_types ?? [], looking_for: q.data.looking_for ?? "" });
  }, [q.data, p]);

  if (q.error) {
    if (typeof window !== "undefined") location.href = "/login?next=/onboarding";
    return null;
  }
  if (!p) return <div className="grid min-h-dvh place-items-center text-[#5b6680]"><Loader2 className="animate-spin" /></div>;

  const set = (k: keyof Profile, v: unknown) => setP({ ...p, [k]: v } as Profile);
  const toggle = (k: "sectors" | "investor_types", v: string) => set(k, p[k].includes(v) ? p[k].filter((x) => x !== v) : [...p[k], v].slice(0, 10));

  const upload = async (f: File) => {
    setErr("");
    setReading(true);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api<{ suggested: Partial<Profile>; slides: number; data_room?: { filled: string[] } }>("/workspace/deck", { method: "POST", body: fd });
      const s = r.suggested;
      setP((x) => x && {
        ...x,
        deck_filename: f.name,
        company_name: x.company_name || s.company_name || "",
        one_liner: x.one_liner || s.one_liner || "",
        sectors: x.sectors.length ? x.sectors : s.sectors ?? [],
        stage: x.stage || s.stage || "",
        round_size: x.round_size || s.round_size || "",
        traction: x.traction || s.traction || "",
        business_model: x.business_model || s.business_model || "",
        geography: x.geography || s.geography || "",
        instrument: x.instrument || s.instrument || "",
        investor_types: x.investor_types.length ? x.investor_types : s.investor_types ?? [],
        looking_for: x.looking_for || s.looking_for || "",
      });
      const n = r.data_room?.filled.length ?? 0;
      setDeckNote(`Read ${r.slides} slides. We filled in what we could below${n ? ` and drafted ${n} sections of your data room` : ""}. Check it over.`);
      setStep("form");
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.problem.title}${e.problem.detail ? `. ${e.problem.detail}` : ""}` : "We couldn't read that file.");
    } finally {
      setReading(false);
    }
  };

  const save = async () => {
    setErr("");
    if (!p.one_liner.trim() || !p.sectors.length) {
      setErr("Add a one-line description and at least one sector so we can match investors.");
      return;
    }
    setSaving(true);
    try {
      await api("/workspace/profile", { method: "PUT", json: p });
      location.href = "/app?welcome=1";
    } catch (e) {
      setErr(e instanceof ApiError ? e.problem.title : "Couldn't save. Please try again.");
      setSaving(false);
    }
  };

  const sectors = facets.data?.sectors ?? [];

  return (
    <div className="lp min-h-dvh bg-[#f5f7fb]">
      <header className="mx-auto flex max-w-3xl items-center justify-between px-5 py-6">
        <Link href="/app" className="flex items-center gap-2.5">
          <LogoMark size={34} />
          <span className="text-xl font-bold tracking-tight text-[#0b1220]">
            Easy<span className="text-[#0f62fe]">Fundraise</span>
          </span>
        </Link>
        <a href="/app" className="text-sm font-medium text-[#5b6680] hover:text-[#0b1220]">Skip for now</a>
      </header>
      <main className="mx-auto max-w-3xl px-5 pb-24">
        <p className="text-sm font-semibold uppercase tracking-wider text-[#0f62fe]">Step 3 of 3 · Your company</p>
        <h1 className="mt-2 text-3xl md:text-4xl font-bold tracking-tight text-[#0b1220]">Tell us about your raise</h1>
        <p className="mt-2 text-[16px] text-[#4a5670] max-w-xl">
          We use this to rank investors by how well they match you, and to personalise every email. Two minutes, and you can change it any time.
        </p>

        {err && <p role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{err}</p>}

        {step === "deck" && (
          <div className="mt-8 grid gap-4 md:grid-cols-2">
            <button
              type="button"
              disabled={reading}
              onClick={() => file.current?.click()}
              className="group rounded-3xl border-2 border-dashed border-[#bcd3ff] bg-white p-7 text-left shadow-sm transition hover:border-[#0f62fe] hover:shadow-md"
            >
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[#eef4ff] text-[#0f62fe]">
                {reading ? <Loader2 className="animate-spin" /> : <FileUp />}
              </span>
              <span className="mt-4 block text-lg font-semibold text-[#0b1220]">{reading ? "Reading your deck…" : "Upload your pitch deck"}</span>
              <span className="mt-1 block text-sm text-[#4a5670]">PDF, up to 20 slides. We fill in your profile and draft your data room from it.</span>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-[#0f62fe]">
                <Sparkles size={15} /> Recommended
              </span>
            </button>
            <button type="button" onClick={() => setStep("form")} className="rounded-3xl border border-[#e2e7f0] bg-white p-7 text-left shadow-sm transition hover:border-[#9fb3d9] hover:shadow-md">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[#f1f3f8] text-[#1c2740]">
                <ArrowRight />
              </span>
              <span className="mt-4 block text-lg font-semibold text-[#0b1220]">Answer a few questions</span>
              <span className="mt-1 block text-sm text-[#4a5670]">No deck handy? Describe your company and what you&apos;re looking for.</span>
            </button>
            <input ref={file} type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </div>
        )}

        {step === "form" && (
          <div className="mt-8 space-y-6 rounded-3xl border border-[#e2e7f0] bg-white p-6 md:p-8 shadow-sm">
            {deckNote && (
              <p className="flex gap-2 rounded-xl bg-[#eef8f3] px-4 py-3 text-sm text-[#0f5a45]">
                <Check size={16} className="mt-0.5 shrink-0" /> {deckNote}
              </p>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Company name</Label>
                <input className={input} value={p.company_name} onChange={(e) => set("company_name", e.target.value)} placeholder="DocAI" />
              </div>
              <div>
                <Label>Business model</Label>
                <select className={input} value={MODELS.includes(p.business_model) ? p.business_model : p.business_model ? "Other" : ""} onChange={(e) => set("business_model", e.target.value)}>
                  <option value="">Choose…</option>
                  {MODELS.map((m) => <option key={m}>{m}</option>)}
                </select>
              </div>
            </div>
            <div>
              <Label hint="One sentence an investor would repeat to their partners.">What does your company do?</Label>
              <textarea className={`${input} min-h-24`} value={p.one_liner} onChange={(e) => set("one_liner", e.target.value)} placeholder="AI triage for primary-care clinics that cuts nurse workload by 30%" />
            </div>
            <div>
              <Label hint="Pick up to 10. We match investors who back these.">Industry</Label>
              <div className="flex flex-wrap gap-2">
                {sectors.slice(0, 30).map((s) => <Chip key={s.value} on={p.sectors.includes(s.value)} onClick={() => toggle("sectors", s.value)}>{s.value}</Chip>)}
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label>Stage</Label>
                <select className={input} value={p.stage} onChange={(e) => set("stage", e.target.value)}>
                  <option value="">Choose…</option>
                  {STAGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div>
                <Label>Raising</Label>
                <input className={input} value={p.round_size} onChange={(e) => set("round_size", e.target.value)} placeholder="$1.5M" />
              </div>
              <div>
                <Label>Instrument</Label>
                <select className={input} value={p.instrument} onChange={(e) => set("instrument", e.target.value)}>
                  <option value="">Not sure yet</option>
                  <option>SAFE</option>
                  <option>Note</option>
                  <option>Equity</option>
                </select>
              </div>
            </div>
            <div>
              <Label hint="Choose all that apply.">Who do you want to raise from?</Label>
              <div className="flex flex-wrap gap-2">
                {TYPES.map(([v, l]) => <Chip key={v} on={p.investor_types.includes(v)} onClick={() => toggle("investor_types", v)}>{l}</Chip>)}
              </div>
            </div>
            <div>
              <Label>Where should investors be based?</Label>
              <div className="flex flex-wrap gap-2">
                {GEOS.map(([v, l]) => <Chip key={v} on={p.geography === v} onClick={() => set("geography", p.geography === v ? "" : v)}>{l}</Chip>)}
              </div>
            </div>
            <div>
              <Label hint="Revenue, users, pilots, growth. Numbers beat adjectives.">Traction</Label>
              <input className={input} value={p.traction} onChange={(e) => set("traction", e.target.value)} placeholder="40 clinics live, $25K MRR, 12% month-on-month" />
            </div>
            <div>
              <Label hint="Beyond money: sector expertise, intros, a lead investor, cheque size…">What are you looking for in an investor?</Label>
              <textarea className={`${input} min-h-24`} value={p.looking_for} onChange={(e) => set("looking_for", e.target.value)} placeholder="A lead angel or seed fund with NHS or clinical networks, cheques of $100K–$500K" />
            </div>
            <div className="flex flex-col-reverse gap-3 border-t border-[#eef1f6] pt-6 sm:flex-row sm:items-center sm:justify-between">
              <button type="button" onClick={() => setStep("deck")} className="text-sm font-medium text-[#5b6680] hover:text-[#0b1220]">
                {p.deck_filename ? `Deck: ${p.deck_filename} · replace` : "Upload a deck instead"}
              </button>
              <button type="button" disabled={saving} onClick={save} className="lp-btn-primary px-7 py-3.5 text-[16px] disabled:opacity-60">
                {saving ? "Finding your matches…" : "Show my investor matches"} <ArrowRight size={18} />
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function OnboardingPage() {
  const [qc] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={qc}>
      <Onboarding />
    </QueryClientProvider>
  );
}

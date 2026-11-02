"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Megaphone, RefreshCw, Shuffle, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { errText, useToast } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";

export type Angle = { label: string; message: string };
export type Playbook = {
  angles: Angle[];
  special_line: string;
  shuffle: boolean;
  quick_update: string;
  quick_update_at: string | null;
  active: boolean;
  unsent: number;
  money_warning: boolean;
};

const EXAMPLES = [
  "230m people ask ChatGPT health questions every week and hit a dead end. We connect them to a real doctor in minutes.",
  "We launch to 1m users with 1,500 doctors, on an AI model built from 875k consultations.",
  "4.6bn people have no access to basic healthcare.",
];

export function usePlaybook() {
  return useQuery<Playbook>({ queryKey: ["playbook"], queryFn: () => api("/outreach/playbook") });
}

function useRefresh() {
  const qc = useQueryClient();
  return (p?: Playbook) => {
    if (p) qc.setQueryData(["playbook"], p);
    qc.invalidateQueries({ queryKey: ["sequences"] });
    qc.invalidateQueries({ queryKey: ["sequence"] });
  };
}

/** A short recent update. New drafts carry it, and saving also puts it in the next email still to go out. */
export function QuickUpdate({ compact = false }: { compact?: boolean }) {
  const toast = useToast();
  const refresh = useRefresh();
  const q = usePlaybook();
  const [text, setText] = useState("");
  useEffect(() => {
    if (q.data) setText(q.data.quick_update);
  }, [q.data]);
  const save = useMutation({
    mutationFn: (t: string) => api<Playbook & { changed: number }>("/outreach/quick-update", { method: "PUT", json: { text: t, apply: true } }),
    onSuccess: (r, t) => {
      refresh(r);
      setText(r.quick_update);
      toast(t.trim() ? `Update saved${r.changed ? `, added to ${r.changed} unsent email${r.changed === 1 ? "" : "s"}` : ". New drafts will include it"}` : "Update cleared");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const saved = q.data?.quick_update ?? "";
  const dirty = text.trim() !== saved;
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <Megaphone size={15} className="text-brand" />
        <span className="text-sm font-semibold">Quick update</span>
        {saved && q.data?.quick_update_at && <span className="text-xs text-muted">saved {fmtDate(q.data.quick_update_at, { day: "numeric", month: "short" })}</span>}
      </div>
      {!compact && <p className="text-xs text-muted mb-2">A line of recent news. It goes into the next email each investor gets, as “Quick update: …”, and into every new draft.</p>}
      <form
        className="flex flex-col sm:flex-row gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) save.mutate(text);
        }}
      >
        <input className="input flex-1" maxLength={300} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. We just signed our third hospital partner" aria-label="Quick update" />
        <div className="flex gap-2">
          <button className="btn-primary flex-1 sm:flex-none" disabled={!dirty || save.isPending}>
            {save.isPending ? "Saving…" : q.data?.unsent ? `Save and add to ${q.data.unsent} unsent` : "Save"}
          </button>
          {saved && (
            <button type="button" className="btn-ghost" title="Clear the update" onClick={() => save.mutate("")} disabled={save.isPending}>
              <X size={16} /> <span className="sm:hidden">Clear</span>
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

/** What emails 1, 2 and 3 focus on, in the founder's words, plus one special line. */
export function PlaybookEditor() {
  const toast = useToast();
  const refresh = useRefresh();
  const q = usePlaybook();
  const [angles, setAngles] = useState<Angle[]>([]);
  const [special, setSpecial] = useState("");
  const [shuffle, setShuffle] = useState(true);
  useEffect(() => {
    if (q.data) {
      setAngles(q.data.angles);
      setSpecial(q.data.special_line);
      setShuffle(q.data.shuffle);
    }
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<Playbook>("/outreach/playbook", { method: "PUT", json: { angles, special_line: special, shuffle } }),
    onSuccess: (r) => {
      refresh(r);
      toast("Playbook saved. New drafts follow it");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const redraft = useMutation({
    mutationFn: () => api<Playbook & { redrafted: number }>("/outreach/playbook/redraft", { method: "POST" }),
    onSuccess: (r) => {
      refresh(r);
      toast(r.redrafted ? `Redrafted ${r.redrafted} draft${r.redrafted === 1 ? "" : "s"}` : "No unapproved drafts to redraft");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  if (!q.data || angles.length < 3) return <div className="skeleton h-40" />;
  const dirty = JSON.stringify([angles, special, shuffle]) !== JSON.stringify([q.data.angles, q.data.special_line, q.data.shuffle]);
  const set = (i: number, k: keyof Angle, v: string) => setAngles((a) => a.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        {angles.map((a, i) => (
          <div key={i} className="rounded-xl border border-line p-3 bg-surface/40">
            <div className="flex items-center gap-2 mb-2">
              <span className="grid place-items-center size-6 rounded-full bg-brand/10 text-brand text-xs font-bold shrink-0">{i + 1}</span>
              <input className="input h-8 text-sm font-semibold" maxLength={60} value={a.label} onChange={(e) => set(i, "label", e.target.value)} aria-label={`Email ${i + 1} focus`} />
            </div>
            <textarea className="textarea min-h-28 text-sm" maxLength={600} value={a.message} onChange={(e) => set(i, "message", e.target.value)} placeholder={EXAMPLES[i]} aria-label={`Email ${i + 1} key message`} />
          </div>
        ))}
      </div>
      <div>
        <label className="label flex items-center gap-1.5" htmlFor="special-line">
          <Sparkles size={13} className="text-brand" /> Special line, used once in one of the three emails
        </label>
        <input id="special-line" className="input" maxLength={300} value={special} onChange={(e) => setSpecial(e.target.value)} placeholder="We were selected by EWOR (top 0.1% of founders), 10x more competitive than Y Combinator." />
      </div>
      <label className="flex items-start gap-2 text-sm cursor-pointer">
        <input type="checkbox" className="mt-0.5 accent-[var(--brand)]" checked={shuffle} onChange={(e) => setShuffle(e.target.checked)} />
        <span>
          <span className="font-medium inline-flex items-center gap-1">
            <Shuffle size={13} /> Shuffle the order for each investor
          </span>
          <span className="block text-xs text-muted">One investor gets 3, 1, 2, the next 2, 3, 1, and so on. Your agent rewords each message for each investor and keeps your numbers exactly.</span>
        </span>
      </label>
      {q.data.money_warning && (
        <p className="text-xs text-warn flex gap-1.5">
          <AlertTriangle size={14} className="shrink-0 mt-px" /> Something here talks about money or investing. Cold emails leave that out, so the agent will reword it, and email 3 should lean on market size and momentum instead.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save playbook"}
        </button>
        <button className="btn-ghost" onClick={() => redraft.mutate()} disabled={dirty || redraft.isPending} title="Redraft every draft you haven't approved yet. Scheduled and sent emails stay as they are.">
          <RefreshCw size={15} className={redraft.isPending ? "animate-spin" : ""} /> {redraft.isPending ? "Redrafting…" : "Redraft unapproved drafts"}
        </button>
      </div>
    </div>
  );
}

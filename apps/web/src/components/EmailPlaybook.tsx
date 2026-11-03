"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Eye, Loader2, Megaphone, Plus, RefreshCw, Sparkles, Star, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Sheet, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

export type EmailPlan = { focus: string; message: string };
export type Playbook = {
  emails: EmailPlan[];
  ask: string;
  strengths: string[];
  update: string;
  update_at: string | null;
  saved_at: string | null;
  unsent: number;
  pending: number; // outreach investors nothing has been sent to yet
  money_warning: boolean;
};
export type Fill = {
  emails: EmailPlan[];
  ask: string;
  strengths: string[];
  update_example: string;
  source: "data room" | "deck" | "profile" | "generic";
  prompts: { label: string; text: string; send?: boolean }[];
};
type Preview = { investor: { id: string; name: string; firm: string }; engine: string; emails: { step: number; subject: string; body: string; update: boolean }[] };

const SHAPE = [
  "About them and the synergy with you → {focus} → what you're looking for → call to action",
  "{focus} (instead of the synergy) → what you're building, said another way → what you're looking for → call to action",
  "{focus} → what you're looking for → call to action",
];
const FOCUS_OPTIONS = ["What we're building", "The problem we solve", "Market opportunity and traction", "Traction so far", "A customer story", "Why now", "Our team"];
const HINTS = [
  "What you're building, in one or two sentences.",
  "The problem you solve, with one number that shows how big it is.",
  "How big the market is, and your best proof so far: users, customers, growth or a pilot.",
];

export function usePlaybook() {
  return useQuery<Playbook>({ queryKey: ["playbook"], queryFn: () => api("/outreach/playbook") });
}

/** The AI fill for this founder's current focuses, from their own data room and deck (neutral blanks when there's no deck). */
export function useSuggest() {
  return useQuery<Fill>({ queryKey: ["playbook-suggest"], queryFn: () => api("/outreach/playbook/suggest"), staleTime: 10 * 60_000 });
}

function useRefresh() {
  const qc = useQueryClient();
  return (p?: Playbook) => {
    if (p) qc.setQueryData(["playbook"], p);
    for (const k of ["sequences", "sequence", "playbook-suggest"]) qc.invalidateQueries({ queryKey: [k] });
  };
}

/** A round / progress / FOMO update. It becomes the next follow-up each investor gets. */
export function UpdateBox({ compact = false }: { compact?: boolean }) {
  const toast = useToast();
  const refresh = useRefresh();
  const q = usePlaybook();
  const sg = useSuggest();
  const [text, setText] = useState("");
  useEffect(() => {
    if (q.data) setText(q.data.update);
  }, [q.data]);
  const save = useMutation({
    mutationFn: (t: string) => api<Playbook & { changed: number }>("/outreach/quick-update", { method: "PUT", json: { text: t, apply: true } }),
    onSuccess: (r, t) => {
      refresh(r);
      setText(r.update);
      toast(t.trim() ? `Update saved${r.changed ? `. It's now the next follow-up for ${r.changed} investor${r.changed === 1 ? "" : "s"}` : ""}` : "Update cleared, follow-ups restored");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const saved = q.data?.update ?? "";
  const dirty = text.trim() !== saved;
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <Megaphone size={15} className="text-brand" />
        <span className="text-sm font-semibold">Round & progress update</span>
      </div>
      {!compact && (
        <p className="text-xs text-muted mb-2">
          News about the round, momentum or progress. The next follow-up each investor gets becomes a short update: this first, then what you&apos;re looking for and a call. Clear it to put the normal follow-ups back.
        </p>
      )}
      <form
        className="flex flex-col sm:flex-row gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) save.mutate(text);
        }}
      >
        <input
          className="input flex-1"
          maxLength={400}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={sg.data?.update_example ? `e.g. ${sg.data.update_example}` : "e.g. Half the round is committed and we close at the end of the month"}
          aria-label="Round and progress update"
        />
        <div className="flex gap-2">
          <button className="btn-primary flex-1 sm:flex-none" disabled={!dirty || save.isPending}>
            {save.isPending ? "Saving…" : q.data?.unsent ? `Save, send as next follow-up (${q.data.unsent})` : "Save"}
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

function PreviewPane({ draft }: { draft: { emails: EmailPlan[]; ask: string; strengths: string[] } }) {
  const toast = useToast();
  const [data, setData] = useState<Preview | null>(null);
  const seen = useRef<string[]>([]);
  const run = useMutation({
    mutationFn: (another: boolean) => api<Preview>("/outreach/playbook/preview", { method: "POST", json: { ...draft, skip: another ? seen.current : [] } }),
    onSuccess: (r) => {
      setData(r);
      if (!seen.current.includes(r.investor.id)) seen.current = [...seen.current, r.investor.id];
    },
    onError: (e) => toast(errText(e), "err"),
  });
  return (
    <div className="rounded-xl border border-line bg-surface/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Eye size={15} className="text-brand" />
        <span className="text-sm font-semibold flex-1">Preview the 3 emails</span>
        {data && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => run.mutate(true)} disabled={run.isPending}>
            <RefreshCw size={13} /> Another investor
          </button>
        )}
        <button type="button" className="btn-primary btn-sm" onClick={() => run.mutate(false)} disabled={run.isPending}>
          {run.isPending ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {run.isPending ? "Writing…" : data ? "Write again" : "Write a preview"}
        </button>
      </div>
      {!data && !run.isPending && <p className="text-xs text-muted mt-1.5">Your agent writes the full sequence for one real investor from your shortlist, the way it would send it. Nothing is saved or sent.</p>}
      {run.isPending && !data && <div className="skeleton h-40 mt-3" />}
      {data && (
        <div className={clsx("mt-3 space-y-3", run.isPending && "opacity-50")}>
          <div className="text-xs text-muted flex items-center gap-1.5">
            <UserRound size={13} /> For {data.investor.name}
            {data.investor.firm ? `, ${data.investor.firm}` : ""}. {"{first name}"} becomes each investor's own first name when it's sent.
          </div>
          {data.emails.map((e) => (
            <div key={e.step} className="rounded-lg border border-line bg-card p-3">
              <div className="flex items-center gap-2 text-xs text-muted mb-1">
                <span className="font-semibold text-ink">Email {e.step}</span>
                {e.update && <span className="chip">round update</span>}
              </div>
              <div className="text-sm font-medium mb-1.5">{e.subject}</div>
              <p className="text-sm whitespace-pre-wrap break-words text-[#334155]">{e.body}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** How emails 1, 2 and 3 are built: each one's main focus and what it says (filled by AI from the deck), what
 *  the founder is looking for, their strengths, and a preview of the full emails. */
export function PlaybookEditor({ onSaved }: { onSaved?: () => void }) {
  const toast = useToast();
  const refresh = useRefresh();
  const q = usePlaybook();
  const sg = useSuggest();
  const [emails, setEmails] = useState<EmailPlan[]>([]);
  const [ask, setAsk] = useState("");
  const [strengths, setStrengths] = useState<string[]>([]);
  const [drafted, setDrafted] = useState<"" | Fill["source"]>("");
  const apply = (f: Fill) => {
    setEmails(f.emails.map((e) => ({ ...e })));
    if (f.ask) setAsk(f.ask);
    if (f.strengths.length) setStrengths(f.strengths);
    setDrafted(f.source);
  };
  useEffect(() => {
    if (q.data) {
      setEmails(q.data.emails);
      setAsk(q.data.ask);
      setStrengths(q.data.strengths);
      setDrafted("");
    }
  }, [q.data]);
  // Never set up: start from what the agent picked out of the deck (unsaved until they press Save).
  useEffect(() => {
    if (q.data && !q.data.saved_at && sg.data && sg.data.source !== "generic") apply(sg.data);
  }, [q.data, sg.data]);
  const fill = useMutation({
    mutationFn: () => api<Fill>("/outreach/playbook/fill", { method: "POST", json: { focuses: emails.map((e) => e.focus), refresh: true } }),
    onSuccess: (f) => {
      if (f.source === "generic") toast("Fill in your data room or upload your deck first, so your agent has something to work from", "err");
      else apply(f);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const save = useMutation({
    mutationFn: () => api<Playbook>("/outreach/playbook", { method: "PUT", json: { emails, ask, strengths: strengths.filter((s) => s.trim()) } }),
    onSuccess: (r) => {
      refresh(r);
      toast(r.pending ? `Saved. Investors you add from now on get these emails. Press “Update ${r.pending} pending investor${r.pending === 1 ? "" : "s"}” to rewrite the ones already waiting` : "Saved. Investors you add from now on get these emails");
      onSaved?.();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  // One investor per request (AI drafting takes ~15s each), so no request runs into the proxy timeout.
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const redraft = useMutation({
    mutationFn: async () => {
      type R = Playbook & { redrafted: number; scheduled_kept: number; back_to_draft: number; left: number; done_ids: string[] };
      const done: string[] = [];
      const sum = { redrafted: 0, scheduled_kept: 0, back_to_draft: 0 };
      let last: R | null = null;
      setProgress({ done: 0, total: q.data?.pending ?? 0 });
      for (let i = 0; i < 500; i++) {
        last = await api<R>("/outreach/playbook/redraft", { method: "POST", json: { skip: done, batch: 1 } });
        done.push(...last.done_ids);
        sum.redrafted += last.redrafted;
        sum.scheduled_kept += last.scheduled_kept;
        sum.back_to_draft += last.back_to_draft;
        setProgress({ done: done.length, total: done.length + last.left });
        if (!last.left || !last.redrafted) break;
      }
      return { ...last!, ...sum };
    },
    onSuccess: (r) => {
      setProgress(null);
      refresh(r);
      if (!r.redrafted) return toast("No pending outreach to update. Everyone has been sent something already");
      const bits = [`Updated ${r.redrafted} investor${r.redrafted === 1 ? "" : "s"} with these emails, each with its own subject line.`];
      if (r.scheduled_kept) bits.push(`${r.scheduled_kept} scheduled keep their send times.`);
      if (r.back_to_draft) bits.push(`${r.back_to_draft} went back to drafts to check and approve again.`);
      toast(bits.join(" "));
    },
    onError: (e) => {
      setProgress(null);
      refresh();
      toast(`${errText(e)}. The ones already done keep their new emails; press again to finish the rest.`, "err");
    },
  });
  if (!q.data || emails.length < 3) return <div className="skeleton h-48" />;
  const draft = { emails, ask, strengths: strengths.filter((s) => s.trim()) };
  const dirty = JSON.stringify(draft) !== JSON.stringify({ emails: q.data.emails, ask: q.data.ask, strengths: q.data.strengths }) || !q.data.saved_at;
  const set = (i: number, k: keyof EmailPlan, v: string) => setEmails((a) => a.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-ghost btn-sm" onClick={() => fill.mutate()} disabled={fill.isPending}>
          {fill.isPending ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} className="text-brand" />} {fill.isPending ? "Reading your data room…" : "Refresh from my data room"}
        </button>
        {drafted && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 text-brand px-2.5 py-1 text-xs font-medium">
            <Sparkles size={12} /> Filled from your {drafted === "profile" ? "company profile" : drafted}. Check it, then save.
          </span>
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        {emails.map((e, i) => (
          <div key={i} className="rounded-xl border border-line p-3 bg-surface/40 flex flex-col">
            <div className="flex items-center gap-2 mb-1">
              <span className="grid place-items-center size-6 rounded-full bg-brand/10 text-brand text-xs font-bold shrink-0">{i + 1}</span>
              <span className="text-sm font-semibold">{i === 0 ? "First email" : `Follow-up ${i}`}</span>
            </div>
            <p className="text-[11px] text-muted mb-2 leading-snug">{SHAPE[i].replace("{focus}", e.focus.toLowerCase() || "main focus")}</p>
            <label className="label" htmlFor={`focus-${i}`}>Main focus</label>
            <input id={`focus-${i}`} className="input h-9 text-sm font-medium" list={`focus-options-${i}`} maxLength={80} value={e.focus} onChange={(ev) => set(i, "focus", ev.target.value)} />
            <datalist id={`focus-options-${i}`}>
              {FOCUS_OPTIONS.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
            <label className="label mt-2" htmlFor={`msg-${i}`}>What it says</label>
            <textarea id={`msg-${i}`} className="textarea min-h-24 text-sm flex-1" maxLength={600} value={e.message} onChange={(ev) => set(i, "message", ev.target.value)} placeholder={HINTS[i]} />
          </div>
        ))}
      </div>

      <div>
        <label className="label" htmlFor="pb-ask">What you&apos;re looking for (in every email)</label>
        <textarea id="pb-ask" className="textarea min-h-16 text-sm" maxLength={400} value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="e.g. We're raising $750k pre-seed and looking for an angel with healthcare distribution." />
      </div>

      <div>
        <div className="label flex items-center gap-1.5">
          <Star size={13} className="text-brand" /> Your strengths (each goes into one email per investor)
        </div>
        <div className="space-y-2">
          {strengths.map((s, i) => (
            <div key={i} className="flex gap-2">
              <input className="input text-sm" maxLength={300} value={s} onChange={(e) => setStrengths((a) => a.map((x, j) => (j === i ? e.target.value : x)))} aria-label={`Strength ${i + 1}`} />
              <button type="button" className="btn-ghost px-3" onClick={() => setStrengths((a) => a.filter((_, j) => j !== i))} aria-label="Remove strength">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          {strengths.length < 4 && (
            <button type="button" className="btn-ghost btn-sm" onClick={() => setStrengths((a) => [...a, ""])}>
              <Plus size={13} /> Add a strength
            </button>
          )}
          {!strengths.length && <p className="text-xs text-muted">e.g. the team&apos;s history together, an accelerator you were picked for, an award, a notable customer or advisor.</p>}
        </div>
      </div>

      {q.data.money_warning && (
        <p className="text-xs text-warn flex gap-1.5">
          <AlertTriangle size={14} className="shrink-0 mt-px" /> Something here mentions an investor&apos;s ticket, cheque or valuation, or the word &quot;invest&quot;. Emails leave those out, so your agent will reword it. Your own raise amount is fine.
        </p>
      )}

      <PreviewPane draft={draft} />

      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : q.data.saved_at ? "Save changes" : "Save my emails"}
        </button>
        {q.data.saved_at && q.data.pending > 0 && (
          <button
            className={dirty ? "btn-ghost" : "btn-primary"}
            onClick={() => redraft.mutate()}
            disabled={dirty || redraft.isPending}
            title={dirty ? "Save first, then update your pending investors" : "Rewrite the emails of every outreach investor who hasn't been sent anything yet. Anyone already emailed stays as they are."}
          >
            <RefreshCw size={15} className={redraft.isPending ? "animate-spin" : ""} />{" "}
            {redraft.isPending
              ? `Updating ${Math.min((progress?.done ?? 0) + 1, progress?.total || 1)} of ${progress?.total || q.data.pending}…`
              : `Update ${q.data.pending} pending investor${q.data.pending === 1 ? "" : "s"}`}
          </button>
        )}
      </div>
    </div>
  );
}

/** The playbook in a sheet, opened from Outreach (button, first visit, ?playbook=1). */
export function PlaybookSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} onClose={onClose} title="Your emails 1, 2 and 3" xl>
      <PlaybookEditor onSaved={onClose} />
    </Sheet>
  );
}

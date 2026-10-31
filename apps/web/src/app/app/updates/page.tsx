"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Megaphone, Plus, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Empty, ErrorState, Field, ListSkeleton, Sheet, errText, useToast } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";

type B = { id: string; kind: string; template: string; title: string; status: string; created_at: string; recipients: number; sent: number; opened: number; replied: number };
type List = { items: B[]; templates: Record<string, Record<string, string>>; committed: string; nameable: { id: string; name: string; firm: string }[] };
type Aud = { count: number; without_email: number; items: { id: string; name: string; firm: string; stage: number }[] };

const STAGES = ["Lead", "Contacted", "Engaged", "Call booked", "Deck sent", "Due diligence", "Term sheet", "Committed", "Closed"];

function Composer({ data, onClose }: { data: List; onClose: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const [kind, setKind] = useState<"round_update" | "investor_update">("round_update");
  const [template, setTemplate] = useState("first_close");
  const [inputs, setInputs] = useState<Record<string, any>>({ amount_committed: data.committed || "", metrics: [{ label: "", value: "" }], wins: [""], asks: [""] });
  const [stages, setStages] = useState<[number, number]>([2, 7]);
  const [exclude, setExclude] = useState<string[]>([]);
  const [followUp, setFollowUp] = useState(false);
  const set = (k: string, v: unknown) => setInputs((x) => ({ ...x, [k]: v }));
  useEffect(() => {
    if (kind === "investor_update") {
      setTemplate("monthly");
      setStages([1, 9]);
    } else {
      setTemplate("first_close");
      setStages([2, 7]);
    }
  }, [kind]);
  const aud = useQuery<Aud>({
    queryKey: ["audience", stages, exclude],
    queryFn: () => api("/broadcasts/audience", { method: "POST", json: { stages, exclude_card_ids: exclude } }),
  });
  const create = useMutation({
    mutationFn: () => api<{ id: string }>("/broadcasts", { method: "POST", json: { kind, template, inputs, audience: { stages, exclude_card_ids: exclude, statuses: ["Active"] }, follow_up: followUp } }),
    onSuccess: (b) => router.push(`/app/updates/${b.id}`),
    onError: (e) => toast(errText(e), "err"),
  });
  const leads: string[] = inputs.lead_card_ids ?? [];
  const list = (k: string, ph: string) => (
    <div className="space-y-1.5">
      {(inputs[k] as string[]).map((v, i) => (
        <input key={i} className="input" value={v} placeholder={ph} onChange={(e) => set(k, (inputs[k] as string[]).map((x, j) => (j === i ? e.target.value : x)).concat(i === inputs[k].length - 1 && e.target.value ? [""] : []))} />
      ))}
    </div>
  );
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <div className="grid grid-cols-2 gap-2" role="group" aria-label="Kind">
        {(["round_update", "investor_update"] as const).map((k) => (
          <button type="button" key={k} onClick={() => setKind(k)} className={`rounded-lg border p-3 text-left text-sm ${kind === k ? "border-brand bg-brand/5" : "border-line"}`}>
            <b>{k === "round_update" ? "Round update" : "Investor update"}</b>
            <div className="text-xs text-muted">{k === "round_update" ? "Momentum news to investors still deciding" : "Monthly or quarterly news for backers"}</div>
          </button>
        ))}
      </div>
      <Field label="Template">
        <select className="input" value={template} onChange={(e) => setTemplate(e.target.value)}>
          {Object.entries(data.templates[kind] ?? {}).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      {kind === "round_update" ? (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Committed so far">
              <input className="input" value={inputs.amount_committed ?? ""} onChange={(e) => set("amount_committed", e.target.value)} placeholder="$900K" />
            </Field>
            <Field label="% allocated">
              <input className="input" type="number" min={0} max={200} value={inputs.pct_allocated ?? ""} onChange={(e) => set("pct_allocated", e.target.value)} />
            </Field>
            <Field label="Round size">
              <input className="input" value={inputs.round_size ?? ""} onChange={(e) => set("round_size", e.target.value)} placeholder="From your profile" />
            </Field>
            <Field label="Closing date">
              <input className="input" value={inputs.closing_date ?? ""} onChange={(e) => set("closing_date", e.target.value)} placeholder="Friday 14 Nov" />
            </Field>
          </div>
          <Field label="Name backers (only those who agreed)">
            {data.nameable.length === 0 ? (
              <p className="text-xs text-muted">Nobody yet. Tick “OK to name in round updates” on a committed investor&apos;s card.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {data.nameable.map((n) => {
                  const on = leads.includes(n.id);
                  return (
                    <button type="button" key={n.id} className={`chip px-2.5 py-1 ${on ? "bg-brand text-white border-brand" : ""}`} onClick={() => set("lead_card_ids", on ? leads.filter((x) => x !== n.id) : [...leads, n.id])}>
                      {n.name}
                      {n.firm && ` · ${n.firm}`}
                    </button>
                  );
                })}
              </div>
            )}
          </Field>
          <Field label="Anything else (optional)">
            <textarea className="textarea min-h-20" value={inputs.extra ?? ""} onChange={(e) => set("extra", e.target.value)} />
          </Field>
        </>
      ) : (
        <>
          <Field label="Period">
            <input className="input" value={inputs.period ?? ""} onChange={(e) => set("period", e.target.value)} placeholder="October 2026" />
          </Field>
          <Field label="Key numbers">
            <div className="space-y-1.5">
              {(inputs.metrics as { label: string; value: string }[]).map((m, i) => (
                <div key={i} className="flex gap-2">
                  <input className="input flex-1" placeholder="MRR" value={m.label} onChange={(e) => set("metrics", inputs.metrics.map((x: any, j: number) => (j === i ? { ...x, label: e.target.value } : x)))} />
                  <input className="input flex-1" placeholder="$42K (+12%)" value={m.value} onChange={(e) => set("metrics", inputs.metrics.map((x: any, j: number) => (j === i ? { ...x, value: e.target.value } : x)))} />
                </div>
              ))}
              <button type="button" className="btn-ghost btn-sm" onClick={() => set("metrics", [...inputs.metrics, { label: "", value: "" }])}>
                <Plus size={14} /> Add number
              </button>
            </div>
          </Field>
          <Field label="Wins">{list("wins", "Signed NHS Leeds")}</Field>
          <Field label="Asks">{list("asks", "Intros to CFOs at mid-size clinics")}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Hiring">
              <input className="input" value={inputs.hiring ?? ""} onChange={(e) => set("hiring", e.target.value)} />
            </Field>
            <Field label="Runway">
              <input className="input" value={inputs.runway ?? ""} onChange={(e) => set("runway", e.target.value)} placeholder="18 months" />
            </Field>
          </div>
        </>
      )}
      <div className="rounded-lg border border-line p-3 space-y-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span>Send to stages</span>
          <select className="input h-9 w-auto" value={stages[0]} onChange={(e) => setStages([+e.target.value, Math.max(+e.target.value, stages[1])])} aria-label="From stage">
            {STAGES.map((s, i) => <option key={s} value={i + 1}>{s}</option>)}
          </select>
          <span>to</span>
          <select className="input h-9 w-auto" value={stages[1]} onChange={(e) => setStages([Math.min(stages[0], +e.target.value), +e.target.value])} aria-label="To stage">
            {STAGES.map((s, i) => <option key={s} value={i + 1}>{s}</option>)}
          </select>
        </div>
        <div className="text-muted">
          {aud.data ? `${aud.data.count} investor${aud.data.count === 1 ? "" : "s"} with an email${aud.data.without_email ? `, ${aud.data.without_email} skipped (no email on card)` : ""}` : "Counting…"}
        </div>
        {aud.data && aud.data.count > 0 && (
          <details>
            <summary className="cursor-pointer text-brand text-xs">See or exclude people</summary>
            <ul className="mt-2 max-h-48 overflow-y-auto space-y-1">
              {aud.data.items.map((p) => (
                <li key={p.id} className="flex items-center gap-2">
                  <span className="flex-1 truncate">
                    {p.name} <span className="text-muted">· {p.firm}</span>
                  </span>
                  <button type="button" className="text-muted" aria-label={`Exclude ${p.name}`} onClick={() => setExclude([...exclude, p.id])}>
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}
        {exclude.length > 0 && (
          <button type="button" className="text-xs text-brand" onClick={() => setExclude([])}>
            Bring back {exclude.length} excluded
          </button>
        )}
        <label className="flex items-center gap-2">
          <input type="checkbox" className="accent-[var(--brand)]" checked={followUp} onChange={(e) => setFollowUp(e.target.checked)} /> Send one short follow-up after 4 days to those who don&apos;t reply
        </label>
      </div>
      <div className="flex gap-2">
        <button type="button" className="btn-ghost" onClick={onClose}>
          Cancel
        </button>
        <button className="btn-primary flex-1" disabled={create.isPending || !aud.data?.count}>
          {create.isPending ? "Writing…" : "Write the emails"}
        </button>
      </div>
      <p className="text-xs text-muted">Nothing is sent yet. You&apos;ll see every email and can edit or remove anyone before approving.</p>
    </form>
  );
}

export default function Updates() {
  const q = useQuery<List>({ queryKey: ["broadcasts"], queryFn: () => api("/broadcasts") });
  const [open, setOpen] = useState(false);
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data!;
  return (
    <>
      <PageHeader
        title="Updates"
        sub={d.committed ? `${d.committed} committed so far` : "Round news and investor updates"}
        actions={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus size={16} /> New update
          </button>
        }
      />
      <div className="card divide-y divide-line">
        {d.items.length === 0 && <Empty icon={<Megaphone />} title="No updates yet" body="Tell investors who are still deciding when you hit a milestone. Momentum is the best follow-up." />}
        {d.items.map((b) => (
          <Link key={b.id} href={`/app/updates/${b.id}`} className="p-3 flex items-center gap-3 hover:bg-surface">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{b.title}</div>
              <div className="text-xs text-muted">
                {b.kind === "round_update" ? "Round update" : "Investor update"} · {b.recipients} recipients · {fmtDate(b.created_at)}
              </div>
            </div>
            <div className="text-right text-xs">
              <span className="chip capitalize">{b.status}</span>
              {b.sent > 0 && (
                <div className="text-muted mt-1">
                  {b.opened} opened · {b.replied} replied
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>
      <Sheet open={open} onClose={() => setOpen(false)} title="New update">
        <Composer data={d} onClose={() => setOpen(false)} />
      </Sheet>
    </>
  );
}

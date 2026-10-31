"use client";

import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { errText, useToast } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import type { Card, FunnelMeta } from "@/lib/types";
import { REJECTION_REASONS, useCardChange, type Suggestion } from "./StatusNote";
import clsx from "clsx";
import { useQueryClient } from "@tanstack/react-query";

const STATUS_LABEL: Record<string, string> = { Rejection: "Rejected" };
const PRIORITY_LABEL: Record<string, string> = { P1: "P1 · Top", P2: "P2 · High", P3: "P3 · Normal", P4: "P4 · Low" };

/** Stage, status, priority and next contact as dropdowns, a note, then one Save. Nothing changes until Save. */
export function UpdatePanel({ card, meta, onSaved }: { card: Card; meta?: FunnelMeta; onSaved?: (closing: boolean) => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [stage, setStage] = useState(card.stage);
  const [status, setStatus] = useState(card.status);
  const [priority, setPriority] = useState(card.priority);
  const [next, setNext] = useState(card.next_contact_date ?? "");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  useEffect(() => {
    setStage(card.stage);
    setStatus(card.status);
    setPriority(card.priority);
    setNext(card.next_contact_date ?? "");
  }, [card.id, card.stage, card.status, card.priority, card.next_contact_date]);

  const change = {
    ...(stage !== card.stage ? { stage } : {}),
    ...(status !== card.status ? { status } : {}),
    ...(priority !== card.priority ? { priority } : {}),
    ...(next !== (card.next_contact_date ?? "") ? { next_contact_date: next || null } : {}),
  };
  const rejecting = status === "Rejection";
  const dirty = Object.keys(change).length > 0 || note.trim() !== "" || (rejecting && reason !== "");
  const save = useCardChange(card.id, (r) => {
    const closing = r.status === "Inactive" || r.status === "Rejection";
    toast(closing ? `${card.name} marked ${r.status === "Inactive" ? "inactive" : "rejected"} and hidden from your tracker` : r.reminder_date ? `Saved. Reminder set for ${fmtDate(r.reminder_date)}` : "Saved");
    setNote("");
    setReason("");
    setSuggestions(r.suggestions);
    onSaved?.(closing);
  });
  const field = "text-xs font-medium text-muted mb-1 block";

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <label>
          <span className={field}>Stage</span>
          <select className={clsx("input", stage !== card.stage && "border-brand ring-2 ring-brand/15")} value={stage} onChange={(e) => setStage(Number(e.target.value))}>
            {meta?.stages.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={field}>Status</span>
          <select className={clsx("input", status !== card.status && "border-brand ring-2 ring-brand/15")} value={status} onChange={(e) => setStatus(e.target.value)}>
            {(meta?.statuses ?? ["Active", "Inactive", "Rejection", "Ghosting"]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s] ?? s}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={field}>Priority</span>
          <select className={clsx("input", priority !== card.priority && "border-brand ring-2 ring-brand/15")} value={priority} onChange={(e) => setPriority(e.target.value)}>
            {["P1", "P2", "P3", "P4"].map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABEL[p]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={field}>Next contact</span>
          <input className={clsx("input", next !== (card.next_contact_date ?? "") && "border-brand ring-2 ring-brand/15")} type="date" value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
      </div>

      {rejecting && card.status !== "Rejection" && (
        <div className="rounded-xl border border-red-300/70 bg-red-50/60 p-3">
          <div className="text-sm font-medium">Why did they pass?</div>
          <p className="text-xs text-muted">Logging the reason helps you spot rejection patterns across your raise.</p>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {REJECTION_REASONS.map((r) => (
              <button key={r} type="button" onClick={() => setReason(reason === r ? "" : r)} className={clsx("chip text-xs", reason === r ? "bg-red-600 text-white border-red-600" : "bg-card hover:border-red-400")}>
                {r}
              </button>
            ))}
          </div>
        </div>
      )}

      <label className="block">
        <span className={field}>Note</span>
        <textarea
          className="textarea min-h-20"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={rejecting && card.status !== "Rejection" ? "Anything they said, in their words (optional)" : 'e.g. "Asked for the deck, follow up Thursday. Intro via Sam"'}
        />
        <span className="text-xs text-muted">Dates in a note become reminders automatically.</span>
      </label>

      <div className="flex items-center gap-2">
        <button className="btn-primary" disabled={!dirty || save.isPending} onClick={() => save.mutate({ change, note, reason: rejecting ? reason : "" }, { onError: (e) => toast(errText(e), "err") })}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        {dirty && (
          <button
            className="btn-ghost"
            onClick={() => {
              setStage(card.stage);
              setStatus(card.status);
              setPriority(card.priority);
              setNext(card.next_contact_date ?? "");
              setNote("");
              setReason("");
            }}
          >
            Cancel
          </button>
        )}
      </div>

      {suggestions.map((s) => (
        <div key={s.field + s.value} className="flex items-center gap-2 rounded-lg border border-brand/30 bg-brand/5 p-2.5 text-sm">
          <Sparkles size={14} className="text-brand shrink-0" />
          <span className="flex-1">
            {s.reason}: set {s.field.replace(/_/g, " ")} to <b>{s.field === "stage" ? meta?.stages[Number(s.value) - 1]?.label : String(s.value)}</b>?
          </span>
          <button
            className="btn-primary btn-sm"
            onClick={async () => {
              try {
                await api(`/funnel/${card.id}`, { method: "PATCH", json: { [s.field]: s.value } });
                setSuggestions((x) => x.filter((y) => y !== s));
                qc.invalidateQueries({ queryKey: ["card", card.id] });
                qc.invalidateQueries({ queryKey: ["funnel"] });
              } catch (e) {
                toast(errText(e), "err");
              }
            }}
          >
            Apply
          </button>
        </div>
      ))}
    </div>
  );
}

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Eye, Megaphone, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { useSuggest } from "@/components/EmailPlaybook";
import { Sheet, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";

type Recipient = { name: string; firm: string; to: string; timezone: string; scheduled_for: string; moved: boolean; clash?: boolean };
type Preview = { count: number; moved: number; clash?: number; recipients: Recipient[]; sample: { to: string; subject: string; body: string } };

const DRAFT_KEY = "ef-progress-update-draft";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const todayStr = () => iso(new Date());
/** Tomorrow, or Monday when tomorrow is a weekend day. */
function tomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  return iso(d);
}

function at(iso: string, tz?: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", ...(tz ? { timeZone: tz } : {}) });
  } catch {
    return new Date(iso).toLocaleString();
  }
}

/** Write a round & progress update once, polish it with AI, preview it, and schedule it to every investor you've
 *  already emailed: 08:35 their time, as a reply in your thread with them, never within a day of another email. */
function Composer({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const sg = useSuggest();
  const [text, setText] = useState(() => {
    try {
      return localStorage.getItem(DRAFT_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [pv, setPv] = useState<Preview | null>(null);
  const [when, setWhen] = useState<"morning" | "now">("morning");
  const [confirm, setConfirm] = useState(false);
  const [day, setDay] = useState(tomorrow());  // in each investor's own time zone
  const [time, setTime] = useState("08:35");
  const keep = (t: string) => {
    setText(t);
    setPv(null);
    try {
      localStorage.setItem(DRAFT_KEY, t);
    } catch {}
  };
  const polish = useMutation({
    mutationFn: () => api<{ text: string; engine: string }>("/outreach/progress-update/polish", { method: "POST", json: { text } }),
    onSuccess: (r) => {
      keep(r.text);
      toast(r.engine === "ai" ? "Polished. Check it still says what you mean." : "Tidied up (AI isn't available right now).");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const preview = useMutation({
    mutationFn: () => api<Preview>("/outreach/progress-update/preview", { method: "POST", json: { text, day: day || null, at: time } }),
    onSuccess: setPv,
    onError: (e) => toast(errText(e), "err"),
  });
  const schedule = useMutation({
    mutationFn: () => api<{ scheduled: number }>("/outreach/progress-update/schedule", { method: "POST", json: { text, when, day: day || null, at: time } }),
    onSuccess: (r) => {
      setConfirm(false);
      for (const k of ["upcoming", "outreach-stats"]) qc.invalidateQueries({ queryKey: [k] });
      try {
        localStorage.removeItem(DRAFT_KEY);
      } catch {}
      const who = `${r.scheduled} investor${r.scheduled === 1 ? "" : "s"}`;
      toast(when === "now" ? `Sending to ${who} now, spaced a minute or two apart. See them under Scheduled emails.` : `Update scheduled for ${who}. See them under Scheduled emails.`);
      onDone();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const ok = text.trim().length >= 3;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        News about the round, momentum or progress. It goes to every investor you&apos;ve already emailed, as a reply in your thread with them.
      </p>
      <textarea
        className="textarea min-h-40 leading-relaxed"
        maxLength={1500}
        value={text}
        onChange={(e) => keep(e.target.value)}
        placeholder={sg.data?.update_example ? `e.g. ${sg.data.update_example}` : "e.g. Half the round is committed and we close at the end of the month. We also signed our second hospital."}
        aria-label="Round and progress update"
      />
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost btn-sm" disabled={!ok || polish.isPending} onClick={() => polish.mutate()}>
          <Sparkles size={13} /> {polish.isPending ? "Polishing…" : "Polish with AI"}
        </button>
        <button className="btn-ghost btn-sm" disabled={!ok || preview.isPending} onClick={() => preview.mutate()}>
          <Eye size={13} /> {preview.isPending ? "Loading…" : "Preview"}
        </button>
      </div>

      {pv && (
        <div className="rounded-xl border border-line bg-surface/50 p-3 space-y-3">
          <div>
            <div className="text-xs text-muted">{pv.sample.to ? `What ${pv.sample.to} gets` : "What they get"}</div>
            <div className="text-sm font-medium mt-1">{pv.sample.subject}</div>
            <div className="text-sm whitespace-pre-wrap mt-2 leading-relaxed">{pv.sample.body}</div>
          </div>
          {pv.count > 0 && (
            <div>
              <div className="text-xs text-muted mb-1">
                {pv.count} investor{pv.count === 1 ? "" : "s"}
                {pv.clash ? `, ${pv.clash} also get another email from you that day` : ""}
              </div>
              <ul className="max-h-48 overflow-auto divide-y divide-line text-xs">
                {pv.recipients.map((r) => (
                  <li key={r.to} className="flex gap-2 py-1.5">
                    <span className="flex-1 min-w-0 truncate">
                      {r.name}
                      {r.firm ? <span className="text-muted">, {r.firm}</span> : null}
                    </span>
                    <span className={r.clash ? "text-warn" : "text-muted"} title={r.clash ? "Another email reaches them that day" : undefined}>
                      {at(r.scheduled_for, r.timezone)} their time
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="rounded-xl border border-line p-3 space-y-2">
        <div className="grid sm:grid-cols-2 gap-2" role="radiogroup" aria-label="When to send">
          {([
            ["morning", "Schedule", "A day and time in each investor's own time zone"],
            ["now", "Send now", "Starts straight away, spaced out within your daily limit"],
          ] as const).map(([k, t, sub]) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={when === k}
              onClick={() => {
                setWhen(k);
                setConfirm(false);
              }}
              className={`text-left rounded-lg border p-2.5 ${when === k ? "border-brand bg-brand/5" : "border-line hover:border-brand/50"}`}
            >
              <div className="text-sm font-medium flex items-center gap-1.5">
                {k === "morning" ? <CalendarClock size={14} className="text-brand" /> : <Send size={14} className="text-brand" />} {t}
              </div>
              <div className="text-[11px] text-muted mt-0.5">{sub}</div>
            </button>
          ))}
        </div>
        {when === "morning" && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <input type="date" className="input h-9 w-auto" value={day} min={todayStr()} onChange={(e) => { setDay(e.target.value); setPv(null); setConfirm(false); }} aria-label="Day" />
            <input type="time" className="input h-9 w-auto" value={time} onChange={(e) => { setTime(e.target.value || "08:35"); setPv(null); setConfirm(false); }} aria-label="Time" />
            <span className="text-xs text-muted">their time{day === tomorrow() && time === "08:35" ? " (suggested: tomorrow morning)" : ""}</span>
          </div>
        )}
        <p className="text-xs text-muted">
          {when === "morning"
            ? "Each investor gets it at this time where they are, as a reply in your thread with them. Preview shows anyone who also gets another email from you that day."
            : "It replies in your thread with each investor. Anyone who just got an email from you will get this one too, so use it for news that can't wait."}
        </p>
        {confirm ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="flex-1">
              {when === "now" ? "Send this update now" : `Schedule this update for ${day} at ${time} their time`} to {pv ? `all ${pv.count}` : "all"} previously emailed investors?
            </span>
            <button className="btn-primary btn-sm" disabled={schedule.isPending} onClick={() => schedule.mutate()}>
              {schedule.isPending ? "Working…" : "Yes"}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setConfirm(false)}>No</button>
          </div>
        ) : (
          <button className="btn-primary w-full" disabled={!ok} onClick={() => setConfirm(true)}>
            <Send size={15} /> {when === "now" ? "Send now to all previously emailed investors" : "Schedule to all previously emailed investors"}
          </button>
        )}
      </div>
    </div>
  );
}

export function ProgressUpdateCard() {
  const [open, setOpen] = useState(false);
  return (
    <div className="card p-3 md:p-4">
      <div className="flex items-center gap-2">
        <Megaphone size={16} className="text-brand shrink-0" />
        <span className="font-semibold text-sm">Round & progress update</span>
      </div>
      <p className="mt-1 text-xs text-muted">Share news with every investor you&apos;ve already emailed, in the same thread.</p>
      <button className="btn-primary btn-sm w-full mt-3" onClick={() => setOpen(true)}>
        <Megaphone size={13} /> Send round &amp; progress update
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Send round & progress update" wide>
        <Composer onDone={() => setOpen(false)} />
      </Sheet>
    </div>
  );
}

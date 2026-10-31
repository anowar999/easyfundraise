"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, MailPlus, Search, Send, Zap } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ConfirmSend, type SendPreview } from "@/components/ConfirmSend";
import { Empty, ListSkeleton, Sheet, errText, useToast } from "@/components/ui";
import { api, ApiError, fmtDate } from "@/lib/api";

type Item = { id: string; status: string; blocker: string | null; sent: number; next_at: string | null; created_at: string; investor: { id: string; name: string; firm: string } };
type List = { auto_send: boolean; items: Item[] };
type Bulk = { needs_confirm: true; from: string; ready: { id: string; name: string; to: string }[]; skipped: { id: string; name: string; reason: string }[] };

function statusText(x: Item) {
  if (x.status === "draft") return x.blocker ? "Needs attention" : "Ready to send";
  if (x.status === "stopped") return "Stopped";
  if (x.next_at) return `${x.sent} of 3 sent · next ${fmtDate(x.next_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
  return x.sent ? `${x.sent} of 3 sent` : "Scheduled";
}

/** One-by-one send: the same confirm screen as the sequence page. */
function SendOne({ x }: { x: Item }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [preview, setPreview] = useState<SendPreview | null>(null);
  const m = useMutation({
    mutationFn: (confirm: boolean) => api(`/sequences/${x.id}/approve`, { method: "POST", json: { confirm } }),
    onSuccess: () => {
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      qc.invalidateQueries({ queryKey: ["outreach-stats"] });
      toast(`Scheduled for ${x.investor.name}. Sends in their local send window and stops on any reply.`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.problem.needs_confirm) setPreview(e.problem.preview as SendPreview);
      else toast(errText(e), "err");
    },
  });
  return (
    <>
      <button className="btn-primary btn-sm" disabled={m.isPending} onClick={() => m.mutate(false)}>
        <Send size={14} /> Send
      </button>
      <ConfirmSend preview={preview} busy={m.isPending} onCancel={() => setPreview(null)} onConfirm={() => m.mutate(true)} />
    </>
  );
}

function AutoSend({ on }: { on: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const save = useMutation({
    mutationFn: (v: boolean) => api("/workspace", { method: "PATCH", json: { auto_send: v } }),
    onSuccess: (_, v) => {
      setAsking(false);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      toast(v ? "Auto-send is on" : "Back to sending one by one");
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const opt = (active: boolean, title: string, body: string, onClick: () => void, icon: React.ReactNode) => (
    <button type="button" onClick={onClick} className={clsx("flex-1 text-left rounded-xl border p-3 transition-colors", active ? "border-brand bg-brand/5" : "border-line hover:border-brand/50")}>
      <div className="flex items-center gap-2 font-semibold text-sm">
        {icon} {title}
        {active && <CheckCircle2 size={15} className="text-brand ml-auto" />}
      </div>
      <p className="text-xs text-muted mt-1">{body}</p>
    </button>
  );
  return (
    <div className="card p-4 mb-4">
      <div className="font-semibold mb-2">How should emails go out?</div>
      <div className="flex flex-col sm:flex-row gap-2">
        {opt(!on, "One by one", "You review each investor's emails and press Send, or send all ready ones at once.", () => on && save.mutate(false), <Send size={15} />)}
        {opt(on, "Auto-send", "Every investor you add to outreach is emailed automatically from your Gmail, in their send window.", () => !on && setAsking(true), <Zap size={15} />)}
      </div>
      <Sheet open={asking} onClose={() => setAsking(false)} title="Turn on auto-send?">
        <ul className="text-sm space-y-2 list-disc pl-5">
          <li>From now on, when you add an investor to outreach, their 3 emails are drafted and scheduled straight away. You won&apos;t review them first.</li>
          <li>Emails go from your connected Gmail, in the investor&apos;s local send window, within your daily limit.</li>
          <li>Each sequence stops as soon as the investor replies. Drafts already on your list are not sent; use Send all for those.</li>
        </ul>
        <div className="flex gap-2 mt-4">
          <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate(true)}>
            <Zap size={16} /> Turn on auto-send
          </button>
          <button className="btn-ghost" onClick={() => setAsking(false)}>
            Cancel
          </button>
        </div>
      </Sheet>
    </div>
  );
}

export function OutreachList() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<List>({ queryKey: ["sequences"], queryFn: () => api("/sequences") });
  const [bulk, setBulk] = useState<Bulk | null>(null);
  const preview = useMutation({
    mutationFn: () => api<Bulk>("/sequences/send-all", { method: "POST", json: { confirm: false } }),
    onSuccess: setBulk,
    onError: (e) => toast(errText(e), "err"),
  });
  const sendAll = useMutation({
    mutationFn: () => api<{ scheduled: number; skipped: unknown[] }>("/sequences/send-all", { method: "POST", json: { confirm: true } }),
    onSuccess: (r) => {
      setBulk(null);
      qc.invalidateQueries({ queryKey: ["sequences"] });
      qc.invalidateQueries({ queryKey: ["outreach-stats"] });
      toast(`Scheduled ${r.scheduled} investor${r.scheduled === 1 ? "" : "s"}${r.skipped.length ? `. ${r.skipped.length} still need attention` : ""}.`);
    },
    onError: (e) => toast(errText(e), "err"),
  });
  if (q.isLoading) return <ListSkeleton rows={4} />;
  const items = (q.data?.items ?? []).filter((x) => x.status !== "stopped");
  const drafts = items.filter((x) => x.status === "draft");
  const ready = drafts.filter((x) => !x.blocker).length;
  return (
    <>
      <AutoSend on={Boolean(q.data?.auto_send)} />
      {items.length === 0 ? (
        <Empty
          icon={<MailPlus size={28} />}
          title="Your outreach list is empty"
          body="Tap the envelope icon on any investor to add them. Their emails are drafted for you."
          action={
            <Link href="/app/investors" className="btn-primary">
              <Search size={16} /> Find investors
            </Link>
          }
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 px-4 py-3 bg-surface/60 border-b border-line">
            <div className="text-sm flex-1">
              <b>{items.length}</b> in outreach · {drafts.length} not sent yet{drafts.length > ready ? ` · ${drafts.length - ready} need attention` : ""}
            </div>
            {drafts.length > 0 && (
              <button className="btn-primary btn-sm" disabled={!ready || preview.isPending} onClick={() => preview.mutate()}>
                <Send size={14} /> Send all ready ({ready})
              </button>
            )}
          </div>
          <div className="divide-y divide-line">
            {items.map((x) => (
              <div key={x.id} className="flex items-center gap-3 px-4 py-3">
                <Link href={`/app/sequences/${x.id}`} className="flex-1 min-w-0">
                  <div className="font-medium truncate">{x.investor.name}</div>
                  <div className="text-xs text-muted truncate">{x.investor.firm}</div>
                  {x.blocker && (
                    <div className="text-xs text-warn flex items-center gap-1 mt-0.5">
                      <AlertTriangle size={12} /> {x.blocker}
                    </div>
                  )}
                </Link>
                <span className={clsx("chip text-xs hidden sm:inline-flex", x.status === "draft" && !x.blocker && "text-brand border-brand/40", x.status !== "draft" && "text-emerald-700 border-emerald-600/30")}>{statusText(x)}</span>
                <Link href={`/app/sequences/${x.id}`} className="btn-ghost btn-sm">
                  Review
                </Link>
                {x.status === "draft" && !x.blocker && <SendOne x={x} />}
              </div>
            ))}
          </div>
        </div>
      )}
      <Sheet open={Boolean(bulk)} onClose={() => setBulk(null)} title="Send to everyone ready?">
        {bulk && (
          <div className="text-sm space-y-3">
            <p>
              From <b>{bulk.from}</b> (your Gmail). Each investor gets 3 emails in their local send window. Each sequence stops on any reply.
            </p>
            <div>
              <div className="font-semibold mb-1">Will be scheduled ({bulk.ready.length})</div>
              <ul className="space-y-0.5">
                {bulk.ready.map((r) => (
                  <li key={r.id}>
                    {r.name} <span className="text-muted">· {r.to}</span>
                  </li>
                ))}
              </ul>
            </div>
            {bulk.skipped.length > 0 && (
              <div>
                <div className="font-semibold mb-1">Skipped ({bulk.skipped.length})</div>
                <ul className="space-y-0.5 text-muted">
                  {bulk.skipped.map((r) => (
                    <li key={r.id}>
                      {r.name}: {r.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex gap-2 pt-1">
              <button className="btn-primary" disabled={!bulk.ready.length || sendAll.isPending} onClick={() => sendAll.mutate()}>
                <Send size={16} /> Confirm and schedule {bulk.ready.length}
              </button>
              <button className="btn-ghost" onClick={() => setBulk(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </Sheet>
    </>
  );
}

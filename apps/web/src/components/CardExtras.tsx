"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Globe, NotebookPen, RefreshCw } from "lucide-react";
import { api, timeAgo } from "@/lib/api";
import { errText, useToast } from "./ui";

type Brief = { id: string; engine: string; created_at: string; content: Record<string, string | string[]> };
const BRIEF_LABELS: [string, string][] = [
  ["recent", "Recent deals & news"],
  ["overlaps", "Why they fit"],
  ["talking_points", "Talking points"],
  ["likely_questions", "Likely questions"],
  ["suggested_asks", "Your asks"],
  ["red_flags", "Watch out for"],
];

/** AGT-04 meeting brief on the funnel card. */
export function MeetingBrief({ cardId }: { cardId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ brief: Brief | null }>({ queryKey: ["brief", cardId], queryFn: () => api(`/agent/briefs/${cardId}`) });
  const make = useMutation({
    mutationFn: () => api<{ brief: Brief }>(`/agent/briefs/${cardId}`, { method: "POST" }),
    onSuccess: (r) => qc.setQueryData(["brief", cardId], r),
    onError: (e) => toast(errText(e), "err"),
  });
  const b = q.data?.brief;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-semibold flex items-center gap-2">
          <NotebookPen size={16} /> Meeting brief
        </h2>
        <button className="btn-ghost btn-sm" onClick={() => make.mutate()} disabled={make.isPending}>
          <RefreshCw size={14} /> {b ? "Refresh" : make.isPending ? "Preparing…" : "Prepare"}
        </button>
      </div>
      {!b && <p className="text-sm text-muted">Who they are, recent deals, likely questions and what to ask. Ready 24 hours before any call you set.</p>}
      {b && (
        <div className="space-y-3 text-sm">
          <div>
            <div className="font-medium">{String(b.content.who)}</div>
            <p className="text-muted mt-0.5">{String(b.content.thesis)}</p>
          </div>
          {BRIEF_LABELS.map(([k, label]) => {
            const items = (b.content[k] as string[]) ?? [];
            if (!items.length) return null;
            return (
              <div key={k}>
                <div className="label">{label}</div>
                <ul className="list-disc pl-5 space-y-0.5">
                  {items.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            );
          })}
          <p className="text-xs text-muted">
            Prepared {timeAgo(b.created_at)} · {b.engine === "template" ? "from stored research" : "by Claude from stored research"}
          </p>
        </div>
      )}
    </div>
  );
}

type View = { id: string; seconds: number; sections: Record<string, number>; downloads: { doc: string }[]; started_at: string };

/** DR-02/03: personal data-room link and what this investor looked at. */
export function RoomActivity({ cardId }: { cardId: string }) {
  const toast = useToast();
  const views = useQuery<{ items: View[] }>({ queryKey: ["room-views", cardId], queryFn: () => api(`/data-room/views?card_id=${cardId}`) });
  const link = useMutation({
    mutationFn: () => api<{ url: string }>("/data-room/links", { method: "POST", json: { card_id: cardId } }),
    onSuccess: async (r) => {
      try {
        await navigator.clipboard.writeText(r.url);
        toast("Personal data-room link copied");
      } catch {
        prompt("Copy this link", r.url);
      }
    },
    onError: (e) => toast(errText(e), "err"),
  });
  const items = views.data?.items ?? [];
  const total = items.reduce((a, v) => a + v.seconds, 0);
  const top = Object.entries(items.reduce<Record<string, number>>((acc, v) => {
    for (const [k, n] of Object.entries(v.sections)) acc[k] = (acc[k] ?? 0) + n;
    return acc;
  }, {})).sort((a, b) => b[1] - a[1]).slice(0, 3);
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-semibold flex items-center gap-2">
          <Globe size={16} /> Data room
        </h2>
        <button className="btn-ghost btn-sm" onClick={() => link.mutate()}>
          <Copy size={14} /> Copy personal link
        </button>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Not viewed yet. Share their personal link and you&apos;ll see what they read.</p>
      ) : (
        <div className="text-sm space-y-1">
          <div>
            {items.length} visit{items.length > 1 ? "s" : ""} · {Math.round(total / 60)} min total · last {timeAgo(items[0].started_at)}
          </div>
          {top.length > 0 && <div className="text-muted">Most time on: {top.map(([k, n]) => `${k.replace(/_/g, " ")} (${Math.round(n / 60) || "<1"} min)`).join(", ")}</div>}
          {items.some((v) => v.downloads.length) && <div className="text-muted">Downloaded: {[...new Set(items.flatMap((v) => v.downloads.map((d) => d.doc)))].join(", ")}</div>}
        </div>
      )}
    </div>
  );
}

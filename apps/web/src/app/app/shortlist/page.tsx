"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Heart, MailPlus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { TicketChip, TypeChip } from "@/components/InvestorChips";
import { CountryTag, OutreachButton } from "@/components/InvestorRow";
import { Avatar, Empty, ErrorState, FitScore, ListSkeleton, errText, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import type { InvestorCard } from "@/lib/types";

type Item = InvestorCard & { added_at: string };

/** Investors saved while browsing. Pick some (or all) and add them to email outreach or move them into the
 *  investor tracker in one go. */
export default function ShortlistPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery<{ items: Item[] }>({ queryKey: ["shortlist"], queryFn: () => api("/shortlist") });
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["shortlist"] });
    qc.invalidateQueries({ queryKey: ["investors"] });
    qc.invalidateQueries({ queryKey: ["funnel"] });
  };
  const move = useMutation({
    mutationFn: (ids: string[]) => api<{ added: number }>("/shortlist/to-tracker", { method: "POST", json: { investor_ids: ids } }),
    onSuccess: (r, ids) => {
      setPicked(new Set());
      toast(`Moved ${ids.length} to your investor tracker${r.added < ids.length ? ` (${ids.length - r.added} were already there)` : ""}`);
      refresh();
    },
    onError: (e) => toast(errText(e), "err"),
  });
  // Adds each one to outreach in turn (each gets its own drafted emails), so the founder sees progress.
  const [adding, setAdding] = useState<{ done: number; total: number } | null>(null);
  const toOutreach = async (ids: string[]) => {
    const todo = items.filter((i) => ids.includes(i.id) && !i.in_outreach);
    if (!todo.length) return toast("Those investors are already in your outreach list");
    let ok = 0;
    const failed: string[] = [];
    setAdding({ done: 0, total: todo.length });
    for (const [k, inv] of todo.entries()) {
      try {
        await api("/sequences", { method: "POST", json: { investor_id: inv.id } });
        ok++;
      } catch (e) {
        failed.push(`${inv.name}: ${errText(e)}`);
      }
      setAdding({ done: k + 1, total: todo.length });
    }
    setAdding(null);
    setPicked(new Set());
    refresh();
    qc.invalidateQueries({ queryKey: ["sequences"] });
    toast(ok ? `Added ${ok} to your outreach list. Their emails are drafted for you to review.` : failed[0], ok ? "ok" : "err");
    if (ok && failed.length) toast(`${failed.length} not added. ${failed[0]}`, "err");
  };
  const remove = useMutation({
    mutationFn: (id: string) => api(`/shortlist/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  if (q.isLoading) return <ListSkeleton rows={6} />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const items = q.data!.items;
  const all = items.length > 0 && picked.size === items.length;
  const toggle = (id: string) => setPicked((p) => {
    const n = new Set(p);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    return n;
  });
  const chosen = picked.size ? [...picked] : items.map((i) => i.id);
  return (
    <>
      <PageHeader
        title="Shortlist"
        sub={items.length ? `${items.length} investor${items.length > 1 ? "s" : ""} saved. Add the ones you want to email to outreach, or move them into your tracker.` : "Save investors with the heart button while you browse."}
        actions={
          items.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <button className="btn-primary" disabled={Boolean(adding)} onClick={() => toOutreach(chosen)}>
                <MailPlus size={16} /> {adding ? `Adding ${adding.done + 1} of ${adding.total}…` : picked.size ? `Add ${picked.size} to outreach` : "Add all to outreach"}
              </button>
              <button className="btn-ghost" disabled={move.isPending} onClick={() => move.mutate(chosen)}>
                {picked.size ? `Move ${picked.size} to tracker` : "Move all to tracker"} <ArrowRight size={16} />
              </button>
            </div>
          )
        }
      />
      {items.length === 0 ? (
        <Empty
          icon={<Heart size={28} />}
          title="Your shortlist is empty"
          body="Browse investors and tap the heart on anyone worth a look. They'll wait here until you're ready to reach out."
          action={
            <Link href="/app/investors" className="btn-primary">
              <Search size={16} /> Find investors
            </Link>
          }
        />
      ) : (
        <div className="card divide-y divide-line overflow-hidden">
          <label className="flex items-center gap-3 px-4 py-2.5 text-sm text-muted bg-surface/60">
            <input type="checkbox" className="h-4 w-4 accent-[var(--brand)]" checked={all} onChange={() => setPicked(all ? new Set() : new Set(items.map((i) => i.id)))} />
            {picked.size ? `${picked.size} selected` : "Select all"}
          </label>
          {items.map((inv) => (
            <div key={inv.id} className="flex items-center gap-3 px-4 py-3 hover:bg-surface/60">
              <input type="checkbox" className="h-4 w-4 accent-[var(--brand)]" checked={picked.has(inv.id)} onChange={() => toggle(inv.id)} aria-label={`Select ${inv.name}`} />
              <Link href={`/app/investors/${inv.id}`} className="flex flex-1 min-w-0 items-center gap-3">
                <Avatar name={inv.name} src={inv.photo_url} logoDomain={inv.firm_domain} size={44} />
                <div className="min-w-0 flex-1">
                  <div className="font-semibold truncate">{inv.name}</div>
                  <div className="text-sm text-muted truncate">
                    {[inv.title, inv.firm].filter(Boolean).join(" · ")}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <TypeChip type={inv.investor_type_label || inv.investor_type} />
                    <TicketChip t={inv} />
                    <CountryTag country={inv.country} location={inv.location} />
                  </div>
                </div>
                {inv.fit && <FitScore score={inv.fit.score} />}
              </Link>
              <OutreachButton inv={inv} />
              {inv.in_funnel ? (
                <span className="chip text-xs">in tracker</span>
              ) : (
                <button className="btn-ghost btn-sm hidden sm:inline-flex" onClick={() => move.mutate([inv.id])}>
                  To tracker
                </button>
              )}
              <button className="p-2 text-muted hover:text-danger" aria-label={`Remove ${inv.name}`} onClick={() => remove.mutate(inv.id)}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

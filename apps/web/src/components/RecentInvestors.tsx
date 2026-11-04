"use client";

import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import Link from "next/link";
import { api, fmtDate } from "@/lib/api";
import { flag } from "@/lib/countries";

type Recent = { id: string; name: string; firm: string; title: string; country: string; viewed_at: string };

/** The last few investor profiles this user opened, for jumping back in. Hidden until there is one. */
export function RecentInvestors({ limit = 3 }: { limit?: number }) {
  const q = useQuery<{ items: Recent[] }>({
    queryKey: ["investors-recent", limit],
    queryFn: () => api(`/investors/recent?limit=${limit}`),
    refetchOnWindowFocus: true,
  });
  const items = q.data?.items ?? [];
  if (!items.length) return null;
  return (
    <div className="card px-4 py-3">
      <h2 className="flex items-center gap-2 font-semibold text-sm mb-2">
        <History size={15} className="text-brand" /> Recently viewed
      </h2>
      <ul className="divide-y divide-line">
        {items.map((x) => (
          <li key={x.id}>
            <Link href={`/app/investors/${x.id}?from=investors`} className="flex items-center gap-2.5 py-2 group">
              <span className="h-8 w-8 shrink-0 rounded-full bg-brand/10 text-brand text-xs font-semibold flex items-center justify-center">
                {x.name
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((w) => w[0])
                  .join("")
                  .toUpperCase()}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium truncate group-hover:text-brand">{x.name}</span>
                <span className="block text-xs text-muted truncate">
                  {[x.firm || x.title, x.country && [flag(x.country), x.country].filter(Boolean).join(" ")].filter(Boolean).join(" · ")}
                </span>
              </span>
              <span className="text-[11px] text-muted shrink-0" title={new Date(x.viewed_at).toLocaleString()}>
                {fmtDate(x.viewed_at, { day: "numeric", month: "short" })}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

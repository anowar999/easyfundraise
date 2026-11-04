"use client";

import { Search, X } from "lucide-react";

/** True when every word of the search is in the investor's name, email or firm (case-insensitive). */
export function matches(q: string, ...fields: (string | null | undefined)[]) {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = fields.filter(Boolean).join(" ").toLowerCase();
  return words.every((w) => hay.includes(w));
}

export function ListSearch({ value, onChange, className = "" }: { value: string; onChange: (v: string) => void; className?: string }) {
  return (
    <label className={`relative flex items-center ${className}`}>
      <Search size={14} className="absolute left-2.5 text-muted pointer-events-none" />
      <input
        className="input h-8 pl-8 pr-7 text-sm w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search name, email or firm"
        aria-label="Search by investor name, email or firm"
      />
      {value && (
        <button type="button" className="absolute right-2 text-muted hover:text-brand" onClick={() => onChange("")} aria-label="Clear search">
          <X size={14} />
        </button>
      )}
    </label>
  );
}

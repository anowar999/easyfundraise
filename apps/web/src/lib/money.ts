/** Compact money for ticket (cheque) sizes: 50000 -> "50k", 2000000 -> "2m", 1500000000 -> "1.5bn". */
export function fmtMoney(n: number, currency = "USD"): string {
  const sym = currency === "EUR" ? "€" : currency === "GBP" ? "£" : currency === "USD" ? "$" : "";
  const [div, unit] = n >= 1e9 ? [1e9, "bn"] : n >= 1e6 ? [1e6, "m"] : n >= 1e3 ? [1e3, "k"] : [1, ""];
  const v = n / div;
  const s = (v >= 100 || Number.isInteger(v) ? Math.round(v) : Math.round(v * 10) / 10).toString();
  return `${sym}${s}${unit}${sym ? "" : ` ${currency}`}`;
}

/** Ticket range: "$50k–$2m", "$250k+", "up to $1m", "$150k"; "" when unknown. */
export function fmtTicket(min?: number | null, max?: number | null, currency?: string | null): string {
  const c = currency || "USD";
  if (min && max) return min === max ? fmtMoney(min, c) : `${fmtMoney(min, c)}–${fmtMoney(max, c)}`;
  if (min) return `${fmtMoney(min, c)}+`;
  if (max) return `up to ${fmtMoney(max, c)}`;
  return "";
}

const TYPE_LABELS: Record<string, string> = {
  vc: "VC",
  angel: "Angel",
  family_office: "Family office",
  cvc: "Corporate VC",
  accelerator: "Accelerator",
  pe: "PE / Buyout",
  growth: "Growth equity",
  wealth_manager: "Wealth manager",
  syndicate: "Angel syndicate",
  other: "Other",
};

/** Readable investor type: "family_office" -> "Family office"; labels already readable ("VC Partner") pass through. */
export function investorTypeLabel(raw?: string | null): string {
  const v = (raw ?? "").trim();
  if (!v) return "";
  const known = TYPE_LABELS[v.toLowerCase()];
  if (known) return known;
  if (/[A-Z]/.test(v)) return v;
  return v.replace(/[_-]+/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
}

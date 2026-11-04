import { Banknote } from "lucide-react";
import { fmtTicket, investorTypeLabel } from "@/lib/money";
import type { Ticket } from "@/lib/types";

const SOURCE_NOTE: Record<string, string> = {
  tracker: "Ticket size you entered",
  research: "Typical ticket per deal, from our research",
  directory: "Ticket per deal from the directory listing, not yet verified",
};

/** "$50k–$2m" chip for how much an investor puts in per deal. Renders nothing when unknown. */
export function TicketChip({ t, className = "" }: { t: Ticket; className?: string }) {
  const s = fmtTicket(t.ticket_min, t.ticket_max, t.ticket_currency);
  if (!s) return null;
  const unverified = t.ticket_source === "directory";
  return (
    <span className={`chip whitespace-nowrap ${unverified ? "text-muted border-dashed" : ""} ${className}`} title={SOURCE_NOTE[t.ticket_source ?? ""] ?? "Ticket per deal"}>
      <Banknote size={12} className="shrink-0" aria-hidden />
      <span className="sr-only">Ticket per deal: </span>
      {unverified ? `~${s}` : s}
    </span>
  );
}

/** Small investor-type chip ("VC", "Angel", "Family office"). */
export function TypeChip({ type, className = "" }: { type?: string | null; className?: string }) {
  const label = investorTypeLabel(type);
  if (!label) return null;
  return <span className={`chip whitespace-nowrap text-muted ${className}`}>{label}</span>;
}

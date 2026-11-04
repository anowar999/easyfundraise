/** The daily allowance: new investors one mailbox may email per day (from the plan, max 20). Only email 1 counts. */
export type Allowance = { cap: number; sent_today: number; left_today: number; days: { day: string; count: number }[]; moved: number };

const dayName = (d: string) => {
  const today = new Date();
  const iso = (x: Date) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  const tomorrow = new Date(today.getTime() + 86400000);
  if (d === iso(today)) return "today";
  if (d === iso(tomorrow)) return "tomorrow";
  return new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
};

/** One plain sentence for confirm screens and toasts. Empty when there's nothing worth saying. */
export function allowanceNote(a?: Allowance | null): string {
  if (!a || !a.cap) return "";
  const later = a.days.filter((d) => dayName(d.day) !== "today");
  if (a.moved > 0) {
    const where = later.map((d) => `${d.count} ${dayName(d.day)}`).join(", ");
    return a.left_today
      ? `Your plan allows ${a.cap} new investors a day and ${a.left_today} are left today, so ${a.moved} will start on a later day in their morning (${where}). Follow-ups don't count.`
      : `You've reached today's ${a.cap} new investors, so ${a.moved === 1 ? "this one starts" : `these ${a.moved} start`} on a later day in their morning (${where}). Follow-ups don't count.`;
  }
  return `${a.left_today} of ${a.cap} new investors left today. Follow-ups don't count.`;
}

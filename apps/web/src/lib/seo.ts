/** Public investor-list pages: slugs, labels and data fetching (aggregates only, never individual investors). */

export const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "https://easyfundraise.com";
const API = process.env.API_URL ?? "http://localhost:8000";
export const MIN_PAGE = 30; // pages with fewer investors than this are not published (thin content)

export const SEGMENTS = {
  angel: { slug: "angel-investors", label: "Angel investors", short: "angel investors" },
  vc: { slug: "venture-capital-firms", label: "Venture capital investors", short: "VC investors" },
  seed: { slug: "seed-investors", label: "Seed investors", short: "seed investors" },
  "pre-seed": { slug: "pre-seed-investors", label: "Pre-seed investors", short: "pre-seed investors" },
} as const;
export type Segment = keyof typeof SEGMENTS | "all";

/** "the United Kingdom", "the Netherlands", plain "Germany". */
export const theCountry = (c: string) => (/^(United |Netherlands|Philippines|Czech Republic|Dominican Republic|Bahamas)/.test(c) ? `the ${c}` : c);

export const slugify = (s: string) => s.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export type Index = { total: number; countries: Record<string, Record<string, number>>; sectors: Record<string, Record<string, number>> };
export type Stats = { segment: string; country: string; sector: string; count: number; countries: { name: string; count: number }[]; sectors: { name: string; count: number }[]; firms: { name: string; count: number }[]; leads: number; active_last_12mo: number };

export async function getIndex(): Promise<Index> {
  const r = await fetch(`${API}/public/investor-stats/index`, { next: { revalidate: 21600 } });
  if (!r.ok) throw new Error(`index ${r.status}`);
  return r.json();
}

export async function getStats(segment: Segment, country = "", sector = ""): Promise<Stats> {
  const q = new URLSearchParams({ segment, country, sector });
  const r = await fetch(`${API}/public/investor-stats?${q}`, { next: { revalidate: 21600 } });
  if (!r.ok) throw new Error(`stats ${r.status}`);
  return r.json();
}

export type Page = { slug: string; title: string; segment: Segment; country?: string; sector?: string; count: number };

/** Every investor-list page worth publishing, derived from live counts. */
export function pagesFrom(idx: Index): Page[] {
  const out: Page[] = [];
  for (const [seg, meta] of Object.entries(SEGMENTS) as [keyof typeof SEGMENTS, (typeof SEGMENTS)[keyof typeof SEGMENTS]][]) {
    for (const [country, n] of Object.entries(idx.countries[seg] ?? {})) {
      if (n >= MIN_PAGE) out.push({ slug: `${meta.slug}-in-${slugify(country)}`, title: `${meta.label} in ${theCountry(country)}`, segment: seg, country, count: n });
    }
  }
  for (const [sector, n] of Object.entries(idx.sectors.all ?? {})) {
    if (n >= MIN_PAGE) out.push({ slug: `${slugify(sector)}-investors`, title: `${sector} investors`, segment: "all", sector, count: n });
  }
  return out;
}

export const fmt = (n: number) => n.toLocaleString("en-US");
/** Rounds down to a friendly "1,200+" style figure. */
export const plus = (n: number) => (n >= 1000 ? `${fmt(Math.floor(n / 100) * 100)}+` : n >= 100 ? `${Math.floor(n / 10) * 10}+` : String(n));

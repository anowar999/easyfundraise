import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/landing/PageShell";
import { getIndex, pagesFrom, plus, SEGMENTS, type Page } from "@/lib/seo";

// Rendered on request (data is cached for 6h by fetch) so builds do not need a running API.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Investor Lists: Angel, Pre-seed, Seed and VC Investors by Country and Sector",
  description: "Browse lists of angel investors, pre-seed and seed investors and venture capital firms by country and sector. 14,900+ investors in the EasyFundraise investor database.",
  alternates: { canonical: "/investors" },
};

function Group({ title, pages }: { title: string; pages: Page[] }) {
  if (!pages.length) return null;
  return (
    <section className="py-10 border-b border-[#eef1f6] last:border-0">
      <h2 className="text-2xl font-bold tracking-tight text-[#0b1220]">{title}</h2>
      <ul className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-2.5">
        {pages.map((p) => (
          <li key={p.slug}>
            <Link href={`/investors/${p.slug}`} className="group flex items-baseline justify-between gap-3 text-[16px] text-[#1c2740] hover:text-[#0f62fe]">
              <span className="group-hover:underline">{p.title}</span>
              <span className="text-sm text-[#7a849a] shrink-0">{plus(p.count)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function InvestorsHub() {
  const idx = await getIndex();
  const pages = pagesFrom(idx);
  return (
    <PageShell
      eyebrow="Investor database"
      title="Find investors by country, stage and sector"
      intro={<>Lists drawn from the {plus(idx.total)} investors in the EasyFundraise investor database. Pick a list to see who invests there, what they back, and how to reach them.</>}
    >
      <div className="mx-auto max-w-6xl px-4 md:px-6 py-6">
        {(Object.keys(SEGMENTS) as (keyof typeof SEGMENTS)[]).map((seg) => (
          <Group key={seg} title={`${SEGMENTS[seg].label} by country`} pages={pages.filter((p) => p.segment === seg)} />
        ))}
        <Group title="Investors by sector" pages={pages.filter((p) => p.sector)} />
      </div>
    </PageShell>
  );
}

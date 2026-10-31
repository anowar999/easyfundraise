import { ArrowRight, Check } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/landing/PageShell";
import { theCountry, getIndex, getStats, MIN_PAGE, pagesFrom, plus, SEGMENTS, slugify, type Page } from "@/lib/seo";

// Rendered on request (data is cached for 6h by fetch) so builds do not need a running API.
export const dynamic = "force-dynamic";

async function resolve(slug: string): Promise<{ page: Page; all: Page[] } | null> {
  const all = pagesFrom(await getIndex());
  const page = all.find((p) => p.slug === slug);
  return page ? { page, all } : null;
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const r = await resolve(slug);
  if (!r) return { title: "Investors", robots: { index: false } };
  const { page } = r;
  const where = page.country ? ` in ${theCountry(page.country)}` : "";
  const what = page.sector ? `${page.sector} investors` : SEGMENTS[page.segment as keyof typeof SEGMENTS].short;
  return {
    title: `${page.title} (${new Date().getFullYear()}): ${plus(page.count)} investors`,
    description: `Find ${plus(page.count)} ${what}${where}. See what they invest in, their stage and sector focus, and send personalised cold emails with EasyFundraise.`,
    alternates: { canonical: `/investors/${slug}` },
  };
}

const ADVICE: Record<string, string[]> = {
  angel: ["Angels decide alone and fast, so a short, personal email beats a long deck.", "Lead with traction or a sharp insight about the market, then ask for 20 minutes.", "Ask each angel who else they would introduce you to. Angels travel in groups."],
  vc: ["Find the partner who covers your sector, not just the firm.", "Reference a portfolio company or thesis they have written about.", "Ask early whether they lead rounds and what cheque size they write."],
  seed: ["At seed most investors want a lead in place. Line up lead conversations first.", "Show early traction and why now. Keep the first email under 120 words.", "Send a round update when you hit 50% committed. Momentum moves followers."],
  "pre-seed": ["Pre-seed investors back teams. Say why you are the right people in one line.", "A clear insight and early signal (waitlist, pilots, LOIs) beats polished metrics.", "Move quickly: run your outreach in a focused four to six week sprint."],
  all: ["Filter by stage first: most investors only write cheques at one or two stages.", "Personalise the first line with something specific about the investor.", "Track every conversation so nobody goes cold between follow-ups."],
};

export default async function InvestorList({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const r = await resolve(slug);
  if (!r) notFound();
  const { page, all } = r;
  const s = await getStats(page.segment, page.country ?? "", page.sector ?? "");
  if (s.count < MIN_PAGE) notFound();
  const seg = page.segment === "all" ? null : SEGMENTS[page.segment];
  const what = page.sector ? `${page.sector} investors` : seg!.short;
  const related = all.filter((p) => p.slug !== slug && ((page.country && p.country === page.country) || (page.segment !== "all" && p.segment === page.segment) || (page.sector && p.sector))).slice(0, 12);
  const faq = [
    [`How many ${what}${page.country ? ` are there in ${theCountry(page.country)}` : " are in the database"}?`, `The EasyFundraise investor database lists ${plus(s.count)} ${what}${page.country ? ` based in ${theCountry(page.country)}` : ""}, updated as we research new investors.`],
    [`How do I contact ${what}?`, `Start a free trial, filter the list by stage and sector, and reveal the investors that fit. EasyFundraise drafts a short personal email for each one and sends it from your own Gmail.`],
    [`What do ${what} invest in?`, s.sectors.length ? `The most common sectors are ${s.sectors.slice(0, 4).map((x) => x.name).join(", ")}.` : "Sector focus varies by investor; each profile shows their thesis and recent deals."],
  ];
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Investors", item: "/investors" }, { "@type": "ListItem", position: 2, name: page.title }] },
      { "@type": "FAQPage", mainEntity: faq.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) },
    ],
  };
  const max = Math.max(...s.sectors.map((x) => x.count), 1);
  return (
    <PageShell
      crumbs={
        <>
          <Link href="/investors" className="hover:text-white">Investor lists</Link> / {page.title}
        </>
      }
      eyebrow="Investor list"
      title={page.title}
      intro={
        <>
          {plus(s.count)} {what}
          {page.country ? ` in ${theCountry(page.country)}` : ""} in the EasyFundraise investor database, with their sector focus, stage and recent activity. Find the ones that fit your round and reach them with a personal email from your own Gmail.
        </>
      }
    >
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <div className="mx-auto max-w-5xl px-4 md:px-6 py-14 grid lg:grid-cols-[1fr_320px] gap-12">
        <div className="space-y-12">
          <section>
            <h2 className="text-2xl md:text-3xl font-bold tracking-tight">What these investors back</h2>
            <ul className="mt-6 space-y-3">
              {s.sectors.map((x) => (
                <li key={x.name}>
                  <div className="flex justify-between text-[15px]">
                    <Link href={`/investors/${slugify(x.name)}-investors`} className="hover:text-[#0f62fe]">{x.name}</Link>
                    <span className="text-[#7a849a]">{plus(x.count)}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-[#eef3ff] overflow-hidden">
                    <div className="h-full rounded-full bg-[linear-gradient(90deg,#0f62fe,#7c5cff)]" style={{ width: `${(100 * x.count) / max}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </section>
          {s.firms.length > 0 && (
            <section>
              <h2 className="text-2xl md:text-3xl font-bold tracking-tight">Firms and networks in this list</h2>
              <p className="mt-2 text-[#4a5670]">Organisations with several investors in this list. Sign in to see every investor, their thesis and contact details.</p>
              <div className="mt-5 flex flex-wrap gap-2">
                {s.firms.map((f) => (
                  <span key={f.name} className="rounded-full border border-[#dfe6f2] bg-[#f6f9ff] px-3.5 py-1.5 text-[15px]">
                    {f.name}
                  </span>
                ))}
              </div>
            </section>
          )}
          {!page.country && s.countries.length > 0 && (
            <section>
              <h2 className="text-2xl md:text-3xl font-bold tracking-tight">Where they are based</h2>
              <ul className="mt-5 grid sm:grid-cols-2 gap-x-8 gap-y-2 text-[15px]">
                {s.countries.map((c) => (
                  <li key={c.name} className="flex justify-between border-b border-[#eef1f6] py-1.5">
                    <span>{c.name}</span>
                    <span className="text-[#7a849a]">{plus(c.count)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <h2 className="text-2xl md:text-3xl font-bold tracking-tight">How to approach {what}</h2>
            <ul className="mt-5 space-y-3">
              {ADVICE[page.segment].map((a) => (
                <li key={a} className="flex gap-3 text-[17px]">
                  <Check size={20} className="text-[#16a34a] mt-0.5 shrink-0" /> {a}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[15px] text-[#4a5670]">
              More in our guide to <Link href="/blog/cold-email-to-investors" className="text-[#0f62fe] underline">cold emailing investors</Link>.
            </p>
          </section>
          <section>
            <h2 className="text-2xl md:text-3xl font-bold tracking-tight">Questions</h2>
            <div className="mt-4 divide-y divide-[#eef1f6]">
              {faq.map(([q, a]) => (
                <div key={q} className="py-4">
                  <h3 className="font-semibold text-lg">{q}</h3>
                  <p className="mt-1 text-[#4a5670]">{a}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
        <aside className="space-y-6 lg:sticky lg:top-24 h-fit">
          <div className="rounded-2xl bg-[#070b1a] text-white p-6 shadow-xl">
            <div className="text-3xl font-extrabold">{plus(s.count)}</div>
            <div className="text-white/70">{what}{page.country ? ` in ${theCountry(page.country)}` : ""}</div>
            <p className="mt-4 text-[15px] text-white/75">See every investor with fit scores, theses and recent deals, then send personal emails from your Gmail.</p>
            <Link href="/login?mode=signup" className="lp-btn-primary mt-5 h-12 w-full text-[16px]">
              See the investors <ArrowRight size={18} />
            </Link>
            <p className="mt-2 text-xs text-white/50 text-center">14-day free trial · no card</p>
          </div>
          {related.length > 0 && (
            <nav aria-label="Related investor lists">
              <div className="font-semibold mb-2">Related lists</div>
              <ul className="space-y-1.5 text-[15px]">
                {related.map((p) => (
                  <li key={p.slug}>
                    <Link href={`/investors/${p.slug}`} className="text-[#0f62fe] hover:underline">{p.title}</Link>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </aside>
      </div>
    </PageShell>
  );
}

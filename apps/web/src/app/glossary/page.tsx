import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/landing/PageShell";

export const metadata: Metadata = {
  title: "Fundraising Glossary: Startup Funding Terms Explained",
  description: "Plain-English definitions of startup fundraising terms: SAFE, pre-money valuation, lead investor, pro rata, angel syndicate, term sheet and more.",
  alternates: { canonical: "/glossary" },
};

const TERMS: [string, string][] = [
  ["Angel investor", "An individual who invests their own money in early-stage startups, typically writing cheques of $10K to $100K at angel or pre-seed stage."],
  ["Angel syndicate", "A group of angels who invest together in one deal, usually led by one experienced angel who negotiates terms for the group."],
  ["Pre-seed round", "The first institutional money into a startup, often $250K to $1.5M, backing the team and insight before meaningful traction."],
  ["Seed round", "A round of typically $1.5M to $4M that funds a startup from early traction to Series A milestones."],
  ["Series A", "The first large priced round, usually led by a venture capital firm once a startup has a repeatable growth engine."],
  ["Venture capital (VC)", "A fund that invests other people's money (from limited partners) into high-growth startups in exchange for equity."],
  ["Lead investor", "The investor who sets the terms of a round, usually writes the largest cheque and often takes a board seat."],
  ["Follow-on investor", "An investor who joins a round on the terms set by the lead."],
  ["SAFE", "Simple Agreement for Future Equity: a contract that converts into shares at a later priced round, usually with a valuation cap and or a discount."],
  ["Convertible note", "A short-term loan that converts into equity at a future round, typically with interest, a cap and a discount."],
  ["Valuation cap", "The maximum valuation at which a SAFE or note converts, protecting early investors if the next round is priced high."],
  ["Pre-money valuation", "The value of a company before new money is invested."],
  ["Post-money valuation", "Pre-money valuation plus the new money raised in the round."],
  ["Dilution", "The reduction in existing shareholders' ownership percentage when new shares are issued."],
  ["Pro rata rights", "An investor's right to invest in future rounds to keep their ownership percentage."],
  ["Term sheet", "A short, mostly non-binding document setting out the key terms of an investment before the legal documents are drafted."],
  ["Due diligence", "The investor's review of a company's financials, legal position, product, market and team before investing."],
  ["Cap table", "A table showing who owns what percentage of the company, including founders, investors and the option pool."],
  ["Option pool", "Shares reserved for future employees, often created or topped up before a priced round."],
  ["Data room", "A shared space with the documents investors need to evaluate and close a deal: deck, financials, contracts and legal documents."],
  ["Warm introduction", "An introduction to an investor from someone they know and trust, such as a founder they backed."],
  ["Cold email", "An email to an investor who does not know you. Short, specific cold emails work well at angel, pre-seed and seed stage."],
  ["Fundraising CRM", "Software for tracking every investor conversation through stages, from first contact to money received."],
  ["Runway", "How many months a startup can operate before running out of cash at its current burn rate."],
  ["Burn rate", "The amount of cash a startup spends each month, net of revenue."],
  ["MRR / ARR", "Monthly or annual recurring revenue, the core traction metric for subscription businesses."],
  ["First close", "The point at which some of the round's money is committed and legally closed, before the round is complete."],
  ["Oversubscribed", "When investors want to put in more money than the round has space for."],
];

export default function Glossary() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "DefinedTermSet",
    name: "Fundraising glossary",
    hasDefinedTerm: TERMS.map(([n, d]) => ({ "@type": "DefinedTerm", name: n, description: d })),
  };
  return (
    <PageShell eyebrow="Resources" title="Fundraising glossary" intro="The startup funding terms you will hear from investors, explained in plain English.">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <dl className="mx-auto max-w-3xl px-4 md:px-6 py-12 divide-y divide-[#eef1f6]">
        {TERMS.map(([n, d]) => (
          <div key={n} id={n.toLowerCase().replace(/[^a-z0-9]+/g, "-")} className="py-5 scroll-mt-24">
            <dt className="text-xl font-bold text-[#0b1220]">{n}</dt>
            <dd className="mt-1 text-[17px] text-[#4a5670] leading-relaxed">{d}</dd>
          </div>
        ))}
      </dl>
      <p className="mx-auto max-w-3xl px-4 md:px-6 pb-16 text-[17px]">
        Ready to put it into practice? Read <Link href="/blog/how-to-find-investors-for-your-startup" className="text-[#0f62fe] underline">how to find investors for your startup</Link>.
      </p>
    </PageShell>
  );
}

import Link from "next/link";
import { LogoMark } from "./LogoMark";

const COLS: [string, [string, string][]][] = [
  ["Product", [["/#investor-database", "Investor database"], ["/#cold-email", "Cold email to investors"], ["/#crm", "Fundraising CRM"], ["/#data-room", "Startup data room"], ["/login", "Start free trial"]]],
  ["Browse investors", [
    ["/investors/angel-investors-in-united-states", "Angel investors in the US"],
    ["/investors/venture-capital-firms-in-united-kingdom", "VC investors in the UK"],
    ["/investors/seed-investors-in-germany", "Seed investors in Germany"],
    ["/investors/pre-seed-investors-in-india", "Pre-seed investors in India"],
    ["/investors/fintech-investors", "Fintech investors"],
    ["/investors/artificial-intelligence-investors", "AI investors"],
    ["/investors/saas-and-enterprise-investors", "SaaS investors"],
    ["/investors", "All investor lists"],
  ]],
  ["Resources", [["/blog", "Fundraising blog"], ["/blog/how-to-find-investors-for-your-startup", "How to find investors"], ["/blog/cold-email-to-investors", "Cold email templates"], ["/blog/pre-seed-vs-seed", "Pre-seed vs seed"], ["/glossary", "Fundraising glossary"], ["/#faq", "FAQ"]]],
  ["Company", [["/legal/privacy", "Privacy policy"], ["/legal/terms", "Terms and conditions"], ["/legal/cookies", "Cookie policy"], ["/legal/data-sources", "Data sources & investor rights"], ["/investor-request", "Investor? Update your profile"]]],
];

export function Footer() {
  return (
    <footer className="lp-dark border-t border-white/10">
      <div className="mx-auto max-w-7xl px-4 md:px-6 py-14 grid gap-10 md:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1.2fr_1fr_1fr]">
        <div>
          <Link href="/" className="flex items-center gap-2.5">
            <LogoMark size={32} />
            <span className="text-lg font-bold text-white">
              Easy<span className="text-[#7cb4ff]">Fundraise</span>
            </span>
          </Link>
          <p className="mt-4 max-w-sm text-[15px] text-white/60 leading-relaxed">
            The investor database, cold email platform and fundraising CRM for founders raising angel, pre-seed and seed rounds.
          </p>
        </div>
        {COLS.map(([title, links]) => (
          <nav key={title} className="flex flex-col gap-2.5 text-[15px] text-white/65" aria-label={title}>
            <span className="text-white font-semibold mb-1">{title}</span>
            {links.map(([href, label]) => (
              <Link key={href} href={href} className="hover:text-white transition-colors">
                {label}
              </Link>
            ))}
          </nav>
        ))}
      </div>
      <div className="border-t border-white/10 py-6 px-4 text-center text-sm text-white/45">© {new Date().getFullYear()} EasyFundraise. All rights reserved.</div>
    </footer>
  );
}

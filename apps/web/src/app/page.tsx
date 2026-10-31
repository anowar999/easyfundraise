import { ArrowRight, Bell, KanbanSquare, Mail, Search, Sparkles, Upload } from "lucide-react";
import Link from "next/link";

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "EasyFundraise",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "AI-powered fundraising platform that helps founders find investors, contact them with personalised outreach, manage their investor pipeline and raise capital.",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD", description: "14-day free trial" },
};

const FEATURES = [
  { icon: Search, title: "Find the investors that fit", body: "Search a researched investor base by sector, stage, geography and check size. See who actually writes pre-seed and seed checks, not just who is tagged that way." },
  { icon: Mail, title: "Short emails that sound like you", body: "Three-email sequences grounded in each investor's own thesis, portfolio and recent deals. Sent from your Gmail, threaded properly, capped at 20 a day." },
  { icon: KanbanSquare, title: "A CRM built for raising", body: "Drag cards from Not started to Payment received. Notes turn into reminders. Import your existing spreadsheet in a minute." },
  { icon: Bell, title: "Never miss a follow-up", body: "A daily brief of who is due, who is going cold and which calls need prep, on your phone or your laptop." },
];

export default function Landing() {
  return (
    <div className="min-h-dvh">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <header className="mx-auto max-w-6xl px-4 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icon.svg" alt="" className="w-8 h-8" />
          <span className="font-bold tracking-tight">
            Easy<span className="text-brand">Fundraise</span>
          </span>
        </Link>
        <Link href="/login" className="btn-primary btn-sm">
          Sign in
        </Link>
      </header>
      <main>
        <section className="mx-auto max-w-6xl px-4 pt-10 pb-16 md:pt-20 md:pb-24 grid md:grid-cols-2 gap-10 items-center">
          <div>
            <div className="chip text-brand border-brand/30 bg-brand/5 mb-4">
              <Sparkles size={12} /> Your personal fundraising agent
            </div>
            <h1 className="text-4xl md:text-5xl font-bold tracking-tight leading-[1.08]">
              Find the right investors. Reach them precisely. Close your round.
            </h1>
            <p className="mt-5 text-lg text-muted max-w-xl">
              Everything a founder needs to find investors, contact them, manage relationships and raise capital, with an AI agent
              that keeps the process moving.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/login" className="btn-primary h-12 px-5 text-base">
                Find investors for your startup <ArrowRight size={18} />
              </Link>
              <Link href="/login?next=/app/funnel/import" className="btn-ghost h-12 px-5 text-base">
                <Upload size={18} /> Import your tracker
              </Link>
            </div>
            <p className="mt-3 text-xs text-muted">14-day free trial. No card. Sign in with Google.</p>
          </div>
          <div className="card p-4 md:p-6 shadow-sm">
            <div className="text-xs text-muted mb-3">Today</div>
            {[
              ["Follow up with Jane Patel", "Seed VC · asked for the deck", "Due today"],
              ["Call with Omar at Northwind", "Brief ready", "Tomorrow 10:00"],
              ["4 new investors like the ones replying", "Health AI · pre-seed", "Review"],
            ].map(([t, s, r]) => (
              <div key={t} className="flex items-center gap-3 py-3 border-b border-line last:border-0">
                <div className="w-2 h-2 rounded-full bg-brand" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{t}</div>
                  <div className="text-xs text-muted truncate">{s}</div>
                </div>
                <div className="text-xs text-brand whitespace-nowrap">{r}</div>
              </div>
            ))}
          </div>
        </section>
        <section className="mx-auto max-w-6xl px-4 pb-20 grid sm:grid-cols-2 gap-4">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="card p-6">
              <Icon className="text-brand" />
              <h2 className="mt-3 font-semibold">{title}</h2>
              <p className="mt-1 text-sm text-muted">{body}</p>
            </div>
          ))}
        </section>
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl px-4 py-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted">
          <span>© {new Date().getFullYear()} EasyFundraise</span>
          <Link href="/legal/privacy">Privacy</Link>
          <Link href="/legal/terms">Terms</Link>
          <Link href="/legal/data-sources">Data sources &amp; investor rights</Link>
          <Link href="/investor-request">Investor? Update or remove your profile</Link>
        </div>
      </footer>
    </div>
  );
}

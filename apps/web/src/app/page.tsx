import { ArrowRight, BellRing, Bot, CalendarCheck, Check, FileSpreadsheet, Globe2, LineChart, Mail, MousePointerClick, Search, ShieldCheck, Sparkles, Target, Users } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { CountUp } from "@/components/landing/CountUp";
import { Footer } from "@/components/landing/Footer";
import { Header } from "@/components/landing/Header";
import { Reveal } from "@/components/landing/Reveal";
import { RoundTabs } from "@/components/landing/RoundTabs";

export const metadata: Metadata = {
  title: { absolute: "Investor Database & Cold Email for Founders | EasyFundraise" },
  description:
    "Search 14,900+ investors, including angels, pre-seed and seed VCs. Send personalised cold emails from your Gmail and track your raise in a fundraising CRM, with an AI agent that keeps it moving.",
  keywords: ["investor database", "angel investor list", "seed VC database", "pre-seed investors", "cold email investors", "fundraising CRM", "startup fundraising", "find investors for startup"],
  alternates: { canonical: "/" },
  openGraph: {
    title: "EasyFundraise: the investor database and AI agent that gets founders funded",
    description: "14,900+ investors, cold emails that get replies, and a fundraising CRM in your pocket.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "EasyFundraise investor database" }],
  },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
};

const FAQ = [
  ["What is EasyFundraise?", "EasyFundraise is a fundraising platform for startup founders. It combines an investor database, personalised cold email outreach from your own Gmail, a fundraising CRM and an AI agent that tells you who to follow up with each day."],
  ["How many investors are in the investor database?", "More than 14,900 investors in 93 countries, including angel investors, angel syndicates, pre-seed and seed VCs, corporate VCs and family offices. Over 13,000 back pre-seed or seed rounds."],
  ["Is it for angel, pre-seed or seed rounds?", "All three. Filter by stage, cheque size, sector and geography to find investors who actually write the cheque you need, whether you are raising an angel round, pre-seed or seed."],
  ["Will my cold emails land in spam?", "Emails are sent from your own Gmail, in small daily batches that warm up over ten days, with at most three a day to any one firm. Each email is short, personal and has an opt-out line, and follow-ups stop as soon as an investor replies."],
  ["Can I import my existing investor spreadsheet?", "Yes. Upload your tracker as Excel or CSV and EasyFundraise matches the columns, removes duplicates and puts every investor in the right stage of your funnel."],
  ["Is the investor data GDPR compliant?", "Investor profiles are built only from public professional sources. Investors can update or remove their profile at any time, and contact details are only shown to founders who reveal them for a genuine raise."],
  ["Do I need traction to raise?", "No. Pre-seed and angel investors back teams and insight before revenue. EasyFundraise shows which investors invest before traction, so you pitch the right people at the right stage."],
  ["Does it work outside the US?", "Yes. The database covers investors in 93 countries, including the UK, Germany, France, Canada, India, Israel and Singapore, and emails are sent in each investor's local time zone."],
  ["Will my emails feel personal or mass-mailed?", "Personal. Each email is written for one investor, using facts about their thesis and portfolio, and you review and approve every email before it is sent."],
  ["Do I need a credit card to try it?", "No. You get a 14-day free trial when you sign in with Google. No card needed."],
];

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "EasyFundraise",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web, iOS, Android",
    url: "https://easyfundraise.com",
    description: "Investor database, cold email outreach and fundraising CRM for startup founders raising angel, pre-seed and seed rounds.",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD", description: "14-day free trial" },
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
  },
];

const TYPES = ["Angel investors", "Angel syndicates", "Pre-seed funds", "Seed VCs", "Series A VCs", "Corporate VCs", "Family offices", "Accelerators", "Operator angels", "Micro VCs"];

function Browser({ src, alt, className = "" }: { src: string; alt: string; className?: string }) {
  return (
    <div className={`rounded-xl md:rounded-2xl overflow-hidden bg-white ring-1 ring-black/5 shadow-[0_30px_80px_-20px_rgba(11,18,32,0.35)] ${className}`}>
      <div className="h-7 md:h-9 flex items-center gap-1.5 px-3 bg-[#f1f4f9] border-b border-[#e3e8ef]">
        <span className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
        <span className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
        <span className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
        <span className="ml-3 hidden sm:block flex-1 max-w-xs h-4 rounded bg-white text-[10px] text-[#8b95a7] px-2 leading-4">app.easyfundraise.com</span>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} loading="lazy" className="block w-full h-auto" width={1600} height={1000} />
    </div>
  );
}

function Phone({ src, alt, className = "" }: { src: string; alt: string; className?: string }) {
  return (
    <div className={`rounded-[2rem] md:rounded-[2.4rem] bg-[#0b1220] p-1.5 md:p-2 shadow-[0_30px_80px_-15px_rgba(11,18,32,0.6)] ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} loading="lazy" className="block w-full h-auto rounded-[1.6rem] md:rounded-[2rem]" width={600} height={1026} />
    </div>
  );
}

function Feature({ id, eyebrow, title, body, points, children, flip = false, icon }: { id: string; eyebrow: string; title: string; body: string; points: string[]; children: ReactNode; flip?: boolean; icon: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 py-20 md:py-28">
      <div className={`mx-auto max-w-7xl px-4 md:px-6 grid lg:grid-cols-[0.9fr_1.1fr] gap-12 lg:gap-16 items-center ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
        <Reveal>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-[#0f62fe] uppercase tracking-[0.14em]">
            {icon} {eyebrow}
          </div>
          <h2 className="mt-3 text-3xl md:text-[44px] leading-[1.1] font-bold tracking-tight text-[#0b1220]">{title}</h2>
          <p className="mt-5 text-lg text-[#4a5670] leading-relaxed">{body}</p>
          <ul className="mt-7 space-y-3.5">
            {points.map((p) => (
              <li key={p} className="flex gap-3 text-[17px] text-[#1c2740]">
                <span className="mt-0.5 grid place-items-center w-6 h-6 rounded-full bg-[#0f62fe]/10 text-[#0f62fe] shrink-0">
                  <Check size={15} strokeWidth={3} />
                </span>
                {p}
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal delay={150}>{children}</Reveal>
      </div>
    </section>
  );
}

export default function Landing() {
  return (
    <div className="lp min-h-dvh overflow-x-clip">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <Header />

      {/* ---------------- Hero ---------------- */}
      <section className="lp-hero-bg relative text-white pt-28 md:pt-36 pb-0 overflow-hidden">
        <div className="lp-grid absolute inset-0 pointer-events-none" />
        <div className="relative mx-auto max-w-7xl px-4 md:px-6 text-center">
          <Reveal>
            <div className="lp-pill inline-flex items-center gap-2.5 rounded-full bg-white/[0.07] px-5 md:px-6 py-2.5 md:py-3 text-base md:text-xl font-semibold text-white">
              <Sparkles className="text-[#8ab8ff]" size={22} /> Your personal fundraising agent
            </div>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="mt-7 mx-auto max-w-5xl text-[40px] leading-[1.05] sm:text-6xl md:text-7xl font-extrabold tracking-[-0.03em]">
              The <span className="lp-gradient-text">investor database</span> and AI agent that gets founders funded
            </h1>
          </Reveal>
          <Reveal delay={160}>
            <p className="mt-6 mx-auto max-w-3xl text-lg md:text-2xl text-white/75 leading-relaxed">
              Search 14,900+ angels and VCs, send cold emails that sound like you, and track every investor until the money lands. Whether you&apos;re raising an angel, pre-seed or seed round.
            </p>
          </Reveal>
          <Reveal delay={240}>
            <div className="mt-9 flex flex-col sm:flex-row justify-center gap-3">
              <Link href="/login?mode=signup" className="lp-btn-primary h-14 px-8 text-lg">
                Find your investors free <ArrowRight size={20} />
              </Link>
              <Link href="/investors" className="lp-btn-glass h-14 px-7 text-lg">
                <Search size={20} /> Browse investor lists
              </Link>
            </div>
            <p className="mt-4 text-sm text-white/55">14-day free trial · No credit card · Sign in with Google</p>
          </Reveal>
        </div>

        {/* Product shot with floating proof points */}
        <div className="relative mx-auto max-w-6xl px-4 md:px-6 mt-14 md:mt-20">
          <Reveal delay={200}>
            <div className="relative">
              <div className="absolute -inset-x-10 -top-10 bottom-0 bg-[radial-gradient(50%_60%_at_50%_30%,rgba(76,141,255,0.45),transparent_70%)] blur-2xl pointer-events-none" />
              <Browser src="/screens/d-investors.webp" alt="EasyFundraise investor database with fit scores, filters by stage, sector and investor type" className="relative rounded-b-none" />
              <Phone src="/screens/m-funnel.webp" alt="Fundraising CRM on a phone" className="hidden md:block absolute -right-10 lg:-right-16 -bottom-6 w-[210px] lg:w-[240px] lp-float-slow" />
              <div className="hidden sm:flex absolute -left-4 md:-left-12 top-[22%] items-center gap-3 rounded-2xl bg-white text-[#0b1220] px-4 py-3 shadow-2xl lp-float">
                <span className="grid place-items-center w-10 h-10 rounded-full bg-[#16a34a]/12 text-[#16a34a]">
                  <Mail size={20} />
                </span>
                <div className="text-left">
                  <div className="text-sm font-semibold">Grace replied</div>
                  <div className="text-xs text-[#5b6474]">&ldquo;Love this. Send me the deck?&rdquo;</div>
                </div>
              </div>
              <div className="hidden sm:flex absolute -left-2 md:-left-8 top-[62%] items-center gap-3 rounded-2xl bg-white text-[#0b1220] px-4 py-3 shadow-2xl lp-float-slow">
                <span className="text-2xl font-extrabold text-[#16a34a]">85</span>
                <div className="text-left text-xs leading-tight text-[#5b6474]">
                  <b className="text-[#0b1220] text-sm">Fit score</b>
                  <br />
                  backs seed health AI
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------------- Numbers + marquee ---------------- */}
      <section className="bg-white border-b border-[#eef1f6]" aria-label="Investor database in numbers">
        <div className="mx-auto max-w-7xl px-4 md:px-6 py-14 md:py-16 grid grid-cols-2 md:grid-cols-4 gap-y-10 text-center">
          {[
            [14900, "+", "investors in the database"],
            [13000, "+", "back pre-seed and seed"],
            [7200, "+", "VC partners and associates"],
            [93, "", "countries covered"],
          ].map(([n, s, l]) => (
            <div key={l as string}>
              <div className="text-4xl md:text-6xl font-extrabold tracking-tight text-[#0b1220]">
                <CountUp to={n as number} suffix={s as string} />
              </div>
              <div className="mt-2 text-[15px] md:text-base text-[#4a5670]">{l}</div>
            </div>
          ))}
        </div>
        <div className="relative overflow-hidden pb-12" aria-hidden>
          <div className="absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-white to-transparent z-10" />
          <div className="absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-white to-transparent z-10" />
          <div className="lp-marquee flex w-max gap-3">
            {[...TYPES, ...TYPES].map((t, k) => (
              <span key={k} className="rounded-full border border-[#dfe6f2] bg-[#f6f9ff] px-5 py-2.5 text-[15px] font-medium text-[#33415c] whitespace-nowrap">
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Rounds ---------------- */}
      <section className="py-20 md:py-28 bg-[linear-gradient(180deg,#fff,#f5f8ff)]">
        <div className="mx-auto max-w-5xl px-4 md:px-6">
          <Reveal>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-[#0b1220] text-center md:text-left">
              Whether you&apos;re raising an angel round, pre-seed or seed, <span className="text-[#0f62fe]">use EasyFundraise</span>
            </h2>
          </Reveal>
          <Reveal delay={120} className="mt-10 text-center md:text-left">
            <RoundTabs />
          </Reveal>
        </div>
      </section>

      {/* ---------------- Features ---------------- */}
      <Feature
        id="investor-database"
        icon={<Search size={16} />}
        eyebrow="Investor database"
        title="Find the investors who actually write your cheque"
        body="Not a stale list of names. Every profile shows what an investor backs, the stage and cheque size they invest at, where they invest and the deals they did recently, so you only pitch people who fit."
        points={["Angels, syndicates, pre-seed and seed VCs, family offices and CVCs", "Filter by sector, stage, cheque size, geography and who leads rounds", "Fit score that explains why each investor matches your startup", "“Who invested in…” to find the backers of companies like yours"]}
      >
        <div className="relative">
          <Browser src="/screens/d-investors.webp" alt="Investor database search with filters for stage, investor type and geography" />
        </div>
      </Feature>

      <div className="bg-[#f5f8ff]">
        <Feature
          id="cold-email"
          flip
          icon={<Mail size={16} />}
          eyebrow="Cold email to investors"
          title="Cold emails investors actually reply to"
          body="Your agent writes a short three-email sequence for each investor, built from facts about their thesis and portfolio. You approve it, and it goes out from your own Gmail at the right time in their time zone."
          points={["Personal openers, never mail-merge templates", "Sent from your Gmail, so replies land in your inbox", "Warm-up and daily limits that protect your domain", "Follow-ups stop the moment an investor replies"]}
        >
          <div className="relative">
            <Browser src="/screens/d-sequence.webp" alt="AI-written cold email sequence to an investor, sent from Gmail" />
            <div className="absolute -bottom-8 -left-4 md:-left-10 w-[62%] hidden sm:block lp-float-slow">
              <Browser src="/screens/d-outreach.webp" alt="Cold email open and reply rates" />
            </div>
          </div>
        </Feature>
      </div>

      <Feature
        id="crm"
        icon={<Target size={16} />}
        eyebrow="Fundraising CRM"
        title="Your whole raise in one funnel, on every device"
        body="Every investor moves from first email to money in the bank on a board built for fundraising. On your phone, update a stage in one tap, add a note after a call and see who replied."
        points={["Nine fundraising stages from Not started to Payment received", "Import your existing investor spreadsheet in a minute", "Notes become reminders automatically", "Works beautifully on iPhone and Android"]}
      >
        <div className="relative pb-10">
          <Browser src="/screens/d-funnel.webp" alt="Fundraising CRM pipeline board with investor stages" />
          <Phone src="/screens/m-card.webp" alt="Investor card on a phone" className="absolute -bottom-2 right-2 md:-right-6 w-[34%] max-w-[220px] lp-float" />
        </div>
      </Feature>

      {/* ---------------- Agent (dark band) ---------------- */}
      <section className="lp-hero-bg text-white py-20 md:py-28 relative overflow-hidden">
        <div className="lp-grid absolute inset-0 pointer-events-none opacity-60" />
        <div className="relative mx-auto max-w-7xl px-4 md:px-6 grid lg:grid-cols-2 gap-14 items-center">
          <Reveal>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-[#8ab8ff] uppercase tracking-[0.14em]">
              <Bot size={16} /> AI fundraising agent
            </div>
            <h2 className="mt-3 text-3xl md:text-5xl font-bold tracking-tight">An agent that keeps your raise moving while you build</h2>
            <p className="mt-5 text-lg text-white/75 leading-relaxed">
              Every morning it tells you who to follow up with, which calls need preparing and who is going cold. Ask it anything about your raise. It never sends anything without your tap.
            </p>
            <div className="mt-8 grid sm:grid-cols-2 gap-x-8 gap-y-6">
              {[
                [BellRing, "Daily brief", "Follow-ups, replies and calls, ready at 9am."],
                [CalendarCheck, "Meeting briefs", "Who they are, what they backed and what to ask."],
                [LineChart, "Learns what works", "Sees which emails get replies and writes more like them."],
                [Users, "Round updates", "Tell investors when you close your lead. Momentum sells."],
              ].map(([Icon, t, b]) => {
                const I = Icon as typeof BellRing;
                return (
                  <div key={t as string} className="flex gap-3">
                    <span className="grid place-items-center w-10 h-10 rounded-xl bg-white/10 ring-1 ring-white/15 text-[#8ab8ff] shrink-0">
                      <I size={20} />
                    </span>
                    <div>
                      <div className="font-semibold">{t as string}</div>
                      <div className="text-[15px] text-white/65">{b as string}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Reveal>
          <Reveal delay={150}>
            <Browser src="/screens/d-home.webp" alt="Daily fundraising brief with follow-ups due and calls this week" />
          </Reveal>
        </div>
      </section>

      <Feature
        id="data-room"
        flip
        icon={<Globe2 size={16} />}
        eyebrow="Data room"
        title="A data room that tells you who's really interested"
        body="Turn your company profile into a polished investor page in minutes. Share one link per investor and see who opened it, which sections they read and what they downloaded."
        points={["Public, password, email or personal-link access", "Per-investor reading time and downloads", "Alerts the moment a lead opens it", "Hidden from search engines unless you choose"]}
      >
        <Browser src="/screens/d-dataroom.webp" alt="Startup data room page shared with investors" />
      </Feature>

      {/* ---------------- How it works ---------------- */}
      <section className="py-20 md:py-28">
        <div className="mx-auto max-w-6xl px-4 md:px-6">
          <Reveal>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-[#0b1220] text-center">From zero to investor meetings in a day</h2>
          </Reveal>
          <ol className="mt-14 grid md:grid-cols-3 gap-10 md:gap-8 relative">
            <div className="hidden md:block absolute top-7 left-[16%] right-[16%] h-px bg-gradient-to-r from-[#0f62fe]/0 via-[#0f62fe]/40 to-[#0f62fe]/0" />
            {[
              [FileSpreadsheet, "Tell us about your raise", "Upload your deck or answer five questions. Import your existing investor list if you have one."],
              [MousePointerClick, "Pick investors who fit", "Your agent ranks thousands of investors by fit. Add the best ones to your funnel in a click."],
              [Mail, "Approve and send", "Review personal emails, approve, and watch replies turn into calls."],
            ].map(([Icon, t, b], k) => {
              const I = Icon as typeof Mail;
              return (
                <Reveal key={t as string} delay={k * 120}>
                  <li className="text-center list-none">
                    <span className="relative mx-auto grid place-items-center w-14 h-14 rounded-2xl bg-[#0f62fe] text-white shadow-[0_12px_30px_-10px_rgba(15,98,254,0.8)]">
                      <I size={24} />
                    </span>
                    <div className="mt-2 text-xs font-bold text-[#0f62fe] tracking-[0.2em]">STEP {k + 1}</div>
                    <h3 className="mt-2 text-xl font-bold text-[#0b1220]">{t as string}</h3>
                    <p className="mt-2 text-[#4a5670] leading-relaxed">{b as string}</p>
                  </li>
                </Reveal>
              );
            })}
          </ol>
          <Reveal className="mt-16 flex flex-wrap justify-center gap-x-8 gap-y-3 text-[15px] text-[#33415c]">
            {["Sends from your own Gmail", "Your data is never used to train AI", "Investors can update or remove their profile", "Cancel anytime"].map((t) => (
              <span key={t} className="inline-flex items-center gap-2">
                <ShieldCheck size={18} className="text-[#16a34a]" /> {t}
              </span>
            ))}
          </Reveal>
        </div>
      </section>

      {/* ---------------- Comparison ---------------- */}
      <section className="py-20 md:py-28 bg-white">
        <div className="mx-auto max-w-5xl px-4 md:px-6">
          <Reveal>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-[#0b1220] text-center">Stop doing the grunt work</h2>
            <p className="mt-4 text-lg text-[#4a5670] text-center">What a raise looks like with a spreadsheet, and with EasyFundraise.</p>
          </Reveal>
          <Reveal delay={100} className="mt-12 overflow-hidden rounded-3xl ring-1 ring-[#e3e8ef]">
            <div className="grid grid-cols-[1.1fr_1fr_1fr] bg-[#f6f9ff] text-sm md:text-base font-semibold">
              <div className="p-4 md:p-5" />
              <div className="p-4 md:p-5 text-[#7a849a]">On your own</div>
              <div className="p-4 md:p-5 text-[#0f62fe]">With EasyFundraise</div>
            </div>
            {[
              ["Building an investor list", "Days of Googling and stale lists", "Minutes, ranked by fit"],
              ["Finding the right contact", "Guessing emails, generic inboxes", "Verified contacts, revealed when you need them"],
              ["Writing outreach", "One template for everyone", "A personal sequence per investor"],
              ["Following up", "Sticky notes and memory", "Automatic, stops when they reply"],
              ["Tracking the round", "A spreadsheet nobody updates", "A funnel that updates itself"],
              ["Sharing your data room", "A Drive link with no insight", "See who read what, and for how long"],
            ].map(([a, b, c]) => (
              <div key={a} className="grid grid-cols-[1.1fr_1fr_1fr] border-t border-[#eef1f6] text-[14px] md:text-[16px]">
                <div className="p-4 md:p-5 font-semibold text-[#0b1220]">{a}</div>
                <div className="p-4 md:p-5 text-[#7a849a]">{b}</div>
                <div className="p-4 md:p-5 text-[#0b1220] flex gap-2">
                  <Check size={18} className="text-[#16a34a] mt-0.5 shrink-0" /> {c}
                </div>
              </div>
            ))}
          </Reveal>
        </div>
      </section>

      {/* ---------------- FAQ ---------------- */}
      <section id="faq" className="scroll-mt-20 py-20 md:py-28 bg-[#f5f8ff]">
        <div className="mx-auto max-w-3xl px-4 md:px-6">
          <Reveal>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight text-[#0b1220] text-center">Questions founders ask</h2>
          </Reveal>
          <div className="mt-10 divide-y divide-[#dfe6f2] border-y border-[#dfe6f2]">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-semibold text-[#0b1220]">
                  {q}
                  <span className="grid place-items-center w-8 h-8 rounded-full bg-white ring-1 ring-[#dfe6f2] text-[#0f62fe] transition-transform group-open:rotate-45 shrink-0">+</span>
                </summary>
                <p className="mt-3 text-[17px] text-[#4a5670] leading-relaxed">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Final CTA ---------------- */}
      <section className="lp-hero-bg relative overflow-hidden text-white py-20 md:py-28">
        <div className="lp-grid absolute inset-0 pointer-events-none" />
        <Reveal className="relative mx-auto max-w-4xl px-4 md:px-6 text-center">
          <h2 className="text-4xl md:text-6xl font-extrabold tracking-tight">
            Your next investor is <span className="lp-gradient-text">already in here</span>
          </h2>
          <p className="mt-5 text-lg md:text-xl text-white/75">Start your 14-day free trial and send your first personal investor email today.</p>
          <div className="mt-9 flex flex-col sm:flex-row justify-center gap-3">
            <Link href="/login?mode=signup" className="lp-btn-primary h-14 px-8 text-lg">
              Find your investors free <ArrowRight size={20} />
            </Link>
            <Link href="/login?next=/app/funnel/import" className="lp-btn-glass h-14 px-7 text-lg">
              <FileSpreadsheet size={20} /> Import your investor list
            </Link>
          </div>
        </Reveal>
      </section>

      <Footer />
    </div>
  );
}

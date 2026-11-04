/** Y Combinator applications that founders (or YC) chose to publish. Seed data for Resources → YC applications.
 *  Links go to where each application was published; the text stays with its authors. */

export type YcApp = {
  company: string;
  batch: string;
  year: number;
  sector: string;
  what: string;
  outcome?: string;
  url: string;
  source: string;
};

export const YC_GUIDES: { title: string; url: string; note: string }[] = [
  { title: "Apply to Y Combinator", url: "https://www.ycombinator.com/apply", note: "Official form, deadlines and what YC looks for." },
  { title: "How to Apply to Y Combinator, by Paul Graham", url: "https://www.paulgraham.com/howtoapply.html", note: "The classic essay on writing answers partners can read fast." },
];

/** Newest first: by year, then by season within the year (Winter, Spring, Summer, Fall) */
export function batchOrder(batch: string, year: number) {
  return year * 10 + ({ W: 0, X: 1, S: 2, F: 3 } as Record<string, number>)[batch[0]];
}

export const YC_APPS: YcApp[] = [
  { company: "MagicBell", batch: "W21", year: 2021, sector: "Developer tools", what: "Notification inbox and delivery infrastructure for apps.", url: "https://shizune.co/yc-application-examples/magicbell", source: "Shizune" },
  { company: "Dendron", batch: "W21", year: 2021, sector: "Developer tools", what: "Open-source note-taking and knowledge base for developers.", url: "https://shizune.co/yc-application-examples/dendron", source: "Shizune" },
  { company: "Metlo", batch: "S21", year: 2021, sector: "Security", what: "API security: finds and protects a company's API endpoints.", url: "https://shizune.co/yc-application-examples/metlo", source: "Shizune" },
  { company: "Virtually", batch: "S20", year: 2020, sector: "Edtech", what: "Software for running online classes and cohort programs.", url: "https://shizune.co/yc-application-examples/virtually", source: "Shizune" },
  { company: "Prolific", batch: "S19", year: 2019, sector: "Research", what: "Recruits vetted participants for online research and AI data.", url: "https://shizune.co/yc-application-examples/prolific", source: "Shizune" },
  { company: "InEvent", batch: "S19", year: 2019, sector: "SaaS", what: "Platform for running in-person, virtual and hybrid events.", url: "https://shizune.co/yc-application-examples/inevent", source: "Shizune" },
  { company: "OpenPhone", batch: "S18", year: 2018, sector: "SaaS", what: "Business phone numbers and calling in an app.", url: "https://shizune.co/yc-application-examples/openphone", source: "Shizune" },
  { company: "Slite", batch: "W18", year: 2018, sector: "SaaS", what: "Shared docs and knowledge base for remote teams.", url: "https://shizune.co/yc-application-examples/slite", source: "Shizune" },
  { company: "Relationship Hero", batch: "S17", year: 2017, sector: "Consumer", what: "On-demand relationship coaching.", url: "https://shizune.co/yc-application-examples/relationship-hero", source: "Shizune" },
  { company: "Simple Habit", batch: "W17", year: 2017, sector: "Consumer health", what: "Short guided meditations for busy people.", url: "https://shizune.co/yc-application-examples/simple-habit", source: "Shizune" },
  { company: "Dropbox", batch: "S07", year: 2007, sector: "SaaS", what: "File sync and backup across computers.", outcome: "IPO in 2018", url: "https://www.ycombinator.com/apply/dropbox", source: "Y Combinator" },
  { company: "Reddit", batch: "S05", year: 2005, sector: "Consumer", what: "The front page of the internet, from YC's first batch.", outcome: "IPO in 2024", url: "https://getintoyc.com/company/reddit/", source: "GetIntoYC" },
  { company: "Mixpanel", batch: "S09", year: 2009, sector: "Analytics", what: "Event-based product analytics.", url: "https://suhaild.medium.com/mixpanels-y-combinator-application-in-2009-34b5d30dbc12", source: "Founder on Medium" },
  { company: "GitLab", batch: "W15", year: 2015, sector: "Developer tools", what: "Open-source code hosting and DevOps.", outcome: "IPO in 2021", url: "https://about.gitlab.com/blog/2016/09/30/gitlabs-application-for-y-combinator-winter-2015/", source: "GitLab blog" },
  { company: "Cruise", batch: "W14", year: 2014, sector: "Mobility", what: "Self-driving car technology.", outcome: "Acquired by GM in 2016", url: "https://www.scribd.com/doc/309342340/Cruise-Automation-Y-Combinator-Application", source: "Scribd" },
  { company: "Paystack", batch: "W16", year: 2016, sector: "Fintech", what: "Online payments for African businesses, starting in Nigeria.", outcome: "Acquired by Stripe in 2020", url: "https://shizune.co/yc-application-examples/paystack", source: "Shizune" },
  { company: "The Muse", batch: "W12", year: 2012, sector: "Careers", what: "Career advice and a look inside companies that are hiring.", url: "https://www.themuse.com/advice/the-muses-successful-application-to-y-combinator-w12", source: "The Muse" },
  { company: "The Flex Company", batch: "S16", year: 2016, sector: "Consumer health", what: "Period care products.", url: "https://medium.com/@laurenschulte/the-flex-companys-successful-y-combinator-s16-application-92bd2b3d568d", source: "Founder on Medium" },
  { company: "Standard Treasury", batch: "S13", year: 2013, sector: "Fintech", what: "APIs for banks.", url: "http://blog.zactownsend.com/our-yc-s13-application", source: "Founder's blog" },
  { company: "Apptimize", batch: "S13", year: 2013, sector: "Developer tools", what: "A/B testing for mobile apps.", url: "http://www.nancyhua.com/2014/10/08/successful-y-combinator-s13-application/", source: "Founder's blog" },
  { company: "Mimir", batch: "S15", year: 2015, sector: "Edtech", what: "Tools for teaching computer science classes.", url: "https://medium.com/@prahasithv/our-successful-ycombinator-s15-application-843c3047cadd", source: "Founder on Medium" },
  { company: "Lollipuff", batch: "W13", year: 2013, sector: "Marketplace", what: "Authenticated resale of designer fashion.", url: "https://shizune.co/yc-application-examples/lollipuff", source: "Shizune" },
];

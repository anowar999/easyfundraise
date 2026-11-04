/** Accelerators, VC-run programs and incubators. Seed data for Resources → Accelerators & VCs and → Incubators.
 *  Deal terms are the published standard terms as of 2026 and change between cohorts, so every card links to the
 *  program's own site. Leave a field out rather than guess. */

export type ProgramKind = "accelerator" | "incubator";

export type Program = {
  name: string;
  kind: ProgramKind;
  /** Short label shown as a tag, e.g. "VC program", "Venture studio" */
  model: string;
  invest?: string;
  equity?: string;
  where?: string;
  note: string;
  url: string;
};

export const PROGRAMS_CHECKED = "2026";

export const PROGRAMS: Program[] = [
  // Accelerators & VC programs
  { name: "Y Combinator", kind: "accelerator", model: "Accelerator", invest: "$500K", equity: "7% on the first $125K, the rest on an uncapped SAFE", where: "San Francisco", note: "Four batches a year. Company must be incorporated in the US, Canada, Cayman or Singapore.", url: "https://www.ycombinator.com" },
  { name: "Techstars", kind: "accelerator", model: "Accelerator", invest: "$220K", equity: "At least 5% common, plus a SAFE", where: "Programs worldwide", note: "Industry and city programs. APAC programs invest $120K in total.", url: "https://www.techstars.com" },
  { name: "a16z speedrun", kind: "accelerator", model: "VC program", invest: "Up to $1M ($500K now, $500K in your next round)", equity: "10% on the first $500K", where: "San Francisco", note: "Andreessen Horowitz's program for games, consumer and AI startups.", url: "https://speedrun.a16z.com" },
  { name: "South Park Commons", kind: "accelerator", model: "VC program", invest: "$1M ($400K now, $600K follow-on)", equity: "7% on the $400K", where: "San Francisco & New York", note: "Founder Fellowship for people at the idea stage, before they have a company.", url: "https://www.southparkcommons.com" },
  { name: "Neo Residency", kind: "accelerator", model: "VC program", invest: "$750K plus $450K in compute credits", equity: "Uncapped, no fixed percentage", where: "San Francisco", note: "Small residency for technical founders.", url: "https://neo.com" },
  { name: "Entrepreneur First", kind: "accelerator", model: "Talent investor", invest: "Up to $250K ($125K plus an optional $125K)", equity: "8% on the first $125K", where: "London, Paris, Bangalore, San Francisco", note: "Join as an individual, find a co-founder in the program, then build.", url: "https://www.joinef.com" },
  { name: "Antler", kind: "accelerator", model: "Talent investor", invest: "Pre-seed check, terms by country", where: "30+ cities worldwide", note: "Residency to meet co-founders and validate an idea, with follow-on investment.", url: "https://www.antler.co" },
  { name: "500 Global Flagship", kind: "accelerator", model: "Accelerator", invest: "$150K", equity: "6%", where: "Global", note: "One of the most active seed investors worldwide.", url: "https://500.co" },
  { name: "SOSV (HAX and others)", kind: "accelerator", model: "VC program", invest: "Average pre-seed of about $550K", equity: "Targets 10%+", where: "San Francisco, New York, Newark", note: "Deep tech, hardware, climate and life sciences.", url: "https://sosv.com" },
  { name: "PearX", kind: "accelerator", model: "VC program", invest: "$250K to $2M depending on stage", where: "Bay Area, relocation required", note: "Pear VC's program for very early founders.", url: "https://pear.vc" },
  { name: "AI Grant", kind: "accelerator", model: "VC program", invest: "$250K plus $600K in credits", equity: "Uncapped, no fixed percentage", where: "San Francisco", note: "For AI-native product companies.", url: "https://aigrant.com" },
  { name: "Betaworks Camp", kind: "accelerator", model: "VC program", invest: "Up to $500K", where: "New York", note: "Themed cohorts with a residency at the start and the end.", url: "https://www.betaworks.com" },
  { name: "Sequoia Arc", kind: "accelerator", model: "VC program", note: "Sequoia's immersive program for pre-seed and seed founders. Terms are set per company.", url: "https://www.sequoiacap.com/arc/" },
  { name: "ERA", kind: "accelerator", model: "Accelerator", invest: "$150K", equity: "6%", where: "New York", note: "Two 4-month cohorts a year.", url: "https://www.eranyc.com" },
  { name: "AngelPad", kind: "accelerator", model: "Accelerator", invest: "$120K plus credits", equity: "About 7%", where: "San Francisco & New York", note: "Small, hands-on batches.", url: "https://angelpad.com" },
  { name: "Alchemist", kind: "accelerator", model: "Accelerator", invest: "About $30K net on average", equity: "About 5%", where: "Remote-friendly", note: "Six months, for startups selling to businesses.", url: "https://www.alchemistaccelerator.com" },
  { name: "gener8tor", kind: "accelerator", model: "Accelerator", invest: "$100K", equity: "7.5%", where: "US Midwest and more", note: "Programs run with cities and corporate partners.", url: "https://www.gener8tor.com" },
  { name: "LAUNCH", kind: "accelerator", model: "Accelerator", invest: "$125K", equity: "7%", where: "San Francisco", note: "14 weeks, run by Jason Calacanis.", url: "https://www.launchaccelerator.co" },
  { name: "43North", kind: "accelerator", model: "Competition", invest: "$1M to each of 5 winners a year", equity: "5%", where: "Buffalo, NY (relocation required)", note: "Startup competition with a year in Buffalo.", url: "https://www.43north.org" },
  { name: "Startupbootcamp", kind: "accelerator", model: "Accelerator", invest: "€25K in expenses covered", equity: "About 8%", where: "Europe and beyond", note: "Industry-focused programs with corporate partners.", url: "https://www.startupbootcamp.org" },

  // Incubators, studios and zero-equity programs
  { name: "Station F Founders Program", kind: "incubator", model: "Campus", equity: "No equity", where: "Paris", note: "Desks and support at the world's largest startup campus. No standard investment.", url: "https://stationf.co" },
  { name: "Berkeley SkyDeck", kind: "incubator", model: "University", invest: "$210K", equity: "7.5%", where: "Berkeley, CA", note: "UC Berkeley's program, with a $7.5K program fee.", url: "https://skydeck.berkeley.edu" },
  { name: "StartX", kind: "incubator", model: "University", equity: "No equity", where: "Stanford, CA", note: "Non-profit community for Stanford founders.", url: "https://startx.com" },
  { name: "MassChallenge", kind: "incubator", model: "Zero equity", equity: "No equity", where: "Boston and other cities", note: "Non-profit programs with cash prizes for winners.", url: "https://masschallenge.org" },
  { name: "Plug and Play", kind: "incubator", model: "Corporate", equity: "No equity for the program", where: "Silicon Valley and 50+ locations", note: "Connects startups with large corporate partners. Its VC arm invests separately.", url: "https://www.plugandplaytechcenter.com" },
  { name: "Founder Institute", kind: "incubator", model: "Pre-accelerator", invest: "None. Founders pay $799 to $1,199", equity: "2.5% warrant", where: "Online and 200+ cities", note: "Part-time program for founders who still have a job.", url: "https://fi.co" },
  { name: "Idealab", kind: "incubator", model: "Venture studio", where: "Pasadena, CA", note: "Started in 1996. Creates companies from its own ideas, then recruits teams.", url: "https://www.idealab.com" },
  { name: "Expa", kind: "incubator", model: "Venture studio", where: "San Francisco & New York", note: "Studio founded by Uber co-founder Garrett Camp.", url: "https://www.expa.com" },
  { name: "Atomic", kind: "incubator", model: "Venture studio", where: "San Francisco & Miami", note: "Builds companies with founders from day one.", url: "https://atomic.vc" },
  { name: "High Alpha", kind: "incubator", model: "Venture studio", where: "Indianapolis", note: "Studio and fund focused on B2B software.", url: "https://highalpha.com" },
  { name: "Pioneer Square Labs", kind: "incubator", model: "Venture studio", where: "Seattle", note: "Studio and seed fund.", url: "https://www.psl.com" },
  { name: "Hexa", kind: "incubator", model: "Venture studio", where: "Paris", note: "Formerly eFounders. Builds B2B software companies.", url: "https://www.hexa.com" },
];

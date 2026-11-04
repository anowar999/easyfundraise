/** Public pitch decks, grouped by the round they raised. Seed data for Resources → Pitch decks.
 *  Every entry links to where the deck was published or reviewed (we never rehost the file). Amounts and years are
 *  as the linked source reports them. To add a deck, append an entry; the page picks it up. */

export type DeckStage = "pre-seed" | "seed" | "series-a";

export type PitchDeck = {
  company: string;
  stage: DeckStage;
  /** As shown to founders, in the round's own currency */
  amount: string;
  /** Rough USD value, only for sorting by size */
  usd: number;
  year: number;
  sector: string;
  what: string;
  url: string;
  source: string;
};

export const DECK_STAGES: { key: DeckStage; label: string; blurb: string }[] = [
  { key: "pre-seed", label: "Pre-seed", blurb: "Idea or early product, usually friends, family, angels or a first small fund. Typically under $2M." },
  { key: "seed", label: "Seed", blurb: "A product with early users or revenue. Rounds typically $1M to $5M, a few much bigger." },
  { key: "series-a", label: "Series A", blurb: "Proven traction and a repeatable way to grow. Rounds typically $5M to $20M+." },
];

const TC = "TechCrunch Pitch Deck Teardown";

export const PITCH_DECKS: PitchDeck[] = [
  // Pre-seed
  { company: "Uber (UberCab)", stage: "pre-seed", amount: "$200K", usd: 200e3, year: 2008, sector: "Mobility", what: "The original UberCab deck: on-demand black cars booked from a phone.", url: "https://techcrunch.com/2023/02/23/sample-pre-seed-pitch-deck-uber-2008/", source: TC },
  { company: "Loom (as OpenTest)", stage: "pre-seed", amount: "$600K", usd: 600e3, year: 2016, sector: "SaaS", what: "Before Loom pivoted to async video, it pitched user testing as OpenTest.", url: "https://bestpitchdeck.com/opentest-loom", source: "Best Pitch Deck" },
  { company: "ElevenLabs", stage: "pre-seed", amount: "$2M", usd: 2e6, year: 2023, sector: "AI", what: "AI voice generation and dubbing, pitched before its rapid rise.", url: "https://bestpitchdeck.com/eleven-labs", source: "Best Pitch Deck" },
  { company: "Party Round", stage: "pre-seed", amount: "$7M", usd: 7e6, year: 2022, sector: "Fintech", what: "\"Venmo for fundraising\": a tool founders use to raise rounds, which raised its own round on itself.", url: "https://techcrunch.com/2022/09/22/sample-angel-pitch-deck-party-round/", source: TC },
  { company: "SquadTrip", stage: "pre-seed", amount: "$1.5M", usd: 1.5e6, year: 2023, sector: "Travel", what: "Booking and payments for group trip organisers.", url: "https://techcrunch.com/2023/08/04/sample-pre-seed-pitch-deck-squadtrip/", source: TC },
  { company: "Tanbii", stage: "pre-seed", amount: "$1.5M", usd: 1.5e6, year: 2023, sector: "Climate", what: "Helps individuals measure and cut their personal CO2 emissions.", url: "https://techcrunch.com/2023/09/01/sample-pre-seed-pitch-deck-tanbii/", source: TC },
  { company: "Geodesic.Life", stage: "pre-seed", amount: "$500K", usd: 500e3, year: 2024, sector: "Proptech", what: "Low-cost, green prefabricated dome houses, raised from friends and family.", url: "https://techcrunch.com/2024/04/19/sample-pre-seed-pitch-deck-geodesic-life/", source: TC },
  { company: "Queerie", stage: "pre-seed", amount: "$300K", usd: 300e3, year: 2024, sector: "Consumer", what: "A social app for the LGBTQ+ community.", url: "https://techcrunch.com/2024/04/05/sample-pre-seed-pitch-deck-queerie/", source: TC },
  { company: "NOQX", stage: "pre-seed", amount: "$200K", usd: 200e3, year: 2024, sector: "SaaS", what: "Stockholm startup helping teams set goals and work together on them.", url: "https://techcrunch.com/2024/04/26/sample-pre-seed-pitch-deck-noqx/", source: TC },
  { company: "The Palau Project", stage: "pre-seed", amount: "$125K", usd: 125e3, year: 2022, sector: "Climate", what: "Scan a product's barcode to see its impact and find lower-impact alternatives. Aimed for $500K, closed $125K.", url: "https://techcrunch.com/2022/10/25/sample-pre-seed-pitch-deck-palau-project/", source: TC },
  { company: "Mentimeter", stage: "pre-seed", amount: "$500K", usd: 500e3, year: 2014, sector: "SaaS", what: "Interactive presentations with live audience polls.", url: "https://www.failory.com/pitch-deck/mentimeter", source: "Failory" },
  { company: "StackShare", stage: "pre-seed", amount: "$300K", usd: 300e3, year: 2015, sector: "Developer tools", what: "Where developers discover and compare the tools other teams use.", url: "https://www.failory.com/pitch-deck/stackshare", source: "Failory" },
  { company: "MonkeyLearn", stage: "pre-seed", amount: "$125K", usd: 125e3, year: 2015, sector: "AI", what: "No-code machine learning for text analysis.", url: "https://www.failory.com/pitch-deck/monkeylearn", source: "Failory" },

  // Seed
  { company: "Airbnb", stage: "seed", amount: "$600K", usd: 600e3, year: 2009, sector: "Marketplace", what: "The famous early AirBed&Breakfast deck: book rooms with locals instead of hotels.", url: "https://www.slideshare.net/slideshow/airbnb-original-pitch-deck/50828878", source: "SlideShare" },
  { company: "Dropbox", stage: "seed", amount: "$1.2M", usd: 1.2e6, year: 2007, sector: "SaaS", what: "File sync that just works, pitched right after Y Combinator.", url: "https://www.slideshare.net/slideshow/dropboxs-original-pitch-deck/251815932", source: "SlideShare" },
  { company: "Buffer", stage: "seed", amount: "~$500K", usd: 500e3, year: 2011, sector: "SaaS", what: "Social media scheduling. The founders published the deck themselves.", url: "https://www.slideshare.net/Bufferapp/buffer-seedrounddeck", source: "Buffer on SlideShare" },
  { company: "Intercom", stage: "seed", amount: "$600K", usd: 600e3, year: 2011, sector: "SaaS", what: "Intercom's first deck: talk to your customers inside your product.", url: "https://www.slideshare.net/slideshow/intercom-1m-of-vc-investment-turned-into-240m-intercoms-initial-pitch-deck/149297642", source: "SlideShare" },
  { company: "Figma", stage: "seed", amount: "$3.8M", usd: 3.8e6, year: 2013, sector: "SaaS", what: "Design in the browser, years before launch.", url: "https://bestpitchdeck.com/figma", source: "Best Pitch Deck" },
  { company: "DoorDash", stage: "seed", amount: "$2.4M", usd: 2.4e6, year: 2013, sector: "Marketplace", what: "Local restaurant delivery, started from a Stanford dorm.", url: "https://bestpitchdeck.com/doordash", source: "Best Pitch Deck" },
  { company: "Wise (TransferWise)", stage: "seed", amount: "$1.3M", usd: 1.3e6, year: 2012, sector: "Fintech", what: "Cheap international money transfers without hidden bank fees.", url: "https://bestpitchdeck.com/transferwise", source: "Best Pitch Deck" },
  { company: "Mistral AI", stage: "seed", amount: "€105M", usd: 113e6, year: 2023, sector: "AI", what: "Europe's open model lab: a famous deck raised before any product existed.", url: "https://bestpitchdeck.com/mistral", source: "Best Pitch Deck" },
  { company: "Xpanceo", stage: "seed", amount: "$40M", usd: 40e6, year: 2024, sector: "Deep tech", what: "Smart contact lenses with a built-in display.", url: "https://techcrunch.com/2024/04/12/sample-seed-pitch-deck-xpanceo/", source: TC },
  { company: "CommandBar", stage: "seed", amount: "$4.8M", usd: 4.8e6, year: 2024, sector: "SaaS", what: "In-app search and help that guides users through software.", url: "https://techcrunch.com/2024/03/01/commandbar-seed-deck-teardown/", source: TC },
  { company: "Spinach.io", stage: "seed", amount: "$6M", usd: 6e6, year: 2023, sector: "AI", what: "An AI assistant for team meetings and stand-ups.", url: "https://techcrunch.com/2023/02/09/sample-seed-pitch-deck-spinach-io/", source: TC },
  { company: "Nokod Security", stage: "seed", amount: "$8M", usd: 8e6, year: 2023, sector: "Security", what: "Security for apps built on low-code and no-code platforms.", url: "https://techcrunch.com/2023/07/07/sample-seed-pitch-deck-nokod-security/", source: TC },
  { company: "CleanHub", stage: "seed", amount: "$7M", usd: 7e6, year: 2023, sector: "Climate", what: "Lets brands fund verified collection of plastic waste.", url: "https://techcrunch.com/2023/07/21/sample-seed-pitch-deck-cleanhub/", source: TC },
  { company: "Learn.xyz", stage: "seed", amount: "$3M", usd: 3e6, year: 2023, sector: "Edtech", what: "Bite-sized learning in a mobile app.", url: "https://techcrunch.com/2023/09/15/sample-seed-pitch-deck-learn-xyz/", source: TC },
  { company: "Prelaunch.com", stage: "seed", amount: "$1.5M", usd: 1.5e6, year: 2023, sector: "SaaS", what: "Helps hardware makers test demand before they build.", url: "https://techcrunch.com/2023/03/23/sample-seed-pitch-deck-prelaunch-dot-com/", source: TC },
  { company: "DeckMatch", stage: "seed", amount: "$1M", usd: 1e6, year: 2023, sector: "Fintech", what: "AI that helps investors screen the pitch decks they receive.", url: "https://techcrunch.com/2023/08/18/sample-seed-pitch-deck-deckmatch/", source: TC },
  { company: "Supliful", stage: "seed", amount: "$1M", usd: 1e6, year: 2022, sector: "E-commerce", what: "Launch your own supplement brand without stock or a factory.", url: "https://techcrunch.com/2022/10/13/sample-seed-pitch-deck-supliful/", source: TC },

  // Series A
  { company: "YouTube", stage: "series-a", amount: "$3.5M", usd: 3.5e6, year: 2005, sector: "Consumer", what: "The deck that raised from Sequoia months after launch.", url: "https://www.slideshare.net/slideshow/youtube-pitch-deck-87211646/87211646", source: "SlideShare" },
  { company: "Front", stage: "series-a", amount: "$10M", usd: 10e6, year: 2016, sector: "SaaS", what: "Shared inbox for teams. The founder published the deck in full.", url: "https://www.slideshare.net/MathildeCollin/front-series-a-deck-64596550", source: "Front on SlideShare" },
  { company: "Mattermark", stage: "series-a", amount: "$6.5M", usd: 6.5e6, year: 2014, sector: "Data", what: "Data on private companies for investors, shared by its founder.", url: "https://www.slideshare.net/DanielleMorrill/mattermark-2nd-final-series-a-deck", source: "Mattermark on SlideShare" },
  { company: "Databricks", stage: "series-a", amount: "$14M", usd: 14e6, year: 2013, sector: "Data", what: "The company behind Apache Spark, pitching managed big-data analytics.", url: "https://bestpitchdeck.com/databricks-series-a", source: "Best Pitch Deck" },
  { company: "Rippling", stage: "series-a", amount: "$45M", usd: 45e6, year: 2019, sector: "SaaS", what: "Payroll, HR and IT for employees in one system.", url: "https://bestpitchdeck.com/rippling", source: "Best Pitch Deck" },
  { company: "Magic Leap", stage: "series-a", amount: "$50M", usd: 50e6, year: 2014, sector: "Deep tech", what: "Mixed-reality headsets, years before shipping.", url: "https://bestpitchdeck.com/magic-leap", source: "Best Pitch Deck" },
  { company: "Xyte", stage: "series-a", amount: "$30M", usd: 30e6, year: 2024, sector: "SaaS", what: "Cloud platform for hardware makers to manage connected devices.", url: "https://techcrunch.com/2024/02/09/sample-series-a-pitch-deck-xyte/", source: TC },
  { company: "Equals", stage: "series-a", amount: "$16M", usd: 16e6, year: 2024, sector: "SaaS", what: "A spreadsheet connected to your company's live data.", url: "https://techcrunch.com/2024/02/16/sample-series-a-pitch-deck-equals/", source: TC },
  { company: "Cloudsmith", stage: "series-a", amount: "$15M", usd: 15e6, year: 2024, sector: "Developer tools", what: "Secure hosting for software packages and artifacts.", url: "https://techcrunch.com/2024/05/10/sample-series-a-pitch-deck-cloudsmith/", source: TC },
  { company: "PhageLab", stage: "series-a", amount: "$11M", usd: 11e6, year: 2024, sector: "Biotech", what: "Bacteriophage-based alternatives to antibiotics for animal health.", url: "https://techcrunch.com/2024/02/02/sample-series-a-pitch-deck-phagelab/", source: TC },
  { company: "SuperScale", stage: "series-a", amount: "$5.4M", usd: 5.4e6, year: 2024, sector: "Gaming", what: "Growth and marketing for mobile games.", url: "https://techcrunch.com/2024/03/15/sample-series-a-pitch-deck-superscale/", source: TC },
  { company: "Point.me", stage: "series-a", amount: "$10M", usd: 10e6, year: 2023, sector: "Travel", what: "Search engine for booking flights with points and miles.", url: "https://techcrunch.com/2023/09/29/sample-series-a-pitch-deck-point-me/", source: TC },
  { company: "Faye", stage: "series-a", amount: "$10M", usd: 10e6, year: 2023, sector: "Insurtech", what: "Travel insurance built around an app.", url: "https://techcrunch.com/2023/05/26/sample-series-a-pitch-deck-faye/", source: TC },
  { company: "BusRight", stage: "series-a", amount: "$7M", usd: 7e6, year: 2023, sector: "SaaS", what: "Routing and tracking software for school buses.", url: "https://techcrunch.com/2023/08/25/sample-series-a-pitch-deck-busright/", source: TC },
  { company: "Fibery", stage: "series-a", amount: "$5.2M", usd: 5.2e6, year: 2023, sector: "SaaS", what: "A flexible work management platform.", url: "https://techcrunch.com/2023/05/11/sample-series-a-pitch-deck-fibery/", source: TC },
  { company: "Hour One", stage: "series-a", amount: "$20M", usd: 20e6, year: 2022, sector: "AI", what: "AI video with lifelike virtual presenters.", url: "https://techcrunch.com/2022/12/01/pitch-deck-teardown-hour-ones-20m-series-a-deck/", source: TC },
  { company: "Vori", stage: "series-a", amount: "$10M", usd: 10e6, year: 2022, sector: "Retail", what: "Software for independent grocery stores.", url: "https://techcrunch.com/2022/10/06/sample-series-a-pitch-deck-vori/", source: TC },
];

/** Startup credit and perk programs. Seed data for Resources → AI perks.
 *  Amounts and eligibility are what each program published as of October 2026; they change often, so every card
 *  links to the official page. */

export type PerkKind = "ai" | "cloud" | "dev" | "ops";

export type Perk = {
  name: string;
  provider: string;
  kind: PerkKind;
  value: string;
  who: string;
  url: string;
};

export const PERK_KINDS: { key: PerkKind; label: string }[] = [
  { key: "ai", label: "AI models & GPUs" },
  { key: "cloud", label: "Cloud" },
  { key: "dev", label: "Dev & data tools" },
  { key: "ops", label: "Sales, support & ops" },
];

export const PERKS_CHECKED = "October 2026";

export const PERKS: Perk[] = [
  { name: "Claude for Startups", provider: "Anthropic", kind: "ai", value: "Up to $100K in Claude API credits", who: "Through Anthropic's partner VCs and accelerators. The direct cohort was full in October 2026.", url: "https://claude.com/programs/startups" },
  { name: "OpenAI for Startups", provider: "OpenAI", kind: "ai", value: "API credits and support (amount not published)", who: "VC-backed startups through OpenAI's investor partners.", url: "https://openai.com/startups/" },
  { name: "ElevenLabs Startup Grants", provider: "ElevenLabs", kind: "ai", value: "33M characters of voice AI over 12 months", who: "Startups with fewer than 25 employees.", url: "https://elevenlabs.io/startup-grants" },
  { name: "NVIDIA Inception", provider: "NVIDIA", kind: "ai", value: "Preferred hardware pricing, partner cloud credits, training", who: "AI startups at any stage. Free to join, no equity.", url: "https://www.nvidia.com/en-us/startups/" },
  { name: "Modal for Startups", provider: "Modal", kind: "ai", value: "Free GPU credits (amount not published)", who: "New customers backed by a Modal VC partner, or who raised $1M+.", url: "https://modal.com/startups" },
  { name: "Pinecone for Startups", provider: "Pinecone", kind: "ai", value: "Free Standard tier with Pro support, usage credits", who: "Under 100 employees, Series A or earlier.", url: "https://www.pinecone.io/startup-program/" },

  { name: "Google for Startups Cloud", provider: "Google", kind: "cloud", value: "Up to $350K over 2 years for AI startups, incl. Gemini ($2K Start tier)", who: "Bigger tiers need verifiable pre-seed to Series A funding. Email domain must match your website.", url: "https://cloud.google.com/startup" },
  { name: "AWS Activate", provider: "Amazon Web Services", kind: "cloud", value: "Up to $200K, usable on Bedrock ($1K to $5K self-funded)", who: "Pre-Series B, founded in the last 10 years. The big tier needs an investor that is an Activate provider.", url: "https://aws.amazon.com/startups/credits" },
  { name: "Microsoft for Startups", provider: "Microsoft", kind: "cloud", value: "Up to $150K in Azure credits", who: "Largest amounts go to startups referred by Microsoft's investor network.", url: "https://www.microsoft.com/en-us/startups" },
  { name: "Cloudflare for Startups", provider: "Cloudflare", kind: "cloud", value: "$10K, $100K or $350K by tier, incl. Workers AI", who: "$10K tier for teams under $1M raised. Higher tiers need a partner, up to Series B.", url: "https://www.cloudflare.com/forstartups/" },
  { name: "DigitalOcean Hatch", provider: "DigitalOcean", kind: "cloud", value: "12 months of credits (amount set by your referring partner)", who: "Raised $10M or less. Service businesses excluded.", url: "https://www.digitalocean.com/hatch" },
  { name: "Vercel for Startups", provider: "Vercel", kind: "cloud", value: "Up to $30K", who: "Criteria not published. Apply on the page.", url: "https://vercel.com/startups" },

  { name: "MongoDB for Startups", provider: "MongoDB", kind: "dev", value: "Atlas credits and Voyage AI tokens for 12 months", who: "Under 7 years old, Series A or earlier, single software product.", url: "https://www.mongodb.com/startups" },
  { name: "PostHog for Startups", provider: "PostHog", kind: "dev", value: "$50K for 12 months", who: "Under 2 years old, under $5M raised, company email.", url: "https://posthog.com/startups" },
  { name: "Datadog for Startups", provider: "Datadog", kind: "dev", value: "Up to $100K for a year, incl. LLM observability", who: "Series A or earlier, new to Datadog, partner referral needed.", url: "https://www.datadoghq.com/partner/datadog-for-startups/" },
  { name: "Sentry for Startups", provider: "Sentry", kind: "dev", value: "Up to $5K in credits plus priority support", who: "Early-stage startups. Apply on the page.", url: "https://sentry.io/for/startups/" },
  { name: "Linear for Startups", provider: "Linear", kind: "dev", value: "Up to 6 months of Business plan free", who: "Under 50 employees and affiliated with a Linear partner.", url: "https://linear.app/startups" },

  { name: "Stripe Atlas", provider: "Stripe", kind: "ops", value: "$2,500 Stripe credits plus $200K+ in partner offers", who: "Founders incorporating a US company through Atlas.", url: "https://stripe.com/atlas" },
  { name: "Notion for Startups", provider: "Notion", kind: "ops", value: "Up to 6 months of Business plan with Notion AI", who: "Under 100 employees. Longer offers through partners.", url: "https://www.notion.com/startups" },
  { name: "HubSpot for Startups", provider: "HubSpot", kind: "ops", value: "90% off in year one", who: "Pre-seed to Series A, with a partner or verifiable funding.", url: "https://www.hubspot.com/startups" },
  { name: "Intercom Early Stage", provider: "Intercom", kind: "ops", value: "93% off in year one", who: "Under $10M funded, under 15 employees, not already a customer.", url: "https://www.intercom.com/early-stage" },
];

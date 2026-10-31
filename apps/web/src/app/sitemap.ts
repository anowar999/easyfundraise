import type { MetadataRoute } from "next";

const base = process.env.NEXT_PUBLIC_SITE_URL ?? "https://easyfundraise.com";

export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/legal/privacy", "/legal/terms", "/legal/data-sources", "/investor-request"].map((p) => ({
    url: `${base}${p}`,
    changeFrequency: p ? "monthly" : "weekly",
    priority: p ? 0.4 : 1,
  }));
}

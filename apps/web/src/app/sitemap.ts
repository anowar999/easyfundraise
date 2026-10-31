import type { MetadataRoute } from "next";
import { allPosts } from "@/lib/blog";
import { getIndex, pagesFrom, SITE } from "@/lib/seo";

// Rendered on request (data is cached for 6h by fetch) so builds do not need a running API.
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const fixed: MetadataRoute.Sitemap = [
    { url: SITE, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE}/investors`, changeFrequency: "weekly", priority: 0.9 },
    { url: `${SITE}/blog`, changeFrequency: "weekly", priority: 0.8 },
    { url: `${SITE}/glossary`, changeFrequency: "monthly", priority: 0.6 },
    ...["privacy", "terms", "cookies", "data-sources"].map((s) => ({ url: `${SITE}/legal/${s}`, changeFrequency: "yearly" as const, priority: 0.3 })),
    { url: `${SITE}/investor-request`, changeFrequency: "yearly", priority: 0.3 },
  ];
  const posts = (await allPosts()).map((p) => ({ url: `${SITE}/blog/${p.slug}`, lastModified: p.date, changeFrequency: "monthly" as const, priority: 0.7 }));
  let lists: MetadataRoute.Sitemap = [];
  try {
    lists = pagesFrom(await getIndex()).map((p) => ({ url: `${SITE}/investors/${p.slug}`, changeFrequency: "weekly" as const, priority: 0.8 }));
  } catch {
    // API unreachable (e.g. during a Docker build): the lists are added on the next revalidation.
  }
  return [...fixed, ...posts, ...lists];
}

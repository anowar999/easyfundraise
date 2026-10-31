import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/landing/PageShell";
import { allPosts, readingTime } from "@/lib/blog";

export const metadata: Metadata = {
  title: "Fundraising Blog: Guides for Founders Raising Angel, Pre-seed and Seed Rounds",
  description: "Practical guides on finding investors, cold emailing VCs and angels, pre-seed vs seed, and running your raise like a sales process.",
  alternates: { canonical: "/blog" },
};

export default async function Blog() {
  const posts = await allPosts();
  return (
    <PageShell eyebrow="Blog" title="Fundraising guides for founders" intro="How to find investors, write cold emails that get replies, and close your round faster.">
      <div className="mx-auto max-w-4xl px-4 md:px-6 py-12 divide-y divide-[#eef1f6]">
        {posts.map((p) => (
          <article key={p.slug} className="py-8">
            <div className="text-sm text-[#7a849a]">
              {new Date(p.date).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })} · {readingTime(p.body)} min read
            </div>
            <h2 className="mt-1 text-2xl md:text-3xl font-bold tracking-tight">
              <Link href={`/blog/${p.slug}`} className="hover:text-[#0f62fe]">{p.title}</Link>
            </h2>
            <p className="mt-2 text-lg text-[#4a5670]">{p.description}</p>
            <Link href={`/blog/${p.slug}`} className="mt-3 inline-flex items-center gap-1.5 font-semibold text-[#0f62fe]">
              Read the guide <ArrowRight size={16} />
            </Link>
          </article>
        ))}
      </div>
    </PageShell>
  );
}

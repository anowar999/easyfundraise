import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/landing/PageShell";
import { allPosts, getPost, readingTime } from "@/lib/blog";
import { Markdown } from "@/lib/markdown";

export async function generateStaticParams() {
  return (await allPosts()).map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const p = await getPost((await params).slug);
  if (!p) return {};
  return { title: p.title, description: p.description, alternates: { canonical: `/blog/${p.slug}` }, openGraph: { type: "article", title: p.title, description: p.description, publishedTime: p.date } };
}

export default async function Post({ params }: { params: Promise<{ slug: string }> }) {
  const p = await getPost((await params).slug);
  if (!p) notFound();
  const more = (await allPosts()).filter((x) => x.slug !== p.slug).slice(0, 3);
  const jsonLd = { "@context": "https://schema.org", "@type": "Article", headline: p.title, description: p.description, datePublished: p.date, author: { "@type": "Organization", name: "EasyFundraise" }, publisher: { "@type": "Organization", name: "EasyFundraise" } };
  return (
    <PageShell
      crumbs={<Link href="/blog" className="hover:text-white">Blog</Link>}
      title={p.title}
      intro={
        <>
          <span className="block">{p.description}</span>
          <span className="block mt-3 text-base text-white/50">
            {new Date(p.date).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })} · {readingTime(p.body)} min read
          </span>
        </>
      }
    >
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <article className="mx-auto max-w-3xl px-4 md:px-6 py-12 text-[18px] leading-[1.75] text-[#1c2740] [&_h2]:!text-2xl md:[&_h2]:!text-3xl [&_h2]:!font-bold [&_h2]:!mt-12 [&_h2]:tracking-tight [&_a]:!text-[#0f62fe]">
        <Markdown source={p.body} />
      </article>
      <section className="mx-auto max-w-3xl px-4 md:px-6 pb-16">
        <div className="rounded-3xl lp-hero-bg text-white p-8 md:p-10">
          <h2 className="text-2xl md:text-3xl font-bold">Find investors who fit your round</h2>
          <p className="mt-2 text-white/75">Search 14,900+ investors, send personal emails from your Gmail and track every conversation.</p>
          <Link href="/login" className="lp-btn-primary mt-6 h-12 px-6 text-[16px]">
            Start free <ArrowRight size={18} />
          </Link>
        </div>
        {more.length > 0 && (
          <div className="mt-12">
            <h2 className="text-xl font-bold">More guides</h2>
            <ul className="mt-3 space-y-2">
              {more.map((m) => (
                <li key={m.slug}>
                  <Link href={`/blog/${m.slug}`} className="text-[#0f62fe] hover:underline text-lg">{m.title}</Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </PageShell>
  );
}

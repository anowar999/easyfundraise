import { readFile } from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/landing/PageShell";
import { Markdown } from "@/lib/markdown";

const DOCS: Record<string, { file: string; title: string }> = {
  privacy: { file: "privacy-policy.md", title: "Privacy Policy" },
  terms: { file: "terms.md", title: "Terms and Conditions" },
  cookies: { file: "cookie-policy.md", title: "Cookie Policy" },
  "data-sources": { file: "data-sources-and-investor-rights.md", title: "Data Sources and Investor Rights" },
};

export function generateStaticParams() {
  return Object.keys(DOCS).map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return { title: DOCS[slug]?.title ?? "Legal", alternates: { canonical: `/legal/${slug}` } };
}

export default async function Legal({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = DOCS[slug];
  if (!doc) notFound();
  const source = (await readFile(path.join(process.cwd(), "content/legal", doc.file), "utf8")).replace(/^# .*\n+/, "");
  return (
    <PageShell eyebrow="Legal" title={doc.title}>
      <article className="mx-auto max-w-3xl px-4 md:px-6 py-12 text-[16px] text-[#1c2740] [&_a]:!text-[#0f62fe]">
        <Markdown source={source} />
      </article>
    </PageShell>
  );
}

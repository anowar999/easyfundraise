import { readFile } from "node:fs/promises";
import path from "node:path";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Markdown } from "@/lib/markdown";

const DOCS: Record<string, { file: string; title: string }> = {
  privacy: { file: "privacy-policy.md", title: "Privacy Policy" },
  terms: { file: "terms.md", title: "Terms & Conditions" },
  "data-sources": { file: "data-sources-and-investor-rights.md", title: "Data Sources & Investor Rights" },
};

export function generateStaticParams() {
  return Object.keys(DOCS).map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return { title: DOCS[slug]?.title ?? "Legal" };
}

export default async function Legal({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = DOCS[slug];
  if (!doc) notFound();
  const source = await readFile(path.join(process.cwd(), "content/legal", doc.file), "utf8");
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Link href="/" className="text-sm text-brand">← EasyFundraise</Link>
      <article className="mt-6 text-[15px]">
        <Markdown source={source} />
      </article>
    </div>
  );
}

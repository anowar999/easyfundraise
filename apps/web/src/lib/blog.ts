import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

export type Post = { slug: string; title: string; description: string; date: string; body: string };
const DIR = path.join(process.cwd(), "content/blog");

function parse(slug: string, raw: string): Post {
  const m = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(raw);
  const meta: Record<string, string> = {};
  for (const line of (m?.[1] ?? "").split("\n")) {
    const i = line.indexOf(":");
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^"(.*)"$/, "$1");
  }
  return { slug, title: meta.title ?? slug, description: meta.description ?? "", date: meta.date ?? "", body: (m?.[2] ?? raw).trim() };
}

export async function allPosts(): Promise<Post[]> {
  const files = (await readdir(DIR)).filter((f) => f.endsWith(".md"));
  const posts = await Promise.all(files.map(async (f) => parse(f.replace(/\.md$/, ""), await readFile(path.join(DIR, f), "utf8"))));
  return posts.sort((a, b) => b.date.localeCompare(a.date));
}

export async function getPost(slug: string): Promise<Post | null> {
  if (!/^[a-z0-9-]+$/.test(slug)) return null;
  try {
    return parse(slug, await readFile(path.join(DIR, `${slug}.md`), "utf8"));
  } catch {
    return null;
  }
}

export const readingTime = (body: string) => Math.max(2, Math.round(body.split(/\s+/).length / 220));

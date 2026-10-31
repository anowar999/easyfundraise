import type { ReactNode } from "react";

/** Minimal Markdown renderer for our own legal pages and blog posts (headings, paragraphs, lists, bold, links). */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\[(.+?)\]\((.+?)\)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(<strong key={m.index}>{m[1]}</strong>);
    else out.push(<a key={m.index} href={m[3]} className="text-brand underline">{m[2]}</a>);
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

export function Markdown({ source }: { source: string }) {
  const blocks = source.split(/\n{2,}/);
  return (
    <>
      {blocks.map((b, i) => {
        const t = b.trim();
        if (!t) return null;
        const h = /^(#{1,3})\s+(.*)$/.exec(t);
        if (h) {
          const cls = ["text-3xl font-bold mt-2", "text-xl font-semibold mt-8", "text-lg font-semibold mt-6"][h[1].length - 1];
          const Tag = (["h1", "h2", "h3"] as const)[h[1].length - 1];
          return <Tag key={i} className={cls}>{inline(h[2])}</Tag>;
        }
        if (/^[-*]\s/.test(t))
          return (
            <ul key={i} className="list-disc pl-6 space-y-1 mt-3">
              {t.split("\n").map((l, j) => <li key={j}>{inline(l.replace(/^[-*]\s+/, ""))}</li>)}
            </ul>
          );
        if (/^\d+\.\s/.test(t))
          return (
            <ol key={i} className="list-decimal pl-6 space-y-1 mt-3">
              {t.split("\n").map((l, j) => <li key={j}>{inline(l.replace(/^\d+\.\s+/, ""))}</li>)}
            </ol>
          );
        return <p key={i} className="mt-3 leading-relaxed">{inline(t.replace(/\n/g, " "))}</p>;
      })}
    </>
  );
}

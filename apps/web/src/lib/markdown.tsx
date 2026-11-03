import type { ReactNode } from "react";

/** Minimal Markdown renderer for our own legal pages and blog posts (headings, paragraphs, lists, bold, links). */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\[(.+?)\]\((.+?)\)|`([^`]+)`/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(<strong key={m.index}>{m[1]}</strong>);
    else if (m[4]) out.push(<code key={m.index} className="rounded bg-surface px-1 text-[0.9em]">{m[4]}</code>);
    else if (!/^(https?:\/\/|\/|mailto:)/.test(m[3])) out.push(m[2]);
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

/** Chat answers from the agents: bold, `code`, links, bullet and numbered lists and line breaks, sized for a reply
 *  bubble. Plain text in, React out (no raw HTML is ever rendered). */
export function ChatMarkdown({ source, className = "" }: { source: string; className?: string }) {
  const out: ReactNode[] = [];
  const lines = source.replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) {
      i++;
      continue;
    }
    const bullet = /^\s*[-*•]\s+/;
    const num = /^\s*\d+[.)]\s+/;
    if (bullet.test(l) || num.test(l)) {
      const re = bullet.test(l) ? bullet : num;
      const items: string[] = [];
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ""));
      const Tag = re === bullet ? "ul" : "ol";
      out.push(
        <Tag key={i} className={`${re === bullet ? "list-disc" : "list-decimal"} pl-5 space-y-1`}>
          {items.map((t, j) => <li key={j}>{inline(t)}</li>)}
        </Tag>,
      );
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !bullet.test(lines[i]) && !num.test(lines[i])) para.push(lines[i++]);
    const h = /^#{1,4}\s+(.*)$/.exec(para[0]);
    if (h && para.length === 1) {
      out.push(<p key={i} className="font-semibold">{inline(h[1])}</p>);
      continue;
    }
    out.push(
      <p key={i}>
        {para.map((t, j) => (
          <span key={j}>
            {j > 0 && <br />}
            {inline(t)}
          </span>
        ))}
      </p>,
    );
  }
  return <div className={`space-y-2 break-words ${className}`}>{out}</div>;
}

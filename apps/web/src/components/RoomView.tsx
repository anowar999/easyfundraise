"use client";

import { Download, ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";

export type RoomSection = {
  id: string;
  type: "problem" | "solution" | "product" | "traction" | "market" | "why_now" | "business_model" | "team" | "ask" | "use_of_funds" | "faq" | "text";
  title: string;
  body?: string;
  metrics?: { label: string; value: string }[];
  people?: { name: string; role: string; link?: string }[];
  items?: { label?: string; pct?: string; q?: string; a?: string }[];
  links?: { label: string; url: string }[];
};
export type RoomContent = { layout?: number; hero: { title: string; one_liner?: string; round?: string; instrument?: string; cta_label?: string; cta_url?: string }; sections: RoomSection[] };
type Doc = { id: string; label: string; filename: string; size: number };

const safeUrl = (u?: string) => (u && /^(https?:|mailto:)/i.test(u) ? u : undefined);

/** A YouTube, Vimeo or Loom link becomes a player; anything else stays a link. */
export function embedUrl(u: string): string | null {
  try {
    const url = new URL(u);
    const host = url.hostname.replace(/^www\./, "");
    if (host === "youtu.be") return `https://www.youtube-nocookie.com/embed/${url.pathname.slice(1)}`;
    if (host.endsWith("youtube.com")) {
      const id = url.searchParams.get("v") || url.pathname.match(/\/(?:embed|shorts)\/([\w-]+)/)?.[1];
      return id ? `https://www.youtube-nocookie.com/embed/${id}` : null;
    }
    if (host === "vimeo.com") {
      const id = url.pathname.match(/\/(\d+)/)?.[1];
      return id ? `https://player.vimeo.com/video/${id}` : null;
    }
    if (host === "loom.com") {
      const id = url.pathname.match(/\/(?:share|embed)\/(\w+)/)?.[1];
      return id ? `https://www.loom.com/embed/${id}` : null;
    }
  } catch {}
  return null;
}

function ProductLinks({ links }: { links: { label: string; url: string }[] }) {
  const ok = links.filter((l) => safeUrl(l.url));
  const video = ok.map((l) => embedUrl(l.url)).find(Boolean);
  return (
    <div className="mt-4 space-y-3">
      {video && (
        <div className="aspect-video overflow-hidden rounded-xl border border-line bg-black">
          <iframe src={video} title="Product video" className="h-full w-full" allow="fullscreen; picture-in-picture" allowFullScreen loading="lazy" />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {ok.map((l) => (
          <a key={l.url} href={l.url} target="_blank" rel="noreferrer nofollow" className="btn-ghost btn-sm">
            {l.label || "Open"} <ExternalLink size={14} />
          </a>
        ))}
      </div>
    </div>
  );
}

function Section({ s }: { s: RoomSection }) {
  return (
    <section data-section={s.id} className="py-8 border-t border-line">
      <h2 className="text-lg md:text-xl font-semibold mb-3">{s.title}</h2>
      {s.body && <p className="whitespace-pre-wrap leading-relaxed text-[15px]">{s.body}</p>}
      {s.type === "product" && !!s.links?.length && <ProductLinks links={s.links} />}
      {["traction", "market", "ask"].includes(s.type) && !!s.metrics?.some((m) => m.label && m.value) && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
          {s.metrics!.filter((m) => m.label && m.value).map((m) => (
            <div key={m.label} className="rounded-xl border border-line p-4">
              <div className="text-2xl font-bold">{m.value}</div>
              <div className="text-xs text-muted">{m.label}</div>
            </div>
          ))}
        </div>
      )}
      {s.type === "team" && !!s.people?.length && (
        <div className="grid sm:grid-cols-2 gap-3 mt-4">
          {s.people.filter((p) => p.name).map((p) => (
            <div key={p.name} className="rounded-xl border border-line p-4">
              <div className="font-semibold">{safeUrl(p.link) ? <a href={safeUrl(p.link)} target="_blank" rel="noreferrer nofollow" className="text-brand">{p.name}</a> : p.name}</div>
              <div className="text-sm text-muted">{p.role}</div>
            </div>
          ))}
        </div>
      )}
      {s.type === "use_of_funds" && !!s.items?.length && (
        <div className="space-y-2 mt-4">
          {s.items.filter((i) => i.label).map((i) => (
            <div key={i.label}>
              <div className="flex justify-between text-sm">
                <span>{i.label}</span>
                <span className="font-mono">{i.pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-surface overflow-hidden">
                <div className="h-full bg-brand" style={{ width: `${Math.min(100, Number(i.pct) || 0)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
      {s.type === "faq" && (
        <div className="space-y-2">
          {s.items?.filter((i) => i.q).map((i) => (
            <details key={i.q} className="rounded-xl border border-line p-4">
              <summary className="font-medium cursor-pointer">{i.q}</summary>
              <p className="mt-2 text-sm whitespace-pre-wrap">{i.a}</p>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}

/** DR-01 page, with DR-03 per-section time tracking when onPing is given. */
export function RoomView({ content, docs = [], docHref, onPing }: { content: RoomContent; docs?: Doc[]; docHref?: (d: Doc) => string; onPing?: (seconds: number, sections: Record<string, number>) => void }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!onPing || !root.current) return;
    const visible = new Set<string>();
    const acc: Record<string, number> = {};
    let secs = 0;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => {
        const id = (e.target as HTMLElement).dataset.section!;
        if (e.isIntersecting) visible.add(id);
        else visible.delete(id);
      }),
      { threshold: 0.4 },
    );
    root.current.querySelectorAll("[data-section]").forEach((el) => io.observe(el));
    const tick = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      secs += 1;
      visible.forEach((id) => (acc[id] = (acc[id] ?? 0) + 1));
    }, 1000);
    const flush = () => {
      if (secs === 0) return;
      onPing(secs, { ...acc });
      secs = 0;
      Object.keys(acc).forEach((k) => delete acc[k]);
    };
    const every = setInterval(flush, 15000);
    const hide = () => document.visibilityState === "hidden" && flush();
    document.addEventListener("visibilitychange", hide);
    return () => {
      flush();
      io.disconnect();
      clearInterval(tick);
      clearInterval(every);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [onPing]);
  const h = content.hero;
  return (
    <div ref={root} className="max-w-3xl mx-auto px-4 md:px-6">
      <header data-section="hero" className="py-10 md:py-16">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight">{h.title}</h1>
        {h.one_liner && <p className="text-lg text-muted mt-2">{h.one_liner}</p>}
        {(h.round || h.instrument) && (
          <p className="mt-4 text-sm">
            Raising <b>{h.round}</b>
            {h.instrument && ` on a ${h.instrument}`}
          </p>
        )}
        {safeUrl(h.cta_url) && (
          <a href={safeUrl(h.cta_url)} target="_blank" rel="noreferrer" className="btn-primary mt-5 inline-flex">
            {h.cta_label || "Get in touch"}
          </a>
        )}
      </header>
      {content.sections.filter((s) => s.body || s.metrics?.some((m) => m.value) || s.people?.length || s.items?.length || s.links?.length).map((s) => <Section key={s.id} s={s} />)}
      {docs.length > 0 && (
        <section data-section="documents" className="py-8 border-t border-line">
          <h2 className="text-lg md:text-xl font-semibold mb-3">Documents</h2>
          <div className="space-y-2">
            {docs.map((d) => (
              <a key={d.id} href={docHref?.(d)} className="flex items-center gap-3 rounded-xl border border-line p-3 hover:bg-surface">
                <Download size={16} className="text-brand" />
                <span className="flex-1">{d.label}</span>
                <span className="text-xs text-muted">{(d.size / 1024 / 1024).toFixed(1)} MB</span>
              </a>
            ))}
          </div>
        </section>
      )}
      <footer className="py-10 text-xs text-muted text-center">Made with EasyFundraise</footer>
    </div>
  );
}

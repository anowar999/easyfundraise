import type { Metadata } from "next";
import type { ReactNode } from "react";

const API = process.env.API_URL ?? "http://localhost:8000";

/** DR-05: data rooms are noindex unless the founder opts in and the room is public. */
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  try {
    const r = await fetch(`${API}/public/rooms/${encodeURIComponent(slug)}/meta`, { cache: "no-store" });
    if (r.ok) {
      const m = await r.json();
      return { title: m.title || "Data room", description: m.one_liner || undefined, robots: m.indexable ? undefined : { index: false, follow: false } };
    }
  } catch {}
  return { title: "Data room", robots: { index: false, follow: false } };
}

export default function RoomLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-dvh bg-card text-ink">{children}</div>;
}

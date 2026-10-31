import type { ReactNode } from "react";
import { Footer } from "./Footer";
import { Header } from "./Header";

/** Public marketing page: dark title band under the fixed header, light content, shared footer. */
export function PageShell({ eyebrow, title, intro, children, crumbs }: { eyebrow?: string; title: ReactNode; intro?: ReactNode; children: ReactNode; crumbs?: ReactNode }) {
  return (
    <div className="lp min-h-dvh overflow-x-clip">
      <Header />
      <section className="lp-hero-bg relative text-white pt-28 md:pt-36 pb-14 md:pb-20 overflow-hidden">
        <div className="lp-grid absolute inset-0 pointer-events-none" />
        <div className="relative mx-auto max-w-5xl px-4 md:px-6">
          {crumbs && <div className="text-sm text-white/55 mb-4">{crumbs}</div>}
          {eyebrow && <div className="text-sm font-semibold text-[#8ab8ff] uppercase tracking-[0.14em]">{eyebrow}</div>}
          <h1 className="mt-2 text-4xl md:text-6xl font-extrabold tracking-tight leading-[1.05]">{title}</h1>
          {intro && <div className="mt-5 max-w-3xl text-lg md:text-xl text-white/75 leading-relaxed">{intro}</div>}
        </div>
      </section>
      <main>{children}</main>
      <Footer />
    </div>
  );
}

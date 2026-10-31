"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LogoMark } from "./LogoMark";

const LINKS = [
  ["/#investor-database", "Investor database"],
  ["/#cold-email", "Cold email"],
  ["/#crm", "Fundraising CRM"],
  ["/investors", "Investor lists"],
  ["/blog", "Blog"],
];

export function Header() {
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setSolid(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${solid || open ? "bg-[#070b1a]/85 backdrop-blur-xl border-b border-white/10" : "bg-transparent"}`}>
      <div className="mx-auto max-w-7xl px-4 md:px-6 h-16 md:h-[72px] flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5" aria-label="EasyFundraise home">
          <LogoMark />
          <span className="text-lg md:text-xl font-bold tracking-tight text-white">
            Easy<span className="text-[#7cb4ff]">Fundraise</span>
          </span>
        </Link>
        <nav className="hidden lg:flex items-center gap-7 text-[15px] text-white/75" aria-label="Main">
          {LINKS.map(([h, l]) => (
            <a key={h} href={h} className="hover:text-white transition-colors">
              {l}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/login" className="hidden sm:inline-flex h-10 items-center px-4 text-[15px] font-medium text-white/85 hover:text-white">
            Sign in
          </Link>
          <Link href="/login?mode=signup" className="lp-btn-primary h-10 px-4 text-[15px]">
            Start free
          </Link>
          <button className="lg:hidden p-2 text-white" onClick={() => setOpen(!open)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>
      {open && (
        <nav className="lg:hidden px-4 pb-4 flex flex-col text-white/85" aria-label="Mobile">
          {LINKS.map(([h, l]) => (
            <a key={h} href={h} onClick={() => setOpen(false)} className="py-3 border-b border-white/10 text-base">
              {l}
            </a>
          ))}
          <Link href="/login" className="py-3 text-base">
            Sign in
          </Link>
        </nav>
      )}
    </header>
  );
}

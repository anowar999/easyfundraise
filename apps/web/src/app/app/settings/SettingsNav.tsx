"use client";

import clsx from "clsx";
import { Bell, Bot, Brain, Building2, CreditCard, KeyRound, Laptop, Layers, Mail, PenLine, Send, ShieldOff, Target, Users } from "lucide-react";
import { useEffect, useState } from "react";

export const SECTIONS = [
  { id: "company", label: "Company profile", icon: Building2 },
  { id: "agent", label: "Agent instructions", icon: Bot },
  { id: "exclusions", label: "Exclusion list", icon: ShieldOff },
  { id: "account", label: "Signature & timezone", icon: PenLine },
  { id: "gmail", label: "Gmail", icon: Mail },
  { id: "outreach", label: "Sending & automations", icon: Send },
  { id: "positioning", label: "Positioning advice", icon: Target },
  { id: "memory", label: "Agent memory", icon: Brain },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "team", label: "Team", icon: Users },
  { id: "workspaces", label: "Workspaces", icon: Layers },
  { id: "signin", label: "Sign-in & password", icon: KeyRound },
  { id: "devices", label: "Signed-in devices", icon: Laptop },
  { id: "plan", label: "Plan & usage", icon: CreditCard },
];

/** Jump links for the long Settings page: a sticky list on the right on desktop, a scrollable chip row on phones.
 *  Highlights the section you're reading. */
export function SettingsNav({ variant }: { variant: "side" | "chips" }) {
  const [active, setActive] = useState(SECTIONS[0].id);
  useEffect(() => {
    // The section you're reading is the last one whose top has scrolled past the top of the screen.
    const onScroll = () => {
      let cur = SECTIONS[0].id;
      for (const sec of SECTIONS) {
        const el = document.getElementById(sec.id);
        if (el && el.getBoundingClientRect().top <= 140) cur = sec.id;
      }
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) cur = SECTIONS[SECTIONS.length - 1].id;
      setActive(cur);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const go = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    history.replaceState(null, "", `#${id}`);
  };

  if (variant === "chips")
    return (
      <nav aria-label="Settings sections" className="lg:hidden sticky top-14 md:top-0 z-20 -mx-4 px-4 py-2 mb-3 bg-surface/95 backdrop-blur border-b border-line">
        <div className="flex gap-1.5 overflow-x-auto scrollbar-none">
          {SECTIONS.map((s) => (
            <a key={s.id} href={`#${s.id}`} onClick={go(s.id)} className={clsx("chip whitespace-nowrap px-3 py-1.5 text-sm", active === s.id ? "bg-ink text-surface border-ink" : "bg-card")}>
              {s.label}
            </a>
          ))}
        </div>
      </nav>
    );
  return (
    <nav aria-label="Settings sections" className="hidden lg:block sticky top-6 self-start">
      <div className="card p-2">
        <div className="px-2.5 pt-1.5 pb-2 text-xs font-semibold uppercase tracking-wide text-muted">Jump to</div>
        <ul className="space-y-0.5">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                onClick={go(s.id)}
                aria-current={active === s.id ? "true" : undefined}
                className={clsx("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors", active === s.id ? "bg-brand/10 text-brand font-medium" : "text-ink/80 hover:bg-surface")}
              >
                <s.icon size={16} className={active === s.id ? "text-brand" : "text-muted"} /> {s.label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

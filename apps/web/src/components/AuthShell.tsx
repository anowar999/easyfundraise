import Link from "next/link";
import { Check } from "lucide-react";
import { LogoMark } from "@/components/landing/LogoMark";

const POINTS = [
  "14,900+ angels and VCs, ranked by fit for your round",
  "Personal cold emails sent from your own Gmail",
  "A funnel that tracks every investor until the money lands",
];

/** Full-page split layout for sign-in and onboarding: brand story on the left, the form on the right. */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="lp min-h-dvh grid lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative overflow-hidden lp-hero-bg text-white px-6 pt-6 pb-8 lg:px-14 lg:py-12 flex flex-col lg:sticky lg:top-0 lg:h-dvh">
        <div className="absolute inset-0 lp-grid pointer-events-none" />
        <Link href="/" className="relative flex items-center gap-2.5 w-fit">
          <LogoMark size={36} />
          <span className="text-xl font-bold tracking-tight">
            Easy<span className="text-[#7cb4ff]">Fundraise</span>
          </span>
        </Link>
        <div className="relative hidden lg:block mt-auto pt-10">
          <h2 className="text-4xl xl:text-5xl font-bold tracking-tight leading-[1.08] max-w-xl">
            Your personal <span className="lp-gradient-text">fundraising agent</span>
          </h2>
          <ul className="mt-8 space-y-3.5 text-lg text-white/80">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3">
                <span className="mt-1 grid place-items-center w-5 h-5 rounded-full bg-[#19c3a6]/20 text-[#6ee7c8] shrink-0">
                  <Check size={13} strokeWidth={3} />
                </span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative hidden lg:block mt-10 -mr-24 xl:-mr-32 max-h-[34vh] overflow-hidden rounded-xl [mask-image:linear-gradient(to_bottom,#000_70%,transparent)]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/screens/d-funnel.webp" alt="EasyFundraise fundraising funnel" className="rounded-xl ring-1 ring-white/15 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)]" />
        </div>
        <p className="relative hidden lg:block mt-8 text-sm text-white/50">For founders raising angel, pre-seed and seed rounds.</p>
      </aside>
      <main className="flex flex-col px-5 py-10 sm:px-10 lg:px-16 lg:py-12 bg-white">
        <div className="w-full max-w-[440px] m-auto">{children}</div>
        <p className="mt-10 text-center text-xs text-[#7a849a]">
          <Link href="/legal/privacy" className="hover:underline">Privacy</Link> · <Link href="/legal/terms" className="hover:underline">Terms</Link> · <Link href="/legal/cookies" className="hover:underline">Cookies</Link>
        </p>
      </main>
    </div>
  );
}

export const GoogleG = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
    <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
    <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
    <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
  </svg>
);

export const GmailIcon = ({ size = 22 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
    <path fill="#4caf50" d="M45 16.2l-5 2.75-5 4.75V40h7a3 3 0 0 0 3-3V16.2z" />
    <path fill="#1e88e5" d="M3 16.2l3.6 1.7L13 23.7V40H6a3 3 0 0 1-3-3V16.2z" />
    <path fill="#e53935" d="M35 11.2L24 19.45 13 11.2 12 17l1 6.7 11 8.25 11-8.25 1-6.7z" />
    <path fill="#c62828" d="M3 12.3v3.9l10 7.5V11.2L9.9 8.9A4.3 4.3 0 0 0 3 12.3z" />
    <path fill="#fbc02d" d="M45 12.3v3.9l-10 7.5V11.2l3.1-2.3A4.3 4.3 0 0 1 45 12.3z" />
  </svg>
);

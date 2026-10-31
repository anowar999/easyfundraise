"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Check, Inbox, Lock, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { AuthShell, GmailIcon } from "@/components/AuthShell";

const WHY = [
  { icon: Inbox, t: "Sent from you, replies land in your inbox", d: "Investors see a personal email from your address, not a mailing tool." },
  { icon: Check, t: "You approve every email first", d: "Nothing goes out until you review it and confirm." },
  { icon: ShieldCheck, t: "Follow-ups stop the moment they reply", d: "We read replies to investor threads only, to stop follow-ups and update your investor tracker." },
];

function WelcomeInner() {
  const params = useSearchParams();
  const raw = params.get("next") || "/app";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/app";
  const [me, setMe] = useState<{ email: string } | null>(null);

  useEffect(() => {
    api("/auth/me").then(setMe).catch(() => (location.href = `/login?next=${encodeURIComponent(next)}`));
  }, [next]);

  return (
    <AuthShell>
      <p className="text-sm font-semibold uppercase tracking-wider text-[#0f62fe]">Step 2 of 3</p>
      <h1 className="mt-2 text-3xl md:text-[34px] font-bold tracking-tight text-[#0b1220]">
        You&apos;re in. Now connect your Gmail
      </h1>
      <p className="mt-2 text-[16px] text-[#4a5670]">
        So your agent can send personal investor emails from <strong className="text-[#0b1220]">{me?.email ?? "your address"}</strong>.
      </p>

      <ul className="mt-8 space-y-5">
        {WHY.map(({ icon: I, t, d }) => (
          <li key={t} className="flex gap-4">
            <span className="grid place-items-center w-10 h-10 rounded-xl bg-[#eef4ff] text-[#0f62fe] shrink-0">
              <I size={20} />
            </span>
            <span>
              <span className="block font-semibold text-[#0b1220]">{t}</span>
              <span className="text-sm text-[#4a5670]">{d}</span>
            </span>
          </li>
        ))}
      </ul>

      <a
        href={`/api/gmail/connect?${new URLSearchParams({ next })}`}
        className="mt-9 flex py-3.5 w-full items-center justify-center gap-3 rounded-full bg-[#0f62fe] text-[16px] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(15,98,254,0.9)] hover:bg-[#2b74ff] transition"
      >
        <span className="grid place-items-center w-7 h-7 rounded-full bg-white">
          <GmailIcon size={18} />
        </span>
        Connect Gmail
      </a>
      <p className="mt-3 flex items-center justify-center gap-1.5 text-[13px] text-[#0f7a5f]">
        <Lock size={13} /> Tokens are encrypted. Disconnect any time in Settings.
      </p>
      <a href={next} className="mt-6 flex items-center justify-center gap-1 text-sm font-medium text-[#4a5670] hover:text-[#0b1220]">
        Skip for now, I&apos;ll browse investors first <ArrowRight size={15} />
      </a>
    </AuthShell>
  );
}

export default function Welcome() {
  return (
    <Suspense>
      <WelcomeInner />
    </Suspense>
  );
}

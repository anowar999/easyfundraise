"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Eye, EyeOff, Info, KeyRound, Lock, Mail, MailCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { AuthShell, GoogleG } from "@/components/AuthShell";

type Cfg = { google: boolean; dev_login: boolean; email_link: boolean; gmail_fake: boolean };

const ERRORS: Record<string, string> = {
  cancelled: "Google sign-in was cancelled. You can try again.",
  expired: "That sign-in link has expired or was already replaced. Enter your email for a new one.",
};

const problem = (e: unknown, fallback: string) =>
  e instanceof ApiError ? e.problem.title + (e.problem.detail ? `. ${e.problem.detail}` : "") : fallback;

function LoginInner() {
  const params = useSearchParams();
  const raw = params.get("next") || "/app";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/app";
  const signup = params.get("mode") === "signup";
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [gmail, setGmail] = useState(true);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{ email: string; devLink?: string } | null>(null);
  const [err, setErr] = useState(ERRORS[params.get("error") ?? ""] ?? "");
  const [usePw, setUsePw] = useState(false);
  const [pw, setPw] = useState("");
  const [showPw, setShowPw] = useState(false);

  useEffect(() => {
    api<Cfg>("/auth/config").then(setCfg).catch(() => setCfg({ google: false, dev_login: false, email_link: false, gmail_fake: false }));
  }, []);

  const pwMode = usePw || cfg?.email_link === false;
  const googleHref = `/api/auth/google/start?${new URLSearchParams({ gmail: gmail ? "1" : "0", next })}`;

  const pwLogin = async () => {
    setBusy(true);
    try {
      const r = await api<{ next: string }>("/auth/password/login", { method: "POST", json: { email, password: pw, next } });
      location.href = r.next || next;
    } catch (e) {
      setErr(problem(e, "Sign-in failed. Please try again."));
      setBusy(false);
    }
  };

  const sendLink = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (pwMode) return pwLogin();
    setBusy(true);
    try {
      const r = await api<{ sent: boolean; dev_link?: string }>("/auth/email/start", { method: "POST", json: { email, next } });
      setSent({ email, devLink: r.dev_link });
    } catch (e) {
      setErr(problem(e, "We couldn't send the link. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const devLogin = async () => {
    setErr("");
    try {
      const r = await api<{ next: string }>("/auth/dev-login", { method: "POST", json: { email, next, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone } });
      location.href = r.next || next;
    } catch (e) {
      setErr(problem(e, "Sign-in failed"));
    }
  };

  if (sent) {
    return (
      <AuthShell>
        <div className="grid place-items-center w-14 h-14 rounded-2xl bg-[#eef4ff] text-[#0f62fe]">
          <MailCheck size={28} />
        </div>
        <h1 className="mt-6 text-3xl font-bold tracking-tight text-[#0b1220]">Check your inbox</h1>
        <p className="mt-3 text-[16px] leading-relaxed text-[#4a5670]">
          We sent a sign-in link to <strong className="text-[#0b1220]">{sent.email}</strong>. It works for 15 minutes. Open it on this device to continue.
        </p>
        {sent.devLink && (
          <div className="mt-6 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-medium">Email isn&apos;t set up on this server yet (development).</p>
            <a href={sent.devLink} className="mt-3 inline-flex items-center gap-1.5 font-semibold text-[#0f62fe] hover:underline">
              Open the sign-in link <ArrowRight size={15} />
            </a>
          </div>
        )}
        <button onClick={() => setSent(null)} className="mt-8 text-sm font-medium text-[#0f62fe] hover:underline">
          Use a different email
        </button>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <h1 className="text-3xl md:text-[34px] font-bold tracking-tight text-[#0b1220]">{signup ? "Start your free trial" : "Welcome back"}</h1>
      <p className="mt-2 text-[16px] text-[#4a5670]">
        {signup ? "14 days free, no credit card. Set up in two minutes." : "Sign in to keep your raise moving."}
      </p>

      {err && (
        <p role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {err}
        </p>
      )}

      <a
        href={cfg?.google ? googleHref : undefined}
        aria-disabled={!cfg?.google}
        className={`mt-8 flex h-13 py-3.5 w-full items-center justify-center gap-3 rounded-full border border-[#d5dbe6] bg-white text-[16px] font-semibold text-[#0b1220] shadow-sm transition ${cfg?.google ? "hover:border-[#b6c0d1] hover:shadow-md" : "opacity-50 cursor-not-allowed"}`}
      >
        <GoogleG /> Continue with Google
      </a>
      {cfg && !cfg.google && <p className="mt-2 text-xs text-[#7a849a]">Google sign-in isn&apos;t configured on this server yet.</p>}

      <label className="mt-4 flex gap-3 rounded-2xl border border-[#e6ebf3] bg-[#f7f9fc] p-4 cursor-pointer has-[:checked]:border-[#bcd3ff] has-[:checked]:bg-[#f2f7ff]">
        <input type="checkbox" checked={gmail} onChange={(e) => setGmail(e.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-[#0f62fe]" />
        <span className="text-sm leading-relaxed text-[#4a5670]">
          <span className="block text-[15px] font-semibold text-[#0b1220]">Also connect my Gmail to send investor emails</span>
          Google will ask you to let EasyFundraise <strong className="font-medium text-[#1c2740]">send email</strong> on your behalf and <strong className="font-medium text-[#1c2740]">read replies</strong> so follow-ups stop when an investor answers.
          <span className="mt-2 flex items-center gap-1.5 text-[13px] text-[#0f7a5f]">
            <Lock size={13} /> Nothing is ever sent without your approval. Disconnect any time.
          </span>
        </span>
      </label>

      {cfg && (
        <>
          <div className="my-7 flex items-center gap-4 text-xs font-medium uppercase tracking-wider text-[#9aa3b5]">
            <span className="h-px flex-1 bg-[#e6ebf3]" /> or <span className="h-px flex-1 bg-[#e6ebf3]" />
          </div>
          <form onSubmit={sendLink} className="space-y-3">
            <label htmlFor="email" className="block text-sm font-medium text-[#1c2740]">
              Work email
            </label>
            <div className="relative">
              <Mail size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#9aa3b5]" />
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="you@company.com"
                className="h-13 py-3.5 w-full rounded-full border border-[#d5dbe6] bg-white pl-11 pr-4 text-[16px] text-[#0b1220] placeholder:text-[#9aa3b5] outline-none focus:border-[#0f62fe] focus:ring-4 focus:ring-[#0f62fe]/15"
              />
            </div>
            {pwMode && (
              <>
                <div className="flex items-baseline justify-between">
                  <label htmlFor="password" className="block text-sm font-medium text-[#1c2740]">
                    Password
                  </label>
                  {cfg.email_link && (
                    <button type="button" className="text-xs font-medium text-[#0f62fe] hover:underline" onClick={() => { setUsePw(false); setErr(""); }}>
                      Forgot it? Email me a link
                    </button>
                  )}
                </div>
                <div className="relative">
                  <KeyRound size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#9aa3b5]" />
                  <input
                    id="password"
                    type={showPw ? "text" : "password"}
                    required
                    value={pw}
                    onChange={(e) => setPw(e.target.value)}
                    autoComplete="current-password"
                    className="h-13 py-3.5 w-full rounded-full border border-[#d5dbe6] bg-white pl-11 pr-12 text-[16px] text-[#0b1220] outline-none focus:border-[#0f62fe] focus:ring-4 focus:ring-[#0f62fe]/15"
                  />
                  <button type="button" onClick={() => setShowPw(!showPw)} aria-label={showPw ? "Hide password" : "Show password"} className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 text-[#7a849a] hover:text-[#1c2740]">
                    {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </>
            )}
            <button disabled={busy} className="lp-btn-primary w-full py-3.5 text-[16px] disabled:opacity-60">
              {pwMode ? (busy ? "Signing in…" : "Sign in") : busy ? "Sending…" : "Continue with email"} <ArrowRight size={18} />
            </button>
            {pwMode ? (
              <p className="flex gap-1.5 text-xs text-[#7a849a]">
                <Info size={14} className="shrink-0 mt-px" /> Signed up with Google? Add a password in Settings, then use it here. Your Gmail stays connected.
              </p>
            ) : (
              <div className="flex flex-wrap items-start justify-between gap-2 text-xs text-[#7a849a]">
                <p className="flex gap-1.5">
                  <Info size={14} className="shrink-0 mt-px" /> We&apos;ll email you a magic link. No password needed.
                </p>
                {!signup && (
                  <button type="button" className="font-medium text-[#0f62fe] hover:underline" onClick={() => { setUsePw(true); setErr(""); }}>
                    Use a password instead
                  </button>
                )}
              </div>
            )}
          </form>
        </>
      )}

      {cfg?.dev_login && (
        <button type="button" onClick={devLogin} disabled={!email} className="mt-4 w-full text-center text-xs text-[#9aa3b5] hover:text-[#4a5670] disabled:opacity-50">
          Developer: sign in instantly as this email
        </button>
      )}

      <p className="mt-8 text-center text-[15px] text-[#4a5670]">
        {signup ? "Already have an account? " : "New to EasyFundraise? "}
        <Link href={`/login?${new URLSearchParams({ ...(signup ? {} : { mode: "signup" }), next })}`} className="font-semibold text-[#0f62fe] hover:underline">
          {signup ? "Sign in" : "Start free trial"}
        </Link>
      </p>
      <p className="mt-6 text-center text-xs leading-relaxed text-[#7a849a]">
        By continuing you agree to our <Link className="underline" href="/legal/terms">Terms</Link> and <Link className="underline" href="/legal/privacy">Privacy Policy</Link>.
        EasyFundraise&apos;s use of Google data follows the Google API Services User Data Policy, including the Limited Use requirements.
      </p>
    </AuthShell>
  );
}

export default function Login() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}

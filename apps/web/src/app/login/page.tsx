"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";

function LoginInner() {
  const params = useSearchParams();
  const next = params.get("next") || "/app";
  const [cfg, setCfg] = useState<{ google: boolean; dev_login: boolean } | null>(null);
  const [email, setEmail] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api("/auth/config").then(setCfg).catch(() => setCfg({ google: false, dev_login: false }));
  }, []);

  const devLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      await api("/auth/dev-login", { method: "POST", json: { email, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone } });
      location.href = next.startsWith("/") ? next : "/app";
    } catch (e) {
      setErr(e instanceof ApiError ? e.problem.title + (e.problem.detail ? `: ${e.problem.detail}` : "") : "Sign-in failed");
    }
  };

  return (
    <div className="min-h-dvh grid place-items-center px-4">
      <div className="w-full max-w-sm card p-6">
        <div className="flex items-center gap-2 mb-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icon.svg" alt="" className="w-9 h-9" />
          <span className="text-lg font-bold">
            Easy<span className="text-brand">Fundraise</span>
          </span>
        </div>
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="text-sm text-muted mt-1">Use the Google account you raise from. We only ask for your name and email now.</p>
        {cfg?.google && (
          <a href="/api/auth/google/start" className="btn-primary w-full mt-6 h-11">
            Continue with Google
          </a>
        )}
        {cfg?.dev_login && (
          <form onSubmit={devLogin} className="mt-6 space-y-3">
            <div className="text-xs text-muted rounded-md bg-amber-500/10 border border-amber-500/30 p-2">
              Development sign-in (no password). Disabled in production.
            </div>
            <input className="input" type="email" required placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            <button className="btn-ghost w-full">Sign in with email (dev)</button>
          </form>
        )}
        {cfg && !cfg.google && !cfg.dev_login && <p className="mt-6 text-sm text-danger">Sign-in is not configured.</p>}
        {err && <p className="mt-3 text-sm text-danger" role="alert">{err}</p>}
        <p className="mt-6 text-xs text-muted">
          By continuing you agree to the <a className="underline" href="/legal/terms">Terms</a> and <a className="underline" href="/legal/privacy">Privacy Policy</a>.
        </p>
      </div>
    </div>
  );
}

export default function Login() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}

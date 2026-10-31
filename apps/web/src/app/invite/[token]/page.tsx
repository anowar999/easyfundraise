"use client";

import { Users } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, setWorkspace } from "@/lib/api";

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<{ workspace: string; role: string; email: string } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    fetch(`/api/invites/${encodeURIComponent(token)}`)
      .then(async (r) => (r.ok ? setInfo(await r.json()) : setErr("This invite has expired or was already used.")))
      .catch(() => setErr("Couldn't load the invite."));
  }, [token]);
  const accept = async () => {
    setBusy(true);
    try {
      const r = await api<{ workspace_id: string }>(`/invites/${encodeURIComponent(token)}/accept`, { method: "POST" });
      setWorkspace(r.workspace_id);
      location.href = "/app";
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.problem.title}. ${e.problem.detail ?? ""}` : "Something went wrong.");
      setBusy(false);
    }
  };
  return (
    <main className="min-h-dvh grid place-items-center p-4 bg-surface">
      <div className="card p-6 max-w-sm w-full text-center">
        <Users className="mx-auto text-brand mb-3" />
        {info ? (
          <>
            <h1 className="text-xl font-semibold">Join {info.workspace}</h1>
            <p className="text-sm text-muted mt-1">
              You&apos;ve been invited as {info.role === "editor" ? "an editor" : "a viewer"}. Sign in as <b>{info.email}</b> to accept.
            </p>
            <button className="btn-primary w-full mt-5" disabled={busy} onClick={accept}>
              Accept invite
            </button>
          </>
        ) : (
          <p className="text-sm text-muted">{err || "Loading…"}</p>
        )}
        {info && err && <p className="text-sm text-danger mt-3">{err}</p>}
        <Link href="/" className="text-xs text-muted block mt-4">
          EasyFundraise
        </Link>
      </div>
    </main>
  );
}

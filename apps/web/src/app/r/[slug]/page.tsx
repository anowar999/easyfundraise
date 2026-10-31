"use client";

import { Lock } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { RoomView, type RoomContent } from "@/components/RoomView";
import { ListSkeleton } from "@/components/ui";

type Resp = { locked: true; access: string; title: string } | { locked: false; content: RoomContent; view_id: string; docs: { id: string; label: string; filename: string; size: number }[] };

async function call(path: string, init?: RequestInit) {
  const r = await fetch(`/api/public/rooms/${path}`, { credentials: "same-origin", ...init, headers: { "content-type": "application/json" } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.title || "Something went wrong");
  return body;
}

function Room() {
  const { slug } = useParams<{ slug: string }>();
  const k = useSearchParams().get("k") ?? "";
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    call(`${encodeURIComponent(slug)}${k ? `?k=${encodeURIComponent(k)}` : ""}`)
      .then((d) => {
        setData(d);
        // Drop the token from the address bar once the cookie is set, so a forwarded URL doesn't carry it.
        if (k && !d.locked) history.replaceState(null, "", location.pathname);
      })
      .catch((e) => setErr(e.message));
  }, [slug, k]);
  useEffect(load, [load]);
  const viewId = data && !data.locked ? data.view_id : "";
  const ping = useCallback(
    (seconds: number, sections: Record<string, number>) => {
      const body = JSON.stringify({ view_id: viewId, seconds, sections });
      const url = `/api/public/rooms/${encodeURIComponent(slug)}/ping`;
      if (document.visibilityState === "hidden" && navigator.sendBeacon) navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      else fetch(url, { method: "POST", body, headers: { "content-type": "application/json" }, keepalive: true }).catch(() => {});
    },
    [slug, viewId],
  );
  if (err) return <div className="max-w-md mx-auto p-8 text-center text-muted">This data room isn&apos;t available.</div>;
  if (!data) return <div className="max-w-3xl mx-auto p-6"><ListSkeleton rows={4} /></div>;
  if (data.locked)
    return (
      <div className="max-w-sm mx-auto px-4 py-16">
        <Lock className="text-brand mb-3" />
        <h1 className="text-2xl font-semibold">{data.title}</h1>
        {data.access === "magic" ? (
          <p className="text-muted mt-2">This data room opens from a personal link. Ask the founder to send you one.</p>
        ) : (
          <form
            className="space-y-3 mt-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setErr("");
              try {
                await call(`${encodeURIComponent(slug)}/unlock`, { method: "POST", body: JSON.stringify({ email: email || null, password: password || null }) });
                load();
              } catch (x) {
                alert((x as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <input className="input" type="email" required={data.access === "email"} value={email} onChange={(e) => setEmail(e.target.value)} placeholder={data.access === "email" ? "Your work email" : "Your email (optional)"} aria-label="Email" />
            {data.access === "password" && <input className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" aria-label="Password" />}
            <button className="btn-primary w-full" disabled={busy}>
              View data room
            </button>
            <p className="text-xs text-muted">The founder will see that you viewed it.</p>
          </form>
        )}
      </div>
    );
  return <RoomView content={data.content} docs={data.docs} onPing={ping} docHref={(d) => `/api/public/rooms/${encodeURIComponent(slug)}/docs/${d.id}?view=${data.view_id}`} />;
}

export default function Page() {
  return (
    <Suspense>
      <Room />
    </Suspense>
  );
}

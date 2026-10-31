"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function InvestorRequest() {
  const [form, setForm] = useState({ name: "", email: "", linkedin: "", kind: "remove", message: "" });
  const [done, setDone] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      const r = await api<{ message: string }>("/public/investor-requests", { method: "POST", json: form });
      setDone(r.message);
    } catch (e) {
      setErr(e instanceof ApiError ? e.problem.title : "Something went wrong");
    }
  };
  return (
    <div className="mx-auto max-w-lg px-4 py-10">
      <Link href="/" className="text-sm text-brand">← EasyFundraise</Link>
      <h1 className="text-2xl font-semibold mt-6">Investor? Update or remove your profile</h1>
      <p className="text-sm text-muted mt-2">
        Our directory is compiled from publicly available professional sources. You can ask us to correct or remove your profile at any time. We respond within 72 hours. See{" "}
        <Link className="text-brand underline" href="/legal/data-sources">data sources &amp; investor rights</Link>.
      </p>
      {done ? (
        <div className="card p-4 mt-6 text-sm">{done}</div>
      ) : (
        <form onSubmit={submit} className="card p-4 mt-6 space-y-3">
          <input className="input" required placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="input" required type="email" placeholder="Email we have on file" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input" placeholder="LinkedIn URL (helps us find you)" value={form.linkedin} onChange={(e) => setForm({ ...form, linkedin: e.target.value })} />
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="radio" checked={form.kind === "remove"} onChange={() => setForm({ ...form, kind: "remove" })} /> Remove my profile</label>
            <label className="flex items-center gap-2"><input type="radio" checked={form.kind === "update"} onChange={() => setForm({ ...form, kind: "update" })} /> Update details</label>
          </div>
          <textarea className="textarea min-h-24" placeholder="Anything we should know" value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
          {err && <p className="text-sm text-danger">{err}</p>}
          <button className="btn-primary w-full">Send request</button>
        </form>
      )}
    </div>
  );
}

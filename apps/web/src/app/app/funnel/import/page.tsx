"use client";

import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { errText, useToast } from "@/components/ui";
import { api, qs } from "@/lib/api";

type Column = { index: number; header: string; field: string | null };
type SheetInfo = { name: string; header_row: number; rows: number; score: number; columns: Column[]; preview: string[][] };
type Preview = { filename: string; fields: string[]; suggested_sheet: string | null; sheets: SheetInfo[] };
type Result = { created: number; updated: number; linked: number; skipped: number };

const FIELD_LABELS: Record<string, string> = {
  name: "Contact name",
  firm: "Firm",
  investor_type: "Investor type",
  priority: "Priority",
  status: "Status",
  stage: "Stage",
  can_lead: "Can lead",
  ticket_size: "Ticket / check size",
  agreed_size: "Agreed size",
  instrument: "Instrument",
  contact_method: "Contact method",
  email: "Email",
  linkedin: "LinkedIn",
  referrer: "Referrer / intro",
  last_contacted: "Last contacted",
  next_contact: "Next contact date",
  notes: "Notes",
  next_steps: "Next steps",
  tags: "Tag / wave",
};

export default function ImportPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [sheet, setSheet] = useState("");
  const [mapping, setMapping] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [drag, setDrag] = useState(false);

  const current = useMemo(() => preview?.sheets.find((s) => s.name === sheet), [preview, sheet]);

  const choose = async (f: File) => {
    setFile(f);
    setResult(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const p = await api<Preview>("/funnel/import/preview", { method: "POST", body: fd });
      setPreview(p);
      const s = p.sheets.find((x) => x.name === p.suggested_sheet) ?? p.sheets[0];
      pickSheet(s);
    } catch (e) {
      toast(errText(e), "err");
      setFile(null);
    } finally {
      setBusy(false);
    }
  };

  const pickSheet = (s?: SheetInfo) => {
    if (!s) return;
    setSheet(s.name);
    setMapping(Object.fromEntries(s.columns.filter((c) => c.field).map((c) => [c.index, c.field!])));
  };

  const setField = (col: number, field: string) => {
    setMapping((m) => {
      const next = Object.fromEntries(Object.entries(m).filter(([k, v]) => v !== field || Number(k) === col));
      if (field) next[col] = field;
      else delete next[col];
      return next;
    });
  };

  const commit = async () => {
    if (!file || !current) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api<Result>(`/funnel/import/commit${qs({ sheet, mapping: JSON.stringify(mapping), header_row: current.header_row })}`, { method: "POST", body: fd });
      setResult(r);
      qc.invalidateQueries({ queryKey: ["funnel"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    } catch (e) {
      toast(errText(e), "err");
    } finally {
      setBusy(false);
    }
  };

  const mapped = new Set(Object.values(mapping));
  const canImport = mapped.has("name") || mapped.has("firm");

  return (
    <>
      <Link href="/app/funnel" className="text-sm text-muted flex items-center gap-1 mb-3">
        <ArrowLeft size={16} /> Funnel
      </Link>
      <PageHeader title="Import your investor tracker" sub="Excel (.xlsx) or CSV. We detect the header row and match your columns; you can adjust anything before importing." />

      {result ? (
        <div className="card p-6 text-center">
          <CheckCircle2 className="mx-auto text-accent" size={40} />
          <h2 className="text-lg font-semibold mt-3">Imported into your funnel</h2>
          <p className="text-sm text-muted mt-1">
            {result.created} new · {result.updated} updated · {result.linked} matched to investor profiles
            {result.skipped > 0 && ` · ${result.skipped} rows without a name or firm skipped`}
          </p>
          <div className="mt-5 flex justify-center gap-2">
            <Link href="/app/funnel" className="btn-primary">
              Open funnel
            </Link>
            <button className="btn-ghost" onClick={() => { setResult(null); setPreview(null); setFile(null); }}>
              Import another
            </button>
          </div>
        </div>
      ) : !preview ? (
        <div
          className={clsx("card border-dashed p-10 text-center cursor-pointer", drag && "border-brand bg-brand/5")}
          onClick={() => input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files[0];
            if (f) choose(f);
          }}
        >
          <Upload className="mx-auto text-brand" size={32} />
          <div className="mt-3 font-medium">{busy ? "Reading your file…" : "Choose a file or drop it here"}</div>
          <p className="text-sm text-muted mt-1">Works with trackers like "Investment firm · Contact person · Stage · Next touch date · Notes". Max 10MB.</p>
          <input ref={input} type="file" accept=".xlsx,.xlsm,.csv" className="hidden" onChange={(e) => e.target.files?.[0] && choose(e.target.files[0])} />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="card p-4 flex flex-wrap items-center gap-3">
            <FileSpreadsheet className="text-brand" />
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">{preview.filename}</div>
              <div className="text-xs text-muted">{preview.sheets.length} sheet{preview.sheets.length > 1 ? "s" : ""}</div>
            </div>
            <button className="btn-ghost btn-sm" onClick={() => { setPreview(null); setFile(null); }}>
              Change file
            </button>
          </div>

          {preview.sheets.length > 1 && (
            <div className="card p-4">
              <div className="label">Which sheet holds your investors?</div>
              <div className="flex flex-wrap gap-2">
                {preview.sheets.map((s) => (
                  <button key={s.name} onClick={() => pickSheet(s)} className={clsx("chip px-3 py-1.5 text-sm", sheet === s.name && "bg-brand text-white border-brand")}>
                    {s.name} <span className="opacity-70">· {s.rows} rows</span>
                    {s.name === preview.suggested_sheet && <span className="opacity-70">· suggested</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          {current && (
            <div className="card p-4">
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="font-semibold">Match your columns</h2>
                <span className="text-xs text-muted">{current.rows} rows</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                {current.columns.map((col) => {
                  const sample = current.preview.map((r) => r[col.index]).filter(Boolean)[0];
                  return (
                    <div key={col.index} className="flex items-center gap-3 py-1.5 border-b border-line">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{col.header}</div>
                        <div className="text-xs text-muted truncate">{sample ?? "—"}</div>
                      </div>
                      <select className={clsx("input w-44 h-9 text-sm", mapping[col.index] && "border-brand")} value={mapping[col.index] ?? ""} onChange={(e) => setField(col.index, e.target.value)}>
                        <option value="">Don't import</option>
                        {preview.fields.map((f) => (
                          <option key={f} value={f}>
                            {FIELD_LABELS[f] ?? f}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
              {!canImport && <p className="text-sm text-danger mt-3">Map at least a contact name or firm column.</p>}
            </div>
          )}

          {current && current.preview.length > 0 && (
            <div className="card p-4 overflow-x-auto">
              <h2 className="font-semibold mb-2">Preview</h2>
              <table className="text-xs w-full">
                <thead>
                  <tr className="text-left text-muted">
                    {Object.entries(mapping).map(([i, f]) => (
                      <th key={i} className="px-2 py-1 font-medium whitespace-nowrap">
                        {FIELD_LABELS[f] ?? f}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {current.preview.map((r, ri) => (
                    <tr key={ri} className="border-t border-line">
                      {Object.keys(mapping).map((i) => (
                        <td key={i} className="px-2 py-1 max-w-48 truncate">
                          {r[Number(i)]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="sticky bottom-[calc(64px_+_env(safe-area-inset-bottom))] md:bottom-4 z-10">
            <button className="btn-primary w-full h-12 shadow-lg" disabled={!canImport || busy} onClick={commit}>
              {busy ? "Importing…" : `Import ${current?.rows ?? 0} rows into my funnel`}
            </button>
            <p className="text-xs text-muted text-center mt-1.5 bg-surface/80">Duplicates are matched by email, LinkedIn, or name + firm and updated, not doubled.</p>
          </div>
        </div>
      )}
    </>
  );
}

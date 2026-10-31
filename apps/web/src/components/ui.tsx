"use client";

import clsx from "clsx";
import { AlertTriangle, Lock, RotateCw, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ApiError } from "@/lib/api";

export const STATUS_COLORS: Record<string, string> = {
  Active: "bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-300",
  Inactive: "bg-gray-500/10 text-gray-500 border-gray-500/30",
  Rejection: "bg-red-500/10 text-red-600 border-red-500/30 dark:text-red-300",
  Ghosting: "bg-amber-500/10 text-amber-600 border-amber-500/30 dark:text-amber-300",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={clsx("chip font-medium", STATUS_COLORS[status] ?? STATUS_COLORS.Inactive)}>{status}</span>;
}

export function Badge({ children, tone = "default", title }: { children: ReactNode; tone?: "default" | "green" | "amber" | "red" | "blue"; title?: string }) {
  const tones = {
    default: "text-muted",
    green: "bg-green-500/10 text-green-700 border-green-600/30 dark:text-green-300",
    amber: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
    red: "bg-red-500/10 text-red-600 border-red-500/30 dark:text-red-300",
    blue: "bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-300",
  };
  return (
    <span title={title} className={clsx("chip", tones[tone])}>
      {children}
    </span>
  );
}

export function Avatar({ name, src, logoDomain, size = 40 }: { name: string; src?: string; logoDomain?: string; size?: number }) {
  // Photo first, then the firm's logo (from its website), then initials.
  const sources = [src, logoDomain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(logoDomain)}&sz=128` : ""].filter(Boolean) as string[];
  const [failed, setFailed] = useState(0);
  const initials = name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  const current = sources[failed];
  if (current) {
    const isLogo = current !== src;
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={current}
        alt=""
        width={size}
        height={size}
        onError={() => setFailed((n) => n + 1)}
        className={clsx("rounded-full shrink-0 bg-white", isLogo ? "object-contain p-1.5 border border-line" : "object-cover")}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div className="rounded-full bg-brand/10 text-brand grid place-items-center font-semibold shrink-0" style={{ width: size, height: size, fontSize: size / 2.6 }}>
      {initials}
    </div>
  );
}

export function FitScore({ score }: { score: number }) {
  const tone = score >= 60 ? "text-green-600 dark:text-green-400" : score >= 35 ? "text-brand" : "text-muted";
  return (
    <div className={clsx("text-right leading-none shrink-0", tone)} title="Match score: how well this investor fits your company profile (sector, stage, cheque size, location, investor type)">
      <div className="text-lg font-semibold">{score}%</div>
      <div className="text-[10px] uppercase tracking-wide mt-0.5">match</div>
    </div>
  );
}

export function Locked({ label = "Locked", onClick }: { label?: string; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className="inline-flex items-center gap-1.5 text-sm text-muted no-select">
      <Lock size={14} aria-hidden />
      <span className="blur-[3px]" aria-hidden>
        hidden@locked.vc
      </span>
      <span className="sr-only">{label}</span>
    </button>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} />;
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="card p-4 flex gap-3">
          <Skeleton className="w-10 h-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Empty({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="card p-8 text-center flex flex-col items-center gap-2">
      {icon && <div className="text-muted mb-1">{icon}</div>}
      <div className="font-semibold">{title}</div>
      {body && <p className="text-sm text-muted max-w-sm">{body}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const p = error instanceof ApiError ? error.problem : null;
  return (
    <div className="card p-6 flex flex-col items-center gap-2 text-center" role="alert">
      <AlertTriangle className="text-warn" />
      <div className="font-semibold">{p?.title ?? "Something went wrong"}</div>
      {p?.detail && <p className="text-sm text-muted">{p.detail}</p>}
      {p?.ref && <p className="text-xs text-muted font-mono">ref {p.ref}</p>}
      <div className="flex gap-2 mt-2">
        {retry && (
          <button className="btn-ghost btn-sm" onClick={retry}>
            <RotateCw size={14} /> Retry
          </button>
        )}
        {p?.upgrade && (
          <a className="btn-primary btn-sm" href="/app/settings#plan">
            See plans
          </a>
        )}
      </div>
    </div>
  );
}

/** Bottom sheet on phones, centred dialog on larger screens. */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open || typeof document === "undefined") return null;
  // Portalled to <body> so it sits above the tab bar and the agent button, whatever page it's opened from
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center" role="dialog" aria-modal="true" aria-label={title}>
      <button className="absolute inset-0 bg-black/40" aria-label="Close" onClick={onClose} />
      <div className="relative w-full sm:max-w-lg max-h-[88vh] overflow-y-auto bg-card rounded-t-2xl sm:rounded-2xl border border-line shadow-xl safe-bottom">
        <div className="sticky top-0 bg-card flex items-center justify-between px-4 py-3 border-b border-line">
          <div className="font-semibold">{title}</div>
          <button className="p-1 text-muted" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

type Toast = { id: number; text: string; tone: "ok" | "err" };
const ToastCtx = createContext<(text: string, tone?: "ok" | "err") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed z-[60] left-1/2 -translate-x-1/2 bottom-20 sm:bottom-6 flex flex-col gap-2 w-[min(92vw,420px)]" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={clsx("rounded-lg px-4 py-3 text-sm font-medium shadow-lg text-white ring-1 ring-white/10", t.tone === "ok" ? "bg-[#0b1220]" : "bg-danger")}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

export function errText(e: unknown): string {
  if (e instanceof ApiError) {
    const p = e.problem;
    return [p.title, p.detail, p.ref ? `· ref ${p.ref}` : ""].filter(Boolean).join(" ");
  }
  return "Something went wrong";
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

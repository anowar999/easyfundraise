"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Bell, BarChart3, Globe, Home, KanbanSquare, ListPlus, LogOut, Megaphone, Menu, Search, Settings, Shield, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, getWorkspace, setWorkspace } from "@/lib/api";
import { AgentChat } from "./AgentChat";
import { Sheet, ToastProvider } from "./ui";

const NAV = [
  { href: "/app", label: "Home", icon: Home, exact: true },
  { href: "/app/investors", label: "Investors", icon: Search },
  { href: "/app/shortlist", label: "Shortlist", icon: ListPlus },
  { href: "/app/funnel", label: "Investor tracker", short: "Tracker", icon: KanbanSquare },
  { href: "/app/outreach", label: "Outreach", icon: BarChart3 },
  { href: "/app/updates", label: "Updates", icon: Megaphone },
  { href: "/app/data-room", label: "Data room", icon: Globe },
  { href: "/app/notifications", label: "Alerts", icon: Bell },
  { href: "/app/settings", label: "Settings", icon: Settings },
];
// Phones: four primary tabs + "More" (the rest live in a sheet)
const TABS = ["/app", "/app/investors", "/app/funnel", "/app/notifications"];

export type Me = {
  id: string;
  email: string;
  name: string;
  picture: string;
  timezone: string;
  is_admin: boolean;
  signature: string;
  workspaces: { id: string; name: string; role: string; tier: string }[];
  notify_prefs: Record<string, any>;
  mfa_enabled: boolean;
  mfa_required: boolean;
};

function WorkspaceSwitcher({ me }: { me: Me }) {
  if (me.workspaces.length < 2) return null;
  return (
    <select
      className="input h-9 text-sm"
      aria-label="Workspace"
      value={getWorkspace() ?? me.workspaces[0].id}
      onChange={(e) => {
        setWorkspace(e.target.value);
        location.href = "/app";
      }}
    >
      {me.workspaces.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
    </select>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: true } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}

export function useMe() {
  return useQuery<Me>({ queryKey: ["me"], queryFn: () => api("/auth/me"), staleTime: 60_000 });
}

function useUnread() {
  return useQuery<{ unread: number }>({
    queryKey: ["notifications", "count"],
    queryFn: () => api("/notifications?unread=true"),
    refetchInterval: 60_000,
  });
}

export function AppShell({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const path = usePathname();
  const router = useRouter();
  const me = useMe();
  const unread = useUnread();
  const [more, setMore] = useState(false);

  useEffect(() => {
    const ws = me.data?.workspaces;
    if (ws?.length && !ws.some((w) => w.id === getWorkspace())) setWorkspace(ws[0].id);
  }, [me.data]);

  useEffect(() => {
    if (admin && me.data && !me.data.is_admin) router.replace("/app");
  }, [admin, me.data, router]);

  const active = (href: string, exact?: boolean) => (exact ? path === href : path.startsWith(href));
  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    location.href = "/login";
  };
  const count = unread.data?.unread ?? 0;

  return (
    <div className="min-h-dvh">
      {/* Desktop sidebar */}
      <aside className="app-nav hidden md:flex fixed inset-y-0 left-0 w-64 flex-col px-3 py-5 text-white">
        <Link href="/app" className="flex items-center gap-2.5 px-2.5 mb-7">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icon.svg" alt="" className="w-9 h-9 rounded-[10px] shadow-[0_0_24px_rgba(76,141,255,0.45)]" />
          <span className="text-[17px] font-bold tracking-tight">
            Easy<span className="logo-accent">Fundraise</span>
          </span>
        </Link>
        <nav className="flex flex-col gap-1" aria-label="Main">
          {NAV.map(({ href, label, icon: Icon, exact }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium transition",
                active(href, exact) ? "bg-white/[0.12] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]" : "text-white/65 hover:bg-white/[0.06] hover:text-white",
              )}
            >
              <Icon size={18} className={active(href, exact) ? "text-[#8ab8ff]" : ""} />
              {label}
              {label === "Alerts" && count > 0 && <span className="ml-auto text-xs font-semibold rounded-full bg-brand text-white px-1.5">{count}</span>}
            </Link>
          ))}
          {me.data?.is_admin && (
            <Link
              href="/admin"
              className={clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium", path.startsWith("/admin") ? "bg-white/[0.12] text-white" : "text-white/65 hover:bg-white/[0.06] hover:text-white")}
            >
              <Shield size={18} /> Admin
            </Link>
          )}
        </nav>
        <div className="mt-auto space-y-3">
          {me.data && <WorkspaceSwitcher me={me.data} />}
          <div className="rounded-2xl bg-white/[0.06] ring-1 ring-white/10 p-3.5 text-xs">
            <div className="flex items-center gap-1.5 font-semibold text-white">
              <Sparkles size={14} className="text-[#8ab8ff]" /> Your Raise Agent
            </div>
            <p className="text-white/60 mt-1 leading-relaxed">Ask it anything, or tell it what to do. It watches follow-ups, replies and meetings for you.</p>
          </div>
          <div className="flex items-center gap-2 px-2 pt-3 border-t border-white/10">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate">{me.data?.name}</div>
              <div className="text-xs text-white/55 truncate">{me.data?.email}</div>
            </div>
            <button onClick={logout} className="p-2 text-white/55 hover:text-white" aria-label="Sign out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-30 flex items-center justify-between bg-card/90 backdrop-blur border-b border-line px-4 h-14">
        <Link href="/app" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icon.svg" alt="" className="w-7 h-7" />
          <span className="font-bold tracking-tight">
            Easy<span className="logo-accent">Fundraise</span>
          </span>
        </Link>
        <div className="flex items-center gap-1">
          {me.data?.is_admin && (
            <Link href="/admin" className="p-2 text-muted" aria-label="Admin">
              <Shield size={20} />
            </Link>
          )}
          <button onClick={logout} className="p-2 text-muted" aria-label="Sign out">
            <LogOut size={20} />
          </button>
        </div>
      </header>

      <main className="md:pl-64 pb-24 md:pb-10">
        {/* The tracker board uses the whole width; other pages keep a readable column */}
        <div className={clsx("mx-auto px-4 py-4 md:py-8", path.startsWith("/app/funnel") && !/\/app\/funnel\/./.test(path) ? "max-w-none md:px-6" : "max-w-6xl")}>{children}</div>
      </main>

      {!admin && <AgentChat />}

      {/* Mobile bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-card/95 backdrop-blur border-t border-line safe-bottom" aria-label="Main">
        <div className="grid grid-cols-5">
          {NAV.filter((n) => TABS.includes(n.href)).map(({ href, label, short, icon: Icon, exact }) => (
            <Link
              key={href}
              href={href}
              className={clsx("relative flex flex-col items-center gap-0.5 py-2 text-[11px]", active(href, exact) ? "text-brand" : "text-muted")}
            >
              <Icon size={22} />
              {short ?? label}
              {label === "Alerts" && count > 0 && (
                <span className="absolute top-1 right-[calc(50%_-_18px)] min-w-4 h-4 text-[10px] rounded-full bg-danger text-white px-1 grid place-items-center">
                  {count > 9 ? "9+" : count}
                </span>
              )}
            </Link>
          ))}
          <button
            onClick={() => setMore(true)}
            className={clsx("flex flex-col items-center gap-0.5 py-2 text-[11px]", NAV.some((n) => !TABS.includes(n.href) && path.startsWith(n.href)) ? "text-brand" : "text-muted")}
          >
            <Menu size={22} />
            More
          </button>
        </div>
      </nav>
      <Sheet open={more} onClose={() => setMore(false)} title="More">
        <div className="grid grid-cols-2 gap-2">
          {NAV.filter((n) => !TABS.includes(n.href)).map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} onClick={() => setMore(false)} className="card p-4 flex items-center gap-2 text-sm">
              <Icon size={18} className="text-brand" /> {label}
            </Link>
          ))}
          {me.data?.is_admin && (
            <Link href="/admin" onClick={() => setMore(false)} className="card p-4 flex items-center gap-2 text-sm">
              <Shield size={18} className="text-brand" /> Admin
            </Link>
          )}
        </div>
        {me.data && me.data.workspaces.length > 1 && (
          <div className="mt-4">
            <div className="label">Workspace</div>
            <WorkspaceSwitcher me={me.data} />
          </div>
        )}
      </Sheet>
    </div>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-4 md:mb-6">
      <div className="min-w-0">
        <h1 className="text-2xl md:text-[28px] font-bold tracking-tight text-ink">{title}</h1>
        {sub && <div className="text-[15px] text-muted mt-1">{sub}</div>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

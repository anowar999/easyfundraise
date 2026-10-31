import type { Metadata } from "next";
import { AppShell, Providers } from "@/components/AppShell";

export const metadata: Metadata = { title: "App", robots: { index: false, follow: false } };

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AppShell>{children}</AppShell>
    </Providers>
  );
}

import type { Metadata } from "next";
import { AppShell, Providers } from "@/components/AppShell";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AppShell admin>{children}</AppShell>
    </Providers>
  );
}

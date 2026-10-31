import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://easyfundraise.com"),
  title: { default: "EasyFundraise: find investors, reach them, close your round", template: "%s · EasyFundraise" },
  description:
    "Everything founders need to find investors, contact them with personalised emails, manage the pipeline and raise capital, powered by AI.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/apple-touch-icon.png" },
  openGraph: { type: "website", siteName: "EasyFundraise", images: ["/logo.svg"] },
  appleWebApp: { capable: true, title: "EasyFundraise", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F6F8FB" },
    { media: "(prefers-color-scheme: dark)", color: "#0B1220" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}

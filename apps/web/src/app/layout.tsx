import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://easyfundraise.com"),
  title: { default: "EasyFundraise: find investors, reach them, close your round", template: "%s · EasyFundraise" },
  description:
    "Everything founders need to find investors, contact them with personalised emails, manage the pipeline and raise capital, powered by AI.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/apple-touch-icon.png" },
  openGraph: { type: "website", siteName: "EasyFundraise", images: ["/og.png"] },
  appleWebApp: { capable: true, title: "EasyFundraise", statusBarStyle: "default" },
};

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "https://easyfundraise.com";

// Site-wide structured data: who we are (Organization) and the site name search engines should show (WebSite).
const siteJsonLd = [
  { "@context": "https://schema.org", "@type": "Organization", name: "EasyFundraise", url: SITE, logo: `${SITE}/icon-256.png` },
  { "@context": "https://schema.org", "@type": "WebSite", name: "EasyFundraise", url: SITE },
];

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#F3F5FA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(siteJsonLd) }} />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}

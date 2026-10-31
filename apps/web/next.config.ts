import type { NextConfig } from "next";

const api = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Same-origin API so the httpOnly session cookie works without CORS.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
  async headers() {
    const noindex = process.env.NEXT_PUBLIC_ENV !== "prod";
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          ...(noindex ? [{ key: "X-Robots-Tag", value: "noindex" }] : []),
        ],
      },
      { source: "/app/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex" }] },
      { source: "/admin/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex" }] },
    ];
  },
};

export default config;

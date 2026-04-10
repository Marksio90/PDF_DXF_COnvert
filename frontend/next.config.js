/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  // Proxy /api/* to backend — eliminates CORS and NEXT_PUBLIC_API_URL build-time baking.
  // Set BACKEND_URL env var at runtime (not build time).
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

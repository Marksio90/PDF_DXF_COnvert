/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  // Proxy requests to backend — no CORS, no build-time env baking needed.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/health",     destination: `${backend}/health` },
    ];
  },
};

module.exports = nextConfig;

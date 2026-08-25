/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a static site to `out/` (the dashboard is fully client-rendered and talks to the
  // API over HTTP), so the backend can serve it directly — no Node runtime on the VM.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker builds
  output: 'standalone',
  
  // Ensure all routes are included in standalone build
  outputFileTracingRoot: undefined,
  
  // Add explicit page extensions
  pageExtensions: ['tsx', 'ts', 'jsx', 'js'],
};

export default nextConfig;

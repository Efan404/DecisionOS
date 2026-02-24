/** @type {import('next').NextConfig} */
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000'

const config = {
  output: 'standalone',
  reactStrictMode: false,
  async rewrites() {
    return [
      {
        source: '/api-proxy/:path*',
        destination: `${API_INTERNAL_URL}/:path*`,
      },
    ]
  },
}

export default config

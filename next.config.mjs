import createNextIntlPlugin from 'next-intl/plugin'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const withNextIntl = createNextIntlPlugin(path.join(__dirname, 'frontend/i18n.ts'))

/** @type {import('next').NextConfig} */
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000'

const nextConfig = {
  reactStrictMode: false,
  transpilePackages: ['nextstepjs'],
  async rewrites() {
    return [
      {
        source: '/api-proxy/:path*',
        destination: `${API_INTERNAL_URL}/:path*`,
      },
    ]
  },
}

export default withNextIntl(nextConfig)

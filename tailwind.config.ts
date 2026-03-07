import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './frontend/app/**/*.{js,ts,jsx,tsx,mdx}',
    './frontend/components/**/*.{js,ts,jsx,tsx,mdx}',
    './node_modules/nextstepjs/dist/**/*.{js,ts,jsx,tsx}',
  ],
}

export default config

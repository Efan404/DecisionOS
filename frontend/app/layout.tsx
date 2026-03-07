import type { Metadata } from 'next'
import { NextIntlClientProvider } from 'next-intl'
import { getMessages, getLocale } from 'next-intl/server'

import './globals.css'
import { AppShell } from '../components/layout/AppShell'
import { OnboardingProvider } from '../components/onboarding/OnboardingProvider'
import { StoreHydration } from '../components/providers/StoreHydration'
import { ToasterProvider } from '../components/providers/ToasterProvider'

export const metadata: Metadata = {
  title: 'DecisionOS',
  description: 'A single-user, single-workspace decision management system for product ideas.',
  icons: {
    icon: '/icon.svg',
    shortcut: '/icon.svg',
    apple: '/icon.svg',
  },
}

type RootLayoutProps = Readonly<{
  children: React.ReactNode
}>

export default async function RootLayout({ children }: RootLayoutProps) {
  const locale = await getLocale()
  const messages = await getMessages()

  return (
    <html lang={locale}>
      <body className="min-h-screen bg-[#f5f5f5] text-[#1e1e1e] antialiased">
        <NextIntlClientProvider messages={messages}>
          <StoreHydration />
          <ToasterProvider />
          <OnboardingProvider>
            <AppShell>{children}</AppShell>
          </OnboardingProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}

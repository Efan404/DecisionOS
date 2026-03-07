import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Mock next-intl: useTranslations returns "namespace.key" in tests
vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, _params?: Record<string, unknown>) =>
    `${namespace}.${key}`,
  NextIntlClientProvider: ({ children }: { children: unknown }) => children,
  getLocale: async () => 'en',
  getMessages: async () => ({}),
  getTranslations: async (namespace: string) => (key: string) => `${namespace}.${key}`,
}))

type MockRouter = {
  push: ReturnType<typeof vi.fn>
  replace: ReturnType<typeof vi.fn>
  prefetch: ReturnType<typeof vi.fn>
  back: ReturnType<typeof vi.fn>
  forward: ReturnType<typeof vi.fn>
  refresh: ReturnType<typeof vi.fn>
}

const createRouter = (): MockRouter => ({
  push: vi.fn(),
  replace: vi.fn(),
  prefetch: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
})

const navigationState: {
  pathname: string
  searchParams: URLSearchParams
  router: MockRouter
} = {
  pathname: '/ideas/test/scope-freeze',
  searchParams: new URLSearchParams(),
  router: createRouter(),
}

export const nextNavigationMock = {
  get router() {
    return navigationState.router
  },
  get pathname() {
    return navigationState.pathname
  },
  setPathname(pathname: string) {
    navigationState.pathname = pathname
  },
  setSearchParams(params: URLSearchParams | string) {
    navigationState.searchParams =
      typeof params === 'string' ? new URLSearchParams(params) : new URLSearchParams(params)
  },
  reset() {
    navigationState.pathname = '/ideas/test/scope-freeze'
    navigationState.searchParams = new URLSearchParams()
    navigationState.router = createRouter()
  },
}

vi.mock('next/navigation', () => ({
  useRouter: () => navigationState.router,
  usePathname: () => navigationState.pathname,
  useSearchParams: () => navigationState.searchParams,
}))

afterEach(() => {
  cleanup()
  nextNavigationMock.reset()
})

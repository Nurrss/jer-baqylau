import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Logo } from '@/components/common/Logo'
import { LanguageSwitch } from '@/components/layout/AppShell'

/** Minimal chrome for pages opened without login (owner's phone, act verification). */
export function PublicLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="min-h-full bg-background">
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b bg-card/95 px-4 py-2.5 backdrop-blur">
        <Logo className="size-7" />
        <span className="flex-1 font-semibold">{t('public.brand')}</span>
        <LanguageSwitch />
      </header>
      <main className="mx-auto grid w-full max-w-xl gap-4 px-4 py-5">{children}</main>
    </div>
  )
}

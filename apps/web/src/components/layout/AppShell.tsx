import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import {
  BarChart3,
  FileText,
  LogOut,
  Map as MapIcon,
  Megaphone,
  Moon,
  ShieldAlert,
  Sun,
  UserRound,
} from 'lucide-react'
import { useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useSignals } from '@/api/queries'
import { Logo } from '@/components/common/Logo'
import { Tooltip } from '@/components/ui/misc'
import { playChime, useRealtimeEvents, useRealtimeStatus, type SignalCreatedPayload } from '@/lib/realtime'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'
import { useUiStore } from '@/store/ui'

const NAV = [
  { to: '/', icon: MapIcon, key: 'map', end: true },
  { to: '/signals', icon: Megaphone, key: 'signals' },
  { to: '/violations', icon: ShieldAlert, key: 'violations' },
  { to: '/applications', icon: FileText, key: 'applications' },
  { to: '/dashboard', icon: BarChart3, key: 'dashboard' },
] as const

function LanguageSwitch() {
  const { i18n } = useTranslation()
  return (
    <div
      className="flex rounded-lg border bg-muted p-0.5 text-xs font-semibold"
      role="group"
      aria-label="Language"
    >
      {(['ru', 'kk'] as const).map((lng) => (
        <button
          key={lng}
          type="button"
          onClick={() => void i18n.changeLanguage(lng)}
          aria-pressed={i18n.language === lng}
          className={cn(
            'rounded-md px-2.5 py-1 transition-colors',
            i18n.language === lng
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {lng === 'ru' ? 'RU' : 'ҚАЗ'}
        </button>
      ))}
    </div>
  )
}

function RealtimeIndicator() {
  const { t } = useTranslation()
  const mode = useRealtimeStatus((s) => s.mode)
  const color = {
    realtime: 'bg-success',
    polling: 'bg-accent',
    connecting: 'bg-muted-foreground',
    offline: 'bg-destructive',
  }[mode]
  return (
    <Tooltip content={t(`realtime.hint.${mode}`)}>
      <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
        <span className={cn('relative flex size-2 rounded-full', color)}>
          {mode === 'realtime' && (
            <span className={cn('absolute inset-0 animate-ping rounded-full opacity-60', color)} />
          )}
        </span>
        {t(`realtime.${mode}`)}
      </span>
    </Tooltip>
  )
}

function UserMenu() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-muted"
        aria-label={t('auth.account')}
      >
        <span className="grid size-7 place-items-center rounded-full bg-primary/10 text-primary">
          <UserRound className="size-4" />
        </span>
        <span className="hidden max-w-40 truncate md:block">{user?.name}</span>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-52 rounded-lg border bg-card p-1 text-card-foreground shadow-lg"
        >
          <div className="px-2 py-1.5">
            <p className="text-sm font-medium">{user?.name}</p>
            <p className="text-xs text-muted-foreground">{user?.email}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item
            onSelect={() => void logout()}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-muted"
          >
            <LogOut className="size-4" /> {t('auth.logout')}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

export function AppShell() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)
  const newSignals = useSignals(['NEW']).data?.total ?? 0

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  const onSignalCreated = useCallback(
    (payload: SignalCreatedPayload) => {
      const ui = useUiStore.getState()
      ui.markFresh(payload.signal_id)
      if (ui.soundEnabled) playChime()
      toast(t('realtime.newSignal', { code: payload.tracking_code }), {
        description: payload.duplicate_of ? t('realtime.newSignalDuplicate') : t('realtime.newSignalHint'),
        duration: 10_000,
        action: {
          label: t('realtime.showOnMap'),
          onClick: () => {
            navigate('/')
            useUiStore.getState().selectSignal(payload.signal_id)
            useUiStore.getState().flyTo({ center: [payload.lon, payload.lat], zoom: 17 })
          },
        },
      })
    },
    [navigate, t],
  )
  useRealtimeEvents(onSignalCreated)

  return (
    <div className="flex h-full">
      <nav
        className="z-20 flex w-16 shrink-0 flex-col items-center gap-1 bg-sidebar py-3 text-sidebar-foreground lg:w-56 lg:items-stretch lg:px-3"
        aria-label={t('nav.label')}
      >
        <div className="mb-4 flex items-center gap-2.5 px-1 lg:px-2">
          <Logo className="size-9 shrink-0" />
          <div className="hidden leading-tight lg:block">
            <p className="text-[15px] font-bold tracking-tight text-white">ЖерБақылау</p>
            <p className="text-[11px] text-sidebar-foreground/80">{t('app.region')}</p>
          </div>
        </div>
        {NAV.map(({ to, icon: Icon, key, ...rest }) => (
          <NavLink
            key={to}
            to={to}
            end={'end' in rest}
            className={({ isActive }) =>
              cn(
                'group relative flex items-center gap-3 rounded-lg p-2.5 text-sm font-medium transition-colors lg:px-3',
                isActive ? 'bg-sidebar-active text-white' : 'hover:bg-sidebar-active/60 hover:text-white',
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-accent" />}
                <Icon className="size-5 shrink-0" />
                <span className="hidden lg:block">{t(`nav.${key}`)}</span>
                {key === 'signals' && newSignals > 0 && (
                  <span className="absolute top-1 right-1 grid min-w-4.5 place-items-center rounded-full bg-signal px-1 text-[10px] leading-4.5 font-bold text-white lg:static lg:ml-auto">
                    {newSignals}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
        <div className="mt-auto hidden px-2 text-[10px] leading-snug text-sidebar-foreground/60 lg:block">
          {t('app.demoNotice')}
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="z-10 flex h-14 shrink-0 items-center gap-3 border-b bg-card px-4">
          <h1 className="truncate text-sm font-semibold text-muted-foreground">{t('app.subtitle')}</h1>
          <div className="ml-auto flex items-center gap-3">
            <RealtimeIndicator />
            <LanguageSwitch />
            <Tooltip content={theme === 'dark' ? t('theme.light') : t('theme.dark')}>
              <button
                type="button"
                className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                aria-label={theme === 'dark' ? t('theme.light') : t('theme.dark')}
              >
                {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
              </button>
            </Tooltip>
            <UserMenu />
          </div>
        </header>
        <main className="relative min-h-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

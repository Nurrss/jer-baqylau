import { Loader2, LockKeyhole } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { Logo } from '@/components/common/Logo'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { authMode } from '@/lib/supabase'
import { useAuthStore } from '@/store/auth'

export function LoginPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const status = useAuthStore((s) => s.status)
  const login = useAuthStore((s) => s.login)
  const errorMessage = useErrorMessage()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/'
  if (status === 'authenticated') return <Navigate to={from} replace />

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      const message =
        err instanceof Error && /invalid login credentials/i.test(err.message)
          ? t('errors.INVALID_CREDENTIALS')
          : errorMessage(err)
      setError(message)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-sidebar p-12 text-white lg:flex lg:flex-col">
        <div
          className="absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              'linear-gradient(#f2b705 1px, transparent 1px), linear-gradient(90deg, #f2b705 1px, transparent 1px)',
            backgroundSize: '48px 48px',
            transform: 'rotate(-8deg) scale(1.3)',
          }}
        />
        <div className="relative flex items-center gap-3">
          <Logo className="size-11" />
          <span className="text-xl font-bold tracking-tight">ЖерБақылау</span>
        </div>
        <div className="relative mt-auto max-w-md">
          <h2 className="text-3xl leading-tight font-semibold">{t('login.heroTitle')}</h2>
          <p className="mt-4 text-sidebar-foreground">{t('login.heroText')}</p>
        </div>
      </aside>

      <main className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center justify-between">
            <div className="flex items-center gap-2 lg:hidden">
              <Logo className="size-8" />
              <span className="font-bold">ЖерБақылау</span>
            </div>
            <div className="ml-auto flex rounded-lg border bg-muted p-0.5 text-xs font-semibold">
              {(['ru', 'kk'] as const).map((lng) => (
                <button
                  key={lng}
                  type="button"
                  onClick={() => void i18n.changeLanguage(lng)}
                  className={
                    i18n.language === lng
                      ? 'rounded-md bg-card px-2.5 py-1 shadow-sm'
                      : 'rounded-md px-2.5 py-1 text-muted-foreground'
                  }
                >
                  {lng === 'ru' ? 'RU' : 'ҚАЗ'}
                </button>
              ))}
            </div>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{t('login.title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('login.subtitle')}</p>

          <form className="mt-8 grid gap-4" onSubmit={onSubmit} noValidate>
            <div className="grid gap-2">
              <Label htmlFor="email">{t('login.email')}</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="inspector@jer.kz"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">{t('login.password')}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" disabled={pending || !email || !password}>
              {pending ? <Loader2 className="animate-spin" /> : <LockKeyhole />}
              {t('login.submit')}
            </Button>
          </form>
          <p className="mt-6 text-xs text-muted-foreground">
            {authMode === 'local' ? t('login.localModeHint') : t('login.supabaseHint')}
          </p>
        </div>
      </main>
    </div>
  )
}

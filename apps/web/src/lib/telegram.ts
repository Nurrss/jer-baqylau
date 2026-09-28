/**
 * Telegram Mini App SDK (https://core.telegram.org/bots/webapps).
 * Loaded only on the citizen pages (/app, /inspect); the inspector panel never needs it.
 */
import { useEffect, useState } from 'react'

export interface TgLocation {
  latitude: number
  longitude: number
  horizontal_accuracy?: number | null
}

interface TgLocationManager {
  isInited: boolean
  isLocationAvailable: boolean
  isAccessRequested: boolean
  isAccessGranted: boolean
  init(callback?: () => void): void
  getLocation(callback: (location: TgLocation | null) => void): void
  openSettings(): void
}

export interface TgWebApp {
  initData: string
  initDataUnsafe: { user?: { id: number; first_name: string; language_code?: string } }
  version: string
  colorScheme: 'light' | 'dark'
  ready(): void
  expand(): void
  close(): void
  isVersionAtLeast(version: string): boolean
  setHeaderColor?(color: string): void
  setBackgroundColor?(color: string): void
  HapticFeedback?: {
    impactOccurred(style: 'light' | 'medium' | 'heavy'): void
    notificationOccurred(type: 'success' | 'error' | 'warning'): void
  }
  LocationManager?: TgLocationManager
}

declare global {
  interface Window {
    Telegram?: { WebApp: TgWebApp }
  }
}

/** Username of the citizens' bot (links from pages opened outside Telegram). */
export const BOT_USERNAME =
  (import.meta.env.VITE_TELEGRAM_BOT as string | undefined)?.replace(/^@/, '') || 'take_a_place_bot'

const SDK_URL = 'https://telegram.org/js/telegram-web-app.js'
let loading: Promise<TgWebApp | null> | null = null

/** The Mini App object when the page runs inside Telegram, otherwise null. */
export function loadTelegram(): Promise<TgWebApp | null> {
  if (!loading) {
    loading = new Promise((resolve) => {
      const done = () => {
        const app = window.Telegram?.WebApp
        resolve(app && app.initData ? app : null)
      }
      if (window.Telegram?.WebApp) {
        done()
        return
      }
      const script = document.createElement('script')
      script.src = SDK_URL
      script.async = true
      script.onload = done
      script.onerror = () => resolve(null)
      document.head.appendChild(script)
      window.setTimeout(done, 4000) // blocked network: behave as a normal web page
    })
  }
  return loading
}

/** `{ tg, ready }`: tg is null outside Telegram (the page then works as a normal web page). */
export function useTelegram(): { tg: TgWebApp | null; ready: boolean } {
  const [state, setState] = useState<{ tg: TgWebApp | null; ready: boolean }>({ tg: null, ready: false })
  useEffect(() => {
    let alive = true
    void loadTelegram().then((tg) => {
      if (!alive) return
      if (tg) {
        tg.ready()
        tg.expand()
      }
      setState({ tg, ready: true })
    })
    return () => {
      alive = false
    }
  }, [])
  return state
}

/** Telegram's own location access (Bot API 8.0+): works where the webview blocks the browser API. */
export function telegramLocationManager(tg: TgWebApp | null): TgLocationManager | null {
  return tg?.LocationManager && tg.isVersionAtLeast('8.0') ? tg.LocationManager : null
}

export function haptic(tg: TgWebApp | null, type: 'success' | 'error' | 'warning' | 'light'): void {
  if (!tg?.HapticFeedback) return
  if (type === 'light') tg.HapticFeedback.impactOccurred('light')
  else tg.HapticFeedback.notificationOccurred(type)
}

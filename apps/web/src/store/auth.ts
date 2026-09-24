import { create } from 'zustand'
import type { Inspector, TokenResponse } from '@/api/types'
import { API_URL, toApiError } from '@/api/client'
import { authMode, supabase } from '@/lib/supabase'

const LOCAL_TOKEN_KEY = 'jer-local-token'

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthState {
  status: Status
  user: Inspector | null
  init: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  getAccessToken: () => Promise<string | null>
  handleUnauthorized: () => void
}

function readLocalToken(): string | null {
  try {
    return localStorage.getItem(LOCAL_TOKEN_KEY)
  } catch {
    return null
  }
}

function writeLocalToken(token: string | null) {
  try {
    if (token) localStorage.setItem(LOCAL_TOKEN_KEY, token)
    else localStorage.removeItem(LOCAL_TOKEN_KEY)
  } catch {
    // storage unavailable (private mode) — session lives in memory only
  }
}

let memoryToken: string | null = null

async function fetchMe(token: string): Promise<Inspector | null> {
  const response = await fetch(`${API_URL}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
  return response.ok ? ((await response.json()) as Inspector) : null
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'loading',
  user: null,

  async init() {
    if (authMode === 'supabase' && supabase) {
      const { data } = await supabase.auth.getSession()
      const session = data.session
      set(
        session
          ? { status: 'authenticated', user: userFromSupabase(session.user) }
          : { status: 'anonymous', user: null },
      )
      supabase.auth.onAuthStateChange((_event, next) => {
        set(
          next
            ? { status: 'authenticated', user: userFromSupabase(next.user) }
            : { status: 'anonymous', user: null },
        )
      })
      return
    }
    memoryToken = readLocalToken()
    const user = memoryToken ? await fetchMe(memoryToken).catch(() => null) : null
    if (!user) {
      memoryToken = null
      writeLocalToken(null)
    }
    set({ status: user ? 'authenticated' : 'anonymous', user })
  },

  async login(email, password) {
    if (authMode === 'supabase' && supabase) {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      set({ status: 'authenticated', user: userFromSupabase(data.user) })
      return
    }
    const response = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!response.ok) throw await toApiError(response)
    const body = (await response.json()) as TokenResponse
    memoryToken = body.access_token
    writeLocalToken(body.access_token)
    set({ status: 'authenticated', user: body.user })
  },

  async logout() {
    if (supabase) await supabase.auth.signOut()
    memoryToken = null
    writeLocalToken(null)
    set({ status: 'anonymous', user: null })
  },

  async getAccessToken() {
    if (authMode === 'supabase' && supabase) {
      const { data } = await supabase.auth.getSession()
      return data.session?.access_token ?? null
    }
    return memoryToken
  },

  handleUnauthorized() {
    if (get().status === 'authenticated') void get().logout()
  },
}))

function userFromSupabase(user: {
  id: string
  email?: string
  user_metadata?: Record<string, unknown>
}): Inspector {
  const meta = user.user_metadata ?? {}
  const name = (meta.full_name as string | undefined) ?? (meta.name as string | undefined) ?? user.email ?? ''
  return { id: user.id, email: user.email ?? null, name }
}

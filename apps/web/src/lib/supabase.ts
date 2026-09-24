import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

/** Supabase is used only for inspector Auth and Realtime; data goes through the API. */
export const supabase: SupabaseClient | null =
  url && anonKey
    ? createClient(url, anonKey, {
        auth: { persistSession: true, autoRefreshToken: true, storageKey: 'jer-auth' },
        realtime: { params: { eventsPerSecond: 10 } },
      })
    : null

export const authMode: 'supabase' | 'local' = supabase ? 'supabase' : 'local'

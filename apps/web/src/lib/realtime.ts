import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { create } from 'zustand'
import { api, unwrap } from '@/api/client'
import { qk } from '@/api/queries'
import type { EventOut } from '@/api/types'
import { supabase } from '@/lib/supabase'
import { useAuthStore } from '@/store/auth'

export type RealtimeMode = 'connecting' | 'realtime' | 'polling' | 'offline'

export const useRealtimeStatus = create<{ mode: RealtimeMode; set: (mode: RealtimeMode) => void }>((set) => ({
  mode: 'connecting',
  set: (mode) => set({ mode }),
}))

export interface SignalCreatedPayload {
  signal_id: string
  tracking_code: string
  lat: number
  lon: number
  parcel_id: string | null
  duplicate_of: string | null
}

const POLL_INTERVAL_MS = 5000

function invalidate(qc: QueryClient, event: Pick<EventOut, 'type' | 'payload'>) {
  const p = event.payload as Record<string, string | undefined>
  const inv = (queryKey: readonly unknown[]) => void qc.invalidateQueries({ queryKey })
  switch (event.type) {
    case 'signal.created':
      inv(['signals'])
      inv(qk.parcels)
      inv(qk.dashboard)
      if (p.parcel_id) inv(qk.parcel(p.parcel_id))
      if (p.duplicate_of) inv(qk.signal(p.duplicate_of))
      break
    case 'signal.status_changed':
      inv(['signals'])
      if (p.signal_id) inv(qk.signal(p.signal_id))
      if (p.parcel_id) inv(qk.parcel(p.parcel_id))
      inv(qk.dashboard)
      break
    case 'parcel.status_changed':
    case 'parcel.updated':
      inv(qk.parcels)
      inv(['violations'])
      inv(qk.dashboard)
      if (p.parcel_id) inv(qk.parcel(p.parcel_id))
      break
    case 'photo.added':
      if (p.owner_type === 'PARCEL' && p.owner_id) inv(qk.parcel(p.owner_id))
      if (p.owner_type === 'SIGNAL' && p.owner_id) {
        inv(qk.signal(p.owner_id))
        inv(['signals'])
      }
      break
    case 'application.status_changed':
      inv(['applications'])
      break
    case 'satellite.scan_completed':
      inv(qk.ndvi)
      inv(qk.parcels)
      break
    case 'satellite.history_ready':
      if (p.parcel_id) inv(['parcel-satellite', p.parcel_id])
      break
    case 'inspection.requested':
    case 'inspection.submitted':
    case 'inspection.reviewed':
    case 'inspection.plan_created':
      inv(['inspections'])
      inv(['inspection'])
      inv(['risk'])
      inv(['evidence'])
      break
    case 'demo.reset':
      void qc.invalidateQueries()
      break
  }
}

/**
 * Subscribes to domain events: Supabase Realtime (postgres_changes on `events`) when configured,
 * otherwise polling `/api/v1/events`. Falls back to polling if the socket fails.
 */
export function useRealtimeEvents(onSignalCreated: (payload: SignalCreatedPayload) => void) {
  const qc = useQueryClient()
  const authenticated = useAuthStore((s) => s.status === 'authenticated')
  const setMode = useRealtimeStatus((s) => s.set)
  const callback = useRef(onSignalCreated)
  useEffect(() => {
    callback.current = onSignalCreated
  }, [onSignalCreated])

  useEffect(() => {
    if (!authenticated) return
    let cancelled = false
    let pollTimer: number | undefined
    let lastId: number | null = null
    const seen = new Set<number>()
    let supabaseChannel: ReturnType<NonNullable<typeof supabase>['channel']> | null = null

    const handle = (event: EventOut) => {
      if (seen.has(event.id)) return
      seen.add(event.id)
      invalidate(qc, event)
      if (event.type === 'signal.created') callback.current(event.payload as unknown as SignalCreatedPayload)
    }

    const poll = async () => {
      try {
        const data = unwrap(
          await api.GET('/api/v1/events', { params: { query: lastId === null ? {} : { since: lastId } } }),
        )
        if (lastId !== null) data.items.forEach(handle)
        // After a demo reset the feed id never goes backwards (see ADR-008).
        lastId = data.last_id
        if (!cancelled) setMode(supabaseChannel ? 'realtime' : 'polling')
      } catch {
        if (!cancelled) setMode('offline')
      }
      if (!cancelled) pollTimer = window.setTimeout(poll, POLL_INTERVAL_MS)
    }

    const startPolling = () => {
      if (pollTimer === undefined && !cancelled) void poll()
    }

    if (supabase) {
      supabaseChannel = supabase
        .channel('jer-events')
        .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'events' }, (msg) => {
          handle(msg.new as EventOut)
        })
        .subscribe((status) => {
          if (cancelled) return
          if (status === 'SUBSCRIBED') setMode('realtime')
          if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
            supabaseChannel = null
            startPolling()
          }
        })
    } else {
      startPolling()
    }

    return () => {
      cancelled = true
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
      if (supabaseChannel && supabase) void supabase.removeChannel(supabaseChannel)
    }
  }, [authenticated, qc, setMode])
}

/** Short two-tone chime (Web Audio; no asset needed). */
export function playChime() {
  try {
    const AudioCtx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    const now = ctx.currentTime
    ;[880, 1320].forEach((freq, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.0001, now + i * 0.14)
      gain.gain.exponentialRampToValueAtTime(0.18, now + i * 0.14 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.14 + 0.35)
      osc.connect(gain).connect(ctx.destination)
      osc.start(now + i * 0.14)
      osc.stop(now + i * 0.14 + 0.4)
    })
    window.setTimeout(() => void ctx.close(), 1000)
  } catch {
    // autoplay blocked — the toast is enough
  }
}

import createClient, { type Middleware } from 'openapi-fetch'
import { useAuthStore } from '@/store/auth'
import type { paths } from './schema'

export const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: Record<string, unknown> }
}

export async function toApiError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {}
  try {
    body = (await response.clone().json()) as ErrorBody
  } catch {
    // non-JSON error (proxy, network) — keep defaults
  }
  return new ApiError(
    response.status,
    body.error?.code ?? `HTTP_${response.status}`,
    body.error?.message ?? response.statusText,
    body.error?.details ?? {},
  )
}

const auth: Middleware = {
  async onRequest({ request }) {
    const token = await useAuthStore.getState().getAccessToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
  async onResponse({ response }) {
    if (response.status === 401) useAuthStore.getState().handleUnauthorized()
    if (!response.ok) throw await toApiError(response)
    return response
  },
}

export const api = createClient<paths>({ baseUrl: API_URL })
api.use(auth)

/** Unwrap openapi-fetch results; errors are already thrown by the middleware. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    throw new ApiError(result.response.status, 'EMPTY_RESPONSE', 'Empty response from server')
  }
  return result.data
}

/** Multipart upload with progress (fetch has no upload progress). */
export function uploadWithProgress<T>(
  path: string,
  files: File[],
  onProgress: (fraction: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    void useAuthStore
      .getState()
      .getAccessToken()
      .then((token) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', `${API_URL}${path}`)
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) onProgress(event.loaded / event.total)
        }
        xhr.onload = () => {
          const body = (() => {
            try {
              return JSON.parse(xhr.responseText) as unknown
            } catch {
              return undefined
            }
          })()
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body as T)
            return
          }
          if (xhr.status === 401) useAuthStore.getState().handleUnauthorized()
          const err = (body as ErrorBody | undefined)?.error
          reject(
            new ApiError(
              xhr.status,
              err?.code ?? `HTTP_${xhr.status}`,
              err?.message ?? xhr.statusText,
              err?.details,
            ),
          )
        }
        xhr.onerror = () => reject(new ApiError(0, 'NETWORK_ERROR', 'Network error'))
        const form = new FormData()
        files.forEach((file) => form.append('files', file))
        xhr.send(form)
      })
  })
}

/** Authenticated file download (exports, PDF) that keeps the server-provided filename. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = await useAuthStore.getState().getAccessToken()
  const response = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw await toApiError(response)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const name = /filename="?([^"]+)"?/.exec(disposition)?.[1] ?? fallbackName
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

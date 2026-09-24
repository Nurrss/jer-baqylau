import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'

/** Human-readable, localized message for API/network errors. */
export function useErrorMessage() {
  const { t, i18n } = useTranslation()
  return (error: unknown): string => {
    if (error instanceof ApiError) {
      const key = `errors.${error.code}`
      if (i18n.exists(key)) return t(key)
      if (error.status === 0) return t('errors.NETWORK_ERROR')
      if (error.status >= 500) return t('errors.SERVER')
      return error.message
    }
    if (error instanceof Error && /fetch|network/i.test(error.message)) return t('errors.NETWORK_ERROR')
    return t('errors.UNKNOWN')
  }
}

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import kk from '@/locales/kk.json'
import ru from '@/locales/ru.json'

export const LANGUAGES = ['ru', 'kk'] as const
export type Language = (typeof LANGUAGES)[number]
const STORAGE_KEY = 'jer-lang'

function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'ru' || saved === 'kk') return saved
  } catch {
    // ignore
  }
  return navigator.language?.toLowerCase().startsWith('kk') ? 'kk' : 'ru'
}

void i18n.use(initReactI18next).init({
  resources: { ru: { translation: ru }, kk: { translation: kk } },
  lng: initialLanguage(),
  fallbackLng: 'ru',
  interpolation: { escapeValue: false },
  returnNull: false,
})

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
  try {
    localStorage.setItem(STORAGE_KEY, lng)
  } catch {
    // ignore
  }
})
document.documentElement.lang = i18n.language

export default i18n

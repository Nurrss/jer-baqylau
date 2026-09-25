import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Toaster } from 'sonner'
import { ApiError } from '@/api/client'
import { AppShell } from '@/components/layout/AppShell'
import { TooltipProvider } from '@/components/ui/misc'
import { ApplicationsPage } from '@/pages/ApplicationsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { HomePage } from '@/pages/HomePage'
import { LoginPage } from '@/pages/LoginPage'
import { MapPage } from '@/pages/MapPage'
import { SignalsPage } from '@/pages/SignalsPage'
import { ViolationsPage } from '@/pages/ViolationsPage'
import { useAuthStore } from '@/store/auth'
import { useUiStore } from '@/store/ui'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
})

function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status)
  const location = useLocation()
  if (status === 'loading') {
    return (
      <div className="grid h-full place-items-center">
        <Loader2 className="size-6 animate-spin text-primary" />
      </div>
    )
  }
  if (status === 'anonymous')
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <>{children}</>
}

export default function App() {
  const init = useAuthStore((s) => s.init)
  const theme = useUiStore((s) => s.theme)

  useEffect(() => {
    void init()
  }, [init])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <RequireAuth>
                  <AppShell />
                </RequireAuth>
              }
            >
              <Route index element={<HomePage />} />
              <Route path="map" element={<MapPage />} />
              <Route path="signals" element={<SignalsPage />} />
              <Route path="violations" element={<ViolationsPage />} />
              <Route path="applications" element={<ApplicationsPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-center" richColors closeButton theme={theme} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}

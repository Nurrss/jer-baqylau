import type { ReactNode } from 'react'

export function Section({
  title,
  icon,
  children,
  aside,
}: {
  title: string
  icon?: ReactNode
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <section className="border-t px-5 py-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          {icon}
          {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

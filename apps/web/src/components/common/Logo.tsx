export function Logo({ className }: { className?: string }) {
  // Placeholder emblem: stylized land parcel grid inside a shield.
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path d="M16 2 4 6.5v8.3C4 22.4 9.1 28.1 16 30c6.9-1.9 12-7.6 12-15.2V6.5L16 2Z" fill="#0b6aa8" />
      <path d="M16 2 28 6.5v8.3C28 22.4 22.9 28.1 16 30V2Z" fill="#095a90" />
      <path d="M9 11h6v5H9zM17 11h6v5h-6zM9 18h6v4.5H9zM17 18h6v4.5h-6z" fill="#f2b705" opacity=".95" />
    </svg>
  )
}

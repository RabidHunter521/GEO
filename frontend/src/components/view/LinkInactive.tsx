// frontend/src/components/view/LinkInactive.tsx
// Shown for invalid, revoked, or archived share links. Deliberately gives
// no hints about which state applies, and no path into the admin app.
export function LinkInactive() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-app-wash px-4">
      <div className="max-w-md rounded-xl border bg-card p-8 text-center shadow-brand">
        <p className="font-display text-lg font-bold tracking-tight text-primary">
          SeenBy
        </p>
        <h1 className="mt-4 font-display text-xl font-semibold">
          This link is no longer active
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Please contact your SeenBy consultant for a new link.
        </p>
      </div>
    </div>
  )
}

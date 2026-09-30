import { cn } from "@/lib/utils"

// shadcn/ui Skeleton. Pulses only when the viewer allows motion.
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-md bg-muted motion-safe:animate-pulse", className)} {...props} />
}

export { Skeleton }

"use client"

import { useState, useTransition } from "react"
import { ArrowDownUp, Check, Copy, KeyRound, Mail, Trash2, UserPlus, UserX, UserCheck } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { copyToClipboard } from "@/lib/utils"
import { timeAgo } from "@/lib/relative-time"
import type { TeamLinkIssued, TeamMember, TeamRole } from "@/types"
import { deleteAction, inviteAction, resetAction, setActiveAction, setRoleAction } from "./actions"

const STATUS_BADGE: Record<TeamMember["status"], { label: string; className: string }> = {
  active: { label: "Active", className: "bg-score-strong-bg text-score-strong border-score-strong/25" },
  invited: { label: "Invite pending", className: "bg-score-watch-bg text-score-watch-fg border-score-watch/30" },
  deactivated: { label: "Deactivated", className: "bg-muted text-muted-foreground" },
}

function IssuedLink({ issued, onClose }: { issued: TeamLinkIssued; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  return (
    <div role="status" className="space-y-2 rounded-lg border border-primary/25 bg-primary/5 p-4">
      <p className="text-sm font-medium">
        {issued.emailed
          ? `Setup link emailed to ${issued.user.email}.`
          : `The email to ${issued.user.email} couldn't be sent. Share this link with them directly:`}
      </p>
      <div className="flex gap-2">
        <Input readOnly value={issued.link} className="font-mono text-xs" aria-label="Setup link" />
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Copy setup link"
          onClick={async () => {
            const ok = await copyToClipboard(issued.link)
            setCopied(ok)
            toast[ok ? "success" : "error"](ok ? "Link copied" : "Couldn't copy — select it manually")
          }}
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Works once, for 48 hours. They choose a password and connect an authenticator app.
      </p>
      <Button type="button" variant="ghost" size="sm" onClick={onClose}>
        Done
      </Button>
    </div>
  )
}

function InviteForm({ onIssued }: { onIssued: (i: TeamLinkIssued) => void }) {
  const [role, setRole] = useState<TeamRole>("staff")
  const [pending, start] = useTransition()
  const [error, setError] = useState<string | null>(null)

  return (
    <form
      className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[1fr_1fr_140px_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        const form = e.currentTarget
        const fd = new FormData(form)
        setError(null)
        start(async () => {
          const res = await inviteAction(String(fd.get("email")), String(fd.get("name")), role)
          if (res.ok) {
            form.reset()
            setRole("staff")
            onIssued(res.data)
          } else {
            setError(res.error)
          }
        })
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="invite-name">Name</Label>
        <Input id="invite-name" name="name" required maxLength={255} placeholder="Full name" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="invite-email">Email</Label>
        <Input id="invite-email" name="email" type="email" required maxLength={255} placeholder="name@company.com" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="invite-role">Role</Label>
        <Select value={role} onValueChange={(v) => setRole(v as TeamRole)}>
          <SelectTrigger id="invite-role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="staff">Staff</SelectItem>
            <SelectItem value="owner">Owner</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button type="submit" disabled={pending}>
        <UserPlus className="mr-1.5 h-4 w-4" />
        {pending ? "Inviting…" : "Invite"}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-destructive sm:col-span-4">
          {error}
        </p>
      )}
    </form>
  )
}

function MemberRow({
  member,
  isSelf,
  onIssued,
}: {
  member: TeamMember
  isSelf: boolean
  onIssued: (i: TeamLinkIssued) => void
}) {
  const [pending, start] = useTransition()
  const badge = STATUS_BADGE[member.status]

  const reset = () =>
    start(async () => {
      const res = await resetAction(member.id)
      if (res.ok) onIssued(res.data)
      else toast.error(res.error)
    })
  const otherRole: TeamRole = member.role === "owner" ? "staff" : "owner"
  const setRole = () =>
    start(async () => {
      const res = await setRoleAction(member.id, otherRole)
      if (res.ok) toast.success(`${member.name} is now ${otherRole === "owner" ? "an owner" : "staff"}`)
      else toast.error(res.error)
    })
  const remove = () =>
    start(async () => {
      const res = await deleteAction(member.id)
      if (res.ok) toast.success(`${member.name} was deleted`)
      else toast.error(res.error)
    })
  const setActive = (active: boolean) =>
    start(async () => {
      const res = await setActiveAction(member.id, active)
      if (res.ok) toast.success(active ? `${member.name} can sign in again` : `${member.name} can no longer sign in`)
      else toast.error(res.error)
    })

  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 font-medium">
          {member.name}
          <Badge variant="outline" className="capitalize">
            {member.role}
          </Badge>
          <Badge variant="outline" className={badge.className}>
            {badge.label}
          </Badge>
        </p>
        <p className="truncate text-sm text-muted-foreground">{member.email}</p>
        <p className="text-xs text-muted-foreground">
          {member.status === "invited"
            ? "Hasn't set up their account yet"
            : member.last_login_at
              ? `Last signed in ${timeAgo(member.last_login_at)}`
              : "Never signed in"}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {/* Not on your own row: resetting yourself would lock you out, and the
            API refuses to deactivate the caller. */}
        {isSelf && <span className="text-xs text-muted-foreground">This is you</span>}
        {!isSelf && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="outline" size="sm" disabled={pending}>
                <ArrowDownUp className="mr-1.5 h-3.5 w-3.5" />
                {otherRole === "owner" ? "Make owner" : "Make staff"}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  Make {member.name} {otherRole === "owner" ? "an owner" : "staff"}?
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {otherRole === "owner"
                    ? "Owners can also manage the team, archive clients and publish benchmarks."
                    : "Staff can't manage the team, archive clients or publish benchmarks."}{" "}
                  {member.status === "invited"
                    ? "Their invite link keeps working."
                    : "It applies from their next click."}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={setRole}>
                  {otherRole === "owner" ? "Make owner" : "Make staff"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
        {member.is_active && !isSelf && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="outline" size="sm" disabled={pending}>
                {member.status === "invited" ? <Mail className="mr-1.5 h-3.5 w-3.5" /> : <KeyRound className="mr-1.5 h-3.5 w-3.5" />}
                {member.status === "invited" ? "Resend invite" : "Reset sign-in"}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {member.status === "invited" ? `Resend ${member.name}'s invite?` : `Reset ${member.name}'s sign-in?`}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {member.status === "invited"
                    ? "The previous link stops working and a new one is sent."
                    : "Their password and authenticator are cleared, so they can't sign in until they use the new link. Use this for a forgotten password or a lost phone."}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={reset}>Send new link</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
        {isSelf ? null : member.is_active ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="outline" size="sm" disabled={pending} className="text-destructive hover:text-destructive">
                <UserX className="mr-1.5 h-3.5 w-3.5" />
                Deactivate
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Deactivate {member.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  They are signed out of the API immediately and can&apos;t sign in. Their past work
                  stays in the activity log. You can reactivate them later.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => setActive(false)}>Deactivate</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <>
            <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => setActive(true)}>
              <UserCheck className="mr-1.5 h-3.5 w-3.5" />
              Reactivate
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="outline" size="sm" disabled={pending} className="text-destructive hover:text-destructive">
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                  Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete {member.name} permanently?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Their account is removed and can&apos;t be restored. Past activity still shows
                    their name. You can invite the same email again later.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={remove}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </>
        )}
      </div>
    </li>
  )
}

export function TeamManager({ members, currentUserId }: { members: TeamMember[]; currentUserId: string }) {
  const [issued, setIssued] = useState<TeamLinkIssued | null>(null)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Team</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everyone who can sign in to the admin panel. Each person has their own password and
          authenticator app. Staff can do everything except manage the team, archive clients and
          publish benchmarks. Change someone&apos;s role at any time; deactivate them before deleting.
        </p>
      </div>

      <InviteForm onIssued={setIssued} />
      {issued && <IssuedLink issued={issued} onClose={() => setIssued(null)} />}

      <ul className="divide-y rounded-lg border bg-card">
        {members.map((m) => (
          <MemberRow key={m.id} member={m} isSelf={m.id === currentUserId} onIssued={setIssued} />
        ))}
      </ul>
    </div>
  )
}

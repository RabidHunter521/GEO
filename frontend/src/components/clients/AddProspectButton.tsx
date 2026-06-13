// frontend/src/components/clients/AddProspectButton.tsx
"use client"

import { useState } from "react"
import { UserPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ProspectQuickForm } from "./ProspectQuickForm"

export function AddProspectButton() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <UserPlus className="h-4 w-4 mr-2" />
        Add Prospect
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Scan a Prospect</DialogTitle>
          </DialogHeader>
          <ProspectQuickForm onClose={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  )
}

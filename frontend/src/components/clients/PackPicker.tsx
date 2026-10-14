// frontend/src/components/clients/PackPicker.tsx
"use client"

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
  INDUSTRY_PACKS,
  subcategoriesFor,
  subcategoryLabel,
  suggestedPackFor,
  type PackChoice,
  type PackKey,
} from "@/lib/industry-packs"

const NONE = "__none__"

/**
 * Industry pack, subcategory and buyer term, chosen while a client is created.
 * The parent applies the industry's suggested pack (applyIndustryToChoice) until
 * the admin picks one here; this component only renders and reports changes.
 */
export function PackPicker({
  idPrefix,
  industry,
  value,
  onChange,
}: {
  idPrefix: string
  industry: string
  value: PackChoice
  onChange: (next: PackChoice) => void
}) {
  const suggestion = suggestedPackFor(industry)
  const subcategories = subcategoriesFor(value.pack)

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-pack`}>Industry pack</Label>
        <Select
          value={value.pack ?? NONE}
          onValueChange={(next) =>
            onChange({
              ...value,
              pack: next === NONE ? null : (next as PackKey),
              subcategory: null,
              packTouched: true,
            })
          }
        >
          <SelectTrigger id={`${idPrefix}-pack`} aria-describedby={`${idPrefix}-pack-help`}>
            <SelectValue placeholder="No pack (standard questions)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>No pack (standard questions)</SelectItem>
            {INDUSTRY_PACKS.map((pack) => (
              <SelectItem key={pack.key} value={pack.key}>
                {pack.label}
                {suggestion?.key === pack.key ? " (suggested)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p id={`${idPrefix}-pack-help`} className="text-xs text-muted-foreground">
          {!industry
            ? "Pick an industry first and we'll suggest a pack."
            : suggestion
              ? `Suggested for ${industry}. The pack decides which buyer questions this client is scanned on.`
              : `No pack fits ${industry} yet, so the standard questions are used. Fill in what buyers call this business below to keep them readable.`}
        </p>
      </div>

      {value.pack && subcategories.length > 0 && (
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-subcategory`}>Subcategory</Label>
          <Select
            value={value.subcategory ?? NONE}
            onValueChange={(next) =>
              onChange({ ...value, subcategory: next === NONE ? null : next })
            }
          >
            <SelectTrigger id={`${idPrefix}-subcategory`}>
              <SelectValue placeholder="Not set" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Not set</SelectItem>
              {subcategories.map((sub) => (
                <SelectItem key={sub} value={sub}>
                  {subcategoryLabel(sub)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-buyer-term`}>What buyers call this business</Label>
        <Input
          id={`${idPrefix}-buyer-term`}
          value={value.buyerTerm}
          maxLength={120}
          onChange={(e) => onChange({ ...value, buyerTerm: e.target.value })}
          placeholder="e.g. payment gateway, dental clinic, condo developer"
        />
        <p className="text-xs text-muted-foreground">
          Optional. Used in scan questions instead of the industry, e.g. &ldquo;Best payment
          gateway in Malaysia&rdquo;.
        </p>
      </div>
    </div>
  )
}

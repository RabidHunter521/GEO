// frontend/src/components/ui/searchable-select.tsx
// Typeahead combobox: type to narrow the list (prefix matches first), pick
// with mouse or keyboard. Used for country/state selection in client forms.
"use client"

import { useMemo, useRef, useState } from "react"
import { Check, ChevronDown } from "lucide-react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface Props {
  id?: string
  options: string[]
  value: string
  onChange: (value: string) => void
  placeholder?: string
  emptyMessage?: string
  disabled?: boolean
  /** Commit typed text as the value on blur even if it isn't in the list. */
  allowFreeText?: boolean
}

export function SearchableSelect({
  id,
  options,
  value,
  onChange,
  placeholder,
  emptyMessage = "No matches found",
  disabled,
  allowFreeText = false,
}: Props) {
  const [open, setOpen] = useState(false)
  // null = not editing → input shows the committed value
  const [query, setQuery] = useState<string | null>(null)
  const [highlighted, setHighlighted] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const filtered = useMemo(() => {
    const q = (query ?? "").trim().toLowerCase()
    if (!q) return options
    const starts = options.filter((o) => o.toLowerCase().startsWith(q))
    const contains = options.filter(
      (o) => !o.toLowerCase().startsWith(q) && o.toLowerCase().includes(q),
    )
    return [...starts, ...contains]
  }, [options, query])

  function commit(next: string) {
    onChange(next)
    setQuery(null)
    setOpen(false)
  }

  function handleBlur() {
    if (query !== null) {
      const exact = options.find((o) => o.toLowerCase() === query.trim().toLowerCase())
      if (exact) onChange(exact)
      else if (allowFreeText) onChange(query.trim())
      // else: revert to the previously committed value
    }
    setQuery(null)
    setOpen(false)
  }

  function scrollHighlightedIntoView(index: number) {
    listRef.current?.children[index]?.scrollIntoView({ block: "nearest" })
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      if (!open) return setOpen(true)
      const next = Math.min(highlighted + 1, filtered.length - 1)
      setHighlighted(next)
      scrollHighlightedIntoView(next)
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      const next = Math.max(highlighted - 1, 0)
      setHighlighted(next)
      scrollHighlightedIntoView(next)
    } else if (e.key === "Enter") {
      if (open && filtered[highlighted]) {
        e.preventDefault()
        commit(filtered[highlighted])
      }
    } else if (e.key === "Escape") {
      setQuery(null)
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <Input
        id={id}
        ref={inputRef}
        role="combobox"
        aria-expanded={open}
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        value={query ?? value}
        onFocus={() => {
          setOpen(true)
          setHighlighted(0)
        }}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
          setHighlighted(0)
        }}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        className="pr-8"
      />
      <ChevronDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      {open && (
        <ul
          ref={listRef}
          // preventDefault keeps the input focused so onBlur doesn't fire
          // before the option click registers
          onMouseDown={(e) => e.preventDefault()}
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {filtered.length === 0 && (
            <li className="px-2 py-1.5 text-sm text-muted-foreground">
              {emptyMessage}
            </li>
          )}
          {filtered.map((option, i) => (
            <li
              key={option}
              onClick={() => commit(option)}
              onMouseEnter={() => setHighlighted(i)}
              className={cn(
                "flex cursor-pointer items-center justify-between rounded-sm px-2 py-1.5 text-sm",
                i === highlighted && "bg-accent text-accent-foreground",
              )}
            >
              {option}
              {option === value && <Check className="h-4 w-4 shrink-0" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

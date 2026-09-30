import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { COMPANY_LEGAL_NAME, COMPANY_REGISTRATION_NUMBER } from "@/lib/company"

describe("company identity", () => {
  it("matches the backend constants", () => {
    const py = readFileSync(resolve(__dirname, "../../../../backend/app/core/constants.py"), "utf8")
    expect(py).toContain(`COMPANY_LEGAL_NAME: Final = "${COMPANY_LEGAL_NAME}"`)
    expect(py).toContain(`COMPANY_REGISTRATION_NUMBER: Final = "${COMPANY_REGISTRATION_NUMBER}"`)
  })
})

# Education Intelligence Pack — Design

**Status:** Draft for review
**Date:** 2026-08-08
**Scope:** K-12 and enrichment. Colleges, universities and vocational
institutes are deliberately OUT — see "Scope boundary" below.
**Depends on:** Phase 4 industry packs (shipped), pack schema profiles +
authority targets (merge `e2edf1c`), subcategory-scoped queries (merge
`f48ccbb`).

## Why this pack

Education scores on all six of the criteria that made healthcare, F&B and
local services worth building: parents demonstrably ask AI which school or
tuition centre to pick, the category is geographically anchored, it has a real
Malaysian directory ecosystem, and — the important one — it carries facts that
are consequential when wrong.

The risk asymmetry is close to healthcare's. A wrong fee costs a parent a
phone call. A false accreditation, an invented curriculum, or a fabricated
results claim can make a parent enrol a child for a qualification the school
cannot actually deliver, and they will not find out for a year. That asymmetry
is what the risk rules encode.

## Scope boundary

The pack covers the parent-buyer market. Higher education is excluded because
it introduces programme-level accreditation as an entire second risk
vocabulary, and swaps the parent buyer for an adult-learner buyer with
different queries. If higher ed is wanted later it should be its own pack, not
eight more subcategories here.

## Subcategories

```python
subcategories = (
    "tuition_centre", "enrichment", "kindergarten",
    "international_school", "private_school",
    "language_centre", "driving_school", "other_education",
)
```

## Schema profile

**Finding worth stating plainly: the schema axis pays less here than it did
for healthcare or F&B.** schema.org's `EducationalOrganization` has only six
subtypes (`CollegeOrUniversity`, `ElementarySchool`, `HighSchool`,
`MiddleSchool`, `Preschool`, `School`). `DrivingSchool` returns 404 and
`LanguageSchool` does not exist — both were verified against schema.org, not
assumed. Inventing either would put an invalid `@type` on a client's live
site, which is the exact failure the schema axis was built to prevent.

So only three subcategories get a genuine override:

| Subcategory | `@type` |
|---|---|
| `kindergarten` | `Preschool` |
| `international_school` | `School` |
| `private_school` | `School` |
| everything else | `EducationalOrganization` (default) |

The value instead comes from `guidance`, which is where education differs
structurally from every pack so far:

- Emit **`Course`** entries instead of the generic `Service` entries, one per
  programme or subject offered. `Course` is a real, widely-adopted type with
  `name`, `description`, `provider`, `educationalLevel` and `courseCode`.
  This is the single biggest structured-data win available to an education
  client and no other pack can use it.
- Do not emit `hasCredential`, `educationalCredentialAwarded`, or any
  accreditation property. Accreditation is a risk-sensitive fact and is
  published only after Truth Vault review.
- Do not emit named teacher or principal entries. Same reason healthcare
  refuses to emit `Physician`.
- Do not emit exam results, pass rates, placement rates, or any outcome
  claim, in any property or in the description.
- Do not emit `priceRange` or fee properties.

## Truth fields (20)

| fact_type | key | type | scope | flags |
|---|---|---|---|---|
| `teacher` | `name` | text | location | required |
| `teacher` | `qualification` | text | location | **risk** |
| `teacher` | `subjects` | list | location | |
| `teacher` | `languages` | list | location | |
| `programme` | `offered` | list | either | **risk**, required |
| `programme` | `curriculum` | text | either | **risk** |
| `programme` | `levels` | list | either | |
| `programme` | `class_size` | number | either | |
| `programme` | `not_offered` | list | either | |
| `accreditation` | `body` | text | either | **risk** |
| `accreditation` | `registration_number` | text | either | **risk** |
| `accreditation` | `valid_until` | text | either | |
| `outcomes` | `results_published` | text | either | **risk** |
| `outcomes` | `placements` | list | either | **risk** |
| `fees` | `range` | text | either | |
| `fees` | `registration_fee` | text | either | |
| `fees` | `payment_plans` | boolean | either | |
| `campus` | `name` | text | location | required |
| `campus` | `amenities` | list | location | |
| `campus` | `transport_provided` | boolean | location | |
| `admissions` | `intake_months` | list | either | |
| `admissions` | `age_range` | text | either | |
| `admissions` | `entrance_assessment` | boolean | either | |

`teacher` is location-scoped for the same reason `practitioner` is: a teacher
works at one campus, and a brand-scoped qualification would let one branch's
staff answer for every branch.

## Risk rules

Severity follows the harm asymmetry, not the effort to fix.

| id | target | severity |
|---|---|---|
| `false_accreditation` | `accreditation.body` | critical |
| `false_registration` | `accreditation.registration_number` | critical |
| `invented_curriculum` | `programme.curriculum` | critical |
| `invented_programme` | `programme.offered` | critical |
| `unsupported_results_claim` | `outcomes.*` | critical |
| `false_teacher_qualification` | `teacher.qualification` | high |
| `teacher_not_at_campus` | `teacher.name` | high |
| `wrong_fees` | `fees.range` | medium |
| `wrong_admissions` | `admissions.*` | medium |
| `wrong_campus_detail` | `campus.*` | low |

`invented_curriculum` is critical because a curriculum claim ("follows the
IB", "Cambridge IGCSE") is specific, checkable, and the single thing a parent
most relies on when comparing schools.

Every `review_instruction` describes what a reviewer should CHECK. None
asserts that anything is unlawful or improper — `validate_pack` already
rejects that vocabulary, and education is a sector where it would be
especially tempting and especially wrong.

## Query templates

12 generic + 14 subcategory-scoped (2 each across 7 real subcategories).
Every scoped template is anchored to `{brand}` or a location placeholder, so
it lands in the `brand` or `local` category — only `recommendation` and
`local` pay for position extraction, so an unanchored yes/no question would
buy an LLM call it cannot use.

**Generic (excerpt):**

- `brand_overview` — "What is {brand}?"
- `subject_discovery` — "Where can my child learn {subject} in {city}?"
- `brand_programmes` — "What subjects does {brand} teach?"
- `fees_check` — "How much are the fees at {brand}?"
- `reputation` — "Is {brand} a good school?"
- `admissions` — "How do I enrol my child at {brand}?"
- `brand_vs_competitor` — "{brand} vs {competitor}: which is better for my child?"
- `local_best` — "Best {industry} in {location}"

**Scoped (excerpt):**

| Subcategory | Query |
|---|---|
| `tuition_centre` | "Does {brand} offer small group classes for {subject}?" |
| `kindergarten` | "What is the teacher to child ratio at {brand}?" |
| `international_school` | "Which curriculum does {brand} follow?" |
| `private_school` | "What are the entry requirements for {brand}?" |
| `language_centre` | "How long does it take to learn {subject} at {brand}?" |
| `driving_school` | "How long does it take to get a licence with {brand}?" |
| `enrichment` | "What age can my child start at {brand}?" |

## Integration point — do not miss this

Two changes outside the pack file are REQUIRED, and skipping either produces a
pack that validates cleanly and then silently generates zero subject queries:

1. **`ALLOWED_PLACEHOLDERS`** in `app/industry_packs/base.py` gains `subject`
   and `level`. Without this, `validate_pack` rejects the templates at import.

2. **`_FACT_SOURCES`** in `app/services/pack_query_service.py` gains:

   ```python
   "subject": (("programme", "offered"),),
   "level":   (("programme", "levels"),),
   ```

   Without this, `_values_for` finds no source, every `{subject}` template is
   dropped as "missing placeholder", and the pack quietly loses half its
   queries. This is logged at DEBUG only.

New placeholders are preferred over overloading the existing `{service}` and
`{specialty}` because the templates then read correctly, and a healthcare
client has no `programme.offered` so nothing changes for existing packs.

## Authority targets

| key | name | type |
|---|---|---|
| `education_register` | Education authority register listing | directory |
| `schooladvisor` | SchoolAdvisor listing | directory |
| `eduadvisor` | EduAdvisor listing | directory |
| `afterschool_my` | Afterschool.my listing | directory |

**Priority:** `gbp`, `education_register`, `schooladvisor`, `facebook`.
Facebook is a priority here and not for healthcare — Malaysian parents
research schools through Facebook groups and pages to a degree that makes the
page a genuine authority asset, not just a social presence.

`education_register` deliberately carries no `provenance_domain`, matching
`medical_register` and `trade_licence_register`: which register applies is
country-specific and belongs in the Truth Vault, not hardcoded in a pack.

**Verify before implementing:** the three commercial directory domains above
are named from general knowledge and have NOT been checked. Confirm each
resolves and is still active before writing them into the pack — a dead
`url_hint` in the admin picker is a broken checklist item.

## Trusted sources

`official_website`, `education_authority_register`, `accreditation_body`,
`google_business_profile`, `recognized_directory`, `reviewed_publication`.

## What this does not change

- No schema change, no migration. `INDUSTRY_PACK_KEYS` is a plain tuple with
  no Postgres enum, by design.
- No score weight change, so no `SCORE_VERSION` bump.
- `MAX_PACK_QUERIES_PER_SCAN` stays 28.
- Existing packs and unpacked clients are untouched.

## Files

| File | Change |
|---|---|
| `app/core/constants.py` | add `"education"` to `INDUSTRY_PACK_KEYS` |
| `app/industry_packs/base.py` | add `subject`, `level` to `ALLOWED_PLACEHOLDERS` |
| `app/industry_packs/education.py` | new pack (~330 lines) |
| `app/industry_packs/__init__.py` | register on import |
| `app/services/pack_query_service.py` | extend `_FACT_SOURCES` |
| `frontend/src/lib/industry-packs.ts` | mirror entry (`PackKey` union + fields) |
| `backend/tests/test_education_pack.py` | new |
| `backend/tests/test_industry_pack_frontend_mirror.py` | passes once mirror lands |

## Acceptance

1. `validate_pack` accepts the pack at import; the registry reports four packs.
2. A `kindergarten` client's `schema.json` carries `"@type": "Preschool"` and
   `Course` entries rather than `Service`.
3. A `tuition_centre` client and an `international_school` client, given
   identical facts, produce measurably different query sets.
4. A client with approved `programme.offered` produces `{subject}` queries
   with no leaked braces — the proof that both integration points landed.
5. The authority picker offers the four education targets and no F&B or
   healthcare targets.
6. Banned-language scan clean; no generated output claims accreditation,
   registration or regulatory approval.

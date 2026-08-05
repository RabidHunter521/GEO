"""Cohort definition contracts for the Phase 6 benchmark engine.

Nothing here is client-facing. `CohortSpec` names the dimensions that make two
organizations comparable, and `CohortEligibility` explains, per client and per
period, whether they counted and why. Both are operator/audit surfaces; the
client-safe comparison schema is a separate, whitelisted shape (Task 4).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import (
    BENCHMARK_COVERAGE_BANDS,
    BENCHMARK_DEFINITION_VERSION,
    BENCHMARK_MAX_STALENESS_DAYS,
    BENCHMARK_MERGED_SCALE_BANDS,
    BENCHMARK_MIN_COVERAGE,
    BENCHMARK_SCALE_BANDS,
    MIN_COHORT_MEMBER_FLOOR,
)

# Sentinel used in the cohort key for a dimension that is deliberately absent,
# so "no subcategory recorded" and "subcategory literally named *" can never
# collide into the same key.
ABSENT = "*"


class CohortDefinitionConfig(BaseModel):
    """Versioned thresholds behind a cohort definition.

    Bundled into one versioned object rather than read as loose constants so a
    threshold change is forced to mint a new `definition_version` — a snapshot
    can then always be traced back to the exact rules that produced it.
    """

    model_config = ConfigDict(frozen=True)

    definition_version: str = BENCHMARK_DEFINITION_VERSION
    scale_bands: dict[str, tuple[int, int]] = Field(
        default_factory=lambda: dict(BENCHMARK_SCALE_BANDS)
    )
    merged_scale_bands: dict[str, str] = Field(
        default_factory=lambda: dict(BENCHMARK_MERGED_SCALE_BANDS)
    )
    coverage_bands: dict[str, tuple[int, int]] = Field(
        default_factory=lambda: dict(BENCHMARK_COVERAGE_BANDS)
    )
    min_coverage: int = BENCHMARK_MIN_COVERAGE
    max_staleness_days: int = BENCHMARK_MAX_STALENESS_DAYS
    min_member_count: int = MIN_COHORT_MEMBER_FLOOR
    # None means "accept whatever prompt version produced the samples". A tuple
    # pins the cohort to specific measurement versions, so a prompt rewrite can
    # be prevented from silently mixing into an existing comparison.
    supported_measurement_versions: tuple[str, ...] | None = None


class CohortSpec(BaseModel):
    """The dimensions that define one comparable population."""

    model_config = ConfigDict(frozen=True)

    industry_pack: str
    subcategory: str | None = None
    country_code: str
    market_area: str | None = None
    scale_band: str
    coverage_band: str
    period_type: str = "month"
    definition_version: str = BENCHMARK_DEFINITION_VERSION

    @property
    def cohort_key(self) -> str:
        return "|".join(
            (
                self.industry_pack,
                self.subcategory or ABSENT,
                self.country_code,
                self.market_area or ABSENT,
                self.scale_band,
                self.coverage_band,
                self.period_type,
            )
        )


class CohortEligibility(BaseModel):
    """Why one client did or did not count toward a cohort in one period.

    `reason_codes` is empty exactly when `eligible` is True, and carries every
    failing rule rather than the first one — an operator fixing a client's
    exclusion should not have to re-run to discover the next reason.
    """

    client_id: uuid.UUID
    eligible: bool
    reason_codes: list[str] = Field(default_factory=list)
    spec: CohortSpec | None = None
    location_count: int = 0
    measurement_coverage: int = 0
    measurement_version: str | None = None
    last_observed_at: datetime | None = None

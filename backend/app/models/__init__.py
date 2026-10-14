from app.models.outcome_action import (
    OUTCOME_ACTION_STATUSES,
    OUTCOME_ACTION_TYPES,
    OutcomeAction,
)
from app.models.business_location import BusinessLocation
from app.models.truth_fact import TruthFact, TruthFactVersion, TRUTH_FACT_VERSION_STATUSES
from app.models.tracked_query import TrackedQuery
from app.models.conversion_event import ConversionEvent
from app.models.attribution_setting import AttributionSetting
from app.models.attribution_signal import AttributionSignal
from app.models.search_query_signal import SearchQuerySignal
from app.models.benchmark_cohort import (
    BenchmarkCohort,
    BenchmarkCohortMembership,
)
from app.models.benchmark_snapshot import (
    ApprovedSnapshotImmutableError,
    BenchmarkSnapshot,
)
from app.models.benchmark_publication import (
    BENCHMARK_PUBLICATION_STATUSES,
    ApprovedPublicationImmutableError,
    BenchmarkPublication,
)
from app.models.misinformation_finding import MisinformationFinding

from app.models.workspace import Workspace
from app.models.user import User, USER_ROLES
from app.models.client_win import ClientWin

# Load every model module, so the metadata is complete whenever this package is
# imported. A ForeignKey to a table whose module nobody imported fails only when
# a row is first flushed: in the worker that was the first scan after each deploy
# (outcome_actions -> work_log_entries), which silently dropped the recommended
# actions for that scan.
import importlib as _importlib
import pkgutil as _pkgutil

for _module in _pkgutil.iter_modules(__path__):
    _importlib.import_module(f"{__name__}.{_module.name}")

__all__ = [
    "AttributionSetting",
    "AttributionSignal",
    "OUTCOME_ACTION_STATUSES",
    "OUTCOME_ACTION_TYPES",
    "OutcomeAction",
    "BusinessLocation",
    "TruthFact",
    "TruthFactVersion",
    "TRUTH_FACT_VERSION_STATUSES",
    "TrackedQuery",
    "ConversionEvent",
    "SearchQuerySignal",
    "BenchmarkCohort",
    "BenchmarkCohortMembership",
    "ApprovedSnapshotImmutableError",
    "BenchmarkSnapshot",
    "BENCHMARK_PUBLICATION_STATUSES",
    "ApprovedPublicationImmutableError",
    "BenchmarkPublication",
    "MisinformationFinding",
    "Workspace",
    "User",
    "USER_ROLES",
    "ClientWin",
]

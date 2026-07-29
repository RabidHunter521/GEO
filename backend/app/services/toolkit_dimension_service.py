from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ToolkitDimensionState:
    technical_foundations_verified: bool
    structured_data_verified: bool


def derive_toolkit_dimensions(
    results: Mapping[str, bool],
) -> ToolkitDimensionState:
    return ToolkitDimensionState(
        technical_foundations_verified=bool(results["robots_verified"]),
        structured_data_verified=bool(results["schema_verified"]),
    )

from __future__ import annotations

from typing import Any, TypedDict


class ZoneState(TypedDict, total=False):
    # Input
    address: str
    radius_m: float
    job_id: str
    started_at: float

    # Written by zone_resolver_agent
    center_lat: float
    center_lon: float
    candidates: list[dict[str, Any]]
    enumeration_method: str  # "bdnb_bulk" | "grid_fallback"

    # Written by collector_fanout_agent
    building_results: list[dict[str, Any]]

    # Written by aggregator_agent
    aggregate: dict[str, Any]

    # Written by report_agent (final output)
    report: dict[str, Any]

    # Progress callback
    on_progress: Any

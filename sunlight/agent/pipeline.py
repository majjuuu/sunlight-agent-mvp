"""Fixed-script baseline: geocode -> buildings -> climate -> engine.

This is the ablation arm for the paper ("why an agent and not a script?").
It handles exactly one input shape (a geocodable address + explicit floor and
facade) and fails hard on anything else - no input resolution, no recovery,
no interpretation. Comparing its task-success rate against the agent's on the
messy-input benchmark is Evaluation #2/#4.
"""

from __future__ import annotations

from sunlight.tools.assess import compute_direct_sun_hours
from sunlight.tools.buildings import fetch_building_context
from sunlight.tools.climate import fetch_climate
from sunlight.tools.geocode import geocode


def run_pipeline(
    address: str,
    floor: int,
    facade_azimuth_deg: float,
    radius_m: int = 300,
) -> dict:
    """Deterministic end-to-end assessment. Raises on any missing data."""
    geo = geocode(address)
    if not geo.get("found"):
        raise ValueError(f"geocoding failed for {address!r}")
    buildings = fetch_building_context(geo["lat"], geo["lon"], radius_m)
    climate = fetch_climate(geo["lat"], geo["lon"])
    result = compute_direct_sun_hours(
        lat=geo["lat"],
        lon=geo["lon"],
        floor=floor,
        facade_azimuth_deg=facade_azimuth_deg,
        buildings_payload=buildings,
        monthly_sunshine_fraction=climate["monthly_sunshine_fraction"],
    )
    return {
        "mode": "fixed_pipeline",
        "location": {k: geo[k] for k in ("lat", "lon", "display_name")},
        "assessment": result,
        "buildings_payload": buildings,
    }

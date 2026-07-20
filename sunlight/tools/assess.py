"""The agent-facing wrapper around the deterministic engine.

compute_direct_sun_hours() is the ONLY path from the agent to sunlight
numbers. It takes JSON, calls the engine, returns JSON. The LLM never gets
to write these fields itself.
"""

from __future__ import annotations

from sunlight.engine.geometry import TargetPoint
from sunlight.engine.simulate import apply_climate, simulate_year
from sunlight.tools.buildings import to_engine_buildings

STOREY_M = 3.0
WINDOW_OFFSET_M = 1.5  # window mid-height above the floor slab

# Livability-of-light score references (documented in the paper):
#   winter: 4 h/day of direct winter sun ~= excellent for Seoul latitudes
#   annual: 2000 expected hours/yr ~= a very sunny unobstructed south unit
WINTER_REF_DAILY_H = 4.0
ANNUAL_REF_H = 2000.0
SCORE_WEIGHTS = {"winter": 0.45, "annual": 0.35, "obstruction": 0.20}


def compute_livability_score(result: dict) -> dict:
    """0-100 score from the engine metrics. Pure arithmetic - the formula is
    returned alongside the number so reports can show their work."""
    monthly = result["monthly_avg_daily_hours"]
    winter_daily = sum(monthly.get(m, 0.0) for m in (12, 1, 2)) / 3.0
    annual = (
        result.get("climate_corrected", {}).get("annual_expected_hours")
        or result["annual_direct_hours"]
    )
    winter_c = min(1.0, winter_daily / WINTER_REF_DAILY_H)
    annual_c = min(1.0, annual / ANNUAL_REF_H)
    obstruction_c = 1.0 - result["obstruction_loss_pct"] / 100.0
    w = SCORE_WEIGHTS
    score = 100.0 * (w["winter"] * winter_c + w["annual"] * annual_c + w["obstruction"] * obstruction_c)
    return {
        "score": round(score),
        "components": {
            "winter_sun": round(winter_c, 3),
            "annual_sun": round(annual_c, 3),
            "unobstructedness": round(obstruction_c, 3),
        },
        "formula": (
            f"100 * ({w['winter']} * min(1, winter_daily_h/{WINTER_REF_DAILY_H})"
            f" + {w['annual']} * min(1, annual_expected_h/{ANNUAL_REF_H:.0f})"
            f" + {w['obstruction']} * (1 - obstruction_loss))"
        ),
        "inputs": {
            "winter_daily_h": round(winter_daily, 2),
            "annual_expected_h": round(float(annual), 1),
            "obstruction_loss_pct": result["obstruction_loss_pct"],
        },
    }


_tz_finder = None


def local_timezone(lat: float, lon: float) -> str:
    """IANA timezone at the point, so hourly profiles are in local clock time."""
    global _tz_finder
    if _tz_finder is None:
        from timezonefinder import TimezoneFinder

        _tz_finder = TimezoneFinder()
    return _tz_finder.timezone_at(lat=lat, lng=lon) or "UTC"


def compute_direct_sun_hours(
    lat: float,
    lon: float,
    floor: int,
    facade_azimuth_deg: float | None,
    buildings_payload: dict,
    monthly_sunshine_fraction: dict | None = None,
    year: int = 2025,
    step_minutes: int = 30,
    tz: str | None = None,
) -> dict:
    """Annual/monthly/representative-day direct sun for one unit."""
    tz = tz or local_timezone(lat, lon)
    height = max(0.0, (floor - 1) * STOREY_M) + WINDOW_OFFSET_M
    target = TargetPoint(lat=lat, lon=lon, height_m=height, facade_azimuth_deg=facade_azimuth_deg)
    result = simulate_year(
        target, to_engine_buildings(buildings_payload), year=year, step_minutes=step_minutes, tz=tz
    )

    out = {
        "assumptions": {
            "timezone": tz,
            "floor": floor,
            "window_height_m": round(height, 1),
            "storey_height_m": STOREY_M,
            "facade_azimuth_deg": facade_azimuth_deg,
            "year": year,
            "step_minutes": step_minutes,
        },
        "annual_direct_hours": result.annual_direct_hours,
        "annual_facade_potential_hours": result.annual_facade_potential_hours,
        "annual_sun_up_hours": result.annual_sun_up_hours,
        "obstruction_loss_pct": result.obstruction_loss_pct,
        "monthly_direct_hours": result.monthly_direct_hours,
        "monthly_avg_daily_hours": result.monthly_avg_daily_hours,
        "representative_days": result.representative_days,
        "target_inside_building": result.target_inside_building,
        "data_quality": buildings_payload.get("stats", {}),
    }
    if monthly_sunshine_fraction:
        fraction = {int(k): float(v) for k, v in monthly_sunshine_fraction.items()}
        out["climate_corrected"] = apply_climate(result.monthly_direct_hours, fraction)
    out["livability_score"] = compute_livability_score(out)
    return out

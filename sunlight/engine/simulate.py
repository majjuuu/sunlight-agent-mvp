"""Direct-sun-hours simulation: sun path x horizon profile x facade orientation.

Pure computation - no network, no LLM. The agent layer treats this module as
an oracle and never overrides its numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from sunlight.engine.geometry import Building, HorizonProfile, TargetPoint, build_horizon
from sunlight.engine.sunpath import year_sun_positions

REPRESENTATIVE_DAYS = {
    "winter_solstice": "12-21",
    "spring_equinox": "03-20",
    "summer_solstice": "06-21",
}


@dataclass
class SimulationResult:
    """All geometric sun metrics for one target point."""

    annual_direct_hours: float                 # obstruction- and facade-aware
    annual_facade_potential_hours: float       # facade-aware, obstruction-free
    annual_sun_up_hours: float                 # daylight hours (altitude > 0)
    monthly_direct_hours: dict[int, float]     # month -> total geometric hours
    monthly_avg_daily_hours: dict[int, float]  # month -> mean hours/day
    representative_days: dict[str, list[dict]]  # day -> hourly profile
    obstruction_loss_pct: float                # share of facade-potential lost to blockers
    target_inside_building: str | None
    timeseries: pd.DataFrame = field(repr=False, default=None)


def simulate_year(
    target: TargetPoint,
    buildings: list[Building],
    year: int = 2025,
    step_minutes: int = 30,
    tz: str = "Asia/Seoul",
    horizon: HorizonProfile | None = None,
) -> SimulationResult:
    """Compute when direct sun reaches the target over a full year."""
    if horizon is None:
        horizon = build_horizon(target, buildings)

    sun = year_sun_positions(target.lat, target.lon, year, step_minutes, tz)
    alt = sun["altitude"].to_numpy()
    az = sun["azimuth"].to_numpy()

    sun_up = alt > 0.0
    if target.facade_azimuth_deg is None:
        facade_ok = np.ones_like(sun_up)
    else:
        # Direct sun can enter the window only from the front hemisphere.
        rel = np.radians(az - target.facade_azimuth_deg)
        facade_ok = np.cos(rel) > 0.0
    unobstructed = alt > horizon.elevation_at(az)
    direct = sun_up & facade_ok & unobstructed

    step_h = step_minutes / 60.0
    ts = sun.assign(sun_up=sun_up, facade_ok=facade_ok, unobstructed=unobstructed, direct=direct)

    monthly = ts.groupby(ts.index.month)["direct"].sum() * step_h
    days_in_month = ts.groupby(ts.index.month)["direct"].count() * step_h / 24.0
    monthly_avg = monthly / days_in_month

    facade_potential = float((sun_up & facade_ok).sum()) * step_h
    direct_total = float(direct.sum()) * step_h
    loss = 0.0 if facade_potential == 0 else 100.0 * (1.0 - direct_total / facade_potential)

    rep = {}
    for name, mmdd in REPRESENTATIVE_DAYS.items():
        day = ts[ts.index.strftime("%m-%d") == mmdd]
        rep[name] = [
            {
                "time": t.strftime("%H:%M"),
                "altitude": round(float(r["altitude"]), 1),
                "azimuth": round(float(r["azimuth"]), 1),
                "direct_sun": bool(r["direct"]),
            }
            for t, r in day.iterrows()
            if r["altitude"] > -5.0
        ]

    return SimulationResult(
        annual_direct_hours=round(direct_total, 1),
        annual_facade_potential_hours=round(facade_potential, 1),
        annual_sun_up_hours=round(float(sun_up.sum()) * step_h, 1),
        monthly_direct_hours={int(m): round(float(v), 1) for m, v in monthly.items()},
        monthly_avg_daily_hours={int(m): round(float(v), 2) for m, v in monthly_avg.items()},
        representative_days=rep,
        obstruction_loss_pct=round(loss, 1),
        target_inside_building=horizon.target_inside_building,
        timeseries=ts,
    )


def apply_climate(
    monthly_geometric_hours: dict[int, float],
    monthly_sunshine_fraction: dict[int, float],
) -> dict:
    """Convert geometric sun-hours into climate-expected sun-hours.

    sunshine_fraction is the monthly ratio of actual bright sunshine to the
    astronomically possible amount (from PVGIS / NASA POWER). Multiplying is
    the standard first-order cloudiness correction.
    """
    expected = {
        m: round(h * monthly_sunshine_fraction.get(m, 1.0), 1)
        for m, h in monthly_geometric_hours.items()
    }
    return {
        "monthly_expected_hours": expected,
        "annual_expected_hours": round(sum(expected.values()), 1),
        "annual_geometric_hours": round(sum(monthly_geometric_hours.values()), 1),
    }

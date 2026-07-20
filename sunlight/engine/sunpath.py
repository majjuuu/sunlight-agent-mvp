"""Sun-position computation via pvlib (NREL SPA). Pure and deterministic."""

from __future__ import annotations

import pandas as pd
import pvlib


def sun_positions(
    lat: float,
    lon: float,
    start: str,
    end: str,
    step_minutes: int = 30,
    tz: str = "Asia/Seoul",
) -> pd.DataFrame:
    """Sun altitude/azimuth for every timestep in [start, end).

    Returns a DataFrame indexed by tz-aware timestamps with columns:
      altitude  - apparent solar elevation in degrees (refraction-corrected)
      azimuth   - compass azimuth in degrees (0=N, 90=E, 180=S, 270=W)
    """
    times = pd.date_range(start=start, end=end, freq=f"{step_minutes}min", tz=tz, inclusive="left")
    solpos = pvlib.solarposition.get_solarposition(times, lat, lon)
    return pd.DataFrame(
        {
            "altitude": solpos["apparent_elevation"],
            "azimuth": solpos["azimuth"],
        },
        index=times,
    )


def year_sun_positions(
    lat: float,
    lon: float,
    year: int = 2025,
    step_minutes: int = 30,
    tz: str = "Asia/Seoul",
) -> pd.DataFrame:
    """Sun positions over one full calendar year."""
    return sun_positions(lat, lon, f"{year}-01-01", f"{year + 1}-01-01", step_minutes, tz)

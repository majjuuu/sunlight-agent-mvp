"""Climate correction from NASA POWER climatology (free, no key).

Geometric sun-hours say when the sun COULD hit the window; clouds decide how
often it actually does. The monthly ratio of all-sky to clear-sky surface
shortwave irradiance is a standard first-order sunshine-fraction proxy.
"""

from __future__ import annotations

import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
MONTH_KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def fetch_climate(lat: float, lon: float) -> dict:
    """Monthly sunshine fraction (0..1) for the location.

    Returns {monthly_sunshine_fraction: {1: f, ..., 12: f}, source, note}.
    """
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN",
        "community": "RE",
        "latitude": lat,
        "longitude": lon,
        "format": "JSON",
    }
    resp = requests.get(POWER_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()["properties"]["parameter"]
    allsky, clrsky = data["ALLSKY_SFC_SW_DWN"], data["CLRSKY_SFC_SW_DWN"]

    fraction = {}
    for i, key in enumerate(MONTH_KEYS, start=1):
        a, c = allsky.get(key), clrsky.get(key)
        if a is None or c is None or c <= 0 or a < 0:
            fraction[i] = 0.6  # conservative fallback
        else:
            fraction[i] = round(min(1.0, max(0.0, a / c)), 3)

    return {
        "monthly_sunshine_fraction": fraction,
        "source": "NASA POWER climatology (all-sky / clear-sky shortwave ratio)",
        "note": "first-order cloudiness proxy; not a per-hour forecast",
    }

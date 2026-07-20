"""Geocoding via OSM Nominatim (free, no key). Global; V-World can be added later."""

from __future__ import annotations

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "sunlight-agent-research/0.1 (yonseidesignitlab@gmail.com)"


def geocode(query: str, country_bias: str | None = None) -> dict:
    """Resolve an address or place name to lat/lon (worldwide).

    Returns {found, lat, lon, display_name, confidence_note} - the agent uses
    confidence_note to decide whether to double-check with the user.
    country_bias ("kr", "us", ...) optionally restricts results to one country.
    """
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 3,
        "accept-language": "en,ko",
    }
    if country_bias:
        params["countrycodes"] = country_bias
    resp = requests.get(
        NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return {"found": False, "note": "no geocoding match; try a simpler or road-name address"}
    best = results[0]
    return {
        "found": True,
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
        "display_name": best.get("display_name", ""),
        "osm_type": best.get("osm_type", ""),
        "confidence_note": (
            "single match" if len(results) == 1 else f"{len(results)} candidates; using the first"
        ),
        "alternatives": [r.get("display_name", "") for r in results[1:]],
    }

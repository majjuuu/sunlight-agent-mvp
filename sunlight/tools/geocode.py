"""Geocoding with a provider chain.

Order (first hit wins):
  1. Google Places Text Search (New)  - if GOOGLE_MAPS_API_KEY is set. Returns
     the same top result the Google Maps search box shows; best for landmark /
     building / campus names worldwide.
  2. Photon (Komoot)                   - free, no key, OSM-based fuzzy search.
  3. Nominatim (OSM)                   - free, no key, final fallback.

The free OSM providers frequently mis-resolve US campus/building names (e.g.
"University of Michigan Union" -> a credit union), which is why Google is the
preferred primary when a key is available.
"""

from __future__ import annotations

import os

import requests

from sunlight.config import load_env

load_env()

USER_AGENT = "sunlight-agent-research/0.1 (yonseidesignitlab@gmail.com)"
GOOGLE_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def _google(query: str) -> dict | None:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            GOOGLE_TEXT_SEARCH,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            },
            json={"textQuery": query, "maxResultCount": 3},
            timeout=20,
        )
        if resp.status_code != 200:
            # 403 = API not enabled / key restricted; fall through to free providers.
            return {"_error": f"google {resp.status_code}: {resp.text[:160]}"}
        places = resp.json().get("places", [])
        if not places:
            return None
        best = places[0]
        loc = best["location"]
        return {
            "found": True,
            "lat": float(loc["latitude"]),
            "lon": float(loc["longitude"]),
            "display_name": best.get("formattedAddress")
            or best.get("displayName", {}).get("text", ""),
            "provider": "google_places",
            "confidence_note": "top Google Maps result",
            "alternatives": [
                p.get("formattedAddress", "") for p in places[1:]
            ],
        }
    except requests.RequestException as e:
        return {"_error": f"google request failed: {e}"}


def _photon(query: str) -> dict | None:
    try:
        resp = requests.get(
            PHOTON_URL,
            params={"q": query, "limit": 3},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        feats = resp.json().get("features", [])
        if not feats:
            return None
        p = feats[0]["properties"]
        lon, lat = feats[0]["geometry"]["coordinates"]
        name = ", ".join(
            str(p[k]) for k in ("name", "street", "city", "state", "country") if p.get(k)
        )
        return {
            "found": True,
            "lat": float(lat),
            "lon": float(lon),
            "display_name": name,
            "provider": "photon",
            "confidence_note": "OSM fuzzy match (Photon); verify landmark names",
            "alternatives": [],
        }
    except requests.RequestException as e:
        return {"_error": f"photon request failed: {e}"}


def _nominatim(query: str, country_bias: str | None) -> dict | None:
    params = {"q": query, "format": "jsonv2", "limit": 3, "accept-language": "en,ko"}
    if country_bias:
        params["countrycodes"] = country_bias
    try:
        resp = requests.get(
            NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        best = results[0]
        return {
            "found": True,
            "lat": float(best["lat"]),
            "lon": float(best["lon"]),
            "display_name": best.get("display_name", ""),
            "provider": "nominatim",
            "confidence_note": (
                "single match" if len(results) == 1 else f"{len(results)} candidates; using the first"
            ),
            "alternatives": [r.get("display_name", "") for r in results[1:]],
        }
    except requests.RequestException as e:
        return {"_error": f"nominatim request failed: {e}"}


def geocode(query: str, country_bias: str | None = None) -> dict:
    """Resolve an address or place name to lat/lon (worldwide).

    Tries Google (if keyed) -> Photon -> Nominatim, returning the first solid
    hit. `country_bias` ("kr", "us", ...) only constrains the Nominatim step.
    Returns {found, lat, lon, display_name, provider, confidence_note, ...}.
    """
    errors: list[str] = []
    for fn in (
        lambda: _google(query),
        lambda: _photon(query),
        lambda: _nominatim(query, country_bias),
    ):
        res = fn()
        if res is None:
            continue
        if res.get("_error"):
            errors.append(res["_error"])
            continue
        if res.get("found"):
            if errors:
                res["provider_notes"] = errors  # earlier providers that failed
            return res
    return {
        "found": False,
        "note": "no geocoding match across providers; try a simpler or road-name address",
        "provider_errors": errors,
    }

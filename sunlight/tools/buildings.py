"""Building footprints + heights from OpenStreetMap Overpass.

Height resolution order (each step down is flagged as more estimated):
  1. `height` tag (measured/entered)          -> height_estimated=False
  2. `building:levels` x 3.0 m per storey      -> height_estimated=True
  3. neither                                   -> DEFAULT_LEVELS x 3.0 m, flagged

Korea note: OSM height coverage in Seoul is uneven. The V-World national GIS
has authoritative building heights; plug it in here as a second source when
an API key is available.
"""

from __future__ import annotations

import re

import requests

from sunlight.engine.geometry import Building

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [
    OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "sunlight-agent-research/0.1 (yonseidesignitlab@gmail.com)"
STOREY_M = 3.0
DEFAULT_LEVELS = 2


def _parse_height(tags: dict) -> tuple[float, bool, str]:
    """-> (height_m, estimated?, how)"""
    raw = tags.get("height") or tags.get("building:height")
    if raw:
        m = re.match(r"^\s*([\d.]+)", str(raw))
        if m:
            return float(m.group(1)), False, "osm height tag"
    levels = tags.get("building:levels")
    if levels:
        m = re.match(r"^\s*([\d.]+)", str(levels))
        if m:
            return float(m.group(1)) * STOREY_M, True, f"levels tag ({m.group(1)}) x {STOREY_M} m"
    return DEFAULT_LEVELS * STOREY_M, True, f"no data; assumed {DEFAULT_LEVELS} storeys"


def fetch_building_context(lat: float, lon: float, radius_m: int = 300) -> dict:
    """All building footprints within radius_m of the point.

    Returns {buildings: [...], stats: {...}} where each building carries its
    footprint ring, height, and an explicit estimated flag - the agent must
    report estimate coverage to the user.
    """
    query = f"""
    [out:json][timeout:60];
    (
      way["building"](around:{radius_m},{lat},{lon});
      relation["building"](around:{radius_m},{lat},{lon});
    );
    out tags geom;
    """
    last_err: Exception | None = None
    elements = None
    for url in OVERPASS_MIRRORS:
        try:
            resp = requests.post(
                url, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=90
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except requests.RequestException as e:  # try the next mirror
            last_err = e
    if elements is None:
        raise RuntimeError(f"all Overpass mirrors failed: {last_err}")

    buildings: list[dict] = []
    n_measured = 0
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "way":
            geom = el.get("geometry")
            if not geom or len(geom) < 4:
                continue
            ring = [(p["lon"], p["lat"]) for p in geom]
        elif el["type"] == "relation":
            outer = next(
                (m for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")),
                None,
            )
            if not outer or len(outer["geometry"]) < 4:
                continue
            ring = [(p["lon"], p["lat"]) for p in outer["geometry"]]
        else:
            continue
        height, estimated, how = _parse_height(tags)
        if not estimated:
            n_measured += 1
        buildings.append(
            {
                "source_id": f"{el['type']}/{el['id']}",
                "footprint_lonlat": ring,
                "height_m": height,
                "height_estimated": estimated,
                "height_source": how,
                "name": tags.get("name", ""),
                "levels": tags.get("building:levels", ""),
            }
        )

    return {
        "buildings": buildings,
        "stats": {
            "count": len(buildings),
            "with_measured_height": n_measured,
            "with_estimated_height": len(buildings) - n_measured,
            "radius_m": radius_m,
            "source": "OpenStreetMap Overpass",
        },
    }


def to_engine_buildings(payload: dict) -> list[Building]:
    """Convert the JSON tool output into engine Building objects."""
    return [
        Building(
            footprint_lonlat=[tuple(p) for p in b["footprint_lonlat"]],
            height_m=b["height_m"],
            height_estimated=b["height_estimated"],
            source_id=b["source_id"],
        )
        for b in payload["buildings"]
    ]

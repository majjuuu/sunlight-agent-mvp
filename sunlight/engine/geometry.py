"""Obstruction geometry: building prisms -> horizon profile at the target point.

The sky around the target is discretized into 1-degree azimuth bins. Each
surrounding building (footprint polygon extruded to its height) raises the
obstruction elevation angle in the bins its silhouette covers. A sun position
is blocked iff its altitude is below the profile elevation at its azimuth.

All math here is plain trigonometry on a local tangent plane - valid for the
few-hundred-metre radius relevant to shadow casting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Point, Polygon

AZ_BINS = 360  # 1-degree resolution

M_PER_DEG_LAT = 111_132.0


def m_per_deg_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


@dataclass
class Building:
    """A surrounding building: footprint (lon, lat) ring + height above ground."""

    footprint_lonlat: list[tuple[float, float]]
    height_m: float
    height_estimated: bool = False
    source_id: str = ""
    tags: dict = field(default_factory=dict)


@dataclass
class TargetPoint:
    """The unit being assessed: a point on a facade at floor height."""

    lat: float
    lon: float
    height_m: float  # window height above ground (floor * storey height)
    facade_azimuth_deg: float | None = None  # compass direction the window faces; None = roof/all


@dataclass
class HorizonProfile:
    """Max obstruction elevation (deg) per 1-degree azimuth bin."""

    elevation_deg: np.ndarray  # shape (360,)
    target_inside_building: str | None = None  # source_id of own building, if detected

    def elevation_at(self, azimuth_deg: np.ndarray | float) -> np.ndarray | float:
        bins = (np.round(np.asarray(azimuth_deg)) % AZ_BINS).astype(int)
        out = self.elevation_deg[bins]
        return float(out) if np.isscalar(azimuth_deg) else out


def _local_xy(lonlat: list[tuple[float, float]], origin_lon: float, origin_lat: float) -> np.ndarray:
    """(lon, lat) ring -> local (x_east, y_north) metres around the origin."""
    arr = np.asarray(lonlat, dtype=float)
    x = (arr[:, 0] - origin_lon) * m_per_deg_lon(origin_lat)
    y = (arr[:, 1] - origin_lat) * M_PER_DEG_LAT
    return np.column_stack([x, y])


def _fill_arc(profile: np.ndarray, az1: float, el1: float, az2: float, el2: float) -> None:
    """Raise profile bins along the shorter arc between two silhouette samples."""
    d = (az2 - az1) % 360.0
    if d > 180.0:  # walk the other way
        az1, el1, az2, el2 = az2, el2, az1, el1
        d = 360.0 - d
    steps = max(1, int(math.ceil(d)))
    for i in range(steps + 1):
        f = i / steps
        az = (az1 + f * d) % 360.0
        el = el1 + f * (el2 - el1)
        b = int(round(az)) % AZ_BINS
        if el > profile[b]:
            profile[b] = el


def build_horizon(target: TargetPoint, buildings: list[Building]) -> HorizonProfile:
    """Project every building prism onto the target's sky dome.

    A building whose roof is below the target window contributes nothing.
    The polygon containing the target itself (its own building) is skipped.
    """
    profile = np.zeros(AZ_BINS)
    own_building: str | None = None
    origin = Point(0.0, 0.0)

    for b in buildings:
        dh = b.height_m - target.height_m
        if dh <= 0:
            continue
        xy = _local_xy(b.footprint_lonlat, target.lon, target.lat)
        poly = Polygon(xy)
        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty:
                continue
            xy = np.asarray(poly.exterior.coords)
        if poly.contains(origin):
            own_building = b.source_id or "unnamed"
            continue

        # Sample the roof outline densely enough that consecutive samples
        # subtend < ~0.5 degrees seen from the target.
        ring = xy if np.array_equal(xy[0], xy[-1]) else np.vstack([xy, xy[0]])
        prev_az = prev_el = None
        for i in range(len(ring) - 1):
            p1, p2 = ring[i], ring[i + 1]
            edge_len = float(np.hypot(*(p2 - p1)))
            d_min = max(1.0, min(np.hypot(*p1), np.hypot(*p2)))
            step = max(0.25, d_min * 0.008)  # ~0.46 deg angular step
            n = max(1, min(4000, int(math.ceil(edge_len / step))))
            for k in range(n + 1):
                p = p1 + (p2 - p1) * (k / n)
                dist = float(np.hypot(p[0], p[1]))
                if dist < 0.5:
                    dist = 0.5  # target virtually touching the wall
                az = (math.degrees(math.atan2(p[0], p[1]))) % 360.0
                el = math.degrees(math.atan2(dh, dist))
                if prev_az is not None:
                    _fill_arc(profile, prev_az, prev_el, az, el)
                else:
                    bin_ = int(round(az)) % AZ_BINS
                    profile[bin_] = max(profile[bin_], el)
                prev_az, prev_el = az, el

    return HorizonProfile(elevation_deg=profile, target_inside_building=own_building)

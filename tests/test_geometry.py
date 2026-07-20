"""Horizon-profile geometry against hand-computed obstruction angles."""

import math

from sunlight.engine.geometry import (
    Building,
    TargetPoint,
    build_horizon,
    m_per_deg_lon,
    M_PER_DEG_LAT,
)

LAT, LON = 37.5665, 126.9780


def _rect(center_east_m, center_north_m, width_m, depth_m):
    """Axis-aligned rectangle footprint in (lon, lat) around the target."""
    mlon, mlat = m_per_deg_lon(LAT), M_PER_DEG_LAT
    x0, x1 = center_east_m - width_m / 2, center_east_m + width_m / 2
    y0, y1 = center_north_m - depth_m / 2, center_north_m + depth_m / 2
    return [
        (LON + x / mlon, LAT + y / mlat)
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    ]


def test_wall_due_south_45_degrees():
    # 20 m tall face, nearest edge 20 m due south -> atan(20/20) = 45 deg at az 180
    target = TargetPoint(lat=LAT, lon=LON, height_m=0.0)
    b = Building(_rect(0, -25, 10, 10), height_m=20.0)  # face at y=-20
    hp = build_horizon(target, [b])
    assert 43.0 <= hp.elevation_at(180.0) <= 46.0
    # nothing to the north
    assert hp.elevation_at(0.0) == 0.0


def test_building_below_target_ignored():
    target = TargetPoint(lat=LAT, lon=LON, height_m=15.0)  # 5th floor
    b = Building(_rect(0, -25, 10, 10), height_m=12.0)  # shorter than the window
    hp = build_horizon(target, [b])
    assert hp.elevation_deg.max() == 0.0


def test_relative_height_used():
    # Roof 30 m, window at 15 m -> effective 15 m over 20 m -> atan(15/20) = 36.9 deg
    target = TargetPoint(lat=LAT, lon=LON, height_m=15.0)
    b = Building(_rect(0, -25, 10, 10), height_m=30.0)
    hp = build_horizon(target, [b])
    expected = math.degrees(math.atan2(15, 20))
    assert abs(hp.elevation_at(180.0) - expected) <= 1.5


def test_own_building_detected_and_skipped():
    target = TargetPoint(lat=LAT, lon=LON, height_m=5.0)
    own = Building(_rect(0, 0, 30, 30), height_m=50.0, source_id="own-1")
    hp = build_horizon(target, [own])
    assert hp.target_inside_building == "own-1"
    assert hp.elevation_deg.max() == 0.0


def test_wide_wall_covers_expected_azimuth_span():
    # 100 m half-width at 20 m distance -> covers roughly az 180 +/- 78 deg
    target = TargetPoint(lat=LAT, lon=LON, height_m=0.0)
    b = Building(_rect(0, -30, 200, 20), height_m=30.0)
    hp = build_horizon(target, [b])
    assert hp.elevation_at(180.0) > 50.0
    assert hp.elevation_at(120.0) > 10.0
    assert hp.elevation_at(240.0) > 10.0
    assert hp.elevation_at(0.0) == 0.0

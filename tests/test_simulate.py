"""End-to-end engine checks against textbook daylight values for Seoul.

Seoul (37.57 N): winter-solstice daylight ~9.6 h, summer ~14.8 h,
annual sun-up hours ~4400 (refraction adds a few minutes per day).
"""

from sunlight.engine.geometry import Building, TargetPoint, M_PER_DEG_LAT, m_per_deg_lon
from sunlight.engine.simulate import simulate_year, apply_climate

LAT, LON = 37.5665, 126.9780


def _rect(center_east_m, center_north_m, width_m, depth_m):
    mlon, mlat = m_per_deg_lon(LAT), M_PER_DEG_LAT
    x0, x1 = center_east_m - width_m / 2, center_east_m + width_m / 2
    y0, y1 = center_north_m - depth_m / 2, center_north_m + depth_m / 2
    return [
        (LON + x / mlon, LAT + y / mlat)
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    ]


def _rep_day_hours(result, day):
    return sum(1 for s in result.representative_days[day] if s["direct_sun"]) * 0.5


def test_unobstructed_annual_sun_up_hours():
    target = TargetPoint(lat=LAT, lon=LON, height_m=10.0, facade_azimuth_deg=None)
    r = simulate_year(target, [])
    assert 4300.0 <= r.annual_sun_up_hours <= 4550.0


def test_south_facade_winter_solstice_full_daylight():
    # In winter the sun rises SE and sets SW, so an unobstructed south facade
    # sees direct sun for essentially the whole ~9.6 h day.
    target = TargetPoint(lat=LAT, lon=LON, height_m=10.0, facade_azimuth_deg=180.0)
    r = simulate_year(target, [])
    assert 9.0 <= _rep_day_hours(r, "winter_solstice") <= 10.5


def test_north_facade_gets_little_winter_sun():
    target = TargetPoint(lat=LAT, lon=LON, height_m=10.0, facade_azimuth_deg=0.0)
    r = simulate_year(target, [])
    assert _rep_day_hours(r, "winter_solstice") <= 0.5


def test_tall_wall_south_blocks_winter_sun():
    target = TargetPoint(lat=LAT, lon=LON, height_m=3.0, facade_azimuth_deg=180.0)
    wall = Building(_rect(0, -25, 200, 20), height_m=100.0)  # 100 m slab 15 m away
    r = simulate_year(target, [wall])
    assert _rep_day_hours(r, "winter_solstice") <= 1.0
    assert r.monthly_direct_hours[12] <= 20.0
    assert r.obstruction_loss_pct > 30.0


def test_obstruction_only_reduces_hours():
    target = TargetPoint(lat=LAT, lon=LON, height_m=10.0, facade_azimuth_deg=180.0)
    free = simulate_year(target, [])
    blocked = simulate_year(target, [Building(_rect(0, -25, 40, 20), height_m=60.0)])
    assert blocked.annual_direct_hours < free.annual_direct_hours
    assert blocked.annual_facade_potential_hours == free.annual_facade_potential_hours


def test_apply_climate_scales_months():
    out = apply_climate({1: 100.0, 7: 100.0}, {1: 0.6, 7: 0.4})
    assert out["monthly_expected_hours"] == {1: 60.0, 7: 40.0}
    assert out["annual_expected_hours"] == 100.0

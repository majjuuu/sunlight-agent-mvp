"""Sanity checks of pvlib sun positions against textbook values for Seoul.

Solar noon altitude = 90 - latitude +/- 23.44 (declination) at the solstices.
"""

from sunlight.engine.sunpath import sun_positions

SEOUL_LAT, SEOUL_LON = 37.5665, 126.9780


def _max_altitude(day: str) -> float:
    df = sun_positions(SEOUL_LAT, SEOUL_LON, day, day + " 23:59", step_minutes=5)
    return float(df["altitude"].max())


def test_summer_solstice_noon_altitude():
    # 90 - 37.57 + 23.44 = 75.87 deg
    assert 74.5 <= _max_altitude("2025-06-21") <= 77.0


def test_winter_solstice_noon_altitude():
    # 90 - 37.57 - 23.44 = 28.99 deg
    assert 28.0 <= _max_altitude("2025-12-21") <= 30.5


def test_azimuth_south_at_solar_noon():
    df = sun_positions(SEOUL_LAT, SEOUL_LON, "2025-03-20", "2025-03-20 23:59", step_minutes=5)
    noon_az = float(df.loc[df["altitude"].idxmax(), "azimuth"])
    assert 175.0 <= noon_az <= 185.0

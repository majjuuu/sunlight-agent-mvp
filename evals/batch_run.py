"""Evaluation #1 scaffolding: batch-run the system over a CSV of test sites.

Usage:
    uv run python evals/batch_run.py [sites.csv] [results.csv]

Input CSV columns: site_id, address, lat, lon, floor, facade_azimuth_deg, notes
(lat/lon optional - geocoded from address when blank).

Output: one row per site with annual/seasonal direct-sun-hours from OUR system.
Paste reference-engine values (Ladybug/Radiance) into ground_truth.csv with the
same site_ids, then run compare_ground_truth.py for RMSE/MAE/correlation.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from sunlight.tools.assess import compute_direct_sun_hours
from sunlight.tools.buildings import fetch_building_context
from sunlight.tools.climate import fetch_climate
from sunlight.tools.geocode import geocode

HERE = Path(__file__).parent


def run_site(row: dict) -> dict:
    if row.get("lat") and row.get("lon"):
        lat, lon = float(row["lat"]), float(row["lon"])
    else:
        g = geocode(row["address"])
        if not g.get("found"):
            return {"site_id": row["site_id"], "status": "geocode_failed"}
        lat, lon = g["lat"], g["lon"]
        time.sleep(1.1)  # Nominatim usage policy: max 1 req/s

    buildings = fetch_building_context(lat, lon, radius_m=300)
    climate = fetch_climate(lat, lon)
    r = compute_direct_sun_hours(
        lat=lat,
        lon=lon,
        floor=int(row["floor"]),
        facade_azimuth_deg=float(row["facade_azimuth_deg"]),
        buildings_payload=buildings,
        monthly_sunshine_fraction=climate["monthly_sunshine_fraction"],
    )
    monthly = r["monthly_direct_hours"]
    return {
        "site_id": row["site_id"],
        "status": "ok",
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "floor": row["floor"],
        "facade_azimuth_deg": row["facade_azimuth_deg"],
        "annual_direct_hours": r["annual_direct_hours"],
        "winter_hours_dec_feb": round(monthly[12] + monthly[1] + monthly[2], 1),
        "summer_hours_jun_aug": round(monthly[6] + monthly[7] + monthly[8], 1),
        "obstruction_loss_pct": r["obstruction_loss_pct"],
        "annual_expected_hours": r.get("climate_corrected", {}).get("annual_expected_hours", ""),
        "livability_score": r["livability_score"]["score"],
        "n_buildings": buildings["stats"]["count"],
        "n_measured_heights": buildings["stats"]["with_measured_height"],
    }


def main() -> None:
    sites_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "sites.csv"
    out_csv = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "results.csv"

    rows = list(csv.DictReader(open(sites_csv, encoding="utf-8-sig")))
    results = []
    for row in rows:
        print(f"[{row['site_id']}] {row['address']} ...", flush=True)
        try:
            results.append(run_site(row))
        except Exception as e:
            results.append({"site_id": row["site_id"], "status": f"error: {e}"})

    fields = sorted({k for r in results for k in r}, key=lambda k: (k != "site_id", k))
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(f"wrote {out_csv} ({len(results)} sites)")


if __name__ == "__main__":
    main()

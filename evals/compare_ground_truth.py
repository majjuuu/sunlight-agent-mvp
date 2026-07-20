"""Evaluation #1: agreement between our engine and a reference engine.

Fill evals/ground_truth.csv (site_id, annual_direct_hours) with values from
Ladybug/Honeybee (Radiance) or ClimateStudio for the same target points, then:

    uv run python evals/compare_ground_truth.py

Reports RMSE, MAE, and Pearson correlation on annual direct-sun-hours.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
    ours = {
        r["site_id"]: float(r["annual_direct_hours"])
        for r in csv.DictReader(open(HERE / "results.csv", encoding="utf-8-sig"))
        if r.get("status") == "ok"
    }
    truth_path = HERE / "ground_truth.csv"
    if not truth_path.exists():
        truth_path.write_text("site_id,annual_direct_hours\n", encoding="utf-8")
        print(f"created empty {truth_path} - paste reference-engine values there")
        return
    truth = {
        r["site_id"]: float(r["annual_direct_hours"])
        for r in csv.DictReader(open(truth_path, encoding="utf-8-sig"))
        if r.get("annual_direct_hours")
    }

    common = sorted(set(ours) & set(truth))
    if len(common) < 2:
        print(f"need >= 2 overlapping sites (have {len(common)})")
        return

    x = [truth[s] for s in common]
    y = [ours[s] for s in common]
    n = len(common)
    errors = [yi - xi for xi, yi in zip(x, y)]
    rmse = math.sqrt(sum(e * e for e in errors) / n)
    mae = sum(abs(e) for e in errors) / n
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    r = cov / (sx * sy) if sx and sy else float("nan")

    print(f"n = {n} sites")
    print(f"RMSE = {rmse:.1f} h/yr")
    print(f"MAE  = {mae:.1f} h/yr")
    print(f"Pearson r = {r:.4f}")
    for s in common:
        print(f"  {s}: ref={truth[s]:8.1f}  ours={ours[s]:8.1f}  err={ours[s]-truth[s]:+7.1f}")


if __name__ == "__main__":
    main()

"""Evaluation #2: agentic robustness benchmark.

Feeds varied input types (clean address, vague Korean phrase, listing text,
missing floor/facade, unresolvable address) to the agent and logs:
  - task success (a parseable report with a score was produced)
  - tool-selection correctness (expected tools were called, dependency order)
  - graceful degradation (assumptions flagged / recovery attempted / honest
    failure instead of hallucinated numbers)

Requires ANTHROPIC_API_KEY. Also runs the fixed pipeline on every case as the
ablation baseline (it should fail on the messy ones - that contrast is the
paper's answer to "why an agent?").

Usage:
    uv run python evals/benchmark_harness.py [benchmark_inputs.jsonl] [benchmark_results.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sunlight.agent.orchestrator import run_agent
from sunlight.agent.pipeline import run_pipeline

HERE = Path(__file__).parent

DEPENDENCY_ORDER = ["geocode", "fetch_building_context", "compute_direct_sun_hours"]


def check_case(case: dict, out: dict) -> dict:
    trace_tools = [t["tool"] for t in out["trace"] if "tool" in t]
    report = out.get("report") or {}

    success = bool(report.get("livability_score") is not None and not report.get("parse_error"))
    expected = case.get("expect_tools", [])
    tools_ok = all(t in trace_tools for t in expected) if case.get("expect_success", True) else True

    # dependency order: first occurrences must be in engine-dependency order
    firsts = [trace_tools.index(t) for t in DEPENDENCY_ORDER if t in trace_tools]
    order_ok = firsts == sorted(firsts)

    graceful = True
    if case.get("expect_flagged_assumptions"):
        graceful = bool(report.get("assumptions_and_estimates"))
    if case.get("expect_graceful_failure"):
        # honest failure: no score fabricated, failure surfaced in text
        graceful = report.get("livability_score") is None or not out.get("assessment")
        success = graceful  # for this case type, honesty IS success
    if case.get("expect_retry_or_simplify"):
        geocode_calls = [t for t in out["trace"] if t.get("tool") == "geocode"]
        recovered = any(t.get("ok") for t in geocode_calls)
        graceful = recovered

    return {
        "task_success": success,
        "tool_selection_ok": tools_ok,
        "dependency_order_ok": order_ok,
        "graceful": graceful,
        "tools_called": trace_tools,
        "n_tool_errors": sum(1 for t in out["trace"] if t.get("ok") is False),
    }


def run_pipeline_baseline(case: dict) -> dict:
    """The fixed script gets the raw query and hard-coded defaults - exactly
    what a non-agentic system would have to do with messy input."""
    try:
        run_pipeline(case["query"], floor=3, facade_azimuth_deg=180.0)
        return {"baseline_success": True}
    except Exception as e:
        return {"baseline_success": False, "baseline_error": f"{type(e).__name__}: {e}"}


def main() -> None:
    inputs = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "benchmark_inputs.jsonl"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "benchmark_results.json"

    cases = [json.loads(line) for line in open(inputs, encoding="utf-8") if line.strip()]
    results = []
    for case in cases:
        print(f"[{case['case_id']}] {case['kind']} ...", flush=True)
        row = {"case_id": case["case_id"], "kind": case["kind"]}
        try:
            out = run_agent(case["query"], priority=case.get("priority"))
            row.update(check_case(case, out))
            row["report"] = out.get("report")
            row["trace"] = out["trace"]
        except Exception as e:
            row.update({"task_success": False, "agent_error": f"{type(e).__name__}: {e}"})
        row.update(run_pipeline_baseline(case))
        results.append(row)

    n = len(results)
    summary = {
        "n_cases": n,
        "agent_task_success_rate": sum(bool(r.get("task_success")) for r in results) / n,
        "tool_selection_rate": sum(bool(r.get("tool_selection_ok")) for r in results) / n,
        "dependency_order_rate": sum(bool(r.get("dependency_order_ok")) for r in results) / n,
        "graceful_degradation_rate": sum(bool(r.get("graceful")) for r in results) / n,
        "baseline_pipeline_success_rate": sum(bool(r.get("baseline_success")) for r in results) / n,
    }
    out_path.write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

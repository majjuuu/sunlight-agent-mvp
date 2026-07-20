"""Minimal FastAPI backend serving the single-page frontend + /api/assess.

Runs in two modes:
  - agent    : LLM orchestrator (requires ANTHROPIC_API_KEY)
  - pipeline : fixed deterministic pipeline (no LLM; needs explicit address,
               floor, and facade). Also the no-key fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sunlight.agent.pipeline import run_pipeline
from sunlight.config import load_env

load_env()

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Sunlight Agent MVP")


class AssessRequest(BaseModel):
    query: str
    floor: int | None = None
    facade_azimuth_deg: float | None = None
    priority: str | None = None
    mode: str = "auto"  # auto | agent | pipeline


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _slim_buildings(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    return [
        {
            "source_id": b.get("source_id", ""),
            "footprint": b["footprint_lonlat"],
            "height_m": b["height_m"],
            "estimated": b["height_estimated"],
            "name": b.get("name", ""),
        }
        for b in payload["buildings"]
    ]


@app.post("/api/assess")
def assess(req: AssessRequest) -> dict:
    mode = req.mode
    if mode == "auto":
        mode = "agent" if _has_api_key() else "pipeline"

    if mode == "agent":
        if not _has_api_key():
            raise HTTPException(400, "agent mode needs ANTHROPIC_API_KEY; use mode=pipeline")
        from sunlight.agent.orchestrator import run_agent  # lazy: anthropic import

        out = run_agent(req.query, priority=req.priority)
    else:
        if req.floor is None or req.facade_azimuth_deg is None:
            raise HTTPException(
                400,
                "pipeline mode needs explicit floor and facade_azimuth_deg "
                "(the fixed script cannot infer them - that's the agent's job)",
            )
        try:
            out = run_pipeline(req.query, req.floor, req.facade_azimuth_deg)
        except Exception as e:
            raise HTTPException(422, f"pipeline failed: {e}") from e

    return {
        "mode": out["mode"],
        "location": out.get("location"),
        "report": out.get("report"),
        "assessment": out.get("assessment"),
        "buildings": _slim_buildings(out.get("buildings_payload")),
        "trace": out.get("trace", []),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

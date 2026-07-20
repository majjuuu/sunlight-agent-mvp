"""LLM agent orchestrator.

Role separation (the paper's credibility anchor):
  - The LLM plans, resolves messy input, selects tools, recovers from missing
    data, and writes the human-language interpretation.
  - Every NUMBER comes from the deterministic tools; the livability score and
    its formula are computed in Python inside compute_direct_sun_hours.

Implementation notes:
  - Manual tool-use loop (not the SDK tool runner) so every tool selection,
    error, and degradation event is logged into `trace` - that trace is the
    raw data for the agentic-robustness evaluation.
  - Large payloads (building footprints) are cached server-side in
    ToolExecutor and summarized for the model; the model never round-trips
    geometry through its context.
"""

from __future__ import annotations

import json
import os

import anthropic

from sunlight.tools.assess import compute_direct_sun_hours
from sunlight.tools.buildings import fetch_building_context
from sunlight.tools.climate import fetch_climate
from sunlight.tools.geocode import geocode
from sunlight.tools.websearch import web_search_future_context

MODEL = os.environ.get("SUNLIGHT_AGENT_MODEL", "claude-opus-4-8")
MAX_TURNS = 12

SYSTEM_PROMPT = """You are a daylight-assessment agent helping non-experts decide \
whether a specific home or office unit gets enough direct sunlight. Users give messy \
input: a clean address, a listing description, or a vague phrase like \
"5th floor south-facing, morning light matters". The system works worldwide and \
accepts input in any language; do not assume a country unless the input implies one.

Hard rules:
1. You NEVER compute or estimate sunlight numbers yourself. Every number (hours, \
score, percentages) must come from tool results. If a tool did not return it, say it \
is unknown.
2. Call tools in dependency order: geocode -> fetch_building_context -> fetch_climate \
-> compute_direct_sun_hours. web_search_future_context is optional context.
3. Degrade gracefully: if a tool fails or data is missing, try a simplified query or \
proceed with defaults, and record every assumption. If floor or facade orientation is \
not given and cannot be inferred from the input, use floor=3 and facade 180 (south) \
as defaults and FLAG them as assumptions in `assumptions_and_estimates` - do not \
refuse.
4. Distinguish measured vs estimated data. fetch_building_context reports how many \
building heights were measured vs estimated - reflect that honestly as a confidence \
note.
5. Interpretation must be tailored to the user's stated priority (morning light, \
plants, avoiding summer overheating, general brightness). Use the representative-day \
profiles: morning = direct sun before 12:00, afternoon = after 12:00.
6. Write the plain-language report for a layperson: seasons, times of day, and which \
neighboring building blocks what, e.g. "the building to the south blocks afternoon \
sun from late October to February". If the user wrote in Korean, write report fields \
in Korean.
7. An empty web-search result means UNKNOWN future construction, never "none planned".
"""

TOOLS = [
    {
        "name": "geocode",
        "description": (
            "Resolve an address or place name to lat/lon (worldwide). Call this "
            "first. If it fails, retry with a simplified query (e.g. drop the unit "
            "number, use the building or complex name)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Address or place name"}},
            "required": ["query"],
        },
    },
    {
        "name": "fetch_building_context",
        "description": (
            "Fetch surrounding building footprints and heights around a point "
            "(OpenStreetMap). Returns summary stats including how many heights are "
            "measured vs estimated. The full geometry is cached server-side for "
            "compute_direct_sun_hours."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_m": {"type": "integer", "description": "Search radius, default 300"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "fetch_climate",
        "description": (
            "Monthly sunshine fraction (0-1) for the location from NASA POWER "
            "climatology, used to convert geometric sun-hours to expected sun-hours."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "compute_direct_sun_hours",
        "description": (
            "THE deterministic solar engine. Computes annual/monthly direct-sun-hours, "
            "representative-day profiles (winter solstice, equinox, summer solstice), "
            "obstruction loss, climate-corrected expected hours, and the 0-100 "
            "livability score with its formula. Requires fetch_building_context to "
            "have been called for this location first (its geometry is cached). "
            "facade_azimuth_deg: 0=N, 90=E, 180=S, 270=W; null for no facade "
            "constraint."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "floor": {"type": "integer", "description": "1-based floor number"},
                "facade_azimuth_deg": {"type": ["number", "null"]},
            },
            "required": ["lat", "lon", "floor", "facade_azimuth_deg"],
        },
    },
    {
        "name": "web_search_future_context",
        "description": (
            "Best-effort search for planned/approved construction near the address "
            "that could block sunlight in the future. Empty results mean UNKNOWN."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"address": {"type": "string"}},
            "required": ["address"],
        },
    },
]

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "resolved_input": {
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "floor": {"type": "integer"},
                "facade_azimuth_deg": {"type": "number"},
                "user_priority": {"type": "string"},
            },
            "required": ["address", "lat", "lon", "floor", "facade_azimuth_deg", "user_priority"],
            "additionalProperties": False,
        },
        "livability_score": {"type": "integer"},
        "score_formula": {"type": "string"},
        "report": {"type": "string", "description": "Plain-language narrative for a layperson"},
        "seasonal_breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "season": {"type": "string"},
                    "avg_daily_direct_hours": {"type": "number"},
                    "summary": {"type": "string"},
                },
                "required": ["season", "avg_daily_direct_hours", "summary"],
                "additionalProperties": False,
            },
        },
        "priority_note": {"type": "string"},
        "assumptions_and_estimates": {"type": "array", "items": {"type": "string"}},
        "data_quality": {"type": "string"},
        "future_obstruction_note": {"type": "string"},
    },
    "required": [
        "resolved_input",
        "livability_score",
        "score_formula",
        "report",
        "seasonal_breakdown",
        "priority_note",
        "assumptions_and_estimates",
        "data_quality",
        "future_obstruction_note",
    ],
    "additionalProperties": False,
}


class ToolExecutor:
    """Runs the deterministic tools and caches heavy payloads server-side."""

    def __init__(self) -> None:
        self.buildings_payload: dict | None = None
        self.climate: dict | None = None
        self.last_geocode: dict | None = None
        self.last_assessment: dict | None = None

    def execute(self, name: str, args: dict) -> dict:
        if name == "geocode":
            self.last_geocode = geocode(args["query"])
            return self.last_geocode

        if name == "fetch_building_context":
            self.buildings_payload = fetch_building_context(
                args["lat"], args["lon"], int(args.get("radius_m", 300))
            )
            # The model sees stats only; geometry stays here.
            return {"stats": self.buildings_payload["stats"]}

        if name == "fetch_climate":
            self.climate = fetch_climate(args["lat"], args["lon"])
            return self.climate

        if name == "compute_direct_sun_hours":
            if self.buildings_payload is None:
                return {
                    "error": "fetch_building_context has not been called yet for this "
                    "location - call it first so obstruction geometry is available."
                }
            result = compute_direct_sun_hours(
                lat=args["lat"],
                lon=args["lon"],
                floor=int(args["floor"]),
                facade_azimuth_deg=args["facade_azimuth_deg"],
                buildings_payload=self.buildings_payload,
                monthly_sunshine_fraction=(
                    self.climate["monthly_sunshine_fraction"] if self.climate else None
                ),
            )
            self.last_assessment = result
            return result

        if name == "web_search_future_context":
            return web_search_future_context(args["address"])

        return {"error": f"unknown tool {name}"}


def run_agent(query: str, priority: str | None = None, client: anthropic.Anthropic | None = None) -> dict:
    """Full agentic assessment of one messy input.

    Returns {report, trace, assessment, buildings_payload}. `trace` records
    every tool call (name, args, ok/error) for the robustness benchmark.
    """
    client = client or anthropic.Anthropic()
    executor = ToolExecutor()
    trace: list[dict] = []

    user_content = query if not priority else f"{query}\n\n(User priority: {priority})"
    messages: list[dict] = [{"role": "user", "content": user_content}]

    response = None
    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            output_config={"format": {"type": "json_schema", "schema": REPORT_SCHEMA}},
            messages=messages,
        )

        if response.stop_reason == "refusal":
            trace.append({"event": "refusal"})
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            entry = {"tool": block.name, "args": block.input}
            try:
                result = executor.execute(block.name, block.input)
                is_error = bool(isinstance(result, dict) and result.get("error"))
                entry["ok"] = not is_error
                if is_error:
                    entry["error"] = result["error"]
            except Exception as e:  # network failures etc. -> let the agent recover
                result = {"error": f"{type(e).__name__}: {e}"}
                entry["ok"] = False
                entry["error"] = str(e)
            trace.append(entry)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                    "is_error": not entry["ok"],
                }
            )
        messages.append({"role": "user", "content": tool_results})

    report = None
    if response is not None and response.stop_reason not in ("refusal", "tool_use"):
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            report = json.loads(text)
        except json.JSONDecodeError:
            report = {"report": text, "parse_error": True}

    return {
        "mode": "agent",
        "report": report,
        "trace": trace,
        "assessment": executor.last_assessment,
        "buildings_payload": executor.buildings_payload,
        "location": executor.last_geocode,
    }

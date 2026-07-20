# Sunlight Agent — Agentic AI for Accessible Daylight Assessment (Seoul MVP)

Research prototype for an IEEE paper: an agentic-AI system that assesses how much
direct sunlight a specific building unit receives, for non-experts deciding where
to live or site an office.

## The one architecture rule

**Every sunlight number comes from deterministic, validated code — never from the
LLM.** The LLM agent only orchestrates tools, recovers from missing data, retrieves
context, and writes the human-language interpretation. Even the 0–100 livability
score is computed in Python with a published formula
(`sunlight/tools/assess.py::compute_livability_score`).

```
            ┌───────────────────────────────────────────────┐
            │              AGENT ORCHESTRATOR (LLM)          │
            │  resolves messy input · plans tool calls in    │
            │  dependency order · recovers from failures ·   │
            │  flags estimates · writes the layperson report │
            │           sunlight/agent/orchestrator.py       │
            └───────┬───────────────────────────────────────┘
                    │ tool calls (numbers flow one way: up)
    ┌───────────────▼───────────────────────────────────────┐
    │            DETERMINISTIC TOOLS (no LLM)                │
    │  geocode()                 Nominatim (Korea-biased)    │
    │  fetch_building_context()  OSM Overpass footprints +   │
    │                            heights (estimates FLAGGED) │
    │  fetch_climate()           NASA POWER sunshine fraction│
    │  compute_direct_sun_hours()  ← THE ENGINE              │
    │  web_search_future_context() best-effort, UNKNOWN≠none │
    └───────────────┬───────────────────────────────────────┘
                    │
    ┌───────────────▼───────────────────────────────────────┐
    │        DETERMINISTIC SOLAR ENGINE  sunlight/engine/    │
    │  sunpath.py   pvlib (NREL SPA) sun positions, 30-min   │
    │  geometry.py  building prisms → 1° horizon profile     │
    │  simulate.py  year simulation, monthly + solstice/     │
    │               equinox profiles, climate correction     │
    └────────────────────────────────────────────────────────┘
```

## Repo layout

| Path | What it is |
|---|---|
| `sunlight/engine/` | Pure-Python solar engine (pvlib + shapely). No network, no LLM. Unit-tested against textbook values. |
| `sunlight/tools/` | Agent-callable data tools (JSON in/out). Free/open sources only. |
| `sunlight/agent/orchestrator.py` | LLM agent (Claude, manual tool-use loop). Logs every tool call into a `trace` for the robustness eval. |
| `sunlight/agent/pipeline.py` | **Fixed-script baseline** — the ablation arm for "why an agent?". Handles exactly one input shape, no recovery. |
| `sunlight/server/` | FastAPI backend + single-page Leaflet frontend. |
| `evals/` | Evaluation scaffolding (see below). |
| `tests/` | 14 unit tests: solstice altitudes, hand-computed obstruction angles, daylight-length sanity, climate scaling. |

## How to run

```powershell
# env (this machine: keep uv data off the "&" username path)
$env:UV_CACHE_DIR = "C:\!Claude_Erica\.uvdata\cache"
$env:UV_PYTHON_INSTALL_DIR = "C:\!Claude_Erica\.uvdata\python"
cd C:\!Claude_Erica\SunlightAgent

uv sync                 # install
uv run pytest           # engine tests
uv run uvicorn sunlight.server.app:app --port 8100   # web app → http://localhost:8100
```

(Or via the Claude Code preview: launch config `sunlight-agent`, which runs
`start-server.cmd`.)

Agent mode needs `ANTHROPIC_API_KEY` in the environment. Without it the server
falls back to the fixed pipeline (which requires explicit floor + facade).

## Modes

- **agent** — messy input in (`"5th floor south-facing, morning light matters"`), tools planned by the
  LLM, structured JSON report out (score, narrative, seasonal breakdown, flagged
  assumptions, priority-conditioned note).
- **pipeline** — deterministic script: geocode → buildings → climate → engine.
  Same numbers, no input resolution, no recovery, no interpretation. This is the
  baseline that messy inputs should break, demonstrating the agent's contribution.

## Evaluation scaffolding (`evals/`)

1. **Ground-truth accuracy** (paper Eval #1):
   `uv run python evals/batch_run.py` runs `evals/sites.csv` (10 Seoul sites) and
   writes `results.csv`. Paste Ladybug/Radiance reference values into
   `ground_truth.csv`, then `uv run python evals/compare_ground_truth.py` →
   RMSE / MAE / Pearson r.
2. **Agentic robustness** (paper Eval #2):
   `uv run python evals/benchmark_harness.py` feeds 10 varied inputs
   (`benchmark_inputs.jsonl`: clean address, vague phrase, listing text, missing
   floor/facade, unresolvable address) to the agent AND to the fixed-pipeline
   baseline, logging task success rate, tool-selection correctness, dependency
   order, and graceful-degradation rate. Requires `ANTHROPIC_API_KEY`.

## Data sources (all free/open)

- Sun position: `pvlib` (NREL solar position algorithms)
- Footprints/heights: OpenStreetMap Overpass (heights flagged measured vs
  estimated; `building:levels × 3 m` fallback). V-World (Korea's national GIS
  platform) is the planned upgrade for authoritative Korean building heights.
- Climate: NASA POWER climatology (all-sky / clear-sky irradiance ratio as
  monthly sunshine fraction)
- Geocoding: OSM Nominatim (Korea-biased)

## Known limitations (be honest in the paper)

- OSM height coverage in Seoul is uneven (~20% measured near City Hall); the
  estimate share is reported with every result.
- Horizon profile is 1° azimuth bins; near-field geometry (<2 m) is clamped.
- Climate correction is a first-order monthly cloudiness proxy, not per-hour.
- Interior daylight (window size, glazing, room depth) is out of scope — the
  metric is direct sun at the window plane.

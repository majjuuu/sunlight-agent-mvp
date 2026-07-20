"""Deterministic solar engine.

CORE ARCHITECTURE RULE: every sunlight NUMBER in this system is produced by
this package (pvlib solar positions + pure-geometry shadow casting).
No LLM code is imported here, and nothing here calls a network API.
"""

from sunlight.engine.geometry import Building, TargetPoint, HorizonProfile, build_horizon
from sunlight.engine.simulate import SimulationResult, simulate_year, apply_climate

__all__ = [
    "Building",
    "TargetPoint",
    "HorizonProfile",
    "build_horizon",
    "SimulationResult",
    "simulate_year",
    "apply_climate",
]

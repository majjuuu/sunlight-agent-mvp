"""Environment/config loading. Reads a project-root .env once (if present).

Keys used:
  GOOGLE_MAPS_API_KEY   - enables Google Places geocoding (optional)
  ANTHROPIC_API_KEY     - enables the LLM agent mode (optional)
  SUNLIGHT_AGENT_MODEL  - overrides the agent model id (optional)
"""

from __future__ import annotations

_loaded = False


def load_env() -> None:
    """Load a .env from the project root into os.environ, at most once.

    No-op (and never raises) if python-dotenv or the file is absent, so the
    system still runs purely on real environment variables.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import find_dotenv, load_dotenv

        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path)
    except Exception:
        pass

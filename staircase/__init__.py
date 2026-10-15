"""Staircase: IEP goals reasoned over a graph of the standards."""

import os
from pathlib import Path

# Read a local .env (never committed) so the model key is available without exporting it.
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

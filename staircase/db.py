"""Connection and naming. One FalkorDB graph per district."""

from __future__ import annotations

import os
import re

from falkordb import FalkorDB

GRADES = ["K", "1", "2", "3", "4", "5", "6", "7", "8"]

_TENANT = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
_db: FalkorDB | None = None


def db() -> FalkorDB:
    global _db
    if _db is None:
        _db = FalkorDB(
            host=os.environ.get("FALKORDB_HOST", "localhost"),
            port=int(os.environ.get("FALKORDB_PORT", "6379")),
            username=os.environ.get("FALKORDB_USERNAME") or None,
            password=os.environ.get("FALKORDB_PASSWORD") or None,
        )
    return _db


def graph_for(tenant: str):
    if not _TENANT.match(tenant):
        raise ValueError(f"tenant names are lowercase letters, digits and dashes: {tenant!r}")
    return db().select_graph(f"staircase:{tenant}")

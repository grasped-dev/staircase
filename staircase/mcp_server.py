"""The same tool catalogue over MCP, so any MCP client (Claude, an IDE agent) can
choose the tools itself. The client never sees Cypher; it sees typed tools.

Run:  python -m staircase.mcp_server            (stdio)
Env:  STAIRCASE_DISTRICT (default "demo"), FALKORDB_HOST / FALKORDB_PORT
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .goal import draft_goal as _draft
from .tools import Tools

DISTRICT = os.environ.get("STAIRCASE_DISTRICT", "demo")
mcp = FastMCP("staircase")


def _t() -> Tools:
    return Tools(DISTRICT)


@mcp.tool()
def list_subareas() -> dict:
    """The goal sub-areas (reading, writing, math) and how many standards each holds."""
    return _t().list_subareas()


@mcp.tool()
def baseline_options(subarea: str, student_grade: str, years_behind: int) -> dict:
    """Standards at the student's instructional level in a sub-area, ranked by how many later standards build on each."""
    return _t().baseline_options(subarea, student_grade, years_behind)


@mcp.tool()
def staircase(standard: str, student_grade: str, depth: int = 1, sid: str | None = None) -> dict:
    """The steps below a standard, its parts, and the shortest climb from it to the student's grade level."""
    return _t().staircase(standard, student_grade, depth=depth, sid=sid)


@mcp.tool()
def frontier(sid: str, subarea: str) -> dict:
    """Standards the student is ready for: not mastered, with every recorded step below them mastered."""
    return _t().frontier(sid, subarea)


@mcp.tool()
def group_students(subarea: str) -> dict:
    """Students who share a next step in a sub-area and could be taught together."""
    return _t().group_students(subarea)


@mcp.tool()
def foundations(subarea: str, limit: int = 10) -> dict:
    """The most load-bearing standards in a sub-area, by PageRank over what builds on what."""
    return _t().foundations(subarea, limit)


@mcp.tool()
def path_between(from_standard: str, to_standard: str) -> dict:
    """Why two standards are connected: the shortest progression from one up to the other."""
    return _t().path_between(from_standard, to_standard)


@mcp.tool()
def recall(sid: str) -> dict:
    """What earlier sessions recorded for a student: mastery and saved goals, with dates."""
    return _t().recall(sid)


@mcp.tool()
def draft_goal(baseline: str, student_grade: str, sid: str | None = None) -> dict:
    """Goal cards from a baseline standard: the goal one grade up the climb, objectives from the
    still-to-develop steps, and the aligned grade-level standard. Read-only; nothing is saved."""
    return _draft(_t(), baseline, student_grade, sid=sid)


if __name__ == "__main__":
    mcp.run()

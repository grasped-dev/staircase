"""A demonstration caseload.

These are invented profiles for showing the tool, not students. Each one is an
ID, a grade and a set of mastered standards, which is all the graph ever holds
about a real student too. IDs start with D- so they can never be mistaken for a
district ID.

Run:  python -m staircase.demo [tenant]
"""

from __future__ import annotations

import sys

from .seed import seed
from .tools import Tools

# (id, grade, [(sub-area, mastered through grade, standards still missing)])
PROFILES = [
    ("D-1001", "5", [("comp-lit", 2, []), ("phonics", 2, []), ("NF", 3, ["3.NF.A.3"])]),
    ("D-1002", "5", [("comp-lit", 2, []), ("NBT", 2, []), ("NF", 3, ["3.NF.A.3"])]),
    ("D-1003", "4", [("comp-lit", 2, []), ("phonics", 1, []), ("composition", 2, [])]),
    ("D-1004", "4", [("comp-lit", 1, []), ("phonics", 2, []), ("OA", 2, [])]),
    ("D-1005", "3", [("comp-lit", 1, []), ("phonics", 1, []), ("OA", 1, [])]),
    ("D-1006", "5", [("comp-info", 2, []), ("NBT", 3, []), ("NF", 3, [])]),
    ("D-1007", "4", [("composition", 2, []), ("conventions", 2, []), ("OA", 2, [])]),
    ("D-1008", "3", [("phonics", 1, []), ("fluency", 1, []), ("NBT", 1, [])]),
]


def cone(t: Tools, key: str, upto: int) -> list[str]:
    """Every standard at or below a grade that is in the sub-area or leads into it."""
    rows = t._q(
        "MATCH (s:Standard)-[:IN_SUBAREA]->(:SubArea {key: $k}) WHERE s.gi <= $g RETURN s.id "
        "UNION "
        "MATCH (s:Standard)-[:IN_SUBAREA]->(:SubArea {key: $k}) "
        "MATCH (p:Standard)-[:PROGRESSES_TO*1..3]->(s) WHERE p.gi <= $g RETURN p.id AS `s.id`",
        {"k": key, "g": upto},
    )
    return sorted({r[0] for r in rows})


def load_demo(tenant: str = "demo") -> dict:
    seed(tenant)
    t = Tools(tenant)
    counts = {}
    for sid, grade, areas in PROFILES:
        t.add_student(sid, grade)
        ids: set[str] = set()
        for key, upto, missing in areas:
            ids |= set(cone(t, key, upto)) - set(missing)
        # A mastered standard means its parts are mastered too.
        parts = [r[0] for r in t._q(
            "MATCH (c:Standard)-[:PART_OF]->(s:Standard) WHERE s.id IN $ids RETURN c.id", {"ids": sorted(ids)})]
        ids |= set(parts)
        t.set_mastery(sid, sorted(ids), session="demo-seed")
        counts[sid] = len(ids)
    return counts


if __name__ == "__main__":
    print(load_demo(sys.argv[1] if len(sys.argv) > 1 else "demo"))

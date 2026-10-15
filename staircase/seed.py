"""Load the standards staircases into a FalkorDB graph.

Each district (tenant) gets its own graph, named ``staircase:<tenant>``. The
graph holds the public standards maps and, later, that district's students.
A query against one district's graph cannot reach another district's, because
it is a different graph, not a WHERE clause.

Run:  python -m staircase.seed [tenant]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .db import graph_for, GRADES

DATA = Path(__file__).resolve().parent.parent / "data"


def _grade_and_strand(subject: str, node_id: str) -> tuple[str | None, str | None, int | None]:
    """Grade, strand (ELA prefix or math domain) and standard number from an id."""
    parts = node_id.split(".")
    if subject == "ela":
        grade = parts[1] if len(parts) > 1 and parts[1] in GRADES else None
        strand = parts[0] if grade else None
        num = int(parts[2]) if grade and len(parts) > 2 and parts[2].isdigit() else None
    else:
        grade = parts[0] if parts[0] in GRADES else None
        strand = parts[1] if grade and len(parts) > 1 else None
        last = parts[-1]
        digits = "".join(ch for ch in last if ch.isdigit())
        num = int(digits) if grade and len(parts) >= 4 and digits else None
    return grade, strand, num


def load_maps() -> dict[str, list[dict]]:
    return {s: json.loads((DATA / f"{s}.json").read_text()) for s in ("math", "ela")}


def load_subareas() -> list[dict]:
    return json.loads((DATA / "subareas.json").read_text())["subareas"]


def in_subarea(sub: dict, subject: str, strand: str | None, num: int | None) -> bool:
    if sub["subject"] != subject or strand is None:
        return False
    for rule in sub["strands"]:
        if rule["code"] != strand:
            continue
        if subject == "ela" and "numbers" in rule:
            if num in rule["numbers"]:
                return True
        else:
            return True
    return False


def build_rows(maps: dict[str, list[dict]], subareas: list[dict]):
    nodes, progress, related, part_of, members = [], set(), set(), [], []
    for subject, items in maps.items():
        for n in items:
            grade, strand, num = _grade_and_strand(subject, n["id"])
            nodes.append({
                "id": n["id"],
                "subject": subject,
                "level": n["level"],
                "grade": grade,
                "gi": GRADES.index(grade) if grade else None,
                "strand": strand,
                "num": num,
                "description": n["description"],
                "cluster_type": n.get("cluster_type") or "",
                "source": n.get("source") or "",
            })
            if n.get("parent"):
                part_of.append({"child": n["id"], "parent": n["parent"]})
            conn = n.get("connections", {})
            for t in conn.get("progress to", []):
                progress.add((n["id"], t))
            for f in conn.get("progress from", []):
                progress.add((f, n["id"]))
            for r in conn.get("related", []):
                a, b = sorted((n["id"], r))
                if a != b:
                    related.add((a, b))
            if n["level"] == "Standard" and grade is not None:
                for sub in subareas:
                    lo, hi = GRADES.index(sub["minGrade"]), GRADES.index(sub["maxGrade"])
                    if in_subarea(sub, subject, strand, num) and grade in GRADES[: 9]:
                        members.append({"id": n["id"], "key": sub["key"]})
    return (
        nodes,
        [{"a": a, "b": b} for a, b in sorted(progress)],
        [{"a": a, "b": b} for a, b in sorted(related)],
        part_of,
        members,
    )


def _batched(rows, size=500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def seed(tenant: str = "demo", reset: bool = True) -> dict:
    g = graph_for(tenant)
    if reset:
        try:
            g.delete()
        except Exception:
            pass
        g = graph_for(tenant)

    maps, subareas = load_maps(), load_subareas()
    nodes, progress, related, part_of, members = build_rows(maps, subareas)

    g.query("CREATE INDEX FOR (s:Standard) ON (s.id)")
    g.query("CREATE INDEX FOR (s:Student) ON (s.sid)")
    g.query("CREATE INDEX FOR (a:SubArea) ON (a.key)")

    for batch in _batched(nodes):
        g.query("UNWIND $rows AS r CREATE (s:Standard) SET s = r", {"rows": batch})
    for batch in _batched(part_of):
        g.query(
            "UNWIND $rows AS r MATCH (c:Standard {id: r.child}), (p:Standard {id: r.parent}) "
            "CREATE (c)-[:PART_OF]->(p)",
            {"rows": batch},
        )
    # A progresses to B: A is a step below B on the staircase.
    # BUILDS_ON is the same edge reversed, so PageRank can score foundations.
    for batch in _batched(progress):
        g.query(
            "UNWIND $rows AS r MATCH (a:Standard {id: r.a}), (b:Standard {id: r.b}) "
            "CREATE (a)-[:PROGRESSES_TO]->(b), (b)-[:BUILDS_ON]->(a)",
            {"rows": batch},
        )
    for batch in _batched(related):
        g.query(
            "UNWIND $rows AS r MATCH (a:Standard {id: r.a}), (b:Standard {id: r.b}) "
            "CREATE (a)-[:RELATED]->(b)",
            {"rows": batch},
        )
    g.query(
        "UNWIND $rows AS r CREATE (:SubArea {key: r.key, label: r.label, area: r.area, "
        "subject: r.subject, minGrade: r.minGrade, maxGrade: r.maxGrade})",
        {"rows": subareas},
    )
    for batch in _batched(members):
        g.query(
            "UNWIND $rows AS r MATCH (s:Standard {id: r.id}), (a:SubArea {key: r.key}) "
            "CREATE (s)-[:IN_SUBAREA]->(a)",
            {"rows": batch},
        )
    counts = {
        "standards": len(nodes),
        "progresses_to": len(progress),
        "related": len(related),
        "part_of": len(part_of),
        "subarea_members": len(members),
    }
    return counts


if __name__ == "__main__":
    tenant = sys.argv[1] if len(sys.argv) > 1 else "demo"
    print(seed(tenant))

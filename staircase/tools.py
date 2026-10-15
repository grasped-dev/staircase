"""The tool catalogue.

The agent never writes Cypher. Every query below was written by a person, is
parameterised, and runs only after its arguments resolve against the graph.
Each tool returns one of five outcomes:

  answered_with_path    the graph held the relationships; the hops come back with the answer
  answered_from_memory  a previous session recorded this (mastery, a saved goal), with its date
  answered              a lookup with no path to show (a list of options)
  not_in_graph          the thing exists, but nothing in the maps connects it the way the question assumed
  unknown               the standard, sub-area or student is not in the graph, so no query ran

"Not in the graph" is not the same as "no prerequisite" or "nothing to climb".
It means the maps do not record one, and the tool says so.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .db import GRADES, graph_for
from .privacy import check_grade, check_student_id, PrivacyError

MAX_DEPTH = 3


@dataclass
class Result:
    tool: str
    args: dict
    outcome: str
    data: dict = field(default_factory=dict)
    message: str = ""
    ms: float = 0.0
    rows: int = 0

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "args": self.args,
            "outcome": self.outcome,
            "message": self.message,
            "ms": round(self.ms, 1),
            "rows": self.rows,
            "data": self.data,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Tools:
    def __init__(self, tenant: str = "demo"):
        self.tenant = tenant
        self.g = graph_for(tenant)
        self.trace: list[dict] = []

    # ── plumbing ────────────────────────────────────────────────────────────

    def _q(self, cypher: str, params: dict | None = None):
        return self.g.ro_query(cypher, params or {}).result_set

    def _w(self, cypher: str, params: dict | None = None):
        return self.g.query(cypher, params or {}).result_set

    def _finish(self, r: Result, t0: float) -> dict:
        r.ms = (time.perf_counter() - t0) * 1000
        d = r.to_dict()
        self.trace.append({k: d[k] for k in ("tool", "args", "outcome", "ms", "rows")})
        return d

    # ── resolvers: every name the model gives is checked against the graph ──

    def resolve_standard(self, sid: str) -> dict | None:
        """A Standard (or the Standard a sub-standard belongs to), matched exactly."""
        rows = self._q(
            "MATCH (s:Standard {id: $id}) "
            "OPTIONAL MATCH (s)-[:PART_OF]->(p:Standard {level: 'Standard'}) "
            "WITH CASE WHEN s.level = 'Sub-standard' THEN p ELSE s END AS n "
            "RETURN n.id, n.level, n.subject, n.grade, n.gi, n.strand, n.description",
            {"id": (sid or "").strip()},
        )
        if not rows or rows[0][0] is None:
            return None
        i, level, subject, grade, gi, strand, desc = rows[0]
        if level != "Standard" or gi is None:
            return None
        return {"id": i, "subject": subject, "grade": grade, "gi": gi, "strand": strand, "description": desc}

    def resolve_subarea(self, key: str) -> dict | None:
        rows = self._q(
            "MATCH (a:SubArea {key: $k}) RETURN a.key, a.label, a.area, a.subject, a.minGrade, a.maxGrade",
            {"k": (key or "").strip()},
        )
        if not rows:
            return None
        k, label, area, subject, lo, hi = rows[0]
        return {"key": k, "label": label, "area": area, "subject": subject, "minGrade": lo, "maxGrade": hi}

    def resolve_student(self, sid: str) -> dict | None:
        try:
            sid = check_student_id(sid)
        except PrivacyError:
            return None
        rows = self._q("MATCH (s:Student {sid: $sid}) RETURN s.sid, s.grade", {"sid": sid})
        return {"sid": rows[0][0], "grade": rows[0][1]} if rows else None

    def _mastered(self, sid: str | None) -> dict[str, str]:
        if not sid:
            return {}
        rows = self._q(
            "MATCH (:Student {sid: $sid})-[m:MASTERED]->(s:Standard) RETURN s.id, m.at", {"sid": sid}
        )
        return {i: at for i, at in rows}

    # ── 1. sub-areas ────────────────────────────────────────────────────────

    def list_subareas(self) -> dict:
        t0 = time.perf_counter()
        rows = self._q(
            "MATCH (a:SubArea) OPTIONAL MATCH (s:Standard)-[:IN_SUBAREA]->(a) "
            "RETURN a.key, a.label, a.area, a.subject, a.minGrade, a.maxGrade, count(s) ORDER BY a.subject, a.area, a.label"
        )
        data = {
            "subareas": [
                {"key": k, "label": l, "area": ar, "subject": s, "minGrade": lo, "maxGrade": hi, "standards": c}
                for k, l, ar, s, lo, hi, c in rows
            ]
        }
        return self._finish(Result("list_subareas", {}, "answered", data, rows=len(rows)), t0)

    # ── 2. baseline options, ranked by leverage ─────────────────────────────

    def baseline_options(self, subarea: str, student_grade: str, years_behind: int) -> dict:
        t0 = time.perf_counter()
        args = {"subarea": subarea, "student_grade": student_grade, "years_behind": years_behind}
        sub = self.resolve_subarea(subarea)
        try:
            grade = check_grade(student_grade)
        except PrivacyError as e:
            return self._finish(Result("baseline_options", args, "unknown", message=str(e)), t0)
        if not sub:
            return self._finish(Result("baseline_options", args, "unknown", message=f"No sub-area {subarea!r}."), t0)

        gi = GRADES.index(grade)
        raw = max(0, gi - max(0, int(years_behind)))
        lo, hi = GRADES.index(sub["minGrade"]), GRADES.index(sub["maxGrade"])
        base = min(max(raw, lo), hi, max(gi, lo))
        note = None
        if base != raw:
            note = (
                f"{sub['label']} standards are written for grades {sub['minGrade']} to {sub['maxGrade']}, "
                f"so the list shows grade {GRADES[base]} instead of grade {GRADES[raw]}."
            )

        # Leverage: how many standards further up the staircase build on this one.
        rows = self._q(
            "MATCH (s:Standard {gi: $gi})-[:IN_SUBAREA]->(:SubArea {key: $k}) "
            "OPTIONAL MATCH (s)-[:PROGRESSES_TO*1..8]->(d:Standard) "
            "WITH s, count(DISTINCT d) AS unlocks "
            "RETURN s.id, s.description, unlocks ORDER BY unlocks DESC, s.id",
            {"gi": base, "k": sub["key"]},
        )
        options = [{"id": i, "description": d, "unlocks": u} for i, d, u in rows]
        data = {"subarea": sub, "student_grade": grade, "baseline_grade": GRADES[base], "note": note, "options": options}
        outcome = "answered" if options else "not_in_graph"
        msg = "" if options else f"No {sub['label']} standards at grade {GRADES[base]} in the maps."
        return self._finish(Result("baseline_options", args, outcome, data, msg, rows=len(options)), t0)

    # ── 3. the staircase for one standard ───────────────────────────────────

    def staircase(self, standard: str, student_grade: str, depth: int = 1, sid: str | None = None) -> dict:
        t0 = time.perf_counter()
        depth = max(1, min(int(depth), MAX_DEPTH))
        args = {"standard": standard, "student_grade": student_grade, "depth": depth}
        if sid:
            args["sid"] = sid
        s = self.resolve_standard(standard)
        if not s:
            return self._finish(
                Result("staircase", args, "unknown", message=f"{standard!r} is not a K-8 standard in the maps. Nothing ran."),
                t0,
            )
        try:
            grade = check_grade(student_grade)
        except PrivacyError as e:
            return self._finish(Result("staircase", args, "unknown", message=str(e)), t0)
        target_gi = GRADES.index(grade)
        mastered = self._mastered(check_student_id(sid) if sid else None)

        # Below: the steps that lead into this standard, with the route.
        below_rows = self._q(
            f"MATCH p = (pre:Standard)-[:PROGRESSES_TO*1..{depth}]->(s:Standard {{id: $id}}) "
            "RETURN DISTINCT pre.id, pre.grade, pre.gi, pre.description, length(p), [n IN nodes(p) | n.id] "
            "ORDER BY length(p), pre.gi DESC, pre.id",
            {"id": s["id"]},
        )
        seen, below = set(), []
        for pid, pg, pgi, pdesc, hops, via in below_rows:
            if pid in seen:
                continue
            seen.add(pid)
            below.append({
                "id": pid, "grade": pg, "description": pdesc, "hops": hops, "via": via,
                "mastered": pid in mastered, "mastered_at": mastered.get(pid),
            })

        # The standard's own parts: the task analysis inside the step.
        parts = [
            {"id": i, "description": d, "mastered": i in mastered}
            for i, d in self._q(
                "MATCH (c:Standard)-[:PART_OF]->(:Standard {id: $id}) RETURN c.id, c.description ORDER BY c.id",
                {"id": s["id"]},
            )
        ]

        # Above: the shortest climb to a standard at the student's own grade.
        climb, climb_note = [], None
        if s["gi"] >= target_gi:
            climb_note = f"{s['id']} is already at or above grade {grade}; there is no climb."
        else:
            rows = self._q(
                "MATCH (s:Standard {id: $id}), (t:Standard {subject: s.subject, gi: $gi, level: 'Standard'}) "
                "WITH s, t, shortestPath((s)-[:PROGRESSES_TO*]->(t)) AS p WHERE p IS NOT NULL "
                "WITH [n IN nodes(p) | {id: n.id, grade: n.grade, gi: n.gi, description: n.description}] AS steps, "
                "length(p) AS hops, CASE WHEN t.strand = s.strand THEN 0 ELSE 1 END AS other, t.id AS tid "
                "RETURN steps, hops ORDER BY other, hops, tid LIMIT 1",
                {"id": s["id"], "gi": target_gi},
            )
            if rows:
                climb = rows[0][0]
            else:
                # The maps do not reach grade level from here. Climb as far as they go, and say where it stops.
                rows = self._q(
                    "MATCH p = (s:Standard {id: $id})-[:PROGRESSES_TO*1..8]->(t:Standard {level: 'Standard'}) "
                    "WHERE t.gi <= $gi "
                    "WITH [n IN nodes(p) | {id: n.id, grade: n.grade, gi: n.gi, description: n.description}] AS steps, "
                    "t.gi AS top, CASE WHEN t.strand = s.strand THEN 0 ELSE 1 END AS other, length(p) AS hops "
                    "RETURN steps, top ORDER BY top DESC, other, hops LIMIT 1",
                    {"id": s["id"], "gi": target_gi},
                )
                if rows:
                    climb = rows[0][0]
                    climb_note = (
                        f"The maps carry {s['id']} up to grade {climb[-1]['grade']} and record no progression "
                        f"from there to a grade {grade} standard."
                    )
                else:
                    climb_note = f"The maps record no standard that {s['id']} progresses to."
        for step in climb:
            step["mastered"] = step["id"] in mastered

        data = {"standard": s, "student_grade": grade, "below": below, "parts": parts, "climb": climb,
                "climb_note": climb_note}
        if below or climb:
            outcome, msg = "answered_with_path", ""
        else:
            outcome = "not_in_graph"
            msg = f"The maps record nothing leading into or out of {s['id']}. That is a gap in the maps, not a finding about the student."
        return self._finish(Result("staircase", args, outcome, data, msg, rows=len(below) + len(climb)), t0)

    # ── 4. what the student is ready for ────────────────────────────────────

    def frontier(self, sid: str, subarea: str) -> dict:
        t0 = time.perf_counter()
        args = {"sid": sid, "subarea": subarea}
        st, sub = self.resolve_student(sid), self.resolve_subarea(subarea)
        if not st or not sub:
            what = "student" if not st else "sub-area"
            return self._finish(Result("frontier", args, "unknown", message=f"Unknown {what}. Nothing ran."), t0)
        rows = self._frontier_rows(st["sid"], st["grade"], sub["key"])
        if not rows:
            any_mastery = self._q(
                "MATCH (:Student {sid: $sid})-[:MASTERED]->(:Standard)-[:IN_SUBAREA]->(:SubArea {key: $k}) RETURN count(*)",
                {"sid": st["sid"], "k": sub["key"]},
            )[0][0]
            msg = (
                f"No mastery is recorded for {st['sid']} in {sub['label']}, so the graph cannot place a next step."
                if not any_mastery
                else f"Every {sub['label']} standard the maps connect to {st['sid']}'s mastered skills is either mastered or still has an unmastered step below it."
            )
            return self._finish(Result("frontier", args, "not_in_graph", {"student": st, "subarea": sub}, msg), t0)
        ready = [
            {"id": i, "grade": g, "description": d, "builds_on": b, "mastered_since": at}
            for i, g, d, b, at, _gi in rows
        ]
        data = {"student": st, "subarea": sub, "ready": ready}
        return self._finish(Result("frontier", args, "answered_from_memory", data, rows=len(ready)), t0)

    def _frontier_rows(self, sid: str, grade: str, key: str):
        # Ready to learn: not mastered, at or below the student's grade, and every step
        # the maps record below it is mastered (at least one, so "ready" is earned, not assumed).
        done = self._mastered(sid)
        rows = self._q(
            "MATCH (s:Standard)-[:IN_SUBAREA]->(:SubArea {key: $k}) "
            "WHERE s.gi <= $gi AND NOT s.id IN $done "
            "MATCH (pre:Standard)-[:PROGRESSES_TO]->(s) "
            "WITH s, collect(pre.id) AS pres "
            "WHERE size(pres) > 0 AND all(p IN pres WHERE p IN $done) "
            "RETURN s.id AS id, s.grade AS grade, s.description AS description, pres, s.gi AS gi "
            "ORDER BY gi, id",
            {"k": key, "gi": GRADES.index(grade), "done": list(done)},
        )
        return [(i, g, d, pres, max(done[p] for p in pres), gi) for i, g, d, pres, gi in rows]

    # ── 5. who can be taught together ───────────────────────────────────────

    def group_students(self, subarea: str) -> dict:
        t0 = time.perf_counter()
        args = {"subarea": subarea}
        sub = self.resolve_subarea(subarea)
        if not sub:
            return self._finish(Result("group_students", args, "unknown", message=f"No sub-area {subarea!r}."), t0)
        students = self._q("MATCH (s:Student) RETURN s.sid, s.grade ORDER BY s.sid")
        by_step: dict[str, dict] = {}
        placed = []
        for sid, grade in students:
            rows = self._frontier_rows(sid, grade, sub["key"])
            if rows:
                placed.append(sid)
            for i, g, d, b, at, _gi in rows:
                e = by_step.setdefault(i, {"id": i, "grade": g, "description": d, "students": []})
                e["students"].append(sid)
        groups = sorted(
            (e for e in by_step.values() if len(e["students"]) >= 2),
            key=lambda e: (-len(e["students"]), e["id"]),
        )
        data = {"subarea": sub, "groups": groups, "students_placed": placed,
                "students_without_mastery": [s for s, _ in students if s not in placed]}
        if not groups:
            return self._finish(
                Result("group_students", args, "not_in_graph", data,
                       f"No two students share a next step in {sub['label']}."), t0)
        return self._finish(Result("group_students", args, "answered_from_memory", data, rows=len(groups)), t0)

    # ── 6. foundations: PageRank over BUILDS_ON ─────────────────────────────

    def foundations(self, subarea: str, limit: int = 10) -> dict:
        t0 = time.perf_counter()
        limit = max(1, min(int(limit), 25))
        args = {"subarea": subarea, "limit": limit}
        sub = self.resolve_subarea(subarea)
        if not sub:
            return self._finish(Result("foundations", args, "unknown", message=f"No sub-area {subarea!r}."), t0)
        rows = self._q(
            "CALL algo.pageRank('Standard', 'BUILDS_ON') YIELD node, score "
            "MATCH (node)-[:IN_SUBAREA]->(:SubArea {key: $k}) "
            "RETURN node.id, node.grade, node.description, score ORDER BY score DESC, node.id LIMIT $limit",
            {"k": sub["key"], "limit": limit},
        )
        data = {"subarea": sub, "ranked": [
            {"id": i, "grade": g, "description": d, "score": round(sc, 5)} for i, g, d, sc in rows]}
        return self._finish(Result("foundations", args, "answered", data, rows=len(rows)), t0)

    # ── 7. why are these two connected ──────────────────────────────────────

    def path_between(self, from_standard: str, to_standard: str) -> dict:
        t0 = time.perf_counter()
        args = {"from": from_standard, "to": to_standard}
        a, b = self.resolve_standard(from_standard), self.resolve_standard(to_standard)
        if not a or not b:
            missing = from_standard if not a else to_standard
            return self._finish(Result("path_between", args, "unknown", message=f"{missing!r} is not in the maps."), t0)
        rows = self._q(
            "MATCH (a:Standard {id: $a}), (b:Standard {id: $b}) "
            "WITH shortestPath((a)-[:PROGRESSES_TO*]->(b)) AS p WHERE p IS NOT NULL "
            "RETURN [n IN nodes(p) | {id: n.id, grade: n.grade, description: n.description}]",
            {"a": a["id"], "b": b["id"]},
        )
        if not rows:
            return self._finish(Result("path_between", args, "not_in_graph", {"from": a, "to": b},
                                       f"The maps record no progression from {a['id']} up to {b['id']}."), t0)
        return self._finish(Result("path_between", args, "answered_with_path", {"path": rows[0][0]},
                                   rows=len(rows[0][0])), t0)

    # ── 8. memory ───────────────────────────────────────────────────────────

    def recall(self, sid: str) -> dict:
        t0 = time.perf_counter()
        args = {"sid": sid}
        st = self.resolve_student(sid)
        if not st:
            return self._finish(Result("recall", args, "unknown", message="No student with that ID in this district's graph."), t0)
        mastered = [
            {"id": i, "grade": g, "at": at, "session": ses}
            for i, g, at, ses in self._q(
                "MATCH (:Student {sid: $sid})-[m:MASTERED]->(s:Standard) RETURN s.id, s.grade, m.at, m.session ORDER BY m.at DESC, s.id",
                {"sid": st["sid"]},
            )
        ]
        goals = [
            {"gid": gid, "created": c, "text": t, "baseline": bl, "goal": gl, "aligned": al}
            for gid, c, t, bl, gl, al in self._q(
                "MATCH (g:Goal)-[:FOR]->(:Student {sid: $sid}) "
                "OPTIONAL MATCH (g)-[:STARTS_FROM]->(b:Standard) OPTIONAL MATCH (g)-[:TARGETS]->(t:Standard) "
                "OPTIONAL MATCH (g)-[:ALIGNS_TO]->(a:Standard) "
                "RETURN g.gid, g.created, g.text, b.id, t.id, a.id ORDER BY g.created DESC",
                {"sid": st["sid"]},
            )
        ]
        outcome = "answered_from_memory" if (mastered or goals) else "not_in_graph"
        msg = "" if (mastered or goals) else f"{st['sid']} is in the graph with nothing recorded yet."
        return self._finish(Result("recall", args, outcome, {"student": st, "mastered": mastered, "goals": goals}, msg,
                                   rows=len(mastered) + len(goals)), t0)

    def add_student(self, sid: str, grade: str) -> dict:
        t0 = time.perf_counter()
        sid, grade = check_student_id(sid), check_grade(grade)
        self._w("MERGE (s:Student {sid: $sid}) SET s.grade = $g", {"sid": sid, "g": grade})
        return self._finish(Result("add_student", {"sid": sid, "grade": grade}, "answered", {"sid": sid, "grade": grade}), t0)

    def set_mastery(self, sid: str, standards: list[str], mastered: bool = True, session: str | None = None) -> dict:
        t0 = time.perf_counter()
        sid = check_student_id(sid)
        args = {"sid": sid, "standards": standards, "mastered": mastered}
        if not self.resolve_student(sid):
            return self._finish(Result("set_mastery", args, "unknown", message="Add the student first."), t0)
        resolved, rejected = [], []
        for x in standards:
            r = self._q("MATCH (s:Standard {id: $id}) WHERE s.level IN ['Standard', 'Sub-standard'] RETURN s.id", {"id": x})
            (resolved if r else rejected).append(x)
        if mastered:
            self._w(
                "MATCH (st:Student {sid: $sid}) UNWIND $ids AS i MATCH (s:Standard {id: i}) "
                "MERGE (st)-[m:MASTERED]->(s) ON CREATE SET m.at = $at, m.session = $ses",
                {"sid": sid, "ids": resolved, "at": _now(), "ses": session or "manual"},
            )
        else:
            self._w(
                "MATCH (:Student {sid: $sid})-[m:MASTERED]->(s:Standard) WHERE s.id IN $ids DELETE m",
                {"sid": sid, "ids": resolved},
            )
        outcome = "answered" if not rejected else "unknown"
        msg = "" if not rejected else f"Not in the maps, not recorded: {', '.join(rejected)}"
        return self._finish(Result("set_mastery", args, outcome, {"recorded": resolved, "rejected": rejected}, msg,
                                   rows=len(resolved)), t0)

    def save_goal(self, sid: str, draft: dict, session: str | None = None) -> dict:
        """Write an accepted goal back as nodes, so the next session starts from it."""
        t0 = time.perf_counter()
        sid = check_student_id(sid)
        args = {"sid": sid}
        if not self.resolve_student(sid):
            return self._finish(Result("save_goal", args, "unknown", message="Add the student first."), t0)
        text = draft.get("goal", {}).get("text", "")
        if "[Student]" not in text:
            return self._finish(Result("save_goal", args, "unknown",
                                       message="A saved goal says [Student], never a name."), t0)
        gid = uuid.uuid4().hex[:12]
        self._w(
            "MATCH (st:Student {sid: $sid}), (b:Standard {id: $b}), (t:Standard {id: $t}) "
            "OPTIONAL MATCH (a:Standard {id: $a}) "
            "CREATE (g:Goal {gid: $gid, created: $at, session: $ses, text: $text})-[:FOR]->(st), "
            "(g)-[:STARTS_FROM]->(b), (g)-[:TARGETS]->(t) "
            "FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END | CREATE (g)-[:ALIGNS_TO]->(a))",
            {"sid": sid, "b": draft["baseline"]["standard"], "t": draft["goal"]["standard"],
             "a": (draft.get("aligned") or {}).get("standard") or "", "gid": gid, "at": _now(),
             "ses": session or "manual", "text": text},
        )
        for n, obj in enumerate(draft.get("objectives", []), 1):
            self._w(
                "MATCH (g:Goal {gid: $gid}), (s:Standard {id: $sid}) "
                "CREATE (o:Objective {n: $n, text: $text})-[:OF]->(g), (o)-[:PRACTICES]->(s)",
                {"gid": gid, "sid": obj["standard"], "n": n, "text": obj["text"]},
            )
        return self._finish(Result("save_goal", args, "answered", {"gid": gid}), t0)


# The catalogue the agent and the MCP server see. Arguments are typed and checked.
CATALOGUE: dict[str, dict[str, Any]] = {
    "list_subareas": {"args": {}, "about": "The goal sub-areas (reading, writing, math) and how many standards each holds."},
    "baseline_options": {
        "args": {"subarea": "subarea_key", "student_grade": "grade K-8", "years_behind": "int 0-8"},
        "about": "Standards at the student's instructional level in a sub-area, ranked by how many later standards build on each.",
    },
    "staircase": {
        "args": {"standard": "standard_id", "student_grade": "grade K-8", "depth": "int 1-3", "sid": "student_id (optional)"},
        "about": "The steps below a standard, its parts, and the shortest climb from it to the student's grade level.",
    },
    "frontier": {
        "args": {"sid": "student_id", "subarea": "subarea_key"},
        "about": "Standards the student is ready for: not mastered, with every recorded step below them mastered.",
    },
    "group_students": {
        "args": {"subarea": "subarea_key"},
        "about": "Students in this district's graph who share a next step and could be taught together.",
    },
    "foundations": {
        "args": {"subarea": "subarea_key", "limit": "int 1-25"},
        "about": "The most load-bearing standards in a sub-area, by PageRank over what builds on what.",
    },
    "path_between": {
        "args": {"from": "standard_id", "to": "standard_id"},
        "about": "Why two standards are connected: the shortest progression from one up to the other.",
    },
    "recall": {"args": {"sid": "student_id"}, "about": "What earlier sessions recorded for this student: mastery and saved goals, with dates."},
}

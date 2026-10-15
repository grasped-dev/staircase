"""Assemble a goal from the staircase.

The structure comes from the graph, not from a model:

  baseline   the standard the teacher picked at the student's instructional level
  goal       one grade up the climb from the baseline: one year of growth
  aligned    where the climb reaches the student's own grade
  objectives the still-to-develop steps, in teaching order (task analysis, not percent slices)

A model may only rewrite a standard's description as a measurable skill phrase.
Every phrase is checked before anyone reads it, and a failed check falls back
to a phrase built from the standard's own words. The tool scaffolds the
teacher's thinking; the numbers (accuracy, trials, measure) are the teacher's.
"""

from __future__ import annotations

import os
import re

from .db import GRADES
from .tools import Tools, Result, _now

CODE = re.compile(r"\b(?:[A-Z]{1,3}\.[0-9K]{1,2}\.[0-9]{1,2}(?:\.[a-z])?|[0-9K]\.[A-Z]{1,3}\.[A-Z]\.[0-9]{1,2}[a-z]?)\b")
FRAME = "By [date], [Student] will {skill} with __% accuracy in __ of __ trials, as measured by ____."
BASELINE_FRAME = "Currently, when asked to {skill}, [Student] does so with __% accuracy in __ of __ trials, as measured by ____."


def _first_sentence(text: str) -> str:
    text = text.strip().split("\n")[0]
    m = re.match(r"(.+?[.;])(\s|$)", text)
    return (m.group(1) if m else text).rstrip(".;")


def template_skill(description: str) -> str:
    """The standard's own first sentence, lower-cased at the start, as the skill."""
    s = _first_sentence(description)
    return s[0].lower() + s[1:] if s else s


def check_skill(phrase: str, description: str, allowed_codes: set[str]) -> tuple[bool, str]:
    """Accept a model's phrase only if it invents nothing the graph did not give it."""
    p = phrase.strip()
    if not p or len(p.split()) > 40:
        return False, "empty or longer than 40 words"
    invented = set(CODE.findall(p)) - allowed_codes
    if invented:
        return False, f"names standards not on the path: {sorted(invented)}"
    nums_desc = set(re.findall(r"\d+", description))
    nums_new = set(re.findall(r"\d+", p)) - nums_desc
    if nums_new:
        return False, f"adds numbers the standard does not contain: {sorted(nums_new)}"
    if re.search(r"\b(he|she|his|her|him)\b", p, re.I):
        return False, "uses a gendered pronoun; the goal says [Student]"
    words = re.findall(r"\b[A-Z][a-z]+\b", p)
    desc_words = set(re.findall(r"\b[A-Z][a-z]+\b", description))
    stray = [w for w in words[1:] if w not in desc_words]
    if stray:
        return False, f"capitalised words not in the standard (possible names): {stray}"
    return True, "ok"


def _gemini_skill(description: str, grade: str) -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=key)
        prompt = (
            "Rewrite this Common Core standard as one observable, measurable skill for an IEP goal. "
            "Start with a verb in base form (for example: identify, add, write). Keep the standard's own content "
            "and any numbers in it; add no new numbers, names, materials or standard codes. Under 30 words. "
            "Return only the phrase, no period.\n\n"
            f"Grade {grade} standard: {description}"
        )
        resp = client.models.generate_content(
            model=os.environ.get("STAIRCASE_GEMINI_MODEL", "gemini-2.5-flash"), contents=prompt
        )
        out = (resp.text or "").strip().strip('"').rstrip(".")
        return out[:1].lower() + out[1:] if out else None
    except Exception:
        return None


def skill_for(node: dict, allowed: set[str], log: list) -> str:
    desc = node["description"]
    drafted = _gemini_skill(desc, node.get("grade") or "")
    if drafted:
        ok, why = check_skill(drafted, desc, allowed)
        log.append({"standard": node["id"], "source": "model", "accepted": ok, "check": why, "phrase": drafted})
        if ok:
            return drafted
    phrase = template_skill(desc)
    log.append({"standard": node["id"], "source": "standard text", "accepted": True, "check": "built from the standard's own words", "phrase": phrase})
    return phrase


def _spread(items: list, k: int) -> list:
    if len(items) <= k:
        return items
    step = (len(items) - 1) / (k - 1)
    return [items[round(i * step)] for i in range(k)]


def draft_goal(tools: Tools, baseline: str, student_grade: str, sid: str | None = None, depth: int = 1) -> dict:
    """The goal cards for one baseline standard. Read-only: nothing is saved until the teacher accepts."""
    import time

    t0 = time.perf_counter()
    args = {"baseline": baseline, "student_grade": student_grade}
    if sid:
        args["sid"] = sid
    st = tools.staircase(baseline, student_grade, depth=depth, sid=sid)
    if st["outcome"] == "unknown":
        return tools._finish(Result("draft_goal", args, "unknown", message=st["message"]), t0)
    d = st["data"]
    base, climb = d["standard"], d["climb"]
    base_gi = base["gi"]
    if not climb or len(climb) < 2:
        msg = d.get("climb_note") or f"The maps record no step above {base['id']}."
        return tools._finish(Result("draft_goal", args, "not_in_graph", {"staircase": d}, msg), t0)

    goal_node = (next((c for c in climb[1:] if c["gi"] == base_gi + 1), None)
                 or next((c for c in climb[1:] if c["gi"] > base_gi), None))
    if goal_node is None:
        msg = (f"The maps record steps from {base['id']} only within grade {base['grade']} "
               f"({', '.join(c['id'] for c in climb)}), and no step into a higher grade. "
               "There is no year-of-growth goal the graph can support from this baseline.")
        return tools._finish(Result("draft_goal", args, "not_in_graph", {"staircase": d}, msg), t0)
    aligned = climb[-1] if climb[-1]["gi"] == GRADES.index(d["student_grade"]) else None

    # Still to develop, in teaching order: unmastered steps below, then the baseline itself,
    # then the parts of the goal standard. The checked (mastered) ones are kept for the card.
    todo = [b for b in sorted(d["below"], key=lambda b: (GRADES.index(b["grade"]), b["id"])) if not b["mastered"]]
    if not any(c["id"] == base["id"] and c.get("mastered") for c in climb):
        todo.append({"id": base["id"], "grade": base["grade"], "description": base["description"]})
    goal_parts = tools._q(
        "MATCH (c:Standard)-[:PART_OF]->(:Standard {id: $id}) RETURN c.id, c.description ORDER BY c.id",
        {"id": goal_node["id"]},
    )
    mastered_ids = set(tools._mastered(sid)) if sid else set()
    leads_in = tools._q(
        "MATCH (p:Standard)-[:PROGRESSES_TO]->(:Standard {id: $id}) WHERE p.level = 'Standard' "
        "RETURN p.id, p.grade, p.gi, p.description ORDER BY p.gi, p.id",
        {"id": goal_node["id"]},
    )
    have = {t["id"] for t in todo}
    for i, g, gi, desc in leads_in:
        if i not in mastered_ids and i not in have and i != base["id"]:
            todo.append({"id": i, "grade": g, "description": desc})
            have.add(i)
    todo.sort(key=lambda t: (GRADES.index(t["grade"]), t["id"]))
    todo += [{"id": i, "grade": goal_node["grade"], "description": desc} for i, desc in goal_parts if i not in mastered_ids]
    if not todo:
        # Nothing recorded between the baseline and the goal: use the standards the maps relate
        # to the goal at or below its grade, so the objectives still come from the graph.
        for i, g, desc in tools._q(
            "MATCH (:Standard {id: $id})-[:RELATED]-(r:Standard {level: 'Standard'}) WHERE r.gi <= $gi "
            "RETURN r.id, r.grade, r.description ORDER BY r.gi, r.id",
            {"id": goal_node["id"], "gi": goal_node["gi"]},
        ):
            if i not in mastered_ids and i not in have:
                todo.append({"id": i, "grade": g, "description": desc, "via": "related"})
                have.add(i)
    objectives_src = _spread(todo, 3)

    path_ids = {b["id"] for b in d["below"]} | {c["id"] for c in climb} | {base["id"]} | {o["id"] for o in todo}
    log: list = []
    goal_skill = skill_for(goal_node, path_ids, log)
    base_skill = skill_for({**base}, path_ids, log)

    draft = {
        "baseline": {
            "standard": base["id"], "grade": base["grade"], "description": base["description"],
            "text": BASELINE_FRAME.format(skill=base_skill),
        },
        "goal": {
            "standard": goal_node["id"], "grade": goal_node["grade"], "description": goal_node["description"],
            "text": FRAME.format(skill=goal_skill),
        },
        "objectives": [
            {"standard": o["id"], "grade": o["grade"], "description": o["description"],
             "via": o["via"] if isinstance(o.get("via"), str) else "progression",
             "text": FRAME.format(skill=template_skill(o["description"]))}
            for o in objectives_src
        ],
        "aligned": ({"standard": aligned["id"], "grade": aligned["grade"], "description": aligned["description"]}
                    if aligned else None),
        "aligned_note": None if aligned else d.get("climb_note"),
        "goal_note": (None if goal_node["gi"] == base_gi + 1 else
                      f"The maps step from grade {base['grade']} to grade {goal_node['grade']} here, with no grade "
                      f"{GRADES[base_gi + 1]} standard between them, so the goal is more than one year of growth. "
                      "Consider a lower baseline or a sub-skill of this standard."),
        "already_has": [b["id"] for b in d["below"] if b["mastered"]],
        "still_to_develop": [o["id"] for o in todo],
        "objectives_note": (None if objectives_src else
                            f"The maps record nothing still to develop between {base['id']} and {goal_node['id']}. "
                            "Write the objectives from your own task analysis of the goal."),
        "path": [c["id"] for c in climb],
        "below": d["below"],
        "phrase_checks": log,
        "drafted_at": _now(),
    }
    return tools._finish(Result("draft_goal", args, "answered_with_path", draft, rows=len(climb)), t0)


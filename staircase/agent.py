"""The agent: a question in, tool calls out, one checked sentence back.

The model chooses from the catalogue and fills arguments. It never sees or
writes Cypher. Arguments are resolved against the graph by the tools
themselves, so a standard or student the model invents produces the
"unknown" outcome and nothing else runs.

Without a model key, a small keyword router stands in for tool choice, so the
whole thing still works offline.
"""

from __future__ import annotations

import json
import os
import re

from .goal import CODE, draft_goal
from .tools import CATALOGUE, Tools

SID = re.compile(r"\b(?:[A-Z]{1,3}-?)?\d{3,12}\b")

TOOL_SPECS = {
    "list_subareas": {},
    "baseline_options": {"subarea": "string", "student_grade": "string", "years_behind": "integer"},
    "staircase": {"standard": "string", "student_grade": "string", "depth": "integer", "sid": "string"},
    "frontier": {"sid": "string", "subarea": "string"},
    "group_students": {"subarea": "string"},
    "foundations": {"subarea": "string", "limit": "integer"},
    "path_between": {"from_standard": "string", "to_standard": "string"},
    "recall": {"sid": "string"},
    "draft_goal": {"baseline": "string", "student_grade": "string", "sid": "string"},
}
REQUIRED = {
    "baseline_options": ["subarea", "student_grade", "years_behind"],
    "staircase": ["standard", "student_grade"],
    "frontier": ["sid", "subarea"],
    "group_students": ["subarea"],
    "foundations": ["subarea"],
    "path_between": ["from_standard", "to_standard"],
    "recall": ["sid"],
    "draft_goal": ["baseline", "student_grade"],
}


def call(tools: Tools, name: str, args: dict) -> dict:
    if name == "draft_goal":
        return draft_goal(tools, args.get("baseline", ""), str(args.get("student_grade", "")), sid=args.get("sid") or None)
    if name not in TOOL_SPECS:
        return {"tool": name, "outcome": "unknown", "message": f"No tool called {name!r}.", "data": {}, "args": args}
    fn = getattr(tools, name)
    clean = {k: v for k, v in args.items() if k in TOOL_SPECS[name] and v not in (None, "")}
    try:
        return fn(**clean)
    except (TypeError, ValueError) as e:
        return {"tool": name, "outcome": "unknown", "message": f"Arguments did not check: {e}", "data": {}, "args": args}


# ── tool choice ─────────────────────────────────────────────────────────────

def _subarea_from_text(tools: Tools, text: str) -> str | None:
    t = text.lower()
    subs = tools.list_subareas()["data"]["subareas"]
    tools.trace.pop()  # an internal lookup, not part of the answer's trace
    for s in subs:
        if s["key"].lower() in re.findall(r"[a-z-]+", t) or s["label"].lower() in t:
            return s["key"]
    words = {"fraction": "NF", "decod": "phonics", "phonics": "phonics", "fluen": "fluency", "comprehension": "comp-lit",
             "literature": "comp-lit", "informational": "comp-info", "vocab": "vocabulary", "grammar": "conventions",
             "convention": "conventions", "writing": "composition", "essay": "composition", "place value": "NBT",
             "geometry": "G", "measurement": "MD", "ratio": "RP", "equation": "EE", "counting": "CC", "add": "OA",
             "subtract": "OA", "multipl": "OA"}
    for w, k in words.items():
        if w in t:
            return k
    return None


def route_without_model(tools: Tools, question: str, context: dict) -> list[tuple[str, dict]]:
    q = question.strip()
    codes = CODE.findall(q)
    sid = (SID.findall(q.upper()) or [context.get("sid")])[0]
    grade = context.get("student_grade")
    m = re.search(r"\b(?:grade|grader)\s*(K|[1-8])\b|\b([1-8])(?:st|nd|rd|th)[ -]grade", q, re.I)
    if m:
        grade = (m.group(1) or m.group(2)).upper()
    sub = _subarea_from_text(tools, q) or context.get("subarea")
    low = q.lower()
    if len(codes) >= 2 and ("why" in low or "connect" in low or "path" in low):
        return [("path_between", {"from_standard": codes[0], "to_standard": codes[1]})]
    if codes and ("goal" in low or "draft" in low) and grade:
        return [("draft_goal", {"baseline": codes[0], "student_grade": grade, "sid": sid})]
    if codes and grade:
        return [("staircase", {"standard": codes[0], "student_grade": grade, "sid": sid})]
    if ("group" in low or "together" in low) and sub:
        return [("group_students", {"subarea": sub})]
    if ("foundation" in low or "load-bearing" in low or "most important" in low) and sub:
        return [("foundations", {"subarea": sub, "limit": 8})]
    if sid and sub and ("ready" in low or "next" in low or "start" in low):
        return [("recall", {"sid": sid}), ("frontier", {"sid": sid, "subarea": sub})]
    if sid:
        return [("recall", {"sid": sid})]
    return [("list_subareas", {})]


def _gemini_tools():
    from google.genai import types

    decls = []
    for name, params in TOOL_SPECS.items():
        about = CATALOGUE.get(name, {}).get("about") or (
            "Draft goal cards (baseline, goal one grade up, objectives, aligned grade-level standard) from a baseline standard."
        )
        props = {k: types.Schema(type=("INTEGER" if v == "integer" else "STRING")) for k, v in params.items()}
        decls.append(types.FunctionDeclaration(
            name=name, description=about,
            parameters=types.Schema(type="OBJECT", properties=props, required=REQUIRED.get(name, [])) if props else None,
        ))
    return [types.Tool(function_declarations=decls)]


SYSTEM = (
    "You help a special education teacher plan IEP goals over a graph of Common Core standards. "
    "Choose tools; never guess a standard code, a student ID, or a sub-area key. Standard codes look like RL.3.1 "
    "or 4.NF.B.3. Student IDs look like S-1042. Sub-area keys: phonological, phonics, fluency, comp-lit, comp-info, "
    "vocabulary, conventions, composition, CC, OA, NBT, NF, MD, G, RP, NS, EE, SP, F. "
    "Grades are K or 1-8. Call at most three tools."
)


def route_with_model(question: str, context: dict) -> list[tuple[str, dict]] | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=os.environ.get("STAIRCASE_GEMINI_MODEL", "gemini-2.5-flash"),
            contents=f"Context: {json.dumps(context)}\nQuestion: {question}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM, tools=_gemini_tools(),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        calls = []
        for part in (resp.candidates[0].content.parts or []):
            if part.function_call:
                calls.append((part.function_call.name, dict(part.function_call.args or {})))
        return calls[:3] or None
    except Exception:
        return None


# ── the reply sentence ──────────────────────────────────────────────────────

def summarise(result: dict) -> str:
    """One sentence built only from the result's own rows."""
    tool, out, d = result.get("tool"), result.get("outcome"), result.get("data") or {}
    if out in ("unknown", "not_in_graph"):
        return result.get("message") or "Not in the graph."
    if tool == "staircase":
        c = [x["id"] for x in d.get("climb", [])]
        return (f"{d['standard']['id']} has {len(d.get('below', []))} recorded step(s) below it"
                + (f", and climbs {' → '.join(c)} to grade level." if c else f". {d.get('climb_note') or ''}"))
    if tool == "draft_goal":
        return (f"Baseline {d['baseline']['standard']}, goal {d['goal']['standard']}"
                + (f", aligned to {d['aligned']['standard']}" if d.get("aligned") else "")
                + f", with {len(d['objectives'])} objective(s) from the still-to-develop steps.")
    if tool == "frontier":
        return f"{d['student']['sid']} is ready for " + ", ".join(r["id"] for r in d["ready"]) + "."
    if tool == "group_students":
        g = d["groups"][0]
        return (f"{len(d['groups'])} group(s) share a next step; the largest is {len(g['students'])} students "
                f"ready for {g['id']}.")
    if tool == "foundations":
        return "Most load-bearing: " + ", ".join(r["id"] for r in d["ranked"][:5]) + "."
    if tool == "path_between":
        return "Connected by " + " → ".join(p["id"] for p in d["path"]) + "."
    if tool == "recall":
        return (f"{d['student']['sid']}: {len(d['mastered'])} standard(s) marked mastered, "
                f"{len(d['goals'])} saved goal(s).")
    if tool == "baseline_options":
        top = d["options"][0]
        return f"{len(d['options'])} grade {d['baseline_grade']} options; {top['id']} unlocks the most ({top['unlocks']})."
    if tool == "list_subareas":
        return f"{len(d['subareas'])} sub-areas across reading, writing and math."
    return "Done."


def ask(question: str, tenant: str = "demo", context: dict | None = None) -> dict:
    context = {k: v for k, v in (context or {}).items() if v}
    tools = Tools(tenant)
    calls = route_with_model(question, context)
    chooser = "model" if calls else "keyword router"
    if not calls:
        calls = route_without_model(tools, question, context)
    results = [call(tools, name, args) for name, args in calls]
    final = next((r for r in reversed(results) if r.get("outcome") not in ("unknown",)), results[-1])
    return {
        "question": question,
        "chooser": chooser,
        "calls": [{"tool": n, "args": a} for n, a in calls],
        "results": results,
        "answer": summarise(final),
        "outcome": final.get("outcome"),
        "trace": tools.trace,
    }

"""HTTP API and the web page.

Run:  uvicorn app:api --reload
Every response carries the trace of tool calls that produced it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from staircase.agent import ask
from staircase.goal import draft_goal
from staircase.privacy import PrivacyError, audit_graph
from staircase.tools import Tools

ROOT = Path(__file__).resolve().parent
api = FastAPI(title="Staircase", version="0.1.0")


def tools(district: str) -> Tools:
    try:
        return Tools(district)
    except ValueError as e:
        raise HTTPException(400, str(e))


def wrap(t: Tools, result: dict) -> dict:
    return {**result, "trace": t.trace}


@api.get("/api/subareas")
def subareas(district: str = "demo"):
    t = tools(district)
    return wrap(t, t.list_subareas())


@api.get("/api/students")
def students(district: str = "demo"):
    t = tools(district)
    rows = t._q("MATCH (s:Student) OPTIONAL MATCH (s)-[m:MASTERED]->() RETURN s.sid, s.grade, count(m) ORDER BY s.sid")
    return {"students": [{"sid": s, "grade": g, "mastered": c} for s, g, c in rows]}


@api.post("/api/students")
def add_student(sid: str = Body(...), grade: str = Body(...), district: str = Body("demo")):
    t = tools(district)
    try:
        return wrap(t, t.add_student(sid, grade))
    except PrivacyError as e:
        raise HTTPException(422, str(e))


@api.get("/api/baseline")
def baseline(subarea: str, grade: str, years_behind: int = 0, district: str = "demo"):
    t = tools(district)
    return wrap(t, t.baseline_options(subarea, grade, years_behind))


@api.get("/api/staircase")
def staircase(standard: str, grade: str, depth: int = 1, sid: str | None = None, district: str = "demo"):
    t = tools(district)
    try:
        return wrap(t, t.staircase(standard, grade, depth=depth, sid=sid or None))
    except PrivacyError as e:
        raise HTTPException(422, str(e))


@api.post("/api/mastery")
def mastery(sid: str = Body(...), standards: list[str] = Body(...), mastered: bool = Body(True),
            district: str = Body("demo")):
    t = tools(district)
    try:
        return wrap(t, t.set_mastery(sid, standards, mastered, session="web"))
    except PrivacyError as e:
        raise HTTPException(422, str(e))


@api.post("/api/draft")
def draft(baseline: str = Body(...), grade: str = Body(...), sid: str | None = Body(None),
          district: str = Body("demo")):
    t = tools(district)
    try:
        return wrap(t, draft_goal(t, baseline, grade, sid=sid or None))
    except PrivacyError as e:
        raise HTTPException(422, str(e))


@api.post("/api/goals")
def save_goal(sid: str = Body(...), draft: dict = Body(...), district: str = Body("demo")):
    t = tools(district)
    try:
        return wrap(t, t.save_goal(sid, draft, session="web"))
    except PrivacyError as e:
        raise HTTPException(422, str(e))


@api.get("/api/frontier")
def frontier(sid: str, subarea: str, district: str = "demo"):
    t = tools(district)
    return wrap(t, t.frontier(sid, subarea))


@api.get("/api/groups")
def groups(subarea: str, district: str = "demo"):
    t = tools(district)
    return wrap(t, t.group_students(subarea))


@api.get("/api/foundations")
def foundations(subarea: str, limit: int = 8, district: str = "demo"):
    t = tools(district)
    return wrap(t, t.foundations(subarea, limit))


@api.get("/api/path")
def path(from_standard: str = Query(..., alias="from"), to_standard: str = Query(..., alias="to"),
         district: str = "demo"):
    t = tools(district)
    return wrap(t, t.path_between(from_standard, to_standard))


@api.get("/api/recall")
def recall(sid: str, district: str = "demo"):
    t = tools(district)
    return wrap(t, t.recall(sid))


@api.post("/api/ask")
def ask_route(question: str = Body(...), context: dict = Body(default_factory=dict), district: str = Body("demo")):
    if not question.strip():
        raise HTTPException(422, "Ask a question.")
    return ask(question, district, context)


@api.get("/api/privacy")
def privacy(district: str = "demo"):
    t = tools(district)
    problems = audit_graph(t.g)
    return {"ok": not problems, "problems": problems,
            "rule": "A student is an ID, a grade, and the standards marked mastered, with dates. Nothing else."}


api.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@api.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")

"""Checks against a live FalkorDB (docker run -p 6379:6379 falkordb/falkordb).

Where a test checks a path, it checks it against the source JSON, not against
the graph, so a seeding bug cannot make the graph agree with itself.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from staircase.db import GRADES, graph_for
from staircase.goal import check_skill, draft_goal
from staircase.privacy import PrivacyError, audit_graph, check_student_id
from staircase.seed import seed
from staircase.tools import Tools

DATA = Path(__file__).resolve().parent.parent / "data"
SRC = {n["id"]: n for s in ("math", "ela") for n in json.loads((DATA / f"{s}.json").read_text())}


def edge(a, b):
    """A progresses to B in the source maps (either side may record it)."""
    return b in SRC[a]["connections"]["progress to"] or a in SRC[b]["connections"]["progress from"]


@pytest.fixture(scope="module")
def t():
    seed("test-a")
    tools = Tools("test-a")
    tools.add_student("S-2001", "5")
    tools.set_mastery("S-2001", ["RL.1.1", "RL.2.1", "RL.2.2", "RF.1.3", "RF.2.3"])
    yield tools
    graph_for("test-a").delete()


def test_seed_matches_source(t):
    n_prog = len({(a, b) for a, n in SRC.items() for b in n["connections"]["progress to"]}
                 | {(f, a) for a, n in SRC.items() for f in n["connections"]["progress from"]})
    assert t._q("MATCH (s:Standard) RETURN count(s)")[0][0] == len(SRC)
    assert t._q("MATCH ()-[r:PROGRESSES_TO]->() RETURN count(r)")[0][0] == n_prog
    assert t._q("MATCH ()-[r:BUILDS_ON]->() RETURN count(r)")[0][0] == n_prog
    assert t._q("MATCH (a)-[:PROGRESSES_TO]->(b) WHERE NOT (b)-[:BUILDS_ON]->(a) RETURN count(*)")[0][0] == 0


def test_unknown_standard_runs_nothing_else(t):
    before = len(t.trace)
    r = t.staircase("RL.9.99", "5")
    assert r["outcome"] == "unknown"
    assert len(t.trace) == before + 1


def test_climb_follows_real_edges(t):
    for std, grade in [("RL.2.1", "5"), ("RF.2.3", "4"), ("3.NF.A.2", "5"), ("W.2.1", "4")]:
        r = t.staircase(std, grade)
        climb = [c["id"] for c in r["data"]["climb"]]
        assert climb and climb[0] == std
        for a, b in zip(climb, climb[1:]):
            assert edge(a, b), f"{a} -> {b} is not in the source maps"
        for b in r["data"]["below"]:
            for x, y in zip(b["via"], b["via"][1:]):
                assert edge(x, y)


def test_draft_goal_shape(t):
    r = draft_goal(t, "RF.2.3", "4", sid="S-2001")
    d = r["data"]
    assert r["outcome"] == "answered_with_path"
    assert SRC[d["goal"]["standard"]]["id"].split(".")[1] == "3"  # one grade up from grade 2
    assert d["aligned"]["standard"].split(".")[1] == "4"
    assert set(o["standard"] for o in d["objectives"]) <= set(d["still_to_develop"])
    assert "RF.1.3" in d["already_has"]
    for card in [d["baseline"], d["goal"], *d["objectives"]]:
        assert "[Student]" in card["text"]


def test_draft_goal_says_when_maps_stop(t):
    r = draft_goal(t, "2.OA.B.2", "4")
    assert r["outcome"] == "not_in_graph"
    assert "no step into a higher grade" in r["message"]


def test_frontier_is_earned(t):
    r = t.frontier("S-2001", "comp-lit")
    mastered = {"RL.1.1", "RL.2.1", "RL.2.2", "RF.1.3", "RF.2.3"}
    assert r["outcome"] == "answered_from_memory"
    for s in r["data"]["ready"]:
        pres = [a for a, n in SRC.items() if edge(a, s["id"])]
        assert pres and set(pres) <= mastered, s["id"]
        assert s["id"] not in mastered


def test_no_mastery_is_not_a_finding(t):
    r = t.frontier("S-2001", "NF")
    assert r["outcome"] == "not_in_graph"
    assert "No mastery is recorded" in r["message"]


def test_skill_checker():
    desc = "Add and subtract within 20, demonstrating fluency for addition and subtraction within 10."
    allowed = {"2.OA.B.2"}
    assert check_skill("add and subtract within 20 fluently", desc, allowed)[0]
    assert not check_skill("add within 20 as in 3.NF.A.1", desc, allowed)[0]  # invented code
    assert not check_skill("add and subtract within 100", desc, allowed)[0]  # invented number
    assert not check_skill("help her add within 20", desc, allowed)[0]  # pronoun
    assert not check_skill("add within 20 like Maria", desc, allowed)[0]  # a name


def test_privacy(t):
    for bad in ["Maria", "Maria Lopez", "maria.lopez@school.org", "12"]:
        with pytest.raises(PrivacyError):
            check_student_id(bad)
    assert check_student_id("147163") == "147163"
    assert check_student_id("s-1042") == "S-1042"
    assert audit_graph(t.g) == []
    keys = t._q("MATCH (s:Student) RETURN keys(s)")
    assert all(set(k) <= {"sid", "grade"} for (k,) in keys)


def test_tenants_are_separate_graphs(t):
    seed("test-b")
    try:
        other = Tools("test-b")
        assert other.resolve_student("S-2001") is None
        assert other.recall("S-2001")["outcome"] == "unknown"
    finally:
        graph_for("test-b").delete()


def test_goal_memory_round_trip(t):
    draft = draft_goal(t, "RL.2.1", "5", sid="S-2001")["data"]
    bad = {**draft, "goal": {**draft["goal"], "text": "Maria will read."}}
    assert t.save_goal("S-2001", bad)["outcome"] == "unknown"
    saved = t.save_goal("S-2001", draft)
    assert saved["outcome"] == "answered"
    r = t.recall("S-2001")
    assert r["outcome"] == "answered_from_memory"
    assert any(g["gid"] == saved["data"]["gid"] and g["baseline"] == "RL.2.1" for g in r["data"]["goals"])


def test_foundations_pagerank(t):
    r = t.foundations("NF", 5)
    assert r["outcome"] == "answered" and len(r["data"]["ranked"]) == 5
    scores = [x["score"] for x in r["data"]["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_api_refuses_names(monkeypatch):
    import app

    c = TestClient(app.api)
    r = c.post("/api/students", json={"sid": "Maria Lopez", "grade": "4", "district": "demo"})
    assert r.status_code == 422
    assert c.get("/api/privacy").json()["ok"] is True


def test_keyword_router_without_model(monkeypatch, t):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from staircase.agent import ask

    r = ask("Why is K.CC.A.1 connected to 2.NBT.A.1?", "test-a")
    assert r["chooser"] == "keyword router"
    assert r["outcome"] == "answered_with_path"
    ids = r["answer"].replace("Connected by ", "").rstrip(".").split(" → ")
    for a, b in zip(ids, ids[1:]):
        assert edge(a, b)

"""What a student is allowed to be inside the graph.

A student is an opaque local ID and a grade. Nothing else. No name, no date of
birth, no free text. Everything the tool knows about a student is which
standards are marked mastered, and when.

These checks run before any write, so the rule does not depend on anyone
remembering it.
"""

from __future__ import annotations

import re

from .db import GRADES

# A district local ID or SSID: digits, optionally after a short letter prefix
# (S-1042, 147163). A word made only of letters (a name) does not match.
STUDENT_ID = re.compile(r"^(?:[A-Z]{1,3}-?)?\d{3,12}$")

STUDENT_PROPERTIES = {"sid", "grade"}
MASTERED_PROPERTIES = {"at", "session"}


class PrivacyError(ValueError):
    pass


def check_student_id(sid: str) -> str:
    sid = (sid or "").strip().upper()
    if not STUDENT_ID.match(sid):
        raise PrivacyError(
            "Student IDs are a local ID or SSID (digits, optionally after a short prefix such as S-). "
            "Names and other text are not accepted."
        )
    return sid


def check_grade(grade: str) -> str:
    grade = (grade or "").strip().upper()
    if grade not in GRADES:
        raise PrivacyError(f"grade must be one of {', '.join(GRADES)}")
    return grade


def audit_graph(g) -> list[str]:
    """Every property on every Student node and MASTERED edge must be on the allowlist."""
    problems = []
    for (keys,) in g.ro_query("MATCH (s:Student) RETURN keys(s)").result_set:
        extra = set(keys) - STUDENT_PROPERTIES
        if extra:
            problems.append(f"Student node carries {sorted(extra)}")
    for (keys,) in g.ro_query("MATCH (:Student)-[m:MASTERED]->() RETURN keys(m)").result_set:
        extra = set(keys) - MASTERED_PROPERTIES
        if extra:
            problems.append(f"MASTERED edge carries {sorted(extra)}")
    return problems

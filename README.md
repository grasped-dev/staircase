# Staircase

**IEP goals reasoned over a graph of the standards.**

Graph Hacks (FalkorDB x WeMakeDevs), Track 1: Agents That Act on Connected Data.

## The problem, for someone outside special education

About one in seven public school students in the US has an IEP, a legal plan for a student with a disability. Every IEP has annual goals, and a goal is supposed to be built backwards from the student, not forwards from the calendar:

- Start where the student actually is, which is often several grades below their own grade.
- Find the next skill they are ready for.
- Set a goal one year of growth above that.
- Break it into the smaller skills that lead there.
- Then name the grade-level standard it is climbing toward.

All of that is a walk through how skills build on each other. A 5th grader reading at a 2nd-grade level does not need the 5th-grade standard written smaller; they need the specific missing step, two or three grades down, and the route back up.

Districts pay for tools that offer a searchable goal bank. A goal bank can't do that walk, because the answer isn't in any one goal. It's in how the standards relate. Ask a chatbot and you get a fluent goal that may sit on the wrong branch of the staircase, with no way to check.

## What Staircase does

The Common Core standards for ELA and math (K-8) are loaded into FalkorDB as a graph: 1,838 standards and their parts, with 1,407 "progresses to" edges and 221 "related" edges. The math progressions come from the Achieve the Core coherence map; the ELA progressions were built to the same schema from the CCSS vertical progressions.

On top of that graph, an agent:

1. **Ranks where to start.** It lists the standards at the student's instructional level, ranked by how many later standards build on each one (`baseline_options`).
2. **Walks the staircase.** For the standard you pick, it shows the steps below it, its parts, and the shortest climb up to the student's own grade level (`staircase`, a `shortestPath` over `PROGRESSES_TO`).
3. **Drafts the goal from the path.** The baseline is where the student is. The goal is one grade up the climb. The objectives are the still-to-develop steps, in teaching order. The aligned grade-level standard is where the climb reaches the student's grade (`draft_goal`). The teacher fills in the numbers, because those come from their own progress monitoring.
4. **Finds who can be taught together.** It lists students whose next step is the same standard: not mastered, with every recorded step below it mastered (`frontier`, `group_students`).
5. **Finds the load-bearing standards.** PageRank over `BUILDS_ON` shows which skills the most of the staircase rests on (`foundations`).
6. **Explains a connection.** It answers why one standard leads to another, by returning the path (`path_between`).
7. **Remembers.** Mastery and accepted goals are written back as nodes and edges with dates, so the next session starts from them (`recall`, `set_mastery`, `save_goal`).

Every answer comes back with the hops it walked, and the web page shows a trace of each tool call: its arguments, time, row count, and outcome.

## Five outcomes, never a guess

| Outcome | Meaning |
|---|---|
| `answered_with_path` | The graph held the relationships; the path comes back with the answer. |
| `answered_from_memory` | An earlier session recorded this (mastery, a saved goal), returned with its date. |
| `answered` | A lookup with no path to show. |
| `not_in_graph` | The thing exists, but the maps don't connect it the way the question assumed. |
| `unknown` | The standard, sub-area or student isn't in the graph, so no query runs. |

"Not in the graph" is deliberately not "no prerequisite". When the math map records no step from `2.OA.B.2` into grade 3, Staircase says so and tells the teacher there is no year-of-growth goal the graph can support from that baseline. It does not make one up.

## What it deliberately does not do

- **The model never writes Cypher.** It picks from a fixed catalogue of tools, each with a query a person wrote and parameterised.
- **No name it gives is trusted.** Every standard, sub-area and student the model names is resolved against the graph before anything runs.
- **It does not write the goal for the teacher.** The model may only rewrite a standard's description as a measurable skill phrase. That phrase is checked, and it is rejected if it names a standard not on the path, adds a number the standard doesn't contain, uses a pronoun, or introduces a capitalised word the standard doesn't have (a possible name). A rejected phrase falls back to the standard's own words. The page shows how every sentence was checked.
- **It holds no student information beyond what the walk needs.** See below.

## Privacy by structure, with real data

The graph is real, public data: the standards and their progressions. A student inside it is three things:

- an opaque ID (a local ID or SSID: digits, optionally after a short prefix)
- a grade
- the standards marked mastered, with a date

There is no name, no birth date and no free text. A student ID that looks like a name is refused before anything is written. An audit (`/api/privacy`) checks every Student node and `MASTERED` edge against that allowlist on every page load. Saved goals say `[Student]`, never a name.

Each district is its own FalkorDB graph (`staircase:<district>`) in one instance. A query against one district can't reach another, because it's a different graph, not a `WHERE` clause someone could forget. The tests check this.

The demo caseload (`D-1001` to `D-1008`) is invented profiles, made to look exactly like what a real student is in this graph: an ID, a grade and a set of mastered standards.

## Live demo

https://staircase-goals.netlify.app

The page is on Netlify. The API and FalkorDB run together in one Google Cloud Run container (`Dockerfile.cloudrun`), and Netlify forwards `/api` to it. The demo graph is rebuilt from `data/` whenever the container starts, so saved goals do not outlive a restart. The public demo runs without a model: tools are chosen by the keyword router and goal wording comes from the standards themselves.

## Run it

With Docker:

```bash
cp .env.example .env            # optional: add GEMINI_API_KEY for model tool choice
docker compose up --build
# app:              http://localhost:8000
# FalkorDB Browser: http://localhost:3000  (graph: staircase:demo)
```

Without Docker for the app:

```bash
docker run -d -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m staircase.demo       # seeds the graph and the demo caseload
.venv/bin/uvicorn app:api --reload       # http://localhost:8000
.venv/bin/python -m pytest -q            # 14 tests against the live database
```

Without a `GEMINI_API_KEY`, everything still works: a keyword router chooses the tools, and skill phrases come from the standards' own words.

### As MCP tools

The same catalogue is an MCP server, so any MCP client can choose the tools itself:

```json
{
  "mcpServers": {
    "staircase": {
      "command": "/path/to/staircase/.venv/bin/python",
      "args": ["-m", "staircase.mcp_server"],
      "cwd": "/path/to/staircase",
      "env": { "STAIRCASE_DISTRICT": "demo" }
    }
  }
}
```

## Graph data model

```cypher
(:Standard {id, subject, level, grade, gi, strand, num, description})
(:Standard)-[:PART_OF]->(:Standard)            // sub-standard -> standard -> cluster/strand -> grade
(:Standard)-[:PROGRESSES_TO]->(:Standard)      // a step up the staircase
(:Standard)-[:BUILDS_ON]->(:Standard)          // the same edge reversed, for PageRank over foundations
(:Standard)-[:RELATED]->(:Standard)
(:Standard)-[:IN_SUBAREA]->(:SubArea {key, label, area, subject})

(:Student {sid, grade})-[:MASTERED {at, session}]->(:Standard)
(:Goal {gid, created, session, text})-[:FOR]->(:Student)
(:Goal)-[:STARTS_FROM]->(:Standard)            // baseline
(:Goal)-[:TARGETS]->(:Standard)                // one year of growth
(:Goal)-[:ALIGNS_TO]->(:Standard)              // grade-level standard
(:Objective {n, text})-[:OF]->(:Goal)
(:Objective)-[:PRACTICES]->(:Standard)
```

## The queries the product depends on

The climb to grade level (`staircase`):

```cypher
MATCH (s:Standard {id: $id}), (t:Standard {subject: s.subject, gi: $gi, level: 'Standard'})
WITH s, t, shortestPath((s)-[:PROGRESSES_TO*]->(t)) AS p WHERE p IS NOT NULL
WITH [n IN nodes(p) | {id: n.id, grade: n.grade, gi: n.gi, description: n.description}] AS steps,
     length(p) AS hops, CASE WHEN t.strand = s.strand THEN 0 ELSE 1 END AS other, t.id AS tid
RETURN steps, hops ORDER BY other, hops, tid LIMIT 1
```

The steps below, with the route (`staircase`, depth 1-3):

```cypher
MATCH p = (pre:Standard)-[:PROGRESSES_TO*1..$depth]->(s:Standard {id: $id})
RETURN DISTINCT pre.id, pre.grade, pre.gi, pre.description, length(p), [n IN nodes(p) | n.id]
```

Leverage, for ranking where to start (`baseline_options`):

```cypher
MATCH (s:Standard {gi: $gi})-[:IN_SUBAREA]->(:SubArea {key: $k})
OPTIONAL MATCH (s)-[:PROGRESSES_TO*1..8]->(d:Standard)
WITH s, count(DISTINCT d) AS unlocks
RETURN s.id, s.description, unlocks ORDER BY unlocks DESC, s.id
```

Ready to learn (`frontier`, `group_students`):

```cypher
MATCH (s:Standard)-[:IN_SUBAREA]->(:SubArea {key: $k})
WHERE s.gi <= $gi AND NOT s.id IN $done
MATCH (pre:Standard)-[:PROGRESSES_TO]->(s)
WITH s, collect(pre.id) AS pres
WHERE size(pres) > 0 AND all(p IN pres WHERE p IN $done)
RETURN s.id, s.grade, s.description, pres
```

Load-bearing standards (`foundations`):

```cypher
CALL algo.pageRank('Standard', 'BUILDS_ON') YIELD node, score
MATCH (node)-[:IN_SUBAREA]->(:SubArea {key: $k})
RETURN node.id, node.grade, node.description, score ORDER BY score DESC LIMIT $limit
```

Memory, written back (`save_goal`), then read first next session (`recall`):

```cypher
MATCH (st:Student {sid: $sid}), (b:Standard {id: $b}), (t:Standard {id: $t})
CREATE (g:Goal {gid: $gid, created: $at, session: $ses, text: $text})-[:FOR]->(st),
       (g)-[:STARTS_FROM]->(b), (g)-[:TARGETS]->(t)
```

## Tests

`tests/test_staircase.py` runs against a live FalkorDB. Where a test checks a path, it checks every hop against the source JSON rather than the graph, so a seeding bug can't make the graph agree with itself. It covers:

- seed counts against the source
- climbs and routes following real edges
- goal shape (one grade up, objectives drawn from the still-to-develop steps)
- the "maps stop here" outcome
- frontier standards being earned, not assumed
- the skill-phrase checker
- privacy refusals and the audit
- district isolation
- goal memory round-trip
- PageRank ordering
- the API refusing a name
- the keyword router working without a model

## Data

- `data/math.json`: CCSS math K-8 as a coherence map, from the Achieve the Core coherence map.
- `data/ela.json`: CCSS ELA K-12, with progressions authored to the same schema from the CCSS vertical progressions.
- `data/subareas.json`: which standards belong to each goal sub-area (reading, writing, math).

These maps were prepared before the hackathon as data. All code in this repository was written during the event window.

## AI disclosure

- **Built with Claude Code** (Anthropic) as the coding assistant.
- **Gemini at runtime** (`gemini-2.5-flash`, optional) for two narrow jobs: choosing tools from the catalogue, and rewriting a standard's description as a skill phrase that is checked before display.

## Author

Megan Hsu

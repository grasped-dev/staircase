# Demo video script (about 3 minutes)

Run `docker compose up --build`, open http://localhost:8000. The demo caseload loads automatically.

## 1. The problem, in one breath (20s)

"A 5th grader reads at a 2nd-grade level. Their IEP needs a goal: where they are now, one year of growth, the smaller steps in between, and the grade-level standard it climbs toward. The answer to 'where do I start' isn't in any one standard. It's in how the standards build on each other. So I put them in a graph."

## 2. Plan a goal (70s)

- Student **D-1004**, grade 4, **Phonics and decoding**, 2 years behind. Click *Show baseline standards*.
- Point at *unlocks 21*: "ranked by how many later standards build on this one. That's a traversal, not a lookup."
- Click **RF.2.3**. The staircase draws: grade 1 below, the baseline, its parts, and the climb to grade 4.
- "Checked steps are what the student can already do; the graph remembered them from last session." Uncheck one part and check it again, to show the write-back.
- Click *Draft the goal*. Walk the cards: baseline, objectives from the still-to-develop steps, the goal one grade up, the aligned grade-level standard, and the path.
- Open *How each sentence was checked*: "the model only rephrases. If it names a standard not on the path, adds a number, or adds a name, it's rejected."
- Save it.

## 3. The contrast (30s)

- Ask tab: *Show the staircase for RL.9.1 for a 5th grader*. "That isn't a real standard code. The agent says so and runs nothing."
- Plan tab, math, **Operations and algebraic thinking**, grade 4, 2 years behind, pick **2.OA.B.2**, draft. "The maps don't record a step from here into grade 3, so it won't invent a goal. Not in the graph is not the same as nothing to learn."

## 4. The caseload (40s)

- Caseload tab, Phonics: "five students share the same next step, RF.3.3. That's one small group, not five separate plans."
- Load-bearing standards: "PageRank over what builds on what: the skills the most of the staircase rests on."
- *What the graph remembers*: the goal you just saved, with its date.

## 5. Privacy and the agent (20s)

- Top right: "a student in this graph is an ID, a grade, and mastered standards. Type a name as an ID and it's refused before anything is written." Show it in *Add a student by ID*.
- Trace panel: "every answer shows each tool, its arguments, the time, and the rows. The model picks tools; it never writes a query."
- Optional: the same tools over MCP from Claude.

## Track

Track 1: Agents That Act on Connected Data.

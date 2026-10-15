# Demo video script (about 3 minutes)

Run `docker compose up --build`, open http://localhost:8000. The demo caseload loads automatically.

## 1. The problem, in one breath (20s)

"A 5th grader reads at a 2nd-grade level. Their IEP needs a goal: where they are now, one year of growth, the smaller steps in between, and the grade-level standard it climbs toward. The answer to 'where do I start' isn't in any one standard. It's in how the standards build on each other. So I put them in a graph."

## 2. Plan a goal (70s)

- *Write a goal* tab. Student **D-1004**, grade 4, **Phonics and decoding**, 2 years behind. Click *Find a starting point*.
- Point at *leads to 21 later skills*: "ranked by how many later standards build on this one. That's a traversal, not a lookup."
- Click **RF.2.3**. The staircase draws: grade 1 below, the starting point (open its smaller skills), and the climb to grade 4.
- "Checked steps are what the student can already do; the graph remembered them from last session." Uncheck one smaller skill and check it again, to show the write-back.
- Click *Write the goal*. Walk the list: where the student is now, the objectives from the still-to-develop steps, the annual goal one grade up, and the line under it with the aligned grade-level standard and the path. *Copy* puts it on the clipboard.
- Open *How the wording was checked*: "the model only rephrases. If it names a standard not on the path, adds a number, or adds a name, it's rejected."
- Save it.

## 3. The contrast (30s)

- *Ask* tab, type: *Show the staircase for RL.9.1 for a 5th grader*. "That isn't a real standard code. The agent says so and runs nothing."
- *Write a goal*, **Operations and algebraic thinking**, grade 4, 2 years behind, pick **2.OA.B.2**, *Write the goal*. "The maps don't record a step from here into grade 3, so it won't invent a goal. Not in the graph is not the same as nothing to learn."

## 4. The caseload (40s)

- *My caseload*, Phonics: "five students share the same next step, RF.3.3. That's one small group, not five separate plans."
- *Skills the most rests on*: "PageRank over what builds on what."
- *Saved for this student*: the goal you just saved, with its date.

## 5. Privacy and the agent (20s)

- Footer: "a student here is an ID, a grade, and the skills marked mastered." Type a name in *Add a student* and it's refused before anything is written.
- Click *Show how it worked* (top right): "every answer shows each tool the agent called, its arguments, the result, and the time. The model picks tools; it never writes a query." Teachers never have to open it.
- Optional: the same tools over MCP from Claude.

## Track

Track 1: Agents That Act on Connected Data.

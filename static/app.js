const GRADES = ["K", "1", "2", "3", "4", "5", "6", "7", "8"];
const $ = (id) => document.getElementById(id);
const state = { students: [], subareas: [], baseline: null, depth: 1, stair: null, draft: null };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function short(desc, n = 180) {
  const d = String(desc || "").split("\n")[0];
  return d.length > n ? d.slice(0, n - 1) + "…" : d;
}

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  if (data.trace) showTrace(data.trace);
  return data;
}

// ── trace ───────────────────────────────────────────────────────────────────
let traceRows = [];
function showTrace(trace) {
  traceRows = [...trace.slice().reverse(), ...traceRows].slice(0, 40);
  $("trace").innerHTML = traceRows.map((t) => `<tr>
    <td><code>${esc(t.tool)}</code></td>
    <td class="args">${Object.entries(t.args || {}).map(([k, v]) => `${esc(k)}=${esc(Array.isArray(v) ? v.join(",") : v)}`).join("<br>")}</td>
    <td><span class="outcome o-${esc(t.outcome)}">${esc(t.outcome)}</span></td>
    <td>${esc(t.ms)}</td><td>${esc(t.rows)}</td></tr>`).join("");
}

// ── setup ───────────────────────────────────────────────────────────────────
function fillGrades(sel, value) {
  sel.innerHTML = GRADES.map((g) => `<option value="${g}">${g === "K" ? "Kindergarten" : "Grade " + g}</option>`).join("");
  if (value) sel.value = value;
}
function fillSubareas(sel) {
  const groups = { reading: "Reading", writing: "Writing", math: "Math" };
  sel.innerHTML = Object.entries(groups).map(([area, label]) => `<optgroup label="${label}">` +
    state.subareas.filter((s) => s.area === area).map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("") +
    "</optgroup>").join("");
}
function fillStudents() {
  const keep = $("student").value, keepRecall = $("recall-student").value;
  const opts = state.students.map((s) => `<option value="${esc(s.sid)}">${esc(s.sid)} (grade ${esc(s.grade)})</option>`).join("");
  $("student").innerHTML = `<option value="">No student (explore only)</option>` + opts;
  $("recall-student").innerHTML = opts;
  if (keep) $("student").value = keep;
  if (keepRecall) $("recall-student").value = keepRecall;
}

async function loadStudents() {
  state.students = (await api("/api/students")).students;
  fillStudents();
}

async function init() {
  const subs = await api("/api/subareas");
  state.subareas = subs.data.subareas;
  fillSubareas($("subarea"));
  fillSubareas($("group-subarea"));
  $("subarea").value = "comp-lit";
  $("group-subarea").value = "phonics";
  fillGrades($("grade"), "5");
  fillGrades($("new-grade"), "4");
  await loadStudents();
  const p = await api("/api/privacy");
  if (!p.ok) { $("privacy").classList.add("bad"); $("privacy").textContent = "Privacy check failed: " + p.problems.join("; "); }
  examples();
  loadCaseload();
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === b.dataset.tab));
}));

$("student").addEventListener("change", () => {
  const s = state.students.find((x) => x.sid === $("student").value);
  if (s) $("grade").value = s.grade;
  if (state.baseline) loadStair();
});

$("add-student").addEventListener("click", async () => {
  $("add-error").textContent = "";
  try {
    const r = await api("/api/students", { sid: $("new-sid").value, grade: $("new-grade").value });
    await loadStudents();
    $("student").value = r.data.sid;
    $("grade").value = r.data.grade;
    $("new-sid").value = "";
  } catch (e) { $("add-error").textContent = e.message; }
});

// ── plan: baseline ──────────────────────────────────────────────────────────
$("show-baseline").addEventListener("click", async () => {
  const r = await api(`/api/baseline?subarea=${encodeURIComponent($("subarea").value)}&grade=${$("grade").value}&years_behind=${$("years").value || 0}`);
  $("baseline-card").hidden = false;
  $("stair-card").hidden = true;
  $("goal-card").hidden = true;
  $("baseline-note").textContent = r.data.note || (r.outcome === "not_in_graph" ? r.message : "");
  $("baseline-list").innerHTML = (r.data.options || []).map((o) => `<li data-id="${esc(o.id)}">
      <span class="id">${esc(o.id)}</span><span class="desc">${esc(short(o.description))}</span>
      <span class="unlocks">unlocks ${o.unlocks}</span></li>`).join("");
  $("baseline-list").querySelectorAll("li").forEach((li) => li.addEventListener("click", () => {
    $("baseline-list").querySelectorAll("li").forEach((x) => x.classList.toggle("sel", x === li));
    state.baseline = li.dataset.id;
    state.depth = 1;
    loadStair();
  }));
});

// ── plan: staircase ─────────────────────────────────────────────────────────
async function loadStair() {
  const sid = $("student").value;
  const r = await api(`/api/staircase?standard=${encodeURIComponent(state.baseline)}&grade=${$("grade").value}&depth=${state.depth}` + (sid ? `&sid=${encodeURIComponent(sid)}` : ""));
  state.stair = r;
  $("stair-card").hidden = false;
  $("goal-card").hidden = true;
  renderStair(r, !!sid);
}

function stepHtml(n, cls, tag, canCheck, extra = "") {
  const gi = Math.max(0, GRADES.indexOf(n.grade));
  const box = canCheck ? `<input type="checkbox" data-id="${esc(n.id)}" ${n.mastered ? "checked" : ""} title="Mastered">` : "<span></span>";
  return `<div class="st ${cls} ${n.mastered ? "done" : ""}" style="--g:${gi}">
    ${box}<span class="tag">${esc(tag)}</span>
    <div><span class="id">${esc(n.id)}</span> <span class="desc">${esc(short(n.description, 160))}</span></div>
    ${extra}</div>`;
}

function renderStair(r, canCheck) {
  const d = r.data;
  if (r.outcome === "unknown") { $("stair").innerHTML = `<p class="error">${esc(r.message)}</p>`; return; }
  const html = [];
  const below = (d.below || []).slice().sort((a, b) => GRADES.indexOf(a.grade) - GRADES.indexOf(b.grade));
  for (const b of below) {
    html.push(stepHtml(b, "below", `grade ${b.grade} · below`, canCheck, `<span class="via">${esc(b.via.join(" → "))}</span>`));
  }
  const baseMastered = (d.climb[0] || {}).mastered;
  html.push(stepHtml({ ...d.standard, mastered: baseMastered }, "base", `grade ${d.standard.grade} · baseline`, canCheck));
  for (const p of d.parts || []) {
    html.push(stepHtml({ ...p, grade: d.standard.grade }, "part", "part of baseline", canCheck));
  }
  const climb = (d.climb || []).slice(1);
  climb.forEach((c, i) => {
    const isTop = i === climb.length - 1 && c.gi === GRADES.indexOf(d.student_grade);
    html.push(stepHtml(c, "climb" + (isTop ? " top" : ""), `grade ${c.grade} · ${isTop ? "grade level" : "climb"}`, canCheck));
  });
  $("stair").innerHTML = html.join("");
  $("climb-note").textContent = d.climb_note || (canCheck ? "" : "Pick a student to record what is mastered.");
  $("widen").disabled = state.depth >= 3;
  $("stair").querySelectorAll("input[type=checkbox]").forEach((cb) => cb.addEventListener("change", async () => {
    try {
      await api("/api/mastery", { sid: $("student").value, standards: [cb.dataset.id], mastered: cb.checked });
      cb.closest(".st").classList.toggle("done", cb.checked);
    } catch (e) {
      cb.checked = !cb.checked;
      $("climb-note").textContent = "Not recorded: " + e.message;
    }
    loadStudents();
  }));
}

$("widen").addEventListener("click", () => { state.depth = Math.min(3, state.depth + 1); loadStair(); });

// ── plan: goal ──────────────────────────────────────────────────────────────
$("draft").addEventListener("click", async () => {
  const sid = $("student").value || null;
  const r = await api("/api/draft", { baseline: state.baseline, grade: $("grade").value, sid });
  state.draft = r;
  $("goal-card").hidden = false;
  $("saved").textContent = "";
  if (r.outcome !== "answered_with_path") {
    $("goal-note").textContent = r.message;
    $("goal-cards").innerHTML = "";
    $("save-goal").disabled = true;
    return;
  }
  const d = r.data;
  $("goal-note").textContent = [d.goal_note, d.aligned_note, d.objectives_note].filter(Boolean).join(" ");
  const card = (cls, title, n, text) => `<div class="gc ${cls}"><h3>${esc(title)}</h3>
      <div><span class="id">${esc(n.standard)}</span> · grade ${esc(n.grade)}</div>
      <p>${esc(text)}</p><div class="src">${esc(short(n.description, 220))}</div></div>`;
  const parts = [card("", "Baseline", d.baseline, d.baseline.text)];
  d.objectives.forEach((o, i) => parts.push(card("", `Objective ${i + 1}${o.via === "related" ? " (related skill)" : ""}`, o, o.text)));
  parts.push(card("goal", "Goal: one year of growth", d.goal, d.goal.text));
  if (d.aligned) parts.push(`<div class="gc"><h3>Aligned grade-level standard</h3><div><span class="id">${esc(d.aligned.standard)}</span> · grade ${esc(d.aligned.grade)}</div><p class="src">${esc(short(d.aligned.description, 220))}</p></div>`);
  parts.push(`<div class="gc"><h3>The path</h3><p class="path">${esc(d.path.join(" → "))}</p>
      <p class="src">Already has: ${d.already_has.length ? d.already_has.map(esc).join(", ") : "none checked"}<br>
      Still to develop: ${d.still_to_develop.length ? d.still_to_develop.map(esc).join(", ") : "none recorded"}</p></div>`);
  $("goal-cards").innerHTML = parts.join("");
  $("checks").innerHTML = d.phrase_checks.map((c) => `<li><code>${esc(c.standard)}</code> from ${esc(c.source)}: ${c.accepted ? "accepted" : "rejected"} (${esc(c.check)})</li>`).join("");
  $("save-goal").disabled = !sid;
  $("saved").textContent = sid ? "" : "Pick a student to save this goal.";
});

$("save-goal").addEventListener("click", async () => {
  const r = await api("/api/goals", { sid: $("student").value, draft: state.draft.data });
  $("saved").textContent = r.outcome === "answered" ? `Saved as goal ${r.data.gid}. The next session starts from it.` : r.message;
});

// ── caseload ────────────────────────────────────────────────────────────────
async function loadCaseload() {
  const key = $("group-subarea").value;
  const [g, f] = await Promise.all([api(`/api/groups?subarea=${encodeURIComponent(key)}`), api(`/api/foundations?subarea=${encodeURIComponent(key)}&limit=8`)]);
  const d = g.data;
  $("groups").innerHTML = g.outcome === "unknown" || g.outcome === "not_in_graph"
    ? `<p class="note">${esc(g.message)}</p>`
    : d.groups.map((x) => `<div class="group"><span class="id">${esc(x.id)}</span> · grade ${esc(x.grade)}
        <div class="desc">${esc(short(x.description))}</div>
        <div>${x.students.map((s) => `<span class="pill">${esc(s)}</span>`).join("")}</div></div>`).join("") +
      (d.students_without_mastery.length ? `<p class="hint">No mastery recorded in this sub-area for ${d.students_without_mastery.map(esc).join(", ")}, so the graph cannot place them.</p>` : "");
  $("foundations").innerHTML = (f.data.ranked || []).map((r) => `<li><span class="id">${esc(r.id)}</span>
      <span class="desc">${esc(short(r.description, 140))}</span><span class="unlocks">${r.score}</span></li>`).join("");
  loadRecall();
}
$("group-subarea").addEventListener("change", loadCaseload);

async function loadRecall() {
  const sid = $("recall-student").value;
  if (!sid) return;
  const r = await api(`/api/recall?sid=${encodeURIComponent(sid)}`);
  const d = r.data;
  if (r.outcome !== "answered_from_memory") { $("recall").innerHTML = `<p class="note">${esc(r.message)}</p>`; return; }
  const goals = d.goals.map((g) => `<div class="group"><div class="hint">${esc(g.created)}</div>
      <div class="path">${esc(g.baseline)} → ${esc(g.goal)}${g.aligned ? " · aligned " + esc(g.aligned) : ""}</div><p>${esc(g.text)}</p></div>`).join("");
  $("recall").innerHTML = `<p>${d.mastered.length} standards marked mastered, most recently ${esc((d.mastered[0] || {}).at || "never")}.</p>` +
    (goals || `<p class="hint">No saved goals yet.</p>`);
}
$("recall-student").addEventListener("change", loadRecall);

// ── ask ─────────────────────────────────────────────────────────────────────
const EXAMPLES = [
  "Where should D-1004 start next in phonics?",
  "Which students could be taught together in literature comprehension?",
  "Why is K.CC.A.1 connected to 2.NBT.A.1?",
  "Draft a goal from RF.2.3 for a grade 4 student",
  "What are the most load-bearing fraction standards?",
  "Show the staircase for RL.9.1 for a 5th grader",
];
function examples() {
  $("examples").innerHTML = EXAMPLES.map((q) => `<button type="button">${esc(q)}</button>`).join("");
  $("examples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("question").value = b.textContent; doAsk(); }));
}
async function doAsk() {
  const q = $("question").value.trim();
  if (!q) return;
  $("answer").innerHTML = `<p class="hint">Asking…</p>`;
  try {
    const r = await api("/api/ask", { question: q, context: { sid: $("student").value || undefined } });
    const paths = r.results.map((x) => {
      const d = x.data || {};
      if (d.path && Array.isArray(d.path) && d.path.length && typeof d.path[0] === "object") return d.path.map((p) => p.id).join(" → ");
      if (Array.isArray(d.path)) return d.path.join(" → ");
      if (d.climb && d.climb.length) return d.climb.map((c) => c.id).join(" → ");
      return "";
    }).filter(Boolean);
    $("answer").innerHTML = `<div class="answer"><span class="outcome o-${esc(r.outcome)}">${esc(r.outcome)}</span>
      <p>${esc(r.answer)}</p>${paths.map((p) => `<div class="path">${esc(p)}</div>`).join("")}
      <p class="hint">Tools chosen by the ${esc(r.chooser)}: ${r.calls.map((c) => `<code>${esc(c.tool)}(${esc(JSON.stringify(c.args))})</code>`).join(" ")}</p></div>`;
  } catch (e) { $("answer").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}
$("ask-form").addEventListener("submit", (e) => { e.preventDefault(); doAsk(); });

init().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="error" style="padding:16px">Could not reach the graph: ${esc(e.message)}</p>`); });

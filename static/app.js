const GRADES = ["K", "1", "2", "3", "4", "5", "6", "7", "8"];
const $ = (id) => document.getElementById(id);
const state = { students: [], subareas: [], baseline: null, depth: 1, draft: null };

const OUTCOME = {
  answered_with_path: "answered, path shown",
  answered_from_memory: "answered from saved data",
  answered: "answered",
  not_in_graph: "not in the maps",
  unknown: "not found, nothing ran",
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function short(desc, n = 140) {
  const d = String(desc || "").split("\n")[0];
  return d.length > n ? d.slice(0, n - 1).trimEnd() + "…" : d;
}
function gradeName(g) { return g === "K" ? "Kindergarten" : `Grade ${g}`; }

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  if (data.trace) showTrace(data.trace);
  return data;
}

// ── how it worked (hidden unless asked for) ─────────────────────────────────
let traceRows = [];
function showTrace(trace) {
  traceRows = [...trace.slice().reverse(), ...traceRows].slice(0, 40);
  $("trace").innerHTML = traceRows.map((t) => `<tr>
    <td>${esc(t.tool.replace(/_/g, " "))}</td>
    <td class="args">${Object.entries(t.args || {}).map(([k, v]) => `${esc(k)}=${esc(Array.isArray(v) ? v.join(",") : v)}`).join("<br>")}</td>
    <td class="o-${esc(t.outcome)}">${esc(OUTCOME[t.outcome] || t.outcome)}</td>
    <td>${Math.round(t.ms)}</td></tr>`).join("");
}
$("toggle-trace").addEventListener("click", () => {
  const panel = $("trace-panel");
  panel.hidden = !panel.hidden;
  document.querySelector(".layout").classList.toggle("with-trace", !panel.hidden);
  $("toggle-trace").textContent = panel.hidden ? "Show how it worked" : "Hide how it worked";
  $("toggle-trace").setAttribute("aria-pressed", String(!panel.hidden));
});

// ── setup ───────────────────────────────────────────────────────────────────
function fillGrades(sel, value) {
  sel.innerHTML = GRADES.map((g) => `<option value="${g}">${gradeName(g)}</option>`).join("");
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
  const opts = state.students.map((s) => `<option value="${esc(s.sid)}">${esc(s.sid)} · grade ${esc(s.grade)}</option>`).join("");
  $("student").innerHTML = `<option value="">No student</option>` + opts;
  $("recall-student").innerHTML = opts;
  if (keep) $("student").value = keep;
  if (keepRecall) $("recall-student").value = keepRecall;
}
async function loadStudents() {
  state.students = (await api("/api/students")).students;
  fillStudents();
}

async function init() {
  state.subareas = (await api("/api/subareas")).data.subareas;
  fillSubareas($("subarea"));
  fillSubareas($("group-subarea"));
  $("subarea").value = "phonics";
  $("group-subarea").value = "phonics";
  fillGrades($("grade"), "4");
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
    document.querySelector("details.add").open = false;
  } catch (e) { $("add-error").textContent = e.message; }
});

// ── starting point ──────────────────────────────────────────────────────────
$("show-baseline").addEventListener("click", async () => {
  const r = await api(`/api/baseline?subarea=${encodeURIComponent($("subarea").value)}&grade=${$("grade").value}&years_behind=${$("years").value || 0}`);
  $("baseline-card").hidden = false;
  $("stair-card").hidden = true;
  $("goal-card").hidden = true;
  $("baseline-note").textContent = r.data.note || (r.outcome === "not_in_graph" ? r.message : "");
  $("baseline-list").innerHTML = (r.data.options || []).map((o) => `<li data-id="${esc(o.id)}">
      <div class="row1"><span class="code">${esc(o.id)}</span>
      <span class="leads" title="How many later standards build on this one">leads to ${o.unlocks} later skill${o.unlocks === 1 ? "" : "s"}</span></div>
      <div>${esc(short(o.description, 160))}</div></li>`).join("");
  $("baseline-list").querySelectorAll("li").forEach((li) => li.addEventListener("click", () => {
    $("baseline-list").querySelectorAll("li").forEach((x) => x.classList.toggle("sel", x === li));
    state.baseline = li.dataset.id;
    state.depth = 1;
    loadStair();
  }));
  $("baseline-card").scrollIntoView({ behavior: "smooth", block: "start" });
});

// ── the staircase ───────────────────────────────────────────────────────────
async function loadStair() {
  const sid = $("student").value;
  const r = await api(`/api/staircase?standard=${encodeURIComponent(state.baseline)}&grade=${$("grade").value}&depth=${state.depth}` + (sid ? `&sid=${encodeURIComponent(sid)}` : ""));
  $("stair-card").hidden = false;
  $("goal-card").hidden = true;
  renderStair(r, !!sid);
}

function step(n, cls, label, canCheck, inner = "") {
  const gi = Math.max(0, GRADES.indexOf(n.grade));
  const box = canCheck ? `<input type="checkbox" data-id="${esc(n.id)}" ${n.mastered ? "checked" : ""} aria-label="Can already do ${esc(n.id)}">` : "";
  return `<div class="st ${cls} ${n.mastered ? "done" : ""}" style="--g:${gi}">${box}
    <div class="body"><div class="label">${esc(label)} <span class="code">${esc(n.id)}</span></div>
    <div class="text" title="${esc(n.description)}">${esc(short(n.description))}</div>${inner}</div></div>`;
}

function renderStair(r, canCheck) {
  const d = r.data;
  if (r.outcome === "unknown") { $("stair").innerHTML = `<p class="error">${esc(r.message)}</p>`; return; }
  const html = [];
  const below = (d.below || []).slice().sort((a, b) => GRADES.indexOf(a.grade) - GRADES.indexOf(b.grade));
  for (const b of below) html.push(step(b, "below", `${gradeName(b.grade)} · earlier step`, canCheck));

  const parts = d.parts || [];
  const partsHtml = parts.length ? `<details><summary>${parts.length} smaller skills inside this standard</summary>
      ${parts.map((p) => `<label class="${p.mastered ? "done" : ""}">${canCheck ? `<input type="checkbox" data-id="${esc(p.id)}" ${p.mastered ? "checked" : ""}>` : ""}
        <span title="${esc(p.description)}">${esc(short(p.description, 120))}</span></label>`).join("")}</details>` : "";
  const baseMastered = (d.climb[0] || {}).mastered;
  html.push(step({ ...d.standard, mastered: baseMastered }, "base", `${gradeName(d.standard.grade)} · starting point`, canCheck, partsHtml));

  const climb = (d.climb || []).slice(1);
  climb.forEach((c, i) => {
    const isTop = i === climb.length - 1 && c.gi === GRADES.indexOf(d.student_grade);
    html.push(step(c, isTop ? "top" : "climb", `${gradeName(c.grade)}${isTop ? " · grade level" : ""}`, canCheck));
  });
  $("stair").innerHTML = html.join("");
  $("climb-note").textContent = d.climb_note || (canCheck ? "" : "Choose a student to check off what they can do.");
  $("widen").hidden = state.depth >= 3 || !below.length;

  $("stair").querySelectorAll("input[type=checkbox]").forEach((cb) => cb.addEventListener("change", async () => {
    try {
      await api("/api/mastery", { sid: $("student").value, standards: [cb.dataset.id], mastered: cb.checked });
      const holder = cb.closest("label") || cb.closest(".st");
      holder.classList.toggle("done", cb.checked);
    } catch (e) {
      cb.checked = !cb.checked;
      $("climb-note").textContent = "Not saved: " + e.message;
    }
  }));
}

$("widen").addEventListener("click", () => { state.depth = Math.min(3, state.depth + 1); loadStair(); });

// ── the goal ────────────────────────────────────────────────────────────────
$("draft").addEventListener("click", async () => {
  const sid = $("student").value || null;
  $("draft").disabled = true;
  $("draft").textContent = "Writing…";
  try {
    const r = await api("/api/draft", { baseline: state.baseline, grade: $("grade").value, sid });
    state.draft = r;
    renderGoal(r, sid);
  } finally {
    $("draft").disabled = false;
    $("draft").textContent = "Write the goal";
  }
});

function renderGoal(r, sid) {
  $("goal-card").hidden = false;
  $("saved").textContent = "";
  if (r.outcome !== "answered_with_path") {
    $("goal-note").textContent = r.message;
    $("goal-cards").innerHTML = "";
    $("goal-meta").textContent = "";
    $("save-goal").disabled = true;
    $("copy-goal").disabled = true;
    return;
  }
  const d = r.data;
  $("goal-note").textContent = [d.goal_note, d.aligned_note, d.objectives_note].filter(Boolean).join(" ");
  const card = (cls, label, n, text) => `<div class="gc ${cls}">
      <div class="label"><span>${esc(label)}</span><span class="code" title="${esc(n.description)}">${esc(n.standard)}</span></div>
      <p>${esc(text)}</p></div>`;
  const parts = [card("", "Where the student is now", d.baseline, d.baseline.text)];
  d.objectives.forEach((o, i) => parts.push(card("", `Objective ${i + 1}`, o, o.text)));
  parts.push(card("goal", "Annual goal", d.goal, d.goal.text));
  $("goal-cards").innerHTML = parts.join("");
  $("goal-meta").textContent = (d.aligned ? `Aligned to ${d.aligned.standard} (${gradeName(d.aligned.grade).toLowerCase()}). ` : "")
    + `Path: ${d.path.join(" → ")}`;
  $("checks").innerHTML = d.phrase_checks.map((c) => `<li>${esc(c.standard)}: ${c.source === "model" ? (c.accepted ? "reworded, passed the check" : `rewording rejected (${esc(c.check)}), used the standard's own words`) : "the standard's own words"}</li>`).join("");
  $("copy-goal").disabled = false;
  $("save-goal").disabled = !sid;
  $("saved").textContent = sid ? "" : "Choose a student to save.";
  $("goal-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("copy-goal").addEventListener("click", async () => {
  const d = state.draft.data;
  const lines = [`Baseline (${d.baseline.standard}): ${d.baseline.text}`,
    ...d.objectives.map((o, i) => `Objective ${i + 1} (${o.standard}): ${o.text}`),
    `Annual goal (${d.goal.standard}): ${d.goal.text}`];
  if (d.aligned) lines.push(`Aligned grade-level standard: ${d.aligned.standard}`);
  try { await navigator.clipboard.writeText(lines.join("\n\n")); $("saved").textContent = "Copied."; }
  catch { $("saved").textContent = "Copy is blocked in this browser; select the text instead."; }
});

$("save-goal").addEventListener("click", async () => {
  const r = await api("/api/goals", { sid: $("student").value, draft: state.draft.data });
  $("saved").textContent = r.outcome === "answered" ? "Saved. It will be here next time." : r.message;
  loadRecall();
});

// ── caseload ────────────────────────────────────────────────────────────────
async function loadCaseload() {
  const key = $("group-subarea").value;
  const [g, f] = await Promise.all([api(`/api/groups?subarea=${encodeURIComponent(key)}`), api(`/api/foundations?subarea=${encodeURIComponent(key)}&limit=5`)]);
  const d = g.data;
  $("groups").innerHTML = g.outcome === "unknown" || g.outcome === "not_in_graph"
    ? `<p class="hint">${esc(g.message)}</p>`
    : d.groups.slice(0, 6).map((x) => `<div class="group">
        <div class="row1"><span>${esc(gradeName(x.grade))} · <span class="code">${esc(x.id)}</span></span><span class="hint">${x.students.length} students</span></div>
        <div title="${esc(x.description)}">${esc(short(x.description, 120))}</div>
        <div>${x.students.map((s) => `<span class="pill">${esc(s)}</span>`).join("")}</div></div>`).join("") +
      (d.groups.length > 6 ? `<p class="hint">${d.groups.length - 6} smaller groups not shown.</p>` : "") +
      (d.students_without_mastery.length ? `<p class="hint">Nothing checked off yet in this area for ${d.students_without_mastery.map(esc).join(", ")}.</p>` : "");
  $("foundations").innerHTML = (f.data.ranked || []).map((r) => `<li><span class="code">${esc(r.id)}</span>
      <span title="${esc(r.description)}">${esc(short(r.description, 110))}</span></li>`).join("");
  loadRecall();
}
$("group-subarea").addEventListener("change", loadCaseload);

async function loadRecall() {
  const sid = $("recall-student").value;
  if (!sid) return;
  const r = await api(`/api/recall?sid=${encodeURIComponent(sid)}`);
  const d = r.data;
  if (r.outcome !== "answered_from_memory") { $("recall").innerHTML = `<p class="hint">${esc(r.message)}</p>`; return; }
  const goals = d.goals.map((g) => `<div class="group">
      <div class="row1"><span class="code">${esc(g.baseline)} → ${esc(g.goal)}</span><span class="hint">${esc((g.created || "").slice(0, 10))}</span></div>
      <p>${esc(g.text)}</p></div>`).join("");
  $("recall").innerHTML = (goals || `<p class="hint">No saved goals yet.</p>`) +
    `<p class="hint">${d.mastered.length} skills checked off.</p>`;
}
$("recall-student").addEventListener("change", loadRecall);

// ── ask ─────────────────────────────────────────────────────────────────────
const EXAMPLES = [
  "Where should D-1004 start next in phonics?",
  "Which students could work together in literature?",
  "Why is K.CC.A.1 connected to 2.NBT.A.1?",
  "What are the most important fraction skills?",
];
function examples() {
  $("examples").innerHTML = EXAMPLES.map((q) => `<button type="button">${esc(q)}</button>`).join("");
  $("examples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("question").value = b.textContent; doAsk(); }));
}
async function doAsk() {
  const q = $("question").value.trim();
  if (!q) return;
  $("answer").innerHTML = `<p class="hint">Thinking…</p>`;
  try {
    const r = await api("/api/ask", { question: q, context: { sid: $("student").value || undefined } });
    const paths = r.results.map((x) => {
      const d = x.data || {};
      if (Array.isArray(d.path) && d.path.length) return d.path.map((p) => (typeof p === "object" ? p.id : p)).join(" → ");
      if (d.climb && d.climb.length) return d.climb.map((c) => c.id).join(" → ");
      return "";
    }).filter(Boolean);
    $("answer").innerHTML = `<div class="answer"><p>${esc(r.answer)}</p>${paths.map((p) => `<span class="code">${esc(p)}</span>`).join("")}</div>`;
  } catch (e) { $("answer").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}
$("ask-form").addEventListener("submit", (e) => { e.preventDefault(); doAsk(); });

init().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="error" style="padding:16px">Could not reach the graph: ${esc(e.message)}</p>`); });

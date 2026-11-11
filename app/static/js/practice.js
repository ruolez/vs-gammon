const STORAGE_KEY = "gammon-practice";
const MODE_TEXT = { due: t("Missed first, then new"), misses: t("Only missed"), new: t("Only new"), all: t("Everything") };
const SEVERITY_TEXT = { doubtful: t("Errors"), bad: t("Bad or worse"), very_bad: t("Very bad only"), all: t("Every decision") };
const KIND_TEXT = { "": t("Checker and cube"), checker: t("Checker plays"), cube: t("Cube decisions") };

const state = {
  thresholds: null, matches: [], queue: [], index: 0, results: [], cache: new Map(),
  session: { answered: 0, correct: 0, requeued: new Set() },
  d: null, phase: "idle", start: null, frame: null, remaining: [], history: [], finals: null, selected: null,
  result: null, arrows: new Set(Prefs.get("practice.arrows", ["yours", "best"])), candidate: null,
};

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch (_) { return {}; }
}

function savePrefs() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      player: $("s-player").value, severity: $("s-severity").value, kind: $("s-kind").value,
      mode: $("s-mode").value, match: $("s-match").value, shuffle: $("s-shuffle").checked, set: $("s-set").value,
    }));
  } catch (_) {}
}

function minError() {
  const s = $("s-severity").value;
  return s === "all" ? 0 : state.thresholds[s];
}

function queryString() {
  const set = $("s-set").value;
  const q = new URLSearchParams({ min_error: set ? 0 : minError(), mode: $("s-mode").value });
  if (set) q.set("tag", set);
  if (!set && $("s-player").value) q.set("player_name", $("s-player").value);
  if (!set && $("s-match").value) q.set("match_id", $("s-match").value);
  if ($("s-kind").value) q.set("kind", $("s-kind").value);
  return q;
}

function fillSets(value) {
  $("s-set").innerHTML = `<option value="">${t("All positions")}</option>`
    + Tags.list.map((tag) => `<option value="${tag.id}">${esc(tag.name)} (${tag.count})</option>`).join("");
  $("s-set").value = [...$("s-set").options].some((o) => o.value === value) ? value : "";
}

function syncSetControls() {
  const tagged = Boolean($("s-set").value);
  ["s-player", "s-severity", "s-match"].forEach((id) => ($(id).disabled = tagged));
  $("set-note").hidden = !tagged;
}

function shuffle(items) {
  const copy = items.slice();
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function renderSummary() {
  const match = state.matches.find((m) => String(m.id) === $("s-match").value);
  const tag = Tags.byId(Number($("s-set").value));
  const chips = tag ? [tag.name, KIND_TEXT[$("s-kind").value], MODE_TEXT[$("s-mode").value]] : [
    $("s-player").value || t("Both players"),
    SEVERITY_TEXT[$("s-severity").value],
    KIND_TEXT[$("s-kind").value],
    MODE_TEXT[$("s-mode").value],
    match ? `${match.player1} ${t("vs")} ${match.player2}, ${shortDate(match.event_date)}` : $("s-match").value ? $("s-match").selectedOptions[0].textContent : t("All matches"),
  ];
  if ($("s-shuffle").checked) chips.push(t("Shuffled"));
  $("summary").innerHTML = chips.map((c, i) => `<span class="chip">${i === 0 ? `<strong>${esc(c)}</strong>` : esc(c)}</span>`).join("");
}

function renderStats(stats) {
  const accuracy = stats.attempts ? `${Math.round((100 * stats.correct) / stats.attempts)}%` : "–";
  const items = [[stats.new, t("new")], [stats.missed, t("missed")], [stats.mastered, t("solved")], [accuracy, t("accuracy · {tries}", { tries: plural(stats.attempts, "try") })]];
  $("stats").innerHTML = items.map(([n, l]) => `<div class="mini-stat"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
}

function renderProgress() {
  const total = state.queue.length;
  const done = Math.min(state.session.answered, total);
  $("progress").style.width = total ? `${(100 * done) / total}%` : "0%";
  $("progressbar").setAttribute("aria-valuenow", String(done));
  $("progressbar").setAttribute("aria-valuemax", String(total));
  $("progress-text").textContent = total
    ? t("{n} of {total} · {done} answered", { n: Math.min(state.index + 1, total), total, done })
    : t("{done} / {total} this session", { done, total });
}

function renderNav() {
  const empty = !state.queue.length || state.phase === "idle";
  $("prev-pos").disabled = empty || (state.index === 0 && state.phase !== "done");
  $("next-pos").disabled = empty || state.phase === "done";
}

async function go(delta) {
  if (!state.queue.length || state.phase === "idle") return;
  if (state.phase === "done") {
    if (delta < 0) await showPosition().catch((err) => toast(err.message, true));
    return;
  }
  const index = state.index + delta;
  if (index < 0) return;
  if (index >= state.queue.length) return showDone();
  state.index = index;
  try {
    await showPosition();
  } catch (err) {
    toast(err.message, true);
  }
}

async function startSession() {
  savePrefs();
  renderSummary();
  try {
    const { items, stats } = await api.get(`/api/practice/queue?${queryString()}`);
    renderStats(stats);
    const ids = items.map((i) => i.id);
    state.queue = $("s-shuffle").checked ? shuffle(ids) : ids;
    state.index = 0;
    state.results = [];
    state.cache.clear();
    state.session = { answered: 0, correct: 0, requeued: new Set() };
    state.phase = "loading";
    renderProgress();
    if (!state.queue.length) return showEmpty();
    await showPosition();
  } catch (err) {
    toast(err.message, true);
  }
}

function clearStage(prompt) {
  $("prompt").textContent = prompt;
  $("facts").innerHTML = "";
  $("bar").innerHTML = "";
  $("bar").className = "answer-bar";
  $("bar").hidden = true;
}

function showEmpty() {
  state.phase = "idle";
  renderNav();
  clearStage(t("Nothing due here"));
  const why = $("s-set").value
    ? t('No positions with this tag match these options. Choose "Everything" to revisit solved ones, or tag more positions on the Positions page.')
    : t('No positions match these options. Choose "Everything" to revisit solved ones, lower the error level, or import another match.');
  $("board").innerHTML = `<div class="empty tall">${icon("check")}<strong>${t("You are all caught up")}</strong><p>${why}</p><button class="btn secondary" id="open-options">${t("Change options")}</button></div>`;
  $("open-options").addEventListener("click", () => toggleOptions(true));
  $("panel").innerHTML = `<h2>${t("How practice works")}</h2><div class="tips"><div>${t("Every error you make in an analysed match becomes a practice position.")}</div><div>${t("Answer correctly and it counts as solved. Miss it and it comes back first next time.")}</div></div>`;
}

function showDone() {
  state.phase = "done";
  Tags.closePicker();
  renderNav();
  const { answered, correct } = state.session;
  const pct = answered ? Math.round((100 * correct) / answered) : 0;
  clearStage(t("Session complete"));
  $("board").innerHTML = `<div class="session-done">
    <div class="score">${correct}<small> / ${answered}</small></div>
    <h2>${pct >= 80 ? t("Strong session") : pct >= 50 ? t("Good work") : t("Keep at it")}</h2>
    <p class="muted">${t("{pct}% right. Missed positions stay due until you solve them.", { pct })}</p>
    <div class="row-gap top"><button class="btn lg" id="again">${icon("refresh")}${t("Practise again")}</button><a class="btn lg secondary" href="/">${t("Back to dashboard")}</a></div></div>`;
  $("panel").innerHTML = `<h2>${t("Next steps")}</h2><div class="tips"><div>${t("Look at the positions you missed in Review, with every candidate move.")}</div><div>${t("Import new matches and their errors join your practice list.")}</div></div>`;
  $("again").addEventListener("click", startSession);
  api.get(`/api/practice/stats?${queryString()}`).then(({ stats }) => renderStats(stats)).catch(() => {});
  Shell.refresh();
}

function cubeText(d) {
  if (d.crawford_game) return t("Crawford game, no cube");
  if (d.cube_owner === 0) return d.cube_value > 1 ? t("Cube {n} centred", { n: d.cube_value }) : t("Cube centred");
  return t("Cube {n}, owned by {name}", { n: d.cube_value, name: esc(playerName(d, d.cube_owner)) });
}

function scoreText(d) {
  if (!d.match_length) return t("Money game");
  return `${t("{a}–{b} to {n}", { a: d.score1, b: d.score2, n: d.match_length })} (${t("{n}-away", { n: d.match_length - d.score1 })}, ${t("{n}-away", { n: d.match_length - d.score2 })})`;
}

function renderContext() {
  const d = state.d;
  const who = esc(playerName(d, d.player));
  $("prompt").innerHTML = d.kind === "checker"
    ? `<span>${t("{name} to play", { name: who })}</span>${diceSvg(d.dice)}`
    : d.kind === "cube" ? `<span>${t("{name}: double or no double?", { name: who })}</span>`
      : `<span>${t("{doubler} doubles to {n}. {name}: take or pass?", { doubler: esc(playerName(d, d.on_roll)), n: d.cube_value * 2, name: who })}</span>`;
  $("facts").innerHTML = [
    `<span class="chip"><strong>${esc(d.player1)}</strong>${t("vs")}<strong>${esc(d.player2)}</strong>${esc(shortDate(d.event_date))}</span>`,
    `<span class="chip">${t("game {game}, move {move}", { game: d.game_no, move: d.move_no })}</span>`,
    `<span class="chip">${scoreText(d)}</span>`,
    `<span class="chip">${cubeText(d)}</span>`,
    `<span class="tag-line" id="tag-line"></span>`,
  ].join("");
  Tags.mountLine($("tag-line"), d, renderSummary);
}

async function showPosition() {
  const id = state.queue[state.index];
  if (!state.cache.has(id)) state.cache.set(id, (await api.get(`/api/decisions/${id}`)).decision);
  const decision = state.cache.get(id);
  const saved = state.results[state.index];
  Tags.closePicker();
  Object.assign(state, { d: decision, phase: "answer", result: null, candidate: null, selected: null, history: [] });
  $("bar").hidden = false;
  renderContext();
  renderNav();
  renderProgress();
  if (decision.kind === "checker") {
    if (!decision.legal) {
      $("board").innerHTML = `<div class="empty">${icon("alert")}<strong>${t("Move list missing")}</strong><p>${t("This position was analysed before practice existed. Re-analyse its match on the Matches page.")}</p></div>`;
      return;
    }
    state.start = Board.onrollFrame(decision);
    state.frame = state.start;
    state.remaining = Moves.diceList(decision.dice);
    state.finals = Moves.finalPositions(state.start, decision.legal);
  }
  if (saved) {
    state.result = saved;
    return renderResult();
  }
  renderAnswerPhase();
}

const options = () => Moves.nextSteps(state.frame, state.remaining, state.finals);
const moveComplete = () => state.finals.has(Moves.frameKey(state.frame)) && options().length === 0;

function diceState() {
  const left = state.remaining.slice();
  return Moves.diceList(state.d.dice).map((value) => {
    const i = left.indexOf(value);
    if (i >= 0) {
      left.splice(i, 1);
      return { value, used: false };
    }
    return { value, used: true };
  });
}

function renderAnswerPhase() {
  const d = state.d;
  const bar = $("bar");
  bar.className = "answer-bar";
  if (d.kind === "checker") {
    const opts = options();
    const selectable = new Set(opts.map((o) => o.from));
    const targets = new Set(state.selected === null ? [] : opts.filter((o) => o.from === state.selected).map((o) => o.to));
    Board.renderWithLabels($("board"), d, { frame: state.frame, dice: diceState(), interactive: { selectable, targets, selected: state.selected } });
    const complete = moveComplete();
    bar.innerHTML = `
      <button class="btn secondary" id="undo" ${state.history.length ? "" : "disabled"}>${icon("undo")}${t("Undo")} <span class="kbd">⌫</span></button>
      <button class="btn ghost" id="reset" ${state.history.length ? "" : "disabled"}>${t("Reset")}</button>
      <span class="hint">${complete ? t("Move complete. Check it, or undo to change it.") : state.selected !== null ? t("Click a green point to move there.") : t("Click a checker to move it.")}</span>
      <span class="spacer"></span>
      <button class="btn ghost" id="reveal" title="${t("Counts as a miss, so the position comes back later")}">${icon("eye")}${t("Show answer")}</button>
      <button class="btn lg" id="submit" ${complete ? "" : "disabled"}>${t("Check")} <span class="kbd">↵</span></button>`;
    $("undo").addEventListener("click", undo);
    $("reset").addEventListener("click", reset);
    $("submit").addEventListener("click", submitChecker);
    if (state.keyboard) {
      const next = complete ? $("submit") : $("board").querySelector(state.selected !== null ? '.hit[tabindex="0"]:not([data-point="' + state.selected + '"])' : '.hit[tabindex="0"]');
      if (next) next.focus({ preventScroll: true });
    }
  } else {
    const take = d.kind === "take";
    Board.renderWithLabels($("board"), d, { bottom: d.player, cubeOffered: take });
    const [a, b] = take ? [["take", t("Take"), "T"], ["pass", t("Pass"), "P"]] : [["no_double", t("No double"), "N"], ["double", t("Double"), "D"]];
    bar.innerHTML = `
      <button class="btn lg secondary" data-action="${a[0]}">${a[1]} <span class="kbd">${a[2]}</span></button>
      <button class="btn lg secondary" data-action="${b[0]}">${b[1]} <span class="kbd">${b[2]}</span></button>
      <span class="spacer"></span>
      <button class="btn ghost" id="reveal" title="${t("Counts as a miss, so the position comes back later")}">${icon("eye")}${t("Show answer")}</button>`;
    bar.querySelectorAll("[data-action]").forEach((el) => el.addEventListener("click", () => submitCube(el.dataset.action)));
  }
  $("reveal").addEventListener("click", reveal);
  renderAnswerPanel();
}

function renderAnswerPanel() {
  const d = state.d;
  const past = d.practice && d.practice.length
    ? t(d.practice[0].revealed ? "Seen {times}; last time you looked at the answer." : d.practice[0].correct ? "Seen {times}; last time you got it right." : "Seen {times}; last time you missed it.", { times: plural(d.practice.length, "time") })
    : t("First time you see this position.");
  const tips = d.kind === "checker"
    ? `<div><span class="kbd plain">1</span>${t("Click a checker. With one place to go it moves straight away.")}</div>
       <div><span class="kbd plain">2</span>${t("With two places to go they light up green: click one.")}</div>
       <div><span class="kbd plain">⌫</span>${t("Undo a step. Esc resets, Enter checks your move.")}</div>
       <div><span class="kbd plain">Tab</span>${t("Tab moves between checkers; Enter picks one.")}</div>`
    : `<div>${t("Decide from {name}'s side, at the bottom of the board.", { name: esc(playerName(d, d.player)) })}</div>
       <div>${d.kind === "take" ? `<span class="kbd plain">T</span> ${t("Take")} · <span class="kbd plain">P</span> ${t("Pass")}` : `<span class="kbd plain">N</span> ${t("No double")} · <span class="kbd plain">D</span> ${t("Double")}`}</div>`;
  $("panel").innerHTML = `<h2>${t("Your turn")}</h2><div class="tips">${tips}</div><p class="small muted muted-note">${past}</p>`;
}

function applyOption(option) {
  state.history.push({ frame: state.frame, remaining: state.remaining });
  state.frame = Moves.applyStep(state.frame, [option.from, option.to]);
  const i = state.remaining.indexOf(option.die);
  state.remaining = state.remaining.slice(0, i).concat(state.remaining.slice(i + 1));
  state.selected = null;
  renderAnswerPhase();
}

const smallestDie = (choices) => choices.reduce((a, b) => (b.die < a.die ? b : a));

function onBoardClick(ev) {
  state.keyboard = false;
  const hit = ev.target.closest("[data-point]");
  if (hit) activatePoint(Number(hit.dataset.point));
}

function activatePoint(point) {
  if (state.phase !== "answer" || !state.d || state.d.kind !== "checker") return;
  const opts = options();
  if (state.selected !== null) {
    const choices = opts.filter((o) => o.from === state.selected && o.to === point);
    if (choices.length) return applyOption(smallestDie(choices));
  }
  const fromHere = opts.filter((o) => o.from === point);
  if (fromHere.length) {
    if (new Set(fromHere.map((o) => o.to)).size === 1) return applyOption(smallestDie(fromHere));
    state.selected = point;
    return renderAnswerPhase();
  }
  const landing = opts.filter((o) => o.to === point);
  if (landing.length && new Set(landing.map((o) => o.from)).size === 1) return applyOption(smallestDie(landing));
  state.selected = null;
  renderAnswerPhase();
}

function undo() {
  const last = state.history.pop();
  if (!last) return;
  Object.assign(state, { frame: last.frame, remaining: last.remaining, selected: null });
  renderAnswerPhase();
}

function reset() {
  if (!state.history.length) return;
  Object.assign(state, { frame: state.history[0].frame, remaining: state.history[0].remaining, history: [], selected: null });
  renderAnswerPhase();
}

async function submitChecker() {
  if (!moveComplete()) return;
  const index = state.finals.get(Moves.frameKey(state.frame));
  await sendAnswer({ legal_index: index }, state.d.legal[index].steps);
}

async function sendAnswer(body, yourSteps) {
  try {
    const result = await api.post(`/api/practice/${state.d.id}/answer`, body);
    state.result = { ...result, yourSteps, revealed: false };
    state.results[state.index] = state.result;
    state.d.practice = result.history;
    state.session.answered += 1;
    if (result.correct) state.session.correct += 1;
    else requeue();
    renderResult();
  } catch (err) {
    toast(err.message, true);
  }
}

const submitCube = (action) => sendAnswer({ action }, null);

async function reveal() {
  try {
    const { history } = await api.post(`/api/practice/${state.d.id}/reveal`);
    state.d.practice = history;
    state.result = { revealed: true, correct: false };
    state.results[state.index] = state.result;
    state.session.answered += 1;
    requeue();
    renderResult();
  } catch (err) {
    toast(err.message, true);
  }
}

function requeue() {
  const id = state.d.id;
  if (!state.session.requeued.has(id)) {
    state.session.requeued.add(id);
    state.queue.push(id);
  }
}

const bestCandidate = (d) => d.candidates.reduce((b, c) => (c.equity > b.equity ? c : b), d.candidates[0]);
const sameSteps = (a, b) => Moves.frameKey(a.reduce(Moves.applyStep, state.start)) === Moves.frameKey(b.reduce(Moves.applyStep, state.start));

function feedbackHtml() {
  const r = state.result;
  const d = state.d;
  const best = d.kind === "checker" ? bestCandidate(d).move : d.best;
  if (r.revealed) {
    return `<div class="feedback"><span class="mark">${icon("eye")}</span><div><h3>${t("Answer shown")}</h3><p>${t("Best")}: <strong>${esc(t(best))}</strong>. ${t("This one comes back later.")}</p></div></div>`;
  }
  if (r.correct) {
    const text = r.error <= 0.0005 ? t("That is the engine's top choice.") : t("Only <strong>{error}</strong> behind the best, {best}.", { error: r.error.toFixed(3), best: esc(t(best)) });
    return `<div class="feedback"><span class="mark">${icon("check")}</span><div><h3>${r.error <= 0.0005 ? t("Correct, best move!") : t("Correct")}</h3><p>${text}</p></div></div>`;
  }
  const label = r.class ? severityPhrase({ kind: d.kind, class: r.class }) : t("Not quite");
  const approx = r.approx ? ` ${t("(rough estimate)")}` : "";
  return `<div class="feedback"><span class="mark">${icon("x")}</span><div><h3>${label}</h3><p>${t("You lost <strong>{error}</strong>", { error: r.error.toFixed(3) })}${approx}. ${t("Best")}: <strong>${esc(t(best))}</strong></p></div></div>`;
}

function answerLine(kind, label, text, cost) {
  return `<div class="answer-line"><span class="line" style="background:${Board.COLORS[kind]}"></span><span class="lbl">${label}</span><span class="mv">${esc(text)}</span><span class="cost">${cost}</span></div>`;
}

function checkerAnalysis() {
  const d = state.d;
  const r = state.result;
  const best = bestCandidate(d);
  const played = d.candidates[d.played_index];
  let lines = "";
  if (!r.revealed) lines += answerLine("yours", t("You"), r.answer, r.error <= 0.0005 ? t("best") : `−${r.error.toFixed(3)}`);
  lines += answerLine("best", t("Best"), best.move, "");
  lines += answerLine("played", t("In the game"), played.move, d.error > 0.0005 ? `−${d.error.toFixed(3)}` : t("best"));
  const toggles = [["yours", t("You")], ["best", t("Best")], ["played", t("In the game")]].filter(([k]) => k !== "yours" || !r.revealed)
    .map(([k, label]) => `<button type="button" class="move-pill" data-arrow="${k}" aria-pressed="${state.arrows.has(k) && state.candidate === null}" style="--pill-color:${Board.COLORS[k]};min-height:32px"><span class="dot"></span>${label}</button>`).join("");
  const rows = d.candidates.map((c, i) => {
    const tags = [];
    if (c === best) tags.push(`<span class="tag best">${t("best")}</span>`);
    if (!r.revealed && sameSteps(c.steps, r.yourSteps)) tags.push(`<span class="tag you">${t("you")}</span>`);
    if (i === d.played_index) tags.push(`<span class="tag game">${t("game")}</span>`);
    return `<tr data-cand="${i}" class="${state.candidate === i ? "selected" : ""}"><td class="rank">${i + 1}</td><td class="mv">${esc(c.move)}${tags.join("")}</td><td class="num diff">${c === best ? formatEquity(c.equity) : (c.equity - best.equity).toFixed(3)}</td></tr>`;
  }).join("");
  return `<h2>${t("Analysis")}</h2><div class="answer-lines">${lines}</div>
    <div class="move-pills" style="grid-template-columns:repeat(${r.revealed ? 2 : 3},1fr);margin:0 0 14px">${toggles}</div>
    <table class="cands"><thead><tr><th></th><th>${t("Candidates (click to draw)")}</th><th class="num">${t("Equity")}</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function cubeAnalysis() {
  const d = state.d;
  const r = state.result;
  const c = d.cube;
  const optimal = Math.max(c.nd, Math.min(c.dt, c.dp));
  const rows = [["No double", c.nd], ["Double, take", c.dt], ["Double, pass", c.dp]].map(([label, eq]) =>
    `<div class="cube-row ${eq === optimal ? "best" : ""}"><span>${t(label)}${eq === optimal ? `<span class="tag best">${t("best")}</span>` : ""}</span><span class="eq">${formatEquity(eq)}</span><span class="diff">${eq === optimal ? "" : (eq - optimal).toFixed(3)}</span></div>`).join("");
  const win = c.probs ? `<p class="small muted muted-note">${t("{name} wins {win}% (gammons {gammon}%).", { name: esc(playerName(d, d.on_roll)), win: (c.probs[0] * 100).toFixed(1), gammon: (c.probs[1] * 100).toFixed(1) })}</p>` : "";
  return `<h2>${t("Analysis")}</h2><div class="answer-lines">
      ${r.revealed ? "" : answerLine("yours", t("You"), t(r.answer), r.error <= 0.0005 ? t("best") : `−${r.error.toFixed(3)}`)}
      ${answerLine("best", t("Right action"), t(d.best), "")}
      ${answerLine("played", t("In the game"), t(d.action), d.error > 0.0005 ? `−${d.error.toFixed(3)}` : t("best"))}
    </div><div class="small muted note-tight">${t("Equity for {name}, the doubler", { name: esc(playerName(d, d.on_roll)) })}</div><div class="cube-rows">${rows}</div>${win}`;
}

function drawResultBoard() {
  const d = state.d;
  if (d.kind !== "checker") {
    Board.renderWithLabels($("board"), d, { bottom: d.player, cubeOffered: d.kind === "take" });
    return;
  }
  const r = state.result;
  const best = bestCandidate(d);
  const arrows = [];
  if (state.candidate !== null) arrows.push({ kind: "candidate", steps: d.candidates[state.candidate].steps });
  else {
    if (state.arrows.has("played")) arrows.push({ kind: "played", steps: d.candidates[d.played_index].steps });
    if (state.arrows.has("best")) arrows.push({ kind: "best", steps: best.steps });
    const yoursIsBest = !r.revealed && sameSteps(r.yourSteps, best.steps);
    if (state.arrows.has("yours") && !r.revealed && !(yoursIsBest && state.arrows.has("best"))) arrows.push({ kind: "yours", steps: r.yourSteps });
  }
  Board.renderWithLabels($("board"), d, { frame: state.start, arrows, arrowStart: state.start });
}

function renderResult() {
  state.phase = "result";
  const d = state.d;
  const r = state.result;
  drawResultBoard();
  renderProgress();
  const last = state.index + 1 >= state.queue.length;
  const tone = r.revealed ? "shown" : r.correct ? "right" : "wrong";
  const bar = $("bar");
  bar.className = `answer-bar ${tone}`;
  bar.innerHTML = `${feedbackHtml()}<span class="spacer"></span>
    ${d.kind === "checker" && !r.correct ? `<button class="btn ghost" id="retry">${icon("reset")}${t("Try again")}</button>` : ""}
    <a class="btn ghost" href="/review?match=${d.match_id}&focus=${d.id}&min_error=all">${t("Open in Review")}</a>
    <button class="btn lg ${tone === "right" ? "go" : tone === "wrong" ? "stop" : ""}" id="next">${last ? t("Finish") : t("Continue")} <span class="kbd">↵</span></button>`;
  if ($("retry")) $("retry").addEventListener("click", retry);
  $("next").addEventListener("click", next);
  $("panel").innerHTML = d.kind === "checker" ? checkerAnalysis() : cubeAnalysis();
  $("panel").querySelectorAll("[data-arrow]").forEach((el) => el.addEventListener("click", () => {
    const k = el.dataset.arrow;
    if (state.candidate !== null) state.candidate = null;
    else state.arrows.has(k) ? state.arrows.delete(k) : state.arrows.add(k);
    Prefs.set("practice.arrows", [...state.arrows]);
    renderResult();
  }));
  $("panel").querySelectorAll("[data-cand]").forEach((el) => el.addEventListener("click", () => {
    const i = Number(el.dataset.cand);
    state.candidate = state.candidate === i ? null : i;
    renderResult();
  }));
}

function retry() {
  Object.assign(state, { phase: "answer", frame: state.start, remaining: Moves.diceList(state.d.dice), history: [], selected: null, result: null });
  renderAnswerPhase();
}

const next = () => go(1);

function toggleOptions(open) {
  const panel = $("options");
  const show = open === undefined ? panel.hidden : open;
  panel.hidden = !show;
  $("options-btn").setAttribute("aria-expanded", String(show));
}

function onKey(ev) {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) || Tags.picker || document.querySelector("dialog[open]")) return;
  if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
    ev.preventDefault();
    go(ev.key === "ArrowLeft" ? -1 : 1);
    return;
  }
  const key = ev.key.toLowerCase();
  if (key === "tab") state.keyboard = true;
  const focused = document.activeElement.closest && document.activeElement.closest("[data-point]");
  if (focused && (key === "enter" || key === " ")) {
    ev.preventDefault();
    state.keyboard = true;
    activatePoint(Number(focused.dataset.point));
    return;
  }
  if (state.phase === "result" && key === "enter") {
    ev.preventDefault();
    next();
  } else if (state.phase === "answer" && state.d) {
    if (state.d.kind === "checker") {
      if (key === "enter") { ev.preventDefault(); submitChecker(); }
      if (key === "backspace") { ev.preventDefault(); undo(); }
      if (key === "escape") reset();
    } else {
      const map = state.d.kind === "take" ? { t: "take", p: "pass" } : { n: "no_double", d: "double" };
      if (map[key]) submitCube(map[key]);
    }
  }
}

async function loadStreak(player) {
  try {
    const d = await api.get(`/api/dashboard${player ? `?player_name=${encodeURIComponent(player)}` : ""}`);
    const days = d.practice ? d.practice.streak : 0;
    const el = $("streak");
    el.className = `streak ${days ? "" : "cold"}`;
    el.innerHTML = `${icon("flame")}${t("{days} streak", { days: plural(days, "day") })}`;
  } catch (_) {}
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const [{ settings }, { players }, { matches }] = await Promise.all([api.get("/api/settings"), api.get("/api/players"), api.get("/api/matches")]);
    state.thresholds = settings.thresholds;
    state.matches = matches.filter((m) => m.status === "done");
    const prefs = loadPrefs();
    await Tags.load().catch((err) => toast(err.message, true));
    fillSets(prefs.set || "");
    $("s-player").innerHTML = `<option value="">${t("Both players")}</option>` + players.map((p) => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join("");
    $("s-player").value = prefs.player !== undefined ? prefs.player : (settings.me || "");
    $("s-match").innerHTML = `<option value="">${t("All matches")}</option>` + state.matches.map((m) =>
      `<option value="${m.id}">${esc(shortDate(m.event_date))} · ${esc(m.player1)} ${t("vs")} ${esc(m.player2)}</option>`).join("");
    ["severity", "kind", "mode", "match"].forEach((k) => {
      const el = $(`s-${k}`);
      if (prefs[k] !== undefined && [...el.options].some((o) => o.value === prefs[k])) el.value = prefs[k];
    });
    $("s-shuffle").checked = !!prefs.shuffle;
    const params = new URLSearchParams(location.search);
    if (params.get("player_name")) $("s-player").value = params.get("player_name");
    const wanted = params.get("match_id");
    if (wanted && ![...$("s-match").options].some((o) => o.value === wanted)) {
      $("s-match").insertAdjacentHTML("beforeend", `<option value="${esc(wanted)}">${t("{matches} from Review", { matches: plural(wanted.split(",").length, "match") })}</option>`);
    }
    if (wanted) $("s-match").value = wanted;
    if (params.get("kind")) $("s-kind").value = params.get("kind");
    if (params.get("severity")) $("s-severity").value = params.get("severity");
    if (params.has("tag") || params.has("match_id")) fillSets(params.get("tag") || "");
    syncSetControls();
    if ([...params.keys()].length) history.replaceState(null, "", "/practice");
  } catch (err) {
    toast(err.message, true);
    return;
  }
  ["s-player", "s-severity", "s-kind", "s-mode", "s-match", "s-shuffle"].forEach((id) => $(id).addEventListener("change", startSession));
  $("s-set").addEventListener("change", () => { syncSetControls(); startSession(); });
  $("prev-pos").innerHTML = icon("back");
  $("next-pos").innerHTML = icon("forward");
  $("prev-pos").addEventListener("click", () => go(-1));
  $("next-pos").addEventListener("click", () => go(1));
  document.addEventListener("tagschange", () => {
    const before = $("s-set").value;
    fillSets(before);
    if ($("s-set").value !== before) syncSetControls();
    renderSummary();
    if (state.d && $("tag-line")) Tags.mountLine($("tag-line"), state.d, renderSummary);
  });
  $("s-player").addEventListener("change", () => loadStreak($("s-player").value));
  $("options").addEventListener("submit", (ev) => ev.preventDefault());
  $("options-btn").addEventListener("click", () => toggleOptions());
  $("board").addEventListener("click", onBoardClick);
  document.addEventListener("keydown", onKey);
  loadStreak($("s-player").value);
  startSession();
});

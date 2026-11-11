const state = {
  matches: [], picked: new Set(), thresholds: null, decisions: [], selected: new Set(), current: null, focus: null,
  arrows: new Set(Prefs.get("review.arrows", ["played", "best"])), candidate: null, detail: null,
};

const FILTER_DEFAULTS = { matches: [], player: "", kind: "", severity: "doubtful", custom: "0.05", game: "", forced: false };

function readUrl() {
  const p = new URLSearchParams(location.search);
  state.focus = Number(p.get("focus")) || null;
  const found = {};
  if (p.has("match")) found.matches = p.get("match").split(",").filter(Boolean);
  if (p.has("player")) found.player = p.get("player");
  if (p.has("player_name")) found.player = `name:${p.get("player_name")}`;
  if (p.has("kind")) found.kind = p.get("kind");
  if (p.has("min_error")) found.severity = p.get("min_error");
  if (p.has("custom")) found.custom = p.get("custom");
  if (p.has("game")) found.game = p.get("game");
  if (p.has("forced")) found.forced = p.get("forced") === "1";
  return found;
}

function startingFilters(defaultPlayer) {
  const fromUrl = readUrl();
  const base = { ...FILTER_DEFAULTS, player: defaultPlayer ? `name:${defaultPlayer}` : "" };
  if (Object.keys(fromUrl).length) {
    const linked = { ...base, ...fromUrl };
    if (state.focus && !("player" in fromUrl)) linked.player = "";
    return linked;
  }
  const saved = Prefs.get("review.filters", {});
  if (saved.match && !saved.matches) saved.matches = [saved.match];
  delete saved.match;
  return { ...base, ...saved };
}

function onlyMatch(f) {
  return f.matches.length === 1 ? state.matches.find((m) => String(m.id) === f.matches[0]) : null;
}

function rememberFilters(f) {
  let player = f.player;
  if (player === "1" || player === "2") {
    const match = onlyMatch(f);
    player = match ? `name:${player === "1" ? match.player1 : match.player2}` : "";
  }
  Prefs.set("review.filters", { ...f, player });
}

function currentFilters() {
  return {
    matches: state.matches.filter((m) => state.picked.has(String(m.id))).map((m) => String(m.id)), player: $("f-player").value, kind: $("f-kind").value, severity: $("f-severity").value,
    custom: $("f-custom").value, game: $("f-game").value, forced: $("f-forced").checked,
  };
}

function writeUrl(f) {
  const p = new URLSearchParams();
  if (f.matches.length) p.set("match", f.matches.join(","));
  if (f.player.startsWith("name:")) p.set("player_name", f.player.slice(5));
  else if (f.player) p.set("player", f.player);
  if (f.kind) p.set("kind", f.kind);
  if (f.severity !== "doubtful") p.set("min_error", f.severity);
  if (f.severity === "custom") p.set("custom", f.custom);
  if (f.game) p.set("game", f.game);
  if (f.forced) p.set("forced", "1");
  history.replaceState(null, "", `/review${p.toString() ? `?${p}` : ""}`);
}

function minError(f) {
  if (f.severity === "all") return 0;
  if (f.severity === "custom") return Math.max(0, parseFloat(f.custom) || 0);
  return state.thresholds[f.severity];
}

function fillPlayerAndGame(f) {
  const match = onlyMatch(f);
  if (match) {
    $("f-player").innerHTML = `<option value="">${t("Both players")}</option><option value="1">${esc(match.player1)}</option><option value="2">${esc(match.player2)}</option>`;
    $("f-game").innerHTML = `<option value="">${t("All games")}</option>` + (match.games || []).map((g) =>
      `<option value="${g.game_no}">${t("Game {n}", { n: g.game_no })} (${g.score1}–${g.score2}${g.crawford ? `, ${t("Crawford")}` : ""})</option>`).join("");
    $("f-game").disabled = false;
    if (f.player.startsWith("name:")) f.player = f.player.slice(5) === match.player1 ? "1" : f.player.slice(5) === match.player2 ? "2" : "";
  } else {
    const pool = f.matches.length ? state.matches.filter((m) => f.matches.includes(String(m.id))) : state.matches;
    const names = [...new Set(pool.flatMap((m) => [m.player1, m.player2]).filter(Boolean))].sort();
    $("f-player").innerHTML = `<option value="">${t("Both players")}</option>` + names.map((n) => `<option value="name:${esc(n)}">${esc(n)}</option>`).join("");
    $("f-game").innerHTML = `<option value="">${t("All games")}</option>`;
    $("f-game").disabled = true;
  }
  if ([...$("f-player").options].some((o) => o.value === f.player)) $("f-player").value = f.player;
  if ([...$("f-game").options].some((o) => o.value === f.game)) $("f-game").value = f.game;
}

function subtitle() {
  const f = currentFilters();
  const match = onlyMatch(f);
  if (f.matches.length > 1) return t("{matches} selected", { matches: plural(f.matches.length, "match") });
  if (!match) return t("{matches} analysed", { matches: plural(state.matches.length, "match") });
  const len = match.match_length ? t("{n}-point match", { n: match.match_length }) : t("money session");
  return `${match.player1} ${t("vs")} ${match.player2} · ${len} · ${shortDate(match.event_date || match.created_at)}`;
}

async function loadDecisions() {
  const f = currentFilters();
  writeUrl(f);
  rememberFilters(f);
  $("custom-field").hidden = f.severity !== "custom";
  $("review-sub").textContent = subtitle();
  const q = new URLSearchParams({ min_error: minError(f) });
  if (f.matches.length) q.set("match_id", f.matches.join(","));
  if (f.player.startsWith("name:")) q.set("player_name", f.player.slice(5));
  else if (f.player) q.set("player", f.player);
  if (f.kind) q.set("kind", f.kind);
  if (f.game && onlyMatch(f)) q.set("game", f.game);
  if (f.forced) q.set("include_forced", "1");
  try {
    const { decisions } = await api.get(`/api/decisions?${q}`);
    state.decisions = decisions;
    const visible = new Set(decisions.map((d) => d.id));
    state.selected = new Set([...state.selected].filter((id) => visible.has(id)));
    renderRows();
    const wanted = state.focus || state.current;
    state.focus = null;
    const keep = decisions.find((d) => d.id === wanted) || decisions[0];
    showDetail(keep ? keep.id : null);
    if (keep) document.querySelector(`.drow[data-id="${keep.id}"]`)?.scrollIntoView({ block: "center" });
  } catch (err) {
    toast(err.message, true);
  }
}

function rowWhat(d) {
  return d.kind === "take" ? t("{action} (response)", { action: esc(t(d.action)) }) : esc(t(d.action));
}

function rowWho(d) {
  return `${d.kind === "checker" ? diceSvg(d.dice) : icon("cube")}<span>${esc(playerName(d, d.player))}</span>`;
}

function renderRows() {
  const all = state.picked.size !== 1;
  $("rows").innerHTML = state.decisions.map((d) => `
    <div class="drow ${d.id === state.current ? "current" : ""}" data-id="${d.id}" role="button" tabindex="-1">
      <input type="checkbox" data-select="${d.id}" ${state.selected.has(d.id) ? "checked" : ""} aria-label="${t("Select for export")}">
      <span class="where">${all ? `${esc(shortDate(d.event_date))}<br>` : ""}${t("G{game} · {move}", { game: d.game_no, move: d.move_no })}</span>
      <span class="what"><span class="mv">${rowWhat(d)}</span><span class="who" title="${t("Best")}: ${esc(t(d.best))}">${rowWho(d)}</span></span>
      <span class="err"><span class="v">${formatLoss(d.error)}</span><span class="sevtxt ${d.class || "ok"}">${d.class ? SEVERITY_LABEL[d.class] : t("Good")}</span></span>
    </div>`).join("") || `<div class="empty">${icon("check")}<strong>${t("Nothing to review")}</strong><p>${t('No decisions match these filters. Try "Every decision" or another match.')}</p></div>`;
  $("result-count").textContent = plural(state.decisions.length, "decision");
  updateSelection();
}

function updateSelection() {
  const n = state.selected.size;
  $("export-btn").disabled = n === 0;
  $("export-btn").innerHTML = `${icon("download")}${n ? t("Export {n} as .xgp", { n }) : t("Export .xgp")}`;
  const all = state.decisions.length > 0 && state.decisions.every((d) => state.selected.has(d.id));
  $("select-all").checked = all;
  $("select-all").indeterminate = n > 0 && !all;
}

function cubeText(d) {
  if (d.crawford_game) return t("Crawford game");
  if (d.cube_owner === 0) return d.cube_value > 1 ? t("Cube {n} centred", { n: d.cube_value }) : t("Cube centred");
  return `${t("Cube {n}", { n: d.cube_value })} · ${esc(playerName(d, d.cube_owner))}`;
}

function bestCandidate(d) {
  return d.candidates.reduce((b, c) => (c.equity > b.equity ? c : b), d.candidates[0]);
}

function renderBoardPanel(d) {
  const who = esc(playerName(d, d.player));
  const title = t(d.kind === "checker" ? "{name} to play" : d.kind === "cube" ? "{name}: double or not?" : "{name}: take or pass?", { name: who });
  const pills = d.kind === "checker" ? (() => {
    const best = bestCandidate(d);
    const played = d.candidates[d.played_index];
    const same = best === played;
    return `<div class="move-pills">
      <button class="move-pill" data-arrow="played" aria-pressed="${state.arrows.has("played") && state.candidate === null}" style="--pill-color:var(--arrow-game)"><span class="dot"></span>${esc(played.move)} <span class="cost">${same ? t("best") : formatLoss(d.error)}</span></button>
      <button class="move-pill" data-arrow="best" aria-pressed="${state.arrows.has("best") && state.candidate === null}" style="--pill-color:var(--arrow-best)"><span class="dot"></span>${esc(best.move)} <span class="cost">${t("best")}</span></button>
    </div>`;
  })() : "";
  $("board-panel").innerHTML = `
    <div class="position-title"><h2>${title}</h2>${d.kind === "checker" ? diceSvg(d.dice) : ""}${severityChip(d.class)}</div>
    <p class="small muted note-tight">${esc(d.player1)} ${t("vs")} ${esc(d.player2)} · ${t("game {game}, move {move}", { game: d.game_no, move: d.move_no })} · ${d.match_length ? t("{a}–{b} to {n}", { a: d.score1, b: d.score2, n: d.match_length }) : t("money")} · ${cubeText(d)}</p>
    <div id="board"></div>
    ${pills}
    <div class="xgid"><code title="XGID">${esc(d.xgid)}</code><button class="btn sm ghost" id="copy-xgid">${icon("copy")}${t("Copy XGID")}</button></div>`;
  drawBoard(d);
  $("board-panel").querySelectorAll("[data-arrow]").forEach((el) => el.addEventListener("click", () => {
    const k = el.dataset.arrow;
    if (state.candidate !== null) state.candidate = null;
    else state.arrows.has(k) ? state.arrows.delete(k) : state.arrows.add(k);
    Prefs.set("review.arrows", [...state.arrows]);
    renderDetail(d);
  }));
  $("copy-xgid").addEventListener("click", async () => {
    try {
      await (Native.available ? Native.call("copy", { text: d.xgid }) : navigator.clipboard.writeText(d.xgid));
      toast(t("XGID copied. Paste it into eXtreme Gammon."));
    } catch (_) {
      toast(t("Copy failed. Select the text and copy it by hand."), true);
    }
  });
}

function drawBoard(d) {
  if (d.kind !== "checker") {
    Board.renderWithLabels($("board"), d, { bottom: d.player, cubeOffered: d.kind === "take" });
    return;
  }
  const arrows = [];
  if (state.candidate !== null) arrows.push({ kind: "candidate", steps: d.candidates[state.candidate].steps });
  else {
    const best = bestCandidate(d);
    const played = d.candidates[d.played_index];
    if (state.arrows.has("played")) arrows.push({ kind: "played", steps: played.steps });
    if (state.arrows.has("best") && best !== played) arrows.push({ kind: "best", steps: best.steps });
  }
  Board.renderWithLabels($("board"), d, { arrows: arrows.filter((a) => a.steps) });
}

function probsBlock(probs, who) {
  if (!probs) return "";
  const [win, wg, wbg, lg, lbg] = probs;
  const pct = (x) => `${(x * 100).toFixed(1)}%`;
  return `<section><h3>${t("Winning chances for {name}", { name: esc(who) })}</h3>
    <div class="probbar"><span class="w" style="width:${win * 100}%"></span></div>
    <div class="prob-legend"><span>${t("Win")} <strong>${pct(win)}</strong> · ${t("gammon")} ${pct(wg)} · ${t("bg")} ${pct(wbg)}</span><span>${t("Lose")} <strong>${pct(1 - win)}</strong> · ${t("gammon")} ${pct(lg)}</span></div></section>`;
}

function verdict(d) {
  const cost = t("It cost {error} equity, about {pct}% in winning chances.", { error: d.error.toFixed(3), pct: (d.error * 50).toFixed(1) });
  const text = d.error <= 0.0005 ? t("This was the engine's choice.") : `${d.class ? severityPhrase(d) : t("Close")}. ${cost}`;
  return `<section><div class="verdict-line"><h3>${term(t("Equity lost"), t("Equity is your expected result from a position. A mistake loses equity; 0.1 is roughly 5% in winning chances."))}</h3><span class="big ${d.class ? "trend-bad" : "trend-good"}">${formatLoss(d.error)}</span></div><p class="small muted note-tight">${text}</p></section>`;
}

function renderAnalysis(d) {
  let body = verdict(d);
  if (d.kind === "checker") {
    const best = bestCandidate(d);
    body += `<section><h3>${t("Candidate moves")}</h3><table class="cands"><thead><tr><th></th><th>${t("Move")}</th><th class="num">${t("Equity")}</th><th class="num">${t("Diff")}</th></tr></thead><tbody>${
      d.candidates.map((c, i) => `<tr data-cand="${i}" class="${state.candidate === i ? "selected" : ""}">
        <td class="rank">${i + 1}</td>
        <td class="mv">${esc(c.move)}${c === best ? `<span class="tag best">${t("best")}</span>` : ""}${i === d.played_index ? `<span class="tag game">${t("played")}</span>` : ""}</td>
        <td class="num">${formatEquity(c.equity)}</td><td class="num diff">${c === best ? "" : (c.equity - best.equity).toFixed(3)}</td></tr>`).join("")
    }</tbody></table><p class="small muted muted-note">${t("Click a move to draw it on the board.")}</p></section>`;
    body += probsBlock((d.candidates[state.candidate ?? d.played_index] || {}).probs, playerName(d, d.on_roll));
    if (d.forced) body += `<section><p class="small muted">${t("Forced: only one legal play.")}</p></section>`;
  } else {
    const c = d.cube;
    const optimal = Math.max(c.nd, Math.min(c.dt, c.dp));
    const chosen = (label) => (d.kind === "cube" && ((label === "No double" && d.action === "No double") || (label === "Double, take" && d.action === "Double")))
      || (d.kind === "take" && ((label === "Double, take" && d.action === "Take") || (label === "Double, pass" && d.action === "Pass")));
    body += `<section><h3>${t("Cube equities for {name}", { name: esc(playerName(d, d.on_roll)) })}</h3><div class="cube-rows">${
      [["No double", c.nd], ["Double, take", c.dt], ["Double, pass", c.dp]].map(([label, eq]) => `
        <div class="cube-row ${eq === optimal ? "best" : ""}"><span>${t(label)}${chosen(label) ? `<span class="tag game">${t("played")}</span>` : ""}${eq === optimal ? `<span class="tag best">${t("best")}</span>` : ""}</span>
        <span class="eq">${formatEquity(eq)}</span><span class="diff">${eq === optimal ? "" : (eq - optimal).toFixed(3)}</span></div>`).join("")
    }</div><p class="small muted-note">${t("Right action")}: <strong>${esc(t(d.best))}</strong></p></section>`;
    body += probsBlock(c.probs, playerName(d, d.on_roll));
  }
  $("analysis").innerHTML = body;
  $("analysis").querySelectorAll("[data-cand]").forEach((el) => el.addEventListener("click", () => {
    const i = Number(el.dataset.cand);
    state.candidate = state.candidate === i ? null : i;
    renderDetail(d);
  }));
}

function renderDetail(d) {
  renderBoardPanel(d);
  renderAnalysis(d);
}

async function showDetail(id) {
  if (state.current !== id) state.candidate = null;
  state.current = id;
  document.querySelectorAll(".drow").forEach((r) => r.classList.toggle("current", Number(r.dataset.id) === id));
  if (!id) {
    $("board-panel").innerHTML = `<div class="empty">${icon("review")}<strong>${t("No decision selected")}</strong><p>${t("Pick a decision on the left.")}</p></div>`;
    $("analysis").innerHTML = "";
    return;
  }
  const d = state.decisions.find((x) => x.id === id);
  if (d) {
    renderDetail(d);
    markSeen(d);
  }
}

function markSeen(d) {
  if (d.seen_at) return;
  d.seen_at = "now";
  api.post(`/api/decisions/${d.id}/seen`).then(({ match_id, review }) => {
    const match = state.matches.find((m) => m.id === match_id);
    if (match) match.review = review;
    renderMatchMenu();
  }).catch(() => { d.seen_at = null; });
}

function addedAt(m) {
  const date = new Date(m.created_at);
  if (Number.isNaN(date.getTime())) return m.created_at || "";
  return `${shortDate(m.created_at)}, ${date.toLocaleTimeString(I18n.locale(), { hour: "numeric", minute: "2-digit" })}`;
}

function reviewBadge(m) {
  const r = m.review || { mistakes: 0, seen: 0, reviewed: false };
  const title = r.reviewed
    ? t("Reviewed. Click to mark it not reviewed.")
    : t("{seen} of {total} mistakes opened. Click to mark the match reviewed.", { seen: r.seen, total: r.mistakes });
  return `<button type="button" class="mm-review ${r.reviewed ? "done" : ""}" data-review="${m.id}" aria-pressed="${r.reviewed}" title="${esc(title)}">${
    r.reviewed ? `${icon("check")}${t("Reviewed")}` : `${r.seen}/${r.mistakes}`}</button>`;
}

function matchButtonText() {
  const picked = state.matches.filter((m) => state.picked.has(String(m.id)));
  if (!picked.length) return t("All matches");
  if (picked.length === 1) return `${picked[0].player1} ${t("vs")} ${picked[0].player2}`;
  return plural(picked.length, "match");
}

function renderMatchMenu() {
  $("f-match").textContent = matchButtonText();
  const menu = $("match-menu");
  if (menu.hidden) return;
  const focused = menu.contains(document.activeElement) ? document.activeElement : null;
  const focusKey = !focused ? null : focused.dataset.review ? `[data-review="${focused.dataset.review}"]`
    : focused.matches("input") ? `input[value="${focused.value}"]` : focused.matches("[data-clear]") ? "[data-clear]" : null;
  const scroll = menu.querySelector(".mm-list")?.scrollTop || 0;
  const n = state.picked.size;
  menu.innerHTML = `<div class="mm-head"><span>${n ? t("{matches} selected", { matches: plural(n, "match") }) : t("Showing all matches")}</span>
      <button type="button" class="btn ghost sm" data-clear ${n ? "" : "disabled"}>${t("Show all")}</button></div>
    <div class="mm-list">${state.matches.map((m) => {
      const length = m.match_length ? t("{n}-point", { n: m.match_length }) : t("Money");
      const played = m.event_date ? ` · ${t("played {date}", { date: esc(shortDate(m.event_date)) })}` : "";
      return `<div class="mm-row ${state.picked.has(String(m.id)) ? "picked" : ""}">
        <label class="mm-pick"><input type="checkbox" value="${m.id}" ${state.picked.has(String(m.id)) ? "checked" : ""}>
          <span class="mm-text"><span class="mm-title">${esc(m.player1)} ${t("vs")} ${esc(m.player2)}</span>
          <span class="mm-sub">${t("Added {when}", { when: esc(addedAt(m)) })} · ${length}${played}</span></span></label>
        ${reviewBadge(m)}
      </div>`;
    }).join("") || `<div class="empty small">${t("No analysed matches yet")}</div>`}</div>`;
  menu.querySelector(".mm-list").scrollTop = scroll;
  if (focusKey) (menu.querySelector(focusKey) || menu.querySelector("input"))?.focus();
}

function toggleMatchMenu(open) {
  const menu = $("match-menu");
  menu.hidden = !open;
  $("f-match").setAttribute("aria-expanded", String(open));
  renderMatchMenu();
  if (open) menu.querySelector("input")?.focus();
}

function pickedChanged() {
  renderMatchMenu();
  const kept = Prefs.get("review.filters", {}).player || "";
  fillPlayerAndGame({ ...currentFilters(), player: kept, game: "" });
  loadDecisions();
}

async function exportSelected() {
  const ids = state.decisions.filter((d) => state.selected.has(d.id)).map((d) => d.id);
  const button = $("export-btn");
  button.disabled = true;
  button.textContent = t("Exporting…");
  try {
    const response = await api.request("POST", "/api/export", { decision_ids: ids });
    const blob = await response.blob();
    const header = (response.headers.get("Content-Disposition") || "").match(/filename=([^;]+)/);
    const filename = header ? header[1].replace(/"/g, "") : "positions.zip";
    const done = t("Exported {positions} for eXtreme Gammon", { positions: plural(ids.length, "position") });
    if (Native.available) {
      const path = await Native.saveBlob(blob, filename);
      if (path) toast(done, false, { label: t("Show in Finder"), run: () => Native.call("reveal", { path }) });
    } else {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 5000);
      toast(done);
    }
  } catch (err) {
    toast(err.message, true);
  }
  updateSelection();
}

function practiceLink() {
  const f = currentFilters();
  const q = new URLSearchParams();
  if (f.matches.length) q.set("match_id", f.matches.join(","));
  if (f.player.startsWith("name:")) q.set("player_name", f.player.slice(5));
  else if (f.player) {
    const match = onlyMatch(f);
    if (match) q.set("player_name", f.player === "1" ? match.player1 : match.player2);
  }
  if (f.kind) q.set("kind", f.kind);
  if (["doubtful", "bad", "very_bad", "all"].includes(f.severity)) q.set("severity", f.severity);
  return `/practice?${q}`;
}

function step(delta) {
  if (!state.decisions.length) return;
  const index = state.decisions.findIndex((d) => d.id === state.current);
  const next = state.decisions[Math.min(state.decisions.length - 1, Math.max(0, index + delta))];
  showDetail(next.id);
  document.querySelector(`.drow[data-id="${next.id}"]`)?.scrollIntoView({ block: "nearest" });
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const [{ matches }, { settings }] = await Promise.all([api.get("/api/matches"), api.get("/api/settings")]);
    state.matches = matches.filter((m) => m.status === "done").sort((a, b) => b.id - a.id);
    state.thresholds = settings.thresholds;
    state.me = settings.me || "";
  } catch (err) {
    toast(err.message, true);
    return;
  }
  const f = startingFilters(state.me);
  const known = new Set(state.matches.map((m) => String(m.id)));
  state.picked = new Set((f.matches || []).filter((id) => known.has(id)));
  f.matches = [...state.picked];
  renderMatchMenu();
  fillPlayerAndGame(f);
  $("f-kind").value = f.kind;
  $("f-severity").value = f.severity;
  $("f-custom").value = f.custom;
  $("f-forced").checked = f.forced;

  $("f-match").addEventListener("click", () => toggleMatchMenu($("match-menu").hidden));
  $("match-menu").addEventListener("change", (ev) => {
    if (ev.target.type !== "checkbox") return;
    ev.target.checked ? state.picked.add(ev.target.value) : state.picked.delete(ev.target.value);
    pickedChanged();
  });
  $("match-menu").addEventListener("click", async (ev) => {
    if (ev.target.closest("[data-clear]")) {
      state.picked.clear();
      pickedChanged();
      return;
    }
    const button = ev.target.closest("[data-review]");
    if (!button) return;
    const match = state.matches.find((m) => m.id === Number(button.dataset.review));
    try {
      const { review } = await api.put(`/api/matches/${match.id}/reviewed`, { reviewed: !match.review.reviewed });
      match.review = review;
      renderMatchMenu();
    } catch (err) {
      toast(err.message, true);
    }
  });
  document.addEventListener("click", (ev) => {
    if (!$("match-menu").hidden && !ev.composedPath().includes($("match-dd"))) toggleMatchMenu(false);
  });
  $("match-dd").addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("match-menu").hidden) {
      toggleMatchMenu(false);
      $("f-match").focus();
    }
  });
  ["f-player", "f-kind", "f-severity", "f-game", "f-forced"].forEach((id) => $(id).addEventListener("change", loadDecisions));
  $("f-custom").addEventListener("input", () => { clearTimeout(state.timer); state.timer = setTimeout(loadDecisions, 300); });
  $("filters").addEventListener("submit", (ev) => ev.preventDefault());
  $("rows").addEventListener("click", (ev) => {
    const box = ev.target.closest("[data-select]");
    const row = ev.target.closest(".drow");
    if (box) {
      const id = Number(box.dataset.select);
      box.checked ? state.selected.add(id) : state.selected.delete(id);
      updateSelection();
    } else if (row) {
      showDetail(Number(row.dataset.id));
    }
  });
  $("select-all").addEventListener("change", (ev) => {
    state.decisions.forEach((d) => (ev.target.checked ? state.selected.add(d.id) : state.selected.delete(d.id)));
    renderRows();
  });
  $("export-btn").addEventListener("click", exportSelected);
  $("practice-btn").addEventListener("click", () => (location.href = practiceLink()));
  document.addEventListener("keydown", (ev) => {
    if (!$("match-menu").hidden) return;
    const tag = document.activeElement.tagName;
    if (["SELECT", "TEXTAREA"].includes(tag) || (tag === "INPUT" && document.activeElement.type !== "checkbox")) return;
    if (ev.key === "ArrowDown" || ev.key === "j") { ev.preventDefault(); step(1); }
    if (ev.key === "ArrowUp" || ev.key === "k") { ev.preventDefault(); step(-1); }
    if (ev.key === " " && state.current) {
      ev.preventDefault();
      state.selected.has(state.current) ? state.selected.delete(state.current) : state.selected.add(state.current);
      renderRows();
    }
  });
  loadDecisions();
});

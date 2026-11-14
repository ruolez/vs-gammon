const PREFS_KEY = "moves.filters";

const state = {
  matches: [], picked: new Set(), thresholds: null, decisions: [], selected: new Set(), current: null, shown: null, focus: null,
  candidate: null, hover: null, revealed: false, detail: null,
};

const FILTER_DEFAULTS = {
  matches: [], player: "", kind: "", severity: "all", custom: "0.05", game: "", forced: false, tag: "", tagMatch: "any",
};

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
  if (p.has("tag")) found.tag = p.get("tag");
  if (p.has("tag_match")) found.tagMatch = p.get("tag_match");
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
  const saved = Prefs.get(PREFS_KEY, null) || Prefs.get("positions.filters", {});
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
  Prefs.set(PREFS_KEY, { ...f, player });
}

function currentFilters() {
  return {
    matches: state.matches.filter((m) => state.picked.has(String(m.id))).map((m) => String(m.id)), player: $("f-player").value, kind: $("f-kind").value, severity: $("f-severity").value,
    custom: $("f-custom").value, game: $("f-game").value, forced: $("f-forced").checked,
    tag: state.tagFilter.value().tag, tagMatch: state.tagFilter.value().match,
  };
}

function writeUrl(f) {
  const p = new URLSearchParams();
  if (f.matches.length) p.set("match", f.matches.join(","));
  if (f.player.startsWith("name:")) p.set("player_name", f.player.slice(5));
  else if (f.player) p.set("player", f.player);
  if (f.kind) p.set("kind", f.kind);
  if (f.severity !== FILTER_DEFAULTS.severity) p.set("min_error", f.severity);
  if (f.severity === "custom") p.set("custom", f.custom);
  if (f.game) p.set("game", f.game);
  if (f.forced) p.set("forced", "1");
  if (f.tag) p.set("tag", f.tag);
  if (f.tag.includes(",") && f.tagMatch === "all") p.set("tag_match", "all");
  history.replaceState(null, "", `/moves${p.toString() ? `?${p}` : ""}`);
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
  const q = new URLSearchParams({ min_error: minError(f), group: "position" });
  if (f.matches.length) q.set("match_id", f.matches.join(","));
  if (f.player.startsWith("name:")) q.set("player_name", f.player.slice(5));
  else if (f.player) q.set("player", f.player);
  if (f.kind) q.set("kind", f.kind);
  if (f.game && onlyMatch(f)) q.set("game", f.game);
  if (f.forced) q.set("include_forced", "1");
  if (f.tag) q.set("tag", f.tag);
  if (f.tagMatch === "all") q.set("tag_match", "all");
  state.loadedTag = f.tag;
  try {
    const { decisions } = await api.get(`/api/decisions?${q}`);
    state.decisions = decisions;
    const visible = new Set(decisions.map((d) => d.id));
    state.selected = new Set([...state.selected].filter((id) => visible.has(id)));
    renderRows();
    const wanted = state.focus || state.shown;
    state.focus = null;
    const keep = rowOf(wanted) || decisions[0];
    showDetail(keep ? keep.id : null, keep && keep.copies.some((c) => c.id === wanted) ? wanted : null);
    if (keep) scrollListTo(keep.id, true);
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

function rowTags(d) {
  return d.tags && d.tags.length ? `<span class="row-tags">${Tags.chips(d.tags)}</span>` : "";
}

function selectedDecisions() {
  return state.decisions.filter((d) => state.selected.has(d.id));
}

function tagsChanged() {
  if (state.tagFilter.value().tag !== state.loadedTag) return loadDecisions();
  renderRows();
  const d = state.decisions.find((x) => x.id === state.current);
  if (d) renderTagLine(d);
}

function rowOf(id) {
  return state.decisions.find((d) => d.id === id || (d.copies || []).some((c) => c.id === id));
}

function renderTagLine(d) {
  if (!$("tag-line")) return;
  Tags.mountLine($("tag-line"), d, () => {
    const row = rowOf(d.id);
    if (row && row !== d) row.tags = d.tags;
    renderRows();
  });
}

function cameUp(n) {
  return t("This position came up {times}", { times: plural(n, "time") });
}

function deepBadge(d) {
  if (!d.deep_mode) return "";
  const label = d.deep_mode === "rollout" ? t("Rolled out") : t("Evaluated deeper");
  return `<span class="deep-badge" title="${label}">${d.deep_mode === "rollout" ? "R" : "+"}</span>`;
}

function copiesBadge(d) {
  const n = (d.copies || []).length;
  return n > 1 ? `<span class="copies-badge" title="${cameUp(n)}">×${n}</span>` : "";
}

function renderRows() {
  const all = state.picked.size !== 1;
  $("rows").innerHTML = state.decisions.map((d) => `
    <div class="drow ${d.id === state.current ? "current" : ""}" data-id="${d.id}" role="button" tabindex="-1">
      <input type="checkbox" data-select="${d.id}" ${state.selected.has(d.id) ? "checked" : ""} aria-label="${t("Select for export")}">
      <span class="where">${all ? `${esc(shortDate(d.event_date))}<br>` : ""}${t("G{game} · {move}", { game: d.game_no, move: d.move_no })}${copiesBadge(d)}${deepBadge(d)}</span>
      <span class="what"><span class="mv">${rowWhat(d)}</span><span class="who" title="${t("Best")}: ${esc(t(d.best))}">${rowWho(d)}</span>${rowTags(d)}</span>
      <span class="err"><span class="v">${formatLoss(d.error)}</span><span class="sevtxt ${d.class || "ok"}">${d.class ? SEVERITY_LABEL[d.class] : t("Good")}</span></span>
    </div>`).join("")
    || `<div class="empty">${icon("review")}<strong>${t("No positions here")}</strong><p>${t("No positions match these filters. Try another match or tag.")}</p></div>`;
  $("result-count").textContent = plural(state.decisions.length, "position");
  updateSelection();
}

function updateSelection() {
  const n = state.selected.size;
  $("tag-selected").disabled = n === 0;
  $("tag-selected").innerHTML = `${icon("tag")}${n ? t("Tag {n}", { n }) : t("Tag")}`;
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
  const extras = $("bp-extras");
  const keepScroll = extras && extras.dataset.shown === String(d.id) ? extras.scrollTop : 0;
  $("board-panel").innerHTML = `
    <div class="position-title"><h2>${title}</h2>${d.kind === "checker" ? diceSvg(d.dice) : ""}${severityChip(d.class)}<span class="position-facts small muted">${esc(d.player1)} ${t("vs")} ${esc(d.player2)} · ${t("game {game}, move {move}", { game: d.game_no, move: d.move_no })} · ${d.match_length ? t("{a}–{b} to {n}", { a: d.score1, b: d.score2, n: d.match_length }) : t("money")} · ${cubeText(d)}</span></div>
    <div class="board-nav solo"><div id="board"></div></div>
    <div class="bp-extras" id="bp-extras" data-shown="${d.id}">
      <div class="deep-row"><div class="deep-bar" id="deep-bar"></div><div class="tag-line" id="tag-line"></div><button class="btn sm secondary" id="copy-xgid" title="${esc(d.xgid)}">${icon("copy")}${t("Copy XGID")}</button></div>
    </div>`;
  $("bp-extras").scrollTop = keepScroll;
  drawBoard(d);
  renderTagLine(d);
  Deep.mount($("deep-bar"), d, deeperResult);
  $("copy-xgid").addEventListener("click", async () => {
    try {
      await (Native.available ? Native.call("copy", { text: d.xgid }) : navigator.clipboard.writeText(d.xgid));
      toast(t("XGID copied. Paste it into eXtreme Gammon."));
    } catch (_) {
      toast(t("Copy failed. Select the text and copy it by hand."), true);
    }
  });
}

const DEEP_FIELDS = ["candidates", "played_index", "best", "error", "class", "cube", "deep_mode", "legal", "forced"];

function deeperResult(fresh) {
  const row = state.decisions.find((x) => x.id === fresh.id);
  if (row) DEEP_FIELDS.forEach((f) => { row[f] = fresh[f]; });
  state.decisions.forEach((r) => (r.copies || []).forEach((c) => {
    if (c.id === fresh.id) Object.assign(c, { error: fresh.error, class: fresh.class });
  }));
  renderRows();
  if (state.shown === fresh.id) {
    state.candidate = null;
    state.revealed = true;
    renderDetail(row || { ...fresh, copies: (rowOf(fresh.id) || {}).copies });
  }
}

function sourceTag(c) {
  if (c.rollout) return `<span class="tag src" title="${t("Rolled out: {games}", { games: plural(c.rollout.trials, "game") })}">${t("Rollout")}</span>`;
  if (c.plies !== undefined && c.plies !== null) return `<span class="tag src">${t("{n}-ply", { n: c.plies })}</span>`;
  return "";
}

function plusMinus(std) {
  return std ? `<span class="pm" title="${t("Standard error")}">±${std.toFixed(3)}</span>` : "";
}

function bindCopies() {
  $("analysis").querySelectorAll("[data-copy]").forEach((el) => el.addEventListener("click", () => showDetail(state.current, Number(el.dataset.copy))));
}

function copiesSection(d) {
  const copies = d.copies || [];
  if (copies.length < 2) return "";
  return `<section class="copies"><h3>${cameUp(copies.length)}</h3><ul>${copies.map((c) => `
    <li><button type="button" class="copy ${c.id === d.id ? "current" : ""}" data-copy="${c.id}" aria-pressed="${c.id === d.id}">
      <span class="copy-where">${esc(shortDate(c.event_date))} · ${esc(c.player1)} ${t("vs")} ${esc(c.player2)} · ${t("G{game} · {move}", { game: c.game_no, move: c.move_no })}</span>
      <span class="copy-what">${esc(playerName(c, c.player))}: ${rowWhat({ ...c, kind: d.kind })}</span>
      <span class="copy-err ${c.class || "ok"}">${formatLoss(c.error)}</span>
    </button></li>`).join("")}</ul></section>`;
}

function drawBoard(d) {
  const index = state.decisions.findIndex((x) => x.id === state.current);
  const nav = { prev: index > 0, next: index >= 0 && index < state.decisions.length - 1 };
  if (d.kind !== "checker") {
    Board.renderWithLabels($("board"), d, { bottom: d.player, cubeOffered: d.kind === "take", nav });
    return;
  }
  const arrows = [];
  const best = bestCandidate(d);
  const shown = state.hover ?? state.candidate;
  if (shown !== null) {
    const picked = d.candidates[shown];
    arrows.push({ kind: errorClass(best.equity - picked.equity, state.thresholds) || "good", steps: picked.steps });
  } else {
    const played = d.candidates[d.played_index];
    arrows.push({ kind: d.class || "good", steps: played.steps });
    if (best !== played && state.revealed) arrows.push({ kind: "good", steps: best.steps });
  }
  Board.renderWithLabels($("board"), d, { arrows: arrows.filter((a) => a.steps), nav });
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

function reveal() {
  if (state.revealed || !state.detail) return;
  state.revealed = true;
  renderDetail(state.detail);
}

function renderAnalysis(d) {
  if (!state.revealed) {
    $("analysis").innerHTML = `<div class="analysis-hidden">${icon("eye")}<strong>${t("The best move is hidden")}</strong>
      <p>${t("Find your own answer first, then look.")}</p>
      <button type="button" class="btn" id="show-analysis">${t("Show analysis")} <span class="kbd">↵</span></button></div>${copiesSection(d)}`;
    $("analysis").dataset.shown = d.id;
    $("show-analysis").addEventListener("click", reveal);
    bindCopies();
    return;
  }
  let body = verdict(d);
  if (d.kind === "checker") {
    const best = bestCandidate(d);
    body += `<section><h3>${t("Candidate moves")}</h3><table class="cands"><thead><tr><th></th><th>${t("Move")}</th><th class="num">${t("Equity")}</th><th class="num">${t("Diff")}</th></tr></thead><tbody>${
      d.candidates.map((c, i) => `<tr data-cand="${i}" class="${state.candidate === i ? "selected" : ""}">
        <td class="rank">${i + 1}</td>
        <td class="mv">${esc(c.move)}${c === best ? `<span class="tag best">${t("best")}</span>` : ""}${i === d.played_index ? `<span class="tag game">${t("played")}</span>` : ""}${sourceTag(c)}</td>
        <td class="num">${formatEquity(c.equity)}${plusMinus(c.rollout && c.rollout.std)}</td><td class="num diff">${c === best ? "" : (c.equity - best.equity).toFixed(3)}</td></tr>`).join("")
    }</tbody></table><p class="small muted muted-note">${t("Point at a move to see it on the board. Click to keep it.")}</p></section>`;
    body += `<div id="probs">${probsBlock((d.candidates[state.hover ?? state.candidate ?? d.played_index] || {}).probs, playerName(d, d.on_roll))}</div>`;
    if (d.forced) body += `<section><p class="small muted">${t("Forced: only one legal play.")}</p></section>`;
  } else {
    const c = d.cube;
    const optimal = Math.max(c.nd, Math.min(c.dt, c.dp));
    const chosen = (label) => (d.kind === "cube" && ((label === "No double" && d.action === "No double") || (label === "Double, take" && d.action === "Double")))
      || (d.kind === "take" && ((label === "Double, take" && d.action === "Take") || (label === "Double, pass" && d.action === "Pass")));
    const source = c.rollout ? `<p class="small muted note-tight">${t("Rolled out: {games}", { games: plural(c.rollout.trials, "game") })}</p>`
      : c.plies !== undefined && c.plies !== null ? `<p class="small muted note-tight">${t("Evaluated at {n}-ply", { n: c.plies })}</p>` : "";
    const stds = c.rollout ? { "No double": c.rollout.nd_std, "Double, take": c.rollout.dt_std } : {};
    body += `<section><h3>${t("Cube equities for {name}", { name: esc(playerName(d, d.on_roll)) })}</h3>${source}<div class="cube-rows">${
      [["No double", c.nd], ["Double, take", c.dt], ["Double, pass", c.dp]].map(([label, eq]) => `
        <div class="cube-row ${eq === optimal ? "best" : ""}"><span>${t(label)}${chosen(label) ? `<span class="tag game">${t("played")}</span>` : ""}${eq === optimal ? `<span class="tag best">${t("best")}</span>` : ""}</span>
        <span class="eq">${formatEquity(eq)}${plusMinus(stds[label])}</span><span class="diff">${eq === optimal ? "" : (eq - optimal).toFixed(3)}</span></div>`).join("")
    }</div><p class="small muted-note">${t("Right action")}: <strong>${esc(t(d.best))}</strong></p></section>`;
    body += probsBlock(c.probs, playerName(d, d.on_roll));
  }
  const samePosition = $("analysis").dataset.shown === String(d.id);
  $("analysis").innerHTML = body + copiesSection(d);
  $("analysis").dataset.shown = d.id;
  if (!samePosition) $("analysis").scrollTop = 0;
  bindCopies();
  $("analysis").querySelectorAll("[data-cand]").forEach((el) => el.addEventListener("click", () => {
    const i = Number(el.dataset.cand);
    state.candidate = state.candidate === i ? null : i;
    renderDetail(d);
  }));
  const preview = (i) => {
    if (state.hover === i) return;
    state.hover = i;
    drawBoard(d);
    $("probs").innerHTML = probsBlock((d.candidates[i ?? state.candidate ?? d.played_index] || {}).probs, playerName(d, d.on_roll));
  };
  $("analysis").querySelectorAll("[data-cand]").forEach((el) => el.addEventListener("mouseenter", () => preview(Number(el.dataset.cand))));
  $("analysis").querySelector(".cands tbody")?.addEventListener("mouseleave", () => preview(null));
}

function renderDetail(d) {
  state.detail = d;
  renderBoardPanel(d);
  renderAnalysis(d);
}

async function showDetail(id, copyId = null) {
  const shown = copyId || id;
  if (state.shown !== shown) {
    state.candidate = null;
    state.hover = null;
    state.revealed = false;
    Tags.closePicker();
  }
  state.current = id;
  state.shown = shown;
  document.querySelectorAll(".drow").forEach((r) => r.classList.toggle("current", Number(r.dataset.id) === id));
  if (!id) {
    $("board-panel").innerHTML = `<div class="empty">${icon("review")}<strong>${t("No decision selected")}</strong><p>${t("Pick a decision on the left.")}</p></div>`;
    $("analysis").innerHTML = "";
    return;
  }
  const row = state.decisions.find((x) => x.id === id);
  if (!row) return;
  let d = row;
  if (shown !== row.id) {
    try {
      const { decision } = await api.get(`/api/decisions/${shown}`);
      if (state.shown !== shown) return;
      d = { ...decision, copies: row.copies };
    } catch (err) {
      toast(err.message, true);
      return;
    }
  }
  renderDetail(d);
  markSeen(d);
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
  const kept = Prefs.get(PREFS_KEY, {}).player || "";
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
  if (f.tag && f.tag !== "none") return `/practice?tag=${f.tag}${f.tagMatch === "all" ? "&tag_match=all" : ""}`;
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
  scrollListTo(next.id);
}

function scrollListTo(id, center = false) {
  const row = document.querySelector(`.drow[data-id="${id}"]`);
  if (!row) return;
  const list = $("rows");
  const r = row.getBoundingClientRect();
  const box = list.getBoundingClientRect();
  const top = r.top - box.top + list.scrollTop;
  if (center) list.scrollTop = top - (list.clientHeight - r.height) / 2;
  else if (r.top < box.top) list.scrollTop = top;
  else if (r.bottom > box.bottom) list.scrollTop = top + r.height - list.clientHeight;
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
  try {
    await Tags.load();
  } catch (err) {
    toast(err.message, true);
  }
  const f = startingFilters(state.me);
  state.tagFilter = Tags.filter($("f-tag"), { emptyLabel: t("Tag: any"), untagged: true, onChange: () => loadDecisions() });
  state.tagFilter.set(f.tag || "", f.tagMatch);
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
  document.addEventListener("tagschange", tagsChanged);
  $("tag-selected").addEventListener("click", () => Tags.togglePicker($("tag-selected"), selectedDecisions(), () => renderRows()));
  if ($("manage-tags")) $("manage-tags").addEventListener("click", () => Tags.openManager(() => loadDecisions()));
  $("f-custom").addEventListener("input", () => { clearTimeout(state.timer); state.timer = setTimeout(loadDecisions, 300); });
  $("filters").addEventListener("submit", (ev) => ev.preventDefault());
  $("board-panel").addEventListener("click", (ev) => {
    const area = ev.target.closest("[data-step]");
    if (area) step(Number(area.dataset.step));
  });
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
    if (!$("match-menu").hidden || state.tagFilter.isOpen() || Tags.picker || document.querySelector("dialog[open]")) return;
    const tag = document.activeElement.tagName;
    if (["SELECT", "TEXTAREA"].includes(tag) || (tag === "INPUT" && document.activeElement.type !== "checkbox")) return;
    if (ev.key === "ArrowDown" || ev.key === "ArrowRight" || ev.key === "j") { ev.preventDefault(); step(1); }
    if ((ev.key === "t" || ev.key === "T") && $("tag-line")) { ev.preventDefault(); $("tag-line").querySelector(".tag-btn")?.click(); }
    if (ev.key === "ArrowUp" || ev.key === "ArrowLeft" || ev.key === "k") { ev.preventDefault(); step(-1); }
    if (ev.key === "Enter" && !state.revealed && !["BUTTON", "A"].includes(tag)) { ev.preventDefault(); reveal(); }
    if (ev.key === " " && state.current) {
      ev.preventDefault();
      state.selected.has(state.current) ? state.selected.delete(state.current) : state.selected.add(state.current);
      renderRows();
    }
  });
  loadDecisions();
});

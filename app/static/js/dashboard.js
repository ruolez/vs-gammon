const PHASE_NAMES = { opening: "Opening", middle: "Middle game", race: "Race", bearoff: "Bear-off", cube: "Cube" };
let data = null;

function greeting(name) {
  const h = new Date().getHours();
  const part = h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return `${part}, ${name}`;
}

function trendText(last, avg) {
  if (last === null || avg === null || last === undefined || avg === undefined) return "";
  const diff = last - avg;
  if (Math.abs(diff) < 0.05) return "level with your average";
  return diff < 0
    ? `<span class="trend-good">${Math.abs(diff).toFixed(1)} better</span> than your average`
    : `<span class="trend-bad">${diff.toFixed(1)} worse</span> than your average`;
}

function renderStats(d) {
  const s = d.summary;
  const p = d.practice;
  const accuracy = p.attempts ? Math.round((100 * p.correct) / p.attempts) : null;
  const cells = [
    {
      label: "Last match PR", value: s.last_pr === null ? "–" : s.last_pr.toFixed(1),
      foot: s.matches > 1 ? trendText(s.last_pr, s.avg_pr) : "Average error × 500. Lower is better",
    },
    {
      label: "Errors per match", value: s.errors_per_match === null ? "–" : `${s.errors_per_match}`,
      foot: s.blunders_per_match === null ? "" : `${s.blunders_per_match} of them very bad`,
    },
    {
      label: "Due for practice", value: `${p.due}<small>of ${p.positions}</small>`,
      foot: `${p.mastered} solved · ${p.missed} missed · all time`,
    },
    {
      label: "Practice accuracy", value: accuracy === null ? "–" : `${accuracy}<small>%</small>`,
      foot: p.attempts ? `${plural(p.attempts, "answer")}, all time` : "Answer a position to start measuring",
    },
  ];
  $("stats").innerHTML = cells.map((c) => `<div class="stat"><span class="label">${c.label}</span><span class="value">${c.value}</span><span class="foot">${c.foot}</span></div>`).join("");
}

function renderFeatured(d) {
  const m = d.mistakes[0];
  $("hero-title").textContent = "Your biggest recent mistake";
  $("hero-hint").textContent = "Your PR trend appears from your second match";
  $("chart").className = "";
  if (!m) {
    $("chart").innerHTML = `<div class="empty">${icon("check")}<strong>No errors to show</strong><p>Nothing above your doubtful threshold yet.</p></div>`;
    return;
  }
  const checker = m.kind === "checker";
  const played = checker ? m.candidates[m.played_index] : null;
  const best = checker ? m.candidates.reduce((b, c) => (c.equity > b.equity ? c : b), m.candidates[0]) : null;
  const arrows = checker ? [{ kind: "played", steps: played.steps }, { kind: "best", steps: best.steps }] : null;
  const line = (kind, label, text, cost) => `<div class="answer-line"><span class="line" style="background:${Board.COLORS[kind]}"></span><span class="lbl">${label}</span><span class="mv">${esc(text)}</span><span class="cost">${cost}</span></div>`;
  $("chart").innerHTML = `<div class="featured">
    <div id="featured-board"></div>
    <div>
      <div class="what">${checker ? diceSvg(m.dice) : icon("cube")}<span>${esc(playerName(m, m.player))} ${checker ? "to play" : m.kind === "take" ? "to take or pass" : "to double or not"}</span></div>
      <p class="small muted" style="margin-top:6px">vs ${esc(m.opponent)} · ${esc(shortDate(m.event_date))} · game ${m.game_no}, move ${m.move_no}</p>
      <div class="lines">${line("played", "You played", m.action, `−${m.error.toFixed(3)}`)}${line("best", "Best", m.best, "")}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn" href="/practice?player_name=${encodeURIComponent(d.player)}">Practise it</a><a class="btn secondary" href="/review?match=${m.match_id}&focus=${m.id}&min_error=all">Open in Review</a></div>
    </div></div>`;
  Board.renderWithLabels($("featured-board"), m, checker ? { arrows, noNumbers: true } : { bottom: m.player, cubeOffered: m.kind === "take", noNumbers: true });
}

function renderChart(d) {
  const el = $("chart");
  const points = d.matches.filter((m) => m.pr !== null).slice(0, 20).reverse();
  if (points.length < 2) return renderFeatured(d);
  $("hero-title").textContent = "Performance rating by match";
  $("hero-hint").textContent = "Lower is better";
  el.className = "chart-wrap";
  if (!points.length) {
    el.innerHTML = `<div class="empty">${icon("pulse")}<p>Your PR per match appears here once a match is analysed.</p></div>`;
    return;
  }
  const width = Math.max(320, el.clientWidth - 40);
  const height = 230;
  const pad = { l: 36, r: 12, t: 14, b: 30 };
  const max = Math.max(10, Math.ceil(Math.max(...points.map((p) => p.pr)) / 5) * 5);
  const x = (i) => pad.l + (points.length === 1 ? (width - pad.l - pad.r) / 2 : (i * (width - pad.l - pad.r)) / (points.length - 1));
  const y = (v) => pad.t + (1 - v / max) * (height - pad.t - pad.b);
  const ticks = [0, max / 2, max];
  let svg = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="PR per match, oldest to newest">`;
  svg += `<g class="grid">${ticks.map((t) => `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${pad.l - 8}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("")}</g>`;
  if (points.length > 1) {
    const line = points.map((p, i) => `${x(i)},${y(p.pr)}`).join(" ");
    svg += `<polygon class="area" points="${x(0)},${y(0)} ${line} ${x(points.length - 1)},${y(0)}"/>`;
    svg += `<polyline class="line" points="${line}"/>`;
    if (d.summary.avg_pr !== null) svg += `<line class="avg" x1="${pad.l}" x2="${width - pad.r}" y1="${y(d.summary.avg_pr)}" y2="${y(d.summary.avg_pr)}"/>`;
  }
  points.forEach((p, i) => {
    const last = i === points.length - 1;
    svg += `<a href="/review?match=${p.id}"><circle class="pt ${last ? "hot" : ""}" cx="${x(i)}" cy="${y(p.pr)}" r="${last ? 6 : 4.5}"><title>${esc(shortDate(p.date))} vs ${esc(p.opponent)}: PR ${p.pr.toFixed(1)}</title></circle></a>`;
    if (last || points.length <= 8) svg += `<text x="${x(i)}" y="${height - 10}" text-anchor="middle">${esc(shortDate(p.date))}</text>`;
  });
  const latest = points[points.length - 1];
  svg += `<text x="${x(points.length - 1)}" y="${y(latest.pr) - 12}" text-anchor="middle" style="fill:var(--text);font-weight:650;font-size:12px">${latest.pr.toFixed(1)}</text>`;
  svg += "</svg>";
  el.innerHTML = svg;
}

function renderPhases(d) {
  const max = Math.max(0.0001, ...d.phases.map((p) => p.error));
  const worst = d.phases.reduce((a, b) => (b.error > a.error ? b : a), d.phases[0]);
  $("phases").innerHTML = d.phases.map((p) => `
    <div class="phase ${p === worst && p.error > 0 ? "" : "light"}">
      <span class="name">${PHASE_NAMES[p.phase]}</span>
      <span class="bar" role="img" aria-label="${p.error.toFixed(3)} equity lost"><span style="width:${(100 * p.error) / max}%"></span></span>
      <span class="val">${p.error > 0 ? `−${p.error.toFixed(2)}` : "0"}</span>
      <span class="meta">${p.decisions ? `${plural(p.errors, "error")} in ${plural(p.decisions, "decision")}` : "No decisions yet"}</span>
    </div>`).join("");
}

function mistakeRow(m) {
  const what = m.kind === "checker" ? diceSvg(m.dice) : icon("cube");
  const played = esc(m.action);
  return `<a class="mistake" href="/review?match=${m.match_id}&focus=${m.id}&min_error=all">
    <div class="thumb">${Board.render(m, { mini: true })}</div>
    <div>
      <div class="what">${what}<span>${m.kind === "checker" ? played : m.kind === "take" ? `${played} (take or pass)` : `${played} (cube)`}</span></div>
      <div class="moves">Best: <span class="best">${esc(m.best)}</span></div>
      <div class="ctx">vs ${esc(m.opponent)} · ${esc(shortDate(m.event_date))} · game ${m.game_no}, move ${m.move_no}</div>
    </div>
    <div style="text-align:right">${severityChip(m.class)}<div class="small muted tabular" style="margin-top:6px">${formatLoss(m.error)}</div></div>
  </a>`;
}

function renderDeck(d) {
  const p = d.practice;
  $("deck").innerHTML = [[p.due, "due now"], [p.missed, "missed last time"], [p.mastered, "solved"]]
    .map(([n, l]) => `<div><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
  const streak = $("streak");
  streak.className = `streak ${p.streak ? "" : "cold"}`;
  streak.innerHTML = `${icon("flame")}${p.streak ? `${plural(p.streak, "day")} in a row` : "No streak yet"}`;
  $("deck-cta").href = `/practice?player_name=${encodeURIComponent(d.player)}`;
}

function renderMistakes(d) {
  const featuredShown = d.matches.filter((m) => m.pr !== null).length < 2;
  const list = featuredShown ? d.mistakes.slice(1) : d.mistakes;
  $("mistakes").innerHTML = list.length
    ? list.map(mistakeRow).join("")
    : `<div class="empty">${icon("check")}<strong>No errors found</strong><p>Nothing above your doubtful threshold in recent matches.</p></div>`;
  $("mistakes-all").href = `/review?player_name=${encodeURIComponent(d.player)}`;
}

function renderRecent(d) {
  $("recent").innerHTML = d.matches.slice(0, 6).map((m) => {
    const result = m.won ? '<span class="result win">Won</span>' : m.lost ? '<span class="result loss">Lost</span>' : "";
    return `<a class="match-row" href="/review?match=${m.id}">
      <div class="me"><div class="name">${esc(d.player)}</div><div class="sub">PR ${m.pr === null ? "–" : m.pr.toFixed(1)} · ${plural(m.errors, "error")}</div></div>
      <div class="score">${m.my_score}–${m.their_score}<small>${result || `${m.match_length}-pt`} · ${esc(shortDate(m.date))}</small></div>
      <div><div class="name">${esc(m.opponent)}</div><div class="sub">PR ${m.their_pr === null ? "–" : m.their_pr.toFixed(1)}</div></div>
    </a>`;
  }).join("");
}

function renderEmpty() {
  $("dash").hidden = true;
  $("cta").hidden = true;
  $("greeting").textContent = "Welcome to VS Gammon";
  $("greeting-sub").textContent = "Turn your own matches into training.";
  const box = $("dash-empty");
  box.hidden = false;
  box.innerHTML = `<section class="panel"><div class="empty" style="padding:72px 24px">${icon("upload")}
    <strong>Import your first match</strong>
    <p>Drop a .mat file on the Matches page, or watch your Downloads folder so new matches are picked up by themselves. Every move is analysed by GNU Backgammon.</p>
    <div style="display:flex;gap:8px;margin-top:6px"><a class="btn" href="/matches">Import a match</a><a class="btn secondary" href="/settings#folders">Watch a folder</a></div></div></section>`;
}

async function load(player) {
  const q = player ? `?player_name=${encodeURIComponent(player)}` : "";
  try {
    data = await api.get(`/api/dashboard${q}`);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  if (!data.player) return renderEmpty();
  $("greeting").textContent = greeting(data.player);
  const last = data.matches[0];
  $("greeting-sub").textContent = last
    ? `${plural(data.summary.matches, "match", "matches")} analysed · last one ${shortDate(last.date)} against ${last.opponent}`
    : "No analysed matches for this player yet";
  const due = data.practice.due;
  $("cta").innerHTML = `${icon("play")}${due ? `Practise ${due} due` : "Practise"}`;
  $("cta").href = `/practice?player_name=${encodeURIComponent(data.player)}`;
  renderStats(data);
  renderChart(data);
  renderPhases(data);
  renderMistakes(data);
  renderDeck(data);
  renderRecent(data);
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const { players } = await api.get("/api/players");
    const { settings } = await api.get("/api/settings");
    const chosen = settings.me || (players[0] && players[0].name) || "";
    $("player").innerHTML = players.map((p) => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join("");
    $("player").value = chosen;
    $("player").hidden = players.length < 2;
    $("player").addEventListener("change", () => load($("player").value));
    load(chosen);
  } catch (err) {
    toast(err.message, true);
  }
  let timer;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(() => data && data.player && renderChart(data), 150);
  });
});

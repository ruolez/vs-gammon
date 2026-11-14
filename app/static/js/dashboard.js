const PHASE_NAMES = { opening: t("Opening"), middle: t("Middle game"), race: t("Race"), bearoff: t("Bear-off"), cube: t("Cube") };
let data = null;

function greeting(name) {
  const h = new Date().getHours();
  const part = h < 5 ? t("Good evening") : h < 12 ? t("Good morning") : h < 18 ? t("Good afternoon") : t("Good evening");
  return `${part}, ${name}`;
}

function trendText(last, avg) {
  if (last === null || avg === null || last === undefined || avg === undefined) return "";
  const diff = last - avg;
  if (Math.abs(diff) < 0.05) return t("level with your average");
  return diff < 0
    ? t('<span class="trend-good">{n} better</span> than your average', { n: Math.abs(diff).toFixed(1) })
    : t('<span class="trend-bad">{n} worse</span> than your average', { n: diff.toFixed(1) });
}

function renderStats(d) {
  const s = d.summary;
  const p = d.practice;
  const accuracy = p.attempts ? Math.round((100 * p.correct) / p.attempts) : null;
  const cells = [
    {
      label: term(t("Last match PR"), t("Performance rating: your average error per decision × 500. Lower is better; world-class play is around 3 to 5.")),
      value: s.last_pr === null ? "–" : s.last_pr.toFixed(1),
      foot: s.matches > 1 ? trendText(s.last_pr, s.avg_pr) : t("Average error × 500. Lower is better"),
    },
    {
      label: t("Errors per match"), value: s.errors_per_match === null ? "–" : `${s.errors_per_match}`,
      foot: s.blunders_per_match === null ? "" : t("{n} of them very bad", { n: s.blunders_per_match }),
    },
    {
      label: t("Due for practice"), value: `${p.due}<small>${t("of {n}", { n: p.positions })}</small>`,
      foot: t("{solved} solved · {missed} missed · all time", { solved: p.mastered, missed: p.missed }),
    },
    {
      label: t("Practice accuracy"), value: accuracy === null ? "–" : `${accuracy}<small>%</small>`,
      foot: p.attempts ? t("{answers}, all time", { answers: plural(p.attempts, "answer") }) : t("Answer a position to start measuring"),
    },
  ];
  $("stats").innerHTML = cells.map((c) => `<div class="stat"><span class="label">${c.label}</span><span class="value">${c.value}</span><span class="foot">${c.foot}</span></div>`).join("");
}

function renderFeatured(d) {
  const m = d.mistakes[0];
  $("hero-title").textContent = t("Your biggest recent mistake");
  $("hero-hint").textContent = t("Your PR trend appears from your second match");
  $("chart").className = "";
  if (!m) {
    $("chart").innerHTML = `<div class="empty">${icon("check")}<strong>${t("No errors to show")}</strong><p>${t("Nothing above your doubtful threshold yet.")}</p></div>`;
    return;
  }
  const checker = m.kind === "checker";
  const played = checker ? m.candidates[m.played_index] : null;
  const best = checker ? m.candidates.reduce((b, c) => (c.equity > b.equity ? c : b), m.candidates[0]) : null;
  const arrows = checker ? [{ kind: m.class || "good", steps: played.steps }, { kind: "good", steps: best.steps }] : null;
  const line = (kind, label, text, cost) => `<div class="answer-line"><span class="line" style="background:${Board.COLORS[kind]}"></span><span class="lbl">${label}</span><span class="mv">${esc(text)}</span><span class="cost">${cost}</span></div>`;
  $("chart").innerHTML = `<div class="featured">
    <div id="featured-board"></div>
    <div>
      <div class="what">${checker ? diceSvg(m.dice) : icon("cube")}<span>${t(checker ? "{name} to play" : m.kind === "take" ? "{name}: take or pass?" : "{name}: double or not?", { name: esc(playerName(m, m.player)) })}</span></div>
      <p class="small muted note-tight">${t("vs {name}", { name: esc(m.opponent) })} · ${esc(shortDate(m.event_date))} · ${t("game {game}, move {move}", { game: m.game_no, move: m.move_no })}</p>
      <div class="lines">${line(m.class || "good", t("You played"), t(m.action), `−${m.error.toFixed(3)}`)}${line("good", t("Best"), t(m.best), "")}</div>
      <div class="row-gap"><a class="btn" href="/practice?player_name=${encodeURIComponent(d.player)}">${t("Practise it")}</a><a class="btn secondary" href="/moves?match=${m.match_id}&focus=${m.id}&min_error=all">${t("Open in Moves")}</a></div>
    </div></div>`;
  Board.renderWithLabels($("featured-board"), m, checker ? { arrows, noNumbers: true } : { bottom: m.player, cubeOffered: m.kind === "take", noNumbers: true });
}

function renderChart(d) {
  const el = $("chart");
  const points = d.matches.filter((m) => m.pr !== null).slice(0, 20).reverse();
  if (points.length < 2) return renderFeatured(d);
  $("hero-title").textContent = t("Performance rating by match");
  $("hero-hint").textContent = t("Lower is better");
  el.className = "chart-wrap";
  if (!points.length) {
    el.innerHTML = `<div class="empty">${icon("pulse")}<p>${t("Your PR per match appears here once a match is analysed.")}</p></div>`;
    return;
  }
  const width = Math.max(320, el.clientWidth - 40);
  const height = 230;
  const pad = { l: 36, r: 12, t: 14, b: 30 };
  const max = Math.max(10, Math.ceil(Math.max(...points.map((p) => p.pr)) / 5) * 5);
  const x = (i) => pad.l + (points.length === 1 ? (width - pad.l - pad.r) / 2 : (i * (width - pad.l - pad.r)) / (points.length - 1));
  const y = (v) => pad.t + (1 - v / max) * (height - pad.t - pad.b);
  const ticks = [0, max / 2, max];
  let svg = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${t("PR per match, oldest to newest")}">`;
  svg += `<g class="grid">${ticks.map((t) => `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${pad.l - 8}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("")}</g>`;
  if (points.length > 1) {
    const line = points.map((p, i) => `${x(i)},${y(p.pr)}`).join(" ");
    svg += `<polygon class="area" points="${x(0)},${y(0)} ${line} ${x(points.length - 1)},${y(0)}"/>`;
    svg += `<polyline class="line" points="${line}"/>`;
    if (d.summary.avg_pr !== null) svg += `<line class="avg" x1="${pad.l}" x2="${width - pad.r}" y1="${y(d.summary.avg_pr)}" y2="${y(d.summary.avg_pr)}"/>`;
  }
  points.forEach((p, i) => {
    const last = i === points.length - 1;
    svg += `<a href="/moves?match=${p.id}&min_error=doubtful"><circle class="pt ${last ? "hot" : ""}" cx="${x(i)}" cy="${y(p.pr)}" r="${last ? 6 : 4.5}"><title>${esc(shortDate(p.date))} ${t("vs {name}", { name: esc(p.opponent) })}: PR ${p.pr.toFixed(1)}</title></circle></a>`;
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
      <span class="bar" role="img" aria-label="${t("{n} equity lost", { n: p.error.toFixed(3) })}"><span style="width:${(100 * p.error) / max}%"></span></span>
      <span class="val">${p.error > 0 ? `−${p.error.toFixed(2)}` : "0"}</span>
      <span class="meta">${p.decisions ? t("{errors} in {decisions}", { errors: plural(p.errors, "error"), decisions: plural(p.decisions, "decision") }) : t("No decisions yet")}</span>
    </div>`).join("");
}

function mistakeRow(m) {
  const what = m.kind === "checker" ? diceSvg(m.dice) : icon("cube");
  const played = esc(t(m.action));
  return `<a class="mistake" href="/moves?match=${m.match_id}&focus=${m.id}&min_error=all">
    <div class="thumb">${Board.render(m, { mini: true })}</div>
    <div>
      <div class="what">${what}<span>${m.kind === "checker" ? played : m.kind === "take" ? t("{action} (take or pass)", { action: played }) : t("{action} (cube)", { action: played })}</span></div>
      <div class="moves">${t("Best")}: <span class="best">${esc(t(m.best))}</span></div>
      <div class="ctx">${t("vs {name}", { name: esc(m.opponent) })} · ${esc(shortDate(m.event_date))} · ${t("game {game}, move {move}", { game: m.game_no, move: m.move_no })}</div>
    </div>
    <div class="loss-cell">${severityChip(m.class)}<div class="small muted tabular">${formatLoss(m.error)}</div></div>
  </a>`;
}

function renderDeck(d) {
  const p = d.practice;
  $("deck").innerHTML = [[p.due, t("due now")], [p.missed, t("missed last time")], [p.mastered, t("solved")]]
    .map(([n, l]) => `<div><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
  const streak = $("streak");
  streak.className = `streak ${p.streak ? "" : "cold"}`;
  streak.innerHTML = `${icon("flame")}${p.streak ? t("{days} in a row", { days: plural(p.streak, "day") }) : t("No streak yet")}`;
  $("deck-cta").href = `/practice?player_name=${encodeURIComponent(d.player)}`;
}

function renderMistakes(d) {
  const featuredShown = d.matches.filter((m) => m.pr !== null).length < 2;
  const list = featuredShown ? d.mistakes.slice(1) : d.mistakes;
  $("mistakes").innerHTML = list.length
    ? list.map(mistakeRow).join("")
    : `<div class="empty">${icon("check")}<strong>${t("No errors found")}</strong><p>${t("Nothing above your doubtful threshold in recent matches.")}</p></div>`;
  $("mistakes-all").href = `/moves?player_name=${encodeURIComponent(d.player)}&min_error=doubtful`;
}

function renderRecent(d) {
  $("recent").innerHTML = d.matches.slice(0, 6).map((m) => {
    const result = m.won ? `<span class="result win">${t("Won")}</span>` : m.lost ? `<span class="result loss">${t("Lost")}</span>` : "";
    return `<a class="match-row" href="/moves?match=${m.id}&min_error=doubtful">
      <div class="me"><div class="name">${esc(d.player)}</div><div class="sub">PR ${m.pr === null ? "–" : m.pr.toFixed(1)} · ${plural(m.errors, "error")}</div></div>
      <div class="score">${m.my_score}–${m.their_score}<small>${result || t("{n}-point", { n: m.match_length })} · ${esc(shortDate(m.date))}</small></div>
      <div><div class="name">${esc(m.opponent)}</div><div class="sub">PR ${m.their_pr === null ? "–" : m.their_pr.toFixed(1)}</div></div>
    </a>`;
  }).join("");
}

async function renderEmpty() {
  $("dash").hidden = true;
  $("cta").hidden = true;
  $("greeting").textContent = t("Welcome to VS Gammon");
  $("greeting-sub").textContent = t("Turn your own matches into training.");
  const box = $("dash-empty");
  box.hidden = false;
  const { docker_data: canBringOver } = await api.get("/api/shell");
  if (canBringOver) {
    box.innerHTML = `<section class="panel"><div class="empty tall">${icon("folder")}
      <strong>${t("Your matches are ready to move")}</strong>
      <p>${t("VS Gammon found your matches and practice history from the Docker version. They are copied here and the originals stay as they are.")}</p>
      <div class="row-gap top"><button class="btn" id="bring-over">${t("Bring them over")}</button><a class="btn secondary" href="/matches">${t("Start fresh")}</a></div></div></section>`;
    $("bring-over").addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      try {
        await api.post("/api/import-docker");
        location.reload();
      } catch (err) {
        ev.target.disabled = false;
        toast(err.message, true);
      }
    });
    return;
  }
  box.innerHTML = `<section class="panel"><div class="empty tall">${icon("upload")}
    <strong>${t("Import your first match")}</strong>
    <p>${t("Drop a .mat file on the Matches page, or watch your Downloads folder so new matches are picked up by themselves. Every move is analysed by GNU Backgammon.")}</p>
    <div class="row-gap top"><a class="btn" href="/matches">${t("Import a match")}</a><a class="btn secondary" href="/settings#folders">${t("Watch a folder")}</a></div></div></section>`;
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
    ? t("{matches} analysed · last one {date} against {name}", { matches: plural(data.summary.matches, "match"), date: shortDate(last.date), name: last.opponent })
    : t("No analysed matches for this player yet");
  const due = data.practice.due;
  $("cta").innerHTML = `${icon("play")}${due ? t("Practise {n} due", { n: due }) : t("Practise")}`;
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
    const names = players.map((p) => p.name);
    const remembered = Prefs.get("dashboard.player", "");
    const chosen = names.includes(remembered) ? remembered : settings.me || names[0] || "";
    $("player").innerHTML = players.map((p) => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join("");
    $("player").value = chosen;
    $("player").hidden = players.length < 2;
    $("player").addEventListener("change", () => {
      Prefs.set("dashboard.player", $("player").value);
      load($("player").value);
    });
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

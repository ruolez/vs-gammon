/* Live stats beside the game on Play online: takes a screenshot of the site about twice a second, the server reads
   the board, follows the moves and has gnubg analyse them; this panel shows the result. */
(function () {
  const panel = $("live");
  const toggle = $("live-toggle");
  const CAPTURE_MS = 600;
  const POLL_MS = 1500;
  const SNAPSHOT_WIDTH = 1600;
  const SEVERITY_ARROW = { very_bad: "very_bad", bad: "bad", doubtful: "doubtful" };
  let view = null;
  let shown = null;
  let pinned = null;
  let editing = false;
  let capturing = false;
  let lastShot = null;
  let matches = null;
  let stopArmed = null;

  /* Messages stay inside the panel: the game's native view covers the middle of the page, toasts and dialogs too. */
  function notice(message, isError = false) {
    const box = $("live-notice");
    if (!box) return;
    box.textContent = message;
    box.className = `live-notice${isError ? " error" : ""}`;
    box.hidden = false;
    clearTimeout(box._timer);
    box._timer = setTimeout(() => (box.hidden = true), isError ? 7000 : 4000);
  }

  toggle.innerHTML = `${icon("pulse")}<span>${t("Live stats")}</span>`;

  function isOpen() {
    return Prefs.get("live-open", false);
  }

  function setOpen(open) {
    Prefs.set("live-open", open);
    panel.hidden = !open;
    toggle.setAttribute("aria-pressed", String(open));
    if (open) refresh();
  }
  toggle.addEventListener("click", () => setOpen(!isOpen()));

  async function refresh() {
    try {
      view = await api.get("/api/live");
    } catch (_) {
      return;
    }
    if (pinned && view.active) {
      try {
        shown = await api.get(`/api/live/move/${pinned.game_no}/${pinned.index}`);
      } catch (_) {
        pinned = null;
      }
    }
    render();
  }

  /* ---------- capture ---------- */

  function bytes(base64) {
    const raw = atob(base64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  async function captureOnce() {
    if (capturing || !Host || !view?.active || document.hidden) return;
    capturing = true;
    try {
      const shot = await Host.call("play", { action: "snapshot", width: SNAPSHOT_WIDTH });
      if (!shot || !shot.image) {
        lastShot = { found: false, why: "no picture" };
        return;
      }
      const response = await fetch("/api/live/frame", { method: "POST", headers: { "Content-Type": "image/png" }, body: bytes(shot.image) });
      if (response.status === 409) {
        view = { active: false };
        render();
        return;
      }
      lastShot = await response.json();
      if (lastShot.version !== view.version) await refresh();
      else renderStatus();
    } catch (_) {
      // a failed capture is retried on the next tick
    } finally {
      capturing = false;
    }
  }
  setInterval(captureOnce, CAPTURE_MS);
  setInterval(() => { if (isOpen() && !capturing && !document.hidden) refresh(); }, POLL_MS);

  /* ---------- setup ---------- */

  function settingsForm(settings, starting) {
    const opponent = settings.opponent;
    return `<form class="live-form" id="live-form">
      <div class="live-field"><span class="live-label">${t("Opponent")}</span>
        <div class="seg" role="group" aria-label="${t("Opponent")}">
          <button type="button" data-opponent="person" aria-pressed="${opponent === "person"}">${t("A person")}</button>
          <button type="button" data-opponent="ai" aria-pressed="${opponent === "ai"}">${t("Galaxy's AI")}</button>
        </div>
      </div>
      <p class="live-note" id="live-fair">${opponent === "person"
        ? t("Against a person the engine's view of a game shows once that game is over. Moves, pips and dice show as you play.")
        : t("Against the AI every move is analysed as it is played.")}</p>
      <div class="live-grid">
        <label class="live-field"><span class="live-label">${t("Match length")}</span>
          <input type="number" name="match_length" min="0" max="63" value="${settings.match_length}"><span class="live-hint">${t("0 for a money game")}</span></label>
        <span></span>
        <label class="live-field"><span class="live-label">${t("You (bottom)")}</span><input type="text" name="player1" maxlength="40" value="${esc(settings.player1)}"></label>
        <label class="live-field"><span class="live-label">${t("Opponent (top)")}</span><input type="text" name="player2" maxlength="40" value="${esc(settings.player2)}"></label>
        <label class="live-field"><span class="live-label">${t("Your score")}</span><input type="number" name="score1" min="0" max="63" value="${settings.score[0]}"></label>
        <label class="live-field"><span class="live-label">${t("Their score")}</span><input type="number" name="score2" min="0" max="63" value="${settings.score[1]}"></label>
      </div>
      <div class="live-actions">
        ${starting ? "" : `<button type="button" class="btn ghost" data-act="cancel-edit">${t("Cancel")}</button>`}
        <button type="submit" class="btn">${starting ? t("Start reading the board") : t("Save")}</button>
      </div>
    </form>`;
  }

  function formValues(form) {
    const data = new FormData(form);
    const opponent = form.querySelector('[data-opponent][aria-pressed="true"]').dataset.opponent;
    return {
      opponent,
      match_length: Number(data.get("match_length")) || 0,
      player1: data.get("player1"),
      player2: data.get("player2"),
      score: [Number(data.get("score1")) || 0, Number(data.get("score2")) || 0],
    };
  }

  async function replayOptions() {
    if (!matches) {
      try {
        matches = (await api.get("/api/matches")).matches.filter((m) => m.status === "done");
      } catch (_) {
        matches = [];
      }
    }
    const select = $("live-replay");
    if (!select) return;
    select.innerHTML = matches.length
      ? matches.map((m) => `<option value="${m.id}">${esc(m.player1)} – ${esc(m.player2)} · ${t("{n}-point match", { n: m.match_length })}</option>`).join("")
      : `<option value="">${t("No analysed matches yet")}</option>`;
    $("live-replay-go").disabled = !matches.length;
  }

  function renderSetup() {
    const defaults = { opponent: "person", match_length: 7, player1: t("You"), player2: t("Opponent"), score: [0, 0] };
    panel.innerHTML = `
      <header class="live-head"><h2>${t("Live stats")}</h2>
        <button type="button" class="btn ghost sm icon-only" data-act="close" title="${t("Close")}" aria-label="${t("Close")}">${icon("x")}</button></header>
      <div class="live-notice" id="live-notice" role="status" hidden></div>
      <div class="live-scroll">
        <p class="live-intro">${t("Reads the board from the game on the left, follows every move and analyses it with GNU Backgammon.")}</p>
        ${Host ? settingsForm(defaults, true) : `<p class="live-note">${t("Live stats read the game from the screen, so they need the VS Gammon app.")}</p>`}
        ${Host ? `<section class="live-section">
          <h3>${t("Try it on a stored match")}</h3>
          <p class="live-note">${t("Plays one of your analysed matches on a board like Galaxy's, and the sidebar follows it.")}</p>
          <div class="live-row"><select id="live-replay" aria-label="${t("Match")}"></select>
          <button type="button" class="btn secondary" id="live-replay-go" data-act="replay">${t("Replay")}</button></div>
        </section>` : ""}
      </div>`;
    if (Host) replayOptions();
  }

  /* ---------- the running match ---------- */

  function statusText() {
    const reading = lastShot || view.reading;
    if (!reading || reading.at === null) return { cls: "wait", text: t("Waiting for the first screenshot") };
    if (reading.why === "no picture") return { cls: "off", text: t("The game isn't showing") };
    if (!reading.found) return { cls: "off", text: t("No board in view") };
    if (!view.position.frame) return { cls: "wait", text: t("Board found. Waiting for a new game to start") };
    return { cls: "on", text: t("Following the game") };
  }

  function renderStatus() {
    const box = $("live-status");
    if (!box || !view?.active) return;
    const status = statusText();
    const engine = view.engine.error ? t("Engine error") : view.engine.busy ? t("Analysing…") : "";
    box.innerHTML = `<i class="dot ${status.cls}"></i><span>${status.text}</span>${engine ? `<span class="live-engine">${engine}</span>` : ""}`;
  }

  function moveNumberLabel(m) {
    return `${t("Game {n}", { n: m.game_no })}, ${t("move {n}", { n: Math.floor(m.index / 2) + 1 })}`;
  }

  function arrowsFor(entry) {
    const d = entry.decision;
    const arrows = [];
    if (entry.engine && d.candidates) {
      const best = d.candidates.reduce((b, c, i) => (c.equity > d.candidates[b].equity ? i : b), 0);
      const cls = errorClass(d.error, view.thresholds);
      if (best !== d.played_index) arrows.push({ steps: d.candidates[best].steps, kind: "best" });
      arrows.push({ steps: d.played_steps, kind: SEVERITY_ARROW[cls] || "good" });
    } else if (d.played_steps && d.played_steps.length) {
      arrows.push({ steps: d.played_steps, kind: "played" });
    }
    return arrows;
  }

  function boardSection(entry) {
    if (!entry) return `<div class="live-empty">${t("The board shows here once the first move is played.")}</div>`;
    const d = entry.decision;
    const name = d.player === 1 ? view.settings.player1 : view.settings.player2;
    const dice = d.dice ? `${Math.max(...d.dice)}${Math.min(...d.dice)}` : "";
    const move = entry.engine ? d.action : d.played_steps && d.played_steps.length ? d.played_steps.map(([a, b]) => `${a}/${b}`).join(" ") : t("no move");
    let verdict = "";
    if (entry.engine) {
      const cls = errorClass(d.error, view.thresholds);
      verdict = `<div class="live-verdict">${severityChip(cls)}<span class="num">${formatLoss(d.error)}</span>
        ${cls ? `<span class="live-best">${t("Best")}: <strong>${esc(d.best)}</strong></span>` : ""}</div>`;
      const rows = [...d.candidates].map((c, i) => ({ ...c, i })).sort((a, b) => b.equity - a.equity).slice(0, 4);
      const top = rows[0].equity;
      verdict += `<ol class="live-cands">${rows.map((c) => `<li class="${c.i === d.played_index ? "played" : ""}">
        <span>${esc(c.move)}</span><span class="num">${c.equity === top ? formatEquity(c.equity) : formatLoss(top - c.equity)}</span></li>`).join("")}</ol>`;
    }
    return `<div class="live-board" id="live-board"></div>
      <div class="live-move"><span class="swatch p${d.player}"></span><strong>${esc(name)}</strong><span class="num">${dice}</span><span>${esc(move)}</span>
        ${pinned ? `<button type="button" class="btn ghost sm" data-act="follow">${t("Back to the latest")}</button>` : ""}</div>
      ${verdict}`;
  }

  function chancesSection() {
    const current = view.games.length;
    const points = view.graph.filter((p) => p.game_no === current);
    if (view.held) return "";
    if (!points.length) return "";
    const last = points[points.length - 1];
    const W = 300;
    const H = 84;
    const x = (i) => (points.length === 1 ? W / 2 : 6 + (i * (W - 12)) / (points.length - 1));
    const y = (v) => 6 + (1 - v) * (H - 12);
    const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.win).toFixed(1)}`).join(" ");
    const pct = (v) => `${Math.round(v * 100)}%`;
    return `<section class="live-section">
      <h3>${t("Winning chances")} · ${esc(view.settings.player1)}</h3>
      <div class="live-chances"><span class="big num">${pct(last.win)}</span>
        <span class="muted small">${t("gammon {g} · lose gammon {l}", { g: pct(last.gammon), l: pct(last.lose_gammon) })}</span></div>
      <div class="live-graph" id="live-graph">
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${t("Winning chances after each move of this game")}">
          <line x1="0" x2="${W}" y1="${y(0.5)}" y2="${y(0.5)}" class="mid"/>
          <polyline points="${line}" class="series"/>
          <line class="cross" x1="0" x2="0" y1="0" y2="${H}" hidden/>
        </svg>
        <div class="live-tip" hidden></div>
      </div>
    </section>`;
  }

  function statsSection() {
    const s = view.stats;
    const name = (p) => esc(p === 1 ? view.settings.player1 : view.settings.player2);
    const num = (v, digits = 1) => (v === null || v === undefined ? "–" : Number(v).toFixed(digits));
    const errors = (p) => {
      const c = s[p].checker;
      const q = s[p].cube;
      if (!c) return "–";
      return `${c.very_bad + (q ? q.very_bad : 0)} / ${c.bad + (q ? q.bad : 0)} / ${c.doubtful + (q ? q.doubtful : 0)}`;
    };
    const luck = (v) => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}`);
    const rows = [
      [t("PR (lower is better)"), num(s[1].pr), num(s[2].pr)],
      [t("Very bad / bad / doubtful"), errors(1), errors(2)],
      [t("Equity lost"), s[1].checker ? formatLoss(s[1].checker.error + s[1].cube.error) : "–", s[2].checker ? formatLoss(s[2].checker.error + s[2].cube.error) : "–"],
      [t("Luck"), luck(s[1].luck), luck(s[2].luck)],
      [t("Lucky / unlucky rolls"), s[1].rolls ? `${s[1].lucky} / ${s[1].unlucky}` : "–", s[2].rolls ? `${s[2].lucky} / ${s[2].unlucky}` : "–"],
      [t("Pips"), s[1].pips ?? "–", s[2].pips ?? "–"],
    ];
    return `<section class="live-section">
      <h3>${t("Match so far")}</h3>
      <table class="live-stats"><thead><tr><th></th><th><span class="swatch p1"></span>${name(1)}</th><th><span class="swatch p2"></span>${name(2)}</th></tr></thead>
      <tbody>${rows.map((r) => `<tr><th scope="row">${r[0]}</th><td class="num">${r[1]}</td><td class="num">${r[2]}</td></tr>`).join("")}</tbody></table>
    </section>`;
  }

  function movesSection() {
    if (!view.moves.length) return "";
    const rows = view.moves.slice().reverse().slice(0, 120).map((m) => {
      const dice = `${Math.max(...m.dice)}${Math.min(...m.dice)}`;
      const mark = m.class ? `<span class="sevtxt ${m.class}">${formatLoss(m.error)}</span>`
        : m.pending ? `<span class="muted small">…</span>` : "";
      const luck = m.luck_level ? `<span class="live-luck ${m.luck_level}" title="${t("Luck")}: ${m.luck >= 0 ? "+" : "−"}${Math.abs(m.luck).toFixed(2)}">${m.luck > 0 ? "★" : "▾"}</span>` : "";
      const active = pinned && pinned.game_no === m.game_no && pinned.index === m.index;
      return `<li><button type="button" data-move="${m.game_no}:${m.index}" class="${active ? "active" : ""}" title="${moveNumberLabel(m)}">
        <span class="swatch p${m.player}"></span><span class="num">${dice}</span><span class="mv">${esc(m.move || t("no move"))}</span>${luck}${mark}</button></li>`;
    }).join("");
    return `<section class="live-section"><h3>${t("Moves")}</h3><ol class="live-moves">${rows}</ol></section>`;
  }

  function renderActive() {
    const st = view.settings;
    const length = st.match_length ? t("{n}-point match", { n: st.match_length }) : t("Money game");
    const game = view.games.length ? ` · ${t("Game {n}", { n: view.games.length })}` : "";
    const entry = pinned && shown ? shown : view.last;
    panel.innerHTML = `
      <header class="live-head"><h2>${t("Live stats")}</h2>
        <button type="button" class="btn ghost sm" data-act="edit">${t("Edit")}</button>
        <button type="button" class="btn ghost sm${stopArmed ? " danger" : ""}" data-act="stop">${stopArmed ? t("Stop and drop the moves?") : t("Stop")}</button>
        <button type="button" class="btn ghost sm icon-only" data-act="close" title="${t("Close")}" aria-label="${t("Close")}">${icon("x")}</button></header>
      <div class="live-status" id="live-status"></div>
      <div class="live-notice" id="live-notice" role="status" hidden></div>
      <div class="live-scroll">
        ${editing ? settingsForm(st, false) : `<div class="live-score"><span class="swatch p1"></span><strong>${esc(st.player1)}</strong>
          <span class="num">${st.score[0]} – ${st.score[1]}</span><strong>${esc(st.player2)}</strong><span class="swatch p2"></span>
          <span class="muted small">${length}${game}</span></div>`}
        ${view.held ? `<p class="live-held">${icon("eye")}<span>${t("Playing a person: the engine's view of this game shows when it ends.")}</span></p>` : ""}
        ${boardSection(entry)}
        ${chancesSection()}
        ${statsSection()}
        ${movesSection()}
        <div class="live-actions"><button type="button" class="btn secondary" data-act="save" ${view.games.length ? "" : "disabled"}>${t("Save to library")}</button></div>
      </div>`;
    renderStatus();
    if (entry) {
      const d = entry.decision;
      Board.renderWithLabels($("live-board"), d, { bottom: d.on_roll, arrows: arrowsFor(entry).filter((a) => a.steps && a.steps.length) });
    }
    wireGraph();
  }

  function wireGraph() {
    const box = $("live-graph");
    if (!box) return;
    const points = view.graph.filter((p) => p.game_no === view.games.length);
    const svg = box.querySelector("svg");
    const cross = svg.querySelector(".cross");
    const tip = box.querySelector(".live-tip");
    svg.addEventListener("pointermove", (ev) => {
      const rect = svg.getBoundingClientRect();
      const i = Math.max(0, Math.min(points.length - 1, Math.round(((ev.clientX - rect.left) / rect.width) * (points.length - 1))));
      const p = points[i];
      const xv = points.length === 1 ? 150 : 6 + (i * 288) / (points.length - 1);
      cross.setAttribute("x1", xv);
      cross.setAttribute("x2", xv);
      cross.hidden = false;
      const who = p.player === 1 ? view.settings.player1 : view.settings.player2;
      tip.textContent = `${t("After {name}'s move", { name: who })}: ${Math.round(p.win * 100)}%`;
      tip.hidden = false;
      tip.style.left = `${(xv / 300) * 100}%`;
    });
    svg.addEventListener("pointerleave", () => {
      cross.hidden = true;
      tip.hidden = true;
    });
  }

  function render() {
    if (!isOpen()) return;
    if (view?.active && editing && panel.querySelector("#live-form")) return renderStatus();
    const scroll = panel.querySelector(".live-scroll");
    const top = scroll ? scroll.scrollTop : 0;
    if (view?.active) renderActive();
    else if (!panel.querySelector("#live-form") || panel.dataset.mode !== "setup") renderSetup();
    panel.dataset.mode = view?.active ? "active" : "setup";
    const again = panel.querySelector(".live-scroll");
    if (again) again.scrollTop = top;
  }

  /* ---------- events ---------- */

  panel.addEventListener("click", async (ev) => {
    const opponent = ev.target.closest("[data-opponent]");
    if (opponent) {
      opponent.parentElement.querySelectorAll("[data-opponent]").forEach((b) => b.setAttribute("aria-pressed", String(b === opponent)));
      $("live-fair").textContent = opponent.dataset.opponent === "person"
        ? t("Against a person the engine's view of a game shows once that game is over. Moves, pips and dice show as you play.")
        : t("Against the AI every move is analysed as it is played.");
      return;
    }
    const move = ev.target.closest("[data-move]");
    if (move) {
      const [game_no, index] = move.dataset.move.split(":").map(Number);
      pinned = { game_no, index };
      await refresh();
      return;
    }
    const act = ev.target.closest("[data-act]")?.dataset.act;
    try {
      if (act === "close") setOpen(false);
      else if (act === "follow") { pinned = null; shown = null; render(); }
      else if (act === "edit") { editing = true; render(); }
      else if (act === "cancel-edit") { editing = false; render(); }
      else if (act === "stop") {
        if (!stopArmed) {
          stopArmed = setTimeout(() => { stopArmed = null; render(); }, 4000);
          render();
          return;
        }
        clearTimeout(stopArmed);
        stopArmed = null;
        view = await api.del("/api/live");
        pinned = null;
        render();
      } else if (act === "save") {
        const result = await api.post("/api/live/save");
        notice(result.duplicate ? t("This match is already in your library") : t("Saved to your library. It is analysed in full now."));
      } else if (act === "replay") {
        const match = matches.find((m) => String(m.id) === $("live-replay").value);
        if (!match) return;
        view = await api.post("/api/live", { opponent: "ai", match_length: match.match_length, player1: match.player1, player2: match.player2, score: [0, 0] });
        pinned = null;
        render();
        document.dispatchEvent(new CustomEvent("playopen", { detail: `${location.origin}/replay?match=${match.id}` }));
      }
    } catch (err) {
      notice(err.message, true);
    }
  });

  panel.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const values = formValues(ev.target);
    try {
      view = editing ? await api.patch("/api/live", values) : await api.post("/api/live", values);
      editing = false;
      pinned = null;
      render();
    } catch (err) {
      notice(err.message, true);
    }
  });

  setOpen(isOpen());
})();

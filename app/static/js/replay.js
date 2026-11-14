/* Plays a stored match on a board drawn like BackgammonGalaxy's, one screen at a time, so the Play online reader
   can be tested on it: the page only shows pixels, the reader has to work the moves out. */
(function () {
  const PALETTE = { page: "#030712", frame: "#423122", felt: "#4a6439", tray: "#38291d", red: "#ff4422", beige: "#c9b797",
    dark: "#0d0d14", darkEdge: "#000000", light: "#ffffff", lightEdge: "#e6e6e6", label: "#c9b797" };
  const PW = 32;
  const FIELD = 6 * PW;
  const BAR = Math.round(PW * 1.3);
  const MARGIN = PW * 2;
  const TRAY = Math.round(PW * 1.1);
  const HEIGHT = 11 * PW;
  const LEFT = MARGIN;
  const RIGHT = LEFT + FIELD + BAR;
  const TOP = Math.round(PW * 0.9);
  const BOTTOM = TOP + HEIGHT;
  const WIDTH = RIGHT + FIELD + TRAY + MARGIN / 2;
  const TOTAL_H = BOTTOM + Math.round(PW * 0.9);
  const PIPS = { 1: [[0.5, 0.5]], 2: [[0.27, 0.27], [0.73, 0.73]], 3: [[0.25, 0.25], [0.5, 0.5], [0.75, 0.75]],
    4: [[0.27, 0.27], [0.73, 0.27], [0.27, 0.73], [0.73, 0.73]], 5: [[0.25, 0.25], [0.75, 0.25], [0.5, 0.5], [0.25, 0.75], [0.75, 0.75]],
    6: [[0.27, 0.22], [0.73, 0.22], [0.27, 0.5], [0.73, 0.5], [0.27, 0.78], [0.73, 0.78]] };

  const stage = document.getElementById("stage");

  function column(point) {
    if (point <= 6) return RIGHT + (6 - point) * PW;
    if (point <= 12) return LEFT + (12 - point) * PW;
    if (point <= 18) return LEFT + (point - 13) * PW;
    return RIGHT + (point - 19) * PW;
  }

  function checker(cx, cy, dark) {
    const r = PW / 2 - 0.5;
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${dark ? PALETTE.dark : PALETTE.light}" stroke="${dark ? PALETTE.darkEdge : PALETTE.lightEdge}" stroke-width="1"/>`;
  }

  function draw(screen) {
    const frame = screen.frame;
    const pointH = HEIGHT * 0.37;
    let svg = `<svg viewBox="0 0 ${WIDTH} ${TOTAL_H}" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%">`;
    svg += `<rect width="${WIDTH}" height="${TOTAL_H}" rx="20" fill="${PALETTE.frame}"/>`;
    [LEFT, RIGHT].forEach((x) => (svg += `<rect x="${x}" y="${TOP}" width="${FIELD}" height="${HEIGHT}" fill="${PALETTE.felt}"/>`));
    const trayX = RIGHT + FIELD + PW / 4;
    svg += `<rect x="${trayX}" y="${TOP + PW}" width="${TRAY - PW / 4}" height="${HEIGHT / 2 - PW * 1.5}" fill="${PALETTE.tray}"/>`;
    svg += `<rect x="${trayX}" y="${TOP + HEIGHT / 2 + PW / 2}" width="${TRAY - PW / 4}" height="${HEIGHT / 2 - PW * 1.5}" fill="${PALETTE.tray}"/>`;
    for (let point = 1; point <= 24; point++) {
      const x = column(point);
      const fill = point % 2 ? PALETTE.beige : PALETTE.red;
      svg += point > 12
        ? `<polygon shape-rendering="geometricPrecision" points="${x},${TOP} ${x + PW},${TOP} ${x + PW / 2},${TOP + pointH}" fill="${fill}"/>`
        : `<polygon shape-rendering="geometricPrecision" points="${x},${BOTTOM} ${x + PW},${BOTTOM} ${x + PW / 2},${BOTTOM - pointH}" fill="${fill}"/>`;
      const count = frame[point];
      for (let slot = 0; slot < Math.min(Math.abs(count), 5); slot++) {
        const cy = point > 12 ? TOP + (slot + 0.5) * PW : BOTTOM - (slot + 0.5) * PW;
        svg += checker(x + PW / 2, cy, count > 0);
      }
    }
    const barX = LEFT + FIELD + BAR / 2;
    const middle = TOP + HEIGHT / 2;
    for (let i = 0; i < frame[25]; i++) svg += checker(barX, middle + PW * 1.2 + i * PW, true);
    for (let i = 0; i < -frame[0]; i++) svg += checker(barX, middle - PW * 1.2 - i * PW, false);
    const offBottom = 15 - frame.reduce((s, c) => s + (c > 0 ? c : 0), 0);
    const offTop = 15 + frame.reduce((s, c) => s + (c < 0 ? c : 0), 0);
    const pitch = PW * 0.25;
    for (let i = 0; i < offBottom; i++) svg += `<rect x="${trayX + 2}" y="${BOTTOM - PW - 2 - (i + 1) * pitch + 1}" width="${TRAY - PW / 4 - 4}" height="${pitch - 2}" fill="${PALETTE.dark}"/>`;
    for (let i = 0; i < offTop; i++) svg += `<rect x="${trayX + 2}" y="${TOP + PW + 2 + i * pitch + 1}" width="${TRAY - PW / 4 - 4}" height="${pitch - 2}" fill="${PALETTE.light}"/>`;
    if (screen.dice) {
      const bottomRolls = screen.dice.side === "bottom";
      const body = bottomRolls ? PALETTE.dark : PALETTE.light;
      const pip = bottomRolls ? PALETTE.light : PALETTE.dark;
      const field = bottomRolls ? RIGHT : LEFT;
      const size = PW * 0.85;
      screen.dice.values.forEach((value, i) => {
        const x = field + FIELD / 2 - size * 1.15 + i * size * 1.3;
        const y = middle - size / 2;
        svg += `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="${size * 0.15}" fill="${body}"/>`;
        PIPS[value].forEach(([px, py]) => (svg += `<circle shape-rendering="geometricPrecision" cx="${x + px * size}" cy="${y + py * size}" r="${size * 0.09}" fill="${pip}"/>`));
      });
    }
    return svg + "</svg>";
  }

  async function pickMatch() {
    const { matches } = await (await fetch("/api/matches")).json();
    const done = matches.filter((m) => m.status === "done");
    stage.innerHTML = `<div class="picker"><p>${t("Choose a match to replay. The Play online reader follows it like a live game.")}</p>${done
      .map((m) => `<a href="?match=${m.id}">${m.player1} – ${m.player2} <span>· ${t("{n}-point match", { n: m.match_length })}</span></a>`).join("")}</div>`;
    document.querySelector("header .spacer").nextElementSibling.parentElement.querySelectorAll("button, select, label").forEach((el) => (el.hidden = true));
  }

  async function play(matchId) {
    const response = await fetch(`/api/live/replay/${matchId}`);
    if (!response.ok) return pickMatch();
    const { match, screens } = await response.json();
    let index = 0;
    let timer = null;
    const speed = document.getElementById("speed");
    const ms = Number(new URLSearchParams(location.search).get("ms"));
    if (ms > 0) {
      speed.insertAdjacentHTML("beforeend", `<option value="${ms}">${ms} ms</option>`);
      speed.value = String(ms);
    }
    const toggle = document.getElementById("toggle");
    const info = document.getElementById("info");
    const show = () => {
      const screen = screens[index];
      stage.innerHTML = `<div id="board">${draw(screen)}</div>`;
      info.textContent = `${match.player1} – ${match.player2} · ${t("Game {n}", { n: screen.game_no })} · ${screen.score[0]}–${screen.score[1]}`;
    };
    const tick = () => {
      if (index < screens.length - 1) {
        index += 1;
        show();
        timer = setTimeout(tick, Number(speed.value));
      } else {
        timer = null;
        toggle.textContent = t("Play");
      }
    };
    toggle.addEventListener("click", () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
        toggle.textContent = t("Play");
      } else {
        toggle.textContent = t("Pause");
        timer = setTimeout(tick, Number(speed.value));
      }
    });
    document.getElementById("restart").addEventListener("click", () => {
      index = 0;
      show();
    });
    show();
    timer = setTimeout(tick, 2500);
  }

  const id = new URLSearchParams(location.search).get("match");
  if (id) play(id);
  else pickMatch();
})();

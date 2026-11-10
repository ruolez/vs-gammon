const Board = (() => {
  const W = 560;
  const H = 440;
  const FRAME = 12;
  const LABEL = 20;
  const BAR = 40;
  const TRAY = 48;
  const POINT_W = (W - 2 * FRAME - BAR - TRAY - 8) / 12;
  const R = POINT_W / 2 - 1.5;
  const TOP = FRAME + LABEL;
  const BOTTOM = H - FRAME - LABEL;
  const POINT_H = (BOTTOM - TOP) * 0.41;
  const MAX_STACK = 5;
  const BAR_X = FRAME + 6 * POINT_W;
  const TRAY_X = W - FRAME - TRAY;
  const COLORS = {
    played: "var(--arrow-game)", best: "var(--arrow-best)", yours: "var(--arrow-yours)", candidate: "var(--arrow-candidate)",
  };

  function flip(frame) {
    return frame.map((_, i) => -frame[25 - i]);
  }

  function onrollFrame(d) {
    return d.on_roll === 1 ? d.board : flip(d.board);
  }

  function pips(frame) {
    let bottom = 0;
    let top = 0;
    frame.forEach((count, i) => {
      if (count > 0) bottom += i * count;
      if (count < 0) top += (i === 0 ? 25 : 25 - i) * -count;
    });
    return { bottom, top };
  }

  function pointX(point) {
    const index = (point - 1) % 12;
    const column = point <= 12 ? 11 - index : index;
    return FRAME + column * POINT_W + (column >= 6 ? BAR : 0);
  }

  function slot(point, level) {
    const shown = Math.min(level, MAX_STACK - 1);
    if (point === 25) return { x: BAR_X + BAR / 2, y: H / 2 - 30 - R - shown * 2 * R };
    if (point === 0) return { x: TRAY_X + TRAY / 2, y: BOTTOM - 34 };
    const x = pointX(point) + POINT_W / 2;
    return point <= 12 ? { x, y: BOTTOM - R - 1 - shown * 2 * R } : { x, y: TOP + R + 1 + shown * 2 * R };
  }

  function checker(cx, cy, owner, label, ring) {
    const n = owner === 1 ? 1 : 2;
    let svg = `<circle cx="${cx}" cy="${cy}" r="${R}" style="fill:var(--checker-${n});stroke:var(--checker-${n}-edge)" stroke-width="1.3"/>`;
    svg += `<circle cx="${cx}" cy="${cy}" r="${R * 0.62}" fill="none" style="stroke:var(--checker-${n}-edge)" stroke-width="1" opacity="0.55"/>`;
    if (ring) svg += `<circle cx="${cx}" cy="${cy}" r="${R + 3}" fill="none" stroke="${ring}" stroke-width="3"/>`;
    if (label) svg += `<text x="${cx}" y="${cy + 4.5}" text-anchor="middle" font-size="13" font-weight="700" style="fill:var(--checker-${n}-text)" font-family="Inter, sans-serif">${label}</text>`;
    return svg;
  }

  function stack(point, count, owner, ring) {
    let svg = "";
    const shown = Math.min(count, MAX_STACK);
    for (let i = 0; i < shown; i++) {
      const { x, y } = slot(point, i);
      const last = i === shown - 1;
      svg += checker(x, y, owner, last && count > MAX_STACK ? count : "", last ? ring : null);
    }
    return svg;
  }

  function opponentBar(count, owner) {
    let svg = "";
    const shown = Math.min(count, MAX_STACK);
    for (let i = 0; i < shown; i++) {
      svg += checker(BAR_X + BAR / 2, H / 2 + 30 + R + i * 2 * R, owner, i === shown - 1 && count > MAX_STACK ? count : "");
    }
    return svg;
  }

  function die(x, y, value, size, used) {
    const pip = size / 10.5;
    const spots = {
      1: [[0.5, 0.5]], 2: [[0.27, 0.27], [0.73, 0.73]], 3: [[0.26, 0.26], [0.5, 0.5], [0.74, 0.74]],
      4: [[0.28, 0.28], [0.72, 0.28], [0.28, 0.72], [0.72, 0.72]],
      5: [[0.26, 0.26], [0.74, 0.26], [0.5, 0.5], [0.26, 0.74], [0.74, 0.74]],
      6: [[0.28, 0.24], [0.72, 0.24], [0.28, 0.5], [0.72, 0.5], [0.28, 0.76], [0.72, 0.76]],
    }[value] || [];
    let svg = `<g opacity="${used ? 0.28 : 1}"><rect x="${x}" y="${y}" width="${size}" height="${size}" rx="${size * 0.18}" fill="#f8fafc" stroke="rgba(15,23,42,.35)"/>`;
    spots.forEach(([sx, sy]) => (svg += `<circle cx="${x + sx * size}" cy="${y + sy * size}" r="${pip}" fill="#1e2a46"/>`));
    return svg + "</g>";
  }

  function diceOnBoard(dice) {
    const size = dice.length > 2 ? 30 : 38;
    const gap = 8;
    const total = dice.length * size + (dice.length - 1) * gap;
    let x = BAR_X + BAR + 3 * POINT_W - total / 2;
    return dice.map((d) => {
      const s = die(x, H / 2 - size / 2, d.value, size, d.used);
      x += size + gap;
      return s;
    }).join("");
  }

  function cubeSvg(cube, bottomPlayer) {
    const size = 34;
    const x = BAR_X + BAR / 2 - size / 2;
    let y = H / 2 - size / 2;
    let value = cube.owner === 0 && cube.value === 1 ? 64 : cube.value;
    let stroke = "rgba(15,23,42,.35)";
    if (cube.offered) {
      value = cube.value * 2;
      stroke = "var(--arrow-game)";
    } else if (cube.owner !== 0) {
      y = cube.owner === bottomPlayer ? BOTTOM - size - 4 : TOP + 4;
    }
    return `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="7" fill="#f8fafc" style="stroke:${stroke}" stroke-width="${cube.offered ? 3 : 1}"/>` +
      `<text x="${x + size / 2}" y="${y + size / 2 + 5.5}" text-anchor="middle" font-size="15" font-weight="800" fill="#1e2a46" font-family="Inter, sans-serif">${value}</text>`;
  }

  function borneOff(count, atBottom, owner) {
    let svg = "";
    const x = TRAY_X + 9;
    const width = TRAY - 18;
    const h = 7;
    const n = owner === 1 ? 1 : 2;
    for (let i = 0; i < count; i++) {
      const y = atBottom ? BOTTOM - 6 - (i + 1) * (h + 1.5) : TOP + 6 + i * (h + 1.5);
      svg += `<rect x="${x}" y="${y}" width="${width}" height="${h}" rx="2.5" style="fill:var(--checker-${n});stroke:var(--checker-${n}-edge)" stroke-width="0.8"/>`;
    }
    return svg;
  }

  function arrowSvg(start, steps, kind) {
    let frame = start.slice();
    const paths = [];
    steps.forEach(([from, to]) => {
      const fromLevel = Math.max(0, frame[from] - 1);
      const next = Moves.applyStep(frame, [from, to]);
      const end = slot(to, to === 0 ? 0 : Math.max(0, next[to] - 1));
      const open = paths.filter((p) => p.point === from && !p.used);
      const path = open[open.length - 1];
      if (path && from !== 25) {
        path.point = to;
        path.end = end;
        path.used = to === 0;
      } else {
        paths.forEach((p) => { if (p.point === from) p.used = true; });
        paths.push({ start: slot(from, fromLevel), end, point: to, used: to === 0 });
      }
      frame = next;
    });
    return paths.map(({ start: a, end: b }) =>
      `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" style="stroke:${COLORS[kind]}" stroke-width="4" stroke-linecap="round" marker-end="url(#arrow-${kind})" opacity="0.95"/>`).join("");
  }

  function targetSvg(point) {
    if (point === 0) {
      return `<rect x="${TRAY_X + 3}" y="${H / 2 + 8}" width="${TRAY - 6}" height="${BOTTOM - H / 2 - 8}" rx="6" fill="rgba(34,197,94,0.32)" stroke="#22c55e" stroke-width="2"/>`;
    }
    const x = pointX(point);
    const bottomRow = point <= 12;
    const baseY = bottomRow ? BOTTOM : TOP;
    const tipY = bottomRow ? BOTTOM - POINT_H : TOP + POINT_H;
    return `<polygon points="${x + 1},${baseY} ${x + POINT_W - 1},${baseY} ${x + POINT_W / 2},${tipY}" fill="rgba(34,197,94,0.5)" stroke="#22c55e" stroke-width="2" stroke-linejoin="round"/>`;
  }

  function hitAreas() {
    let svg = "";
    for (let point = 1; point <= 24; point++) {
      const y = point <= 12 ? H / 2 : TOP;
      svg += `<rect class="hit" data-point="${point}" x="${pointX(point)}" y="${y}" width="${POINT_W}" height="${(BOTTOM - TOP) / 2}" fill="transparent"/>`;
    }
    svg += `<rect class="hit" data-point="25" x="${BAR_X}" y="${TOP}" width="${BAR}" height="${BOTTOM - TOP}" fill="transparent"/>`;
    svg += `<rect class="hit" data-point="0" x="${TRAY_X}" y="${TOP}" width="${TRAY}" height="${BOTTOM - TOP}" fill="transparent"/>`;
    return svg;
  }

  function render(d, opts = {}) {
    const bottomPlayer = opts.bottom || d.on_roll;
    const topPlayer = bottomPlayer === 1 ? 2 : 1;
    let frame = opts.frame || onrollFrame(d);
    const flipped = bottomPlayer !== d.on_roll;
    if (flipped) frame = flip(frame);
    const interactive = opts.interactive || null;
    const mini = !!opts.mini;
    const half = 6 * POINT_W;

    let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Backgammon position" class="board-svg${interactive ? " interactive" : ""}">`;
    if (opts.arrows) {
      svg += `<defs>${Object.keys(COLORS).map((k) => `<marker id="arrow-${k}" markerUnits="userSpaceOnUse" markerWidth="16" markerHeight="16" refX="12" refY="8" orient="auto"><path d="M1,1.5 L15,8 L1,14.5 z" style="fill:${COLORS[k]}"/></marker>`).join("")}</defs>`;
    }
    svg += `<rect width="${W}" height="${H}" rx="14" style="fill:var(--board-frame)"/>`;
    svg += `<rect x="${FRAME}" y="${TOP}" width="${half}" height="${BOTTOM - TOP}" rx="3" style="fill:var(--board-felt)"/>`;
    svg += `<rect x="${BAR_X + BAR}" y="${TOP}" width="${half}" height="${BOTTOM - TOP}" rx="3" style="fill:var(--board-felt)"/>`;
    svg += `<rect x="${TRAY_X + 2}" y="${TOP}" width="${TRAY - 4}" height="${BOTTOM - TOP}" rx="6" style="fill:var(--tray)"/>`;

    for (let point = 1; point <= 24; point++) {
      const x = pointX(point);
      const bottomRow = point <= 12;
      const baseY = bottomRow ? BOTTOM : TOP;
      const tipY = bottomRow ? BOTTOM - POINT_H : TOP + POINT_H;
      svg += `<polygon points="${x + 1},${baseY} ${x + POINT_W - 1},${baseY} ${x + POINT_W / 2},${tipY}" style="fill:var(${point % 2 ? "--point-a" : "--point-b"})"/>`;
      if (!mini && !opts.noNumbers) {
        const labelY = bottomRow ? H - FRAME - 5 : FRAME + 14;
        svg += `<text x="${x + POINT_W / 2}" y="${labelY}" text-anchor="middle" font-size="11.5" font-weight="600" font-family="Inter, sans-serif" style="fill:var(--board-label)">${point}</text>`;
      }
    }
    if (interactive) interactive.targets.forEach((p) => (svg += targetSvg(p)));

    for (let point = 1; point <= 24; point++) {
      const count = frame[point];
      if (!count) continue;
      let ring = null;
      if (interactive && count > 0) {
        if (interactive.selected === point) ring = "#facc15";
        else if (interactive.selectable.has(point)) ring = "rgba(250,204,21,0.6)";
      }
      svg += stack(point, Math.abs(count), count > 0 ? bottomPlayer : topPlayer, ring);
    }
    if (frame[25] > 0) {
      let ring = null;
      if (interactive && interactive.selectable.has(25)) ring = interactive.selected === 25 ? "#facc15" : "rgba(250,204,21,0.6)";
      svg += stack(25, frame[25], bottomPlayer, ring);
    }
    if (frame[0] < 0) svg += opponentBar(-frame[0], topPlayer);

    const onBoardBottom = frame.reduce((s, c) => s + (c > 0 ? c : 0), 0);
    const onBoardTop = frame.reduce((s, c) => s + (c < 0 ? -c : 0), 0);
    svg += borneOff(15 - onBoardBottom, true, bottomPlayer);
    svg += borneOff(15 - onBoardTop, false, topPlayer);

    if (!d.crawford_game && !mini) svg += cubeSvg({ value: d.cube_value, owner: d.cube_owner, offered: !!opts.cubeOffered }, bottomPlayer);
    if (!mini) {
      if (opts.dice) svg += diceOnBoard(opts.dice);
      else if (d.kind === "checker" && d.dice) svg += diceOnBoard(d.dice.map((v) => ({ value: v, used: false })));
    }
    if (opts.arrows && !flipped) {
      const start = opts.arrowStart || onrollFrame(d);
      opts.arrows.forEach((a) => (svg += arrowSvg(start, a.steps, a.kind)));
    }
    if (interactive) svg += hitAreas();
    return svg + "</svg>";
  }

  function sideLabel(d, player, pipCount, note) {
    const score = player === 1 ? d.score1 : d.score2;
    const scoreText = d.match_length ? ` · ${score} of ${d.match_length}` : "";
    return `<div class="board-label"><span class="who"><span class="swatch p${player}"></span><strong>${esc(playerName(d, player))}</strong><span>${scoreText}</span></span><span class="pips">${note ? `${note} · ` : ""}${pipCount} pips</span></div>`;
  }

  function renderWithLabels(container, d, opts = {}) {
    const bottom = opts.bottom || d.on_roll;
    const top = bottom === 1 ? 2 : 1;
    let frame = opts.frame || onrollFrame(d);
    if (bottom !== d.on_roll) frame = flip(frame);
    const p = pips(frame);
    container.innerHTML =
      sideLabel(d, top, p.top, d.crawford_game ? "Crawford game" : "") +
      render(d, opts) +
      sideLabel(d, bottom, p.bottom, bottom === d.on_roll ? "on roll" : "");
  }

  return { render, renderWithLabels, pips, onrollFrame, flip, COLORS };
})();

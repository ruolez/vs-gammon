(function (root) {
  const BAR = 25;
  const OFF = 0;

  function frameKey(frame) {
    return frame.join(",");
  }

  function applyStep(frame, step) {
    const [from, to] = step;
    const next = frame.slice();
    next[from] -= 1;
    if (to !== OFF) {
      if (next[to] === -1) {
        next[to] = 0;
        next[0] -= 1;
      }
      next[to] += 1;
    }
    return next;
  }

  function allHome(frame) {
    for (let p = 7; p <= BAR; p++) if (frame[p] > 0) return false;
    return true;
  }

  function highestOccupied(frame) {
    for (let p = 6; p >= 1; p--) if (frame[p] > 0) return p;
    return 0;
  }

  function singleSteps(frame, die) {
    if (frame[BAR] > 0) {
      const to = BAR - die;
      return frame[to] >= -1 ? [[BAR, to]] : [];
    }
    const steps = [];
    const home = allHome(frame);
    const highest = home ? highestOccupied(frame) : 0;
    for (let p = 24; p >= 1; p--) {
      if (frame[p] <= 0) continue;
      const to = p - die;
      if (to >= 1) {
        if (frame[to] >= -1) steps.push([p, to]);
      } else if (home && (to === 0 || p === highest)) {
        steps.push([p, OFF]);
      }
    }
    return steps;
  }

  function diceList(dice) {
    return dice[0] === dice[1] ? [dice[0], dice[0], dice[0], dice[0]] : [dice[0], dice[1]];
  }

  function finalPositions(start, legal) {
    const finals = new Map();
    legal.forEach((move, index) => {
      const end = move.steps.reduce(applyStep, start);
      const key = frameKey(end);
      if (!finals.has(key)) finals.set(key, index);
    });
    return finals;
  }

  function removeOne(dice, die) {
    const i = dice.indexOf(die);
    return dice.slice(0, i).concat(dice.slice(i + 1));
  }

  function canFinish(frame, dice, finals, memo) {
    const key = frameKey(frame);
    if (finals.has(key)) return true;
    const memoKey = `${key}|${dice.slice().sort().join("")}`;
    if (memo.has(memoKey)) return memo.get(memoKey);
    let result = false;
    for (const die of new Set(dice)) {
      for (const step of singleSteps(frame, die)) {
        if (canFinish(applyStep(frame, step), removeOne(dice, die), finals, memo)) {
          result = true;
          break;
        }
      }
      if (result) break;
    }
    memo.set(memoKey, result);
    return result;
  }

  function nextSteps(frame, dice, finals) {
    if (finals.has(frameKey(frame)) && !dice.length) return [];
    const memo = new Map();
    const options = [];
    for (const die of new Set(dice)) {
      for (const [from, to] of singleSteps(frame, die)) {
        if (canFinish(applyStep(frame, [from, to]), removeOne(dice, die), finals, memo)) {
          options.push({ from, to, die });
        }
      }
    }
    return options;
  }

  const Moves = { applyStep, singleSteps, diceList, finalPositions, nextSteps, frameKey, BAR, OFF };
  if (typeof module !== "undefined" && module.exports) module.exports = Moves;
  else root.Moves = Moves;
})(this);

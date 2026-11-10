const test = require("node:test");
const assert = require("node:assert/strict");
const Moves = require("../../app/static/js/moves.js");

const START = [0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2, 0];

function frame(points, bar = 0, oppBar = 0) {
  const f = new Array(26).fill(0);
  Object.entries(points).forEach(([p, n]) => (f[Number(p)] = n));
  f[25] = bar;
  f[0] = -oppBar;
  return f;
}

function finalsFor(start, legal) {
  return Moves.finalPositions(start, legal.map((steps) => ({ steps })));
}

test("applyStep moves a checker and hits a blot", () => {
  const f = frame({ 13: 2, 8: -1 });
  assert.deepEqual(Moves.applyStep(f, [13, 8]), frame({ 13: 1, 8: 1 }, 0, 1));
});

test("applyStep enters from the bar and bears off", () => {
  assert.deepEqual(Moves.applyStep(frame({ 6: 1 }, 1), [25, 20]), frame({ 6: 1, 20: 1 }));
  assert.deepEqual(Moves.applyStep(frame({ 3: 2 }), [3, 0]), frame({ 3: 1 }));
});

test("applyStep does not mutate its input", () => {
  const f = START.slice();
  Moves.applyStep(f, [24, 18]);
  assert.deepEqual(f, START);
});

test("singleSteps respects blocked points", () => {
  assert.deepEqual(Moves.singleSteps(START, 5), [[24, 19], [13, 8], [8, 3], [6, 1]].filter(([, t]) => t !== 19 && t !== 1));
});

test("singleSteps forces bar entry first", () => {
  assert.deepEqual(Moves.singleSteps(frame({ 13: 5, 20: -2 }, 1), 5), []);
  assert.deepEqual(Moves.singleSteps(frame({ 13: 5 }, 1), 3), [[25, 22]]);
});

test("singleSteps bears off only with everything home", () => {
  assert.deepEqual(Moves.singleSteps(frame({ 7: 1, 3: 1 }), 3), [[7, 4], [3, 0]].slice(0, 1));
  assert.deepEqual(Moves.singleSteps(frame({ 4: 1, 2: 1 }), 6), [[4, 0]]);
  assert.deepEqual(Moves.singleSteps(frame({ 5: 1, 2: 1 }), 4), [[5, 1]]);
  assert.deepEqual(Moves.singleSteps(frame({ 5: 1, 2: 1 }), 5), [[5, 0]]);
});

test("diceList expands doubles", () => {
  assert.deepEqual([Moves.diceList([6, 6]), Moves.diceList([3, 1])], [[6, 6, 6, 6], [3, 1]]);
});

test("finalPositions maps each legal play's end position to its index", () => {
  const finals = finalsFor(START, [[[24, 21], [21, 20]], [[13, 10], [6, 5]]]);
  assert.deepEqual([...finals.values()], [0, 1]);
  assert.equal(finals.get(Moves.frameKey(Moves.applyStep(Moves.applyStep(START, [6, 5]), [13, 10]))), 1);
});

test("nextSteps offers only steps that can still finish a legal play", () => {
  const f = frame({ 24: 1, 6: 2 });
  const finals = finalsFor(f, [[[24, 18], [18, 13]]]);
  assert.deepEqual(Moves.nextSteps(f, [6, 5], finals), [{ from: 24, to: 18, die: 6 }, { from: 24, to: 19, die: 5 }]);
});

test("nextSteps lets the dice be played in either order", () => {
  const finals = finalsFor(START, [[[13, 7], [13, 10]]]);
  const afterThree = Moves.applyStep(START, [13, 10]);
  assert.deepEqual(Moves.nextSteps(afterThree, [6], finals), [{ from: 13, to: 7, die: 6 }]);
});

test("nextSteps is empty once a legal play is complete", () => {
  const finals = finalsFor(START, [[[13, 7], [13, 10]]]);
  const done = Moves.applyStep(Moves.applyStep(START, [13, 7]), [13, 10]);
  assert.deepEqual([Moves.nextSteps(done, [], finals), finals.has(Moves.frameKey(done))], [[], true]);
});

test("doubles reach a legal four-step play", () => {
  const finals = finalsFor(START, [[[24, 22], [24, 22], [6, 4], [6, 4]]]);
  let f = START;
  let dice = Moves.diceList([2, 2]);
  for (const step of [[6, 4], [24, 22], [6, 4], [24, 22]]) {
    const option = Moves.nextSteps(f, dice, finals).find((s) => s.from === step[0] && s.to === step[1]);
    assert.ok(option, `step ${step} should be offered`);
    f = Moves.applyStep(f, step);
    dice = dice.slice(1);
  }
  assert.ok(finals.has(Moves.frameKey(f)));
});

const REAL = require("./fixtures/galaxy_3pt_legal.json");

test("every legal move gnubg lists in a real match can be played step by step", () => {
  const failures = [];
  for (const position of REAL) {
    const finals = Moves.finalPositions(position.frame, position.legal.map((steps) => ({ steps })));
    position.legal.forEach((steps, index) => {
      let f = position.frame;
      let dice = Moves.diceList(position.dice);
      for (const [from, to] of steps) {
        const option = Moves.nextSteps(f, dice, finals).find((s) => s.from === from && s.to === to);
        if (!option) {
          failures.push({ id: position.id, index, steps, at: [from, to] });
          return;
        }
        f = Moves.applyStep(f, [from, to]);
        dice = dice.filter((d, i) => i !== dice.indexOf(option.die));
      }
      if (finals.get(Moves.frameKey(f)) !== index) failures.push({ id: position.id, index, steps, end: true });
    });
  }
  assert.deepEqual(failures.slice(0, 5), []);
});

test("in a real match, no step sequence ends in a position gnubg does not list", () => {
  const strays = [];
  for (const position of REAL.slice(0, 40)) {
    const finals = Moves.finalPositions(position.frame, position.legal.map((steps) => ({ steps })));
    const walk = (f, dice) => {
      const options = Moves.nextSteps(f, dice, finals);
      if (!options.length && !finals.has(Moves.frameKey(f))) strays.push(position.id);
      options.forEach((o) => walk(Moves.applyStep(f, [o.from, o.to]), dice.filter((_, i) => i !== dice.indexOf(o.die))));
    };
    walk(position.frame, Moves.diceList(position.dice));
  }
  assert.deepEqual([...new Set(strays)], []);
});

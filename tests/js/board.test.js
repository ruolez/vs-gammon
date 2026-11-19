const { describe, test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "..", "app", "static", "js");
const context = vm.createContext({ t: (text) => text, plural: (n, word) => `${n} ${word}`, module: undefined });
vm.runInContext(fs.readFileSync(path.join(JS, "moves.js"), "utf8"), context);
vm.runInContext(`${fs.readFileSync(path.join(JS, "board.js"), "utf8")}; this.Board = Board;`, context);
const { Board } = context;

// Frame seen by the player on roll: index 1-24 = points, positive = own checkers, negative = the opponent's,
// 25 = own bar, 0 = the opponent's bar.
function frame(own, opponent = {}) {
  const f = Array(26).fill(0);
  Object.entries(own).forEach(([p, n]) => (f[p] = n));
  Object.entries(opponent).forEach(([p, n]) => (f[p] = -n));
  return f;
}

function arrowCount(board, steps) {
  const d = { on_roll: 1, board, kind: "checker", crawford_game: true };
  const svg = Board.render(d, { arrows: [{ steps, kind: "played" }] });
  return (svg.match(/var\(--arrow-game\)/g) || []).length;
}

describe("move arrows", () => {
  test("a checker moving on without hitting is one arrow", () => {
    assert.equal(arrowCount(frame({ 13: 2, 8: 2 }), [[13, 7], [7, 1]]), 1);
  });

  test("a checker that hits on its way breaks the arrow at each hit", () => {
    const cases = [
      [frame({ 8: 2 }, { 2: 1, 1: 1 }), [[8, 2], [2, 1]]],
      [frame({ 25: 1 }, { 22: 1 }), [[25, 22], [22, 16]]],
      [frame({ 13: 1 }, { 10: 1, 7: 1 }), [[13, 10], [10, 7], [7, 4]]],
    ];
    assert.deepEqual(cases.map(([board, steps]) => arrowCount(board, steps)), [2, 2, 3]);
  });

  test("two checkers hitting two blots are two arrows", () => {
    assert.equal(arrowCount(frame({ 8: 1, 6: 1 }, { 2: 1, 3: 1 }), [[8, 2], [6, 3]]), 2);
  });
});

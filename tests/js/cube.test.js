const { describe, test } = require("node:test");
const assert = require("node:assert/strict");
const Cube = require("../../app/static/js/cube.js");

const DOUBTFUL = 0.03;
const summary = (options) => options.map((o) => [o.action, o.row, Number(o.loss.toFixed(4)), o.right]);

describe("cubeOptions", () => {
  test("a close double: no double and double are both right", () => {
    const cube = { nd: 0.586, dt: 0.6, dp: 1.0 };
    assert.deepEqual(summary(Cube.cubeOptions("cube", cube, DOUBTFUL)),
      [["No double", "No double", 0.014, true], ["Double", "Double, take", 0, true]]);
  });

  test("a clear double: waiting is wrong", () => {
    const cube = { nd: 0.794, dt: 0.9215, dp: 1.0 };
    assert.deepEqual(summary(Cube.cubeOptions("cube", cube, DOUBTFUL)),
      [["No double", "No double", 0.1275, false], ["Double", "Double, take", 0, true]]);
  });

  test("too good to double: doubling cashes the game and loses the gammons", () => {
    const cube = { nd: 1.05, dt: 1.3, dp: 1.0 };
    assert.deepEqual(summary(Cube.cubeOptions("cube", cube, DOUBTFUL)),
      [["No double", "No double", 0, true], ["Double", "Double, pass", 0.05, false]]);
  });

  test("a loss of exactly the doubtful threshold is a mistake, as in the error grades", () => {
    const cube = { nd: 0.5, dt: 0.5 + DOUBTFUL, dp: 1.0 };
    assert.deepEqual(Cube.cubeOptions("cube", cube, DOUBTFUL).map((o) => o.right), [false, true]);
  });

  test("a take decision weighs take against pass from the doubler's equities", () => {
    assert.deepEqual(summary(Cube.cubeOptions("take", { nd: 0.4, dt: 0.95, dp: 1.0 }, DOUBTFUL)),
      [["Take", "Double, take", 0, true], ["Pass", "Double, pass", 0.05, false]]);
  });

  test("a close take: take and pass are both right", () => {
    assert.deepEqual(summary(Cube.cubeOptions("take", { nd: 0.4, dt: 1.01, dp: 1.0 }, DOUBTFUL)),
      [["Take", "Double, take", 0.01, true], ["Pass", "Double, pass", 0, true]]);
  });
});

describe("otherRightActions", () => {
  const options = (kind, cube) => Cube.cubeOptions(kind, cube, DOUBTFUL);

  test("names the close alternative to gnubg's best action", () => {
    const cases = [
      ["cube", { nd: 0.586, dt: 0.6, dp: 1.0 }, "Double, take", ["No double"]],
      ["cube", { nd: 0.61, dt: 0.6, dp: 1.0 }, "No double, take", ["Double"]],
      ["cube", { nd: 1.01, dt: 1.3, dp: 1.0 }, "Too good to double, pass", ["Double"]],
      ["take", { nd: 0.4, dt: 1.01, dp: 1.0 }, "Pass", ["Take"]],
    ];
    assert.deepEqual(cases.map(([kind, cube, best]) => Cube.otherRightActions(options(kind, cube), best)),
      cases.map((c) => c[3]));
  });

  test("names nothing when only the best action is right", () => {
    const cases = [
      ["cube", { nd: 0.794, dt: 0.9215, dp: 1.0 }, "Double, take"],
      ["cube", { nd: 1.05, dt: 1.3, dp: 1.0 }, "Too good to double, pass"],
      ["take", { nd: 0.4, dt: 0.95, dp: 1.0 }, "Take"],
    ];
    assert.deepEqual(cases.map(([kind, cube, best]) => Cube.otherRightActions(options(kind, cube), best)), [[], [], []]);
  });
});

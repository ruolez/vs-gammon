/* Which cube actions are right. Equities are the doubler's (as stored); every action losing less than the
   doubtful threshold to the best one is right, the same line the error grades and Practice draw. */
(function (root) {
  function cubeOptions(kind, cube, doubtful) {
    const doubled = Math.min(cube.dt, cube.dp);
    const options = kind === "take"
      ? [{ action: "Take", row: "Double, take", loss: Math.max(0, cube.dt - cube.dp) },
        { action: "Pass", row: "Double, pass", loss: Math.max(0, cube.dp - cube.dt) }]
      : [{ action: "No double", row: "No double", loss: Math.max(0, doubled - cube.nd) },
        { action: "Double", row: cube.dt <= cube.dp ? "Double, take" : "Double, pass", loss: Math.max(0, cube.nd - doubled) }];
    return options.map((o) => ({ ...o, right: o.loss < doubtful - 1e-12 }));
  }

  // gnubg's best action is a phrase ("No double, take", "Too good to double, pass", "Take"); this names the other
  // actions that are right too.
  function otherRightActions(options, best) {
    const chosen = best === "Take" || best === "Pass" ? best : best.startsWith("Double") ? "Double" : "No double";
    return options.filter((o) => o.right && o.action !== chosen).map((o) => o.action);
  }

  const Cube = { cubeOptions, otherRightActions };
  if (typeof module !== "undefined" && module.exports) module.exports = Cube;
  else root.Cube = Cube;
})(this);

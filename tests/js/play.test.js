const test = require("node:test");
const assert = require("node:assert/strict");
const Play = require("../../app/static/js/play.js");

test("webAddress keeps a full http or https address", () => {
  const cases = ["https://backgammongalaxy.com/", "http://localhost:8080/game?id=7", "https://example.org/a#b"];
  assert.deepEqual(cases.map(Play.webAddress), ["https://backgammongalaxy.com/", "http://localhost:8080/game?id=7", "https://example.org/a#b"]);
});

test("webAddress adds https to a bare host and trims spaces", () => {
  const cases = ["backgammongalaxy.com", "  www.backgammongalaxy.com/lobby ", "localhost:5000", "192.168.1.20:8000/play"];
  assert.deepEqual(cases.map(Play.webAddress), [
    "https://backgammongalaxy.com/",
    "https://www.backgammongalaxy.com/lobby",
    "https://localhost:5000/",
    "https://192.168.1.20:8000/play",
  ]);
});

test("webAddress refuses what is not a web address", () => {
  const cases = ["", "   ", "backgammon galaxy", "galaxy", "javascript:alert(1)", "file:///etc/passwd", "data:text/html,hi", "ftp://example.com", "https://"];
  assert.deepEqual(cases.map(Play.webAddress), cases.map(() => null));
});

test("viewRect rounds the element box to whole points and never goes negative", () => {
  assert.deepEqual(Play.viewRect({ left: 240.4, top: 57.6, width: 1079.5, height: 802.2 }), { x: 240, y: 58, width: 1080, height: 802 });
  assert.deepEqual(Play.viewRect({ left: -3, top: 10, width: -20, height: 0.4 }), { x: 0, y: 10, width: 0, height: 0 });
});

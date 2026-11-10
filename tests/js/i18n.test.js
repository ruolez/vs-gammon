const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const I18n = require("../../app/static/js/i18n.js");
const RU = require("../../app/static/js/i18n-ru.js");

const STATIC = path.join(__dirname, "../../app/static");
const jsFiles = fs.readdirSync(path.join(STATIC, "js")).filter((f) => f.endsWith(".js") && !f.startsWith("i18n") && f !== "moves.js");
const source = jsFiles.map((f) => fs.readFileSync(path.join(STATIC, "js", f), "utf8")).join("\n");
const pages = fs.readdirSync(STATIC).filter((f) => f.endsWith(".html")).map((f) => fs.readFileSync(path.join(STATIC, f), "utf8"));

function literals(fn) {
  const found = new Set();
  const pattern = new RegExp(`\\b${fn}\\(\\s*(?:"((?:[^"\\\\]|\\\\.)*)"|'((?:[^'\\\\]|\\\\.)*)')`, "g");
  let m;
  while ((m = pattern.exec(source))) found.add((m[1] ?? m[2]).replace(/\\(.)/g, "$1"));
  return [...found];
}

function htmlTexts() {
  const found = new Set();
  for (const html of pages) {
    const body = html.slice(html.indexOf("<body>")).replace(/<script[\s\S]*?<\/script>/g, "").replace(/<svg[\s\S]*?<\/svg>/g, "");
    for (const m of body.matchAll(/>([^<>]+)</g)) {
      const text = m[1].trim();
      if (/[A-Za-z]{2}/.test(text)) found.add(text);
    }
    for (const m of body.matchAll(/(?:title|aria-label|placeholder)="([^"]+)"/g)) found.add(m[1]);
  }
  return [...found];
}

test("every t() string in the app has a Russian translation", () => {
  assert.deepEqual(literals("t").filter((s) => RU.strings[s] === undefined), []);
});

test("every plural() word has Russian forms", () => {
  assert.deepEqual(literals("plural").map((s) => s).concat(literals("tn")).filter((w) => !RU.plurals[w]), []);
});

test("every static page text has a Russian translation", () => {
  const allowed = new Set(["English", "Русский", "VS Gammon", ".mat", "XG", "GNU Backgammon"]);
  assert.deepEqual(htmlTexts().filter((s) => RU.strings[s] === undefined && !allowed.has(s)), []);
});

test("translations keep every placeholder of the English text", () => {
  const broken = Object.entries(RU.strings).filter(([en, ru]) => {
    const names = (s) => (s.match(/\{\w+\}/g) || []).sort().join();
    return names(en) !== names(ru);
  }).map(([en]) => en);
  assert.deepEqual(broken, []);
});

test("t falls back to English and fills placeholders", () => {
  I18n.use("en");
  assert.equal(I18n.t("{n}-point match", { n: 7 }), "7-point match");
  I18n.use("ru");
  assert.equal(I18n.t("18/13"), "18/13");
});

test("Russian plurals use one, few and many forms", () => {
  I18n.use("ru");
  assert.deepEqual([1, 2, 5, 11, 21, 22].map((n) => I18n.tn("match", n)),
    ["1 матч", "2 матча", "5 матчей", "11 матчей", "21 матч", "22 матча"]);
});

test("English plurals", () => {
  I18n.use("en");
  assert.deepEqual([I18n.tn("try", 1), I18n.tn("try", 2), I18n.tn("match", 3)], ["1 try", "2 tries", "3 matches"]);
});

test("server history messages are translated in Russian", () => {
  I18n.use("ru");
  const cases = [
    "Analysed chessgamm0n vs fishsoup (3-point, 2026-11-09) at 2-ply in 1.56 s, 187 decisions. chessgamm0n: PR 9.6, 10 errors (5 very bad); fishsoup: PR 10.3, 11 errors (1 very bad)",
    "Imported chessgamm0n vs fishsoup (3-point, 2026-11-09) from /Users/x/Downloads/m.mat",
    "Imported a vs b (money) by upload (m.mat)",
    "/Users/x/m.mat is already imported as a vs b (7-point)",
    "Analysis of a vs b (5-point) failed: gnubg could not import any games from this file",
    "Re-analysis requested for a vs b (5-point)",
    "Deleted a vs b (5-point)",
    "Exported 3 positions to gammon-positions.zip",
    "Watching /Users/x/Downloads for new match files",
    "Stopped watching /Users/x/Downloads",
    "/Users/x/m.mat: not a match file: no 'N point match' line",
  ];
  const untranslated = cases.filter((c) => !/[а-яё]/i.test(I18n.server(c)));
  assert.deepEqual(untranslated, []);
});

test("server messages stay untouched in English", () => {
  I18n.use("en");
  const text = "Deleted a vs b (5-point)";
  assert.equal(I18n.server(text), text);
});

test("analysed message reads naturally in Russian", () => {
  I18n.use("ru");
  assert.equal(
    I18n.server("Analysed a vs b (3-point, 2026-11-09) at 2-ply in 1.5 s, 187 decisions. a: PR 9.6, 10 errors (5 very bad)"),
    "Проанализирован a против b (матч до 3, 2026-11-09), глубина 2-ply, 1.5 с, 187 решений. a: PR 9.6, 10 ошибок (очень плохих: 5)",
  );
});

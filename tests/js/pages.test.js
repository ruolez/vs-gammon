const { test, describe } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const STATIC_DIR = path.join(__dirname, "..", "..", "app", "static");
const PAGES = fs.readdirSync(STATIC_DIR).filter((name) => name.endsWith(".html"));
const INLINE_SCRIPT = /<script>([\s\S]*?)<\/script>/g;

describe("page head scripts", () => {
  for (const page of PAGES) {
    test(`${page} has inline scripts that parse`, () => {
      const html = fs.readFileSync(path.join(STATIC_DIR, page), "utf8");
      const scripts = [...html.matchAll(INLINE_SCRIPT)].map((m) => m[1]);
      assert.notDeepStrictEqual(scripts, []);
      for (const script of scripts) assert.doesNotThrow(() => new Function(script));
    });
  }
});

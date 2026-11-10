(function (root) {
  const isNode = typeof module !== "undefined" && module.exports;
  const RU = isNode ? require("./i18n-ru.js") : root.I18N_RU;
  const LANGUAGES = { en: { label: "English", short: "EN", locale: "en-US" }, ru: { label: "Русский", short: "RU", locale: "ru-RU" } };
  const EN_PLURALS = {
    match: "matches", game: "games", decision: "decisions", error: "errors", position: "positions", try: "tries",
    answer: "answers", day: "days", time: "times", folder: "folders", ".mat file": ".mat files", pip: "pips",
  };
  const STORAGE_KEY = "ga-lang";

  function detect() {
    try {
      const saved = root.localStorage && root.localStorage.getItem(STORAGE_KEY);
      if (saved && LANGUAGES[saved]) return saved;
    } catch (_) {}
    const nav = root.navigator && root.navigator.language;
    return nav && nav.toLowerCase().startsWith("ru") ? "ru" : "en";
  }

  let lang = detect();

  function fill(text, params) {
    if (!params) return text;
    return text.replace(/\{(\w+)\}/g, (all, key) => (key in params ? params[key] : all));
  }

  function t(text, params) {
    return fill(lang === "ru" && RU.strings[text] !== undefined ? RU.strings[text] : text, params);
  }

  function tn(word, n) {
    if (lang === "ru") {
      const forms = RU.plurals[word];
      if (forms) {
        const rule = new Intl.PluralRules("ru-RU").select(n);
        return `${n} ${forms[rule === "one" ? 0 : rule === "few" ? 1 : 2]}`;
      }
    }
    return `${n} ${n === 1 ? word : EN_PLURALS[word] || word}`;
  }

  function matchDescription(text) {
    const m = text.match(/^(.+) vs (.+) \((?:(\d+)-point|money)(?:, (.+))?\)$/);
    if (!m) return text;
    const kind = m[3] ? t("{n}-point", { n: m[3] }) : t("money");
    return `${m[1]} ${t("vs")} ${m[2]} (${kind}${m[4] ? `, ${m[4]}` : ""})`;
  }

  function playerSummary(text) {
    return text.split("; ").map((part) => {
      const m = part.match(/^(.+): PR (.+), (\d+) errors \((\d+) very bad\)$/);
      if (!m) return part;
      return t("{name}: PR {pr}, {errors} ({blunders} very bad)", { name: m[1], pr: m[2], errors: tn("error", Number(m[3])), blunders: m[4] });
    }).join("; ");
  }

  const SERVER_PATTERNS = [
    [/^Analysed (.+) at (\d+)-ply in ([\d.]+) s, (\d+) decisions\. (.*)$/s, (m) => t("Analysed {match} at {plies}-ply in {seconds} s, {decisions}. {summary}", { match: matchDescription(m[1]), plies: m[2], seconds: m[3], decisions: tn("decision", Number(m[4])), summary: playerSummary(m[5]) })],
    [/^Analysis of (.+) failed: (.*)$/s, (m) => t("Analysis of {match} failed: {reason}", { match: matchDescription(m[1]), reason: server(m[2]) })],
    [/^Analysis of (.+) crashed: (.*)$/s, (m) => t("Analysis of {match} crashed: {reason}", { match: matchDescription(m[1]), reason: m[2] })],
    [/^Imported (.+) by upload \((.+)\)$/, (m) => t("Imported {match} by upload ({file})", { match: matchDescription(m[1]), file: m[2] })],
    [/^Imported (.+) from (.+)$/, (m) => t("Imported {match} from {path}", { match: matchDescription(m[1]), path: m[2] })],
    [/^(.+) is already imported as (.+)$/, (m) => t("{file} is already imported as {match}", { file: m[1], match: matchDescription(m[2]) })],
    [/^Re-analysis requested for (.+)$/, (m) => t("Re-analysis requested for {match}", { match: matchDescription(m[1]) })],
    [/^Deleted (.+)$/, (m) => t("Deleted {match}", { match: matchDescription(m[1]) })],
    [/^Exported (\d+) positions to (.+)$/, (m) => t("Exported {positions} to {file}", { positions: tn("position", Number(m[1])), file: m[2] })],
    [/^Watching (.+) for new match files$/, (m) => t("Watching {path} for new match files", { path: m[1] })],
    [/^Stopped watching (.+)$/, (m) => t("Stopped watching {path}", { path: m[1] })],
    [/^export at most (\d+) positions at a time$/, (m) => t("export at most {n} positions at a time", { n: m[1] })],
    [/^only folders inside (.+) can be used$/, (m) => t("only folders inside {path} can be used", { path: m[1] })],
    [/^no permission to read (.+)$/, (m) => t("no permission to read {path}", { path: m[1] })],
    [/^(.+) is not a folder$/, (m) => t("{path} is not a folder", { path: m[1] })],
    [/^(.+) no longer exists$/, (m) => t("{path} no longer exists", { path: m[1] })],
    [/^'(.+)' is not an answer to this cube decision$/, (m) => t("'{answer}' is not an answer to this cube decision", { answer: m[1] })],
    [/^analysis timed out after (\d+) s$/, (m) => t("analysis timed out after {n} s", { n: m[1] })],
    [/^gnubg exited with code (\S+) without a result: (.*)$/s, (m) => t("gnubg exited with code {code} without a result: {detail}", { code: m[1], detail: m[2] })],
    [/^(.+): (file is larger than 5 MB|not a match file: no 'N point match' line)$/, (m) => `${m[1]}: ${t(m[2])}`],
  ];

  function server(message) {
    if (lang === "en") return message;
    if (RU.strings[message] !== undefined) return RU.strings[message];
    for (const [pattern, render] of SERVER_PATTERNS) {
      const m = message.match(pattern);
      if (m) return render(m);
    }
    return message;
  }

  function translateDom(doc) {
    doc.documentElement.lang = lang;
    if (lang === "en") return;
    doc.title = doc.title.split(" · ").map((part) => t(part)).join(" · ");
    const walker = doc.createTreeWalker(doc.body, 4);
    let node;
    while ((node = walker.nextNode())) {
      const key = node.nodeValue.trim();
      if (key && RU.strings[key] !== undefined) node.nodeValue = node.nodeValue.replace(key, RU.strings[key]);
    }
    doc.querySelectorAll("[title], [aria-label], [placeholder]").forEach((el) => {
      ["title", "aria-label", "placeholder"].forEach((name) => {
        const value = el.getAttribute(name);
        if (value && RU.strings[value] !== undefined) el.setAttribute(name, RU.strings[value]);
      });
    });
  }

  const I18n = {
    LANGUAGES,
    t,
    tn,
    server,
    translateDom,
    get lang() { return lang; },
    locale() { return LANGUAGES[lang].locale; },
    use(next) { if (LANGUAGES[next]) lang = next; },
    set(next) {
      try { root.localStorage.setItem(STORAGE_KEY, next); } catch (_) {}
      lang = next;
    },
  };

  if (isNode) {
    module.exports = I18n;
  } else {
    root.I18n = I18n;
    root.t = t;
    root.addEventListener("DOMContentLoaded", () => translateDom(root.document));
  }
})(typeof window !== "undefined" ? window : globalThis);

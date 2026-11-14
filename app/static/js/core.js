const api = {
  async request(method, url, body) {
    const options = { method, headers: {} };
    if (body instanceof FormData) {
      options.body = body;
    } else if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        message = (await response.json()).error || message;
      } catch (_) {}
      throw new Error(I18n.server(message));
    }
    return response;
  },
  async get(url) { return (await this.request("GET", url)).json(); },
  async post(url, body) { return (await this.request("POST", url, body)).json(); },
  async put(url, body) { return (await this.request("PUT", url, body)).json(); },
  async patch(url, body) { return (await this.request("PATCH", url, body)).json(); },
  async del(url) { return (await this.request("DELETE", url)).json(); },
};

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  practice: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
  review: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="11.5" cy="11.5" r="3.5"/><path d="m16.5 16.5-2.5-2.5"/>',
  matches: '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  settings: '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
  reset: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  copy: '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  panel: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
  alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M9 15h6"/><path d="M12 18v-6"/>',
  pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  play: '<path d="M6 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L7.5 3.64A1 1 0 0 0 6 4.5Z"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  forward: '<path d="m9 18 6-6-6-6"/>',
  tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1.2"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  pencil: '<path d="M21.17 6.81a2.83 2.83 0 0 0-4-4L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/>',
  merge: '<path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.17 2.87L4 22"/><path d="m20 22-5-5"/>',
  cube: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M9 9h.01"/><path d="M15 15h.01"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/>',
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  list: '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
};

function icon(name, cls = "") {
  return `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

const PIPS = {
  1: [[12, 12]], 2: [[7.5, 7.5], [16.5, 16.5]], 3: [[7, 7], [12, 12], [17, 17]],
  4: [[7.5, 7.5], [16.5, 7.5], [7.5, 16.5], [16.5, 16.5]],
  5: [[7, 7], [17, 7], [12, 12], [7, 17], [17, 17]],
  6: [[7.5, 6.5], [16.5, 6.5], [7.5, 12], [16.5, 12], [7.5, 17.5], [16.5, 17.5]],
};

function dieSvg(value, cls = "die") {
  const pips = (PIPS[value] || []).map(([x, y]) => `<circle cx="${x}" cy="${y}" r="2.1" style="fill:var(--die-pip)"/>`).join("");
  return `<svg class="${cls}" viewBox="0 0 24 24" role="img" aria-label="${value}"><rect x="1" y="1" width="22" height="22" rx="5" style="fill:var(--die);stroke:var(--die-edge)"/>${pips}</svg>`;
}

function diceSvg(dice) {
  if (!dice) return "";
  return `<span class="dice">${dieSvg(dice[0])}${dieSvg(dice[1])}</span>`;
}

const SEVERITY_LABEL = { very_bad: t("Very bad"), bad: t("Bad"), doubtful: t("Doubtful") };

function errorClass(error, thresholds) {
  return ["very_bad", "bad", "doubtful"].find((s) => error >= thresholds[s] - 1e-12) || null;
}

function severityChip(cls) {
  return cls ? `<span class="sev ${cls}">${SEVERITY_LABEL[cls]}</span>` : `<span class="sev ok">${t("Good")}</span>`;
}

function severityPhrase(d) {
  const noun = d.kind === "checker" ? "move" : "decision";
  return t({
    very_bad: { move: "Very bad move", decision: "Very bad decision" },
    bad: { move: "Bad move", decision: "Bad decision" },
    doubtful: { move: "Doubtful move", decision: "Doubtful decision" },
  }[d.class][noun]);
}

function formatEquity(value) {
  if (value === null || value === undefined) return "";
  const v = Math.abs(value) < 0.0005 ? 0 : value;
  return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(3);
}

function formatLoss(value) {
  return value > 0.0005 ? `−${value.toFixed(3)}` : "0.000";
}

function playerName(d, player) {
  return player === 1 ? d.player1 : d.player2;
}

function shortDate(value) {
  if (!value) return "";
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(I18n.locale(), { month: "short", day: "numeric" });
}

function plural(n, word) {
  return I18n.tn(word, n);
}

function term(text, explanation) {
  return `<span class="term" title="${esc(explanation)}">${text}</span>`;
}

function confirmDialog({ title, body, action }) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal confirm";
    dialog.innerHTML = `<div class="body"><h3>${esc(title)}</h3><p>${esc(body)}</p></div>
      <footer><button class="btn ghost" data-answer="no">${t("Cancel")}</button><button class="btn danger" data-answer="yes">${esc(action)}</button></footer>`;
    document.body.appendChild(dialog);
    const finish = (answer) => { dialog.close(); dialog.remove(); resolve(answer); };
    dialog.addEventListener("click", (ev) => {
      const button = ev.target.closest("[data-answer]");
      if (button) finish(button.dataset.answer === "yes");
      else if (ev.target === dialog) finish(false);
    });
    dialog.addEventListener("cancel", (ev) => { ev.preventDefault(); finish(false); });
    dialog.showModal();
    dialog.querySelector('[data-answer="no"]').focus();
  });
}

function toast(message, isError = false, action = null) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.innerHTML = `${icon(isError ? "alert" : "check")}<span>${esc(message)}</span>${action ? `<button type="button" class="toast-action">${esc(action.label)}</button>` : ""}`;
  if (action) el.querySelector(".toast-action").addEventListener("click", action.run);
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), action ? 9000 : isError ? 6000 : 3200);
}

/* ---------- remembered choices (per browser) ---------- */
const Prefs = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(`vsg:${key}`);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  },
  set(key, value) {
    try { localStorage.setItem(`vsg:${key}`, JSON.stringify(value)); } catch (_) {}
  },
};

/* ---------- theme ---------- */
const Theme = {
  key: "ga-theme",
  get() {
    try { return localStorage.getItem(this.key) || "system"; } catch (_) { return "system"; }
  },
  resolved(choice) {
    if (choice === "light" || choice === "dark") return choice;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  },
  set(choice) {
    try { localStorage.setItem(this.key, choice); } catch (_) {}
    this.apply();
  },
  apply() {
    document.documentElement.dataset.theme = this.resolved(this.get());
    document.dispatchEvent(new CustomEvent("themechange"));
    document.querySelectorAll("[data-theme-choice]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === this.get())));
    const cycle = document.getElementById("theme-cycle");
    if (cycle) {
      const name = { system: "monitor", light: "sun", dark: "moon" }[this.get()];
      cycle.innerHTML = icon(name);
      cycle.title = t("Switch theme");
    }
    document.dispatchEvent(new CustomEvent("themechange"));
  },
};
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => Theme.apply());

/* ---------- text size ---------- */
const TextSize = {
  key: "ga-text",
  steps: [90, 100, 110, 120, 135, 150],
  get() {
    try { return parseInt(localStorage.getItem(this.key), 10) || 100; } catch (_) { return 100; }
  },
  set(percent) {
    try { localStorage.setItem(this.key, String(percent)); } catch (_) {}
    document.documentElement.style.fontSize = `${percent}%`;
    document.querySelectorAll("[data-text-value]").forEach((el) => (el.textContent = `${percent}%`));
    document.dispatchEvent(new CustomEvent("textsizechange"));
  },
  step(direction) {
    const i = this.steps.indexOf(this.get());
    const next = Math.min(this.steps.length - 1, Math.max(0, (i < 0 ? 1 : i) + direction));
    this.set(this.steps[next]);
  },
};

/* ---------- shell ---------- */
const NAV = [
  ["/", "dashboard", t("Dashboard")],
  ["/practice", "practice", t("Practice")],
  ["/moves", "review", t("Moves")],
  ["/matches", "matches", t("Matches")],
  ["/play", "globe", t("Play online")],
  ["/history", "history", t("History")],
  ["/settings", "settings", t("Settings")],
];

const BRAND_MARK = `<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><defs><clipPath id="brand-clip"><rect x="1" y="1" width="30" height="30" rx="8"/></clipPath></defs><rect x="1" y="1" width="30" height="30" rx="8" fill="var(--accent)"/><g clip-path="url(#brand-clip)"><path d="M1 1H6L3.5 10.5Z" fill="#fff" fill-opacity=".24"/><path d="M1 31H6L3.5 21.5Z" fill="#0b1b4a" fill-opacity=".2"/><path d="M6 1H11L8.5 10.5Z" fill="#0b1b4a" fill-opacity=".2"/><path d="M6 31H11L8.5 21.5Z" fill="#fff" fill-opacity=".24"/><path d="M11 1H16L13.5 10.5Z" fill="#fff" fill-opacity=".24"/><path d="M11 31H16L13.5 21.5Z" fill="#0b1b4a" fill-opacity=".2"/><path d="M16 1H21L18.5 10.5Z" fill="#0b1b4a" fill-opacity=".2"/><path d="M16 31H21L18.5 21.5Z" fill="#fff" fill-opacity=".24"/><path d="M21 1H26L23.5 10.5Z" fill="#fff" fill-opacity=".24"/><path d="M21 31H26L23.5 21.5Z" fill="#0b1b4a" fill-opacity=".2"/><path d="M26 1H31L28.5 10.5Z" fill="#0b1b4a" fill-opacity=".2"/><path d="M26 31H31L28.5 21.5Z" fill="#fff" fill-opacity=".24"/></g><circle cx="16" cy="16.6" r="9.6" fill="#0b1b4a" fill-opacity=".3"/><circle cx="16" cy="16" r="9.6" fill="#fff"/><circle cx="16" cy="16" r="7.9" fill="none" stroke="#c3cee3" stroke-width=".7"/><text x="16" y="19.2" text-anchor="middle" font-family="Inter, sans-serif" font-size="8.6" font-weight="800" letter-spacing="-.3" fill="#1e2a46">VS</text></svg>`;

const Shell = {
  info: null,
  render() {
    const aside = document.getElementById("sidebar");
    if (!aside) return;
    const active = aside.dataset.active;
    aside.innerHTML = `
      <a class="brand" href="/" title="VS Gammon">${BRAND_MARK}<span class="brand-name">VS Gammon</span></a>
      <nav aria-label="${t("Main")}">${NAV.map(([href, ic, label]) => `
        <a class="nav-item ${href === active ? "active" : ""}" href="${href}" title="${label}" ${href === active ? 'aria-current="page"' : ""}>
          ${icon(ic)}<span class="nav-label">${label}</span>${ic === "practice" ? '<span class="badge" id="due-badge" hidden></span>' : ""}
        </a>`).join("")}
      </nav>
      <div class="spacer"></div>
      <div class="sidebar-foot">
        <div class="watch-line" id="watch-line" title="${t("Watched folders")}"><i class="dot off"></i><span></span></div>
        <div class="text-size" role="group" aria-label="${t("Text size")}">
          <button class="btn ghost sm icon-only foot-btn" id="text-down" title="${t("Smaller text")} (−)" aria-label="${t("Smaller text")}">A−</button>
          <span class="value" data-text-value>${TextSize.get()}%</span>
          <button class="btn ghost sm icon-only foot-btn" id="text-up" title="${t("Larger text")} (+)" aria-label="${t("Larger text")}">A+</button>
        </div>
        <div class="foot-row">
          <div class="seg theme" role="group" aria-label="${t("Theme")}">
            <button type="button" data-theme-choice="light" title="${t("Light")}">${icon("sun")}<span class="sr-only">${t("Light")}</span></button>
            <button type="button" data-theme-choice="system" title="${t("Match system")}">${icon("monitor")}<span class="sr-only">${t("System")}</span></button>
            <button type="button" data-theme-choice="dark" title="${t("Dark")}">${icon("moon")}<span class="sr-only">${t("Dark")}</span></button>
          </div>
          <button class="btn ghost sm icon-only theme-cycle" id="theme-cycle" title="${t("Switch theme")}" aria-label="${t("Switch theme")}">${icon("moon")}</button>
          <button class="btn ghost sm icon-only foot-btn" id="lang-toggle" title="${t("Language")}" aria-label="${t("Language")}">${I18n.LANGUAGES[I18n.lang === "en" ? "ru" : "en"].short}</button>
          <button class="btn ghost sm icon-only" id="collapse" title="${t("Collapse sidebar")} (\\)" aria-label="${t("Collapse sidebar")}">${icon("panel")}</button>
        </div>
        <div class="engine-line" id="engine-line"></div>
      </div>`;
    aside.querySelectorAll("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => Theme.set(b.dataset.themeChoice)));
    $("collapse").addEventListener("click", () => this.toggleCollapse());
    $("text-down").addEventListener("click", () => TextSize.step(-1));
    $("text-up").addEventListener("click", () => TextSize.step(1));
    $("lang-toggle").addEventListener("click", () => {
      I18n.set(I18n.lang === "en" ? "ru" : "en");
      location.reload();
    });
    $("theme-cycle").addEventListener("click", () => {
      const order = ["system", "light", "dark"];
      Theme.set(order[(order.indexOf(Theme.get()) + 1) % order.length]);
    });
    Theme.apply();
    this.refresh();
  },
  toggleCollapse() {
    const collapsed = document.documentElement.dataset.sidebar !== "collapsed";
    document.documentElement.dataset.sidebar = collapsed ? "collapsed" : "";
    try { localStorage.setItem("ga-sidebar", collapsed ? "collapsed" : ""); } catch (_) {}
  },
  async refresh() {
    try {
      const info = await api.get("/api/shell");
      this.info = info;
      const badge = $("due-badge");
      if (badge) {
        badge.textContent = info.due;
        badge.hidden = !info.due;
      }
      const watch = $("watch-line");
      if (watch) {
        const on = info.watching.length > 0;
        const home = (p) => p.replace(/^\/Users\/[^/]+/, "~");
        watch.innerHTML = `<i class="dot ${on ? "" : "off"}"></i><span>${on ? t("Watching {paths}", { paths: esc(info.watching.map(home).join(", ")) }) : t('<a href="/settings#folders">Watch a folder</a> to import automatically')}</span>`;
      }
      if ($("engine-line")) $("engine-line").textContent = info.engine ? info.engine.replace(/ \d{8}$/, "") : t("Engine not found");
      document.dispatchEvent(new CustomEvent("shellinfo", { detail: info }));
    } catch (_) {}
  },
};

/* ---------- the desktop window (macOS or Windows app): null in a browser ---------- */
const Host = (() => {
  const mac = window.webkit?.messageHandlers?.vsg;
  if (mac) return { call: (name, args = {}) => mac.postMessage({ name, args }) };
  const webview = window.chrome?.webview;
  if (!webview) return null;
  let next = 0;
  const waiting = new Map();
  webview.addEventListener("message", (ev) => {
    const message = ev.data || {};
    if (message.event) return document.dispatchEvent(new CustomEvent(message.event, { detail: message.detail }));
    const pending = waiting.get(message.id);
    if (!pending) return;
    waiting.delete(message.id);
    if (message.error) pending.reject(new Error(message.error));
    else pending.resolve(message.result);
  });
  return {
    call(name, args = {}) {
      const id = ++next;
      return new Promise((resolve, reject) => {
        waiting.set(id, { resolve, reject });
        webview.postMessage({ id, name, args });
      });
    },
  };
})();

/* ---------- macOS app bridge: absent in a browser ---------- */
const Native = {
  available: Boolean(window.webkit?.messageHandlers?.vsg),
  call(name, args = {}) {
    return window.webkit.messageHandlers.vsg.postMessage({ name, args });
  },
  menuStrings() {
    return {
      "About VS Gammon": t("About VS Gammon"), "Check for Updates…": t("Check for Updates…"), "Settings…": t("Settings…"),
      "Hide VS Gammon": t("Hide VS Gammon"), "Hide Others": t("Hide Others"), "Show All": t("Show All"), "Quit VS Gammon": t("Quit VS Gammon"),
      "File": t("File"), "Import Matches…": t("Import Matches…"), "Close Window": t("Close Window"),
      "Edit": t("Edit"), "Undo": t("Undo"), "Redo": t("Redo"), "Cut": t("Cut"), "Copy": t("Copy"), "Paste": t("Paste"), "Select All": t("Select All"),
      "View": t("View"), "Dashboard": t("Dashboard"), "Practice": t("Practice"), "Moves": t("Moves"), "Matches": t("Matches"), "Play Online": t("Play online"), "History": t("History"),
      "Back": t("Back"), "Forward": t("Forward"), "Reload": t("Reload"),
      "Larger Text": t("Larger Text"), "Smaller Text": t("Smaller Text"), "Actual Size": t("Actual Size"),
      "Theme": t("Theme"), "Light": t("Light"), "Dark": t("Dark"), "Match System": t("Match System"), "Language": t("Language"),
      "Toggle Sidebar": t("Toggle Sidebar"), "Enter Full Screen": t("Enter Full Screen"),
      "Window": t("Window"), "Minimize": t("Minimize"), "Zoom": t("Zoom"),
      "Help": t("Help"), "VS Gammon Help": t("VS Gammon Help"), "GNU Backgammon Source Code": t("GNU Backgammon Source Code"),
      "Analysis is still running": t("Analysis is still running"),
      "It carries on from the start of that match next time you open VS Gammon.": t("It carries on from the start of that match next time you open VS Gammon."),
      "Quit": t("Quit"), "Cancel": t("Cancel"),
    };
  },
  syncAppearance() {
    Native.call("sync", { theme: document.documentElement.dataset.theme, background: getComputedStyle(document.body).backgroundColor });
  },
  async saveBlob(blob, name) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
    return Native.call("saveFile", { name, base64: dataUrl.split(",")[1] });
  },
  privacyAction() {
    return { label: t("Open System Settings"), run: () => Native.call("openPrivacySettings") };
  },
  async notifyNewEvents() {
    const { events } = await api.get("/api/history?limit=5");
    const newest = events.length ? events[0].id : 0;
    const stored = parseInt(localStorage.getItem("ga-seen-event"), 10);
    const seen = Number.isNaN(stored) ? newest : stored;
    const fresh = events.filter((e) => e.id > seen && ["analysed", "analysis_failed"].includes(e.kind)).reverse();
    for (const e of fresh) {
      Native.call("notify", { title: e.kind === "analysed" ? t("Analysis finished") : t("Analysis failed"), body: I18n.server(e.message) });
    }
    localStorage.setItem("ga-seen-event", String(newest));
    if (fresh.length) Shell.refresh();
  },
  init() {
    if (!Native.available) return;
    Native.call("sync", { strings: Native.menuStrings() });
    Native.syncAppearance();
    document.addEventListener("themechange", Native.syncAppearance);
    document.addEventListener("shellinfo", (ev) => Native.call("sync", { due: ev.detail.due }));
    Native.notifyNewEvents().catch(() => {});
    setInterval(() => Native.notifyNewEvents().catch(() => {}), 10000);
  },
};

document.addEventListener("DOMContentLoaded", () => { Shell.render(); Native.init(); });
document.addEventListener("keydown", (ev) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) || ev.metaKey || ev.ctrlKey) return;
  if (ev.key === "\\") Shell.toggleCollapse();
  if (ev.key === "+" || ev.key === "=") TextSize.step(1);
  if (ev.key === "-" || ev.key === "_") TextSize.step(-1);
});

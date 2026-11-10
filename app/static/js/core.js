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
      throw new Error(message);
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
  cube: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M9 9h.01"/><path d="M15 15h.01"/>',
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
  const pips = (PIPS[value] || []).map(([x, y]) => `<circle cx="${x}" cy="${y}" r="2.1" fill="#1e2a46"/>`).join("");
  return `<svg class="${cls}" viewBox="0 0 24 24" role="img" aria-label="${value}"><rect x="1" y="1" width="22" height="22" rx="5" fill="#f8fafc" stroke="rgba(15,23,42,.25)"/>${pips}</svg>`;
}

function diceSvg(dice) {
  if (!dice) return "";
  return `<span class="dice">${dieSvg(dice[0])}${dieSvg(dice[1])}</span>`;
}

const SEVERITY_LABEL = { very_bad: "Very bad", bad: "Bad", doubtful: "Doubtful" };

function severityChip(cls) {
  return cls ? `<span class="sev ${cls}">${SEVERITY_LABEL[cls]}</span>` : `<span class="sev ok">Good</span>`;
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
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function plural(n, word, many = `${word}s`) {
  return `${n} ${n === 1 ? word : many}`;
}

function toast(message, isError = false) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.innerHTML = `${icon(isError ? "alert" : "check")}<span>${esc(message)}</span>`;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), isError ? 6000 : 3200);
}

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
    document.querySelectorAll("[data-theme-choice]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === this.get())));
    const cycle = document.getElementById("theme-cycle");
    if (cycle) {
      const name = { system: "monitor", light: "sun", dark: "moon" }[this.get()];
      cycle.innerHTML = icon(name);
      cycle.title = `Theme: ${this.get()} (click to change)`;
    }
    document.dispatchEvent(new CustomEvent("themechange"));
  },
};
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => Theme.apply());

/* ---------- shell ---------- */
const NAV = [
  ["/", "dashboard", "Dashboard"],
  ["/practice", "practice", "Practice"],
  ["/review", "review", "Review"],
  ["/matches", "matches", "Matches"],
  ["/history", "history", "History"],
  ["/settings", "settings", "Settings"],
];

const BRAND_MARK = `<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="1" y="1" width="30" height="30" rx="8" fill="var(--accent)"/><rect x="7" y="7" width="18" height="18" rx="4.5" fill="#fff"/><text x="16" y="20.6" text-anchor="middle" font-family="Inter, sans-serif" font-size="10" font-weight="800" fill="#1e2a46">64</text></svg>`;

const Shell = {
  info: null,
  render() {
    const aside = document.getElementById("sidebar");
    if (!aside) return;
    const active = aside.dataset.active;
    aside.innerHTML = `
      <a class="brand" href="/" title="VS Gammon">${BRAND_MARK}<span class="brand-name">VS Gammon</span></a>
      <nav aria-label="Main">${NAV.map(([href, ic, label]) => `
        <a class="nav-item ${href === active ? "active" : ""}" href="${href}" title="${label}" ${href === active ? 'aria-current="page"' : ""}>
          ${icon(ic)}<span class="nav-label">${label}</span>${ic === "practice" ? '<span class="badge" id="due-badge" hidden></span>' : ""}
        </a>`).join("")}
      </nav>
      <div class="spacer"></div>
      <div class="sidebar-foot">
        <div class="watch-line" id="watch-line" title="Watched folders"><i class="dot off"></i><span>Loading…</span></div>
        <div class="foot-row">
          <div class="seg theme" role="group" aria-label="Theme">
            <button type="button" data-theme-choice="light" title="Light">${icon("sun")}<span class="sr-only">Light</span></button>
            <button type="button" data-theme-choice="system" title="Match system">${icon("monitor")}<span class="sr-only">System</span></button>
            <button type="button" data-theme-choice="dark" title="Dark">${icon("moon")}<span class="sr-only">Dark</span></button>
          </div>
          <button class="btn ghost sm icon-only theme-cycle" id="theme-cycle" title="Switch theme">${icon("moon")}</button>
          <button class="btn ghost sm icon-only" id="collapse" title="Collapse sidebar (\\)">${icon("panel")}</button>
        </div>
        <div class="engine-line" id="engine-line"></div>
      </div>`;
    aside.querySelectorAll("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => Theme.set(b.dataset.themeChoice)));
    $("collapse").addEventListener("click", () => this.toggleCollapse());
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
        watch.innerHTML = `<i class="dot ${on ? "" : "off"}"></i><span>${on ? `Watching ${esc(info.watching.map(home).join(", "))}` : '<a href="/settings#folders">Watch a folder</a> to import automatically'}</span>`;
      }
      if ($("engine-line")) $("engine-line").textContent = info.engine ? info.engine.replace(/ \d{8}$/, "") : "Engine not found";
      document.dispatchEvent(new CustomEvent("shellinfo", { detail: info }));
    } catch (_) {}
  },
};

document.addEventListener("DOMContentLoaded", () => Shell.render());
document.addEventListener("keydown", (ev) => {
  if (ev.key === "\\" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) Shell.toggleCollapse();
});

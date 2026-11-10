let presets = {};

function setThresholdInputs(t) {
  ["doubtful", "bad", "very_bad"].forEach((k) => ($(`t-${k}`).value = t[k]));
}

let preset = "gnubg";

function setPreset(value) {
  preset = value;
  document.querySelectorAll("#preset-seg [data-preset]").forEach((b) => {
    const on = b.dataset.preset === value;
    b.setAttribute("aria-pressed", String(on));
    b.setAttribute("aria-checked", String(on));
  });
}

async function load() {
  const [{ settings, presets: p }, { players }] = await Promise.all([api.get("/api/settings"), api.get("/api/players")]);
  presets = p;
  setPreset(settings.preset);
  setThresholdInputs(settings.thresholds);
  $("plies").value = String(settings.plies);
  $("threads").value = settings.threads;
  const interval = $("watch-interval");
  if ([...interval.options].some((o) => o.value === String(settings.watch_interval))) interval.value = String(settings.watch_interval);
  $("me").innerHTML = `<option value="">${t("Not set: show both players")}</option>` + players.map((pl) => `<option value="${esc(pl.name)}">${esc(pl.name)} · ${plural(pl.matches, "match")}</option>`).join("");
  $("me").value = settings.me || "";
}

async function save(body, message) {
  try {
    await api.put("/api/settings", body);
    toast(message);
    Shell.refresh();
  } catch (err) {
    toast(err.message, true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  load().catch((err) => toast(err.message, true));
  document.querySelectorAll("#theme-seg [data-theme-choice]").forEach((b) => b.addEventListener("click", () => Theme.set(b.dataset.themeChoice)));
  Theme.apply();
  $("me").addEventListener("change", () => {
    const me = $("me").value;
    const review = Prefs.get("review.filters", null);
    if (review) Prefs.set("review.filters", { ...review, player: me ? `name:${me}` : "" });
    Prefs.set("dashboard.player", "");
    try {
      const practice = JSON.parse(localStorage.getItem("gammon-practice") || "{}");
      practice.player = me;
      localStorage.setItem("gammon-practice", JSON.stringify(practice));
    } catch (_) {}
    save({ me }, me ? t("Showing {name}'s moves by default", { name: me }) : t("Showing both players by default"));
  });
  const saveGrading = () => {
    const body = { preset };
    if (preset === "custom") body.thresholds = Object.fromEntries(["doubtful", "bad", "very_bad"].map((k) => [k, parseFloat($(`t-${k}`).value)]));
    save(body, t("Grading saved. Every match is regraded."));
  };
  document.querySelectorAll("#preset-seg [data-preset]").forEach((b) => b.addEventListener("click", () => {
    setPreset(b.dataset.preset);
    if (presets[b.dataset.preset]) setThresholdInputs(presets[b.dataset.preset]);
    saveGrading();
  }));
  ["doubtful", "bad", "very_bad"].forEach((k) => {
    $(`t-${k}`).addEventListener("input", () => setPreset("custom"));
    $(`t-${k}`).addEventListener("change", saveGrading);
  });
  const saveEngine = () => save({ plies: Number($("plies").value), threads: Number($("threads").value) },
    t("Engine settings saved. Re-analyse to apply them to existing matches."));
  $("plies").addEventListener("change", saveEngine);
  $("threads").addEventListener("change", saveEngine);
  const showText = () => ($("text-value").textContent = `${TextSize.get()}%`);
  $("text-smaller").addEventListener("click", () => TextSize.step(-1));
  $("text-larger").addEventListener("click", () => TextSize.step(1));
  $("text-reset").addEventListener("click", () => TextSize.set(100));
  document.addEventListener("textsizechange", showText);
  showText();
  document.querySelectorAll("#lang-seg [data-lang]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.lang === I18n.lang));
    b.addEventListener("click", () => {
      if (b.dataset.lang === I18n.lang) return;
      I18n.set(b.dataset.lang);
      location.reload();
    });
  });
  const links = [...document.querySelectorAll(".settings nav a")];
  const spy = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) links.forEach((a) => a.classList.toggle("current", a.getAttribute("href") === `#${e.target.id}`));
  }), { rootMargin: "-20% 0px -70% 0px" });
  document.querySelectorAll(".settings section[id]").forEach((el) => spy.observe(el));
  $("reanalyze-all").addEventListener("click", async () => {
    try {
      const { matches } = await api.get("/api/matches");
      await Promise.all(matches.map((m) => api.post(`/api/matches/${m.id}/reanalyze`)));
      toast(t("{matches} queued for analysis", { matches: plural(matches.length, "match") }));
    } catch (err) {
      toast(err.message, true);
    }
  });
  $("watch-interval").addEventListener("change", () => save({ watch_interval: Number($("watch-interval").value) }, t("Check interval saved")));
  if (Native.available) initUpdates();
  document.addEventListener("shellinfo", (ev) => {
    if (ev.detail.engine) $("engine-version").textContent = t("Runs every match again with {engine}", { engine: ev.detail.engine.replace(/ \d{8}$/, "") });
  });
});

async function initUpdates() {
  $("updates").hidden = false;
  $("updates-link").hidden = false;
  const { version } = await Native.call("appInfo");
  $("app-version").textContent = t("VS Gammon {version}", { version });
  $("check-updates").addEventListener("click", async () => {
    $("check-updates").disabled = true;
    try {
      const result = await Native.call("checkUpdate");
      $("update-status").textContent = result.available ? t("Version {version} is available", { version: result.latest }) : t("You have the latest version");
      $("install-update").hidden = !result.available;
    } catch (_) {
      $("update-status").textContent = t("Could not reach the update server. Check your connection.");
    }
    $("check-updates").disabled = false;
  });
  $("install-update").addEventListener("click", async () => {
    $("install-update").disabled = true;
    $("update-status").textContent = t("Downloading the update…");
    const result = await Native.call("installUpdate");
    if (result.ok) return;
    $("install-update").disabled = false;
    $("update-status").textContent = result.reason === "move" ? t("Move VS Gammon to your Applications folder, then try again.") : t("The update could not be installed. Your current version is unchanged.");
  });
  if (location.hash === "#updates") $("check-updates").click();
}

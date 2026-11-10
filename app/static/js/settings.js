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
  $("me").innerHTML = `<option value="">Most frequent player</option>` + players.map((pl) => `<option value="${esc(pl.name)}">${esc(pl.name)} · ${plural(pl.matches, "match", "matches")}</option>`).join("");
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
  $("me").addEventListener("change", () => save({ me: $("me").value }, $("me").value ? `You are ${$("me").value}` : "Using the most frequent player"));
  document.querySelectorAll("#preset-seg [data-preset]").forEach((b) => b.addEventListener("click", () => {
    setPreset(b.dataset.preset);
    if (presets[b.dataset.preset]) setThresholdInputs(presets[b.dataset.preset]);
  }));
  ["doubtful", "bad", "very_bad"].forEach((k) => $(`t-${k}`).addEventListener("input", () => setPreset("custom")));
  $("save-thresholds").addEventListener("click", () => {
    const body = { preset };
    if (preset === "custom") body.thresholds = Object.fromEntries(["doubtful", "bad", "very_bad"].map((k) => [k, parseFloat($(`t-${k}`).value)]));
    save(body, "Grading saved. Every match is regraded.");
  });
  $("save-engine").addEventListener("click", () => save({ plies: Number($("plies").value), threads: Number($("threads").value) },
    "Engine settings saved. Re-analyse to apply them to existing matches."));
  $("reanalyze-all").addEventListener("click", async () => {
    try {
      const { matches } = await api.get("/api/matches");
      await Promise.all(matches.map((m) => api.post(`/api/matches/${m.id}/reanalyze`)));
      toast(`${plural(matches.length, "match", "matches")} queued for analysis`);
    } catch (err) {
      toast(err.message, true);
    }
  });
  $("watch-interval").addEventListener("change", () => save({ watch_interval: Number($("watch-interval").value) }, "Check interval saved"));
  document.addEventListener("shellinfo", (ev) => {
    if (ev.detail.engine) $("engine-version").textContent = `Runs every match again with ${ev.detail.engine.replace(/ \d{8}$/, "")}`;
  });
});

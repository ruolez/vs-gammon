/* Deeper analysis of one decision: deeper evaluation (0–4 ply) or a rollout with every gnubg option.
   Deep.mount(el, decision, onResult) draws the bar under the move; jobs run on the server one at a time. */
const Deep = {
  options: null,
  watching: new Map(),
  PRESETS: ["quick", "standard", "strong"],
  TRIALS: [144, 324, 648, 1296, 2592, 5184],

  async load() {
    if (!this.options) this.options = await api.get("/api/deep/options");
    return this.options;
  },

  presetLabel(name) {
    return { quick: t("Quick"), standard: t("Standard"), strong: t("Strong"), custom: t("Custom") }[name] || name;
  },

  presetNote(name) {
    return {
      quick: t("Plays the games at 0-ply. About 5 s per move."),
      standard: t("Plays the games at 1-ply. About 25 s per move."),
      strong: t("Plays at 2-ply and stops each game after 11 moves to judge it at 2-ply. Several minutes per move."),
      custom: t("Your own settings."),
    }[name];
  },

  rolloutChoice() {
    const saved = Prefs.get("deep.rollout", null) || {};
    const preset = saved.preset && (saved.preset === "custom" || this.PRESETS.includes(saved.preset)) ? saved.preset : "standard";
    const settings = preset === "custom" && saved.custom ? saved.custom : this.options.presets[preset];
    return { preset, settings: structuredClone(settings) };
  },

  evalChoice() {
    return { ...structuredClone(this.options.eval), ...(Prefs.get("deep.eval", null) || {}) };
  },

  defaultMoves(d) {
    if (d.kind !== "checker") return null;
    const ranked = d.candidates.map((c, i) => i).sort((a, b) => d.candidates[b].equity - d.candidates[a].equity);
    const chosen = ranked.slice(0, 3);
    if (!chosen.includes(d.played_index)) chosen.push(d.played_index);
    return chosen.map((i) => d.candidates[i].steps);
  },

  describe(deep) {
    const s = deep.settings;
    if (deep.mode === "eval") return t("Evaluated at {n}-ply", { n: s.checker.plies });
    const parts = [t("Rollout"), plural(s.trials, "game"), t("{n}-ply play", { n: s.checker.plies })];
    if (s.truncation && s.truncation.enabled) parts.push(t("truncated after {n} moves", { n: s.truncation.after }));
    return parts.join(" · ");
  },

  async mount(el, d, onResult) {
    el.innerHTML = "";
    try {
      await this.load();
      const { decision } = await api.get(`/api/decisions/${d.id}`);
      if (!el.isConnected) return;
      this.render(el, { ...d, deep: decision.deep, deep_job: decision.deep_job }, onResult);
    } catch (err) {
      el.innerHTML = `<p class="small muted">${esc(err.message)}</p>`;
    }
  },

  render(el, d, onResult) {
    if (d.deep_job) {
      this.showProgress(el, d.deep_job, d, onResult);
      return;
    }
    const rollout = this.rolloutChoice();
    const current = d.deep ? `<div class="deep-current"><span>${icon("check")}${esc(this.describe(d.deep))}${d.deep.seconds ? ` · ${t("{n} s", { n: Math.round(d.deep.seconds) })}` : ""}</span>
      <button type="button" class="link-btn" data-original>${t("Back to the original analysis")}</button></div>` : "";
    el.innerHTML = `${current}<div class="deep-actions">
        <span class="deep-label">${t("Analyse deeper")}</span>
        <button type="button" class="btn sm secondary" data-eval="3" title="${t("Evaluate the best moves 3 plies deep")}">3-ply</button>
        <button type="button" class="btn sm secondary" data-eval="4" title="${t("Evaluate the best moves 4 plies deep")}">4-ply</button>
        <button type="button" class="btn sm" data-rollout title="${esc(this.presetNote(rollout.preset))}">${icon("play")}${t("Rollout")} · ${esc(this.presetLabel(rollout.preset))}</button>
        <button type="button" class="btn sm ghost icon-only" data-options title="${t("Analysis options")}" aria-label="${t("Analysis options")}">${icon("settings")}</button>
      </div>`;
    const start = async (mode, settings, moves) => {
      try {
        const { job: started } = await api.post(`/api/decisions/${d.id}/deep`, { mode, settings, moves });
        this.render(el, { ...d, deep: null, deep_job: started }, onResult);
      } catch (err) {
        toast(err.message, true);
      }
    };
    el.querySelectorAll("[data-eval]").forEach((b) => b.addEventListener("click", () => {
      const settings = this.evalChoice();
      settings.checker.plies = Number(b.dataset.eval);
      settings.cube.plies = Number(b.dataset.eval);
      start("eval", settings);
    }));
    el.querySelector("[data-rollout]").addEventListener("click", () => start("rollout", rollout.settings, this.defaultMoves(d)));
    el.querySelector("[data-options]").addEventListener("click", () => this.openOptions(d, start));
    el.querySelector("[data-original]")?.addEventListener("click", async () => {
      try {
        await api.del(`/api/decisions/${d.id}/deep`);
        const { decision } = await api.get(`/api/decisions/${d.id}`);
        onResult(decision);
      } catch (err) {
        toast(err.message, true);
      }
    });
  },

  showProgress(el, job, d, onResult) {
    const draw = (current) => {
      el.innerHTML = this.progressHtml(current);
      el.querySelector("[data-cancel]").addEventListener("click", async () => {
        try {
          await api.post(`/api/deep/jobs/${current.id}/cancel`);
        } catch (err) {
          toast(err.message, true);
        }
      });
    };
    draw(job);
    el.dataset.job = String(job.id);
    this.watch(job, (updated) => {
      if (!el.isConnected || el.dataset.job !== String(job.id)) return;
      if (["queued", "running", "cancelling"].includes(updated.status)) {
        draw(updated);
        return;
      }
      delete el.dataset.job;
      this.mount(el, d, onResult);
    }, onResult);
  },

  progressHtml(job) {
    const what = job.mode === "eval" ? t("Evaluating at {n}-ply…", { n: job.settings.checker.plies }) : t("Rolling out…");
    let detail = "";
    let fraction = null;
    if (job.status === "queued") detail = t("Waiting for another analysis to finish");
    else if (job.status === "cancelling") detail = t("Stopping…");
    else if (job.mode === "rollout" && job.total) {
      fraction = job.done / job.total;
      detail = t("{done} of {total} games", { done: job.done.toLocaleString(I18n.locale()), total: job.total.toLocaleString(I18n.locale()) });
      const started = Date.parse(job.started_at);
      if (job.done && !Number.isNaN(started)) {
        const elapsed = (Date.now() - started) / 1000;
        const left = Math.max(0, Math.round(elapsed * (job.total - job.done) / job.done));
        detail += ` · ${t("about {time} left", { time: this.duration(left) })}`;
      }
    } else if (job.mode === "rollout") detail = t("{total} games", { total: job.settings.trials.toLocaleString(I18n.locale()) });
    return `<div class="deep-progress" role="status">
      <div class="deep-progress-head"><strong>${what}</strong><span class="small muted">${detail}</span>
        <button type="button" class="btn sm ghost" data-cancel ${job.status === "cancelling" ? "disabled" : ""}>${t("Cancel")}</button></div>
      <div class="deep-meter ${fraction === null ? "indeterminate" : ""}"><span style="width:${fraction === null ? 30 : Math.max(3, fraction * 100)}%"></span></div>
    </div>`;
  },

  duration(seconds) {
    if (seconds < 60) return t("{n} s", { n: seconds });
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return t("{m} min {s} s", { m: minutes, s: seconds % 60 });
    return t("{h} h {m} min", { h: Math.floor(minutes / 60), m: minutes % 60 });
  },

  watch(job, onUpdate, onResult) {
    const known = this.watching.get(job.id);
    if (known) {
      known.listeners.add(onUpdate);
      return;
    }
    const entry = { listeners: new Set([onUpdate]) };
    this.watching.set(job.id, entry);
    const tick = async () => {
      let current;
      try {
        ({ job: current } = await api.get(`/api/deep/jobs/${job.id}`));
      } catch (_) {
        setTimeout(tick, 3000);
        return;
      }
      const finished = !["queued", "running", "cancelling"].includes(current.status);
      if (finished) {
        this.watching.delete(job.id);
        if (current.status === "done") {
          toast(current.mode === "eval" ? t("Deeper evaluation finished") : t("Rollout finished"));
          try {
            const { decision } = await api.get(`/api/decisions/${current.decision_id}`);
            onResult(decision);
          } catch (_) { /* the page reloads it next time */ }
        } else if (current.status === "error") {
          toast(t("Analysis failed: {reason}", { reason: I18n.server(current.error || "") }), true);
        }
      }
      entry.listeners.forEach((listener) => listener(current));
      if (!finished) setTimeout(tick, current.status === "queued" ? 2000 : 1000);
    };
    setTimeout(tick, 600);
  },

  row(label, controls) {
    return `<div class="do-field"><label>${label}</label><div class="do-inline">${controls}</div></div>`;
  },

  plySelect(name, value) {
    return `<select name="${name}">${[0, 1, 2, 3, 4].map((n) => `<option value="${n}" ${n === value ? "selected" : ""}>${t("{n}-ply", { n })}</option>`).join("")}</select>`;
  },

  check(name, value, label) {
    return `<label class="check"><input type="checkbox" name="${name}" ${value ? "checked" : ""}> ${label}</label>`;
  },

  number(name, value, { step = 1, min = 0, placeholder = "" } = {}) {
    return `<input type="number" name="${name}" value="${value ?? ""}" step="${Number.isInteger(step) ? step : "any"}" min="${min}" placeholder="${esc(placeholder)}">`;
  },

  evalPair(prefix, value) {
    return `${this.plySelect(`${prefix}.plies`, value.plies)}${this.check(`${prefix}.prune`, value.prune, t("Pruning"))}`;
  },

  rolloutForm(s) {
    return `
      <div class="do-field"><label>${t("Games")}</label><div class="do-inline">${this.number("trials", s.trials, { min: 1 })}
        <div class="seg trials">${this.TRIALS.map((n) => `<button type="button" data-trials="${n}" aria-pressed="${n === s.trials}">${n.toLocaleString(I18n.locale())}</button>`).join("")}</div></div></div>
      <div class="do-field"><label>${t("Checker play")}</label><div class="do-inline">${this.evalPair("checker", s.checker)}</div></div>
      <div class="do-field"><label>${t("Cube decisions")}</label><div class="do-inline">${this.evalPair("cube", s.cube)}</div></div>
      <div class="do-field"><label>${t("Options")}</label><div class="do-inline wrap">
        ${this.check("cubeful", s.cubeful, t("Cubeful"))}
        ${this.check("variance_reduction", s.variance_reduction, t("Variance reduction"))}
        ${this.check("quasi_random", s.quasi_random, t("Quasi-random dice"))}
      </div></div>
      <div class="do-field"><label>${t("Seed")}</label><div class="do-inline">${this.number("seed", s.seed, { placeholder: t("Random") })}<span class="small muted">${t("The same seed gives the same dice, so results can be repeated.")}</span></div></div>
      <fieldset class="do-group"><legend>${this.check("truncation.enabled", s.truncation.enabled, t("Truncate"))}</legend>
        ${this.row(t("Stop each game after"), `${this.number("truncation.after", s.truncation.after, { min: 1 })}<span>${t("moves")}</span>`)}
        ${this.row(t("Judge checker play at"), this.evalPair("truncation.checker", s.truncation.checker))}
        ${this.row(t("Judge the cube at"), this.evalPair("truncation.cube", s.truncation.cube))}</fieldset>
      <fieldset class="do-group"><legend>${this.check("later.enabled", s.later.enabled, t("Play later moves at a different depth"))}</legend>
        ${this.row(t("From move"), this.number("later.after", s.later.after, { min: 1 }))}
        ${this.row(t("Checker play"), this.evalPair("later.checker", s.later.checker))}
        ${this.row(t("Cube decisions"), this.evalPair("later.cube", s.later.cube))}</fieldset>
      <fieldset class="do-group"><legend>${t("Bear-off databases (cubeless rollouts)")}</legend>
        <div class="do-inline wrap">${this.check("bearoff.exact", s.bearoff.exact, t("Stop at the exact bear-off database"))}
          ${this.check("bearoff.one_sided", s.bearoff.one_sided, t("Stop at the one-sided bear-off database"))}</div></fieldset>
      <fieldset class="do-group"><legend>${this.check("stop_on_error.enabled", s.stop_on_error.enabled, t("Stop when the result is precise enough"))}</legend>
        ${this.row(t("At least"), `${this.number("stop_on_error.min_games", s.stop_on_error.min_games, { min: 1 })}<span>${t("games")}</span>`)}
        ${this.row(t("Standard error below"), this.number("stop_on_error.max_error", s.stop_on_error.max_error, { step: 0.001, min: 0.0001 }))}</fieldset>
      <fieldset class="do-group"><legend>${this.check("stop_on_jsd.enabled", s.stop_on_jsd.enabled, t("Stop moves that are clearly worse"))}</legend>
        ${this.row(t("At least"), `${this.number("stop_on_jsd.min_games", s.stop_on_jsd.min_games, { min: 1 })}<span>${t("games")}</span>`)}
        ${this.row(t("Behind the best by"), `${this.number("stop_on_jsd.limit", s.stop_on_jsd.limit, { step: 0.01, min: 0.01 })}<span>${t("standard deviations")}</span>`)}</fieldset>
      <p class="small muted">${t("With a stop rule the rollout runs in one go, so there is no progress bar.")}</p>`;
  },

  evalForm(s) {
    return `
      <div class="do-field"><label>${t("Checker play")}</label><div class="do-inline">${this.evalPair("checker", s.checker)}</div></div>
      <div class="do-field"><label>${t("Cube decisions")}</label><div class="do-inline">${this.evalPair("cube", s.cube)}</div></div>
      ${this.row(t("Moves taken deeper"), this.number("moves.count", s.moves.count, { min: 1 }))}
      ${this.row(t("Within"), `${this.number("moves.within", s.moves.within, { step: 0.01, min: 0.01 })}<span>${t("of the best move's equity")}</span>`)}
      <p class="small muted">${t("3-ply takes a second or two; 4-ply about 15 s.")}</p>`;
  },

  movesForm(d, moves) {
    if (d.kind !== "checker") return "";
    const chosen = new Set(moves.map((m) => JSON.stringify(m)));
    return `<fieldset class="do-group"><legend>${t("Moves to roll out")}</legend><div class="do-moves">${d.candidates.map((c, i) => `
      <label class="check"><input type="checkbox" name="move" value="${i}" ${chosen.has(JSON.stringify(c.steps)) ? "checked" : ""}>
        <span class="mv">${esc(c.move)}</span>${i === d.played_index ? `<span class="tag game">${t("played")}</span>` : ""}<span class="small muted">${formatEquity(c.equity)}</span></label>`).join("")}</div></fieldset>`;
  },

  read(form, base) {
    const settings = structuredClone(base);
    form.querySelectorAll("input[name], select[name]").forEach((input) => {
      if (input.name === "move") return;
      const path = input.name.split(".");
      let target = settings;
      path.slice(0, -1).forEach((key) => { target = target[key]; });
      const key = path[path.length - 1];
      if (!(key in target)) return;
      if (input.type === "checkbox") target[key] = input.checked;
      else if (input.name === "seed") target[key] = input.value === "" ? null : Number(input.value);
      else target[key] = Number(input.value);
    });
    return settings;
  },

  openOptions(d, start) {
    const rollout = this.rolloutChoice();
    let preset = rollout.preset;
    let tab = Prefs.get("deep.tab", "rollout");
    const evalSettings = this.evalChoice();
    const moves = this.defaultMoves(d) || [];
    const dialog = document.createElement("dialog");
    dialog.className = "modal deep-options";
    dialog.innerHTML = `<form method="dialog" class="do-form">
      <header><div class="tm-head"><h3>${t("Analyse deeper")}</h3><button type="button" class="btn ghost sm icon-only" data-close aria-label="${t("Close this window")}" title="${t("Close this window")}">${icon("x")}</button></div>
        <div class="seg do-tabs"><button type="button" data-tab="rollout">${t("Rollout")}</button><button type="button" data-tab="eval">${t("Evaluation")}</button></div></header>
      <div class="do-body"></div>
      <footer><button type="button" class="btn ghost" data-close>${t("Cancel")}</button><button type="submit" class="btn" data-start></button></footer>
    </form>`;
    document.body.appendChild(dialog);
    const body = dialog.querySelector(".do-body");
    const close = () => { dialog.close(); dialog.remove(); };

    const draw = (settings) => {
      dialog.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tab === tab)));
      dialog.querySelector("[data-start]").textContent = tab === "rollout" ? t("Start rollout") : t("Evaluate");
      if (tab === "eval") {
        body.innerHTML = this.evalForm(settings || evalSettings);
        return;
      }
      body.innerHTML = `<div class="do-presets">${[...this.PRESETS, "custom"].map((name) => `
          <button type="button" class="do-preset" data-preset="${name}" aria-pressed="${name === preset}"><strong>${esc(this.presetLabel(name))}</strong><span>${esc(this.presetNote(name))}</span></button>`).join("")}</div>
        ${this.movesForm(d, moves)}
        <div class="do-settings">${this.rolloutForm(settings || (preset === "custom" ? rollout.settings : this.options.presets[preset]))}</div>`;
      body.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
        preset = b.dataset.preset;
        const saved = (Prefs.get("deep.rollout", null) || {}).custom;
        draw(preset === "custom" ? (saved || this.read(body, this.options.rollout)) : this.options.presets[preset]);
      }));
      body.querySelectorAll("[data-trials]").forEach((b) => b.addEventListener("click", () => {
        body.querySelector('input[name="trials"]').value = b.dataset.trials;
        body.querySelectorAll("[data-trials]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        markCustom();
      }));
    };
    const markCustom = () => {
      if (preset === "custom") return;
      preset = "custom";
      body.querySelectorAll("[data-preset]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === "custom")));
    };
    body.addEventListener("change", (ev) => { if (tab === "rollout" && ev.target.name !== "move") markCustom(); });
    dialog.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
      tab = b.dataset.tab;
      Prefs.set("deep.tab", tab);
      draw();
    }));
    dialog.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
    dialog.addEventListener("cancel", (ev) => { ev.preventDefault(); close(); });
    dialog.querySelector("form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (tab === "eval") {
        const settings = this.read(body, evalSettings);
        Prefs.set("deep.eval", settings);
        close();
        start("eval", settings);
        return;
      }
      const settings = this.read(body, this.options.rollout);
      Prefs.set("deep.rollout", { preset, custom: preset === "custom" ? settings : (Prefs.get("deep.rollout", null) || {}).custom });
      const picked = [...body.querySelectorAll('input[name="move"]:checked')].map((input) => d.candidates[Number(input.value)].steps);
      if (d.kind === "checker" && !picked.length) {
        toast(t("Choose at least one move to roll out."), true);
        return;
      }
      close();
      start("rollout", settings, d.kind === "checker" ? picked : null);
    });
    draw();
    dialog.showModal();
  },
};

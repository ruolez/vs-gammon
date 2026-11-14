(function () {
  const bar = $("play-bar");
  const input = $("play-url");
  const view = $("play-view");
  const error = $("play-error");
  const buttons = { back: $("play-back"), forward: $("play-forward"), reload: $("play-reload"), home: $("play-home") };
  buttons.back.innerHTML = icon("back");
  buttons.forward.innerHTML = icon("forward");
  buttons.reload.innerHTML = icon("refresh");
  buttons.home.innerHTML = icon("home");

  let address = Prefs.get("play-url", Play.HOME);
  input.value = address;

  function showError(on) {
    error.hidden = !on;
    input.setAttribute("aria-invalid", String(on));
  }
  input.addEventListener("input", () => showError(false));

  if (!Host) {
    $("play-browser").hidden = false;
    bar.classList.add("browser");
    [buttons.back, buttons.forward, buttons.reload].forEach((b) => (b.hidden = true));
    $("play-go").innerHTML = `${icon("external")}<span>${t("Open")}</span>`;
    const openTab = (url) => {
      address = url;
      Prefs.set("play-url", url);
      window.open(url, "_blank", "noopener");
    };
    bar.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const url = Play.webAddress(input.value);
      showError(!url);
      if (url) openTab(url);
    });
    buttons.home.addEventListener("click", () => { input.value = Play.HOME; openTab(Play.HOME); });
    $("play-tab").addEventListener("click", () => openTab(address));
    return;
  }

  const send = (action, args = {}) => Host.call("play", { action, ...args }).catch(() => null);
  const frame = () => ({ rect: Play.viewRect(view.getBoundingClientRect()), scale: window.devicePixelRatio || 1 });
  let loading = false;

  function render(state) {
    if (!state) return;
    loading = Boolean(state.loading);
    buttons.back.disabled = !state.canGoBack;
    buttons.forward.disabled = !state.canGoForward;
    buttons.reload.innerHTML = icon(loading ? "x" : "refresh");
    buttons.reload.title = loading ? t("Stop") : t("Reload");
    buttons.reload.setAttribute("aria-label", buttons.reload.title);
    bar.classList.toggle("loading", loading);
    if (state.url && /^https?:/.test(state.url)) {
      address = state.url;
      Prefs.set("play-url", state.url);
      if (document.activeElement !== input) input.value = state.url;
    }
  }

  function open(url) {
    input.value = url;
    input.blur();
    send("go", { url }).then(render);
  }

  bar.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const url = Play.webAddress(input.value);
    showError(!url);
    if (url) open(url);
  });
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      input.value = address;
      showError(false);
      input.blur();
    }
  });
  input.addEventListener("focus", () => input.select());
  buttons.back.addEventListener("click", () => send("back"));
  buttons.forward.addEventListener("click", () => send("forward"));
  buttons.reload.addEventListener("click", () => send(loading ? "stop" : "reload"));
  buttons.home.addEventListener("click", () => open(Play.HOME));

  document.addEventListener("playstate", (ev) => render(ev.detail));
  document.addEventListener("playopen", (ev) => open(ev.detail));
  const reframe = () => send("frame", frame());
  new ResizeObserver(reframe).observe(view);
  window.addEventListener("resize", reframe);
  window.addEventListener("pagehide", () => send("hide"));
  window.addEventListener("pageshow", (ev) => { if (ev.persisted) send("show", { url: address, ...frame() }).then(render); });
  send("show", { url: address, ...frame() }).then(render);
})();

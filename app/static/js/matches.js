let pollTimer = null;

function counts(s) {
  const n = (k) => s.checker[k] + s.cube[k];
  return ["doubtful", "bad", "very_bad"].map((k) =>
    `<span class="count ${n(k) ? k : "zero"}" title="${SEVERITY_LABEL[k]}">${n(k)}</span>`).join("");
}

function playerLine(m, player) {
  const name = player === 1 ? m.player1 : m.player2;
  const elo = player === 1 ? m.elo1 : m.elo2;
  const s = m.summary && m.summary[player];
  return `<div class="pline">
    <span class="name">${esc(name)}${elo ? `<small>${esc(elo)}</small>` : ""}</span>
    <span class="pr">${s && s.pr !== null ? `PR ${s.pr.toFixed(1)}` : ""}</span>
    <span class="counts" aria-label="${t("doubtful, bad, very bad")}">${s ? counts(s) : ""}</span>
  </div>`;
}

function scoreLine(m) {
  if (!m.games) return "";
  const points = { 1: 0, 2: 0 };
  m.games.forEach((g) => { if (g.winner) points[g.winner] += g.points || 0; });
  return `${points[1]}–${points[2]}`;
}

function statusLabel(m) {
  const text = { queued: t("Queued"), analyzing: t("Analysing"), done: t("Analysed"), error: t("Failed") }[m.status] || m.status;
  return `<span class="status ${m.status}" ${m.error ? `title="${esc(m.error)}"` : ""}>${text}</span>`;
}

function renderMatches(matches) {
  const el = $("matches");
  $("matches-sub").textContent = matches.length
    ? t("{matches} imported. Each one is analysed move by move.", { matches: plural(matches.length, "match") })
    : t("Every match you import is analysed move by move.");
  if (!matches.length) {
    el.innerHTML = `<div class="empty">${icon("matches")}<strong>${t("No matches yet")}</strong><p>${t("Drop a .mat file above, or watch a folder so new downloads are imported automatically.")}</p></div>`;
    return;
  }
  el.innerHTML = `<table class="table stack">
    <thead><tr><th>${t("Date")}</th><th>${t("Match")}</th><th>${t("Players · PR · doubtful / bad / very bad")}</th><th>${t("Status")}</th><th class="num">${t("Actions")}</th></tr></thead>
    <tbody>${matches.map((m) => {
      const source = m.source === "folder" ? t("From {path}", { path: esc((m.source_path || "").replace(/^\/Users\/[^/]+/, "~")) }) : t("Uploaded {file}", { file: esc(m.filename) });
      const length = m.match_length ? t("{n}-point", { n: m.match_length }) : t("Money");
      const games = m.games ? ` · ${plural(m.games.length, "game")}` : "";
      return `<tr>
        <td class="nowrap"><div class="cell-title tabular">${esc(shortDate(m.event_date || m.created_at))}</div><div class="cell-sub">${esc(m.event_time || "")}</div></td>
        <td><div class="cell-title">${length}${games}${m.games ? ` · ${scoreLine(m)}` : ""}</div><div class="cell-sub" title="${esc(m.source_path || m.filename)}">${source}${m.site ? ` · ${esc(m.site)}` : ""}</div></td>
        <td><div class="players">${playerLine(m, 1)}${playerLine(m, 2)}</div></td>
        <td class="nowrap">${statusLabel(m)}${m.plies !== null && m.status === "done" ? `<div class="cell-sub">${m.plies}-ply · ${t("{n} s", { n: m.analysis_seconds })}</div>` : ""}${m.review && m.review.reviewed ? `<div class="cell-sub reviewed">${icon("check")}${t("Reviewed")}</div>` : ""}${m.error ? `<div class="cell-sub status error">${esc(I18n.server(m.error))}</div>` : ""}</td>
        <td><div class="row-actions">
          ${m.status === "done" ? `<a class="btn sm" href="/review?match=${m.id}">${t("Review")}</a><a class="btn sm secondary" href="/practice?match_id=${m.id}">${t("Practise")}</a>` : ""}
          <button class="btn sm ghost icon-only" data-reanalyze="${m.id}" title="${t("Re-analyse")}" aria-label="${t("Re-analyse")}" ${m.status === "analyzing" ? "disabled" : ""}>${icon("refresh")}</button>
          <button class="btn sm ghost icon-only" data-delete="${m.id}" title="${t("Delete")}" aria-label="${t("Delete")}">${icon("trash")}</button>
        </div></td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

function renderWatch(folders) {
  const card = $("watch-card");
  const active = folders.folders.filter((f) => f.enabled);
  if (!folders.available) {
    card.innerHTML = `<span class="t">${icon("folder")}${t("Folder watching is off")}</span><span class="d">${t("Run ./install.sh update once to let the app read your match folders.")}</span>`;
  } else if (active.length) {
    card.innerHTML = `<span class="t">${icon("folder")}${t("Watching {folders}", { folders: plural(active.length, "folder") })}</span>
      <span class="d">${active.map((f) => esc(f.path.replace(/^\/Users\/[^/]+/, "~"))).join(", ")}</span><a class="small" href="/settings#folders">${t("Manage folders")}</a>`;
  } else {
    card.innerHTML = `<span class="t">${icon("folder")}${t("Import automatically")}</span><span class="d">${t("Watch your Downloads folder and new match files are imported and analysed on their own.")}</span><a class="small" href="/settings#folders">${t("Choose a folder")}</a>`;
  }
}

async function refresh() {
  try {
    const [{ matches }, { settings }, folders] = await Promise.all([api.get("/api/matches"), api.get("/api/settings"), api.get("/api/folders")]);
    const t = settings.thresholds;
    $("threshold-note").textContent = window.t("Doubtful ≥ {a} · bad ≥ {b} · very bad ≥ {c}", { a: t.doubtful, b: t.bad, c: t.very_bad });
    renderMatches(matches);
    renderWatch(folders);
    clearTimeout(pollTimer);
    if (matches.some((m) => m.status === "queued" || m.status === "analyzing")) pollTimer = setTimeout(refresh, 1500);
  } catch (err) {
    toast(err.message, true);
  }
}

async function uploadFiles(files) {
  if (!files.length) return;
  const form = new FormData();
  [...files].forEach((f) => form.append("files", f));
  try {
    const { results } = await api.post("/api/matches", form);
    const added = results.filter((r) => r.id && !r.duplicate).length;
    const duplicates = results.filter((r) => r.duplicate).length;
    const failed = results.filter((r) => r.error);
    if (failed.length) toast(failed.map((r) => `${r.filename}: ${I18n.server(r.error)}`).join(" · "), true);
    else toast(duplicates ? t("{matches} queued for analysis, {n} already imported", { matches: plural(added, "match"), n: duplicates }) : t("{matches} queued for analysis", { matches: plural(added, "match") }));
  } catch (err) {
    toast(err.message, true);
  }
  refresh();
  Shell.refresh();
}

document.addEventListener("DOMContentLoaded", () => {
  const zone = $("dropzone");
  const input = $("file-input");
  input.addEventListener("change", () => { uploadFiles(input.files); input.value = ""; });
  ["dragenter", "dragover"].forEach((e) => zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((e) => zone.addEventListener(e, () => zone.classList.remove("over")));
  zone.addEventListener("drop", (ev) => { ev.preventDefault(); uploadFiles(ev.dataTransfer.files); });
  $("matches").addEventListener("click", async (ev) => {
    const re = ev.target.closest("[data-reanalyze]");
    const del = ev.target.closest("[data-delete]");
    try {
      if (re) {
        await api.post(`/api/matches/${re.dataset.reanalyze}/reanalyze`);
        toast(t("Queued for analysis"));
        refresh();
      } else if (del && await confirmDialog({ title: t("Delete this match?"), body: t("Its analysis and practice history are deleted too. This cannot be undone."), action: t("Delete match") })) {
        await api.del(`/api/matches/${del.dataset.delete}`);
        toast(t("Match deleted"));
        refresh();
        Shell.refresh();
      }
    } catch (err) {
      toast(err.message, true);
    }
  });
  refresh();
});

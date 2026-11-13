const KINDS = {
  imported: [t("Imported"), "file"], analysed: [t("Analysed"), "pulse"], analysis_failed: [t("Analysis failed"), "alert"],
  import_failed: [t("Import failed"), "alert"], duplicate: [t("Already imported"), "copy"], reanalysis: [t("Re-analysis requested"), "refresh"],
  exported: [t("Exported"), "download"], deleted: [t("Deleted"), "trash"], folder_added: [t("Watching a folder"), "folder"],
  folder_removed: [t("Stopped watching"), "folder"],
};
let events = [];
let oldest = null;

function dayLabel(at) {
  const date = new Date(at);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  const same = (a, b) => a.toDateString() === b.toDateString();
  if (same(date, today)) return t("Today");
  if (same(date, yesterday)) return t("Yesterday");
  return date.toLocaleDateString(I18n.locale(), { weekday: "long", month: "long", day: "numeric" });
}

function eventRow(e) {
  const [title, ic] = KINDS[e.kind] || [e.kind, "history"];
  const time = new Date(e.at).toLocaleTimeString(I18n.locale(), { hour: "numeric", minute: "2-digit" });
  const link = e.match_id && e.match_status === "done" ? `<a class="btn sm secondary" href="/moves?match=${e.match_id}&min_error=doubtful">${t("Moves")}</a>` : "";
  return `<div class="event"><span class="ic ${esc(e.kind)}">${icon(ic)}</span>
    <div><div class="title">${title}</div><div class="msg">${esc(I18n.server(e.message))}</div></div>
    <div class="time"><span title="${esc(e.at)}">${time}</span>${link}</div></div>`;
}

function render() {
  const el = $("timeline");
  if (!events.length) {
    el.innerHTML = `<div class="empty">${icon("history")}<strong>${t("Nothing here yet")}</strong><p>${t("Imports, analyses and exports will show up here as they happen.")}</p></div>`;
    return;
  }
  let html = "";
  let day = null;
  events.forEach((e) => {
    const label = dayLabel(e.at);
    if (label !== day) {
      html += `<div class="day-head">${label}</div>`;
      day = label;
    }
    html += eventRow(e);
  });
  el.innerHTML = html;
}

async function load(append) {
  const q = new URLSearchParams({ limit: 100 });
  if ($("h-kind").value) q.set("kind", $("h-kind").value);
  if (append && oldest) q.set("before", oldest);
  try {
    const result = await api.get(`/api/history?${q}`);
    events = append ? events.concat(result.events) : result.events;
    if (events.length) oldest = events[events.length - 1].id;
    render();
    $("more").hidden = !result.more;
  } catch (err) {
    toast(err.message, true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const remembered = Prefs.get("history.kind", "");
  if ([...$("h-kind").options].some((o) => o.value === remembered)) $("h-kind").value = remembered;
  $("h-kind").addEventListener("change", () => {
    Prefs.set("history.kind", $("h-kind").value);
    oldest = null;
    load(false);
  });
  $("more").addEventListener("click", () => load(true));
  load(false);
});

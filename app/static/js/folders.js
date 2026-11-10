const Folders = (() => {
  let home = null;
  const short = (p) => p.replace(/^\/Users\/[^/]+/, "~");

  function render(data) {
    home = data.home;
    ["add-folder", "scan-now"].forEach((id) => ($(id).disabled = !data.available));
    const el = $("folder-list");
    if (!data.available) {
      el.innerHTML = `<div class="empty" style="padding:28px">${icon("folder")}<strong>Folder access is off</strong><p>Run <code>./install.sh update</code> once to let the app read your match folders.</p></div>`;
      return;
    }
    if (!data.folders.length) {
      el.innerHTML = `<div class="empty" style="padding:28px">${icon("folder")}<strong>No folders yet</strong><p>Add the folder your match files download to, usually ${esc(short(home))}/Downloads.</p></div>`;
      return;
    }
    el.innerHTML = data.folders.map((f) => `
      <div class="folder">
        <span class="ic">${icon("folder")}</span>
        <div><div class="path">${esc(short(f.path))}</div>
          <div class="meta">${f.last_scan_at ? `Checked ${new Date(f.last_scan_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}` : "Not checked yet"}${f.last_error ? ` · <span class="err">${esc(f.last_error)}</span>` : ""}</div></div>
        <div class="opts">
          <label class="check"><input type="checkbox" data-recursive="${f.id}" ${f.recursive ? "checked" : ""}> Subfolders</label>
          <label class="check"><input type="checkbox" data-enabled="${f.id}" ${f.enabled ? "checked" : ""}> Active</label>
          <button class="btn sm ghost icon-only" data-remove="${f.id}" title="Stop watching" aria-label="Stop watching ${esc(short(f.path))}">${icon("trash")}</button>
        </div>
      </div>`).join("");
  }

  const refresh = async () => render(await api.get("/api/folders"));

  async function browse(path) {
    let listing;
    try {
      listing = await api.get(`/api/fs?path=${encodeURIComponent(path || home)}`);
    } catch (err) {
      toast(err.message, true);
      return;
    }
    const dialog = $("folder-dialog");
    const shortcuts = [["Home", home], ["Downloads", `${home}/Downloads`], ["Desktop", `${home}/Desktop`], ["Documents", `${home}/Documents`]]
      .map(([label, p]) => `<button class="btn sm secondary" data-go="${esc(p)}">${label}</button>`).join("");
    dialog.innerHTML = `
      <header><h3 id="folder-dialog-title">Choose a folder to watch</h3><div class="path">${esc(listing.path)}</div><div class="shortcuts">${shortcuts}</div></header>
      <div class="dir-list">
        ${listing.parent ? `<button class="dir" data-go="${esc(listing.parent)}">${icon("back")}<span>Up one level</span></button>` : ""}
        ${listing.dirs.map((d) => `<button class="dir" data-go="${esc(d.path)}">${icon("folder")}<span>${esc(d.name)}</span></button>`).join("") || '<div class="empty small"><p>No subfolders here</p></div>'}
      </div>
      <footer><span class="small muted">${plural(listing.match_files, ".mat file")} in this folder</span>
        <label class="check"><input type="checkbox" id="modal-recursive"> Include subfolders</label>
        <span class="spacer"></span>
        <button class="btn ghost" id="modal-cancel">Cancel</button>
        <button class="btn" id="modal-choose">Watch this folder</button></footer>`;
    dialog.querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => browse(el.dataset.go)));
    $("modal-cancel").addEventListener("click", () => dialog.close());
    $("modal-choose").addEventListener("click", async () => {
      try {
        const data = await api.post("/api/folders", { path: listing.path, recursive: $("modal-recursive").checked });
        dialog.close();
        render({ available: true, home, folders: data.folders });
        toast(`Watching ${short(listing.path)}. Match files already there are imported now.`);
        Shell.refresh();
        setTimeout(refresh, 3000);
      } catch (err) {
        toast(err.message, true);
      }
    });
    if (!dialog.open) dialog.showModal();
    dialog.querySelector(".dir")?.focus();
  }

  function init() {
    $("add-folder").addEventListener("click", () => browse(`${home}/Downloads`));
    $("folder-dialog").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) ev.currentTarget.close(); });
    $("scan-now").addEventListener("click", async () => {
      try {
        await api.post("/api/folders/scan");
        toast("Checking watched folders…");
        setTimeout(() => { refresh(); Shell.refresh(); }, 2500);
      } catch (err) {
        toast(err.message, true);
      }
    });
    $("folder-list").addEventListener("change", async (ev) => {
      const id = ev.target.dataset.recursive || ev.target.dataset.enabled;
      if (!id) return;
      const key = ev.target.dataset.recursive ? "recursive" : "enabled";
      try {
        render({ available: true, home, folders: (await api.patch(`/api/folders/${id}`, { [key]: ev.target.checked })).folders });
        Shell.refresh();
      } catch (err) {
        toast(err.message, true);
      }
    });
    $("folder-list").addEventListener("click", async (ev) => {
      const remove = ev.target.closest("[data-remove]");
      if (!remove) return;
      try {
        render({ available: true, home, folders: (await api.del(`/api/folders/${remove.dataset.remove}`)).folders });
        Shell.refresh();
      } catch (err) {
        toast(err.message, true);
      }
    });
    refresh().catch((err) => toast(err.message, true));
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", Folders.init);

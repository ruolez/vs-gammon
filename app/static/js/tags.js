const Tags = {
  COLORS: ["blue", "green", "yellow", "orange", "red", "purple", "pink", "slate"],
  list: [],
  picker: null,

  async load() {
    const { tags } = await api.get("/api/tags");
    this.update(tags);
    return tags;
  },

  update(tags) {
    this.list = tags;
    document.dispatchEvent(new CustomEvent("tagschange"));
  },

  byId(id) {
    return this.list.find((tag) => tag.id === id);
  },

  chip(tag) {
    return `<span class="tag-chip" data-color="${tag.color}"><i class="tag-dot"></i>${esc(tag.name)}</span>`;
  },

  chips(ids) {
    return (ids || []).map((id) => this.byId(id)).filter(Boolean).map((tag) => this.chip(tag)).join("");
  },

  nextColor() {
    return this.COLORS[this.list.length % this.COLORS.length];
  },

  async apply(tagId, decisions, on) {
    const ids = decisions.map((d) => d.id);
    const { tags } = await api.post(`/api/tags/${tagId}/decisions`, on ? { add: ids } : { remove: ids });
    decisions.forEach((d) => {
      const set = new Set(d.tags || []);
      on ? set.add(tagId) : set.delete(tagId);
      d.tags = [...set].sort((a, b) => a - b);
    });
    this.update(tags);
  },

  async create(name, color) {
    const { tag, tags } = await api.post("/api/tags", { name, color });
    this.update(tags);
    return tag;
  },

  closePicker() {
    if (!this.picker) return;
    this.picker.close();
    this.picker = null;
  },

  openPicker(anchor, decisions, onChange) {
    this.closePicker();
    const pop = document.createElement("div");
    pop.className = "tag-picker";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", t("Tags"));
    pop.innerHTML = `<input type="text" class="tp-search" maxlength="40" placeholder="${t("Find or create a tag")}" aria-label="${t("Find or create a tag")}">
      <div class="tp-list"></div>
      <div class="tp-foot">${t("Applies to {positions}", { positions: plural(decisions.length, "position") })}</div>`;
    document.body.appendChild(pop);
    const input = pop.querySelector(".tp-search");
    const listEl = pop.querySelector(".tp-list");

    const query = () => input.value.trim().replace(/\s+/g, " ");
    const matching = () => this.list.filter((tag) => tag.name.toLowerCase().includes(query().toLowerCase()));
    const canCreate = () => query() && !this.list.some((tag) => tag.name.toLowerCase() === query().toLowerCase());
    const changed = () => { render(); if (onChange) onChange(); };

    const render = () => {
      const tags = matching();
      listEl.innerHTML = tags.map((tag) => {
        const have = decisions.filter((d) => (d.tags || []).includes(tag.id)).length;
        return `<label class="tp-row"><input type="checkbox" data-tag="${tag.id}" data-have="${have}" ${have === decisions.length ? "checked" : ""}>${this.chip(tag)}</label>`;
      }).join("")
        + (canCreate() ? `<button type="button" class="tp-create" data-create>${icon("plus")}${t("Create “{name}”", { name: esc(query()) })}</button>` : "")
        + (!tags.length && !canCreate() ? `<p class="tp-empty">${t("No tags yet. Type a name to create one.")}</p>` : "");
      listEl.querySelectorAll("[data-have]").forEach((box) => {
        const have = Number(box.dataset.have);
        box.indeterminate = have > 0 && have < decisions.length;
      });
    };

    const createFromQuery = async () => {
      try {
        const tag = await this.create(query(), this.nextColor());
        await this.apply(tag.id, decisions, true);
        input.value = "";
        changed();
        input.focus();
      } catch (err) {
        toast(err.message, true);
      }
    };

    listEl.addEventListener("change", async (ev) => {
      const box = ev.target.closest("[data-tag]");
      if (!box) return;
      try {
        await this.apply(Number(box.dataset.tag), decisions, box.checked);
        changed();
        listEl.querySelector(`[data-tag="${box.dataset.tag}"]`)?.focus();
      } catch (err) {
        toast(err.message, true);
        render();
      }
    });
    listEl.addEventListener("click", (ev) => { if (ev.target.closest("[data-create]")) createFromQuery(); });
    input.addEventListener("input", render);
    input.addEventListener("keydown", async (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      if (canCreate()) return createFromQuery();
      const tags = matching();
      if (tags.length === 1) {
        const on = !decisions.every((d) => (d.tags || []).includes(tags[0].id));
        try {
          await this.apply(tags[0].id, decisions, on);
          changed();
        } catch (err) {
          toast(err.message, true);
        }
      }
    });

    const place = () => {
      const rect = anchor.getBoundingClientRect();
      const width = pop.offsetWidth;
      const left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
      const below = rect.bottom + 6;
      const top = below + pop.offsetHeight > window.innerHeight - 8 ? Math.max(8, rect.top - pop.offsetHeight - 6) : below;
      pop.style.left = `${left + window.scrollX}px`;
      pop.style.top = `${top + window.scrollY}px`;
    };
    const outside = (ev) => {
      const path = ev.composedPath();
      if (!path.includes(pop) && !path.includes(anchor)) this.closePicker();
    };
    const keys = (ev) => {
      if (ev.key === "Escape") {
        ev.stopPropagation();
        this.closePicker();
        anchor.focus();
      }
    };
    pop.addEventListener("keydown", keys);
    document.addEventListener("mousedown", outside, true);
    window.addEventListener("resize", place);
    anchor.setAttribute("aria-expanded", "true");
    this.picker = {
      anchor,
      close: () => {
        document.removeEventListener("mousedown", outside, true);
        window.removeEventListener("resize", place);
        anchor.setAttribute("aria-expanded", "false");
        pop.remove();
      },
    };
    render();
    place();
    input.focus();
  },

  togglePicker(anchor, decisions, onChange) {
    if (this.picker && this.picker.anchor === anchor) return this.closePicker();
    this.openPicker(anchor, decisions, onChange);
  },

  mountLine(line, d, onChange) {
    if (line.dataset.id !== String(d.id)) {
      line.dataset.id = d.id;
      line.innerHTML = `<span class="tag-chips"></span><button type="button" class="btn ghost sm tag-btn" aria-haspopup="dialog" aria-expanded="false" title="${t("Tags")}">${icon("tag")}<span></span></button>`;
      const button = line.querySelector(".tag-btn");
      button.addEventListener("click", () => this.togglePicker(button, [d], onChange));
    }
    line.querySelector(".tag-chips").innerHTML = this.chips(d.tags);
    line.querySelector(".tag-btn span").textContent = d.tags && d.tags.length ? t("Edit tags") : t("Add tag");
  },

  swatches(name, selected) {
    return `<div class="swatches" role="radiogroup" aria-label="${t("Colour")}">${this.COLORS.map((color) =>
      `<label class="swatch-pick" title="${t(color)}"><input type="radio" name="${name}" value="${color}" ${color === selected ? "checked" : ""}><i class="tag-dot" data-color="${color}"></i><span class="sr-only">${t(color)}</span></label>`).join("")}</div>`;
  },

  async openManager(onChange) {
    try {
      await this.load();
    } catch (err) {
      return toast(err.message, true);
    }
    const dialog = document.createElement("dialog");
    dialog.className = "modal tag-manager";
    dialog.innerHTML = `<div class="body">
        <div class="tm-head"><h3>${t("Manage tags")}</h3><button type="button" class="btn ghost sm icon-only" data-close aria-label="${t("Close the tag manager")}" title="${t("Close the tag manager")}">${icon("x")}</button></div>
        <form class="tm-new">
          <input type="text" name="name" maxlength="40" placeholder="${t("New tag name")}" aria-label="${t("New tag name")}" required>
          ${this.swatches("new-color", this.nextColor())}
          <button class="btn" type="submit">${icon("plus")}${t("Add tag")}</button>
        </form>
        <div class="tm-list"></div>
      </div>`;
    document.body.appendChild(dialog);
    const listEl = dialog.querySelector(".tm-list");
    const form = dialog.querySelector(".tm-new");
    let editing = null;

    const changed = (tags) => {
      this.update(tags);
      render();
      if (onChange) onChange();
    };

    const render = () => {
      if (!this.list.length) {
        listEl.innerHTML = `<p class="tm-empty">${t("No tags yet. Add one above, or tag positions straight from the list.")}</p>`;
        return;
      }
      listEl.innerHTML = this.list.map((tag) => `
        <div class="tm-row" data-id="${tag.id}">
          <button type="button" class="tm-color" data-edit-color aria-expanded="${editing === tag.id}" title="${t("Change colour")}" aria-label="${t("Change colour")}"><i class="tag-dot" data-color="${tag.color}"></i></button>
          <input type="text" class="tm-name" value="${esc(tag.name)}" maxlength="40" aria-label="${t("Tag name")}">
          <span class="tm-count">${plural(tag.count, "position")}</span>
          <select class="tm-merge" aria-label="${t("Merge into another tag")}" ${this.list.length > 1 ? "" : "disabled"}>
            <option value="">${t("Merge into…")}</option>${this.list.filter((o) => o.id !== tag.id).map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}
          </select>
          <button type="button" class="btn ghost sm icon-only" data-delete title="${t("Delete tag")}" aria-label="${t("Delete tag")}">${icon("trash")}</button>
          ${editing === tag.id ? `<div class="tm-swatches">${this.swatches(`color-${tag.id}`, tag.color)}</div>` : ""}
        </div>`).join("");
    };

    const run = async (work) => {
      try {
        changed(await work());
      } catch (err) {
        toast(err.message, true);
        render();
      }
    };

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const name = form.elements.name.value;
      const color = form.querySelector('input[name="new-color"]:checked').value;
      await run(async () => (await api.post("/api/tags", { name, color })).tags);
      form.elements.name.value = "";
      form.querySelector(".swatches").outerHTML = this.swatches("new-color", this.nextColor());
      form.elements.name.focus();
    });
    listEl.addEventListener("click", async (ev) => {
      const row = ev.target.closest(".tm-row");
      if (!row) return;
      const tag = this.byId(Number(row.dataset.id));
      if (ev.target.closest("[data-edit-color]")) {
        editing = editing === tag.id ? null : tag.id;
        render();
        listEl.querySelector(`.tm-row[data-id="${tag.id}"] [data-edit-color]`).focus();
      } else if (ev.target.closest("[data-delete]")) {
        const body = tag.count
          ? t("It is removed from {positions}. The positions themselves stay.", { positions: plural(tag.count, "position") })
          : t("No positions have this tag.");
        if (await confirmDialog({ title: t("Delete the tag “{name}”?", { name: tag.name }), body, action: t("Delete tag") })) {
          await run(async () => (await api.del(`/api/tags/${tag.id}`)).tags);
        }
      }
    });
    listEl.addEventListener("change", async (ev) => {
      const row = ev.target.closest(".tm-row");
      if (!row) return;
      const tag = this.byId(Number(row.dataset.id));
      if (ev.target.matches(".tm-name")) {
        await run(async () => (await api.patch(`/api/tags/${tag.id}`, { name: ev.target.value })).tags);
      } else if (ev.target.matches('input[type="radio"]')) {
        editing = null;
        await run(async () => (await api.patch(`/api/tags/${tag.id}`, { color: ev.target.value })).tags);
      } else if (ev.target.matches(".tm-merge") && ev.target.value) {
        const target = this.byId(Number(ev.target.value));
        const ok = await confirmDialog({
          title: t("Merge “{from}” into “{to}”?", { from: tag.name, to: target.name }),
          body: t("Its positions get the tag “{to}” and “{from}” is deleted.", { from: tag.name, to: target.name }),
          action: t("Merge"),
        });
        if (ok) await run(async () => (await api.post(`/api/tags/${tag.id}/merge`, { into: target.id })).tags);
        else render();
      }
    });
    listEl.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && ev.target.matches(".tm-name")) {
        ev.preventDefault();
        ev.target.blur();
      }
    });
    dialog.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-close]") || ev.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => dialog.remove());
    render();
    dialog.showModal();
    form.elements.name.focus();
  },
};

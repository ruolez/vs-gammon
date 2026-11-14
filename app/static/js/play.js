(function (root) {
  function webAddress(input) {
    const text = String(input ?? "").trim();
    if (!text || /\s/.test(text)) return null;
    const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(text) && !/^[^/:]+:\d+(\/|$)/.test(text);
    if (hasScheme && !/^https?:\/\//i.test(text)) return null;
    if (!hasScheme && !/^(localhost|[^/?#]*\.[^/?#]+)(:\d+)?([/?#]|$)/i.test(text)) return null;
    try {
      const url = new URL(hasScheme ? text : `https://${text}`);
      return url.hostname ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function viewRect(box) {
    const x = Math.max(0, Math.round(box.left));
    const y = Math.max(0, Math.round(box.top));
    return { x, y, width: Math.max(0, Math.round(box.left + box.width) - x), height: Math.max(0, Math.round(box.top + box.height) - y) };
  }

  const Play = { webAddress, viewRect, HOME: "https://backgammongalaxy.com/" };
  if (typeof module !== "undefined" && module.exports) module.exports = Play;
  else root.Play = Play;
})(this);

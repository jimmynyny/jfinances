(() => {
  const vw = innerWidth;
  const out = { hscroll: document.documentElement.scrollWidth > vw + 1 ? document.documentElement.scrollWidth : 0,
                clipped: [], cut: [], overflow: [], spill: [], collisions: [], touching: [] };
  const cs = (el) => getComputedStyle(el);
  const visible = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const s = cs(e);
      if (s.display === "none" || s.visibility === "hidden" || parseFloat(s.opacity) < 0.05) return false;
    }
    return true;
  };
  const closedSide = document.querySelector(".mu-side:not([data-open])");
  const overlay = document.querySelector(".mu-drawer") || document.querySelector(".mu-side[data-open]");
  // With a sheet or the menu open, only what is on it counts: the page under it is covered.
  const offstage = (el) => (closedSide && closedSide.contains(el)) || (overlay && !overlay.contains(el));
  const label = (el) => {
    const c = (el.getAttribute("class") || "").toString().trim().split(/\s+/).filter(Boolean).slice(0, 2).join(".");
    return el.tagName.toLowerCase() + (c ? "." + c : "");
  };
  const path = (el) => { const p = []; for (let e = el, i = 0; e && e !== document.body && i < 4; e = e.parentElement, i++) p.unshift(label(e)); return p.join(" > "); };
  const Y = (r) => Math.round(r.top + scrollY);
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  const clipsX = (s) => s.overflowX === "hidden" || s.overflowX === "clip";
  const clipsY = (s) => s.overflowY === "hidden" || s.overflowY === "clip";

  // 1. elements that cut off their own text (ellipsis, overflow hidden, line clamp)
  for (const el of document.querySelectorAll("body *")) {
    if (offstage(el) || el.closest("svg")) continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) continue;
    const s = cs(el);
    if (!(el.innerText || "").trim()) continue;
    if ((clipsX(s) || s.textOverflow === "ellipsis") && el.scrollWidth > el.clientWidth + 1 && visible(el))
      out.clipped.push({ el: path(el), text: el.innerText.trim().slice(0, 70), has: el.clientWidth, needs: el.scrollWidth, y: Y(r) });
    else if (clipsY(s) && el.scrollHeight > el.clientHeight + 2 && ownText(el) && visible(el))
      out.clipped.push({ el: path(el), text: el.innerText.trim().slice(0, 70), hasH: el.clientHeight, needsH: el.scrollHeight, y: Y(r) });
  }

  // 2. text runs
  const runs = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode()); ) {
    const t = n.textContent.trim();
    if (!t) continue;
    const el = n.parentElement;
    if (!el || offstage(el) || !visible(el)) continue;
    const range = document.createRange();
    // measure the ink, not the spaces around it
    const raw = n.textContent, lead = raw.length - raw.trimStart().length, trail = raw.length - raw.trimEnd().length;
    range.setStart(n, lead);
    range.setEnd(n, raw.length - trail);
    for (const rr of range.getClientRects()) {
      if (rr.width < 2 || rr.height < 2) continue;
      runs.push({ el, text: t.slice(0, 40), x1: rr.left, y1: rr.top, x2: rr.right, y2: rr.bottom });
    }
  }
  const blockOf = (el) => { for (let e = el; e; e = e.parentElement) { const d = cs(e).display; if (d !== "inline" && d !== "contents") return e; } return document.body; };
  const scrollerOf = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const s = cs(e); if ((s.overflowX === "auto" || s.overflowX === "scroll") && e.scrollWidth > e.clientWidth + 1) return e; } return null; };
  const clipperOf = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { if (clipsX(cs(e))) return e; } return null; };

  for (const r of runs) {
    // beyond the screen, not inside a horizontal scroller
    if ((r.x2 > vw + 1 || r.x1 < -1) && !scrollerOf(r.el))
      out.overflow.push({ el: path(r.el), text: r.text, left: Math.round(r.x1), right: Math.round(r.x2), y: Math.round(r.y1 + scrollY) });
    // cut by an ancestor that hides overflow
    const c = clipperOf(r.el);
    if (c) { const cr = c.getBoundingClientRect(); if (r.x2 > cr.right + 1 || r.x1 < cr.left - 1) out.cut.push({ el: path(r.el), by: label(c), text: r.text, y: Math.round(r.y1 + scrollY) }); }
    // spilling past its panel
    const panel = r.el.closest(".mu-panel");
    if (panel && !scrollerOf(r.el)) { const pr = panel.getBoundingClientRect(); if (r.x2 > pr.right + 1 || r.x1 < pr.left - 1) out.spill.push({ el: path(r.el), text: r.text, y: Math.round(r.y1 + scrollY) }); }
  }

  // 3. overlapping and touching text from different elements
  runs.sort((a, b) => a.y1 - b.y1);
  for (let i = 0; i < runs.length; i++) {
    const a = runs[i];
    for (let j = i + 1; j < runs.length; j++) {
      const b = runs[j];
      if (b.y1 >= a.y2) break;
      if (a.el === b.el) continue;
      // text inside text of the same line box flows together; a nested block (inline-block, flex item) does not
      if ((a.el.contains(b.el) || b.el.contains(a.el)) && blockOf(a.el) === blockOf(b.el)) continue;
      const ix = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
      const iy = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
      const hMin = Math.min(a.y2 - a.y1, b.y2 - b.y1);
      if (iy <= 0.3 * hMin) continue;
      if (ix > 1) {
        const area = ix * iy, minArea = Math.min((a.x2 - a.x1) * (a.y2 - a.y1), (b.x2 - b.x1) * (b.y2 - b.y1));
        if (area / minArea >= 0.1) out.collisions.push({ a: a.text, b: b.text, ael: path(a.el), bel: path(b.el), y: Math.round(Math.max(a.y1, b.y1) + scrollY) });
      } else if (ix > -3 && iy > 0.5 * hMin && blockOf(a.el) !== blockOf(b.el)) {
        out.touching.push({ a: a.text, b: b.text, gap: +(-ix).toFixed(1), ael: path(a.el), bel: path(b.el), y: Math.round(Math.max(a.y1, b.y1) + scrollY) });
      }
    }
  }
  return out;
})()

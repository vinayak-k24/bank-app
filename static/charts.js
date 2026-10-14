/* Minimal dependency-free SVG charts (works offline). */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, parent) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function frame(container) {
    container.innerHTML = "";
    const w = container.clientWidth || 800, h = container.clientHeight || 280;
    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none" }, container);
    return { svg, w, h, pad: { l: 52, r: 16, t: 14, b: 28 } };
  }
  function axes(f, yMin, yMax, labels, fmt) {
    const { svg, w, h, pad } = f;
    const ih = h - pad.t - pad.b;
    for (let i = 0; i <= 4; i++) {
      const v = yMin + (yMax - yMin) * i / 4, y = pad.t + ih - ih * i / 4;
      el("line", { x1: pad.l, x2: w - pad.r, y1: y, y2: y, stroke: "#eef0f3" }, svg);
      el("text", { x: pad.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "#98a2b3" }, svg).textContent = fmt(v);
    }
    const step = Math.max(1, Math.ceil(labels.length / 8));
    labels.forEach((lab, i) => {
      if (i % step) return;
      el("text", { x: xAt(f, i, labels.length), y: h - 8, "text-anchor": "middle", "font-size": 11, fill: "#98a2b3" }, svg).textContent = lab;
    });
  }
  function xAt(f, i, n) { return f.pad.l + (f.w - f.pad.l - f.pad.r) * (n === 1 ? 0.5 : i / (n - 1)); }
  function yAt(f, v, yMin, yMax) { const ih = f.h - f.pad.t - f.pad.b; return f.pad.t + ih - ih * (v - yMin) / (yMax - yMin || 1); }
  function path(pts) { return pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" "); }

  window.Charts = {
    /* series: [{label, exposure_k, savings_k}], interventions: [{index, label, savings_usd}] */
    savings(container, series, interventions) {
      const f = frame(container);
      f.pad.t = 34;
      const max = Math.max(...series.map(s => Math.max(s.exposure_k, s.savings_k))) * 1.12;
      axes(f, 0, max, series.map(s => s.label), v => "$" + Math.round(v) + "k");
      const n = series.length, base = yAt(f, 0, 0, max);
      [["exposure_k", "#fca5a5", "rgba(252,165,165,.25)"], ["savings_k", "#7c3aed", "rgba(124,58,237,.14)"]].forEach(([key, stroke, fill]) => {
        const pts = series.map((s, i) => [xAt(f, i, n), yAt(f, s[key], 0, max)]);
        el("path", { d: path(pts) + ` L${pts[n - 1][0]},${base} L${pts[0][0]},${base} Z`, fill }, f.svg);
        el("path", { d: path(pts), fill: "none", stroke, "stroke-width": 2.5 }, f.svg);
      });
      const perIndex = {};
      (interventions || []).forEach(iv => {
        const i = Math.max(0, Math.min(n - 1, iv.index));
        const k = perIndex[i] = (perIndex[i] || 0) + 1;
        const x = xAt(f, i, n), y = yAt(f, series[i].savings_k, 0, max);
        el("circle", { cx: x, cy: y, r: 6, fill: "#16a34a", stroke: "#fff", "stroke-width": 2 }, f.svg);
        const anchor = x > f.w * 0.75 ? "end" : "middle";
        const t = el("text", { x: anchor === "end" ? x - 8 : x, y: y - 12 - (k - 1) * 14, "text-anchor": anchor, "font-size": 11, "font-weight": 700, fill: "#065f46" }, f.svg);
        t.textContent = "✓ " + iv.label + " (-$" + Math.round(iv.savings_usd / 1000) + "K)";
      });
    },
    /* segments: [[label, pct, color]] */
    donut(svgHost, segments, center, caption) {
      const r = 46, c = 2 * Math.PI * r;
      let off = 0;
      const rings = segments.map(([, pct, color]) => {
        const len = c * pct / 100, s = `<circle cx="60" cy="60" r="${r}" fill="none" stroke="${color}" stroke-width="12" stroke-dasharray="${len.toFixed(1)} ${c.toFixed(1)}" stroke-dashoffset="${(-off).toFixed(1)}" transform="rotate(-90 60 60)"/>`;
        off += len; return s;
      }).join("");
      svgHost.innerHTML = `<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="${r}" fill="none" stroke="#eef0f3" stroke-width="12"/>${rings}
        <text x="60" y="58" text-anchor="middle" font-size="18" font-weight="800" fill="#101828"></text><text x="60" y="72" text-anchor="middle" font-size="8.5" font-weight="600" fill="#667085"></text></svg>`;
      const texts = svgHost.querySelectorAll("text");
      texts[0].textContent = center; texts[1].textContent = String(caption).toUpperCase();
    },
    /* values: numbers -> polyline in a 120x28 box */
    spark(svgEl, values, color) {
      const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
      const pts = values.map((v, i) => `${(2 + i * 116 / (values.length - 1)).toFixed(1)},${(25 - (v - lo) / span * 22).toFixed(1)}`).join(" ");
      svgEl.innerHTML = `<polyline fill="none" stroke="${color}" stroke-width="2" points="${pts}"/>`;
    },
    /* history/forecast: [{date, balance_usd}], threshold: number */
    forecast(container, history, forecast, threshold) {
      const f = frame(container);
      const all = history.concat(forecast);
      const vals = all.map(p => p.balance_usd).concat([threshold, 0]);
      let lo = Math.min(...vals), hi = Math.max(...vals);
      const padv = (hi - lo) * 0.1 || 500; lo -= padv; hi += padv;
      const labels = all.map(p => p.date.slice(5));
      axes(f, lo, hi, labels, v => (v < 0 ? "-$" : "$") + Math.abs(v / 1000).toFixed(1) + "k");
      const n = all.length;
      const ty = yAt(f, threshold, lo, hi), by = yAt(f, lo, lo, hi);
      el("rect", { x: f.pad.l, y: ty, width: f.w - f.pad.l - f.pad.r, height: Math.max(0, by - ty), fill: "rgba(220,38,38,.07)" }, f.svg);
      el("line", { x1: f.pad.l, x2: f.w - f.pad.r, y1: ty, y2: ty, stroke: "#dc2626", "stroke-dasharray": "4 4" }, f.svg);
      const hp = history.map((p, i) => [xAt(f, i, n), yAt(f, p.balance_usd, lo, hi)]);
      el("path", { d: path(hp), fill: "none", stroke: "#2563eb", "stroke-width": 2.5 }, f.svg);
      const fp = [hp[hp.length - 1]].concat(forecast.map((p, i) => [xAt(f, history.length + i, n), yAt(f, p.balance_usd, lo, hi)]));
      const fl = el("path", { d: path(fp), fill: "none", stroke: "#7c3aed", "stroke-width": 2.5, "stroke-dasharray": "6 4" }, f.svg);
      const len = fl.getTotalLength ? fl.getTotalLength() : 0;
      if (len) { fl.style.transition = "none"; fl.style.strokeDashoffset = len; fl.getBoundingClientRect(); fl.style.transition = "stroke-dashoffset .8s ease"; fl.style.strokeDashoffset = 0; }
      const low = forecast.findIndex(p => p.balance_usd < threshold);
      if (low >= 0) {
        const [x, y] = fp[low + 1];
        el("circle", { cx: x, cy: y, r: 6, fill: "#dc2626", stroke: "#fff", "stroke-width": 2 }, f.svg);
        const t = el("text", { x: Math.min(x + 8, f.w - 120), y: y - 10, "font-size": 12, "font-weight": 600, fill: "#dc2626" }, f.svg);
        t.textContent = "Dips low " + forecast[low].date.slice(5);
      }
    },
  };
})();

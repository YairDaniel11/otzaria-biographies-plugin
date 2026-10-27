/* ===========================================================================
 *  rb-timeline.js — "ציר הדורות": רכיב SVG אינטראקטיבי (בלי ספריות חיצוניות)
 *  - עקומת צפיפות חלקה, צבועה לפי תקופות (צבעים מ-CSS: --era-*)
 *  - בחירת טווח במברשת עם ידיות (עכבר / מגע / מקלדת), זום, גרירת הציר
 *  - ציוני דרך לחיצים, שנה עברית ולועזית, tooltip עם דוגמאות
 *  עובד על מערכי סיכום בלבד (Int32Array של ספירה לכל שנה) — לא על DOM לכל רשומה.
 *  ציר הזמן זורם מימין לשמאל (העתיק מימין) — כמו כיוון הקריאה בעברית.
 * ========================================================================= */
(function () {
  'use strict';
  var FULL0 = 750, FULL1 = 2030, YMAX = 2100;
  var uid = 0;

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function num(n) { return Number(n).toLocaleString('he'); }

  /* טשטוש קופסה (3 מעברים ~ גאוסיאן) על מערך שנים */
  function smooth(src, r) {
    var n = src.length, a = new Float32Array(n), b = new Float32Array(n), i, p, k = 2 * r + 1;
    for (i = 0; i < n; i++) a[i] = src[i];
    for (p = 0; p < 3; p++) {
      var acc = 0;
      for (i = -r; i <= r; i++) acc += a[clamp(i, 0, n - 1)];
      for (i = 0; i < n; i++) {
        b[i] = acc / k;
        acc += a[clamp(i + r + 1, 0, n - 1)] - a[clamp(i - r, 0, n - 1)];
      }
      var t = a; a = b; b = t;
    }
    return a;
  }

  function create(host, o) {
    var id = 'rbt' + (++uid);
    var eras = o.eras || [], gm = o.gm || String;
    var landmarks = [];
    var hist = null, histAll = null;
    var d0 = FULL0, d1 = FULL1;
    var sel = null;             // {lo,hi} — hi לא כולל
    var cur = 0;                // שנת הרב הפתוח בכרטיס
    var hover = null;           // {b,g}
    var drag = null, suppress = false, raf = 0, focusH = '';
    var G = {};                 // גיאומטריה אחרונה
    var anim = 0, animTok = 0;

    host.classList.add('rb-tlc');
    host.innerHTML =
      '<div class="rb-tlc-head">' +
        '<div class="rb-tlc-title"><b>ציר הדורות</b><small>גררו לבחירת טווח · לחצו על תקופה או עמודה</small></div>' +
        '<div class="rb-tlc-slot"></div>' +
        '<div class="rb-tlc-tools" role="toolbar" aria-label="כלי ציר">' +
          '<button type="button" class="rb-ib" data-a="zin" title="התקרבות" aria-label="התקרבות"></button>' +
          '<button type="button" class="rb-ib" data-a="zout" title="התרחקות" aria-label="התרחקות"></button>' +
          '<button type="button" class="rb-ib" data-a="focus" title="התמקד בטווח שנבחר" aria-label="התמקד בטווח שנבחר"></button>' +
          '<button type="button" class="rb-ib" data-a="reset" title="הצג את כל הציר" aria-label="הצג את כל הציר"></button>' +
        '</div>' +
      '</div>' +
      '<div class="rb-tlc-body"><div class="rb-tlc-wrap">' +
        '<svg class="rb-svg" role="group" aria-label="ציר הדורות: התפלגות הרבנים לפי שנים. אפשר לבחור טווח בגרירה, או להשתמש בתקופות שמתחת."></svg>' +
        '<div class="rb-pop" hidden></div>' +
        '<div class="rb-tlc-skel"><span></span></div>' +
      '</div></div>' +
      '';
    var svg = host.querySelector('svg'), pop = host.querySelector('.rb-pop'), wrap = host.querySelector('.rb-tlc-wrap');
    var btn = {}; host.querySelectorAll('[data-a]').forEach(function (b) { btn[b.dataset.a] = b; });
    var ic = o.icon || function () { return ''; };
    btn.zin.innerHTML = ic('zoom_in', 17); btn.zout.innerHTML = ic('zoom_out', 17);
    btn.focus.innerHTML = ic('focus', 17); btn.reset.innerHTML = ic('expand', 17);

    /* ----- גיאומטריה ----- */
    function metrics() {
      var W = Math.max(0, wrap.clientWidth);
      var fpx = parseFloat(getComputedStyle(host).fontSize) || 20;
      var u = clamp(fpx / 20, .85, 1.45), fs = Math.round(fpx * .48 * 10) / 10;
      var narrow = W < 560;
      var padX = narrow ? 12 : 18;
      var laneH = Math.round(15 * u), lanes = 1;
      var top = 2, plotTop = top + lanes * laneH + Math.round(4 * u);
      var plotH = Math.round((narrow ? 34 : 38) * u);
      var base = plotTop + plotH;
      var stripY = base + 3, stripH = Math.round(17 * u);
      var axY = stripY + stripH + Math.round(10 * u);
      var H = axY + Math.round(3 * u) + 1;
      G = { W: W, H: H, u: u, fs: fs, L: padX, iw: Math.max(10, W - 2 * padX), laneH: laneH, lanes: lanes, top: top,
            plotTop: plotTop, plotH: plotH, base: base, stripY: stripY, stripH: stripH, axY: axY, narrow: narrow };
    }
    function X(y) { return G.L + (d1 - y) / (d1 - d0) * G.iw; }
    function Y(x) { return d1 - (x - G.L) / G.iw * (d1 - d0); }
    function gran() { var s = d1 - d0; return s > 700 ? 25 : (s > 260 ? 10 : 5); }
    function hebY(y) { return 'ה׳' + gm((y + 3760) % 1000); }

    function sumRange(arr, a, b) { var s = 0; a = Math.max(0, Math.floor(a)); b = Math.min(YMAX, Math.floor(b)); for (var i = a; i <= b; i++) s += arr[i]; return s; }

    /* ----- ציור ----- */
    function draw() {
      raf = 0;
      metrics();
      if (G.W < 40) return;
      var s = '', i, W = G.W, H = G.H, L = G.L, iw = G.iw, pt = G.plotTop, base = G.base, ph = G.plotH;
      svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      host.classList.toggle('has-data', !!hist);
      btn.zout.disabled = btn.reset.disabled = (d0 <= FULL0 && d1 >= FULL1);
      btn.focus.disabled = !sel;
      btn.zin.disabled = (d1 - d0) <= 42;
      if (!hist) { svg.innerHTML = ''; return; }

      var span = d1 - d0, r = Math.max(2, Math.round(span / 110));
      var filtered = histAll && hist !== histAll;
      var sm = smooth(hist, r), smA = filtered ? smooth(histAll, r) : sm;
      var vmax = 1e-6, vmaxA = 1e-6, y0 = Math.max(0, Math.floor(d0)), y1 = Math.min(YMAX, Math.ceil(d1));
      for (i = y0; i <= y1; i++) { if (sm[i] > vmax) vmax = sm[i]; if (smA[i] > vmaxA) vmaxA = smA[i]; }
      /* בחיפוש: העקומה המלאה מנורמלת לשיא של התוצאות (כדי שהצורה תהיה קריאה), והעקומה הכללית — לשיא שלה, כרקע */
      var f = function (v) { return Math.sqrt(Math.max(0, v) / vmax); };
      var fA = function (v) { return Math.sqrt(Math.max(0, v) / vmaxA); };
      var n = Math.max(20, Math.floor(iw / 3)), pts = [], ptsA = [], px, yr, k;
      for (k = 0; k <= n; k++) {
        px = L + k * iw / n; yr = clamp(Math.round(Y(px)), 0, YMAX);
        pts.push([px, base - f(sm[yr]) * (ph - 6)]);
        if (filtered) ptsA.push([px, base - fA(smA[yr]) * (ph - 6)]);
      }
      function line(P) { return P.map(function (p, j) { return (j ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(''); }
      var area = line(pts) + 'L' + (L + iw).toFixed(1) + ' ' + base + 'L' + L + ' ' + base + 'Z';

      s += '<defs><clipPath id="' + id + 'c"><path d="' + area + '"/></clipPath></defs>';

      /* רצועות תקופה (רקע) + קווי רשת */
      eras.forEach(function (e) {
        var a = Math.max(e.lo, d0), b = Math.min(e.hi, d1);
        if (b <= a) return;
        var xa = X(b), xb = X(a);
        s += '<rect class="rb-band' + (o.getPer && o.getPer() === e.id ? ' on' : '') + '" style="--e:var(' + e.css + ')" x="' + xa.toFixed(1) + '" y="' + pt + '" width="' + (xb - xa).toFixed(1) + '" height="' + ph + '"/>';
      });
      var step = pickStep(span, iw, 46 * G.u), t0 = Math.ceil(d0 / step) * step, ticks = [];
      for (var t = t0; t <= d1; t += step) ticks.push(t);
      ticks.forEach(function (t) { s += '<line class="rb-grid" x1="' + X(t).toFixed(1) + '" x2="' + X(t).toFixed(1) + '" y1="' + pt + '" y2="' + base + '"/>'; });
      s += '<line class="rb-base" x1="' + L + '" x2="' + (L + iw) + '" y1="' + base + '" y2="' + base + '"/>';

      /* עקומה: רפאים (הכל) + מלאה צבועה לפי תקופות */
      if (filtered) s += '<path class="rb-ghost" d="' + line(ptsA) + '"/>';
      s += '<g clip-path="url(#' + id + 'c)">';
      eras.forEach(function (e) {
        var a = Math.max(e.lo, d0), b = Math.min(e.hi, d1);
        if (b <= a) return;
        var xa = X(b), xb = X(a);
        s += '<rect class="rb-fill" style="--e:var(' + e.css + ')" x="' + xa.toFixed(1) + '" y="' + pt + '" width="' + (xb - xa + .5).toFixed(1) + '" height="' + ph + '"/>';
      });
      s += '</g><path class="rb-line" d="' + line(pts) + '"/>';

      /* עמודות לחיצות (hover / בחירת קטע) */
      var g = gran(), b0 = Math.floor(d0 / g) * g;
      for (var b = b0; b < d1; b += g) {
        var xa2 = X(Math.min(b + g, d1)), xb2 = X(Math.max(b, d0));
        var on = sel && b < sel.hi && b + g > sel.lo;
        s += '<rect class="rb-bar' + (on ? ' sel' : '') + (hover && hover.b === b ? ' hv' : '') + '" data-b="' + b + '" x="' + xa2.toFixed(1) + '" y="' + pt + '" width="' + Math.max(1, xb2 - xa2).toFixed(1) + '" height="' + ph + '"/>';
      }

      /* סרגל תקופות */
      var sy = G.stripY, sh = G.stripH;
      eras.forEach(function (e) {
        var a = Math.max(e.lo, d0), b = Math.min(e.hi, d1);
        if (b <= a) return;
        var xa = X(b), xb = X(a), w = xb - xa, on = o.getPer && o.getPer() === e.id;
        var cw = G.fs * .62, lab = w > e.t.length * cw + 12 ? e.t : (w > e.s.length * cw + 8 ? e.s : '');
        if (!lab) { var mc = Math.floor((w - 8) / cw); if (mc >= 3) lab = e.s.slice(0, mc - 1) + '…'; }
        s += '<g class="rb-era' + (on ? ' on' : '') + '" style="--e:var(' + e.css + ')" data-p="' + e.id + '" role="button" aria-label="' + esc(e.t) + '">' +
          '<title>' + esc(e.t + ' · ' + e.lo + '–' + (e.hi > 2100 ? '' : e.hi)) + '</title>' +
          '<rect class="rb-era-bg" x="' + (xa + .5).toFixed(1) + '" y="' + sy + '" width="' + Math.max(0, w - 1).toFixed(1) + '" height="' + sh + '" rx="' + Math.round(sh / 2.6) + '"/>' +
          (lab ? '<text class="rb-era-t" x="' + ((xa + xb) / 2).toFixed(1) + '" y="' + (sy + sh / 2 + G.fs * .36).toFixed(1) + '" text-anchor="middle">' + esc(lab) + '</text>' : '') + '</g>';
      });

      /* ציר: שנה לועזית + עברית */
      ticks.forEach(function (t) {
        var x = X(t);
        s += '<line class="rb-tick" x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + (G.stripY + sh + 1) + '" y2="' + (G.stripY + sh + 4) + '"/>' +
          '<text class="rb-ax" x="' + x.toFixed(1) + '" y="' + G.axY + '" text-anchor="middle">' + t + '</text>';
      });

      /* בחירה: האפלת מה שבחוץ, ידיות וקריאה */
      if (sel) {
        var sx0 = clamp(X(Math.min(sel.hi, d1 + 1)), L, L + iw), sx1 = clamp(X(Math.max(sel.lo, d0 - 1)), L, L + iw);
        var dimH = G.stripY + sh - pt;
        if (sx1 - sx0 < 1) sx1 = sx0 + 1;
        s += '<rect class="rb-dim" x="' + L + '" y="' + pt + '" width="' + Math.max(0, sx0 - L).toFixed(1) + '" height="' + dimH + '"/>' +
             '<rect class="rb-dim" x="' + sx1.toFixed(1) + '" y="' + pt + '" width="' + Math.max(0, L + iw - sx1).toFixed(1) + '" height="' + dimH + '"/>' +
             '<rect class="rb-selbody" x="' + sx0.toFixed(1) + '" y="' + pt + '" width="' + (sx1 - sx0).toFixed(1) + '" height="' + ph + '"/>' +
             '<line class="rb-seltop" x1="' + sx0.toFixed(1) + '" x2="' + sx1.toFixed(1) + '" y1="' + pt + '" y2="' + pt + '"/>';
        s += handle('lo', sx1, sel.lo) + handle('hi', sx0, sel.hi - 1);
      }

      /* ציוני דרך */
      var placed = [[], []], lm = '';
      landmarks.forEach(function (m) {
        if (m.y < d0 + 1 || m.y > d1 - 1) return;
        var x = X(m.y), w = m.s.length * G.fs * .6 + 12, lane = -1, xl = clamp(x - w / 2, 2, W - w - 2);
        for (var l = 0; l < G.lanes; l++) {
          var ok = true;
          for (var q = 0; q < placed[l].length; q++) if (xl < placed[l][q][1] + 5 && xl + w > placed[l][q][0] - 5) { ok = false; break; }
          if (ok) { lane = l; break; }
        }
        var yy = clamp(Math.round(m.y), 0, YMAX), dotY = base - (filtered ? fA : f)(smA[yy]) * (ph - 6);
        if (lane < 0) { lm += '<circle class="rb-dot" cx="' + x.toFixed(1) + '" cy="' + dotY.toFixed(1) + '" r="2.6"/>'; return; }
        placed[lane].push([xl, xl + w]);
        var ly = G.top + (G.lanes - 1 - lane) * G.laneH, lh = G.laneH - 1;
        lm += '<g class="rb-lm" data-i="' + m.i + '" tabindex="0" role="button" aria-label="' + esc(m.full + ' ' + m.y) + '">' +
          '<line class="rb-stem" x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + (ly + lh) + '" y2="' + (dotY - 4).toFixed(1) + '"/>' +
          '<circle class="rb-dot" cx="' + x.toFixed(1) + '" cy="' + dotY.toFixed(1) + '" r="4"/>' +
          '<rect class="rb-lmbg" x="' + xl.toFixed(1) + '" y="' + ly + '" width="' + w.toFixed(1) + '" height="' + lh + '" rx="' + (lh / 2).toFixed(1) + '"/>' +
          '<text class="rb-lmt" x="' + (xl + w / 2).toFixed(1) + '" y="' + (ly + lh / 2 + G.fs * .36).toFixed(1) + '" text-anchor="middle">' + esc(m.s) + '</text></g>';
      });
      s += lm;

      /* הרב הפתוח בכרטיס */
      if (cur >= d0 && cur <= d1) {
        var cx = X(cur);
        s += '<g class="rb-cur" pointer-events="none"><line x1="' + cx.toFixed(1) + '" x2="' + cx.toFixed(1) + '" y1="' + pt + '" y2="' + base + '"/><circle cx="' + cx.toFixed(1) + '" cy="' + base + '" r="4.5"/></g>';
      }
      /* קו hover */
      if (hover && !drag) {
        var hx = X(hover.b + hover.g / 2);
        s += '<line class="rb-hline" x1="' + hx.toFixed(1) + '" x2="' + hx.toFixed(1) + '" y1="' + pt + '" y2="' + base + '"/>';
      }
      svg.innerHTML = s;
      if (focusH) { var fe = svg.querySelector('[data-h="' + focusH + '"]'); if (fe) fe.focus({ preventScroll: true }); }
    }
    function handle(which, x, yr) {
      var gw = Math.round(12 * G.u), gh = Math.round(20 * G.u), cy = G.plotTop + G.plotH / 2 + 6, tw = String(yr).length * G.fs * .62 + 10, th = Math.round(13 * G.u);
      var tx = clamp(x - tw / 2, 1, G.W - tw - 1);
      return '<g class="rb-h" data-h="' + which + '" tabindex="0" role="slider" aria-label="' + (which === 'lo' ? 'תחילת הטווח' : 'סוף הטווח') + '" aria-valuemin="' + FULL0 + '" aria-valuemax="' + FULL1 + '" aria-valuenow="' + yr + '">' +
        '<rect class="rb-hhit" x="' + (x - 14).toFixed(1) + '" y="' + (G.plotTop - 2) + '" width="28" height="' + (G.plotH + 4) + '"/>' +
        '<line class="rb-hline2" x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + G.plotTop + '" y2="' + G.base + '"/>' +
        '<rect class="rb-grip" x="' + (x - gw / 2).toFixed(1) + '" y="' + (cy - gh / 2).toFixed(1) + '" width="' + gw + '" height="' + gh + '" rx="' + (gw / 2) + '"/>' +
        '<path class="rb-gripl" d="M' + (x - 1.6).toFixed(1) + ' ' + (cy - 4) + 'v8M' + (x + 1.6).toFixed(1) + ' ' + (cy - 4) + 'v8"/>' +
        '<rect class="rb-ypill" x="' + tx.toFixed(1) + '" y="' + (G.plotTop + 1) + '" width="' + tw.toFixed(1) + '" height="' + th + '" rx="' + (th / 2) + '"/>' +
        '<text class="rb-ypt" x="' + (tx + tw / 2).toFixed(1) + '" y="' + (G.plotTop + 1 + th / 2 + G.fs * .36).toFixed(1) + '" text-anchor="middle">' + yr + '</text></g>';
    }
    function pickStep(span, iw, minPx) {
      var C = [5, 10, 25, 50, 100, 200, 250, 500];
      for (var i = 0; i < C.length; i++) if (C[i] / span * iw >= minPx) return C[i];
      return 500;
    }
    /* rAF רגיל; גיבוי בטיימר למקרה שהדפדפן מקפיא rAF (חלון מוסתר / בדיקות headless) */
    function redraw() {
      if (raf) return;
      raf = requestAnimationFrame(draw);
      setTimeout(function () { if (raf) { cancelAnimationFrame(raf); draw(); } }, 80);
    }

    /* ----- tooltip ----- */
    /* ה-tooltip ממוקם מעל הציר כולו (מחוץ ל-svg), עם pointer-events:none — לעולם לא מכסה ידיות/מברשת/עמודות */
    function showPop(html, x) {
      pop.innerHTML = html; pop.hidden = false;
      var w = pop.offsetWidth, h = pop.offsetHeight;
      pop.style.left = clamp(x - w / 2, 4, Math.max(4, G.W - w - 4)) + 'px';
      pop.style.top = (-h - 4) + 'px';
    }
    function hidePop() { pop.hidden = true; }
    function binPop(b, g) {
      var lo = Math.max(b, 0), hi = b + g - 1;
      var c = sumRange(hist, lo, hi), ca = histAll ? sumRange(histAll, lo, hi) : c;
      var ex = o.examples ? o.examples(lo, b + g) : [];
      return '<div class="rb-pop-y"><bdi dir="ltr">' + lo + '–' + hi + '</bdi> <span>' + hebY(lo) + '–' + hebY(hi) + '</span> · <b>' + num(c) + '</b> רבנים' + (histAll && c !== ca ? ' <span>מתוך ' + num(ca) + '</span>' : '') + '</div>' +
        (ex.length ? '<div class="rb-pop-e">לדוגמה: ' + ex.map(esc).join(' · ') + '</div>' : '');
    }

    /* ----- אינטראקציה ----- */
    function ptr(e) { var r = svg.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    function snapLo(y) { return Math.floor(y / 5) * 5; }
    function snapHi(y) { return Math.ceil(y / 5) * 5; }
    function setSel(lo, hi, preview) {
      lo = clamp(lo, 1, FULL1 - 5); hi = clamp(hi, lo + 5, FULL1);
      sel = { lo: lo, hi: hi };
      if (o.onSelect) o.onSelect(lo, hi, !!preview);
      redraw();
    }
    function onDown(e) {
      if (e.button != null && e.button > 0) return;
      var p = ptr(e), t = e.target, h = t.closest && t.closest('[data-h]');
      drag = { id: e.pointerId, x0: p.x, y0: p.y, yr0: Y(p.x), moved: false, kind: 'new', d0: d0, d1: d1, sel0: sel ? { lo: sel.lo, hi: sel.hi } : null, zone: p.y > G.base };
      if (h) drag.kind = h.dataset.h;
      else if (t.closest && t.closest('.rb-lm')) drag.kind = 'lm';
      else if (drag.zone) drag.kind = d1 - d0 < FULL1 - FULL0 - 1 ? 'pan' : 'none';
      else if (sel && t.closest && t.closest('.rb-selbody')) drag.kind = 'move';
      if (h) { focusH = h.dataset.h; }
    }
    function onMove(e) {
      var p = ptr(e);
      if (drag && e.pointerId === drag.id && (e.buttons & 1 || e.pointerType === 'touch' || e.pointerType === 'pen')) {
        if (!drag.moved) {
          if (Math.abs(p.x - drag.x0) < 4) return;
          if (drag.kind === 'lm' || drag.kind === 'none') { drag = null; return; }
          drag.moved = true; hidePop();
          try { svg.setPointerCapture(e.pointerId); } catch (er) {}
          host.classList.add('dragging');
        }
        var yr = Y(p.x), k = drag.kind;
        if (k === 'new') {
          var a = Math.min(drag.yr0, yr), b = Math.max(drag.yr0, yr);
          setSel(snapLo(a), Math.max(snapHi(b), snapLo(a) + 5), true);
        } else if (k === 'lo') {          // הקצה הקדום (ימין)
          var hi0 = sel.hi; setSel(Math.min(snapLo(yr), hi0 - 5), hi0, true);
        } else if (k === 'hi') {          // הקצה המאוחר (שמאל)
          var lo0 = sel.lo; setSel(lo0, Math.max(snapHi(yr + 1), lo0 + 5), true);
        } else if (k === 'move') {
          var dy = Math.round((yr - drag.yr0) / 5) * 5, w = drag.sel0.hi - drag.sel0.lo;
          var lo = clamp(drag.sel0.lo + dy, 1, FULL1 - w); setSel(lo, lo + w, true);
        } else if (k === 'pan') {
          var dyr = (p.x - drag.x0) / G.iw * (drag.d1 - drag.d0), n0 = drag.d0 + dyr, n1 = drag.d1 + dyr;
          if (n0 < FULL0) { n1 += FULL0 - n0; n0 = FULL0; } if (n1 > FULL1) { n0 -= n1 - FULL1; n1 = FULL1; }
          d0 = n0; d1 = n1; redraw();
        }
        return;
      }
      if (drag) return;
      /* hover */
      if (e.pointerType === 'touch') return;
      var tgt = e.target, lmEl = tgt.closest && tgt.closest('.rb-lm');
      if (tgt.closest && tgt.closest('[data-h]')) { if (hover) { hover = null; redraw(); } hidePop(); return; }
      if (lmEl) {
        var m = landmarks[+lmEl.dataset.i]; hover = null;
        if (m) showPop('<div class="rb-pop-y">' + esc(m.full) + '</div><div class="rb-pop-e"><bdi dir="ltr">' + m.y + (m.d ? '–' + m.d : '') + '</bdi> · ' + hebY(m.y) + '</div>', X(m.y));
        return;
      }
      if (p.y < G.plotTop - 2 || p.y > G.base || p.x < G.L - 4 || p.x > G.L + G.iw + 4) { if (hover) { hover = null; redraw(); } hidePop(); return; }
      var g = gran(), b = Math.floor(Y(p.x) / g) * g;
      if (!hover || hover.b !== b) { hover = { b: b, g: g }; redraw(); }
      showPop(binPop(b, g), X(b + g / 2));
    }
    function onUp(e) {
      if (!drag || e.pointerId !== drag.id) return;
      var d = drag; drag = null; focusH = '';
      host.classList.remove('dragging');
      if (d.moved) {
        suppress = true; setTimeout(function () { suppress = false; }, 0);
        try { svg.releasePointerCapture(e.pointerId); } catch (er) {}
        if (d.kind !== 'pan' && sel && o.onSelect) o.onSelect(sel.lo, sel.hi, false);
        redraw();
      }
    }
    function onLeave() { if (!drag) { hover = null; hidePop(); redraw(); } }
    function onClick(e) {
      if (suppress) return;
      var t = e.target, el;
      if ((el = t.closest('.rb-lm'))) { if (o.onLandmark) o.onLandmark(+landmarks[+el.dataset.i].x); return; }
      if (t.closest('[data-h]')) return;
      if ((el = t.closest('.rb-era'))) { if (o.onEra) o.onEra(el.dataset.p); return; }
      var b, g = gran();
      if ((el = t.closest('.rb-bar'))) b = +el.dataset.b;
      else {
        var p = ptr(e); if (p.y < G.plotTop || p.y > G.base) return;
        b = Math.floor(Y(p.x) / g) * g;
      }
      if (sel && sel.lo === b && sel.hi === b + g) { api.clearSel(); if (o.onClear) o.onClear(); return; }
      sel = { lo: b, hi: b + g };
      if (o.onSelect) o.onSelect(b, b + g, false);
      redraw();
    }
    function onKey(e) {
      var h = e.target.closest && e.target.closest('[data-h]');
      if (h && sel) {
        var d = e.shiftKey ? 25 : 5, dir = 0;
        if (e.key === 'ArrowLeft') dir = 1; else if (e.key === 'ArrowRight') dir = -1;      // שמאלה = מאוחר יותר (ציר RTL)
        if (dir) {
          e.preventDefault(); focusH = h.dataset.h;
          if (h.dataset.h === 'lo') setSel(Math.min(sel.lo + dir * d, sel.hi - 5), sel.hi, false);
          else setSel(sel.lo, Math.max(sel.hi + dir * d, sel.lo + 5), false);
        }
        return;
      }
      var lm = e.target.closest && e.target.closest('.rb-lm');
      if (lm && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); if (o.onLandmark) o.onLandmark(landmarks[+lm.dataset.i].x); }
      var er = e.target.closest && e.target.closest('.rb-era');
      if (er && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); if (o.onEra) o.onEra(er.dataset.p); }
    }
    svg.addEventListener('pointerdown', onDown);
    svg.addEventListener('pointermove', onMove);
    svg.addEventListener('pointerup', onUp);
    svg.addEventListener('pointercancel', onUp);
    svg.addEventListener('pointerleave', onLeave);
    svg.addEventListener('click', onClick);
    svg.addEventListener('keydown', onKey);
    svg.addEventListener('focusout', function (e) { if (!e.relatedTarget || !svg.contains(e.relatedTarget)) focusH = ''; });
    svg.addEventListener('wheel', function (e) {
      if (!e.ctrlKey) return;
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? .75 : 1.33, Y(ptr(e).x));
    }, { passive: false });

    /* ----- זום ----- */
    function animTo(n0, n1) {
      n0 = Math.max(FULL0, n0); n1 = Math.min(FULL1, n1);
      if (n1 - n0 < 40) { var m = (n0 + n1) / 2; n0 = m - 20; n1 = m + 20; }
      if (n0 < FULL0) { n1 += FULL0 - n0; n0 = FULL0; } if (n1 > FULL1) { n0 -= n1 - FULL1; n1 = FULL1; }
      cancelAnimationFrame(anim); animTok++;
      var a0 = d0, a1 = d1, t0 = performance.now(), D = 220;
      var still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (still || o.noAnim) { d0 = n0; d1 = n1; hover = null; draw(); return; }
      var tok = ++animTok;
      setTimeout(function () { if (tok === animTok && (d0 !== n0 || d1 !== n1)) { cancelAnimationFrame(anim); d0 = n0; d1 = n1; draw(); } }, D + 120);
      (function stepA(t) {
        var k = clamp((t - t0) / D, 0, 1), e = 1 - Math.pow(1 - k, 3);
        d0 = a0 + (n0 - a0) * e; d1 = a1 + (n1 - a1) * e; draw();
        if (k < 1) anim = requestAnimationFrame(stepA);
      })(t0);
    }
    function zoomBy(f, center) {
      var c = center != null ? center : (sel ? (sel.lo + sel.hi) / 2 : (d0 + d1) / 2);
      var s = (d1 - d0) * f, k = (c - d0) / (d1 - d0);
      animTo(c - s * k, c - s * k + s);
    }
    host.querySelector('.rb-tlc-head').addEventListener('click', function (e) {
      var b = e.target.closest('[data-a]'); if (!b) return;
      var a = b.dataset.a;
      if (a === 'zin') zoomBy(.6); else if (a === 'zout') zoomBy(1 / .6);
      else if (a === 'reset') animTo(FULL0, FULL1);
      else if (a === 'focus' && sel) { var pad = Math.max((sel.hi - sel.lo) * .35, 20); animTo(sel.lo - pad, sel.hi + pad); }
        });

    if (window.ResizeObserver) new ResizeObserver(function () { redraw(); }).observe(wrap);
    else window.addEventListener('resize', redraw);

    var api = {
      slot: host.querySelector('.rb-tlc-slot'),
      FULL0: FULL0, FULL1: FULL1,
      setData: function (h, hAll) { hist = h; histAll = hAll || h; redraw(); },
      setLandmarks: function (a) { landmarks = a; redraw(); },
      setSel: function (lo, hi) { sel = (lo == null) ? null : { lo: lo, hi: Math.min(hi, FULL1 + 1) }; redraw(); },
      clearSel: function () { sel = null; redraw(); },
      setCurrent: function (y) { cur = y || 0; redraw(); },
      zoomTo: function (a, b) { animTo(a, b); },
      refresh: redraw,
      draw: draw,
      getSel: function () { return sel; }
    };
    return api;
  }
  window.RbTimeline = { create: create, FULL0: FULL0, FULL1: FULL1 };
})();

/* ===========================================================================
 *  rabbis.js — טאב "ראשונים ואחרונים" (~61 אלף רבנים)
 *  נטען עצלנית: האינדקס (rb-index.js) בלחיצה הראשונה על הטאב; קבצי הרשומות
 *  המלאות (rb-N.js) רק בפתיחת כרטיס רב או בחיפוש בטקסט הביוגרפיה.
 *  ציר הדורות (rb-timeline.js) מסנן את הרשימה בזמן אמת; אפשר להסתיר אותו (נשמר ב-localStorage).
 *  נקודת הכניסה: window.initRabbis (נקראת מ-setTab ב-app.js).
 * ========================================================================= */
(function () {
  'use strict';

  var BASE = 'data/rabbis/';
  var PAGE = 150;                 // שורות לכל מנת רינדור
  var TITLES = ['ר', 'רבי', 'הרב'];   // תארים שמתעלמים מהם בחיפוש
  var MON = ['תשרי', 'חשון', 'כסלו', 'טבת', 'שבט', 'אדר', 'ניסן', 'אייר', 'סיון', 'תמוז', 'אב', 'אלול', 'אדר א', 'אדר ב'];  // כמו RB_MONTHS (זמין לפני טעינת האינדקס)
  var EN_MONTHS = {               // שמות חודשים (Intl באנגלית) -> אינדקס ב-RB_MONTHS
    'Tishri': 0, 'Tishrei': 0, 'Heshvan': 1, 'Cheshvan': 1, 'Marcheshvan': 1, 'Kislev': 2,
    'Tevet': 3, 'Teves': 3, 'Shevat': 4, 'Adar': 5, 'Adar I': 12, 'Adar II': 13,
    'Nisan': 6, 'Iyar': 7, 'Sivan': 8, 'Tamuz': 9, 'Tammuz': 9, 'Av': 10, 'Elul': 11
  };
  var LS_KEY = 'bio-rb-tl-collapsed';
  /* תקופות: lo <= שנה < hi (השנה = לידה, ואם חסרה: פטירה פחות 60). הצבע נגזר ב-CSS: --era-* (style.css) */
  var PERS = [
    { id: 'all', t: 'הכל' },
    { id: 'g', t: 'גאונים', s: 'גאונים', rng: 'עד 1040', lo: 1, hi: 1040, e: 1, css: '--era-g' },
    { id: 'r', t: 'ראשונים', s: 'ראשונים', rng: '1040–1490', lo: 1040, hi: 1490, e: 2, css: '--era-r' },
    { id: 'a', t: 'אחרונים א׳', s: 'אחרונים א׳', rng: '1490–1750', lo: 1490, hi: 1750, e: 3, css: '--era-a' },
    { id: 'b', t: 'אחרונים ב׳', s: 'אחרונים ב׳', rng: '1750–1880', lo: 1750, hi: 1880, e: 4, css: '--era-b' },
    { id: 'c', t: 'דור קרוב', s: 'קרוב', rng: '1880–1950', lo: 1880, hi: 1950, e: 5, css: '--era-c' },
    { id: 'd', t: 'בני זמננו', s: 'זמננו', rng: 'אחרי 1950', lo: 1950, hi: 99999, e: 6, css: '--era-d' },
    { id: 'none', t: 'ללא שנה' }
  ];
  var ERAS = PERS.filter(function (p) { return p.lo != null; });
  /* ציוני דרך: שם הרשומה בדיוק כפי שהוא באינדקס, תווית קצרה, עדיפות (1 = חשוב ביותר) */
  var LANDMARKS = [
    ['יצחקי, שלמה', 'רש״י', 1], ['משה - רמב"ם', 'הרמב״ם', 1], ['קארו, יוסף - בית יוסף', 'הבית יוסף', 1],
    ['ישראל בעל שם טוב', 'הבעש״ט', 1], ['אליהו מוילנא - הגר"א', 'הגר״א', 1], ['סופר, משה - החת"ס', 'החתם סופר', 1],
    ['משה - רמב"ן', 'הרמב״ן', 2], ['לוריא, יצחק - האר"י', 'האר״י', 2], ['איסרלש, משה - הרמ"א', 'הרמ״א', 2],
    ['ישראל מאיר הכהן מראדין', 'החפץ חיים', 2], ['קוק, אברהם יצחק הכהן-ראי"ה', 'הראי״ה', 2],
    ['ר\' סעדיה גאון', 'רס״ג', 3], ['אלפסי, יצחק - הרי"ף', 'הרי״ף', 3], ['יהודה ליוואי - מהר"ל מפרג', 'המהר״ל', 3],
    ['אזולאי, חיים יוסף דוד', 'החיד״א', 3], ['קרליץ, אברהם ישעיה - חזון איש', 'החזון איש', 3], ['ר\' משה פיינשטיין', 'הרב פיינשטיין', 3],
    ['אדרת ן, שלמה - הרשב"א', 'הרשב״א', 4], ['ר\' אשר בן יחיאל (הרא"ש)', 'הרא״ש', 4], ['יעקב מטרויש - רבנו תם', 'ר״ת', 4],
    ['ר\' עובדיה יוסף ב"ר יעקב', 'הרב עובדיה', 4]
  ];
  var F0 = 750, F1 = 2030;        // תחום ציר הדורות המלא (שנים)

  var inited = false, ready = false;
  var R = [];               // רשומות מעובדות: {a:שורת-אינדקס, nn, na, nk, nb, key, e}
  var idToX = new Map();    // id -> אינדקס ב-R
  var nameToX = new Map();  // שם רשומה -> אינדקס ב-R (לציוני דרך)
  var bioN = [];            // טקסט ביוגרפיה מנורמל (לפי אינדקס ב-R), נבנה כשקובץ נטען
  var shardCache = {}, shardP = {};
  var nFiles = 0;
  function eraNum(k) { for (var i = 0; i < ERAS.length; i++) if (k >= ERAS[i].lo && k < ERAS[i].hi) return ERAS[i].e; return 0; }
  var S = { mode: 'list', sort: 'name', per: 'all', lo: 0, hi: 0, q: '', bio: false, yd: 1, ym: 0, cur: -1, label: '' };
  var res = [], shown = 0, base = [], baseT = [], baseKey = '';
  var hist = new Int32Array(2101), histAll = new Int32Array(2101), noYear = 0;   // בסיס נתוני הציר: ספירה לכל שנה (לא DOM לכל רשומה)
  var curBooks = [];
  var openTok = 0;
  var el = {};
  var view, searchT, tl = null, tlOff = false, tlMoveT = 0, exCache = { k: '', v: [] };
  var lastRun = 0, runT = 0;

  /* ----- עזרים ----- */
  function h(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function bd(t) { return h(t).replace(/(\d+–\d+)/g, '<bdi dir="ltr">$1</bdi>'); }
  function ic(n, s) { return (typeof icon === 'function') ? icon(n, s) : ''; }

  /* נרמול לחיפוש: בלי ניקוד, גרשיים נמחקים, מקפים/פסיקים/נקודות -> רווח */
  function nrm(s) {
    return String(s || '')
      .replace(/[֑-ׇ]/g, '')
      .replace(/[\-־–—_\/\\,;:.()\[\]{}]/g, ' ')
      .replace(/["'׳״`’‘“”!?*]/g, '')
      .replace(/\s+/g, ' ').trim();
  }

  /* גימטריה: 15 -> ט"ו, 16 -> ט"ז, אות בודדת -> עם גרש */
  var GL = [[400, 'ת'], [300, 'ש'], [200, 'ר'], [100, 'ק'], [90, 'צ'], [80, 'פ'], [70, 'ע'], [60, 'ס'], [50, 'נ'],
    [40, 'מ'], [30, 'ל'], [20, 'כ'], [10, 'י'], [9, 'ט'], [8, 'ח'], [7, 'ז'], [6, 'ו'], [5, 'ה'], [4, 'ד'], [3, 'ג'], [2, 'ב'], [1, 'א']];
  function gm(n) {
    var s = '';
    n = Math.floor(n);
    if (n <= 0) return '';
    for (var i = 0; i < GL.length; i++) {
      while (n >= GL[i][0]) {
        if (n === 15) { s += 'טו'; n = 0; break; }
        if (n === 16) { s += 'טז'; n = 0; break; }
        s += GL[i][1]; n -= GL[i][0];
      }
    }
    return s.length === 1 ? s + '׳' : s.slice(0, -1) + '״' + s.slice(-1);
  }

  function loadScript(src) {
    return new Promise(function (ok, bad) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = function () { ok(); };
      s.onerror = function () { s.remove(); bad(new Error('load ' + src)); };
      document.head.appendChild(s);
    });
  }

  /* ----- טעינת קבצי רשומות מלאות (עם מטמון) ----- */
  function indexBio(n, arr) {
    for (var i = 0; i < arr.length; i++) {
      var r = arr[i], x = idToX.get(r.i);
      if (x == null) continue;
      bioN[x] = nrm((r.b || '') + ' ' + (r.bp || '') + ' ' + (r.dp || ''));
    }
  }
  function loadShard(n) {
    if (shardCache[n]) return Promise.resolve(shardCache[n]);
    if (shardP[n]) return shardP[n];
    shardP[n] = loadScript(BASE + 'rb-' + (window.RB_VER || '') + '-' + n + '.js').then(function () {
      var a = (window.RB_SHARDS || {})[n];
      if (!a) throw new Error('shard ' + n);
      shardCache[n] = a;
      indexBio(n, a);
      delete shardP[n];
      return a;
    }).catch(function (e) { delete shardP[n]; throw e; });
    return shardP[n];
  }
  function findRec(arr, id) {      // חיפוש בינארי (ממוין לפי i); נפילה לליניארי
    var lo = 0, hi = arr.length - 1;
    while (lo <= hi) {
      var m = (lo + hi) >> 1, v = arr[m].i;
      if (v === id) return arr[m];
      if (v < id) lo = m + 1; else hi = m - 1;
    }
    for (var i = 0; i < arr.length; i++) if (arr[i].i === id) return arr[i];
    return null;
  }

  function ltr(t) { return '<bdi dir="ltr">' + h(t) + '</bdi>'; }

  /* ----- עיבוד האינדקס (בחתיכות כדי לא לתקוע את הממשק) ----- */
  function prepare() {
    var A = window.RB_INDEX || [];
    return new Promise(function (done) {
      var i = 0;
      (function chunk() {
        var e = Math.min(i + 6000, A.length);
        for (; i < e; i++) {
          var a = A[i], b = a[3], d = a[4];
          var key = b > 0 ? b : (d > 0 ? Math.max(1, d - 60) : 0);
          var nn = nrm(a[1]), na = nrm(a[2]);
          R.push({ a: a, nn: nn, na: na, nk: nn + ' ' + na, nb: nrm(a[7]), key: key, e: eraNum(key) });
          idToX.set(a[0], i);
          if (!nameToX.has(a[1])) nameToX.set(a[1], i);
          if (key > 0 && key <= 2100) histAll[key]++; else if (!key) noYear++;
          if (a[10] + 1 > nFiles) nFiles = a[10] + 1;
        }
        if (i < A.length) {
          setStatus('מעבד נתונים… ' + Math.round(i * 100 / A.length) + '%', false, 'load');
          setTimeout(chunk, 0);
        } else done();
      })();
    });
  }

  /* kind: load (ספינר + שלד) · empty (אין תוצאות) · err (שגיאה) */
  function setStatus(msg, html, kind) {
    if (!el.status) return;
    el.status.hidden = !msg;
    el.status.className = 'empty rb-status' + (kind ? ' k-' + kind : '');
    var pre = '';
    if (kind === 'load') pre = '<span class="rb-spin"></span>';
    else if (kind === 'empty') pre = '<span class="rb-sic">' + ic('search', 32) + '</span>';
    else if (kind === 'err') pre = '<span class="rb-sic err">' + ic('error', 32) + '</span>';
    var post = '';
    if (kind === 'load') { post = '<div class="rb-skels" aria-hidden="true">'; for (var i = 0; i < 7; i++) post += '<i style="width:' + (55 + (i * 37) % 40) + '%"></i>'; post += '</div>'; }
    if (!msg) { el.status.innerHTML = ''; return; }
    if (html) el.status.innerHTML = pre + '<div class="rb-smsg">' + msg + '</div>' + post;
    else { el.status.innerHTML = pre + '<div class="rb-smsg"></div>' + post; el.status.querySelector('.rb-smsg').textContent = msg; }
  }

  /* ----- חיפוש ----- */
  function parseQ(q) {
    var n = nrm(q);
    if (!n) return { t: [], full: '', strip: '' };
    var t = n.split(' ');
    var f = t.filter(function (w) { return TITLES.indexOf(w) < 0; });
    if (!f.length) f = t;
    return { t: f, full: n, strip: f.join(' ') };
  }
  function hasAll(s, toks) {
    for (var i = 0; i < toks.length; i++) if (s.indexOf(toks[i]) < 0) return false;
    return true;
  }
  /* דרגת התאמה: 0 מדויק · 1 שם/כינוי · 2 ספרים · 3 ביוגרפיה · -1 אין */
  function tierOf(r, x, Q) {
    if (Q.full === r.nn || Q.full === r.na || Q.strip === r.nn || Q.strip === r.na) return 0;
    if (hasAll(r.nk, Q.t)) return 1;
    var s2 = r.nk + ' ' + r.nb;
    if (hasAll(s2, Q.t)) return 2;
    if (S.bio && bioN[x] && hasAll(s2 + ' ' + bioN[x], Q.t)) return 3;
    return -1;
  }

  /* ----- יארצייט: תאריך עברי ----- */
  function hebToday() {
    try {
      var parts = new Intl.DateTimeFormat('en-u-ca-hebrew', { day: 'numeric', month: 'long', year: 'numeric' }).formatToParts(new Date());
      var d = 0, m = null, y = 0;
      parts.forEach(function (p) {
        if (p.type === 'day') d = parseInt(p.value, 10);
        else if (p.type === 'month') m = p.value;
        else if (p.type === 'year' || p.type === 'relatedYear') y = parseInt(p.value, 10) || y;
      });
      if (d > 0 && m != null && EN_MONTHS[m] != null) return { d: d, m: EN_MONTHS[m], y: y };
    } catch (e) { /* נופלים לברירת מחדל */ }
    return null;
  }
  /* אילו אינדקסי חודש ברשומות מתאימים לחודש הנבחר (אדר פשוט ~ אדר א/ב; אדר ב ~ גם "אדר") */
  function monthSet(m) {
    if (m === 5) return [5, 12, 13];
    if (m === 13) return [13, 5];
    return [m];
  }
  var todayH = null;
  function setToday() {
    todayH = hebToday();
    var t = todayH || { d: 1, m: 0, y: 0 };
    S.yd = t.d; S.ym = t.m;
    el.yd.value = S.yd; el.ym.value = S.ym;
  }

  /* ----- חישוב התוצאות ----- */
  function inPer(r) {
    if (S.per === 'all') return true;
    if (S.per === 'none') return r.key === 0;
    return r.key > 0 && r.key >= S.lo && r.key < S.hi;
  }
  function birthK(r) { return r.a[3] > 0 ? r.a[3] : (r.key > 0 ? r.key : 1e9); }
  function deathK(r) { var d = r.a[4]; return d > 0 ? d : (r.a[3] > 0 ? r.a[3] + 60 : 1e9); }

  function compute() {
    if (!ready) return;
    lastRun = Date.now();
    var Q = parseQ(S.q), n = Q.t.length, yz = S.mode === 'yz', x, r, t;
    var bk = S.q + '|' + S.mode + '|' + S.yd + '|' + S.ym + '|' + (S.bio && S.q ? Object.keys(shardCache).length : 0);
    if (bk !== baseKey) {          // בסיס (לפי חיפוש/מצב) + ההיסטוגרמה של הציר — מחושבים מחדש רק כשהשתנו
      baseKey = bk;
      var ms = yz ? monthSet(S.ym) : null;
      base = []; baseT = [];
      hist = new Int32Array(2101);
      for (x = 0; x < R.length; x++) {
        r = R[x];
        if (yz && !(r.a[5] === S.yd && ms.indexOf(r.a[6]) >= 0)) continue;
        t = 0;
        if (n) { t = tierOf(r, x, Q); if (t < 0) continue; }
        base.push(x); baseT.push(t);
        if (r.key > 0 && r.key <= 2100) hist[r.key]++;
      }
      if (tl && !yz) tl.setData(n ? hist : histAll, histAll);
    }
    var pos = [];
    for (var p = 0; p < base.length; p++) if (yz || inPer(R[base[p]])) pos.push(p);
    var cmp;
    if (yz) {
      cmp = function (p, q) {
        var A = R[base[p]], B = R[base[q]];
        var ba = A.a[7] ? 0 : 1, bb = B.a[7] ? 0 : 1;
        return (baseT[p] - baseT[q]) || (ba - bb) || (deathK(A) - deathK(B)) || (p - q);
      };
    } else if (S.sort === 'birth') {
      cmp = function (p, q) { return (baseT[p] - baseT[q]) || (birthK(R[base[p]]) - birthK(R[base[q]])); };
    } else if (S.sort === 'death') {
      cmp = function (p, q) { return (baseT[p] - baseT[q]) || (deathK(R[base[p]]) - deathK(R[base[q]])); };
    } else {
      cmp = function (p, q) { return (baseT[p] - baseT[q]); };   // סדר האינדקס = לפי שם (מיון יציב)
    }
    pos.sort(cmp);
    res = pos.map(function (p) { return base[p]; });
    renderList();
    renderMeta();
  }
  /* בזמן גרירת מברשת: חישוב מוגבל בקצב כדי שהגרירה תישאר חלקה */
  function computeSoon() {
    var wait = 70 - (Date.now() - lastRun);
    if (wait <= 0) { clearTimeout(runT); runT = 0; compute(); return; }
    if (!runT) runT = setTimeout(function () { runT = 0; compute(); }, wait);
  }

  /* דוגמאות מוכרות לטווח שנים (ל-tooltip של הציר): מעדיפים רשומות עם כינוי וספרים */
  function examples(lo, hi) {
    var k = lo + '|' + hi + '|' + baseKey;
    if (exCache.k === k) return exCache.v;
    var top = [];
    for (var p = 0; p < base.length; p++) {
      var r = R[base[p]];
      if (r.key < lo || r.key >= hi) continue;
      var sc = (r.a[2] ? 2 : 0) + (r.a[7] ? 1 : 0) + (r.a[3] && r.a[4] ? .5 : 0);
      if (sc < 2) continue;
      if (top.length < 3 || sc > top[top.length - 1][0]) {
        top.push([sc, base[p]]);
        top.sort(function (a, b) { return b[0] - a[0] || a[1] - b[1]; });
        if (top.length > 3) top.pop();
      }
    }
    var v = top.map(function (t) { var a = R[t[1]].a; return a[2] ? a[2].split(',')[0] : a[1]; });
    exCache = { k: k, v: v };
    return v;
  }

  /* ----- רינדור הרשימה ----- */
  function yrs(a) {
    var b = a[3], d = a[4];
    if (!b && !d) return '';                 // אין שנים ידועות — לא מציגים כלום (במקום "?")
    if (b && d) return b + '–' + d;
    return b ? 'נולד ' + b : 'נפטר ' + d;
  }
  function rowHtml(x, first) {
    var a = R[x].a;
    return '<div class="row rb-row' + (x === S.cur ? ' active' : '') + '" data-x="' + x + '" role="button" tabindex="' + (first ? 0 : -1) + '">' +
      '<span class="nm">' + h(a[1]) + (a[2] ? ' <small class="rb-k">' + h(a[2]) + '</small>' : '') + '</span>' +
      (yrs(a) ? '<span class="rb-yrs">' + h(yrs(a)) + '</span>' : '') + (R[x].e ? '<i class="rb-edot e' + R[x].e + '"></i>' : '') + '</div>';
  }
  function more() {
    var end = Math.min(shown + PAGE, res.length), s = '';
    for (var i = shown; i < end; i++) s += rowHtml(res[i], i === 0);
    el.list.insertAdjacentHTML('beforeend', s);
    shown = end;
  }
  function renderList() {
    el.list.innerHTML = '';
    shown = 0;
    el.scroll.scrollTop = 0;
    if (!res.length) {
      var tip = (S.q && !S.bio) ? '<div class="rb-tip">אפשר לסמן “חפש גם בטקסט הביוגרפיה”.</div>' : '';
      var act = (S.q || S.per !== 'all') ? '<button type="button" class="navbtn rb-reset">' + ic('reset', 16) + '<span>נקה סינונים</span></button>' : '';
      setStatus('<div>לא נמצאו תוצאות</div>' + tip + act, true, 'empty');
    } else {
      setStatus('');
      more();
    }
  }
  function perEra() { return PERS.filter(function (p) { return p.id === S.per && p.lo != null; })[0]; }
  /* תוכן חיווי הטווח (צ'יפ עם כפתור ניקוי): בכותרת הציר כשהוא פתוח, ובשורה נפרדת כשהוא מוסתר */
  function rangeHtml(n) {
    var lab = S.label ? bd(S.label) : '<bdi dir="ltr">' + S.lo + '–' + (S.hi - 1) + '</bdi>';
    return '<span class="rb-note-l">' + lab + '</span><span class="rb-note-c">' + n.toLocaleString('he') + ' רבנים</span>' +
      '<button type="button" class="rb-note-x" aria-label="נקה סינון" title="נקה סינון">' + ic('dismiss', 14) + '</button>';
  }
  function renderMeta() {
    var n = res.length, custom = S.per === 'custom', yz = S.mode === 'yz';
    el.count.textContent = n.toLocaleString('he') + ' רבנים';
    // חיווי הטווח: בכותרת הציר (פתוח) או בשורת note (מוסתר) — תמיד נראה כשיש סינון פעיל
    el.read.hidden = !(custom && !tlOff && !yz);
    el.note.hidden = !(custom && tlOff && !yz);
    if (custom) { if (!el.read.hidden) el.read.innerHTML = rangeHtml(n); if (!el.note.hidden) el.note.innerHTML = rangeHtml(n); }
    el.tlTitleHint.hidden = !el.read.hidden;
    // כותרת הרשימה
    var lab;
    if (yz) lab = 'יארצייט';
    else if (S.per === 'all') lab = 'כל התקופות';
    else if (S.per === 'none') lab = 'ללא שנה';
    else if (custom) lab = S.label || (S.lo + '–' + (S.hi - 1));
    else { var pp = PERS.filter(function (x) { return x.id === S.per; })[0]; lab = pp ? pp.t + ' · ' + pp.rng : ''; }
    el.lh.innerHTML = '<span class="lh-t">' + bd(lab) + '</span><span class="lh-n">' + n.toLocaleString('he') + '</span>';
    // צ'יפים (שורת התקופות כשהציר מוסתר + צ'יפ "ללא שנה" בכותרת הציר)
    view.querySelectorAll('.rb-chip').forEach(function (c) {
      var on = c.dataset.p === S.per;
      c.classList.toggle('on', on); c.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (tl && !yz) {
      var pe = perEra();
      if (custom) tl.setSel(S.lo, S.hi);
      else if (pe) tl.setSel(pe.lo, pe.hi);
      else tl.clearSel();
    }
    if (yz) {
      var isT = !!todayH && todayH.d === S.yd && todayH.m === S.ym;
      el.yzh.textContent = (isT ? 'יארצייט היום' : 'יארצייט') + ' — ' + gm(S.yd) + ' ' + MON[S.ym] +
        (isT && todayH.y ? ' ' + gm(todayH.y % 1000) : '');
      el.yzb.hidden = isT;
    }
  }

  /* הצגה/הסתרה של אזור הציר (עם שמירה ב-localStorage) */
  function syncChrome(animate) {
    var yz = S.mode === 'yz';
    el.tlBox.classList.toggle('off', tlOff || yz);
    el.tlBox.hidden = false;
    if (animate) {
      el.tlBox.classList.add('moving'); clearTimeout(tlMoveT);
      tlMoveT = setTimeout(function () { el.tlBox.classList.remove('moving'); }, 320);
    }
    if (tlOff || yz) el.tlBox.setAttribute('inert', ''); else el.tlBox.removeAttribute('inert');
    el.tlBox.setAttribute('aria-hidden', (tlOff || yz) ? 'true' : 'false');
    el.tlBtn.setAttribute('aria-expanded', tlOff ? 'false' : 'true');
    el.tlBtn.classList.toggle('is-off', tlOff);
    el.tlBtn.disabled = yz;
    el.tlBtn.querySelector('.tt').textContent = tlOff ? 'הצג ציר' : 'הסתר ציר';
    el.tlBtn.title = tlOff ? 'הצג את ציר הדורות' : 'הסתר את ציר הדורות';
    el.chips.hidden = yz || !tlOff;      // כשהציר פתוח, פס התקופות שבציר משמש כסינון תקופה
    if (ready) renderMeta();
    if (!tlOff && !yz && tl) tl.refresh();
  }
  function setTlOff(v, animate) {
    tlOff = !!v;
    try { localStorage.setItem(LS_KEY, tlOff ? '1' : '0'); } catch (e) { /* ללא שמירה */ }
    syncChrome(animate);
  }

  /* ----- כרטיס רב ----- */
  function openCard(x) {
    var tok = ++openTok;
    S.cur = x;
    el.body.querySelectorAll('.rb-row.active').forEach(function (r) { r.classList.remove('active'); });
    var row = el.list.querySelector('.rb-row[data-x="' + x + '"]');
    if (row) row.classList.add('active');
    view.classList.add('show-detail');
    el.dp.scrollTop = 0;
    var a = R[x].a;
    if (tl) tl.setCurrent(R[x].key);        // סימון הרב הפתוח על הציר
    el.dc.innerHTML = '<div class="rb-msg">טוען…</div>';
    loadShard(a[10]).then(function (arr) {
      if (tok !== openTok) return;
      showCard(x, findRec(arr, a[0]));
    }).catch(function () {
      if (tok !== openTok) return;
      el.dc.innerHTML = '<div class="rb-msg">שגיאה בטעינת הנתונים. <button type="button" class="navbtn rb-retry" data-x="' + x + '">נסה שוב</button></div>';
    });
  }
  /* פס חיים: מיקום הרב על ציר התקופות (מקשר בין הכרטיס לציר הדורות) */
  function pctR(y) { return Math.max(0, Math.min(100, (y - F0) / (F1 - F0) * 100)); }   // מרחק מהימין (הקדום מימין)
  function winStyle(lo, hi) {
    var r = pctR(lo), l = pctR(hi);
    return 'right:' + r + '%;width:' + Math.max(0, l - r) + '%';
  }
  function lifeStrip(r) {
    var a = r.a;
    if (r.key <= 0) return '';
    var b0 = a[3] > 0 ? a[3] : r.key, d0 = a[4] > 0 ? a[4] : b0 + 1;
    var segs = ERAS.map(function (e) {
      var lo = Math.max(e.lo, F0), hi = Math.min(e.hi, F1);
      return hi > lo ? '<i class="e' + e.e + '" style="' + winStyle(lo, hi) + '"></i>' : '';
    }).join('');
    var lo = Math.max(b0, F0), hi = Math.max(Math.min(d0, F1), lo + 3);
    return '<div class="rb-life" aria-hidden="true"><div class="bar">' + segs + '<b style="' + winStyle(lo, hi) + '"></b></div>' +
      '<div class="ends"><span>' + F0 + '</span><span>' + F1 + '</span></div></div>';
  }
  function fact(label, val) { return val ? '<div class="rb-f"><b>' + label + '</b><span>' + val + '</span></div>' : ''; }
  function lifeVal(txt, yr, place) {
    var v = txt ? h(txt) : '';
    if (yr) v += v ? ' (' + yr + ')' : String(yr);
    if (place) v += (v ? ' · ' : '') + h(place);
    return v;
  }
  function showCard(x, rec) {
    rec = rec || {};
    var r = R[x], a = r.a;
    if (rec.n && rec.n !== a[1]) rec = {};          // הגנה: כרטיס שאינו תואם לשורה שנבחרה — לא מציגים עליו פרטים של רב אחר
    var name = rec.n || a[1];
    var yzv = (a[5] > 0 && a[6] >= 0) ? '<a class="rb-yzl" data-d="' + a[5] + '" data-m="' + a[6] + '">' + gm(a[5]) + ' ' + h(MON[a[6]]) + '</a>' : '';
    var bk = rec.bk;
    if (!bk || !bk.length) bk = a[7] ? a[7].split('; ').map(function (t) { return [t, '']; }) : [];
    curBooks = bk;
    var books = '';
    if (bk.length) {
      books = '<h3 class="rb-h">ספרים (' + bk.length + ')</h3><div class="rb-books">' + bk.map(function (b, i) {
        return '<button type="button" class="rb-book" data-k="' + i + '">' + ic('book', 16) + '<span>' + h(b[0]) + (b[1] ? ' <small>' + h(b[1]) + '</small>' : '') + '</span></button>';
      }).join('') + '</div>';
    }
    var role = rec.r || a[9] || '';
    el.dc.innerHTML =
      '<div class="detail-head"><span class="detail-ic">' + ic('person', 26) + '</span>' +
      '<div class="detail-head-t"><h2 class="detail-name">' + h(name) + '</h2>' +
      (role ? '<div class="detail-sub">' + h(role) + '</div>' : '') + '</div></div>' +
      lifeStrip(r) +
      '<div class="rb-facts">' +
      fact('כינוי', h(rec.k || a[2])) + fact('אב', h(rec.f)) +
      fact('נולד', lifeVal(rec.bt, a[3], rec.bp)) +
      fact('נפטר', lifeVal(rec.dt, a[4], rec.dp)) +
      fact('יארצייט', yzv) + '</div>' +
      '<div class="rb-acts">' +
      (r.key > 0 ? '<button type="button" class="navbtn rb-gen">' + ic('calendar', 16) + '<span>בני דורו</span></button>' : '') + '</div>' +
      (rec.b ? '<div class="body rb-bio-t">' + h(rec.b) + '</div>' : '') +
      (rec.s ? '<div class="rb-src"><b>מקורות:</b> ' + rec.s.split('; ').map(function (t, i) {
        return '<span class="rb-srcitem" data-i="' + i + '">' + h(t) + '</span>';
      }).join(' · ') + '</div>' : '') +
      books;
    if (rec.s) markSources(rec.s.split('; '));
  }

  /* מקור (ספר עיון) שקיים בספריית אוצריא הופך ללחיץ; השאר נשארים טקסט. הבדיקה אסינכרונית ולא חוסמת. */
  var srcTok = 0;
  function srcTitle(t) {
    return cleanTitle(String(t).replace(/\s+\d[\d\s,\-–]*$/, '').replace(/\s+ח["״']?[א-ת]{1,2}(\s.*)?$/, ''));
  }
  function markSources(list) {
    var tok = ++srcTok, O = window.Otzaria;
    if (!O || !O.call) return;
    list.slice(0, 12).forEach(function (t, i) {
      findBookByTitle(srcTitle(t)).then(function (b) {
        if (tok !== srcTok || !b) return;
        var n = el.dc.querySelector('.rb-srcitem[data-i="' + i + '"]');
        if (n) { n.classList.add('ok'); n.title = 'פתח באוצריא: ' + b.title; n.dataset.id = b.bookId; }
      });
    });
  }

  /* ----- פתיחת ספר באוצריא לפי כותר ----- */
  function nrmT(s) { return nrm(s).replace(/\s/g, ''); }
  function cleanTitle(t) {
    t = String(t || '');
    t = t.split(/\s+[-–—]+\s+|\s*[(\[{]|\s+["״“]/)[0];
    return t.replace(/[\s,.;:\-–—]+$/, '').trim();
  }
  /* מחזיר את הספר המתאים ביותר בספריית אוצריא לפי כותר, או null */
  async function findBookByTitle(title) {
    var O = window.Otzaria;
    if (!O || !O.call) return null;
    var q = cleanTitle(title);
    if (!q) return null;
    var cands = [q];
    var q2 = q.replace(/["'׳״]/g, '');
    if (q2 && q2 !== q) cands.push(q2);
    try {
      for (var c = 0; c < cands.length; c++) {
        var r = await O.call('library.findBooks', { query: cands[c], limit: 12 });
        var books = (r && r.success && r.data) ? r.data : [];
        var nq = nrmT(cands[c]), best = null, bs = 0;
        books.forEach(function (b) {
          var nt = nrmT(b.title), s = 0;
          if (nt === nq) s = 100;
          else if (nt.indexOf(nq) === 0) s = 60;
          else if (nt.indexOf(nq) >= 0) s = 40;
          else if (nt.length >= 4 && nq.indexOf(nt) >= 0) s = 30;
          if (s > bs) { bs = s; best = b; }
        });
        if (best) return best;
      }
    } catch (e) { /* שקט */ }
    return null;
  }
  async function openBookByTitle(title) {
    var O = window.Otzaria;
    if (!O || !O.call) return;
    var best = await findBookByTitle(title);
    try {
      if (best) await O.call('reader.openBook', { bookId: best.bookId, index: 0 });
      else await O.call('ui.showMessage', { message: 'לא נמצא באוצריא: ' + title });
    } catch (e) { /* שקט */ }
  }
  window.rbOpenBookByTitle = openBookByTitle;

  /* ----- חיפוש בטקסט הביוגרפיה: טעינה הדרגתית של כל הקבצים ----- */
  var bioRun = false;
  function loadedCount() { return Object.keys(shardCache).length; }
  function updProg() {
    if (!S.bio) { el.prog.textContent = ''; return; }
    var n = loadedCount();
    el.prog.textContent = n >= nFiles ? 'כל הביוגרפיות נטענו' : 'טוען ביוגרפיות… ' + n + '/' + nFiles;
  }
  function loadBios() {
    if (bioRun || !ready) return;
    bioRun = true;
    var next = 0, fresh = 0, fail = 0;
    function worker() {
      if (next >= nFiles || !S.bio) return Promise.resolve();
      var f = next++, had = !!shardCache[f];
      return loadShard(f).catch(function () { fail++; }).then(function () {
        if (!had) fresh++;
        updProg();
        if (fresh && fresh % 4 === 0 && S.q) compute();
        return worker();
      });
    }
    Promise.all([worker(), worker()]).then(function () {
      bioRun = false;
      updProg();
      if (fail) el.prog.textContent += ' (' + fail + ' נכשלו)';
      if (S.q) compute();
    });
  }

  /* ----- שליטה בתצוגה ----- */
  function setMode(m) {
    if (m === 'tl') m = 'list';               // תאימות: הציר תמיד חלק מתצוגת הרשימה
    S.mode = m;
    el.modes.querySelectorAll('.rb-mode').forEach(function (b) {
      var on = b.dataset.m === m; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    view.classList.remove('rb-m-list', 'rb-m-yz');
    view.classList.add('rb-m-' + m);
    el.yz.hidden = m !== 'yz';
    el.sortw.hidden = m === 'yz';
    if (m === 'yz') setToday();
    syncChrome(false);
    compute();
  }
  function setPer(id) {
    var p = PERS.filter(function (x) { return x.id === id; })[0];
    S.per = id; S.label = '';
    if (p && p.lo != null) { S.lo = p.lo; S.hi = p.hi; }
    compute();
  }
  function setRange(lo, hi, label) {
    S.per = 'custom'; S.lo = lo; S.hi = hi; S.label = label;
    compute();
  }
  function onBrush(lo, hi, preview) {
    S.per = 'custom'; S.lo = lo; S.hi = hi; S.label = '';
    if (preview) computeSoon(); else { clearTimeout(runT); runT = 0; compute(); }
  }
  function buildLandmarks() {
    var out = [];
    LANDMARKS.forEach(function (m) {
      var x = nameToX.get(m[0]);
      if (x == null || !(R[x].key > 0)) return;
      out.push({ x: x, y: R[x].key, d: R[x].a[4] || 0, s: m[1], full: R[x].a[2] ? R[x].a[2].split(',')[0] + ' — ' + R[x].a[1] : R[x].a[1], pr: m[2] });
    });
    out.sort(function (a, b) { return a.pr - b.pr || a.y - b.y; });
    out.forEach(function (m, i) { m.i = i; });
    return out;
  }

  function build() {
    try { tlOff = localStorage.getItem(LS_KEY) === '1'; } catch (e) { tlOff = false; }
    view.innerHTML =
      '<div class="rb-tools">' +
        '<div class="rb-seg" id="rbModes" role="tablist">' +
          '<button type="button" class="rb-mode on" role="tab" aria-selected="true" data-m="list"><span class="ck">' + ic('check', 16) + '</span><span class="mi">' + ic('list', 18) + '</span><span>רשימה</span></button>' +
          '<button type="button" class="rb-mode" role="tab" aria-selected="false" data-m="yz"><span class="ck">' + ic('check', 16) + '</span><span class="mi">' + ic('calendar', 18) + '</span><span>יארצייט היום</span></button>' +
        '</div>' +
        '<button type="button" class="rb-tlbtn" id="rbTlBtn" aria-controls="rbTlBox" aria-expanded="true"><span class="ti">' + ic('chart', 18) + '</span><span class="tt">הסתר ציר</span><span class="tc">' + ic('chevron_up', 16) + '</span></button>' +
      '<div class="rb-chips" id="rbChips" role="group" aria-label="סינון לפי תקופה" hidden>' + PERS.map(function (p) {
        return '<button type="button" class="rb-chip' + (p.id === 'all' ? ' on' : '') + '" data-p="' + p.id + '" aria-pressed="' + (p.id === 'all') + '">' +
          (p.e ? '<i class="rb-edot e' + p.e + '"></i>' : '') + '<span>' + h(p.t) + '</span>' + (p.rng ? '<small>' + ltr(p.rng) + '</small>' : '') + '</button>';
      }).join('') + '</div>' +
        '<span class="rb-grow"></span>' +
        '<label class="rb-sortw" id="rbSortW"><span class="si">' + ic('sort', 18) + '</span><span>מיון</span> <select id="rbSort">' +
          '<option value="name">לפי שם</option><option value="birth">לפי שנת לידה</option><option value="death">לפי שנת פטירה</option>' +
        '</select></label>' +
        '<label class="rb-bio"><input type="checkbox" id="rbBio"> <span class="sw"></span><span>חפש גם בטקסט הביוגרפיה</span></label>' +
        '<span class="rb-prog" id="rbProg" aria-live="polite"></span>' +
      '</div>' +
      '<div class="rb-tlbox' + (tlOff ? ' off' : '') + '" id="rbTlBox"><div class="rb-tlin"><div class="rb-tl" id="rbTl"></div></div></div>' +
      '<div class="rb-yz" id="rbYz" hidden>' +
        '<div class="rb-yz-h" id="rbYzH"></div>' +
        '<div class="rb-yz-c"><label><span>יום</span> <select id="rbYd"></select></label>' +
        '<label><span>חודש</span> <select id="rbYm"></select></label>' +
        '<button type="button" class="navbtn" id="rbYzB">היום</button></div>' +
      '</div>' +
      '<div class="rb-note" id="rbNote" hidden></div>' +
      '<div class="rb-body" id="rbBody">' +
        '<section class="rb-lp"><div class="rb-lh" id="rbLh"></div><div class="rb-scroll" id="rbScroll"><div class="empty rb-status" id="rbStatus"></div><div id="rbList" role="list"></div></div></section>' +
        '<section class="rb-dp" id="rbDp">' +
          '<div class="detail-nav rb-nav"><button type="button" class="navbtn navlist" id="rbBack"></button></div>' +
          '<div class="dcontent" id="rbDc"><div class="placeholder"><span class="big">' + ic('people', 44) + '</span><div>בחר רב מהרשימה</div></div></div>' +
        '</section>' +
      '</div>';
    el.modes = document.getElementById('rbModes');
    el.tlBtn = document.getElementById('rbTlBtn');
    el.tlBox = document.getElementById('rbTlBox');
    el.tlHost = document.getElementById('rbTl');
    el.lh = document.getElementById('rbLh');
    el.sortw = document.getElementById('rbSortW');
    el.sort = document.getElementById('rbSort');
    el.bio = document.getElementById('rbBio');
    el.prog = document.getElementById('rbProg');
    el.chips = document.getElementById('rbChips');
    el.yz = document.getElementById('rbYz');
    el.yzh = document.getElementById('rbYzH');
    el.yzb = document.getElementById('rbYzB');
    el.yd = document.getElementById('rbYd');
    el.ym = document.getElementById('rbYm');
    el.note = document.getElementById('rbNote');
    el.body = document.getElementById('rbBody');
    el.scroll = document.getElementById('rbScroll');
    el.status = document.getElementById('rbStatus');
    el.list = document.getElementById('rbList');
    el.dp = document.getElementById('rbDp');
    el.dc = document.getElementById('rbDc');
    el.count = document.getElementById('rbCount');
    el.q = document.getElementById('rbQ');
    el.clear = document.getElementById('rbClear');
    document.getElementById('rbBack').innerHTML = ic('arrow_right', 16) + '<span>לרשימה</span>';
    view.classList.add('rb-m-list');

    /* ציר הדורות (rb-timeline.js) */
    tl = window.RbTimeline.create(el.tlHost, {
      eras: ERAS, gm: gm, icon: ic,
      getPer: function () { return S.per; },
      onSelect: onBrush,
      onClear: function () { setPer('all'); },
      onEra: function (id) { setPer(S.per === id ? 'all' : id); },
      onLandmark: function (x) { openCard(x); },
      examples: examples
    });
    /* בכותרת הציר: חיווי הטווח הנבחר + צ'יפ "ללא שנה" (לא ניתן לבחירה בציר עצמו) */
    tl.slot.innerHTML = '<span class="rb-read" id="rbRead" hidden></span>' +
      '<button type="button" class="rb-chip rb-chip-s" data-p="none" aria-pressed="false"><span>ללא שנה</span></button>';
    el.read = document.getElementById('rbRead');
    el.tlTitleHint = el.tlHost.querySelector('.rb-tlc-title small');

    var o = '';
    for (var d = 1; d <= 30; d++) o += '<option value="' + d + '">' + gm(d) + '</option>';
    el.yd.innerHTML = o;
    o = '';
    MON.forEach(function (m, i) { o += '<option value="' + i + '">' + h(m) + '</option>'; });
    el.ym.innerHTML = o;
    el.yd.value = 1; el.ym.value = 0;
    wire();
    syncChrome(false);
  }

  function wire() {
    view.addEventListener('click', function (e) {
      var t = e.target;
      var c;
      if ((c = t.closest('.rb-row'))) { openCard(+c.dataset.x); return; }
      if ((c = t.closest('.rb-srcitem.ok'))) { var O = window.Otzaria; if (O && O.call) O.call('reader.openBook', { bookId: c.dataset.id, index: 0 }); return; }
      if ((c = t.closest('.rb-book'))) { var b = curBooks[+c.dataset.k]; if (b) openBookByTitle(b[0]); return; }
      if (t.closest('#rbTlBtn')) { setTlOff(!tlOff, true); return; }
      if ((c = t.closest('.rb-mode'))) { setMode(c.dataset.m); return; }
      if ((c = t.closest('.rb-chip'))) { setPer(S.per === c.dataset.p && c.dataset.p !== 'all' ? 'all' : c.dataset.p); return; }
      if (t.closest('.rb-note-x')) { setPer('all'); return; }
      if (t.closest('.rb-reset')) { el.q.value = ''; S.q = ''; el.clear.hidden = true; setPer('all'); return; }
      if (t.closest('#rbBack')) { view.classList.remove('show-detail'); return; }
      if ((c = t.closest('.rb-retry'))) { openCard(+c.dataset.x); return; }
      if (t.closest('#rbYzB')) { setToday(); compute(); return; }
      if ((c = t.closest('.rb-yzl'))) {
        var yd = +c.dataset.d, ym = +c.dataset.m;
        setMode('yz');              // מאפס לתאריך של היום
        S.yd = yd; S.ym = ym;
        el.yd.value = yd; el.ym.value = ym;
        compute();
        view.classList.remove('show-detail');
        return;
      }
      if (t.closest('.rb-gen')) {
        var r = R[S.cur];
        if (!r || r.key <= 0) return;
        S.sort = 'birth'; el.sort.value = 'birth';
        el.q.value = ''; S.q = ''; el.clear.hidden = true;
        setMode('list');
        setRange(r.key - 15, r.key + 16, 'בני דורו של ' + r.a[1] + ': ' + (r.key - 15) + '–' + (r.key + 15));
        if (tl) tl.zoomTo(r.key - 120, r.key + 120);     // "בני דורו" מגדיל את הציר סביב הרב
        view.classList.remove('show-detail');
      }
    });
    /* מקלדת: חיצים בין שורות; Enter/רווח פותח כרטיס או קישור יארצייט */
    view.addEventListener('keydown', function (e) {
      var t = e.target, row = t.closest && t.closest('.rb-row');
      if (row) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCard(+row.dataset.x); return; }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          var n = e.key === 'ArrowDown' ? row.nextElementSibling : row.previousElementSibling;
          if (n && n.classList.contains('rb-row')) { row.tabIndex = -1; n.tabIndex = 0; n.focus(); }
          else if (e.key === 'ArrowDown' && shown < res.length) more();
        }
        return;
      }
      if ((e.key === 'Enter' || e.key === ' ') && t.classList && t.classList.contains('rb-yzl')) { e.preventDefault(); t.click(); }
    });
    el.sort.addEventListener('change', function () { S.sort = el.sort.value; compute(); });
    el.bio.addEventListener('change', function () {
      S.bio = el.bio.checked;
      updProg();
      if (S.bio) loadBios();
      if (S.q) compute();
    });
    el.yd.addEventListener('change', function () { S.yd = +el.yd.value; compute(); });
    el.ym.addEventListener('change', function () { S.ym = +el.ym.value; compute(); });
    el.scroll.addEventListener('scroll', function () {
      if (shown < res.length && el.scroll.scrollTop + el.scroll.clientHeight > el.scroll.scrollHeight - 500) more();
    }, { passive: true });
    el.q.addEventListener('input', function () {
      el.clear.hidden = !el.q.value;
      clearTimeout(searchT);
      searchT = setTimeout(function () { S.q = el.q.value; compute(); }, 140);
    });
    el.clear.addEventListener('click', function () {
      el.q.value = ''; el.clear.hidden = true; S.q = ''; compute(); el.q.focus();
    });
  }

  /* ----- אתחול: טעינת האינדקס בלחיצה הראשונה ----- */
  function loadIndex() {
    setStatus('טוען את מאגר הרבנים… (כ-5MB, רק בפעם הראשונה)', false, 'load');
    var p = window.RB_INDEX ? Promise.resolve() : loadScript(BASE + 'rb-index.js');
    p.then(prepare).then(function () {
      ready = true;
      setStatus('');
      if (tl) tl.setLandmarks(buildLandmarks());
      if (S.mode === 'yz') setToday();
      S.q = el.q.value;
      baseKey = '';
      if (S.mode !== 'yz' && tl) tl.setData(histAll, histAll);
      compute();
      var none = el.tlHost.querySelector('.rb-chip[data-p="none"] span');
      if (none) none.textContent = 'ללא שנה · ' + noYear.toLocaleString('he');
      var none2 = el.chips.querySelector('[data-p="none"] span');
      if (none2) none2.textContent = 'ללא שנה';
    }).catch(function () {
      R = []; idToX = new Map(); nameToX = new Map(); nFiles = 0;
      setStatus('<div>שגיאה בטעינת נתוני הרבנים.</div><button type="button" class="navbtn" id="rbReload">נסה שוב</button>', true, 'err');
      var b = document.getElementById('rbReload');
      if (b) b.onclick = loadIndex;
    });
  }

  window.rbCurrentName = function () {
    return (ready && S.cur >= 0 && R[S.cur]) ? R[S.cur].a[1] : '';
  };

  window.initRabbis = function () {
    if (inited) return;
    inited = true;
    view = document.getElementById('rbView');
    if (!view) return;
    build();
    var si = document.getElementById('rbSIcon');
    if (si) si.innerHTML = ic('search', 18);
    el.clear.innerHTML = ic('dismiss', 16);
    loadIndex();
  };
})();

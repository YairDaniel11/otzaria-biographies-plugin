/* ===========================================================================
 *  מנוע משותף לשלושת המוקאפים — ביוגרפיות תנאים ואמוראים
 *  (קוד הדגמה לבחירת פריסה; בתוסף האמיתי ההגיון יעבור ל-js/app.js)
 * ========================================================================= */

const DATA = (window.BIO_DATA || []);

/* ----- נרמול שם לצורך התאמת הפניות "ע"ע" ----- */
function normName(s) {
  return String(s)
    .replace(/\([^)]*\)/g, '')                 // הסרת מספר בסוגריים (7)
    .replace(/["'’]/g, '')                      // הסרת גרשיים/גרש
    .replace(/^(רבי|רבנא|רבן|רב|ר|מר)\s+/, '')   // הסרת תואר מוביל
    .replace(/\s+/g, ' ')
    .trim();
}

/* אינדקס שם -> מזהה ערך */
const NAME_INDEX = new Map();
DATA.forEach(e => {
  const plain = String(e.n).replace(/\([^)]*\)/g, '').trim();
  [normName(e.n), plain].forEach(k => {
    if (k && !NAME_INDEX.has(k)) NAME_INDEX.set(k, e.i);
  });
});

function findEntryByName(raw) {
  const t = String(raw).trim().replace(/[.;,]+$/, '');
  if (NAME_INDEX.has(t)) return NAME_INDEX.get(t);
  const n = normName(t);
  return NAME_INDEX.has(n) ? NAME_INDEX.get(n) : null;
}

/* ----- escape בסיסי (משאיר גרשיים, מטפל ב-< > &) ----- */
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ----- זיהוי מקור ש"ס בתוך סוגריים ----- */
function isSource(inner) {
  const s = inner.trim();
  if (/^\d+$/.test(s)) return false;                       // (7)
  if (/^ע"ע/.test(s)) return false;                        // (ע"ע)
  if (/^(שם|עיין שם|ע"ש|וכו'?|כנ"ל|וע"ע)$/.test(s)) return false;
  if (!/[א-ת]/.test(s)) return false;
  // קישור רק אם נראה כמו ציטוט אמיתי: כולל סימן דף/פרק/הלכה (גרשיים) או גרש
  // (כך הערה מסבירה כמו "כי חשב שמצווה..." לא תהפוך לקישור)
  return /["']/.test(s);
}

/* ----- קישור-אוטומטי לשמות חכמים המוזכרים בטקסט -----
   (א) שמות-כינוי ללא שם-אב  -> התאמה מדויקת (לפחות 2 מילים).
   (ב) שמות עם שם-אב (בן/בר/בריה דְ…) -> התאמה גמישה על השם הפרטי
       (עד 2 שינויי-אות, כולל חילוף אותיות סמוכות), בתנאי ששם-האב זהה במדויק.
   כך מקושרים וריאנטים של כתיב (חנניה≈חנינא, יהושוע≈יהושע) בלי לקשר שמות שונים.
   שמות נפוצים בני מילה אחת (אביי, רבא, "רבי יוחנן", "רב הונא") לא מקושרים. */
const TITLE_RE = /^(רבי|רבנא|רבן|רב|ר'|ר|מר)\s+/;
const TITLE_OPT = '(?:(?:רבי|רבנא|רבן|רב|ר\'|ר|מר)\\s+)?';
const MARKERS = new Set(['בן', 'בר', 'ברבי', 'בריה', 'אבוה', 'אחוה', 'בני', 'ברת', 'ברתיה']);

const EXACT_MAP = new Map();    // גרעין-שם -> id  (ללא שם-אב)
const PATRON_MAP = new Map();   // שם-אב -> [{ first, id }]

DATA.forEach(e => {
  const disp = String(e.n).replace(/\([^)]*\)/g, '').trim();
  const core = disp.replace(TITLE_RE, '').trim();
  const words = core.split(/\s+/);
  let mi = -1;
  for (let k = 1; k < words.length; k++) { if (MARKERS.has(words[k])) { mi = k; break; } }
  if (mi >= 1) {
    const first = words[mi - 1];
    const remainder = words.slice(mi).join(' ');
    if (first.length >= 3 && remainder.length >= 4) {
      if (!PATRON_MAP.has(remainder)) PATRON_MAP.set(remainder, []);
      PATRON_MAP.get(remainder).push({ first, id: e.i });
    }
  } else if (core.length >= 9 && words.length >= 2) {
    if (!EXACT_MAP.has(core)) EXACT_MAP.set(core, e.i);
  }
});

function reAlt(keys) {
  return keys.sort((a, b) => b.length - a.length)
    .map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
}
const EXACT_RE = EXACT_MAP.size
  ? new RegExp('(?<![א-ת"\'])' + TITLE_OPT + '(' + reAlt([...EXACT_MAP.keys()]) + ')(?![א-ת"\'])', 'g')
  : null;
const PATRON_RE = PATRON_MAP.size
  ? new RegExp('(?<![א-ת"\'])(' + TITLE_OPT + '[א-ת\'"]{2,})\\s+(' + reAlt([...PATRON_MAP.keys()]) + ')(?![א-ת"\'])', 'g')
  : null;

/* מרחק עריכה (Optimal String Alignment): חילוף אותיות סמוכות נחשב שינוי אחד */
function osaDist(a, b) {
  if (a === b) return 0;
  const m = a.length, n = b.length;
  if (Math.abs(m - n) > 2) return 9;
  const d = [];
  for (let i = 0; i <= m; i++) d[i] = [i];
  for (let j = 0; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[m][n];
}

/* ----- הפיכת גוף הביוגרפיה ל-HTML עם קישורים ----- */
function renderBody(raw) {
  let s = esc(raw);
  const store = [];
  const hold = html => { store.push(html); return '' + (store.length - 1) + ''; };

  // 1) מקורות ש"ס בסוגריים -> קישור לאוצריא  (מוגנים מקישור-אוטומטי)
  s = s.replace(/\(([^)]+)\)/g, (m, inner) => {
    if (!isSource(inner)) return m;
    return '(' + hold('<a class="src" data-src="' + encodeURIComponent(inner) + '">' + inner + '</a>') + ')';
  });

  // 2) הפניות מפורשות:  ע"ע <שם>; <שם>  (מקשר גם שמות קצרים)
  s = s.replace(/ע"ע\s+([^.()]+)/g, (m, names) => {
    const parts = names.split(/;/).map(p => {
      const t = p.trim();
      if (!t) return p;
      const id = findEntryByName(t);
      return id != null ? hold('<a class="xref" data-goto="' + id + '">' + t + '</a>') : t;
    });
    return 'ע"ע ' + parts.join('; ');
  });

  // 3) שמות עם שם-אב: התאמה גמישה על השם הפרטי, כששם-האב זהה במדויק
  if (PATRON_RE) {
    s = s.replace(PATRON_RE, (m, namePart, remainder) => {
      const cand = namePart.replace(TITLE_RE, '').trim();
      const list = PATRON_MAP.get(remainder) || [];
      let best = null, bestD = 99;
      for (const o of list) { const d = osaDist(cand, o.first); if (d < bestD) { bestD = d; best = o; } }
      const ok = best && (bestD === 0 || (cand.length >= 4 && bestD <= 2));
      return ok ? hold('<a class="xref" data-goto="' + best.id + '">' + m + '</a>') : m;
    });
  }

  // 4) שמות-כינוי ללא שם-אב: התאמה מדויקת
  if (EXACT_RE) {
    s = s.replace(EXACT_RE, (m, core) => {
      const id = EXACT_MAP.get(core);
      return id != null ? hold('<a class="xref" data-goto="' + id + '">' + m + '</a>') : m;
    });
  }

  // שחזור העוגנים השמורים
  s = s.replace(/(\d+)/g, (_, i) => store[+i]);
  return s;
}

/* פיצול שם ל-(תצוגה, מספר) */
function splitName(n) {
  const m = String(n).match(/^(.*?)\s*\((\d+)\)\s*$/);
  return m ? { name: m[1], count: m[2] } : { name: String(n), count: null };
}

/* ----- פתיחת מקור: במוקאפ רק טוסט; בתוסף -> reader.openBookAtRef ----- */
function openInOtzaria(src) {
  toast('🔗 ייפתח באוצריא:  ' + src);
  /* בתוסף האמיתי:
     const book = parseCitation(src);                       // book + ref
     const { data } = await Otzaria.call('library.findBooks', { query: book.title, limit: 1 });
     if (data && data[0]) await Otzaria.call('reader.openBookAtRef', { bookId: data[0].bookId, ref: book.ref });
  */
}

/* ===========================================================================
 *  גלילה אופקית עם משטח מגע
 *  בעמוד RTL כמו זה, ה-WebView של אוצריא מספק לעיתים deltaX בסימן הפוך,
 *  והתוצאה היא גלילה לצד הנגדי לזה שאליו מזיזים את האצבעות. במקום להישען
 *  על התנהגות ברירת המחדל, אנחנו מטפלים בגלילה האופקית בעצמנו: הגדלת
 *  scrollLeft פירושה תמיד תזוזה ימינה פיזית — גם במיכל LTR (0..max) וגם
 *  במיכל RTL (‎-max..0) — ולכן המיפוי הזה נכון בשתי התצוגות.
 * ========================================================================= */
function scrollableXAncestor(node) {
  for (let el = node; el && el !== document.documentElement; el = el.parentElement) {
    if (el.nodeType !== 1) continue;
    if (el.scrollWidth - el.clientWidth <= 1) continue;
    const overflowX = getComputedStyle(el).overflowX;
    if (overflowX === 'auto' || overflowX === 'scroll') return el;
  }
  return null;
}

function installHorizontalScrollFix() {
  window.addEventListener('wheel', ev => {
    const dx = ev.deltaX || (ev.shiftKey ? ev.deltaY : 0);
    if (!dx || ev.ctrlKey) return;
    const el = scrollableXAncestor(ev.target);
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    /* במיכל RTL הטווח הוא ‎-max..0 ובמיכל LTR הוא 0..max.
       בקצה — משאירים את האירוע לדפדפן כדי לא לחסום גלילה של ההורה. */
    const rtl = getComputedStyle(el).direction === 'rtl';
    const next = Math.max(rtl ? -max : 0, Math.min(rtl ? 0 : max, el.scrollLeft + dx));
    if (next === el.scrollLeft) return;
    el.scrollLeft = next;
    ev.preventDefault();
  }, { passive: false });
}

/* ----- טוסט ----- */
let _toastT = null;
function toast(msg) {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastT);
  _toastT = setTimeout(() => el.classList.remove('show'), 2600);
}

/* ===========================================================================
 *  מנוע רשימה עם חיפוש, כותרות אותיות וגלילה אינסופית (windowing)
 * ========================================================================= */
function createList(scrollEl, listEl, onOpen) {
  // מרנדרים את כל הערכים המסוננים בבת אחת — כך פס הגלילה משקף את גובה התוכן האמיתי
  // (במקום גלילה אינסופית/windowing שבה הגלילן "קפץ" כשנטענו עוד שורות).
  const BATCH = Infinity;
  let filtered = DATA;
  let rendered = 0;
  let lastLetter = null;

  function matches(e, q) {
    if (e.n.indexOf(q) !== -1 || e.b.indexOf(q) !== -1) return true;
    // חיפוש גם בשדות ההעשרה (סוג / דור / מקום) של תנאים ואמוראים נבחרים
    const en = (window.BIO_ENRICH || {})[e.i];
    if (en && ((en.place && en.place.indexOf(q) !== -1) ||
               (en.dor && en.dor.indexOf(q) !== -1) ||
               (en.type && en.type.indexOf(q) !== -1))) return true;
    return false;
  }

  function reset(q) {
    q = (q || '').trim();
    filtered = q ? DATA.filter(e => matches(e, q)) : DATA;
    rendered = 0;
    lastLetter = null;
    listEl.innerHTML = '';
    if (!filtered.length) {
      listEl.innerHTML = '<div class="empty">לא נמצאו ערכים</div>';
    }
    renderMore();
    scrollEl.scrollTop = 0;
    updateCount();
  }

  function renderMore() {
    const frag = document.createDocumentFragment();
    const end = Math.min(rendered + BATCH, filtered.length);
    for (let i = rendered; i < end; i++) {
      const e = filtered[i];
      if (e.l !== lastLetter) {
        lastLetter = e.l;
        const h = document.createElement('div');
        h.className = 'letter';
        h.textContent = 'אות ' + e.l;
        frag.appendChild(h);
      }
      const sp = splitName(e.n);
      const row = document.createElement('div');
      row.className = 'row';
      row.dataset.id = e.i;
      row.innerHTML = '<span class="nm">' + esc(sp.name) + '</span>';
      frag.appendChild(row);
    }
    rendered = end;
    listEl.appendChild(frag);
    sentinel(); // ודא שה-sentinel בסוף
  }

  let sEl = null, io = null;
  function sentinel() {
    if (sEl) sEl.remove();
    if (rendered >= filtered.length) return;
    sEl = document.createElement('div');
    sEl.style.height = '1px';
    listEl.appendChild(sEl);
    if (!io) {
      io = new IntersectionObserver(es => {
        if (es.some(x => x.isIntersecting)) renderMore();
      }, { root: scrollEl, rootMargin: '600px' });
    }
    io.observe(sEl);
  }

  function updateCount() {
    const c = document.getElementById('count');
    if (c) c.textContent = filtered.length.toLocaleString('he') + ' ערכים';
  }

  // לחיצה
  listEl.addEventListener('click', ev => {
    const row = ev.target.closest('.row');
    if (row) onOpen(parseInt(row.dataset.id, 10), row);
  });

  function jumpToLetter(L) {
    const idx = filtered.findIndex(e => e.l === L);
    if (idx < 0) return;
    while (rendered <= idx && rendered < filtered.length) renderMore();
    const target = listEl.querySelector('.row[data-id="' + filtered[idx].i + '"]');
    if (!target) return;
    // כותרות-האות הן position:sticky, ולכן offsetTop שלהן אינו אמין (מחזיר את מיקום
    // ההצמדה הנוכחי) — מה שגרם לקפיצה אחורה לא לעבוד. לכן נשענים על offsetTop של
    // השורה (אלמנט סטטי, אמין בשני הכיוונים) ומפחיתים את גובה הכותרת.
    const prev = target.previousElementSibling;
    const headerH = (prev && prev.classList.contains('letter')) ? prev.offsetHeight : 0;
    scrollEl.scrollTop = Math.max(0, target.offsetTop - headerH);
  }

  function scrollToId(id) {
    const idx = filtered.findIndex(e => e.i === id);
    if (idx < 0) return null;
    while (rendered <= idx && rendered < filtered.length) renderMore();
    const target = listEl.querySelector('.row[data-id="' + id + '"]');
    if (target) target.scrollIntoView({ block: 'center' });
    return target;
  }

  /* השכן ברשימה (לפי הסדר המוצג / מסונן): dir=+1 הבא, dir=-1 הקודם */
  function neighbor(id, dir) {
    const idx = filtered.findIndex(e => e.i === id);
    if (idx < 0) return null;
    const j = idx + dir;
    return (j >= 0 && j < filtered.length) ? filtered[j].i : null;
  }

  return { reset, jumpToLetter, scrollToId, neighbor };
}

/* רשימת האותיות לפי סדר הופעתן בנתונים */
const LETTERS = (function () {
  const seen = new Set(), out = [];
  DATA.forEach(e => { if (!seen.has(e.l)) { seen.add(e.l); out.push(e.l); } });
  return out;
})();

/* גלילה אל ערך לפי מזהה (להפניות פנימיות בתצוגת פאנל/מודאל) */
function entryById(id) { return DATA[id]; }

/* ===========================================================================
 *  ערכת נושא (מדמה את צבעי אוצריא; כפתור החלפה רק להדגמה)
 * ========================================================================= */
const THEMES = {
  light: {
    '--c-primary': '#6750A4', '--c-on-primary': '#FFFFFF',
    '--c-surface': '#FFFBFE', '--c-on-surface': '#1C1B1F',
    '--c-surface-2': '#F3EDF7', '--c-outline': '#CAC4D0',
    '--c-primary-subtle': 'rgba(103,80,164,.10)', '--c-error': '#B3261E',
  },
  dark: {
    '--c-primary': '#D0BCFF', '--c-on-primary': '#381E72',
    '--c-surface': '#1C1B1F', '--c-on-surface': '#E6E1E5',
    '--c-surface-2': '#2B2930', '--c-outline': '#49454F',
    '--c-primary-subtle': 'rgba(208,188,255,.14)', '--c-error': '#F2B8B5',
  }
};
function applyTheme(mode) {
  const t = THEMES[mode] || THEMES.light;
  const r = document.documentElement;
  Object.entries(t).forEach(([k, v]) => r.style.setProperty(k, v));
  document.body.classList.toggle('dark', mode === 'dark');
  try { localStorage.setItem('bio-theme', mode); } catch (e) {}
}
function initThemeToggle(btn) {
  let mode = 'light';
  try { mode = localStorage.getItem('bio-theme') || 'light'; } catch (e) {}
  applyTheme(mode);
  if (btn) {
    btn.textContent = mode === 'dark' ? '☀' : '☾';
    btn.addEventListener('click', () => {
      mode = mode === 'dark' ? 'light' : 'dark';
      applyTheme(mode);
      btn.textContent = mode === 'dark' ? '☀' : '☾';
    });
  }
}

/* טיפול בלחיצות על קישורים בתוך גוף ביוגרפיה (delegation) */
function wireBodyLinks(container, onGoto) {
  container.addEventListener('click', ev => {
    const x = ev.target.closest('.xref');
    if (x) { ev.preventDefault(); onGoto(parseInt(x.dataset.goto, 10)); return; }
    const s = ev.target.closest('.src');
    if (s) { ev.preventDefault(); openInOtzaria(decodeURIComponent(s.dataset.src)); }
  });
}

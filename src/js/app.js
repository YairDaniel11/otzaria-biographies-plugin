/* ===========================================================================
 *  app.js — אינטגרציה עם אוצריא + ממשק המשתמש
 *  (המנוע: common.js — נתונים, חיפוש, רשימה, קישורים)
 * ========================================================================= */

/* ----- ערכת נושא מאוצריא (plugin.boot + theme.changed) ----- */
function applyOtzariaTheme(theme) {
  if (!theme) return;
  const cs = theme.colorScheme || {};
  const r = document.documentElement;
  const set = (k, v) => { if (v) r.style.setProperty(k, v); };
  set('--c-primary', cs.primary);
  set('--c-on-primary', cs.onPrimary);
  set('--c-surface', cs.surface);
  set('--c-on-surface', cs.onSurface);
  set('--c-surface-2', cs.surfaceContainerHighest);
  // רקע פס הכותרת — surfaceContainerHigh, כמו הסרגל העליון של מסכי הספרים
  set('--c-topbar', cs.surfaceContainerHigh);
  set('--c-outline', cs.outline);
  set('--c-error', cs.error);
  if (cs.primary && /^#[0-9a-fA-F]{6}$/.test(cs.primary)) {
    const m = cs.primary.slice(1);
    const R = parseInt(m.substr(0, 2), 16), G = parseInt(m.substr(2, 2), 16), B = parseInt(m.substr(4, 2), 16);
    r.style.setProperty('--c-primary-subtle', 'rgba(' + R + ',' + G + ',' + B + ',0.12)');
  }
  // גופן וגודל: ברירת המחדל של התוסף היא גופן המערכת בגודל 20 (לא יורשים מאוצריא) —
  // אלא אם המשתמש בחר אחרת בבורר הגופן.
  document.body.classList.toggle('dark', theme.mode === 'dark');
  applyUserFontPrefs();
}

/* ----- פתיחת מקור באוצריא (מחליף את גרסת המוקאפ ב-common.js) ----- */
const SRC_EXPAND = {
  'ב"ב': 'בבא בתרא', 'ב"מ': 'בבא מציעא', 'ב"ק': 'בבא קמא',
  'ע"ז': 'עבודה זרה', 'מו"ק': 'מועד קטן', 'ר"ה': 'ראש השנה',
  'מע"ש': 'מעשר שני', 'קדושין': 'קידושין'
};
/* נרמול לדף בבלי בלבד: ע"א/עמוד א -> "." · ע"ב/עמוד ב -> ":" · הסרת "דף"/גרשיים/רווחים */
function normRef(s) {
  return String(s || '')
    .replace(/ע["'׳״]+\s*א(?![א-ת])/g, '.').replace(/ע["'׳״]+\s*ב(?![א-ת])/g, ':')
    .replace(/עמוד\s*א\b/g, '.').replace(/עמוד\s*ב\b/g, ':')
    .replace(/דף/g, '').replace(/[׳״"'`]/g, '').replace(/\s+/g, '');
}

/* גימטריה: סכימת ערכי האותיות (מתעלם מגרשיים; עוצר באות לא-עברית) */
const GEM = { א:1,ב:2,ג:3,ד:4,ה:5,ו:6,ז:7,ח:8,ט:9,י:10,כ:20,ך:20,ל:30,מ:40,ם:40,
  נ:50,ן:50,ס:60,ע:70,פ:80,ף:80,צ:90,ץ:90,ק:100,ר:200,ש:300,ת:400 };
function gem(s) { let n = 0; for (const ch of String(s || '')) { if (GEM[ch] == null) break; n += GEM[ch]; } return n; }

/* חילוץ מספר פרק ומספר משני (הלכה/משנה) מתוך ref/כותרת, לפי גימטריה.
   תומך: פ"ח, פי"ח, רפ"א (ריש), ספ"ב (סוף), פרק ל"א · ה"ה, הי"ב, מי"א, משנה ה. */
function refNums(ref) {
  const toks = String(ref || '').replace(/[׳״"'`]/g, '').trim().split(/\s+/);
  let perek = null, sub = null;
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    if (perek === null) {
      const mp = t.match(/^(?:ריש|סוף|פרק|רפ|ספ|פ)(.*)$/);
      if (mp) { let rest = mp[1]; if (!rest && toks[i + 1]) rest = toks[++i]; const g = gem(rest); if (g) { perek = g; continue; } }
    }
    if (sub === null) {
      const mh = t.match(/^(?:הלכה|משנה|ה|מ)(.*)$/);
      if (mh) { let rest = mh[1]; if (!rest && toks[i + 1]) rest = toks[++i]; const g = gem(rest); if (g) { sub = g; continue; } }
    }
  }
  return { perek: perek, sub: sub };
}

/* איתור ה-index בתוכן העניינים לפי ה-ref */
function findTocIndex(toc, ref) {
  if (!Array.isArray(toc) || !ref) return null;
  // א) בבלי — לפי דף/עמוד מנורמל
  const r = normRef(ref);
  if (r) {
    const cands = [r];
    if (!/[.:]/.test(r)) { cands.push(r + '.', r + ':'); }
    for (const e of toc) { if (cands.indexOf(normRef(e.text)) !== -1) return e.index; }
  }
  // ב) פרק/הלכה לפי גימטריה (ירושלמי / משנה / תוספתא / מדרש)
  const rn = refNums(ref);
  if (rn.perek != null) {
    let perekOnly = null;
    for (const e of toc) {
      const en = refNums(e.text);
      if (en.perek === rn.perek) {
        if (rn.sub != null && en.sub === rn.sub) return e.index;     // פרק+הלכה מדויק
        if (en.sub == null && perekOnly === null) perekOnly = e;     // כותרת פרק בלבד
        if (rn.sub == null) return e.index;                          // ה-ref ברמת פרק בלבד
      }
    }
    if (perekOnly) return perekOnly.index;
  }
  // ג) נפילה: כותרת ה-TOC מכילה את ה-ref המנורמל
  if (r && r.length >= 2) { for (const e of toc) { if (normRef(e.text).indexOf(r) !== -1) return e.index; } }
  return null;
}

async function openInOtzaria(src) {
  if (typeof window.Otzaria === 'undefined' || !window.Otzaria.call) return;
  const toks = String(src).trim().split(/\s+/);
  let q, ref, bookName;
  const first = (toks[0] || '').replace(/[,.]/g, '');
  if (first === "ירו'" || first === 'ירושלמי') {
    const tr = (toks[1] || '').replace(/[,.]/g, '');
    bookName = SRC_EXPAND[tr] || tr;
    q = 'ירושלמי ' + bookName;
    ref = toks.slice(2).join(' ');
  } else {
    bookName = SRC_EXPAND[first] || first;
    q = bookName;
    ref = toks.slice(1).join(' ');
  }

  // זיהוי הקורפוס לפי פורמט ה-ref (כשאין סימון מפורש): הלכה=>ירושלמי, משנה=>משנה, ע"א/ב או .:=>בבלי
  let corpus = '';
  if (first === "ירו'" || first === 'ירושלמי' || /ה["'׳]\s*[א-ת]|הלכה/.test(ref)) corpus = 'ירושלמי';
  else if (/מ["'׳]\s*[א-ת]|משנה/.test(ref)) corpus = 'משנה';
  else if (/ע["'׳״]\s*[אב]|[.:]/.test(ref)) corpus = 'בבלי';

  const norm = s => String(s || '').replace(/[׳״"'`\s]/g, '');
  const baseName = norm(bookName);

  try {
    const r = await window.Otzaria.call('library.findBooks', { query: q, limit: 15 });
    const books = (r && r.success) ? r.data : null;
    if (!books || !books.length) {
      await window.Otzaria.call('ui.showMessage', { message: 'לא נמצא מקור באוצריא: ' + src });
      return;
    }

    // ניקוד הספרים: התאמת-שם + התאמת-קורפוס, עם קנס על קורפוס שגוי — כדי לא לפתוח
    // למשל "משנה פאה" כשהמקור הוא "ירושלמי פאה".
    const OTHER = { 'בבלי': /משנה|ירושלמי|תוספתא/, 'ירושלמי': /משנה|בבלי|תוספתא/, 'משנה': /ירושלמי|בבלי|תוספתא/ };
    function score(b) {
      const t = norm(b.title);
      let s = 0;
      if (t === norm(q)) s += 100;
      if (baseName && t.indexOf(baseName) !== -1) s += 25;
      if (corpus && t.indexOf(norm(corpus)) !== -1) s += 50;
      if (corpus && OTHER[corpus] && OTHER[corpus].test(b.title)) s -= 40;
      return s;
    }
    const book = books.slice().sort((a, b) => score(b) - score(a))[0];
    const bookId = book.bookId;

    // מסלול עיקרי: getBookToc -> index -> openBook (ניווט אמיתי לפי אינדקס, לא חיפוש).
    // עוקף את הבאג שבו openBookAtRef שם את ה-ref בתיבת החיפוש ונתקע בעמוד הראשון.
    if (ref) {
      try {
        const t = await window.Otzaria.call('library.getBookToc', { bookId: bookId });
        const toc = (t && t.success) ? t.data : null;
        const idx = findTocIndex(toc, ref);
        if (idx != null) {
          const ro = await window.Otzaria.call('reader.openBook', { bookId: bookId, index: idx });
          if (ro && ro.success) return;
        }
      } catch (e) { /* נופלים למסלול החלופי */ }
    }

    // נפילה: openBookAtRef (יעבוד מאליו אחרי תיקון הליבה של אוצריא), ואז פתיחה רגילה
    const r2 = await window.Otzaria.call('reader.openBookAtRef', { bookId: bookId, ref: ref, index: 0 });
    if (!(r2 && r2.success && r2.data)) {
      await window.Otzaria.call('reader.openBook', { bookId: bookId, index: 0 });
    }
  } catch (e) { /* שקט */ }
}

if (typeof window.Otzaria !== 'undefined' && window.Otzaria.on) {
  window.Otzaria.on('plugin.boot', p => { if (p && p.theme) applyOtzariaTheme(p.theme); });
  window.Otzaria.on('theme.changed', t => applyOtzariaTheme(t));
}

/* ===========================================================================
 *  ממשק המשתמש
 * ========================================================================= */
installHorizontalScrollFix();

const detail = document.getElementById('detail');
const dcontent = document.getElementById('dcontent');
const dnav = document.getElementById('dnav');
const main = document.getElementById('main');
const navBack = document.getElementById('navBack');
const navFwd = document.getElementById('navFwd');
let list;

let hist = [];          // היסטוריית ערכים שנצפו (לכפתור "הקודם")
let hpos = -1;          // מיקום נוכחי בהיסטוריה
let curId = null;       // הערך המוצג כעת
let randomMode = false; // האם הערך הנוכחי נפתח באקראי

/* בלוק העשרה (תנאים/אמוראים נבחרים): צ'יפים + שורת מופעים + תיבת עובדה.
   מוצג רק לערכים שיש להם נתונים ב-BIO_ENRICH; אחרת מחזיר מחרוזת ריקה. */
function enrichBlock(id) {
  const en = (window.BIO_ENRICH || {})[id];
  if (!en) return '';
  let chips = '';
  if (en.type) chips += '<span class="meta-chip type">' + esc(en.type) + '</span>';
  if (en.dor) chips += '<span class="meta-chip">' + esc(en.dor) + '</span>';
  if (en.place) chips += '<span class="meta-chip">' + esc(en.place) + '</span>';
  chips = chips ? '<div class="meta-chips">' + chips + '</div>' : '';
  const fmt = v => { const n = parseInt(v, 10); return isNaN(n) ? null : n.toLocaleString('he'); };
  const cp = [];
  const mm = fmt(en.mishna), yy = fmt(en.yer), bb = fmt(en.bavli);
  if (mm) cp.push('משנה <b>' + mm + '</b>');
  if (yy) cp.push('ירושלמי <b>' + yy + '</b>');
  if (bb) cp.push('בבלי <b>' + bb + '</b>');
  const cite = cp.length ? '<div class="meta-cite">מופעים — ' + cp.join(' · ') + '</div>' : '';
  const fact = en.fact ? '<div class="meta-fact"><span class="ic">' + icon('info', 20) + '</span><div>' + esc(en.fact) + '</div></div>' : '';
  return chips + cite + fact;
}

function render(e) {
  const sp = splitName(e.n);
  dcontent.innerHTML =
    '<div class="detail-head">' +
      '<span class="detail-ic">' + icon('person', 26) + '</span>' +
      '<div class="detail-head-t">' +
        '<h2 class="detail-name">' + esc(sp.name) + '</h2>' +
        '<div class="detail-sub">אות ' + esc(e.l) + '</div>' +
      '</div>' +
    '</div>' +
    enrichBlock(e.i) +
    '<div class="body">' + renderBody(e.b) + '</div>';
  curId = e.i;
  dnav.hidden = false;
  main.classList.add('show-detail');
  document.querySelectorAll('.row.active').forEach(r => r.classList.remove('active'));
  const row = document.querySelector('.row[data-id="' + e.i + '"]');
  if (row) row.classList.add('active');
  detail.scrollTop = 0;
  navBack.disabled = hpos <= 0;
  navFwd.disabled = !randomMode && (!list || list.neighbor(curId, 1) == null);
}

function open(id, opt) {
  opt = opt || {};
  const e = entryById(id);
  if (!e) return;
  randomMode = !!opt.random;
  if (opt.push !== false && hist[hpos] !== id) {
    hist = hist.slice(0, hpos + 1);
    hist.push(id);
    hpos = hist.length - 1;
  }
  render(e);
}

function goBack() { if (hpos > 0) { hpos--; open(hist[hpos], { push: false, random: false }); } }
function goNext() {
  if (randomMode) { goRandom(); return; }
  const nx = list.neighbor(curId, 1);
  if (nx != null) { open(nx, { push: true }); list.scrollToId(nx); }
}
function goRandom() {
  const id = Math.floor(Math.random() * DATA.length);
  open(id, { push: true, random: true });
  list.scrollToId(id);
}

list = createList(document.getElementById('scroll'), document.getElementById('list'), id => open(id, { push: true }));
list.reset('');
wireBodyLinks(detail, id => { open(id, { push: true }); list.scrollToId(id); });

/* לחיצה על צ'יפ העשרה (סוג/דור/מקום) -> סינון הרשימה לפי אותו ערך */
dcontent.addEventListener('click', ev => {
  const c = ev.target.closest('.meta-chip');
  if (!c) return;
  const q = document.getElementById('q');
  q.value = c.textContent.trim();
  q.dispatchEvent(new Event('input', { bubbles: true }));
});

navBack.onclick = goBack;
navFwd.onclick = goNext;
document.getElementById('navRand').onclick = goRandom;

/* אייקוני FluentUI (RTL: "הקודם" מצביע ימינה, "הבא" שמאלה) */
document.getElementById('searchIcon').innerHTML = icon('search', 18);
document.getElementById('clearBtn').innerHTML = icon('dismiss', 16);
document.getElementById('phIcon').innerHTML = icon('person', 48);
navBack.innerHTML = icon('chevron_right', 16) + '<span>הקודם</span>';
navFwd.innerHTML = '<span>הבא</span>' + icon('chevron_left', 16);
document.getElementById('navRand').innerHTML = icon('arrow_shuffle', 16) + '<span>ערך אקראי</span>';
document.getElementById('navList').innerHTML = icon('arrow_right', 16) + '<span>לרשימה</span>';
document.getElementById('navList').onclick = () => main.classList.remove('show-detail');

/* סרגל אותיות אופקי */
const az = document.getElementById('azbar');
az.innerHTML = LETTERS.map(L => '<span data-l="' + L + '">' + L + '</span>').join('');
az.addEventListener('click', e => {
  const s = e.target.closest('span'); if (s) list.jumpToLetter(s.dataset.l);
});

let _t;
const qEl = document.getElementById('q');
const clearBtn = document.getElementById('clearBtn');
qEl.addEventListener('input', e => {
  const v = e.target.value;
  clearBtn.hidden = !v;
  az.classList.toggle('hidden', !!v.trim());
  clearTimeout(_t); _t = setTimeout(() => list.reset(v), 120);
});
clearBtn.addEventListener('click', e => {
  e.preventDefault(); e.stopPropagation();
  qEl.value = '';
  clearBtn.hidden = true;
  az.classList.remove('hidden');
  list.reset('');
  qEl.focus();
});

/* ===========================================================================
 *  שדה החיפוש — מיקוד
 *  תיבת החיפוש היא <label> שעוטף את ה-input, ולכן נגיעה טבעית כבר ממקדת את
 *  השדה ומעלה את מקלדת-המסך. אין טריק preventDefault/focus() — כי ב-WebView
 *  עדכני הוא דווקא *מונע* את עליית המקלדת (focus תכנותי + preventDefault לא
 *  מעלים מקלדת-מסך). נותנים ל-WebView לטפל בזה באופן טבעי.
 * ========================================================================= */


/* ===========================================================================
 *  מפריד נגרר — כוונון רוחב עמודת השמות
 * ========================================================================= */
(function () {
  const divider = document.getElementById('divider');
  const paneList = document.querySelector('.pane-list');
  if (!divider || !paneList) return;
  const KEY = 'bio-list-width';
  const MIN = 150;

  function maxWidth() { return Math.round(main.getBoundingClientRect().width * 0.75); }
  function applyWidth(px) {
    px = Math.max(MIN, Math.min(maxWidth(), px));
    paneList.style.width = px + 'px';
    return px;
  }
  // שחזור רוחב שמור
  try {
    const saved = parseInt(localStorage.getItem(KEY), 10);
    if (saved > 0) applyWidth(saved);
  } catch (e) {}

  let dragging = false;
  function onMove(e) {
    if (!dragging) return;
    const x = (e.touches ? e.touches[0].clientX : e.clientX);
    // העמודה בצד ימין (RTL): רוחבה = מקצה ימין של האזור עד מיקום הסמן
    applyWidth(main.getBoundingClientRect().right - x);
    if (e.cancelable) e.preventDefault();
  }
  function onUp() {
    if (!dragging) return;
    dragging = false;
    divider.classList.remove('dragging');
    document.body.style.userSelect = '';
    try { localStorage.setItem(KEY, parseInt(paneList.style.width, 10) || ''); } catch (e) {}
  }
  function onDown(e) {
    dragging = true;
    divider.classList.add('dragging');
    document.body.style.userSelect = 'none';
    if (e.cancelable) e.preventDefault();
  }
  divider.addEventListener('pointerdown', onDown);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
})();

/* ===========================================================================
 *  בורר גופן וגודל טקסט (העדפת המשתמש, נשמרת מקומית)
 * ========================================================================= */
const FONT_KEY = 'bio-font-family', SIZE_KEY = 'bio-font-size', HEAD_KEY = 'bio-font-headings';
function getUserFont() { try { return localStorage.getItem(FONT_KEY) || ''; } catch (e) { return ''; } }
function getUserSize() { try { return parseInt(localStorage.getItem(SIZE_KEY), 10) || 0; } catch (e) { return 0; } }
function getUserHeadings() { try { return localStorage.getItem(HEAD_KEY) === '1'; } catch (e) { return false; } }

/* בונה ערך font-family תקין משם גופן בודד שהמשתמש הזין:
   שם בודד -> עטיפה במרכאות + נפילה ל-serif; מחרוזת עם פסיקים (stack) -> כמו שהיא. */
function fontStack(name) {
  name = String(name || '').trim();
  if (!name) return '';
  if (name.indexOf(',') !== -1) return name;
  return '"' + name.replace(/"/g, '') + '", serif';
}

/* מחיל את העדפות המשתמש על גופן/גודל (גובר על אוצריא).
   הגופן חל תמיד על התוכן (--prayer-font); ועל הכותרות/הממשק (--ui-font)
   רק אם המשתמש סימן זאת. */
function applyUserFontPrefs() {
  const r = document.documentElement;
  const stack = fontStack(getUserFont());
  const size = getUserSize();
  const headingsOn = getUserHeadings();
  if (stack) r.style.setProperty('--prayer-font', stack);
  else r.style.removeProperty('--prayer-font');
  if (stack && headingsOn) r.style.setProperty('--ui-font', stack);
  else r.style.removeProperty('--ui-font');
  if (size) {
    r.style.setProperty('--fs', size + 'px');
    // --fs-ui (גודל הכותרות/הממשק) מתעדכן רק אם "החל גם על הכותרות" מסומן
    if (headingsOn) r.style.setProperty('--fs-ui', size + 'px');
    else r.style.removeProperty('--fs-ui');
  } else {
    r.style.removeProperty('--fs');
    r.style.removeProperty('--fs-ui');
  }
}

/* רשימת מועמדים לבדיקת התקנה (כשאין הרשאת queryLocalFonts — כמו בתוך אוצריא) */
const FONT_PROBE = [
  // ── עברית: ברירות מחדל / Windows ──
  'David','David CLM','David Libre','Frank Ruhl Libre','FrankRuhlCLM','Frank Ruhl CLM','FrankRuehl',
  'Narkisim','Narkis Tam','Narkis Classic','Narkis Block','Miriam','Miriam Fixed','Miriam CLM',
  'Miriam Mono CLM','Aharoni','Levenim MT','Gisha','Rod','Arial Hebrew',
  // ── עברית: CLM / קוד פתוח ──
  'Hadassah Friedlaender','Hadasim CLM','Drugulin CLM','Stam Ashkenaz CLM','Stam Sefarad CLM',
  'Nachlieli CLM','Yehuda CLM','Shofar','Simple CLM','Caladings CLM','Ellinia CLM',
  'Taamey Frank CLM','Taamey Ashkenaz','Taamey David CLM','Keren CLM','Keter YG','KeterYG',
  'Keter Aram Tsova','Ezra SIL','Ezra SIL SR','SBL Hebrew','Cardo','Shlomo','Shlomo Stam',
  'Rashi','Vilna','Meorot','Mekorot CLM',
  // ── עברית: משפחת Guttman ──
  'Guttman Aharoni','Guttman Adii','Guttman Aram','Guttman Calligraphic','Guttman CourMir',
  'Guttman David','Guttman Drogolin','Guttman Frank','Guttman Hatzvi','Guttman Haim',
  'Guttman Hodes','Guttman Kav','Guttman Keren','Guttman Logo1','Guttman Mantova',
  'Guttman Miryam','Guttman Myamfix','Guttman Rashi','Guttman Soncino','Guttman Stam',
  'Guttman Toledo','Guttman Vilna','Guttman Yad','Guttman Yad-Brush','Guttman Yad-Light',
  // ── עברית: Google Fonts ──
  'Heebo','Rubik','Assistant','Alef','Secular One','Suez One','Bellefair','Tinos','Cousine',
  'Amatic SC','Varela Round','Karantina','Bona Nova','Frank Ruhl Hofshi',
  'Noto Sans Hebrew','Noto Serif Hebrew','Noto Rashi Hebrew','Open Sans Hebrew',
  // ── Windows / Office ──
  'Arial','Arial Black','Arial Narrow','Calibri','Calibri Light','Cambria','Cambria Math',
  'Candara','Century Gothic','Comic Sans MS','Consolas','Constantia','Corbel','Courier New',
  'Ebrima','Franklin Gothic Medium','Franklin Gothic Book','Gabriola','Gadugi','Garamond','Georgia',
  'Impact','Ink Free','Javanese Text','Leelawadee UI','Lucida Console','Lucida Sans Unicode',
  'Malgun Gothic','Microsoft Himalaya','Microsoft JhengHei','Microsoft Sans Serif','Microsoft YaHei',
  'MingLiU-ExtB','Mongolian Baiti','MS Gothic','MV Boli','Myanmar Text','Nirmala UI',
  'Palatino Linotype','Segoe MDL2 Assets','Segoe Print','Segoe Script','Segoe UI','Segoe UI Emoji',
  'Segoe UI Historic','Segoe UI Light','Segoe UI Semibold','Segoe UI Symbol','SimSun','Sitka',
  'Sitka Text','Sylfaen','Tahoma','Times New Roman','Trebuchet MS','Verdana','Webdings','Wingdings',
  'Wingdings 2','Wingdings 3','Yu Gothic','Bahnschrift','Dubai','Book Antiqua','Bookman Old Style',
  'Century','Monotype Corsiva','Rockwell','Rockwell Condensed','Bodoni MT','Goudy Old Style',
  'Perpetua','Baskerville Old Face','Bell MT','Calisto MT','Footlight MT Light','Berlin Sans FB',
  'Bernard MT Condensed','Britannic Bold','Broadway','Brush Script MT','Californian FB','Castellar',
  'Centaur','Chiller','Colonna MT','Cooper Black','Copperplate Gothic Bold','Curlz MT','Elephant',
  'Engravers MT','Eras Bold ITC','Felix Titling','Forte','Freestyle Script','French Script MT',
  'Gigi','Gill Sans MT','Goudy Stout','Harlow Solid Italic','Harrington','High Tower Text',
  'Imprint MT Shadow','Informal Roman','Jokerman','Juice ITC','Kristen ITC','Kunstler Script',
  'Lucida Bright','Lucida Calligraphy','Lucida Fax','Lucida Handwriting','Lucida Sans',
  'Lucida Sans Typewriter','Magneto','Maiandra GD','Matura MT Script Capitals','Mistral',
  'Modern No. 20','Niagara Engraved','Niagara Solid','OCR A Extended','Old English Text MT','Onyx',
  'Palace Script MT','Papyrus','Parchment','Perpetua Titling MT','Playbill','Poor Richard','Pristina',
  'Rage Italic','Ravie','Script MT Bold','Showcard Gothic','Snap ITC','Stencil','Tempus Sans ITC',
  'Tw Cen MT','Viner Hand ITC','Vivaldi','Vladimir Script','Wide Latin',
  // ── Google / עיצוב (לטיני) ──
  'Roboto','Roboto Condensed','Roboto Mono','Roboto Slab','Open Sans','Lato','Montserrat',
  'Poppins','Raleway','Nunito','Nunito Sans','Merriweather','Merriweather Sans','Playfair Display',
  'PT Sans','PT Serif','PT Mono','Source Sans Pro','Source Serif Pro','Source Code Pro','Inter',
  'Work Sans','Fira Sans','Fira Code','Fira Mono','IBM Plex Sans','IBM Plex Serif','IBM Plex Mono',
  'Oswald','Lora','Quicksand','Ubuntu','Ubuntu Mono','Ubuntu Condensed','Spectral','Crimson Text',
  'Libre Baskerville','Libre Franklin','Bitter','Cabin','Caveat','Cinzel','Comfortaa','Dancing Script',
  'DM Sans','DM Serif Display','Exo 2','Inconsolata','Josefin Sans','Karla','Lobster','Manrope',
  'Mukta','Mulish','Noto Sans','Noto Serif','Pacifico','Prompt','Titillium Web','Vollkorn',
  'Yanone Kaffeesatz','Zilla Slab','Bebas Neue','Barlow','Barlow Condensed','Archivo','Rajdhani',
  'Sora','Outfit',
];

/* זיהוי הגופנים המותקנים — שלוש שיטות (כמו בתוסף הוורד); עובד גם בתוך אוצריא ללא הרשאה */
async function detectInstalledFonts() {
  // שיטה 1: queryLocalFonts — מחזיר את כל הגופנים (אם נתמך ומאושר)
  try {
    if (typeof window.queryLocalFonts === 'function') {
      const lf = await window.queryLocalFonts();
      const fams = Array.from(new Set(lf.map(f => f.family)));
      if (fams.length > 5) return fams;
    }
  } catch (e) {}
  // שיטה 2: FontFace local() probe — אמין ב-WebView (העיקרי בתוך אוצריא)
  const found = [];
  try {
    const res = await Promise.allSettled(FONT_PROBE.map(name => {
      const ff = new FontFace('_fp_' + name.replace(/\W/g, '_'), "local('" + name + "')");
      return ff.load().then(() => name);
    }));
    res.forEach(r => { if (r.status === 'fulfilled') found.push(r.value); });
  } catch (e) {}
  // שיטה 3: גיבוי מדידת רוחב (אם probe כמעט לא החזיר)
  if (found.length < 5) {
    try {
      const ctx = document.createElement('canvas').getContext('2d');
      const T = 'AaBb012אבגדמ';
      ctx.font = '16px monospace';
      const bw = ctx.measureText(T).width;
      FONT_PROBE.forEach(f => {
        ctx.font = "16px '" + f + "',monospace";
        if (Math.abs(ctx.measureText(T).width - bw) > 0.5 && found.indexOf(f) === -1) found.push(f);
      });
    } catch (e) {}
  }
  return Array.from(new Set(found));
}

(function () {
  const btn = document.getElementById('fontBtn');
  const panel = document.getElementById('fontPanel');
  const famInp = document.getElementById('fpFamily');
  const headChk = document.getElementById('fpHeadings');
  const loadBtn = document.getElementById('fpLoadFonts');
  const fontList = document.getElementById('fpFontList');
  const hint = document.getElementById('fpFontHint');
  const sizeInp = document.getElementById('fpSize');
  const sizeVal = document.getElementById('fpSizeVal');
  const resetBtn = document.getElementById('fpReset');
  if (!btn || !panel) return;

  // מיגרציה: ערך ישן שנשמר כ-stack ("'David Libre','David',serif") -> שם גופן בודד נקי
  try {
    const v0 = localStorage.getItem(FONT_KEY);
    if (v0 && /[,"']/.test(v0)) {
      const m = v0.match(/'([^']+)'|"([^"]+)"|([^,]+)/);
      const clean = ((m && (m[1] || m[2] || m[3])) || '').trim();
      if (clean) localStorage.setItem(FONT_KEY, clean);
    }
  } catch (e) {}

  // מיגרציה חד-פעמית: ברירת המחדל הוחלפה מ"דוד" לגופן המערכת (System UI) —
  // מנקה העדפת גופן ישנה שנשמרה במכשיר, כדי שברירת המחדל החדשה אכן תוצג.
  try {
    if (!localStorage.getItem('bio-font-migrated-sysui')) {
      localStorage.removeItem(FONT_KEY);
      localStorage.setItem('bio-font-migrated-sysui', '1');
    }
  } catch (e) {}

  let fontsLoaded = false;
  function populateFonts(list) {
    fontList.innerHTML = list.map(f =>
      '<option value="' + String(f).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;') + '"></option>'
    ).join('');
  }
  async function ensureFonts(force) {
    if (fontsLoaded && !force) return;
    if (hint) hint.textContent = 'טוען רשימת גופנים…';
    const list = (await detectInstalledFonts()).sort((a, b) => a.localeCompare(b, 'he'));
    if (list.length) {
      populateFonts(list);
      fontsLoaded = true;
      if (hint) hint.textContent = 'נמצאו ' + list.length.toLocaleString('he') + ' גופנים מותקנים. בחרו מהרשימה או הקלידו שם.';
    } else if (hint) {
      hint.textContent = 'לא זוהו גופנים אוטומטית — אפשר להקליד שם של כל גופן מותקן.';
    }
  }

  function currentSizePx() {
    const s = getUserSize();
    if (s) return s;
    const v = getComputedStyle(document.documentElement).getPropertyValue('--fs');
    return parseInt(v, 10) || 18;
  }
  function syncControls() {
    famInp.value = getUserFont();
    headChk.checked = getUserHeadings();
    const s = currentSizePx();
    sizeInp.value = s;
    sizeVal.textContent = s + 'px';
  }

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const open = panel.hasAttribute('hidden');
    if (open) { syncControls(); ensureFonts(); panel.removeAttribute('hidden'); }
    else panel.setAttribute('hidden', '');
  });
  // סגירה בלחיצה מחוץ לפאנל
  document.addEventListener('pointerdown', e => {
    if (!panel.hasAttribute('hidden') && !panel.contains(e.target) && e.target !== btn) {
      panel.setAttribute('hidden', '');
    }
  });

  // הקלדה/בחירת גופן (שדה חופשי + השלמה מ-datalist)
  famInp.addEventListener('input', () => {
    try { localStorage.setItem(FONT_KEY, famInp.value.trim()); } catch (e) {}
    applyUserFontPrefs();
  });

  // החלה גם על כותרות/ממשק
  headChk.addEventListener('change', () => {
    try { localStorage.setItem(HEAD_KEY, headChk.checked ? '1' : '0'); } catch (e) {}
    applyUserFontPrefs();
  });

  // רענון רשימת הגופנים (זיהוי מחדש — שלוש שיטות, עובד גם בתוך אוצריא)
  loadBtn.addEventListener('click', async () => {
    loadBtn.disabled = true;
    loadBtn.textContent = 'טוען…';
    await ensureFonts(true);
    loadBtn.textContent = 'רענן רשימת גופנים';
    loadBtn.disabled = false;
  });

  sizeInp.addEventListener('input', () => {
    sizeVal.textContent = sizeInp.value + 'px';
    try { localStorage.setItem(SIZE_KEY, sizeInp.value); } catch (e) {}
    applyUserFontPrefs();
  });
  resetBtn.addEventListener('click', () => {
    try {
      localStorage.removeItem(FONT_KEY); localStorage.removeItem(SIZE_KEY); localStorage.removeItem(HEAD_KEY);
    } catch (e) {}
    // החזרה לברירת המחדל של התוסף (גופן המערכת 20) — הסרת כל ההגדרות האישיות
    document.documentElement.style.removeProperty('--prayer-font');
    document.documentElement.style.removeProperty('--ui-font');
    document.documentElement.style.removeProperty('--fs');
    syncControls();
  });
})();

/* ===========================================================================
 *  מתג טאבים: ביוגרפיות  /  סדר הדורות
 * ========================================================================= */
(function () {
  const tabs = document.getElementById('tabs');
  const mainEl = document.getElementById('main');
  const sederView = document.getElementById('sederView');
  const eventsView = document.getElementById('eventsView');
  const masaotView = document.getElementById('masaotView');
  if (!tabs || !sederView) return;
  let sederInited = false;
  let eventsInited = false;
  let masaotInited = false;

  function setTab(name) {
    const seder = (name === 'seder');
    const events = (name === 'events');
    const masaot = (name === 'masaot');
    document.body.classList.toggle('mode-seder', seder);
    document.body.classList.toggle('mode-events', events);
    document.body.classList.toggle('mode-masaot', masaot);
    mainEl.hidden = seder || events || masaot;
    sederView.hidden = !seder;
    if (eventsView) eventsView.hidden = !events;
    if (masaotView) masaotView.hidden = !masaot;
    tabs.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    if (seder) initSeder();
    if (events) initEvents();
    if (masaot) initMasaot();
  }
  tabs.addEventListener('click', e => {
    const t = e.target.closest('.tab');
    if (t) setTab(t.dataset.tab);
  });

  /* ----- אתחול ציר הזמן של סדר הדורות (פעם אחת, בלחיצה ראשונה על הטאב) ----- */
  function initSeder() {
    if (sederInited) return;
    sederInited = true;

    const DATA = window.SEDER || [];
    const app = document.getElementById('sederApp');
    const nav = document.getElementById('sederNav');
    const qInput = document.getElementById('sederQ');
    const countEl = document.getElementById('sederCount');
    const sClear = document.getElementById('sederClear');
    const scrim = document.getElementById('sederScrim');
    const drawer = document.getElementById('sederDrawer');
    const drawerBody = document.getElementById('sederDrawerBody');
    const drawerTitle = document.getElementById('sederDrawerTitle');

    /* גברים (אבות/חכמים) = דמות מלאה; נשים (אמהות) = דמות מתאר; מלכים = כתר; ספר; אירועים = מידע */
    const TYPE_ICON = { man1:'person_filled', man2:'person_filled', ptira:'person_filled', tsadika:'person',
      melech1:'crown', melech2:'crown', melech3:'crown', sefer:'book',
      event:'info', event2:'info', tkufa:'info', fromto:'info' };
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const escA = s => esc(s).replace(/"/g, '&quot;');
    // הוספת רווח אחרי פסיק בשמות תקופות ("האמוראים,סבוראים" -> "האמוראים, סבוראים")
    // לתצוגה בלבד — מאפשר גלישת שורה ומונע חיתוך. ערכי ה-data נשארים מקוריים.
    const fmtSec = s => String(s || '').replace(/,(?=\S)/g, ', ');
    const yr = e => (e.y1 && e.y2 && e.y1 !== e.y2) ? esc(e.y1) + '–' + esc(e.y2) : (e.y1 ? esc(e.y1) : '');
    const ic = e => icon(TYPE_ICON[e.type] || 'person_filled', 18);
    const num = v => { const n = parseInt(v, 10); return isNaN(n) ? null : n; };

    /* תיוג פרשת השבוע לפי שנת האירוע — טווחי שנים שחולצו מ"סדר הדורות.xlsx"
       (מכסה את התקופה המקראית: בראשית עד תחילת שמות). */
    const PARSHA_RANGES = [
      ['בראשית', 1, 1558], ['נח', 1559, 2046], ['וירא', 2047, 2084], ['חיי שרה', 2085, 2171],
      ['וישלח', 2172, 2173], ['תולדות', 2174, 2183], ['ויצא', 2184, 2205], ['וישלח', 2206, 2207],
      ['וישב', 2216, 2228], ['מקץ', 2229, 2236], ['ויגש', 2237, 2238], ['ויחי', 2239, 2309],
      ['שמות', 2340, 2349]
    ];
    const PARSHA_OPEN = {
      'בראשית': 'בראשית א', 'נח': 'בראשית ו', 'לך לך': 'בראשית יב', 'וירא': 'בראשית יח',
      'חיי שרה': 'בראשית כג', 'תולדות': 'בראשית כה', 'ויצא': 'בראשית כח', 'וישלח': 'בראשית לב',
      'וישב': 'בראשית לז', 'מקץ': 'בראשית מא', 'ויגש': 'בראשית מד', 'ויחי': 'בראשית מז', 'שמות': 'שמות א'
    };
    const parshaFor = y => {
      const n = parseInt(y, 10);
      if (isNaN(n)) return '';
      for (let i = 0; i < PARSHA_RANGES.length; i++) {
        const r = PARSHA_RANGES[i];
        if (n >= r[1] && n <= r[2]) return r[0];
      }
      return '';
    };

    const SECTIONS = [];
    (function () { const s = new Set(); DATA.forEach(e => { if (!s.has(e.sec)) { s.add(e.sec); SECTIONS.push(e.sec); } }); })();

    function render(query) {
      const q = (query || '').trim();
      const list = q ? DATA.filter(e => (e.name + ' ' + e.desc + ' ' + e.sec).indexOf(q) !== -1) : DATA;
      let cur = null, html = '', open = false;
      list.forEach(e => {
        if (e.sec !== cur) {
          if (open) html += '</div>';
          cur = e.sec;
          html += '<div class="sanchor" data-sa="' + escA(e.sec) + '"></div>' +
            '<div class="period" data-sec="' + escA(e.sec) + '">' + esc(fmtSec(e.sec)) + '</div><div class="tl">';
          open = true;
        }
        const y = yr(e), di = DATA.indexOf(e), pn = parshaFor(e.y1);
        html += '<div class="item"><div class="dot">' + ic(e) + '</div>' +
          '<div class="body"><div class="line"><span class="nm">' + esc(e.name) + '</span>' +
          (y ? '<button class="yr" dir="ltr" data-idx="' + di + '" data-tip="הצג בני התקופה">' + y + '</button>' : '') +
          (pn ? '<button class="prsh" data-open="' + escA(PARSHA_OPEN[pn] || '') + '" title="פתח את הפרשה בקורא">פרשת ' + esc(pn) + '</button>' : '') + '</div>' +
          (e.desc ? '<div class="desc">' + esc(e.desc) + '</div>' : '') + '</div></div>';
      });
      if (open) html += '</div>';
      if (!list.length) html = '<div class="empty">לא נמצאו תוצאות</div>';
      app.innerHTML = html;
      countEl.textContent = list.length.toLocaleString('he') + ' ערכים';
      updateActive();
    }

    /* ----- ניווט תקופות (ימין) ----- */
    nav.innerHTML = '<div class="sn-title">תקופות</div>' +
      SECTIONS.map(s => '<button class="sn-item" data-sec="' + escA(s) + '">' + esc(fmtSec(s)) + '</button>').join('');
    function findAnchor(sec) { return Array.prototype.find.call(app.querySelectorAll('.sanchor'), a => a.dataset.sa === sec); }
    function topOf(el) { return el.getBoundingClientRect().top - sederView.getBoundingClientRect().top + sederView.scrollTop; }
    function gotoSec(sec) {
      if (qInput.value.trim()) { qInput.value = ''; if (sClear) sClear.hidden = true; render(''); }
      const a = findAnchor(sec);
      if (a) sederView.scrollTo({ top: Math.max(0, topOf(a) - 4), behavior: 'smooth' });
    }
    nav.addEventListener('click', e => { const b = e.target.closest('.sn-item'); if (b) gotoSec(b.dataset.sec); });
    function setActive(sec) { nav.querySelectorAll('.sn-item').forEach(b => b.classList.toggle('active', b.dataset.sec === sec)); }
    function updateActive() {
      const line = sederView.getBoundingClientRect().top + 24; let act = null;
      app.querySelectorAll('.sanchor').forEach(a => { if (a.getBoundingClientRect().top <= line) act = a.dataset.sa; });
      if (act) setActive(act);
    }
    sederView.addEventListener('scroll', () => { requestAnimationFrame(updateActive); }, { passive: true });

    /* ----- חלונית "בני התקופה" (שמאל) ----- */
    document.getElementById('sederSIcon').innerHTML = icon('search', 18);
    document.getElementById('sederDrawerClose').innerHTML = icon('dismiss', 18);
    function closeDrawer() { drawer.classList.remove('open'); scrim.classList.remove('open'); }
    function openContemporaries(idx) {
      const e = DATA[idx]; if (!e) return;
      const a1 = num(e.y1), a2 = num(e.y2) || a1; if (a1 === null) return;
      const lo = Math.min(a1, a2), hi = Math.max(a1, a2);
      const mates = DATA.filter(o => {
        const o1 = num(o.y1); if (o1 === null) return false;
        const o2 = num(o.y2) || o1; return Math.min(o1, o2) <= hi && Math.max(o1, o2) >= lo;
      });
      drawerTitle.innerHTML = 'בני תקופתו של ' + esc(e.name) +
        '<small>שנים ' + esc(yr(e)) + ' ליצירה · ' + mates.length + ' דמויות/אירועים</small>';
      drawerBody.innerHTML = mates.map(o =>
        '<div class="d-row"><span class="d-ic">' + ic(o) + '</span>' +
        '<span class="d-nm">' + esc(o.name) + (o.desc ? ' <small>' + esc(o.desc) + '</small>' : '') + '</span>' +
        (yr(o) ? '<span class="d-yr" dir="ltr">' + yr(o) + '</span>' : '') + '</div>').join('');
      drawer.classList.add('open'); scrim.classList.add('open');
    }
    app.addEventListener('click', e => {
      const pp = e.target.closest('.prsh'); if (pp) { if (pp.dataset.open) openInOtzaria(pp.dataset.open); return; }
      const y = e.target.closest('.yr'); if (y) openContemporaries(+y.dataset.idx);
    });
    scrim.addEventListener('click', closeDrawer);
    document.getElementById('sederDrawerClose').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

    /* ----- חיפוש ----- */
    let _st;
    qInput.addEventListener('input', () => {
      if (sClear) sClear.hidden = !qInput.value;
      clearTimeout(_st); const v = qInput.value; _st = setTimeout(() => render(v), 120);
    });
    if (sClear) {
      sClear.innerHTML = icon('dismiss', 16);
      sClear.addEventListener('click', () => { qInput.value = ''; sClear.hidden = true; render(''); qInput.focus(); });
    }
    // מיקוד שדה החיפוש: נגיעה טבעית על ה-<label> ממקדת את ה-input ומעלה את
    // מקלדת-המסך — ללא טריק preventDefault/focus() שמונע אותה ב-WebView עדכני.

    render('');
  }

  /* ----- אתחול "לוח אירועים" (פעם אחת, בלחיצה ראשונה על הטאב) ----- */
  function initEvents() {
    if (eventsInited) return;
    eventsInited = true;
    if (!eventsView) return;

    const DATA = window.EVENTS || [];
    const MONTHS = window.EVENTS_MONTHS || [];
    const app = document.getElementById('eventsApp');
    const nav = document.getElementById('eventsNav');
    const qInput = document.getElementById('eventsQ');
    const countEl = document.getElementById('eventsCount');
    const eClear = document.getElementById('eventsClear');
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const escA = s => esc(s).replace(/"/g, '&quot;');

    function dateLabel(e) {
      if (e.dateText) return e.dateText;
      return (e.day ? esc(e.day) + ' ' : '') + esc(e.month);
    }

    function render(query) {
      const q = (query || '').trim();
      let list = DATA;
      if (q) {
        list = list.filter(e =>
          (e.event + ' ' + e.source + ' ' + e.month + ' ' + e.day + ' ' + e.category + ' ' + e.year).indexOf(q) !== -1);
      }
      let cur = null, html = '', open = false;
      list.forEach(e => {
        if (e.month !== cur) {
          if (open) html += '</div>';
          cur = e.month;
          html += '<div class="sanchor" data-sa="' + escA(e.month) + '"></div>' +
            '<div class="period" data-sec="' + escA(e.month) + '">' + esc(e.month) + '</div><div class="tl">';
          open = true;
        }
        html += '<div class="item"><div class="dot">' + icon('calendar', 18) + '</div>' +
          '<div class="body"><div class="line"><span class="nm">' + esc(dateLabel(e)) + '</span>' +
          (e.category ? '<span class="yr" dir="rtl" style="cursor:default">' + esc(e.category) + '</span>' : '') +
          (e.year ? '<span class="yr" dir="rtl" style="cursor:default">' + esc(e.year) + '</span>' : '') + '</div>' +
          '<div class="desc evdesc">' + esc(e.event) + (e.source ? ' <span class="evsrc">(' + esc(e.source) + ')</span>' : '') + '</div>' +
          '</div></div>';
      });
      if (open) html += '</div>';
      if (!list.length) html = '<div class="empty">לא נמצאו תוצאות</div>';
      app.innerHTML = html;
      countEl.textContent = list.length.toLocaleString('he') + ' אירועים';
      updateActive();
    }

    /* ----- ניווט חודשים (ימין) ----- */
    function renderNav() {
      nav.innerHTML = '<div class="sn-title">חודשים</div>' +
        MONTHS.map(m => '<button class="sn-item" data-sec="' + escA(m) + '">' + esc(m) + '</button>').join('');
    }
    renderNav();

    function findAnchor(sec) { return Array.prototype.find.call(app.querySelectorAll('.sanchor'), a => a.dataset.sa === sec); }
    function topOf(el) { return el.getBoundingClientRect().top - eventsView.getBoundingClientRect().top + eventsView.scrollTop; }
    function gotoSec(sec) {
      if (qInput.value.trim()) { qInput.value = ''; if (eClear) eClear.hidden = true; render(''); }
      const a = findAnchor(sec);
      if (a) eventsView.scrollTo({ top: Math.max(0, topOf(a) - 4), behavior: 'smooth' });
    }
    nav.addEventListener('click', e => {
      const b = e.target.closest('.sn-item');
      if (b) gotoSec(b.dataset.sec);
    });
    function setActive(sec) { nav.querySelectorAll('.sn-item').forEach(b => b.classList.toggle('active', b.dataset.sec === sec)); }
    function updateActive() {
      const line = eventsView.getBoundingClientRect().top + 24; let act = null;
      app.querySelectorAll('.sanchor').forEach(a => { if (a.getBoundingClientRect().top <= line) act = a.dataset.sa; });
      if (act) setActive(act);
    }
    eventsView.addEventListener('scroll', () => { requestAnimationFrame(updateActive); }, { passive: true });

    /* ----- חיפוש ----- */
    document.getElementById('eventsSIcon').innerHTML = icon('search', 18);
    let _et;
    qInput.addEventListener('input', () => {
      if (eClear) eClear.hidden = !qInput.value;
      clearTimeout(_et); const v = qInput.value; _et = setTimeout(() => render(v), 120);
    });
    if (eClear) {
      eClear.innerHTML = icon('dismiss', 16);
      eClear.addEventListener('click', () => { qInput.value = ''; eClear.hidden = true; render(''); qInput.focus(); });
    }

    render('');
  }

  /* ----- אתחול "מסעות במדבר" (פעם אחת, בלחיצה ראשונה על הטאב) ----- */
  function initMasaot() {
    if (masaotInited) return;
    masaotInited = true;
    if (!masaotView) return;

    const DATA = window.MASAOT || [];
    const PHASES = window.MASAOT_PHASES || [];
    const app = document.getElementById('masaotApp');
    const nav = document.getElementById('masaotNav');
    const qInput = document.getElementById('masaotQ');
    const countEl = document.getElementById('masaotCount');
    const mClear = document.getElementById('masaotClear');
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const escA = s => esc(s).replace(/"/g, '&quot;');

    function render(query) {
      const q = (query || '').trim();
      let list = DATA;
      if (q) list = list.filter(e => (e.name + ' ' + e.parsha + ' ' + e.ref + ' ' + e.note + ' ' + e.phase).indexOf(q) !== -1);
      let cur = null, html = '', open = false;
      list.forEach(e => {
        if (e.phase !== cur) {
          if (open) html += '</div>';
          cur = e.phase;
          html += '<div class="sanchor" data-sa="' + escA(e.phase) + '"></div>' +
            '<div class="period" data-sec="' + escA(e.phase) + '">' + esc(e.phase) + '</div><div class="tl">';
          open = true;
        }
        html += '<div class="item" data-ref="' + escA(e.ref || '') + '" title="פתח בקורא"><div class="dot">' + icon('flag', 18) + '</div>' +
          '<div class="body"><div class="line">' +
          '<span class="mnum">' + esc(String(e.n)) + '</span>' +
          '<span class="nm">' + esc(e.name) + '</span>' +
          (e.parsha ? '<span class="prsh" title="הפרשה שבה מסופרים אירועי התחנה">פרשת ' + esc(e.parsha) + '</span>' : '') +
          (e.ref ? '<span class="mref">' + esc(e.ref) + '</span>' : '') + '</div>' +
          (e.note ? '<div class="desc">' + esc(e.note) + '</div>' : '') +
          '</div></div>';
      });
      if (open) html += '</div>';
      if (!list.length) html = '<div class="empty">לא נמצאו תוצאות</div>';
      app.innerHTML = html;
      countEl.textContent = list.length.toLocaleString('he') + ' מסעות';
      updateActive();
    }

    nav.innerHTML = '<div class="sn-title">שלבי המסע</div>' +
      PHASES.map(p => '<button class="sn-item" data-sec="' + escA(p) + '">' + esc(p) + '</button>').join('');

    function findAnchor(sec) { return Array.prototype.find.call(app.querySelectorAll('.sanchor'), a => a.dataset.sa === sec); }
    function topOf(el) { return el.getBoundingClientRect().top - masaotView.getBoundingClientRect().top + masaotView.scrollTop; }
    function gotoSec(sec) {
      if (qInput.value.trim()) { qInput.value = ''; if (mClear) mClear.hidden = true; render(''); }
      const a = findAnchor(sec);
      if (a) masaotView.scrollTo({ top: Math.max(0, topOf(a) - 4), behavior: 'smooth' });
    }
    nav.addEventListener('click', e => { const b = e.target.closest('.sn-item'); if (b) gotoSec(b.dataset.sec); });
    function setActive(sec) { nav.querySelectorAll('.sn-item').forEach(b => b.classList.toggle('active', b.dataset.sec === sec)); }
    function updateActive() {
      const line = masaotView.getBoundingClientRect().top + 24; let act = null;
      app.querySelectorAll('.sanchor').forEach(a => { if (a.getBoundingClientRect().top <= line) act = a.dataset.sa; });
      if (act) setActive(act);
    }
    masaotView.addEventListener('scroll', () => { requestAnimationFrame(updateActive); }, { passive: true });
    app.addEventListener('click', ev => { const it = ev.target.closest('.item'); if (it && it.dataset.ref) openInOtzaria(it.dataset.ref); });

    document.getElementById('masaotSIcon').innerHTML = icon('search', 18);
    let _mt;
    qInput.addEventListener('input', () => {
      if (mClear) mClear.hidden = !qInput.value;
      clearTimeout(_mt); const v = qInput.value; _mt = setTimeout(() => render(v), 120);
    });
    if (mClear) {
      mClear.innerHTML = icon('dismiss', 16);
      mClear.addEventListener('click', () => { qInput.value = ''; mClear.hidden = true; render(''); qInput.focus(); });
    }

    render('');
  }
})();

/* ===========================================================================
 *  דיווח על שגיאה בתוכן — כפתור צף + חלונית, שליחה למייל דרך EmailJS (POST)
 *  (FormSubmit נבדק ונפסל: ה-AJAX endpoint שלו מתעלם מ-_subject ומשדות
 *  מותאמים אישית ומחזיר רק הודעה גנרית — לא מתאים לצרכינו)
 * ========================================================================= */
(function () {
  // הגדרות EmailJS — יש ליצור חשבון חינמי ב-emailjs.com, לחבר שירות מייל
  // (Gmail), וליצור תבנית (Template) עם המשתנים: name, email, tab, entry,
  // version, details, subject. יש להעתיק לכאן את שלושת הערכים מהדשבורד.
  const EMAILJS_SERVICE_ID  = 'service_7gghdnh';
  const EMAILJS_TEMPLATE_ID = 'template_qecjmom';
  const EMAILJS_PUBLIC_KEY  = 'tBRM5V_rbfHfFG5Tu';
  // EmailJS חוסם כברירת מחדל בקשות שלא מגיעות מדפדפן "אמיתי" — הפעלנו
  // ב-Account > Security את "Allow API for non-browser applications", מה
  // שדורש לצרף גם accessToken (המפתח הפרטי) לכל בקשה.
  const EMAILJS_ACCESS_TOKEN = 'DYYXa2HMkyfZpGA6tVh9r';
  const EMAILJS_URL = 'https://api.emailjs.com/api/v1.0/email/send';
  const RN_KEY = 'bio-report-name', RE_KEY = 'bio-report-email';
  let otzVersion = '';

  const fab     = document.getElementById('reportFab');
  const overlay = document.getElementById('reportOverlay');
  const closeBtn= document.getElementById('reportClose');
  const cancel  = document.getElementById('rfCancel');
  const send    = document.getElementById('rfSend');
  const nameEl  = document.getElementById('rfName');
  const emailEl = document.getElementById('rfEmail');
  const detEl   = document.getElementById('rfDetails');
  const statusEl= document.getElementById('reportStatus');
  const ctxEl   = document.getElementById('reportContext');
  if (!fab || !overlay) return;

  let sending = false;

  /* אייקונים */
  fab.innerHTML = icon('flag', 22);
  document.getElementById('reportHeadIc').innerHTML = icon('flag', 20);
  closeBtn.innerHTML = icon('dismiss', 18);
  send.innerHTML = icon('send', 18) + '<span>שלח דיווח</span>';

  const ls = {
    get(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  };

  function setStatus(msg, type) {
    statusEl.textContent = msg || '';
    statusEl.className = 'report-status' + (type ? ' ' + type : '');
  }

  /* הערך שהיה פתוח בעת הדיווח (רק בטאב הביוגרפיות) */
  function currentContext() {
    if (document.body.classList.contains('mode-seder')) return { tab: 'סדר הדורות', entry: '' };
    if (document.body.classList.contains('mode-events')) return { tab: 'לוח אירועים', entry: '' };
    let entry = '';
    if (curId != null) {
      const e = entryById(curId);
      if (e) entry = splitName(e.n).name;
    }
    return { tab: 'ביוגרפיות', entry };
  }

  function openModal() {
    nameEl.value  = ls.get(RN_KEY);
    emailEl.value = ls.get(RE_KEY);
    setStatus('');
    const ctx = currentContext();
    if (ctx.entry) {
      ctxEl.hidden = false;
      ctxEl.innerHTML = 'הדיווח מתייחס לערך: <b>' + esc(ctx.entry) + '</b>';
    } else {
      ctxEl.hidden = true;
    }
    overlay.hidden = false;
    setTimeout(() => { (nameEl.value ? detEl : nameEl).focus(); }, 30);
  }

  function closeModal() {
    if (sending) return;
    overlay.hidden = true;
  }

  function setSending(on) {
    sending = on;
    send.disabled = on;
    send.innerHTML = on
      ? '<span>שולח…</span>'
      : icon('send', 18) + '<span>שלח דיווח</span>';
  }

  async function submit() {
    if (sending) return;
    const name  = nameEl.value.trim();
    const email = emailEl.value.trim();
    const det   = detEl.value.trim();

    if (!name || !email || !det) {
      setStatus('אנא מלאו את כל השדות: שם, מייל ופרטי הדיווח.', 'error');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setStatus('כתובת המייל אינה תקינה.', 'error');
      return;
    }

    const ctx = currentContext();
    const subject = 'דיווח שגיאה בתוכן — ביוגרפיות' + (ctx.entry ? ' — ' + ctx.entry : '');

    // שמירת שם ומייל מיד עם האימות — גם אם השליחה בהמשך תיכשל, לא נאבד אותם
    ls.set(RN_KEY, name);
    ls.set(RE_KEY, email);

    setSending(true);
    setStatus('');

    // template_params — חייבים להתאים למשתנים שהוגדרו בתבנית ב-EmailJS
    const payload = {
      service_id:  EMAILJS_SERVICE_ID,
      template_id: EMAILJS_TEMPLATE_ID,
      user_id:     EMAILJS_PUBLIC_KEY,
      accessToken: EMAILJS_ACCESS_TOKEN,
      template_params: {
        subject: subject,
        name:    name,
        email:   email,
        tab:     ctx.tab,
        entry:   ctx.entry || '—',
        version: otzVersion || '—',
        details: det
      }
    };

    try {
      // network.fetch ולא fetch() ישיר: רץ בצד אוצריא ולכן אינו כפוף ל-CORS,
      // ועובר דרך מנגנון האישור של רשימת ההיתר (דורש network.access)
      const res = await Otzaria.call('network.fetch', {
        url: EMAILJS_URL,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.success) {
        const err = res.error || {};
        const msg = err.code === 'error.forbidden'
          ? 'גישת הרשת לכתובת זו אינה מאושרת.'
          : err.code === 'error.permission_denied'
          ? 'חסרה הרשאת גישה לרשת — אשרו אותה בהגדרות התוסף.'
          : (err.message || 'שגיאה לא ידועה');
        setStatus('שליחת הדיווח נכשלה — ' + msg + (err.retryable ? ' נסו שוב.' : ''), 'error');
        setSending(false);
        return;
      }
      if (!res.data.ok) {
        setStatus('שליחת הדיווח נכשלה (' + (res.data.body || ('קוד ' + res.data.status)) + '). נסו שוב.', 'error');
        setSending(false);
        return;
      }
      detEl.value = '';
      setStatus('✓ תודה! הדיווח נשלח בהצלחה.', 'success');
      setSending(false);
      setTimeout(() => { if (!sending) closeModal(); }, 2400);
    } catch (e) {
      setStatus('שליחת הדיווח נכשלה — בדקו חיבור לרשת ונסו שוב.', 'error');
      setSending(false);
    }
  }

  fab.addEventListener('click', openModal);
  closeBtn.addEventListener('click', closeModal);
  cancel.addEventListener('click', closeModal);
  send.addEventListener('click', submit);
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !overlay.hidden) closeModal(); });

  // שליפת גרסת אוצריא (best-effort) — תצורף לדיווח. הרשאת app.info.read כבר קיימת.
  if (window.Otzaria && window.Otzaria.call) {
    window.Otzaria.call('app.getInfo').then(r => {
      if (r && r.success && r.data) {
        otzVersion = (r.data.version || '') + (r.data.platform ? ' (' + r.data.platform + ')' : '');
      }
    }).catch(() => {});
  }
})();

/* החלת העדפות גופן שמורות בטעינה */
applyUserFontPrefs();

/* אם ה-SDK כבר זמין בטעינה — החל ערכת נושא נוכחית */
if (typeof window.Otzaria !== 'undefined' && window.Otzaria.call) {
  window.Otzaria.call('app.getTheme').then(r => { if (r && r.success) applyOtzariaTheme(r.data); }).catch(() => {});
}

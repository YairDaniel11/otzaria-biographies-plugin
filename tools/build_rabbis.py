# -*- coding: utf-8 -*-
"""
בונה את נתוני "ראשונים ואחרונים" של תוסף הביוגרפיות מחמשת קבצי המקור:

  1. רשימת רבנים עם ביוגרפיות מאוצר הספר העברי (CSV)         — הליבה: ~55 אלף רבנים
  2. ביוגרפיות מתוך קובץ "שנות דור" ועוד (xlsx)               — מחבר, תפקיד, לידה, פטירה, ספרים
  3. רשימות היארצייטים (xlsx)                                  — יום פטירה לפי לוח עברי
  4. הרשימה הכרונולוגית של בר-אילן (RTF)                      — מחבר, שנת לידה, ספריו וקטגוריות
  5. ספרי אוצרות התורה והשו"ת (xlsx)                           — נשמר רק מה שאומת מול שם המחבר

הפלט (תחת src/data/rabbis/):
  rb-index.js      אינדקס קל: שם, כינוי, שנים, יארצייט, ספרים — נטען עם פתיחת הטאב
  rb-<אות>.js      ביוגרפיה מלאה לכל רב, מחולק לפי אות — נטען רק כשצריך
  (אין תלות בשרת: הכול סקריפטים סטטיים שאוצריא טוענת מתוך החבילה)

6. תוסף "יומא דהילולא" (631 רבנים → תגית h; 26 ישיבות → src/data/yeshivot.js)
הרצה:  python -I tools/build_rabbis.py [--src <תיקיית המקורות>] [--report <קובץ>] [--out <תיקייה>] [--yoma <קובץ>]
"""
import argparse, collections, csv, difflib, glob, hashlib, io, json, os, re, sys
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hebdates import (MONTHS, is_leap, parse_hebrew_date, hy_to_g, name_tokens, norm_text, sort_key,
                      clean_quotes, gem)
from hebdates import _spell_norm
from rtflib import rtf_paragraphs

# הצגת "מקורות" (ספרי העיון שמהם נלקח המידע) כבויה בינתיים — להפעלה: True ובנייה מחדש
INCLUDE_SOURCES = False
# שמות (בדיוק כפי שהם ברשומה) שהוסרו לבקשת בעל התוסף — לא יחזרו בבנייה חוזרת
EXCLUDE_NAMES = {
    "ר' שניאור אשכנזי",
    "ר' נדב כהן",
    "ר' חגי לונדין",
    "ר' דן טיומקין",
    "ר' אבידן ויצמן",
    "ר' חנן חסן",
    "ר' יהושע הכט",
    "תת אלוף יוסף קסטל",
    'אברהם אביש מפפד"מ',
    "אבוש",
    "אאיליון - משפחה",
}
# רשומות שבשמן תואר "דוקטור"/"ד"ר"/"פרופסור"/"פרופ'" — הוסרו לבקשת בעל התוסף.
# גם "דוקטור, אליעזר" (שם משפחה) נמחק — לבקשת בעל התוסף.
ACADEMIC_TITLE = re.compile(
    r"דוקטור|(?<![א-ת])ד[\"'״׳]ר(?![א-ת])|(?<![א-ת])דר['׳](?![א-ת])|פרופסור|פרופ(?:['׳\"״]|(?![א-ת]))|(?<![א-ת])פרוף")


def has_academic_title(name):
    return bool(ACADEMIC_TITLE.search(name))
OUT_DIR = os.path.join(HERE, "..", "src", "data", "rabbis")
POINTS = re.compile(r"[֑-ׇ]")           # ניקוד וטעמים
csv.field_size_limit(10 ** 7)


def find(src, *patterns):
    """מחפש קובץ מקור לפי כמה תבניות (שם בעברית, ואחריו מזהה ההעלאה) — הראשונה שמצליחה."""
    for pattern in patterns:
        hits = glob.glob(os.path.join(src, pattern))
        if hits:
            return hits[0]
    sys.exit("לא נמצא קובץ מקור: " + " | ".join(patterns))


def clean_name(name):
    """ניקוי שם: בלי ניקוד, בלי מספר הבחנה בסוף ("אולמן-1", "אברהם ביניש5") ובלי סימני ?/! בסוף."""
    s = norm_text(POINTS.sub("", name or ""))
    s = re.sub(r"\s*-?\s*\d+$", "", s)
    s = re.sub(r"[\s?!]+$", "", s)
    s = re.sub(r"^[\s?!]+", "", s)
    return s


def new_rec(name, tag):
    return {"n": clean_name(name), "f": "", "k": "", "r": "", "bt": "", "by": 0, "bp": "", "dt": "", "dy": 0, "dp": "",
            "yz": None, "b": "", "s": [], "bk": [], "tags": {tag}, "approx_by": False,
            "e": "", "rb": "", "yl": "", "co": {}, "pend": []}


# מחרוזת תאריך שהיא בעצם פרוזה ("בשנת תרנ הגיע לארץ ישראל") — אין לחלץ ממנה שנה
_PROSE_WORDS = 6
PLACES = set()                       # לקסיקון מקומות (עמודות 5 ו-7 ב-CSV) — נבנה ב-load_csv
VALID_CATS = None                    # קטגוריות ספרים חוקיות (מה-RTF) — נבנה ב-load_rtf
_NOT_BIRTH_DEATH = re.compile(r"נדפס|הודפס|נדפסו|הדפסה")


# ----------------------------------------------------------------------------- שיוך ספרים
# ברשימות מצטברות (RTF של בר-אילן, שורות "בר-אילן" ב"שנות דור") רק הפריט הראשון של מחבר מאומת;
# פריטים עוקבים עשויים להיות ספרים אנונימיים/קיבוציים ("תוספות", "אוצר ההלכה") ולכן נשמרים כ"ממתינים"
# ומשויכים רק אם בכותר מופיע טוקן משם המחבר/כינויו, או שהכותר זהה לספר מאומת של אותו מחבר.
_ATTR_STOP = {"אבן", "אבי", "בן", "בר", "רבינו", "רבנו", "הרב", "רבי", "מרן", "הגאון", "הצדיק", "האדמור", "אדמור",
              "הרבי", "מורנו", "החכם", "הרה", "הגדול", "הקדוש", "הזקן", "הראשון", "האחרון"}
_ATTR_PREF = "והבלמכש"


def author_tokens(name):
    """טוקני שם להתאמה מול כותרי ספרים: בלי תארים/ניקוד, אורך >= 3, עד שם האב (ב"ר / בן ר')."""
    s = norm_text(POINTS.sub("", name or ""))
    s = re.split(r"\s(?:ב[\"״]ר|בר[\"״]|ב['׳]ר)\s|\sבן\s+ר['׳]?\s", s + " ")[0]
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    out = set()
    for t in re.split(r"[^א-ת\"'׳״]+", s):
        c = clean_quotes(t)
        if len(c) >= 3 and c not in _ATTR_STOP and c not in _SKIP_TOKENS_H:
            out.add(c)
    return out


_SKIP_TOKENS_H = {clean_quotes(x) for x in ("ר", "רבי", "הרב", "הגאון", "מהר\"ר", "הרה\"ג", "הגה\"צ", "הג\"ר", "הגר",
                                           "זצ\"ל", "זצוק\"ל", "זי\"ע", "שליט\"א")}


def title_has_token(title, toks):
    """האם בכותר מופיעה מילה השווה לאחד הטוקנים (גם עם אות שימוש/קידומת: הרמב"ם, ברש"י, והרשב"א)."""
    for w in re.split(r"[^א-ת\"'׳״]+", title):
        w = clean_quotes(w)
        if not w:
            continue
        if w in toks:
            return True
        for k in (1, 2):
            if len(w) - k >= 3 and all(ch in _ATTR_PREF for ch in w[:k]) and w[k:] in toks:
                return True
    return False


# שמות פרטיים/משפחה נפוצים: התאמת טוקן כזה בלבד בכותר היא ראיה חלשה (ניתנת לסתירה ע"י קטלוג)
COMMON_GIVEN = {clean_quotes(x) for x in (
    "אברהם יצחק יעקב משה אהרן יוסף דוד שלמה שמואל ישראל אליהו אליעזר יהודה שמעון מנחם מרדכי נתן צבי חיים זאב בנימין "
    "יחיאל מאיר עקיבא נחמן פנחס רפאל ראובן לוי יהושע ישעיהו ירמיהו אפרים מנשה גרשון זלמן שניאור ברוך נפתלי אשר דב בער "
    "יונה אריה ליב לייב אלעזר זכריה חנניה טוב עמרם הלל כהן כץ שמחה עובדיה יצחק אלחנן ישעיה דניאל אלכסנדר "
    "יום מנדל מענדל נחום פינחס שרגא יקותיאל טוביה הירש אלימלך זכאי יוסי חנוך").split()}


def tk_norm(t):
    """נרמול טוקן שם להשוואה: כתיב (ווילנא/וילנא), בלי ה' הידיעה בתחילת טוקן ארוך."""
    t = _spell_norm(clean_quotes(t))
    return t[1:] if len(t) >= 4 and t[0] == "ה" else t


def _tkm(a, b):
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


_AUTH_STOP2 = _ATTR_STOP | {"אבו", "אבא", "מכון", "הוצאת", "אוסף", "עורך", "מהדיר", "מחבר"}


def _words(s):
    return [w for w in (clean_quotes(x) for x in re.split(r"[^א-ת\"'׳״]+", s or "")) if w]


def parse_author(a, years=None, nicks=()):
    """מחרוזת מחבר מקטלוג -> (טוקני שם מנורמלים, כינויים מנורמלים, (שנת לידה, שנת פטירה))."""
    a = norm_text(POINTS.sub("", a or ""))
    ys = years or (0, 0)
    m = re.search(r"(?<!\d)(\d{3,4})\s*-\s*(\d{3,4})(?!\d)", a)
    if m and not years:
        ys = (int(m.group(1)), int(m.group(2)))
    nk = set()
    for g in re.findall(r"[\[(]([^\])]*)[\])]", a):
        nk |= {tk_norm(w) for w in _words(g) if len(w) >= 2}
    for g in nicks:
        nk |= {tk_norm(w) for w in _words(g) if len(w) >= 2}
    main = re.sub(r"\([^)]*\)|\[[^\]]*\]|\d{3,4}\s*-\s*\d{3,4}|\d{3,4}", " ", a)
    toks = {tk_norm(w) for w in _words(main) if len(w) >= 3 and w not in _AUTH_STOP2 and w not in _SKIP_TOKENS_H}
    return frozenset(toks), frozenset(nk), ys


_CONT = {"על", "חלק", "חלקים", "כרך", "מהדורה", "מהדורת", "הוצאת"}


def title_variants(t):
    """וריאנטים של כותר להשוואה: מילים עבריות בלבד; בלי סוגריים; לפני מקף/נקודתיים; קטוע לפני "על/חלק..."; בלי "ספר/שו"ת" בראש."""
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t or "")
    bases = [t]
    part = re.split(r"\s[-–—:\\]\s|[:\\]", t)[0]
    if part != t:
        bases.append(part)
    out = set()
    for b in bases:
        words = _words(b)
        if not words:
            continue
        cands = [words]
        for i, w in enumerate(words):
            if i >= 1 and w in _CONT:
                cands.append(words[:i]); break
        for ws in list(cands):
            if len(ws) > 1 and ws[0] in ("ספר", "שות"):
                cands.append(ws[1:])
        for ws in cands:
            k = " ".join(ws)
            if len(k.replace(" ", "")) >= 4:
                out.add(k)
    return out


_NICK_GENERIC = {"בעל", "זקן", "רבינו", "רבנו", "הרב", "רבי", "מרן", "גאון", "הגאון", "הקדוש", "החסיד", "הגדול"}


class RInfo:
    """זהות המחבר (הרשומה) להתאמה מול מחברי קטלוג."""

    def __init__(self, rec):
        names = [rec["n"]] + list(rec.get("pnames", []))
        self.toks = set()
        self.words = set()
        for nm in names:
            self.toks |= {tk_norm(t) for t in author_tokens(nm)}
            self.words |= {tk_norm(w) for w in _words(nm) if len(w) >= 2}
        self.words |= {tk_norm(w) for w in _words(rec["k"]) if len(w) >= 2}
        self.toks -= {t for t in self.toks if len(t) < 3}
        self.by, self.dy = rec["by"], rec["dy"]

    def _years_ok(self, ys):
        if not (ys[0] and ys[1] and (self.by or self.dy)):
            return False
        return ((not self.by) or abs(self.by - ys[0]) <= 3) and ((not self.dy) or abs(self.dy - ys[1]) <= 3)

    def match(self, ainfo):
        at, an, ys = ainfo
        hit = [t for t in self.toks if t in at or any(_tkm(t, x) for x in at)]
        score = len(hit)
        nickhit = [n for n in an if n in self.words and len(n) >= 3 and n not in COMMON_GIVEN and n not in _NICK_GENERIC]
        if score >= 2:
            # שני טוקנים שכולם שמות פרטיים נפוצים ("יצחק","יהודה") אינם מספיקים בלי שנות חיים תואמות
            return any(h not in COMMON_GIVEN for h in hit) or self._years_ok(ys)
        if nickhit and (score >= 1 or any(len(n) >= 4 for n in nickhit)):
            return True
        if score == 1 and ys[0] and ys[1] and (self.by or self.dy):
            okb = (not self.by) or abs(self.by - ys[0]) <= 3
            okd = (not self.dy) or abs(self.dy - ys[1]) <= 3
            if okb and okd and (self.by or self.dy) and hit[0] not in COMMON_GIVEN and len(hit[0]) >= 4:
                return True
        return False

    def overlaps(self, ainfo):
        at, an, _ = ainfo
        return any(t in at or t in an for t in self.toks) or any(n in self.words for n in an if len(n) >= 3)


class Catalog:
    """אינדקס זמני בזיכרון: כותר מנורמל -> מחברים (מקטלוגי הספרייה/הברי-בוקס/אוצר-החכמה/מאגר הביוגרפיות).
    משמש כראיית אימות בזמן הבנייה בלבד — שום טקסט ממנו אינו נכתב לתוצר."""

    def __init__(self):
        self.idx = collections.defaultdict(set)       # וריאנט כותר -> {מזהה מחבר}
        self.full = collections.defaultdict(set)      # כותר מלא (ללא וריאנט קטוע) -> {מזהה מחבר}
        self.authors = []                             # מזהה -> (tokens, nicks, years)
        self._ids = {}
        self.rows = 0

    def _aid(self, key, ainfo):
        i = self._ids.get(key)
        if i is None:
            i = self._ids[key] = len(self.authors)
            self.authors.append(ainfo)
        return i

    def add(self, title, author_key, ainfo):
        if not ainfo[0] and not ainfo[1]:
            return
        aid = self._aid(author_key, ainfo)
        self.rows += 1
        vs = title_variants(title)
        for v in vs:
            self.idx[v].add(aid)
        w = " ".join(_words(re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title or "")))
        if len(w.replace(" ", "")) >= 4:
            self.full[w].add(aid)

    def verify(self, title, rinfo):
        for v in title_variants(title):
            for aid in self.idx.get(v, ()):
                if rinfo.match(self.authors[aid]):
                    return True
        return False

    def contradicts(self, title, rinfo):
        """אותו כותר מלא קיים בקטלוג, וכל מחבריו אינם תואמים ל-R ואין חפיפת טוקנים כלל."""
        w = " ".join(_words(re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title or "")))
        aids = self.full.get(w)
        if not aids or len(w.replace(" ", "")) < 6:
            return False
        return all(not rinfo.match(self.authors[a]) and not rinfo.overlaps(self.authors[a]) for a in aids)


def build_catalog(seforim_db, hb_db, bios_gz, log):
    """בונה Catalog מהמקורות הקיימים (קריאה בלבד, ללא כתיבה/העתקה)."""
    import sqlite3, gzip
    cat = Catalog()
    cache = {}

    def A(a):
        r = cache.get(a)
        if r is None:
            r = cache[a] = parse_author(a)
        return r

    def ro(path):
        return sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro&immutable=1", uri=True)

    n = collections.Counter()
    if seforim_db and os.path.exists(seforim_db):
        c = ro(seforim_db)
        for t, a in c.execute("select b.title, a.name from book b join book_author ba on ba.bookId=b.id join author a on a.id=ba.authorId"):
            cat.add(t, a, A(a)); n["seforim"] += 1
        c.close()
    if hb_db and os.path.exists(hb_db):
        c = ro(hb_db)
        seen = set()
        for t, a in c.execute("select title, author from hebrew_books"):
            if t and a and (t, a) not in seen:
                seen.add((t, a)); cat.add(t, a, A(a)); n["hb"] += 1
        seen = set()
        for t, a in c.execute("select title, authors from otzar_hahochma"):
            if not t or not a or (t, a) in seen:
                continue
            seen.add((t, a))
            try:
                names = json.loads(a)
            except Exception:
                names = [a]
            for nm in names if isinstance(names, list) else [names]:
                if isinstance(nm, str) and nm:
                    cat.add(t, nm, A(nm)); n["oh"] += 1
        c.close()
    if bios_gz and os.path.exists(bios_gz):
        # מאגר הביוגרפיות המובנה של אוצריא (AGPL-3.0, ייחוס: abaye) — ראיית אימות בלבד, בלי העתקת טקסטים לתוצר
        with gzip.open(bios_gz, "rt", encoding="utf-8") as fh:
            g = json.load(fh)
        for e in g.get("entries", []):
            works = e.get("works") or []
            if not works:
                continue

            def yr(d):
                m = re.search(r"\d{3,4}", str((d or {}).get("gregorian", "")))
                return int(m.group(0)) if m else 0
            nicks = [k for k in (e.get("known_as") or []) if isinstance(k, str)]
            ai = parse_author(e.get("name", ""), years=(yr(e.get("born")), yr(e.get("died"))), nicks=nicks)
            for w in works:
                if isinstance(w, dict) and w.get("title"):
                    cat.add(w["title"], "bio:" + e.get("id", ""), ai); n["bios"] += 1
    log("catalog rows:", dict(n), "distinct title variants:", len(cat.idx), "authors:", len(cat.authors))
    return cat


def title_token_hits(title, toks):
    """הטוקנים (מנורמלים) מתוך toks שמופיעים בכותר (גם עם אות שימוש/קידומת)."""
    hits = set()
    for w in re.split(r"[^א-ת\"'׳״]+", title):
        w = clean_quotes(w)
        if not w:
            continue
        if w in toks:
            hits.add(w)
        for k in (1, 2):
            if len(w) - k >= 3 and all(ch in _ATTR_PREF for ch in w[:k]) and w[k:] in toks:
                hits.add(w[k:])
    return hits


def resolve_pending(rec, legacy=False, catalog=None):
    """משייך ספרים ממתינים למחבר. סדר: (1) אימות לפי קטלוג; (2) כותר זהה לספר מאומת של המחבר;
    (3) טוקן שם/כינוי בכותר (טוקן פרטי נפוץ בלבד נסתר אם הקטלוג מייחס את הכותר למחבר אחר לגמרי).
    מחזיר (התקבלו, נדחו, שוחזרו, הוסרו, אומתו_בקטלוג) — רשימות [כותר, קטגוריה]."""
    if not rec["pend"]:
        return [], [], [], [], []
    toks = set(author_tokens(rec["n"])) | author_tokens(rec["k"])
    toks |= {t for t in (author_tokens(nm) for nm in rec.get("pnames", [])) for t in t}
    auth = [bk_key(b[0]) for b in rec["bk"] if bk_key(b[0])]
    have = {(bk_key(b[0]), b[1]) for b in rec["bk"]}
    rinfo = RInfo(rec) if catalog is not None else None
    acc, rej, restored, removed, verified = [], [], [], [], []
    for t, c in rec["pend"]:
        key = bk_key(t)
        hits = title_token_hits(t, toks)
        v1 = legacy or bool(hits)
        v1_auth = False
        if not v1 and key:
            v1_auth = any(a == key or (min(len(a), len(key)) >= 5 and (a in key or key in a)) for a in auth)
            v1 = v1_auth
        in_cat = bool(catalog is not None and catalog.verify(t, rinfo))
        weak = bool(hits) and not v1_auth and all(tk_norm(h) in COMMON_GIVEN or len(h) < 4 for h in hits)
        if in_cat:
            ok = True
            verified.append([t, c])
            if not v1:
                restored.append([t, c])
        elif v1 and weak and catalog is not None and catalog.contradicts(t, rinfo):
            ok = False
            removed.append([t, c])
        else:
            ok = v1
        if ok:
            if (key, c) not in have and not (not c and any(h[0] == key for h in have)):
                have.add((key, c)); rec["bk"].append([t, c])
            acc.append([t, c])
        else:
            rej.append([t, c])
    rec["pend"] = []
    return acc, rej, restored, removed, verified


def set_date(rec, which, text):
    """which: 'b' | 'd'. ממלא text/year/יארצייט מתוך מחרוזת תאריך."""
    text = norm_text(text)
    if not text:
        return
    if len(text.split()) > _PROSE_WORDS or _NOT_BIRTH_DEATH.search(text):
        # פרוזה/שנת הדפסה: נשמר כטקסט לתצוגה בלבד, בלי שנה מפוענחת
        if which == "b":
            rec["bt"] = rec["bt"] or text
        else:
            rec["dt"] = rec["dt"] or text
        return
    p = parse_hebrew_date(text)
    year = hy_to_g(p["hy"], p["month"], p["day"]) if p["hy"] else p["greg"]
    if which == "b":
        rec["bt"] = rec["bt"] or text
        if not rec["by"] and year:
            rec["by"] = year
            rec["approx_by"] = p["approx"]
    else:
        if not p["hy"] and p["month"] < 0 and not re.search(r"\d", text):
            # אין בשדה תאריך: מקום אמיתי (מהלקסיקון) נשמר כמקום; שבר שנה ("ש - בערך") נשמר כטקסט
            if text in PLACES:
                rec["dp"] = rec["dp"] or text
            else:
                rec["dt"] = rec["dt"] or text
            return
        rec["dt"] = rec["dt"] or text
        if not rec["dy"] and year:
            rec["dy"] = year
        if rec["yz"] is None and p["day"] and p["month"] >= 0:
            rec["yz"] = [p["day"], p["month"]]


# ----------------------------------------------------------------------------- מקורות
def load_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))[1:]
    for r in rows:                                   # לקסיקון מקומות — להבחנה בין מקום לשבר-שנה בשדה הפטירה
        for c in (5, 7):
            if r[c].strip():
                PLACES.add(norm_text(r[c]))
    recs = []
    for r in rows:
        name = norm_text(r[2])
        if not name or re.search(r"\s-\s*קה[לי]*ה", name):
            continue                                 # "X - קהילה": קהילה ולא אדם
        bio_text = norm_text(r[10])
        tail = ""
        mref = re.search(r"\s*ראה(?: גם)?\s*:\s*(.*)$", name)
        if mref and bio_text:
            tail, name = mref.group(1).strip(), name[:mref.start()].strip()
        # הפניות ("X ראה: Y") ורשומות "- משפחה" ריקות אינן אנשים — נשמטות
        if not bio_text and (re.search(r"(?<![א-ת])ראה(?: גם)?\s*:?", name) or re.search(r"\s-\s*משפחה\s*$", name)):
            continue
        rec = new_rec(name, "c")
        rec["f"] = norm_text(r[3])
        rec["bp"] = norm_text(r[5])
        rec["dp"] = norm_text(r[7])
        nick = norm_text(r[8])
        rec["k"] = (nick + (" " if nick and tail else "") + ("ראה: " + tail if tail else "")).strip()
        rec["b"] = bio_text
        rec["s"] = [x.strip() for x in r[11].split(";") if x.strip()]
        set_date(rec, "b", r[4])
        set_date(rec, "d", r[6])
        recs.append(rec)
    return recs


def split_books(cell):
    """"אבודרהם (הלכה ומנהג - ראשונים); פירוש קדמון (מפרשי ש"ס)" -> [(כותר, קטגוריה)]"""
    out = []
    for part in re.split(r";\s*", norm_text(cell)):
        part = part.strip()
        if not part:
            continue
        if len(part) > 120 and "," in part:        # רשימה שלמה בתא אחד — מפצלים לפי פסיק
            for sub in part.split(","):
                sub = sub.strip()
                if sub:
                    out.append((sub, ""))
            continue
        m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", part)
        if m and m.group(1) and (VALID_CATS is None or m.group(2).strip() in VALID_CATS):
            out.append((m.group(1).strip(), m.group(2).strip()))
        else:
            out.append((part, ""))          # סוגריים שאינם קטגוריה ("(ג' חלקים)") נשארים בכותר
    return out


def load_shnot(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    rows = rows[1:]
    g = lambda r, i: norm_text(str(r[i])) if r[i] not in (None, "") else ""
    authors = collections.OrderedDict()
    for r in rows:
        who = g(r, 20)
        if not who or who in ("לא ידוע",):
            continue
        a = authors.setdefault(who, {"role": collections.Counter(), "birth": "", "death": "", "gbirth": 0,
                                    "srcs": [], "books": [], "pend": [], "tag": "s", "yz_only": False, "notes": []})
        role, title, src, birth, death = g(r, 3), g(r, 4), g(r, 7), g(r, 13), g(r, 16)
        group = g(r, 17)
        if src == "רשימת היארצייטים":
            a["yz_only"] = True
        elif src and src not in a["srcs"]:
            a["srcs"].append(src)
        if role and (len(role) > 60 or re.search(r"מספריו|מחיבוריו|יש להבדיל|נדפס|חיבר גם", role)):
            if role not in a["notes"]:
                a["notes"].append(role)               # פרוזה — לביוגרפיה, לא לתפקיד
        elif role:
            a["role"][role] += 1
        if re.fullmatch(r"\d{3,4}", birth):          # שורות בר-אילן: שנת לידה לועזית
            a["gbirth"] = a["gbirth"] or int(birth)
        elif birth and not a["birth"]:
            a["birth"] = birth
        if death and not a["death"]:
            a["death"] = death
        if title:
            items = split_books(title)
            if re.fullmatch(r"\d{3,4}", birth) and group == "Personal" and not src:
                # שורת "בר-אילן" (רשימת כותרים מצטברת): רק הכותר הראשון מאומת
                a["books"] += items[:1]; a["pend"] += items[1:]
            else:
                a["books"] += items                     # שורה מפורטת: הכותר והמחבר מפורשים
    recs = []
    for who, a in authors.items():
        rec = new_rec(who, "s")
        rec["r"] = a["role"].most_common(1)[0][0] if a["role"] else ""
        if a["gbirth"]:
            rec["by"] = a["gbirth"]
            rec["bt"] = str(a["gbirth"])
        set_date(rec, "b", a["birth"])
        set_date(rec, "d", a["death"])
        rec["s"] = a["srcs"][:3]
        rec["b"] = " ".join(a["notes"])
        seen = set()
        for t, c in a["books"]:
            if t not in seen:
                seen.add(t); rec["bk"].append([t, c])
        rec["pend"] = [[t, c] for t, c in a["pend"] if t not in seen]
        recs.append(rec)
    return recs


def load_yahrzeit(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    recs = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not r[3]:
            continue
        name = norm_text(POINTS.sub("", str(r[3])))
        rec = new_rec(name, "y")
        day = gem(clean_quotes(str(r[0]))) if r[0] else 0
        mtxt = clean_quotes(str(r[1])).strip() if r[1] else ""
        if not r[0] and r[2]:
            pd = parse_hebrew_date(str(r[2]))              # התאריך המלא נמצא בעמודת השנה
            if pd["day"] and pd["month"] >= 0:
                day, mtxt = pd["day"], MONTHS[pd["month"]]
        mtxt = {"כסליו": "כסלו", "חשוון": "חשון"}.get(mtxt, mtxt)
        if mtxt in MONTHS and 1 <= day <= 30:
            rec["yz"] = [day, MONTHS.index(mtxt)]
            rec["dt"] = ("%s %s" % (str(r[0]).strip(), mtxt)) + ((" " + norm_text(str(r[2]))) if r[2] else "")
        if r[2] and rec["yz"] and rec["yz"][1] == 5:
            py = parse_hebrew_date(str(r[2]))
            if py["hy"] and is_leap(py["hy"]):
                rec["yz"][1] = 13                  # "אדר" בשנה מעוברת = אדר ב'
        if r[2]:
            p = parse_hebrew_date(str(r[2]))
            if p["hy"]:
                rec["dy"] = hy_to_g(p["hy"], rec["yz"][1] if rec["yz"] else -1, rec["yz"][0] if rec["yz"] else 0)
        if not rec["dy"] and re.search(r"אלפים|ד['׳]\s*ת", name):
            # השנה מוטמעת בשם ("..., ד' אלפים תתס"ה, קבור ...")
            pn = parse_hebrew_date(name)
            if pn["hy"]:
                rec["dy"] = hy_to_g(pn["hy"], rec["yz"][1] if rec["yz"] else -1, rec["yz"][0] if rec["yz"] else 0)
        if r[4]:
            rec["bk"] = [[t, c] for t, c in split_books(str(r[4]))]
        rec["r"] = norm_text(str(r[7])) if r[7] else ""
        recs.append(rec)
    return recs


def load_rtf(path):
    paras = rtf_paragraphs(path)
    cats = collections.Counter()
    for p in paras:
        m = re.match(r"^.*\(([^()]*)\)\s*$", p)
        if m:
            cats[m.group(1)] += 1
    catset = {c for c, n in cats.items() if n >= 4}
    global VALID_CATS
    VALID_CATS = catset
    started = False
    authors, cur = [], None
    hdr_seen_item = {}
    hdr = re.compile(r"^(?P<name>.*?)\s*(?:\((?P<y>\d{3,4})(?P<q>\?)?\))?\s*:\|(?P<rest>.*)$")
    for p in paras:
        if p.startswith("*   *"):
            break
        m = hdr.match(p)
        if m:
            started = True
            name = norm_text(m.group("name"))
            cur = new_rec(name, "r")
            if m.group("y"):
                cur["by"] = int(m.group("y"))
                cur["bt"] = str(cur["by"]) + ("?" if m.group("q") else "")
                cur["approx_by"] = bool(m.group("q"))
            authors.append(cur)
            p = norm_text(m.group("rest"))
            if not p:
                hdr_seen_item[id(cur)] = True        # כותרת בלי פריט: אין פריט מאומת
        if not started or cur is None or not p:
            continue
        m2 = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", p)
        item = [m2.group(1).strip(), m2.group(2)] if (m2 and m2.group(2) in catset) else [p, ""]
        # רק הפריט שבשורת הכותרת מאומת; הבאים אחריו ממתינים לאימות שם-מחבר
        (cur["pend"] if hdr_seen_item.get(id(cur)) else cur["bk"]).append(item)
        hdr_seen_item[id(cur)] = True
    return authors


YOMA_CATS = {"רבנים ופוסקים": "רב ופוסק", "ראשי ישיבות": "ראש ישיבה", "אדמורי\"ם": "אדמו\"ר",
             "בעלי מוסר": "בעל מוסר", "קבלה": "מקובל"}


def load_yoma(path):
    """תוסף "יומא דהילולא" (קובץ .otzplugin או js/data.js): מחזיר (רבנים כרשומות, ישיבות כרשימת dict כמות שהן, סטטיסטיקה).
    קישורי bioUrl (חיצוניים) אינם נשמרים. ספרים: מפוצלים לפי פסיקים שמחוץ לסוגריים."""
    import zipfile
    if path.lower().endswith((".otzplugin", ".zip")):
        with zipfile.ZipFile(path) as z:
            js = z.read("js/data.js").decode("utf-8")
    else:
        with io.open(path, encoding="utf-8") as fh:
            js = fh.read()
    dec = json.JSONDecoder()

    def const(name):
        i = js.index("const " + name)
        j = js.index("=", i) + 1
        while js[j] in " \t\r\n":
            j += 1
        return dec.raw_decode(js, j)[0]

    books, yesh = const("EMBEDDED_BOOKS"), const("EMBEDDED_YESHIVOT")
    st = collections.Counter()
    recs = []

    def year_of(txt, month=-1, day=0):
        t = re.sub(r"\[[^\]]*\]|~", "", txt or "").strip()
        if not t or t == "?":
            return 0, ""
        if not re.search(r"[א-ת]", t):
            return 0, t
        hy = parse_hebrew_date(t)["hy"]
        return (hy_to_g(hy, month, day) if hy else 0), t

    plus = lambda t: re.sub(r"\s*\+\s*", ", ", norm_text(t or ""))      # "פדובה + רג'ו" -> "פדובה, רג'ו"

    for x in books:
        name = norm_text(x["author"])
        name = re.sub(r"^רבי\s+", "ר' ", name)
        rec = new_rec(name, "h")
        rec["s"] = ["יומא דהילולא"]
        dd = norm_text(x.get("deathDate") or "")
        dy_txt = re.sub(r"\[[^\]]*\]|~", "", x.get("deathYear") or "").strip()
        # יום+חודש (אדר/אדר א'/אדר ב' לפי הכתוב; "אדר" בשנה מעוברת = אדר ב')
        pd = parse_hebrew_date((dd + " " + dy_txt).strip()) if dd else None
        if pd and pd["day"] and pd["month"] >= 0:
            rec["yz"] = [pd["day"], pd["month"]]
        m_ = rec["yz"][1] if rec["yz"] else -1
        d_ = rec["yz"][0] if rec["yz"] else 0
        rec["dy"], _t = year_of(x.get("deathYear"), m_, d_)
        rec["by"], bt = year_of(x.get("birthYear"))
        if not rec["by"] and not rec["dy"]:
            # אין שנים בשדות — ניסיון מהתקופה ("תמ"ז-תק"ג")
            parts = re.split(r"\s*-\s*", re.sub(r"\[[^\]]*\]", "", x.get("era") or ""))
            if len(parts) == 2:
                rec["by"], bt = year_of(parts[0]); rec["dy"], _t = year_of(parts[1], m_, d_)
        rec["approx_by"] = "~" in (x.get("birthYear") or "") or "?" in (x.get("birthYear") or "")
        if bt and re.search(r"[א-ת]", bt):
            rec["bt"] = bt
        if dd or dy_txt:
            rec["dt"] = (dd + " " + dy_txt).strip()
        rec["bp"] = plus(x.get("birthLocation"))
        rec["dp"] = plus(x.get("deathLocation"))
        rec["e"] = norm_text(x.get("era") or "")
        rec["yl"] = plus(x.get("yeshivaLocation"))
        rab = norm_text(x.get("rabbinut") or "")
        cat = norm_text(x.get("category") or "")
        if rab:
            rec["rb"] = plus(rab)
            if re.match(r"^(ישיבת|ישיבה|רב )", rab) or "[" in rab:
                role = rab
            else:
                role = "רב ב" + ", ".join(p.strip() for p in rab.split("+") if p.strip())
        else:
            role = ""
        cats = YOMA_CATS.get(cat, cat)
        rec["r"] = (cats + (" - " + role if role and cats else role)) if (cats or role) else ""
        co = {}
        for k, key in (("a", "activityCoord"), ("d", "deathCoord"), ("b", "birthCoord")):
            v = re.sub(r"\s+", "", x.get(key) or "")
            if v:
                co[k] = v
        rec["co"] = co
        # ספרים: title (העיקרי) + books (פסיקים שמחוץ לסוגריים)
        def split_top(text):
            out_, depth, cur = [], 0, ""
            for ch in text or "":
                if ch in "([":
                    depth += 1
                elif ch in ")]":
                    depth = max(0, depth - 1)
                if ch == "," and depth == 0:
                    out_.append(cur); cur = ""
                else:
                    cur += ch
            out_.append(cur)
            return out_
        titles = [norm_text(i) for i in split_top(x.get("title")) + split_top(x.get("books")) if norm_text(i)]
        seen = set()
        for t in titles:
            k = bk_key(t)
            if k and k not in seen:
                seen.add(k); rec["bk"].append([t, ""])
        if x.get("bioUrl"):
            st["url_dropped"] += 1
        recs.append(rec)
    return recs, yesh, st


def load_otzrot(path):
    """אוצרות התורה/השו"ת. עמודת "פרטים נוספים" אינה מיושרת תמיד עם המחבר,
    ולכן נשמרת רק כשאחד מרכיבי שם המחבר מופיע בה (אימות)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)][1:]
    out, total, verified = [], 0, 0
    for r in rows:
        if not r[1]:
            continue
        total += 1
        author = norm_text(str(r[2])) if r[2] else ""
        details = norm_text(str(r[6])) if r[6] else ""
        toks = [t for t in name_tokens(author, csv_style="," in author) if len(t) > 2]
        ok = bool(toks) and len(details) > 0 and sum(1 for t in toks if t in clean_quotes(details)) >= min(2, len(toks))
        if ok:
            verified += 1
        city = norm_text(str(r[4])) if r[4] and str(r[4]) != "None" else ""
        year = norm_text(str(r[5])) if r[5] and str(r[5]) != "None" else ""
        out.append({"title": norm_text(str(r[1])), "author": author, "subject": norm_text(str(r[3])) if r[3] and str(r[3]) != "None" else "",
                    "city": city, "year": year, "details": details if ok else "", "db": norm_text(str(r[0]))})
    return out, total, verified


# ----------------------------------------------------------------------------- איחוד
def yzn(y):
    """יום+חודש להשוואה: אדר ב' (13) נחשב כמו אדר (5) — מקורות שונים כותבים כל אחד אחרת."""
    return (y[0], 5 if y[1] == 13 else y[1])


def compat(a, b, tol_b=4, tol_d=2):
    """בדיקת התאמת שנים: מחזיר (מתאים?, יש_ראיה_מחזקת?)."""
    strong = False
    for ka, kb, tol in (("by", "by", tol_b), ("dy", "dy", tol_d)):
        if a[ka] and b[kb]:
            if abs(a[ka] - b[kb]) > tol:
                return False, False
            strong = True
    if a["yz"] and b["yz"]:
        if yzn(a["yz"]) == yzn(b["yz"]):
            strong = True               # אותו יום פטירה — ראיה חזקה
        elif a["dy"] and b["dy"] and a["dy"] != b["dy"]:
            return False, False         # יום פטירה שונה ושנה שונה — אנשים שונים
    return True, strong


def tok_match(a, b):
    """התאמת טוקנים עם סובלנות לכתיב (וריאנטים כמו שניאורסון/שניאורסאהן, הגר/האגר)."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.82


class Matcher:
    """אינדקס של רשומות לפי טוקנים ולפי תאריך פטירה מלא — לאיתור רשומה מתאימה לרשומה חיצונית."""

    def __init__(self, recs, csv_style=True):
        self.recs = recs
        self.csv_style = csv_style
        self.toks = []
        self.inv = collections.defaultdict(list)
        self.yzidx = collections.defaultdict(list)       # (שנת פטירה, יום, חודש) -> אינדקסים
        for r in recs:
            self._index(r)

    def _index(self, r):
        i = len(self.toks)
        ts = set(name_tokens(r["n"], csv_style=self.csv_style))
        self.toks.append(ts)
        for t in ts:
            self.inv[t].append(i)
        if r["dy"] and r["yz"]:
            self.yzidx[(r["dy"],) + yzn(r["yz"])].append(i)

    def add(self, r):
        self.recs.append(r)
        self._index(r)

    def _by_death_date(self, ext, et):
        """מסלול שני: אותו תאריך פטירה מלא (שנה+יום+חודש) + טוקן שם משותף (בכתיב מקורב)."""
        if not (ext["dy"] and ext["yz"]):
            return None
        scored = []
        for i in self.yzidx.get((ext["dy"],) + yzn(ext["yz"]), ()):
            shared = [t for t in et if any(tok_match(t, c) for c in self.toks[i])]
            if not shared:
                continue
            rare = any(len(self.inv.get(t, ())) <= 60 for t in shared)
            if len(shared) >= 2 or rare:
                scored.append((len(shared), i))
        if not scored:
            return None
        scored.sort(reverse=True)
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None
        return scored[0][1]

    def find(self, ext):
        et = set(name_tokens(ext["n"], csv_style=False))
        if not et:
            return None
        hit = self._find_by_name(ext, et)
        return hit if hit is not None else self._by_death_date(ext, et)

    def _find_by_name(self, ext, et):
        if len(et) < 2:
            return None
        # הטוקן הנדיר ביותר מצמצם את המועמדים
        rare = min(sorted(et), key=lambda t: len(self.inv.get(t, ())) or 10 ** 9)      # sorted: בנייה דטרמיניסטית
        cands = self.inv.get(rare, [])
        if not cands or len(cands) > 4000:
            return None
        tol_b = 25 if ext["approx_by"] or "r" in ext["tags"] else 4
        best = []
        for i in cands:
            ct = self.toks[i]
            if not (et <= ct or (ct <= et and len(ct) >= 2)):
                continue
            ok, strong = compat(ext, self.recs[i], tol_b=tol_b)
            if not ok:
                continue
            exact_date = bool(ext["yz"] and self.recs[i]["yz"] and yzn(ext["yz"]) == yzn(self.recs[i]["yz"]))
            # בלי ראיית שנים — נדרש שם ארוך (3+ טוקנים) והתאמה מלאה
            if not strong and not (len(et) >= 3 and et == ct):
                continue
            # התאמת תת-קבוצה בלבד (לא שוויון) עם שם קצר — מסוכן, אלא אם יום הפטירה זהה
            if et != ct and len(et) < 3 and not exact_date:
                continue
            score = (2 if et == ct else 1, 1 if strong else 0)
            best.append((score, i))
        if not best:
            return None
        best.sort(reverse=True)
        if len(best) > 1 and best[0][0] == best[1][0]:
            return None                         # עמימות — לא מאחדים
        return best[0][1]


def bk_key(title):
    """מפתח השוואה לכותר ספר: אותיות עבריות בלבד (כך "אגרות משה" ו"אגרות משה – שו"ת" לא תמיד נבלעים, אך כפילות מדויקת כן)."""
    return re.sub(r"[^א-ת]", "", title)


def merge_into(core, ext):
    """משלים שדות חסרים ברשומת הליבה מרשומה חיצונית; מוסיף ספרים ומקורות."""
    for k in ("r", "bt", "bp", "dt", "dp"):
        if not core[k] and ext[k]:
            core[k] = ext[k]
    for k in ("by", "dy"):
        if not core[k] and ext[k]:
            core[k] = ext[k]
    if core["yz"] is None and ext["yz"]:
        core["yz"] = ext["yz"]
    have = {(bk_key(b[0]), b[1]) for b in core["bk"]}
    for t, c in ext["bk"]:
        if (bk_key(t), c) not in have and not (not c and any(h[0] == bk_key(t) for h in have)):
            have.add((bk_key(t), c)); core["bk"].append([t, c])
    for s in ext["s"]:
        if s not in core["s"]:
            core["s"].append(s)
    for k in ("e", "rb", "yl"):
        if not core[k] and ext[k]:
            core[k] = ext[k]
    for k, v in ext["co"].items():
        core["co"].setdefault(k, v)
    if ext["pend"]:
        core["pend"] += ext["pend"]
        core.setdefault("pnames", []).append(ext["n"])
        core.setdefault("pnames", []).extend(ext.get("pnames", []))
    core["tags"] |= ext["tags"]


def dedupe_externals(recs):
    """מאחד רשומות חיצוניות זהות לגמרי בשם ובשנים (למשל אותו מחבר ב-RTF וב"שנות דור")."""
    by_key = {}
    out = []
    for r in recs:
        key = " ".join(sorted(name_tokens(r["n"], csv_style=False)))
        hit = None
        for cand in by_key.get(key, []):
            ok, strong = compat(r, cand, tol_b=25)
            if ok and (strong or len(key.split()) >= 3):
                hit = cand
                break
        if hit is not None:
            merge_into(hit, r)
        else:
            by_key.setdefault(key, []).append(r)
            out.append(r)
    return out


def era_of(rec):
    y = rec["by"] or (rec["dy"] - 60 if rec["dy"] else 0)
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.expanduser("~/הורדות"))
    ap.add_argument("--report", default="")
    ap.add_argument("--out", default=OUT_DIR, help="תיקיית פלט (ברירת מחדל: src/data/rabbis); קבצי *.js ישנים בה נמחקים")
    ap.add_argument("--yeshivot-out", default=os.path.join(HERE, "..", "src", "data", "yeshivot.js"))
    ap.add_argument("--yoma", default=os.path.expanduser(
        "~/Desktop/מאגרי גיטאב/אוצריא/תוספי אוצריא/תוספים/יומא דהילולא v1.0.1.otzplugin"),
        help="קובץ התוסף יומא דהילולא (.otzplugin או data.js); '-' לדילוג")
    ap.add_argument("--seforim-db", default="C:/ProgramData/otzaria/books/seforim.db", help="קטלוג ספריית אוצריא (קריאה בלבד)")
    ap.add_argument("--hb-db", default="C:/ProgramData/otzaria/books/otzar-HB_catalog.db", help="קטלוג היברו-בוקס/אוצר החכמה (קריאה בלבד)")
    ap.add_argument("--bios-gz", default=os.path.expanduser("~/AppData/Roaming/otzaria/biographies-app.json.gz"),
                    help="מאגר הביוגרפיות של אוצריא — ראיית אימות בלבד (AGPL-3.0, ייחוס: abaye)")
    ap.add_argument("--no-catalog", action="store_true", help="בלי אימות מול קטלוגים (הכלל הישן בלבד)")
    ap.add_argument("--lib-authors-out", default=os.path.join(HERE, "..", "src", "data", "lib-authors.js"))
    ap.add_argument("--legacy-attribution", action="store_true", help="בדיקת השוואה: בלי כלל השיוך החדש")
    ap.add_argument("--dump-attr", default="", help="קובץ JSON לדוגמאות שיוך (התקבלו/נדחו)")
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)
    rep = io.open(args.report, "w", encoding="utf-8") if args.report else sys.stdout
    P = lambda *a: rep.write(" ".join(str(x) for x in a) + "\n")

    core = load_csv(find(args.src, "*רבנים*ביוגרפיות*.csv", "*1793053864434*.csv"))
    rtf = load_rtf(find(args.src, "*כרונולוגית*.rtf", "*1793055225292*.rtf"))     # ראשון: קובע את VALID_CATS
    shnot = load_shnot(find(args.src, "*שנות-דור*.xlsx", "*1793054927081*.xlsx"))
    yahr = load_yahrzeit(find(args.src, "*היארצייטים*.xlsx", "*1793055067103*.xlsx"))
    otz, otz_total, otz_ok = load_otzrot(find(args.src, "*אוצרות-התורה*.xlsx", "*1793054383839*.xlsx"))
    yoma, yesh, ystat = ([], [], collections.Counter()) if args.yoma == "-" else load_yoma(args.yoma)
    P("yoma: rabbis", len(yoma), "yeshivot", len(yesh), dict(ystat))
    P("loaded: csv", len(core), "shnot authors", len(shnot), "yahrzeit", len(yahr), "rtf authors", len(rtf),
      "otzrot rows", otz_total, "verified", otz_ok)

    M = Matcher(core)
    stats = collections.Counter()
    leftovers = []                      # רשומות חיצוניות שלא נמצא להן מקבילה בליבה
    ML = Matcher(leftovers, csv_style=False)

    def place(e, label):
        i = M.find(e)
        if i is not None:
            merge_into(core[i], e); stats[label + "_core"] += 1
            return
        j = ML.find(e)
        if j is not None:
            merge_into(ML.recs[j], e); stats[label + "_ext_merged"] += 1
            return
        ML.add(e); stats[label + "_new"] += 1

    for e in rtf + shnot:
        place(e, "ext")
    for y in yahr:
        place(y, "yz")
    ystats = collections.Counter()
    ylog = []
    # מסלול נוסף ליומא דהילולא: שנות לידה ופטירה זהות במדויק + טוקן שם משותף (בכתיב מקורב) — מועמד יחיד בלבד
    yyidx = collections.defaultdict(list)
    for src_recs, tag_ in ((core, "core"), (ML.recs, "ext")):
        for k_, r_ in enumerate(src_recs):
            if r_["by"] and r_["dy"]:
                yyidx[(r_["by"], r_["dy"])].append((tag_, k_))

    def by_years(e, et):
        if not (e["by"] and e["dy"]):
            return None
        scored = []
        for tag_, k_ in yyidx.get((e["by"], e["dy"]), ()):
            r_ = core[k_] if tag_ == "core" else ML.recs[k_]
            ct = set(name_tokens(r_["n"], csv_style=(tag_ == "core")))
            shared = [t for t in et if len(t) > 2 and any(tok_match(t, c) for c in ct)]
            if len(shared) >= 2 or (shared and len(et) <= 2 and len(ct) <= 3):
                scored.append((len(shared), tag_, k_))
        scored.sort(reverse=True)
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][1:]
        return None

    for e in yoma:
        i = M.find(e)
        if i is not None:
            ylog.append(["core", e["n"], e["by"], e["dy"], core[i]["n"], core[i]["by"], core[i]["dy"]])
            merge_into(core[i], e); ystats["merged_core"] += 1; continue
        j = ML.find(e)
        if j is not None:
            tgt = ML.recs[j]
            ylog.append(["ext", e["n"], e["by"], e["dy"], tgt["n"], tgt["by"], tgt["dy"]])
            ystats["merged_ext" if tgt["tags"] - {"h"} else "merged_dup_yoma"] += 1
            merge_into(tgt, e); continue
        hit_ = by_years(e, set(name_tokens(e["n"], csv_style=False)))
        if hit_:
            tg_ = core[hit_[1]] if hit_[0] == "core" else ML.recs[hit_[1]]
            ylog.append([hit_[0] + "-years", e["n"], e["by"], e["dy"], tg_["n"], tg_["by"], tg_["dy"]])
            merge_into(tg_, e); ystats["merged_" + hit_[0] + "_by_years"] += 1; continue
        ylog.append(["new", e["n"], e["by"], e["dy"], "", 0, 0])
        ML.add(e); ystats["new"] += 1
    P("yoma placement:", dict(ystats))
    P(dict(stats))

    # 3) אוצרות: מוסיף ספר ופירוט אומת למחבר תואם (בלי ליצור רשומות חדשות)
    ostats = collections.Counter()
    allrecs = core + leftovers
    M2 = Matcher(allrecs)
    for o in otz:
        if not o["author"]:
            ostats["no_author"] += 1; continue
        ext = new_rec(o["author"], "a")
        i = M2.find(ext)
        if i is None:
            ostats["unmatched"] += 1; continue
        ostats["matched"] += 1
        rec = allrecs[i]
        label = o["subject"] if o["subject"] and len(o["subject"]) < 40 else ""
        if o["title"] not in {b[0] for b in rec["bk"]}:
            rec["bk"].append([o["title"], label])
        if o["details"] and o["details"] not in rec["b"]:
            rec["b"] = (rec["b"] + " " + o["details"]).strip() if rec["b"] else o["details"]
        rec["tags"].add("a")
    P("otzrot:", dict(ostats))

    # שיוך ספרים ממתינים (כלל: טוקן שם/כינוי בכותר, או כותר זהה לספר מאומת)
    acc_all, rej_all, rest_all, rem_all, ver_all = [], [], [], [], []
    catalog = None if args.no_catalog else build_catalog(args.seforim_db, args.hb_db, args.bios_gz, P)
    for r in allrecs:
        a, rj, rs, rm, vf = resolve_pending(r, legacy=args.legacy_attribution, catalog=catalog)
        acc_all += [(r["n"], t, c) for t, c in a]
        rej_all += [(r["n"], t, c) for t, c in rj]
        rest_all += [(r["n"], t, c) for t, c in rs]
        rem_all += [(r["n"], t, c) for t, c in rm]
        ver_all += [(r["n"], t, c) for t, c in vf]
    P("attribution: pending accepted", len(acc_all), "rejected", len(rej_all), "| catalog-verified", len(ver_all),
      "restored (rejected by token rule)", len(rest_all), "removed (catalog contradicts weak token)", len(rem_all))
    if args.dump_attr:
        with io.open(args.dump_attr, "w", encoding="utf-8") as fh:
            json.dump({"accepted": acc_all, "rejected": rej_all, "restored": rest_all, "removed": rem_all, "verified": ver_all, "yoma": ylog}, fh, ensure_ascii=False)

    # ----- פלט -----
    yoma_excl = sum(1 for r in allrecs if "h" in r["tags"] and (r["n"] in EXCLUDE_NAMES or has_academic_title(r["n"])))
    P("yoma-touched records excluded by name rules:", yoma_excl)
    recs = [r for r in allrecs if r["n"] not in EXCLUDE_NAMES and not has_academic_title(r["n"])]
    P("excluded (names + academic titles):", len(allrecs) - len(recs))
    dropped = collections.Counter()
    for r in recs:
        for k in ("by", "dy"):
            if r[k] and not (800 <= r[k] <= 2030):
                r[k] = 0; dropped["out_of_range"] += 1
        if r["by"] and r["dy"] and (r["dy"] < r["by"] or r["dy"] - r["by"] > 110):
            r["by"] = r["dy"] = 0; dropped["impossible_lifespan"] += 1
    P("years dropped:", dict(dropped))
    recs.sort(key=lambda r: (sort_key(r["n"]), clean_quotes(r["n"])))
    for i, r in enumerate(recs):
        r["i"] = i
    P("total records:", len(recs))
    cnt = collections.Counter()
    for r in recs:
        cnt["year"] += bool(r["by"] or r["dy"]); cnt["yz"] += bool(r["yz"]); cnt["bk"] += bool(r["bk"]); cnt["bio"] += bool(r["b"])
    P("coverage:", dict(cnt))

    os.makedirs(out_dir, exist_ok=True)
    for f in glob.glob(os.path.join(out_dir, "*.js")):
        os.remove(f)
    letters = sorted({sort_key(r["n"]) for r in recs}, key=lambda c: (c == "#", c))
    shard_of = {L: n for n, L in enumerate(letters)}
    by_shard = collections.defaultdict(list)
    index = []
    for r in recs:
        sh = shard_of[sort_key(r["n"])]
        full = {"i": r["i"], "n": r["n"]}
        for k_out, k_in in (("f", "f"), ("k", "k"), ("r", "r"), ("bt", "bt"), ("bp", "bp"), ("dt", "dt"), ("dp", "dp"), ("b", "b")):
            if r[k_in]:
                full[k_out] = r[k_in]
        if INCLUDE_SOURCES and r["s"]:
            full["s"] = "; ".join(r["s"])
        if r["bk"]: full["bk"] = r["bk"]
        for k_out in ("e", "rb", "yl"):
            if r[k_out]:
                full[k_out] = r[k_out]
        if r["co"]:
            full["co"] = r["co"]
        by_shard[sh].append(full)
        # שורת אינדקס: [id, שם, כינוי, שנת-לידה, שנת-פטירה, יום, חודש, ספרים, מקור, תפקיד, קובץ]
        yz = r["yz"] or [0, -1]
        index.append([r["i"], r["n"], r["k"], r["by"], r["dy"], yz[0], yz[1],
                      "; ".join(b[0] for b in r["bk"])[:160], "".join(sorted(r["tags"])), r["r"][:60], sh])
    ver = hashlib.md5(json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:8]
    for sh, items in by_shard.items():
        name = "rb-%s-%d.js" % (ver, sh)
        with io.open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write("window.RB_SHARDS=window.RB_SHARDS||{};window.RB_SHARDS[%d]=" % sh)
            json.dump(items, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write(";\nwindow.RB_LOADED&&window.RB_LOADED(%d);\n" % sh)
    with io.open(os.path.join(out_dir, "rb-index.js"), "w", encoding="utf-8") as fh:
        fh.write('window.RB_VER="%s";\nwindow.RB_MONTHS=' % ver)
        json.dump(MONTHS, fh, ensure_ascii=False)
        fh.write(";\nwindow.RB_LETTERS=")
        json.dump(letters, fh, ensure_ascii=False)
        fh.write(";\nwindow.RB_INDEX=")
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    sizes = sorted(((os.path.getsize(f), os.path.basename(f)) for f in glob.glob(os.path.join(out_dir, "*.js"))), reverse=True)
    P("files:", len(sizes), "total bytes:", sum(s for s, _ in sizes), "largest:", sizes[:4])
    P("letters:", letters)
    P("tag counts:", dict(collections.Counter(t for r in recs for t in r["tags"])), "books total:", sum(len(r["bk"]) for r in recs))
    if args.lib_authors_out and not args.no_catalog and args.seforim_db and os.path.exists(args.seforim_db):
        # lib-authors.js: כותר מנורמל (אותיות עבריות בלבד) -> שמות מחברים כפי שבקטלוג הספרייה (קריאה בלבד)
        import sqlite3
        c_ = sqlite3.connect("file:" + args.seforim_db.replace("\\", "/") + "?mode=ro&immutable=1", uri=True)
        la = collections.OrderedDict()
        for t_, a_ in c_.execute("select b.title, a.name from book b join book_author ba on ba.bookId=b.id "
                                 "join author a on a.id=ba.authorId order by b.id, a.id"):
            k_ = re.sub(r"[^א-ת]", "", POINTS.sub("", t_ or ""))
            if k_ and a_ and a_ not in la.setdefault(k_, []):
                la[k_].append(a_)
        c_.close()
        os.makedirs(os.path.dirname(os.path.abspath(args.lib_authors_out)), exist_ok=True)
        with io.open(args.lib_authors_out, "w", encoding="utf-8") as fh:
            fh.write("window.LIB_AUTHORS=")
            json.dump(la, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write(";\n")
        P("lib-authors:", len(la), "titles; bytes", os.path.getsize(args.lib_authors_out))
    if yesh:
        os.makedirs(os.path.dirname(os.path.abspath(args.yeshivot_out)), exist_ok=True)
        with io.open(args.yeshivot_out, "w", encoding="utf-8") as fh:
            fh.write("window.YESHIVOT=")
            json.dump(yesh, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write(";\n")
        P("yeshivot written:", len(yesh))
    if args.report:
        rep.close()


if __name__ == "__main__":
    main()

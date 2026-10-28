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
from hebdates import _spell_norm, _SKIP_TOKENS
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
    r = difflib.SequenceMatcher(None, a, b).ratio()
    return r >= 0.85 or (min(len(a), len(b)) >= 5 and r >= 0.8)


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
        elif v1 and weak and catalog is not None:
            ok = False                           # טוקן שם פרטי נפוץ בלבד (אליהו/משה/יוסף...) בלי אישור קטלוג — לא משייכים
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
        rec["raw"] = name
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


# ----------------------------------------------------------------------------- איחוד כפילויות
_REL_WORDS = {"בעל", "זקן", "אבי", "חותן", "חתן", "תלמיד", "רבו", "בן", "נכד", "אחי", "גיס", "בנו", "אביו", "אחיו", "מחבר",
              "בר", "אם", "אמו", "בת", "אשת", "אשתו", "נין", "תלמידו", "מורו", "חבר", "דודו", "אחיין", "הסבא", "סבא"}
_ALIAS_STOP = {"רבי", "רבינו", "רבנו", "הרב", "הגאון", "הצדיק", "הכהן", "הלוי", "כהן", "לוי", "הקדוש", "הגדול", "הזקן", "החסיד",
               "המגיד", "הראשון", "האחרון", "הצעיר", "הנגיד", "הדיין", "הרופא", "הדרשן", "הפרשן"}

_PLACE_TOKS = None
_COMMON_ALL = set(COMMON_GIVEN)       # שמות פרטיים/משפחה נפוצים (קבוע + לפי שכיחות בנתונים) — מתעדכן ב-dedupe_records
_NONPLACE = set()                     # טוקנים שמופיעים כשם פרטי/משפחה ב-CSV (לא מקום גם אם מתחילים ב-מ'/ב')
_TRACE = None                         # (דיבוג) מילון זוגות שנחסמו -> סיבה
_GIVENISH = set()                     # טוקנים שמופיעים בעיקר כשם פרטי (לפי עמודת "משפחה, פרטי" ב-CSV)
_ROLE_WORDS = {"אדמור", "אבד", "ראבד", "אב", "רב", "דיין", "מגיד", "ראש", "ישיבה", "רבה", "מרא", "דאתרא", "חכם", "באשי", "הרב"}
_CTRY_WORDS = {clean_quotes(x) for x in ("גרמניה", "ספרד", "צרפת", "פולין", "אשכנז", "איטליה", "תימן", "מרוקו", "פרס", "בבל", "עיראק",
                                          "טורקיה", "רוסיה", "ליטא", "הונגריה", "אנגליה", "מצרים", "סוריה", "פרובנס", "בוהמיה",
                                          "מורביה", "אוסטריה", "הולנד")}
_ROLE_CUT = re.compile(r"(?<![א-ת])(?:אב[\"״]ד|ראב[\"״]ד|גאב[\"״]ד|ר[\"״]י|מחבר|מחברו|בעל|מייסד|מנהל|נשיא|ראש\s+(?:ישיבת|ישיבה|עדת|הקהל|חסידי)|רב\s+קהילת)(?![א-ת])")


def _ntok(s):
    return [t for t in (clean_quotes(x) for x in re.split(r"[\s,;:\-–—־]+", s or "")) if t and t not in _SKIP_TOKENS]


def is_place_tok(t):
    """טוקן שנראה כשם מקום (ממילון המקומות ב-CSV, גם עם מ' מוצא: "מלויצק")."""
    global _PLACE_TOKS
    if _PLACE_TOKS is None:
        _PLACE_TOKS = {tk_norm(w) for pl in PLACES for w in _words(pl) if len(w) >= 3}
    if t in _PLACE_TOKS and t not in _COMMON_ALL:
        return True
    return t[:1] in ("מ", "ב") and len(t) >= 5 and t[1:] in _PLACE_TOKS and t[1:] not in COMMON_GIVEN


def _pref_place(t):
    """מקום עם מ'/ב' מקדימה ("מוילנא") — מחזיר את שם המקום או None."""
    is_place_tok("")
    if t[:1] in ("מ", "ב") and len(t) >= 5 and t[1:] in _PLACE_TOKS and t[1:] not in COMMON_GIVEN:
        return t[1:]
    return None


_NAMED_ALIASES = {_spell_norm("".join(w.split())) for w in ("בן איש חי", "חפץ חיים", "אור החיים", "חתם סופר", "שפת אמת", "דברי חיים",
                                                           "אמרי אמת", "חזון איש", "בעל שם טוב", "נודע ביהודה", "פרי מגדים", "מגן אברהם",
                                                           "טורי זהב", "בית יוסף", "שולחן ערוך", "חיי אדם", "ערוך השולחן", "אבני נזר")}


def alias_key(s):
    """מפתח כינוי: אותיות עבריות בלבד, בלי גרשיים, בלי ה' הידיעה, כתיב מאוחד; None אם קצר/כללי/קשר-לאחר."""
    ws = _words(s)
    nk = _spell_norm("".join(ws[1:] if ws and ws[0] == "בעל" else ws))
    nk = nk[1:] if nk[:1] == "ה" else nk
    if nk in _NAMED_ALIASES:
        return nk
    if ws and ws[0] == "בעל" and len(ws) == 2 and re.search(r"[א-ת][\"״][א-ת]", s):
        ws = ws[1:]
    if not ws or len(ws) > 2 or ws[0] in _REL_WORDS:
        return None
    if len(ws) == 2 and ws[0] in ("רבינו", "רבנו", "רבי", "הרב") and tk_norm(ws[1]) in COMMON_GIVEN:
        return None
    abbr = bool(re.search(r"[א-ת][\"״][א-ת]", s))       # ראשי תיבות (הרמ"א) אינם שם מקום גם אם יש מקום באותיות זהות
    if any(w in _ROLE_WORDS or (not abbr and is_place_tok(tk_norm(w))) for w in ws):
        return None                                  # "אדמו"ר מדומברובה" הוא תואר/מקום ולא זהות
    k = _spell_norm("".join(ws))
    if k[:1] == "ה" and len(k) >= 4:
        k = k[1:]
    if k.startswith("רבנו"):
        k = "רבינו" + k[4:]
    if len(k) < 3 or k in _ALIAS_STOP or k in COMMON_GIVEN or (not abbr and is_place_tok(k)):
        return None
    return k


_DASH_TAIL = re.compile(r"(?:\s[-–—]\s*|\s*[-–—]\s+)(.+)$")


def _alias_cands(tail):
    c = [tail, re.split(r"\s+בעל\s+", tail)[0]]
    ws = tail.split()
    if ws and re.search(r"[\"״]", ws[0]):
        c.append(ws[0])
    if ws and ws[0] == "בעל" and len(ws) >= 2 and re.search(r"[\"״]", ws[1]):
        c.append(ws[1])
    return c


def rec_aliases(r):
    """כינויים/קיצורים: שדה k, החלק שאחרי " - " בשם (גם "X בעל Y"), תוכן סוגריים, ו"רבנו X"."""
    out = set()
    names = [r["n"]] + list(r.get("pnames", []))
    for part in re.split(r"[,;]", r["k"] or ""):
        part = part.strip()
        if not part or re.match(r"ראה\s*:", part):
            continue
        k = alias_key(part)
        if k:
            out.add(k)
            continue
        m = re.match(r"בעל\s+(\S+)$", part)
        if m and re.search(r"[\"״]", m.group(1)):
            k = alias_key(m.group(1))
            if k:
                out.add(k)
    for nm in names:
        tails = []
        m = _DASH_TAIL.search(nm)
        if m:
            tails.append(m.group(1))
        tails += re.findall(r"[\[(]([^\])]*)[\])]", nm)
        for t in tails:
            for c in _alias_cands(t):
                k = alias_key(c)
                if k:
                    out.add(k)
        if "c" not in r["tags"] or "," not in nm:
            for w in nm.split():
                if re.fullmatch(r"ה[א-ת]{1,4}[\"״][א-ת]{1,2}", w) and clean_quotes(w) not in _SKIP_TOKENS                         and not re.fullmatch(r"ה(?:אב|ראב|גאב|ר|מו|נ|ז|ע)[\"״][א-ת]{1,2}", w):
                    k = alias_key(w)
                    if k:
                        out.add(k)
        m = re.match(r"^(?:רבינו|רבנו)\s+(\S+)$", clean_quotes(nm))
        if m:
            k = alias_key(nm)
            if k:
                out.add(k)
    return out


def _yzm(y):
    return (y[0], 5 if y[1] in (5, 12, 13) else y[1])


def _year_from_piece(p):
    p = p.strip().rstrip(".")
    if not p or len(p.split()) > 4 or re.search(r"\d", p):
        return None
    pd = parse_hebrew_date(p)
    if not pd["hy"] or not (4560 <= pd["hy"] <= 5790):
        return None
    return pd


def normalize_rec(r):
    """נרמול שם לפני האיחוד: חותך זנב תיאורי (אחרי פסיק/נקודה/תפקיד/מדינות), מחלץ שנת פטירה מזנב גימטרי,
    ומפיק כינוי מ-"X - הרמב"ם" / "X בעל הש"ך". רשומות CSV ("משפחה, פרטי") לא נחתכות."""
    n = r["n"]
    r["n0"] = n
    csv_ = "c" in r["tags"] and "," in n
    kadd = []
    if not csv_:
        m = re.match(r"^([^,]+?)\s*,\s*(.+)$", n) or re.match(r"^(.+?[א-ת\"'׳״])\.\s+(.{8,})$", n)
        if m and len(_ntok(m.group(1))) >= 2:
            head, tail = m.group(1).strip(), m.group(2)
            for piece in re.split(r"\s*,\s*", tail):
                pd = _year_from_piece(piece)
                if not pd:
                    pw = piece.split()
                    pd = (_year_from_piece(" ".join(pw[:1])) or _year_from_piece(" ".join(pw[:2]))) if len(pw) > 4 else None
                if pd:
                    if pd["day"] and pd["month"] >= 0 and r["yz"] is None:
                        r["yz"] = [pd["day"], pd["month"]]
                    if not r["dy"]:
                        r["dy"] = hy_to_g(pd["hy"], r["yz"][1], r["yz"][0]) if r["yz"] else pd["hy"] - 3760
                    break
            n = head
        m = _DASH_TAIL.search(n) or re.search(r"[-–—](ה?[א-ת]+[\"״][א-ת]+(?:\s[^-]*)?)$", n)
        if m:
            head, tail = n[:m.start()].strip(), m.group(1).strip()
            if len(_ntok(head)) >= 2 and len(tail.split()) <= 4:
                cands = [c for c in _alias_cands(tail) if alias_key(c)]
                if cands:
                    kadd.append(cands[1] if len(cands) > 1 and re.search(r"[\"״]", cands[1]) else cands[0])
                    n = head
        ws_ = n.split()
        if len(ws_) >= 3 and re.fullmatch(r"ה?[א-ת]{1,5}[\"״][א-ת]{1,2}", ws_[-1]) and clean_quotes(ws_[-1]) not in _SKIP_TOKENS                 and alias_key(ws_[-1]) and len(_ntok(" ".join(ws_[:-1]))) >= 2                 and clean_quotes(ws_[-2]) not in _REL_WORDS and clean_quotes(ws_[-2]) not in ("של", "ישיבת", "בית", "ספר", "על"):
            kadd.append(ws_[-1])
            n = " ".join(ws_[:-1])
        toks = n.split()
        while len(toks) > 2 and len(_ntok(" ".join(toks[:-1]))) >= 2 and clean_quotes(toks[-1]) in _CTRY_WORDS:
            toks.pop()
        n = " ".join(toks)
        m = _ROLE_CUT.search(n)
        if m and len(_ntok(n[:m.start()])) >= 2:
            tail = n[m.start():]
            if tail.startswith("בעל"):
                w = tail[3:].split()
                if w and re.search(r"[\"״]", w[0]):
                    kadd.append(w[0])
            n = n[:m.start()].strip()
    r["n"] = n
    parts = [x.strip() for x in re.split(r",", r["k"] or "") if x.strip()]
    parts = [x for x in parts if len(clean_quotes(x)) >= 2 or x.startswith("ראה")]     # "י" / "ב" אינם כינוי
    for a in kadd:
        if a not in parts and not any(clean_quotes(a) == clean_quotes(x) for x in parts):
            parts.append(a)
    r["k"] = ",".join(parts)


_FATHER_BR = re.compile(r"(?<![א-ת])(?:ב[\"״]ר|בר[\"״]|ב['׳]ר)\s+(?:ר['׳]?\s+|רבי\s+)?([א-ת\"'׳״]+)(?:\s+([א-ת\"'׳״]+))?")
_FATHER_BEN = re.compile(r"(?<![א-ת])בן\s+(?:ר['׳]?\s+|רבי\s+|הרב\s+)?([א-ת\"'׳״]+)")


def prep(r):
    """מאפיינים מחושבים לרשומה (נשמרים ב-r["_c"]) — לשימוש חוזר בכללי האיחוד."""
    n = r["n"]
    csv_ = "c" in r["tags"] and "," in n
    fam_s, rest = (n.split(",", 1) if csv_ else ("", n))
    toks, places, fam = set(), set(), set()
    for src, is_rest in ((fam_s, False), (rest, True)):
        order = {}
        for ix, t in reversed(list(enumerate(_ntok(src)))):
            order[tk_norm(t)] = ix
        for t in author_tokens(src):
            nt = tk_norm(t)
            if len(nt) < 3:
                continue
            pp = _pref_place(nt)
            if pp:
                places.add(pp)
            elif csv_ and is_rest and nt in _PLACE_TOKS and nt not in _COMMON_ALL:
                places.add(nt)
            elif ((csv_ and is_rest) or (not csv_ and order.get(nt, 0) >= 1)) and _lp(nt):
                places.add(nt[1:])
            else:
                toks.add(nt)
                if not is_rest:
                    fam.add(nt)
    for part in re.split(r"[,;]", r["k"] or ""):
        for w in _words(part):
            pp = _pref_place(tk_norm(w))
            if pp:
                places.add(pp)
    fs, fa_all = set(), set()
    for m in _FATHER_BR.finditer(n):
        for g in (m.group(1), m.group(2)):
            if g:
                t = tk_norm(g)
                if len(t) >= 3 and not _pref_place(t):
                    fs.add(t)
    if r.get("f"):
        for w in _words(r["f"])[:3]:
            t = tk_norm(w)
            if len(t) >= 3 and not _pref_place(t) and not _lp(t):
                fs.add(t)
    fa_all |= fs
    for m in _FATHER_BEN.finditer(n):
        t = tk_norm(m.group(1))
        if len(t) >= 3:
            fa_all.add(t)
    ordered = _ntok(rest if csv_ else n)
    giv = tk_norm(ordered[0]) if ordered else ""
    r["_c"] = {"toks": toks, "places": places, "fam": fam, "fs": fs, "fa_all": fa_all, "giv": giv,
               "ft": toks | fs, "al": rec_aliases(r)}


def _lp(t):
    """היוריסטיקה: טוקן שנראה כמקום מפורש (מ'/ב' + שם) ואינו שם פרטי נפוץ."""
    return (t[:1] in ("מ", "ב") and len(t) >= 5 and t not in COMMON_GIVEN and t not in _GIVENISH and t not in _NONPLACE
            and t not in _COMMON_ALL)


def _tm(x, y):
    return x == y or (len(x) >= 4 and len(y) >= 4 and _tkm(x, y))


def _overlap(sa, sb):
    return any(_tm(x, y) for x in sa for y in sb)


def _pm(x, y):
    return x == y or (len(x) >= 4 and len(y) >= 4 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.75)


def _famish(t):
    return t not in COMMON_GIVEN and t not in _GIVENISH


def name_compat(a, b):
    """תאימות שמות: אחרי הסרת כינויים — קבוצת הטוקנים הקטנה (כולל שם האב) מוכלת בגדולה (עם סבילות כתיב)."""
    ca, cb = a["_c"], b["_c"]
    al = ca["al"] | cb["al"]
    ta = {t for t in ca["toks"] if t not in al}
    tb = {t for t in cb["toks"] if t not in al}
    ta = (ta - ca["fa_all"]) or ta                   # שם האב ("ישראל בן אליעזר") אינו חלק מזהות השם
    tb = (tb - cb["fa_all"]) or tb
    if not ta or not tb:
        return True
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(x in big or any(len(x) >= 4 and _tkm(x, y) for y in big) for x in small)


def _dyd(a, b):
    return abs(a["dy"] - b["dy"]) if (a["dy"] and b["dy"]) else None


def _yz_eq(a, b):
    return bool(a["yz"] and b["yz"] and _yzm(a["yz"]) == _yzm(b["yz"]))


def _core_equal(a, b):
    """אותו שם (אחרי הסרת כינויים): לפחות 2 טוקנים, כולם תואמים (לפי הטוקנים, או לפי הטוקנים+שם האב), ולפחות אחד מבחין."""
    ca, cb = a["_c"], b["_c"]
    al_ = ca["al"] | cb["al"]
    for key in ("toks", "ft"):
        ta_, tb_ = {t for t in ca[key] if t not in al_}, {t for t in cb[key] if t not in al_}
        if (len(ta_) >= 2 and len(ta_) == len(tb_) and all(any(_tm(x, y) for y in tb_) for x in ta_)
                and any(_famish(t) for t in ta_)):
            return True
    return False


_CW = [0]


def _cw(k):
    _CW[0] = k
    return True


def contra(a, b, strong=False):
    """האם שתי רשומות סותרות (אנשים שונים): שנים, יום+חודש, שם האב, אב/בן הפוכים, שם משפחה, מקומות מפורשים."""
    ca, cb = a["_c"], b["_c"]
    dyd, yzq = _dyd(a, b), _yz_eq(a, b)
    if a["by"] and b["by"] and abs(a["by"] - b["by"]) > 3 and not (yzq and (dyd is None or dyd <= 1) and abs(a["by"] - b["by"]) <= 12):
        same_name = (dyd is None or dyd <= 2) and abs(a["by"] - b["by"]) <= 20 and _core_equal(a, b)
        loose = strong and dyd is None and abs(a["by"] - b["by"]) <= 12
        if not (dyd is not None and dyd <= 1 and abs(a["by"] - b["by"]) <= 8) and not same_name and not loose:
            return _cw(1)
    if dyd is not None and dyd > 1:
        if not (dyd == 2 and a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 5 and _core_equal(a, b)):
            return _cw(2)
    if a["yz"] and b["yz"] and not yzq:
        ya, yb = _yzm(a["yz"]), _yzm(b["yz"])
        rosh = ((ya[0] == 30 and yb[0] == 1 and (yb[1] - ya[1]) % 12 in (1, 2)) or (yb[0] == 30 and ya[0] == 1 and (ya[1] - yb[1]) % 12 in (1, 2)))             and dyd is not None and dyd <= 1                  # ל' בחודש / א' בחודש הבא (ראש חודש)
        same_mon = ya[1] == yb[1] and dyd == 0 and _core_equal(a, b)      # אותה שנה, אותו חודש ושם זהה: פער ימים הוא כנראה שגיאת העתקה
        soft = rosh or same_mon or (a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1 and dyd is not None and dyd <= 1
                and _yzm(a["yz"])[1] == _yzm(b["yz"])[1]) or (strong and _yzm(a["yz"])[1] == _yzm(b["yz"])[1] and abs(a["yz"][0] - b["yz"][0]) <= 1
                and (dyd is None or dyd <= 1))
        if not soft:
            return _cw(3)
    if ca["fs"] and cb["fs"] and not _overlap(ca["fs"], cb["fs"]):
        return _cw(4)
    ga, gb = ca["giv"], cb["giv"]
    if ga and gb and not _tm(ga, gb):
        if (gb in ca["fa_all"] and ga not in cb["toks"]) or (ga in cb["fa_all"] and gb not in ca["toks"]):
            return _cw(5)
    if ca["fam"] and cb["fam"] and not _overlap(ca["fam"], cb["fam"]):
        return _cw(6)
    pa, pb = ca["places"], cb["places"]
    if pa and pb and not any(_pm(x, y) for x in pa for y in pb):
        if not (yzq or (a["dy"] and a["dy"] == b["dy"] and not (1939 <= a["dy"] <= 1945))):
            return _cw(7)
    return False


def positive(a, b):
    """ראיה חיובית: יום פטירה זהה, או שנת פטירה/לידה קרובות (±1)."""
    if _yz_eq(a, b):
        return True
    d = _dyd(a, b)
    if d is not None and d <= 1:
        return True
    return bool(a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1)


def positive_year(a, b):
    """ראיית שנים של ממש (בלי יום+חודש לבדו)."""
    d = _dyd(a, b)
    if d is not None and d <= 1:
        return True
    if a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1:
        return True
    return _yz_eq(a, b) and d is not None and d <= 2


def year_evidence(a, b):
    d = _dyd(a, b)
    byc = bool(a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1)
    if d is not None and d <= 1:
        return 2 if (byc or _yz_eq(a, b)) else 1
    if _yz_eq(a, b) and d is not None and d <= 2:
        return 2
    if _yz_eq(a, b) and d is None:
        return 1                                     # אותו יום+חודש פטירה ושנה חסרה בצד אחד
    if a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 5 and d == 2:
        return 1                                     # פער פטירה של שנתיים בין מקורות — רק עם שנת לידה קרובה
    if byc and (d is None or d <= 2):
        return 1                                     # שנת לידה זהה והפטירה חסרה בצד אחד / סטייה של שנתיים
    return 0


def _shared(a, b):
    """(מספר טוקני שם משותפים, מהם 'מבחינים' — לא שם פרטי נפוץ — כולל כינוי/מקום משותפים)."""
    ca, cb = a["_c"], b["_c"]
    hit = [x for x in ca["ft"] if x in cb["ft"] or any(len(x) >= 4 and _tkm(x, y) for y in cb["ft"])]
    n = len(hit)
    nf = sum(1 for x in hit if _famish(x))
    if nf == 0 and ca["giv"] and _tm(ca["giv"], cb["giv"]) and (_overlap(ca["fs"], cb["fa_all"]) or _overlap(cb["fs"], ca["fa_all"])):
        nf = 1                                       # אותו שם פרטי ואותו שם אב — מבחין
    if ca["al"] & cb["al"]:
        n += 1
        nf += 1
    if any(_pm(x, y) for x in ca["places"] for y in cb["places"]):
        n += 1
        nf += 1
    return n, nf


def _share_rare(a, b):
    n, nf = _shared(a, b)
    by_close = bool(a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1)
    return (nf >= 1 and (n >= 2 or by_close)) or (n >= 2 and by_close)


def load_bios_entries(path):
    import gzip
    if not path or not os.path.exists(path):
        return []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh).get("entries", [])


def _nums(d):
    return {int(x) for x in re.findall(r"(?<!\d)(\d{3,4})(?!\d)", str((d or {}).get("gregorian", "")))}


def _first_num(d):
    m = re.search(r"(?<!\d)(\d{3,4})(?!\d)", str((d or {}).get("gregorian", "")))
    return int(m.group(1)) if m else 0


def name_score(n):
    toks = name_tokens(n, csv_style=("," in n))
    sc = min(len(toks), 4)
    if re.search(r"ב[\"״]ר|(?<![א-ת])בן\s", n):
        sc += 1
    if len(toks) <= 1:
        sc -= 3
    if re.search(r"\s[-–—]\s", n):
        sc -= 3
    if re.search(r"[.\[(]", n) or len(n) > 45:
        sc -= 3
    if re.search(r"\sו(?:ר['׳]|רבי)", n):
        sc -= 6                                    # שני אנשים ברשומה אחת ("ר' צמח ור' שמעון")
    if re.search(r"(?<![א-ת])(?:%s)$" % "|".join(sorted(_CTRY_WORDS)), clean_quotes(n)):
        sc -= 3
    if re.match(r"^(ר'|רבי |רבינו |רבנו )", n):
        sc += 1
    return sc


def rec_richness(r):
    return (3 * bool(r["b"]) + bool(r["by"]) + bool(r["dy"]) + 2 * bool(r["yz"]) + min(len(r["bk"]), 5) + 2 * ("c" in r["tags"]) +
            bool(r["r"]) + bool(r["bp"]) + bool(r["dp"]))


def absorb(main, other):
    """ממזג את other אל main (מעבר ל-merge_into): ביוגרפיה ארוכה, אב, כינויים, שמות, שנת פטירה מדויקת."""
    if other["yz"] and not main["yz"] and other["dy"]:
        main["dy"] = other["dy"]            # רשומה עם חודש מדויקת בשנת הפטירה (1204 ולא 1205)
    merge_into(main, other)
    if len(other["b"]) > len(main["b"]):
        main["b"] = other["b"]
    for k in ("f", "raw"):
        if not main.get(k) and other.get(k):
            main[k] = other[k]
    main.setdefault("pnames", [])
    for nm in [other["n"]] + list(other.get("pnames", [])):
        if nm not in main["pnames"] and nm != main["n"]:
            main["pnames"].append(nm)
    if other["k"]:
        parts = [x.strip() for x in main["k"].split(",") if x.strip()]
        for x in other["k"].split(","):
            if x.strip() and x.strip() not in parts:
                parts.append(x.strip())
        main["k"] = ",".join(parts)
    if other["approx_by"] is False and main["by"] == other["by"]:
        main["approx_by"] = False


# כינויים נפוצים לדמויות בולטות: (כינויים, ביטוי לשם, טווח שנות פטירה) — מתווספים לשמות החלופיים של הרשומה התואמת בלבד
NOTABLE = [
    (["הרמב\"ם"], r"משה (בן|ב.ר) מ[י]*מון", (1203, 1206)),
    (["הרמב\"ן"], r"משה (בן|ב.ר) נחמן|משה גירונדי", (1268, 1271)),
    (["הגר\"א"], r"אליהו (בן שלמה זלמן|מוילנא|מווילנא|מוילנה|מווילנה)", (1796, 1798)),
    (["הרמ\"א"], r"משה איסרל[שי]", (1571, 1573)),
    (["הבעש\"ט", "הבעל שם טוב"], r"ישראל (בן אליעזר|בעל שם טוב)", (1759, 1761)),
    (["מרן", "הבית יוסף"], r"יוסף (קארו|קרו)", (1574, 1576)),
    (["האר\"י", "האריז\"ל"], r"יצחק לוריא", (1571, 1573)),
    (["הרשב\"א"], r"שלמה (בן |ב.ר )?(אברהם )?(אבן )?אדרת", (1309, 1311)),
    (["הרא\"ש"], r"אשר (בן|ב.ר) יחיאל", (1326, 1328)),
    (["הרשב\"ם"], r"שמואל (בן|ב.ר) מאיר", (1158, 1161)),
    (["הר\"ן"], r"ני?סים.*גירונדי|גירונדי.*ני?סים", (1375, 1377)),
    (["הרי\"ף"], r"יצחק.*אלפ[אס]+י|אלפ[אס]+י.*יצחק", (1102, 1105)),
    (["הטור", "בעל הטורים"], r"יעקב (בן|ב.ר) אשר", (1339, 1341)),
    (["השל\"ה"], r"ישעיה.*הורו[ויב]+יץ|הורו[ויב]+יץ.*ישעיה", (1629, 1631)),
    (["הש\"ך"], r"שבתי (הכהן|כהן)|כהן, שבתי", (1662, 1664)),
    (["הב\"ח"], r"יואל סירקיש|סירקיש.*יואל", (1639, 1641)),
    (["הט\"ז"], r"דוד (הלוי )?סגל|סגל.*דוד", (1666, 1668)),
    (["רשב\"ץ", "הרשב\"ץ", "התשב\"ץ"], r"שמעון.*דוראן|דוראן.*שמעון", (1443, 1445)),
    (["מהרח\"ו"], r"חיים ויט[אל]+|ויט[אל]+.*חיים", (1619, 1621)),
    (["מהרי\"ק"], r"יוסף.*קולון|קולון.*יוסף", (1479, 1481)),
    (["מהר\"ל", "המהר\"ל מפראג"], r"יהודה.*(ליוואי|ליווא)|(ליוואי|ליווא).*יהודה", (1608, 1610)),
    (["רעק\"א"], r"עקיבא (איגר|אייגר)|איגר.*עקיבא", (1836, 1838)),
    (["החזו\"א", "החזון איש"], r"אברהם ישעיהו? קרליץ|קרליץ.*אברהם ישעיהו?", (1953, 1955)),
    (["חת\"ס", "החתם סופר"], r"משה סופר|סופר.*משה", (1838, 1840)),
    (["הבן איש חי"], r"יוסף חיים.*(בגדאד|בן אליהו)|חיים, יוסף", (1908, 1910)),
    (["החפץ חיים"], r"ישראל מאיר.*(קגן|הכהן)", (1932, 1934)),
    (["אור החיים"], r"חיים.*עטר|עטר.*חיים", (1742, 1744)),
    (["רבנו תם", "רבינו תם"], r"יעקב.*(מאיר תם|בן מאיר|מטרוי)|רבי?נו תם", (1170, 1172)),
    (["רבנו גרשום", "רבינו גרשום", "מאור הגולה"], r"גרשום", (1039, 1041)),
    (["הרב קוק", "הראי\"ה"], r"אברהם יצחק.*קוק|קוק.*אברהם יצחק", (1934, 1936)),
    (["הרב עובדיה יוסף", "מרן"], r"עובדיה.*יוסף|יוסף.*עובדיה", (2012, 2014)),
]


def _alt_key(s):
    return _spell_norm(clean_quotes(re.sub(r"\s+", "", s or "")))


def finalize_alts(r, limit=200):
    """שמות חלופיים לחיפוש (עמודת אינדקס 11): שמות/כינויים שנבלעו, בלי כפילויות, עד ~200 תווים."""
    have = {_alt_key(r["n"])} | {_alt_key(x) for x in r["k"].split(",") if x.strip()}
    out, size = [], 0
    for a in r.get("alts", []):
        a = re.sub(r"\s+", " ", a).strip(" ,;.-")
        key = _alt_key(a)
        if not a or key in have or len(a) > 60 or len(key) < 3 or re.match(r"ראה\s*:", a):
            continue
        have.add(key)
        if size + len(a) + 2 > limit:
            continue
        out.append(a)
        size += len(a) + 2
    return "; ".join(out)


def dedupe_records(recs, bios_entries, log):
    """מאחד רשומות של אותו אדם. מחזיר (רשימה חדשה, יומן איחודים). דיוק לפני כיסוי: איחוד רק בלי סתירה ועם ראיה."""
    global _GIVENISH
    n = len(recs)
    for r in recs:                                   # שנים מחוץ לטווח (פענוח שגוי, למשל 738) אינן ראיה ואינן סתירה
        for k in ("by", "dy"):
            if r[k] and not (800 <= r[k] <= 2030):
                r[k] = 0
    for r in recs:
        normalize_rec(r)
    freq = collections.Counter()
    for r in recs:
        freq.update({tk_norm(t) for t in author_tokens(r["n"])})
    _COMMON_ALL.clear()
    _COMMON_ALL.update(COMMON_GIVEN)
    _COMMON_ALL.update(t for t, c in freq.items() if c >= 40)
    is_place_tok("")
    gc, fc = collections.Counter(), collections.Counter()
    for r in recs:
        if "c" in r["tags"] and "," in r["n"]:
            fam_s, rest = r["n"].split(",", 1)
            ot = [tk_norm(t) for t in _ntok(rest)]
            gc.update({t for t in (ot if len(ot) <= 1 else ot[:-1]) if not _pref_place(t)})
            fc.update({tk_norm(t) for t in author_tokens(fam_s)})
    _GIVENISH = {t for t, v in gc.items() if v >= 12 and v > 2 * fc[t]}
    _NONPLACE.clear()
    _NONPLACE.update(t for t, v in gc.items() if v >= 2 and not _pref_place(t))
    _NONPLACE.update(t for t, v in fc.items() if v >= 1)
    for r in recs:
        prep(r)
    ok_rec = [not (r["n"] in EXCLUDE_NAMES or has_academic_title(r["n"])) for r in recs]
    parent = list(range(n))
    members = {i: [i] for i in range(n)}
    events = []                                   # (סיבה, i, j)
    CAP = 8

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def suffix(r):
        m = re.search(r"\s-\s*([אבגד]|\d+)\s*$|[א-ת]-([אבגד])\s*$", r.get("raw", "") or r["n0"])
        return (m.group(1) or m.group(2)) if m else ""

    tidx = collections.defaultdict(set)
    for i, r in enumerate(recs):
        for t in r["_c"]["ft"]:
            tidx[t].add(i)

    def combo_rare(a, b):
        """צירוף טוקני השם המשותפים נדיר ביותר (<=3 רשומות) — מבחין גם כששני הטוקנים נפוצים כשמות פרטיים."""
        sh = [x for x in a["_c"]["ft"] if x in b["_c"]["ft"]]
        if len(sh) < 2:
            return False
        sets = sorted((tidx[x] for x in sh), key=len)
        cur = set(sets[0])
        for st in sets[1:]:
            cur &= st
            if len(cur) <= 3:
                return True
        return len(cur) <= 3

    def block(i, j, strong):
        """סיבת חסימה של איחוד i,j (או None). כל זוג חברים באשכולות: בלי סתירה ועם שמות תואמים; הזוג עצמו: עוגן שם."""
        ri, rj = find(i), find(j)
        for x in members[ri]:
            for y in members[rj]:
                a, b = recs[x], recs[y]
                if contra(a, b, strong):
                    return "contra"
                if not name_compat(a, b):
                    return "compat"
                if suffix(a) and suffix(b) and suffix(a) != suffix(b):
                    return "suffix"               # "X - א" / "X - ב": אנשים שונים עם אותו שם
                if re.search(r"\sו(?:ר['׳]|רבי)", a["n"]) or re.search(r"\sו(?:ר['׳]|רבי)", b["n"]):
                    return "two-persons"          # רשומה משותפת לשני אנשים — לא מאחדים
        a, b = recs[i], recs[j]
        nn, nf = _shared(a, b)
        eq_by = bool(a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1 and len(a["_c"]["toks"]) == len(b["_c"]["toks"]) >= 2
                     and all(any(_tm(x, y) for y in b["_c"]["toks"]) for x in a["_c"]["toks"]))
        if nf == 0 and not combo_rare(a, b) and not eq_by:      # רק שמות פרטיים נפוצים משותפים: נדרש עוגן שנים חזק
            d = _dyd(a, b)
            if not (d is not None and d <= 1 and ((a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1) or _yz_eq(a, b))):
                return "common-only"
        return None

    def try_union(i, j, reason, strong=False):
        if i == j or not (ok_rec[i] and ok_rec[j]):
            return False
        ri, rj = find(i), find(j)
        if ri == rj:
            return False
        if len(members[ri]) + len(members[rj]) > CAP:
            if _TRACE is not None:
                _TRACE[(i, j)] = "cap"
            return False
        why = block(i, j, strong)
        if why:
            if _TRACE is not None:
                _TRACE[(i, j)] = why
            return False
        parent[rj] = ri
        members[ri] += members.pop(rj)
        events.append((reason, i, j))
        return True

    def numbered(r):
        raw = r.get("raw", "")
        return bool(re.search(r"\d\s*$|\s-\s*[אבגד]\s*$|\s-\s*\d", raw))

    aidx = collections.defaultdict(list)
    for i, r in enumerate(recs):
        for k in r["_c"]["al"]:
            aidx[k].append(i)
    # --- ב': זהויות מאגר הביוגרפיות של אוצריא (ראיית אימות בלבד; שום טקסט לא מועתק)
    tix = collections.defaultdict(set)
    rec_tokens = []
    for i, r in enumerate(recs):
        ts = set()
        for nm in [r["n"]] + list(r.get("pnames", [])):
            ts |= {tk_norm(t) for t in author_tokens(nm)}
        ts = {t for t in ts if len(t) >= 3}
        for nm in [r["n"]] + list(r.get("pnames", [])):
            m_f = re.search(r"ב[\"״]ר\s+([א-ת\"'׳״]+)", nm)         # שם האב נחשב לטוקן נוסף ("משה ב"ר מיימון")
            if m_f and len(tk_norm(m_f.group(1))) >= 3:
                ts.add(tk_norm(m_f.group(1)))
        rec_tokens.append(ts)
        for t in ts:
            tix[t].add(i)
    bstats = collections.Counter()
    rec_entries = collections.defaultdict(set)         # רשומה -> ערכים שהיא מתאימה להם
    entry_recs = {}
    for ei, e in enumerate(bios_entries):
        names = [e.get("name", "")] + [k for k in (e.get("known_as") or []) if isinstance(k, str)]
        nsets = []
        ekeys = set()
        for nm in names:
            nsets.append({tk_norm(t) for t in author_tokens(nm) if len(tk_norm(t)) >= 3})
            k = alias_key(nm)
            if k:
                ekeys.add(k)
            for g in re.findall(r"[\[(]([^\])]*)[\])]", nm):
                k = alias_key(g)
                if k:
                    ekeys.add(k)
        nsets = [x for x in nsets if x]
        eb, ed = _nums(e.get("born")), _nums(e.get("died"))
        cands = collections.Counter()
        for ns in nsets:
            for t in ns:
                lst = tix.get(t)
                if lst and len(lst) <= 3000:
                    for i in lst:
                        cands[i] += 1
        for k in ekeys:
            for i in aidx.get(k, ()):
                cands[i] += 2
        matched = []
        for i, c in cands.items():
            r = recs[i]
            if not ok_rec[i]:
                continue
            if r["by"] and eb and all(abs(r["by"] - y) > 3 for y in eb) and not (
                    r["dy"] and ed and any(abs(r["dy"] - y) <= 2 for y in ed) and all(abs(r["by"] - y) <= 8 for y in eb)):
                continue
            if r["dy"] and ed and all(abs(r["dy"] - y) > 2 for y in ed):
                continue
            pos = bool((r["by"] and eb and any(abs(r["by"] - y) <= 3 for y in eb)) or
                       (r["dy"] and ed and any(abs(r["dy"] - y) <= 2 for y in ed)))
            alias_hit = bool(r["_c"]["al"] & ekeys) and bool(rec_tokens[i] & {t for ns_ in nsets for t in ns_})
            name_hit = False
            T = rec_tokens[i]
            for ns in nsets:
                inter = T & ns
                if len(inter) >= 2:
                    if pos and (T == ns or T <= ns or ns <= T):
                        name_hit = True
                        break
                    if len(inter) >= 3 and T == ns and any(t not in _COMMON_ALL and not is_place_tok(t) for t in inter):
                        name_hit = True
                        break
            if alias_hit and (pos or name_hit or not (r["by"] or r["dy"])):
                matched.append(i)
            elif name_hit:
                matched.append(i)
        entry_recs[ei] = matched
        for i in matched:
            rec_entries[i].add(ei)
    # תיקון שנים/יום לפי מאגר אוצריא לרשומות שהותאמו בביטחון (רק תיקוני סטייה קטנה) — לפני האיחוד
    bstat = collections.Counter()
    for i, es in rec_entries.items():
        r = recs[i]
        if len(es) != 1 or len(entry_recs[next(iter(es))]) != 1:
            continue
        e = bios_entries[next(iter(es))]
        bv, dv = _first_num(e.get("born")), _first_num(e.get("died"))
        if bv and r["by"] and r["by"] != bv and abs(r["by"] - bv) <= 8:
            r["by"] = bv; bstat["bios_single_by"] += 1
        if dv and r["dy"] and r["dy"] != dv and abs(r["dy"] - dv) <= 2:
            r["dy"] = dv; bstat["bios_single_dy"] += 1
        if r["yz"] and dv and r["dy"] and abs(r["dy"] - dv) <= 1:
            pd_ = parse_hebrew_date(str((e.get("died") or {}).get("hebrew", "")))
            if pd_["day"] and pd_["month"] >= 0 and _yzm(r["yz"])[1] == _yzm([pd_["day"], pd_["month"]])[1]                     and r["yz"][0] != pd_["day"] and abs(r["yz"][0] - pd_["day"]) <= 1:
                r["yz"] = [pd_["day"], r["yz"][1]]; bstat["bios_single_yz"] += 1

    # --- ג: שם זהה (>=3 טוקנים, כולל "בן") ללא סתירה
    groups = collections.defaultdict(list)
    for i, r in enumerate(recs):
        ts = frozenset(name_tokens(r["n"], csv_style=("c" in r["tags"] and "," in r["n"])))
        if len(ts) >= 3 and any(len(t) >= 4 and tk_norm(t) not in _COMMON_ALL for t in ts):
            groups[ts].append(i)
    for ts, ids in groups.items():
        if 2 <= len(ids) <= 30:
            for a_ in range(len(ids)):
                for b_ in range(a_ + 1, len(ids)):
                    i, j = ids[a_], ids[b_]
                    if "c" in recs[i]["tags"] and "c" in recs[j]["tags"]:
                        continue
                    try_union(i, j, "שם-זהה", strong=True)

    # --- ד: CSV–CSV: שם+מקום זהים, בלי סתירה, עם ראיית שנים של ממש (או שם אב זהה). שם כללי+מקום בלי שנים — לא מאחדים
    cg = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if "c" in r["tags"] and r.get("raw") and not numbered(r):
            cg[clean_quotes(norm_text(r["n"]))].append(i)
    for key, ids in cg.items():
        if 2 <= len(ids) <= 8 and len(_words(key)) >= 2:
            for a_ in range(len(ids)):
                for b_ in range(a_ + 1, len(ids)):
                    i, j = ids[a_], ids[b_]
                    a, b = recs[i], recs[j]
                    if contra(a, b):
                        continue
                    if positive_year(a, b) or (a["f"] and a["f"] == b["f"] and (a["dy"] or b["dy"] or a["by"] or b["by"])):
                        try_union(i, j, "CSV-CSV")

    # --- ב: כינוי זהה + אין סתירה (+ ראיה חיובית או טוקן שם נדיר משותף)
    for k, ids in aidx.items():
        if 2 <= len(ids) <= 12:
            for a_ in range(len(ids)):
                for b_ in range(a_ + 1, len(ids)):
                    i, j = ids[a_], ids[b_]
                    a, b = recs[i], recs[j]
                    if contra(a, b, True):
                        continue
                    if positive(a, b) or _share_rare(a, b):
                        try_union(i, j, "כינוי", strong=True)

    # --- יום+שנת פטירה זהים (±1) + טוקן שם מבחין משותף (או כינוי)
    didx = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if r["yz"] and r["dy"]:
            didx[_yzm(r["yz"])].append(i)
    for key, ids in didx.items():
        if len(ids) < 2 or len(ids) > 400:
            continue
        byy = collections.defaultdict(list)
        for i in ids:
            byy[recs[i]["dy"]].append(i)
        for y, lst in byy.items():
            cand = lst + byy.get(y + 1, [])
            for a_ in range(len(lst)):
                for j in cand:
                    i = lst[a_]
                    if j <= i and j in lst:
                        continue
                    a, b = recs[i], recs[j]
                    if contra(a, b):
                        continue
                    if _share_rare(a, b) or (a["_c"]["al"] & b["_c"]["al"]):
                        try_union(i, j, "יום-פטירה")

    for ei, matched in entry_recs.items():
        good = [i for i in matched if len(rec_entries[i]) == 1]
        if len(matched) != len(good) and len(good) >= 2:
            bstats["entry_with_ambiguous_rec"] += 1
        if len(good) >= 2:
            bstats["entries_multi"] += 1
            for a_ in range(1, len(good)):
                try_union(good[0], good[a_], "ביוגרפיות-אוצריא", strong=True)
            for a_ in range(1, len(good)):
                for b_ in range(a_ + 1, len(good)):
                    try_union(good[a_], good[b_], "ביוגרפיות-אוצריא", strong=True)
    log("bios identity entries:", len(bios_entries), dict(bstats))

    # --- שם+שנים: קבוצת הטוקנים (כולל שם האב) של אחת מוכלת בשנייה, ראיית שנים, בלי סתירה
    seen_pairs = set()

    def name_years(i, j, reason="שם+שנים"):
        if (i, j) in seen_pairs or find(i) == find(j):
            return
        seen_pairs.add((i, j))
        a, b = recs[i], recs[j]
        ev = year_evidence(a, b)
        if not ev:
            return
        if contra(a, b):
            if _TRACE is not None:
                _TRACE[(i, j)] = "ny-contra"
            return
        if not name_compat(a, b):
            if _TRACE is not None:
                _TRACE[(i, j)] = "ny-compat"
            return
        nn, nf = _shared(a, b)
        both_years = bool(a["by"] and b["by"] and a["dy"] and b["dy"])
        eq_by = bool(a["by"] and b["by"] and abs(a["by"] - b["by"]) <= 1 and len(a["_c"]["toks"]) == len(b["_c"]["toks"]) >= 2
                     and all(any(_tm(x, y) for y in b["_c"]["toks"]) for x in a["_c"]["toks"]))
        if nn >= 2 and (nf >= 1 or (ev == 2 and both_years) or combo_rare(a, b) or eq_by):
            try_union(i, j, reason)
        elif _TRACE is not None:
            _TRACE[(i, j)] = "ny-weak-name %s" % ((nn, nf),)

    post = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if ok_rec[i] and (r["dy"] or r["by"] or r["yz"]):
            for t in r["_c"]["ft"]:
                if _famish(t) and len(t) >= 3:
                    post[t].append(i)
    for t, lst in post.items():
        if 2 <= len(lst) <= 400:
            for a_ in range(len(lst)):
                for b_ in range(a_ + 1, len(lst)):
                    name_years(lst[a_], lst[b_])
    byd = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if ok_rec[i] and r["by"] and r["dy"]:
            byd[r["dy"]].append(i)
    for y, lst in byd.items():
        cand = lst + byd.get(y + 1, [])
        for i in lst:
            for j in cand:
                if j > i or (j in lst and j > i):
                    pass
                if j == i or (j in lst and j < i):
                    continue
                if abs(recs[i]["by"] - recs[j]["by"]) <= 4:
                    name_years(min(i, j), max(i, j))

    # --- בלי שנים כלל: שם מוכל בשם יחיד-משמעית של רשומה עשירה (5+ ספרים או יום פטירה)
    def rich(r):
        return len(r["bk"]) >= 5 or bool(r["yz"])

    for i, r in enumerate(recs):
        if not ok_rec[i] or r["by"] or r["dy"] or r["yz"] or r["_c"]["places"] or find(i) != i:
            continue
        ft = r["_c"]["ft"]
        fam_t = [t for t in ft if _famish(t)]
        if len(ft) < 2 or not fam_t:
            continue
        pool = set()
        rare_t = min(fam_t, key=lambda t: len(post.get(t, ())) or 10 ** 9)
        if len(post.get(rare_t, ())) > 60:
            continue
        pool.update(post.get(rare_t, ()))
        cands = [j for j in pool if j != i and name_compat(r, recs[j]) and not contra(r, recs[j]) and
                 r["_c"]["giv"] and r["_c"]["giv"] == recs[j]["_c"]["giv"] and
                 all(any(_tm(x, y) for y in recs[j]["_c"]["ft"]) for x in ft)]
        richc = [j for j in cands if rich(recs[j])]
        if len(richc) == 1 and len(cands) <= 3:
            try_union(richc[0], i, "ללא-שנים")

    # --- ביצוע המיזוג
    bios_of = collections.defaultdict(set)
    for i, es in rec_entries.items():
        bios_of[find(i)] |= es
    mlog = []
    out = []
    removed = set()
    for root, mem in members.items():
        if len(mem) < 2:
            continue
        rs = [recs[i] for i in mem]
        main = max(rs, key=rec_richness)
        names_before = [r["n"] for r in rs]
        years = [(r["by"], r["dy"]) for r in rs]
        yzs = [r["yz"] for r in rs if r["yz"]]
        alts = []
        for r in rs:
            alts.append(r["n"])
            alts += list(r.get("pnames", []))
            alts += [x.strip() for x in r["k"].split(",") if x.strip()]
            alts += r.get("alts", [])
            m_ = _DASH_TAIL.search(r["n"])
            if m_:
                alts.append(m_.group(1))
        for r in rs:
            if r is not main:
                absorb(main, r)
                removed.add(id(r))
        # קונצנזוס שנים/יום: ערך אוצריא אם הוא קרוב לאחד הערכים ברשומות; אחרת הרוב; אחרת הראשית
        es = bios_of.get(root, set())
        bi = bios_entries[next(iter(es))] if len(es) == 1 else None
        for key, tol in (("by", 1), ("dy", 1)):
            vals = [y[0 if key == "by" else 1] for y in years if y[0 if key == "by" else 1]]
            if len(set(vals)) > 1:
                bv = _first_num(bi.get("born" if key == "by" else "died")) if bi else 0
                if bv and any(abs(bv - v) <= tol for v in vals):
                    main[key] = bv
                    bstat["bios_" + key] += 1
                else:
                    cnt = collections.Counter(vals)
                    top, topc = cnt.most_common(1)[0]
                    if topc > 1 and sum(1 for c in cnt.values() if c == topc) == 1:
                        main[key] = top
        if len({_yzm(y) for y in yzs}) > 1:
            pd_ = parse_hebrew_date(str((bi or {}).get("died", {}).get("hebrew", ""))) if bi else None
            if pd_ and pd_["day"] and pd_["month"] >= 0 and any(_yzm(y) == _yzm([pd_["day"], pd_["month"]]) for y in yzs):
                main["yz"] = [pd_["day"], pd_["month"]]
                bstat["bios_yz"] += 1
            else:
                cnt = collections.Counter(_yzm(y) for y in yzs)
                top, topc = cnt.most_common(1)[0]
                if topc > 1 and sum(1 for c in cnt.values() if c == topc) == 1:
                    main["yz"] = [y for y in yzs if _yzm(y) == top][0]
        best = max(names_before, key=lambda x: (name_score(x), x == main["n"]))
        if best != main["n"]:
            old = main["n"]
            main["n"] = best
            if old not in main["pnames"]:
                main["pnames"].append(old)
        main["alts"] = alts
        main["k"] = main["k"][:200]
        reasons = sorted({ev[0] for ev in events if find(ev[1]) == root or find(ev[2]) == root})
        mlog.append({"names": [r["n0"] for r in rs], "years": years, "reasons": reasons, "main": main["n"]})
    for i, r in enumerate(recs):
        if id(r) not in removed:
            out.append(r)
    # כינויים נפוצים לדמויות בולטות (רק לרשומה שמתאימה לשם ולשנות החיים)
    nstat = collections.Counter()
    for nicks, rx, (lo, hi) in NOTABLE:
        for r in out:
            txt = clean_quotes(r["n"] + " ; " + " ; ".join(r.get("alts", [])))
            if not re.search(rx, txt):
                continue
            if not (r["dy"] and lo <= r["dy"] <= hi or (not r["dy"] and r["by"] and lo - 110 <= r["by"] <= hi)):
                continue
            if "," in r["n"] and not (r["dy"] or r["by"]):
                continue
            r.setdefault("alts", [])
            for nk in nicks:
                r["alts"].append(nk)
            nstat[nicks[0]] += 1
    log("dedupe extras:", dict(bstat), "| notable nicknames added:", sum(nstat.values()))
    for r in out:
        r.pop("_c", None)
    return out, mlog



# ספרים ששויכו בטעות לדמויות בולטות (מחבריהם לפי הקטלוג: רבנו שמחה מויטרי, ר' נתן שטרנהרץ, ר' יחזקאל פייוויל, ר' יצחק קארו, החפץ חיים, ר' בצלאל אשכנזי...)
BOOK_DENY = [
    (r"משה (בן|ב.ר) מ[י]*מון", (1203, 1206), ["מוסרהשכל"]),
    (r"משה (בן|ב.ר) נחמן|משה גירונדי", (1268, 1271), ["עליםלתרופה", "תולדותאדם", "זכרצדיק"]),
    (r"שלמה.*יצחקי|יצחקי.*שלמה|רשי", (1104, 1106), ["מחזורויטרי"]),
    (r"יוסף (קארו|קרו)", (1574, 1576), ["תולדותיצחק", "כלליהתלמוד"]),
    (r"אשר (בן|ב.ר) יחיאל", (1326, 1328), ["שםעולם"]),
    (r"אליהו (בן שלמה זלמן|מוילנא|מווילנא|מוילנה|מווילנה)|הגרא", (1796, 1798),
     ["אשיישראל", "מעילצדקה", "ידאליהו", "שדהאליהו", "משנתאליהו", "דבריאליהו"]),
]


def clean_father_field(f):
    """שדה אב מזוהם ("מאיר כץ - גבורת אנשי" -> "מאיר כץ"): חותכים " - X" אלא אם X נראה ככינוי (ראשי תיבות / ה' הידיעה / רבנו)."""
    m = re.match(r"^(.*?)\s+[-–—]\s+(.+)$", f or "")
    if not m:
        return f or ""
    tail = m.group(2).strip()
    if re.search(r"[\"״]", tail) or tail.startswith(("ה", "רבנו", "רבינו", "בעל")):
        return f
    return m.group(1).strip()


# איחודים ידניים לדמויות בולטות שהאיחוד האוטומטי השאיר נפרדות בגלל סתירות קלות בשנים (שם ראשי, שמות נבלעים, שנות לידה/פטירה מקובלות)
MANUAL_MERGES = [
    ("יצחקי, שלמה", ["ר' שלמה יצחקי ב\"ר יצחק"], 1040, 1105),
    ("ר' יוסף קארו ב\"ר אפרים", ["ר' יוסף קארו"], 1488, 1575),
    ("ר' אברהם אבן עזרא", ["רבי אברהם אבן עזרא"], 1089, 1164),
    ("ר' עובדיה יוסף ב\"ר יעקב", ["ר' עובדיה יוסף"], 1920, 2013),
    ("אלשיך משה בן חיים", ["ר' משה אלשיך", "רבי משה אלשיך ישראל"], 1508, 1593),
    ("ויטל חיים בן יוסף", ["ר' חיים ויטאל ב\"ר יוסף"], 1543, 1620),
    ("גבירול ן, שלמה", ["ר' שלמה אבן גבירול", "ר' שלמה אבן גבירול ב\"ר יהודה"], 1021, 1058),
    ("יהודה הלוי מספרד", ["ר' יהודה הלוי", "ר' יהודה הלוי ב\"ר שמואל"], 1075, 1141),
    ("ר' נסים ב\"ר ראובן", ["נסים בן ראובן גרונדי", "ר' ניסים גירונדי"], 1320, 1376),
    ("יעקב בן אשר", ["ר' יעקב בן הרא\"ש"], 1269, 1343),
    ("מולין, יעקב הלוי - מהרי\"ל", ["ר' יעקב בן משה מולין", "ר' יעקב סג\"ל מולין ב\"ר משה"], 1365, 1427),
    ("ר' שמואל ב\"ר מאיר", ["ר' שמואל בן מאיר"], 1085, 1158),
    ("מאיר מרוטנבורג", ["ר' מאיר בן ברוך מרוטנבורג"], 1215, 1293),
    ("ר' יהודה החסיד משפירא ב\"ר שמואל", ["ר' יהודה החסיד"], 1150, 1217),
]
# רשומות שקיבלו בטעות כינוי של אביהן (ה"רשב"ץ" הוא ר' שמעון דוראן, לא בנו ר' שלמה)
STRIP_NICKS = [("ר' שלמה בן ר' שמעון דוראן", r"רשב\"ץ|תשב\"ץ")]


def apply_manual_merges(recs, log):
    by_name = {}
    for r in recs:
        by_name.setdefault(r["n"], []).append(r)
    removed, merged, missing = set(), [], []
    for main_n, others, by, dy in MANUAL_MERGES:
        mains = by_name.get(main_n)
        if not mains:
            missing.append(main_n); continue
        main = mains[0]
        names = [main_n]
        for on in others:
            for o in by_name.get(on, []):
                if o is not main and id(o) not in removed:
                    absorb(main, o)
                    main.setdefault("alts", []).append(o["n"])
                    removed.add(id(o)); names.append(on)
        main["by"], main["dy"] = by, dy
        main["approx_by"] = False
        merged.append({"names": names, "years": [[by, dy]], "reasons": ["ידני"], "main": main_n})
    for nm, rx in STRIP_NICKS:
        for r in by_name.get(nm, []):
            r["k"] = ",".join(x for x in r["k"].split(",") if x and not re.search(rx, x))
            r["alts"] = [a for a in r.get("alts", []) if not re.search(rx, a)]
    log("manual merges:", len(merged), "records absorbed:", len(removed), "| main not found:", missing)
    return [r for r in recs if id(r) not in removed], merged


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
    ap.add_argument("--pre-pickle", default="", help="(דיבוג) שמירת הרשומות לפני איחוד כפילויות")
    ap.add_argument("--no-dedupe", action="store_true", help="בלי איחוד כפילויות")
    ap.add_argument("--dedupe-log", default="", help="קובץ JSON לדוח ביקורת של האיחודים")
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
    # איחוד כפילויות (כינויים, זהויות מאגר הביוגרפיות, שם זהה, CSV-CSV)
    n_before = len(core) + len(leftovers)
    allrecs = core + leftovers
    if args.pre_pickle:
        import pickle
        with open(args.pre_pickle, "wb") as pf:
            pickle.dump((allrecs, PLACES), pf)
    qlist = ["רמב\"ם", "רש\"י", "רמב\"ן", "רי\"ף", "הגר\"א", "מהר\"ל", "הבעש\"ט", "בית יוסף", "רמ\"א", "חתם סופר", "האר\"י",
             "ר' נחמן מברסלב", "החזון איש", "הרב קוק", "ר' משה פיינשטיין", "האדמו\"ר הזקן", "החפץ חיים", "הרשב\"א",
             "הרא\"ש", "הרשב\"ם", "הטור", "השל\"ה", "הבן איש חי", "הרב עובדיה יוסף", "מרן"]

    def qcount(recs_, q):
        qw = [tk_norm(w) for w in _words(q) if w not in ("ר", "הרב")]
        out_ = []
        for r_ in recs_:
            ws = [tk_norm(w) for w in _words(r_["n"] + " " + r_["k"])]
            if any(ws[i:i + len(qw)] == qw for i in range(len(ws) - len(qw) + 1)):
                out_.append(r_["n"])
        return out_
    before_q = {q: qcount(allrecs, q) for q in qlist}
    if args.no_dedupe:
        dlog = []
    else:
        allrecs, dlog = dedupe_records(allrecs, [] if args.no_catalog else load_bios_entries(args.bios_gz), P)
        allrecs, mm_ = apply_manual_merges(allrecs, P)
        dlog += mm_
    after_q = {q: qcount(allrecs, q) for q in qlist}
    big = sum(1 for m in dlog if len(m["names"]) > 4)
    bad_years = sum(1 for m in dlog if max((y[1] for y in m["years"] if y[1]), default=0) - min((y[1] for y in m["years"] if y[1]), default=0) >= 2)
    P("dedupe: records before", n_before, "after", len(allrecs), "clusters merged", len(dlog),
      "by reason", dict(collections.Counter(r_ for m in dlog for r_ in m["reasons"])), "| clusters >4 members:", big,
      "| death-year spread >=2:", bad_years)
    if args.dedupe_log:
        with io.open(args.dedupe_log, "w", encoding="utf-8") as fh:
            json.dump({"merges": dlog, "before": before_q, "after": after_q}, fh, ensure_ascii=False, indent=1)
    ostats = collections.Counter()
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

    # הסרת ספרים ששויכו בטעות (לפי הקטלוג: כל מחברי הכותר הזהה אינם תואמים לרשומה; ורשימת הסרות ידנית מאומתת)
    swept = []
    for r in allrecs:
        if catalog is not None and r["bk"]:
            ri_ = RInfo(r)
            keep = []
            for b_ in r["bk"]:
                if catalog.contradicts(b_[0], ri_):
                    swept.append((r["n"], b_[0]))
                else:
                    keep.append(b_)
            r["bk"] = keep
        txt_ = clean_quotes(r["n"] + " ; " + " ; ".join(r.get("alts", [])))
        for rx_, (lo_, hi_), keys_ in BOOK_DENY:
            if re.search(rx_, txt_) and r["dy"] and lo_ <= r["dy"] <= hi_:
                keep = []
                for b_ in r["bk"]:
                    if any(bk_key(b_[0]).startswith(k_) for k_ in keys_):
                        swept.append((r["n"], b_[0]))
                    else:
                        keep.append(b_)
                r["bk"] = keep
    P("books removed (catalog contradiction / manual deny):", len(swept))
    if args.dump_attr:
        with io.open(args.dump_attr + ".swept.json", "w", encoding="utf-8") as fh:
            json.dump(swept, fh, ensure_ascii=False)

    # ----- פלט -----
    yoma_excl = sum(1 for r in allrecs if "h" in r["tags"] and (r["n"] in EXCLUDE_NAMES or has_academic_title(r["n"])))
    P("yoma-touched records excluded by name rules:", yoma_excl)
    recs = [r for r in allrecs if r["n"] not in EXCLUDE_NAMES and not has_academic_title(r["n"])]
    P("excluded (names + academic titles):", len(allrecs) - len(recs))
    dropped = collections.Counter()
    for r in recs:
        r["f"] = clean_father_field(r.get("f", ""))
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
        # שורת אינדקס: [id, שם, כינוי, שנת-לידה, שנת-פטירה, יום, חודש, ספרים, מקור, תפקיד, קובץ, (שמות חלופיים)]
        yz = r["yz"] or [0, -1]
        row = [r["i"], r["n"], r["k"], r["by"], r["dy"], yz[0], yz[1],
               "; ".join(b[0] for b in r["bk"])[:160], "".join(sorted(r["tags"])), r["r"][:60], sh]
        alt = finalize_alts(r)
        if alt:
            row.append(alt)                      # עמודה 11 (רק כשיש): שמות חלופיים לחיפוש, מופרדים ב-"; "
        index.append(row)
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

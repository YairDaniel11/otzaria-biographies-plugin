# -*- coding: utf-8 -*-
"""כלים לפענוח שנים, תאריכים ושמות בעברית — משותף לצינור בניית נתוני הרבנים."""
import re

GEM = {c: v for c, v in zip("אבגדהוזחטיכלמנסעפצקרשת", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400])}
GEM.update({"ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90})

# סדר החודשים: אינדקס -> שם. "אדר" בשנה פשוטה/אדר שני, ו"אדר א" בשנה מעוברת.
MONTHS = ["תשרי", "חשון", "כסלו", "טבת", "שבט", "אדר", "ניסן", "אייר", "סיון", "תמוז", "אב", "אלול", "אדר א", "אדר ב"]
_MONTH_WORDS = [
    (r"אד\"?א|אדר\s*(?:א['׳]?|ראשון)", 12),
    (r"אד\"?ב|אדר\s*(?:ב['׳]?|שני)", 13),
    (r"אדר", 5),
    (r"תשרי", 0), (r"מרחשוון|מר\s*חשוון|חשוון|חשון|מרחשון", 1), (r"כסליו|כסלו", 2), (r"טבת", 3), (r"שבט", 4),
    (r"ניסן", 6), (r"אייר|איר", 7), (r"סיוון|סיון", 8), (r"תמוז", 9), (r"מנחם[\s-]*אב|אב", 10), (r"אלול", 11),
]

_QUOTES = re.compile(r"[\"'׳״`’‘“”]")
_STOP_YEARISH = {"שנה", "שם", "רש", "שר", "ראש", "רב", "קר", "שק", "קש", "שש", "רח", "שני", "שנת",
                 "של", "שלח", "שרה", "שרי", "שרש", "רשת"}  # מילים שנראות כמו שנה
_YEAR_RE = re.compile(r"^([תקרש]{1,4})([יכלמנסעפצםךןףץ]?)(ט[וז]|[א-ט]?)$")
_YEAR_RE_P = re.compile(r"^([תקרש]{0,4})([יכלמנסעפצםךןףץ]?)(ט[וז]|[א-ט]?)$")   # אחרי אלפים מפורש: מותר בלי מאות ("ה'ל")
_DAY_RE = re.compile(r"^([יכל]?)([א-ט]?)$")


def gem(s):
    return sum(GEM.get(c, 0) for c in s)


def clean_quotes(s):
    return _QUOTES.sub("", s or "")


def year_token(tok, prefixed=False, loose=False):
    """אסימון גימטרי של שנה בת-אלף (תרלז -> 637). None אם זה לא שנה.
    prefixed: האסימון בא אחרי סימון אלפים מפורש (ד'/ה') — אז מותר מעל 900 ("תתקסה")
    וגם מילים שנראות כשנה ("של") נחשבות שנה."""
    t = clean_quotes(tok)
    if not t:
        return None
    if not (prefixed or loose) and (t in _STOP_YEARISH or len(t) < 2):
        return None
    if len(t) >= 4 and t[0] == "ה" and not prefixed:
        t = t[1:]                                    # "התשנח" — ה' קידומת בלי גרש
    m = (_YEAR_RE_P if prefixed else _YEAR_RE).match(t)
    if not m and 3 <= len(t) <= 5 and t[0] == "ת" and all(c in GEM for c in t):
        # אותיות בסדר שגוי ("תערב", "תשדם") — מסדרים מהגדול לקטן ובודקים שוב
        m = _YEAR_RE.match("".join(sorted(t, key=lambda c: -GEM[c])))
    if not m:
        return None
    v = gem(t)
    if v < (10 if prefixed else 100) or v > (999 if prefixed else 900):
        return None
    return v


def day_token(tok):
    t = clean_quotes(tok)
    if t in ("טו", "טז", "חי"):
        return gem(t)                                # 15, 16, 18 (כתיב "חי" במקום י"ח)
    if not t or len(t) > 2:
        return None
    if not _DAY_RE.match(t):
        return None
    v = gem(t)
    return v if 1 <= v <= 30 else None


def find_month(text):
    """מחזיר (אינדקס_חודש, התחלה, סוף) של החודש הראשון בטקסט, או None."""
    best = None
    for pat, idx in _MONTH_WORDS:
        # אחרי החודש לא תבוא אות (גם לא דרך גרשיים) — כדי ש"אב"ד" לא ייקרא "אב"
        for m in re.finditer(r"(?<![א-ת])(?:[בלמ](?=" + pat + r"))?(?:" + pat + r")(?![\"'׳״]?[א-ת])", text):
            if best is None or m.start() < best[1] or (m.start() == best[1] and m.end() > best[2]):
                best = (idx, m.start(), m.end())
        # לא עוצרים: "אדר א" צריך לגבור על "אדר"
    return best


def parse_hebrew_date(text):
    """מפענח מחרוזת כמו "תרנו - יח כסלו" / "ח' תמוז תשנד" / "ה'תקלד" / "תש.." .
    מחזיר dict עם: hy (שנה עברית מלאה או 0), day, month (אינדקס ב-MONTHS), approx."""
    out = {"hy": 0, "day": 0, "month": -1, "approx": False, "greg": 0}
    if not text:
        return out
    gm = re.search(r"(?<!\d)(1\d{3}|20[0-2]\d)(?!\d)", text)
    if gm:
        out["greg"] = int(gm.group(1))                 # שנה לועזית כתובה בספרות
    s = text.replace("\\", " ").replace("/", " ")
    out["approx"] = bool(re.search(r"בערך|בקירוב|לערך|אחרי|לפני|\?|\.\.| או |[א-ת]-[א-ת]", text.replace("\\", " | ")))
    mo = find_month(s)
    if mo:
        out["month"] = mo[0]
        before = re.findall(r"[א-ת\"'׳״]+", s[:mo[1]])
        if before:
            d = day_token(before[-1])
            if d:
                out["day"] = d
            elif clean_quotes(before[-1]) in ("רח", "ראשחודש"):
                out["day"] = 1
    # אלפים מפורש: ד' אלפים תשעב / ה'תקלד / ג"א תתק. אבל "ד' תשרי תקנט" — כאן ד' הוא היום בחודש.
    thousands = 5000
    prefixed = False
    rest_src = s
    for m in re.finditer(r"(?<![א-ת])([בגדה])(?:['׳]|\"א)\s*(?:אלפים\s*)?([א-ת\"״]+)", s):
        after = s[m.end(1):]
        mo2 = find_month(after)
        if mo2 and mo2[1] <= 3:
            continue                                  # אחרי האות בא חודש — זה יום, לא אלפים
        thousands = {"ב": 2000, "ג": 3000, "ד": 4000, "ה": 5000}[m.group(1)]
        prefixed = True
        rest_src = m.group(2) + " " + s[m.end():]
        break
    toks = list(re.finditer(r"[א-ת\"'׳״]+", rest_src))
    # כשיש כמה שנים בשדה ("תקפ \ ד' תשרי תקפא") — מעדיפים את זו שבאה אחרי החודש
    mo_r = find_month(rest_src)
    if mo_r:
        toks = [t for t in toks if t.start() >= mo_r[2]] + [t for t in toks if t.start() < mo_r[2]]
    for tm in toks:
        loose = bool(mo_r) and tm.start() >= mo_r[2]
        v = year_token(tm.group(0), prefixed=prefixed, loose=loose)
        if v:
            out["hy"] = thousands + v
            break
    # "אדר" בשנה מעוברת הוא אדר ב' (בשנה פשוטה נשאר אדר)
    if out["hy"] and out["month"] == 5 and is_leap(out["hy"]):
        out["month"] = 13
    return out


# ---------- לוח עברי -> שנה לועזית (ג'ולייני לפני 15.10.1582) ----------
_HEB_EPOCH = -1373427                      # R.D. של 1 תשרי ה'א'
_GREG_START = 577735                       # R.D. של 15.10.1582 (תחילת הלוח הגרגוריאני)


def is_leap(hy):
    return (7 * hy + 1) % 19 < 7


def _elapsed_days(y):
    months = (235 * y - 234) // 19
    parts = 12084 + 13753 * months
    day = months * 29 + parts // 25920
    if (3 * (day + 1)) % 7 < 3:
        day += 1
    return day


def _rosh_hashana(y):
    ny0, ny1, ny2 = _elapsed_days(y - 1), _elapsed_days(y), _elapsed_days(y + 1)
    delay = 2 if ny2 - ny1 == 356 else (1 if ny1 - ny0 == 382 else 0)
    return _HEB_EPOCH + ny1 + delay


def _year_len(y):
    return _rosh_hashana(y + 1) - _rosh_hashana(y)


def _month_start_offset(y, month):
    """ימים מ-1 בתשרי עד תחילת החודש (אינדקס כמו MONTHS; 5=אדר/אדר ב' בשנה מעוברת, 12=אדר א', 13=אדר ב')."""
    ln = _year_len(y)
    leap = is_leap(y)
    cheshvan = 30 if ln % 10 == 5 else 29
    kislev = 29 if ln % 10 == 3 else 30
    lens = [30, cheshvan, kislev, 29, 30]                      # תשרי..שבט
    if leap:
        lens += [30, 29]                                       # אדר א', אדר ב'
    else:
        lens += [29]                                           # אדר
    lens += [30, 29, 30, 29, 30, 29]                           # ניסן..אלול
    if leap:
        pos = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 12: 5, 5: 6, 13: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12}
    else:
        pos = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 12: 5, 13: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 11}
    return sum(lens[:pos[month]])


def _year_of_fixed(d):
    if d >= _GREG_START:
        d0 = d - 1
        n400, d1 = divmod(d0, 146097)
        n100, d2 = divmod(d1, 36524)
        n4, d3 = divmod(d2, 1461)
        n1 = d3 // 365
        year = 400 * n400 + 100 * n100 + 4 * n4 + n1
        return year if (n100 == 4 or n1 == 4) else year + 1
    return (4 * (d + 1) + 1464) // 1461                        # ג'ולייני


def hy_to_g(hy, month=-1, day=0):
    """שנה עברית -> לועזית. עם חודש (ואם אפשר יום) — חישוב מדויק לפי הלוח העברי;
    בלי חודש — הערכה hy-3760 (רוב החודשים נופלים בחציו השני של השנה)."""
    if not hy:
        return 0
    if month < 0:
        return hy - 3760
    d = _rosh_hashana(hy) + _month_start_offset(hy, month) + ((day or 15) - 1)
    return _year_of_fixed(d)


def norm_text(s):
    return re.sub(r"\s+", " ", (s or "").replace("‏", "").replace("‎", "")).strip()


# ---------- שמות ----------
_TITLES = {"ר", "רבי", "הרב", "הגאון", "מהר\"ר", "מוהר\"ר", "מהרר", "מוהרר", "הרה\"ג", "הרהג", "הגה\"צ", "הגהצ",
           "הג\"ר", "הגר", "רבינו", "רבנו", "מו\"ר", "מור", "מרן", "האדמו\"ר", "האדמור", "אדמו\"ר", "אדמור",
           "הצדיק", "הרה\"צ", "הרהצ", "הרה\"ג", "זקן", "החכם", "חכם", "ה\"ר", "הר"}
_NOISE = {"זצל", "זצ\"ל", "זל", "ז\"ל", "הי\"ד", "היד", "שליט\"א", "שליטא", "זיע\"א", "זיעא", "נ\"ע", "נע", "זצוק\"ל", "זצוקל"}


def split_surname(name):
    """"פסחוביץ, חיים מסטרי" -> ("פסחוביץ", "חיים מסטרי")."""
    if "," in name:
        a, b = name.split(",", 1)
        return a.strip(), b.strip()
    return "", name.strip()


def name_tokens(name, csv_style=False):
    """טוקנים מנורמלים של שם להשוואה: בלי תארים, סוגריים, שם אב ("ב"ר ...")."""
    s = norm_text(name)
    if csv_style and "," in s:
        a, b = s.split(",", 1)
        s = b.strip() + " " + a.strip()
    elif "," in s:
        s = s.split(",", 1)[0]          # אחרי הפסיק בא תיאור התפקיד
    s = re.split(r"\s[–—-]\s*|[–—-]\s+|\s*[–—]\s*|\\| \(|\[", s)[0]
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    # שם האב: ב"ר / בן ר' ...
    s = re.split(r"\s(?:ב\"ר|בר\"|ב'ר|בן\s+ר['׳]?|בן)\s", s + " ")[0] if re.search(r"\sב\"ר\s|\sב'ר\s", " " + s + " ") else s
    toks = []
    for t in re.split(r"[\s,;:–—\-־]+", re.sub(r"[֑-ׇ]", "", s)):
        c = clean_quotes(t)
        if not c or c in _SKIP_TOKENS:
            continue
        toks.append(_spell_norm(c))
    return toks


_SKIP_TOKENS = {clean_quotes(x) for x in _TITLES} | {clean_quotes(x) for x in _NOISE}


def _spell_norm(tok):
    """איחוד וריאנטי כתיב נפוצים: ווילנא/וילנא, שניאורסאהן/שניאורסון (חלקית), ז'/ז."""
    t = re.sub(r"וו+", "ו", tok)
    t = re.sub(r"יי+", "י", t)
    return t


def sort_key(name):
    """מפתח מיון/חלוקה לאותיות — לפי תחילת השם (שם משפחה בראש, כמו באוצר הרבנים)."""
    s = clean_quotes(norm_text(name))
    for ch in s:
        if "א" <= ch <= "ת":
            return ch
    return "#"

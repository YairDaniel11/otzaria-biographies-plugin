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

הרצה:  python -I tools/build_rabbis.py [--src <תיקיית המקורות>] [--report <קובץ>]
"""
import argparse, collections, csv, difflib, glob, hashlib, io, json, os, re, sys
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hebdates import (MONTHS, is_leap, parse_hebrew_date, hy_to_g, name_tokens, norm_text, sort_key,
                      clean_quotes, gem)
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
            "yz": None, "b": "", "s": [], "bk": [], "tags": {tag}, "approx_by": False}


# מחרוזת תאריך שהיא בעצם פרוזה ("בשנת תרנ הגיע לארץ ישראל") — אין לחלץ ממנה שנה
_PROSE_WORDS = 6
PLACES = set()                       # לקסיקון מקומות (עמודות 5 ו-7 ב-CSV) — נבנה ב-load_csv
VALID_CATS = None                    # קטגוריות ספרים חוקיות (מה-RTF) — נבנה ב-load_rtf
_NOT_BIRTH_DEATH = re.compile(r"נדפס|הודפס|נדפסו|הדפסה")


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
                                    "srcs": [], "books": [], "tag": "s", "yz_only": False, "notes": []})
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
            a["books"] += split_books(title)
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
        if not started or cur is None or not p:
            continue
        m2 = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", p)
        if m2 and m2.group(2) in catset:
            cur["bk"].append([m2.group(1).strip(), m2.group(2)])
        else:
            cur["bk"].append([p, ""])
    return authors


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
        rare = min(et, key=lambda t: len(self.inv.get(t, ())) or 10 ** 9)
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
    args = ap.parse_args()
    rep = io.open(args.report, "w", encoding="utf-8") if args.report else sys.stdout
    P = lambda *a: rep.write(" ".join(str(x) for x in a) + "\n")

    core = load_csv(find(args.src, "*רבנים*ביוגרפיות*.csv", "*1793053864434*.csv"))
    rtf = load_rtf(find(args.src, "*כרונולוגית*.rtf", "*1793055225292*.rtf"))     # ראשון: קובע את VALID_CATS
    shnot = load_shnot(find(args.src, "*שנות-דור*.xlsx", "*1793054927081*.xlsx"))
    yahr = load_yahrzeit(find(args.src, "*היארצייטים*.xlsx", "*1793055067103*.xlsx"))
    otz, otz_total, otz_ok = load_otzrot(find(args.src, "*אוצרות-התורה*.xlsx", "*1793054383839*.xlsx"))
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

    # ----- פלט -----
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

    os.makedirs(OUT_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(OUT_DIR, "*.js")):
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
        by_shard[sh].append(full)
        # שורת אינדקס: [id, שם, כינוי, שנת-לידה, שנת-פטירה, יום, חודש, ספרים, מקור, תפקיד, קובץ]
        yz = r["yz"] or [0, -1]
        index.append([r["i"], r["n"], r["k"], r["by"], r["dy"], yz[0], yz[1],
                      "; ".join(b[0] for b in r["bk"])[:160], "".join(sorted(r["tags"])), r["r"][:60], sh])
    ver = hashlib.md5(json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:8]
    for sh, items in by_shard.items():
        name = "rb-%s-%d.js" % (ver, sh)
        with io.open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as fh:
            fh.write("window.RB_SHARDS=window.RB_SHARDS||{};window.RB_SHARDS[%d]=" % sh)
            json.dump(items, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write(";\nwindow.RB_LOADED&&window.RB_LOADED(%d);\n" % sh)
    with io.open(os.path.join(OUT_DIR, "rb-index.js"), "w", encoding="utf-8") as fh:
        fh.write('window.RB_VER="%s";\nwindow.RB_MONTHS=' % ver)
        json.dump(MONTHS, fh, ensure_ascii=False)
        fh.write(";\nwindow.RB_LETTERS=")
        json.dump(letters, fh, ensure_ascii=False)
        fh.write(";\nwindow.RB_INDEX=")
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    sizes = sorted(((os.path.getsize(f), os.path.basename(f)) for f in glob.glob(os.path.join(OUT_DIR, "*.js"))), reverse=True)
    P("files:", len(sizes), "total bytes:", sum(s for s, _ in sizes), "largest:", sizes[:4])
    P("letters:", letters)
    if args.report:
        rep.close()


if __name__ == "__main__":
    main()

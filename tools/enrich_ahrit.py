# -*- coding: utf-8 -*-
"""העשרת אינדקס הרבנים (src/data/rabbis/rb-index.js) משנות חיים מתוך "רשימת הספרים אחרית הימים".

עיקרון: "דיוק לפני כיסוי". משלימים רק שדה *חסר* (שנת לידה / שנת פטירה / יארצייט) ולעולם לא דורסים,
ורק כשהרשומה זוהתה בוודאות: מועמד יחיד שמכיל את כל מילות שם המחבר, ועם ראיה בלתי-תלויה בשדה המושלם
(כותר ספר זהה ברשימת הספרים של הרב, או שנה אחרת שמתאימה בטווח שנה). סתירה בשנה קיימת פוסלת את ההתאמה.

שימוש:
  python -I tools/enrich_ahrit.py --src "<רשימת הספרים אחרית הימים.txt>" --gen      # יוצר tools/enrich-data/ahrit-patches.json + דוח
  python -I tools/enrich_ahrit.py --apply                                             # מחיל את הטלאים על rb-index.js (idempotent)
יש להריץ --apply מחדש אחרי כל הרצה של build_rabbis.py (שמייצר את האינדקס מחדש).
"""
import argparse, collections, io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hebdates as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "src", "data", "rabbis", "rb-index.js")
PATCHES = os.path.join(ROOT, "tools", "enrich-data", "ahrit-patches.json")
NEW = os.path.join(ROOT, "tools", "enrich-data", "ahrit-new.json")

STOP = {"ר", "רבי", "רבינו", "רבנו", "הרב", "הגאון", "מהר", "הרה", "בן", "בר", "הגרון", "ז"}
DEL = set("\"'()[].^:;,\\\u05f3\u05f4")


def cl(s):
    return "".join(" " if ch == "-" else ("" if ch in DEL else ch) for ch in s)


def toks(s):
    return [w for w in cl(s).split() if w not in STOP and len(w) > 1]


def bk(s):
    return re.sub(r"[^א-ת]", "", s)


def load_index():
    t = io.open(INDEX, encoding="utf-8").read()
    i = t.index("window.RB_INDEX=")
    head, body = t[:i + 16], t[i + 16:]
    j = body.rindex("]")
    return head, json.loads(body[:j + 1]), body[j + 1:]


def parse_dates(txt):
    """-> dict(hy, greg, month, day, ok): ok=False כשאין שנה ודאית (ערך מקורב / כמה חלופות)."""
    if not txt:
        return None
    d = H.parse_hebrew_date(txt)
    if not d["hy"]:
        return None
    words = txt.split()
    clean = len(words) <= 4 and all(re.fullmatch(r"[א-ת\"'׳״]+", w) for w in words) and "אלפים" not in txt
    g = H.hy_to_g(d["hy"], d["month"], d["day"]) if d["month"] >= 0 else H.hy_to_g(d["hy"])
    ok = clean and not d["approx"] and not re.search(r"וי\"א|בערך|בע'|כנראה|לפני|אחרי|לאחר|ר\"ה|חול|יו\"ט", txt) and 1000 <= g <= 2030
    return {"hy": d["hy"], "g": g, "m": d["month"], "d": d["day"], "ok": ok}


def parse_records(raw):
    body = raw.split("אות א</h2>", 1)[1]
    body = re.sub(r"<h2>.*?</h2>", "\n", body)
    lines = []
    for ln in body.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if lines and "מחבר:" not in ln and "מחבר:" in lines[-1]:
            lines[-1] += " " + ln
        else:
            lines.append(ln)
    recs = []
    for ln in lines:
        m = re.match(r"^(.*?)\.\s*מחבר:\s*(.*?)\.\s*(.*)$", ln)
        if not m:
            continue
        title, au, rest = m.groups()

        def f(k):
            mm = re.search(k + r":\s*(.*?)(?:\.\s*(?:שנת|הערות|מקור)|\.?$)", rest)
            return mm.group(1).strip() if mm else ""
        recs.append({"title": title.split(" - ")[0].strip(), "au": au.strip(),
                     "b": f("שנת לידה"), "d": f("שנת פטירה"), "note": f("הערות"), "src": f("מקור")})
    return recs


def near(y, ys, tol=1):
    return any(abs(y - z) <= tol for z in ys)


TITLES = {"ר", "רבי", "רבינו", "רבנו", "רב", "הרב", "הגאון", "הרה", "מהר", "הנשיא", "הגה", "הרבי", "מוהר", "הצדיק", "האדמו", "הגרון"}
GIVEN_M = {"משה", "מרדכי", "מנחם", "מאיר", "מנדל", "מיכל", "מיכאל", "משולם", "מנשה", "מצליח", "מימון", "מסעוד", "מנצור", "מוסא", "מזל", "מרים", "מעוז", "מצרי"}


def is_place(t, surnames):
    """מילה אחרונה בשם שהיא שם מקום ("מפראג"): מתחילה ב-מ, לא שם פרטי מוכר ולא שם משפחה שקיים באינדקס."""
    return len(t) >= 4 and t[0] == "מ" and t not in GIVEN_M and t not in surnames


NOISE_W ={"היד", "זצל", "זצוקל", "זל", "שליטא", "זיעא", "עה", "נע", "יצו", "אבד", "אבדק", "הנזכר"}
SUFFIX = {"הלוי", "הכהן"}


def build_name(au, places):
    """שם מחבר מהקובץ -> שם בסגנון האינדקס: "משפחה, פרטי [מקום]". None אם זו לא דמות בודדת."""
    if re.search(r"(?:^|\s)ו?ר['׳]\s|הגיסים|הנ\"ל| ו(?:בנו|אחיו)", au) and au.count("ר'") > 1:
        return None
    paren = re.findall(r"\(([^)]*)\)", au)
    core = re.sub(r"\([^)]*\)", "", au)
    core = re.split(r"\s+ב\"ר\s|\s+ב:ר\s|\s+בן\s+ר['׳]|\s+[-\\]\s*|\?", core)[0]
    ws = [w for w in core.split() if re.sub(r"[\"'׳״]", "", w) not in TITLES | NOISE_W]
    if not ws:
        return None
    place = ""
    if len(ws) >= 3 and is_place(ws[-1], places):
        place = ws.pop()
    if len(ws) == 1:
        return (ws[0] + (" " + place if place else "")).strip()
    sur = ws[-1]
    if sur in SUFFIX and paren:
        sur = paren[0].strip()
        given = " ".join(ws)
    else:
        given = " ".join(ws[:-1])
    return ("%s, %s%s" % (sur, given, " " + place if place else "")).strip()


def build_new(to_add, idx, stats):
    places = {r[1].split(",")[0].strip() for r in idx if "," in r[1]}      # שמות משפחה קיימים — לא מקומות
    letters = ["א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ", "ק", "ר", "ש", "ת"]
    out, seen = [], set()
    for au, a, why in to_add:
        name = build_name(au, places)
        if not name:
            stats["לא נוסף: לא דמות בודדת"] += 1
            continue
        pb, pd_ = parse_dates(a["b"]), parse_dates(a["d"])
        rec = {"n": name, "why": why, "au": au}
        if pb and pb["ok"]:
            rec["by"] = pb["g"]
        if pd_ and pd_["ok"]:
            rec["dy"] = pd_["g"]
            if pd_["m"] >= 0 and pd_["d"]:
                rec["yd"], rec["ym"] = pd_["d"], pd_["m"]
        for k, t in (("bt", a["b"]), ("dt", a["d"])):
            if t:
                rec[k] = t[:60]
        if a["note"]:
            rec["r"] = a["note"][:60]
            rec["note"] = a["note"]
        rec["bk"] = [t for t in a["titles"]][:40]
        if rec.get("by") and rec.get("dy") and not (5 <= rec["dy"] - rec["by"] <= 115):
            stats["לא נוסף: אורך חיים לא סביר"] += 1
            continue
        key = (name, rec.get("dy", 0))
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    stats["נוספו כחדשים"] = len(out)
    return out


def generate(src, report_path):
    recs = parse_records(io.open(src, encoding="utf-8").read())
    auth = collections.OrderedDict()      # מפתח (שם, שנת פטירה עברית) — מבדיל בין בעלי שם זהה
    groups = collections.defaultdict(list)
    for r in recs:
        d = H.parse_hebrew_date(r["d"]) if r["d"] else None
        dh = d["hy"] if d and d["hy"] else 0
        ks = groups[r["au"]]
        key = next((k for k in ks if k[1] == dh), None) if dh else (ks[0] if ks else None)
        if key is None:
            key = (r["au"], dh)
            ks.append(key)
        a = auth.setdefault(key, {"au": r["au"], "b": "", "d": "", "books": set(), "titles": [], "note": "", "src": ""})
        a["b"] = a["b"] or r["b"]
        a["d"] = a["d"] or r["d"]
        a["note"] = a["note"] or r["note"]
        a["books"].add(bk(r["title"]))
        if r["title"] not in a["titles"]:
            a["titles"].append(r["title"])
    _, idx, _ = load_index()
    inv = collections.defaultdict(set)
    for k, r in enumerate(idx):
        for w in set(toks(r[1])):
            inv[w].add(k)
    stats = collections.Counter()
    patches, rep, skipped = [], [], []
    to_add = []
    for (au, _dh), a in auth.items():
        core = re.split(r"\s+ב\"ר\s|\(", au)[0]
        tk = toks(core)
        if len(tk) < 2:
            stats["שם קצר מדי"] += 1
            skipped.append(("שם קצר", au))
            continue
        cand = None
        for w in tk:
            cand = inv.get(w, set()) if cand is None else cand & inv.get(w, set())
        cand = [k for k in (cand or []) if len(toks(idx[k][1])) <= len(tk) + 4]
        if not cand:
            stats["אין מועמד באינדקס"] += 1
            to_add.append((au, a, "חדש"))
            continue
        pb, pd_ = parse_dates(a["b"]), parse_dates(a["d"])
        books = {b for b in a["books"] if len(b) >= 4}
        good = []
        alive = 0
        for k in cand:
            r = idx[k]
            # סתירה בשנה קיימת פוסלת
            if pb and pb["ok"] and r[3] and not near(r[3], [pb["g"]]):
                continue
            if pd_ and pd_["ok"] and r[4] and not near(r[4], [pd_["g"]]):
                continue
            alive += 1
            ev_book = bool(r[7]) and bool({bk(x) for x in r[7].split("; ")} & books)
            ev_b = bool(pb and r[3] and near(r[3], [pb["g"]]))
            ev_d = bool(pd_ and r[4] and near(r[4], [pd_["g"]]))
            if ev_book or (ev_b and ev_d):
                good.append((k, ev_book, ev_b, ev_d))
            elif ev_b or ev_d:
                good.append((k, ev_book, ev_b, ev_d))
        if len(good) > 1:
            stats["דו-משמעי"] += 1
            skipped.append(("דו-משמעי", au))
            continue
        if not good:
            if alive == 0:                      # כל המועמדים סותרים בשנים — אדם אחר באותו שם
                stats["שם זהה, שנים סותרות (נוסף כחדש)"] += 1
                to_add.append((au, a, "שם זהה בשנים אחרות"))
            else:
                stats["מועמד לא מאומת (לא נוסף)"] += 1
                skipped.append(("מועמד לא מאומת", au))
            continue
        k, ev_book, ev_b, ev_d = good[0]
        r = idx[k]
        stats["זוהה"] += 1
        p = {"i": r[0], "n": r[1]}
        # השלמת לידה: ראיה בלתי-תלויה = ספר או פטירה תואמת; השלמת פטירה: ספר או לידה תואמת
        if pb and pb["ok"] and not r[3] and (ev_book or ev_d):
            p["by"] = pb["g"]
        if pd_ and pd_["ok"] and not r[4] and (ev_book or ev_b):
            p["dy"] = pd_["g"]
        dy_final = r[4] or p.get("dy")
        if pd_ and pd_["ok"] and not r[5] and pd_["m"] >= 0 and pd_["d"] and dy_final and near(dy_final, [pd_["g"]]):
            if r[4] or ev_book or ev_b:
                p["yd"], p["ym"] = pd_["d"], pd_["m"]
        # בדיקת סבירות: חיים בני 5-115 שנה
        by_f, dy_f = r[3] or p.get("by"), r[4] or p.get("dy")
        if by_f and dy_f and not (5 <= dy_f - by_f <= 115):
            stats["נפסל: אורך חיים לא סביר"] += 1
            continue
        if len(p) > 2:
            patches.append(p)
            rep.append("%s | מחבר בקובץ: %s | תאריכים: לידה=%s פטירה=%s | טלא=%s | ראיה: ספר=%s לידה=%s פטירה=%s" % (
                r[1], au, a["b"], a["d"], {k_: v for k_, v in p.items() if k_ not in ("i", "n")}, ev_book, ev_b, ev_d))
    new = build_new(to_add, idx, stats)
    with io.open(NEW, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, indent=0)
    os.makedirs(os.path.dirname(PATCHES), exist_ok=True)
    with io.open(PATCHES, "w", encoding="utf-8") as fh:
        json.dump(patches, fh, ensure_ascii=False, indent=0)
    with io.open(report_path, "w", encoding="utf-8") as fh:
        fh.write("סטטיסטיקה: %s\nטלאים: %d (לידה %d, פטירה %d, יארצייט %d)\n\n" % (
            dict(stats), len(patches), sum("by" in p for p in patches), sum("dy" in p for p in patches), sum("yd" in p for p in patches)))
        fh.write("\n".join(rep) + "\n\n=== רשומות חדשות (%d) ===\n" % len(new))
        for n in new:
            fh.write("%s | %s => %s | %s - %s | %s\n" % (n["why"], n["au"], n["n"], n.get("bt", ""), n.get("dt", ""), n.get("r", "")))
        fh.write("\n=== לא נוספו ===\n" + "\n".join("%s: %s" % x for x in skipped) + "\n")
    print(dict(stats), "patches:", len(patches))


def apply():
    patches = json.load(io.open(PATCHES, encoding="utf-8"))
    head, idx, tail = load_index()
    byid = {r[0]: r for r in idx}
    n = collections.Counter()
    for p in patches:
        r = byid.get(p["i"])
        if not r or r[1] != p["n"]:
            n["דולג (הרשומה השתנתה)"] += 1
            continue
        if "by" in p and not r[3]:
            r[3] = p["by"]; n["לידה"] += 1
        if "dy" in p and not r[4]:
            r[4] = p["dy"]; n["פטירה"] += 1
        if "yd" in p and not r[5] and r[6] < 0:
            r[5], r[6] = p["yd"], p["ym"]; n["יארצייט"] += 1
    add_new_records(head, idx, n)
    with io.open(INDEX, "w", encoding="utf-8", newline="") as fh:
        fh.write(head)
        json.dump(idx, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(tail)
    print(dict(n))


SRC_LABEL = "אחרית הימים (פרקוביץ ומורגנשטרן)"


def add_new_records(head, idx, n):
    """מוסיף את הרשומות החדשות (ahrit-new.json) לאינדקס ולקובצי הנתונים לפי אות. idempotent: לפי שם + תג h."""
    if not os.path.exists(NEW):
        return
    new = json.load(io.open(NEW, encoding="utf-8"))
    letters = json.loads(re.search(r"window\.RB_LETTERS=(\[.*?\]);", head, re.S).group(1))
    ver = re.search(r'window\.RB_VER="([0-9a-f]+)"', head).group(1)
    have = {r[1] for r in idx if "w" in r[8]}
    nxt = max(r[0] for r in idx) + 1
    by_shard = collections.defaultdict(list)
    for p in new:
        if p["n"] in have:
            continue
        L = H.sort_key(p["n"])
        if L not in letters:
            n["דולג (אות לא מוכרת)"] += 1
            continue
        sh = letters.index(L)
        books = p.get("bk", [])
        row = [nxt, p["n"], "", p.get("by", 0), p.get("dy", 0), p.get("yd", 0), p.get("ym", -1),
               "; ".join(books)[:160], "w", p.get("r", ""), sh]
        key = H.clean_quotes(p["n"])
        pos = None
        for k in range(len(idx) - 1, -1, -1):          # אחרי הרשומה האחרונה באותה אות ששמה <= החדש
            if idx[k][10] == sh and H.clean_quotes(idx[k][1]) <= key:
                pos = k + 1
                break
        if pos is None:
            pos = next((k for k, r in enumerate(idx) if r[10] >= sh), len(idx))
        idx.insert(pos, row)
        rec = {"i": nxt, "n": p["n"]}
        for k_out, k_in in (("bt", "bt"), ("dt", "dt")):
            if p.get(k_in):
                rec[k_out] = p[k_in]
        if p.get("r"):
            rec["r"] = p["r"]
        if p.get("note"):
            rec["b"] = p["note"]
        rec["s"] = SRC_LABEL
        if books:
            rec["bk"] = [[t, ""] for t in books]
        by_shard[sh].append(rec)
        nxt += 1
        n["רשומות חדשות"] += 1
    for sh, recs in by_shard.items():
        path = os.path.join(ROOT, "src", "data", "rabbis", "rb-%s-%d.js" % (ver, sh))
        t = io.open(path, encoding="utf-8").read()
        m = re.match(r"^(window\.RB_SHARDS=window\.RB_SHARDS\|\|\{\};window\.RB_SHARDS\[%d\]=)(\[.*\])(;\s*window\.RB_LOADED.*)$" % sh, t, re.S)
        arr = json.loads(m.group(2))
        arr.extend(recs)
        arr.sort(key=lambda r: r["i"])
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(m.group(1) + json.dumps(arr, ensure_ascii=False, separators=(",", ":")) + m.group(3))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src")
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default="enrich_report.txt")
    a = ap.parse_args()
    if a.gen:
        generate(a.src, a.report)
    if a.apply:
        apply()

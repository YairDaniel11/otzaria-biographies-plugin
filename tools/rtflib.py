"""מפענח RTF מינימלי: מחזיר רשימת פסקאות/תאים (טקסט נקי) מקובץ RTF של וורד."""
import re

SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "latentstyles", "listtable", "listoverridetable",
        "rsidtbl", "themedata", "colorschememapping", "datastore", "generator", "header", "footer",
        "pgdsctbl", "xmlnstbl", "mmathPr", "wgrffmtfilter", "factoidname", "private", "pict", "object"}
SEP = {"par", "cell", "row", "sect", "page"}
CTRL = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?")


def rtf_paragraphs(path, codepage="cp1255"):
    raw = open(path, "rb").read().decode("latin-1")
    out, cur = [], []
    stack = []          # לכל קבוצה: (skip, uc)
    skip = False
    uc = 1
    i, n = 0, len(raw)
    skip_chars = 0
    def flush():
        s = "".join(cur).strip()
        cur.clear()
        if s:
            out.append(s)
    while i < n:
        ch = raw[i]
        if ch == "{":
            stack.append((skip, uc)); i += 1
            # בדיקת יעד
            m = re.match(r"\\\*|\\([a-zA-Z]+)", raw[i:i + 40])
            if m and (m.group(0) == "\\*" or m.group(1) in SKIP):
                skip = True
            continue
        if ch == "}":
            if stack: skip, uc = stack.pop()
            i += 1; continue
        if ch in "\r\n":
            i += 1; continue
        if ch == "\\":
            nx = raw[i + 1] if i + 1 < n else ""
            if nx == "'":
                hx = raw[i + 2:i + 4]
                i += 4
                if skip_chars: skip_chars -= 1; continue
                if not skip:
                    try: cur.append(bytes([int(hx, 16)]).decode(codepage, "replace"))
                    except ValueError: pass
                continue
            if nx in "\\{}":
                if not skip: cur.append(nx)
                i += 2; continue
            if nx == "~":
                if not skip: cur.append(" ")
                i += 2; continue
            if nx in "-_*:|":
                i += 2; continue
            m = CTRL.match(raw, i)
            if not m:
                i += 1; continue
            word, arg = m.group(1), m.group(2)
            i = m.end()
            if word == "uc" and arg is not None:
                uc = int(arg)
            elif word == "u" and arg is not None:
                if not skip:
                    cur.append(chr(int(arg) % 65536))
                skip_chars = uc
            elif word in SEP:
                if not skip: flush()
            elif word in ("tab",):
                if not skip: cur.append(" ")
            elif word in ("line",):
                if not skip: cur.append(" ")
            elif word == "emdash": cur.append("—")
            elif word == "endash": cur.append("–")
            elif word in ("lquote", "rquote"): cur.append("'")
            elif word in ("ldblquote", "rdblquote"): cur.append('"')
            continue
        if skip_chars:
            skip_chars -= 1; i += 1; continue
        if not skip:
            cur.append(ch)
        i += 1
    flush()
    return out

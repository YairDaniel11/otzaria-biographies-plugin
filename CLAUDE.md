# ביוגרפיות (תוסף לאוצריא)

> טיוטה שנוצרה אוטומטית מקריאת קבצי המאגר. יש לאמת פרטים לפני הסתמכות.

תוסף לאוצריא (JS/HTML/CSS, webapp): אנציקלופדיית תנאים ואמוראים, ראשונים ואחרונים (כ-56 אלף רבנים), ציר דורות, סדר הדורות, מסעות במדבר ולוח אירועים. id: `com.otzaria.biographies-tannaim-amoraim`.

## מבנה
- `src/manifest.json` - מניפסט (גרסה, הרשאות, allowlist רשת ל-`https://api.emailjs.com`, `toolTab`).
- `src/index.html`, `src/js/` (`app.js`, `common.js`, `icons.js`, `rabbis.js`, `rb-timeline.js`), `src/css/` (`style.css`, `rabbis.css`, `rabbis-extra.css`).
- `src/i18n/` (`i18n.js`, `en.js`) - תרגום לאנגלית לפי שפת הממשק של אוצריא.
- `src/data/` - `bio-data.js`, `bio-enrich.js`, `events-data.js`, `lib-authors.js`, `masaot-data.js`, `yeshivot.js`; `src/data/rabbis/rb-index.js` + `rb-<hash>-N.js` (ביוגרפיות לפי אות, נטענים לפי צורך); `src/seder-hadorot/seder-list.js`.
- `tools/` - `build_rabbis.py` (מייצר את `src/data/rabbis/`), `hebdates.py`, `rtflib.py`. הנתונים שנוצרו אינם לעריכה ידנית.
- `build.ps1` - אריזה מקומית.

## בנייה והרצה
- בנייה מקומית: `.\build.ps1` (יוצר `otzaria-biographies.otzplugin` בשורש; הארכיון שטוח, `manifest.json` בשורשו). התקנה: הגדרות -> ניהול תוספים -> התקנה מקובץ.
- יצירת נתוני רבנים: `python -I tools/build_rabbis.py --src <תיקיית מקורות> --report build_report.txt` (דגלים נוספים ב-README: `--yoma`, `--out`, `--seforim-db`, `--hb-db`, `--bios-gz`, `--no-catalog`). קבצי המקור אינם במאגר; הרצה לא נבדקה.

## שחרור / CI
- `.github/workflows/release.yml`: בדחיפה ל-`main` או ידנית - קורא גרסה מ-manifest, `Otzaria/otzaria-plugin-validator@v1` (אימות, בנייה, פרסום לחנות; סודות `OTZARIA_USER`/`OTZARIA_PASSWORD`), ויוצר תג `vX.Y.Z` + GitHub Release עם ה-`.otzplugin`.
- גרסה חדשה = העלאת `version` ב-`src/manifest.json` ודחיפה ל-`main`; אם לא השתנתה - מדלג.
- מספור: הספרה האחרונה עולה עד 9 ואז מתגלגלת (`1.0.9` -> `1.1.0`).

## מוסכמות ומלכודות
- כלל שיוך ספרים: "דיוק לפני כיסוי" (ראו README, סעיף נתוני "ראשונים ואחרונים").
- מאגר הביוגרפיות של אוצריא (AGPL-3.0, abaye) משמש כראיית אימות בלבד בבנייה, ויש לייחס אותו (README).
- הקריאה לרשת עברה מ-`network.fetch` ל-`network.fetchStream` (הוסר באוצריא 0.9.98) - ראו קומיט 4c211d6.
- `.gitignore`: `*.otzplugin`, `__pycache__/`.
- קיים תוסף אחות "ביוגרפיות+" עם קוד דומה (`bio-data.js` וכו') - שינויים משותפים צריכים להיעשות בשניהם; מידת הסנכרון לא נבדקה.
- README מציין סוד `OTZARIA_PLUGIN_ID`, אך ה-workflow הנוכחי לא משתמש בו (מזהה לפי ה-id במניפסט).

## מצב נוכחי
- ענף `main`, remote `origin`: https://github.com/YairDaniel11/otzaria-biographies-plugin.git; עץ נקי (`main...origin/main`).
- מניפסט: 2.3.6, `stability: stable`, `minAppVersion` 0.9.97.
- קומיטים אחרונים: v2.3.6 (מקורות מידע בכרטיס הרב), v2.3.5 (איחוד כפילויות, שמות חלופיים לחיפוש), v2.3.4 (אימות מחברים, אירועים), v2.3.3 (לשונית "ראשונים ואחרונים"); לפניהם מעבר ל-Action הרשמי ותמיכה רב-לשונית.

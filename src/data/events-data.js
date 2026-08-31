/* ===========================================================================
 *  נתוני "לוח אירועים" — נחלץ מקובץ "לוח ארועים.xlsx"
 *  כל אירוע: day (יום בחודש העברי, אותיות), month (שם החודש העברי),
 *  dateText (תאריך מפורש אם קיים בגיליון), year (שנה עברית אם קיימת),
 *  event (תיאור האירוע), source (מקור), category (קטגוריה/סוג)
 * ========================================================================= */
window.EVENTS = [
  { day:"א", month:"תשרי", dateText:"", year:"", event:"עולי בבל החלו להעלות עולות לה'", source:"עזרה ג:ו", category:"תנ״ך" },
  { day:"י", month:"תשרי", dateText:"", year:"", event:"יחזקאל מתנבא על הבית השלישי", source:"יחזקאל מ:א", category:"תנ״ך" },
  { day:"כא", month:"תשרי", dateText:"", year:"", event:"נבואת חגי השניה", source:"חגי ב:א", category:"תנ״ך" },
  { day:"כד", month:"תשרי", dateText:"", year:"", event:"נבואת חגי השלישית", source:"חגי ב:כ", category:"תנ״ך" },
  { day:"כד", month:"תשרי", dateText:"", year:"", event:"עולי בבל נאספו בצום ובשקים והתוודו על עוונותיהם", source:"נחמיה ט:א", category:"תנ״ך" },
  { day:"א", month:"חשון", dateText:"א חשון", year:"ב' תתקלו", event:"נגמר בנין בית ראשון על ידי שלמה המלך, אך ננעל עד ח' תשרי תתקלז", source:"ילקוט שמעוני מלכים קפד", category:"מדרשים" },
  { day:"ד", month:"כסלו", dateText:"", year:"", event:"נבואת זכריה שהצומות יהפכו לששון ולשמחה", source:"זכריה ז:א", category:"שואה" },
  { day:"כ", month:"כסלו", dateText:"", year:"", event:"כל עולי בבל נקבצו לכינוס תשובה עם עזרא הסופר", source:"עזרא י:ט", category:"תנ״ך" },
  { day:"א", month:"טבת", dateText:"", year:"", event:"הושיבו בית דין לגרש הנשים הנכריות מעולי בבל", source:"עזרא י:טז", category:"תנ״ך" },
  { day:"ה", month:"טבת", dateText:"", year:"", event:"בא הפליט לומר ליחזקאל שהוכתה העיר", source:"יחזקאל לג:כא", category:"תנ״ך" },
  { day:"יב", month:"טבת", dateText:"", year:"", event:"יחזקאל מתנבא על מצרים", source:"יחזקאל כט:א", category:"תנ״ך" },
  { day:"א", month:"שבט", dateText:"", year:"", event:"הואיל משה באר את התורה הזאת לאמר", source:"דברים א:ג", category:"תנ״ך" },
  { day:"א", month:"אדר", dateText:"", year:"", event:"יחזקאל התנבא קינה על פרעה", source:"יחזקאל לב:א", category:"תנ״ך" },
  { day:"כז-כה", month:"אדר", dateText:"", year:"", event:"נשא אויל מרודך את ראש יהויכין מבית הכלא", source:"מלכים ב כה:כז ירמיהו נב:לא", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"הקב\"ה דיבר עם משה החודש הזה לכם", source:"", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"הוקם המשכן", source:"שמות מ:יז", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"יחזקאל התנבא על צור", source:"יחזקאל כו:א", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"יחזקאל מתנבא על פורענות מצרים ע\"י נבוכדנצר", source:"יחזקאל כט:יז", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"עזרא וחבריו יוצאים מבבל", source:"עזרא ז:ט", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"עזרא ובית דינו סיימו לגרש הנשים הנכריות מעולי בבל", source:"עזרא י:טז", category:"תנ״ך" },
  { day:"א", month:"ניסן", dateText:"", year:"", event:"שלוחי חזקיהו מתחילים לקדש את בית ה'", source:"ד\"ה ב כט:יז", category:"תנ״ך" },
  { day:"ז", month:"ניסן", dateText:"", year:"", event:"נבואה נגד פרעה ע\"י יחזקאל", source:"יחזקאל ל:כ", category:"תנ״ך" },
  { day:"ח", month:"ניסן", dateText:"", year:"", event:"שלוחי חזקיהו מתחילים לקדש את האולם", source:"ד\"ה ב כט:יז", category:"תנ״ך" },
  { day:"י", month:"ניסן", dateText:"", year:"", event:"העם עלו מן הירדן", source:"יהושע ד:יט", category:"תנ״ך" },
  { day:"יב", month:"ניסן", dateText:"", year:"", event:"עזרא וחבריו נוסעים מנהר אהוא בדרכם לירושלים", source:"עזרא ח:לא", category:"תנ״ך" },
  { day:"טז", month:"ניסן", dateText:"", year:"", event:"שלוחי חזקיהו סיימו לקדש את בית ה'", source:"ד\"ה ב כט:יז", category:"תנ״ך" },
  { day:"כד", month:"ניסן", dateText:"", year:"", event:"דניאל רואה את המלאכים", source:"דניאל י:ד", category:"תנ״ך" },
  { day:"א", month:"אייר", dateText:"", year:"", event:"נצטוה משה למנות את ישראל", source:"במדבר א:א", category:"תנ״ך" },
  { day:"יד", month:"אייר", dateText:"", year:"", event:"החל המן לרדת במדבר", source:"שמות טז:א", category:"תנ״ך" },
  { day:"כ", month:"אייר", dateText:"", year:"", event:"בני ישראל נוסעים בראשונה", source:"שמות י:יא", category:"תנ״ך" },
  { day:"א", month:"סיון", dateText:"", year:"", event:"נבואה נגד פרעה ע\"י יחזקאל", source:"יחזקאל לא:א", category:"תנ״ך" },
  { day:"א", month:"סיון", dateText:"", year:"", event:"בני ישראל באים למדבר סיני", source:"שמות יט:א", category:"תנ״ך" },
  { day:"כג", month:"סיון", dateText:"", year:"", event:"התאספו סופרי אחשוורוש לכתוב אגרות שניות", source:"אסתר", category:"תנ״ך" },
  { day:"ה", month:"תמוז", dateText:"", year:"", event:"נפתחו השמים וראה יחזקאל מראות אלקים", source:"יחזקאל א:א", category:"תנ״ך" },
  { day:"א", month:"אב", dateText:"", year:"", event:"עזרא וחבריו מגיעים לירושלים", source:"עזרא ז:ט", category:"תנ״ך" },
  { day:"י", month:"אב", dateText:"", year:"", event:"באו אנשים מזקני ישראל לדרוש את ה' מאת יחזקאל", source:"יחזקאל כ:א", category:"תנ״ך" },
  { day:"א", month:"אלול", dateText:"", year:"", event:"נבואת חגי", source:"חגי א:א", category:"תנ״ך" },
  { day:"ה", month:"אלול", dateText:"", year:"", event:"נפלה על יחזקאל יד ה' וראה המלאכים", source:"יחזקאל ח:א", category:"תנ״ך" },
  { day:"כד", month:"אלול", dateText:"", year:"", event:"העם באו לעשות מלאכה לבניית בית שני", source:"חגי א:טו", category:"תנ״ך" },
];

/* סדר חודשי השנה העברית (תשרי עד אלול), לניווט/רינדור לפי חודש */
window.EVENTS_MONTHS = ["תשרי", "חשון", "כסלו", "טבת", "שבט", "אדר", "ניסן", "אייר", "סיון", "תמוז", "אב", "אלול"];

/* רשימת הקטגוריות ("לסוג") כפי שהופיעה ברשימת הבחירה המקורית בגיליון */
window.EVENTS_CATEGORIES = ["תנ״ך", "חסידות", "מדינת ישראל", "תולדות ישראל", "שואה", "מדרשים"];

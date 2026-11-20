‏# מדריך פקודות ותפעול: סנכרון, לוגים, קלאודטופ ו-PowerShell

‏מסמך זה מרכז את כל הפקודות השימושיות לתפעול, בדיקת תקינות בלוגים, הפעלה ידנית/מתוזמנת ושמירת שינויים ב-Git עבור הפרויקט `family_vacation_planner`.

---

‏## 1. איך בודקים בלוגים ובשרת שהכול עובד כמו שצריך

‏### א. בדיקת לוגי הטיימר והסנכרון בקלאודטופ (`systemd --user`)
‏הרץ מתוך **הטרמינל של הקלאודטופ**:

- ‏**בדיקת סטטוס הטיימר ומועד ההרצה הבא** (מציגה מתי הטיימר רץ בפעם האחרונה ומתי ירוץ שוב):
```bash
systemctl --user list-timers fvp-elal-sync.timer --no-pager
```

- ‏**צפייה בלוג המלא של הריצות האחרונות** (מציגה את הפלט המדויק של הסקריפט מתוך `journald`):
```bash
journalctl --user -u fvp-elal-sync.service -n 120 --no-pager
```

- ‏**צפייה בקובץ ההתקדמות והקפיצה של מחזור ה-5 ימים** (מציגה את המצב השמור על הדיסק ב-`shard_state.json`):
```bash
cat ~/.local/share/fvp-chrome-sync-profile/shard_state.json
```

‏#### מה מחפשים בתוך הלוג ומה כל שורה אומרת:

1. ‏**בחירת המנה היומית התקינה:**
   - ‏תחפש שורה בפורמט:
     `Selected uniform 5-day rotation shard 2/5: 5 window(s) (2027-02-01 .. 2027-04-12, cycle anchor 2026-11-23).`
   - ‏המשמעות: הסקריפט חילק את השנה ל-`5` מנות, בחר את החלק הבא בתור, וסורק רק `5` חלונות של שבועיים (`20` בקשות רגועות בלבד).

2. ‏**שליפה תקינה מאל על לכל חלון וקבינה:**
   - ‏תחפש שורה של הצלחת טעינת הדף:
     `El Al rbddataclients ready. Checking active calculator airports & running polite sharded scan...`
   - ‏ולאחריה שורות לכל חלון במחלקות `Economy (E)` ו-`Premium (A)`:
     `[01/05] Full-Year Window 06/25 (2027-02-01 .. 2027-02-15) | Economy (E): 284 available flight records`
     `[01/05] Full-Year Window 06/25 (2027-02-01 .. 2027-02-15) | Premium (A): 41 available flight records`
   - ‏המשמעות: נתוני הטיסות החיות התקבלו מהמחשבון של אל על. (אם בחלון חורפי/רחוק יש `0 available flight records` אך לא הופיעה שגיאה, זה תקין — המשמעות היא שלא נפתחו מושבי בונוס באותם תאריכים והשרת ינקה מושבים ישנים שכבר נמכרו).

3. ‏**דחיפה מוצלחת לשרת הפרודקשן (`GCP`) וניקוי טיסות שאזלו:**
   - ‏תחפש בסיום:
     `-> Remote sync batch 1/2 (800 raw -> 391 rows synced)`
     `Synced 742 merged #live flight rows (reconciled 10 slice(s)) to remote server (https://family-trip-planner.duckdns.org).`
   - ‏המשמעות: המידע נשמר בשרת הפרודקשן והטווחים שנסרקו עודכנו כולל מחיקת מושבי בונוס שירדו ל-`0`.

4. ‏**קידום סמן ההתקדמות למנה הבאה:**
   - ‏תחפש את השורה האחרונה:
     `Saved resume state (.../shard_state.json): shard 2/5 complete; next run will resume at shard 3/5.`
   - ‏בתוך `shard_state.json` השדה `"last_completed_shard"` ממוספר מ-`0` עד `4` (כלומר `0` = מנה `1/5`, `4` = מנה `5/5`), ו-`"completed_at"` מציג תאריך השלמה אחרון לכל מנה.

5. ‏**הודעות תקלה שחשוב לזהות:**
   - ‏**הגנת קירור פעילה (לא נשלחו בקשות):**
     `Cooldown guard active: today (...) is before --not-before 2026-11-23. Exiting cleanly with zero network traffic.`
   - ‏**עצירה בטוחה על חסימת קצב (`Reblaze`):**
     `Fail-fast abort: https://www.elal.com/rbddataclients/ did not initialize cleanly within 45s (last seen page: title='' ...)`
     או:
     `! Fail-fast stop on window [...] ... Aborting remaining requests immediately to avoid rate-limit escalation.`
     במצב זה הסקריפט עוצר מיד כדי לא להאריך חסימה, והסמן **לא** זז קדימה (בפעם הבאה ינסה שוב את אותו החלק).
   - ‏**כשל תקשורת לשרת אחרי שהטיסות כבר נמשכו מאל על:**
     מופיעה שורת `Remote upload failed (...)` ומתחתיה פקודת התאוששות עם `--from-file` שמעלה את הקובץ `~/.local/share/fvp-chrome-sync-profile/last_fetched_snapshot.json` בלי לפנות שוב לאל על.

---

‏### ב. בדיקת זמינות ועדכניות המידע בשרת הפרודקשן (`GCP`)
- ‏**בדיקת תקינות השרת (`Health Check`):** הרץ מכל טרמינל כדי לוודא שהאתר והמסד זמינים ומחזירים `status: ok`:
```bash
curl -s "https://family-trip-planner.duckdns.org/api/v1/health" | python3 -m json.tool
```

- ‏**בדיקת טיסות חיות ליעד ולתאריך לדוגמה דרך ה-API:** הרץ מכל טרמינל כדי לראות שהשרת מחזיר טיסות אמיתיות לרומא באפריל `2027` עם תאריך משיכה (`fetched_at`) ותוקף (`expires_at`):
```bash
curl -s "https://family-trip-planner.duckdns.org/api/v1/elal-bonus/availability?destination=FCO&start_date=2027-04-10&end_date=2027-04-20" | python3 -m json.tool | head -n 50
```

- ‏**בדיקה ישירה של המסד ולוג השרת ב-GCP VM** — הרץ מתוך **Google Cloud Shell** כדי לראות כמה שורות חיות (`#live`) שמורות כרגע, מה טווח התאריכים ומתי בוצעה הכתיבה האחרונה, ולוודא שהשירות רץ ללא שגיאות:
```bash
gcloud compute ssh family-vacation-planner-vm \
  --project=family-trip-planner-514920 \
  --zone=me-west1-a \
  --command="sqlite3 /opt/family_vacation_planner/data/vacation_planner.db \"SELECT COUNT(*), MIN(flight_date), MAX(flight_date), MAX(fetched_at) FROM elal_bonus_availability WHERE source_url LIKE '%#live%';\" && sudo journalctl -u family-vacation-planner.service -n 30 --no-pager"
```

---

‏## 2. איך מריצים ידנית את סקריפט הסנכרון

‏### א. ממחשב אישי (`Mac` / `Windows` — מבחוץ ללא צורך בתיקיית הקוד)
- ‏**הרצת המנה היומית הרגועה (`5` חלונות, חלון כרום גלוי, מעלה ישירות לשרת):**
  - ‏בטרמינל של **macOS**:
```bash
curl -fsSL https://family-trip-planner.duckdns.org/sync_elal_to_server.py -o sync_elal_to_server.py && python3 sync_elal_to_server.py --no-local
```
  - ‏ב-**PowerShell ב-Windows** (שימוש ב-`curl.exe` כדי להוריד את הסקריפט ולהריץ):
```powershell
curl.exe -fsSL https://family-trip-planner.duckdns.org/sync_elal_to_server.py -o sync_elal_to_server.py; python sync_elal_to_server.py --no-local
```

- ‏**הרצה ידנית מהירה לתאריך ספציפי בלבד (`4` בקשות סה"כ — הכי בטוח כשרוצים לבדוק מועד מסוים מיד):**
```bash
python3 sync_elal_to_server.py --no-local --target-date 2027-04-18
```

- ‏**דיבאג ושמירת תוצאות לקובץ מקומי:**
```bash
python3 sync_elal_to_server.py --no-local --target-date 2027-04-18 --save-json /tmp/elal_debug.json
```

- ‏**שחזור / העלאה מקובץ גיבוי אם הייתה תקלה בהעלאה לשרת (אפס בקשות לאל על):**
```bash
python3 sync_elal_to_server.py --no-local --from-file ~/.local/share/fvp-chrome-sync-profile/last_fetched_snapshot.json
```

‏### ב. מתוך תיקיית הפרויקט בקלאודטופ
‏הרץ מתוך `/usr/local/google/home/yonibudovsky/family_vacation_planner`:

- ‏**הרצת המנה הבאה בתור עכשיו ידנית (בלי לחכות לשעה המתוזמנת):**
```bash
python3 scripts/sync_elal_to_server.py --shard-count 5 --shard-index auto
```

- ‏**דחיפה של שורות חיות תקפות שכבר קיימות במסד המקומי לשרת הפרודקשן (אפס פניות לאל על):**
```bash
python3 scripts/sync_elal_to_server.py --push-local-db
```

---

‏## 3. איך מפעילים, בודקים ועוצרים את הסקריפט המתוזמן בקלאודטופ

‏כל הפקודות כאן מיועדות להרצה מתוך **הטרמינל של הקלאודטופ**:

- ‏**התקנה והפעלה ראשונית של הטיימר היומי** (כולל תאריך מינימום `--not-before` להגנה מקירור; בתיקייה `/usr/local/google/home/yonibudovsky/family_vacation_planner`):
```bash
bash scripts/install_cloudtop_daily_sync.sh 2026-11-23
```

- ‏**הפעלה מיידית של השירות המתוזמן עכשיו (בדיקת השירות של `systemd`):**
```bash
systemctl --user start fvp-elal-sync.service
```

- ‏**עצירה זמנית או ביטול של הטיימר היומי:**
```bash
systemctl --user disable --now fvp-elal-sync.timer
```

- ‏**הפעלה מחדש של הטיימר לאחר עצירה:**
```bash
systemctl --user enable --now fvp-elal-sync.timer
```

- ‏**עדכון שרת הפרודקשן ב-GCP לאחר שינויי קוד** — הרץ מתוך **Google Cloud Shell** כדי ששרת האתר ימשוך מהמאגר וייטען מחדש:
```bash
gcloud compute ssh family-vacation-planner-vm \
  --project=family-trip-planner-514920 \
  --zone=me-west1-a \
  --command="sudo /usr/local/bin/sync-vacation-planner.sh"
```

---

‏## 4. איך עושים קומיט ודחיפה ב-PowerShell (`Windows`)

‏הרץ מתוך חלון **PowerShell** בתיקיית הפרויקט המקומית שלך:

1. ‏**מעבר לתיקיית הפרויקט ובדיקת מצב הקבצים:**
```powershell
cd C:\path\to\family_vacation_planner
git status
```

2. ‏**סימון הקבצים לקומיט:**
   - ‏לסימון קובץ מסוים או כמה קבצים ספציפיים (הדרך הבטוחה ביותר):
```powershell
git add path\to\file1.py path\to\file2.js
```
   - ‏או סימון כל השינויים במאגר **תוך החרגה של תיקיית `.agents`** (אם קיימת במחשב שלך — לעולם לא לדחוף אותה):
```powershell
git add --all -- ':!.agents'
```

3. ‏**בדיקה אחרונה מה נכנס לקומיט:**
```powershell
git status
```

4. ‏**ביצוע הקומיט ודחיפה אל GitHub (`origin main`):**
```powershell
git commit -m "Describe your change in English or Hebrew"
git push origin main
```

5. ‏**שליפת עדכונים מהענף הראשי לפני שמתחילים לעבוד (אופציונלי ומומלץ):**
```powershell
git pull --rebase origin main
```

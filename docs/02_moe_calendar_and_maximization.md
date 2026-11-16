# 02 — Flight Date Selection Modes & Israeli Ministry of Education Vacation Maximization (`R2`)

**Parent Document**: [`../APPLICATION_PLAN.md`](../APPLICATION_PLAN.md) (§3) | **Index**: [`../README.md`](../README.md)  
**Rubric Coverage**: `RUB-R2.1`, `RUB-R2.2`, `RUB-R2.3`

---

## 1. Date Selection Mode 1: Specific & Flexible Dates (`SPECIFIC_DATES` — `RUB-R2.1`)

Mode 1 supports families who already know their target travel dates or want to search around a specific event (e.g., a family bar mitzvah, wedding, or fixed employer shutdown):

1. **Departure & Return Specification**:
   - **Exact Dates**: Fixed `specific_departure_date` ($D_{\text{dep}}$) and `specific_return_date` ($D_{\text{ret}}$).
   - **Flexible Window ($\pm N$ Days)**: $D_{\text{dep}} \pm k_{\text{dep}}$ and $D_{\text{ret}} \pm k_{\text{ret}}$ where $k \in \{0, 1, 2, 3, 5, 7\}$ (`flex_days_plus_minus`), bounded by `[min_trip_nights, max_trip_nights]`.
2. **Family Passenger Composition & Children's Ages (Framework Optional)**:
   - User enters `adults_count` ($1\text{–}6$) and each child's **age (`child_age_years`, $0\text{–}18$)**, which automatically classifies the passenger for airline pricing (`<2` infant on lap/seat, `2–11` child, `12–15` youth).
   - **Educational Framework (`framework_type`) is Optional**: In Mode 1 (`SPECIFIC_DATES`), specifying each child's educational framework is **optional and not mandatory**. Entering each child's educational framework is only needed when searching by vacations (`Mode 2` or `Mode 3`), where the system uses the child's age to pre-suggest the matching framework (`גילאי 0–3` $\to$ `מעון יום`, `גילאי 3–6` $\to$ `גן ילדים`, `גילאי 6–9` $\to$ `יסודי א'–ג'`, `גילאי 9–12` $\to$ `יסודי ד'–ו'`, `גילאי 12–15` $\to$ `חטיבת ביניים`, `גילאי 15–18` $\to$ `תיכון`) and lets the user confirm or adjust it to match the exact vacation schedule.
3. **Cabin & Schedule Constraints**:
   - Preferred cabins (`ECONOMY`, `PREMIUM`, `BUSINESS`, or mixed cabin), direct flights only vs. max 1 connection ($\ge 90$ min minimum connection time for families), and time-of-day filters (avoiding middle-of-the-night departures with toddlers).
4. **Conditional MoE Calendar Impact Overlay in Mode 1**:
   - If the user has optionally configured children's frameworks, `MoECalendarService` displays an **MoE Impact Summary Badge**; otherwise Mode 1 executes directly with only passenger counts and children's ages.

---

## 2. Date Selection Mode 2: Israeli Ministry of Education (`משרד החינוך`) Multi-Framework Taxonomy (`RUB-R2.2`)

In Mode 2 (`MOE_VACATION_MAXIMIZATION`), each child $c \in \{1..C\}$ in the household profile is parameterized by their exact Israeli Ministry of Education framework, school week structure (`5_DAY` vs. `6_DAY`), and holiday extension (`Nitzanim`):

| Framework Enum (`MoEFrameworkType`) | Hebrew Name | Ages / Grades | Official Summer Start | Criticality Weight ($\omega_c$) | Key Schedule Rules & Divergences |
|---|---|---|---|---|---|
| `DAYCARE_SUPERVISED` | מעונות יום ומשפחתונים בפיקוח | Ages 0–3 | **Aug 9** (ends **Aug 8**) | $\omega = 0.25$ | Operates until Aug 8; minimal year-round holidays (no pre-Pesach week off; only Erev Chag & Chol HaMoed variations). |
| `MUNICIPAL_GAN` | גני ילדים רשמיים (טרום-טרום, טרום, חובה) | Ages 3–6 | **Jul 1** (ends **Jun 30**) | $\omega = 0.25$ | **Isru Chag** (Sukkot, Pesach, Shavuot) & **Lag BaOmer** are **regular school days**. Eligible for **Nitzanim** (`בית הספר של החגים` 5 days in Hanukkah & 5 days pre-Pesach + `בית הספר של החופש הגדול` covering **all of July**, Jul 1–30/31). |
| `ELEMENTARY_1_3` | בית ספר יסודי (כיתות א'–ג') | Grades 1–3 (Ages 6–9) | **Jul 1** (ends **Jun 30**) | $\omega = 0.50$ | **Isru Chag** & **Lag BaOmer** are **regular school days**. Eligible for **Nitzanim** (5 days Hanukkah, 5 days pre-Pesach, and **all of July** Jul 1–30/31). |
| `ELEMENTARY_4_6` | בית ספר יסודי (כיתות ד'–ו') | Grades 4–6 (Ages 9–12) | **Jul 1** (ends **Jun 30**) | $\omega = 0.75$ | **Isru Chag** & **Lag BaOmer** are **regular school days**. Not covered by standard Nitzanim holiday camps. |
| `MIDDLE_SCHOOL_7_9` | חטיבת ביניים (כיתות ז'–ט') | Grades 7–9 (Ages 12–15) | **Jun 21** (ends **Jun 20**; or Jun 18/19 in 2026) | $\omega = 1.00$ | **Hybrid Rule (Circulars `schedule-o` & `0363`)**: Follows the **Elementary schedule during the year** (**Isru Chag Sukkot** & **Lag BaOmer** are **regular learning days**!), **EXCEPT** ends the school year 10 days early on **June 20** alongside High Schools! |
| `HIGH_SCHOOL_10_12` | חטיבה עליונה / תיכון (כיתות י'–י"ב) | Grades 10–12 (Ages 15–18) | **Jun 21** (ends **Jun 20**; or Jun 18/19 in 2026) | $\omega = 1.35$ | Governed by Circulars `0346` (תשפ"ו) & `0364` (תשפ"ז). Ends **June 20**. **Isru Chag Sukkot is an official VACATION day**. **Lag BaOmer** is a **VACATION day in תשפ"ו (May 5, 2026)** and a regular school day in תשפ"ז (May 25, 2027). Supports individual **Bagrut exam blackout dates**. |
| `SPECIAL_ED` | חינוך מיוחד | Eligible ages 3–21 | **Aug 16** (ends **Aug 15**) | $\omega = 0.50$ | Extended year and holiday operation during Sukkot, Hanukkah, Pesach, and July through August 15. |
| `RELIGIOUS_HAREDI` | ממלכתי-דתי / מוסדות חרדיים | All ages | Custom / Bein HaZmanim | Configurable | Supports Fast Day toggles and Bein HaZmanim (`בין הזמנים`: Nissan, Av, Tishrei). |

### Crucial Structural Modifiers
1. **`5_DAY` vs. `6_DAY` School Week (`school_week_days`)**:
   - In a **`5_DAY` (Sun–Thu)** school, every **Friday is a non-school day** ($\psi = 0.0$), enabling Thursday-evening or Friday-morning departures with zero Friday school absence. Moreover, when June 20 falls on Saturday (as in 2026), 6-day Middle/High schools finish on **Friday, June 19, 2026**, whereas 5-day schools finish on **Thursday, June 18, 2026**!
   - In a **`6_DAY` (Sun–Fri)** school, Friday is a short learning day (until ~11:45–12:45, weighted at $\psi = 0.35$).
2. **Nitzanim Holiday & Summer Camps (`holiday_extension_mode` & `treat_camp_as_vacation`)**:
   - **Nitzanim in Holidays (`בית הספר של החגים`)**: Operates **5 Sun–Thu days in Hanukkah** and **5 Sun–Thu days in the pre-Seder week of Pesach** (08:00–13:00, or until 16:00 with Tzaharon) for `MUNICIPAL_GAN` and `ELEMENTARY_1_3`.
   - **School of the Summer Vacation (`בית הספר של החופש הגדול`)**: Covers **all of July (July 1–30/31, ~22 Sun–Thu operating days)** for `MUNICIPAL_GAN` and `ELEMENTARY_1_3`.
   - Families can toggle `treat_camp_as_vacation`:
     - `True`: Treat Nitzanim days as available for travel abroad (since zero formal school curriculum is missed).
     - `False`: Treat Nitzanim days as covered childcare workdays and prioritize **Uncovered Vacation Windows** (e.g., the second half of Pesach after Nitzanim ends, or August 1–31) when parents have no childcare anyway!

---

## 2b. Date Selection Mode 3: Specific Holiday / Vacation & Year Maximizer (`HOLIDAY_DIRECT_INTENT`)

Mode 3 (`HOLIDAY_DIRECT_INTENT`) provides a focused, structured mode for planning around a **single chosen holiday or vacation period in a specific year** (for example: selecting **Holiday = `חופשת פסח`** and **Year = `2027`** to maximize vacation days and find bonus ticket options, or selecting any other holiday/vacation such as `סוכות`, `גשר כיפור–סוכות`, `חנוכה`, `ראש השנה`, `פורים`, `שבועות`, `יום העצמאות`, `החופש הגדול - סוף יוני`, `יולי`, or `אוגוסט`):

1. **Structured Selection Controls**:
   - **Dropdown 1 — בחר חג / חופשה (`direct_holiday_code`)**: `פסח`, `סוכות`, `גשר כיפור–סוכות`, `חנוכה`, `פורים`, `שבועות`, `ראש השנה`, `יום העצמאות`, `החופש הגדול (20–30 ביוני)`, `יולי`, `אוגוסט`.
   - **Dropdown 2 — בחר שנה (`direct_target_year`)**: `2026`, `2027`, `2028`, ... (automatically backed by the Annual MoE Calendar Auto-Updater).
   - **Sliders — מקסום ימי החופש (`min_trip_nights`–`max_trip_nights`, `max_bridge_days_shift`)**: Desired trip length (e.g., 5–8 nights) and allowed bridge days ($\pm 0..3$ ימי גשר) around that holiday.
2. **Automated Holiday Window Maximization & Bonus Scan**:
   - Resolves `(direct_holiday_code, direct_target_year)` via `MoECalendarService` to the exact holiday dates for the family's children in that year (for example, `PESACH` + `2027` $\to$ `Tue, Apr 13 – Wed, Apr 28, 2027`, automatically highlighting the Nitzanim week `Apr 13–19` vs. the uncovered week `Apr 20–28`).
   - Generates all candidate trip sub-windows (`4–10` nights, plus configurable $\pm 0..3$ bridge days `Apr 10 – May 1, 2027`) to maximize total vacation days per parent PTO day (`PER`) and minimize school absences (`SAP`), queries `https://www.elal.com/rbddataclients/` and configured multi-club passenger wallets, and presents ranked vacation options for that specific holiday.

---

## 3. Verified MoE Holiday Calendars: תשפ"ו (2025–2026) & תשפ"ז (2026–2027)

Full tables for both **תשפ"ו (2025–2026, Circulars `schedule-o` & `0346`)** and **תשפ"ז (2026–2027, Circulars `0363` & `0364`)** are embedded in [`APPLICATION_PLAN.md` §3.3](../APPLICATION_PLAN.md#33-authoritative-moe-holiday-calendars-תשפו-20252026--תשפז-20262027). Key cross-year and cross-framework highlights verified by the engine:

1. **The Yom Kippur–Sukkot Bridge Reform & Isru Chag Sukkot Divergence**:
   - In both **תשפ"ו** (Oct 3–5, 2025) and **תשפ"ז** (Sep 22–24, 2026), all MoE frameworks enjoy a continuous 14–15 day vacation spanning Yom Kippur, the official 3-day MoE bridge (`גשר כיפור–סוכות`), and Sukkot.
   - In exchange for those 3 bridge days, **Isru Chag Sukkot** (Wed, Oct 15, 2025 in תשפ"ו; Sun, Oct 4, 2026 in תשפ"ז) is a **regular learning day for `MUNICIPAL_GAN`, `ELEMENTARY_1_3`, `ELEMENTARY_4_6`, and `MIDDLE_SCHOOL_7_9`**, while remaining an **official vacation day for `HIGH_SCHOOL_10_12`**.
2. **Ben Gurion Airport (`TLV`) Yom Kippur Total Shutdown**:
   - Israeli airspace and `TLV` close completely on Yom Kippur (`Oct 1, 2025 ~13:00` to `Oct 2, 2025 ~22:30` in תשפ"ו; `Sep 20, 2026 ~13:00` to `Sep 21, 2026 ~22:30` in תשפ"ז). While children are on continuous vacation, `MoECalendarService` blocks flight departures/landings at `TLV` during the shutdown window, automatically proposing departures either on/before Erev Yom Kippur morning or from Motzei Yom Kippur / the next morning onward.
3. **Lag BaOmer (`ל"ג בעומר`) Year-Over-Year Difference**:
   - In **תשפ"ו** (`Tue, May 5, 2026`): Vacation day **only for `HIGH_SCHOOL_10_12`**; regular school day for `K–9`.
   - In **תשפ"ז** (`Tue, May 25, 2027`): **Regular school day across ALL frameworks (`K–12`)**.
4. **The June 20 vs. June 30 Summer Break Arbitrage Window**:
   - `MIDDLE_SCHOOL_7_9` and `HIGH_SCHOOL_10_12` start summer vacation on **June 20** (or **Thu Jun 18 / Fri Jun 19, 2026** when June 20 is Saturday), whereas `MUNICIPAL_GAN` and `ELEMENTARY_1_6` continue until **June 30** (mostly end-of-year ceremonies and light days weighted at $\psi = 0.50$).

---

## 4. 3-Layer Calendar Data Architecture, Annual Auto-Updater & JSON Schema

The complete JSON Schema (`MinistryOfEducationSchoolYearCalendar`, Draft 2020-12) is provided in [`APPLICATION_PLAN.md` §3.4](../APPLICATION_PLAN.md#34-3-layer-calendar-data-architecture-annual-auto-updater--json-schema) and powers the **Annually Self-Updating 3-Layer Calendar Repository (`MoECalendarAutoUpdaterService`)**:
- **Layer 1 (Bundled & Auto-Synced Official MoE Circulars)**: Pre-seeded with `calendars/moe_5786_2025_2026.json` and `calendars/moe_5787_2026_2027.json`. A scheduled `APScheduler` job (and `POST /api/v1/moe-calendar/sync/{school_year}`) automatically checks the Ministry of Education Director General Circulars (`חוזרי מנכ"ל משרד החינוך`, `apps.education.gov.il/mankal` / `gov.il`) every year to ingest newly published holiday circulars (`AUTO_SYNCED_CIRCULAR`).
- **Layer 2 (Deterministic Hebrew-to-Gregorian Statutory Rule Projector)**: Because flights and El Al bonus tickets open 11–12 months in advance (often before the next school year's circular is published), `HebrewCalendarRuleProjector` uses `pyluach` / `hdate` + `Hebcal REST API (i=on)` and the invariant MoE statutory rules to automatically generate the full vacation calendar for **any future year (`2027–2028`, `2028–2029`, ...)** (`HEBREW_RULE_PROJECTED`), seamlessly reconciling with Layer 1 once the official circular is released.
- **Layer 3 (Municipal Nitzanim Override & `.ics` Export)**: Municipal Nitzanim date override UI + `.ics` calendar export (`USER_MUNICIPAL_OVERRIDE`).

---

## 5. Formal Vacation Utilization Maximization Algorithm (`RUB-R2.3`)

Given a household profile with children $c \in \{1..C\}$, `VacationMaximizerEngine` executes a 4-stage pipeline:

1. **Daily Vectorization**: Computes parent PTO cost $P(d) \in \{0.0, 0.5, 1.0\}$ and per-child state $S_c(d)$ with absence penalty weight $\psi(S_c(d)) \in \{0.0, 0.15, 0.35, 0.50, 0.75, 1.00, \infty\}$.
2. **Multi-Child Set Construction**:
   - **Strict Intersection ($\mathcal{I}$)**: $\mathcal{I} = \{ d \mid \forall c,\; S_c(d) = \text{VACATION} \}$
   - **Camp-Adjusted Intersection ($\mathcal{I}_{\text{camp}}$)**: $\mathcal{I}_{\text{camp}} = \{ d \mid \forall c,\; S_c(d) \in \{\text{VACATION}, \text{CAMP\_OPTIONAL}\} \}$
   - **Framework-Delta Union ($\mathcal{U}$)**: $\mathcal{U} = \{ d \mid \exists c,\; S_c(d) \in \{\text{VACATION}, \text{CAMP\_OPTIONAL}\} \}$
3. **Bridge-Day ("Yemei Gesher") Candidate Window Expansion**:
   - Merges clusters separated by $\le B_{\max}$ days ($B_{\max} = 3$) and shifts boundaries $d_{\text{dep}} \in [a - 3, b]$, $d_{\text{ret}} \in [a, b + 3]$.
4. **Explicit Mathematical Scoring Formulas (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`)**:
   - **PTO Efficiency Ratio (`PER`)**:
     $$\text{PER}(W) = \frac{D_{\text{total}}(W)}{\max(\text{PTO}(W),\; 0.5)}$$
   - **School Absence Penalty (`SAP`)**:
     $$\text{SAP}(W) = \frac{1}{C} \sum_{c=1}^{C} \sum_{d \in W} \omega_c \cdot \psi(S_c(d))$$
   - **Childcare Coverage Gain (`CCG`)**:
     $$\text{CCG}(W) = \frac{1}{C \cdot D_{\text{total}}(W)} \sum_{c=1}^{C} \sum_{d \in W} \mathbb{I}\big(S_c(d) = \text{VACATION} \lor \text{is\_weekend}(d)\big)$$
   - **Vacation Utilization Score (`VUS` $\in [0, 100]$)**:
     $$\text{VUS}(W) = \text{clamp}_{[0,100]}\!\left( 100 \cdot \left[ \alpha \cdot \min\!\left(\frac{\text{PER}(W)}{4.0},\; 1.0\right) + \beta \cdot \text{CCG}(W) - \gamma \cdot \frac{\text{SAP}(W)}{D_{\text{total}}(W)} \right] \right)$$
   - **Flight / Bonus Value Score (`FBVS` $\in [0, 100]$)** & **Combined Trip Optimization Score (`CTOS` $\in [0, 100]$)**:
     $$\text{CTOS}(W, F) = w_{\text{calendar}} \cdot \text{VUS}(W) + w_{\text{flight}} \cdot \text{FBVS}(F) \qquad (w_{\text{calendar}} = 0.55,\; w_{\text{flight}} = 0.45)$$

---

## 6. Six Worked Numerical Israeli Holiday Optimization Examples

See [`APPLICATION_PLAN.md` §3.6](../APPLICATION_PLAN.md#36-six-worked-numerical-optimization-examples-across-israeli-holidays) for the full numerical table evaluating:
1. **Ex 1 — Kippur–Sukkot Mega-Bridge (`Sep 22 – Oct 3, 2026`)**: 12 days, $\text{SAP} = 0.00$, $\text{CCG} = 1.00$, avoiding `TLV` Yom Kippur closure.
2. **Ex 2 — Hanukkah Post-Nitzanim Shift (`Dec 10 – Dec 14, 2026`)**: Shifting return by 1 bridge day (`Mon Dec 14`) unlocks `2+` Economy & `2+` Business bonus seats on El Al (`FBVS = 92`).
3. **Ex 3 — Purim Long-Weekend Bridge (`Mar 23 – Mar 27, 2027`)**: Adding 1 bridge day (`Thu Mar 25`) turns a 2-day Purim holiday into a 5-day family vacation with only 1 school day missed ($\text{SAP} = 0.69$).
4. **Ex 4 — Pesach Pre-Holiday Shoulder Bridge (`Apr 11 – Apr 18, 2027` & `Apr 19 – Apr 26, 2027`)**: Departing 2 days early unlocks `LY381` Rome bonus seats saving `$2,100` (`CTOS = 95.0`), while the second half of Pesach (`Apr 19–26`) achieves $\text{PER} = 4.00$ and $\text{VUS} = 100.0$ during the post-Nitzanim uncovered week.
5. **Ex 5 — Shavuot Extended Weekend (`Jun 9 – Jun 12, 2027`)**: 4-day trip for `1.5` parent PTO days ($\text{PER} = 2.67$) and `1` school day missed.
6. **Ex 6 — June 20–30 Inter-Framework Arbitrage (`Jun 21 – Jun 28, 2027`)**: Middle/High schoolers miss `0` days (`Summer started Jun 20`) while airfares are 35–50% lower than July 1+.

# 04 — BiDi/RTL UX/UI Design, Wireframes & End-to-End Family Workflows (`R2`, `R3`)

**Parent Document**: [`../APPLICATION_PLAN.md`](../APPLICATION_PLAN.md) (§5) | **Index**: [`../README.md`](../README.md)  
**Rubric Coverage**: `RUB-R2.1`, `RUB-R2.2`, `RUB-R3.1`, `RUB-R3.2`, `RUB-R3.3`

---

## 1. 4-Zone BiDi/RTL Dashboard Architecture

The frontend (`React 19 + TypeScript + Vite + Tailwind CSS v4`) renders natively in Hebrew Right-to-Left (`<div dir="rtl" lang="he">`) with an instant Hebrew/English toggle:

```text
+--------------------------------------------------------------------------------------------------+
| [Zone 1: Top Navigation & Active Family Profile Summary Bar]                                     |
| 👨‍👩‍👧‍👦 משפחת בודובסקי (2 מבוגרים, 3 ילדים: גן חובה+ניצנים | כיתה ד' יסודי | כיתה ח' חט"ב 5 ימים)       |
| ✈️ יתרת מתמיד: 185,000 נק' + שובר FlyCard | 🏖️ תקציב חופש הורים: 14 ימים | [⚙️ עריכת פרופיל משפחה] |
+--------------------------------------------------------------------------------------------------+
| [Zone 2: Multi-Axis Search & Mode Control Panel (`SearchControlPanel`)]                          |
| +----------------------------------------------+ +---------------------------------------------+ |
| | 📅 מצב בחירת תאריכים (Date Selection Mode)   | | 🛫 מצב חברות תעופה ומועדונים (Airline Mode) | |
| | ( ) Mode 1: תאריכים ספציפיים (Specific Dates)| | (*) Mode 1: מיקוד באל על (Focus on El Al)   | |
| | ( ) Mode 2: מקסום חופשות שנתי (MoE Max)      | |     [x] 🎯 חיפוש כרטיסי בונוס (Bonus Tickets| |
| | (*) Mode 3: חג/חופשה ספציפיים למקסום החופש   | |         via elal.com/rbddataclients/)       | |
| |     [חג: חופשת פסח ▾] [שנה: 2027 ▾] [גשר ±2]| | ( ) Mode 2: כל החברות + ריבוי מועדונים      | |
| +----------------------------------------------+ +---------------------------------------------+ |
| [Contextual Filters for Active Date Mode + Active Airline Mode]                [🔍 חפש חופשות]   |
+--------------------------------------------------------------------------------------------------+
| [Zone 3: Multi-Child MoE Vacation & Bridge-Day Interactive Timeline Heatmap]                     |
| Stacked horizontal Gantt track per child framework + Parent PTO strip + El Al Bonus Seat Badges  |
+--------------------------------------------------------------------------------------------------+
| [Zone 4: Ranked Vacation Proposals Grid & Side-by-Side Comparison Modal]                         |
| [Tab 1: 🌟 חופשות מבוססות כרטיסי בונוס אל על (Bonus Ticket Vacation Options)] [Tab 2: כל הטיסות] |
+--------------------------------------------------------------------------------------------------+
```

---

## 2. Workflow 1: Household & MoE Educational Framework Configuration (`FamilyProfileDrawer`)

1. **Adult & Parent PTO Policy**:
   - Configures `adults_count` ($1\text{–}6$), workweek (`SUN_THU` vs. `SUN_FRI`), Erev Chag PTO weight (`0.0`, `0.5`, `1.0`), Chol HaMoed PTO weight (`0.5`, `1.0`), `annual_pto_budget`, and `max_pto_per_trip`.
2. **Per-Child Age & Optional Israeli MoE Framework Assignment (`ChildFramework[]`)**:
   - For each child, the user enters the **child's age (`child_age_years`, 0–18)** (used for airline infant/child/youth pricing and to auto-suggest a default educational framework).
   - **Optional Educational Framework Selector (Active When Searching by Vacations — Modes 2 & 3)**:
     - When searching by specific dates (`Mode 1`), selecting an educational framework is **completely optional** (not mandatory).
     - When searching by children's vacations (`Mode 2` or `Mode 3`), the user selects (or confirms the age-based suggestion for) each child's framework from all 8 `MoEFrameworkType` options (`DAYCARE_SUPERVISED`, `MUNICIPAL_GAN`, `ELEMENTARY_1_3`, `ELEMENTARY_4_6`, `MIDDLE_SCHOOL_7_9`, `HIGH_SCHOOL_10_12`, `SPECIAL_ED`, `RELIGIOUS_HAREDI`), along with `school_week_days` (`5` vs. `6`) and `holiday_extension_mode` (`NONE`, `NITZANIM_CHAGIM_ONLY`, `NITZANIM_FULL_WITH_JULY`) so the system matches the exact vacation dates for that family.
3. **Per-Passenger & Multi-Club Loyalty Wallets (`PassengerLoyaltyWallet[]`)**:
   - Allows entering available points **per individual passenger and across multiple loyalty programs** (`ELAL_MATMID`, `BRITISH_AVIOS`, `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`, `QANTAS_FREQUENT_FLYER`, `AEGEAN_MILES_BONUS`, `AMEX_MR_ISRAEL`, `ISRAELI_CC_TRAVEL_POINTS`), along with per-passenger `has_club_credit_card` (`FlyCard` / `FlyCard Premium`), `companion_vouchers_count`, `can_pool_with_family`, and `transfer_ratio_to_airline`.

---

## 3. Workflow 2: Orthogonal 3-Mode Date & Airline Switching (`SearchControlPanel`)

### 3.1 Left Axis — Date Selection Mode (`DateModeSelector` — `R2`)
- **Mode 1 (`SPECIFIC_DATES`)**: Displays exact departure/return date pickers (with overlaid Hebrew dates and MoE holiday badges), flexibility selector ($\pm 0, \pm 1, \pm 2, \pm 3, \pm 5, \pm 7$ days), and an inline **Live MoE Impact Preview Badge** showing parent PTO days and per-child school days missed for the chosen dates.
- **Mode 2 (`MOE_VACATION_MAXIMIZATION`)**: Displays School Year selector (`תשפ"ו 2025–2026`, `תשפ"ז 2026–2027`, `תשפ"ח 2027–2028+` with **Annual Auto-Updater status badge**), multi-select holiday chips (`ראש השנה`, `כיפור + גשר + סוכות`, `חנוכה`, `פורים`, `פסח`, `עצמאות / שבועות`, `חלון 20–30 ביוני חט"ב/תיכון`, `יולי / אוגוסט`), min/max nights slider, Bridge-Day ("Yemei Gesher") shift slider ($\pm 0..3$ days), and overlap policy (`STRICT_ALL_CHILDREN_OFF`, `CAMP_ADJUSTED_INTERSECTION`, `MAXIMIZE_EFFICIENCY_SCORE`).
- **Mode 3 (`HOLIDAY_DIRECT_INTENT` — חיפוש ממוקד לפי חג/חופשה ספציפיים ושנה למקסום ימי החופש)**:
  - Structured dropdown/pill selection of a **Specific Holiday/Vacation (`direct_holiday_code`)** (such as `חופשת פסח`, `סוכות`, `גשר כיפור–סוכות`, `חנוכה`, `ראש השנה`, `פורים`, `שבועות`, `יום העצמאות`, `החופש הגדול - יוני/יולי/אוגוסט`) and **Target Year (`direct_target_year`)** (such as `2027`), plus desired nights and bridge-day tolerance ($\pm 0..3$ ימי גשר).
  - Automatically resolves that holiday's exact Ministry of Education dates for the chosen year, computes all optimal sub-windows and bridge combinations to maximize vacation days relative to parent PTO and school schedules, and scans `https://www.elal.com/rbddataclients/` & multi-club passenger wallets for the best vacation options.

### 3.2 Right Axis — Airline Selection Mode (`AirlineModeSelector` — `R3`)
- **Mode 1 (`EL_AL_ONLY`)**: Locks carrier to El Al (`LY` + optional Sun d'Or `2U`) and expands `ElAlBonusSearchSubPanel`:
  - Master toggle: `[x] חיפוש כרטיסי בונוס באתר https://www.elal.com/rbddataclients/`.
  - Destination scope: **"גלה יעדים עם כרטיסי בונוס פנויים" (`ANYWHERE`)** or multi-select destinations (with automatic metro expansion `NYC`$\to$`JFK`/`EWR`, `LON`$\to$`LHR`/`LTN`).
  - Cabin checkboxes (`Economy E/X/U`, `Premium P/A/R`, `Business I/W`) and family fulfillment toggle (`ALLOW_HYBRID_BONUS_PLUS_CASH`).
- **Mode 2 (`ALL_AIRLINES`)**: Enables multi-carrier search with Direct/1-Stop filter, LCC/Full-Service toggles, and the **Family Baggage Normalizer**.

---

## 4. Workflow 3: Inspecting & Comparing Bonus Ticket Vacation Options (`BonusVacationOptionCard` & `BonusVacationComparisonTable` — `RUB-R3.3`)

The complete ASCII wireframe for `BonusVacationOptionCard` is shown in [`APPLICATION_PLAN.md` §5.2](../APPLICATION_PLAN.md#52-flagship-bonusvacationoptioncard--bonusvacationcomparisontable). Every card presents four integrated sections:
1. **Header & Combined Score (`CTOS`)**: Destination, dates, duration, and `CTOS` / `VUS` / `FBVS` badges.
2. **Live `https://www.elal.com/rbddataclients/` Award Breakdown**: Outbound and inbound flight numbers (`LY381` / `LY384`), departure/arrival times, and exact per-cabin Classic Award seat counts (`0`, `1`, `2+`) across Economy (`E`/`X`/`U`), Premium (`P`/`A`/`R`), and Business (`I`/`W`).
3. **Recommended Family Ticket Allocation (5 Strategies)**: Shows the exact per-passenger ticket breakdown on the same flight (e.g., `2x Economy Bonus + 2x Premium/Business Bonus + 1x Commercial Cash`), total Matmid points + port taxes + supplemental cash fare, net USD/ILS cash saved vs. 100% cash benchmark, and Cents-Per-Point (`CPP`).
4. **Day-by-Day Multi-Child MoE & Parent PTO Impact Strip**: Visual calendar matrix showing for each day of the trip whether parents use PTO (`0.0`, `0.5`, `1.0`) and whether each child is on official MoE vacation (`🏖️`), Nitzanim camp (`🟡`), weekend (`🟢`), or bridge day missed (`❌`), plus action buttons linking directly to `https://www.elal.com/rbddataclients/` and `elal.com`.

### Side-by-Side Comparison Matrix (`BonusVacationComparisonTable`)
| Metric | Option A: Rome (`FCO`) — Pre-Pesach Bridge | Option B: Athens (`ATH`) — Hanukkah | Option C: Madrid (`MAD`) — June 20–30 Arbitrage |
|---|---|---|---|
| **Dates & Duration** | Apr 11 – Apr 18, 2027 (7 nights / 8 days) | Dec 6 – Dec 11, 2026 (5 nights / 6 days) | Jun 21 – Jun 28, 2027 (7 nights / 8 days) |
| **El Al Flights (`rbddataclients`)** | `LY381` / `LY384` | `LY541` / `LY544` | `LY395` / `LY398` |
| **Bonus Seats (`Out` / `In`)** | Out: `2+ Econ, 2+ Prem` / In: `2+ Econ, 1 Prem, 2+ Biz` | Out: `2+ Econ, 2+ Biz` / In: `2+ Econ, 2+ Biz` | Out: `2+ Econ, 2+ Prem` / In: `2+ Econ, 2+ Prem` |
| **Family Strategy (5 Pax)** | `HYBRID_BONUS_PLUS_CASH` (4 Bonus + 1 Cash) | `HYBRID_BONUS_PLUS_CASH` (4 Bonus + 1 Cash) | `HYBRID_BONUS_PLUS_CASH` (4 Bonus + 1 Cash) |
| **Matmid Points + Cash Out-of-Pocket** | `142,000 pts` + `$850` (`$390` tax + `$460` cash ticket) | `98,000 pts` + `$610` (`$310` tax + `$300` cash ticket) | `150,000 pts` + `$940` (`$410` tax + `$530` cash ticket) |
| **Net Cash Saved vs. 100% Cash** | **`$2,100` saved** (`CPP = 1.48¢`) | **`$1,490` saved** (`CPP = 1.52¢`) | **`$2,360` saved** (`CPP = 1.57¢`) |
| **Parent PTO & `PER` Leverage** | `2.0 PTO` during Chol HaMoed (`PER = 4.0x`) | `4.0 PTO` (`PER = 1.5x`) | `6.0 PTO` (`PER = 1.33x`) |
| **MoE School Days Missed per Child** | Gan: `0` (Nitzanim) \| Gr.4: `2` \| Gr.8: `2` | Gan: `0` \| Gr.4: `0` \| Gr.8: `0` | Gan: `5` \| Gr.4: `5` \| Gr.8: **`0` (Off Jun 20!)** |
| **Combined Score (`CTOS`)** | **95 / 100** | **91 / 100** | **82 / 100** |

---

## 5. Mobile-First Responsive Web & PWA Adaptation (`360px–430px` Mobile, `768px` Tablet, `1280px+` Desktop)

Because parents frequently plan and review vacation options from their smartphones, the Web App implements a **Mobile-First Responsive RTL Architecture** + **Installable PWA (`manifest.webmanifest`)**:

| Viewport Breakpoint | Layout & Navigation Adaptation | Component-Specific Mobile UX Optimizations |
|---|---|---|
| **Mobile (`< 640px`, e.g., iPhone / Android `360px–430px`)** | • **Sticky Top Compact Bar**: Shows active household badge, Matmid points pill, and quick-filter chip.<br>• **Bottom Navigation Bar (`BottomNav`)**: 4 thumb-friendly tabs (`🔍 חיפוש`, `📅 לוח חופשות`, `🌟 הצעות (${count})`, `👨‍👩‍👧‍👦 פרופיל`).<br>• **Slide-Up Bottom Sheets**: `FamilyProfileDrawer` and `SearchControlPanel` open as native-feeling touch bottom sheets with `44px × 44px` minimum tap targets. | • **`MultiChildCalendarHeatmap`**: Uses a sticky right-hand column (`position: sticky; inset-inline-start: 0` in RTL) for child names (`נועה`, `עידו`, `מאיה`) with smooth horizontal touch-scrolling and holiday quick-jump pills.<br>• **`BonusVacationOptionCard`**: Stacks outbound (`🛫 הלוך`) and inbound (`🛬 חזור`) legs vertically; collapses the day-by-day MoE absence table into an expandable accordion (`הצג פירוט יומי לכל ילד ▾`).<br>• **`BonusVacationComparisonModal`**: Renders as a horizontal swipeable snap-carousel (`scroll-snap-type: x mandatory`) with a pinned metric label column. |
| **Tablet (`640px – 1024px`)** | • 2-column adaptive grid with collapsible filter drawer and docked comparison tray. | • Side-by-side outbound/inbound flight legs inside `BonusVacationOptionCard`; 2-up comparison view. |
| **Desktop (`> 1024px`)** | • Full 4-Zone dashboard visible simultaneously with side-by-side Dual-Axis mode selectors and 3-column comparison table. | • Full school-year Gantt heatmap and expanded MoE daily impact strip visible without scrolling. |

### Mobile Wireframe (`390px` Smartphone Viewport in RTL)
```text
+--------------------------------------------+
| ✈️ חופשה משפחתית | 🌟 185K נק' | [⚙️ פרופיל]|
+--------------------------------------------+
| [📅 סביב חופשות משה"ח ▾] [🛫 אל על+בונוס ▾]|
| חגים: [פסח ✓] [חנוכה ✓] [20-30 יוני ✓]     |
| גשר: [±2 ימים] | 5 נוסעים   [🔍 חפש (12)] |
+--------------------------------------------+
| 🏆 #1 רומא (FCO) • פסח + גשר   [CTOS: 95]  |
| 📅 א' 11/4 - א' 18/4 (7 לילות)             |
| ------------------------------------------ |
| 🛫 הלוך LY381 (07:15): 2+ תיירים | 2+ פרימ'|
| 🛬 חזור LY384 (21:45): 2+ תיירים | 2+ עסקים|
| ------------------------------------------ |
| 🧩 2x בונוס תיירים + 2x פרימיום + 1x מזומן |
| 💰 142,000 נק' + $850 (חיסכון: $2,100!)    |
| 🏫 הורים: 2 ימי חופש | ניצנים: מכסה גן     |
| [פירוט יומי לילדים ▾] [🔗 אמת ב-אל על] [⚖️] |
+--------------------------------------------+
| [🔍 חיפוש] [📅 לוח משה"ח] [🌟 תוצאות] [⚖️(2)]|
+--------------------------------------------+
```

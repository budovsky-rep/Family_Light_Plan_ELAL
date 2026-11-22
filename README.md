# Israeli Family Vacation & El Al Bonus Ticket Planner (`family_vacation_planner`)

> **Pre-Implementation Application Plan (`R1`, `R2`, `R3`, `AC-1..3`)**  
> A practical, personal-use application plan designed *before starting the code build* to help Israeli families find optimal flights either on **specific/flexible dates (Mode 1)** or **around children's vacations across Israeli Ministry of Education (`משרד החינוך`) educational frameworks to maximize vacation utilization (Mode 2)**, with an orthogonal switch between **focusing on El Al flights (`EL_AL_ONLY`, including searching Classic Award bonus tickets at `https://www.elal.com/rbddataclients/` and synthesizing complete family vacation options using bonus tickets)** and **allowing all airlines (`ALL_AIRLINES`)**.

---

## 1. Executive Summary

Planning a family vacation from Israel (`TLV`) when children attend different **Ministry of Education (`משרד החינוך`)** frameworks—such as Supervised Daycare (`מעון יום`, ending Aug 8), Municipal Kindergarten (`גן ילדים`, ending Jun 30 + **Nitzanim** camps), Lower Elementary (`כיתות א'–ג'`, ending Jun 30 + **Nitzanim**), Upper Elementary (`כיתות ד'–ו'`, ending Jun 30), Middle School (`חטיבת ביניים ז'–ט'`, ending **Jun 20**), and High School (`תיכון י'–י"ב`, ending **Jun 20** with Bagrut blackouts)—requires balancing parent PTO days, school absences, prepaid Nitzanim childcare coverage, commercial airfares, and scarce El Al Matmid bonus seat inventory.

This repository contains the complete, self-contained **Pre-Implementation Application Plan** across seven structured documents.

---

## 2. Architecture & Multi-Mode Matrix Overview

| Axis / Dimension | Mode 1 | Mode 2 | Mode 3 (Specific Holiday & Year Maximizer) |
|---|---|---|---|
| **Axis 1: Flight Date Selection (`R2`)** | **`SPECIFIC_DATES` (בחירת תאריכים ספציפיים)**<br>• Exact departure & return dates ($D_{\text{dep}}, D_{\text{ret}}$)<br>• Flexible window search ($\pm N$ days, $N \in \{0..7\}$)<br>• Full family passenger composition<br>• Automatic MoE school/PTO impact overlay badge | **`MOE_VACATION_MAXIMIZATION` (סביב חופשות משרד החינוך — סריקה שנתית)**<br>• Multi-child profile across all **8 Israeli MoE frameworks**, `5_DAY` vs. `6_DAY` week, & **Nitzanim**<br>• **Annual Auto-Updater** (`תשפ"ו`, `תשפ"ז`, `תשפ"ח+` via MoE Circulars + `pyluach`/`Hebcal` statutory rules)<br>• Set operations ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$) + $\pm 3$-day **"Yemei Gesher"** & `VUS`/`CTOS` scoring | **`HOLIDAY_DIRECT_INTENT` (חיפוש לפי חג/חופשה ספציפיים ושנה למקסום ימי החופש)**<br>• Structured selection of a **Specific Holiday/Vacation** (`פסח`, `סוכות`, `חנוכה`, `פורים`, `שבועות`, `ראש השנה`, `יולי`, `אוגוסט`, ...) + **Target Year** (`2026`, `2027`, `2028`...)<br>• Auto-resolves that holiday's exact dates for the chosen year, optimizes sub-windows & bridge days to maximize vacation utilization, and finds matching bonus/commercial flights |
| **Axis 2: Airline & Loyalty Selection (`R3`)** | **`EL_AL_ONLY` (מיקוד בטיסות אל על + כרטיסי בונוס)**<br>• Filters to El Al (`LY`) & Sun d'Or (`LY`/`2U`) with Shabbat constraints<br>• Queries Classic Award bonus tickets at **`https://www.elal.com/rbddataclients/`** (`E`/`X`/`U`, `P`/`A`/`R`, `I`/`W`)<br>• **Per-Passenger & Multi-Club Point Wallets** (`passenger_loyalty_wallets`) + **6 Family Bonus Fulfillment Strategies** | **`ALL_AIRLINES` (כל חברות התעופה + ריבוי מועדונים)**<br>• Aggregates legacy and low-cost carriers (`LY`, `6H`, `IZ`, `W6`, `FR`, `U2`, `A3`, `LH`, `BA`, `AF`, `UA`, `DL`, `FZ`, etc.)<br>• Backed by 3-tier flight APIs (`fast-flights`/`fli`, `SerpApi Google Flights`, `Duffel API`) + **Family Baggage Normalizer**<br>• Supports multi-club point redemptions (`ELAL_MATMID`, `BRITISH_AVIOS`, `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`, `AMEX_MR_ISRAEL`, etc.) | *Combines automatically with Mode 1 (`EL_AL_ONLY` bonus scan) or Multi-Club mode based on each passenger's available point wallets* |

---

## 3. Deliverable Document Map & Navigation Index

| Document Path | Primary Focus | Key Contents |
|---|---|---|
| **[`APPLICATION_PLAN.md`](./APPLICATION_PLAN.md)** | **Master Consolidated End-to-End Application Plan** | Complete, self-contained specification covering `R1`, `R2`, `R3`, 7-table SQLite DDL, Pydantic/TypeScript models, REST APIs, MoE `תשפ"ו`–`תשפ"ז` calendars, `VUS`/`CTOS` math + 6 worked examples, `rbddataclients` spec, UI wireframes, 5-phase roadmap, and 9-item verification rubric. |
| **[`docs/01_architecture_and_tech_stack.md`](./docs/01_architecture_and_tech_stack.md)** | **R1: Architecture, Tech Stack, Database DDL & APIs** | Mobile-responsive Web App (PWA-ready) + CLI rationale (`Python 3.13 + FastAPI + SQLite 3.53 WAL + Playwright` & `React 19 + TS + Tailwind v4 RTL` across mobile/tablet/desktop viewports), 6 backend modules, two-tier TTL cache, 7-table SQLite DDL, Pydantic v2 & TypeScript schemas, and 7 REST endpoints. |
| **[`docs/02_moe_calendar_and_maximization.md`](./docs/02_moe_calendar_and_maximization.md)** | **R2: Date Selection Modes, MoE Calendars & Maximization Math** | Mode 1 (`SPECIFIC_DATES`) & Mode 2 (`MOE_VACATION_MAXIMIZATION`), all 8 Israeli MoE frameworks, `5_DAY` vs. `6_DAY` week, Nitzanim rules, complete verified `תשפ"ו` (`schedule-o`/`0346`) & `תשפ"ז` (`0363`/`0364`) tables, 3-layer calendar JSON Schema, set math ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$), $\pm 3$-day bridge generator, and `PER`/`SAP`/`CCG`/`VUS`/`FBVS`/`CTOS` formulas with 6 worked examples. |
| **[`docs/03_airlines_and_elal_bonus_engine.md`](./docs/03_airlines_and_elal_bonus_engine.md)** | **R3: Airline Modes, `elal.com/rbddataclients/` & Bonus Synthesizer** | `EL_AL_ONLY` vs. `ALL_AIRLINES` mode switcher, `https://www.elal.com/rbddataclients/` protocol, metro-to-airport 3-letter IATA expansion (`NYC`$\to$`JFK`/`EWR`, `LON`$\to$`LHR`/`LTN`), RBD mapping (`E`/`X`/`U`, `P`/`A`/`R`, `I`/`W`), `0`/`1`/`2+` seat cap handling, Pure Points + Taxes zone table (Zones A–E), Fly Card promos, 5 family bonus fulfillment strategies, and 3-tier commercial flight APIs. |
| **[`docs/04_ui_ux_and_user_workflows.md`](./docs/04_ui_ux_and_user_workflows.md)** | **BiDi/RTL UX/UI Design, Wireframes & User Workflows** | 4-zone RTL (`dir="rtl"`) dashboard architecture, ASCII wireframes (`FamilyProfileDrawer`, `SearchControlPanel`, `ElAlBonusSearchSubPanel`, `MultiChildCalendarHeatmap`, `BonusVacationOptionCard`, `BonusVacationComparisonTable`), React component props contracts, and end-to-end family scenarios. |
| **[`docs/05_implementation_roadmap_and_rubric.md`](./docs/05_implementation_roadmap_and_rubric.md)** | **5-Phase Build Roadmap, Test Matrix & Verification Rubric** | Post-planning 5-phase implementation roadmap, unit/integration/E2E verification test matrix, and the explicit 9-item Point-by-Point Verification Rubric (`RUB-R1.1` through `RUB-AC.1`). |
| **[`docs/06_gmail_auth_and_privacy_architecture.md`](./docs/06_gmail_auth_and_privacy_architecture.md)** | **M5: Gmail OAuth 2.0 Sign-In, Per-User Privacy Isolation & Production Setup** | Pure-stdlib Google OAuth 2.0 / OIDC + PKCE (`S256`) architecture and trade-offs, SHA-256 session & CSRF security, children's-age data minimization, legacy shared profile quarantine, and step-by-step `https://breezyflights.com` production configuration guide. |

---

## 4. Rubric Traceability Matrix (`ORIGINAL_REQUEST.md` $\leftrightarrow$ Deliverable Sections)

| Rubric ID | Requirement / Acceptance Criterion (`ORIGINAL_REQUEST.md`) | Master Plan Section (`APPLICATION_PLAN.md`) | Deep-Dive Document (`docs/01..05_*.md`) |
|---|---|---|---|
| **`RUB-R1.1`** | Pre-implementation Application Plan delivered in `/home/yonibudovsky/teamwork_projects/family_vacation_planner` (`R1`, `AC-1`) | §1, §2, §6 | All (`docs/01` – `docs/05`) |
| **`RUB-R1.2`** | Technology stack, local-first platform, and data-sourcing choices justified (`R1`) | §2.1 – §2.7 | `docs/01_architecture_and_tech_stack.md` (§1 – §6) |
| **`RUB-R2.1`** | Flight Date Selection Mode 1: Specific & flexible ($\pm N$ days) date search (`R2`, `AC-2`) | §3.1 | `docs/02_moe_calendar_and_maximization.md` (§1) |
| **`RUB-R2.2`** | Flight Date Selection Mode 2: Israeli Ministry of Education frameworks (`תשפ"ו` & `תשפ"ז`, 5/6-day, Nitzanim) (`R2`, `AC-2`) | §3.2 – §3.4 | `docs/02_moe_calendar_and_maximization.md` (§2 – §4) |
| **`RUB-R2.3`** | Vacation utilization maximization algorithm ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$, bridge days, `PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS` + 6 worked examples) (`R2`, `AC-2`) | §3.5 – §3.6 | `docs/02_moe_calendar_and_maximization.md` (§5 – §6) |
| **`RUB-R3.1`** | Option to focus on El Al (`EL_AL_ONLY`) or select all airlines (`ALL_AIRLINES`) (`R3`, `AC-3`) | §4.1, §4.5 | `docs/03_airlines_and_elal_bonus_engine.md` (§1, §5) |
| **`RUB-R3.2`** | Searching El Al bonus tickets via `https://www.elal.com/rbddataclients/` (`R3`, `AC-3`) | §4.2 – §4.3 | `docs/03_airlines_and_elal_bonus_engine.md` (§2 – §3) |
| **`RUB-R3.3`** | Synthesizing & presenting vacation options utilizing bonus tickets (5 strategies, `BonusVacationOptionCard`, comparison matrix) (`R3`, `AC-3`) | §4.4, §5.2 | `docs/03_airlines_and_elal_bonus_engine.md` (§4) & `docs/04_ui_ux_and_user_workflows.md` (§4) |
| **`RUB-AC.1`** | Explicit point-by-point verification rubric included for independent review (`AC-2`, `AC-3`) | §6.2 | `docs/05_implementation_roadmap_and_rubric.md` (§3) |

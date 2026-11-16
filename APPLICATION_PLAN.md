# Master Application Plan: Israeli Family Vacation & El Al Bonus Ticket Planner (`family_vacation_planner`)

**Document Status**: Authoritative Pre-Implementation Application Plan (`R1`, `R2`, `R3`, `AC-1..3`)  
**Target Directory**: `/home/yonibudovsky/teamwork_projects/family_vacation_planner/`  
**Primary Reference Portal**: `https://www.elal.com/rbddataclients/` (El Al Matmid Classic Award Seat Availability Calculator)  
**Target School Years Pre-Seeded**: **תשפ"ו (2025–2026)** & **תשפ"ז (2026–2027)** (Israeli Ministry of Education / משרד החינוך)

---

## Table of Contents

1. [Executive Summary & Planning Scope (`R1`)](#1-executive-summary--planning-scope-r1)
2. [R1 — Target Platform, System Architecture, Tech Stack & Data Sources](#2-r1--target-platform-system-architecture-tech-stack--data-sources)
   - [2.1 Architectural Rationale: Local-First Web App + CLI Companion](#21-architectural-rationale-local-first-web-app--cli-companion)
   - [2.2 Technology Stack Specification](#22-technology-stack-specification)
   - [2.3 Six Core Backend Modules & Service Boundaries](#23-six-core-backend-modules--service-boundaries)
   - [2.4 Two-Tier SQLite TTL Caching, Rate Limiting & Configuration Management](#24-two-tier-sqlite-ttl-caching-rate-limiting--configuration-management)
   - [2.5 Complete 7-Table Relational Database Schema (SQLite DDL)](#25-complete-7-table-relational-database-schema-sqlite-ddl)
   - [2.6 Backend Pydantic v2 & Frontend TypeScript Domain Models](#26-backend-pydantic-v2--frontend-typescript-domain-models)
   - [2.7 Internal REST API Endpoints (`v1`)](#27-internal-rest-api-endpoints-v1)
3. [R2 — Flight Date Selection Modes & Israeli Ministry of Education Vacation Maximization](#3-r2--flight-date-selection-modes--israeli-ministry-of-education-vacation-maximization)
   - [3.1 Date Selection Mode 1: Specific & Flexible Dates (`SPECIFIC_DATES`)](#31-date-selection-mode-1-specific--flexible-dates-specific_dates)
   - [3.2 Date Selection Mode 2: Around Children's Vacations Across Israeli MoE Frameworks (`MOE_VACATION_MAXIMIZATION`)](#32-date-selection-mode-2-around-childrens-vacations-across-israeli-moe-frameworks-moe_vacation_maximization)
   - [3.3 Authoritative MoE Holiday Calendars: תשפ"ו (2025–2026) & תשפ"ז (2026–2027)](#33-authoritative-moe-holiday-calendars-תשפו-20252026--תשפז-20262027)
   - [3.4 3-Layer Calendar Data Architecture & JSON Schema](#34-3-layer-calendar-data-architecture--json-schema)
   - [3.5 Formal Vacation Utilization Maximization Algorithm & Mathematical Scoring (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`)](#35-formal-vacation-utilization-maximization-algorithm--mathematical-scoring-per-sap-ccg-vus-fbvs-ctos)
   - [3.6 Six Worked Numerical Optimization Examples Across Israeli Holidays](#36-six-worked-numerical-optimization-examples-across-israeli-holidays)
4. [R3 — Airline Selection Modes (`EL_AL_ONLY` vs. `ALL_AIRLINES`) & El Al Bonus Ticket Engine (`https://www.elal.com/rbddataclients/`)](#4-r3--airline-selection-modes-el_al_only-vs-all_airlines--el-al-bonus-ticket-engine-httpswwwelalcomrbddataclients)
   - [4.1 Orthogonal Airline Selection Mode Switcher](#41-orthogonal-airline-selection-mode-switcher)
   - [4.2 Technical Specification of `https://www.elal.com/rbddataclients/` Integration](#42-technical-specification-of-httpswwwelalcomrbddataclients-integration)
   - [4.3 El Al RBD Bucket Mapping, Pure Points + Taxes Zone Table & Fly Card Promotions](#43-el-al-rbd-bucket-mapping-pure-points--taxes-zone-table--fly-card-promotions)
   - [4.4 Solving the "`2` (`2+`) Seat Cap" Problem: The 5 Family Bonus Fulfillment Strategies](#44-solving-the-2-2-seat-cap-problem-the-5-family-bonus-fulfillment-strategies)
   - [4.5 3-Tier Commercial Flight Provider Architecture (`ALL_AIRLINES` & Cash Benchmarks)](#45-3-tier-commercial-flight-provider-architecture-all_airlines--cash-benchmarks)
5. [End-to-End BiDi/RTL UX/UI Specifications & Component Wireframes](#5-end-to-end-bidirtl-uxui-specifications--component-wireframes)
   - [5.1 4-Zone Dashboard Layout](#51-4-zone-dashboard-layout)
   - [5.2 Flagship `BonusVacationOptionCard` & `BonusVacationComparisonTable`](#52-flagship-bonusvacationoptioncard--bonusvacationcomparisontable)
   - [5.3 React + TypeScript + Tailwind RTL Component Hierarchy](#53-react--typescript--tailwind-rtl-component-hierarchy)
6. [Post-Planning 5-Phase Implementation Roadmap & Point-by-Point Verification Rubric](#6-post-planning-5-phase-implementation-roadmap--point-by-point-verification-rubric)
   - [6.1 5-Phase Implementation Roadmap](#61-5-phase-implementation-roadmap)
   - [6.2 Explicit Point-by-Point Pre-Build Verification Rubric (`RUB-R1.1` through `RUB-AC.1`)](#62-explicit-point-by-point-pre-build-verification-rubric-rub-r11-through-rub-ac1)

---

## 1. Executive Summary & Planning Scope (`R1`)

This document defines the complete, practical, pre-implementation **Application Plan** for the **Israeli Family Vacation & El Al Bonus Ticket Planner** (`family_vacation_planner`), authored **before starting the actual code build** (`R1`).

Planning an international family trip from Israel (`TLV`) involves solving a multi-dimensional combinatorial problem that standard flight search engines cannot express:
1. **Multi-Child Educational Framework Divergence (`R2`)**: An Israeli household frequently has children spanning different **Ministry of Education (`משרד החינוך`)** frameworks simultaneously—such as a toddler in a Supervised Daycare (`מעון יום`, ending August 8), a 5-year-old in Municipal Kindergarten (`גן חובה`, ending June 30 with **Nitzanim** holiday/July camps), a 9-year-old in Elementary School (`כיתה ד'`, ending June 30 without Nitzanim), and a 14-year-old in Middle School (`חטיבת ביניים כיתה ח'`, ending **June 20** on a 5-day school week). Standard calendars fail to identify when all children are off, when prepaid Nitzanim camps cover childcare, or when taking 1–2 "Yemei Gesher" (`ימי גשר` / bridge days) multiplies parent PTO efficiency by $3\times\text{–}5\times$ while beating holiday peak airfares.
2. **Airline Selection & El Al Matmid Bonus Ticket Synthesis (`R3`)**: Families need to toggle effortlessly between **Mode 1: Focus on El Al (`EL_AL_ONLY`)**—including searching Classic Award bonus seat availability at `https://www.elal.com/rbddataclients/` across Economy (`E`/`X`/`U`), Premium (`P`/`A`/`R`), and Business (`I`/`W`) cabins—and **Mode 2: All Airlines (`ALL_AIRLINES`)** across full-service and low-cost carriers with normalized family baggage pricing. Crucially, because `https://www.elal.com/rbddataclients/` caps its per-cabin seat display at `2` (`2+` seats available) while families require $3\text{–}6$ tickets, the application synthesizes actionable **Vacation Options Utilizing Bonus Tickets** using five concrete family fulfillment strategies: **Full-Bonus Same Cabin**, **Split-Cabin Bonus** (e.g., 2 Economy + 2 Premium/Business on the same flight), **Hybrid Bonus + Cash** (e.g., 2 Bonus + 2–3 Cash on the same flight), **One-Way Bonus + One-Way Cash / Open-Jaw Bonus**, and **Cash & Points**.

### Companion Documentation Suite Index
Alongside this self-contained master plan (`APPLICATION_PLAN.md`), the repository includes modular deep-dive specifications:
- [`README.md`](./README.md) — Executive Overview, Quick Navigation Index, & Rubric Traceability Matrix.
- [`docs/01_architecture_and_tech_stack.md`](./docs/01_architecture_and_tech_stack.md) — Platform, Tech Stack, 6 Backend Modules, SQLite DDL (7 Tables), Pydantic v2 / TypeScript Schemas, REST APIs, Caching & Config.
- [`docs/02_moe_calendar_and_maximization.md`](./docs/02_moe_calendar_and_maximization.md) — Date Modes 1 & 2, Israeli MoE Frameworks, Verified `תשפ"ו` & `תשפ"ז` Calendars, Set Math ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$), Bridge-Day Algorithm, & Scoring Formulas (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`) + 6 Worked Examples.
- [`docs/03_airlines_and_elal_bonus_engine.md`](./docs/03_airlines_and_elal_bonus_engine.md) — Airline Modes (`EL_AL_ONLY` vs. `ALL_AIRLINES`), `https://www.elal.com/rbddataclients/` Integration Spec, RBD Mapping, `2+` Seat Cap Solver, 5 Bonus Fulfillment Strategies, Zone Points Table, & 3-Tier Flight APIs.
- [`docs/04_ui_ux_and_user_workflows.md`](./docs/04_ui_ux_and_user_workflows.md) — BiDi/RTL 4-Zone UI Architecture, ASCII Wireframes, Component Contracts, & End-to-End Family Scenarios.
- [`docs/05_implementation_roadmap_and_rubric.md`](./docs/05_implementation_roadmap_and_rubric.md) — 5-Phase Post-Planning Implementation Roadmap, Test Matrix, & Explicit Point-by-Point Verification Rubric (`RUB-R1.1`..`RUB-AC.1`).

---

## 2. R1 — Target Platform, System Architecture, Tech Stack & Data Sources

### 2.1 Architectural Rationale: Local-First Web App + CLI Companion

For personal, practical family use (`R1`), the application is designed as a **Local-First Web Application + CLI Companion**:
1. **Zero Cloud Hosting Cost & Complete Privacy**: Family member names, children's birthdates, school frameworks, and Matmid Frequent Flyer point balances remain in a local SQLite database (`data/vacation_planner.db`) on the user's machine.
2. **Bilingual BiDi/RTL Interactive Visual Dashboard**: Comparing multi-child school calendars in Hebrew (`dir="rtl"`), adjusting bridge-day sliders, and inspecting multi-cabin El Al bonus combinations requires a responsive browser UI (`React 19 + TypeScript + Tailwind CSS v4`).
3. **Resilient Headless Browser & Async Scraping Runtime**: Querying `https://www.elal.com/rbddataclients/` and Google Flights Protobuf endpoints requires a local Python backend (`Python 3.13 + FastAPI + Playwright + httpx`) capable of managing browser session cookies, polite token-bucket rate limiting, and local SQLite TTL caching.
4. **CLI Companion (`plan-vacation`)**: Enables quick terminal searches and optional background cron checks when new El Al bonus seats open up on target holiday dates.

### 2.2 Technology Stack Specification

| Layer | Selected Technology | Rationale for Personal Israeli Family Planner |
|---|---|---|
| **Backend Runtime & API** | **Python 3.13 + FastAPI + Uvicorn + Pydantic v2** | Native async concurrency for parallel route/date queries; strict schema validation for calendar matrices and ticket allocations. |
| **Database & Persistence** | **SQLite 3.53 (WAL Mode) + SQLAlchemy 2.0** | Zero-admin single-file database (`data/vacation_planner.db`) with concurrent read/write support via Write-Ahead Logging (`PRAGMA journal_mode=WAL;`). |
| **El Al Bonus Connector** | **`Playwright` (Headless Chromium) + `httpx` + `tenacity`** | Navigates `https://www.elal.com/rbddataclients/`, handles Akamai/Cloudflare WAF session cookies, intercepts XHR/Fetch JSON award grids, and enforces exponential backoff. |
| **Commercial Flight Providers** | **3-Tier Pluggable Adapter**:<br>1. `fast-flights` / `fli` (Google Flights Protobuf client)<br>2. **SerpApi Google Flights API** (250 free/mo + 1h cache)<br>3. **Duffel API** (self-serve NDC/GDS REST) | Reflects the verified 2025–2026 API landscape where Amadeus Self-Service discontinued its public free tier and Kiwi Tequila became invite-only. Guarantees zero-cost immediate personal operation. |
| **Hebrew & MoE Calendar Engine** | **Bundled MoE JSON Rule Packs (`תשפ"ו`, `תשפ"ז`) + `pyluach` / `hdate` + `Hebcal REST API (i=on)`** | Authoritative Ministry of Education circulars (`schedule-o`, `0346`, `0363`, `0364`) are not on `data.gov.il`; local curated JSON packs + Hebcal Israel (`i=on`) projection ensure 100% accuracy. |
| **Frontend Web UI (Desktop + Mobile PWA)** | **React 19 + TypeScript + Vite + Tailwind CSS v4 (RTL + Mobile-First Responsive + PWA)** | Native logical CSS properties (`ms-*`, `me-*`, `ps-*`, `pe-*`) for seamless Hebrew RTL (`dir="rtl"`), mobile-first breakpoints (`360px–430px` smartphone bottom sheets, sticky RTL calendar columns, and swipeable cards; `1280px+` 4-zone desktop dashboard), and installable PWA (`manifest.webmanifest`). |
| **CLI & Background Jobs** | **Typer + Rich + APScheduler** | Terminal tables for `rbddataclients` award scans and scheduled local checks for newly released bonus seats. |

### 2.3 Six Core Backend Modules & Service Boundaries

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                   Presentation Layer (Local Web UI & CLI)                    │
│  ┌─────────────────────────────────────────┐  ┌───────────────────────────┐  │
│  │ React 19 + TS + Tailwind v4 RTL Web UI  │  │ Typer + Rich CLI Tool     │  │
│  │ • FamilyProfileDrawer (8 MoE Frameworks)│  │ • Quick Date/Bonus Search │  │
│  │ • SearchControlPanel (2x2 Mode Switcher)│  │ • Background Alert Runner │  │
│  │ • MultiChildCalendarHeatmap & BonusCard │  │ • ICS / JSON Export       │  │
│  └────────────────────┬────────────────────┘  └─────────────┬─────────────┘  │
└───────────────────────┼─────────────────────────────────────┼────────────────┘
                        │ REST JSON (`/api/v1/*`)             │ Direct Python
┌───────────────────────▼─────────────────────────────────────▼────────────────┐
│                        Core Application Service Layer                        │
│  ┌────────────────────────┐ ┌──────────────────────┐ ┌────────────────────┐  │
│  │ 1. `calendar_engine`   │ │ 2. `vacation_        │ │ 4. `planner_       │  │
│  │ (`MoECalendarService`) │ │    optimizer`        │ │    synthesizer`    │  │
│  │ • 8 MoE Frameworks     │ │ (`VacationMaximizer  │ │ (`BonusVacation    │  │
│  │ • 5-Day vs 6-Day Week  │ │   Engine`)           │ │   PlannerService`) │  │
│  │ • Nitzanim Camp Rules  │ │ • Sets I, I_camp, U  │ │ • 5 Family Bonus   │  │
│  │ • TLV Yom Kippur Check │ │ • ±3d Bridge Expander│ │   Strategies       │  │
│  │ • Parent PTO Vector    │ │ • PER/SAP/CCG/VUS    │ │ • FBVS & CTOS Rank │  │
│  └───────────┬────────────┘ └──────────┬───────────┘ └─────────┬──────────┘  │
│              └─────────────────────────┼───────────────────────┘             │
│                                        ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                 3. `providers` (Flight & Award Adapters)               │  │
│  │  • `ElAlRbdDataClientAdapter` (`https://www.elal.com/rbddataclients/`) │  │
│  │  • `AllAirlinesSearchAdapter` (`fast-flights`/`fli`, SerpApi, Duffel)  │  │
│  └───────────┬─────────────────────────────────┬──────────────────────────┘  │
└──────────────┼─────────────────────────────────┼─────────────────────────────┘
               ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│       5. `storage_cache` (SQLite 3.53 WAL) & 6. `config_manager` (YAML/.env) │
│  • 7 Core Relational Tables (`family_profiles` .. `vacation_option_proposals`)│
│  • Two-Tier TTL Cache (`elal_bonus_availability` 4h, `flight_itineraries` 6h)│
└──────────────────────────────────────────────────────────────────────────────┘
```

1. **`calendar_engine` (`MoECalendarService`)**: Resolves daily status across all 8 Israeli MoE educational frameworks, `5_DAY` vs. `6_DAY` school weeks, Nitzanim (`בית הספר של החגים` & `בית הספר של החופש הגדול`) overlays, parent PTO weights ($P(d) \in \{0, 0.5, 1.0\}$), and Ben Gurion Airport (`TLV`) Yom Kippur shutdown / El Al Shabbat flight windows.
2. **`vacation_optimizer` (`VacationMaximizerEngine`)**: Computes multi-child Strict Intersection ($\mathcal{I}$), Camp-Adjusted Intersection ($\mathcal{I}_{\text{camp}}$), and Framework-Delta Union ($\mathcal{U}$), generates $\pm 3$-day "Yemei Gesher" (bridge-day) candidate windows, and evaluates `PER`, `SAP`, `CCG`, and `VUS`.
3. **`providers` (`ElAlRbdDataClientAdapter` & `AllAirlinesSearchAdapter`)**: Queries `https://www.elal.com/rbddataclients/` with metro-to-airport IATA expansion (`NYC` $\to$ `JFK`/`EWR`, `LON` $\to$ `LHR`/`LTN`) and queries commercial flight providers (`fast-flights`/`fli`, `SerpApi`, `Duffel`) with automatic family baggage normalization.
4. **`planner_synthesizer` (`BonusVacationPlannerService`)**: Pairs outbound and inbound legs and solves the **Family Bonus Ticket Composition Problem** across the 5 fulfillment strategies (`FULL_BONUS_SAME_CABIN`, `SPLIT_CABIN_BONUS`, `HYBRID_BONUS_PLUS_CASH`, `ONE_WAY_BONUS_ONE_WAY_CASH`, `CASH_AND_POINTS`), computing `FBVS` and `CTOS`.
5. **`storage_cache` (`SQLiteRepository`)**: Manages the 7 SQLite tables, atomic transactions, and two-tier TTL cache invalidation.
6. **`config_manager` (`SettingsLoader`)**: Loads `config/settings.yaml` (default airport `TLV`, currency, Matmid point valuation, optimization weights) and `.env` secrets (`SERPAPI_API_KEY`, `DUFFEL_ACCESS_TOKEN`).

### 2.4 Two-Tier SQLite TTL Caching, Rate Limiting & Configuration Management

- **Tier 1 Award Cache (`elal_bonus_availability`)**: Keyed by `(origin_iata, destination_iata, flight_date, flight_number)`. Default **TTL = 4 hours** (configurable down to 15 minutes or bypassed via `force_refresh=True`). Allows instant re-ranking when the user tweaks bridge-day tolerances or PTO weights without re-scraping `elal.com/rbddataclients/`.
- **Tier 2 Commercial Fare Cache (`flight_itineraries`)**: Keyed by `(origin_iata, destination_iata, departure_date, return_date, passenger_hash, airline_selection_mode)`. Default **TTL = 6 hours**.
- **Polite Token-Bucket Rate Limiter for `rbddataclients`**: Enforces a maximum of **1 request every 2.5 seconds** with uniform random jitter (`[1.5s, 3.5s]`) and a cap of **15 route-month queries per batch**, protecting the user's IP from Akamai/Cloudflare blocks.

### 2.5 Complete 8-Table Relational Database Schema (SQLite DDL)

The SQLite database (`backend/app/db/schema.sql`) comprises 8 normalized tables with strict foreign-key and `CHECK` constraints (including `passenger_loyalty_wallets` for per-passenger multi-club point balances, auto-updating `moe_vacation_windows`, and 3-mode `flight_search_queries`):

```sql
PRAGMA foreign_keys = ON;

-- 1. FamilyProfile: Stores household configuration, parent PTO rules, and default household Matmid summary
CREATE TABLE family_profiles (
    id TEXT PRIMARY KEY,                          -- UUID v4
    profile_name TEXT NOT NULL DEFAULT 'המשפחה שלי',
    adults_count INTEGER NOT NULL DEFAULT 2 CHECK (adults_count BETWEEN 1 AND 6),
    workweek_type TEXT NOT NULL DEFAULT 'SUN_THU' CHECK (workweek_type IN ('SUN_THU', 'SUN_FRI')),
    erev_chag_pto_weight REAL NOT NULL DEFAULT 0.5 CHECK (erev_chag_pto_weight IN (0.0, 0.5, 1.0)),
    chol_hamoed_pto_weight REAL NOT NULL DEFAULT 0.5 CHECK (chol_hamoed_pto_weight IN (0.0, 0.5, 1.0)),
    annual_pto_budget REAL NOT NULL DEFAULT 14.0 CHECK (annual_pto_budget >= 0.0),
    max_pto_per_trip REAL NOT NULL DEFAULT 5.0 CHECK (max_pto_per_trip >= 0.0),
    matmid_points_balance INTEGER NOT NULL DEFAULT 0 CHECK (matmid_points_balance >= 0),
    has_flycard INTEGER NOT NULL DEFAULT 1 CHECK (has_flycard IN (0, 1)),
    flycard_tier TEXT NOT NULL DEFAULT 'FLY_CARD_PREMIUM' CHECK (flycard_tier IN ('NONE', 'FLY_CARD', 'FLY_CARD_PREMIUM')),
    flycard_companion_vouchers INTEGER NOT NULL DEFAULT 0 CHECK (flycard_companion_vouchers >= 0),
    point_valuation_usd REAL NOT NULL DEFAULT 0.016 CHECK (point_valuation_usd > 0.0),
    preferred_currency TEXT NOT NULL DEFAULT 'USD' CHECK (preferred_currency IN ('USD', 'ILS', 'EUR')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. PassengerLoyaltyWallet: Per-passenger available points across multiple frequent flyer clubs & credit card programs
CREATE TABLE passenger_loyalty_wallets (
    id TEXT PRIMARY KEY,                          -- UUID v4
    family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
    passenger_id TEXT NOT NULL,                   -- e.g. 'ADULT_1', 'ADULT_2', 'CHILD_1', or 'FAMILY_POOL'
    passenger_name TEXT NOT NULL,                 -- e.g. 'יוני (הורה 1)', 'הורה 2', 'נועה'
    program_code TEXT NOT NULL CHECK (program_code IN (
        'ELAL_MATMID',                            -- מועדון הנוסע המתמיד אל על
        'BRITISH_AVIOS',                          -- British Airways / Qatar / Finnair Avios (oneworld)
        'FLYING_BLUE',                            -- Air France / KLM Flying Blue (SkyTeam + Family Pool)
        'UNITED_MILEAGEPLUS',                     -- United MileagePlus (Star Alliance + Miles Pooling)
        'MILES_AND_MORE',                         -- Lufthansa / Swiss / Austrian Miles & More (Mileage Pooling)
        'DELTA_SKYMILES',                         -- Delta SkyMiles (SkyTeam + El Al partner awards)
        'QANTAS_FREQUENT_FLYER',                  -- Qantas Frequent Flyer (El Al & oneworld partner awards)
        'AEGEAN_MILES_BONUS',                     -- Aegean Miles+Bonus (Star Alliance + Together account)
        'AMEX_MR_ISRAEL',                         -- אמריקן אקספרס ישראל (נקודות ניתנות להמרה למועדוני תעופה)
        'ISRAELI_CC_TRAVEL_POINTS'                -- נקודות כרטיסי אשראי (MAX Sky / Cal Fly / Isracard)
    )),
    available_points INTEGER NOT NULL DEFAULT 0 CHECK (available_points >= 0),
    can_pool_with_family INTEGER NOT NULL DEFAULT 0 CHECK (can_pool_with_family IN (0, 1)),
    pool_group_id TEXT,                           -- Optional shared pool ID when club supports family pooling
    transfer_ratio_to_airline REAL NOT NULL DEFAULT 1.0 CHECK (transfer_ratio_to_airline > 0.0),
    has_club_credit_card INTEGER NOT NULL DEFAULT 0 CHECK (has_club_credit_card IN (0, 1)), -- e.g. FlyCard per passenger
    companion_vouchers_count INTEGER NOT NULL DEFAULT 0 CHECK (companion_vouchers_count >= 0),
    point_valuation_cents REAL NOT NULL DEFAULT 1.5 CHECK (point_valuation_cents > 0.0),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_loyalty_wallets_profile_pax ON passenger_loyalty_wallets(family_profile_id, passenger_id, program_code);

-- 3. ChildFramework: Stores each child's age and (optionally, when searching by vacations) their Israeli Ministry of Education framework
CREATE TABLE child_frameworks (
    id TEXT PRIMARY KEY,                          -- UUID v4
    family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
    child_name TEXT NOT NULL DEFAULT 'ילד/ה',
    child_age_years INTEGER NOT NULL CHECK (child_age_years BETWEEN 0 AND 21), -- Age in years (0-21) for airline fare & vacation matching
    birth_date TEXT,                              -- Optional ISO-8601 YYYY-MM-DD
    passenger_Current_type TEXT NOT NULL DEFAULT 'CHILD' CHECK (passenger_Current_type IN (
        'INFANT_LAP',                             -- Under 2 on parent lap
        'INFANT_SEAT',                            -- Under 2 in dedicated seat
        'CHILD',                                  -- Ages 2-11
        'YOUTH'                                   -- Ages 12-17
    )),
    -- Optional educational framework (nullable: only required when user wants to match vacations by child framework):
    framework_type TEXT CHECK (framework_type IS NULL OR framework_type IN (
        'DAYCARE_SUPERVISED',                     -- מעונות יום ומשפחתונים בפיקוח (גילאי 0-3, סיום 8 באוגוסט)
        'MUNICIPAL_GAN',                          -- גני ילדים רשמיים (גילאי 3-6, סיום 30 ביוני + ניצנים)
        'ELEMENTARY_1_3',                         -- בית ספר יסודי כיתות א'-ג' (סיום 30 ביוני + ניצנים)
        'ELEMENTARY_4_6',                         -- בית ספר יסודי כיתות ד'-ו' (סיום 30 ביוני)
        'MIDDLE_SCHOOL_7_9',                      -- חטיבת ביניים כיתות ז'-ט' (חופשות יסודי בשנה + סיום 20 ביוני)
        'HIGH_SCHOOL_10_12',                      -- חטיבה עליונה כיתות י'-י"ב (סיום 20 ביוני + אסרו חג סוכות + בגרויות)
        'SPECIAL_ED',                             -- חינוך מיוחד (מסגרת מוארכת עד 15 באוגוסט)
        'RELIGIOUS_HAREDI'                        -- ממלכתי-דתי / מוסדות חרדיים (צומות ובין הזמנים)
    )),
    education_stream TEXT NOT NULL DEFAULT 'MAMLACHTI' CHECK (education_stream IN (
        'MAMLACHTI', 'MAMLACHTI_DATI', 'CHAREDI', 'SPECIAL_EDUCATION'
    )),
    school_week_days INTEGER NOT NULL DEFAULT 5 CHECK (school_week_days IN (5, 6)),
    holiday_extension_mode TEXT NOT NULL DEFAULT 'NONE' CHECK (holiday_extension_mode IN (
        'NONE',                                   -- ללא צהרון/ניצנים
        'NITZANIM_CHAGIM_ONLY',                   -- בית הספר של החגים בלבד (5 ימים בחנוכה + 5 ימים לפני פסח)
        'NITZANIM_FULL_WITH_JULY'                 -- ניצנים מלא כולל בית הספר של החופש הגדול (כל חודש יולי)
    )),
    treat_camp_as_vacation INTEGER NOT NULL DEFAULT 1 CHECK (treat_camp_as_vacation IN (0, 1)),
    max_school_days_missed INTEGER NOT NULL DEFAULT 2 CHECK (max_school_days_missed BETWEEN 0 AND 14),
    absence_penalty_weight REAL NOT NULL DEFAULT 1.0 CHECK (absence_penalty_weight >= 0.0),
    bagrut_blackout_dates_json TEXT NOT NULL DEFAULT '[]' -- JSON array of YYYY-MM-DD exam dates
);

-- 3. MoEVacationWindow: Official Israeli Ministry of Education holiday & vacation windows per school year
CREATE TABLE moe_vacation_windows (
    id TEXT PRIMARY KEY,                          -- e.g. '2026_2027_PESACH_ELEMENTARY_1_3'
    school_year TEXT NOT NULL,                    -- e.g. '2025-2026' (תשפ"ו), '2026-2027' (תשפ"ז)
    circular_id TEXT NOT NULL,                    -- e.g. 'schedule-o', '0346', '0363', '0364'
    holiday_code TEXT NOT NULL,                   -- e.g. 'ROSH_HASHANAH', 'YOM_KIPPUR_SUKKOT', 'HANUKKAH', 'PURIM', 'PESACH', 'YOM_HAATZMAUT', 'LAG_BAOMER', 'SHAVUOT', 'SUMMER_JUNE_20_30', 'SUMMER_JULY', 'SUMMER_AUGUST'
    holiday_name_he TEXT NOT NULL,
    holiday_name_en TEXT NOT NULL,
    framework_type TEXT NOT NULL CHECK (framework_type IN (
        'DAYCARE_SUPERVISED', 'MUNICIPAL_GAN', 'ELEMENTARY_1_3', 'ELEMENTARY_4_6',
        'MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12', 'SPECIAL_ED', 'RELIGIOUS_HAREDI'
    )),
    start_date TEXT NOT NULL,                     -- ISO-8601 YYYY-MM-DD (first day off school)
    end_date TEXT NOT NULL,                       -- ISO-8601 YYYY-MM-DD (last day off school)
    resumes_on_date TEXT NOT NULL,                -- ISO-8601 YYYY-MM-DD (day studies resume)
    is_covered_by_nitzanim INTEGER NOT NULL DEFAULT 0 CHECK (is_covered_by_nitzanim IN (0, 1)),
    nitzanim_start_date TEXT,                     -- ISO-8601 YYYY-MM-DD if Nitzanim operates during part of window
    nitzanim_end_date TEXT,                       -- ISO-8601 YYYY-MM-DD
    parent_workday_status TEXT NOT NULL DEFAULT 'REGULAR_WORKDAY' CHECK (parent_workday_status IN (
        'PUBLIC_HOLIDAY_OFF',                     -- חג רשמי (שבתון מלא במשק - 0 ימי חופש הורים)
        'EREV_CHAG_HALF_DAY',                     -- ערב חג (0.5 יום חופש הורים)
        'CHOL_HAMOED',                            -- חול המועד (0.5 יום חופש הורים)
        'REGULAR_WORKDAY'                         -- יום עבודה רגיל במשק (אך חופשה במוסדות החינוך, למשל אסרו חג / חנוכה)
    )),
    tlv_airport_closed INTEGER NOT NULL DEFAULT 0 CHECK (tlv_airport_closed IN (0, 1)),
    calendar_sync_source TEXT NOT NULL DEFAULT 'OFFICIAL_MOE_CIRCULAR' CHECK (calendar_sync_source IN (
        'OFFICIAL_MOE_CIRCULAR',                  -- Pre-seeded or verified MoE Director General Circular
        'AUTO_SYNCED_CIRCULAR',                   -- Automatically fetched by yearly MoECalendarAutoUpdaterService
        'HEBREW_RULE_PROJECTED',                  -- Algorithmically projected via pyluach/Hebcal + MoE statutory rules
        'USER_MUNICIPAL_OVERRIDE'                 -- Local municipal/school override by user
    )),
    last_synced_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_reference TEXT NOT NULL
);
CREATE INDEX idx_moe_vacation_year_framework ON moe_vacation_windows(school_year, framework_type, start_date);

-- 4. FlightSearchQuery: Captures user search execution across Date Mode (1/2/3) and Airline Mode (1/2)
CREATE TABLE flight_search_queries (
    id TEXT PRIMARY KEY,                          -- UUID v4
    family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
    date_selection_mode TEXT NOT NULL CHECK (date_selection_mode IN (
        'SPECIFIC_DATES',                         -- R2 Mode 1: Specific / Flexible Dates
        'MOE_VACATION_MAXIMIZATION',              -- R2 Mode 2: Around Children's MoE Vacations (Full School-Year Optimizer)
        'HOLIDAY_DIRECT_INTENT'                   -- R2 Mode 3: Specific Holiday/Vacation + Year Maximizer (e.g. Pesach 2027)
    )),
    airline_selection_mode TEXT NOT NULL CHECK (airline_selection_mode IN (
        'EL_AL_ONLY',                             -- R3 Mode 1: Focus on El Al (including rbddataclients bonus)
        'ALL_AIRLINES'                            -- R3 Mode 2: All Airlines (including multi-club bonus & commercial fares)
    )),
    search_elal_bonus_tickets INTEGER NOT NULL DEFAULT 1 CHECK (search_elal_bonus_tickets IN (0, 1)),
    include_sundor_flights INTEGER NOT NULL DEFAULT 1 CHECK (include_sundor_flights IN (0, 1)),
    origin_iata TEXT NOT NULL DEFAULT 'TLV',
    destination_iatas_json TEXT NOT NULL,         -- JSON array of IATA/Metro codes or '["ANYWHERE"]'
    -- Mode 1 (Specific Dates) fields:
    specific_departure_date TEXT,                 -- YYYY-MM-DD
    specific_return_date TEXT,                    -- YYYY-MM-DD
    flex_days_plus_minus INTEGER NOT NULL DEFAULT 0 CHECK (flex_days_plus_minus BETWEEN 0 AND 7),
    -- Mode 2 (MoE Vacation Maximization) fields:
    school_year TEXT,                             -- e.g. '2025-2026', '2026-2027', '2027-2028'
    target_holiday_codes_json TEXT,               -- JSON array of holiday_code strings
    -- Mode 3 (Specific Holiday/Vacation + Year Maximizer) fields:
    direct_holiday_code TEXT,                     -- Selected holiday/vacation code: e.g. 'PESACH', 'SUKKOT', 'HANUKKAH', 'ROSH_HASHANAH', 'PURIM', 'SHAVUOT', 'SUMMER_JULY', 'SUMMER_AUGUST'
    direct_target_year INTEGER CHECK (direct_target_year IS NULL OR direct_target_year BETWEEN 2025 AND 2035), -- Selected year: e.g. 2027
    min_trip_nights INTEGER NOT NULL DEFAULT 4 CHECK (min_trip_nights >= 1),
    max_trip_nights INTEGER NOT NULL DEFAULT 10 CHECK (max_trip_nights >= min_trip_nights),
    max_bridge_days_shift INTEGER NOT NULL DEFAULT 3 CHECK (max_bridge_days_shift BETWEEN 0 AND 5),
    overlap_policy TEXT NOT NULL DEFAULT 'MAXIMIZE_EFFICIENCY_SCORE' CHECK (overlap_policy IN (
        'STRICT_ALL_CHILDREN_OFF',
        'CAMP_ADJUSTED_INTERSECTION',
        'MAXIMIZE_EFFICIENCY_SCORE'
    )),
    -- El Al & Multi-Club Bonus Filters:
    preferred_cabins_json TEXT NOT NULL DEFAULT '["ECONOMY","PREMIUM","BUSINESS"]',
    enabled_loyalty_programs_json TEXT NOT NULL DEFAULT '["ELAL_MATMID"]', -- Can include multiple clubs per passenger
    allow_hybrid_bonus_cash INTEGER NOT NULL DEFAULT 1 CHECK (allow_hybrid_bonus_cash IN (0, 1)),
    direct_flights_only INTEGER NOT NULL DEFAULT 1 CHECK (direct_flights_only IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 5. ElAlBonusAvailability: Cached Classic Award records fetched from https://www.elal.com/rbddataclients/
CREATE TABLE elal_bonus_availability (
    id TEXT PRIMARY KEY,                          -- Deterministic key: flight_number + '_' + flight_date
    origin_iata TEXT NOT NULL,                    -- Exact 3-letter airport IATA (e.g. 'TLV', 'JFK', 'EWR', 'LHR', 'LTN')
    destination_iata TEXT NOT NULL,               -- Exact 3-letter airport IATA
    direction TEXT NOT NULL CHECK (direction IN ('OUTBOUND', 'INBOUND')),
    flight_number TEXT NOT NULL,                  -- e.g. 'LY381', 'LY001', 'LY5121' (Sun d'Or)
    operating_carrier TEXT NOT NULL DEFAULT 'LY', -- 'LY' (El Al mainline) or '2U' (Sun d'Or)
    flight_date TEXT NOT NULL,                    -- YYYY-MM-DD
    departure_time_local TEXT NOT NULL,           -- HH:MM
    arrival_time_local TEXT NOT NULL,             -- HH:MM
    aircraft_type TEXT,                           -- e.g. '789', '788', '772', '739', '738'
    -- Seat counts reported by https://www.elal.com/rbddataclients/ (0, 1, or 2 representing '2+ seats'):
    economy_award_seats INTEGER NOT NULL DEFAULT 0 CHECK (economy_award_seats BETWEEN 0 AND 9),
    economy_seats_is_two_plus INTEGER NOT NULL DEFAULT 0 CHECK (economy_seats_is_two_plus IN (0, 1)),
    economy_rbd_code TEXT NOT NULL DEFAULT 'E',   -- Classic Award Economy RBD ('E' / 'X' / 'U')
    premium_award_seats INTEGER NOT NULL DEFAULT 0 CHECK (premium_award_seats BETWEEN 0 AND 9),
    premium_seats_is_two_plus INTEGER NOT NULL DEFAULT 0 CHECK (premium_seats_is_two_plus IN (0, 1)),
    premium_rbd_code TEXT NOT NULL DEFAULT 'P',   -- Classic Award Premium RBD ('P' / 'A' / 'R')
    business_award_seats INTEGER NOT NULL DEFAULT 0 CHECK (business_award_seats BETWEEN 0 AND 9),
    business_seats_is_two_plus INTEGER NOT NULL DEFAULT 0 CHECK (business_seats_is_two_plus IN (0, 1)),
    business_rbd_code TEXT NOT NULL DEFAULT 'I',  -- Classic Award Business RBD ('I' / 'W')
    -- Points & mandatory airport taxes per passenger (one-way):
    award_zone TEXT NOT NULL DEFAULT 'ZONE_B',    -- 'ZONE_A' .. 'ZONE_E'
    economy_points_per_pax INTEGER,
    premium_points_per_pax INTEGER,
    business_points_per_pax INTEGER,
    flycard_promo_active INTEGER NOT NULL DEFAULT 0 CHECK (flycard_promo_active IN (0, 1)),
    taxes_usd_per_pax REAL NOT NULL DEFAULT 0.0 CHECK (taxes_usd_per_pax >= 0.0),
    source_url TEXT NOT NULL DEFAULT 'https://www.elal.com/rbddataclients/',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL                      -- TTL expiration timestamp
);
CREATE INDEX idx_elal_bonus_route_date ON elal_bonus_availability(origin_iata, destination_iata, flight_date);

-- 6. FlightItinerary: Round-trip or Open-Jaw flight pairing (El Al Bonus, Hybrid, or All-Airlines Cash)
CREATE TABLE flight_itineraries (
    id TEXT PRIMARY KEY,                          -- UUID v4
    search_query_id TEXT NOT NULL REFERENCES flight_search_queries(id) ON DELETE CASCADE,
    origin_iata TEXT NOT NULL,
    destination_iata TEXT NOT NULL,
    return_origin_iata TEXT NOT NULL,             -- Matches destination_iata or alternate airport for Open-Jaw
    destination_city_he TEXT NOT NULL,
    destination_city_en TEXT NOT NULL,
    departure_date TEXT NOT NULL,                 -- YYYY-MM-DD
    return_date TEXT NOT NULL,                    -- YYYY-MM-DD
    trip_nights INTEGER NOT NULL CHECK (trip_nights >= 1),
    primary_carrier_iata TEXT NOT NULL,           -- 'LY' or other carrier ('A3', 'LH', 'BA', 'W6', 'FR', 'IZ', '6H')
    is_elal_flight INTEGER NOT NULL CHECK (is_elal_flight IN (0, 1)),
    utilizes_elal_bonus INTEGER NOT NULL CHECK (utilizes_elal_bonus IN (0, 1)),
    fulfillment_strategy TEXT NOT NULL CHECK (fulfillment_strategy IN (
        'FULL_BONUS_SAME_CABIN',                  -- Strategy 1: All passengers in same award cabin (requires checkout verify if >2)
        'SPLIT_CABIN_BONUS',                      -- Strategy 2: 100% Bonus split across cabins on same flight (e.g. 2 Econ + 2 Prem/Biz)
        'HYBRID_BONUS_PLUS_CASH',                 -- Strategy 3: Bonus tickets + Commercial Cash tickets on exact same flight
        'ONE_WAY_BONUS_ONE_WAY_CASH',             -- Strategy 4: Asymmetric direction mix or Open-Jaw Bonus
        'CASH_AND_POINTS',                        -- Strategy 5: El Al commercial fare discounted with Matmid Cash & Points
        'MULTI_CLUB_PER_PASSENGER_SPLIT',         -- Strategy 6: Multi-passenger / multi-club point split across wallets
        'COMMERCIAL_CASH_ONLY'                    -- Pure cash itinerary (All Airlines or El Al cash benchmark)
    )),
    outbound_legs_json TEXT NOT NULL,             -- JSON array of FlightLeg objects
    inbound_legs_json TEXT NOT NULL,              -- JSON array of FlightLeg objects
    outbound_bonus_id TEXT REFERENCES elal_bonus_availability(id),
    inbound_bonus_id TEXT REFERENCES elal_bonus_availability(id),
    family_ticket_allocation_json TEXT NOT NULL,  -- JSON array of PassengerTicketAllocation objects (with passenger_id & program_code)
    points_used_by_wallet_json TEXT NOT NULL DEFAULT '{}', -- JSON map of wallet_id/program_code -> points deducted per passenger
    requires_two_plus_seat_verification INTEGER NOT NULL DEFAULT 0 CHECK (requires_two_plus_seat_verification IN (0, 1)),
    total_matmid_points INTEGER NOT NULL DEFAULT 0 CHECK (total_matmid_points >= 0),
    total_taxes_and_fees_usd REAL NOT NULL DEFAULT 0.0 CHECK (total_taxes_and_fees_usd >= 0.0),
    total_supplemental_cash_fares_usd REAL NOT NULL DEFAULT 0.0 CHECK (total_supplemental_cash_fares_usd >= 0.0),
    total_baggage_fees_usd REAL NOT NULL DEFAULT 0.0 CHECK (total_baggage_fees_usd >= 0.0),
    total_out_of_pocket_cash_usd REAL NOT NULL CHECK (total_out_of_pocket_cash_usd >= 0.0),
    full_cash_benchmark_usd REAL NOT NULL CHECK (full_cash_benchmark_usd >= 0.0),
    net_cash_saved_usd REAL NOT NULL DEFAULT 0.0,
    cents_per_point_value REAL,                   -- (full_cash_benchmark_usd - total_out_of_pocket_cash_usd) * 100.0 / total_matmid_points
    rbddataclients_verify_url TEXT,               -- Direct link to https://www.elal.com/rbddataclients/
    booking_deep_link_url TEXT NOT NULL
);

-- 7. VacationOptionProposal: Joins a FlightItinerary with MoE Multi-Child Vacation Maximization Metrics
CREATE TABLE vacation_option_proposals (
    id TEXT PRIMARY KEY,                          -- UUID v4
    search_query_id TEXT NOT NULL REFERENCES flight_search_queries(id) ON DELETE CASCADE,
    itinerary_id TEXT NOT NULL REFERENCES flight_itineraries(id) ON DELETE CASCADE,
    associated_holiday_codes_json TEXT NOT NULL,  -- JSON array e.g. '["PESACH"]'
    window_set_type TEXT NOT NULL DEFAULT 'CAMP_ADJUSTED_INTERSECTION' CHECK (window_set_type IN (
        'STRICT_INTERSECTION',                    -- Set I: All children strictly off (no school, no camp)
        'CAMP_ADJUSTED_INTERSECTION',             -- Set I_camp: All children off school (includes Nitzanim days)
        'FRAMEWORK_DELTA_UNION',                  -- Set U: Partial framework overlap (e.g. June 20-30 Middle/High off)
        'SPECIFIC_USER_WINDOW'                    -- Mode 1 user-selected dates
    )),
    total_vacation_days INTEGER NOT NULL CHECK (total_vacation_days >= 1),
    parent_pto_days_used REAL NOT NULL CHECK (parent_pto_days_used >= 0.0),
    pto_efficiency_ratio REAL NOT NULL,           -- PER = total_vacation_days / MAX(0.5, parent_pto_days_used)
    school_absence_penalty REAL NOT NULL,         -- SAP weighted school absence penalty across children
    childcare_coverage_gain REAL NOT NULL,        -- CCG fraction of trip covering unsupervised vacation/weekend days
    per_child_impact_json TEXT NOT NULL,          -- JSON array of ChildTripImpact objects
    total_school_days_missed_across_children INTEGER NOT NULL CHECK (total_school_days_missed_across_children >= 0),
    max_single_child_school_days_missed INTEGER NOT NULL CHECK (max_single_child_school_days_missed >= 0),
    -- Explicit Mathematical Scoring Breakdown (0 to 100):
    vacation_utilization_score REAL NOT NULL CHECK (vacation_utilization_score BETWEEN 0.0 AND 100.0), -- VUS
    flight_bonus_value_score REAL NOT NULL CHECK (flight_bonus_value_score BETWEEN 0.0 AND 100.0),   -- FBVS
    combined_trip_optimization_score REAL NOT NULL CHECK (combined_trip_optimization_score BETWEEN 0.0 AND 100.0), -- CTOS
    explanation_summary_he TEXT NOT NULL,         -- Hebrew explanation of why this option maximizes vacation + bonus value
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_proposals_query_rank ON vacation_option_proposals(search_query_id, combined_trip_optimization_score DESC);
```

### 2.6 Backend Pydantic v2 & Frontend TypeScript Domain Models

#### Backend Pydantic v2 Schemas (`backend/app/schemas/domain.py`)
```python
from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class MoEFrameworkType(str, Enum):
    DAYCARE_SUPERVISED = "DAYCARE_SUPERVISED"   # מעונות יום מפוקחים (0-3, עד 8 באוגוסט)
    MUNICIPAL_GAN = "MUNICIPAL_GAN"             # גני ילדים רשמיים (3-6, עד 30 ביוני + ניצנים)
    ELEMENTARY_1_3 = "ELEMENTARY_1_3"           # יסודי כיתות א'-ג' (עד 30 ביוני + ניצנים)
    ELEMENTARY_4_6 = "ELEMENTARY_4_6"           # יסודי כיתות ד'-ו' (עד 30 ביוני)
    MIDDLE_SCHOOL_7_9 = "MIDDLE_SCHOOL_7_9"     # חטיבת ביניים ז'-ט' (חופשות יסודי + סיום 20 ביוני)
    HIGH_SCHOOL_10_12 = "HIGH_SCHOOL_10_12"     # תיכון י'-י"ב (סיום 20 ביוני + אסרו חג סוכות + בגרויות)
    SPECIAL_ED = "SPECIAL_ED"                   # חינוך מיוחד (עד 15 באוגוסט)
    RELIGIOUS_HAREDI = "RELIGIOUS_HAREDI"       # ממלכתי-דתי / חרדי (בין הזמנים וצומות)

class HolidayExtensionMode(str, Enum):
    NONE = "NONE"
    NITZANIM_CHAGIM_ONLY = "NITZANIM_CHAGIM_ONLY"
    NITZANIM_FULL_WITH_JULY = "NITZANIM_FULL_WITH_JULY"

class DateSelectionMode(str, Enum):
    SPECIFIC_DATES = "SPECIFIC_DATES"                         # R2 Mode 1: Specific / Flexible Dates
    MOE_VACATION_MAXIMIZATION = "MOE_VACATION_MAXIMIZATION"   # R2 Mode 2: Full School-Year MoE Vacation Optimizer
    HOLIDAY_DIRECT_INTENT = "HOLIDAY_DIRECT_INTENT"           # R2 Mode 3: Direct Holiday + Year Bonus Express ("חופשת פסח 2027")

class LoyaltyProgramCode(str, Enum):
    ELAL_MATMID = "ELAL_MATMID"
    BRITISH_AVIOS = "BRITISH_AVIOS"
    FLYING_BLUE = "FLYING_BLUE"
    UNITED_MILEAGEPLUS = "UNITED_MILEAGEPLUS"
    MILES_AND_MORE = "MILES_AND_MORE"
    DELTA_SKYMILES = "DELTA_SKYMILES"
    QANTAS_FREQUENT_FLYER = "QANTAS_FREQUENT_FLYER"
    AEGEAN_MILES_BONUS = "AEGEAN_MILES_BONUS"
    AMEX_MR_ISRAEL = "AMEX_MR_ISRAEL"
    ISRAELI_CC_TRAVEL_POINTS = "ISRAELI_CC_TRAVEL_POINTS"

class PassengerLoyaltyWallet(BaseModel):
    id: str
    passenger_id: str          # e.g. "ADULT_1", "ADULT_2", "CHILD_1", "FAMILY_POOL"
    passenger_name: str
    program_code: LoyaltyProgramCode
    available_points: int = Field(default=0, ge=0)
    can_pool_with_family: bool = False
    pool_group_id: Optional[str] = None
    transfer_ratio_to_airline: float = 1.0
    has_club_credit_card: bool = False
    companion_vouchers_count: int = 0
    point_valuation_cents: float = 1.5

class AirlineSelectionMode(str, Enum):
    EL_AL_ONLY = "EL_AL_ONLY"                                 # R3 Mode 1
    ALL_AIRLINES = "ALL_AIRLINES"                             # R3 Mode 2

class FulfillmentStrategy(str, Enum):
    FULL_BONUS_SAME_CABIN = "FULL_BONUS_SAME_CABIN"
    SPLIT_CABIN_BONUS = "SPLIT_CABIN_BONUS"
    HYBRID_BONUS_PLUS_CASH = "HYBRID_BONUS_PLUS_CASH"
    ONE_WAY_BONUS_ONE_WAY_CASH = "ONE_WAY_BONUS_ONE_WAY_CASH"
    CASH_AND_POINTS = "CASH_AND_POINTS"
    MULTI_CLUB_PER_PASSENGER_SPLIT = "MULTI_CLUB_PER_PASSENGER_SPLIT"
    COMMERCIAL_CASH_ONLY = "COMMERCIAL_CASH_ONLY"

class ChildFramework(BaseModel):
    id: str
    child_name: str = "ילד/ה"
    child_age_years: int = Field(ge=0, le=21)                 # Age of child (0-21)
    birth_date: Optional[date] = None                         # Optional exact birthdate
    passenger_Current_type: str = "CHILD"
    framework_type: Optional[MoEFrameworkType] = None         # Optional: only required when searching by vacations
    education_stream: str = "MAMLACHTI"
    school_week_days: int = Field(default=5, ge=5, le=6)
    holiday_extension_mode: HolidayExtensionMode = HolidayExtensionMode.NONE
    treat_camp_as_vacation: bool = True
    max_school_days_missed: int = Field(default=2, ge=0, le=14)
    absence_penalty_weight: float = 1.0
    bagrut_blackout_dates: List[date] = []

class FamilyProfile(BaseModel):
    id: str
    profile_name: str
    adults_count: int = Field(default=2, ge=1, le=6)
    workweek_type: str = "SUN_THU"
    erev_chag_pto_weight: float = 0.5
    chol_hamoed_pto_weight: float = 0.5
    annual_pto_budget: float = 14.0
    max_pto_per_trip: float = 5.0
    matmid_points_balance: int = 0
    has_flycard: bool = True
    flycard_tier: str = "FLY_CARD_PREMIUM"
    flycard_companion_vouchers: int = 0
    point_valuation_usd: float = 0.016
    preferred_currency: str = "USD"
    children: List[ChildFramework] = []
    passenger_loyalty_wallets: List[PassengerLoyaltyWallet] = []

class ElAlBonusAvailability(BaseModel):
    id: str
    origin_iata: str
    destination_iata: str
    direction: str  # "OUTBOUND" | "INBOUND"
    flight_number: str
    operating_carrier: str = "LY"
    flight_date: date
    departure_time_local: str
    arrival_time_local: str
    aircraft_type: Optional[str] = None
    economy_award_seats: int = 0
    economy_seats_is_two_plus: bool = False
    economy_rbd_code: str = "E"
    premium_award_seats: int = 0
    premium_seats_is_two_plus: bool = False
    premium_rbd_code: str = "P"
    business_award_seats: int = 0
    business_seats_is_two_plus: bool = False
    business_rbd_code: str = "I"
    award_zone: str = "ZONE_B"
    economy_points_per_pax: Optional[int] = None
    premium_points_per_pax: Optional[int] = None
    business_points_per_pax: Optional[int] = None
    flycard_promo_active: bool = False
    taxes_usd_per_pax: float = 0.0
    source_url: str = "https://www.elal.com/rbddataclients/"
    fetched_at: datetime
    expires_at: datetime

class PassengerTicketAllocation(BaseModel):
    passenger_label: str
    ticket_mode: str       # "ELAL_MATMID_BONUS" | "ELAL_CASH_AND_POINTS" | "COMMERCIAL_CASH"
    direction: str         # "ROUND_TRIP" | "OUTBOUND_ONLY" | "INBOUND_ONLY"
    cabin_class: str       # "ECONOMY" | "PREMIUM" | "BUSINESS"
    rbd_code: str          # "E" | "X" | "U" | "P" | "A" | "R" | "I" | "W" | "Y" ...
    points_used: int = 0
    cash_fare_usd: float = 0.0
    taxes_usd: float = 0.0

class ChildDayStatus(BaseModel):
    calendar_date: date
    state_code: str        # "VACATION" | "CAMP_OPTIONAL" | "WEEKEND" | "SCHOOL_FRIDAY" | "SCHOOL_END_OF_YEAR_WANING" | "SCHOOL_REGULAR" | "EXAM_BLACKOUT"
    psi_penalty: float
    label_he: str

class ChildTripImpact(BaseModel):
    child_id: str
    child_name: str
    framework_type: MoEFrameworkType
    official_vacation_days: int
    weekend_days: int
    nitzanim_days_overlapped: int
    bridge_school_days_missed: int
    weighted_absence_score: float
    within_allowed_absence_limit: bool
    daily_breakdown: List[ChildDayStatus]

class VacationOptionProposal(BaseModel):
    id: str
    search_query_id: str
    associated_holiday_codes: List[str]
    window_set_type: str
    total_vacation_days: int
    parent_pto_days_used: float
    pto_efficiency_ratio: float           # PER
    school_absence_penalty: float         # SAP
    childcare_coverage_gain: float        # CCG
    per_child_impact: List[ChildTripImpact]
    total_school_days_missed_across_children: int
    max_single_child_school_days_missed: int
    vacation_utilization_score: float     # VUS (0..100)
    flight_bonus_value_score: float       # FBVS (0..100)
    combined_trip_optimization_score: float # CTOS (0..100)
    explanation_summary_he: str
```

#### Frontend TypeScript Interfaces (`frontend/src/types/domain.ts`)
```typescript
export type MoEFrameworkType =
  | 'DAYCARE_SUPERVISED'
  | 'MUNICIPAL_GAN'
  | 'ELEMENTARY_1_3'
  | 'ELEMENTARY_4_6'
  | 'MIDDLE_SCHOOL_7_9'
  | 'HIGH_SCHOOL_10_12'
  | 'SPECIAL_ED'
  | 'RELIGIOUS_HAREDI';

export type DateSelectionMode =
  | 'SPECIFIC_DATES'
  | 'MOE_VACATION_MAXIMIZATION'
  | 'HOLIDAY_DIRECT_INTENT';
export type AirlineSelectionMode = 'EL_AL_ONLY' | 'ALL_AIRLINES';

export type LoyaltyProgramCode =
  | 'ELAL_MATMID'
  | 'BRITISH_AVIOS'
  | 'FLYING_BLUE'
  | 'UNITED_MILEAGEPLUS'
  | 'MILES_AND_MORE'
  | 'DELTA_SKYMILES'
  | 'QANTAS_FREQUENT_FLYER'
  | 'AEGEAN_MILES_BONUS'
  | 'AMEX_MR_ISRAEL'
  | 'ISRAELI_CC_TRAVEL_POINTS';

export type FulfillmentStrategy =
  | 'FULL_BONUS_SAME_CABIN'
  | 'SPLIT_CABIN_BONUS'
  | 'HYBRID_BONUS_PLUS_CASH'
  | 'ONE_WAY_BONUS_ONE_WAY_CASH'
  | 'CASH_AND_POINTS'
  | 'MULTI_CLUB_PER_PASSENGER_SPLIT'
  | 'COMMERCIAL_CASH_ONLY';
```

### 2.7 Internal REST API Endpoints (`v1`)

| HTTP Method & Route | Request Payload / Query Params | Response Type | Requirement & Service Mapping |
|---|---|---|---|
| `GET /api/v1/profile` | `?profile_id=...` | `FamilyProfile` | Loads household profile, children's MoE frameworks, PTO rules, and per-passenger multi-club loyalty wallets (`storage_cache`). |
| `PUT /api/v1/profile` | `FamilyProfile` | `FamilyProfile` | Creates/updates multi-child MoE framework configurations and per-passenger loyalty wallets across multiple clubs (`R2`, `R3`). |
| `GET /api/v1/moe-calendar/{school_year}` | `?profile_id=...` | `MoECalendarTimelineResponse` | Returns `MoEVacationWindow[]` for any requested school year (`2025-2026`, `2026-2027`, `2027-2028`, ...), auto-generating or syncing future years if needed (`R2`). |
| `POST /api/v1/moe-calendar/sync/{school_year}` | `{ force_remote_check: bool }` | `MoECalendarSyncStatus` | **Annual Auto-Updater**: Checks official Ministry of Education Director General Circulars (`חוזרי מנכ"ל משרד החינוך`) and `Hebcal (i=on)` / `pyluach` statutory rules to automatically populate or refresh vacation dates for the target year (`R2`). |
| `POST /api/v1/elal-bonus/sync` | `{ destinations, start_date, end_date, force_refresh }` | `ElAlBonusSyncStatus` | Expands metro IATAs and fetches live Classic Award seats from `https://www.elal.com/rbddataclients/` (`R3.2`). |
| `GET /api/v1/elal-bonus/availability` | `?destination=FCO&start_date=...&end_date=...` | `ElAlBonusAvailability[]` | Returns cached/live `rbddataclients` Economy (`E`/`X`/`U`), Premium (`P`/`A`/`R`), and Business (`I`/`W`) award seats (`R3.2`). |
| `POST /api/v1/vacations/search` | `FlightSearchQuery` | `VacationOptionProposal[]` | Unified search orchestrator handling Date Modes 1 (`SPECIFIC_DATES`), 2 (`MOE_VACATION_MAXIMIZATION`), & 3 (`HOLIDAY_DIRECT_INTENT` — structured specific holiday/vacation & year maximizer) crossed with Airline Modes 1 & 2 and per-passenger multi-club point wallets (`R2`, `R3`). |
| `POST /api/v1/vacations/compare` | `{ proposal_ids: string[] }` | `VacationComparisonMatrix` | Generates side-by-side comparison matrix across per-passenger points/clubs, cash, PTO efficiency, and school absences (`R2`, `R3.3`). |

---

## 3. R2 — Flight Date Selection Modes & Israeli Ministry of Education Vacation Maximization

### 3.1 Date Selection Mode 1: Specific & Flexible Dates (`SPECIFIC_DATES`)

Mode 1 serves families who have target travel dates in mind or want to search around a specific family event:
1. **Exact or Flexible Date Window**:
   - **Exact Dates**: Fixed `specific_departure_date` ($D_{\text{dep}}$) and `specific_return_date` ($D_{\text{ret}}$).
   - **Flexible Window ($\pm N$ Days)**: $D_{\text{dep}} \pm k$ and $D_{\text{ret}} \pm k$ where $k \in \{0, 1, 2, 3, 5, 7\}$, constrained by desired trip length $[L_{\min}, L_{\max}]$ nights.
2. **Full Family Passenger Composition & Optional Framework Input**:
   - **Passenger Counts & Children's Ages**: User specifies `adults` ($1\text{–}6$, age $16+$) and each child's **age (`child_age_years`, $0\text{–}18$)** (which automatically determines airline ticket category: `<2` infant on lap/seat, `2–11` child fare, `12–15` youth).
   - **Educational Framework is Strictly Optional in Mode 1**: When searching by specific dates (`SPECIFIC_DATES`), entering which educational framework (`מסגרת לימודים`) each child attends is **completely optional and not required**. Only if the user chooses to search by vacations (`Mode 2` or `Mode 3`)—or optionally enables framework matching—does the user select each child's educational framework (`מעון`, `גן`, `יסודי א'-ג'`, `יסודי ד'-ו'`, `חט"ב`, `תיכון`) so the system can tailor the exact vacation dates (with smart default framework suggestions based on the child's age!).
3. **Optional MoE Calendar Impact Overlay in Mode 1**:
   - If the user has optionally filled in their children's frameworks, `MoECalendarService` overlays the household's Israeli MoE frameworks onto $[D_{\text{dep}}, D_{\text{ret}}]$; if not, Mode 1 searches flights purely by the chosen dates and passenger ages without requiring any school framework input.

### 3.2 Date Selection Mode 2: Around Children's Vacations Across Israeli MoE Frameworks (`MOE_VACATION_MAXIMIZATION`)

Mode 2 models the complete taxonomy of **Israeli Ministry of Education (`משרד החינוך`)** educational frameworks and schedule modifiers:

| Framework Enum Code | Hebrew Framework Name | Ages / Grades | Official Summer Start | School Week (`5_DAY` vs `6_DAY`) | Holiday Extensions (`Nitzanim`) & Special Schedule Rules |
|---|---|---|---|---|---|
| `DAYCARE_SUPERVISED` | מעונות יום ומשפחתונים בפיקוח | Ages 0–3 | **Aug 9** (ends **Aug 8**) | 6-day (short Fri) | Minimal year-round holidays (no pre-Pesach week off; summer break only Aug 9–31). |
| `MUNICIPAL_GAN` | גני ילדים רשמיים (טרום-טרום, טרום, חובה) | Ages 3–6 | **Jul 1** (ends **Jun 30**) | 6-day (Fri 07:30–12:45) | **Isru Chag** & **Lag BaOmer** are regular school days. Eligible for **Nitzanim**: 5 days in Hanukkah, 5 days pre-Pesach, and **בית הספר של החופש הגדול** (all of July, Jul 1–30/31). |
| `ELEMENTARY_1_3` | בית ספר יסודי (כיתות א'–ג') | Grades 1–3 (Ages 6–9) | **Jul 1** (ends **Jun 30**) | 5-day or 6-day | **Isru Chag** & **Lag BaOmer** are regular school days. Eligible for **Nitzanim** in Hanukkah (5 days), pre-Pesach (5 days), and July (**בית הספר של החופש הגדול**, Jul 1–30/31). |
| `ELEMENTARY_4_6` | בית ספר יסודי (כיתות ד'–ו') | Grades 4–6 (Ages 9–12) | **Jul 1** (ends **Jun 30**) | 5-day or 6-day | **Isru Chag** & **Lag BaOmer** are regular school days. Not covered by standard Nitzanim holiday camps (optional municipal "Kayitz Plus" in summer). |
| `MIDDLE_SCHOOL_7_9` | חטיבת ביניים (כיתות ז'–ט') | Grades 7–9 (Ages 12–15) | **Jun 21** (ends **Jun 20**; or Jun 18/19 in 2026) | Often 5-day (Fri off) | **Crucial Hybrid Rule (Circulars `schedule-o` & `0363`)**: Follows the **Elementary schedule during the year** (**Isru Chag Sukkot** and **Lag BaOmer** are **regular school days**!), **EXCEPT** ends the school year 10 days early on **June 20** alongside High Schools! |
| `HIGH_SCHOOL_10_12` | חטיבה עליונה / תיכון (כיתות י'–י"ב) | Grades 10–12 (Ages 15–18) | **Jun 21** (ends **Jun 20**; or Jun 18/19 in 2026) | Often 5-day (Fri off) | Governed by Upper Secondary Circulars (`0346` for תשפ"ו, `0364` for תשפ"ז). Ends **June 20**. **Isru Chag Sukkot is an official VACATION day**. **Lag BaOmer** is a **VACATION day in תשפ"ו (May 5, 2026)** and a regular school day in תשפ"ז (May 25, 2027). Supports individual **Bagrut exam blackout dates**. |
| `SPECIAL_ED` | חינוך מיוחד | Eligible ages 3–21 | **Aug 16** (ends **Aug 15**) | 5-day or 6-day | Operates extended year and holiday frameworks during Sukkot, Hanukkah, Pesach, and July through August 15. |
| `RELIGIOUS_HAREDI` | ממלכתי-דתי / מוסדות חרדיים | All ages | Custom / Bein HaZmanim | 5-day or 6-day | Supports Fast Day toggles (`צום גדליה`, `י' בטבת`, `תענית אסתר`, `י"ז בתמוז`) and Bein HaZmanim (`בין הזמנים`: Nissan, Av, Tishrei). |

### 3.2b Date Selection Mode 3: Specific Holiday / Vacation & Year Maximizer (`HOLIDAY_DIRECT_INTENT`)

In addition to Mode 1 (`SPECIFIC_DATES`) and Mode 2 (`MOE_VACATION_MAXIMIZATION` across the full school year), the application supports **Mode 3 (`HOLIDAY_DIRECT_INTENT` — חיפוש ממוקד לפי חג/חופשה ספציפיים ושנה למקסום ימי החופש)**:
- **Structured Holiday & Year Selection Controls (No Free-Text Required)**:
  - The user selects a specific holiday/vacation and target year from structured selectors:
    1. **בחירת חג / חופשה (`direct_holiday_code`)**: Dropdown / pill selector with all Ministry of Education vacations (`חופשת פסח`, `חופשת סוכות`, `גשר כיפור–סוכות`, `חופשת חנוכה`, `ראש השנה`, `פורים`, `שבועות`, `יום העצמאות`, `החופש הגדול — 20–30 ביוני`, `החופש הגדול — יולי`, `החופש הגדול — אוגוסט`).
    2. **בחירת שנה (`direct_target_year`)**: Dropdown / pill selector (`2026`, `2027`, `2028`, ...).
    3. **טווח לילות וגמישות ימי גשר (`min_trip_nights`–`max_trip_nights`, `max_bridge_days_shift`)**: Configures how many nights the family wants to travel and how many bridge days ($\pm 0..3$ ימי גשר) around that holiday are allowed to maximize vacation days.
- **Automated Vacation Maximization & Bonus Ticket Pipeline in Mode 3**:
  1. **Holiday & Year Resolution**: Maps `(direct_holiday_code, direct_target_year)` to the exact Ministry of Education vacation window for that holiday in that year across the children's configured frameworks (for example, selecting `חופשת פסח` + `2027` resolves to `Tue, Apr 13 – Wed, Apr 28, 2027`, automatically distinguishing the Nitzanim week `Apr 13–19` from the uncovered week `Apr 20–28`). If the selected year is a future year not yet cached, triggers the **Annual MoE Calendar Auto-Updater** automatically.
  2. **Vacation Maximization Around the Selected Holiday**: Generates all candidate sub-windows (`[min_trip_nights, max_trip_nights]`) inside and around that specific holiday (including $\pm 0..3$ bridge days before the holiday starts or after it ends) and ranks them by how effectively they maximize total vacation days relative to parent PTO (`PER`), Nitzanim coverage (`CCG`), and minimal school absences (`SAP`).
  3. **Bonus Ticket & Flight Matching**: Scans `https://www.elal.com/rbddataclients/` (when focusing on El Al bonus tickets) or all airlines across those optimal holiday sub-windows, matches available seats against each passenger's multi-club point wallets (`passenger_loyalty_wallets`), and displays the ranked vacation options for that holiday!

### 3.3 Authoritative MoE Holiday Calendars: תשפ"ו (2025–2026) & תשפ"ז (2026–2027)

#### Table 3.3A — School Year תשפ"ו (2025–2026) Verified Ministry of Education Calendar
*(Source: MoE Director General Circulars `schedule-o` [K–9] & `0346` [Grades 10–12])*

| Holiday / Event | Hebrew Dates (תשפ"ו) | Vacation Dates (Inclusive) | School Resumes | Framework Divergences, Nitzanim & Airport Constraints |
|---|---|---|---|---|
| **School Year Start** | ח' באלול תשפ"ה | — | **Mon, Sep 1, 2025** | All frameworks start Mon, Sep 1, 2025. |
| **Rosh Hashanah (ראש השנה)** | כ"ט באלול תשפ"ה – ב' בתשרי תשפ"ו | **Mon, Sep 22 – Wed, Sep 24, 2025** | **Thu, Sep 25, 2025** | Preceded by Fri/Sat Sep 19–20; taking **Sun, Sep 21** as a 1-day bridge creates a **6-day trip (Sep 19–24)** for 1 school day missed! |
| **Yom Kippur + Bridge + Sukkot (יום הכיפורים, גשר, וסוכות)** | ט' בתשרי – כ"ב בתשרי תשפ"ו | **Wed, Oct 1 – Tue, Oct 14, 2025** *(K–9)*<br>**Wed, Oct 1 – Wed, Oct 15, 2025** *(10–12)* | **Wed, Oct 15, 2025** *(K–9)*<br>**Thu, Oct 16, 2025** *(10–12)* | Includes the 3-day **Yom Kippur–Sukkot Bridge** (Oct 3–5). **Isru Chag Sukkot (Wed, Oct 15, 2025)** is a **school day for Gan, Elementary (1–6), and Middle School (7–9)**, and a **vacation day ONLY for High School (10–12)**. `TLV` airport closed Oct 1 (~13:00) to Oct 2 (~22:30). |
| **Hanukkah (חנוכה)** | כ"ו בכסלו – ב' בטבת תשפ"ו | **Tue, Dec 16 – Mon, Dec 22, 2025** | **Tue, Dec 23, 2025** | **Nitzanim (`בית הספר של החגים`)** operates 5 days (Tue–Thu Dec 16–18 & Sun–Mon Dec 21–22) for `MUNICIPAL_GAN` & `ELEMENTARY_1_3`. |
| **Purim (פורים)** | י"ד–ט"ו באדר תשפ"ו | **Tue, Mar 3 – Wed, Mar 4, 2026** | **Thu, Mar 5, 2026** | Ta'anit Esther (Mon, Mar 2) is a regular school day. Adding **Thu, Mar 5** (+ Fri Mar 6) creates a **5-day trip (Mar 3–7)** for 1–2 bridge days. |
| **Pesach (פסח)** | ו' בניסן – כ"א בניסן תשפ"ו | **Tue, Mar 24 – Wed, Apr 8, 2026** | **Thu, Apr 9, 2026** | 16-day break! **Isru Chag Pesach (Thu, Apr 9)** is a **regular school day for ALL frameworks**. **Nitzanim** operates 5 days pre-Seder (Tue–Thu Mar 24–26, Sun–Mon Mar 29–30). **Uncovered by Nitzanim**: Tue Mar 31 – Wed Apr 8. |
| **Yom HaZikaron & Yom HaAtzmaut** | ד'–ה' באייר תשפ"ו | **Tue, Apr 21 (Ends 12:00) – Wed, Apr 22, 2026 (Off)** | **Thu, Apr 23, 2026** | Official vacation day on Wed, Apr 22, 2026. |
| **Lag BaOmer (ל"ג בעומר)** | י"ח באייר תשפ"ו | **Tue, May 5, 2026** *(Vacation ONLY for Grades 10–12)* | **Wed, May 6, 2026** | **Regular school day** for `MUNICIPAL_GAN`, `ELEMENTARY_1_6`, and `MIDDLE_SCHOOL_7_9`. **Vacation day ONLY for `HIGH_SCHOOL_10_12`**. |
| **Shavuot (שבועות)** | ה'–ו' בסיוון תשפ"ו | **Thu, May 21 – Fri, May 22, 2026** *(+ Sat May 23)* | **Sun, May 24, 2026** | 3-day Thu–Sat holiday weekend across all frameworks. |
| **Summer Break Start — Middle & High (`7–12`)** | ג'/ד' בתמוז תשפ"ו | **Fri, Jun 19, 2026** (`5_DAY` last day: **Thu, Jun 18**; `6_DAY` last day: **Fri, Jun 19**) | **Tue, Sep 1, 2026** | Because June 20, 2026 falls on Saturday, 5-day Middle/High schools finish **Thu, June 18, 2026**—creating a **12-day pre-July arbitrage window (Jun 19–30)**! |
| **Summer Break Start — Gan & Elementary (`K–6`)** | ט"ו בתמוז תשפ"ו | **Wed, Jul 1, 2026** *(Last school day: Tue, Jun 30, 2026)* | **Tue, Sep 1, 2026** | **Nitzanim Summer School (`בית הספר של החופש הגדול`)** covers **all of July (Jul 1–30/31, 2026)** for Gan & Grades 1–3. **August 1–31** has zero public camps. |

#### Table 3.3B — School Year תשפ"ז (2026–2027) Verified Ministry of Education Calendar
*(Source: MoE Director General Circulars `0363` [K–9] & `0364` [Grades 10–12])*

| Holiday / Event | Hebrew Dates (תשפ"ז) | Vacation Dates (Inclusive) | School Resumes | Framework Divergences, Nitzanim & Airport Constraints |
|---|---|---|---|---|
| **School Year Start** | י"ט באלול תשפ"ו | — | **Tue, Sep 1, 2026** | All frameworks start Tue, Sep 1, 2026. |
| **Rosh Hashanah (ראש השנה)** | כ"ט באלול תשפ"ו – ב' בתשרי תשפ"ז | **Fri, Sep 11 – Sun, Sep 13, 2026** | **Mon, Sep 14, 2026** | 3-day Fri–Sun holiday weekend across all frameworks. |
| **Yom Kippur + Bridge + Sukkot (יום הכיפורים, גשר, וסוכות)** | ט' בתשרי – כ"א/כ"ב בתשרי תשפ"ז | **Sun, Sep 20 – Sat, Oct 3, 2026** *(K–9)*<br>**Sun, Sep 20 – Sun, Oct 4, 2026** *(10–12)* | **Sun, Oct 4, 2026** *(K–9)*<br>**Mon, Oct 5, 2026** *(10–12)* | 14–15 days continuous vacation (16–17 days including Fri/Sat Sep 18–19 before!). Includes the 3-day **Yom Kippur–Sukkot Bridge** (Tue Sep 22 – Thu Sep 24). **Isru Chag Sukkot (Sun, Oct 4, 2026)** is a **school day for K–Grade 9** and a **vacation day ONLY for High School (10–12)**. `TLV` airport closed Sep 20 (~13:00) to Sep 21 (~22:30). |
| **Hanukkah (חנוכה)** | כ"ו בכסלו – ב' בטבת תשפ"ז | **Sun, Dec 6 – Sat, Dec 12, 2026** | **Sun, Dec 13, 2026** | Full Sun–Sat week off (plus Fri Dec 4 for 5-day schools = **9-day window Dec 4–12**). **Nitzanim** operates 5 days (Sun Dec 6 – Thu Dec 10) for Gan & Grades 1–3. |
| **Purim (פורים)** | י"ד–ט"ו באדר ב' תשפ"ז | **Tue, Mar 23 – Wed, Mar 24, 2027** | **Thu, Mar 25, 2027** | Ta'anit Esther (Mon, Mar 22) is a regular school day. Adding **Thu, Mar 25** (+ Fri/Sat Mar 26–27) creates a **5-day trip (Mar 23–27)** for 1 bridge day! |
| **Pesach (פסח)** | ו' בניסן – כ"א בניסן תשפ"ז | **Tue, Apr 13 – Wed, Apr 28, 2027** | **Thu, Apr 29, 2027** | 16-day break! **Isru Chag Pesach (Thu, Apr 29)** is a **regular school day for ALL frameworks**. **Nitzanim** operates 5 days pre-Seder (Tue–Thu Apr 13–15, Sun–Mon Apr 18–19). **Uncovered by Nitzanim**: Tue Apr 20 – Wed Apr 28, 2027 (9 continuous uncovered days!). |
| **Yom HaZikaron & Yom HaAtzmaut** | ד'–ה' באייר תשפ"ז | **Tue, May 11 (Ends 12:00) – Wed, May 12, 2027 (Off)** | **Thu, May 13, 2027** | Official vacation day on Wed, May 12, 2027. |
| **Lag BaOmer (ל"ג בעומר)** | י"ח באייר תשפ"ז | *Tue, May 25, 2027 (Regular school day)* | — | **Regular learning day across ALL frameworks (`K–12`)** per Circulars `0363` & `0364` (unlike תשפ"ו!). |
| **Shavuot (שבועות)** | ה'–ו' בסיוון תשפ"ז | **Thu, Jun 10 – Fri, Jun 11, 2027** *(+ Sat Jun 12)* | **Sun, Jun 13, 2027** | 3-day Thu–Sat holiday weekend across all frameworks. |
| **Summer Break Start — Middle & High (`7–12`)** | ט"ו בסיוון תשפ"ז | **Mon, Jun 21, 2027** *(Last school day: Sun, Jun 20, 2027)* | **Wed, Sep 1, 2027** | Middle (`7–9`) and High Schools (`10–12`) finish **Sun, June 20, 2027**. |
| **Summer Break Start — Gan & Elementary (`K–6`)** | כ"ה בסיוון תשפ"ז | **Thu, Jul 1, 2027** *(Last school day: Wed, Jun 30, 2027)* | **Wed, Sep 1, 2027** | **Nitzanim Summer School (`בית הספר של החופש הגדול`)** runs **Jul 1 – Jul 30, 2027** (Sun–Thu) for Gan & Grades 1–3. |

### 3.4 3-Layer Calendar Data Architecture, Annual Auto-Updater & JSON Schema

Because `data.gov.il` does not publish a dataset for Ministry of Education school vacations, `MoECalendarService` combines a **3-Layer Calendar Data Architecture** with an **Automatic Annual Calendar Updater (`MoECalendarAutoUpdaterService`)** so the system automatically stays current every year (`תשפ"ו`, `תשפ"ז`, `תשפ"ח`, `תשפ"ט`, and beyond):
1. **Layer 1 — Bundled & Auto-Synced Official MoE Circular Rule Packs (`OFFICIAL_MOE_CIRCULAR` / `AUTO_SYNCED_CIRCULAR`)**:
   - Pre-seeded with verified files `calendars/moe_5786_2025_2026.json` and `calendars/moe_5787_2026_2027.json` encoding Circulars `schedule-o`, `0346`, `0363`, and `0364`.
   - **Scheduled Annual Official Circular SyncJob (`APScheduler` + `/api/v1/moe-calendar/sync/{school_year}`)**: Automatically checks the Ministry of Education Director General Circulars portal (`חוזרי מנכ"ל משרד החינוך — לוח החופשות והחגים`, `apps.education.gov.il/mankal` / `gov.il`) for newly published school-year circulars, parses the official holiday tables across all frameworks (`K–12`), updates `moe_vacation_windows` in SQLite, and saves `calendars/moe_<hebrew_year>_<greg_year>.json`.
2. **Layer 2 — Deterministic Hebrew-to-Gregorian Statutory Rule Projector (`HEBREW_RULE_PROJECTED`)**:
   - Because El Al opens flights and `rbddataclients` bonus seats **11–12 months in advance** (often *before* the Ministry of Education publishes the next school year's circular in spring), whenever a user searches a future year (e.g. Mode 3: *"חופשת פסח בשנת 2028"*), `HebrewCalendarRuleProjector` automatically computes that year's exact MoE calendar using `pyluach` / `hdate` + `Hebcal REST API (i=on)` and the invariant MoE statutory rules (Sept 1 start shifted to Sept 2 if Shabbat; כ"ט אלול–ב' תשרי Rosh Hashanah; ט'–י' תשרי Yom Kippur + י"א–י"ד תשרי Kippur–Sukkot bridge; ט"ו–כ"א/כ"ב תשרי Sukkot; כ"ה כסלו–ב'/ג' טבת Hanukkah + 5 Sun–Thu Nitzanim days; י"ד–ט"ו אדר Purim; ו'–כ"א ניסן Pesach + 5 Sun–Thu Nitzanim days; ה' אייר Yom HaAtzmaut with early/late Shabbat shift rules; י"ח אייר Lag BaOmer; ה'–ו' סיוון Shavuot; June 20 Middle/High end shifted to June 18/19 if Shabbat; June 30 Gan/Elementary end + July Nitzanim; Aug 8 Daycare end).
   - Once the official MoE circular is published later in the year, the background updater reconciles any minor circular adjustments automatically.
3. **Layer 3 — Municipal Nitzanim Override & `.ics` Calendar Export (`USER_MUNICIPAL_OVERRIDE`)**: Allows parents to adjust local municipal Nitzanim camp dates by 1 click, add school-specific "teacher study days" (`ימי היערכות`), and export chosen vacation proposals to `.ics`.

#### Authoritative JSON Schema (`calendars/schema/moe_calendar.schema.json`)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "MinistryOfEducationSchoolYearCalendar",
  "type": "object",
  "required": ["school_year_hebrew", "school_year_gregorian", "circular_ids", "frameworks", "periods"],
  "properties": {
    "school_year_hebrew": { "type": "string", "example": "תשפ\"ז" },
    "school_year_gregorian": { "type": "string", "example": "2026-2027" },
    "circular_ids": {
      "type": "array",
      "items": { "type": "string" },
      "example": ["0363", "0364"]
    },
    "frameworks": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["label_he", "grades", "start_date", "end_date_6day", "end_date_5day", "nitzanim_eligible"],
        "properties": {
          "label_he": { "type": "string" },
          "grades": { "type": "string" },
          "start_date": { "type": "string", "format": "date" },
          "end_date_6day": { "type": "string", "format": "date" },
          "end_date_5day": { "type": "string", "format": "date" },
          "nitzanim_eligible": { "type": "boolean" }
        }
      }
    },
    "periods": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name_he", "name_en", "start_date", "end_date", "resume_date", "applies_to_frameworks"],
        "properties": {
          "id": { "type": "string", "example": "sukkot_5787" },
          "name_he": { "type": "string", "example": "יום הכיפורים, גשר וחג הסוכות" },
          "name_en": { "type": "string", "example": "Yom Kippur, Bridge & Sukkot" },
          "start_date": { "type": "string", "format": "date" },
          "end_date": { "type": "string", "format": "date" },
          "resume_date": { "type": "string", "format": "date" },
          "applies_to_frameworks": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "DAYCARE_SUPERVISED",
                "MUNICIPAL_GAN",
                "ELEMENTARY_1_3",
                "ELEMENTARY_4_6",
                "MIDDLE_SCHOOL_7_9",
                "HIGH_SCHOOL_10_12",
                "SPECIAL_ED",
                "RELIGIOUS_HAREDI"
              ]
            }
          },
          "framework_overrides": {
            "type": "object",
            "additionalProperties": {
              "type": "object",
              "properties": {
                "end_date": { "type": "string", "format": "date" },
                "resume_date": { "type": "string", "format": "date" }
              }
            }
          },
          "nitzanim_window": {
            "type": "object",
            "nullable": true,
            "properties": {
              "active": { "type": "boolean" },
              "program_name_he": { "type": "string", "example": "בית הספר של החגים - ניצנים" },
              "start_date": { "type": "string", "format": "date" },
              "end_date": { "type": "string", "format": "date" },
              "operating_days_count": { "type": "integer", "example": 5 },
              "hours_base": { "type": "string", "example": "08:00-13:00" },
              "uncovered_vacation_dates": {
                "type": "array",
                "items": { "type": "string", "format": "date" }
              }
            }
          },
          "tlv_airport_restrictions": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "start_iso": { "type": "string" },
                "end_iso": { "type": "string" },
                "reason": { "type": "string", "example": "Yom Kippur Ben Gurion Airport total shutdown" }
              }
            }
          }
        }
      }
    }
  }
}
```

### 3.5 Formal Vacation Utilization Maximization Algorithm & Mathematical Scoring (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`)

#### Step 1 — Daily Multi-Child & Parent Status Vectorization
For every calendar date $d$ in the school year $[T_{\text{start}}, T_{\text{end}}]$:
1. **Parent PTO Cost $P(d) \in \{0.0, 0.5, 1.0\}$**:
   - $P(d) = 0.0$ on Friday and Saturday (for standard Sun–Thu Israeli workweek) and on statutory Israeli public holidays (`ראש השנה`, `יום כיפור`, `חג ראשון של סוכות`, `שמחת תורה`, `חג ראשון ושביעי של פסח`, `יום העצמאות`, `שבועות`).
   - $P(d) = 0.5$ (configurable to $0.0, 0.5, 1.0$) on Erev Chag (`ערב חג`) and Chol HaMoed (`חול המועד`).
   - $P(d) = 1.0$ on regular Sun–Thu workdays (including Hanukkah, Purim, Isru Chag, and July/August).
2. **Child Daily State $S_c(d)$ and Absence Penalty Weight $\psi(S_c(d))$ for Child $c \in \{1..C\}$**:
   - `VACATION` ($\psi = 0.00$): Official MoE vacation with no active Nitzanim camp.
   - `CAMP_OPTIONAL` ($\psi = 0.15$ if `treat_camp_as_vacation=True`, else $0.75$): Official MoE vacation day where child $c$ is enrolled in **Nitzanim** (`בית הספר של החגים` or `בית הספר של החופש הגדול`). Allows parents to choose between traveling *during* camp or targeting *uncovered* vacation days (e.g., April 20–28 in Pesach or August) when parents have zero childcare!
   - `SCHOOL_FRIDAY` ($\psi = 0.35$): Short Friday learning day in a `6_DAY` framework ($\psi = 0.00$ in a `5_DAY` framework).
   - `SCHOOL_END_OF_YEAR_WANING` ($\psi = 0.50$): June 21–30 in `MUNICIPAL_GAN`, `ELEMENTARY_1_3`, and `ELEMENTARY_4_6` (after grades are finalized and Middle/High schoolers are already on summer break).
   - `SCHOOL_REGULAR` ($\psi = 1.00$): Standard Sun–Thu instructional day.
   - `EXAM_BLACKOUT` ($\psi = \infty$): High-school Bagrut exam date (disqualifies candidate window if overlapped).

#### Step 2 — Multi-Child Vacation Set Operations ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$)
1. **Strict Intersection Set ($\mathcal{I}$)**:
   $$\mathcal{I} = \big\{\, d \;\big|\; \forall c \in \{1..C\},\; S_c(d) = \text{VACATION} \,\big\}$$
   *(Every child in the family is off school AND has no camp—highest urgency for family childcare coverage).*
2. **Camp-Adjusted Intersection Set ($\mathcal{I}_{\text{camp}}$)**:
   $$\mathcal{I}_{\text{camp}} = \big\{\, d \;\big|\; \forall c \in \{1..C\},\; S_c(d) \in \{\text{VACATION}, \text{CAMP\_OPTIONAL}\} \,\big\}$$
   *(Every child is on official MoE vacation, including Nitzanim days).*
3. **Framework-Delta Union Set ($\mathcal{U}$)**:
   $$\mathcal{U} = \big\{\, d \;\big|\; \exists c \in \{1..C\},\; S_c(d) \in \{\text{VACATION}, \text{CAMP\_OPTIONAL}\} \,\big\}$$
   *(Captures cross-framework arbitrage windows such as **June 20–30**, where Middle/High schoolers are on vacation and Elementary/Gan children only miss low-weight waning days before July peak airfares).*

#### Step 3 — Bridge-Day ("Yemei Gesher" / ימי גשר) Window Expansion
1. **Cluster Merging**: Any two non-school intervals (e.g., a holiday and a Fri–Sat weekend, or Yom Kippur and Sukkot) separated by $\le B_{\max}$ regular days (default $B_{\max} = 3$) are merged into a **Bridgeable Macro-Window** $[a, b]$.
2. **Boundary Shifting**: Candidate trip windows $W = [d_{\text{dep}}, d_{\text{ret}}]$ are generated by shifting boundaries within:
   $$d_{\text{dep}} \in [a - B_{\max},\; b], \qquad d_{\text{ret}} \in [a,\; b + B_{\max}]$$
   subject to $L_{\min} \le D_{\text{total}}(W) \le L_{\max}$, max parent PTO budget $\text{PTO}(W) \le P_{\max}$, max per-child school days missed $\le A_{\max, c}$, and `TLV` Yom Kippur / El Al Shabbat operational windows.

#### Step 4 — Explicit Mathematical Scoring Formulas (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`)
For a candidate window $W = [d_{\text{dep}}, d_{\text{ret}}]$ of total calendar days $D_{\text{total}}(W) = d_{\text{ret}} - d_{\text{dep}} + 1$:

1. **Parent PTO Cost & PTO Efficiency Ratio (`PER`)**:
   $$\text{PTO}(W) = \sum_{d \in W} P(d), \qquad \text{PER}(W) = \frac{D_{\text{total}}(W)}{\max(\text{PTO}(W),\; 0.5)}$$
2. **Family School Absence Penalty (`SAP`)**:
   $$\text{SAP}(W) = \frac{1}{C} \sum_{c=1}^{C} \sum_{d \in W} \omega_c \cdot \psi(S_c(d))$$
   where framework criticality weight $\omega_c$ is: `DAYCARE_SUPERVISED` / `MUNICIPAL_GAN` $= 0.25$, `ELEMENTARY_1_3` $= 0.50$, `ELEMENTARY_4_6` $= 0.75$, `MIDDLE_SCHOOL_7_9` $= 1.00$, `HIGH_SCHOOL_10_12` $= 1.35$.
3. **Childcare Coverage Gain (`CCG`)**:
   $$\text{CCG}(W) = \frac{1}{C \cdot D_{\text{total}}(W)} \sum_{c=1}^{C} \sum_{d \in W} \mathbb{I}\big(S_c(d) = \text{VACATION} \lor \text{is\_weekend}(d)\big)$$
4. **Vacation Utilization Score (`VUS` $\in [0, 100]$)**:
   $$\text{VUS}(W) = \text{clamp}_{[0,100]}\!\left( 100 \cdot \left[ \alpha \cdot \min\!\left(\frac{\text{PER}(W)}{4.0},\; 1.0\right) + \beta \cdot \text{CCG}(W) - \gamma \cdot \frac{\text{SAP}(W)}{D_{\text{total}}(W)} \right] \right)$$
   with default weights $\alpha = 0.60$, $\beta = 0.40$, $\gamma = 0.35$.
5. **Flight Price / El Al Bonus Value Score (`FBVS` $\in [0, 100]$)**:
   - **Commercial Cash Mode**:
     $$\text{FBVS}_{\text{cash}}(F) = 100 \cdot \left(1 - \frac{\text{Cost}_{\text{total}}(F) - \text{Cost}_{\min}}{\max(\text{Cost}_{\max} - \text{Cost}_{\min},\; 1)}\right) - \text{Penalty}_{\text{stops/times}}(F)$$
   - **El Al Bonus Ticket Mode (`rbddataclients`)**:
     $$\text{FBVS}_{\text{bonus}}(F) = 100 \cdot \left( 0.50 \cdot \frac{N_{\text{seats\_covered\_by\_bonus}}}{N_{\text{passengers}}} + 0.30 \cdot \min\!\left(\frac{\text{CPP}(F)}{2.0\text{¢}},\; 1.0\right) + 0.20 \cdot \text{Schedule\_Quality}(F) \right)$$
     where Cents-Per-Point $\text{CPP}(F) = \frac{(\text{Full\_Cash\_Benchmark} - \text{Out\_Of\_Pocket\_Cash}) \times 100}{\text{Total\_Matmid\_Points}}$.
6. **Combined Trip Optimization Score (`CTOS` $\in [0, 100]$)**:
   $$\text{CTOS}(W, F) = w_{\text{calendar}} \cdot \text{VUS}(W) + w_{\text{flight}} \cdot \text{FBVS}(F) \qquad (\text{default } w_{\text{calendar}} = 0.55,\; w_{\text{flight}} = 0.45)$$

### 3.6 Six Worked Numerical Optimization Examples Across Israeli Holidays

Consider a benchmark 5-person Israeli household (`משפחת בודובסקי`): 2 Adults (Sun–Thu workweek, Erev Chag $= 0.5$ PTO, Chol HaMoed $= 0.5$ PTO) + 3 Children: **Noa** (`MUNICIPAL_GAN`, $\omega_1=0.25$, Nitzanim Full), **Ido** (`ELEMENTARY_4_6`, $\omega_2=0.75$, 5-day week), and **Maya** (`MIDDLE_SCHOOL_7_9`, $\omega_3=1.00$, 5-day week):

| # | Candidate Holiday & Bridge Window (`תשפ"ז 2026–2027`) | Dates & Total Days ($D_{\text{total}}$) | Parent PTO ($\text{PTO}(W)$) & `PER` | Per-Child School Missed & `SAP` | `CCG` & `VUS` ($0\text{–}100$) | El Al Bonus & `CTOS` Outcome |
|---|---|---|---|---|---|---|
| **Ex 1** | **Kippur–Sukkot Mega-Bridge** (`Set I`) | **Tue Sep 22 – Sat Oct 3, 2026** ($12\text{ days}$, flying out after Yom Kippur shutdown) | $3\text{ bridge} + 4 \times 0.5\text{ Chol HaMoed} + 0.5\text{ Erev} = \mathbf{5.5\text{ PTO}}$<br>$\text{PER} = \frac{12}{5.5} = \mathbf{2.18}$ | Noa: $0$, Ido: $0$, Maya: $0$<br>$\text{SAP} = \mathbf{0.00}$ | $\text{CCG} = \mathbf{1.00}$<br>$\text{VUS} = \mathbf{72.7}$ (or $\mathbf{96.0}$ for 8-day Sukkot sub-window Sep 25–Oct 3 where $\text{PTO}=2.0, \text{PER}=4.0$) | Zero school missed across all 3 children; avoids `TLV` Sep 20–21 Yom Kippur closure. |
| **Ex 2** | **Hanukkah Post-Nitzanim Shift** (`Set I_camp` + 1 Bridge Day) | **Thu Dec 10 – Mon Dec 14, 2026** ($5\text{ days}$) | Thu ($1.0$) + Sun ($1.0$) + Mon ($1.0$) $= \mathbf{3.0\text{ PTO}}$<br>$\text{PER} = \frac{5}{3.0} = \mathbf{1.67}$ | Noa: $1$ day + $1$ Nitzanim, Ido: $1$ day, Maya: $1$ day (Mon Dec 14)<br>$\text{SAP} = \mathbf{0.68}$ | $\text{CCG} = \mathbf{0.73}$<br>$\text{VUS} = \mathbf{49.5}$ (vs. Dec 4–12 full Hanukkah $\text{VUS} = \mathbf{78.5}$) | Shifting return to Mon Dec 14 avoids Sat/Sun Hanukkah return peak and unlocks `2+` Economy + `2+` Business bonus seats (`FBVS = 92`). |
| **Ex 3** | **Purim Long-Weekend Bridge** (1 Bridge Day `Thu Mar 25`) | **Tue Mar 23 – Sat Mar 27, 2027** ($5\text{ days}$) | Tue ($1.0$) + Wed ($1.0$) + Thu ($1.0$) $= \mathbf{3.0\text{ PTO}}$<br>$\text{PER} = \frac{5}{3.0} = \mathbf{1.67}$ | Only **Thu Mar 25** missed ($1$ day; Fri is off for 5-day schools!)<br>$\text{SAP} = \mathbf{0.69}$ | $\text{CCG} = \mathbf{0.77}$<br>$\text{VUS} = \mathbf{51.0}$ | Turns a 2-day Tuesday–Wednesday Purim break into a **5-day European city break** for just **1 school day missed**! |
| **Ex 4** | **Pesach Pre-Holiday Shoulder Bridge** (-2 Bridge Days) | **Sun Apr 11 – Sun Apr 18, 2027** ($8\text{ days}$) | Sun ($1.0$) + Mon ($1.0$) + 3 pre-Seder ($3.0$) $= \mathbf{5.0\text{ PTO}}$ (or $\mathbf{2.0\text{ PTO}}$ during Apr 19–26 Seder/Chol HaMoed week, $\text{PER} = \mathbf{4.00}$!) | Noa: $0$ (Nitzanim), Ido: $2$ days, Maya: $2$ days<br>$\text{SAP} = \mathbf{1.17}$ | $\text{CCG} = \mathbf{0.75}$<br>$\text{VUS} = \mathbf{84.9}$ (Apr 19–26 Uncovered Week: $\text{VUS} = \mathbf{100.0}$!) | Flying out Sun Apr 11 (2 days before MoE Pesach break starts) unlocks `2+ Econ` & `2+ Prem` on `LY381` (`FCO`), saving `$2,100` (`CTOS = 95.0`). |
| **Ex 5** | **Shavuot Extended Weekend** (+1 Bridge Day `Wed Jun 9`) | **Wed Jun 9 – Sat Jun 12, 2027** ($4\text{ days}$) | Wed ($1.0$) + Thu Erev Chag ($0.5$) + Fri Chag ($0.0$) $= \mathbf{1.5\text{ PTO}}$<br>$\text{PER} = \frac{4}{1.5} = \mathbf{2.67}$ | Only **Wed Jun 9** missed ($1$ school day)<br>$\text{SAP} = \mathbf{0.67}$ | $\text{CCG} = \mathbf{0.75}$<br>$\text{VUS} = \mathbf{64.2}$ | **4-day Cyprus/Greece trip** (`LCA`/`ATH`/`RHO`) using **1.5 parent PTO days** and **1 school day**. |
| **Ex 6** | **June 20–30 Inter-Framework Arbitrage** (`Set U`) | **Mon Jun 21 – Mon Jun 28, 2027** ($8\text{ days}$) | $6\text{ workdays} = \mathbf{6.0\text{ PTO}}$<br>$\text{PER} = \frac{8}{6.0} = \mathbf{1.33}$ | Maya (`MIDDLE_SCHOOL_7_9`): **$0$ days missed!**<br>Ido & Noa: $5$ waning days ($\psi=0.50$, $\text{SAP} = \mathbf{0.83}$) | $\text{CCG} = \mathbf{0.58}$<br>$\text{VUS} = \mathbf{39.6}$ ( Calendar) vs. $\text{FBVS} = \mathbf{94.0}$ (Flight/Bonus) | Middle/High school is already out on June 20; airfares are **35–50% cheaper** than July 1+ and `rbddataclients` bonus seats are wide open! |

---

## 4. R3 — Airline Selection Modes (`EL_AL_ONLY` vs. `ALL_AIRLINES`) & El Al Bonus Ticket Engine (`https://www.elal.com/rbddataclients/`)

### 4.1 Orthogonal Airline Selection Mode Switcher

The application provides an explicit top-level toggle (`airline_selection_mode`) orthogonal to the Date Selection Mode:
1. **Mode 1: Focus on El Al (`EL_AL_ONLY`)**:
   - Restricts flight queries to **El Al (`LY`)** mainline and **Sun d'Or (`LY`/`2U`)** seasonal leisure flights from/to `TLV`.
   - Automatically enforces **El Al Shabbat Operational Constraints** (no departures from `TLV` between Friday ~14:00/15:00 local time and Motzei Shabbat after Havdalah).
   - Unlocks the **El Al Bonus Ticket Search Engine** powered by `https://www.elal.com/rbddataclients/` (`search_elal_bonus_tickets = True`), pairing Classic Award availability with commercial El Al cash benchmarks.
2. **Mode 2: All Airlines (`ALL_AIRLINES`)**:
   - Queries all operating carriers serving `TLV` (El Al `LY`, Israir `6H`, Arkia `IZ`, Blue Bird `BZ`, TUS `U8`, Wizz Air `W6`, Ryanair `FR`, easyJet `U2`, Aegean `A3`, Lufthansa Group `LH`/`OS`/`LX`/`SN`, Air France `AF`, British Airways `BA`, United `UA`, Delta `DL`, Flydubai `FZ`, Etihad `EY`, etc.).
   - Applies the **Family Baggage Cost Normalizer**, adding the family's required cabin trolleys and checked suitcases to Low-Cost Carrier (LCC) base fares so LCCs and full-service carriers are compared on true total family out-of-pocket cost.

### 4.2 Technical Specification of `https://www.elal.com/rbddataclients/` Integration

1. **Portal Purpose & Mechanics**:
   - `https://www.elal.com/rbddataclients/` is El Al's standalone **Matmid Classic Award Seat Availability Calculator** (`מחשבון זמינות מושבי בונוס`).
   - It exposes Classic Award seat inventory across **Economy (`תיירים`)**, **Premium (`פרימיום`)**, and **Business (`עסקים`)** cabins up to ~11–12 months ahead, alongside one-way point requirements and estimated airport taxes (USD).
2. **Strict 3-Letter Airport IATA Expansion (Metro Code Rejection Rule)**:
   - Unlike `elal.com`'s main commercial widget, `https://www.elal.com/rbddataclients/` **rejects metropolitan multi-airport codes** (`NYC`, `LON`, `PAR`, `TYO`, `MIL`).
   - `ElAlRbdDataClientAdapter` automatically expands any metropolitan code into constituent El Al 3-letter airport IATAs before querying `rbddataclients`:
     - `NYC` $\to$ `["JFK", "EWR"]`
     - `LON` $\to$ `["LHR", "LTN"]`
     - `PAR` $\to$ `["CDG"]`
     - `MIL` $\to$ `["MXP"]`
     - `ROM` $\to$ `["FCO"]`
     - `TYO` $\to$ `["NRT"]`
     - `MIA_AREA` $\to$ `["MIA", "FLL"]`
3. **Output Seat Indicators (`0`, `1`, `2` = `2+` Cap)**:
   - For each flight/date and cabin class, `rbddataclients` returns:
     - `0` (or empty): Zero Classic Award seats available in that cabin.
     - `1`: **Exactly 1** Classic Award seat remains in that RBD bucket (`*_seats_is_two_plus = False`).
     - `2`: **2 or more ($\ge 2$)** Classic Award seats are available in that RBD bucket (`*_seats_is_two_plus = True`).
4. **Ingestion Pipeline (`ElAlRbdDataClientAdapter`)**:
   - Uses a warmed **Playwright headless Chromium context** (with `httpx` replay of session cookies) to navigate `https://www.elal.com/rbddataclients/`, trigger outbound (`TLV` $\to$ `DEST`) and inbound (`DEST` $\to$ `TLV`) date-grid queries, intercept the JSON award payload, normalize into `ElAlBonusAvailability`, and persist to SQLite with a 4-hour TTL.

### 4.3 El Al RBD Bucket Mapping, Pure Points + Taxes Zone Table & Fly Card Promotions

#### Table 4.3A — El Al (`LY`) Reservation Booking Designator (RBD) Mapping
| Cabin Class | Classic Award / Bonus RBD Codes (`rbddataclients`) | Commercial Cash Revenue RBD Codes | Fleet & Family Planning Notes |
|---|---|---|---|
| **Economy (`תיירים`)** | **`E`**, **`X`**, **`U`** | Full/Flex: `Y`, `S`, `M`<br>Classic: `Q`, `B`, `H`, `V`, `N`<br>Lite: `K`, `L`, `T`, `O`, `G` | Available on all El Al mainline (`787`, `777`, `737`) and Sun d'Or (`LY`/`2U`) aircraft. Includes 1 checked bag ($23\text{ kg}$) + 1 cabin trolley on Classic Awards. |
| **Premium (`פרימיום`)** | **`P`** (plus upgrade/promo **`A`**, **`R`**) | `W`, `Q`, `B`, `P` | Available on widebody fleet (`Boeing 787-8/787-9 Dreamliner` & `777-200ER`). Not present on narrowbody `737-800/900` unless widebody-operated (`LHR`, `CDG`, `FCO`, `ATH`, `BCN`, `AMS`, `MAD` select rotations). |
| **Business (`עסקים`)** | **`I`**, **`W`** | Full: `J`, `C`<br>Discounted: `D`, `Z`, `I`, `R` | Lie-flat on `787`/`777`, recliner on `737`. Highest Cents-Per-Point (`CPP`) value on long-haul routes. |

#### Table 4.3B — Matmid Classic Award Pure Points + Taxes Zone Reference Table (One-Way per Passenger)
| Award Zone | Representative El Al IATA Destinations | Economy Award (`E`/`X`/`U`) One-Way Points | Premium Award (`P`/`A`/`R`) One-Way Points | Business Award (`I`/`W`) One-Way Points | Typical One-Way Port Taxes (USD) |
|---|---|---|---|---|---|
| **Zone A — Short-Haul (Cyprus, Greece, Balkans, Georgia)** | `LCA`, `PFO`, `ATH`, `RHO`, `HER`, `JMK`, `SKG`, `SOF`, `OTP`, `TBS`, `BUS`, `KIV`, `TIA` | `7,500 – 15,000 pts`<br>*(Tuesday 50% Promo: `3,750 – 7,500`)* | `18,000 – 25,000 pts` *(if 787)* | `25,000 – 35,000 pts` | `$35 – $65` |
| **Zone B — Central & Eastern Europe / Italy** | `FCO`, `MXP`, `VCE`, `VIE`, `BUD`, `PRG`, `WAW`, `KRK`, `BEG`, `ZAG`, `DBV`, `MUC`, `BER`, `FRA`, `ZRH` | `15,000 – 22,500 pts`<br>*(Tuesday 50% Promo: `7,500 – 11,250`)* | `30,000 – 40,000 pts` | `45,000 – 65,000 pts` | `$45 – $95` |
| **Zone C — Western Europe & UK** | `CDG`, `LHR`, `LTN`, `AMS`, `MAD`, `BCN`, `LIS`, `NCE`, `MRS`, `LYS` | `20,000 – 25,000 pts`<br>*(Tuesday 50% Promo: `10,000 – 12,500`)* | `35,000 – 45,000 pts` | `60,000 – 75,000 pts` | `$55 – $180` *(Note: `LHR` return carries high UK APD tax; planner flags `LTN` alternative!)* |
| **Zone D — Far East & South Africa** | `BKK`, `HKT`, `NRT`, `JNB` | `35,000 – 45,000 pts` | `65,000 – 80,000 pts` | `90,000 – 115,000 pts` | `$50 – $95` |
| **Zone E — North America** | `JFK`, `EWR`, `BOS`, `MIA`, `FLL`, `LAX` | `35,000 – 47,500 pts` | `70,000 – 85,000 pts` | `100,000 – 125,000 pts` | `$45 – $85` |

### 4.4 Solving the "`2` (`2+`) Seat Cap" Problem: The 5 Family Bonus Fulfillment Strategies

Because `https://www.elal.com/rbddataclients/` caps its displayed award seat count at `2` (`2+` seats available) while a family requires $N \in \{3..6\}$ seats, a naive filter (`award_seats >= N`) would discard every flight! Instead, `BonusVacationPlannerService` synthesizes and ranks **five concrete Family Bonus Ticket Fulfillment Strategies** on every candidate flight pair:

1. **Strategy 1 — Full-Family Single-Cabin Bonus (`FULL_BONUS_SAME_CABIN`)**:
   - **Condition**: `rbddataclients` reports `2` (`2+`) in the target cabin (e.g., Economy `E`) on both outbound and inbound legs, AND the family's `matmid_points_balance` covers $N$ passengers.
   - **Action**: Generates a full-family bonus proposal, sets `requires_two_plus_seat_verification = True` when $N \ge 3$, and provides a 1-click deep link to `elal.com` with `Points/Award` pre-selected for $N$ passengers to verify if seats $3\dots N$ clear in the `E` bucket.
2. **Strategy 2 — Full-Family Split-Cabin Bonus on Same Flight (`SPLIT_CABIN_BONUS`)**:
   - **Condition**: The **exact same flight number** has `2` (`2+`) seats in Economy (`E`) AND `1` or `2` (`2+`) seats in Premium (`P`) or Business (`I`).
   - **Action**: Allocates, e.g., **2 passengers in Economy Bonus + 2 passengers in Premium/Business Bonus on the exact same aircraft**. Guarantees 4 guaranteed Classic Award seats using 100% points + taxes even if each cabin strictly has only 2 award seats!
3. **Strategy 3 — Hybrid Bonus + Commercial Cash on Same Flight (`HYBRID_BONUS_PLUS_CASH`)**:
   - **Condition**: Total available bonus seats across desired cabins on flight `LYxxx` is $K < N$ (or user's Matmid point wallet only covers $K$ tickets).
   - **Action**: Allocates **$K$ Matmid Classic Award tickets** (e.g., `2x Economy Bonus` + `2x Premium Bonus`) + **$(N - K)$ Commercial Cash tickets** on the **exact same `LYxxx` flight number**. Computes blended family cost (`Total Points + Award Taxes + Supplemental Cash Tickets`) and exact USD/ILS saved vs. buying $N$ commercial cash tickets. *(Enforces adult/child PNR pairing so no child under 12 is booked alone on a separate PNR without an adult).*
4. **Strategy 4 — Asymmetric Direction / Open-Jaw Bonus Mix (`ONE_WAY_BONUS_ONE_WAY_CASH`)**:
   - **Condition**: Because El Al Classic Awards are priced one-way, if outbound on a peak holiday start has `0` bonus seats while the return flight has `2+` bonus seats (or if flying Bonus into `MXP` Milan and returning Bonus from `FCO` Rome both have `2+` seats):
   - **Action**: Pairs **One-Way Bonus + One-Way Cash** (or **Open-Jaw Bonus** `TLV -> MXP` / `FCO -> TLV`) to salvage a high-value holiday redemption.
5. **Strategy 5 — El Al `Cash & Points` Fallback (`CASH_AND_POINTS`)**:
   - **Condition**: When `rbddataclients` reports `0` Classic Award seats across all cabins on a required date.
   - **Action**: Computes the commercial El Al fare discounted via Matmid `Cash & Points` (`כסף ונקודות`), displaying an explicit warning badge if the effective Cents-Per-Point ($\text{CPP} < 0.8\text{¢}$) is lower than saving points for a Classic Award (`1.4\text{¢}–2.2\text{¢}`).
6. **Strategy 6 — Per-Passenger & Multi-Club Loyalty Wallet Split (`MULTI_CLUB_PER_PASSENGER_SPLIT`)**:
   - **Condition**: Families frequently hold points split across **individual passengers** (e.g., Parent 1 has `75,000` El Al Matmid points and Parent 2 has `68,000` El Al Matmid points in separate un-pooled accounts) AND/OR across **multiple frequent flyer programs & credit cards** (`ELAL_MATMID`, `BRITISH_AVIOS`, `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`, `QANTAS_FREQUENT_FLYER`, `AEGEAN_MILES_BONUS`, `AMEX_MR_ISRAEL`, `ISRAELI_CC_TRAVEL_POINTS`).
   - **Action**: `MultiClubWalletAllocationEngine` tracks the exact point balance $W_{p, m}$ for each passenger $p$ and loyalty club $m$:
     - **Per-Passenger Account Splitting within El Al Matmid**: Allocates whole passenger tickets to specific member accounts so no single passenger's Matmid balance is exceeded (e.g., Parent 1's wallet issues `2x Economy Bonus` = `60,000 pts`; Parent 2's wallet issues `2x Economy/Premium Bonus` = `65,000 pts`; 5th ticket issued via Cash or Partner/Transferable points).
     - **Cross-Club Family & Directional Splitting**: Supports issuing outbound legs via **El Al Matmid (`rbddataclients`)** and return legs via **Avios / Flying Blue / Miles & More / United** (or allocating 3 family members on El Al Matmid and 2 family members on a partner/alliance award or transferable credit-card points), displaying an exact **Per-Passenger & Per-Club Point Deduction Breakdown (`points_used_by_wallet_json`)** on every proposal card!

### 4.5 3-Tier Commercial Flight Provider Architecture (`ALL_AIRLINES` & Cash Benchmarks)

Based on our verification of the 2025–2026 flight API landscape—where **Amadeus Self-Service API** retired its free public developer portal and **Kiwi Tequila API** moved to invite-only commercial access—`AllAirlinesSearchAdapter` implements a **3-Tier Pluggable Provider Architecture** that works out-of-the-box for personal use:
1. **Tier 1 (Primary Keyless Local Engine) — `fast-flights` / `fli` (Google Flights Protobuf Client)**: Encodes Google Flights `tfs` Protobuf queries and fetches live multi-carrier schedules and fares directly from Google Flights with zero API keys or monthly quotas.
2. **Tier 2 (Structured JSON Free-Tier API) — SerpApi Google Flights Engine (`serpapi.com`)**: Active self-serve developer tier providing **250 free live searches/month** plus unlimited free 1-hour cached lookups, returning flight numbers, aircraft types, baggage rules, and booking tokens.
3. **Tier 3 (Official NDC/GDS REST API) — Duffel API (`duffel.com`)**: Self-serve developer REST API (`offer_requests`) for structured multi-airline fare cross-checks, with optional adapter interfaces retained for legacy enterprise keys (`AmadeusAdapter`, `KiwiTequilaAdapter`).

---

## 5. End-to-End BiDi/RTL UX/UI Specifications & Component Wireframes

### 5.1 4-Zone Dashboard Layout

The web interface is built RTL-first (`<div dir="rtl" lang="he">`) with an instant Hebrew/English switcher and consists of four synchronized zones:
1. **Zone 1 — Active Family Profile & Matmid Wallet Bar**: Displays the household summary (e.g., `2 מבוגרים + 3 ילדים: נועה [גן חובה+ניצנים] | עידו [כיתה ד' יסודי 5 ימים] | מאיה [כיתה ח' חט"ב 5 ימים]`), Matmid Points balance (`185,000 נק'`), FlyCard status, and parent PTO budget.
2. **Zone 2 — Dual-Axis Mode Control Panel (`SearchControlPanel`)**:
   - **Left Axis — Date Selection Mode (`R2`)**: Radio pill switching between **Mode 1: Specific Dates (`תאריכים ספציפיים ±N ימים`)** and **Mode 2: Around Children's MoE Vacations (`סביב חופשות משרד החינוך למקסום ניצול החופשה`)**.
   - **Right Axis — Airline Selection Mode (`R3`)**: Radio pill switching between **Mode 1: Focus on El Al (`מיקוד בטיסות אל על` + `[x] חיפוש כרטיסי בונוס באתר elal.com/rbddataclients/`)** and **Mode 2: All Airlines (`כל חברות התעופה`)**.
3. **Zone 3 — Multi-Child MoE Vacation & Bridge-Day Timeline Heatmap (`MultiChildCalendarHeatmap`)**: Horizontal Gantt chart showing each child's daily MoE status (`חופשה רשמית`, `ניצנים`, `לימודים ו'`, `סוף שנה 20–30 ביוני`), parent PTO cost strip, and El Al `rbddataclients` bonus seat density badges.
4. **Zone 4 — Ranked Vacation Proposals Grid & Comparison Modal**: Displays synthesized `BonusVacationOptionCard` and `AllAirlinesItineraryCard` results ranked by `CTOS`.

### 5.2 Flagship `BonusVacationOptionCard` & `BonusVacationComparisonTable`

#### ASCII Wireframe: `BonusVacationOptionCard`
```text
+==================================================================================================+
| 🏆 אפשרות #1: רומא (FCO) — חופשת פסח + גשר מקדים                    [ציון משוקלל CTOS: 95 / 100] |
| 📅 יום א' 11 אפריל 2027  <--->  יום א' 18 אפריל 2027 (7 לילות / 8 ימים מלאים)                    |
+--------------------------------------------------------------------------------------------------+
| ✈️ זמינות כרטיסי בונוס אל על (מקור: https://www.elal.com/rbddataclients/ — עודכן לפני 12 דק')     |
| +----------------------------------------------+ +---------------------------------------------+ |
| | 🛫 הלוך: LY381 (TLV 07:15 -> FCO 10:00)      | | 🛬 חזור: LY384 (FCO 21:45 -> TLV 02:10+1)   | |
| | תאריך: 11/04/2027 (יומיים לפני תחילת חופש)  | | תאריך: 18/04/2027 (חופשת פסח משרד החינוך)  | |
| | מושבי בונוס פנויים ב-rbddataclients:          | | מושבי בונוס פנויים ב-rbddataclients:         | |
| |   • תיירים (Economy E/X/U): [ 2+ מושבים ]    | |   • תיירים (Economy E/X/U): [ 2+ מושבים ]   | |
| |   • פרימיום (Premium P/A/R): [ 2+ מושבים ]   | |   • פרימיום (Premium P/A/R): [ 1 מושב פנוי ]| |
| |   • עסקים (Business I/W):    [ 0 מושבים ]    | |   • עסקים (Business I/W):    [ 2+ מושבים ]  | |
| +----------------------------------------------+ +---------------------------------------------+ |
| 🧩 אסטרטגיית כרטיסים למשפחה (5 נוסעים): HYBRID_BONUS_PLUS_CASH / SPLIT_CABIN על אותה טיסה בדיוק:  |
|   ✅ 2x בונוס תיירים (E) + ✅ 2x בונוס פרימיום/עסקים (P/I) + 💳 1x כרטיס מזומן על LY381 / LY384   |
|   💰 עלות כוללת: 142,000 נק' מתמיד + $390 מסי נמל + $460 כרטיס מזומן = $850 מזומן סה"כ           |
|   📉 השוואה למחיר מזומן מלא (5 כרטיסים = $2,950): חיסכון של $2,100 במזומן! (CPP: 1.48¢ לנקודה)   |
+--------------------------------------------------------------------------------------------------+
| 🏫 ניתוח ניצול חופשות משרד החינוך וימי חופש הורים (VUS: 84.9 | PER: 4.0x | SAP: 1.17 | CCG: 0.75)|
|                                                                                                  |
| תאריך:         | א' 11/4 | ב' 12/4 | ג' 13/4 | ד' 14/4 | ה' 15/4 | ו' 16/4 | ש' 17/4 | א' 18/4 |
| ---------------+---------+---------+---------+---------+---------+---------+---------+---------+ |
| 👔 הורים (PTO) | ⚠️ 1.0  | ⚠️ 1.0  | 🏖️ חופש | 🏖️ חופש | 🏖️ חופש | 🟢 סופ"ש| 🟢 סופ"ש| 🏖️ חופש |
| 🧒 נועה (גן+ניצ)| 🟡 ניצנ'| 🟡 ניצנ'| 🏖️ פסח  | 🏖️ פסח  | 🏖️ פסח  | 🟢 סופ"ש| 🟢 סופ"ש| 🏖️ פסח  |
| 👦 עידו (כיתה ד)| ❌ גשר 1| ❌ גשר 2| 🏖️ פסח  | 🏖️ פסח  | 🏖️ פסח  | 🟢 סופ"ש| 🟢 סופ"ש| 🏖️ פסח  |
| 👧 מאיה (חט"ב ח)| ❌ גשר 1| ❌ גשר 2| 🏖️ פסח  | 🏖️ פסח  | 🏖️ פסח  | 🟢 סופ"ש| 🟢 סופ"ש| 🏖️ פסח  |
+--------------------------------------------------------------------------------------------------+
| [🔗 אמת זמינות ב-elal.com/rbddataclients] [🛫 עבור להזמנת בונוס באל על] [⚖️ הוסף להשוואת חופשות] |
+==================================================================================================+
```

### 5.3 React + TypeScript + Tailwind RTL Component Hierarchy

| Component | Planned Path | Core Responsibility |
|---|---|---|
| `AppShell` | `frontend/src/components/layout/AppShell.tsx` | Root BiDi/RTL container (`dir="rtl"`), top family profile bar, and Matmid wallet summary. |
| `FamilyProfileDrawer` | `frontend/src/components/profile/FamilyProfileDrawer.tsx` | Configures adults, PTO rules, children across all 8 `MoEFrameworkType` options, `5_DAY`/`6_DAY` week, and Nitzanim. |
| `SearchControlPanel` | `frontend/src/components/search/SearchControlPanel.tsx` | Orthogonal `DateModeSelector` (Mode 1 Specific vs. Mode 2 MoE Maximization) and `AirlineModeSelector` (Mode 1 El Al vs. Mode 2 All Airlines). |
| `ElAlBonusSearchSubPanel` | `frontend/src/components/search/ElAlBonusSearchSubPanel.tsx` | Controls `https://www.elal.com/rbddataclients/` bonus search, cabin filters (`Economy`, `Premium`, `Business`), and hybrid family allocation toggles. |
| `MultiChildCalendarHeatmap` | `frontend/src/components/calendar/MultiChildCalendarHeatmap.tsx` | Interactive school-year timeline visualizing $\mathcal{I}$, $\mathcal{I}_{\text{camp}}$, $\mathcal{U}$ sets, bridge days, and bonus seat density. |
| `BonusVacationOptionCard` | `frontend/src/components/results/BonusVacationOptionCard.tsx` | Renders a synthesized bonus vacation option with RBD seat counts, 5-strategy family ticket allocation, savings/CPP, and per-child MoE absence grid. |
| `BonusVacationComparisonModal` | `frontend/src/components/results/BonusVacationComparisonModal.tsx` | Side-by-side matrix comparing 2–4 pinned vacation proposals across points, cash, `PER`, `SAP`, `VUS`, `FBVS`, and `CTOS`. |
| `AllAirlinesItineraryCard` | `frontend/src/components/results/AllAirlinesItineraryCard.tsx` | Displays multi-carrier itineraries in `ALL_AIRLINES` mode with family baggage normalization and MoE impact strip. |

---

## 6. Post-Planning 5-Phase Implementation Roadmap & Point-by-Point Verification Rubric

### 6.1 5-Phase Implementation Roadmap

Once this pre-build Application Plan is approved, implementation proceeds through five independently verifiable phases:

| Phase | Milestone Name | Scope & Key Deliverables | Verification Gate |
|---|---|---|---|
| **Phase 1** | **Foundation, SQLite Schema & Israeli MoE Calendar Engine** | Initialize project layout; create 7-table SQLite database (`schema.sql`); bundle verified `תשפ"ו` (`2025–2026`) and `תשפ"ז` (`2026–2027`) MoE JSON calendars; implement `MoECalendarService` & `VacationMaximizerEngine` ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$, `PER`, `SAP`, `CCG`, `VUS`). | Automated `pytest` suite verifying June 20 vs. June 30 split, Middle School hybrid rule, Lag BaOmer תשפ"ו vs. תשפ"ז difference, Nitzanim July/Hanukkah/Pesach rules, and `TLV` Yom Kippur closure. |
| **Phase 2** | **El Al `rbddataclients` Connector & 5-Strategy Bonus Synthesizer** | Implement `ElAlRbdDataClientAdapter` (`https://www.elal.com/rbddataclients/`) with metro-to-airport IATA expansion, token-bucket rate limiter, and 4h SQLite TTL cache; implement `BonusVacationPlannerService` across all 5 family fulfillment strategies. | Unit & fixture integration tests verifying `0`/`1`/`2+` seat parsing across `E`/`P`/`I` RBDs and 5-person family hybrid/split-cabin allocation math. |
| **Phase 3** | **3-Tier All-Airlines Search Adapter & Unified REST API** | Implement `AllAirlinesSearchAdapter` (`fast-flights`/`fli`, `SerpApi Google Flights`, `Duffel API`) with family baggage cost normalization; expose all 7 FastAPI endpoints (`/api/v1/*`). | API integration tests covering all $2 \times 2$ combinations of Date Selection Modes (`SPECIFIC_DATES`, `MOE_VACATION_MAXIMIZATION`) and Airline Selection Modes (`EL_AL_ONLY`, `ALL_AIRLINES`). |
| **Phase 4** | **React 19 + TypeScript + Tailwind v4 RTL Frontend** | Build `AppShell`, `FamilyProfileDrawer`, `SearchControlPanel`, `ElAlBonusSearchSubPanel`, `MultiChildCalendarHeatmap`, `BonusVacationOptionCard`, and `BonusVacationComparisonModal`. | Component & Playwright E2E tests verifying RTL rendering, mode switching, and interactive comparison table. |
| **Phase 5** | **CLI Companion, `.ics` Export & Local Packaging** | Implement `plan-vacation` Typer CLI, `.ics` calendar export, deep links to `https://www.elal.com/rbddataclients/` and `elal.com`, and 1-command local startup (`make dev`). | End-to-end smoke test across the 6 worked Israeli family holiday scenarios. |

### 6.2 Explicit Point-by-Point Pre-Build Verification Rubric (`RUB-R1.1` through `RUB-AC.1`)

Every requirement and acceptance criterion in `ORIGINAL_REQUEST.md` is mapped below for independent verification:

| Rubric ID | Source Requirement (`ORIGINAL_REQUEST.md`) | Verbatim Requirement Clause | Target Section in `APPLICATION_PLAN.md` & `docs/` | Concrete Verification Pass Criteria |
|---|---|---|---|---|
| **`RUB-R1.1`** | `R1` & `AC-1` | *"Help plan the family vacation planning application before starting the actual build itself."* / *"The application plan is written to `~/teamwork_projects/family_vacation_planner` and specifies the application design before starting the build itself."* | `APPLICATION_PLAN.md` (§1–§6), `README.md`, and `docs/01..05_*.md` in `/home/yonibudovsky/teamwork_projects/family_vacation_planner/` | 1. All 7 plan documents exist in `/home/yonibudovsky/teamwork_projects/family_vacation_planner/`.<br>2. Deliverable is a complete pre-build specification authored before application code build begins. |
| **`RUB-R1.2`** | `R1` | *"Technology, platform, and general data-sourcing choices (beyond the specified El Al bonus ticket URL) are left to the team to determine as part of the plan."* | `APPLICATION_PLAN.md` §2.1–§2.7 & `docs/01_architecture_and_tech_stack.md` | Explicitly specifies and justifies: (1) Local-first Web App + CLI platform, (2) Python 3.13 + FastAPI + SQLite 3.53 WAL + React 19/TS/Tailwind v4 RTL stack, (3) 3-tier flight data sources (`fast-flights`/`fli`, `SerpApi`, `Duffel`), and (4) 3-layer MoE calendar data sources. |
| **`RUB-R2.1`** | `R2` & `AC-2` | *"The planned application must help find flights on suitable dates and support two modes: (1) choosing specific dates..."* | `APPLICATION_PLAN.md` §3.1 & `docs/02_moe_calendar_and_maximization.md` §1 | Specifies UX controls, query schema (`specific_departure_date`, `specific_return_date`, `flex_days_plus_minus` $\in \{0..7\}$), passenger composition, and automatic MoE calendar impact preview badge for Mode 1 (`SPECIFIC_DATES`). |
| **`RUB-R2.2`** | `R2` & `AC-2` | *"...or (2) finding flights around children's vacations across different educational framework types (according to the Israeli Ministry of Education)..."* | `APPLICATION_PLAN.md` §3.2–§3.4 & `docs/02_moe_calendar_and_maximization.md` §2–§4 | Models all 8 Israeli MoE educational frameworks (`DAYCARE_SUPERVISED`, `MUNICIPAL_GAN`, `ELEMENTARY_1_3`, `ELEMENTARY_4_6`, `MIDDLE_SCHOOL_7_9`, `HIGH_SCHOOL_10_12`, `SPECIAL_ED`, `RELIGIOUS_HAREDI`), `5_DAY` vs. `6_DAY` week, Nitzanim (`בית הספר של החגים` & `בית הספר של החופש הגדול`), and full `תשפ"ו` & `תשפ"ז` holiday tables including the Middle School hybrid rule and June 20 vs. June 30 divergence. |
| **`RUB-R2.3`** | `R2` & `AC-2` | *"...to help maximize utilization of the vacation."* / *"...including how vacation utilization is maximized."* | `APPLICATION_PLAN.md` §3.5–§3.6 & `docs/02_moe_calendar_and_maximization.md` §5–§6 | Defines daily vectorization ($P(d), S_c(d)$), multi-child set operations ($\mathcal{I}, \mathcal{I}_{\text{camp}}, \mathcal{U}$), $\pm 3$-day "Yemei Gesher" bridge-day window expansion, explicit mathematical scoring formulas (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`), and 6 worked numerical Israeli holiday examples. |
| **`RUB-R3.1`** | `R3` & `AC-3` | *"The planned application must provide an option to either focus on El Al flights or allow selection of all airlines."* | `APPLICATION_PLAN.md` §4.1, §4.5 & `docs/03_airlines_and_elal_bonus_engine.md` §1, §5 | Specifies UI switcher and backend routing between Mode 1 (`EL_AL_ONLY`, `LY` + Sun d'Or `2U` with Shabbat constraints) and Mode 2 (`ALL_AIRLINES`, multi-carrier search with family baggage cost normalization). |
| **`RUB-R3.2`** | `R3` & `AC-3` | *"When focusing on El Al, it must include an option to search for bonus tickets on https://www.elal.com/rbddataclients/..."* | `APPLICATION_PLAN.md` §4.2–§4.3 & `docs/03_airlines_and_elal_bonus_engine.md` §2–§3 | Details `https://www.elal.com/rbddataclients/` integration: metro-to-airport 3-letter IATA expansion (`NYC`$\to$`JFK`/`EWR`, `LON`$\to$`LHR`/`LTN`), Classic Award RBD mapping (`Economy`: `E`/`X`/`U`, `Premium`: `P`/`A`/`R`, `Business`: `I`/`W`), `0`/`1`/`2+` seat cap parsing, Pure Points + Taxes zone table (Zones A–E), Fly Card promos, and Playwright/XHR caching. |
| **`RUB-R3.3`** | `R3` & `AC-3` | *"...and display the available options for planning a vacation using bonus tickets."* / *"...(3) presenting vacation planning options that utilize bonus tickets."* | `APPLICATION_PLAN.md` §4.4, §5.2 & `docs/03_airlines_and_elal_bonus_engine.md` §4 & `docs/04_ui_ux_and_user_workflows.md` §4 | Specifies the 5 Family Bonus Fulfillment Strategies (`FULL_BONUS_SAME_CABIN`, `SPLIT_CABIN_BONUS`, `HYBRID_BONUS_PLUS_CASH`, `ONE_WAY_BONUS_ONE_WAY_CASH`, `CASH_AND_POINTS`) and `BonusVacationOptionCard` / `BonusVacationComparisonTable` displaying RBD seat counts, family ticket allocation, points + taxes vs. cash savings & CPP, day-by-day MoE child absence table, and deep links. |
| **`RUB-AC.1`** | `AC-2` & `AC-3` | *"An independent review against an explicit point-by-point rubric verifies that the plan covers..."* | `APPLICATION_PLAN.md` §6.2, `README.md` §4, & `docs/05_implementation_roadmap_and_rubric.md` §3 | Embeds this explicit 9-item point-by-point rubric (`RUB-R1.1`..`RUB-AC.1`) with exact file/section mappings and automated verification checks. |

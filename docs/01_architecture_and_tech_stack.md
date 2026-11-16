# 01 — Architecture, Technology Stack, Database DDL & Service Contracts (`R1`)

**Parent Document**: [`../APPLICATION_PLAN.md`](../APPLICATION_PLAN.md) (§2) | **Index**: [`../README.md`](../README.md)  
**Rubric Coverage**: `RUB-R1.1`, `RUB-R1.2`

---

## 1. Platform & Architectural Rationale (`R1`)

Because the application is planned for **personal, practical family use** (`R1`), it uses a **Local-First Web Application + CLI Companion** architecture:
1. **Zero Cloud Infrastructure Cost & Privacy by Design**: Household member details, children's exact birthdates, Israeli Ministry of Education (`משרד החינוך`) school frameworks, and El Al Matmid Frequent Flyer point balances are stored locally in an embedded **SQLite 3.53 (WAL mode)** database (`data/vacation_planner.db`).
2. **Mobile-First Responsive Bilingual BiDi/RTL Web Application & PWA (`localhost:5173` / LAN / Mobile)**: Designed as a **responsive Web App adapted for both Mobile (`360px–430px` iOS/Android smartphones) and Desktop (`1280px+`)**, with **Progressive Web App (`manifest.webmanifest`)** support so parents can install it to their phone's Home Screen and browse/compare vacation options together on the couch. Visualizing multi-child school vacation timelines in Hebrew (`dir="rtl"`), tuning "Yemei Gesher" (`ימי גשר`) sliders, and comparing 5-passenger El Al bonus ticket allocations alongside commercial cash fares uses an adaptive `React 19 + TypeScript + Vite + Tailwind CSS v4` UI (bottom sheets, sticky mobile action bars, touch-scrollable RTL heatmaps, and swipeable option cards on mobile; 4-zone split dashboard on desktop).
3. **Local Async Backend & Headless Browser Engine (`0.0.0.0:8000`)**: Querying `https://www.elal.com/rbddataclients/` and multi-airline flight endpoints requires a Python runtime (`Python 3.13 + FastAPI + Playwright + httpx`) that maintains warmed browser session cookies, enforces polite token-bucket rate limiting, caches results in SQLite, and binds to `0.0.0.0` (or Tailscale/Cloudtop proxy) for seamless access from mobile devices.
4. **CLI Companion (`plan-vacation`)**: Built with `Typer + Rich + APScheduler` so the user can run quick terminal queries (`plan-vacation search --mode moe-maximize --airline elal-only`) or schedule background alerts when new El Al Matmid bonus seats open on target holiday dates.

---

## 2. Technology Stack Specification

| Architectural Layer | Selected Stack | Version / Environment | Justification |
|---|---|---|---|
| **Backend API & Orchestration** | **Python + FastAPI + Uvicorn + Pydantic v2** | Python `3.13.x` | Native `asyncio` concurrency for parallel route/month queries; strict type validation for calendar matrices and ticket allocations. |
| **Relational Database & Cache** | **SQLite (WAL mode) + SQLAlchemy 2.0** | SQLite `3.53.x` | Single-file zero-configuration local storage (`data/vacation_planner.db`) supporting concurrent reads/writes via `PRAGMA journal_mode=WAL;`. |
| **El Al Bonus Portal Client** | **`Playwright` (Chromium) + `httpx` + `tenacity`** | Playwright `1.50+` | Loads `https://www.elal.com/rbddataclients/`, passes Akamai/Cloudflare WAF challenges, intercepts XHR/Fetch JSON award responses, and retries with exponential backoff. |
| **Commercial Flight Providers** | **3-Tier Pluggable Architecture**:<br>• Tier 1: `fast-flights` / `fli` (Google Flights Protobuf/RPC)<br>• Tier 2: **SerpApi Google Flights API** (250 free/mo + 1h cache)<br>• Tier 3: **Duffel API** (self-serve NDC/GDS REST) | 2025–2026 Verified | Accounts for the 2025–2026 API landscape where Amadeus Self-Service discontinued its public free portal and Kiwi Tequila became invite-only. Ensures zero-friction personal operation. |
| **Hebrew & MoE Calendar Engine** | **Bundled MoE JSON Rule Packs (`תשפ"ו`, `תשפ"ז`) + `pyluach` / `hdate` + `Hebcal REST API (i=on)`** | Israel 1-Day Schedule (`i=on`) | `data.gov.il` lacks a Ministry of Education vacation dataset; curated JSON packs from MoE Circulars (`schedule-o`, `0346`, `0363`, `0364`) + Hebcal projection guarantee accuracy. |
| **Frontend Web UI** | **React 19 + TypeScript + Vite + Tailwind CSS v4** | Node `v24.x` | Logical RTL layout utilities (`dir="rtl"`), interactive Gantt calendar heatmaps, and side-by-side bonus vacation comparison drawers. |
| **CLI & Background Scheduler** | **Typer + Rich + APScheduler** | Python `3.13.x` | Terminal tables for `rbddataclients` scans and optional cron alerts for newly released Classic Award seats. |

---

## 3. Six Core Backend Modules & Planned Directory Layout

### 3.1 Planned Post-Approval Codebase Layout
When implementation begins after approval of this plan, the application will follow this modular structure:

```text
family_vacation_planner/
├── backend/
│   ├── app/
│   │   ├── main.py                             # FastAPI application entrypoint & CORS/RTL middleware
│   │   ├── api/v1/endpoints.py                 # 7 REST API routes (/api/v1/*)
│   │   ├── config_manager/                     # Module 6: YAML settings & .env secrets loader
│   │   │   └── settings.py
│   │   ├── storage_cache/                      # Module 5: SQLite 3.53 WAL repository & TTL cache
│   │   │   ├── schema.sql                      # 7-table relational DDL
│   │   │   └── repository.py
│   │   ├── calendar_engine/                    # Module 1: MoECalendarService (8 frameworks, Nitzanim, TLV Kippur)
│   │   │   └── moe_calendar_service.py
│   │   ├── vacation_optimizer/                 # Module 2: VacationMaximizerEngine (Sets I/I_camp/U, PER/SAP/CCG/VUS)
│   │   │   └── maximizer_engine.py
│   │   ├── providers/                          # Module 3: ElAlRbdDataClientAdapter & AllAirlinesSearchAdapter
│   │   │   ├── elal_rbd_client.py              # https://www.elal.com/rbddataclients/ connector + metro IATA expander
│   │   │   └── commercial_flights.py           # 3-tier fast-flights/fli -> SerpApi -> Duffel + baggage normalizer
│   │   ├── planner_synthesizer/                # Module 4: BonusVacationPlannerService (5 family bonus strategies + CTOS)
│   │   │   └── bonus_planner_service.py
│   │   ├── schemas/domain.py                   # Pydantic v2 domain models
│   │   └── cli/main.py                         # Typer + Rich CLI companion (`plan-vacation`)
│   └── calendars/
│       ├── schema/moe_calendar.schema.json     # JSON Schema (Draft 2020-12)
│       ├── moe_5786_2025_2026.json             # Verified תשפ"ו MoE calendar (Circulars schedule-o & 0346)
│       └── moe_5787_2026_2027.json             # Verified תשפ"ז MoE calendar (Circulars 0363 & 0364)
└── frontend/
    └── src/
        ├── types/domain.ts                     # TypeScript interfaces mirroring Pydantic v2 schemas
        └── components/                         # BiDi/RTL React 19 components (AppShell, BonusVacationOptionCard, etc.)
```

### 3.2 Inter-Module Service Contracts

1. **`MoECalendarService` (`calendar_engine`) $\leftrightarrow$ `VacationMaximizerEngine` (`vacation_optimizer`)**:
   - `MoECalendarService.get_daily_status_matrix(profile: FamilyProfile, start_date: date, end_date: date) -> DailyFamilyCalendarMatrix`
   - Computes per-date parent PTO cost $P(d) \in \{0.0, 0.5, 1.0\}$, `TLV` airport operational status (Yom Kippur shutdown & El Al Shabbat windows), and per-child state $S_c(d) \in \{\text{VACATION}, \text{CAMP\_OPTIONAL}, \text{SCHOOL\_FRIDAY}, \text{SCHOOL\_END\_OF\_YEAR\_WANING}, \text{SCHOOL\_REGULAR}, \text{EXAM\_BLACKOUT}\}$.
   - `VacationMaximizerEngine.generate_candidate_windows(matrix: DailyFamilyCalendarMatrix, query: FlightSearchQuery) -> list[CandidateVacationWindow]`
   - Computes $\mathcal{I}$, $\mathcal{I}_{\text{camp}}$, and $\mathcal{U}$ clusters, expands boundaries by $\pm B_{\max}$ bridge days (`Yemei Gesher`), and scores windows using `PER`, `SAP`, `CCG`, and `VUS`.
2. **`ElAlRbdDataClientAdapter` & `AllAirlinesSearchAdapter` (`providers`) $\leftrightarrow$ `BonusVacationPlannerService` (`planner_synthesizer`)**:
   - `ElAlRbdDataClientAdapter.fetch_award_availability(origin: str, destinations: list[str], start_date: date, end_date: date, force_refresh: bool = False) -> list[ElAlBonusAvailability]`
   - Expands metro codes (`NYC` $\to$ `JFK`/`EWR`, `LON` $\to$ `LHR`/`LTN`), queries `https://www.elal.com/rbddataclients/` (or 4-hour SQLite cache), and returns normalized Economy (`E`/`X`/`U`), Premium (`P`/`A`/`R`), and Business (`I`/`W`) award seat counts (`0`, `1`, `2+`) with points and port taxes.
   - `BonusVacationPlannerService.synthesize_proposals(windows: list[CandidateVacationWindow], award_inventory: list[ElAlBonusAvailability], cash_offers: list[FlightOffer], profile: FamilyProfile, query: FlightSearchQuery) -> list[VacationOptionProposal]`
   - Pairs outbound/inbound legs, solves the **5 Family Bonus Fulfillment Strategies**, computes `FBVS` and `CTOS`, and produces ranked `VacationOptionProposal` objects.

---

## 4. Two-Tier SQLite TTL Caching, Rate Limiting & Configuration

### 4.1 Two-Tier SQLite TTL Cache
- **Tier 1 — El Al Award Cache (`elal_bonus_availability`)**:
  - Key: `(origin_iata, destination_iata, flight_date, flight_number)`.
  - Default TTL: **4 hours** (`14,400 seconds`), configurable down to 15 minutes or bypassed with `force_refresh=True`.
  - Allows instant interactive re-scoring when the user adjusts bridge-day sliders or parent PTO weights without re-querying `https://www.elal.com/rbddataclients/`.
- **Tier 2 — Commercial Flight Quote Cache (`flight_itineraries`)**:
  - Key: `(origin_iata, destination_iata, departure_date, return_date, passenger_hash, airline_selection_mode)`.
  - Default TTL: **6 hours** (`21,600 seconds`).

### 4.2 Configuration File (`config/settings.yaml`)
```yaml
app:
  default_origin_iata: "TLV"
  default_currency: "USD"
  supported_currencies: ["USD", "ILS", "EUR"]
  locale_default: "he-IL"

elal_rbd_client:
  base_url: "https://www.elal.com/rbddataclients/"
  cache_ttl_seconds: 14400
  rate_limit_min_interval_sec: 2.0
  rate_limit_jitter_sec: [1.5, 3.5]
  max_route_months_per_batch: 15
  metro_iata_expansion:
    NYC: ["JFK", "EWR"]
    LON: ["LHR", "LTN"]
    PAR: ["CDG"]
    MIL: ["MXP"]
    ROM: ["FCO"]
    TYO: ["NRT"]
    MIA_AREA: ["MIA", "FLL"]

optimization_weights:
  vus_alpha_per: 0.60
  vus_beta_ccg: 0.40
  vus_gamma_sap: 0.35
  ctos_calendar_weight: 0.55
  ctos_flight_weight: 0.45
```

---

## 5. Complete 8-Table Relational Database Schema (SQLite DDL)

The complete SQLite DDL (`backend/app/db/schema.sql`) is identical to [`APPLICATION_PLAN.md` §2.5](../APPLICATION_PLAN.md#25-complete-8-table-relational-database-schema-sqlite-ddl) and defines the 8 core tables:
1. `family_profiles` — Household configuration, parent workweek (`SUN_THU`/`SUN_FRI`), Erev Chag/Chol HaMoed PTO weights, annual/per-trip PTO budgets, and household summary.
2. `passenger_loyalty_wallets` — **Per-passenger point balances across multiple frequent flyer clubs & credit card programs** (`ELAL_MATMID`, `BRITISH_AVIOS`, `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`, `QANTAS_FREQUENT_FLYER`, `AEGEAN_MILES_BONUS`, `AMEX_MR_ISRAEL`, `ISRAELI_CC_TRAVEL_POINTS`), supporting individual passenger wallets, family pooling flags, transfer ratios, and per-passenger vouchers.
3. `child_frameworks` — Per-child birthdate, passenger category (`INFANT_LAP`, `INFANT_SEAT`, `CHILD`, `YOUTH`), Israeli MoE framework (`DAYCARE_SUPERVISED`, `MUNICIPAL_GAN`, `ELEMENTARY_1_3`, `ELEMENTARY_4_6`, `MIDDLE_SCHOOL_7_9`, `HIGH_SCHOOL_10_12`, `SPECIAL_ED`, `RELIGIOUS_HAREDI`), `5` vs. `6` school week days, Nitzanim mode (`NONE`, `NITZANIM_CHAGIM_ONLY`, `NITZANIM_FULL_WITH_JULY`), and Bagrut blackout dates.
4. `moe_vacation_windows` — Verified & **annually auto-updated** Ministry of Education holiday windows (`calendar_sync_source` in `OFFICIAL_MOE_CIRCULAR`, `AUTO_SYNCED_CIRCULAR`, `HEBREW_RULE_PROJECTED`, `USER_MUNICIPAL_OVERRIDE`) with circular IDs, Nitzanim sub-windows, parent workday status, and `TLV` Yom Kippur closure flags.
5. `flight_search_queries` — Search parameters across **3 Date Selection Modes** (`SPECIFIC_DATES`, `MOE_VACATION_MAXIMIZATION`, and `HOLIDAY_DIRECT_INTENT` e.g. *"חופשת פסח 2027 — חפש כרטיסי בונוס"*) and Airline Selection Modes (`EL_AL_ONLY`, `ALL_AIRLINES`).
6. `elal_bonus_availability` — Cached Classic Award availability from `https://www.elal.com/rbddataclients/` across Economy (`E`/`X`/`U`), Premium (`P`/`A`/`R`), and Business (`I`/`W`) with `0`/`1`/`2+` (`*_seats_is_two_plus`) indicators, award zones (`ZONE_A`..`ZONE_E`), points, and taxes.
7. `flight_itineraries` — Paired outbound/inbound itineraries supporting all 6 bonus fulfillment strategies (`FULL_BONUS_SAME_CABIN`, `SPLIT_CABIN_BONUS`, `HYBRID_BONUS_PLUS_CASH`, `ONE_WAY_BONUS_ONE_WAY_CASH`, `CASH_AND_POINTS`, `MULTI_CLUB_PER_PASSENGER_SPLIT`) plus `COMMERCIAL_CASH_ONLY`, per-passenger/per-wallet point deductions (`points_used_by_wallet_json`), baggage fees, net cash saved, and Cents-Per-Point (`CPP`).
8. `vacation_option_proposals` — Joins `flight_itineraries` with MoE multi-child calendar impact (`PER`, `SAP`, `CCG`, `VUS`, `FBVS`, `CTOS`, and per-child day-by-day status breakdown).

---

## 6. REST API Endpoints (`v1`)

| Endpoint | Method | Request Body / Query Params | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/profile` | `GET` | `?profile_id=<uuid>` | `FamilyProfile` | Retrieves active household profile, children's MoE frameworks, and per-passenger multi-club loyalty wallets. |
| `/api/v1/profile` | `PUT` | `FamilyProfile` | `FamilyProfile` | Updates household profile, children's MoE frameworks, PTO rules, and per-passenger loyalty wallets across clubs. |
| `/api/v1/moe-calendar/{school_year}` | `GET` | `?profile_id=<uuid>` | `MoECalendarTimelineResponse` | Returns `MoEVacationWindow[]` for any requested school year (`2025-2026`, `2026-2027`, `2027-2028`, ...), auto-projecting or syncing future years on demand. |
| `/api/v1/moe-calendar/sync/{school_year}` | `POST` | `{ force_remote_check: bool }` | `MoECalendarSyncStatus` | **Annual Auto-Updater**: Syncs newly published Ministry of Education circulars or projects future years from statutory Hebrew rules (`pyluach`/`Hebcal i=on`). |
| `/api/v1/elal-bonus/sync` | `POST` | `{ destinations, start_date, end_date, force_refresh }` | `ElAlBonusSyncStatus` | Expands metro IATAs and syncs live award seats from `https://www.elal.com/rbddataclients/`. |
| `/api/v1/elal-bonus/availability` | `GET` | `?destination=FCO&start_date=...&end_date=...` | `list[ElAlBonusAvailability]` | Returns cached/live `rbddataclients` Classic Award inventory across Economy, Premium, and Business. |
| `/api/v1/vacations/search` | `POST` | `FlightSearchQuery` | `list[VacationOptionProposal]` | Executes unified search across Date Modes 1, 2 & 3 (`HOLIDAY_DIRECT_INTENT`) and Airline Modes 1 & 2, allocating points across per-passenger multi-club wallets. |
| `/api/v1/vacations/compare` | `POST` | `{ proposal_ids: list[str] }` | `VacationComparisonMatrix` | Produces side-by-side comparison matrix for 2–4 selected vacation proposals. |

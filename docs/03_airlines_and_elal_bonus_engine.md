# 03 — Airline Selection Modes (`EL_AL_ONLY` vs. `ALL_AIRLINES`) & El Al Bonus Ticket Engine (`https://www.elal.com/rbddataclients/`) (`R3`)

**Parent Document**: [`../APPLICATION_PLAN.md`](../APPLICATION_PLAN.md) (§4) | **Index**: [`../README.md`](../README.md)  
**Rubric Coverage**: `RUB-R3.1`, `RUB-R3.2`, `RUB-R3.3`

---

## 1. Airline Selection Mode Switcher (`EL_AL_ONLY` vs. `ALL_AIRLINES` — `RUB-R3.1`)

The planner provides an explicit top-level toggle (`airline_selection_mode`) that operates orthogonally to the Date Selection Mode (`SPECIFIC_DATES` vs. `MOE_VACATION_MAXIMIZATION`):

| Mode Enum | UI Label (Hebrew / English) | Carrier Scope | Bonus Ticket & Pricing Behavior |
|---|---|---|---|
| **`EL_AL_ONLY`** | **מיקוד בטיסות אל על (`Focus on El Al`)** | **El Al (`LY`)** mainline + optional **Sun d'Or (`LY`/`2U`)** seasonal leisure flights from/to `TLV`. | • Enforces **El Al Shabbat operational windows** (no departures between Fri afternoon and Motzei Shabbat).<br>• Unlocks the **El Al Bonus Ticket Search Engine** querying `https://www.elal.com/rbddataclients/`.<br>• Synthesizes complete vacation options across **5 Family Bonus Fulfillment Strategies** benchmarked against El Al commercial cash fares. |
| **`ALL_AIRLINES`** | **כל חברות התעופה (`All Airlines`)** | All full-service and low-cost carriers serving `TLV` (`LY`, `6H`, `IZ`, `BZ`, `U8`, `W6`, `FR`, `U2`, `A3`, `LH`, `OS`, `LX`, `BA`, `AF`, `UA`, `DL`, `FZ`, `EY`, etc.). | • Queries the 3-tier multi-airline flight engine (`fast-flights`/`fli`, `SerpApi Google Flights`, `Duffel API`).<br>• Applies the **Family Baggage Cost Normalizer** (automatically adding required cabin trolleys + checked suitcases to LCC base fares). |

---

## 2. Technical Specification of `https://www.elal.com/rbddataclients/` Integration (`RUB-R3.2`)

### 2.1 Role & Mechanics of `https://www.elal.com/rbddataclients/`
- `https://www.elal.com/rbddataclients/` is El Al's standalone **Matmid Classic Award Seat Availability Calculator** (`מחשבון זמינות מושבי בונוס`).
- It queries Classic Award inventory across **Economy (`תיירים`)**, **Premium (`פרימיום`)**, and **Business (`עסקים`)** cabins up to ~11–12 months ahead, returning per-date / per-flight seat availability indicators (`0`, `1`, or `2` representing `2+` available seats), base one-way Matmid point costs, and mandatory airport taxes (USD).

### 2.2 Metropolitan-to-Airport 3-Letter IATA Expansion Rule
- Unlike `elal.com`'s main commercial booking widget, `https://www.elal.com/rbddataclients/` **rejects metropolitan city codes** (`NYC`, `LON`, `PAR`, `MIL`, `ROM`, `TYO`).
- `ElAlRbdDataClientAdapter` automatically expands any city/metro code into constituent El Al 3-letter airport IATA codes before querying `rbddataclients`:
  - `NYC` $\to$ `["JFK", "EWR"]`
  - `LON` $\to$ `["LHR", "LTN"]`
  - `PAR` $\to$ `["CDG"]`
  - `MIL` $\to$ `["MXP"]`
  - `ROM` $\to$ `["FCO"]`
  - `TYO` $\to$ `["NRT"]`
  - `MIA_AREA` $\to$ `["MIA", "FLL"]`

### 2.3 Playwright + XHR Ingestion, Rate Limiting & SQLite Caching
1. **Session & XHR Interception**: Because `elal.com` sits behind Akamai/Cloudflare WAF protection, `ElAlRbdDataClientAdapter` uses a warmed **Playwright headless Chromium context** (with `httpx` cookie reuse) to navigate `https://www.elal.com/rbddataclients/` and intercept the JSON award availability grid.
2. **Polite Token-Bucket Rate Limiter**: Maximum **1 request per 2.0–3.5 seconds** (with random jitter) and a cap of **15 route-month queries per batch**.
3. **4-Hour SQLite TTL Cache (`elal_bonus_availability`)**: Stores normalized responses keyed by `(origin_iata, destination_iata, flight_date, flight_number)` with a 4-hour default TTL.

---

## 3. El Al RBD Bucket Mapping, Pure Points + Taxes Zone Table & Fly Card Promotions

### 3.1 El Al (`LY`) Reservation Booking Designator (RBD) Mapping
| Cabin Class | Classic Award / Bonus RBD Codes (`rbddataclients`) | Commercial Revenue RBD Codes | Fleet & Family Notes |
|---|---|---|---|
| **Economy (`תיירים`)** | **`E`**, **`X`**, **`U`** | Full/Flex: `Y`, `S`, `M`<br>Classic: `Q`, `B`, `H`, `V`, `N`<br>Lite: `K`, `L`, `T`, `O`, `G` | Present on all El Al mainline (`787`, `777`, `737`) and Sun d'Or (`LY`/`2U`) aircraft. Includes 1 checked bag ($23\text{ kg}$) + 1 trolley. |
| **Premium (`פרימיום`)** | **`P`** (plus promo/upgrade **`A`**, **`R`**) | `W`, `Q`, `B`, `P` | Present on widebody fleet (`787-8/9`, `777-200ER`). Not available on narrowbody `737` routes unless widebody-operated. |
| **Business (`עסקים`)** | **`I`**, **`W`** | Full: `J`, `C`<br>Discounted: `D`, `Z`, `I`, `R` | Lie-flat on `787`/`777`, recliner on `737`. Highest Cents-Per-Point (`CPP`) value on long-haul routes. |

### 3.2 Pure Points + Taxes Zone Reference Table (One-Way per Passenger)
See [`APPLICATION_PLAN.md` §4.3 Table 4.3B](../APPLICATION_PLAN.md#43-el-al-rbd-bucket-mapping-pure-points--taxes-zone-table--fly-card-promotions) for the full 5-zone table (`ZONE_A` Short-Haul Greece/Cyprus `7,500–15,000 pts` Economy; `ZONE_B` Central Europe/Italy `15,000–22,500 pts`; `ZONE_C` Western Europe/UK `20,000–25,000 pts`; `ZONE_D` Far East/Africa `35,000–45,000 pts`; `ZONE_E` North America `35,000–47,500 pts`), including **Fly Card / Fly Card Premium** discounts and recurring **"Tuesday Points Party" (50% off points)** promotions.

---

## 4. Solving the "`2` (`2+`) Seat Cap": The 5 Family Bonus Fulfillment Strategies (`RUB-R3.3`)

Because `https://www.elal.com/rbddataclients/` displays `0`, `1`, or `2` (`2+` seats available) per cabin while a family requires $N \in \{3..6\}$ tickets, `BonusVacationPlannerService` synthesizes and ranks **five concrete Family Bonus Ticket Fulfillment Strategies**:

1. **`FULL_BONUS_SAME_CABIN` (Full-Family Single-Cabin Bonus)**:
   - Triggered when `rbddataclients` reports `2` (`2+`) in the target cabin (e.g., Economy `E`) on both outbound and inbound legs and `matmid_points_balance` covers all $N$ passengers.
   - Sets `requires_two_plus_seat_verification = True` when $N \ge 3$ and generates a 1-click verification deep link to `elal.com` checkout for $N$ passengers.
2. **`SPLIT_CABIN_BONUS` (Full-Family Split-Cabin Bonus on Exact Same Flight)**:
   - Triggered when the **exact same flight** has `2` (`2+`) seats in Economy (`E`) AND `1`–`2` (`2+`) seats in Premium (`P`) or Business (`I`).
   - Example (Family of 4): **2 Economy Bonus (`E`) + 2 Premium/Business Bonus (`P`/`I`) on the exact same `LY` flight**. Guarantees 4 confirmed bonus seats on the same aircraft using 100% points + taxes!
3. **`HYBRID_BONUS_PLUS_CASH` (Mixed Bonus + Commercial Cash on Exact Same Flight)**:
   - Triggered when available bonus seats $K < N$ (or when the family's Matmid point wallet covers $K$ seats).
   - Example (Family of 5 on `LY381`/`LY384` Rome): **2 Economy Bonus (`E`) + 2 Premium/Business Bonus (`P`/`I`) + 1 Commercial Cash ticket on the exact same flight**. Computes blended cost (`142,000 pts + $390 award taxes + $460 cash ticket = $850 out-of-pocket` vs. `$2,950` full cash benchmark $\to$ **`$2,100` saved**, `CPP = 1.48¢`). Enforces adult-child PNR pairing so no child under 12 is isolated on a separate PNR.
4. **`ONE_WAY_BONUS_ONE_WAY_CASH` / `OPEN_JAW_BONUS` (Asymmetric Direction or Open-Jaw Mix)**:
   - Exploits El Al's one-way modular award pricing when peak outbound dates have `0` award seats (`Cash` outbound + `Bonus` inbound) or when flying Bonus into `MXP` (Milan) and returning Bonus from `FCO` (Rome) both have `2+` award seats.
5. **`CASH_AND_POINTS` (El Al Commercial Fare with Matmid Cash & Points Discount)**:
   - Fallback when `rbddataclients` reports `0` Classic Award seats across all cabins, flagging when effective $\text{CPP} < 0.8\text{¢}$.
6. **`MULTI_CLUB_PER_PASSENGER_SPLIT` (Per-Passenger & Multi-Club Loyalty Wallet Allocation)**:
   - Uses the `passenger_loyalty_wallets` table to track the exact available points $W_{p, m}$ for **each individual passenger $p$ across multiple frequent flyer programs $m$** (`ELAL_MATMID`, `BRITISH_AVIOS`, `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`, `QANTAS_FREQUENT_FLYER`, `AEGEAN_MILES_BONUS`, `AMEX_MR_ISRAEL`, `ISRAELI_CC_TRAVEL_POINTS`).
   - **Per-Passenger Account Splitting within El Al Matmid**: When Parent 1 and Parent 2 hold separate Matmid balances (e.g., `75,000 pts` and `68,000 pts`), allocates integer passenger tickets to each account without exceeding either passenger's balance.
   - **Cross-Club Family & Directional Splitting**: Combines El Al Matmid bonus tickets (e.g., outbound on `LY` via `rbddataclients`, or 3 passengers on `ELAL_MATMID`) with partner or other airline loyalty clubs (e.g., inbound on `BRITISH_AVIOS` / `FLYING_BLUE` / `MILES_AND_MORE` / `UNITED_MILEAGEPLUS`, or 2 passengers via `DELTA_SKYMILES` / `QANTAS_FREQUENT_FLYER` / transferable `AMEX_MR_ISRAEL` points), showing a clear **Per-Passenger & Per-Club Point Deduction Summary** on every vacation card.

---

## 5. 3-Tier Commercial Flight Provider Architecture (`ALL_AIRLINES` & Cash Benchmarks)

To support **Mode 2 (`ALL_AIRLINES`)** and provide accurate commercial cash benchmarks in **Mode 1 (`EL_AL_ONLY`)** in the 2025–2026 API landscape (where Amadeus Self-Service closed its public free portal and Kiwi Tequila became invite-only), `AllAirlinesSearchAdapter` implements a 3-tier provider chain:
1. **Tier 1 (Primary Keyless Engine)**: `fast-flights` / `fli` (direct Google Flights Protobuf/RPC query client, zero API keys or quotas).
2. **Tier 2 (Structured Free-Tier JSON API)**: **SerpApi Google Flights API** (`serpapi.com`, 250 free live searches/month + unlimited free 1h cached queries).
3. **Tier 3 (Official NDC/GDS Developer REST API)**: **Duffel API** (`duffel.com` offer requests), plus optional adapter interfaces for enterprise `Amadeus` / `Kiwi Tequila` credentials.

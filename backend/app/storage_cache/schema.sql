PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 0a. Users: Verified Gmail / Google OIDC accounts & opt-in future notification readiness
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                          -- UUID v4 internal user_id
    google_sub TEXT NOT NULL UNIQUE,              -- Immutable Google OIDC 'sub' claim
    email TEXT NOT NULL UNIQUE,                   -- Normalized lowercase verified Gmail/Google address
    email_verified INTEGER NOT NULL DEFAULT 1 CHECK (email_verified IN (0, 1)),
    display_name TEXT NOT NULL DEFAULT '',
    notification_email TEXT NOT NULL,             -- Locked to verified email for future notifications
    notifications_enabled INTEGER NOT NULL DEFAULT 0 CHECK (notifications_enabled IN (0, 1)),
    notification_preferences_json TEXT NOT NULL DEFAULT '{"award_seat_alerts":false,"holiday_reminders":false,"preferred_locale":"he"}',
    notification_consent_updated_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 0b. AuthSessions: Revocable server-side sessions storing SHA-256 token digest only
CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,                          -- UUID v4
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_sha256 TEXT NOT NULL UNIQUE,            -- SHA-256 hex digest of raw cookie token (raw token never stored)
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);

-- 0c. OAuthLoginStates: Single-use 10-minute PKCE (S256) + Login-CSRF cookie binding
CREATE TABLE IF NOT EXISTS oauth_login_states (
    state_sha256 TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    nonce TEXT NOT NULL,
    browser_binding_sha256 TEXT NOT NULL,
    return_to TEXT NOT NULL DEFAULT '/',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- 1. FamilyProfile: Stores household configuration and default household Matmid summary
CREATE TABLE IF NOT EXISTS family_profiles (
    id TEXT PRIMARY KEY,                          -- UUID v4 or user-profile-<user_id>
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    is_legacy_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (is_legacy_quarantined IN (0, 1)),
    profile_name TEXT NOT NULL DEFAULT 'המשפחה שלי',
    adults_count INTEGER NOT NULL DEFAULT 2 CHECK (adults_count BETWEEN 1 AND 6),
    matmid_points_balance INTEGER NOT NULL DEFAULT 0 CHECK (matmid_points_balance >= 0),
    has_flycard INTEGER NOT NULL DEFAULT 1 CHECK (has_flycard IN (0, 1)),
    flycard_tier TEXT NOT NULL DEFAULT 'FLY_CARD_PREMIUM' CHECK (flycard_tier IN ('NONE', 'FLY_CARD', 'FLY_CARD_PREMIUM')),
    flycard_companion_vouchers INTEGER NOT NULL DEFAULT 0 CHECK (flycard_companion_vouchers >= 0),
    point_valuation_usd REAL NOT NULL DEFAULT 0.016 CHECK (point_valuation_usd > 0.0),
    preferred_currency TEXT NOT NULL DEFAULT 'USD' CHECK (preferred_currency IN ('USD', 'ILS', 'EUR')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_family_profiles_user_id ON family_profiles(user_id) WHERE user_id IS NOT NULL;

-- 2. PassengerLoyaltyWallet: Per-passenger available points across multiple frequent flyer clubs & credit card programs
CREATE TABLE IF NOT EXISTS passenger_loyalty_wallets (
    id TEXT PRIMARY KEY,                          -- UUID v4
    family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
    passenger_id TEXT NOT NULL,                   -- e.g. 'ADULT_1', 'ADULT_2', 'CHILD_1', or 'FAMILY_POOL'
    passenger_name TEXT NOT NULL,                 -- e.g. 'הורה 1', 'הורה 2', 'ילד/ה 1'
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
CREATE INDEX IF NOT EXISTS idx_loyalty_wallets_profile_pax ON passenger_loyalty_wallets(family_profile_id, passenger_id, program_code);

-- 3. ChildFramework: Stores each child's age and (optionally, when searching by vacations) their Israeli Ministry of Education framework
CREATE TABLE IF NOT EXISTS child_frameworks (
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

-- 4. MoEVacationWindow: Official Israeli Ministry of Education holiday & vacation windows per school year
CREATE TABLE IF NOT EXISTS moe_vacation_windows (
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
CREATE INDEX IF NOT EXISTS idx_moe_vacation_year_framework ON moe_vacation_windows(school_year, framework_type, start_date);

-- 5. FlightSearchQuery: Captures user search execution across Date Mode (Specific Dates or Holiday Direct Intent) and Airline Mode (1/2)
CREATE TABLE IF NOT EXISTS flight_search_queries (
    id TEXT PRIMARY KEY,                          -- UUID v4
    family_profile_id TEXT REFERENCES family_profiles(id) ON DELETE CASCADE,
    date_selection_mode TEXT NOT NULL CHECK (date_selection_mode IN (
        'SPECIFIC_DATES',                         -- Mode 1: Specific / Flexible Dates
        'HOLIDAY_DIRECT_INTENT'                   -- Holiday Mode: Specific Holiday/Vacation + Year Planner (e.g. Pesach 2027)
    )),
    airline_selection_mode TEXT NOT NULL CHECK (airline_selection_mode IN (
        'EL_AL_ONLY',                             -- R3 Mode 1: Focus on El Al (including rbddataclients bonus)
        'ALL_AIRLINES'                            -- R3 Mode 2: All Airlines (including multi-club bonus & commercial fares)
    )),
    search_elal_bonus_tickets INTEGER NOT NULL DEFAULT 1 CHECK (search_elal_bonus_tickets IN (0, 1)),
    include_sundor_flights INTEGER NOT NULL DEFAULT 1 CHECK (include_sundor_flights IN (0, 1)),
    origin_iata TEXT NOT NULL DEFAULT 'TLV',
    destination_iatas_json TEXT NOT NULL,         -- JSON array of IATA/Metro codes or '["ANYWHERE"]'
    -- Specific Dates fields:
    specific_departure_date TEXT,                 -- YYYY-MM-DD
    specific_return_date TEXT,                    -- YYYY-MM-DD
    flex_days_plus_minus INTEGER NOT NULL DEFAULT 0 CHECK (flex_days_plus_minus BETWEEN 0 AND 7),
    -- School-year & holiday filter fields:
    school_year TEXT,                             -- e.g. '2025-2026', '2026-2027', '2027-2028'
    target_holiday_codes_json TEXT,               -- JSON array of holiday_code strings
    -- Direct Holiday/Vacation + Year fields:
    direct_holiday_code TEXT,                     -- Selected holiday/vacation code: e.g. 'PESACH', 'SUKKOT', 'HANUKKAH', 'ROSH_HASHANAH', 'PURIM', 'SHAVUOT', 'SUMMER_JULY', 'SUMMER_AUGUST'
    direct_target_year INTEGER CHECK (direct_target_year IS NULL OR direct_target_year BETWEEN 2025 AND 2035), -- Selected year: e.g. 2027
    min_trip_nights INTEGER NOT NULL DEFAULT 4 CHECK (min_trip_nights >= 1),
    max_trip_nights INTEGER NOT NULL DEFAULT 10 CHECK (max_trip_nights >= min_trip_nights),
    max_bridge_days_shift INTEGER NOT NULL DEFAULT 3 CHECK (max_bridge_days_shift BETWEEN 0 AND 5),
    overlap_policy TEXT NOT NULL DEFAULT 'CAMP_ADJUSTED_INTERSECTION' CHECK (overlap_policy IN (
        'STRICT_ALL_CHILDREN_OFF',
        'CAMP_ADJUSTED_INTERSECTION'
    )),
    -- El Al & Multi-Club Bonus Filters:
    preferred_cabins_json TEXT NOT NULL DEFAULT '["ECONOMY","PREMIUM","BUSINESS"]',
    enabled_loyalty_programs_json TEXT NOT NULL DEFAULT '["ELAL_MATMID"]', -- Can include multiple clubs per passenger
    preferred_vacation_types_json TEXT NOT NULL DEFAULT '[]',
    weather_filter_mode TEXT NOT NULL DEFAULT 'SOFT_PRIORITIZE' CHECK (weather_filter_mode IN ('SOFT_PRIORITIZE', 'HARD_THRESHOLD')),
    min_weather_suitability_score REAL CHECK (min_weather_suitability_score IS NULL OR (min_weather_suitability_score BETWEEN 0.0 AND 100.0)),
    allow_hybrid_bonus_cash INTEGER NOT NULL DEFAULT 1 CHECK (allow_hybrid_bonus_cash IN (0, 1)),
    direct_flights_only INTEGER NOT NULL DEFAULT 1 CHECK (direct_flights_only IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 6. ElAlBonusAvailability: Cached Classic Award records fetched from https://www.elal.com/rbddataclients/
CREATE TABLE IF NOT EXISTS elal_bonus_availability (
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
CREATE INDEX IF NOT EXISTS idx_elal_bonus_route_date ON elal_bonus_availability(origin_iata, destination_iata, flight_date);

-- 7. FlightItinerary: Round-trip or Open-Jaw flight pairing (El Al Bonus, Hybrid, or All-Airlines Cash)
CREATE TABLE IF NOT EXISTS flight_itineraries (
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
    seated_passengers_count INTEGER NOT NULL DEFAULT 1 CHECK (seated_passengers_count >= 1),
    bonus_tickets_count INTEGER NOT NULL DEFAULT 0 CHECK (bonus_tickets_count >= 0),
    cash_tickets_count INTEGER NOT NULL DEFAULT 0 CHECK (cash_tickets_count >= 0),
    primary_cabin TEXT NOT NULL DEFAULT 'ECONOMY' CHECK (primary_cabin IN ('ECONOMY', 'PREMIUM', 'BUSINESS')),
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

-- 8. VacationOptionProposal: Joins a FlightItinerary with MoE Multi-Child School Break Alignment Metrics
CREATE TABLE IF NOT EXISTS vacation_option_proposals (
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
    school_absence_penalty REAL NOT NULL,         -- SAP weighted school absence penalty across children
    childcare_coverage_gain REAL NOT NULL,        -- CCG fraction of trip covering unsupervised vacation/weekend days
    per_child_impact_json TEXT NOT NULL,          -- JSON array of ChildTripImpact objects
    total_school_days_missed_across_children INTEGER NOT NULL CHECK (total_school_days_missed_across_children >= 0),
    max_single_child_school_days_missed INTEGER NOT NULL CHECK (max_single_child_school_days_missed >= 0),
    -- Explicit Mathematical Scoring Breakdown (0 to 100):
    holiday_alignment_score REAL NOT NULL DEFAULT 0.0 CHECK (holiday_alignment_score >= 0.0 AND holiday_alignment_score <= 100.0), -- HAS
    flight_bonus_value_score REAL NOT NULL CHECK (flight_bonus_value_score BETWEEN 0.0 AND 100.0),   -- FBVS
    weather_suitability_score REAL NOT NULL DEFAULT 0.0 CHECK (weather_suitability_score BETWEEN 0.0 AND 100.0), -- WSS
    vacation_type_scores_json TEXT NOT NULL DEFAULT '{}',
    weather_metrics_json TEXT,
    combined_trip_optimization_score REAL NOT NULL CHECK (combined_trip_optimization_score BETWEEN 0.0 AND 100.0), -- CTOS
    explanation_summary_he TEXT NOT NULL,         -- Hebrew explanation of school break alignment + bonus value
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_proposals_query_rank ON vacation_option_proposals(search_query_id, combined_trip_optimization_score DESC);

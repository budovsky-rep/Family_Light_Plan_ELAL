/**
 * Family Vacation Planner — Interactive Frontend Application (`frontend/src/app.js`)
 *
 * Implements:
 * - Rolling 1-Year Holiday Selection (`HOLIDAY_DIRECT_INTENT`) with upcoming year & holiday length `(N days)`
 *   initializing editable `#input-max-nights`
 * - Manual Date Entry + `±` Day Flexibility (`SPECIFIC_DATES`, optional `child.framework_type`)
 * - Exclusive El Al (`EL_AL_ONLY`) & single household Matmid balance (`#prof-matmid-points`)
 * - Default `ANYWHERE` destination discovery across all open El Al routes
 * - Boarding-Pass styled vacation proposal cards with visual flight route telemetry
 * - All 8 Israeli Ministry of Education (`MoEFrameworkType`) frameworks + age-based auto-suggestion
 * - BiDi Hebrew (`rtl` / `he`) & English (`ltr` / `en`) live layout switcher
 */

(function () {
  'use strict';

  const MOE_FRAMEWORKS = [
    { value: '', labelHe: 'ללא מסגרת / אופציונלי (Optional / null)', labelEn: 'Optional / None (Manual Dates)' },
    { value: 'DAYCARE_SUPERVISED', labelHe: 'מעונות יום בפיקוח (גילאי 0–3 — עד 8 באוגוסט)', labelEn: 'Supervised Daycare (Ages 0–3)' },
    { value: 'MUNICIPAL_GAN', labelHe: 'גני ילדים עירוניים (גילאי 3–6 — עד 30 ביוני + ניצנים)', labelEn: 'Municipal Kindergarten (Ages 3–6 + Nitzanim)' },
    { value: 'ELEMENTARY_1_3', labelHe: 'יסודי כיתות א׳–ג׳ (גילאי 6–9 — עד 30 ביוני + ניצנים)', labelEn: 'Elementary Grades 1–3 (+ Nitzanim)' },
    { value: 'ELEMENTARY_4_6', labelHe: 'יסודי כיתות ד׳–ו׳ (גילאי 9–12 — עד 30 ביוני)', labelEn: 'Elementary Grades 4–6' },
    { value: 'MIDDLE_SCHOOL_7_9', labelHe: 'חטיבת ביניים כיתות ז׳–ט׳ (גילאי 12–15 — עד 20 ביוני)', labelEn: 'Middle School Grades 7–9 (Ends June 20)' },
    { value: 'HIGH_SCHOOL_10_12', labelHe: 'תיכון כיתות י׳–י"ב (גילאי 15–18 — עד 20 ביוני + בגרויות)', labelEn: 'High School Grades 10–12 (Ends June 20)' },
    { value: 'SPECIAL_ED', labelHe: 'חינוך מיוחד (הארכה עד 15 באוגוסט)', labelEn: 'Special Education (Until Aug 15)' },
    { value: 'RELIGIOUS_HAREDI', labelHe: 'חינוך ממלכתי-דתי / חרדי', labelEn: 'Religious / Haredi Framework' }
  ];

  const CANONICAL_ROLLING_HOLIDAYS = [
    { code: 'ROSH_HASHANAH', nameHe: 'ראש השנה', nameEn: 'Rosh Hashanah' },
    { code: 'YOM_KIPPUR_SUKKOT_BRIDGE', nameHe: 'גשר יום כיפור–סוכות', nameEn: 'Yom Kippur–Sukkot Bridge' },
    { code: 'SUKKOT', nameHe: 'חופשת סוכות', nameEn: 'Sukkot Break' },
    { code: 'HANUKKAH', nameHe: 'חופשת חנוכה', nameEn: 'Hanukkah Break' },
    { code: 'PURIM', nameHe: 'חופשת פורים', nameEn: 'Purim Break' },
    { code: 'PESACH', nameHe: 'חופשת פסח', nameEn: 'Passover Break' },
    { code: 'YOM_HAATZMAUT', nameHe: 'יום העצמאות', nameEn: 'Independence Day' },
    { code: 'SHAVUOT', nameHe: 'חופשת שבועות', nameEn: 'Shavuot Break' },
    { code: 'SUMMER_JUNE_20_30', nameHe: 'החופש הגדול — 20–30 ביוני', nameEn: 'Summer Break — June 20–30' },
    { code: 'SUMMER_JULY', nameHe: 'החופש הגדול — יולי', nameEn: 'Summer Break — July' },
    { code: 'SUMMER_AUGUST', nameHe: 'החופש הגדול — אוגוסט', nameEn: 'Summer Break — August' }
  ];

  const CANONICAL_WORKPLACE_ROLLING_HOLIDAYS = [
    { code: 'ROSH_HASHANAH', nameHe: 'ראש השנה', nameEn: 'Rosh Hashanah', autumn: true },
    { code: 'YOM_KIPPUR_SUKKOT_BRIDGE', nameHe: 'גשר כיפור–סוכות', nameEn: 'Yom Kippur–Sukkot Bridge', autumn: true },
    { code: 'SUKKOT', nameHe: 'סוכות וחול המועד', nameEn: 'Sukkot & Chol HaMoed', autumn: true },
    { code: 'PESACH', nameHe: 'פסח וחול המועד', nameEn: 'Passover & Chol HaMoed', autumn: false },
    { code: 'YOM_HAATZMAUT', nameHe: 'יום העצמאות (גשר סופ״ש)', nameEn: 'Independence Day Bridge', autumn: false },
    { code: 'SHAVUOT', nameHe: 'חג השבועות (סופ״ש ארוך)', nameEn: 'Shavuot Long Weekend', autumn: false }
  ];

  const WORKPLACE_INDIVIDUAL_HOLIDAYS_CLIENT = [
    { code: 'ROSH_HASHANAH', nameHe: 'ראש השנה', nameEn: 'Rosh Hashanah', autumn: true },
    { code: 'SUKKOT', nameHe: 'סוכות בלבד (חול המועד)', nameEn: 'Sukkot Alone (Chol HaMoed)', autumn: true },
    { code: 'PESACH', nameHe: 'פסח וחול המועד', nameEn: 'Passover & Chol HaMoed', autumn: false },
    { code: 'YOM_HAATZMAUT', nameHe: 'יום העצמאות', nameEn: 'Independence Day', autumn: false },
    { code: 'SHAVUOT', nameHe: 'חג השבועות', nameEn: 'Shavuot', autumn: false }
  ];

  const WORKPLACE_MEGA_BRIDGE_HOLIDAYS_CLIENT = [
    {
      code: 'FULL_TISHREI',
      nameHe: 'כל חגי תשרי: ראש השנה → סוכות',
      nameEn: 'All Tishrei Holidays: Rosh Hashanah → Sukkot',
      constituents: ['ROSH_HASHANAH', 'YOM_KIPPUR', 'SUKKOT'],
      prio: 1
    },
    {
      code: 'YOM_KIPPUR_SUKKOT_BRIDGE',
      nameHe: 'גשר כיפור–סוכות',
      nameEn: 'Yom Kippur–Sukkot Bridge',
      constituents: ['YOM_KIPPUR', 'SUKKOT'],
      prio: 2
    },
    {
      code: 'ROSH_HASHANAH_KIPPUR_BRIDGE',
      nameHe: 'גשר ראש השנה–כיפור',
      nameEn: 'Rosh Hashanah–Yom Kippur Bridge',
      constituents: ['ROSH_HASHANAH', 'YOM_KIPPUR'],
      prio: 3
    }
  ];

  const WORKPLACE_RECOMMENDED_NIGHTS_CLIENT = {
    BEST_YEAR_MAXIMIZER: [3, 15],
    FULL_TISHREI: [16, 23],
    YOM_KIPPUR_SUKKOT_BRIDGE: [10, 16],
    YOM_KIPPUR_SUKKOT: [10, 16],
    ROSH_HASHANAH_KIPPUR_BRIDGE: [9, 13],
    SUKKOT: [4, 8],
    PESACH: [4, 7],
    ROSH_HASHANAH: [2, 4],
    YOM_HAATZMAUT: [2, 4],
    SHAVUOT: [2, 4]
  };

  const SHORT_MONTHS_HE = [
    'ינו׳', 'פבר׳', 'מרץ', 'אפר׳', 'מאי', 'יונ׳',
    'יול׳', 'אוג׳', 'ספט׳', 'אוק׳', 'נוב׳', 'דצמ׳'
  ];
  const SHORT_MONTHS_EN = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
  ];

  const ALL_8_FRAMEWORKS = [
    'DAYCARE_SUPERVISED',
    'MUNICIPAL_GAN',
    'ELEMENTARY_1_3',
    'ELEMENTARY_4_6',
    'MIDDLE_SCHOOL_7_9',
    'HIGH_SCHOOL_10_12',
    'SPECIAL_ED',
    'RELIGIOUS_HAREDI'
  ];
  const K12_NO_DAYCARE = ALL_8_FRAMEWORKS.filter((fw) => fw !== 'DAYCARE_SUPERVISED');

  const BUNDLED_SCHOOL_YEAR_PERIODS = {
    '2025-2026': [
      { code: 'ROSH_HASHANAH', start: '2025-09-22', end: '2025-09-24', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'YOM_KIPPUR_SUKKOT', start: '2025-10-01', end: '2025-10-14', fws: ALL_8_FRAMEWORKS, overrides: { HIGH_SCHOOL_10_12: ['2025-10-01', '2025-10-15'] } },
      { code: 'HANUKKAH', start: '2025-12-16', end: '2025-12-22', fws: K12_NO_DAYCARE, overrides: {} },
      { code: 'PURIM', start: '2026-03-03', end: '2026-03-04', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'PESACH', start: '2026-03-24', end: '2026-04-08', fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: ['2026-04-01', '2026-04-08'] } },
      { code: 'YOM_HAATZMAUT', start: '2026-04-22', end: '2026-04-22', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SHAVUOT', start: '2026-05-21', end: '2026-05-22', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SUMMER_JUNE_20_30', start: '2026-06-19', end: '2026-06-30', fws: ['MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12'], overrides: {} },
      { code: 'SUMMER_JULY', start: '2026-07-01', end: '2026-07-31', fws: ['MUNICIPAL_GAN', 'ELEMENTARY_1_3', 'ELEMENTARY_4_6', 'MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12', 'RELIGIOUS_HAREDI'], overrides: {} },
      { code: 'SUMMER_AUGUST', start: '2026-08-01', end: '2026-08-31', fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: ['2026-08-09', '2026-08-31'], SPECIAL_ED: ['2026-08-16', '2026-08-31'] } }
    ],
    '2026-2027': [
      { code: 'ROSH_HASHANAH', start: '2026-09-11', end: '2026-09-13', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'YOM_KIPPUR_SUKKOT', start: '2026-09-20', end: '2026-10-03', fws: ALL_8_FRAMEWORKS, overrides: { HIGH_SCHOOL_10_12: ['2026-09-20', '2026-10-04'] } },
      { code: 'HANUKKAH', start: '2026-12-06', end: '2026-12-12', fws: K12_NO_DAYCARE, overrides: {} },
      { code: 'PURIM', start: '2027-03-23', end: '2027-03-24', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'PESACH', start: '2027-04-13', end: '2027-04-28', fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: ['2027-04-21', '2027-04-28'] } },
      { code: 'YOM_HAATZMAUT', start: '2027-05-12', end: '2027-05-12', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SHAVUOT', start: '2027-06-10', end: '2027-06-11', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SUMMER_JUNE_20_30', start: '2027-06-21', end: '2027-06-30', fws: ['MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12'], overrides: {} },
      { code: 'SUMMER_JULY', start: '2027-07-01', end: '2027-07-31', fws: ['MUNICIPAL_GAN', 'ELEMENTARY_1_3', 'ELEMENTARY_4_6', 'MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12', 'RELIGIOUS_HAREDI'], overrides: {} },
      { code: 'SUMMER_AUGUST', start: '2027-08-01', end: '2027-08-31', fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: ['2027-08-09', '2027-08-31'], SPECIAL_ED: ['2027-08-16', '2027-08-31'] } }
    ],
    '2027-2028': [
      { code: 'ROSH_HASHANAH', start: '2027-10-01', end: '2027-10-03', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'YOM_KIPPUR_SUKKOT', start: '2027-10-10', end: '2027-10-23', fws: ALL_8_FRAMEWORKS, overrides: { HIGH_SCHOOL_10_12: ['2027-10-10', '2027-10-24'] } },
      { code: 'HANUKKAH', start: '2027-12-26', end: '2028-01-01', fws: K12_NO_DAYCARE, overrides: {} },
      { code: 'PURIM', start: '2028-03-12', end: '2028-03-13', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'PESACH', start: '2028-04-02', end: '2028-04-17', fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: ['2028-04-10', '2028-04-17'] } },
      { code: 'YOM_HAATZMAUT', start: '2028-05-02', end: '2028-05-02', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SHAVUOT', start: '2028-05-31', end: '2028-06-01', fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SUMMER_JUNE_20_30', start: '2028-06-21', end: '2028-06-30', fws: ['MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12'], overrides: {} },
      { code: 'SUMMER_JULY', start: '2028-07-01', end: '2028-07-31', fws: ['MUNICIPAL_GAN', 'ELEMENTARY_1_3', 'ELEMENTARY_4_6', 'MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12', 'RELIGIOUS_HAREDI'], overrides: {} },
      { code: 'SUMMER_AUGUST', start: '2028-08-01', end: '2028-08-31', fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: ['2028-08-09', '2028-08-31'], SPECIAL_ED: ['2028-08-16', '2028-08-31'] } }
    ]
  };

  const DESTINATION_ICONS = {
    ROM: '🏛️',
    FCO: '🏛️',
    MXP: '🏔️',
    VCE: '🛶',
    VRN: '🎢',
    NAP: '🍕',
    ATH: '🏖️',
    RHO: '🏝️',
    HER: '🏝️',
    SKG: '🌊',
    CFU: '🏝️',
    EFL: '🏖️',
    PVK: '🏖️',
    JMK: '🏝️',
    JTR: '🌅',
    LCA: '☀️',
    PFO: '🏖️',
    TBS: '🏔️',
    BUS: '🌊',
    TIV: '⛵',
    TIA: '🏖️',
    DBV: '🏰',
    ZAG: '🏞️',
    LJU: '🏞️',
    BEG: '🏰',
    OTP: '🏰',
    SOF: '⛰️',
    RMO: '🍇',
    PAR: '🥐',
    CDG: '🥐',
    LYS: '⛷️',
    NCE: '🏖️',
    LON: '🎡',
    LHR: '🎡',
    LTN: '🎡',
    MAD: '💃',
    BCN: '🌊',
    GVA: '⛷️',
    ZRH: '🏔️',
    BSL: '🎢',
    MUC: '🏰',
    FRA: '🎢',
    VIE: '🎻',
    SZG: '⛷️',
    PRG: '🏰',
    BUD: '♨️',
    WAW: '🏰',
    KRK: '🎢',
    AMS: '🌷',
    BER: '🐻',
    LIS: '🚋',
    OPO: '🍷',
    DXB: '☀️',
    SEZ: '🏝️',
    NYC: '🗽',
    JFK: '🗽',
    EWR: '🗽',
    BOS: '🍂',
    MIA: '🌴',
    FLL: '🌴',
    LAX: '🎬',
    BKK: '🌴',
    HKT: '🏝️',
    TYO: '⛩️',
    NRT: '⛩️'
  };

  const VACATION_TYPE_LABELS_HE = {
    ANY: '🌍 הכל (ללא סינון)',
    BEACH_AND_POOL: '🏖️ בטן-גב (חוף ובריכה)',
    NATURE_TRIP: '🥾 טיול בטבע ונופים',
    URBAN_CULTURE: '🏛️ עיר, תרבות ושופינג',
    FAMILY_ATTRACTIONS_PARKS: '🎢 פארקים ואטרקציות',
    SNOW_AND_SKI: '⛷️ חופשת שלג וסקי',
    WINTER_FESTIVE: '🎄 שווקי חורף'
  };

  const VACATION_TYPE_LABELS_EN = {
    ANY: '🌍 All Styles',
    BEACH_AND_POOL: '🏖️ Beach & Pool',
    NATURE_TRIP: '🥾 Nature & Hiking',
    URBAN_CULTURE: '🏛️ Urban & Culture',
    FAMILY_ATTRACTIONS_PARKS: '🎢 Theme Parks',
    SNOW_AND_SKI: '⛷️ Snow & Ski',
    WINTER_FESTIVE: '🎄 Winter Markets'
  };

  const INITIAL_PROPOSALS_LIMIT = 6;

  function escapeHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function parseIsoParts(isoStr) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(isoStr || '').trim());
    if (!m) return null;
    return { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) };
  }

  function formatUtcDateIso(utcMs) {
    const dt = new Date(utcMs);
    const y = dt.getUTCFullYear();
    const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const d = String(dt.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function isoToUtcMs(isoStr) {
    const p = parseIsoParts(isoStr);
    if (!p) return NaN;
    return Date.UTC(p.y, p.m - 1, p.d);
  }

  function addDaysIso(isoStr, deltaDays) {
    const ms = isoToUtcMs(isoStr);
    if (!Number.isFinite(ms)) return isoStr;
    return formatUtcDateIso(ms + Number(deltaDays) * 86400000);
  }

  function diffDaysIso(startIso, endIso) {
    const s = isoToUtcMs(startIso);
    const e = isoToUtcMs(endIso);
    if (!Number.isFinite(s) || !Number.isFinite(e)) return 0;
    return Math.round((e - s) / 86400000);
  }

  function utcWeekdayMon0(isoStr) {
    // Convert JS UTC day (Sun=0..Sat=6) to Python weekday (Mon=0..Fri=4, Sat=5, Sun=6)
    const jsDay = new Date(isoToUtcMs(isoStr)).getUTCDay();
    return (jsDay + 6) % 7;
  }

  function getAsOfOverrideIso() {
    if (typeof window !== 'undefined' && window.__FVP_REFERENCE_DATE__) {
      const cand = String(window.__FVP_REFERENCE_DATE__).trim().slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(cand)) return cand;
    }
    try {
      const params = new URLSearchParams((typeof window !== 'undefined' && window.location && window.location.search) || '');
      const qAsOf = (params.get('as_of') || '').trim().slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(qAsOf)) return qAsOf;
    } catch (_ignore) {
      // Ignore malformed query string
    }
    return null;
  }

  function getReferenceToday() {
    const overrideIso = getAsOfOverrideIso();
    if (overrideIso) return overrideIso;
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function inferSchoolYearForIso(isoStr) {
    const p = parseIsoParts(isoStr) || { y: 2026, m: 11, d: 19 };
    return p.m >= 9 ? `${p.y}-${p.y + 1}` : `${p.y - 1}-${p.y}`;
  }

  function isHebrewLeapYear(hebYear) {
    return (((7 * hebYear + 1) % 19) + 19) % 19 < 7;
  }

  function hebrewCalendarElapsedDays(hebYear) {
    const yPrev = hebYear - 1;
    const monthsElapsed =
      235 * Math.floor(yPrev / 19) +
      12 * (yPrev % 19) +
      Math.floor((7 * (yPrev % 19) + 1) / 19);
    const partsElapsed = 204 + 793 * (monthsElapsed % 1080);
    const hoursElapsed =
      5 +
      12 * monthsElapsed +
      793 * Math.floor(monthsElapsed / 1080) +
      Math.floor(partsElapsed / 1080);
    const conjunctionDay = 1 + 29 * monthsElapsed + Math.floor(hoursElapsed / 24);
    const conjunctionParts = 1080 * (hoursElapsed % 24) + (partsElapsed % 1080);

    let altDay = conjunctionDay;
    if (
      conjunctionParts >= 19440 ||
      (conjunctionDay % 7 === 2 && conjunctionParts >= 9924 && !isHebrewLeapYear(hebYear)) ||
      (conjunctionDay % 7 === 1 && conjunctionParts >= 16789 && isHebrewLeapYear(hebYear - 1))
    ) {
      altDay = conjunctionDay + 1;
    }
    const rem = altDay % 7;
    if (rem === 0 || rem === 3 || rem === 5) {
      return altDay + 1;
    }
    return altDay;
  }

  function roshHashanahIso(hebYear) {
    const anchorElapsed = hebrewCalendarElapsedDays(5786);
    const targetElapsed = hebrewCalendarElapsedDays(hebYear);
    return addDaysIso('2025-09-23', targetElapsed - anchorElapsed);
  }

  const WORKPLACE_YEAR_CACHE = {};

  function getWorkplaceHolidaySetsClient(hebYear) {
    if (WORKPLACE_YEAR_CACHE[hebYear]) {
      return WORKPLACE_YEAR_CACHE[hebYear];
    }
    const rh1 = roshHashanahIso(hebYear);
    const pes1 = addDaysIso(roshHashanahIso(hebYear + 1), -163);
    const fifthIyar = addDaysIso(pes1, 20);
    const wdIyar = utcWeekdayMon0(fifthIyar);
    let atzmautIso = fifthIyar;
    if (wdIyar === 4) atzmautIso = addDaysIso(fifthIyar, -1);
    else if (wdIyar === 5) atzmautIso = addDaysIso(fifthIyar, -2);
    else if (wdIyar === 0) atzmautIso = addDaysIso(fifthIyar, 1);
    const shavuotIso = addDaysIso(pes1, 50);

    const officialSet = new Set([
      rh1,
      addDaysIso(rh1, 1),
      addDaysIso(rh1, 9),
      addDaysIso(rh1, 14),
      addDaysIso(rh1, 21),
      pes1,
      addDaysIso(pes1, 6),
      atzmautIso,
      shavuotIso
    ]);
    const cholSet = new Set([
      addDaysIso(rh1, 15),
      addDaysIso(rh1, 16),
      addDaysIso(rh1, 17),
      addDaysIso(rh1, 18),
      addDaysIso(rh1, 19),
      addDaysIso(rh1, 20),
      addDaysIso(pes1, 1),
      addDaysIso(pes1, 2),
      addDaysIso(pes1, 3),
      addDaysIso(pes1, 4),
      addDaysIso(pes1, 5)
    ]);
    const entry = { rh1, pes1, atzmautIso, shavuotIso, officialSet, cholSet };
    WORKPLACE_YEAR_CACHE[hebYear] = entry;
    return entry;
  }

  function classifyWorkdayClient(isoDateStr) {
    const wd = utcWeekdayMon0(isoDateStr);
    if (wd === 4 || wd === 5) {
      return 'WEEKEND';
    }
    const gYear = Number(String(isoDateStr).slice(0, 4));
    const s = getWorkplaceHolidaySetsClient(gYear + 3760);
    const a = getWorkplaceHolidaySetsClient(gYear + 3761);
    if (s.officialSet.has(isoDateStr) || a.officialSet.has(isoDateStr)) {
      return 'OFFICIAL_HOLIDAY';
    }
    if (s.cholSet.has(isoDateStr) || a.cholSet.has(isoDateStr)) {
      return 'CHOL_HAMOED';
    }
    return 'REGULAR_WORKDAY';
  }

  function computeTripWorkdaysClient(depIso, retIso) {
    if (!depIso || !retIso) {
      return {
        workplace_vacation_days_cost: 0,
        regular_workdays_count: 0,
        chol_hamoed_workdays_count: 0,
        official_holiday_workdays_saved_count: 0,
        weekend_days_count: 0,
        holiday_or_weekend_days_count: 0
      };
    }
    const span = diffDaysIso(depIso, retIso);
    if (!Number.isFinite(span) || span < 0) {
      return {
        workplace_vacation_days_cost: 0,
        regular_workdays_count: 0,
        chol_hamoed_workdays_count: 0,
        official_holiday_workdays_saved_count: 0,
        weekend_days_count: 0,
        holiday_or_weekend_days_count: 0
      };
    }
    let regCnt = 0;
    let cholCnt = 0;
    let offCnt = 0;
    let wkndCnt = 0;
    for (let i = 0; i <= span; i += 1) {
      const dIso = addDaysIso(depIso, i);
      const bucket = classifyWorkdayClient(dIso);
      if (bucket === 'WEEKEND') wkndCnt += 1;
      else if (bucket === 'OFFICIAL_HOLIDAY') offCnt += 1;
      else if (bucket === 'CHOL_HAMOED') cholCnt += 1;
      else regCnt += 1;
    }
    const cost = Math.round((regCnt * 1.0 + cholCnt * 0.5) * 10) / 10;
    return {
      workplace_vacation_days_cost: cost,
      regular_workdays_count: regCnt,
      chol_hamoed_workdays_count: cholCnt,
      official_holiday_workdays_saved_count: offCnt,
      weekend_days_count: wkndCnt,
      holiday_or_weekend_days_count: offCnt + wkndCnt
    };
  }

  function projectWorkplaceHolidaysClient(schoolYearStr) {
    const parts = String(schoolYearStr || '2026-2027').split('-');
    const y2 = Number(parts[1]) || 2027;
    const hebYear = y2 + 3760;
    const yr = getWorkplaceHolidaySetsClient(hebYear);
    const specs = [
      { code: 'ROSH_HASHANAH', he: 'ראש השנה', en: 'Rosh Hashanah', start: yr.rh1, end: addDaysIso(yr.rh1, 1), status: 'OFFICIAL_HOLIDAY' },
      { code: 'YOM_KIPPUR', he: 'יום הכיפורים', en: 'Yom Kippur', start: addDaysIso(yr.rh1, 9), end: addDaysIso(yr.rh1, 9), status: 'OFFICIAL_HOLIDAY' },
      { code: 'SUKKOT_I', he: 'חג סוכות א׳', en: 'Sukkot I', start: addDaysIso(yr.rh1, 14), end: addDaysIso(yr.rh1, 14), status: 'OFFICIAL_HOLIDAY' },
      { code: 'CHOL_HAMOED_SUKKOT', he: 'חול המועד סוכות', en: 'Chol HaMoed Sukkot', start: addDaysIso(yr.rh1, 15), end: addDaysIso(yr.rh1, 20), status: 'CHOL_HAMOED' },
      { code: 'SIMCHAT_TORAH', he: 'שמיני עצרת / שמחת תורה', en: 'Simchat Torah', start: addDaysIso(yr.rh1, 21), end: addDaysIso(yr.rh1, 21), status: 'OFFICIAL_HOLIDAY' },
      { code: 'PESACH_I', he: 'חג פסח א׳', en: 'Passover I', start: yr.pes1, end: yr.pes1, status: 'OFFICIAL_HOLIDAY' },
      { code: 'CHOL_HAMOED_PESACH', he: 'חול המועד פסח', en: 'Chol HaMoed Pesach', start: addDaysIso(yr.pes1, 1), end: addDaysIso(yr.pes1, 5), status: 'CHOL_HAMOED' },
      { code: 'PESACH_VII', he: 'שביעי של פסח', en: 'Passover VII', start: addDaysIso(yr.pes1, 6), end: addDaysIso(yr.pes1, 6), status: 'OFFICIAL_HOLIDAY' },
      { code: 'YOM_HAATZMAUT', he: 'יום העצמאות', en: 'Independence Day', start: yr.atzmautIso, end: yr.atzmautIso, status: 'OFFICIAL_HOLIDAY' },
      { code: 'SHAVUOT', he: 'חג השבועות', en: 'Shavuot', start: yr.shavuotIso, end: yr.shavuotIso, status: 'OFFICIAL_HOLIDAY' }
    ];
    return specs.map((sp) => {
      const isOff = sp.status === 'OFFICIAL_HOLIDAY';
      const evalCost = computeTripWorkdaysClient(sp.start, sp.end);
      return {
        id: `workplace_${hebYear}_${sp.code}`,
        school_year: schoolYearStr,
        holiday_code: sp.code,
        name_he: sp.he,
        name_en: sp.en,
        start_date: sp.start,
        end_date: sp.end,
        calendar_days: Math.max(1, diffDaysIso(sp.start, sp.end) + 1),
        workplace_status: sp.status,
        workday_cost_per_day: isOff ? 0 : 0.5,
        effective_workdays_cost: evalCost.workplace_vacation_days_cost,
        status_badge_he: isOff ? 'שבתון · 0 ימי חופש' : 'חול המועד · 0.5 יום',
        status_badge_en: isOff ? 'Holiday · 0d' : 'Chol HaMoed · 0.5d'
      };
    });
  }

  function isTupleKeyGreater(a, b) {
    for (let i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) return a[i] > b[i];
    }
    return false;
  }

  function computeRecommendedWorkplaceWindowClient(startIso, endIso) {
    const coreDays = Math.max(1, diffDaysIso(startIso, endIso) + 1);
    if (coreDays >= 4) {
      return [startIso, endIso];
    }
    let bestKey = null;
    let bestSpan = [startIso, endIso];
    [4, 5].forEach((length) => {
      for (let offset = 0; offset <= length - coreDays; offset += 1) {
        const ws = addDaysIso(startIso, -offset);
        const we = addDaysIso(ws, length - 1);
        if (we < endIso) continue;
        const ev = computeTripWorkdaysClient(ws, we);
        const cost = Number(ev.workplace_vacation_days_cost || 0);
        const ratio = Math.round((length / Math.max(0.5, cost)) * 100) / 100;
        const weWd = utcWeekdayMon0(we);
        const wsWd = utcWeekdayMon0(ws);
        const wkndEndBonus = weWd === 5 || weWd === 6 ? 1 : 0;
        const nonFriStart = wsWd !== 4 ? 1 : 0;
        const key = [ratio, -cost, length, wkndEndBonus, nonFriStart, -offset];
        if (bestKey === null || isTupleKeyGreater(key, bestKey)) {
          bestKey = key;
          bestSpan = [ws, we];
        }
      }
    });
    return bestSpan;
  }

  function buildUpcomingWorkplaceHolidaysClient(refIso) {
    const curSy = inferSchoolYearForIso(refIso);
    const y1 = Number(curSy.split('-')[0]);
    const upcoming = [];

    CANONICAL_WORKPLACE_ROLLING_HOLIDAYS.forEach((meta) => {
      for (let i = 0; i < 3; i += 1) {
        const syY1 = y1 + i;
        const sy = `${syY1}-${syY1 + 1}`;
        const hebYear = syY1 + 3761;
        const yr = getWorkplaceHolidaySetsClient(hebYear);
        let sIso = null;
        let eIso = null;
        if (meta.code === 'ROSH_HASHANAH') {
          sIso = yr.rh1;
          eIso = addDaysIso(yr.rh1, 1);
        } else if (meta.code === 'YOM_KIPPUR_SUKKOT_BRIDGE') {
          sIso = addDaysIso(yr.rh1, 9);
          eIso = addDaysIso(yr.rh1, 21);
        } else if (meta.code === 'SUKKOT') {
          sIso = addDaysIso(yr.rh1, 14);
          eIso = addDaysIso(yr.rh1, 21);
        } else if (meta.code === 'PESACH') {
          sIso = yr.pes1;
          eIso = addDaysIso(yr.pes1, 6);
        } else if (meta.code === 'YOM_HAATZMAUT') {
          sIso = yr.atzmautIso;
          eIso = yr.atzmautIso;
        } else if (meta.code === 'SHAVUOT') {
          sIso = yr.shavuotIso;
          eIso = yr.shavuotIso;
        }
        if (!sIso || !eIso) continue;
        if (eIso >= refIso) {
          const holidayDays = Math.max(1, diffDaysIso(sIso, eIso) + 1);
          let officialHolidayDays = 0;
          let cholHamoedDays = 0;
          for (let k = 0; k < holidayDays; k += 1) {
            const dIso = addDaysIso(sIso, k);
            if (yr.officialSet.has(dIso)) officialHolidayDays += 1;
            if (yr.cholSet.has(dIso)) cholHamoedDays += 1;
          }
          const coreEval = computeTripWorkdaysClient(sIso, eIso);
          const recSpan = computeRecommendedWorkplaceWindowClient(sIso, eIso);
          const recStart = recSpan[0];
          const recEnd = recSpan[1];
          const recDays = Math.max(1, diffDaysIso(recStart, recEnd) + 1);
          const recEval = computeTripWorkdaysClient(recStart, recEnd);
          const recCost = Number(recEval.workplace_vacation_days_cost || 0);
          const recSaved = Math.round(Math.max(0, recDays - recCost) * 10) / 10;
          const recRatio = Math.round((recDays / Math.max(0.5, recCost)) * 100) / 100;
          const costStr = Number.isInteger(recCost)
            ? String(recCost)
            : String(Math.round(recCost * 10) / 10);
          const costUnitHe = recCost === 1 ? 'יום חופש' : 'ימי חופש';
          const costUnitEn = recCost === 1 ? 'workday' : 'workdays';
          const dayWordHe = recDays === 1 ? 'יום' : 'ימים';
          const dayWordEn = recDays === 1 ? 'day' : 'days';
          const targetYear = Number(sIso.slice(0, 4));
          upcoming.push({
            holiday_code: meta.code,
            name_he: meta.nameHe,
            name_en: meta.nameEn,
            target_year: targetYear,
            school_year: sy,
            start_date: sIso,
            end_date: eIso,
            holiday_days: holidayDays,
            recommended_window_start: recStart,
            recommended_window_end: recEnd,
            recommended_trip_days: recDays,
            recommended_workdays_cost: recCost,
            recommended_workdays_saved: recSaved,
            recommended_efficiency_ratio: recRatio,
            workplace_workdays_cost: Number(coreEval.workplace_vacation_days_cost || 0),
            official_holiday_days: officialHolidayDays,
            chol_hamoed_days: cholHamoedDays,
            is_ongoing: sIso <= refIso && refIso <= eIso,
            calendar_mode: 'WORKPLACE',
            label_he: `${meta.nameHe} ${targetYear} (${recDays} ${dayWordHe} · ${costStr} ${costUnitHe})`,
            label_en: `${meta.nameEn} ${targetYear} (${recDays} ${dayWordEn} · ${costStr} ${costUnitEn})`
          });
          break;
        }
      }
    });

    upcoming.sort((a, b) => {
      if (a.start_date !== b.start_date) return a.start_date < b.start_date ? -1 : 1;
      if (a.end_date !== b.end_date) return a.end_date < b.end_date ? -1 : 1;
      if (a.holiday_days !== b.holiday_days) return a.holiday_days - b.holiday_days;
      return a.holiday_code < b.holiday_code ? -1 : 1;
    });
    return upcoming;
  }

  function isTlvYomKippurClosureClient(dateIso) {
    if (!dateIso || dateIso.length < 10) return false;
    const yr = Number(dateIso.slice(0, 4));
    if (!Number.isFinite(yr)) return false;
    const rh1 = roshHashanahIso(yr + 3761);
    const ykEve = addDaysIso(rh1, 8);
    const ykDay = addDaysIso(rh1, 9);
    return dateIso === ykEve || dateIso === ykDay;
  }

  function detectMergedWorkplaceHolidaysClient(startIso, endIso) {
    if (!startIso || !endIso || endIso < startIso) return [];
    const sYear = Number(startIso.slice(0, 4));
    const eYear = Number(endIso.slice(0, 4));
    const hebYears = Array.from(
      new Set([sYear + 3760, sYear + 3761, eYear + 3760, eYear + 3761])
    ).sort((a, b) => a - b);
    const seen = new Set();
    const found = [];
    hebYears.forEach((hebY) => {
      const yr = getWorkplaceHolidaySetsClient(hebY);
      const specs = [
        { code: 'ROSH_HASHANAH', name_he: 'ראש השנה', name_en: 'Rosh Hashanah', short_name_he: 'ראש השנה', short_name_en: 'Rosh Hashanah', start_date: yr.rh1, end_date: addDaysIso(yr.rh1, 1), is_stay_abroad_holiday: false },
        { code: 'YOM_KIPPUR', name_he: 'יום כיפור (שהייה בחו״ל)', name_en: 'Yom Kippur (abroad)', short_name_he: 'יום כיפור', short_name_en: 'Yom Kippur', start_date: addDaysIso(yr.rh1, 9), end_date: addDaysIso(yr.rh1, 9), is_stay_abroad_holiday: true },
        { code: 'SUKKOT', name_he: 'סוכות', name_en: 'Sukkot', short_name_he: 'סוכות', short_name_en: 'Sukkot', start_date: addDaysIso(yr.rh1, 14), end_date: addDaysIso(yr.rh1, 21), is_stay_abroad_holiday: false },
        { code: 'PESACH', name_he: 'פסח', name_en: 'Passover', short_name_he: 'פסח', short_name_en: 'Passover', start_date: yr.pes1, end_date: addDaysIso(yr.pes1, 6), is_stay_abroad_holiday: false },
        { code: 'YOM_HAATZMAUT', name_he: 'יום העצמאות', name_en: 'Independence Day', short_name_he: 'יום העצמאות', short_name_en: 'Independence Day', start_date: yr.atzmautIso, end_date: yr.atzmautIso, is_stay_abroad_holiday: false },
        { code: 'SHAVUOT', name_he: 'שבועות', name_en: 'Shavuot', short_name_he: 'שבועות', short_name_en: 'Shavuot', start_date: yr.shavuotIso, end_date: yr.shavuotIso, is_stay_abroad_holiday: false }
      ];
      specs.forEach((sp) => {
        if (sp.start_date <= endIso && sp.end_date >= startIso) {
          const key = `${sp.code}:${sp.start_date}`;
          if (!seen.has(key)) {
            seen.add(key);
            found.push(sp);
          }
        }
      });
    });
    found.sort((a, b) => (a.start_date !== b.start_date ? (a.start_date < b.start_date ? -1 : 1) : (a.code < b.code ? -1 : 1)));
    return found;
  }

  function computeRecommendedMegaBridgeWindowClient(code, startIso, endIso, constituents) {
    const reqSet = new Set(constituents || []);
    const recRange = WORKPLACE_RECOMMENDED_NIGHTS_CLIENT[code] || [10, 16];
    const yr = Number(startIso.slice(0, 4));
    const rh1 = roshHashanahIso(yr + 3761);
    const ykDay = addDaysIso(rh1, 9);
    let bestKey = null;
    let bestSpan = null;
    for (let ds = -3; ds <= 1; ds += 1) {
      const ws = addDaysIso(startIso, ds);
      if (isTlvYomKippurClosureClient(ws) || utcWeekdayMon0(ws) === 5) continue;
      for (let de = -2; de <= 3; de += 1) {
        const we = addDaysIso(endIso, de);
        if (we <= ws) continue;
        if (isTlvYomKippurClosureClient(we) || utcWeekdayMon0(we) === 5) continue;
        const nights = diffDaysIso(ws, we);
        const merged = detectMergedWorkplaceHolidaysClient(ws, we);
        const foundCodes = new Set(merged.map((m) => m.code));
        let ok = true;
        reqSet.forEach((reqCode) => {
          if (!foundCodes.has(reqCode)) ok = false;
        });
        if (!ok) continue;
        if (reqSet.has('YOM_KIPPUR') && !(ws < ykDay && ykDay < we)) continue;
        const ev = computeTripWorkdaysClient(ws, we);
        const days = nights + 1;
        const cost = Number(ev.workplace_vacation_days_cost || 0);
        const saved = Math.round(Math.max(0, days - cost) * 10) / 10;
        const ratio = Math.round((days / Math.max(0.5, cost)) * 100) / 100;
        const inRec = nights >= recRange[0] && nights <= recRange[1] ? 1 : 0;
        const prefSpan = ws <= startIso && we >= addDaysIso(endIso, -1) ? 1 : 0;
        const key = [inRec, prefSpan, ratio, saved, -cost, nights];
        if (bestKey === null || isTupleKeyGreater(key, bestKey)) {
          bestKey = key;
          bestSpan = [ws, we];
        }
      }
    }
    if (bestSpan) return bestSpan;
    let wsFb = startIso;
    while (isTlvYomKippurClosureClient(wsFb) || utcWeekdayMon0(wsFb) === 5) {
      wsFb = addDaysIso(wsFb, -1);
    }
    let weFb = endIso;
    while (isTlvYomKippurClosureClient(weFb) || utcWeekdayMon0(weFb) === 5) {
      weFb = addDaysIso(weFb, 1);
    }
    return [wsFb, weFb];
  }

  function buildUpcomingWorkplaceCatalogClient(refIso) {
    const curSy = inferSchoolYearForIso(refIso);
    const y1 = Number(curSy.split('-')[0]);
    const refYear = Number(refIso.slice(0, 4));
    const winEnd = `${refYear + 1}${refIso.slice(4)}`;

    const buildItem = (meta, groupId) => {
      for (let i = 0; i < 3; i += 1) {
        const syY1 = y1 + i;
        const sy = `${syY1}-${syY1 + 1}`;
        const hebYear = syY1 + 3761;
        const yr = getWorkplaceHolidaySetsClient(hebYear);
        let sIso = null;
        let eIso = null;
        if (meta.code === 'ROSH_HASHANAH') {
          sIso = yr.rh1;
          eIso = addDaysIso(yr.rh1, 1);
        } else if (meta.code === 'FULL_TISHREI') {
          sIso = yr.rh1;
          eIso = addDaysIso(yr.rh1, 21);
        } else if (meta.code === 'ROSH_HASHANAH_KIPPUR_BRIDGE') {
          sIso = yr.rh1;
          eIso = addDaysIso(yr.rh1, 9);
        } else if (meta.code === 'YOM_KIPPUR_SUKKOT_BRIDGE') {
          sIso = addDaysIso(yr.rh1, 9);
          eIso = addDaysIso(yr.rh1, 21);
        } else if (meta.code === 'SUKKOT') {
          sIso = addDaysIso(yr.rh1, 14);
          eIso = addDaysIso(yr.rh1, 21);
        } else if (meta.code === 'PESACH') {
          sIso = yr.pes1;
          eIso = addDaysIso(yr.pes1, 6);
        } else if (meta.code === 'YOM_HAATZMAUT') {
          sIso = yr.atzmautIso;
          eIso = yr.atzmautIso;
        } else if (meta.code === 'SHAVUOT') {
          sIso = yr.shavuotIso;
          eIso = yr.shavuotIso;
        }
        if (!sIso || !eIso || eIso < refIso) continue;
        const holidayDays = Math.max(1, diffDaysIso(sIso, eIso) + 1);
        const coreEval = computeTripWorkdaysClient(sIso, eIso);
        const isMega = groupId === 'MEGA_BRIDGES';
        const recSpan = isMega
          ? computeRecommendedMegaBridgeWindowClient(meta.code, sIso, eIso, meta.constituents)
          : computeRecommendedWorkplaceWindowClient(sIso, eIso);
        let recStart = recSpan[0];
        let recEnd = recSpan[1];
        while (isTlvYomKippurClosureClient(recStart)) recStart = addDaysIso(recStart, -1);
        while (isTlvYomKippurClosureClient(recEnd)) recEnd = addDaysIso(recEnd, 1);
        const recDays = Math.max(1, diffDaysIso(recStart, recEnd) + 1);
        const recRange = WORKPLACE_RECOMMENDED_NIGHTS_CLIENT[meta.code] || [4, 7];
        const recEval = computeTripWorkdaysClient(recStart, recEnd);
        const recCost = Number(recEval.workplace_vacation_days_cost || 0);
        const recSaved = Math.round(Math.max(0, recDays - recCost) * 10) / 10;
        const recRatio = Math.round((recDays / Math.max(0.5, recCost)) * 100) / 100;
        const merged = detectMergedWorkplaceHolidaysClient(recStart, recEnd);
        const costStr = Number.isInteger(recCost) ? String(recCost) : String(Math.round(recCost * 10) / 10);
        const targetYear = Number(sIso.slice(0, 4));
        return {
          id: `workplace_${hebYear}_${meta.code}`,
          holiday_code: meta.code,
          holiday_group: groupId,
          is_mega_vacation: isMega,
          name_he: meta.nameHe,
          name_en: meta.nameEn,
          target_year: targetYear,
          school_year: sy,
          start_date: sIso,
          end_date: eIso,
          holiday_days: holidayDays,
          recommended_window_start: recStart,
          recommended_window_end: recEnd,
          recommended_trip_days: recDays,
          recommended_min_nights: recRange[0],
          recommended_max_nights: recRange[1],
          recommended_workdays_cost: recCost,
          recommended_workdays_saved: recSaved,
          recommended_efficiency_ratio: recRatio,
          workplace_workdays_cost: Number(coreEval.workplace_vacation_days_cost || 0),
          merged_holidays: merged,
          includes_yom_kippur_abroad: merged.some((m) => Boolean(m.is_stay_abroad_holiday)),
          is_ongoing: sIso <= refIso && refIso <= eIso,
          calendar_mode: 'WORKPLACE',
          label_he: `${meta.nameHe} ${targetYear} (${recDays} ${recDays === 1 ? 'יום' : 'ימים'} · ${costStr} ${recCost === 1 ? 'יום חופש' : 'ימי חופש'})`,
          label_en: `${meta.nameEn} ${targetYear} (${recDays} ${recDays === 1 ? 'day' : 'days'} · ${costStr} ${recCost === 1 ? 'workday' : 'workdays'})`
        };
      }
      return null;
    };

    const individualItems = WORKPLACE_INDIVIDUAL_HOLIDAYS_CLIENT
      .map((m) => buildItem(m, 'INDIVIDUAL_HOLIDAYS'))
      .filter(Boolean)
      .sort((a, b) => (a.start_date !== b.start_date ? (a.start_date < b.start_date ? -1 : 1) : (a.holiday_code < b.holiday_code ? -1 : 1)));

    const megaItems = WORKPLACE_MEGA_BRIDGE_HOLIDAYS_CLIENT
      .map((m) => ({ prio: m.prio, item: buildItem(m, 'MEGA_BRIDGES') }))
      .filter((x) => Boolean(x.item))
      .sort((a, b) => (a.item.target_year !== b.item.target_year ? a.item.target_year - b.item.target_year : a.prio - b.prio))
      .map((x) => x.item);

    const bestYearOption = {
      id: 'workplace_best_year_maximizer',
      holiday_code: 'BEST_YEAR_MAXIMIZER',
      holiday_group: 'BEST_YEAR',
      is_mega_vacation: false,
      is_best_year_maximizer: true,
      name_he: '✨ המיקסום הטוב ביותר בשנה הקרובה',
      name_en: '✨ Best Maximization Next Year',
      label_he: '✨ המיקסום הטוב ביותר בשנה הקרובה',
      label_en: '✨ Best Maximization Next Year',
      subtitle_he: 'סורק את כל חגי המשק ואיחודי החגים בשנה הקרובה',
      subtitle_en: 'Scans all Israeli workplace holidays & bridges over the next 12 months',
      start_date: refIso,
      end_date: winEnd,
      target_year: refYear + 1,
      recommended_window_start: refIso,
      recommended_window_end: winEnd,
      recommended_min_nights: 3,
      recommended_max_nights: 15,
      merged_holidays: [],
      includes_yom_kippur_abroad: false,
      calendar_mode: 'WORKPLACE'
    };

    return {
      best_year_option: bestYearOption,
      holiday_groups: [
        {
          group_id: 'INDIVIDUAL_HOLIDAYS',
          label_he: 'חגי משק בודדים',
          label_en: 'Individual Market Holidays',
          items: individualItems
        },
        {
          group_id: 'MEGA_BRIDGES',
          label_he: 'מגה-חופשות ואיחודי חגים',
          label_en: 'Mega-Vacations & Holiday Bridges',
          items: megaItems
        }
      ],
      catalog_count: individualItems.length + megaItems.length,
      catalog_items: [...individualItems, ...megaItems]
    };
  }

  function formatCompactDateRange(startIso, endIso, isHe) {
    if (!startIso || !endIso) return '';
    const sParts = String(startIso).slice(0, 10).split('-').map(Number);
    const eParts = String(endIso).slice(0, 10).split('-').map(Number);
    if (sParts.length !== 3 || eParts.length !== 3) return `${startIso}–${endIso}`;
    const [sy, sm, sd] = sParts;
    const [ey, em, ed] = eParts;
    const months = isHe ? SHORT_MONTHS_HE : SHORT_MONTHS_EN;
    const sMon = months[(sm - 1) % 12] || String(sm);
    const eMon = months[(em - 1) % 12] || String(em);
    if (sy === ey && sm === em) {
      return isHe ? `${sd}–${ed} ב${sMon} ${sy}` : `${sMon} ${sd}–${ed}, ${sy}`;
    }
    if (sy === ey) {
      return isHe ? `${sd} ב${sMon} – ${ed} ב${eMon} ${sy}` : `${sMon} ${sd} – ${eMon} ${ed}, ${sy}`;
    }
    return isHe ? `${sd} ב${sMon} ${sy} – ${ed} ב${eMon} ${ey}` : `${sMon} ${sd}, ${sy} – ${eMon} ${ed}, ${ey}`;
  }

  function projectSchoolYearPeriods(schoolYearStr) {
    if (BUNDLED_SCHOOL_YEAR_PERIODS[schoolYearStr]) {
      return BUNDLED_SCHOOL_YEAR_PERIODS[schoolYearStr];
    }
    const parts = schoolYearStr.split('-');
    const y2 = Number(parts[1]);
    const hebYear = y2 + 3760;

    const rh1 = roshHashanahIso(hebYear);
    const rhStart = addDaysIso(rh1, -1);
    const rhEnd = addDaysIso(rh1, 1);
    const ykEve = addDaysIso(rh1, 8);
    const sukkotK9End = addDaysIso(rh1, 21);
    const sukkot1012End = addDaysIso(rh1, 22);

    const rhNext = roshHashanahIso(hebYear + 1);
    const yearLen = diffDaysIso(rh1, rhNext);
    const hanOffset = yearLen % 10 === 5 ? 85 : 84;
    const hanStart = addDaysIso(rh1, hanOffset);
    const hanEnd = addDaysIso(hanStart, 6);

    const pesach1 = addDaysIso(rhNext, -163);
    const purimStart = addDaysIso(pesach1, -30);
    const purimEnd = addDaysIso(pesach1, -29);
    const pesachStart = addDaysIso(pesach1, -9);
    const pesachEnd = addDaysIso(pesach1, 6);
    const pesachDaycareStart = addDaysIso(pesach1, -1);

    const fifthIyar = addDaysIso(pesach1, 20);
    const wdIyar = utcWeekdayMon0(fifthIyar);
    let atzmautIso = fifthIyar;
    if (wdIyar === 4) atzmautIso = addDaysIso(fifthIyar, -1);
    else if (wdIyar === 5) atzmautIso = addDaysIso(fifthIyar, -2);
    else if (wdIyar === 0) atzmautIso = addDaysIso(fifthIyar, 1);

    const shavuotStart = addDaysIso(pesach1, 49);
    const shavuotEnd = addDaysIso(pesach1, 50);

    const june20Iso = `${y2}-06-20`;
    const wdJun20 = utcWeekdayMon0(june20Iso);
    let summer712Start = `${y2}-06-21`;
    if (wdJun20 === 5) summer712Start = `${y2}-06-19`;
    else if (wdJun20 === 4) summer712Start = `${y2}-06-20`;

    return [
      { code: 'ROSH_HASHANAH', start: rhStart, end: rhEnd, fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'YOM_KIPPUR_SUKKOT', start: ykEve, end: sukkotK9End, fws: ALL_8_FRAMEWORKS, overrides: { HIGH_SCHOOL_10_12: [ykEve, sukkot1012End] } },
      { code: 'HANUKKAH', start: hanStart, end: hanEnd, fws: K12_NO_DAYCARE, overrides: {} },
      { code: 'PURIM', start: purimStart, end: purimEnd, fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'PESACH', start: pesachStart, end: pesachEnd, fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: [pesachDaycareStart, pesachEnd] } },
      { code: 'YOM_HAATZMAUT', start: atzmautIso, end: atzmautIso, fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SHAVUOT', start: shavuotStart, end: shavuotEnd, fws: ALL_8_FRAMEWORKS, overrides: {} },
      { code: 'SUMMER_JUNE_20_30', start: summer712Start, end: `${y2}-06-30`, fws: ['MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12'], overrides: {} },
      { code: 'SUMMER_JULY', start: `${y2}-07-01`, end: `${y2}-07-31`, fws: ['MUNICIPAL_GAN', 'ELEMENTARY_1_3', 'ELEMENTARY_4_6', 'MIDDLE_SCHOOL_7_9', 'HIGH_SCHOOL_10_12', 'RELIGIOUS_HAREDI'], overrides: {} },
      { code: 'SUMMER_AUGUST', start: `${y2}-08-01`, end: `${y2}-08-31`, fws: ALL_8_FRAMEWORKS, overrides: { DAYCARE_SUPERVISED: [`${y2}-08-09`, `${y2}-08-31`], SPECIAL_ED: [`${y2}-08-16`, `${y2}-08-31`] } }
    ];
  }

  function buildUpcomingHolidaysClient(refIso, profileObj) {
    const curSy = inferSchoolYearForIso(refIso);
    const y1 = Number(curSy.split('-')[0]);
    const schoolYears = [`${y1}-${y1 + 1}`, `${y1 + 1}-${y1 + 2}`, `${y1 + 2}-${y1 + 3}`];
    const childFws = new Set(
      ((profileObj && profileObj.children) || [])
        .map((c) => c && c.framework_type)
        .filter(Boolean)
    );

    const upcoming = [];
    CANONICAL_ROLLING_HOLIDAYS.forEach((meta) => {
      const srcCode =
        meta.code === 'YOM_KIPPUR_SUKKOT_BRIDGE' || meta.code === 'SUKKOT'
          ? 'YOM_KIPPUR_SUKKOT'
          : meta.code;

      for (let i = 0; i < schoolYears.length; i += 1) {
        const sy = schoolYears[i];
        const periods = projectSchoolYearPeriods(sy);
        const period = periods.find((p) => p.code === srcCode);
        if (!period) continue;

        const fwWindows = period.fws.map((fw) => {
          const ov = period.overrides && period.overrides[fw];
          return {
            fw,
            start: ov ? ov[0] : period.start,
            end: ov ? ov[1] : period.end
          };
        });
        let relevant =
          childFws.size > 0 ? fwWindows.filter((w) => childFws.has(w.fw)) : fwWindows;
        if (relevant.length === 0) relevant = fwWindows;

        const starts = relevant.map((w) => w.start).sort();
        const ends = relevant.map((w) => w.end).sort();
        let sIso =
          meta.code === 'SUMMER_AUGUST' && childFws.size > 0
            ? starts[starts.length - 1]
            : starts[0];
        const eIso = ends[ends.length - 1];
        if (meta.code === 'SUKKOT') {
          const shifted = addDaysIso(sIso, 5);
          sIso = shifted <= eIso ? shifted : eIso;
        }

        if (eIso >= refIso) {
          const holidayDays = Math.max(1, diffDaysIso(sIso, eIso) + 1);
          const targetYear = Number(sIso.slice(0, 4));
          const dayWordHe = holidayDays === 1 ? 'יום' : 'ימים';
          const dayWordEn = holidayDays === 1 ? 'day' : 'days';
          upcoming.push({
            holiday_code: meta.code,
            name_he: meta.nameHe,
            name_en: meta.nameEn,
            target_year: targetYear,
            school_year: sy,
            start_date: sIso,
            end_date: eIso,
            holiday_days: holidayDays,
            label_he: `${meta.nameHe} ${targetYear} (${holidayDays} ${dayWordHe})`,
            label_en: `${meta.nameEn} ${targetYear} (${holidayDays} ${dayWordEn})`
          });
          break;
        }
      }
    });

    upcoming.sort((a, b) => {
      if (a.start_date !== b.start_date) return a.start_date < b.start_date ? -1 : 1;
      if (a.end_date !== b.end_date) return a.end_date < b.end_date ? -1 : 1;
      if (a.holiday_days !== b.holiday_days) return a.holiday_days - b.holiday_days;
      return a.holiday_code < b.holiday_code ? -1 : 1;
    });
    return upcoming;
  }

  function createCleanGuestProfile() {
    return {
      id: 'guest-ephemeral',
      profile_name: '',
      adults_count: 2,
      matmid_points_balance: 0,
      has_flycard: false,
      flycard_tier: 'NONE',
      flycard_companion_vouchers: 0,
      point_valuation_usd: 0.016,
      preferred_currency: 'USD',
      children: [],
      passenger_loyalty_wallets: []
    };
  }

  function isWorkplaceModeProfile(profileObj) {
    return !profileObj || !Array.isArray(profileObj.children) || profileObj.children.length === 0;
  }

  function generateClientChildId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `child-${crypto.randomUUID()}`;
    }
    return `child-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }

  const state = {
    locale: 'he',
    dir: 'rtl',
    dateSelectionMode: 'SPECIFIC_DATES',
    airlineSelectionMode: 'EL_AL_ONLY',
    selectedVacationTypes: [],
    weatherFilterMode: 'SOFT_PRIORITIZE',
    weatherFallbackMessageHe: null,
    validationErrorHe: null,
    validationErrorEn: null,
    isCalendarVisible: false,
    isSearchFiltersOpen: false,
    isProfileSheetOpen: false,
    profileSheetView: null,
    isAuthPopoverOpen: false,
    isBookingHandoffOpen: false,
    bookingHandoffProposal: null,
    isSharePlanOpen: false,
    sharePlanProposal: null,
    sharePlanEmailSending: false,
    sharePlanStatusType: null,
    sharePlanStatusHe: '',
    sharePlanStatusEn: '',
    sharePlanFallbackGmailUrl: '',
    sharePlanRecipientValue: '',
    sharePlanNoteValue: '',
    sharePlanPdfBusy: false,
    sharePlanPdfNoticeHe: '',
    sharePlanPdfNoticeEn: '',
    sharePlanCopyDone: false,
    visibleRenderableProposals: [],
    lastActiveMobileZone: 'zone-search',
    isDestPickerOpen: false,
    destFilterQuery: '',
    selectedDestinations: [],
    showAllProposals: false,
    auth: {
      authenticated: false,
      isAdmin: false,
      oauthConfigured: false,
      emailShareConfigured: false,
      testMode: false,
      csrfToken: null,
      user: null
    },
    adminBonusSync: null,
    isAdminSyncExpanded: true,
    isAdminSyncRefreshing: false,
    notificationsOptIn: false,
    authNoticeHe: null,
    authNoticeEn: null,
    saveFeedbackHe: null,
    saveFeedbackEn: null,
    profileSaveErrorHe: null,
    profileSaveErrorEn: null,
    confirmingDeleteProfile: false,
    profile: createCleanGuestProfile(),
    profileDirty: false,
    lastSearchProfile: null,
    lastSearchCalendarMode: 'WORKPLACE',
    lastPlanningMode: 'workplace',
    upcomingHolidays: [],
    workplaceCatalog: null,
    maxWorkdaysOffBudget: null,
    workdaysBudgetExceeded: false,
    activeHolidayGroup: null,
    userSelectedHoliday: false,
    userEditedMaxNights: false,
    userEditedMinNights: false,
    userEditedManualDates: false,
    calendarData: null,
    proposals: []
  };

  let latestSearchSeq = 0;
  let latestHolidayFetchSeq = 0;

  function syncVacationTypePills() {
    const activeSet = new Set(state.selectedVacationTypes || []);
    const isAny = activeSet.size === 0 || activeSet.has('ANY');
    document.querySelectorAll('[data-vacation-type]').forEach((btn) => {
      const vt = btn.getAttribute('data-vacation-type');
      if (vt === 'ANY') {
        btn.classList.toggle('active', isAny);
      } else {
        btn.classList.toggle('active', !isAny && activeSet.has(vt));
      }
    });
  }

  function formatVacationTypeBadge(vtype) {
    const code = String(vtype || 'ANY').toUpperCase();
    return state.locale === 'he'
      ? (VACATION_TYPE_LABELS_HE[code] || code)
      : (VACATION_TYPE_LABELS_EN[code] || code);
  }

  function getScrollBehavior() {
    if (
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return 'auto';
    }
    return 'smooth';
  }

  // Selective inert targets when the shared calendar modal popup is open:
  // `#app-header` and `#mobile-thumb-dock` stay non-inert & uncovered so clicking the calendar trigger a 2nd time closes it!
  const CALENDAR_MODAL_INERT_SELECTORS = [
    '#vacation-hero',
    '.sidebar-column',
    '#zone-results',
    '#site-footer'
  ];
  let calendarModalOpenerEl = null;

  const BOOKING_HANDOFF_SUPPRESS_KEY = 'fvp_elal_handoff_suppress_v1';
  const BOOKING_HANDOFF_INERT_SELECTORS = [
    '#app-header',
    '#dashboard-shell',
    '#site-footer',
    '#mobile-thumb-dock'
  ];
  let bookingHandoffOpenerEl = null;
  let bookingHandoffScrollbarPx = 0;
  let sharePlanOpenerEl = null;
  let sharePlanScrollbarPx = 0;

  function isBookingHandoffSuppressed() {
    try {
      return (
        typeof localStorage !== 'undefined' &&
        localStorage.getItem(BOOKING_HANDOFF_SUPPRESS_KEY) === '1'
      );
    } catch (_err) {
      return false;
    }
  }

  function setBookingHandoffSuppressed(suppressed) {
    try {
      if (typeof localStorage === 'undefined') return;
      if (suppressed) {
        localStorage.setItem(BOOKING_HANDOFF_SUPPRESS_KEY, '1');
      } else {
        localStorage.removeItem(BOOKING_HANDOFF_SUPPRESS_KEY);
      }
    } catch (_err) {
      // Ignore storage access errors in restricted contexts
    }
  }

  function syncBodyScrollLock() {
    document.body.classList.toggle(
      'is-sheet-locked',
      Boolean(
        state.isCalendarVisible ||
          state.isProfileSheetOpen ||
          state.isBookingHandoffOpen ||
          state.isSharePlanOpen
      )
    );
  }

  function clearOpenKpiTooltips() {
    document.querySelectorAll('.kpi-cell.is-tooltip-open, .stub-weather-card.is-tooltip-open').forEach((el) => {
      el.classList.remove('is-tooltip-open');
    });
    document.querySelectorAll('.stub-score-header.has-open-inline-kpi').forEach((hdrEl) => {
      hdrEl.classList.remove('has-open-inline-kpi');
    });
    document.querySelectorAll('.proposal-card.has-open-tooltip').forEach((cardEl) => {
      cardEl.classList.remove('has-open-tooltip');
    });
  }

  function setCalendarVisibility(visible, optsOrScroll) {
    const options =
      optsOrScroll && typeof optsOrScroll === 'object' ? optsOrScroll : {};
    const willOpen = Boolean(visible);
    const wasOpen = Boolean(state.isCalendarVisible);

    if (willOpen && !wasOpen) {
      if (state.isBookingHandoffOpen) {
        closeBookingHandoffModal({ restoreFocus: false });
      }
      if (state.isSharePlanOpen) {
        closeSharePlanModal({ restoreFocus: false });
      }
      if (state.isProfileSheetOpen) {
        setProfileSheetOpen(false, { restoreFocus: false });
      }
      if (state.isAuthPopoverOpen) {
        setAuthPopoverOpen(false, { restoreFocus: false });
      }
      if (state.isDestPickerOpen) {
        setDestPickerOpen(false);
      }
    }

    state.isCalendarVisible = willOpen;
    const calZone = document.getElementById('zone-calendar');
    const calBackdrop = document.getElementById('calendar-modal-backdrop');
    const isHe = state.locale === 'he';

    if (calZone) {
      if (willOpen) {
        renderCalendarTable();
        renderWorkplaceCalendarTable();
        syncPlanningModeUi();
        calZone.removeAttribute('hidden');
        calZone.style.display = 'flex';
        calZone.classList.add('is-calendar-open');
        calZone.setAttribute('role', 'dialog');
        calZone.setAttribute('aria-modal', 'true');
      } else {
        calZone.setAttribute('hidden', '');
        calZone.style.display = 'none';
        calZone.classList.remove('is-calendar-open');
        calZone.removeAttribute('role');
        calZone.removeAttribute('aria-modal');
      }
    }

    if (calBackdrop) {
      if (willOpen) {
        calBackdrop.removeAttribute('hidden');
        calBackdrop.style.display = 'block';
      } else {
        calBackdrop.setAttribute('hidden', '');
        calBackdrop.style.display = 'none';
      }
    }

    CALENDAR_MODAL_INERT_SELECTORS.forEach((sel) => {
      const el = document.querySelector(sel);
      if (!el) return;
      if (willOpen) {
        el.setAttribute('inert', '');
      } else if (
        state.profileSheetView !== 'travelers' &&
        !state.isBookingHandoffOpen &&
        !state.isSharePlanOpen
      ) {
        el.removeAttribute('inert');
      }
    });

    syncBodyScrollLock();

    const btnTop = document.getElementById('btn-toggle-calendar');
    if (btnTop) {
      const isWpCal = isWorkplaceModeProfile(state.profile);
      btnTop.classList.toggle('active', willOpen);
      btnTop.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      btnTop.textContent = willOpen
        ? isHe
          ? '📅 הסתר לוח'
          : '📅 Hide Calendar'
        : isWpCal
          ? isHe
            ? '📅 לוח חגי המשק'
            : '📅 Workplace Holidays'
          : isHe
            ? '📅 לוח חופשות'
            : '📅 MoE Calendar';
    }
    const dockCalBtn = document.getElementById('btn-mobile-dock-calendar');
    if (dockCalBtn) {
      dockCalBtn.classList.toggle('active', willOpen);
      dockCalBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      const dockLabel = dockCalBtn.querySelector('.mobile-dock-label');
      if (dockLabel) {
        dockLabel.textContent = willOpen
          ? isHe
            ? 'הסתר לוח'
            : 'Hide'
          : isHe
            ? 'חופשות'
            : 'Calendar';
      }
    }

    if (willOpen && !wasOpen) {
      const activeEl = document.activeElement;
      const fallbackTrigger =
        typeof window !== 'undefined' && window.innerWidth < 1024 ? dockCalBtn : btnTop;
      calendarModalOpenerEl =
        options.opener ||
        (activeEl && activeEl !== document.body ? activeEl : fallbackTrigger);
      if (options.focusContent !== false) {
        const closeBtn = document.getElementById('btn-close-calendar');
        if (closeBtn) {
          setTimeout(() => {
            if (!state.isCalendarVisible) return;
            closeBtn.focus();
          }, 40);
        }
      }
    } else if (!willOpen && wasOpen) {
      if (options.restoreFocus !== false) {
        const activeEl = document.activeElement;
        const focusWasInside =
          !activeEl ||
          activeEl === document.body ||
          Boolean(calZone && calZone.contains(activeEl));
        const fallbackTrigger =
          typeof window !== 'undefined' && window.innerWidth < 1024 ? dockCalBtn : btnTop;
        const restoreEl =
          calendarModalOpenerEl &&
          document.contains(calendarModalOpenerEl) &&
          !calendarModalOpenerEl.hasAttribute('hidden')
            ? calendarModalOpenerEl
            : fallbackTrigger;
        if (focusWasInside && restoreEl) {
          restoreEl.focus();
        }
      }
      calendarModalOpenerEl = null;
    }
  }

  // Desktop (>=1180px) only: while the passenger window is open, everything else on the page is inert
  const DESKTOP_MODAL_INERT_SELECTORS = [
    '#app-header',
    '#vacation-hero',
    '#household-summary-bar',
    '#zone-search',
    '.content-column',
    '#site-footer'
  ];
  let profileSheetOpenerEl = null;
  let authPopoverOpenerEl = null;
  // Width of the classic page scrollbar that the open passenger window is standing in for (0 = none / overlay scrollbars)
  let heldPageScrollbarPx = 0;

  function renderProfileSaveError() {
    const errEl = document.getElementById('profile-save-error');
    if (!errEl) return;
    const msg = state.locale === 'he' ? state.profileSaveErrorHe : state.profileSaveErrorEn;
    if (msg) {
      errEl.textContent = `⚠️ ${msg}`;
      errEl.removeAttribute('hidden');
    } else {
      errEl.textContent = '';
      errEl.setAttribute('hidden', '');
    }
  }

  function getActiveHeaderAuthTrigger() {
    const isAuthed = Boolean(state.auth && state.auth.authenticated && state.auth.user);
    return document.getElementById(isAuthed ? 'btn-header-account' : 'btn-header-auth');
  }

  function setAuthPopoverOpen(open, opts) {
    const options = opts || {};
    const willOpen = Boolean(open);
    const wasOpen = Boolean(state.isAuthPopoverOpen);
    if (willOpen && state.isBookingHandoffOpen) {
      closeBookingHandoffModal({ restoreFocus: false });
    }
    if (willOpen && state.isSharePlanOpen) {
      closeSharePlanModal({ restoreFocus: false });
    }
    if (willOpen && state.isProfileSheetOpen) {
      setProfileSheetOpen(false, { restoreFocus: false });
    }
    if (willOpen && state.isCalendarVisible) {
      setCalendarVisibility(false, { restoreFocus: false });
    }
    if (willOpen && state.isDestPickerOpen) {
      setDestPickerOpen(false);
    }
    state.isAuthPopoverOpen = willOpen;
    if (!willOpen && state.confirmingDeleteProfile) {
      state.confirmingDeleteProfile = false;
      renderAuthControls();
    }
    const popover = document.getElementById('header-auth-popover');
    if (popover) {
      if (willOpen) {
        popover.removeAttribute('hidden');
        popover.style.display = 'block';
      } else {
        popover.setAttribute('hidden', '');
        popover.style.display = 'none';
      }
    }
    const btnAuth = document.getElementById('btn-header-auth');
    const btnAccount = document.getElementById('btn-header-account');
    const isAuthed = Boolean(state.auth && state.auth.authenticated && state.auth.user);
    if (btnAuth) btnAuth.setAttribute('aria-expanded', willOpen && !isAuthed ? 'true' : 'false');
    if (btnAccount) btnAccount.setAttribute('aria-expanded', willOpen && isAuthed ? 'true' : 'false');

    if (willOpen) {
      if (!wasOpen) {
        const activeEl = document.activeElement;
        authPopoverOpenerEl =
          options.opener || (activeEl && activeEl !== document.body ? activeEl : getActiveHeaderAuthTrigger());
      }
      if (options.focusContent !== false) {
        const focusTarget = document.getElementById(isAuthed ? 'btn-signout' : 'btn-google-signin');
        if (focusTarget) {
          setTimeout(() => {
            if (!state.isAuthPopoverOpen) return;
            focusTarget.focus();
          }, 50);
        }
      }
    } else if (wasOpen) {
      if (options.restoreFocus !== false) {
        const activeEl = document.activeElement;
        const focusWasInside =
          !activeEl || activeEl === document.body || Boolean(popover && popover.contains(activeEl));
        const fallbackTrigger = getActiveHeaderAuthTrigger();
        const restoreEl =
          authPopoverOpenerEl && document.contains(authPopoverOpenerEl) && !authPopoverOpenerEl.hasAttribute('hidden')
            ? authPopoverOpenerEl
            : fallbackTrigger;
        if (focusWasInside && restoreEl) {
          restoreEl.focus();
        }
      }
      authPopoverOpenerEl = null;
    }
  }

  // Removes everything the desktop modal window adds (none of it is ever set below 1180px)
  function clearDesktopProfileViewState() {
    const profZone = document.getElementById('zone-profile');
    if (profZone) {
      profZone.removeAttribute('data-sheet-view');
      profZone.removeAttribute('role');
      profZone.removeAttribute('aria-modal');
      if (profZone.getAttribute('aria-labelledby') !== 'zone-profile-title') {
        profZone.setAttribute('aria-labelledby', 'zone-profile-title');
      }
    }
    DESKTOP_MODAL_INERT_SELECTORS.forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) el.removeAttribute('inert');
    });
    const editBtn = document.getElementById('btn-open-profile-sheet');
    if (editBtn) editBtn.setAttribute('aria-expanded', 'false');
    document.body.style.removeProperty('padding-inline-start');
    document.body.style.removeProperty('padding-inline-end');
    state.profileSheetView = null;
    if (state.profileSaveErrorHe || state.profileSaveErrorEn) {
      state.profileSaveErrorHe = null;
      state.profileSaveErrorEn = null;
      renderProfileSaveError();
    }
  }

  // A sheet opened below 1180px must not survive at desktop width, and a desktop modal window must not survive below it
  function closeProfileSheetOnBreakpointCross() {
    if (typeof window === 'undefined') return;
    if ((state.isCalendarVisible || state.isBookingHandoffOpen || state.isSharePlanOpen) && !state.isProfileSheetOpen) return;
    if (!state.isProfileSheetOpen && !document.body.classList.contains('is-sheet-locked')) return;
    const isSheetViewport = window.innerWidth < 1180;
    const openedAsDesktopView = state.profileSheetView !== null;
    if (isSheetViewport === openedAsDesktopView) {
      setProfileSheetOpen(false);
    }
  }

  function setProfileSheetOpen(open, opts) {
    const options = opts || {};
    const willOpen = Boolean(open);
    if (willOpen && state.isBookingHandoffOpen) {
      closeBookingHandoffModal({ restoreFocus: false });
    }
    if (willOpen && state.isSharePlanOpen) {
      closeSharePlanModal({ restoreFocus: false });
    }
    if (willOpen && state.isAuthPopoverOpen) {
      setAuthPopoverOpen(false, { restoreFocus: false });
    }
    if (willOpen && state.isCalendarVisible) {
      setCalendarVisibility(false, { restoreFocus: false });
    }
    const isSheetViewport = typeof window !== 'undefined' && window.innerWidth < 1180;
    const profZone = document.getElementById('zone-profile');
    const backdrop = document.getElementById('profile-sheet-backdrop');
    const btnEditTravelers = document.getElementById('btn-open-profile-sheet');
    const dockProfBtn = document.querySelector('.mobile-dock-btn[data-dock-zone="zone-profile"]');

    if (!isSheetViewport) {
      // Desktop (>=1180px): clicking "Edit" opens the travelers panel as a wide centered modal dialog
      const view = willOpen ? 'travelers' : null;
      const wasOpen = state.isProfileSheetOpen;
      const isModal = view === 'travelers';
      const pageScrollbarPx = document.body.classList.contains('is-sheet-locked')
        ? heldPageScrollbarPx
        : Math.max(0, window.innerWidth - document.documentElement.clientWidth);
      clearDesktopProfileViewState();
      state.isProfileSheetOpen = Boolean(view);
      state.profileSheetView = view;
      if (profZone) {
        profZone.classList.toggle('is-sheet-open', Boolean(view));
        if (view) {
          profZone.setAttribute('data-sheet-view', view);
          profZone.setAttribute('role', 'dialog');
          profZone.setAttribute('aria-modal', 'true');
        }
      }
      if (backdrop) {
        if (isModal) {
          backdrop.removeAttribute('hidden');
          backdrop.style.display = 'block';
        } else {
          backdrop.setAttribute('hidden', '');
          backdrop.style.display = 'none';
        }
      }
      if (isModal) {
        DESKTOP_MODAL_INERT_SELECTORS.forEach((sel) => {
          const el = document.querySelector(sel);
          if (el) el.setAttribute('inert', '');
        });
      }
      syncBodyScrollLock();
      heldPageScrollbarPx = isModal ? pageScrollbarPx : 0;
      if (heldPageScrollbarPx > 0) {
        const scrollbarSide =
          getComputedStyle(document.documentElement).direction === 'rtl'
            ? 'padding-inline-start'
            : 'padding-inline-end';
        document.body.style.setProperty(scrollbarSide, `${heldPageScrollbarPx}px`);
      }
      if (btnEditTravelers) btnEditTravelers.setAttribute('aria-expanded', isModal ? 'true' : 'false');
      if (dockProfBtn) dockProfBtn.classList.remove('active');
      if (isModal) {
        if (!wasOpen) {
          const activeEl = document.activeElement;
          profileSheetOpenerEl =
            options.opener || (activeEl && activeEl !== document.body ? activeEl : btnEditTravelers);
        }
        const focusTarget = document.getElementById(
          options.focusMatmid ? 'prof-matmid-points' : 'prof-adults-count'
        );
        if (focusTarget) {
          setTimeout(() => {
            if (state.profileSheetView !== 'travelers') return;
            focusTarget.focus();
            if (options.focusMatmid && typeof focusTarget.select === 'function') {
              focusTarget.select();
            }
          }, 80);
        }
      } else if (wasOpen) {
        if (options.restoreFocus !== false) {
          const activeEl = document.activeElement;
          const focusWasInside =
            !activeEl || activeEl === document.body || Boolean(profZone && profZone.contains(activeEl));
          if (focusWasInside && profileSheetOpenerEl && document.contains(profileSheetOpenerEl)) {
            profileSheetOpenerEl.focus();
          }
        }
        profileSheetOpenerEl = null;
      }
      return;
    }

    const wasSheetOpen = state.isProfileSheetOpen;
    clearDesktopProfileViewState();
    state.isProfileSheetOpen = willOpen;
    if (!willOpen && (state.profileSaveErrorHe || state.profileSaveErrorEn)) {
      state.profileSaveErrorHe = null;
      state.profileSaveErrorEn = null;
      renderProfileSaveError();
    }
    if (profZone) {
      profZone.classList.toggle('is-sheet-open', state.isProfileSheetOpen);
    }
    if (backdrop) {
      if (state.isProfileSheetOpen) {
        backdrop.removeAttribute('hidden');
        backdrop.style.display = 'block';
      } else {
        backdrop.setAttribute('hidden', '');
        backdrop.style.display = 'none';
      }
    }
    syncBodyScrollLock();
    if (btnEditTravelers) {
      btnEditTravelers.setAttribute('aria-expanded', state.isProfileSheetOpen ? 'true' : 'false');
    }
    if (dockProfBtn) {
      if (state.isProfileSheetOpen) {
        document.querySelectorAll('.mobile-dock-btn').forEach((b) => {
          const z = b.getAttribute('data-dock-zone');
          if (z !== 'zone-calendar' && z !== 'zone-profile') {
            if (b.classList.contains('active')) {
              state.lastActiveMobileZone = z;
            }
            b.classList.remove('active');
          }
        });
        dockProfBtn.classList.add('active');
      } else {
        dockProfBtn.classList.remove('active');
        const restoreZone = state.lastActiveMobileZone || 'zone-search';
        const restoreBtn = document.querySelector(`.mobile-dock-btn[data-dock-zone="${restoreZone}"]`);
        if (restoreBtn) {
          restoreBtn.classList.add('active');
        }
      }
    }
    if (state.isProfileSheetOpen) {
      if (!wasSheetOpen) {
        const activeEl = document.activeElement;
        profileSheetOpenerEl =
          options.opener || (activeEl && activeEl !== document.body ? activeEl : btnEditTravelers);
      }
      if (options.focusMatmid) {
        const matmidEl = document.getElementById('prof-matmid-points');
        if (matmidEl) {
          setTimeout(() => {
            if (!state.isProfileSheetOpen) return;
            matmidEl.focus();
            if (typeof matmidEl.select === 'function') matmidEl.select();
          }, 90);
        }
      }
    } else if (wasSheetOpen) {
      if (options.restoreFocus !== false) {
        const activeEl = document.activeElement;
        const focusWasInside =
          !activeEl || activeEl === document.body || Boolean(profZone && profZone.contains(activeEl));
        if (focusWasInside && profileSheetOpenerEl && document.contains(profileSheetOpenerEl)) {
          profileSheetOpenerEl.focus();
        }
      }
      profileSheetOpenerEl = null;
    }
  }

  function syncSearchFiltersSummary() {
    const isHe = state.locale === 'he';
    const summaryEl = document.getElementById('search-filters-summary-text');
    const toggleBtn = document.getElementById('btn-toggle-search-filters');
    const drawerEl = document.getElementById('search-secondary-drawer');
    if (drawerEl) {
      drawerEl.classList.toggle('is-open', Boolean(state.isSearchFiltersOpen));
    }
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', state.isSearchFiltersOpen ? 'true' : 'false');
    }
    if (!summaryEl) return;

    const activeStyles = (state.selectedVacationTypes || []).filter((vt) => vt && vt !== 'ANY');
    const styleLabel =
      activeStyles.length > 0
        ? isHe
          ? `🌤️ ${activeStyles.length} סגנונות פעילים`
          : `🌤️ ${activeStyles.length} styles active`
        : isHe
          ? '🌤️ סגנון: הכל'
          : '🌤️ Any style';

    if (state.dateSelectionMode === 'HOLIDAY_DIRECT_INTENT') {
      const minN = Number((document.getElementById('input-min-nights') || {}).value || 4);
      const maxN = Number((document.getElementById('input-max-nights') || {}).value || 7);
      const rangeLtr = `\u2066${minN}–${maxN}\u2069`;
      const nightsLabel = isHe ? `🌙 ${rangeLtr} לילות` : `🌙 ${rangeLtr} nights`;
      const isWp = isWorkplaceModeProfile(state.profile);
      const budgetSuffix =
        isWp && state.maxWorkdaysOffBudget !== null && Number.isFinite(state.maxWorkdaysOffBudget)
          ? isHe
            ? ` · 💼 \u2066≤${state.maxWorkdaysOffBudget}\u2069 ימי חופש`
            : ` · 💼 \u2066≤${state.maxWorkdaysOffBudget}\u2069 workdays`
          : '';
      summaryEl.textContent = `${styleLabel} · ${nightsLabel}${budgetSuffix}`;
    } else {
      summaryEl.textContent = styleLabel;
    }
  }

  function getSelectedDestinationCodes() {
    if (Array.isArray(state.selectedDestinations) && state.selectedDestinations.length > 0) {
      return state.selectedDestinations.slice();
    }
    return ['ANYWHERE'];
  }

  function syncNativeSelectFromDestState() {
    const selectEl = document.getElementById('select-destination');
    if (!selectEl || !selectEl.options) return;
    const activeSet = new Set(state.selectedDestinations || []);
    const isAnywhere = activeSet.size === 0;
    Array.from(selectEl.options).forEach((opt) => {
      const code = String(opt.value || '').trim().toUpperCase();
      if (code === 'ANYWHERE') {
        opt.selected = isAnywhere;
      } else {
        opt.selected = !isAnywhere && activeSet.has(code);
      }
    });
  }

  function syncDestStateFromNativeSelect() {
    const selectEl = document.getElementById('select-destination');
    if (!selectEl || !selectEl.options) return;
    const chosen = Array.from(selectEl.selectedOptions || [])
      .map((opt) => String(opt.value || '').trim().toUpperCase())
      .filter(Boolean);
    if (
      chosen.length === 0 ||
      (chosen.length === 1 && (chosen[0] === 'ANYWHERE' || chosen[0] === 'ALL'))
    ) {
      state.selectedDestinations = [];
    } else {
      const specific = chosen.filter((c) => c !== 'ANYWHERE' && c !== 'ALL');
      state.selectedDestinations = Array.from(new Set(specific));
    }
    syncNativeSelectFromDestState();
  }

  function formatDestOptionShortName(optEl, isHe) {
    if (!optEl) return '';
    const code = String(optEl.value || '').trim().toUpperCase();
    const rawLabel = String(
      (isHe ? optEl.getAttribute('data-he') : optEl.getAttribute('data-en')) ||
        optEl.textContent ||
        code
    ).trim();
    const withoutParen = rawLabel.replace(/\s*\([^)]*\)\s*$/, '').trim();
    const primaryCity = withoutParen.split(',')[0].trim();
    return primaryCity || withoutParen || code;
  }

  function setDestPickerOpen(open) {
    if (open && state.isCalendarVisible) {
      setCalendarVisibility(false, { restoreFocus: false });
    }
    state.isDestPickerOpen = Boolean(open);
    const popoverEl = document.getElementById('dest-picker-popover');
    const toggleBtn = document.getElementById('btn-dest-picker-toggle');
    const filterInput = document.getElementById('input-dest-filter');
    if (popoverEl) {
      if (state.isDestPickerOpen) {
        popoverEl.removeAttribute('hidden');
        popoverEl.style.display = 'flex';
      } else {
        popoverEl.setAttribute('hidden', '');
        popoverEl.style.display = 'none';
      }
    }
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', state.isDestPickerOpen ? 'true' : 'false');
    }
    if (!state.isDestPickerOpen && state.destFilterQuery) {
      state.destFilterQuery = '';
      if (filterInput) filterInput.value = '';
    }
    renderDestinationMultiSelect();
    if (
      state.isDestPickerOpen &&
      filterInput &&
      typeof window !== 'undefined' &&
      window.innerWidth >= 768
    ) {
      setTimeout(() => {
        filterInput.focus();
      }, 30);
    }
  }

  function renderDestinationMultiSelect() {
    const isHe = state.locale === 'he';
    const selectEl = document.getElementById('select-destination');
    const summaryEl = document.getElementById('dest-picker-summary');
    const chipsEl = document.getElementById('dest-selected-chips');
    const listEl = document.getElementById('dest-options-list');
    const filterInput = document.getElementById('input-dest-filter');

    if (filterInput) {
      filterInput.placeholder = isHe
        ? 'סינון יעד או קוד שדה (למשל BKK, ROM, אתונה)...'
        : 'Filter city, country, or IATA (e.g. BKK, ROM, Athens)...';
    }
    if (!selectEl) return;

    const optionsByCode = new Map();
    const allOptions = Array.from(selectEl.options || []);
    allOptions.forEach((opt) => {
      const code = String(opt.value || '').trim().toUpperCase();
      if (code) optionsByCode.set(code, opt);
    });

    const selectedCodes = Array.isArray(state.selectedDestinations)
      ? state.selectedDestinations
      : [];
    const selectedSet = new Set(selectedCodes);
    const isAnywhere = selectedSet.size === 0;

    if (summaryEl) {
      if (isAnywhere) {
        const anyOpt = optionsByCode.get('ANYWHERE');
        summaryEl.textContent = anyOpt
          ? String(
              (isHe ? anyOpt.getAttribute('data-he') : anyOpt.getAttribute('data-en')) ||
                anyOpt.textContent ||
                ''
            ).trim()
          : isHe
            ? '🌍 כל היעדים הפתוחים בבונוס (ANYWHERE)'
            : '🌍 All Open Award Destinations (ANYWHERE)';
      } else if (selectedCodes.length === 1) {
        const oneOpt = optionsByCode.get(selectedCodes[0]);
        summaryEl.textContent = oneOpt
          ? String(
              (isHe ? oneOpt.getAttribute('data-he') : oneOpt.getAttribute('data-en')) ||
                oneOpt.textContent ||
                selectedCodes[0]
            ).trim()
          : selectedCodes[0];
      } else {
        const previewNames = selectedCodes
          .slice(0, 3)
          .map((c) => formatDestOptionShortName(optionsByCode.get(c), isHe) || c);
        const extra = selectedCodes.length > 3 ? ` +${selectedCodes.length - 3}` : '';
        summaryEl.textContent = isHe
          ? `✈️ ${selectedCodes.length} יעדים נבחרו: ${previewNames.join(', ')}${extra}`
          : `✈️ ${selectedCodes.length} destinations: ${previewNames.join(', ')}${extra}`;
      }
    }

    if (chipsEl) {
      if (isAnywhere) {
        chipsEl.setAttribute('hidden', '');
        chipsEl.style.display = 'none';
        chipsEl.innerHTML = '';
      } else {
        chipsEl.removeAttribute('hidden');
        chipsEl.style.display = 'flex';
        const chipsHtml = selectedCodes
          .map((code) => {
            const opt = optionsByCode.get(code);
            const shortName = formatDestOptionShortName(opt, isHe) || code;
            const icon = DESTINATION_ICONS[code] || '✈️';
            return `<button type="button" class="dest-chip" data-remove-dest="${escapeHtml(code)}" title="${isHe ? 'הסר יעד' : 'Remove destination'}"><span>${icon} ${escapeHtml(shortName)} (<span dir="ltr">${escapeHtml(code)}</span>)</span><span aria-hidden="true">✕</span></button>`;
          })
          .join('');
        const clearBtnHtml = `<button type="button" class="dest-chip dest-chip-clear-all" id="btn-dest-clear-all">${isHe ? 'נקה הכל' : 'All open'}</button>`;
        chipsEl.innerHTML = chipsHtml + clearBtnHtml;
      }
    }

    if (listEl) {
      const q = String(state.destFilterQuery || '').trim().toLowerCase();
      const matchingOpts = allOptions.filter((opt) => {
        if (!q) return true;
        const code = String(opt.value || '').toLowerCase();
        const heTxt = String(opt.getAttribute('data-he') || '').toLowerCase();
        const enTxt = String(opt.getAttribute('data-en') || '').toLowerCase();
        const rawTxt = String(opt.textContent || '').toLowerCase();
        return code.includes(q) || heTxt.includes(q) || enTxt.includes(q) || rawTxt.includes(q);
      });

      if (matchingOpts.length === 0) {
        listEl.innerHTML = `<p class="dest-options-empty">${isHe ? 'לא נמצאו יעדים התואמים לסינון.' : 'No matching destinations found.'}</p>`;
      } else {
        listEl.innerHTML = matchingOpts
          .map((opt) => {
            const code = String(opt.value || '').trim().toUpperCase();
            const isOptSelected = code === 'ANYWHERE' ? isAnywhere : selectedSet.has(code);
            const labelTxt = String(
              (isHe ? opt.getAttribute('data-he') : opt.getAttribute('data-en')) ||
                opt.textContent ||
                code
            ).trim();
            const icon = code === 'ANYWHERE' ? '' : (DESTINATION_ICONS[code] ? `${DESTINATION_ICONS[code]} ` : '');
            return `
              <button type="button" class="dest-option-row${isOptSelected ? ' is-selected' : ''}" role="option" aria-selected="${isOptSelected ? 'true' : 'false'}" data-dest-option="${escapeHtml(code)}">
                <span class="dest-option-main">
                  <span class="dest-option-check" aria-hidden="true">${isOptSelected ? '✓' : ''}</span>
                  <span class="dest-option-label">${icon}${escapeHtml(labelTxt)}</span>
                </span>
                <span class="dest-option-iata" dir="ltr">${escapeHtml(code)}</span>
              </button>
            `;
          })
          .join('');
      }
    }
  }

  let pendingDestSearchQueued = false;

  function toggleDestinationSelection(code, triggerSearch) {
    const norm = String(code || '').trim().toUpperCase();
    if (!norm || norm === 'ANYWHERE' || norm === 'ALL') {
      state.selectedDestinations = [];
    } else {
      const next = Array.isArray(state.selectedDestinations)
        ? state.selectedDestinations.slice()
        : [];
      const idx = next.indexOf(norm);
      if (idx >= 0) {
        next.splice(idx, 1);
      } else {
        next.push(norm);
      }
      state.selectedDestinations = next;
    }
    syncNativeSelectFromDestState();
    renderDestinationMultiSelect();
    if (triggerSearch && !pendingDestSearchQueued) {
      pendingDestSearchQueued = true;
      Promise.resolve().then(() => {
        pendingDestSearchQueued = false;
        runVacationSearch();
      });
    }
  }

  function isTextEntryControl(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toUpperCase();
    if (tag === 'TEXTAREA') return true;
    if (tag !== 'INPUT') return false;
    const t = String(el.type || 'text').toLowerCase();
    return t !== 'checkbox' && t !== 'radio' && t !== 'button' && t !== 'submit' && t !== 'reset';
  }

  function bindKeyboardViewportGuard() {
    document.addEventListener('focusin', (ev) => {
      if (typeof window !== 'undefined' && window.innerWidth < 1024 && isTextEntryControl(ev.target)) {
        document.body.classList.add('is-keyboard-open');
      }
    });
    document.addEventListener('focusout', (ev) => {
      if (isTextEntryControl(ev.relatedTarget)) {
        return;
      }
      document.body.classList.remove('is-keyboard-open');
    });
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', () => {
        if (window.innerWidth >= 1024) {
          document.body.classList.remove('is-keyboard-open');
        }
        closeProfileSheetOnBreakpointCross();
      });
      if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
          closeProfileSheetOnBreakpointCross();
          if (window.innerWidth >= 1024) {
            document.body.classList.remove('is-keyboard-open');
            return;
          }
          const shrunk = window.innerHeight - window.visualViewport.height > 140;
          if (shrunk) {
            document.body.classList.add('is-keyboard-open');
          } else if (!isTextEntryControl(document.activeElement)) {
            document.body.classList.remove('is-keyboard-open');
          }
        });
      }
    }
  }

  function suggestFrameworkByAge(ageYears) {
    const age = Number(ageYears) || 0;
    if (age < 3) return 'DAYCARE_SUPERVISED';
    if (age < 6) return 'MUNICIPAL_GAN';
    if (age < 9) return 'ELEMENTARY_1_3';
    if (age < 12) return 'ELEMENTARY_4_6';
    if (age < 15) return 'MIDDLE_SCHOOL_7_9';
    return 'HIGH_SCHOOL_10_12';
  }

  function formatGenericChildTitle(idx) {
    return state.locale === 'he' ? `ילד/ה #${idx + 1}` : `Child #${idx + 1}`;
  }

  function buildHouseholdPassengerSummary(profileObj, itineraryObj, isHe) {
    const adults = Math.max(1, Number((profileObj && profileObj.adults_count) || 2));
    const children = Array.isArray(profileObj && profileObj.children) ? profileObj.children : [];
    const rawLapInfants = children.filter(
      (c) =>
        Number(c.child_age_years ?? 6) < 2 &&
        String(c.passenger_Current_type || '').toUpperCase() !== 'INFANT_SEAT'
    ).length;
    const fallbackSeated = adults + (children.length - Math.min(adults, rawLapInfants));
    const rawBackendSeated = Number(itineraryObj && itineraryObj.seated_passengers_count);
    const seatedCount =
      Number.isFinite(rawBackendSeated) && rawBackendSeated >= 1
        ? Math.round(rawBackendSeated)
        : fallbackSeated;
    const totalTravelers = Math.max(adults + children.length, seatedCount);
    const infantsLap = Math.max(0, totalTravelers - seatedCount);
    const seatedChildren = Math.max(0, seatedCount - adults);

    const seatsLabelHe = seatedCount === 1 ? 'מושב 1' : `${seatedCount} מושבים`;
    const seatsLabelEn = seatedCount === 1 ? '1 seat' : `${seatedCount} seats`;
    const infantsLabelHe = infantsLap === 1 ? 'תינוק ללא מושב' : `${infantsLap} תינוקות ללא מושב`;
    const infantsLabelEn = infantsLap === 1 ? '1 lap infant' : `${infantsLap} lap infants`;
    const adultsLabelHe = adults === 1 ? 'מבוגר 1' : `${adults} מבוגרים`;
    const adultsLabelEn = adults === 1 ? '1 adult' : `${adults} adults`;
    const childrenLabelHe = seatedChildren === 1 ? 'ילד/ה 1' : `${seatedChildren} ילדים`;
    const childrenLabelEn = seatedChildren === 1 ? '1 child' : `${seatedChildren} children`;

    let paxSummaryText = '';
    if (infantsLap > 0) {
      paxSummaryText = isHe
        ? `${totalTravelers} נוסעים (${seatsLabelHe} + ${infantsLabelHe})`
        : `${totalTravelers} travelers (${seatsLabelEn} + ${infantsLabelEn})`;
    } else if (seatedChildren > 0) {
      paxSummaryText = isHe
        ? `${totalTravelers} נוסעים (${adultsLabelHe} + ${childrenLabelHe})`
        : `${totalTravelers} travelers (${adultsLabelEn} + ${childrenLabelEn})`;
    } else if (seatedCount !== adults) {
      paxSummaryText = isHe
        ? `${totalTravelers} נוסעים (${seatsLabelHe})`
        : `${totalTravelers} travelers (${seatsLabelEn})`;
    } else {
      paxSummaryText = isHe ? `עבור ${adultsLabelHe}` : `For ${adultsLabelEn}`;
    }
    return { adults, infantsLap, seatedChildren, seatedCount, totalTravelers, paxSummaryText };
  }

  function formatStrategyLabel(strategyCode, itineraryObj, dirInfo) {
    const code = String(strategyCode || '');
    const isHe = state.locale === 'he';
    const it = itineraryObj || null;
    const destIata = String((it && it.destination_iata) || '').trim().toUpperCase();
    const retOrigIata = String((it && it.return_origin_iata) || destIata).trim().toUpperCase();
    const isOpenJaw = Boolean(destIata && retOrigIata && destIata !== retOrigIata);
    const cov = String(
      (dirInfo && dirInfo.coverage) || (it && it.bonus_direction_coverage) || ''
    )
      .trim()
      .toUpperCase();

    if (code === 'ONE_WAY_BONUS_ONE_WAY_CASH') {
      if (isOpenJaw && cov === 'BOTH_DIRECTIONS') {
        if (Number((it && it.cash_tickets_count) || 0) > 0) {
          return isHe
            ? `מסלול משולב (${destIata}/${retOrigIata}) · בונוס לחלק מהנוסעים`
            : `Open-jaw (${destIata}/${retOrigIata}) · partial-party bonus`;
        }
        return isHe
          ? `מסלול משולב (הלוך ל-${destIata}, חזור מ-${retOrigIata})`
          : `Open-jaw bonus (out to ${destIata}, back from ${retOrigIata})`;
      }
      if (cov === 'BOTH_DIRECTIONS') {
        return isHe ? 'מימוש נקודות לכיוון אחד' : 'One-direction points option';
      }
      if (isOpenJaw) {
        return isHe
          ? `מסלול משולב (${destIata}/${retOrigIata}) · כיוון אחד בבונוס + כיוון אחד מסחרי`
          : `Open-jaw (${destIata}/${retOrigIata}) · one way on bonus + one way commercial`;
      }
    }

    const labelsHe = {
      FULL_BONUS_SAME_CABIN: 'בונוס מלא באותה מחלקה',
      SPLIT_CABIN_BONUS: 'בונוס מפוצל בין מחלקות (אותה טיסה)',
      HYBRID_BONUS_PLUS_CASH: 'בונוס לחלק מהנוסעים + כרטיסים מסחריים',
      ONE_WAY_BONUS_ONE_WAY_CASH: 'כיוון אחד בבונוס + כיוון אחד מסחרי',
      CASH_AND_POINTS: 'נקודות + כסף (Cash & Points)',
      MULTI_CLUB_PER_PASSENGER_SPLIT: 'פיצול נקודות בין מועדונים ונוסעים',
      COMMERCIAL_CASH_ONLY: 'כרטיסים מסחריים (ללא בונוס)'
    };
    const labelsEn = {
      FULL_BONUS_SAME_CABIN: 'Full Bonus (Same Cabin)',
      SPLIT_CABIN_BONUS: 'Split-Cabin Bonus (Same Flight)',
      HYBRID_BONUS_PLUS_CASH: 'Bonus for some travelers + commercial tickets',
      ONE_WAY_BONUS_ONE_WAY_CASH: 'One way on bonus + one way commercial',
      CASH_AND_POINTS: 'Points + money (Cash & Points)',
      MULTI_CLUB_PER_PASSENGER_SPLIT: 'Multi-Club Per-Passenger Split',
      COMMERCIAL_CASH_ONLY: 'Commercial tickets (no bonus)'
    };
    return (isHe ? labelsHe[code] : labelsEn[code]) || code;
  }

  function resolveCardStrategyBadge(itineraryObj, dirInfo, isHe) {
    const it = itineraryObj || {};
    const strategyCode = String(it.fulfillment_strategy || 'FULL_BONUS_SAME_CABIN');
    const destIata = String(it.destination_iata || '').trim().toUpperCase();
    const retOrigIata = String(it.return_origin_iata || destIata).trim().toUpperCase();
    const isOpenJaw = Boolean(destIata && retOrigIata && destIata !== retOrigIata);
    const cov = String(
      (dirInfo && dirInfo.coverage) || it.bonus_direction_coverage || ''
    )
      .trim()
      .toUpperCase();

    if (strategyCode === 'FULL_BONUS_SAME_CABIN') {
      if (!isOpenJaw) return '';
      return isHe
        ? `מסלול משולב (הלוך ל-${destIata}, חזור מ-${retOrigIata})`
        : `Open-jaw bonus (out to ${destIata}, back from ${retOrigIata})`;
    }
    if (strategyCode === 'ONE_WAY_BONUS_ONE_WAY_CASH') {
      if (!isOpenJaw && cov !== 'BOTH_DIRECTIONS') {
        return '';
      }
      if (isOpenJaw && cov !== 'BOTH_DIRECTIONS') {
        return isHe
          ? `מסלול משולב (הלוך ל-${destIata}, חזור מ-${retOrigIata})`
          : `Open-jaw route (out to ${destIata}, back from ${retOrigIata})`;
      }
    }
    return formatStrategyLabel(strategyCode, it, dirInfo);
  }

  function classifyFareByAge(ageYears) {
    const age = Number(ageYears) || 0;
    if (age < 2) return state.locale === 'he' ? 'תינוק (גיל <2)' : 'Infant (<2)';
    if (age < 12) return state.locale === 'he' ? 'ילד/ה (גילאי 2–11)' : 'Child (2–11)';
    return state.locale === 'he' ? 'נוער (גילאי 12–18)' : 'Youth (12–18)';
  }

  async function apiGet(path) {
    const resp = await fetch(path, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store'
    });
    if (!resp.ok) {
      const err = new Error(`GET ${path} failed (${resp.status})`);
      err.status = resp.status;
      throw err;
    }
    return resp.json();
  }

  async function apiSend(method, path, bodyObj) {
    const hdrs = { 'Content-Type': 'application/json' };
    if (state.auth && state.auth.csrfToken) {
      hdrs['X-CSRF-Token'] = state.auth.csrfToken;
    }
    const resp = await fetch(path, {
      method,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: hdrs,
      body: JSON.stringify(bodyObj || {})
    });
    if (!resp.ok) {
      const errText = await resp.text();
      const err = new Error(`${method} ${path} failed (${resp.status}): ${errText}`);
      err.status = resp.status;
      err.bodyText = errText;
      throw err;
    }
    return resp.json();
  }

  function extractApiErrorDetail(err) {
    if (!err) return '';
    if (err.bodyText) {
      try {
        const parsed = JSON.parse(err.bodyText);
        const msg = parsed && (typeof parsed.detail === 'string' ? parsed.detail : typeof parsed.error === 'string' ? parsed.error : '');
        if (msg) {
          return msg.trim();
        }
      } catch (_ignore) {
        // Non-JSON error body
      }
    }
    return '';
  }

  let autoAdjustPulseTimer = null;

  function pulseHolidayDurationAdjusted() {
    const durEl = document.getElementById('controls-holiday-duration');
    if (!durEl) return;
    durEl.classList.remove('is-auto-adjusted');
    void durEl.offsetWidth;
    durEl.classList.add('is-auto-adjusted');
    if (autoAdjustPulseTimer) clearTimeout(autoAdjustPulseTimer);
    autoAdjustPulseTimer = setTimeout(() => {
      durEl.classList.remove('is-auto-adjusted');
    }, 900);
  }

  function applyHolidayDurationDefault(holidayDaysOrObj, opts) {
    const options = opts || {};
    const forceBoth = Boolean(options.forceBoth);
    const isObj = holidayDaysOrObj && typeof holidayDaysOrObj === 'object';
    const calMode = isObj ? String(holidayDaysOrObj.calendarMode || holidayDaysOrObj.calendar_mode || '').toUpperCase() : '';
    const isWorkplace = calMode === 'WORKPLACE';
    const holidayCode = isObj ? String(holidayDaysOrObj.holidayCode || holidayDaysOrObj.holiday_code || '').toUpperCase() : '';
    const maxInput = document.getElementById('input-max-nights');
    const minInput = document.getElementById('input-min-nights');

    if (isWorkplace) {
      const recPair = WORKPLACE_RECOMMENDED_NIGHTS_CLIENT[holidayCode] || null;
      const recMinRaw = isObj
        ? (holidayDaysOrObj.recommendedMinNights ?? holidayDaysOrObj.recommended_min_nights ?? (recPair ? recPair[0] : null))
        : null;
      const recMaxRaw = isObj
        ? (holidayDaysOrObj.recommendedMaxNights ?? holidayDaysOrObj.recommended_max_nights ?? (recPair ? recPair[1] : null))
        : null;
      const coreDays = Math.max(1, Math.round(Number(isObj ? (holidayDaysOrObj.holidayDays ?? holidayDaysOrObj.holiday_days) : holidayDaysOrObj) || 7));
      const fallbackMax = Math.min(45, Math.max(1, Math.round(Number(isObj ? (holidayDaysOrObj.recommendedTripDays ?? holidayDaysOrObj.recommended_trip_days ?? coreDays) : coreDays) || 7)));
      const fallbackMin = Math.min(coreDays <= 2 ? 2 : 4, fallbackMax);
      const targetMin = Math.min(45, Math.max(1, Math.round(Number(recMinRaw ?? fallbackMin))));
      const targetMax = Math.min(45, Math.max(targetMin, Math.round(Number(recMaxRaw ?? fallbackMax))));

      if (forceBoth) {
        if (minInput) minInput.value = String(targetMin);
        if (maxInput) maxInput.value = String(targetMax);
        pulseHolidayDurationAdjusted();
      } else {
        if (!state.userEditedMaxNights && maxInput) {
          maxInput.value = String(targetMax);
        }
        if (!state.userEditedMinNights && minInput) {
          const effMax = maxInput ? Number(maxInput.value || targetMax) : targetMax;
          minInput.value = String(Math.min(targetMin, Math.max(1, effMax)));
        }
      }
      syncSearchFiltersSummary();
      return;
    }

    const coreDays = Math.max(
      1,
      Math.round(Number(isObj ? (holidayDaysOrObj.holidayDays ?? holidayDaysOrObj.holiday_days) : holidayDaysOrObj) || 7)
    );
    const daysNum = Math.min(45, Math.max(1, coreDays));
    const defaultMinCap = 4;
    if (maxInput && (forceBoth || !state.userEditedMaxNights)) {
      maxInput.value = String(daysNum);
    }
    if (minInput) {
      if (forceBoth || !state.userEditedMinNights) {
        minInput.value = String(Math.min(defaultMinCap, daysNum));
      } else if (Number(minInput.value || 1) > daysNum && !state.userEditedMaxNights) {
        minInput.value = String(daysNum);
      }
    }
    syncSearchFiltersSummary();
  }

  function getActiveWorkplaceCatalog() {
    if (
      state.workplaceCatalog &&
      Array.isArray(state.workplaceCatalog.holiday_groups) &&
      state.workplaceCatalog.holiday_groups.length > 0
    ) {
      return state.workplaceCatalog;
    }
    const built = buildUpcomingWorkplaceCatalogClient(getAsOfOverrideIso() || getReferenceToday());
    state.workplaceCatalog = built;
    return built;
  }

  function findWorkplaceHolidayItem(code) {
    const norm = String(code || '').trim().toUpperCase();
    const cat = getActiveWorkplaceCatalog();
    if (cat.best_year_option && cat.best_year_option.holiday_code === norm) {
      return cat.best_year_option;
    }
    const found = (cat.catalog_items || []).find((it) => it.holiday_code === norm);
    return found || null;
  }

  function syncBestYearQuickButton() {
    const btn = document.getElementById('btn-best-year-quick');
    if (!btn) return;
    const isWp = isWorkplaceModeProfile(state.profile);
    const isHolidayMode = state.dateSelectionMode === 'HOLIDAY_DIRECT_INTENT';
    const show = isWp && isHolidayMode;
    btn.hidden = !show;
    btn.style.display = show ? 'inline-flex' : 'none';
    const selectEl = document.getElementById('select-direct-holiday');
    const isActive = Boolean(show && selectEl && selectEl.value === 'BEST_YEAR_MAXIMIZER');
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  }

  function renderWorkplaceHolidayBrief() {
    const briefEl = document.getElementById('workplace-holiday-brief');
    if (!briefEl) return;
    const isWp = isWorkplaceModeProfile(state.profile);
    const isHolidayMode = state.dateSelectionMode === 'HOLIDAY_DIRECT_INTENT';
    if (!isWp || !isHolidayMode) {
      briefEl.hidden = true;
      briefEl.style.display = 'none';
      briefEl.innerHTML = '';
      return;
    }
    const selectEl = document.getElementById('select-direct-holiday');
    const code = (selectEl && selectEl.value) || 'PESACH';
    const item = findWorkplaceHolidayItem(code);
    if (!item) {
      briefEl.hidden = true;
      briefEl.style.display = 'none';
      return;
    }
    const isHe = state.locale === 'he';
    const recMin = item.recommended_min_nights || 3;
    const recMax = item.recommended_max_nights || 15;
    const nightsRangeHtml = `<strong dir="ltr">${escapeHtml(recMin)}–${escapeHtml(recMax)}</strong> ${isHe ? 'לילות' : 'nights'}`;

    let bodyHtml = '';
    let isFeatured = false;

    if (code === 'BEST_YEAR_MAXIMIZER') {
      isFeatured = true;
      bodyHtml = `
        <span class="brief-main-line">
          ${
            isHe
              ? `✨ סורק את כל חגי המשק ואיחודי החגים בשנה הקרובה · טווח מומלץ: ${nightsRangeHtml}`
              : `✨ Scans all Israeli workplace holidays & bridges over the next 12 months · Recommended: ${nightsRangeHtml}`
          }
        </span>
      `;
    } else if (item.holiday_group === 'MEGA_BRIDGES' || item.is_mega_vacation) {
      isFeatured = true;
      const mergedNames = (item.merged_holidays || []).map((m) =>
        isHe ? (m.short_name_he || m.name_he) : (m.short_name_en || m.name_en)
      );
      const chainText = mergedNames.length > 0 ? mergedNames.join(' → ') : (isHe ? item.name_he : item.name_en);
      const spanTxt = formatCompactDateRange(
        item.recommended_window_start || item.start_date,
        item.recommended_window_end || item.end_date,
        isHe
      );
      bodyHtml = `
        <span class="brief-main-line">
          🌉 <strong>${escapeHtml(chainText)}</strong> · ${escapeHtml(spanTxt)} · ${isHe ? 'טווח מומלץ:' : 'Recommended:'} ${nightsRangeHtml}
        </span>
      `;
    } else {
      const spanTxt = formatCompactDateRange(
        item.recommended_window_start || item.start_date,
        item.recommended_window_end || item.end_date,
        isHe
      );
      bodyHtml = `
        <span class="brief-main-line">
          📅 ${escapeHtml(spanTxt)} · ${isHe ? 'טווח מומלץ:' : 'Recommended:'} ${nightsRangeHtml}
        </span>
      `;
    }

    briefEl.classList.toggle('is-featured', isFeatured);
    briefEl.innerHTML = bodyHtml;
    briefEl.hidden = false;
    briefEl.style.display = 'flex';
  }

  function syncWorkdaysBudgetUi() {
    const budgetWrap = document.getElementById('controls-workday-budget');
    const clearBtn = document.getElementById('btn-clear-workdays-budget');
    const inputEl = document.getElementById('input-max-workdays-off');
    const isWp = isWorkplaceModeProfile(state.profile);
    const isHolidayMode = state.dateSelectionMode === 'HOLIDAY_DIRECT_INTENT';
    const show = isWp && isHolidayMode;

    if (budgetWrap) {
      budgetWrap.hidden = !show;
      budgetWrap.style.display = show ? 'flex' : 'none';
    }
    const val = state.maxWorkdaysOffBudget;
    const hasVal = val !== null && Number.isFinite(val);
    if (inputEl && document.activeElement !== inputEl) {
      inputEl.value = hasVal ? String(val) : '';
    }
    if (clearBtn) {
      clearBtn.hidden = !hasVal;
      clearBtn.style.display = hasVal ? 'inline-flex' : 'none';
    }
    document.querySelectorAll('#workday-budget-presets .budget-preset-pill').forEach((btn) => {
      const presetRaw = btn.getAttribute('data-budget-preset');
      const isMatch =
        presetRaw === ''
          ? !hasVal
          : hasVal && Math.abs(Number(presetRaw) - val) < 1e-6;
      btn.classList.toggle('active', isMatch);
      btn.setAttribute('aria-pressed', isMatch ? 'true' : 'false');
    });
  }

  function setWorkdaysBudgetValue(rawVal, triggerSearch) {
    if (rawVal === null || rawVal === undefined || String(rawVal).trim() === '') {
      state.maxWorkdaysOffBudget = null;
    } else {
      const parsed = Number(rawVal);
      if (!Number.isFinite(parsed) || parsed < 0) {
        return;
      }
      state.maxWorkdaysOffBudget = Math.min(45, Math.round(parsed * 2) / 2);
    }
    syncWorkdaysBudgetUi();
    syncSearchFiltersSummary();
    if (triggerSearch) {
      runVacationSearch();
    }
  }

  function syncWorkplaceHolidayControlsVisibility() {
    const isWp = isWorkplaceModeProfile(state.profile);
    if (!isWp && state.maxWorkdaysOffBudget !== null) {
      state.maxWorkdaysOffBudget = null;
      const inputEl = document.getElementById('input-max-workdays-off');
      if (inputEl) inputEl.value = '';
    }
    syncBestYearQuickButton();
    renderWorkplaceHolidayBrief();
    syncWorkdaysBudgetUi();
  }

  function populateHolidaySelector(holidaysList, opts) {
    const options = opts || {};
    const selectEl = document.getElementById('select-direct-holiday');
    if (!selectEl) return;

    const prevVal = selectEl.value;
    const isHe = state.locale === 'he';
    const fallbackCalMode = isWorkplaceModeProfile(state.profile) ? 'WORKPLACE' : 'MOE';

    if (fallbackCalMode === 'WORKPLACE') {
      const catalog = getActiveWorkplaceCatalog();
      const bestOpt = catalog.best_year_option;
      const groups = Array.isArray(catalog.holiday_groups) ? catalog.holiday_groups : [];
      const indGroup = groups.find((g) => g.group_id === 'INDIVIDUAL_HOLIDAYS') || { items: [] };
      const megaGroup = groups.find((g) => g.group_id === 'MEGA_BRIDGES') || { items: [] };
      const allItems = [
        ...(bestOpt ? [bestOpt] : []),
        ...(indGroup.items || []),
        ...(megaGroup.items || [])
      ];
      if (allItems.length === 0) return;

      const hasPrev =
        Boolean(options.preserveSelection) &&
        allItems.some((h) => h.holiday_code === prevVal);
      const defaultCode =
        (indGroup.items && indGroup.items[0] && indGroup.items[0].holiday_code) ||
        allItems[0].holiday_code;
      const activeCode = hasPrev ? prevVal : defaultCode;

      const buildOptionHtml = (h, grpTag) => {
        const selAttr = h.holiday_code === activeCode ? ' selected' : '';
        const text = isHe ? h.label_he : h.label_en;
        const recDays = h.recommended_trip_days ?? h.holiday_days ?? 7;
        const recMin = h.recommended_min_nights ?? (WORKPLACE_RECOMMENDED_NIGHTS_CLIENT[h.holiday_code] || [4, 7])[0];
        const recMax = h.recommended_max_nights ?? (WORKPLACE_RECOMMENDED_NIGHTS_CLIENT[h.holiday_code] || [4, 7])[1];
        const wpCostAttr = h.recommended_workdays_cost !== undefined && h.recommended_workdays_cost !== null ? String(h.recommended_workdays_cost) : '';
        const wpSavedAttr = h.recommended_workdays_saved !== undefined && h.recommended_workdays_saved !== null ? String(h.recommended_workdays_saved) : '';
        const wpRatioAttr = h.recommended_efficiency_ratio !== undefined && h.recommended_efficiency_ratio !== null ? String(h.recommended_efficiency_ratio) : '';
        const ykAttr = h.includes_yom_kippur_abroad ? 'true' : 'false';
        return `<option value="${escapeHtml(h.holiday_code)}"${selAttr} data-holiday-group="${escapeHtml(grpTag)}" data-year="${escapeHtml(h.target_year || '')}" data-days="${escapeHtml(h.holiday_days || recDays)}" data-rec-days="${escapeHtml(recDays)}" data-rec-min-nights="${escapeHtml(recMin)}" data-rec-max-nights="${escapeHtml(recMax)}" data-includes-yk-abroad="${ykAttr}" data-workdays-cost="${escapeHtml(wpCostAttr)}" data-workdays-saved="${escapeHtml(wpSavedAttr)}" data-efficiency-ratio="${escapeHtml(wpRatioAttr)}" data-calendar-mode="WORKPLACE" data-start="${escapeHtml(h.start_date || '')}" data-end="${escapeHtml(h.end_date || '')}" data-he="${escapeHtml(h.label_he)}" data-en="${escapeHtml(h.label_en)}">${escapeHtml(text)}</option>`;
      };

      const bestHtml = bestOpt ? buildOptionHtml(bestOpt, 'best_year') : '';
      const indLabel = isHe ? '📅 חגי משק בודדים' : '📅 Individual Market Holidays';
      const megaLabel = isHe ? '🌉 מגה-חופשות ואיחודי חגים' : '🌉 Mega-Vacations & Holiday Bridges';
      const indHtml = (indGroup.items || []).length
        ? `<optgroup label="${escapeHtml(indLabel)}" data-holiday-group="individual">${indGroup.items.map((h) => buildOptionHtml(h, 'individual')).join('')}</optgroup>`
        : '';
      const megaHtml = (megaGroup.items || []).length
        ? `<optgroup label="${escapeHtml(megaLabel)}" data-holiday-group="mega_bridge">${megaGroup.items.map((h) => buildOptionHtml(h, 'mega_bridge')).join('')}</optgroup>`
        : '';

      selectEl.innerHTML = bestHtml + indHtml + megaHtml;
      selectEl.value = activeCode;

      const chosen = allItems.find((h) => h.holiday_code === activeCode) || allItems[0];
      state.activeHolidayGroup = chosen ? chosen.holiday_group || null : null;
      if (
        options.applyDurationDefault ||
        (!hasPrev && !state.userEditedMaxNights && !state.userEditedMinNights)
      ) {
        applyHolidayDurationDefault(chosen, { forceBoth: Boolean(options.forceBoth) });
      }
      syncBestYearQuickButton();
      renderWorkplaceHolidayBrief();
      updateActiveModeBadge();
      return;
    }

    if (!Array.isArray(holidaysList) || holidaysList.length === 0) return;

    const hasPrev =
      Boolean(options.preserveSelection) &&
      holidaysList.some((h) => h.holiday_code === prevVal);
    const activeCode = hasPrev ? prevVal : holidaysList[0].holiday_code;

    selectEl.innerHTML = holidaysList
      .map((h) => {
        const selAttr = h.holiday_code === activeCode ? ' selected' : '';
        const text = isHe ? h.label_he : h.label_en;
        const recDays = h.recommended_trip_days !== undefined && h.recommended_trip_days !== null
          ? h.recommended_trip_days
          : h.holiday_days;
        const calMode = h.calendar_mode || fallbackCalMode;
        const wpCostAttr = h.recommended_workdays_cost !== undefined && h.recommended_workdays_cost !== null
          ? String(h.recommended_workdays_cost)
          : '';
        const wpSavedAttr = h.recommended_workdays_saved !== undefined && h.recommended_workdays_saved !== null
          ? String(h.recommended_workdays_saved)
          : '';
        const wpRatioAttr = h.recommended_efficiency_ratio !== undefined && h.recommended_efficiency_ratio !== null
          ? String(h.recommended_efficiency_ratio)
          : '';
        return `<option value="${escapeHtml(h.holiday_code)}"${selAttr} data-year="${escapeHtml(h.target_year)}" data-days="${escapeHtml(h.holiday_days)}" data-rec-days="${escapeHtml(recDays)}" data-workdays-cost="${escapeHtml(wpCostAttr)}" data-workdays-saved="${escapeHtml(wpSavedAttr)}" data-efficiency-ratio="${escapeHtml(wpRatioAttr)}" data-calendar-mode="${escapeHtml(calMode)}" data-start="${escapeHtml(h.start_date)}" data-end="${escapeHtml(h.end_date)}" data-he="${escapeHtml(h.label_he)}" data-en="${escapeHtml(h.label_en)}">${escapeHtml(text)}</option>`;
      })
      .join('');

    selectEl.value = activeCode;
    state.activeHolidayGroup = null;
    if (options.applyDurationDefault || (!hasPrev && !state.userEditedMaxNights)) {
      const chosen = holidaysList.find((h) => h.holiday_code === activeCode) || holidaysList[0];
      applyHolidayDurationDefault({
        holidayDays: chosen.holiday_days,
        recommendedTripDays: chosen.recommended_trip_days,
        calendarMode: chosen.calendar_mode || fallbackCalMode
      });
    }
    syncWorkplaceHolidayControlsVisibility();
  }

  function initDefaultManualDates() {
    if (state.userEditedManualDates) return;
    const refIso = getReferenceToday();
    const depInput = document.getElementById('input-dep-date');
    const retInput = document.getElementById('input-ret-date');
    if (depInput) depInput.value = addDaysIso(refIso, 21);
    if (retInput) retInput.value = addDaysIso(refIso, 28);
  }

  function syncHouseholdDisplaySummary(matmidOverride) {
    const isHe = state.locale === 'he';
    const adults = Math.max(1, Number((state.profile && state.profile.adults_count) || 2));
    const kids = Array.isArray(state.profile && state.profile.children)
      ? state.profile.children.length
      : 0;
    const matmidTotal =
      matmidOverride !== undefined
        ? matmidOverride
        : Math.max(0, Math.round(Number((state.profile && state.profile.matmid_points_balance) || 0)));

    const summaryText = document.getElementById('household-summary-text');
    if (summaryText) {
      const partyIcon = kids === 0 ? '👥' : '👨‍👩‍👧‍👦';
      const aNum = `<span class="num">${escapeHtml(adults)}</span>`;
      const kNum = `<span class="num">${escapeHtml(kids)}</span>`;
      const pNum = `<span class="num">${escapeHtml(matmidTotal.toLocaleString())}</span>`;
      summaryText.innerHTML = isHe
        ? `${partyIcon} ${aNum} מבוגרים · ${kNum} ילדים · 💳 ${pNum} מתמיד`
        : `${partyIcon} ${aNum} Adults · ${kNum} Kids · 💳 ${pNum} Matmid`;
    }
  }

  function syncHouseholdMatmidBalance(readFromDomInput) {
    const matmidInput = document.getElementById('prof-matmid-points');
    let matmidTotal = 0;
    if (readFromDomInput && matmidInput) {
      matmidTotal = Math.max(0, Math.round(Number(matmidInput.value || 0)));
      if (state.profile) {
        state.profile.matmid_points_balance = matmidTotal;
        state.profile.passenger_loyalty_wallets = [];
      }
    } else if (state.profile) {
      matmidTotal = Math.max(0, Math.round(Number(state.profile.matmid_points_balance || 0)));
      state.profile.matmid_points_balance = matmidTotal;
      state.profile.passenger_loyalty_wallets = [];
      if (matmidInput) {
        matmidInput.value = String(matmidTotal);
      }
    } else if (matmidInput) {
      matmidTotal = Math.max(0, Math.round(Number(matmidInput.value || 0)));
    }

    syncHouseholdDisplaySummary(matmidTotal);
    return matmidTotal;
  }

  function syncProfileStateFromDom() {
    if (!state.profile) {
      state.profile = createCleanGuestProfile();
    }
    const adultsEl = document.getElementById('prof-adults-count');
    if (adultsEl && adultsEl.value !== '') {
      state.profile.adults_count = Number(adultsEl.value);
    }
    syncHouseholdMatmidBalance(true);
    state.profile.passenger_loyalty_wallets = [];

    document.querySelectorAll('[data-child-age]').forEach((ageEl) => {
      const idx = Number(ageEl.getAttribute('data-child-age'));
      if (state.profile.children && state.profile.children[idx] && ageEl.value !== '') {
        const ageNum = Number(ageEl.value);
        state.profile.children[idx].child_age_years = ageNum;
      }
    });
    document.querySelectorAll('[data-child-fw]').forEach((fwEl) => {
      const idx = Number(fwEl.getAttribute('data-child-fw'));
      if (state.profile.children && state.profile.children[idx]) {
        const val = fwEl.value;
        state.profile.children[idx].framework_type = val === '' ? null : val;
      }
    });
    (state.profile.children || []).forEach((ch) => {
      const ageNum = Number(ch.child_age_years ?? 6);
      ch.child_name = 'ילד/ה';
      ch.birth_date = null;
      if (ageNum < 2) {
        if (ch.passenger_Current_type !== 'INFANT_SEAT') ch.passenger_Current_type = 'INFANT_LAP';
      } else if (ageNum <= 11) {
        ch.passenger_Current_type = 'CHILD';
      } else {
        ch.passenger_Current_type = 'YOUTH';
      }
    });
  }

  function formatAdminIsraelDateTime(isoUtcStr, shortMode) {
    if (!isoUtcStr) return '';
    try {
      const dt = new Date(isoUtcStr);
      if (Number.isNaN(dt.getTime())) return String(isoUtcStr);
      const parts = {};
      new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Jerusalem',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      })
        .formatToParts(dt)
        .forEach((p) => {
          parts[p.type] = p.value;
        });
      const hh = parts.hour === '24' ? '00' : parts.hour;
      if (shortMode) {
        return `${parts.day}/${parts.month} · ${hh}:${parts.minute}`;
      }
      return `${parts.day}/${parts.month}/${parts.year} · ${hh}:${parts.minute}`;
    } catch (_err) {
      return String(isoUtcStr).slice(0, 16).replace('T', ' ');
    }
  }

  function formatAdminSyncAge(ageHours, isHe) {
    if (ageHours === null || ageHours === undefined || !Number.isFinite(Number(ageHours))) {
      return isHe ? 'ללא נתונים' : 'no data';
    }
    const h = Math.max(0, Number(ageHours));
    if (h < 1) {
      return isHe ? 'לפני פחות משעה' : '<1h ago';
    }
    if (h < 48) {
      const roundedH = Math.round(h * 10) / 10;
      return isHe ? `לפני ${roundedH} שעות` : `${roundedH}h ago`;
    }
    const days = Math.round((h / 24) * 10) / 10;
    return isHe ? `לפני ${days} ימים` : `${days}d ago`;
  }

  const ADMIN_MONTH_SHORT_HE = [
    '',
    'ינו׳',
    'פבר׳',
    'מרץ',
    'אפר׳',
    'מאי',
    'יונ׳',
    'יול׳',
    'אוג׳',
    'ספט׳',
    'אוק׳',
    'נוב׳',
    'דצמ׳'
  ];

  const ADMIN_MONTH_SHORT_EN = [
    '',
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec'
  ];

  function normalizeAdminSyncPeriods(sync) {
    const rawList = Array.isArray(sync && sync.periods)
      ? sync.periods
      : Array.isArray(sync && sync.months)
        ? sync.months
        : [];
    const holidayMonths = new Map();
    if (Array.isArray(state.upcomingHolidays)) {
      state.upcomingHolidays.forEach((h) => {
        const s = String(h.start_date || '').slice(0, 7);
        const e = String(h.end_date || '').slice(0, 7);
        const nmHe = String(h.name_he || h.holiday_name_he || '').trim();
        const nmEn = String(h.name_en || h.holiday_name_en || '').trim();
        [s, e].forEach((mKey) => {
          if (mKey.length === 7) {
            if (!holidayMonths.has(mKey)) {
              holidayMonths.set(mKey, { he: [], en: [] });
            }
            const bucket = holidayMonths.get(mKey);
            if (nmHe && !bucket.he.includes(nmHe)) bucket.he.push(nmHe);
            if (nmEn && !bucket.en.includes(nmEn)) bucket.en.push(nmEn);
          }
        });
      });
    }
    return rawList.map((item, idx) => {
      const pKey = String(item.period_key || item.month_key || item.start_date || '').slice(0, 7);
      const yr = Number(item.year || (pKey.length === 7 ? pKey.slice(0, 4) : 0));
      const mo = Number(item.month || (pKey.length === 7 ? pKey.slice(5, 7) : 0));
      const rows = Math.max(0, Number(item.rows_count ?? item.flights_count ?? 0));
      const dests = Math.max(0, Number(item.destinations_count ?? item.routes_count ?? 0));
      const rawSt = String(item.status || '').toUpperCase();
      const normSt =
        rawSt === 'COVERED' || rawSt === 'FRESH'
          ? 'COVERED'
          : rawSt === 'PARTIAL' || rawSt === 'DUE' || rawSt === 'STALE'
            ? (rows > 0 ? 'PARTIAL' : 'EMPTY')
            : rows > 0
              ? 'COVERED'
              : 'EMPTY';
      const fallbackBucket = holidayMonths.get(pKey) || { he: [], en: [] };
      const holidaysHe = Array.isArray(item.holidays_he)
        ? item.holidays_he.map((x) => String(x || '').trim()).filter(Boolean)
        : fallbackBucket.he.slice();
      const holidaysEn = Array.isArray(item.holidays_en)
        ? item.holidays_en.map((x) => String(x || '').trim()).filter(Boolean)
        : fallbackBucket.en.slice();
      const hasHoliday =
        item.has_school_holiday !== undefined
          ? Boolean(item.has_school_holiday)
          : (holidaysHe.length > 0 || holidaysEn.length > 0 || holidayMonths.has(pKey));
      return {
        index: Number(item.period_index || idx + 1),
        periodKey: pKey || `P${idx + 1}`,
        year: yr,
        month: mo,
        status: normSt,
        rowsCount: rows,
        destinationsCount: dests,
        lastSyncedAtUtc: item.last_synced_at_utc || item.last_synced_at || null,
        hasHoliday,
        holidaysHe,
        holidaysEn
      };
    });
  }

  async function refreshAdminBonusSync() {
    if (!state.auth || !state.auth.authenticated || !state.auth.isAdmin) return;
    state.isAdminSyncRefreshing = true;
    renderAdminBonusSync();
    try {
      const res = await apiGet('/api/v1/admin/bonus-sync-status');
      if (res && res.admin_bonus_sync) {
        state.adminBonusSync = res.admin_bonus_sync;
      }
    } catch (err) {
      if (err && (err.status === 401 || err.status === 403)) {
        state.auth.isAdmin = false;
        state.adminBonusSync = null;
      }
    } finally {
      state.isAdminSyncRefreshing = false;
      renderAdminBonusSync();
    }
  }

  function renderAdminBonusSync() {
    const slot = document.getElementById('admin-bonus-sync-slot');
    const mini = document.getElementById('auth-admin-sync-mini');
    const isHe = state.locale === 'he';
    const isAdmin = Boolean(
      state.auth && state.auth.authenticated && state.auth.isAdmin && state.adminBonusSync
    );

    if (!isAdmin) {
      if (slot) {
        slot.innerHTML = '';
        slot.setAttribute('hidden', '');
        slot.style.display = 'none';
      }
      if (mini) {
        mini.innerHTML = '';
        mini.setAttribute('hidden', '');
        mini.style.display = 'none';
      }
      return;
    }

    const sync = state.adminBonusSync;
    const periods = normalizeAdminSyncPeriods(sync);
    const periodTotal = Number(sync.period_count || sync.total_periods_count || periods.length || 12);
    const coveredCount =
      sync.covered_periods_count !== undefined
        ? Number(sync.covered_periods_count)
        : periods.filter((p) => p.status === 'COVERED').length;
    const nonEmptyCount = periods.filter((p) => p.rowsCount > 0).length;

    const healthState = String(sync.health_state || (nonEmptyCount > 0 ? 'HEALTHY' : 'EMPTY')).toUpperCase();
    const healthLabel =
      healthState === 'HEALTHY'
        ? (isHe ? 'סנכרון תקין' : 'Sync Healthy')
        : healthState === 'PARTIAL'
          ? (isHe ? 'כיסוי חלקי' : 'Partial Coverage')
          : healthState === 'DELAYED'
            ? (isHe ? 'נדרש רענון' : 'Refresh Recommended')
            : healthState === 'STALE'
              ? (isHe ? 'נתונים מיושנים' : 'Sync Stale')
              : (isHe ? 'מאגר ריק' : 'Empty DB');

    const lastSyncIso = sync.last_synced_at_utc || sync.last_synced_at || null;
    const lastDtFull = lastSyncIso
      ? formatAdminIsraelDateTime(lastSyncIso, false)
      : (isHe ? 'טרם סונכרן' : 'Never synced');
    const lastDtShort = lastSyncIso
      ? formatAdminIsraelDateTime(lastSyncIso, true)
      : (isHe ? 'טרם סונכרן' : 'Never synced');
    const lastAgeVal = sync.last_sync_age_hours !== undefined ? sync.last_sync_age_hours : sync.age_hours;
    const lastAgeTxt = formatAdminSyncAge(lastAgeVal, isHe);
    const totalRowsFmt = Number(sync.total_active_rows ?? sync.total_rows ?? 0).toLocaleString('en-US');
    const destCnt = Number(sync.active_destinations_count ?? sync.destinations_count ?? 0);
    const horizonDays = Number(sync.horizon_days || 350);

    if (mini) {
      mini.setAttribute('data-health', healthState);
      mini.innerHTML = `
        <div class="auth-admin-mini-top">
          <span class="auth-admin-mini-title">🛡️ ${isHe ? 'סנכרון בונוס (אדמין)' : 'Award Sync (Admin)'}</span>
          <span class="auth-admin-mini-badge">${escapeHtml(healthLabel)}</span>
        </div>
        <div class="auth-admin-mini-meta">
          <span class="num" dir="ltr">${coveredCount}/${periodTotal}</span> ${isHe ? 'חודשים' : 'months'} ·
          <span class="num" dir="ltr">${escapeHtml(totalRowsFmt)}</span> ${isHe ? 'טיסות' : 'flights'} ·
          ${lastSyncIso ? `<span class="num" dir="ltr">${escapeHtml(lastDtShort)}</span>` : escapeHtml(lastDtShort)} (${escapeHtml(lastAgeTxt)})
        </div>
      `;
      mini.removeAttribute('hidden');
      mini.style.display = 'flex';
    }

    if (!slot) return;

    const maxPeriodRows = Math.max(1, ...periods.map((p) => p.rowsCount));
    const sparkHtml = periods
      .map(
        (p) =>
          `<span class="admin-horizon-pip" data-status="${escapeHtml(p.status)}"></span>`
      )
      .join('');

    const periodsHtml = periods
      .map((p) => {
        const mLabel =
          p.month >= 1 && p.month <= 12
            ? (isHe ? ADMIN_MONTH_SHORT_HE[p.month] : ADMIN_MONTH_SHORT_EN[p.month])
            : escapeHtml(p.periodKey);
        const yrShort = p.year >= 2000 ? String(p.year).slice(-2) : '';
        const fillPct =
          p.status === 'EMPTY' || p.rowsCount <= 0
            ? 0
            : Math.max(18, Math.min(100, Math.round((p.rowsCount / maxPeriodRows) * 100)));
        const rowsLabel = p.rowsCount > 0 ? p.rowsCount.toLocaleString('en-US') : '—';
        const destLabel =
          p.rowsCount > 0
            ? `<span class="num" dir="ltr">${p.destinationsCount}</span> ${isHe ? 'יעדים' : 'dest'}`
            : (isHe ? 'ללא מלאי' : 'Empty');
        const stTitle =
          p.status === 'COVERED'
            ? (isHe ? 'מכוסה' : 'Covered')
            : p.status === 'PARTIAL'
              ? (isHe ? 'כיסוי חלקי' : 'Partial')
              : (isHe ? 'ללא נתונים' : 'Empty');
        const syncShort = p.lastSyncedAtUtc ? ` · ${formatAdminIsraelDateTime(p.lastSyncedAtUtc, true)}` : '';
        const holidayNames = isHe ? p.holidaysHe : p.holidaysEn;
        const holidaySuffix = p.hasHoliday && holidayNames.length > 0 ? ` · ${holidayNames.join(', ')}` : '';
        const cellTitle = `${p.periodKey} — ${stTitle}${syncShort}${holidaySuffix}`;
        const isWpAdmin = isWorkplaceModeProfile(state.profile);
        const holidayTip = isWpAdmin
          ? (holidayNames.length > 0
              ? (isHe ? `חופשות במשק: ${holidayNames.join(' · ')}` : `Workplace holidays: ${holidayNames.join(' · ')}`)
              : (isHe ? 'חופשות במשק בחודש זה' : 'Workplace holidays in this month'))
          : (holidayNames.length > 0
              ? (isHe ? `חופשות מוסדות חינוך: ${holidayNames.join(' · ')}` : `School holidays: ${holidayNames.join(' · ')}`)
              : (isHe ? 'חופשת מוסדות חינוך בחודש זה' : 'School holiday in this month'));
        const holidayMark = p.hasHoliday
          ? `<span class="admin-period-holiday" title="${escapeHtml(holidayTip)}" aria-hidden="true">✦</span>`
          : '';
        return `
          <div class="admin-period-cell" data-admin-period="${escapeHtml(p.periodKey)}" data-status="${escapeHtml(p.status)}" title="${escapeHtml(cellTitle)}">
            <div class="admin-period-head">
              <span class="admin-period-month">${mLabel} <span class="admin-period-yr" dir="ltr">${escapeHtml(yrShort)}</span></span>
              ${holidayMark}
            </div>
            <div class="admin-period-meter" aria-hidden="true">
              <div class="admin-period-meter-fill" style="width: ${fillPct}%;"></div>
            </div>
            <div class="admin-period-foot">
              <span class="admin-period-rows" dir="ltr">${escapeHtml(rowsLabel)}</span>
              <span class="admin-period-dests">${destLabel}</span>
            </div>
          </div>`;
      })
      .join('');

    const sourceTag = isHe
      ? `🧩 תוסף כרום ידני · <span class="num" dir="ltr">${horizonDays}</span> ימים`
      : `🧩 Manual Chrome Extension · <span class="num" dir="ltr">${horizonDays}d</span>`;

    const guidanceNote =
      nonEmptyCount === periodTotal && healthState === 'HEALTHY'
        ? (isHe
            ? 'כיסוי שנתי מלא מסנכרון ידני בדפדפן מחובר לאל על (ללא משיכה מרחוק).'
            : 'Full-year coverage from manual browser-assisted EL AL extension sync.')
        : nonEmptyCount > 0
          ? (isHe
              ? `מכוסים ${coveredCount} מתוך ${periodTotal} חודשים — לרענון מלא הפעל סנכרון ידני מתוסף הכרום.`
              : `${coveredCount} of ${periodTotal} months covered — run manual Chrome extension sync to refresh.`)
          : (isHe
              ? 'לא נמצאו טיסות בונוס במסד הנתונים — הפעל סנכרון ידני מתוסף הכרום.'
              : 'No award flights in database — run manual sync from the Chrome extension.');

    slot.innerHTML = `
      <details class="admin-sync-telemetry" id="admin-bonus-sync-panel" data-health="${escapeHtml(healthState)}"${state.isAdminSyncExpanded ? ' open' : ''}>
        <summary class="admin-sync-summary">
          <div class="admin-sync-summary-main">
            <span class="admin-sync-crest">🛡️ ${isHe ? 'אדמין' : 'Admin'}</span>
            <span class="admin-sync-health-pill">● ${escapeHtml(healthLabel)}</span>
            <span class="admin-sync-stat">
              <strong>${isHe ? 'סנכרון אחרון:' : 'Last sync:'}</strong>
              ${lastSyncIso ? `<span class="admin-sync-mono" dir="ltr">${escapeHtml(lastDtFull)}</span>` : escapeHtml(lastDtFull)}
              <span class="admin-sync-age">(${escapeHtml(lastAgeTxt)})</span>
            </span>
            <span class="admin-sync-sep" aria-hidden="true">│</span>
            <span class="admin-sync-stat">
              <span class="admin-sync-mono" dir="ltr">${escapeHtml(totalRowsFmt)}</span> ${isHe ? 'טיסות' : 'flights'} ·
              <span class="admin-sync-mono" dir="ltr">${destCnt}</span> ${isHe ? 'יעדים' : 'routes'} ·
              <span class="admin-sync-mono" dir="ltr">${coveredCount}/${periodTotal}</span> ${isHe ? 'חודשים' : 'months'}
            </span>
          </div>
          <div class="admin-sync-summary-end">
            <span class="admin-horizon-spark" aria-hidden="true">${sparkHtml}</span>
            <span class="admin-sync-chevron" aria-hidden="true">▾</span>
          </div>
        </summary>
        <div class="admin-sync-drawer">
          <div class="admin-sync-toolbar">
            <div class="admin-sync-toolbar-info">
              <span class="admin-sync-source-tag">${sourceTag}</span>
              <span class="admin-sync-mode-note">${escapeHtml(guidanceNote)}</span>
            </div>
            <button type="button" class="btn-admin-sync-refresh" id="btn-refresh-admin-sync"${state.isAdminSyncRefreshing ? ' disabled' : ''}>${state.isAdminSyncRefreshing ? (isHe ? '⏳ מרענן...' : '⏳ Refreshing...') : (isHe ? '↻ בדיקת סטטוס חיה' : '↻ Refresh Status')}</button>
          </div>
          <div class="admin-periods-grid" id="admin-periods-grid">${periodsHtml}</div>
        </div>
      </details>
    `;
    slot.removeAttribute('hidden');
    slot.style.display = 'block';

    const detailsEl = document.getElementById('admin-bonus-sync-panel');
    if (detailsEl) {
      detailsEl.addEventListener('toggle', () => {
        state.isAdminSyncExpanded = Boolean(detailsEl.open);
      });
    }
    const refreshBtn = document.getElementById('btn-refresh-admin-sync');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        refreshAdminBonusSync();
      });
    }
  }

  function renderAuthControls() {
    const isHe = state.locale === 'he';
    const isAuthed = Boolean(state.auth && state.auth.authenticated && state.auth.user);
    const userEmail = isAuthed && state.auth.user ? String(state.auth.user.email || '') : '';

    const btnHeaderAuth = document.getElementById('btn-header-auth');
    const btnHeaderAccount = document.getElementById('btn-header-account');
    const btnHeaderSignout = document.getElementById('btn-header-signout');
    if (btnHeaderAuth) {
      if (isAuthed) {
        btnHeaderAuth.setAttribute('hidden', '');
        btnHeaderAuth.style.display = 'none';
        btnHeaderAuth.setAttribute('aria-expanded', 'false');
      } else {
        btnHeaderAuth.removeAttribute('hidden');
        btnHeaderAuth.style.display = 'inline-flex';
        btnHeaderAuth.setAttribute('aria-expanded', state.isAuthPopoverOpen ? 'true' : 'false');
        const authLbl = document.getElementById('header-auth-label');
        if (authLbl) authLbl.textContent = isHe ? 'כניסה' : 'Sign in';
      }
    }
    if (btnHeaderAccount) {
      if (isAuthed) {
        btnHeaderAccount.removeAttribute('hidden');
        btnHeaderAccount.style.display = 'inline-flex';
        btnHeaderAccount.setAttribute('aria-expanded', state.isAuthPopoverOpen ? 'true' : 'false');
        const accEmailEl = document.getElementById('header-account-email');
        if (accEmailEl) accEmailEl.textContent = userEmail;
        const accShortEl = document.getElementById('header-account-short');
        if (accShortEl) accShortEl.textContent = isHe ? 'חשבון' : 'Account';
      } else {
        btnHeaderAccount.setAttribute('hidden', '');
        btnHeaderAccount.style.display = 'none';
        btnHeaderAccount.setAttribute('aria-expanded', 'false');
      }
    }
    if (btnHeaderSignout) {
      if (isAuthed) {
        btnHeaderSignout.removeAttribute('hidden');
        btnHeaderSignout.style.display = 'inline-flex';
        btnHeaderSignout.textContent = isHe ? 'התנתקות' : 'Sign out';
      } else {
        btnHeaderSignout.setAttribute('hidden', '');
        btnHeaderSignout.style.display = 'none';
      }
    }

    const authCard = document.getElementById('profile-auth-card');
    if (authCard) {
      authCard.classList.toggle('profile-auth-card-signed-in', isAuthed);
    }

    const guestPanel = document.getElementById('auth-guest-panel');
    const userPanel = document.getElementById('auth-user-panel');
    if (guestPanel) {
      if (isAuthed) {
        guestPanel.setAttribute('hidden', '');
        guestPanel.style.display = 'none';
      } else {
        guestPanel.removeAttribute('hidden');
        guestPanel.style.display = 'flex';
      }
    }
    if (userPanel) {
      if (isAuthed) {
        userPanel.removeAttribute('hidden');
        userPanel.style.display = 'flex';
      } else {
        userPanel.setAttribute('hidden', '');
        userPanel.style.display = 'none';
      }
    }

    const emailEl = document.getElementById('auth-user-email');
    if (emailEl) {
      emailEl.textContent = userEmail;
    }

    const notifCheckbox = document.getElementById('input-notifications-opt-in');
    if (notifCheckbox) {
      notifCheckbox.checked = Boolean(state.notificationsOptIn);
    }

    const confirmBar = document.getElementById('auth-delete-confirm-bar');
    if (confirmBar) {
      if (isAuthed && state.confirmingDeleteProfile) {
        confirmBar.removeAttribute('hidden');
        confirmBar.style.display = 'flex';
      } else {
        confirmBar.setAttribute('hidden', '');
        confirmBar.style.display = 'none';
      }
    }

    const statusNote = document.getElementById('auth-status-note');
    if (statusNote) {
      const msg = isHe ? state.authNoticeHe : state.authNoticeEn;
      if (!isAuthed && msg) {
        statusNote.textContent = msg;
        statusNote.removeAttribute('hidden');
        statusNote.style.display = 'block';
      } else {
        statusNote.textContent = '';
        statusNote.setAttribute('hidden', '');
        statusNote.style.display = 'none';
      }
    }

    const fbMsg = isHe ? state.saveFeedbackHe : state.saveFeedbackEn;
    ['auth-save-feedback', 'profile-save-feedback'].forEach((fbId) => {
      const feedbackEl = document.getElementById(fbId);
      if (!feedbackEl) return;
      if (isAuthed && fbMsg) {
        feedbackEl.textContent = fbMsg;
        feedbackEl.removeAttribute('hidden');
        feedbackEl.style.display = 'block';
      } else {
        feedbackEl.textContent = '';
        feedbackEl.setAttribute('hidden', '');
        feedbackEl.style.display = 'none';
      }
    });

    renderProfileSaveError();
    renderAdminBonusSync();
    syncApplyProfileButtonLabel();
  }

  function syncApplyProfileButtonLabel() {
    const btnApplyProfile = document.getElementById('btn-apply-profile-sheet');
    if (!btnApplyProfile) return;
    const isHe = state.locale === 'he';
    const isWp = isWorkplaceModeProfile(state.profile);
    const isAuthed = Boolean(state.auth && state.auth.authenticated);
    let heLbl;
    let enLbl;
    if (isAuthed) {
      heLbl = isWp ? '✓ שמור ועדכן הרכב נוסעים' : '✓ שמור ועדכן הרכב משפחה';
      enLbl = isWp ? '✓ Save & Apply Travelers' : '✓ Save & Apply Family';
    } else {
      heLbl = isWp ? '✓ עדכן הרכב נוסעים והצג חופשות' : '✓ עדכן הרכב משפחה והצג חופשות';
      enLbl = isWp ? '✓ Apply Travelers & Show Vacations' : '✓ Apply Family & Show Vacations';
    }
    btnApplyProfile.setAttribute('data-he', heLbl);
    btnApplyProfile.setAttribute('data-en', enLbl);
    btnApplyProfile.textContent = isHe ? heLbl : enLbl;
  }

  function renderProfileControls() {
    if (!state.profile) {
      state.profile = createCleanGuestProfile();
    }
    renderAuthControls();
    const isHe = state.locale === 'he';
    syncHouseholdMatmidBalance(false);
    const adultsInput = document.getElementById('prof-adults-count');
    const matmidInput = document.getElementById('prof-matmid-points');
    if (adultsInput) adultsInput.value = state.profile.adults_count;
    if (matmidInput) matmidInput.value = state.profile.matmid_points_balance;
    syncHouseholdDisplaySummary();

    const childrenContainer = document.getElementById('children-list-container');
    if (childrenContainer) {
      const isOptionalMode = state.dateSelectionMode === 'SPECIFIC_DATES';
      if (!state.profile.children || state.profile.children.length === 0) {
        const emptyHint = isHe
          ? 'ללא ילדים — פועל אוטומטית מצב חגי המשק ומיקסום אורך הטיול ביחס לימי חופש מהעבודה. לחצו "+ ילד/ה" למעבר לתכנון לפי גילאי ילדים.'
          : '0 children — automatically optimizing around Israeli workplace holidays & workday efficiency. Click "+ Add Child" to switch to family planning.';
        childrenContainer.innerHTML = `<p class="children-empty-hint">${escapeHtml(emptyHint)}</p>`;
        return;
      }
      childrenContainer.innerHTML = state.profile.children
        .map((child, idx) => {
          const fwOptions = MOE_FRAMEWORKS.map((fw) => {
            const currentFw = child.framework_type === null ? '' : String(child.framework_type || '');
            const selected = currentFw === fw.value ? 'selected' : '';
            const label = isHe ? fw.labelHe : fw.labelEn;
            return `<option value="${escapeHtml(fw.value)}" ${selected}>${escapeHtml(label)}</option>`;
          }).join('');
          return `
            <div class="compact-profile-item">
              <div class="compact-item-top">
                <span class="compact-item-title">🧒 ${escapeHtml(formatGenericChildTitle(idx))} · <span class="compact-item-sub compact-item-sub-text">${escapeHtml(classifyFareByAge(child.child_age_years))}</span></span>
                <button type="button" class="btn-secondary btn-remove-inline" data-remove-child="${idx}">${isHe ? 'הסר' : 'Remove'}</button>
              </div>
              <div class="form-grid form-grid-2">
                <div class="form-field">
                  <label>${isHe ? 'גיל (0–18):' : 'Age (0–18):'}</label>
                  <input type="number" min="0" max="18" value="${escapeHtml(child.child_age_years)}" data-child-age="${idx}" dir="ltr" />
                </div>
                <div class="form-field">
                  <label>${isHe ? 'מסגרת (' + (isOptionalMode ? 'אופציונלי / Optional' : 'משרד החינוך') + '):' : 'Framework (' + (isOptionalMode ? 'Optional' : 'MoE Calendar') + '):'}</label>
                  <select data-child-fw="${idx}">
                    ${fwOptions}
                  </select>
                </div>
              </div>
            </div>
          `;
        })
        .join('');
    }
  }

  const FRAMEWORK_SHORT_LABELS_HE = {
    DAYCARE_SUPERVISED: 'מעונות יום (0–3)',
    MUNICIPAL_GAN: 'גני ילדים',
    ELEMENTARY_1_3: 'יסודי (א׳–ג׳)',
    ELEMENTARY_4_6: 'יסודי (ד׳–ו׳)',
    MIDDLE_SCHOOL_7_9: 'חטיבת ביניים (ז׳–ט׳)',
    HIGH_SCHOOL_10_12: 'תיכון (י׳–י״ב)',
    SPECIAL_ED: 'חינוך מיוחד',
    RELIGIOUS_HAREDI: 'ממ״ד / חרדי'
  };

  const FRAMEWORK_SHORT_LABELS_EN = {
    DAYCARE_SUPERVISED: 'Daycare (0–3)',
    MUNICIPAL_GAN: 'Kindergarten',
    ELEMENTARY_1_3: 'Elementary (1–3)',
    ELEMENTARY_4_6: 'Elementary (4–6)',
    MIDDLE_SCHOOL_7_9: 'Middle School (7–9)',
    HIGH_SCHOOL_10_12: 'High School (10–12)',
    SPECIAL_ED: 'Special Ed',
    RELIGIOUS_HAREDI: 'Religious / Haredi'
  };

  function formatGroupedFrameworksLabel(frameworkCodes) {
    const isHe = state.locale === 'he';
    const labelsMap = isHe ? FRAMEWORK_SHORT_LABELS_HE : FRAMEWORK_SHORT_LABELS_EN;
    const uniqueCodes = Array.from(new Set(frameworkCodes));
    if (uniqueCodes.length >= 8) {
      return isHe ? 'כל מסגרות החינוך' : 'All Educational Frameworks';
    }
    return uniqueCodes.map((code) => labelsMap[code] || code).join(' · ');
  }

  function renderCalendarTable() {
    const tbody = document.getElementById('moe-calendar-tbody');
    const syncBadge = document.getElementById('calendar-sync-badge');
    if (!tbody) return;
    const isHe = state.locale === 'he';
    const isWp = isWorkplaceModeProfile(state.profile);
    if (!state.calendarData) {
      tbody.innerHTML = '';
      if (syncBadge) {
        if (isWp) {
          const fallbackSy = inferSchoolYearForIso(getReferenceToday());
          const wpLabel = isHe ? 'לוח חגים ומועדים במשק' : 'Statutory Workplace Calendar';
          syncBadge.innerHTML = `<span class="num" dir="ltr">${escapeHtml(fallbackSy)}</span> | ${escapeHtml(wpLabel)}`;
        } else {
          syncBadge.textContent = '';
        }
      }
      return;
    }

    if (syncBadge) {
      if (isWp) {
        const wpLabel = isHe ? 'לוח חגים ומועדים במשק' : 'Statutory Workplace Calendar';
        syncBadge.innerHTML = `<span class="num" dir="ltr">${escapeHtml(state.calendarData.school_year)}</span> | ${escapeHtml(wpLabel)}`;
      } else {
        const syncSourceLabel = state.calendarData.calendar_sync_source === 'OFFICIAL_MOE_CIRCULAR'
          ? (isHe ? 'חוזר מנכ״ל משרד החינוך' : 'Official MoE Circular')
          : state.calendarData.calendar_sync_source;
        // School year stays in the telemetry face; the worded source label renders in the body face
        syncBadge.innerHTML = `<span class="num" dir="ltr">${escapeHtml(state.calendarData.school_year)}</span> | ${escapeHtml(syncSourceLabel)}`;
      }
    }

    const windows = state.calendarData.windows || [];
    const groupedMap = new Map();

    windows.forEach((w) => {
      const resumeDate = w.resumes_on_date || w.school_resume_date || w.resume_date || w.end_date || '';
      const nitzFlag = Boolean(w.is_covered_by_nitzanim);
      const nitzStart = w.nitzanim_start_date || '';
      const nitzEnd = w.nitzanim_end_date || '';
      const groupKey = `${w.holiday_code}::${w.start_date}::${w.end_date}::${resumeDate}::${nitzFlag}::${nitzStart}::${nitzEnd}`;

      if (!groupedMap.has(groupKey)) {
        groupedMap.set(groupKey, {
          holiday_name_he: w.holiday_name_he,
          holiday_name_en: w.holiday_name_en || w.holiday_name_he,
          start_date: w.start_date,
          end_date: w.end_date,
          resume_date: resumeDate,
          total_calendar_days: w.total_calendar_days || w.calendar_days_count,
          is_covered_by_nitzanim: nitzFlag,
          nitzanim_start_date: nitzStart,
          nitzanim_end_date: nitzEnd,
          frameworks: []
        });
      }
      const group = groupedMap.get(groupKey);
      if (!group.frameworks.includes(w.framework_type)) {
        group.frameworks.push(w.framework_type);
      }
    });

    const groupedRows = Array.from(groupedMap.values());

    tbody.innerHTML = groupedRows
      .map((g) => {
        // Same wording as before; each date is an unbreakable token so the badge wraps between words, never inside a date
        const nitzBadge = g.is_covered_by_nitzanim
          ? `<span class="badge-camp">${isHe ? 'קייטנת ניצנים' : 'Nitzanim'} (<span class="cal-nowrap">${escapeHtml(g.nitzanim_start_date)}</span> ${isHe ? 'עד' : 'to'} <span class="cal-nowrap">${escapeHtml(g.nitzanim_end_date)}</span>)</span>`
          : `<span class="badge-vacation">${isHe ? 'חופשה מלאה' : 'Full Vacation'}</span>`;
        const daysCount =
          g.total_calendar_days ||
          Math.max(1, Math.round((new Date(g.end_date) - new Date(g.start_date)) / 86400000) + 1);
        const fwLabel = formatGroupedFrameworksLabel(g.frameworks);
        const holidayTitle = isHe ? g.holiday_name_he : g.holiday_name_en;
        const lblHoliday = isHe ? 'חג / חופשה' : 'Holiday';
        const lblFw = isHe ? 'מסגרת חינוכית' : 'Frameworks';
        const lblStart = isHe ? 'תחילת חופשה' : 'Starts';
        const lblEnd = isHe ? 'סיום חופשה' : 'Ends';
        const lblResume = isHe ? 'חזרה ללימודים' : 'Resumes';
        const lblDays = isHe ? 'ימים' : 'Days';
        const lblCamp = isHe ? 'קייטנת ניצנים' : 'Nitzanim';
        return `
          <tr>
            <td class="sticky-col" data-label="${escapeHtml(lblHoliday)}">${escapeHtml(holidayTitle)}</td>
            <td class="cal-cell-fw" data-label="${escapeHtml(lblFw)}"><span style="font-weight: 600; color: var(--text-primary); white-space: normal;">${escapeHtml(fwLabel)}</span></td>
            <td dir="ltr" data-label="${escapeHtml(lblStart)}">${escapeHtml(g.start_date)}</td>
            <td dir="ltr" data-label="${escapeHtml(lblEnd)}">${escapeHtml(g.end_date)}</td>
            <td dir="ltr" data-label="${escapeHtml(lblResume)}">${escapeHtml(g.resume_date)}</td>
            <td class="cal-cell-days" dir="ltr" data-label="${escapeHtml(lblDays)}">${escapeHtml(daysCount)}</td>
            <td class="cal-cell-camp" data-label="${escapeHtml(lblCamp)}">${nitzBadge}</td>
          </tr>
        `;
      })
      .join('');
  }

  function renderWorkplaceCalendarTable() {
    const tbody = document.getElementById('workplace-calendar-tbody');
    if (!tbody) return;
    const isHe = state.locale === 'he';
    const currentSy =
      (state.calendarData && state.calendarData.school_year) ||
      inferSchoolYearForIso(getReferenceToday());
    const rows =
      state.calendarData &&
      Array.isArray(state.calendarData.workplace_holidays) &&
      state.calendarData.workplace_holidays.length > 0
        ? state.calendarData.workplace_holidays
        : projectWorkplaceHolidaysClient(currentSy);

    const lblHoliday = isHe ? 'חג / מועד' : 'Holiday';
    const lblDates = isHe ? 'תאריכים' : 'Dates';
    const lblDays = isHe ? 'ימים' : 'Days';
    const lblCost = isHe ? 'חופשת עבודה' : 'Workday Cost';

    tbody.innerHTML = rows
      .map((r) => {
        const isOfficial = String(r.workplace_status || '') === 'OFFICIAL_HOLIDAY';
        const rateStr = isOfficial ? '0' : '0.5';
        const badgeCls = isOfficial ? 'badge-vacation' : 'badge-camp';
        const badgeTxt = isHe
          ? (r.status_badge_he || (isOfficial ? 'שבתון · 0 ימי חופש' : 'חול המועד · 0.5 יום'))
          : (r.status_badge_en || (isOfficial ? 'Holiday · 0d' : 'Chol HaMoed · 0.5d'));
        const startStr = String(r.start_date || '');
        const endStr = String(r.end_date || '');
        const datesHtml =
          startStr === endStr
            ? `<span class="work-cell-val"><span class="cal-nowrap">${escapeHtml(startStr)}</span></span>`
            : `<span class="work-cell-val"><span class="cal-nowrap">${escapeHtml(startStr)}</span> – <span class="cal-nowrap">${escapeHtml(endStr)}</span></span>`;
        const calDays =
          r.calendar_days || Math.max(1, diffDaysIso(startStr, endStr) + 1);
        const titleTxt = isHe ? (r.name_he || r.holiday_code) : (r.name_en || r.name_he || r.holiday_code);
        return `
          <tr data-workday-rate="${rateStr}" data-holiday-code="${escapeHtml(r.holiday_code || '')}">
            <td class="work-col-title" data-label="${escapeHtml(lblHoliday)}">${escapeHtml(titleTxt)}</td>
            <td dir="ltr" data-label="${escapeHtml(lblDates)}">${datesHtml}</td>
            <td dir="ltr" data-label="${escapeHtml(lblDays)}"><span class="work-cell-val">${escapeHtml(calDays)}</span></td>
            <td data-label="${escapeHtml(lblCost)}"><span class="${badgeCls}">${escapeHtml(badgeTxt)}</span></td>
          </tr>
        `;
      })
      .join('');

    const bridgesNoteEl = document.getElementById('workplace-calendar-bridges-note');
    if (bridgesNoteEl) {
      const isWp = isWorkplaceModeProfile(state.profile);
      if (!isWp) {
        bridgesNoteEl.hidden = true;
        bridgesNoteEl.style.display = 'none';
        bridgesNoteEl.innerHTML = '';
      } else {
        const cat = getActiveWorkplaceCatalog();
        const megaGrp = (cat.holiday_groups || []).find((g) => g.group_id === 'MEGA_BRIDGES');
        const megaList = (megaGrp && megaGrp.items) || [];
        const megaSummary = megaList
          .map((m) => `<strong>${escapeHtml(isHe ? m.name_he : m.name_en)}</strong> (${escapeHtml(m.recommended_min_nights)}–${escapeHtml(m.recommended_max_nights)} ${isHe ? 'לילות' : 'nights'})`)
          .join(' · ');
        bridgesNoteEl.innerHTML = `
          <div class="bridges-note-title">
            ${isHe ? '🌉 מגה-חופשות ואיחודי חגים בולטים:' : '🌉 Highlighted Mega-Vacations & Holiday Bridges:'}
          </div>
          <div class="bridges-note-body">${megaSummary}</div>
        `;
        bridgesNoteEl.hidden = false;
        bridgesNoteEl.style.display = 'block';
      }
    }
  }

  const GOOGLE_FLIGHTS_PLACE_NAMES = {
    TLV: 'Tel Aviv',
    ATH: 'Athens',
    LCA: 'Larnaca',
    RHO: 'Rhodes',
    PFO: 'Paphos',
    TBS: 'Tbilisi',
    ROM: 'Rome',
    FCO: 'Rome',
    MIL: 'Milan',
    MXP: 'Milan',
    VIE: 'Vienna',
    BUD: 'Budapest',
    PRG: 'Prague',
    BER: 'Berlin',
    MUC: 'Munich',
    LON: 'London',
    LHR: 'London Heathrow',
    LTN: 'London',
    PAR: 'Paris',
    CDG: 'Paris Charles de Gaulle',
    MAD: 'Madrid',
    BCN: 'Barcelona',
    AMS: 'Amsterdam',
    BKK: 'Bangkok',
    TYO: 'Tokyo Narita',
    NRT: 'Tokyo Narita',
    HKT: 'HKT',
    NYC: 'New York JFK',
    JFK: 'New York JFK',
    EWR: 'Newark',
    MIA: 'Miami',
    FLL: 'Fort Lauderdale',
    HER: 'Heraklion',
    SKG: 'Thessaloniki',
    CFU: 'Corfu',
    EFL: 'Kefalonia',
    JTR: 'Santorini',
    BUS: 'Batumi',
    TIV: 'Tivat',
    BEG: 'Belgrade',
    OTP: 'Bucharest',
    SOF: 'Sofia',
    WAW: 'Warsaw',
    KRK: 'Krakow',
    VCE: 'Venice',
    GVA: 'Geneva',
    ZRH: 'Zurich',
    FRA: 'Frankfurt am Main',
    LIS: 'Lisbon',
    OPO: 'Porto',
    NCE: 'NCE',
    LYS: 'Lyon',
    BSL: 'Basel',
    SZG: 'Salzburg',
    TIA: 'Tirana',
    NAP: 'Naples',
    VRN: 'Verona',
    JMK: 'Mykonos',
    PVK: 'Preveza',
    DBV: 'Dubrovnik',
    ZAG: 'Zagreb',
    LJU: 'Ljubljana',
    RMO: 'Chisinau',
    KIV: 'Chisinau',
    SEZ: 'Seychelles',
    DXB: 'Dubai',
    LAX: 'Los Angeles',
    BOS: 'Boston'
  };

  function resolveGoogleFlightsPlace(iataCode, fallbackCityEn) {
    const code = String(iataCode || 'TLV').trim().toUpperCase();
    if (GOOGLE_FLIGHTS_PLACE_NAMES[code]) {
      return GOOGLE_FLIGHTS_PLACE_NAMES[code];
    }
    if (fallbackCityEn) {
      const cleaned = String(fallbackCityEn).split('(')[0].trim();
      if (cleaned) return cleaned;
    }
    return code;
  }

  function resolveGoogleFlightsCabinPhrase(primaryCabin) {
    const normCabin = String(primaryCabin || 'ECONOMY').trim().toUpperCase();
    if (normCabin === 'BUSINESS') return ' business class';
    if (normCabin === 'PREMIUM') return ' premium economy';
    return '';
  }

  function resolveElAlBookingUrl(it) {
    if (!it || !it.is_elal_flight) return null;
    const serverGfUrl = String(it.elal_google_flights_url || '').trim();
    if (
      serverGfUrl.startsWith('https://www.google.com/travel/flights') &&
      !serverGfUrl.includes('nonstop+on+EL+AL') &&
      !serverGfUrl.includes('nonstop%20on%20EL%20AL')
    ) {
      return serverGfUrl;
    }

    // Client-side builder using verified Google Flights destination names
    const orig = String(it.origin_iata || 'TLV').toUpperCase();
    const dest = String(it.destination_iata || 'FCO').toUpperCase();
    const retOrig = String(it.return_origin_iata || dest).toUpperCase();
    const origPlace = resolveGoogleFlightsPlace(orig);
    const destPlace = resolveGoogleFlightsPlace(dest, it.destination_city_en);
    const depIso = String(it.departure_date || '2027-04-11');
    const retIso = String(it.return_date || '2027-04-18');
    const cabinPhrase = resolveGoogleFlightsCabinPhrase(it.primary_cabin);

    const prof = state.lastSearchProfile || state.profile || {};
    let adt = Math.max(1, Number(prof.adults_count || 2));
    let chd = 0;
    let inf = 0;
    (prof.children || []).forEach((c) => {
      const age = Number(c.child_age_years ?? 6);
      const pType = String(c.passenger_Current_type || '').toUpperCase();
      if (pType === 'INFANT_LAP' || (!pType && age < 2)) {
        inf += 1;
      } else if (age < 12 || pType === 'CHILD' || pType === 'INFANT_SEAT') {
        chd += 1;
      } else {
        adt += 1;
      }
    });
    inf = Math.min(inf, adt);

    const paxParts = [adt === 1 ? '1 adult' : `${adt} adults`];
    if (chd > 0) paxParts.push(chd === 1 ? '1 child' : `${chd} children`);
    if (inf > 0) paxParts.push(inf === 1 ? '1 infant' : `${inf} infants`);
    const paxPhrase =
      paxParts.length === 1
        ? paxParts[0]
        : paxParts.length === 2
          ? `${paxParts[0]} and ${paxParts[1]}`
          : `${paxParts[0]}, ${paxParts[1]} and ${paxParts[2]}`;

    const qStr =
      retOrig === dest
        ? `Flights to ${destPlace} from ${origPlace} on ${depIso} through ${retIso} with ${paxPhrase}${cabinPhrase} nonstop`
        : `One way flights to ${destPlace} from ${origPlace} on ${depIso} with ${paxPhrase}${cabinPhrase} nonstop`;

    const params = new URLSearchParams();
    params.set('q', qStr);
    params.set('curr', 'USD');
    params.set('gl', 'IL');
    params.set('hl', 'en');
    return `https://www.google.com/travel/flights?${params.toString()}`;
  }

  function resolveElAlSingleAdultGoogleFlightsUrl(it) {
    if (!it || !it.is_elal_flight) return null;
    const serverSingleUrl = String(it.elal_google_flights_single_adult_url || '').trim();
    if (
      serverSingleUrl.startsWith('https://www.google.com/travel/flights') &&
      !serverSingleUrl.includes('nonstop+on+EL+AL') &&
      !serverSingleUrl.includes('nonstop%20on%20EL%20AL')
    ) {
      return serverSingleUrl;
    }

    const orig = String(it.origin_iata || 'TLV').toUpperCase();
    const dest = String(it.destination_iata || 'FCO').toUpperCase();
    const retOrig = String(it.return_origin_iata || dest).toUpperCase();
    const origPlace = resolveGoogleFlightsPlace(orig);
    const destPlace = resolveGoogleFlightsPlace(dest, it.destination_city_en);
    const depIso = String(it.departure_date || '2027-04-11');
    const retIso = String(it.return_date || '2027-04-18');
    const cabinPhrase = resolveGoogleFlightsCabinPhrase(it.primary_cabin);

    const qStr =
      retOrig === dest
        ? `Flights to ${destPlace} from ${origPlace} on ${depIso} through ${retIso} with 1 adult${cabinPhrase} nonstop`
        : `One way flights to ${destPlace} from ${origPlace} on ${depIso} with 1 adult${cabinPhrase} nonstop`;

    const params = new URLSearchParams();
    params.set('q', qStr);
    params.set('curr', 'USD');
    params.set('gl', 'IL');
    params.set('hl', 'en');
    return `https://www.google.com/travel/flights?${params.toString()}`;
  }

  function formatHandoffCabinLabel(primaryCabin, isHe) {
    const code = String(primaryCabin || 'ECONOMY').trim().toUpperCase();
    if (code === 'BUSINESS') return isHe ? 'עסקים' : 'Business';
    if (code === 'PREMIUM') return isHe ? 'פרימיום' : 'Premium';
    return isHe ? 'תיירים' : 'Economy';
  }

  function renderHandoffLegCoupon(directionKey, lane, leg, fromIata, toIata, isHe) {
    const hasBonus = Boolean(lane && lane.hasBonus);
    const seatsNum = hasBonus ? Math.max(1, Number(lane.seats || 1)) : 0;
    const twoPlus = Boolean(hasBonus && lane.twoPlus);
    const eyebrowText =
      directionKey === 'outbound'
        ? (isHe ? 'הלוך' : 'Outbound')
        : (isHe ? 'חזור' : 'Return');

    let seatsHtml = '';
    if (!hasBonus) {
      seatsHtml = `<span class="handoff-leg-empty">${isHe ? 'ללא בונוס' : 'No bonus'}</span>`;
    } else if (twoPlus) {
      seatsHtml = `<span class="handoff-leg-count" dir="ltr">2+</span> <span class="handoff-leg-unit">${isHe ? 'מושבי בונוס' : 'bonus seats'}</span>`;
    } else if (seatsNum === 1) {
      seatsHtml = isHe
        ? `<span class="handoff-leg-unit">מושב בונוס</span> <span class="handoff-leg-count" dir="ltr">1</span>`
        : `<span class="handoff-leg-count" dir="ltr">1</span> <span class="handoff-leg-unit">bonus seat</span>`;
    } else {
      seatsHtml = `<span class="handoff-leg-count" dir="ltr">${seatsNum}</span> <span class="handoff-leg-unit">${isHe ? 'מושבי בונוס' : 'bonus seats'}</span>`;
    }

    const fn = leg && leg.flight_number ? String(leg.flight_number).trim() : '';
    let flightHtml = '';
    if (!hasBonus || !fn || fn === 'LY_CASH') {
      const commercialLabel = isHe ? 'טיסה מסחרית (ללא בונוס)' : 'Commercial flight (no bonus)';
      flightHtml = `<span class="handoff-leg-flight handoff-leg-flight-commercial">${escapeHtml(commercialLabel)}</span>`;
    } else {
      const depT = leg.departure_time_local ? String(leg.departure_time_local).slice(0, 5) : '';
      const arrT = leg.arrival_time_local ? String(leg.arrival_time_local).slice(0, 5) : '';
      const timeRange = depT && arrT ? `${depT}–${arrT}` : depT;
      flightHtml = timeRange
        ? `<span class="handoff-leg-flight" dir="ltr"><span class="handoff-flight-num">${escapeHtml(fn)}</span><span class="handoff-flight-sep" aria-hidden="true"> · </span><span class="handoff-flight-times">${escapeHtml(timeRange)}</span></span>`
        : `<span class="handoff-leg-flight" dir="ltr"><span class="handoff-flight-num">${escapeHtml(fn)}</span></span>`;
    }

    return `
      <div class="handoff-leg" data-handoff-leg="${directionKey}" data-has-bonus="${hasBonus ? 'true' : 'false'}">
        <div class="handoff-leg-top">
          <span class="handoff-leg-eyebrow">${escapeHtml(eyebrowText)}</span>
          <span class="handoff-leg-route" dir="ltr">${escapeHtml(fromIata)} → ${escapeHtml(toIata)}</span>
        </div>
        <div class="handoff-leg-seats" data-seats="${seatsNum}" data-two-plus="${twoPlus ? 'true' : 'false'}">
          ${seatsHtml}
        </div>
        ${flightHtml}
      </div>
    `;
  }

  function renderBookingHandoffModalContent() {
    const bodyEl = document.getElementById('booking-handoff-body');
    const ctaGroupEl = document.getElementById('booking-handoff-cta-group');
    const proposal = state.bookingHandoffProposal;
    if (!bodyEl || !ctaGroupEl || !proposal) return;

    const isHe = state.locale === 'he';
    const it = proposal.itinerary || {};
    const dirInfo = resolveBonusDirectionInfo(it);
    const cardProfile = state.lastSearchProfile || state.profile || {};
    const paxInfo = buildHouseholdPassengerSummary(cardProfile, it, isHe);
    const seatedCount = Math.max(1, Number(paxInfo.seatedCount || 1));
    const totalTravelers = Math.max(seatedCount, Number(paxInfo.totalTravelers || seatedCount));

    const orig = String(it.origin_iata || 'TLV').trim().toUpperCase();
    const dest = String(it.destination_iata || 'FCO').trim().toUpperCase();
    const retOrig = String(it.return_origin_iata || dest).trim().toUpperCase();
    const isOpenJaw = retOrig !== dest;
    const destIcon = DESTINATION_ICONS[dest] || '✈️';
    const cityTitle = isHe
      ? (it.destination_city_he || dest)
      : (it.destination_city_en || dest);
    const depIso = String(it.departure_date || '');
    const retIso = String(it.return_date || '');
    const nightsNum = Math.max(1, Number(it.trip_nights || 1));
    const nightsText = isHe
      ? (nightsNum === 1 ? 'לילה 1' : `${nightsNum} לילות`)
      : (nightsNum === 1 ? '1 night' : `${nightsNum} nights`);
    const cabinText = formatHandoffCabinLabel(it.primary_cabin, isHe);

    const routeDisplay = isOpenJaw
      ? `${orig} → ${dest} / ${retOrig} → ${orig}`
      : `${orig} ⇄ ${dest}`;
    const openJawBadgeHtml = isOpenJaw
      ? `<span class="handoff-openjaw-tag">${isHe ? 'מסלול משולב' : 'Open-jaw'}</span>`
      : '';

    const directionStatement = formatBonusDirectionStatement(dirInfo.coverage, isHe);
    const coveragePillCls =
      dirInfo.coverage === 'BOTH_DIRECTIONS'
        ? 'handoff-coverage-pill'
        : 'handoff-coverage-pill handoff-coverage-pill-partial';

    const outLeg = (it.outbound_legs && it.outbound_legs[0]) || null;
    const inLeg = (it.inbound_legs && it.inbound_legs[0]) || null;
    const outCouponHtml = renderHandoffLegCoupon('outbound', dirInfo.outbound, outLeg, orig, dest, isHe);
    const inCouponHtml = renderHandoffLegCoupon('inbound', dirInfo.inbound, inLeg, retOrig, orig, isHe);

    const hasSingleSeatBonus =
      (dirInfo.outbound.hasBonus && !dirInfo.outbound.twoPlus && dirInfo.outbound.seats === 1) ||
      (dirInfo.inbound.hasBonus && !dirInfo.inbound.twoPlus && dirInfo.inbound.seats === 1);
    const warnNeeded = seatedCount > 2 || (seatedCount >= 2 && hasSingleSeatBonus);

    let step3CalloutHtml = '';
    if (seatedCount > 2) {
      const warnText = isHe
        ? `הרכב של ${seatedCount} מושבים: חיפוש לכל הנוסעים יחד עלול להציג 0 אפשרויות בונוס כשיש רק 1–2 מושבי בונוס בטיסה. מומלץ לפתוח למבוגר 1 ולהעלות בהדרגה באל על <span class="handoff-seq-mono" dir="ltr">(1 → 2 → 3…)</span> כדי לגלות את מספר המושבים המדויק.`
        : `${seatedCount} seated travelers: searching for all passengers at once can show zero bonus options when only 1–2 bonus seats exist. Open for 1 adult first and increment gradually on EL AL <span class="handoff-seq-mono" dir="ltr">(1 → 2 → 3…)</span> to find the exact count.`;
      step3CalloutHtml = `<div class="handoff-warning-callout" data-handoff-warning="high"><span aria-hidden="true">⚠️</span> <span>${warnText}</span></div>`;
    } else if (seatedCount === 2 && hasSingleSeatBonus) {
      const warnText = isHe
        ? `מושב בונוס 1 בכיוון אחד לפחות: חיפוש ל-2 נוסעים יחד עלול להסתיר את מושב הבונוס הפנוי. מומלץ לפתוח למבוגר 1 ולבדוק זמינות <span class="handoff-seq-mono" dir="ltr">(1 → 2)</span> ישירות באל על.`
        : `Only 1 bonus seat on at least one direction: searching for 2 passengers together can hide the open bonus seat. Open for 1 adult first and check availability <span class="handoff-seq-mono" dir="ltr">(1 → 2)</span> on EL AL.`;
      step3CalloutHtml = `<div class="handoff-warning-callout" data-handoff-warning="high"><span aria-hidden="true">⚠️</span> <span>${warnText}</span></div>`;
    } else {
      const tipText = isHe
        ? 'טיפ: גם כשמופיע 2+, הזמינות החיה בהזמנה (במיוחד בסאן דור) עלולה לרדת למושב 1 — התחלה במבוגר 1 והעלאה הדרגתית באתר אל על <span class="handoff-seq-mono" dir="ltr">(1 → 2)</span> מונעת פספוס מושבי בונוס.'
        : 'Tip: Even when 2+ is shown, live booking availability (especially on Sun d\'Or) can drop to 1 seat — starting with 1 adult and incrementing on EL AL <span class="handoff-seq-mono" dir="ltr">(1 → 2)</span> avoids missing open bonus seats.';
      step3CalloutHtml = `<div class="handoff-warning-callout" data-handoff-warning="info"><span aria-hidden="true">ℹ️</span> <span>${tipText}</span></div>`;
    }

    const step1Title = isHe ? 'בחרו את טיסות אל על ב-Google Flights' : 'Pick the EL AL flights on Google Flights';
    const step1Body = isHe
      ? 'הקישור ייפתח עם היעד והתאריכים ממולאים מראש. בחרו את טיסות אל על שמופיעות למעלה והמשיכו לאתר אל על.'
      : 'Google Flights opens pre-filled with your destination and dates. Select the EL AL flights shown above and continue to EL AL\'s site.';

    const step2Title = isHe ? 'התחברו קודם לחשבון הנוסע המתמיד (Login)' : 'Sign in (Login) to your Matmid account first';
    const step2Body = isHe
      ? 'באתר אל על, מושבי הבונוס ומחירי הנקודות מוצגים רק לאחר התחברות לחשבון המתמיד.'
      : 'On EL AL\'s site, bonus ticket availability and points pricing only appear after you sign in.';

    const step3Title = isHe ? 'בדקו כמות מושבי בונוס מדויקת והזמינו' : 'Check exact bonus seat count & book';
    const step3Body = isHe
      ? 'אמתו את זמינות מושבי הבונוס העדכנית (שעלולה להיות נמוכה יותר ממחשבון אל על, במיוחד בטיסות סאן דור) והשלימו את ההזמנה ישירות באתר אל על.'
      : 'Confirm live bonus seat availability (which may be lower than EL AL\'s calculator, especially on Sun d\'Or flights) and complete your booking directly on EL AL.';

    bodyEl.innerHTML = `
      <div class="handoff-cheatsheet" id="booking-handoff-cheatsheet" data-bonus-directions="${escapeHtml(dirInfo.dirAttr)}">
        <div class="handoff-slip-head">
          <div class="handoff-slip-top">
            <div class="handoff-slip-dest">
              <span class="handoff-slip-icon" aria-hidden="true">${destIcon}</span>
              <strong class="handoff-slip-city">${escapeHtml(cityTitle)}</strong>
              ${openJawBadgeHtml}
            </div>
            <span class="handoff-slip-route" dir="ltr">${escapeHtml(routeDisplay)}</span>
          </div>
          <div class="handoff-slip-meta">
            <span class="handoff-slip-dates" dir="ltr">${escapeHtml(depIso)} → ${escapeHtml(retIso)}</span>
            <span class="handoff-slip-sep" aria-hidden="true">·</span>
            <span class="handoff-slip-nights">${escapeHtml(nightsText)}</span>
            <span class="handoff-slip-sep" aria-hidden="true">·</span>
            <span class="handoff-slip-cabin">${escapeHtml(cabinText)}</span>
            <span class="handoff-slip-sep" aria-hidden="true">·</span>
            <span class="handoff-slip-pax">${escapeHtml(paxInfo.paxSummaryText)}</span>
          </div>
        </div>
        <div class="handoff-slip-coverage">
          <span class="${coveragePillCls}">
            <span class="bonus-direction-dot" aria-hidden="true"></span>
            <span>${escapeHtml(directionStatement)}</span>
          </span>
        </div>
        <div class="handoff-legs-grid">
          ${outCouponHtml}
          ${inCouponHtml}
        </div>
      </div>

      <ol class="handoff-steps" id="booking-handoff-steps">
        <li class="handoff-step">
          <span class="handoff-step-num" dir="ltr" aria-hidden="true">1</span>
          <div class="handoff-step-content">
            <strong class="handoff-step-title">${escapeHtml(step1Title)}</strong>
            <p class="handoff-step-desc">${escapeHtml(step1Body)}</p>
          </div>
        </li>
        <li class="handoff-step">
          <span class="handoff-step-num" dir="ltr" aria-hidden="true">2</span>
          <div class="handoff-step-content">
            <strong class="handoff-step-title">${escapeHtml(step2Title)}</strong>
            <p class="handoff-step-desc">${escapeHtml(step2Body)}</p>
          </div>
        </li>
        <li class="handoff-step">
          <span class="handoff-step-num" dir="ltr" aria-hidden="true">3</span>
          <div class="handoff-step-content">
            <strong class="handoff-step-title">${escapeHtml(step3Title)}</strong>
            <p class="handoff-step-desc">${escapeHtml(step3Body)}</p>
            ${step3CalloutHtml}
          </div>
        </li>
      </ol>
    `;

    const fullPartyUrl = resolveElAlBookingUrl(it) || 'https://www.google.com/travel/flights';
    const singleAdultUrl = resolveElAlSingleAdultGoogleFlightsUrl(it) || fullPartyUrl;
    const travelersCountLabel = isHe
      ? (totalTravelers === 1 ? 'נוסע 1' : `${totalTravelers} נוסעים`)
      : (totalTravelers === 1 ? '1 traveler' : `${totalTravelers} travelers`);

    let ctaHtml = '';
    if (seatedCount <= 1) {
      const label = isHe
        ? '✈️ המשך ל-Google Flights להזמנה באל על'
        : '✈️ Continue to Google Flights for EL AL';
      ctaHtml = `
        <a class="btn-handoff-primary" id="btn-handoff-book-full" href="${escapeHtml(fullPartyUrl)}" target="_blank" rel="noopener noreferrer" data-handoff-cta="full-party" data-handoff-priority="primary">
          <span>${escapeHtml(label)}</span>
          <span dir="ltr" aria-hidden="true">↗</span>
        </a>
      `;
    } else if (warnNeeded) {
      const singleLabel = isHe
        ? '✈️ פתח למבוגר 1 ב-Google Flights (מומלץ)'
        : '✈️ Open for 1 Adult on Google Flights (Recommended)';
      const fullLabel = isHe
        ? `פתיחה לכל ההרכב (${travelersCountLabel})`
        : `Open for Full Party (${travelersCountLabel})`;
      ctaHtml = `
        <a class="btn-handoff-primary" id="btn-handoff-book-single" href="${escapeHtml(singleAdultUrl)}" target="_blank" rel="noopener noreferrer" data-handoff-cta="single-adult" data-handoff-priority="primary">
          <span>${escapeHtml(singleLabel)}</span>
          <span dir="ltr" aria-hidden="true">↗</span>
        </a>
        <a class="btn-handoff-secondary" id="btn-handoff-book-full" href="${escapeHtml(fullPartyUrl)}" target="_blank" rel="noopener noreferrer" data-handoff-cta="full-party" data-handoff-priority="secondary">
          <span>${escapeHtml(fullLabel)}</span>
          <span dir="ltr" aria-hidden="true">↗</span>
        </a>
      `;
    } else {
      const fullLabel = isHe
        ? `✈️ המשך ל-Google Flights (${travelersCountLabel})`
        : `✈️ Continue to Google Flights (${travelersCountLabel})`;
      const singleLabel = isHe
        ? 'בדיקה למבוגר 1 בלבד ב-Google Flights'
        : 'Check for 1 Adult Only on Google Flights';
      ctaHtml = `
        <a class="btn-handoff-primary" id="btn-handoff-book-full" href="${escapeHtml(fullPartyUrl)}" target="_blank" rel="noopener noreferrer" data-handoff-cta="full-party" data-handoff-priority="primary">
          <span>${escapeHtml(fullLabel)}</span>
          <span dir="ltr" aria-hidden="true">↗</span>
        </a>
        <a class="btn-handoff-secondary" id="btn-handoff-book-single" href="${escapeHtml(singleAdultUrl)}" target="_blank" rel="noopener noreferrer" data-handoff-cta="single-adult" data-handoff-priority="secondary">
          <span>${escapeHtml(singleLabel)}</span>
          <span dir="ltr" aria-hidden="true">↗</span>
        </a>
      `;
    }
    ctaGroupEl.innerHTML = ctaHtml;
  }

  function openBookingHandoffModal(proposal, opts) {
    if (!proposal) return;
    const options = opts || {};
    if (state.isSharePlanOpen) {
      closeSharePlanModal({ restoreFocus: false });
    }
    if (state.isCalendarVisible) {
      setCalendarVisibility(false, { restoreFocus: false });
    }
    if (state.isProfileSheetOpen) {
      setProfileSheetOpen(false, { restoreFocus: false });
    }
    if (state.isAuthPopoverOpen) {
      setAuthPopoverOpen(false, { restoreFocus: false });
    }
    if (state.isDestPickerOpen) {
      setDestPickerOpen(false);
    }
    clearOpenKpiTooltips();

    const wasOpen = Boolean(state.isBookingHandoffOpen);
    const pageScrollbarPx =
      typeof window !== 'undefined' && window.innerWidth >= 768
        ? (document.body.classList.contains('is-sheet-locked')
            ? bookingHandoffScrollbarPx
            : Math.max(0, window.innerWidth - document.documentElement.clientWidth))
        : 0;

    state.isBookingHandoffOpen = true;
    state.bookingHandoffProposal = proposal;
    if (!wasOpen) {
      const activeEl = document.activeElement;
      bookingHandoffOpenerEl =
        options.opener || (activeEl && activeEl !== document.body ? activeEl : null);
    }

    renderBookingHandoffModalContent();

    const suppressInput = document.getElementById('input-booking-handoff-suppress');
    if (suppressInput) {
      suppressInput.checked = isBookingHandoffSuppressed();
    }

    const backdrop = document.getElementById('booking-handoff-backdrop');
    const modal = document.getElementById('booking-handoff-modal');
    if (backdrop) {
      backdrop.removeAttribute('hidden');
      backdrop.style.display = 'block';
    }
    if (modal) {
      modal.removeAttribute('hidden');
      modal.style.display = 'flex';
      modal.classList.add('is-open');
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
    }

    BOOKING_HANDOFF_INERT_SELECTORS.forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) el.setAttribute('inert', '');
    });

    syncBodyScrollLock();
    bookingHandoffScrollbarPx = pageScrollbarPx;
    if (bookingHandoffScrollbarPx > 0) {
      const scrollbarSide =
        getComputedStyle(document.documentElement).direction === 'rtl'
          ? 'padding-inline-start'
          : 'padding-inline-end';
      document.body.style.setProperty(scrollbarSide, `${bookingHandoffScrollbarPx}px`);
    }

    const closeBtn = document.getElementById('btn-close-booking-handoff');
    if (closeBtn && options.focusContent !== false) {
      setTimeout(() => {
        if (!state.isBookingHandoffOpen) return;
        closeBtn.focus();
      }, 40);
    }
  }

  function closeBookingHandoffModal(opts) {
    const options = opts || {};
    const wasOpen = Boolean(state.isBookingHandoffOpen);
    state.isBookingHandoffOpen = false;
    state.bookingHandoffProposal = null;

    const backdrop = document.getElementById('booking-handoff-backdrop');
    const modal = document.getElementById('booking-handoff-modal');
    if (modal) {
      modal.setAttribute('hidden', '');
      modal.style.display = 'none';
      modal.classList.remove('is-open');
      modal.removeAttribute('role');
      modal.removeAttribute('aria-modal');
    }
    if (backdrop) {
      backdrop.setAttribute('hidden', '');
      backdrop.style.display = 'none';
    }

    BOOKING_HANDOFF_INERT_SELECTORS.forEach((sel) => {
      const el = document.querySelector(sel);
      if (!el) return;
      if (state.profileSheetView !== 'travelers' && !state.isCalendarVisible && !state.isSharePlanOpen) {
        el.removeAttribute('inert');
      }
    });

    if (bookingHandoffScrollbarPx > 0 && state.profileSheetView !== 'travelers' && !state.isSharePlanOpen) {
      document.body.style.removeProperty('padding-inline-start');
      document.body.style.removeProperty('padding-inline-end');
    }
    bookingHandoffScrollbarPx = 0;

    syncBodyScrollLock();

    if (wasOpen && options.restoreFocus !== false) {
      const activeEl = document.activeElement;
      const focusWasInside =
        !activeEl || activeEl === document.body || Boolean(modal && modal.contains(activeEl));
      if (focusWasInside && bookingHandoffOpenerEl && document.contains(bookingHandoffOpenerEl)) {
        bookingHandoffOpenerEl.focus();
      }
    }
    bookingHandoffOpenerEl = null;
  }

  function buildSharePlanPayload(proposal) {
    const p = proposal || {};
    const it = p.itinerary || {};
    const isHe = state.locale === 'he';
    const destName = isHe
      ? (it.destination_city_he || it.destination_city_en || it.destination_iata || '')
      : (it.destination_city_en || it.destination_city || it.destination_iata || '');
    const originIata = String(it.origin_iata || 'TLV').toUpperCase();
    const destIata = String(it.destination_iata || '').toUpperCase();
    const outLeg = Array.isArray(it.outbound_legs) && it.outbound_legs[0] ? it.outbound_legs[0] : {};
    const inLeg = Array.isArray(it.inbound_legs) && it.inbound_legs[0] ? it.inbound_legs[0] : {};
    const fmtLeg = (leg, seats, isTwoPlus) => {
      const fn = String(leg.flight_number || '').trim();
      const depT = String(leg.departure_time_local || '').trim();
      const arrT = String(leg.arrival_time_local || '').trim();
      const times = depT && arrT ? `${depT}–${arrT}` : '';
      const seatsNum = Number(seats || 0);
      let seatsTxt = '';
      if (seatsNum >= 1) {
        const sLabel = isTwoPlus && seatsNum >= 2 ? '\u20662+\u2069' : `\u2066${seatsNum}\u2069`;
        seatsTxt = isHe ? `${sLabel} מושבי בונוס` : `${sLabel} bonus seats`;
      } else {
        seatsTxt = isHe ? 'כרטיס מסחרי' : 'Commercial fare';
      }
      const codeAndTimes = [fn && fn !== 'LY_CASH' ? fn : '', times].filter(Boolean).join(' · ');
      const isolatedFlight = codeAndTimes ? `\u2066${codeAndTimes}\u2069` : '';
      return [isolatedFlight, seatsTxt].filter(Boolean).join(' · ');
    };
    const dirInfo = resolveBonusDirectionInfo(it);
    const bonusSummary =
      dirInfo.coverage === 'BOTH_DIRECTIONS'
        ? (isHe ? 'בונוס בשני הכיוונים' : 'Bonus seats in both directions')
        : dirInfo.coverage === 'OUTBOUND_ONLY'
          ? (isHe ? 'בונוס בהלוך בלבד' : 'Bonus outbound only')
          : dirInfo.coverage === 'INBOUND_ONLY'
            ? (isHe ? 'בונוס בחזור בלבד' : 'Bonus return only')
            : (isHe ? 'טיסות אל על מסחריות' : 'EL AL commercial flights');

    const rawMinPts = it.min_points_per_bonus_ticket ?? it.min_points_per_single_award_ticket ?? 0;
    const minPtsNum = Number(rawMinPts || 0);
    const rawBasis = String(it.min_points_basis || it.min_points_per_single_award_ticket_scope || 'ROUND_TRIP').trim().toUpperCase();
    const isRoundTripPts = rawBasis === 'ROUND_TRIP' || dirInfo.coverage === 'BOTH_DIRECTIONS';
    let minPointsText = '';
    if (minPtsNum > 0) {
      const fmtPts = minPtsNum.toLocaleString('en-US');
      if (isRoundTripPts) {
        minPointsText = isHe
          ? `החל מ-\u2066${fmtPts}\u2069 נק׳ לכרטיס בונוס אחד (הלוך ושוב)`
          : `From ${fmtPts} pts per bonus ticket (round trip)`;
      } else {
        minPointsText = isHe
          ? `החל מ-\u2066${fmtPts}\u2069 נק׳ לכרטיס בונוס אחד (כיוון אחד)`
          : `From ${fmtPts} pts per bonus ticket (one way)`;
      }
    }

    const activeProf = state.lastSearchProfile || state.profile;
    const isWpCard = isWorkplaceModeProfile(activeProf);
    const adultsCnt = Math.max(1, Number((activeProf && activeProf.adults_count) || 2));
    const kidsCnt = Array.isArray(activeProf && activeProf.children) ? activeProf.children.length : 0;
    const partySummary = isHe
      ? `${adultsCnt} מבוגרים${kidsCnt > 0 ? ` · ${kidsCnt} ילדים` : ' · ללא ילדים'}`
      : `${adultsCnt} Adults${kidsCnt > 0 ? ` · ${kidsCnt} Kids` : ' · No kids'}`;

    const wdCost =
      p.workplace_vacation_days_cost !== undefined && p.workplace_vacation_days_cost !== null
        ? Number(p.workplace_vacation_days_cost)
        : null;
    const wdSaved =
      p.workdays_saved_count !== undefined && p.workdays_saved_count !== null
        ? Number(p.workdays_saved_count)
        : null;
    const wdRatio =
      p.workday_efficiency_ratio !== undefined && p.workday_efficiency_ratio !== null
        ? Number(p.workday_efficiency_ratio)
        : null;
    let workdaysSummary = '';
    if (wdCost !== null && !Number.isNaN(wdCost)) {
      const costStr = Number.isInteger(wdCost) ? String(wdCost) : wdCost.toFixed(1).replace(/\.0$/, '');
      const dayUnitHe = wdCost === 1 ? 'יום חופש מהעבודה' : 'ימי חופש מהעבודה';
      const dayUnitEn = wdCost === 1 ? 'workday off' : 'workdays off';
      if (isWpCard && wdRatio !== null && wdSaved !== null) {
        const savedStr = Number.isInteger(wdSaved) ? String(wdSaved) : wdSaved.toFixed(1).replace(/\.0$/, '');
        workdaysSummary = isHe
          ? `${costStr} ${dayUnitHe} (נחסכו ${savedStr} ימים · יחס \u2066×${wdRatio.toFixed(1)}\u2069)`
          : `${costStr} ${dayUnitEn} (${savedStr} saved · ×${wdRatio.toFixed(1)} leverage)`;
      } else {
        workdaysSummary = isHe ? `${costStr} ${dayUnitHe}` : `${costStr} ${dayUnitEn}`;
      }
    }

    let schoolFitSummary = '';
    if (!isWpCard && p.vacation_window && p.vacation_window.holiday_alignment_score !== undefined) {
      const hasScore = Number(p.vacation_window.holiday_alignment_score || 0).toFixed(1);
      const missed = Number(p.vacation_window.total_school_days_missed_across_children || 0);
      schoolFitSummary = isHe
        ? `${hasScore}/100 (${missed} חיסורים)`
        : `${hasScore}/100 (${missed} missed days)`;
    }

    const wm = p.weather_metrics || {};
    const highRaw = wm.avg_day_high_c ?? wm.avg_max_temp_c ?? wm.avg_high_c;
    const lowRaw = wm.avg_night_low_c ?? wm.avg_min_temp_c ?? wm.avg_low_c;
    let climateSummary = '';
    if (highRaw !== undefined && lowRaw !== undefined) {
      const hi = Math.round(Number(highRaw));
      const lo = Math.round(Number(lowRaw));
      const wScoreRaw = p.weather_suitability_score ?? wm.overall_weather_suitability_score;
      const wScore = wScoreRaw !== undefined && wScoreRaw !== null ? Math.round(Number(wScoreRaw)) : null;
      climateSummary = isHe
        ? `\u2066${hi}°/${lo}°C\u2069${wScore !== null ? ` · אקלים \u2066${wScore}/100\u2069` : ''}`
        : `${hi}°/${lo}°C${wScore !== null ? ` · Climate ${wScore}/100` : ''}`;
    }

    const mergedRaw =
      isWpCard && Array.isArray(p.merged_holidays) && p.merged_holidays.length > 0
        ? p.merged_holidays
        : (isWpCard && it.departure_date && it.return_date
            ? detectMergedWorkplaceHolidaysClient(it.departure_date, it.return_date)
            : []);
    const mergedHolidaysText = mergedRaw
      .map((m) => (isHe ? (m.short_name_he || m.name_he) : (m.short_name_en || m.name_en)))
      .filter(Boolean)
      .join(' + ');

    const bookingUrl = resolveElAlBookingUrl(it) || '';
    const singleAdultBookingUrl = resolveElAlSingleAdultGoogleFlightsUrl(it) || '';
    const appUrl =
      typeof window !== 'undefined' &&
      window.location &&
      /^https?:\/\//i.test(String(window.location.origin || ''))
        ? window.location.origin
        : 'https://breezyflights.com';

    return {
      destination_name: destName,
      origin_iata: originIata,
      destination_iata: destIata,
      departure_date: String(it.departure_date || ''),
      return_date: String(it.return_date || ''),
      trip_nights: Number(it.trip_nights || 1),
      outbound_flight: fmtLeg(outLeg, it.outbound_bonus_seats, it.outbound_bonus_seats_is_two_plus),
      return_flight: fmtLeg(inLeg, it.inbound_bonus_seats, it.inbound_bonus_seats_is_two_plus),
      outbound_has_bonus: Number(it.outbound_bonus_seats || 0) >= 1,
      inbound_has_bonus: Number(it.inbound_bonus_seats || 0) >= 1,
      bonus_summary: bonusSummary,
      min_points_text: minPointsText,
      workdays_summary: workdaysSummary,
      school_fit_summary: schoolFitSummary,
      climate_summary: climateSummary,
      merged_holidays_text: mergedHolidaysText,
      party_summary: partySummary,
      booking_url: bookingUrl,
      single_adult_booking_url: singleAdultBookingUrl,
      app_url: appUrl
    };
  }

  function buildWhatsAppCaption(plan, personalNote, isHe) {
    const note = String(personalNote || '').trim();
    const nightsLbl = isHe ? `${plan.trip_nights} לילות` : `${plan.trip_nights} nights`;
    const parts = [];
    if (isHe) {
      parts.push(`✈️ תוכנית חופשה ב${plan.destination_name} (${plan.origin_iata} ⇄ ${plan.destination_iata}) · ${plan.departure_date}–${plan.return_date} (${nightsLbl})`);
      if (note) parts.push(`💬 ${note}`);
      parts.push('📄 מצורף קובץ ה-PDF המעוצב עם כל פרטי הטיסות ומדריך ההזמנה מ-breezyflights.');
    } else {
      parts.push(`✈️ Vacation Plan to ${plan.destination_name} (${plan.origin_iata} ⇄ ${plan.destination_iata}) · ${plan.departure_date}–${plan.return_date} (${nightsLbl})`);
      if (note) parts.push(`💬 ${note}`);
      parts.push('📄 Attached is the styled PDF brochure with full flight details & EL AL booking guide from breezyflights.');
    }
    return parts.join('\n');
  }

  function buildSinglePagePdfBytes(jpegBytes, imgW, imgH, linkRectPx, linkUrl) {
    const enc = new TextEncoder();
    const chunks = [];
    let byteLen = 0;
    const pushU8 = (u8) => {
      chunks.push(u8);
      byteLen += u8.length;
    };
    const pushStr = (s) => pushU8(enc.encode(s));

    const pageW = 595.28;
    const pageH = Math.round((imgH / imgW) * pageW * 100) / 100;
    const hasLink = Boolean(linkRectPx && linkUrl && /^https?:\/\//i.test(linkUrl));

    // PDF header + binary marker
    pushStr('%PDF-1.4\n');
    pushU8(new Uint8Array([0x25, 0xE2, 0xE3, 0xCF, 0xD3, 0x0A]));

    const offsets = [0];

    // 1: Catalog
    offsets.push(byteLen);
    pushStr('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n');

    // 2: Pages
    offsets.push(byteLen);
    pushStr('2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n');

    // 3: Page
    offsets.push(byteLen);
    const annotsClause = hasLink ? ' /Annots [6 0 R]' : '';
    pushStr(
      `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW.toFixed(2)} ${pageH.toFixed(2)}] ` +
        `/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R${annotsClause} >>\nendobj\n`
    );

    // 4: Image XObject (/DCTDecode)
    offsets.push(byteLen);
    pushStr(
      `4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${imgW} /Height ${imgH} ` +
        `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`
    );
    pushU8(jpegBytes);
    pushStr('\nendstream\nendobj\n');

    // 5: Content Stream
    const streamStr = `q\n${pageW.toFixed(2)} 0 0 ${pageH.toFixed(2)} 0 0 cm\n/Im0 Do\nQ\n`;
    const streamBytes = enc.encode(streamStr);
    offsets.push(byteLen);
    pushStr(`5 0 obj\n<< /Length ${streamBytes.length} >>\nstream\n`);
    pushU8(streamBytes);
    pushStr('endstream\nendobj\n');

    // 6: Optional clickable URI link annotation over booking CTA button
    if (hasLink) {
      const scale = pageW / imgW;
      const lx1 = (linkRectPx.x * scale).toFixed(2);
      const lx2 = ((linkRectPx.x + linkRectPx.w) * scale).toFixed(2);
      const ly2 = (pageH - linkRectPx.y * scale).toFixed(2);
      const ly1 = (pageH - (linkRectPx.y + linkRectPx.h) * scale).toFixed(2);
      const escapedUri = String(linkUrl)
        .replace(/\\/g, '\\\\')
        .replace(/\(/g, '\\(')
        .replace(/\)/g, '\\)');
      offsets.push(byteLen);
      pushStr(
        `6 0 obj\n<< /Type /Annot /Subtype /Link /Rect [${lx1} ${ly1} ${lx2} ${ly2}] ` +
          `/Border [0 0 0] /A << /S /URI /URI (${escapedUri}) >> >>\nendobj\n`
      );
    }

    const xrefOffset = byteLen;
    const objCount = offsets.length;
    pushStr(`xref\n0 ${objCount}\n`);
    pushStr('0000000000 65535 f \n');
    for (let i = 1; i < objCount; i += 1) {
      pushStr(`${String(offsets[i]).padStart(10, '0')} 00000 n \n`);
    }
    pushStr(`trailer\n<< /Size ${objCount} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`);

    const out = new Uint8Array(byteLen);
    let pos = 0;
    for (const c of chunks) {
      out.set(c, pos);
      pos += c.length;
    }
    return out;
  }

  function generateVacationPlanPdfArtifact(plan, personalNote, isHe) {
    const W = 1080;
    const outerPad = 32;
    const cardX = outerPad;
    const cardW = W - outerPad * 2;
    const pad = 34;
    const innerW = cardW - pad * 2;
    const fontFamily = "'Heebo', 'Rubik', 'Assistant', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif";

    const measureCanvas = document.createElement('canvas');
    measureCanvas.width = W;
    measureCanvas.height = 100;
    const mCtx = measureCanvas.getContext('2d');

    const wrapTextLines = (ctx, text, maxW, fontSpec) => {
      const clean = String(text || '').trim();
      if (!clean) return [];
      ctx.font = fontSpec;
      const paragraphs = clean.split(/\n+/);
      const allLines = [];
      for (const para of paragraphs) {
        const words = para.trim().split(/\s+/).filter(Boolean);
        if (words.length === 0) continue;
        let line = words[0];
        for (let i = 1; i < words.length; i += 1) {
          const candidate = `${line} ${words[i]}`;
          if (ctx.measureText(candidate).width <= maxW) {
            line = candidate;
          } else {
            allLines.push(line);
            line = words[i];
          }
        }
        allLines.push(line);
      }
      return allLines;
    };

    const noteClean = String(personalNote || '').trim();
    const noteFont = `600 20px ${fontFamily}`;
    const noteLines = noteClean ? wrapTextLines(mCtx, noteClean, innerW - 44, noteFont) : [];

    const metricCards = [];
    if (plan.party_summary) {
      metricCards.push({ icon: '👥', label: isHe ? 'הרכב נוסעים' : 'Travelers', value: plan.party_summary, tone: 'neutral' });
    }
    if (plan.workdays_summary) {
      metricCards.push({ icon: '💼', label: isHe ? 'חופשת עבודה' : 'Workdays Off', value: plan.workdays_summary, tone: 'pine' });
    }
    if (plan.school_fit_summary) {
      metricCards.push({ icon: '🏫', label: isHe ? 'התאמה לחופשת בי"ס' : 'School Fit', value: plan.school_fit_summary, tone: 'azure' });
    }
    if (plan.merged_holidays_text) {
      metricCards.push({ icon: '🌉', label: isHe ? 'חגים בחלון' : 'Holidays', value: plan.merged_holidays_text, tone: 'brass' });
    }
    if (plan.climate_summary) {
      metricCards.push({ icon: '☀️', label: isHe ? 'אקלים צפוי' : 'Climate', value: plan.climate_summary, tone: 'neutral' });
    }

    const guideSteps = isHe
      ? [
          '1. עוברים ל-Google Flights, בוחרים את טיסות אל על המוצגות מעלה וממשיכים משם לאתר אל על (elal.com).',
          '2. באתר אל על יש להתחבר קודם לחשבון המתמיד (Login) — ורק לאחר ההתחברות רואים את זמינות כרטיסי הבונוס.',
          '3. טיפ חשוב במעל 2 נוסעים: אם לא רואים בונוס, בדקו קודם עבור נוסע 1 והעלו בהדרגה (ייתכן שיש רק 1–2 כרטיסים).'
        ]
      : [
          '1. Open Google Flights, pick the EL AL flights shown above, and click through to elal.com.',
          '2. Sign in to your Matmid account on elal.com first — award seats only appear after login.',
          '3. Tip for 3+ passengers: check 1 passenger first and scale up to see exact bonus seat inventory.'
        ];
    const guideBodyFont = `500 18px ${fontFamily}`;
    const wrappedGuideSteps = guideSteps.map((s) => wrapTextLines(mCtx, s, innerW - 44, guideBodyFont));
    const guideTotalLines = wrappedGuideSteps.reduce((acc, arr) => acc + arr.length, 0);

    // Compute exact dynamic height so there is zero clipping and zero blank tail
    const headerH = 200;
    const noteBoxH = noteLines.length > 0 ? 44 + noteLines.length * 28 + 18 : 0;
    const bonusRowH = plan.min_points_text ? 92 : 52;
    const flightsBoxH = 140;
    const metricRows = Math.ceil(metricCards.length / 2);
    const metricsSectionH = metricRows > 0 ? metricRows * 96 + (metricRows - 1) * 14 + 22 : 0;
    const tearLineH = 44;
    const guideBoxH = 58 + guideTotalLines * 26 + guideSteps.length * 10 + 18;
    const ctaBoxH = plan.booking_url ? 82 : 0;
    const footerH = 62;
    const cardH =
      headerH +
      24 +
      noteBoxH +
      bonusRowH +
      flightsBoxH +
      22 +
      metricsSectionH +
      tearLineH +
      guideBoxH +
      (ctaBoxH ? 18 + ctaBoxH : 0) +
      20 +
      footerH;
    const H = cardH + outerPad * 2;

    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');

    const drawRoundedRect = (x, y, w, h, r) => {
      const rad = Math.min(r, w / 2, h / 2);
      ctx.beginPath();
      ctx.moveTo(x + rad, y);
      ctx.lineTo(x + w - rad, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + rad);
      ctx.lineTo(x + w, y + h - rad);
      ctx.quadraticCurveTo(x + w, y + h, x + w - rad, y + h);
      ctx.lineTo(x + rad, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - rad);
      ctx.lineTo(x, y + rad);
      ctx.quadraticCurveTo(x, y, x + rad, y);
      ctx.closePath();
    };

    const drawTopRoundedRect = (x, y, w, h, r) => {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + r);
      ctx.lineTo(x + w, y + h);
      ctx.lineTo(x, y + h);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
    };

    const drawBottomRoundedRect = (x, y, w, h, r) => {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + w, y);
      ctx.lineTo(x + w, y + h - r);
      ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      ctx.lineTo(x + r, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - r);
      ctx.closePath();
    };

    // 1. Outer background & main boarding-pass card
    ctx.fillStyle = '#EEF3F8';
    ctx.fillRect(0, 0, W, H);

    ctx.save();
    ctx.shadowColor = 'rgba(11, 31, 58, 0.14)';
    ctx.shadowBlur = 24;
    ctx.shadowOffsetY = 10;
    drawRoundedRect(cardX, outerPad, cardW, cardH, 26);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.restore();

    drawRoundedRect(cardX, outerPad, cardW, cardH, 26);
    ctx.strokeStyle = '#CBD5E1';
    ctx.lineWidth = 2;
    ctx.stroke();

    const startX = isHe ? cardX + cardW - pad : cardX + pad;
    const endX = isHe ? cardX + pad : cardX + cardW - pad;
    const setAlignedText = (alignStart) => {
      ctx.direction = isHe ? 'rtl' : 'ltr';
      if (alignStart) {
        ctx.textAlign = isHe ? 'right' : 'left';
      } else {
        ctx.textAlign = isHe ? 'left' : 'right';
      }
    };

    // 2. Flight-Deck Navy Header
    let y = outerPad;
    const hdrGrad = ctx.createLinearGradient(cardX, y, cardX + cardW, y + headerH);
    hdrGrad.addColorStop(0, '#0B1F3A');
    hdrGrad.addColorStop(1, '#14386B');
    drawTopRoundedRect(cardX, y, cardW, headerH, 26);
    ctx.fillStyle = hdrGrad;
    ctx.fill();

    // Subtle brass accent line under header
    ctx.fillStyle = '#F59E0B';
    ctx.fillRect(cardX, y + headerH - 5, cardW, 5);

    ctx.textBaseline = 'top';
    setAlignedText(true);
    ctx.fillStyle = '#FCD34D';
    ctx.font = `800 24px ${fontFamily}`;
    ctx.fillText('breezyflights', startX, y + 26);

    setAlignedText(false);
    ctx.fillStyle = '#CBD5E1';
    ctx.font = `600 17px ${fontFamily}`;
    ctx.fillText(
      isHe ? 'תוכנית חופשה וכרטיסי בונוס באל על' : 'EL AL Award Vacation Plan',
      endX,
      y + 30
    );

    setAlignedText(true);
    ctx.fillStyle = '#FFFFFF';
    ctx.font = `800 40px ${fontFamily}`;
    const routeHeadline = `${plan.destination_name}  ·  ${plan.origin_iata} ⇄ ${plan.destination_iata}`;
    ctx.fillText(routeHeadline, startX, y + 70);

    // Date & nights pill inside header
    const nightsLbl = isHe ? `${plan.trip_nights} לילות` : `${plan.trip_nights} nights`;
    const datePillText = `📅  ${plan.departure_date} → ${plan.return_date}  ·  ${nightsLbl}`;
    ctx.font = `700 20px ${fontFamily}`;
    const dpW = Math.min(innerW, ctx.measureText(datePillText).width + 38);
    const dpX = isHe ? startX - dpW : startX;
    const dpY = y + 132;
    drawRoundedRect(dpX, dpY, dpW, 42, 21);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.14)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(252, 211, 77, 0.55)';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = '#FFFFFF';
    ctx.fillText(datePillText, isHe ? dpX + dpW - 19 : dpX + 19, dpY + 10);

    y += headerH + 24;

    // 3. Optional Personal Note Callout
    if (noteLines.length > 0) {
      const nH = 38 + noteLines.length * 28;
      drawRoundedRect(cardX + pad, y, innerW, nH, 14);
      ctx.fillStyle = '#FFFBEB';
      ctx.fill();
      ctx.strokeStyle = '#FDE68A';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Accent bar on inline-start edge
      const barX = isHe ? cardX + pad + innerW - 6 : cardX + pad;
      ctx.fillStyle = '#D97706';
      ctx.fillRect(barX, y + 8, 6, nH - 16);

      setAlignedText(true);
      ctx.fillStyle = '#92400E';
      ctx.font = `800 17px ${fontFamily}`;
      ctx.fillText(isHe ? '💬 הערה אישית:' : '💬 Personal note:', isHe ? startX - 18 : startX + 18, y + 12);
      ctx.fillStyle = '#78350F';
      ctx.font = noteFont;
      noteLines.forEach((ln, idx) => {
        ctx.fillText(ln, isHe ? startX - 18 : startX + 18, y + 36 + idx * 28);
      });
      y += nH + 18;
    }

    // 4. Bonus status + Matmid points badges
    setAlignedText(true);
    ctx.font = `800 19px ${fontFamily}`;
    const bonusBadgeTxt = `●  ${plan.bonus_summary || (isHe ? 'טיסות אל על' : 'EL AL Flights')}`;
    const bbW = Math.min(innerW, ctx.measureText(bonusBadgeTxt).width + 34);
    const bbX = isHe ? startX - bbW : startX;
    drawRoundedRect(bbX, y, bbW, 38, 19);
    ctx.fillStyle = '#ECFDF5';
    ctx.fill();
    ctx.strokeStyle = '#86EFAC';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = '#065F46';
    ctx.fillText(bonusBadgeTxt, isHe ? bbX + bbW - 17 : bbX + 17, y + 9);

    if (plan.min_points_text) {
      y += 46;
      ctx.font = `700 18px ${fontFamily}`;
      const ptsTxt = `🎫  ${plan.min_points_text}`;
      const ptW = Math.min(innerW, ctx.measureText(ptsTxt).width + 32);
      const ptX = isHe ? startX - ptW : startX;
      drawRoundedRect(ptX, y, ptW, 36, 12);
      ctx.fillStyle = '#FFFBEB';
      ctx.fill();
      ctx.strokeStyle = '#FCD34D';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = '#92400E';
      ctx.fillText(ptsTxt, isHe ? ptX + ptW - 16 : ptX + 16, y + 8);
      y += 46;
    } else {
      y += 52;
    }

    // 5. Two-column Outbound & Return Flight Coupons
    const colGap = 18;
    const colW = (innerW - colGap) / 2;
    const drawFlightCoupon = (xPos, titleStr, detailStr, hasBonus) => {
      drawRoundedRect(xPos, y, colW, flightsBoxH, 16);
      ctx.fillStyle = hasBonus ? '#F0FDF4' : '#F8FAFC';
      ctx.fill();
      ctx.strokeStyle = hasBonus ? '#86EFAC' : '#CBD5E1';
      ctx.lineWidth = 2;
      ctx.stroke();

      const cStartX = isHe ? xPos + colW - 20 : xPos + 20;
      setAlignedText(true);
      ctx.fillStyle = hasBonus ? '#0D7A5F' : '#475569';
      ctx.font = `800 19px ${fontFamily}`;
      ctx.fillText(titleStr, cStartX, y + 18);

      const detailLines = wrapTextLines(
        ctx,
        detailStr || (isHe ? 'פרטי טיסה זמינים בקישור ההזמנה' : 'Flight details via booking link'),
        colW - 40,
        `700 20px ${fontFamily}`
      );
      ctx.fillStyle = '#0B1F3A';
      ctx.font = `700 20px ${fontFamily}`;
      detailLines.slice(0, 3).forEach((ln, idx) => {
        ctx.fillText(ln, cStartX, y + 54 + idx * 28);
      });
    };

    const outColX = isHe ? cardX + pad + colW + colGap : cardX + pad;
    const inColX = isHe ? cardX + pad : cardX + pad + colW + colGap;
    drawFlightCoupon(
      outColX,
      isHe ? `🛫 טיסת הלוך · ${plan.departure_date}` : `🛫 Outbound · ${plan.departure_date}`,
      plan.outbound_flight,
      plan.outbound_has_bonus
    );
    drawFlightCoupon(
      inColX,
      isHe ? `🛬 טיסת חזור · ${plan.return_date}` : `🛬 Return · ${plan.return_date}`,
      plan.return_flight,
      plan.inbound_has_bonus
    );
    y += flightsBoxH + 22;

    // 6. Trip Metrics 2-Column Grid
    if (metricCards.length > 0) {
      const mGap = 14;
      const mW = (innerW - mGap) / 2;
      const mH = 96;
      const toneStyles = {
        pine: { bg: '#ECFDF5', border: '#A7F3D0', label: '#0D7A5F' },
        azure: { bg: '#EFF6FF', border: '#BFDBFE', label: '#0B3B8C' },
        brass: { bg: '#FFFBEB', border: '#FDE68A', label: '#B45309' },
        neutral: { bg: '#F8FAFC', border: '#CBD5E1', label: '#475569' }
      };
      metricCards.forEach((mc, idx) => {
        const rowIdx = Math.floor(idx / 2);
        const isFirstInRow = idx % 2 === 0;
        const isLastAlone = idx === metricCards.length - 1 && isFirstInRow;
        const tileW = isLastAlone ? innerW : mW;
        const tileX = isLastAlone
          ? cardX + pad
          : isHe
            ? (isFirstInRow ? cardX + pad + mW + mGap : cardX + pad)
            : (isFirstInRow ? cardX + pad : cardX + pad + mW + mGap);
        const tileY = y + rowIdx * (mH + mGap);
        const ts = toneStyles[mc.tone] || toneStyles.neutral;

        drawRoundedRect(tileX, tileY, tileW, mH, 14);
        ctx.fillStyle = ts.bg;
        ctx.fill();
        ctx.strokeStyle = ts.border;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        const tx = isHe ? tileX + tileW - 18 : tileX + 18;
        setAlignedText(true);
        ctx.fillStyle = ts.label;
        ctx.font = `700 17px ${fontFamily}`;
        ctx.fillText(`${mc.icon} ${mc.label}`, tx, tileY + 14);

        const valLines = wrapTextLines(ctx, mc.value, tileW - 36, `700 19px ${fontFamily}`);
        ctx.fillStyle = '#0B1F3A';
        ctx.font = `700 19px ${fontFamily}`;
        valLines.slice(0, 2).forEach((ln, li) => {
          ctx.fillText(ln, tx, tileY + 44 + li * 24);
        });
      });
      y += metricsSectionH;
    }

    // 7. Perforated Boarding-Pass Tear Line + Semicircular Notches
    const tearY = y + tearLineH / 2;
    ctx.save();
    ctx.setLineDash([10, 8]);
    ctx.strokeStyle = '#CBD5E1';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cardX + 24, tearY);
    ctx.lineTo(cardX + cardW - 24, tearY);
    ctx.stroke();
    ctx.restore();

    // Side ticket notches
    for (const notchX of [cardX, cardX + cardW]) {
      ctx.beginPath();
      ctx.arc(notchX, tearY, 16, 0, Math.PI * 2);
      ctx.fillStyle = '#EEF3F8';
      ctx.fill();
      ctx.strokeStyle = '#CBD5E1';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    y += tearLineH;

    // 8. 3-Step EL AL Booking Guide Card
    drawRoundedRect(cardX + pad, y, innerW, guideBoxH, 16);
    ctx.fillStyle = '#EFF6FF';
    ctx.fill();
    ctx.strokeStyle = '#BFDBFE';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    const gBarX = isHe ? cardX + pad + innerW - 6 : cardX + pad;
    ctx.fillStyle = '#0B3B8C';
    ctx.fillRect(gBarX, y + 10, 6, guideBoxH - 20);

    const gTextX = isHe ? startX - 20 : startX + 20;
    setAlignedText(true);
    ctx.fillStyle = '#0B3B8C';
    ctx.font = `800 20px ${fontFamily}`;
    ctx.fillText(
      isHe ? 'ℹ️ מדריך הזמנה באל על — לפני שממשיכים' : 'ℹ️ EL AL Booking Guide — Before You Book',
      gTextX,
      y + 18
    );

    let gy = y + 52;
    ctx.fillStyle = '#1E293B';
    ctx.font = guideBodyFont;
    wrappedGuideSteps.forEach((stepLines) => {
      stepLines.forEach((ln) => {
        ctx.fillText(ln, gTextX, gy);
        gy += 26;
      });
      gy += 10;
    });
    y += guideBoxH;

    // 9. Clickable Navy Booking CTA Button (linked in PDF /Annot)
    let ctaRect = null;
    if (plan.booking_url) {
      y += 18;
      const ctaH = 66;
      ctaRect = { x: cardX + pad, y, w: innerW, h: ctaH };
      const ctaGrad = ctx.createLinearGradient(ctaRect.x, ctaRect.y, ctaRect.x, ctaRect.y + ctaH);
      ctaGrad.addColorStop(0, '#1347A6');
      ctaGrad.addColorStop(1, '#0B3B8C');
      drawRoundedRect(ctaRect.x, ctaRect.y, ctaRect.w, ctaH, 16);
      ctx.fillStyle = ctaGrad;
      ctx.fill();

      ctx.direction = isHe ? 'rtl' : 'ltr';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#FFFFFF';
      ctx.font = `800 22px ${fontFamily}`;
      ctx.fillText(
        isHe
          ? '✈️ לחצו כאן לבדיקת זמינות והזמנת טיסת אל על ↗'
          : '✈️ Click here to check availability & book EL AL flight ↗',
        ctaRect.x + ctaRect.w / 2,
        ctaRect.y + ctaH / 2
      );
      y += ctaBoxH;
    }

    // 10. Branded Footer
    y += 20;
    const footerY = outerPad + cardH - footerH;
    drawBottomRoundedRect(cardX, footerY, cardW, footerH, 26);
    ctx.fillStyle = '#F8FAFC';
    ctx.fill();
    ctx.strokeStyle = '#E2E8F0';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cardX, footerY);
    ctx.lineTo(cardX + cardW, footerY);
    ctx.stroke();

    ctx.direction = isHe ? 'rtl' : 'ltr';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#64748B';
    ctx.font = `600 16px ${fontFamily}`;
    ctx.fillText(
      isHe
        ? 'תוכנן באמצעות breezyflights.com  ·  אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על'
        : 'Planned with breezyflights.com  ·  Independent vacation planner not affiliated with EL AL',
      W / 2,
      footerY + footerH / 2
    );

    const dataUrl = canvas.toDataURL('image/jpeg', 0.94);
    const b64 = dataUrl.split(',')[1] || '';
    const binStr = atob(b64);
    const jpegBytes = new Uint8Array(binStr.length);
    for (let i = 0; i < binStr.length; i += 1) {
      jpegBytes[i] = binStr.charCodeAt(i);
    }

    const pdfBytes = buildSinglePagePdfBytes(jpegBytes, W, H, ctaRect, plan.booking_url);
    const safeDest = String(plan.destination_iata || 'TRIP').replace(/[^A-Z0-9_-]/gi, '');
    const safeDep = String(plan.departure_date || 'plan').replace(/[^0-9-]/g, '');
    const filename = `breezyflights_${safeDest}_${safeDep}.pdf`;
    const blob = new Blob([pdfBytes], { type: 'application/pdf' });
    let file = null;
    try {
      file = new File([blob], filename, { type: 'application/pdf' });
    } catch (_fileErr) {
      file = null;
    }
    if (typeof window !== 'undefined') {
      window.__fvpLastSharePdfMeta = {
        filename,
        size: pdfBytes.length,
        header: String.fromCharCode(...pdfBytes.slice(0, 8)),
        width: W,
        height: H
      };
      window.__fvpLastSharePdfBytes = pdfBytes;
    }
    return { file, blob, filename, pdfBytes };
  }

  function triggerPdfDownload(blob, filename) {
    if (!blob || typeof document === 'undefined' || typeof URL === 'undefined') return;
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => {
      try {
        URL.revokeObjectURL(objUrl);
      } catch (_ignore) {
        // Ignore revoke errors
      }
    }, 4000);
  }

  async function handleShareWhatsAppPdf() {
    if (!state.sharePlanProposal || state.sharePlanPdfBusy) return;
    const isHe = state.locale === 'he';
    const noteEl = document.getElementById('input-share-email-note');
    const noteVal = noteEl ? String(noteEl.value || '').trim() : state.sharePlanNoteValue;
    state.sharePlanNoteValue = noteVal;
    state.sharePlanPdfBusy = true;
    state.sharePlanPdfNoticeHe = '';
    state.sharePlanPdfNoticeEn = '';
    renderSharePlanModalContent();

    try {
      const plan = buildSharePlanPayload(state.sharePlanProposal);
      const pdfArt = generateVacationPlanPdfArtifact(plan, noteVal, isHe);
      const caption = buildWhatsAppCaption(plan, noteVal, isHe);
      const canNativeFileShare =
        Boolean(pdfArt.file) &&
        typeof navigator !== 'undefined' &&
        typeof navigator.canShare === 'function' &&
        typeof navigator.share === 'function' &&
        navigator.canShare({ files: [pdfArt.file] });

      if (canNativeFileShare) {
        try {
          await navigator.share({
            files: [pdfArt.file],
            title: isHe ? `תוכנית חופשה ב${plan.destination_name}` : `Vacation Plan to ${plan.destination_name}`,
            text: caption
          });
          state.sharePlanPdfNoticeHe = '✓ קובץ ה-PDF שותף בהצלחה!';
          state.sharePlanPdfNoticeEn = '✓ Branded PDF shared successfully!';
          return;
        } catch (shareErr) {
          if (shareErr && shareErr.name === 'AbortError') {
            return;
          }
          // Fall through to download + WhatsApp Web handoff
        }
      }

      // Desktop / fallback: download branded PDF & open WhatsApp with short intro caption
      triggerPdfDownload(pdfArt.blob, pdfArt.filename);
      const waUrl = `https://wa.me/?text=${encodeURIComponent(caption)}`;
      if (typeof window !== 'undefined' && typeof window.open === 'function') {
        window.open(waUrl, '_blank', 'noopener,noreferrer');
      }
      state.sharePlanPdfNoticeHe = `✓ קובץ ה-PDF המעוצב הורד (${pdfArt.filename}) — גררו או צרפו אותו לצ׳אט בוואטסאפ!`;
      state.sharePlanPdfNoticeEn = `✓ Branded PDF downloaded (${pdfArt.filename}) — attach or drag it into your WhatsApp chat!`;
    } finally {
      state.sharePlanPdfBusy = false;
      if (state.isSharePlanOpen) {
        renderSharePlanModalContent();
      }
    }
  }

  function handleDownloadSharePdf() {
    if (!state.sharePlanProposal || state.sharePlanPdfBusy) return;
    const isHe = state.locale === 'he';
    const noteEl = document.getElementById('input-share-email-note');
    const noteVal = noteEl ? String(noteEl.value || '').trim() : state.sharePlanNoteValue;
    state.sharePlanNoteValue = noteVal;
    const plan = buildSharePlanPayload(state.sharePlanProposal);
    const pdfArt = generateVacationPlanPdfArtifact(plan, noteVal, isHe);
    triggerPdfDownload(pdfArt.blob, pdfArt.filename);
    state.sharePlanPdfNoticeHe = `✓ קובץ ה-PDF הורד (${pdfArt.filename})`;
    state.sharePlanPdfNoticeEn = `✓ PDF downloaded (${pdfArt.filename})`;
    renderSharePlanModalContent();
  }

  function renderSharePlanModalContent() {
    const bodyEl = document.getElementById('share-plan-body');
    const eyebrowEl = document.getElementById('share-plan-eyebrow');
    const titleEl = document.getElementById('share-plan-title');
    const closeBtn = document.getElementById('btn-close-share-plan');
    if (!bodyEl || !state.sharePlanProposal) return;

    const isHe = state.locale === 'he';
    const isAuthed = Boolean(state.auth && state.auth.authenticated && state.auth.user);
    const plan = buildSharePlanPayload(state.sharePlanProposal);

    if (eyebrowEl) {
      eyebrowEl.textContent = isHe ? 'שיתוף תוכנית חופשה' : 'Share Vacation Plan';
    }
    if (titleEl) {
      titleEl.textContent = isHe
        ? `שתף את החופשה ב${plan.destination_name}`
        : `Share your ${plan.destination_name} trip`;
    }
    if (closeBtn) {
      closeBtn.setAttribute('aria-label', isHe ? 'סגירת חלון השיתוף' : 'Close share dialog');
    }

    const summaryChips = [];
    if (plan.bonus_summary) summaryChips.push(`🎫 ${plan.bonus_summary}`);
    if (plan.workdays_summary) summaryChips.push(`💼 ${plan.workdays_summary}`);
    if (plan.school_fit_summary) summaryChips.push(`🏫 ${plan.school_fit_summary}`);
    if (plan.merged_holidays_text) summaryChips.push(`🌉 ${plan.merged_holidays_text}`);
    if (plan.climate_summary) summaryChips.push(`☀️ ${plan.climate_summary}`);

    const summaryHtml = `
      <div class="share-plan-summary-card">
        <div class="share-plan-summary-head">
          <span class="share-plan-dest-title">${escapeHtml(plan.destination_name)} · <span dir="ltr">${escapeHtml(plan.origin_iata)} ⇄ ${escapeHtml(plan.destination_iata)}</span></span>
          <span class="share-plan-dates-pill"><span dir="ltr">${escapeHtml(plan.departure_date)} → ${escapeHtml(plan.return_date)}</span> · ${escapeHtml(plan.trip_nights)} ${isHe ? 'לילות' : 'nights'}</span>
        </div>
        <div class="share-plan-summary-meta">
          ${summaryChips.map((chip) => `<span class="share-plan-meta-chip">${escapeHtml(chip)}</span>`).join('')}
        </div>
      </div>
    `;

    if (!isAuthed) {
      bodyEl.innerHTML = `
        ${summaryHtml}
        <div class="share-plan-guest-gate" id="share-plan-guest-gate">
          <p class="share-plan-guest-title">
            ${isHe ? '🔒 שיתוף במייל ובוואטסאפ זמין למשתמשים מחוברים עם Google' : '🔒 Email & WhatsApp sharing is available for signed-in Google users'}
          </p>
          <p class="share-plan-guest-copy">
            ${
              isHe
                ? 'התחברו בחשבון ה-Gmail שלכם כדי לשלוח את תוכנית החופשה המלאה אוטומטית במייל או לשתף אותה בוואטסאפ בלחיצה אחת. הנתונים שהזנתם יישמרו אוטומטית.'
                : 'Sign in with your Gmail account to email this complete vacation plan automatically or share it to WhatsApp in one click. Your current inputs will be preserved.'
            }
          </p>
          <button type="button" class="btn-share-google-signin" id="btn-share-google-signin">
            <span aria-hidden="true">G</span>
            <span>${isHe ? 'התחברות עם Google כדי לשתף' : 'Sign in with Google to share'}</span>
          </button>
        </div>
      `;
      return;
    }

    const userEmail = String(state.auth.user.email || '');
    const recipientVal = state.sharePlanRecipientValue || userEmail;
    const noteVal = state.sharePlanNoteValue || '';
    const pdfNoticeText = isHe ? state.sharePlanPdfNoticeHe : state.sharePlanPdfNoticeEn;
    const pdfNoticeHtml = pdfNoticeText
      ? `<div class="share-pdf-notice" id="share-pdf-notice" role="status">${escapeHtml(pdfNoticeText)}</div>`
      : '';
    const statusText = isHe ? state.sharePlanStatusHe : state.sharePlanStatusEn;
    let statusHtml = '';
    if (statusText) {
      const statusCls = state.sharePlanStatusType === 'success' ? 'is-success' : 'is-error';
      const fallbackHtml = state.sharePlanFallbackGmailUrl
        ? `<a class="share-gmail-fallback-link" id="link-share-gmail-fallback" href="${escapeHtml(state.sharePlanFallbackGmailUrl)}" target="_blank" rel="noopener noreferrer">✉️ ${isHe ? 'פתיחה ישירה ב-Gmail Compose' : 'Open directly in Gmail Compose'} ↗</a>`
        : '';
      statusHtml = `
        <div class="share-email-status ${statusCls}" id="share-email-status" role="${state.sharePlanStatusType === 'success' ? 'status' : 'alert'}">
          <span>${escapeHtml(statusText)}</span>
          ${fallbackHtml}
        </div>
      `;
    }

    bodyEl.innerHTML = `
      <span class="share-plan-sender-badge">
        <span aria-hidden="true">✓</span>
        <span>${isHe ? 'מחובר עם Google:' : 'Signed in with Google:'} <strong dir="ltr">${escapeHtml(userEmail)}</strong></span>
      </span>
      ${summaryHtml}
      <div class="share-quick-channels">
        <button
          type="button"
          class="btn-share-whatsapp"
          id="btn-share-whatsapp"
          ${state.sharePlanPdfBusy ? 'disabled' : ''}
        >
          <span aria-hidden="true">💬</span>
          <span>${
            state.sharePlanPdfBusy
              ? (isHe ? 'יוצר PDF...' : 'Creating PDF...')
              : (isHe ? 'שתף PDF בוואטסאפ' : 'Share PDF on WhatsApp')
          }</span>
        </button>
        <button
          type="button"
          class="btn-share-copy"
          id="btn-share-download-pdf"
          ${state.sharePlanPdfBusy ? 'disabled' : ''}
        >
          <span aria-hidden="true">📄</span>
          <span>${isHe ? 'הורד PDF מעוצב' : 'Download PDF'}</span>
        </button>
      </div>
      ${pdfNoticeHtml}
      <div class="share-email-divider">${isHe ? 'או שלח אוטומטית במייל (כולל מדריך הזמנה)' : 'Or email automatically (includes booking guide)'}</div>
      <form class="share-email-form" id="share-email-form" novalidate>
        <div class="share-email-field">
          <label for="input-share-email-to">${isHe ? 'נמענים במייל (עד 3 כתובות):' : 'Email recipients (up to 3):'}</label>
          <input
            type="text"
            id="input-share-email-to"
            dir="ltr"
            value="${escapeHtml(recipientVal)}"
            placeholder="name@gmail.com"
            autocomplete="email"
          />
          <span class="share-email-hint">
            ${
              isHe
                ? 'ברירת מחדל: ה-Gmail שלך. אפשר להחליף או להוסיף כתובות (למשל של בן/בת זוג) מופרדות בפסיק.'
                : 'Defaults to your Gmail address. You can replace it or add comma-separated emails.'
            }
          </span>
        </div>
        <div class="share-email-field">
          <label for="input-share-email-note">${isHe ? 'הערה אישית (אופציונלי):' : 'Personal note (optional):'}</label>
          <textarea
            id="input-share-email-note"
            maxlength="300"
            placeholder="${isHe ? 'לדוגמה: מה דעתך על הטיול הזה?' : 'e.g., What do you think about this trip?'}"
          >${escapeHtml(noteVal)}</textarea>
        </div>
        <button type="submit" class="btn-share-send-email" id="btn-share-send-email" ${state.sharePlanEmailSending ? 'disabled' : ''}>
          <span aria-hidden="true">✉️</span>
          <span>${
            state.sharePlanEmailSending
              ? (isHe ? 'שולח מייל...' : 'Sending email...')
              : (isHe ? 'שלח תוכנית במייל' : 'Send Plan by Email')
          }</span>
        </button>
        ${statusHtml}
      </form>
    `;
  }

  function openSharePlanModal(proposal, opts) {
    if (!proposal) return;
    const options = opts || {};
    if (state.isBookingHandoffOpen) {
      closeBookingHandoffModal({ restoreFocus: false });
    }
    if (state.isCalendarVisible) {
      setCalendarVisibility(false, { restoreFocus: false });
    }
    if (state.isProfileSheetOpen) {
      setProfileSheetOpen(false, { restoreFocus: false });
    }
    if (state.isAuthPopoverOpen) {
      setAuthPopoverOpen(false, { restoreFocus: false });
    }
    if (state.isDestPickerOpen) {
      setDestPickerOpen(false);
    }
    clearOpenKpiTooltips();

    const wasOpen = Boolean(state.isSharePlanOpen);
    const pageScrollbarPx =
      typeof window !== 'undefined' && window.innerWidth >= 768
        ? (document.body.classList.contains('is-sheet-locked')
            ? sharePlanScrollbarPx
            : Math.max(0, window.innerWidth - document.documentElement.clientWidth))
        : 0;

    state.isSharePlanOpen = true;
    state.sharePlanProposal = proposal;
    state.sharePlanEmailSending = false;
    state.sharePlanStatusType = null;
    state.sharePlanStatusHe = '';
    state.sharePlanStatusEn = '';
    state.sharePlanFallbackGmailUrl = '';
    state.sharePlanPdfBusy = false;
    state.sharePlanPdfNoticeHe = '';
    state.sharePlanPdfNoticeEn = '';
    state.sharePlanCopyDone = false;
    state.sharePlanNoteValue = '';
    state.sharePlanRecipientValue =
      state.auth && state.auth.authenticated && state.auth.user && state.auth.user.email
        ? String(state.auth.user.email)
        : '';

    if (!wasOpen) {
      const activeEl = document.activeElement;
      sharePlanOpenerEl =
        options.opener || (activeEl && activeEl !== document.body ? activeEl : null);
    }

    renderSharePlanModalContent();

    const backdrop = document.getElementById('share-plan-backdrop');
    const modal = document.getElementById('share-plan-modal');
    if (backdrop) {
      backdrop.removeAttribute('hidden');
      backdrop.style.display = 'block';
    }
    if (modal) {
      modal.removeAttribute('hidden');
      modal.style.display = 'flex';
      modal.classList.add('is-open');
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
    }

    BOOKING_HANDOFF_INERT_SELECTORS.forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) el.setAttribute('inert', '');
    });

    syncBodyScrollLock();
    sharePlanScrollbarPx = pageScrollbarPx;
    if (sharePlanScrollbarPx > 0) {
      const scrollbarSide =
        getComputedStyle(document.documentElement).direction === 'rtl'
          ? 'padding-inline-start'
          : 'padding-inline-end';
      document.body.style.setProperty(scrollbarSide, `${sharePlanScrollbarPx}px`);
    }

    const closeBtn = document.getElementById('btn-close-share-plan');
    if (closeBtn && options.focusContent !== false) {
      setTimeout(() => {
        if (!state.isSharePlanOpen) return;
        closeBtn.focus();
      }, 40);
    }
  }

  function closeSharePlanModal(opts) {
    const options = opts || {};
    const wasOpen = Boolean(state.isSharePlanOpen);
    state.isSharePlanOpen = false;
    state.sharePlanProposal = null;
    state.sharePlanEmailSending = false;

    const backdrop = document.getElementById('share-plan-backdrop');
    const modal = document.getElementById('share-plan-modal');
    if (modal) {
      modal.setAttribute('hidden', '');
      modal.style.display = 'none';
      modal.classList.remove('is-open');
      modal.removeAttribute('role');
      modal.removeAttribute('aria-modal');
    }
    if (backdrop) {
      backdrop.setAttribute('hidden', '');
      backdrop.style.display = 'none';
    }

    BOOKING_HANDOFF_INERT_SELECTORS.forEach((sel) => {
      const el = document.querySelector(sel);
      if (!el) return;
      if (
        state.profileSheetView !== 'travelers' &&
        !state.isCalendarVisible &&
        !state.isBookingHandoffOpen
      ) {
        el.removeAttribute('inert');
      }
    });

    if (sharePlanScrollbarPx > 0 && state.profileSheetView !== 'travelers' && !state.isBookingHandoffOpen) {
      document.body.style.removeProperty('padding-inline-start');
      document.body.style.removeProperty('padding-inline-end');
    }
    sharePlanScrollbarPx = 0;

    syncBodyScrollLock();

    if (wasOpen && options.restoreFocus !== false) {
      const activeEl = document.activeElement;
      const focusWasInside =
        !activeEl || activeEl === document.body || Boolean(modal && modal.contains(activeEl));
      if (focusWasInside && sharePlanOpenerEl && document.contains(sharePlanOpenerEl)) {
        sharePlanOpenerEl.focus();
      }
    }
    sharePlanOpenerEl = null;
  }

  async function submitSharePlanEmail() {
    if (!state.sharePlanProposal || state.sharePlanEmailSending) return;
    if (!state.auth || !state.auth.authenticated) {
      startGoogleSignIn();
      return;
    }
    const toInput = document.getElementById('input-share-email-to');
    const noteInput = document.getElementById('input-share-email-note');
    const rawRecipients = toInput ? String(toInput.value || '').trim() : state.sharePlanRecipientValue;
    const personalNote = noteInput ? String(noteInput.value || '').trim() : state.sharePlanNoteValue;
    state.sharePlanRecipientValue = rawRecipients;
    state.sharePlanNoteValue = personalNote;
    state.sharePlanEmailSending = true;
    state.sharePlanStatusType = null;
    state.sharePlanStatusHe = '';
    state.sharePlanStatusEn = '';
    state.sharePlanFallbackGmailUrl = '';
    renderSharePlanModalContent();

    try {
      const plan = buildSharePlanPayload(state.sharePlanProposal);
      const resp = await apiSend('POST', '/api/v1/share/email', {
        recipients: rawRecipients || (state.auth.user && state.auth.user.email) || '',
        locale: state.locale,
        personal_note: personalNote,
        plan
      });
      const recipsText = Array.isArray(resp.recipients) ? resp.recipients.join(', ') : rawRecipients;
      state.sharePlanStatusType = 'success';
      state.sharePlanStatusHe = `✓ תוכנית החופשה נשלחה בהצלחה אל ${recipsText}`;
      state.sharePlanStatusEn = `✓ Vacation plan emailed successfully to ${recipsText}`;
      state.sharePlanFallbackGmailUrl = '';
    } catch (err) {
      if (err && err.status === 401) {
        await handleSignOut();
        renderSharePlanModalContent();
        return;
      }
      let payload = {};
      if (err && err.bodyText) {
        try {
          payload = JSON.parse(err.bodyText) || {};
        } catch (_parseErr) {
          payload = {};
        }
      }
      const errCode = String(payload.error || '');
      state.sharePlanStatusType = 'error';
      state.sharePlanFallbackGmailUrl = String(payload.fallback_gmail_compose_url || '');
      if (errCode === 'email_not_configured') {
        state.sharePlanStatusHe =
          'שליחת מייל אוטומטית מהשרת עדיין לא הוגדרה (נדרש SMTP). בינתיים אפשר לפתוח ישירות ב-Gmail Compose:';
        state.sharePlanStatusEn =
          'Automatic server email delivery is not configured yet (SMTP required). You can open it directly in Gmail Compose instead:';
      } else if (errCode === 'invalid_recipient' || errCode === 'too_many_recipients') {
        state.sharePlanStatusHe =
          'בדקו שכתובת המייל תקינה (עד 3 כתובות מופרדות בפסיק).';
        state.sharePlanStatusEn =
          'Please enter valid recipient email addresses (up to 3, comma-separated).';
      } else if (errCode === 'rate_limit_exceeded') {
        state.sharePlanStatusHe =
          'הגעת למגבלת שליחת המיילים השעתית. נסו שוב מאוחר יותר או שתפו בוואטסאפ.';
        state.sharePlanStatusEn =
          'Hourly email share limit reached. Please try again later or share via WhatsApp.';
      } else {
        state.sharePlanStatusHe =
          'לא ניתן היה לשלוח את המייל כרגע. ניתן לנסות שוב או לשתף דרך וואטסאפ.';
        state.sharePlanStatusEn =
          'Could not send email right now. Please retry or share via WhatsApp.';
      }
    } finally {
      state.sharePlanEmailSending = false;
      if (state.isSharePlanOpen) {
        renderSharePlanModalContent();
      }
    }
  }

  function resolveBonusDirectionInfo(itineraryObj) {
    const it = itineraryObj || {};
    const rawCov = String(it.bonus_direction_coverage || '').trim().toUpperCase();
    const hasOutRaw =
      it.outbound_bonus_seats !== null &&
      it.outbound_bonus_seats !== undefined &&
      it.outbound_bonus_seats !== '';
    const hasInRaw =
      it.inbound_bonus_seats !== null &&
      it.inbound_bonus_seats !== undefined &&
      it.inbound_bonus_seats !== '';
    const outSeatsNum = hasOutRaw ? Math.max(0, Math.round(Number(it.outbound_bonus_seats) || 0)) : 0;
    const inSeatsNum = hasInRaw ? Math.max(0, Math.round(Number(it.inbound_bonus_seats) || 0)) : 0;
    const outTwoPlus = Boolean(it.outbound_bonus_seats_is_two_plus);
    const inTwoPlus = Boolean(it.inbound_bonus_seats_is_two_plus);

    let coverage = rawCov;
    if (
      coverage !== 'BOTH_DIRECTIONS' &&
      coverage !== 'OUTBOUND_ONLY' &&
      coverage !== 'INBOUND_ONLY' &&
      coverage !== 'NONE'
    ) {
      if (hasOutRaw || hasInRaw) {
        if (outSeatsNum >= 1 && inSeatsNum >= 1) coverage = 'BOTH_DIRECTIONS';
        else if (outSeatsNum >= 1) coverage = 'OUTBOUND_ONLY';
        else if (inSeatsNum >= 1) coverage = 'INBOUND_ONLY';
        else coverage = 'NONE';
      } else {
        const outLegFn = String((it.outbound_legs && it.outbound_legs[0] && it.outbound_legs[0].flight_number) || '').trim();
        const inLegFn = String((it.inbound_legs && it.inbound_legs[0] && it.inbound_legs[0].flight_number) || '').trim();
        const fallbackOut = Boolean(it.outbound_bonus_id) && outLegFn !== 'LY_CASH';
        const fallbackIn = Boolean(it.inbound_bonus_id) && inLegFn !== 'LY_CASH';
        if (fallbackOut && fallbackIn) coverage = 'BOTH_DIRECTIONS';
        else if (fallbackOut) coverage = 'OUTBOUND_ONLY';
        else if (fallbackIn) coverage = 'INBOUND_ONLY';
        else coverage = 'NONE';
      }
    }

    if (coverage === 'NONE') {
      return {
        coverage: 'NONE',
        dirAttr: 'none',
        outbound: { hasBonus: false, seats: 0, twoPlus: false },
        inbound: { hasBonus: false, seats: 0, twoPlus: false }
      };
    }

    const outHasBonus =
      coverage === 'BOTH_DIRECTIONS' || coverage === 'OUTBOUND_ONLY'
        ? (hasOutRaw ? outSeatsNum >= 1 : true)
        : false;
    const inHasBonus =
      coverage === 'BOTH_DIRECTIONS' || coverage === 'INBOUND_ONLY'
        ? (hasInRaw ? inSeatsNum >= 1 : true)
        : false;

    if (!outHasBonus && !inHasBonus) {
      return {
        coverage: 'NONE',
        dirAttr: 'none',
        outbound: { hasBonus: false, seats: 0, twoPlus: false },
        inbound: { hasBonus: false, seats: 0, twoPlus: false }
      };
    }

    const effectiveCov =
      outHasBonus && inHasBonus
        ? 'BOTH_DIRECTIONS'
        : outHasBonus
          ? 'OUTBOUND_ONLY'
          : 'INBOUND_ONLY';
    const dirAttr =
      effectiveCov === 'BOTH_DIRECTIONS'
        ? 'both'
        : effectiveCov === 'OUTBOUND_ONLY'
          ? 'outbound'
          : 'inbound';

    return {
      coverage: effectiveCov,
      dirAttr,
      outbound: {
        hasBonus: outHasBonus,
        seats: outHasBonus ? Math.max(1, outSeatsNum) : 0,
        twoPlus: outHasBonus && outTwoPlus
      },
      inbound: {
        hasBonus: inHasBonus,
        seats: inHasBonus ? Math.max(1, inSeatsNum) : 0,
        twoPlus: inHasBonus && inTwoPlus
      }
    };
  }

  function getRenderableBonusProposals(proposalsList) {
    if (!Array.isArray(proposalsList)) return [];
    return proposalsList.filter((p) => {
      const info = resolveBonusDirectionInfo(p && p.itinerary);
      return info.coverage !== 'NONE';
    });
  }

  function formatBonusDirectionStatement(coverage, isHe) {
    if (coverage === 'BOTH_DIRECTIONS') {
      return isHe ? 'בונוס בשני הכיוונים' : 'Bonus seats in both directions';
    }
    if (coverage === 'OUTBOUND_ONLY') {
      return isHe ? 'בונוס בכיוון אחד בלבד — הלוך' : 'Bonus seats one way only — outbound';
    }
    if (coverage === 'INBOUND_ONLY') {
      return isHe ? 'בונוס בכיוון אחד בלבד — חזור' : 'Bonus seats one way only — return';
    }
    return isHe ? 'אין מושבי בונוס בתאריכים האלה' : 'No bonus seats on these dates';
  }

  function renderBonusCouponLane(directionKey, lane, leg, isHe) {
    const hasBonus = Boolean(lane && lane.hasBonus);
    const seatsNum = hasBonus ? Math.max(1, Number(lane.seats || 1)) : 0;
    const twoPlus = Boolean(hasBonus && lane.twoPlus);
    const eyebrowText =
      directionKey === 'outbound'
        ? (isHe ? 'הלוך' : 'Outbound')
        : (isHe ? 'חזור' : 'Return');

    let seatsInnerHtml = '';
    if (!hasBonus) {
      seatsInnerHtml = `<span class="bonus-lane-empty">${isHe ? 'אין בונוס' : 'No bonus seats'}</span>`;
    } else if (twoPlus) {
      seatsInnerHtml = `<span class="bonus-lane-count" dir="ltr">2+</span> <span class="bonus-lane-unit">${isHe ? 'מושבי בונוס' : 'bonus seats'}</span>`;
    } else if (seatsNum === 1) {
      seatsInnerHtml = isHe
        ? `<span class="bonus-lane-unit">מושב בונוס</span> <span class="bonus-lane-count" dir="ltr">1</span>`
        : `<span class="bonus-lane-count" dir="ltr">1</span> <span class="bonus-lane-unit">bonus seat</span>`;
    } else {
      seatsInnerHtml = `<span class="bonus-lane-count" dir="ltr">${seatsNum}</span> <span class="bonus-lane-unit">${isHe ? 'מושבי בונוס' : 'bonus seats'}</span>`;
    }

    const fn = leg && leg.flight_number ? String(leg.flight_number).trim() : '';
    let flightTagHtml = '';
    if (!hasBonus || !fn || fn === 'LY_CASH') {
      const commercialLabel = isHe ? 'טיסה מסחרית (אין בונוס)' : 'Commercial flight (no bonus)';
      flightTagHtml = `<span class="bonus-lane-flight bonus-lane-flight-commercial">${escapeHtml(commercialLabel)}</span>`;
    } else {
      const depT = leg.departure_time_local ? String(leg.departure_time_local).slice(0, 5) : '';
      const arrT = leg.arrival_time_local ? String(leg.arrival_time_local).slice(0, 5) : '';
      const timeRange = depT && arrT ? `${depT}–${arrT}` : depT;
      flightTagHtml = timeRange
        ? `<span class="bonus-lane-flight" dir="ltr"><span class="bonus-flight-num">${escapeHtml(fn)}</span><span class="bonus-flight-sep" aria-hidden="true"> · </span><span class="bonus-flight-times">${escapeHtml(timeRange)}</span></span>`
        : `<span class="bonus-lane-flight" dir="ltr"><span class="bonus-flight-num">${escapeHtml(fn)}</span></span>`;
    }

    return `
      <div class="bonus-lane" data-direction="${directionKey}" data-has-bonus="${hasBonus ? 'true' : 'false'}">
        <span class="bonus-lane-eyebrow">${escapeHtml(eyebrowText)}</span>
        <div class="bonus-lane-seats" data-seats="${seatsNum}" data-two-plus="${twoPlus ? 'true' : 'false'}">
          ${seatsInnerHtml}
        </div>
        ${flightTagHtml}
      </div>
    `;
  }

  function updateZoneResultsTitle() {
    const zResults = document.getElementById('zone-results-title');
    if (!zResults) return;
    const isHe = state.locale === 'he';
    const count = getRenderableBonusProposals(state.proposals).length;
    const countSuffix = count > 0 ? ` (${count})` : '';
    zResults.textContent = isHe
      ? `תוצאות חיפוש, דירוג חופשות וניצול כרטיסי בונוס${countSuffix}`
      : `Ranked Vacation Proposals & Award Fulfillment${countSuffix}`;
  }

  function pickCompactWeatherIcon(wm) {
    if (!wm) return '🌤️';
    const snowIdx = Number(wm.snow_reliability_index || 0);
    const highC = Number(wm.avg_day_high_c ?? wm.avg_max_temp_c ?? 0);
    const rainD = Number(wm.estimated_rain_days_in_trip ?? wm.expected_rain_days_in_trip ?? 0);
    const sunH = Number(wm.sunshine_hours_per_day || 0);
    if (snowIdx >= 0.45 || highC <= 3) return '❄️';
    if (rainD >= 3.0) return '🌧️';
    if (sunH >= 7.5 && rainD <= 1.2) return '☀️';
    return '🌤️';
  }

  const WEATHER_STYLE_ACTIVITIES_FALLBACK_HE = {
    BEACH_AND_POOL: 'רחצה בחופים מוגנים, בריכות, טיילת חוף ושייט משפחתי רגוע',
    NATURE_TRIP: 'מסלולי הליכה קלים למשפחות, תצפיות פנורמיות ושמורות טבע',
    URBAN_CULTURE: 'שיטוט בעיר העתיקה, מוזיאונים לכל המשפחה, שווקים ובתי קפה',
    FAMILY_ATTRACTIONS_PARKS: 'אקווריומים, מוזיאוני מדע, פארקי חוויה ואטרקציות אינטראקטיביות לילדים',
    SNOW_AND_SKI: 'מדרונות גלישה לכל הרמות, מזחלות שלג, רכבלים ועיירות אלפיניות',
    WINTER_FESTIVE: 'דוכני חורף מוארים, החלקה על הקרח, מדרחובים חגיגיים ומוזיאונים חמימים'
  };

  const WEATHER_STYLE_ACTIVITIES_FALLBACK_EN = {
    BEACH_AND_POOL: 'family beaches, resort pools, waterfront promenades, and calm boat outings',
    NATURE_TRIP: 'scenic family trails, panoramic viewpoints, national parks, and nature reserves',
    URBAN_CULTURE: 'historic old-town walks, interactive museums, local markets, and neighborhood cafes',
    FAMILY_ATTRACTIONS_PARKS: 'theme parks, science museums, zoos, aquariums, and hands-on family attractions',
    SNOW_AND_SKI: 'family ski slopes, snow tubing, alpine cable cars, and cozy mountain villages',
    WINTER_FESTIVE: 'illuminated winter markets, outdoor ice rinks, festive plazas, and warm indoor museums'
  };

  const WEATHER_STYLE_ACTIVITIES_FALLBACK_WORKPLACE_HE = {
    BEACH_AND_POOL: 'רחצה בחופים, בריכות, טיילת חוף ושייט רגוע',
    NATURE_TRIP: 'מסלולי הליכה, תצפיות פנורמיות ושמורות טבע',
    URBAN_CULTURE: 'שיטוט בעיר העתיקה, מוזיאונים, שווקים ובתי קפה',
    FAMILY_ATTRACTIONS_PARKS: 'פארקי חוויה, אקווריומים, מוזיאוני מדע ואטרקציות מובילות',
    SNOW_AND_SKI: 'מדרונות גלישה לכל הרמות, רכבלים ועיירות אלפיניות',
    WINTER_FESTIVE: 'דוכני חורף מוארים, החלקה על הקרח, מדרחובים חגיגיים ומוזיאונים חמימים'
  };

  const WEATHER_STYLE_ACTIVITIES_FALLBACK_WORKPLACE_EN = {
    BEACH_AND_POOL: 'beaches, resort pools, waterfront promenades, and boat outings',
    NATURE_TRIP: 'scenic trails, panoramic viewpoints, national parks, and nature reserves',
    URBAN_CULTURE: 'historic old-town walks, museums, local markets, and neighborhood cafes',
    FAMILY_ATTRACTIONS_PARKS: 'theme parks, science museums, aquariums, and headline attractions',
    SNOW_AND_SKI: 'ski slopes, alpine cable cars, and cozy mountain villages',
    WINTER_FESTIVE: 'illuminated winter markets, outdoor ice rinks, festive plazas, and warm indoor museums'
  };

  function renderWeatherTooltipHtml(tooltipId, wm, cityTitle, wssVal, isHe, isWorkplaceMode) {
    const highC = Number(wm.avg_day_high_c ?? wm.avg_max_temp_c ?? 0).toFixed(1);
    const lowC = Number(wm.avg_night_low_c ?? wm.avg_min_temp_c ?? 0).toFixed(1);
    const sunH = Number(wm.sunshine_hours_per_day || 0).toFixed(1);
    const rainD = Number(wm.estimated_rain_days_in_trip ?? wm.expected_rain_days_in_trip ?? 0).toFixed(1);
    const hasSea = wm.sea_water_temp_c !== null && wm.sea_water_temp_c !== undefined;
    const seaC = hasSea ? Number(wm.sea_water_temp_c).toFixed(1) : null;
    const recList = Array.isArray(wm.recommended_vacation_types) ? wm.recommended_vacation_types : [];
    const primaryStyle = String(recList[0] || wm.best_matching_vacation_type || 'URBAN_CULTURE').toUpperCase();

    const summaryText = isHe
      ? (wm.weather_summary_he ||
          `מזג אוויר צפוי: ${highC}°C ביום / ${lowC}°C בלילה${seaC ? `, טמפ׳ ים ${seaC}°C` : ''}, כ-${sunH} שעות שמש ביום וכ-${rainD} ימי גשם משוערים בטיול (${wssVal.toFixed(0)}/100).`)
      : (wm.weather_summary_en ||
          `Expected weather: ${highC}°C day / ${lowC}°C night${seaC ? `, sea ${seaC}°C` : ''}, about ${sunH}h daily sunshine and about ${rainD} expected rain days (${wssVal.toFixed(0)}/100).`);

    const fallbackMapHe = isWorkplaceMode
      ? WEATHER_STYLE_ACTIVITIES_FALLBACK_WORKPLACE_HE
      : WEATHER_STYLE_ACTIVITIES_FALLBACK_HE;
    const fallbackMapEn = isWorkplaceMode
      ? WEATHER_STYLE_ACTIVITIES_FALLBACK_WORKPLACE_EN
      : WEATHER_STYLE_ACTIVITIES_FALLBACK_EN;
    const fallbackDefaultEn = isWorkplaceMode
      ? 'local sights and outings'
      : 'local sights and family outings';

    const fallbackStyles = recList.length > 0 ? recList.slice(0, 2) : [primaryStyle];
    const fallbackRecText = isHe
      ? fallbackStyles
          .map((vt) => {
            const code = String(vt || '').toUpperCase();
            const lbl = formatVacationTypeBadge(code);
            const idea = fallbackMapHe[code] || '';
            return idea ? `${lbl} — ${idea}` : lbl;
          })
          .join(' · ')
      : `In ${cityTitle}: ` +
        fallbackStyles
          .map((vt) => {
            const code = String(vt || '').toUpperCase();
            const lbl = formatVacationTypeBadge(code);
            const idea = fallbackMapEn[code] || fallbackDefaultEn;
            return `${lbl} (${idea})`;
          })
          .join(' · ') +
        '.';

    const activityText = isHe
      ? (wm.activity_recommendations_he || fallbackRecText)
      : (wm.activity_recommendations_en || fallbackRecText);

    const titleText = isHe
      ? `🌤️ מזג אוויר ומה לעשות ב${cityTitle}`
      : `🌤️ Weather & What to Do in ${cityTitle}`;
    const forecastKicker = isHe ? 'תחזית עונתית:' : 'Seasonal forecast:';
    const activitiesKicker = isHe ? 'מומלץ ביעד במזג אוויר זה:' : 'What to do in this weather:';
    const stylePillsHtml =
      recList.length > 0
        ? `<div class="kpi-tooltip-pills">${recList
            .slice(0, 3)
            .map((vt) => `<span class="kpi-tooltip-pill">${escapeHtml(formatVacationTypeBadge(vt))}</span>`)
            .join('')}</div>`
        : '';

    return `
      <div class="kpi-tooltip weather-tooltip" id="${escapeHtml(tooltipId)}" role="tooltip">
        <strong class="kpi-tooltip-title">${escapeHtml(titleText)}</strong>
        <p class="kpi-tooltip-line"><span class="kpi-tooltip-kicker">${escapeHtml(forecastKicker)}</span> ${escapeHtml(summaryText)}</p>
        <p class="kpi-tooltip-line"><span class="kpi-tooltip-kicker">${escapeHtml(activitiesKicker)}</span> ${escapeHtml(activityText)}</p>
        ${stylePillsHtml}
      </div>
    `;
  }

  function renderKpiTooltipHtml(tooltipId, titleText, calcText, meaningText, isHe) {
    const calcKicker = isHe ? 'איך חושב:' : 'How calculated:';
    const meaningKicker = isHe ? 'משמעות:' : 'Meaning:';
    return `
      <div class="kpi-tooltip" id="${escapeHtml(tooltipId)}" role="tooltip">
        <strong class="kpi-tooltip-title">${escapeHtml(titleText)}</strong>
        <p class="kpi-tooltip-line"><span class="kpi-tooltip-kicker">${escapeHtml(calcKicker)}</span> ${escapeHtml(calcText)}</p>
        <p class="kpi-tooltip-line"><span class="kpi-tooltip-kicker">${escapeHtml(meaningKicker)}</span> ${escapeHtml(meaningText)}</p>
      </div>
    `;
  }

  function buildKpiExplanations(p, it, dirInfo, seatedCount, hasVal, schoolMissed, fbvsVal, wpInfo, isHe, leverageInfo) {
    const totalDays = Math.max(1, diffDaysIso(it.departure_date, it.return_date) + 1);
    const wCost = Number((wpInfo && wpInfo.workplace_vacation_days_cost) ?? 0);
    const workdaysStr = Number.isInteger(wCost) ? String(wCost) : wCost.toFixed(1);
    const regWorkCnt = Number((wpInfo && wpInfo.regular_workdays_count) ?? 0);
    const cholWorkCnt = Number((wpInfo && wpInfo.chol_hamoed_workdays_count) ?? 0);
    const freeWorkCnt = Number((wpInfo && wpInfo.holiday_or_weekend_days_count) ?? 0);
    const isWpCard = Boolean(leverageInfo && leverageInfo.isWorkplaceCard);

    let workTitle = isHe ? 'חופשת עבודה (ימי חופש מהעבודה)' : 'Workdays Off (Per Working Traveler)';
    let workCalc = '';
    let workMeaning = '';

    if (isWpCard) {
      workTitle = isHe ? 'חופשת עבודה ויעילות ימי חופש' : 'Workdays Off & Trip Leverage';
      if (leverageInfo.isZeroWorkday) {
        workCalc = isHe
          ? `לוח עבודה ישראלי א׳–ה׳ על פני ${totalDays} ימי טיול: 0 רגילים, 0 חוה״מ, ${freeWorkCnt} סופ״ש/שבתון (0) ← 0 ימי חופש (נחסכו כל ${totalDays} הימים).`
          : `Sun–Thu Israeli workplace calendar over ${totalDays} trip days: 0 regular, 0 Chol HaMoed, ${freeWorkCnt} Fri–Sat/holiday (0) → 0 days off (all ${totalDays} days covered).`;
        workMeaning = isHe
          ? `מקסום מלא — ${totalDays} ימי חופשה ב-0 ימי חופש מהעבודה. יעילות ימי החופש מובילה את הדירוג המשוקלל לצד מושבי הבונוס ואקלים.`
          : `Maximum leverage — ${totalDays} trip days for 0 workdays off. Workday efficiency leads the weighted ranking score alongside award seats and climate.`;
      } else {
        workCalc = isHe
          ? `לוח עבודה ישראלי א׳–ה׳ על פני ${totalDays} ימי טיול: ${regWorkCnt} רגילים (1), ${cholWorkCnt} חוה״מ (0.5), ${freeWorkCnt} סופ״ש/שבתון (0) ← ${workdaysStr} ימי חופש (יחס ×${leverageInfo.effRatioDisplay}, נחסכו ${leverageInfo.savedStr} ימים).`
          : `Sun–Thu Israeli workplace calendar over ${totalDays} trip days: ${regWorkCnt} regular (1), ${cholWorkCnt} Chol HaMoed (0.5), ${freeWorkCnt} Fri–Sat/holiday (0) → ${workdaysStr} days off (×${leverageInfo.effRatioDisplay} ratio, ${leverageInfo.savedStr} saved).`;
        workMeaning = isHe
          ? `כל יום חופש מהעבודה מניב ×${leverageInfo.effRatioDisplay} ימי טיול (${leverageInfo.savedStr} ימים נחסכו בסופ״ש ובחגי המשק). יעילות ימי החופש מובילה את הדירוג המשוקלל לצד מושבי הבונוס ואקלים.`
          : `Each workday off yields ×${leverageInfo.effRatioDisplay} trip days (${leverageInfo.savedStr} days covered by weekends & statutory holidays). Workday efficiency leads the weighted ranking score alongside award seats and climate.`;
      }
    } else {
      workCalc = isHe
        ? `מחושב לפי לוח עבודה ישראלי קבוע א׳–ה׳ על פני ${totalDays} ימי טיול: ${regWorkCnt} ימי עבודה רגילים (1.0), ${cholWorkCnt} ימי חול המועד (0.5), ו-${freeWorkCnt} ימי שישי-שבת וחג שבתון (0) ← ${workdaysStr} ימי חופש לנוסע/ת עובד/ת.`
        : `Computed on the fixed Sun–Thu Israeli workplace calendar across ${totalDays} trip days: ${regWorkCnt} regular workdays (1.0), ${cholWorkCnt} Chol HaMoed half-days (0.5), and ${freeWorkCnt} Fri–Sat/official holiday days (0) → ${workdaysStr} days off per working traveler.`;

      if (wCost === 0) {
        workMeaning = isHe
          ? `ניצול מלא של סופ״ש וחגי שבתון במשק — 0 ימי חופשת עבודה לעובד/ת יחיד/ה עבור ${totalDays} ימי טיול.`
          : `Full weekend and statutory holiday coverage — 0 workplace vacation days needed per working traveler across ${totalDays} trip days.`;
      } else if (freeWorkCnt > 0 || cholWorkCnt > 0) {
        workMeaning = isHe
          ? `ניצול יעיל של סופ״ש ומועדי המשק — נדרשים ${workdaysStr} ימי חופשת עבודה בלבד לעובד/ת יחיד/ה עבור ${totalDays} ימי חופשה (אינו תלוי במספר הטסים).`
          : `Efficient weekend and holiday bridge — requires ${workdaysStr} workplace vacation day(s) per working traveler for a ${totalDays}-day trip (independent of party size).`;
      } else {
        workMeaning = isHe
          ? `התאריכים נופלים על ימי עבודה רגילים במשק — נדרשים ${workdaysStr} ימי חופשת עבודה לעובד/ת יחיד/ה עבור ${totalDays} ימי טיול.`
          : `Dates fall on regular Sun–Thu workdays — requires ${workdaysStr} workplace vacation day(s) per working traveler across ${totalDays} trip days.`;
      }
    }
    const impacts = Array.isArray(p && p.per_child_impact) ? p.per_child_impact : [];
    const fwImpacts = impacts.filter((c) => c && c.framework_type);
    const ccgPct = Math.round(Number((p && p.childcare_coverage_gain) ?? 1) * 100);
    const hasNum = Number(hasVal) || 0;

    const maxSingle = Number((p && p.max_single_child_school_days_missed) || 0);
    const q = state.lastSearchQuery || null;
    const shiftDays =
      p &&
      p.window_set_type === 'SPECIFIC_USER_WINDOW' &&
      q &&
      q.specific_departure_date &&
      q.specific_return_date
        ? Math.abs(diffDaysIso(q.specific_departure_date, it.departure_date)) +
          Math.abs(diffDaysIso(q.specific_return_date, it.return_date))
        : 0;
    const shiftNoteHe =
      shiftDays > 0 ? ` (כולל הפחתה קלה על הזזת גמישות של ${shiftDays} ימים מתאריכי היעד)` : '';
    const shiftNoteEn =
      shiftDays > 0 ? ` (including a minor flex deduction for shifting ${shiftDays} day(s) from requested dates)` : '';

    let fitCalc = '';
    if (fwImpacts.length > 0) {
      fitCalc = isHe
        ? `מחושב על פני ${totalDays} ימי טיול עבור ${fwImpacts.length} ילדים מול לוח משרד החינוך: 65% כיסוי חופשת לימודים, סופ״ש וקייטנות (${ccgPct}% מהטיול) + 35% חפיפה משותפת, בניכוי ימי חיסור (${schoolMissed})${shiftNoteHe}.`
        : `Computed across ${totalDays} trip days for ${fwImpacts.length} school-age children against the MoE calendar: 65% break/weekend/camp coverage (${ccgPct}% of trip) + 35% shared break overlap, minus missed school days (${schoolMissed})${shiftNoteEn}.`;
    } else {
      fitCalc = isHe
        ? `מחושב על פני ${totalDays} ימי טיול מול לוח החופשות הרשמי של משרד החינוך וסופי שבוע${shiftNoteHe}.`
        : `Computed across ${totalDays} trip days against the official MoE break calendar and weekends${shiftNoteEn}.`;
    }

    const missedCalcAddon =
      fwImpacts.length > 0
        ? (isHe
            ? ` בסוגריים: ימי לימודים פעילים (ללא חגים, שישי-שבת וקייטנות) שמוחסרים על ידי ${fwImpacts.length} ילדים (עד ${maxSingle} לילד/ה).`
            : ` In parentheses: active classroom days (excluding breaks, weekends, and camps) missed across ${fwImpacts.length} children (up to ${maxSingle} per child).`)
        : (isHe
            ? ' בסוגריים: ימי לימודים פעילים שמוחסרים (0 ילדים במסגרת חינוכית בהרכב הטסים).'
            : ' In parentheses: active classroom days missed (0 active school frameworks in traveler party).');

    const missedMeaningAddon =
      schoolMissed === 0
        ? (isHe
            ? ' אפס ימי חיסור משנת הלימודים.'
            : ' Zero missed school days.')
        : (isHe
            ? ` סה״כ ${schoolMissed} ימי היעדרות מצטברים (${maxSingle} בפועל לילד/ה).`
            : ` ${schoolMissed} combined child-day absences (${maxSingle} actual day(s) per child).`);

    let fitMeaning = '';
    if (hasNum >= 85) {
      fitMeaning =
        (isHe
          ? `התאמה גבוהה מאוד (${hasVal}/100) — הטיול יושב ברובו על חופשת בית הספר הרשמית וסופי שבוע.`
          : `Excellent fit (${hasVal}/100) — almost the entire trip sits inside official school break dates and weekends.`) +
        missedMeaningAddon;
    } else if (hasNum >= 60) {
      fitMeaning =
        (isHe
          ? `התאמה טובה (${hasVal}/100) — רוב הטיול מכוסה בחופשת לימודים, סופ״ש או קייטנה עם גלישה מתונה לימי לימודים.`
          : `Good fit (${hasVal}/100) — most trip days sit on school break, weekend, or camp dates with modest overlap.`) +
        missedMeaningAddon;
    } else if (hasNum > 0) {
      fitMeaning =
        (isHe
          ? `חפיפה חלקית (${hasVal}/100) — רק חלק מימי הטיול יושבים על חופשת לימודים או סופ״ש, והשאר נופלים על ימי לימודים פעילים.`
          : `Partial overlap (${hasVal}/100) — only part of the trip sits on school break or weekend dates; the rest are active school days.`) +
        missedMeaningAddon;
    } else if (schoolMissed > 0) {
      fitMeaning = isHe
        ? `אין חפיפה לחופשת בית ספר (${hasVal}/100) — התאריכים שנבחרו נופלים במלואם על ימי לימודים רגילים (ללא חופשת משרד החינוך או סופ״ש). סה״כ ${schoolMissed} ימי חיסור מצטברים (${maxSingle} בפועל לילד/ה).`
        : `No school break overlap (${hasVal}/100) — the selected dates fall entirely on regular school days outside official MoE breaks and weekends. ${schoolMissed} combined child-day absences (${maxSingle} actual day(s) per child).`;
    } else {
      fitMeaning = isHe
        ? `מחוץ לחופשות משרד החינוך (${hasVal}/100) — התאריכים הם ימי לימודים רגילים בלוח החינוך (0 חיסורים להרכב הטסים הנוכחי).`
        : `Outside official school breaks (${hasVal}/100) — regular school days on the MoE calendar (0 absences for the current traveler party).`;
    }

    const safeSeated = Math.max(1, Number(seatedCount) || 1);
    const outS = dirInfo.outbound.seats;
    const inS = dirInfo.inbound.seats;
    const outLblHe = !dirInfo.outbound.hasBonus ? '0' : (dirInfo.outbound.twoPlus ? '\u20662+\u2069' : String(outS));
    const inLblHe = !dirInfo.inbound.hasBonus ? '0' : (dirInfo.inbound.twoPlus ? '\u20662+\u2069' : String(inS));
    const outLblEn = !dirInfo.outbound.hasBonus ? '0' : (dirInfo.outbound.twoPlus ? '2+' : String(outS));
    const inLblEn = !dirInfo.inbound.hasBonus ? '0' : (dirInfo.inbound.twoPlus ? '2+' : String(inS));
    const outPct = Math.round(Math.min(1, outS / safeSeated) * 100);
    const inPct = Math.round(Math.min(1, inS / safeSeated) * 100);
    const fbvsNum = Number(fbvsVal) || 0;
    const fbvsStr = fbvsNum.toFixed(1);

    const bonusCalc = isHe
      ? `ממוצע כיסוי מושבי הבונוס הפנויים בשני הכיוונים מול ${safeSeated} נוסעים בעלי מושב: הלוך ${outLblHe} מושבים (${outPct}%) וחזור ${inLblHe} מושבים (${inPct}%) ← ${fbvsStr}/100`
      : `Average open bonus-seat coverage across both legs for ${safeSeated} seated travelers: outbound ${outLblEn} seats (${outPct}%) and return ${inLblEn} seats (${inPct}%) → ${fbvsStr}/100.`;

    let bonusMeaning = '';
    if (fbvsNum >= 100) {
      bonusMeaning = isHe
        ? 'כיסוי בונוס מלא (100/100) — קיימים מספיק מושבי בונוס פתוחים לכל הנוסעים בהלוך ובחזור.'
        : 'Full award seat coverage (100/100) — enough open bonus seats for every seated traveler both ways.';
    } else if (fbvsNum >= 50) {
      bonusMeaning = isHe
        ? `כיסוי בונוס משמעותי (${fbvsStr}/100) — מושבי הבונוס מכסים כיוון מלא או ${isWpCard ? 'חלק מהנוסעים' : 'חלק מהמשפחה'} בשני הכיוונים (בסימון \u20662+\u2069 ייתכן שיש מושבים נוספים).`
        : `Substantial award seat coverage (${fbvsStr}/100) — open bonus seats cover one full leg or ${isWpCard ? 'part of your party' : 'part of the family'} both ways (2+ flights may hold more seats).`;
    } else {
      bonusMeaning = isHe
        ? `כיסוי בונוס חלקי (${fbvsStr}/100) — מספר מושבי הבונוס הפתוחים נמוך ממספר הנוסעים הזקוקים למושב.`
        : `Partial award seat coverage (${fbvsStr}/100) — open bonus seats cover only a fraction of your party's needed seats.`;
    }

    return {
      schoolFit: {
        title: isHe ? 'התאמה לחופשת בית ספר וחיסורים' : 'School Break Fit & Absences',
        calc: fitCalc + missedCalcAddon,
        meaning: fitMeaning
      },
      bonusValue: {
        title: isHe ? 'כדאיות בונוס' : 'Award Value',
        calc: bonusCalc,
        meaning: bonusMeaning
      },
      workdaysCost: {
        title: workTitle,
        calc: workCalc,
        meaning: workMeaning
      }
    };
  }

  function renderProposals() {
    const container = document.getElementById('proposals-container');
    if (!container) return;
    const isHe = state.locale === 'he';
    const renderableProposals = getRenderableBonusProposals(state.proposals);
    updateZoneResultsTitle();

    if (state.validationErrorHe || state.validationErrorEn) {
      const valMsg = isHe
        ? (state.validationErrorHe || 'נא לבדוק את ערכי הקלט בטופס ולנסות שוב.')
        : (state.validationErrorEn || 'Check your search or profile inputs and try again.');
      container.innerHTML = `
        <div class="status-banner-card">
          <strong class="status-banner-title">
            ⚠️ ${isHe ? 'ערכי קלט לא תקינים' : 'Invalid Search or Profile Inputs'}
          </strong>
          <p class="status-banner-body">
            ${escapeHtml(valMsg)}
          </p>
        </div>
      `;
      return;
    }

    if (renderableProposals.length === 0) {
      const NO_SYNCED_FLIGHTS_TOKEN_HE = 'אין משיכה של טיסות מהשרת';
      const rawHe = String(state.statusMessageHe || '');
      const isWpEmpty = isWorkplaceModeProfile(state.profile);
      const hasBudgetActive =
        isWpEmpty &&
        state.maxWorkdaysOffBudget !== null &&
        Number.isFinite(state.maxWorkdaysOffBudget);
      const isBudgetEmpty = Boolean(hasBudgetActive && (state.workdaysBudgetExceeded || !rawHe.includes(NO_SYNCED_FLIGHTS_TOKEN_HE)));
      const isStandardUnsynced = !isBudgetEmpty && (!rawHe || rawHe.includes(NO_SYNCED_FLIGHTS_TOKEN_HE));
      const selectDestEl = document.getElementById('select-destination');
      const chosenOpts = selectDestEl
        ? Array.from(selectDestEl.selectedOptions || []).filter(
            (o) => o.value && o.value !== 'ANYWHERE'
          )
        : [];
      const destLabel =
        chosenOpts.length === 1
          ? String(chosenOpts[0].textContent || '').trim()
          : chosenOpts.length > 1
            ? chosenOpts
                .map((o) => formatDestOptionShortName(o, isHe) || o.value)
                .join(' · ')
            : '';

      const bStr = hasBudgetActive ? String(state.maxWorkdaysOffBudget) : '';
      const badgeText = isBudgetEmpty
        ? (isHe ? `💼 תקציב ימי חופש (≤${bStr})` : `💼 Workdays Budget (≤${bStr})`)
        : (isHe ? '✈️ מחכה למשיכת טיסות' : '✈️ Awaiting Flight Sync');
      const headlineText = isBudgetEmpty
        ? (isHe ? 'אין חלונות בתקציב ימי החופש שנבחר' : 'No Windows Within Workdays Budget')
        : (isHe ? 'מחכה למשיכת טיסות' : 'Awaiting Flight Sync');
      const subText = isBudgetEmpty
        ? (rawHe && isHe
            ? rawHe
            : (!isHe && state.statusMessageEn
                ? String(state.statusMessageEn)
                : (isHe
                    ? `לא נמצאו חלונות טיסה בתקציב של עד ${bStr} ימי חופש מהעבודה עבור הבחירה הנוכחית. ניתן להסיר את המגבלה או לבחור ב״✨ המיקסום הטוב ביותר בשנה הקרובה״.`
                    : `No flight windows matched a budget of up to ${bStr} workdays off for this selection. Clear the budget filter or try '✨ Best Maximization Next Year'.`)))
        : isStandardUnsynced
          ? isHe
            ? 'לא נמצאו מושבי בונוס פנויים במאגר עבור היעד והחופשה שנבחרו (מאגר טיסות הבונוס מתעדכן פעם ביום). מומלץ לנסות יעד נוסף או מועד חופשה אחר.'
            : 'No open award seats are currently available in the database for the selected destination and holiday (the bonus flight database updates once daily). Try another destination or vacation window.'
          : isHe
            ? rawHe
            : String(state.statusMessageEn || 'No matching flights found for the current search filters.');

      const budgetActionHtml = isBudgetEmpty
        ? `
          <div class="awaiting-flights-actions">
            <button type="button" class="btn-secondary" id="btn-empty-clear-budget">
              ${isHe ? 'הסרת מגבלת תקציב ימי החופש' : 'Clear workdays budget'}
            </button>
          </div>
        `
        : '';

      container.innerHTML = `
        <div class="awaiting-flights-showcase" role="status" aria-live="polite">
          <div class="awaiting-flights-scrim">
            <div class="awaiting-flights-badges">
              <span class="awaiting-flights-pill">${escapeHtml(badgeText)}</span>
              ${destLabel ? `<span class="awaiting-flights-dest-pill">📍 ${escapeHtml(destLabel)}</span>` : ''}
            </div>
            <h3 class="awaiting-flights-headline">${escapeHtml(headlineText)}</h3>
            <p class="awaiting-flights-sub">${escapeHtml(subText)}</p>
            ${budgetActionHtml}
          </div>
        </div>
      `;
      return;
    }

    const activeMatmidPts = Number((state.profile && state.profile.matmid_points_balance) || 0);
    const zeroPointsAlertHtml =
      activeMatmidPts <= 0
        ? `
          <div class="zero-points-alert-card" id="zero-points-search-alert" role="status">
            <div class="zero-points-alert-main">
              <strong class="zero-points-alert-title">
                💡 ${
                  isHe
                    ? 'החיפוש רץ עם יתרת מתמיד 0 — מוצגים מושבי הבונוס הפנויים ומספר הנקודות לכרטיס אחד'
                    : 'Search ran with 0 Matmid points — showing open bonus seats and the points one ticket takes'
                }
              </strong>
              <p class="zero-points-alert-body">
                ${
                  isHe
                    ? 'הזינו את יתרת המתמיד כדי לראות לאילו כרטיסי בונוס יש לכם מספיק נקודות.'
                    : 'Enter your Matmid balance to see which bonus tickets your points cover.'
                }
              </p>
            </div>
            <button type="button" class="btn-secondary btn-compact-action btn-zero-points-cta" data-focus-matmid="true">
              ${isHe ? '✏️ הזנת יתרת מתמיד' : '✏️ Enter Matmid Balance'}
            </button>
          </div>
        `
        : '';

    const awardSourceNoteHtml = `
      <details class="award-source-note-card award-note-disclosure" id="award-source-note-banner">
        <summary class="award-note-summary">
          ℹ️ <strong>${
            isHe
              ? 'הערה על מאגר כרטיסי הבונוס של אל על:'
              : 'About the EL AL award seat database:'
          }</strong>
        </summary>
        <p class="award-note-body">${
          isHe
            ? '<strong>מאגר טיסות הבונוס מתעדכן פעם ביום.</strong> מספר מושבי הבונוס ומספר הנקודות לכרטיס מבוססים על מאגר כרטיסי הבונוס של אל על ואינם מחייבים. "2+" פירושו שלפחות 2 מושבי בונוס הופיעו במחשבון אל על, אך הזמינות החיה במנוע ההזמנות (במיוחד בטיסות סאן דור / חכירה) עלולה להיות נמוכה יותר. הזמינות והנקודות הסופיות נקבעות בעת ההזמנה באל על.'
            : '<strong>The bonus flight database is updated once daily.</strong> Bonus seat counts and points per ticket come from EL AL\'s award seat database and are not binding. "2+" means at least 2 bonus seats appeared in EL AL\'s calculator, though live booking inventory (especially on Sun d\'Or / leased flights) may be lower. Final availability and points are set when you book with EL AL.'
        }</p>
      </details>
    `;

    const fallbackBannerHtml = state.weatherFallbackMessageHe
      ? `
        <div class="weather-fallback-card">
          🌤️ ${escapeHtml(isHe ? state.weatherFallbackMessageHe : 'Strict weather filter was relaxed to display the highest-rated weather options for these dates.')}
        </div>
      `
      : '';

    const totalCount = renderableProposals.length;
    const visibleList = state.showAllProposals
      ? renderableProposals
      : renderableProposals.slice(0, INITIAL_PROPOSALS_LIMIT);
    state.visibleRenderableProposals = visibleList;

    const cardsHtml = visibleList
      .map((p, idx) => {
        const it = p.itinerary || {};
        const dirInfo = resolveBonusDirectionInfo(it);
        const wm = p.weather_metrics || null;
        const wssVal = Number(
          p.weather_suitability_score ??
            (wm && wm.overall_weather_suitability_score) ??
            0
        );

        const destIcon = DESTINATION_ICONS[it.destination_iata] || '✈️';
        const cityTitle = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);

        const cardProfile = state.lastSearchProfile || state.profile;
        const hasChildrenInSearch = state.lastSearchProfile
          ? Array.isArray(state.lastSearchProfile.children) &&
            state.lastSearchProfile.children.length > 0
          : Array.isArray(p && p.per_child_impact)
            ? p.per_child_impact.length > 0
            : Array.isArray(state.profile && state.profile.children) &&
              state.profile.children.length > 0;
        const isWorkplaceCard = !hasChildrenInSearch;

        let topStyleChipHtml = '';
        let stubWeatherHtml = '';
        if (wm) {
          const recList = wm.recommended_vacation_types || [];
          if (recList.length > 0) {
            topStyleChipHtml = `<span class="weather-badge-tag">${formatVacationTypeBadge(recList[0])}</span>`;
          }
          const wIcon = pickCompactWeatherIcon(wm);
          const highC = Math.round(Number(wm.avg_day_high_c ?? wm.avg_max_temp_c ?? 0));
          const lowC = Math.round(Number(wm.avg_night_low_c ?? wm.avg_min_temp_c ?? 0));
          const sunH = Number(wm.sunshine_hours_per_day || 0).toFixed(1);
          const rainD = Number(
            wm.estimated_rain_days_in_trip ?? wm.expected_rain_days_in_trip ?? 0
          ).toFixed(1);
          const hasSea = wm.sea_water_temp_c !== null && wm.sea_water_temp_c !== undefined;
          const seaC = hasSea ? Math.round(Number(wm.sea_water_temp_c)) : 0;
          const seaSpan = hasSea
            ? `<span class="stub-weather-datum" data-weather-sea="${seaC}">🌊 <span class="num" dir="ltr">${seaC}°C</span></span>`
            : '';
          const scoreCls =
            wssVal >= 75
              ? 'stub-weather-score stub-weather-score-high'
              : 'stub-weather-score';
          const tipIdWeather = `weather-tip-${idx}`;
          const weatherTooltipHtml = renderWeatherTooltipHtml(
            tipIdWeather,
            wm,
            cityTitle,
            wssVal,
            isHe,
            isWorkplaceCard
          );
          stubWeatherHtml = `
                <div class="stub-weather-card" data-weather-compact="true" data-weather-score="${wssVal.toFixed(0)}" tabindex="0" aria-describedby="${tipIdWeather}">
                  <div class="stub-weather-main">
                    <span class="stub-weather-temp">
                      <span aria-hidden="true">${wIcon}</span>
                      <strong class="num" dir="ltr">${highC}°/${lowC}°C</strong>
                    </span>
                    <span class="${scoreCls}">
                      <span>${isHe ? 'אקלים' : 'Climate'}</span>
                      <strong class="num" dir="ltr">${wssVal.toFixed(0)}/100</strong>
                      <span class="kpi-info-cue" aria-hidden="true">ⓘ</span>
                    </span>
                  </div>
                  <div class="stub-weather-meta">
                    <span class="stub-weather-datum">☀️ <span class="num" dir="ltr">${sunH}h</span></span>
                    <span class="stub-weather-datum">🌧️ <span class="num" dir="ltr">${rainD}</span> ${isHe ? 'ימי גשם' : 'rain d'}</span>
                    ${seaSpan}
                  </div>
                  ${weatherTooltipHtml}
                </div>`;
        }

        const paxInfo = buildHouseholdPassengerSummary(cardProfile, it, isHe);
        const seatedCount = paxInfo.seatedCount;

        const wpFallback =
          p &&
          p.workplace_vacation_days_cost !== undefined &&
          p.workplace_vacation_days_cost !== null
            ? {
                workplace_vacation_days_cost: Number(p.workplace_vacation_days_cost),
                regular_workdays_count: Number(p.regular_workdays_count ?? 0),
                chol_hamoed_workdays_count: Number(p.chol_hamoed_workdays_count ?? 0),
                official_holiday_workdays_saved_count: Number(
                  p.official_holiday_workdays_saved_count ?? 0
                ),
                weekend_days_count: Number(p.weekend_days_count ?? 0),
                holiday_or_weekend_days_count: Number(
                  p.holiday_or_weekend_days_count ??
                    Number(p.official_holiday_workdays_saved_count ?? 0) +
                      Number(p.weekend_days_count ?? 0)
                )
              }
            : computeTripWorkdaysClient(it.departure_date, it.return_date);
        const wCost = Number(wpFallback.workplace_vacation_days_cost || 0);
        const workdaysStr = Number.isInteger(wCost) ? String(wCost) : wCost.toFixed(1);

        const tripDays =
          p && p.trip_calendar_days !== undefined && p.trip_calendar_days !== null
            ? Math.max(1, Number(p.trip_calendar_days))
            : Math.max(1, diffDaysIso(it.departure_date, it.return_date) + 1);
        const workdaysSaved =
          p && p.workdays_saved_count !== undefined && p.workdays_saved_count !== null
            ? Math.max(0, Math.round(Number(p.workdays_saved_count) * 10) / 10)
            : Math.max(0, Math.round((tripDays - wCost) * 10) / 10);
        const isZeroWorkday =
          p && p.is_zero_workday_trip !== undefined && p.is_zero_workday_trip !== null
            ? Boolean(p.is_zero_workday_trip)
            : wCost === 0;
        const effRatioRaw =
          p && p.workday_efficiency_ratio !== undefined && p.workday_efficiency_ratio !== null
            ? Number(p.workday_efficiency_ratio)
            : Math.round((tripDays / Math.max(0.5, wCost)) * 100) / 100;
        const effRatioDisplay = effRatioRaw.toFixed(1);
        const effRatioAttr = effRatioRaw.toFixed(2);
        const savedStr = Number.isInteger(workdaysSaved)
          ? String(workdaysSaved)
          : workdaysSaved.toFixed(1);

        const leverageInfo = {
          isWorkplaceCard,
          tripDays,
          workdaysSaved,
          effRatioDisplay,
          isZeroWorkday,
          savedStr
        };

        const tierCode = p.recommendation_tier || (idx === 0 ? 'RECOMMENDED' : idx < 4 ? 'TOP_CHOICE' : 'ALTERNATIVE');
        const fbvsVal = p.flight_bonus_value_score ?? p.family_bonus_value_score ?? 0;
        const hasVal = Number(p.holiday_alignment_score ?? 0).toFixed(1);
        const schoolMissed = Number(p.total_school_days_missed_across_children || 0);
        const missedParenText = isHe
          ? (schoolMissed === 1 ? 'חיסור 1' : `${schoolMissed} חיסורים`)
          : `${schoolMissed} missed`;
        const missedParenCls =
          schoolMissed === 0 ? 'kpi-missed-paren kpi-missed-zero' : 'kpi-missed-paren';

        const kpiInfo = buildKpiExplanations(
          p,
          it,
          dirInfo,
          seatedCount,
          hasVal,
          schoolMissed,
          fbvsVal,
          wpFallback,
          isHe,
          leverageInfo
        );
        const tipIdWork = `kpi-tip-work-${idx}`;
        const workdaysTooltipHtml = renderKpiTooltipHtml(
          tipIdWork,
          kpiInfo.workdaysCost.title,
          kpiInfo.workdaysCost.calc,
          kpiInfo.workdaysCost.meaning,
          isHe
        );
        const workUnitTxt = isHe
          ? (wCost === 1 ? 'יום חופש' : 'ימי חופש')
          : (wCost === 1 ? 'day' : 'days');
        const effPillCls = isZeroWorkday
          ? 'kpi-efficiency-pill kpi-efficiency-pill-zero'
          : 'kpi-efficiency-pill';
        const effPillText = isZeroWorkday
          ? (isHe ? '✨ 0 ימי חופש' : '✨ 0 Workdays')
          : `×${effRatioDisplay}`;
        const effPillHtml = isWorkplaceCard
          ? `<span class="${effPillCls}" data-kpi-efficiency="true" data-workday-ratio="${escapeHtml(effRatioAttr)}"${isZeroWorkday ? '' : ' dir="ltr"'}>${escapeHtml(effPillText)}</span>`
          : '';
        const savedParenCls =
          workdaysSaved > 0 ? 'kpi-saved-paren kpi-saved-positive' : 'kpi-saved-paren';
        const savedParenText =
          workdaysSaved > 0
            ? (isHe
                ? (workdaysSaved === 1 ? 'נחסך יום 1' : `נחסכו ${savedStr} ימים`)
                : `${savedStr} saved`)
            : (isHe ? '0 נחסכו' : '0 saved');
        const savedParenHtml = isWorkplaceCard
          ? ` <span class="${savedParenCls}" data-workdays-saved="${escapeHtml(savedStr)}">(${escapeHtml(savedParenText)})</span>`
          : '';
        const workdaysCellHtml = `
                  <div class="score-pill kpi-cell" data-kpi="workdays-cost" data-workdays="${escapeHtml(workdaysStr)}" tabindex="0" aria-describedby="${tipIdWork}">
                    <div class="kpi-cell-head">
                      <span class="kpi-cell-label">💼 ${isHe ? 'חופשת עבודה' : 'Workdays Off'}</span>
                      <span class="kpi-info-cue" aria-hidden="true">ⓘ</span>
                      ${effPillHtml}
                    </div>
                    <strong class="kpi-cell-val"><span class="num" dir="ltr">${escapeHtml(workdaysStr)}</span> <span class="kpi-workdays-unit">${escapeHtml(workUnitTxt)}</span>${savedParenHtml}</strong>
                    ${workdaysTooltipHtml}
                  </div>`;
        const pairedVacationAttr = hasChildrenInSearch ? ' data-paired-vacation="true"' : '';
        let stubKpiGridInnerHtml = workdaysCellHtml;
        if (hasChildrenInSearch) {
          const tipIdFit = `kpi-tip-fit-${idx}`;
          const schoolFitTooltipHtml = renderKpiTooltipHtml(
            tipIdFit,
            kpiInfo.schoolFit.title,
            kpiInfo.schoolFit.calc,
            kpiInfo.schoolFit.meaning,
            isHe
          );
          stubKpiGridInnerHtml += `
                  <div class="score-pill kpi-cell" data-kpi="school-fit" data-school-missed="${schoolMissed}" tabindex="0" aria-describedby="${tipIdFit}">
                    <div class="kpi-cell-head">
                      <span class="kpi-cell-label">🏫 ${isHe ? 'התאמה לחופשת בי"ס' : 'School Break Fit'}</span>
                      <span class="kpi-info-cue" aria-hidden="true">ⓘ</span>
                    </div>
                    <strong class="kpi-cell-val"><span class="num" dir="ltr">${hasVal}/100</span> <span class="${missedParenCls}">(${escapeHtml(missedParenText)})</span></strong>
                    ${schoolFitTooltipHtml}
                  </div>`;
        }

        const strategyCode = String(it.fulfillment_strategy || 'FULL_BONUS_SAME_CABIN');
        const stratBadgeText = resolveCardStrategyBadge(it, dirInfo, isHe);
        const strategyTagHtml = stratBadgeText
          ? `<span class="bonus-strategy-tag" title="${escapeHtml(stratBadgeText)}">${escapeHtml(stratBadgeText)}</span>`
          : '';

        const directionStatementText = formatBonusDirectionStatement(dirInfo.coverage, isHe);
        const directionBadgeCls =
          dirInfo.coverage === 'BOTH_DIRECTIONS'
            ? 'bonus-direction-badge'
            : 'bonus-direction-badge bonus-direction-badge-partial';

        const elalBookUrl = resolveElAlBookingUrl(it);
        const outLeg = (it.outbound_legs && it.outbound_legs[0]) || null;
        const inLeg = (it.inbound_legs && it.inbound_legs[0]) || null;
        const outboundCouponHtml = renderBonusCouponLane('outbound', dirInfo.outbound, outLeg, isHe);
        const inboundCouponHtml = renderBonusCouponLane('inbound', dirInfo.inbound, inLeg, isHe);

        const showTwoPlusNote =
          dirInfo.outbound.twoPlus ||
          dirInfo.inbound.twoPlus ||
          Boolean(it.requires_two_plus_seat_verification);
        const twoPlusTailHtml = isHe
          ? ' = לפחות 2 מושבי בונוס לפי מחשבון אל על (הזמינות החיה בהזמנה, במיוחד בסאן דור, עלולה להיות נמוכה יותר).'
          : ' = at least 2 bonus seats per EL AL\'s calculator (live booking inventory, especially on Sun d\'Or, may be lower).';
        const twoPlusPartyHtml =
          seatedCount > 2
            ? (isHe
                ? ` נדרשים ${escapeHtml(seatedCount)} מושבים — כדאי לבדוק הזמנה של <span class="two-plus-nowrap">2 ועוד 2\u200F.</span>`
                : ` ${escapeHtml(seatedCount)} seats needed — try booking <span class="two-plus-nowrap">2 and 2.</span>`)
            : '';
        const twoPlusNoteHtml = showTwoPlusNote
          ? `<p class="two-plus-note"><span dir="ltr">2+</span>${twoPlusTailHtml}${twoPlusPartyHtml}</p>`
          : '';

        const returnOriginLabel =
          it.return_origin_iata && it.return_origin_iata !== it.destination_iata
            ? `${it.destination_iata}/${it.return_origin_iata}`
            : it.destination_iata;

        const rawMinPts = it.min_points_per_bonus_ticket;
        const minPtsNum =
          rawMinPts !== null && rawMinPts !== undefined && rawMinPts !== ''
            ? Math.round(Number(rawMinPts))
            : NaN;
        const hasMinPts = Number.isFinite(minPtsNum) && minPtsNum > 0;
        const rawBasis = String(it.min_points_basis || '').trim().toUpperCase();
        const minPtsScope =
          rawBasis === 'ONE_WAY'
            ? 'one_way'
            : rawBasis === 'ROUND_TRIP'
              ? 'round_trip'
              : dirInfo.coverage === 'BOTH_DIRECTIONS'
                ? 'round_trip'
                : 'one_way';
        const minPtsLabel =
          minPtsScope === 'round_trip'
            ? (isHe ? 'נקודות לכרטיס בונוס אחד (הלוך ושוב)' : 'Points for one bonus ticket (round trip)')
            : (isHe ? 'נקודות לכרטיס בונוס אחד (כיוון אחד)' : 'Points for one bonus ticket (one way)');
        const minPtsFormatted = hasMinPts ? minPtsNum.toLocaleString('en-US') : '';
        const minPtsValue = hasMinPts
          ? (isHe ? `החל מ-${minPtsFormatted}` : `from ${minPtsFormatted}`)
          : '';
        const minPointsRowHtml = hasMinPts
          ? `
                    <div class="min-points-ticket flight-bonus-points-pill" data-min-points="${minPtsNum}" data-scope="${minPtsScope}">
                      <span class="flight-points-icon" aria-hidden="true">🎫</span>
                      <span class="stub-fare-label">${escapeHtml(minPtsLabel)}</span>
                      <span class="stub-fare-val stub-fare-points">${escapeHtml(minPtsValue)}</span>
                    </div>`
          : '';

        const elalBookBtnHtml = elalBookUrl
          ? `
              <a class="btn-elal-book" href="${escapeHtml(elalBookUrl)}" target="_blank" rel="noopener noreferrer" data-elal-book-link="true" data-proposal-idx="${idx}" title="${isHe ? 'פתיחת הטיסה ב-Google Flights לבדיקת זמינות והזמנה באל על' : 'Open the flight on Google Flights to check availability and book with EL AL'}">
                <span>✈️ ${isHe ? 'להזמנת טיסת אל על' : 'Book EL AL Flight'}</span>
                <span dir="ltr" aria-hidden="true">↗</span>
              </a>
            `
          : '';
        const sharePlanBtnHtml = `
              <button type="button" class="btn-share-plan" data-share-plan-trigger="true" data-proposal-idx="${idx}" aria-haspopup="dialog" aria-controls="share-plan-modal" aria-label="${isHe ? 'שיתוף תוכנית החופשה במייל או בוואטסאפ' : 'Share vacation plan via Email or WhatsApp'}" title="${isHe ? 'שתף תוכנית חופשה במייל או בוואטסאפ' : 'Share vacation plan via Email or WhatsApp'}">
                <span class="btn-share-plan-icon" aria-hidden="true">📤</span>
                <span class="btn-share-plan-label">${isHe ? 'שתף' : 'Share'}</span>
              </button>
            `;
        const bookingGuideBtnHtml = elalBookUrl
          ? `
              <button type="button" class="btn-booking-guide" data-booking-guide-trigger="true" data-proposal-idx="${idx}" aria-haspopup="dialog" aria-controls="booking-handoff-modal" aria-label="${isHe ? 'פתיחת מדריך ההזמנה ופרטי הטיסות' : 'Open booking guide and flight details'}" title="${isHe ? 'פתיחת מדריך ההזמנה ופרטי הטיסות' : 'Open booking guide and flight details'}">
                <span class="btn-booking-guide-icon" aria-hidden="true">ⓘ</span>
                <span class="btn-booking-guide-label">${isHe ? 'מדריך הזמנה' : 'Booking guide'}</span>
              </button>
            `
          : '';

        const ctosTitleText = isWorkplaceCard
          ? (isHe
              ? 'ציון מיקסום חופשה (יעילות ימי חופש מהעבודה + זמינות בונוס + אקלים)'
              : 'Trip Maximization Score (Workday Leverage + Award Seats + Climate)')
          : (isHe ? 'ציון התאמה משוקלל' : 'Overall Optimization Score');

        const mergedHolidaysRaw =
          isWorkplaceCard && Array.isArray(p.merged_holidays) && p.merged_holidays.length > 0
            ? p.merged_holidays
            : (isWorkplaceCard && it.departure_date && it.return_date
                ? detectMergedWorkplaceHolidaysClient(it.departure_date, it.return_date)
                : []);
        const mergedStripHtml =
          isWorkplaceCard && mergedHolidaysRaw.length > 0
            ? (() => {
                const isMergedCombo = mergedHolidaysRaw.length >= 2;
                const spansYkAbroad = mergedHolidaysRaw.some((m) => Boolean(m.is_stay_abroad_holiday));
                const chipsHtml = mergedHolidaysRaw
                  .map((m) => {
                    const chipLabel = isHe
                      ? (m.short_name_he || m.name_he || m.code)
                      : (m.short_name_en || m.name_en || m.code);
                    return `<span class="merged-holiday-chip" data-holiday-code="${escapeHtml(m.code || '')}">${escapeHtml(chipLabel)}</span>`;
                  })
                  .join('<span class="merged-holiday-plus" aria-hidden="true">+</span>');
                const prefixTxt = isMergedCombo
                  ? (isHe ? '🌉 איחוד חגים:' : '🌉 Merged holidays:')
                  : (isHe ? '🗓️ חג משק:' : '🗓️ Workplace holiday:');
                const ykPillHtml = spansYkAbroad
                  ? `<span class="merged-yk-pill">${isHe ? '✈️ שהייה בחו״ל בכיפור · חוסך יום חופש' : '✈️ Abroad over Yom Kippur · saves 1 workday'}</span>`
                  : '';
                return `
                  <div class="card-merged-holidays-strip ${isMergedCombo ? 'is-mega-combo' : 'is-single-holiday'}" data-merged-holidays="true" data-merged-count="${mergedHolidaysRaw.length}"${spansYkAbroad ? ' data-yom-kippur-abroad="true"' : ''}>
                    <span class="merged-holidays-label">${escapeHtml(prefixTxt)}</span>
                    <span class="merged-holidays-chain">${chipsHtml}</span>
                    ${ykPillHtml}
                  </div>
                `;
              })()
            : '';

        return `
          <article class="proposal-card tier-${escapeHtml(tierCode)}" data-strategy="${escapeHtml(strategyCode)}" data-bonus-directions="${escapeHtml(dirInfo.dirAttr)}" data-proposal-idx="${idx}">
            <div class="proposal-pass-grid">
              <div class="proposal-pass-main">
                <div class="proposal-top-bar">
                  <div class="proposal-dest-header">
                    <span class="proposal-dest-icon" aria-hidden="true">${destIcon}</span>
                    <div class="proposal-title-group">
                      <strong class="proposal-dest-title">${escapeHtml(cityTitle)}</strong>
                      <span class="proposal-route-pair"><span class="route-pair-origin" dir="ltr">${escapeHtml(it.origin_iata || 'TLV')}</span> <span aria-hidden="true">⇄</span> <span class="route-pair-dest" dir="ltr">${escapeHtml(it.destination_iata)}</span></span>
                      ${topStyleChipHtml}
                    </div>
                    <div class="proposal-header-actions">
                      ${sharePlanBtnHtml}
                      ${bookingGuideBtnHtml}
                    </div>
                  </div>
                </div>

                <div class="boarding-route-bar">
                  <div class="route-endpoint">
                    <span class="route-iata" dir="ltr">${escapeHtml(it.origin_iata || 'TLV')}</span>
                    <span class="route-date" dir="ltr">${escapeHtml(it.departure_date)}</span>
                  </div>
                  <div class="route-arc-Track">
                    <span class="route-nights-pill" dir="auto">${escapeHtml(it.trip_nights)} ${isHe ? 'לילות' : 'Nights'}</span>
                    <div class="route-arc-line">
                      <span>●</span>
                      <span class="route-arc-dash"></span>
                      <span class="route-arc-plane" aria-hidden="true">✈️</span>
                      <span class="route-arc-dash"></span>
                      <span>●</span>
                    </div>
                  </div>
                  <div class="route-endpoint route-endpoint-end">
                    <span class="route-iata" dir="ltr">${escapeHtml(returnOriginLabel)}</span>
                    <span class="route-date" dir="ltr">${escapeHtml(it.return_date)}</span>
                  </div>
                  ${mergedStripHtml}
                </div>

                <div class="bonus-direction-block">
                  <div class="bonus-direction-header">
                    <div class="bonus-direction-status-group">
                      <span class="${directionBadgeCls}">
                        <span class="bonus-direction-dot" aria-hidden="true"></span>
                        <span class="bonus-direction-statement">${escapeHtml(directionStatementText)}</span>
                      </span>
                      ${strategyTagHtml}
                    </div>${minPointsRowHtml}
                  </div>
                  <div class="bonus-lanes">
                    ${outboundCouponHtml}
                    ${inboundCouponHtml}
                  </div>
                  ${twoPlusNoteHtml}
                </div>
              </div>

              <div class="proposal-pass-stub">
                <div class="stub-score-header">
                  <div class="stub-ctos-badge" dir="ltr" title="${escapeHtml(ctosTitleText)}">
                    <span>⭐</span>
                    <span class="stub-ctos-num">${Number(p.combined_trip_optimization_score || 0).toFixed(1)}</span>
                    <span class="stub-ctos-max">/100</span>
                  </div>
                </div>
                ${stubWeatherHtml}

                <div class="stub-kpi-grid"${pairedVacationAttr}>${stubKpiGridInnerHtml}
                </div>

                ${elalBookBtnHtml ? `<div class="stub-actions-stack">${elalBookBtnHtml}</div>` : ''}
              </div>
            </div>
          </article>
        `;
      })
      .join('');

    const toggleFeedHtml =
      totalCount > INITIAL_PROPOSALS_LIMIT
        ? `
          <div class="proposals-feed-toggle-wrap">
            <button type="button" class="btn-secondary btn-feed-toggle" data-toggle-all-proposals="true">
              ${
                state.showAllProposals
                  ? (isHe ? `הצג ${INITIAL_PROPOSALS_LIMIT} חלופות מובילות בלבד ▴` : `Show top ${INITIAL_PROPOSALS_LIMIT} proposals only ▴`)
                  : (isHe ? `הצג את כל ${totalCount} החלופות ▾` : `Show all ${totalCount} proposals ▾`)
              }
            </button>
          </div>
        `
        : '';

    container.innerHTML = zeroPointsAlertHtml + awardSourceNoteHtml + fallbackBannerHtml + cardsHtml + toggleFeedHtml;
  }

  function updateActiveModeBadge() {
    const badge = document.getElementById('active-mode-badge');
    if (!badge) return;
    const isHe = state.locale === 'he';
    const isWp = isWorkplaceModeProfile(state.profile);
    const mode = state.dateSelectionMode;
    const selectEl = document.getElementById('select-direct-holiday');
    const selectedCode = selectEl ? selectEl.value : '';
    if (mode === 'SPECIFIC_DATES') {
      badge.textContent = isHe ? 'תאריכים ידניים (±גמישות)' : 'Manual Dates (±Flex)';
    } else if (isWp && selectedCode === 'BEST_YEAR_MAXIMIZER') {
      badge.textContent = isHe ? 'מיקסום שנתי · כל חגי המשק' : 'Best Year · All Workplace Holidays';
    } else if (isWp) {
      badge.textContent = isHe ? 'חגי משק · יעילות ימי חופש' : 'Workplace Holidays · Max Leverage';
    } else {
      badge.textContent = isHe ? 'תכנון לפי חג (שנה קדימה)' : 'Rolling 1-Year Holiday';
    }
  }

  function setDateMode(mode) {
    const normMode = mode === 'SPECIFIC_DATES' ? 'SPECIFIC_DATES' : 'HOLIDAY_DIRECT_INTENT';
    state.dateSelectionMode = normMode;
    document.querySelectorAll('.mode-tab-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-mode') === normMode);
    });
    const cHoliday = document.getElementById('controls-holiday-direct');
    const cHolidayDur = document.getElementById('controls-holiday-duration');
    const cSpec = document.getElementById('controls-specific-dates');
    if (cHoliday) cHoliday.style.display = normMode === 'HOLIDAY_DIRECT_INTENT' ? 'grid' : 'none';
    if (cHolidayDur) cHolidayDur.style.display = normMode === 'HOLIDAY_DIRECT_INTENT' ? 'grid' : 'none';
    if (cSpec) cSpec.style.display = normMode === 'SPECIFIC_DATES' ? 'grid' : 'none';

    syncWorkplaceHolidayControlsVisibility();
    updateActiveModeBadge();
    syncSearchFiltersSummary();
    renderProfileControls();
  }

  function syncPlanningModeUi() {
    const isWp = isWorkplaceModeProfile(state.profile);
    const isHe = state.locale === 'he';
    const modeStr = isWp ? 'workplace' : 'family';

    const shell = document.getElementById('dashboard-shell');
    if (shell) {
      shell.setAttribute('data-planning-mode', modeStr);
    }

    const calZone = document.getElementById('zone-calendar');
    if (calZone) {
      calZone.setAttribute('data-calendar-mode', modeStr);
    }
    const moeCol = document.getElementById('calendar-col-moe');
    if (moeCol) {
      if (isWp) moeCol.setAttribute('aria-hidden', 'true');
      else moeCol.removeAttribute('aria-hidden');
    }
    const btnSyncMoe = document.getElementById('btn-sync-moe-year');
    if (btnSyncMoe) {
      btnSyncMoe.hidden = isWp;
      if (isWp) btnSyncMoe.setAttribute('aria-hidden', 'true');
      else btnSyncMoe.removeAttribute('aria-hidden');
    }

    document.title = isWp
      ? (isHe
          ? 'breezyflights | מתכנן חופשות חכם לפי חגי המשק וכרטיסי בונוס אל על'
          : 'breezyflights | Smart Workplace Holiday & EL AL Award Planner')
      : (isHe
          ? 'breezyflights | מתכנן חופשות משפחתיות חכם וכרטיסי בונוס אל על'
          : 'breezyflights | Smart Family Vacation & EL AL Award Planner');

    const headerTitleLocal = document.getElementById('header-title-local');
    if (headerTitleLocal) {
      headerTitleLocal.textContent = isWp
        ? (isHe ? 'מתכנן חופשות חכם' : 'Smart Vacation Planner')
        : (isHe ? 'מתכנן חופשות משפחתיות חכם' : 'Smart Family Vacation Planner');
    }
    const headerSubtitle = document.getElementById('header-subtitle');
    if (headerSubtitle) {
      headerSubtitle.textContent = isWp
        ? (isHe
            ? 'תכנון חופשות לפי חגי המשק, מיקסום אורך הטיול לימי חופש וכרטיסי בונוס באל על'
            : 'Maximize trip length per workday off around Israeli workplace holidays & EL AL award seats')
        : (isHe
            ? 'תכנון חופשות לפי לוח משרד החינוך, קייטנות ניצנים וכרטיסי בונוס באל על'
            : 'Plan around official MoE school breaks, Nitzanim camps & EL AL Matmid award seats');
    }

    const btnToggleCal = document.getElementById('btn-toggle-calendar');
    if (btnToggleCal && !state.isCalendarVisible) {
      btnToggleCal.textContent = isWp
        ? (isHe ? '📅 לוח חגי המשק' : '📅 Workplace Holidays')
        : (isHe ? '📅 לוח חופשות' : '📅 MoE Calendar');
    }

    const heroSection = document.getElementById('vacation-hero');
    if (heroSection) {
      heroSection.setAttribute(
        'aria-label',
        isWp
          ? (isHe
              ? 'פתיח breezyflights לתכנון חופשות לפי חגי המשק'
              : 'breezyflights Israeli workplace holiday vacation planner overview')
          : (isHe
              ? 'פתיח breezyflights לתכנון חופשות משפחתיות'
              : 'breezyflights family vacation planner overview')
      );
    }
    const heroEyebrow = document.getElementById('hero-eyebrow');
    if (heroEyebrow) {
      heroEyebrow.innerHTML = isWp
        ? (isHe
            ? '🏝️ <span class="hero-eyebrow-short">חופשות חכמות</span><span class="hero-eyebrow-sub">חגי המשק · יותר טיול בפחות ימי חופש</span>'
            : '🏝️ <span class="hero-eyebrow-short">Smart Escapes</span><span class="hero-eyebrow-sub">Israeli Workplace Holidays · Max Workday Leverage</span>')
        : (isHe
            ? '🏝️ <span class="hero-eyebrow-short">חופשות חכמות</span><span class="hero-eyebrow-sub">תכנון חכם לחופשה המשפחתית הבאה</span>'
            : '🏝️ <span class="hero-eyebrow-short">Smart Escapes</span><span class="hero-eyebrow-sub">Smart Family Vacation Planning</span>');
    }
    const heroHeadline = document.getElementById('hero-headline');
    if (heroHeadline) {
      heroHeadline.textContent = isWp
        ? (isHe
            ? 'הפכו כל חג במשק לחופשה ארוכה במינימום ימי חופש'
            : 'Turn Every Workplace Holiday Into a Longer Escape With Minimal Days Off')
        : (isHe
            ? 'הפכו כל חופשת בית ספר לחופשה משפחתית חלומית'
            : 'Turn Every School Break Into a Dream Family Escape');
    }
    const heroLead = document.getElementById('hero-lead');
    if (heroLead) {
      heroLead.textContent = isWp
        ? (isHe
            ? 'הצלבה חכמה בין חגי המשק הישראלי, גשרי סופ״ש וחול המועד ומושבי בונוס מנתב״ג לכל היעדים הפתוחים.'
            : 'Smart cross-matching of Israeli statutory workplace holidays, weekend & Chol HaMoed bridges, and EL AL Matmid award seats from TLV across all open destinations.')
        : (isHe
            ? 'הצלבה חכמה בין לוח החופשות של משרד החינוך, קייטנות ניצנים ומושבי בונוס מנתב״ג לכל היעדים הפתוחים.'
            : 'Smart cross-matching of official MoE school breaks, Nitzanim camps, and EL AL Matmid award seats from TLV across all open destinations.');
    }

    const labelDirectHoliday = document.getElementById('label-direct-holiday');
    if (labelDirectHoliday) {
      labelDirectHoliday.textContent = isWp
        ? (isHe ? 'חג במשק בשנה הקרובה:' : 'Upcoming Workplace Holiday (Next 12 Months):')
        : (isHe ? 'חג / חופשה בשנה הקרובה:' : 'Upcoming Holiday (Next 12 Months):');
    }

    const btnRunSearch = document.getElementById('btn-run-search');
    if (btnRunSearch) {
      btnRunSearch.textContent = isWp
        ? (isHe ? '✈️ חפש אפשרויות חופשה וכרטיסי בונוס' : '✈️ Search Award Vacations')
        : (isHe ? '✈️ חפש אפשרויות חופשה וכרטיסי בונוס' : '✈️ Search Family Award Vacations');
    }

    const zProfile = document.getElementById('zone-profile-title');
    if (zProfile) {
      zProfile.textContent = isWp
        ? (isHe ? 'הרכב הנוסעים ויתרת מתמיד' : 'Travelers & Matmid Balance')
        : (isHe ? 'פרופיל משפחה, גילאי ילדים ויתרת מתמיד' : 'Family Profile, Children & Matmid Balance');
    }

    const childrenSummaryTitle = document.getElementById('profile-children-summary-title');
    if (childrenSummaryTitle) {
      childrenSummaryTitle.textContent = isWp
        ? (isHe ? '👶 ילדים (0 — מצב חגי משק אוטומטי)' : '👶 Children (0 — Auto Workplace Holidays Mode)')
        : (isHe
            ? '👶 ילדים ומסגרות חינוך (אופציונלי בתאריכים ידניים)'
            : '👶 Children & MoE Frameworks (Optional in Manual Dates)');
    }

    syncApplyProfileButtonLabel();

    const authDeleteConfirmText = document.getElementById('auth-delete-confirm-text');
    if (authDeleteConfirmText) {
      authDeleteConfirmText.textContent = isWp
        ? (isHe
            ? 'למחוק לצמיתות את נתוני הפרופיל השמורים בחשבון?'
            : 'Permanently delete your saved profile data?')
        : (isHe
            ? 'למחוק לצמיתות את נתוני המשפחה השמורים בחשבון?'
            : 'Permanently delete your saved family data?');
    }

    const calTitle = document.getElementById('zone-calendar-title');
    if (calTitle) {
      calTitle.textContent = isWp
        ? (isHe ? 'לוח חגים ומועדים במשק הישראלי' : 'Israeli Public & Workplace Holidays')
        : (isHe
            ? 'לוח חופשות משרד החינוך ולוח חגים ומועדים במשק'
            : 'School Vacations & Public / Workplace Holidays');
    }

    syncWorkplaceHolidayControlsVisibility();
    updateActiveModeBadge();
  }

  function applyLocaleStrings() {
    const isHe = state.locale === 'he';
    const dataAttr = isHe ? 'data-he' : 'data-en';
    const ariaAttr = isHe ? 'data-aria-he' : 'data-aria-en';

    document.querySelectorAll('[data-he][data-en]').forEach((el) => {
      const txt = el.getAttribute(dataAttr);
      if (txt !== null) {
        el.textContent = txt;
      }
    });

    document.querySelectorAll('[data-aria-he][data-aria-en]').forEach((el) => {
      const ariaTxt = el.getAttribute(ariaAttr);
      if (ariaTxt) {
        el.setAttribute('aria-label', ariaTxt);
      }
    });

    syncPlanningModeUi();
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: true,
      applyDurationDefault: false
    });
    syncWorkplaceHolidayControlsVisibility();

    const vtTitle = document.getElementById('vacation-type-title');
    if (vtTitle) {
      vtTitle.textContent = isHe
        ? '🌤️ סגנון חופשה ותיעדוף מזג אוויר ביעד:'
        : '🌤️ Vacation Style & Destination Weather Prioritization:';
    }
    const vtHint = document.getElementById('vacation-type-hint');
    if (vtHint) {
      vtHint.textContent = isHe
        ? 'בחרו סגנון חופשה אחד או יותר לתיעדוף מזג אוויר אידיאלי'
        : 'Select one or more styles to prioritize ideal destination weather';
    }
    const zSearch = document.getElementById('zone-search-title');
    if (zSearch) {
      zSearch.textContent = isHe
        ? 'חיפוש חופשה וכרטיסי בונוס'
        : 'Vacation & Award Flight Search';
    }

    syncSearchFiltersSummary();
    renderDestinationMultiSelect();
    setCalendarVisibility(state.isCalendarVisible, { focusContent: false, restoreFocus: false });
    renderProfileControls();
    renderCalendarTable();
    renderWorkplaceCalendarTable();
    renderProposals();
    if (state.isBookingHandoffOpen && state.bookingHandoffProposal) {
      renderBookingHandoffModalContent();
    }
    if (state.isSharePlanOpen && state.sharePlanProposal) {
      renderSharePlanModalContent();
    }
  }

  function collectActiveFrameworksCsv() {
    if (!state.profile || !Array.isArray(state.profile.children)) return '';
    const fws = state.profile.children
      .map((c) => (c && c.framework_type ? String(c.framework_type).trim() : ''))
      .filter(Boolean);
    return fws.join(',');
  }

  function refreshClientHolidaysOnProfileEdit() {
    latestHolidayFetchSeq += 1;
    const refIso = getAsOfOverrideIso() || getReferenceToday();
    const isWp = isWorkplaceModeProfile(state.profile);
    const nextMode = isWp ? 'workplace' : 'family';
    const modeChanged = state.lastPlanningMode !== nextMode;
    state.lastPlanningMode = nextMode;
    if (modeChanged && !state.userEditedMaxNights) {
      state.userEditedMinNights = false;
    }
    if (isWp) {
      state.workplaceCatalog = buildUpcomingWorkplaceCatalogClient(refIso);
      state.upcomingHolidays = buildUpcomingWorkplaceHolidaysClient(refIso);
    } else {
      state.upcomingHolidays = buildUpcomingHolidaysClient(refIso, state.profile);
    }
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: true,
      applyDurationDefault: !state.userEditedMaxNights && !state.userEditedMinNights
    });
  }

  async function scrubBrowserClientState() {
    try {
      sessionStorage.clear();
    } catch (_e1) {
      // Ignore storage access errors in restricted contexts
    }
    try {
      localStorage.clear();
    } catch (_e2) {
      // Ignore storage access errors in restricted contexts
    }
    if (typeof caches !== 'undefined' && typeof caches.keys === 'function') {
      try {
        const cacheNames = await caches.keys();
        await Promise.all(
          cacheNames.map(async (cName) => {
            const cacheObj = await caches.open(cName);
            const reqs = await cacheObj.keys();
            await Promise.all(
              reqs.map((req) => {
                try {
                  const u = new URL(req.url);
                  if (u.pathname.startsWith('/api/')) {
                    return cacheObj.delete(req);
                  }
                } catch (_uErr) {
                  // Ignore non-URL cache entries
                }
                return false;
              })
            );
          })
        );
      } catch (_cErr) {
        // Ignore CacheStorage errors
      }
    }
  }

  function startGoogleSignIn() {
    const canSignIn = Boolean(
      state.auth && (state.auth.oauthConfigured || state.auth.testMode)
    );
    if (!canSignIn) {
      state.authNoticeHe =
        'התחברות Gmail טרם הוגדרה בשרת זה (נדרשת הגדרת GOOGLE_OAUTH_CLIENT_ID בקובץ auth.env). ניתן להמשיך לחפש חופשות כאורחים.';
      state.authNoticeEn =
        'Gmail OAuth 2.0 is not configured on this server yet (set GOOGLE_OAUTH_CLIENT_ID in auth.env). You can continue searching as a guest.';
      renderAuthControls();
      setAuthPopoverOpen(true);
      return;
    }

    syncProfileStateFromDom();
    const hasDraftChanges = Boolean(
      state.profile &&
        (state.profileDirty ||
          Number(state.profile.adults_count || 2) !== 2 ||
          Number(state.profile.matmid_points_balance || 0) > 0 ||
          (Array.isArray(state.profile.children) && state.profile.children.length > 0))
    );
    if (hasDraftChanges && state.profile) {
      try {
        sessionStorage.setItem(
          'fvp_pending_oauth_draft',
          JSON.stringify({
            ts: Date.now(),
            adults_count: state.profile.adults_count,
            matmid_points_balance: state.profile.matmid_points_balance,
            children: (state.profile.children || []).map((c) => ({
              child_age_years: Number(c.child_age_years ?? 6),
              framework_type: c.framework_type || null
            }))
          })
        );
      } catch (_sErr) {
        // Ignore sessionStorage quota/privacy restrictions
      }
    }
    const loginUrl = `/api/v1/auth/google/login?lang=${encodeURIComponent(state.locale)}`;
    window.location.assign(loginUrl);
  }

  async function handleSignOut() {
    try {
      await apiSend('POST', '/api/v1/auth/logout', {});
    } catch (_logoutErr) {
      // Always complete client-side scrub even if session already expired
    }
    state.auth = {
      authenticated: false,
      isAdmin: false,
      oauthConfigured: Boolean(state.auth && state.auth.oauthConfigured),
      testMode: Boolean(state.auth && state.auth.testMode),
      csrfToken: null,
      user: null
    };
    state.adminBonusSync = null;
    state.isAdminSyncExpanded = true;
    state.isAdminSyncRefreshing = false;
    state.notificationsOptIn = false;
    state.authNoticeHe = null;
    state.authNoticeEn = null;
    state.saveFeedbackHe = null;
    state.saveFeedbackEn = null;
    state.confirmingDeleteProfile = false;
    state.validationErrorHe = null;
    state.validationErrorEn = null;
    state.profile = createCleanGuestProfile();
    state.profileDirty = false;
    state.lastPlanningMode = 'workplace';
    state.userSelectedHoliday = false;
    state.userEditedMaxNights = false;
    state.userEditedMinNights = false;
    state.calendarData = null;
    state.proposals = [];
    state.lastSearchProfile = null;
    state.showAllProposals = false;

    await scrubBrowserClientState();
    syncPlanningModeUi();
    renderProfileControls();
    renderCalendarTable();
    renderWorkplaceCalendarTable();
    renderProposals();
    await refreshUpcomingHolidaysFromServer(true);
    await loadCalendarForSchoolYear();
    await runVacationSearch();
  }

  async function handleDeleteSavedProfile() {
    if (!state.auth || !state.auth.authenticated) return;
    try {
      await apiSend('DELETE', '/api/v1/profile', {});
      state.profile = createCleanGuestProfile();
      state.profileDirty = false;
      state.lastPlanningMode = 'workplace';
      state.userSelectedHoliday = false;
      state.userEditedMaxNights = false;
      state.userEditedMinNights = false;
      state.calendarData = null;
      state.confirmingDeleteProfile = false;
      state.validationErrorHe = null;
      state.validationErrorEn = null;
      state.proposals = [];
      state.lastSearchProfile = null;
      state.showAllProposals = false;
      state.saveFeedbackHe = '✓ הנתונים השמורים נמחקו מהחשבון.';
      state.saveFeedbackEn = '✓ Saved profile data deleted from your account.';
      await scrubBrowserClientState();
      syncPlanningModeUi();
      renderProfileControls();
      renderCalendarTable();
      renderWorkplaceCalendarTable();
      renderProposals();
      await refreshUpcomingHolidaysFromServer(true);
      await loadCalendarForSchoolYear();
      await runVacationSearch();
    } catch (err) {
      if (err && err.status === 401) {
        await handleSignOut();
      }
    }
  }

  async function refreshUpcomingHolidaysFromServer(applyDefaultNights) {
    const myFetchSeq = ++latestHolidayFetchSeq;
    const refIso = getReferenceToday();
    const asOfOverride = getAsOfOverrideIso();
    const effectiveAsOf = asOfOverride || refIso;
    const isWp = isWorkplaceModeProfile(state.profile);
    const nextMode = isWp ? 'workplace' : 'family';
    const modeChanged = state.lastPlanningMode !== nextMode;
    state.lastPlanningMode = nextMode;
    if (modeChanged && !state.userEditedMaxNights) {
      state.userEditedMinNights = false;
    }

    let fetchedHolidays = null;
    if (isWp) {
      try {
        const upcomingRes = await apiGet(
          `/api/v1/workplace-calendar/upcoming?as_of=${encodeURIComponent(effectiveAsOf)}`
        );
        if (myFetchSeq !== latestHolidayFetchSeq || isWorkplaceModeProfile(state.profile) !== isWp) return;
        if (upcomingRes && Array.isArray(upcomingRes.holidays) && upcomingRes.holidays.length > 0) {
          fetchedHolidays = upcomingRes.holidays;
        }
        if (
          upcomingRes &&
          Array.isArray(upcomingRes.holiday_groups) &&
          upcomingRes.holiday_groups.length > 0
        ) {
          state.workplaceCatalog = {
            best_year_option: upcomingRes.best_year_option || null,
            holiday_groups: upcomingRes.holiday_groups,
            catalog_count: upcomingRes.catalog_count || 0,
            catalog_items: upcomingRes.catalog_items || []
          };
        } else {
          state.workplaceCatalog = buildUpcomingWorkplaceCatalogClient(effectiveAsOf);
        }
      } catch (_err) {
        if (myFetchSeq !== latestHolidayFetchSeq || isWorkplaceModeProfile(state.profile) !== isWp) return;
        fetchedHolidays = buildUpcomingWorkplaceHolidaysClient(effectiveAsOf);
        state.workplaceCatalog = buildUpcomingWorkplaceCatalogClient(effectiveAsOf);
      }
      if (!fetchedHolidays || fetchedHolidays.length === 0) {
        fetchedHolidays = buildUpcomingWorkplaceHolidaysClient(effectiveAsOf);
      }
      if (!state.workplaceCatalog) {
        state.workplaceCatalog = buildUpcomingWorkplaceCatalogClient(effectiveAsOf);
      }
    } else {
      const fwCsv = collectActiveFrameworksCsv();
      const qs = fwCsv
        ? `?as_of=${encodeURIComponent(effectiveAsOf)}&frameworks=${encodeURIComponent(fwCsv)}`
        : `?as_of=${encodeURIComponent(effectiveAsOf)}`;
      try {
        const upcomingRes = await apiGet(`/api/v1/moe-calendar/upcoming${qs}`);
        if (myFetchSeq !== latestHolidayFetchSeq || isWorkplaceModeProfile(state.profile) !== isWp) return;
        if (upcomingRes && Array.isArray(upcomingRes.holidays) && upcomingRes.holidays.length > 0) {
          fetchedHolidays = upcomingRes.holidays;
        }
      } catch (_err) {
        if (myFetchSeq !== latestHolidayFetchSeq || isWorkplaceModeProfile(state.profile) !== isWp) return;
        fetchedHolidays = buildUpcomingHolidaysClient(effectiveAsOf, state.profile);
      }
      if (!fetchedHolidays || fetchedHolidays.length === 0) {
        fetchedHolidays = buildUpcomingHolidaysClient(effectiveAsOf, state.profile);
      }
    }

    if (myFetchSeq !== latestHolidayFetchSeq || isWorkplaceModeProfile(state.profile) !== isWp) return;
    state.upcomingHolidays = fetchedHolidays;
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: state.userSelectedHoliday,
      applyDurationDefault:
        (Boolean(applyDefaultNights) || modeChanged) &&
        !state.userEditedMaxNights &&
        !state.userEditedMinNights
    });
  }

  async function loadCalendarForSchoolYear(refIsoOverride) {
    const refIso = refIsoOverride || getReferenceToday();
    const currentSy = inferSchoolYearForIso(refIso);
    const calFwCsv = collectActiveFrameworksCsv();
    const calPath = calFwCsv
      ? `/api/v1/moe-calendar/${currentSy}?frameworks=${encodeURIComponent(calFwCsv)}`
      : `/api/v1/moe-calendar/${currentSy}`;
    try {
      state.calendarData = await apiGet(calPath);
    } catch (_calErr) {
      state.calendarData = null;
    }
    renderCalendarTable();
    renderWorkplaceCalendarTable();
  }

  async function loadInitialData() {
    const refIso = getReferenceToday();
    initDefaultManualDates();
    setDateMode(state.dateSelectionMode);
    state.validationErrorHe = null;
    state.validationErrorEn = null;
    state.proposals = [];
    state.lastSearchProfile = null;
    state.showAllProposals = false;
    state.profile = createCleanGuestProfile();
    state.lastPlanningMode = 'workplace';
    syncPlanningModeUi();
    syncDestStateFromNativeSelect();
    renderDestinationMultiSelect();
    renderProfileControls();
    state.workplaceCatalog = buildUpcomingWorkplaceCatalogClient(getAsOfOverrideIso() || refIso);
    state.upcomingHolidays = buildUpcomingWorkplaceHolidaysClient(getAsOfOverrideIso() || refIso);
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: state.userSelectedHoliday,
      applyDurationDefault: !state.userEditedMaxNights && !state.userEditedMinNights
    });

    try {
      let sess = null;
      try {
        sess = await apiGet('/api/v1/auth/session');
      } catch (_sessErr) {
        sess = null;
      }

      if (sess && sess.authenticated && sess.user) {
        state.auth = {
          authenticated: true,
          isAdmin: Boolean(sess.is_admin),
          oauthConfigured: Boolean(sess.oauth_configured),
          emailShareConfigured: Boolean(sess.email_share_configured),
          testMode: Boolean(sess.test_mode),
          csrfToken: sess.csrf_token || null,
          user: sess.user
        };
        state.adminBonusSync =
          sess.is_admin && sess.admin_bonus_sync ? sess.admin_bonus_sync : null;
        state.notificationsOptIn = Boolean(sess.user.notifications_enabled);

        const loadedProfile = await apiGet('/api/v1/profile');
        loadedProfile.passenger_loyalty_wallets = [];

        let pendingDraft = null;
        try {
          const rawDraft = sessionStorage.getItem('fvp_pending_oauth_draft');
          sessionStorage.removeItem('fvp_pending_oauth_draft');
          if (rawDraft) {
            const parsedDraft = JSON.parse(rawDraft);
            if (parsedDraft && Date.now() - Number(parsedDraft.ts || 0) < 5 * 60 * 1000) {
              pendingDraft = parsedDraft;
            }
          }
        } catch (_dErr) {
          pendingDraft = null;
        }

        if (loadedProfile.is_persisted === false && pendingDraft) {
          loadedProfile.adults_count = Number(pendingDraft.adults_count || 2);
          loadedProfile.matmid_points_balance = Number(pendingDraft.matmid_points_balance || 0);
          loadedProfile.children = Array.isArray(pendingDraft.children)
            ? pendingDraft.children.map((ch) => {
                const ageVal = Number(ch.child_age_years ?? 6);
                return {
                  id: generateClientChildId(),
                  child_name: 'ילד/ה',
                  birth_date: null,
                  child_age_years: ageVal,
                  passenger_Current_type:
                    ageVal < 2 ? 'INFANT_LAP' : ageVal <= 11 ? 'CHILD' : 'YOUTH',
                  framework_type: ch.framework_type || null,
                  school_week_days: 5,
                  holiday_extension_mode: 'NITZANIM_FULL_WITH_JULY',
                  treat_camp_as_vacation: true,
                  bagrut_blackout_dates: []
                };
              })
            : [];
          try {
            const savedDraft = await apiSend('PUT', '/api/v1/profile', {
              ...loadedProfile,
              notifications_enabled: Boolean(state.notificationsOptIn)
            });
            savedDraft.passenger_loyalty_wallets = [];
            state.profile = savedDraft;
            state.profileDirty = false;
            const isWpSaved = isWorkplaceModeProfile(state.profile);
            state.saveFeedbackHe = isWpSaved
              ? '✓ הפרופיל נשמר בחשבון שלך.'
              : '✓ הפרופיל המשפחתי נשמר בחשבון שלך.';
            state.saveFeedbackEn = isWpSaved
              ? '✓ Profile saved to your account.'
              : '✓ Family profile saved to your account.';
          } catch (_autoSaveErr) {
            state.profile = loadedProfile;
            state.profileDirty = true;
          }
        } else {
          state.profile = loadedProfile;
          state.profileDirty = false;
        }
      } else {
        state.auth = {
          authenticated: false,
          isAdmin: false,
          oauthConfigured: Boolean(sess && sess.oauth_configured),
          testMode: Boolean(sess && sess.test_mode),
          csrfToken: null,
          user: null
        };
        state.adminBonusSync = null;
        state.notificationsOptIn = false;
        try {
          sessionStorage.removeItem('fvp_pending_oauth_draft');
        } catch (_rmErr) {
          // Ignore
        }
        state.profile = createCleanGuestProfile();
        state.profileDirty = false;
      }

      syncPlanningModeUi();
      renderProfileControls();
      await refreshUpcomingHolidaysFromServer(!state.userEditedMaxNights);
      await loadCalendarForSchoolYear(refIso);
      await runVacationSearch();
    } catch (err) {
      console.error('Initialization error:', err);
    }
  }

  async function runVacationSearch() {
    const mySearchSeq = ++latestSearchSeq;
    syncProfileStateFromDom();
    const destCodes = getSelectedDestinationCodes();
    const selectHolidayEl = document.getElementById('select-direct-holiday');
    const holidayVal =
      (selectHolidayEl && selectHolidayEl.value) ||
      (isWorkplaceModeProfile(state.profile) ? 'PESACH' : 'HANUKKAH');
    const selectedHolidayOpt =
      selectHolidayEl && selectHolidayEl.selectedOptions && selectHolidayEl.selectedOptions[0];
    const yearVal =
      selectedHolidayOpt && selectedHolidayOpt.dataset && selectedHolidayOpt.dataset.year
        ? Number(selectedHolidayOpt.dataset.year)
        : undefined;

    const refIso = getReferenceToday();
    const depVal = (document.getElementById('input-dep-date') || {}).value || addDaysIso(refIso, 21);
    const retVal = (document.getElementById('input-ret-date') || {}).value || addDaysIso(refIso, 28);
    const flexRaw = (document.getElementById('input-flex-days') || {}).value;
    const flexVal = flexRaw === '' || flexRaw === undefined ? 2 : Number(flexRaw);
    const minNightsInputVal = Number((document.getElementById('input-min-nights') || {}).value || 4);
    const maxNightsInputVal = Number((document.getElementById('input-max-nights') || {}).value || 7);
    const bridgeDays = Number((document.getElementById('input-bridge-days') || {}).value || 3);
    const matmidBalanceVal = syncHouseholdMatmidBalance(true);

    const weatherModeVal =
      (document.getElementById('select-weather-filter-mode') || {}).value ||
      state.weatherFilterMode ||
      'SOFT_PRIORITIZE';
    state.weatherFilterMode = weatherModeVal;

    let effectiveMinNights = minNightsInputVal;
    let effectiveMaxNights = maxNightsInputVal;
    if (state.dateSelectionMode === 'SPECIFIC_DATES') {
      const baseNights = diffDaysIso(depVal, retVal);
      const clampedFlex = Math.max(0, Math.min(7, Number.isFinite(flexVal) ? flexVal : 0));
      if (baseNights >= 1) {
        effectiveMinNights = Math.max(1, baseNights - 2 * clampedFlex);
        effectiveMaxNights = Math.min(45, Math.max(effectiveMinNights, baseNights + 2 * clampedFlex));
      } else {
        effectiveMinNights = 1;
        effectiveMaxNights = 7;
      }
    }

    const inlineChildren = ((state.profile && state.profile.children) || []).map((ch) => ({
      child_name: 'ילד/ה',
      birth_date: null,
      child_age_years: Number(ch.child_age_years ?? 6),
      passenger_Current_type: ch.passenger_Current_type || 'CHILD',
      framework_type: ch.framework_type || null,
      school_week_days: Number(ch.school_week_days || 5),
      holiday_extension_mode: ch.holiday_extension_mode || 'NITZANIM_FULL_WITH_JULY',
      treat_camp_as_vacation: ch.treat_camp_as_vacation !== false
    }));

    const payload = {
      date_selection_mode: state.dateSelectionMode,
      airline_selection_mode: 'EL_AL_ONLY',
      enabled_loyalty_programs: ['ELAL_MATMID'],
      matmid_points_balance: matmidBalanceVal,
      inline_profile: {
        adults_count: Number((state.profile && state.profile.adults_count) || 2),
        matmid_points_balance: matmidBalanceVal,
        children: inlineChildren
      },
      destination_iatas: destCodes,
      direct_holiday_code: holidayVal,
      specific_departure_date: depVal,
      specific_return_date: retVal,
      flex_days_plus_minus: flexVal,
      min_trip_nights: effectiveMinNights,
      max_trip_nights: effectiveMaxNights,
      max_bridge_days_shift: bridgeDays,
      preferred_vacation_types: state.selectedVacationTypes || [],
      weather_filter_mode: weatherModeVal
    };
    if (
      holidayVal !== 'BEST_YEAR_MAXIMIZER' &&
      yearVal !== undefined &&
      Number.isFinite(yearVal)
    ) {
      payload.direct_target_year = yearVal;
    }
    const isWpSearch = inlineChildren.length === 0;
    if (isWpSearch) {
      if (state.maxWorkdaysOffBudget !== null && Number.isFinite(state.maxWorkdaysOffBudget)) {
        payload.max_workdays_off = state.maxWorkdaysOffBudget;
      }
      if (holidayVal === 'BEST_YEAR_MAXIMIZER') {
        payload.as_of_date = getAsOfOverrideIso() || refIso;
      }
    }

    state.validationErrorHe = null;
    state.validationErrorEn = null;
    state.workdaysBudgetExceeded = false;

    try {
      const res = await apiSend('POST', '/api/v1/vacations/search', payload);
      if (mySearchSeq !== latestSearchSeq) return;
      state.lastSearchQuery = res.query || payload || null;
      state.lastSearchCalendarMode =
        res.calendar_mode || (inlineChildren.length === 0 ? 'WORKPLACE' : 'MOE');
      state.lastSearchProfile = {
        adults_count: payload.inline_profile.adults_count,
        matmid_points_balance: matmidBalanceVal,
        children: inlineChildren.map((c) => ({ ...c }))
      };
      state.proposals = res.proposals || [];
      state.showAllProposals = false;
      state.workdaysBudgetExceeded = Boolean(res.workdays_budget_exceeded);
      state.statusMessageHe = res.status_message_he || null;
      state.statusMessageEn = res.status_message_en || null;
      state.weatherFallbackMessageHe = res.weather_fallback_message_he || null;
    } catch (err) {
      if (mySearchSeq !== latestSearchSeq) return;
      const detail = extractApiErrorDetail(err);
      const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      state.proposals = [];
      state.lastSearchProfile = null;
      state.showAllProposals = false;
      state.validationErrorHe = `נא לוודא שטווח התאריכים ומספר הלילות בטופס החיפוש תקינים ולנסות שוב.${detailSuffixHe}`;
      state.validationErrorEn = `Verify that the return date is on or after the departure date and the nights range is valid, then try again.${detailSuffixEn}`;
    }
    renderProposals();
    syncSearchFiltersSummary();
  }

  function bindEvents() {
    document.querySelectorAll('.mode-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        setDateMode(btn.getAttribute('data-mode'));
      });
    });

    const btnDestToggle = document.getElementById('btn-dest-picker-toggle');
    if (btnDestToggle) {
      btnDestToggle.addEventListener('click', () => {
        setDestPickerOpen(!state.isDestPickerOpen);
      });
    }

    const inputDestFilterEl = document.getElementById('input-dest-filter');
    if (inputDestFilterEl) {
      inputDestFilterEl.addEventListener('input', () => {
        state.destFilterQuery = inputDestFilterEl.value || '';
        renderDestinationMultiSelect();
      });
    }

    const btnDestReset = document.getElementById('btn-dest-popover-reset');
    if (btnDestReset) {
      btnDestReset.addEventListener('click', () => {
        state.selectedDestinations = [];
        state.destFilterQuery = '';
        if (inputDestFilterEl) inputDestFilterEl.value = '';
        syncNativeSelectFromDestState();
        renderDestinationMultiSelect();
        runVacationSearch();
      });
    }

    const btnDestDone = document.getElementById('btn-dest-popover-done');
    if (btnDestDone) {
      btnDestDone.addEventListener('click', () => {
        setDestPickerOpen(false);
        runVacationSearch();
      });
    }

    const selectDestNative = document.getElementById('select-destination');
    if (selectDestNative) {
      selectDestNative.addEventListener('change', () => {
        syncDestStateFromNativeSelect();
        renderDestinationMultiSelect();
        runVacationSearch();
      });
    }

    const selectHolidayEl = document.getElementById('select-direct-holiday');
    if (selectHolidayEl) {
      selectHolidayEl.addEventListener('change', () => {
        state.userSelectedHoliday = true;
        state.userEditedMinNights = false;
        state.userEditedMaxNights = false;
        const opt = selectHolidayEl.selectedOptions && selectHolidayEl.selectedOptions[0];
        const days = opt && opt.dataset ? Number(opt.dataset.days || 7) : 7;
        const recDays =
          opt && opt.dataset && opt.dataset.recDays ? Number(opt.dataset.recDays) : days;
        const recMin =
          opt && opt.dataset && opt.dataset.recMinNights ? Number(opt.dataset.recMinNights) : undefined;
        const recMax =
          opt && opt.dataset && opt.dataset.recMaxNights ? Number(opt.dataset.recMaxNights) : undefined;
        const calMode =
          (opt && opt.dataset && opt.dataset.calendarMode) ||
          (isWorkplaceModeProfile(state.profile) ? 'WORKPLACE' : 'MOE');
        applyHolidayDurationDefault(
          {
            holidayCode: selectHolidayEl.value,
            holidayDays: days,
            recommendedTripDays: recDays,
            recommendedMinNights: recMin,
            recommendedMaxNights: recMax,
            calendarMode: calMode
          },
          { forceBoth: true }
        );
        syncBestYearQuickButton();
        renderWorkplaceHolidayBrief();
        updateActiveModeBadge();
      });
    }

    const btnBestYearQuick = document.getElementById('btn-best-year-quick');
    if (btnBestYearQuick) {
      btnBestYearQuick.addEventListener('click', () => {
        if (!isWorkplaceModeProfile(state.profile)) return;
        const sel = document.getElementById('select-direct-holiday');
        if (!sel) return;
        const hasBestYear = Array.from(sel.options || []).some((o) => o.value === 'BEST_YEAR_MAXIMIZER');
        if (!hasBestYear) return;
        sel.value = 'BEST_YEAR_MAXIMIZER';
        state.userSelectedHoliday = true;
        state.userEditedMinNights = false;
        state.userEditedMaxNights = false;
        const bestItem = findWorkplaceHolidayItem('BEST_YEAR_MAXIMIZER');
        applyHolidayDurationDefault(
          bestItem || {
            holidayCode: 'BEST_YEAR_MAXIMIZER',
            recommendedMinNights: 3,
            recommendedMaxNights: 15,
            calendarMode: 'WORKPLACE'
          },
          { forceBoth: true }
        );
        syncBestYearQuickButton();
        renderWorkplaceHolidayBrief();
        updateActiveModeBadge();
        runVacationSearch();
      });
    }

    const budgetPresetsWrap = document.getElementById('workday-budget-presets');
    if (budgetPresetsWrap) {
      budgetPresetsWrap.addEventListener('click', (ev) => {
        const pill =
          ev.target && typeof ev.target.closest === 'function'
            ? ev.target.closest('.budget-preset-pill')
            : null;
        if (!pill) return;
        const presetVal = pill.getAttribute('data-budget-preset');
        setWorkdaysBudgetValue(presetVal === '' ? null : presetVal, true);
      });
    }

    const inputMaxWorkdaysEl = document.getElementById('input-max-workdays-off');
    if (inputMaxWorkdaysEl) {
      inputMaxWorkdaysEl.addEventListener('input', () => {
        const raw = String(inputMaxWorkdaysEl.value || '').trim();
        if (raw === '') {
          setWorkdaysBudgetValue(null, false);
        } else {
          const parsed = Number(raw);
          if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 45) {
            state.maxWorkdaysOffBudget = parsed;
            syncWorkdaysBudgetUi();
            syncSearchFiltersSummary();
          }
        }
      });
      inputMaxWorkdaysEl.addEventListener('change', () => {
        const raw = String(inputMaxWorkdaysEl.value || '').trim();
        setWorkdaysBudgetValue(raw === '' ? null : raw, true);
      });
    }

    const btnClearBudget = document.getElementById('btn-clear-workdays-budget');
    if (btnClearBudget) {
      btnClearBudget.addEventListener('click', () => {
        setWorkdaysBudgetValue(null, true);
      });
    }

    const inputMaxNightsEl = document.getElementById('input-max-nights');
    if (inputMaxNightsEl) {
      const markMaxEdited = () => {
        state.userEditedMaxNights = true;
        syncSearchFiltersSummary();
      };
      inputMaxNightsEl.addEventListener('input', markMaxEdited);
      inputMaxNightsEl.addEventListener('change', markMaxEdited);
    }

    const inputMinNightsEl = document.getElementById('input-min-nights');
    if (inputMinNightsEl) {
      const markMinEdited = () => {
        state.userEditedMinNights = true;
        syncSearchFiltersSummary();
      };
      inputMinNightsEl.addEventListener('input', markMinEdited);
      inputMinNightsEl.addEventListener('change', markMinEdited);
    }

    const btnToggleFilters = document.getElementById('btn-toggle-search-filters');
    if (btnToggleFilters) {
      btnToggleFilters.addEventListener('click', () => {
        state.isSearchFiltersOpen = !state.isSearchFiltersOpen;
        syncSearchFiltersSummary();
      });
    }

    const inputDepDateEl = document.getElementById('input-dep-date');
    const inputRetDateEl = document.getElementById('input-ret-date');
    if (inputDepDateEl) {
      inputDepDateEl.addEventListener('change', () => {
        state.userEditedManualDates = true;
        if (inputRetDateEl && inputDepDateEl.value) {
          if (!inputRetDateEl.value || inputRetDateEl.value <= inputDepDateEl.value) {
            inputRetDateEl.value = addDaysIso(inputDepDateEl.value, 7);
          }
        }
      });
      inputDepDateEl.addEventListener('input', () => {
        state.userEditedManualDates = true;
      });
    }
    if (inputRetDateEl) {
      const markRetEdited = () => {
        state.userEditedManualDates = true;
      };
      inputRetDateEl.addEventListener('change', markRetEdited);
      inputRetDateEl.addEventListener('input', markRetEdited);
    }

    document.querySelectorAll('[data-vacation-type]').forEach((pillBtn) => {
      pillBtn.addEventListener('click', () => {
        const vt = pillBtn.getAttribute('data-vacation-type');
        if (!vt || vt === 'ANY') {
          state.selectedVacationTypes = [];
        } else {
          const cur = new Set(state.selectedVacationTypes || []);
          cur.delete('ANY');
          if (cur.has(vt)) {
            cur.delete(vt);
          } else {
            cur.add(vt);
          }
          state.selectedVacationTypes = Array.from(cur);
        }
        syncVacationTypePills();
        syncSearchFiltersSummary();
        runVacationSearch();
      });
    });

    const selectWeatherModeEl = document.getElementById('select-weather-filter-mode');
    if (selectWeatherModeEl) {
      selectWeatherModeEl.addEventListener('change', () => {
        state.weatherFilterMode = selectWeatherModeEl.value || 'SOFT_PRIORITIZE';
        runVacationSearch();
      });
    }

    const btnRunSearch = document.getElementById('btn-run-search');
    if (btnRunSearch) {
      btnRunSearch.addEventListener('click', async () => {
        setAuthPopoverOpen(false, { restoreFocus: false });
        setProfileSheetOpen(false, { restoreFocus: false });
        setCalendarVisibility(false, { restoreFocus: false });
        await runVacationSearch();
        if (typeof window !== 'undefined' && window.innerWidth < 1180) {
          state.lastActiveMobileZone = 'zone-results';
          document.querySelectorAll('.mobile-dock-btn').forEach((b) => {
            if (b.getAttribute('data-dock-zone') !== 'zone-calendar') {
              b.classList.toggle('active', b.getAttribute('data-dock-zone') === 'zone-results');
            }
          });
          const resultsZone = document.getElementById('zone-results');
          if (resultsZone) {
            resultsZone.scrollIntoView({ behavior: getScrollBehavior(), block: 'start' });
          }
        }
      });
    }

    const btnToggleLocale = document.getElementById('btn-toggle-locale');
    if (btnToggleLocale) {
      btnToggleLocale.addEventListener('click', () => {
        if (state.dir === 'rtl') {
          state.dir = 'ltr';
          state.locale = 'en';
          document.documentElement.setAttribute('dir', 'ltr');
          document.documentElement.setAttribute('lang', 'en');
          btnToggleLocale.textContent = 'עב';
        } else {
          state.dir = 'rtl';
          state.locale = 'he';
          document.documentElement.setAttribute('dir', 'rtl');
          document.documentElement.setAttribute('lang', 'he');
          btnToggleLocale.textContent = 'EN';
        }
        applyLocaleStrings();
      });
    }

    const profMatmidInput = document.getElementById('prof-matmid-points');
    if (profMatmidInput) {
      const onMatmidChange = () => {
        syncHouseholdMatmidBalance(true);
        state.profileDirty = true;
      };
      profMatmidInput.addEventListener('input', onMatmidChange);
      profMatmidInput.addEventListener('change', onMatmidChange);
    }

    const profAdultsInput = document.getElementById('prof-adults-count');
    if (profAdultsInput) {
      const onAdultsChange = () => {
        if (state.profile) {
          state.profile.adults_count = Number(profAdultsInput.value || 2);
          state.profileDirty = true;
          renderProfileControls();
        }
      };
      profAdultsInput.addEventListener('input', onAdultsChange);
      profAdultsInput.addEventListener('change', onAdultsChange);
    }

    const btnOpenProfileSheet = document.getElementById('btn-open-profile-sheet');
    if (btnOpenProfileSheet) {
      btnOpenProfileSheet.addEventListener('click', () => {
        setProfileSheetOpen(true, { focusMatmid: false, opener: btnOpenProfileSheet });
      });
    }

    const btnCloseProfileSheet = document.getElementById('btn-close-profile-sheet');
    if (btnCloseProfileSheet) {
      btnCloseProfileSheet.addEventListener('click', () => {
        setProfileSheetOpen(false);
      });
    }

    const profileBackdrop = document.getElementById('profile-sheet-backdrop');
    if (profileBackdrop) {
      profileBackdrop.addEventListener('click', () => {
        setProfileSheetOpen(false);
      });
    }

    const btnApplyProfileSheet = document.getElementById('btn-apply-profile-sheet');
    if (btnApplyProfileSheet) {
      btnApplyProfileSheet.addEventListener('click', async () => {
        syncProfileStateFromDom();
        state.validationErrorHe = null;
        state.validationErrorEn = null;
        state.profileSaveErrorHe = null;
        state.profileSaveErrorEn = null;
        renderProfileSaveError();

        if (state.auth && state.auth.authenticated) {
          try {
            const saveBody = {
              ...state.profile,
              notifications_enabled: Boolean(state.notificationsOptIn)
            };
            const saved = await apiSend('PUT', '/api/v1/profile', saveBody);
            saved.passenger_loyalty_wallets = [];
            state.profile = saved;
            state.profileDirty = false;
            const isWpSaved = isWorkplaceModeProfile(state.profile);
            state.saveFeedbackHe = isWpSaved
              ? '✓ הפרופיל נשמר בחשבון שלך.'
              : '✓ הפרופיל המשפחתי נשמר בחשבון שלך.';
            state.saveFeedbackEn = isWpSaved
              ? '✓ Profile saved to your account.'
              : '✓ Family profile saved to your account.';
          } catch (err) {
            if (err && err.status === 401) {
              await handleSignOut();
              return;
            }
            const detail = extractApiErrorDetail(err);
            const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
            const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
            state.proposals = [];
            state.lastSearchProfile = null;
            state.showAllProposals = false;
            const isWpErr = isWorkplaceModeProfile(state.profile);
            state.validationErrorHe = isWpErr
              ? `לא ניתן לשמור את הפרופיל — בדקו שמספר המבוגרים (1–6) ויתרת המתמיד תקינים.${detailSuffixHe}`
              : `לא ניתן לשמור את פרופיל המשפחה — בדקו שגילאי הילדים (0–18), מספר המבוגרים (1–6) ויתרת המתמיד תקינים.${detailSuffixHe}`;
            state.validationErrorEn = isWpErr
              ? `Could not save profile — verify adults count (1–6) and non-negative Matmid balance.${detailSuffixEn}`
              : `Could not save family profile — verify adults count (1–6), child ages (0–18), and non-negative Matmid balance.${detailSuffixEn}`;
            if (state.isProfileSheetOpen) {
              state.profileSaveErrorHe = state.validationErrorHe;
              state.profileSaveErrorEn = state.validationErrorEn;
              state.saveFeedbackHe = null;
              state.saveFeedbackEn = null;
              renderAuthControls();
            }
            renderProposals();
            return;
          }
        }

        syncPlanningModeUi();
        renderProfileControls();
        renderCalendarTable();
        renderWorkplaceCalendarTable();
        setProfileSheetOpen(false);
        await refreshUpcomingHolidaysFromServer(!state.userEditedMaxNights);
        if (state.auth && state.auth.authenticated) {
          await loadCalendarForSchoolYear();
        }
        await runVacationSearch();
        if (typeof window !== 'undefined' && window.innerWidth < 1180) {
          state.lastActiveMobileZone = 'zone-results';
          document.querySelectorAll('.mobile-dock-btn').forEach((b) => {
            if (b.getAttribute('data-dock-zone') !== 'zone-calendar') {
              b.classList.toggle('active', b.getAttribute('data-dock-zone') === 'zone-results');
            }
          });
          const resultsZone = document.getElementById('zone-results');
          if (resultsZone) {
            resultsZone.scrollIntoView({ behavior: getScrollBehavior(), block: 'start' });
          }
        }
      });
    }

    function syncKpiTooltipDirection(cellEl) {
      if (
        !cellEl ||
        !cellEl.classList ||
        !cellEl.classList.contains('kpi-cell') ||
        typeof window === 'undefined'
      ) {
        return;
      }
      const hdr = document.getElementById('app-header');
      const hdrBottom = hdr ? Math.max(0, hdr.getBoundingClientRect().bottom) : 56;
      const r = cellEl.getBoundingClientRect();
      const shouldOpenDown = r.top < hdrBottom + 255 && window.innerHeight - r.bottom > 220;
      cellEl.classList.toggle('is-tooltip-down', shouldOpenDown);
    }

    function closeAllKpiTooltips(exceptCell) {
      document.querySelectorAll('.kpi-cell.is-tooltip-open, .stub-weather-card.is-tooltip-open').forEach((el) => {
        if (el !== exceptCell) {
          el.classList.remove('is-tooltip-open');
        }
      });
      document.querySelectorAll('.stub-score-header.has-open-inline-kpi').forEach((hdrEl) => {
        if (!exceptCell || !hdrEl.contains(exceptCell)) {
          hdrEl.classList.remove('has-open-inline-kpi');
        }
      });
      document.querySelectorAll('.proposal-card.has-open-tooltip').forEach((cardEl) => {
        if (!exceptCell || !cardEl.contains(exceptCell)) {
          cardEl.classList.remove('has-open-tooltip');
        }
      });
    }

    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') {
        if (state.isSharePlanOpen) {
          closeSharePlanModal();
          return;
        }
        if (state.isBookingHandoffOpen) {
          closeBookingHandoffModal();
          return;
        }
        if (state.isDestPickerOpen) {
          setDestPickerOpen(false);
        }
        if (state.isAuthPopoverOpen) {
          setAuthPopoverOpen(false);
        }
        if (state.isProfileSheetOpen) {
          setProfileSheetOpen(false);
        }
        if (state.isCalendarVisible) {
          setCalendarVisibility(false);
        }
        closeAllKpiTooltips(null);
        if (
          document.activeElement &&
          document.activeElement.classList &&
          (document.activeElement.classList.contains('kpi-cell') ||
            document.activeElement.classList.contains('stub-weather-card'))
        ) {
          document.activeElement.blur();
        }
      }
    });

    const btnCloseSharePlan = document.getElementById('btn-close-share-plan');
    if (btnCloseSharePlan) {
      btnCloseSharePlan.addEventListener('click', () => {
        closeSharePlanModal();
      });
    }

    const sharePlanBackdrop = document.getElementById('share-plan-backdrop');
    if (sharePlanBackdrop) {
      sharePlanBackdrop.addEventListener('click', () => {
        closeSharePlanModal();
      });
    }

    const sharePlanBody = document.getElementById('share-plan-body');
    if (sharePlanBody) {
      sharePlanBody.addEventListener('click', async (ev) => {
        const t = ev.target;
        if (!t || typeof t.closest !== 'function') return;
        if (t.closest('#btn-share-google-signin')) {
          startGoogleSignIn();
          return;
        }
        if (t.closest('#btn-share-whatsapp') && state.sharePlanProposal) {
          await handleShareWhatsAppPdf();
          return;
        }
        if (t.closest('#btn-share-download-pdf') && state.sharePlanProposal) {
          handleDownloadSharePdf();
          return;
        }
      });

      sharePlanBody.addEventListener('input', (ev) => {
        const t = ev.target;
        if (!t) return;
        if (t.id === 'input-share-email-to') {
          state.sharePlanRecipientValue = String(t.value || '');
        } else if (t.id === 'input-share-email-note') {
          state.sharePlanNoteValue = String(t.value || '');
        }
      });

      sharePlanBody.addEventListener('submit', (ev) => {
        if (ev.target && ev.target.id === 'share-email-form') {
          ev.preventDefault();
          submitSharePlanEmail();
        }
      });
    }

    const btnCloseBookingHandoff = document.getElementById('btn-close-booking-handoff');
    if (btnCloseBookingHandoff) {
      btnCloseBookingHandoff.addEventListener('click', () => {
        closeBookingHandoffModal();
      });
    }

    const bookingHandoffBackdrop = document.getElementById('booking-handoff-backdrop');
    if (bookingHandoffBackdrop) {
      bookingHandoffBackdrop.addEventListener('click', () => {
        closeBookingHandoffModal();
      });
    }

    const inputBookingHandoffSuppress = document.getElementById('input-booking-handoff-suppress');
    if (inputBookingHandoffSuppress) {
      inputBookingHandoffSuppress.addEventListener('change', () => {
        setBookingHandoffSuppressed(Boolean(inputBookingHandoffSuppress.checked));
      });
    }

    const bookingHandoffCtaGroup = document.getElementById('booking-handoff-cta-group');
    if (bookingHandoffCtaGroup) {
      bookingHandoffCtaGroup.addEventListener('click', (ev) => {
        const ctaLink =
          ev.target && typeof ev.target.closest === 'function'
            ? ev.target.closest('a[data-handoff-cta]')
            : null;
        if (!ctaLink) return;
        closeBookingHandoffModal({ restoreFocus: true });
      });
    }

    const btnHeaderAuth = document.getElementById('btn-header-auth');
    if (btnHeaderAuth) {
      btnHeaderAuth.addEventListener('click', () => {
        setAuthPopoverOpen(!state.isAuthPopoverOpen, { opener: btnHeaderAuth });
      });
    }

    const btnHeaderAccount = document.getElementById('btn-header-account');
    if (btnHeaderAccount) {
      btnHeaderAccount.addEventListener('click', () => {
        setAuthPopoverOpen(!state.isAuthPopoverOpen, { opener: btnHeaderAccount });
      });
    }

    const btnGoogleSignin = document.getElementById('btn-google-signin');
    if (btnGoogleSignin) {
      btnGoogleSignin.addEventListener('click', () => {
        startGoogleSignIn();
      });
    }

    const btnHeaderSignout = document.getElementById('btn-header-signout');
    if (btnHeaderSignout) {
      btnHeaderSignout.addEventListener('click', () => {
        setAuthPopoverOpen(false, { restoreFocus: false });
        handleSignOut();
      });
    }

    const btnSignout = document.getElementById('btn-signout');
    if (btnSignout) {
      btnSignout.addEventListener('click', () => {
        handleSignOut();
      });
    }

    const btnDeleteProfile = document.getElementById('btn-delete-profile');
    if (btnDeleteProfile) {
      btnDeleteProfile.addEventListener('click', () => {
        state.confirmingDeleteProfile = !state.confirmingDeleteProfile;
        renderAuthControls();
      });
    }

    const btnCancelDelete = document.getElementById('btn-cancel-delete-profile');
    if (btnCancelDelete) {
      btnCancelDelete.addEventListener('click', () => {
        state.confirmingDeleteProfile = false;
        renderAuthControls();
      });
    }

    const btnConfirmDelete = document.getElementById('btn-confirm-delete-profile');
    if (btnConfirmDelete) {
      btnConfirmDelete.addEventListener('click', () => {
        handleDeleteSavedProfile();
      });
    }

    const inputNotifOptIn = document.getElementById('input-notifications-opt-in');
    if (inputNotifOptIn) {
      inputNotifOptIn.addEventListener('change', async () => {
        state.notificationsOptIn = Boolean(inputNotifOptIn.checked);
        if (state.auth && state.auth.authenticated) {
          try {
            const res = await apiSend('PUT', '/api/v1/auth/notifications', {
              notifications_enabled: state.notificationsOptIn,
              notification_preferences: {
                award_seat_alerts: state.notificationsOptIn,
                holiday_reminders: state.notificationsOptIn,
                preferred_locale: state.locale === 'en' ? 'en' : 'he'
              }
            });
            if (res && res.user) {
              state.auth.user = res.user;
            }
            state.saveFeedbackHe = state.notificationsOptIn
              ? '✓ העדפת ההתראות נשמרה בחשבון.'
              : '✓ התראות עתידיות כובו.';
            state.saveFeedbackEn = state.notificationsOptIn
              ? '✓ Notification readiness preference saved.'
              : '✓ Future email notifications disabled.';
            renderAuthControls();
          } catch (err) {
            if (err && err.status === 401) {
              await handleSignOut();
            }
          }
        }
      });
    }

    const btnAddChild = document.getElementById('btn-add-child');
    if (btnAddChild) {
      btnAddChild.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (!state.profile) state.profile = createCleanGuestProfile();
        const detailsEl = btnAddChild.closest('details');
        if (detailsEl) detailsEl.open = true;
        const defaultAge = 7;
        state.profile.children.push({
          id: generateClientChildId(),
          child_name: 'ילד/ה',
          birth_date: null,
          child_age_years: defaultAge,
          passenger_Current_type: 'CHILD',
          framework_type: suggestFrameworkByAge(defaultAge),
          school_week_days: 5,
          holiday_extension_mode: 'NITZANIM_FULL_WITH_JULY',
          treat_camp_as_vacation: true,
          bagrut_blackout_dates: []
        });
        state.profileDirty = true;
        syncPlanningModeUi();
        renderProfileControls();
        refreshClientHolidaysOnProfileEdit();
        renderCalendarTable();
        renderWorkplaceCalendarTable();
      });
    }

    document.body.addEventListener('input', (ev) => {
      const target = ev.target;
      if (!target || !state.profile) return;
      if (target.hasAttribute('data-child-age')) {
        const idx = Number(target.getAttribute('data-child-age'));
        if (state.profile.children[idx] && target.value !== '') {
          const newAge = Number(target.value);
          state.profile.children[idx].child_age_years = newAge;
          state.profile.children[idx].passenger_Current_type =
            newAge < 2 ? 'INFANT_LAP' : newAge <= 11 ? 'CHILD' : 'YOUTH';
          state.profileDirty = true;
        }
      }
    });

    document.body.addEventListener('change', (ev) => {
      const target = ev.target;
      if (!target || !state.profile) return;
      if (target.hasAttribute('data-child-age')) {
        const idx = Number(target.getAttribute('data-child-age'));
        const newAge = Number(target.value || 0);
        state.profile.children[idx].child_age_years = newAge;
        state.profile.children[idx].passenger_Current_type =
          newAge < 2 ? 'INFANT_LAP' : newAge <= 11 ? 'CHILD' : 'YOUTH';
        if (
          state.profile.children[idx].framework_type !== null ||
          state.dateSelectionMode !== 'SPECIFIC_DATES'
        ) {
          state.profile.children[idx].framework_type = suggestFrameworkByAge(newAge);
        }
        state.profileDirty = true;
        renderProfileControls();
        refreshClientHolidaysOnProfileEdit();
      } else if (target.hasAttribute('data-child-fw')) {
        const idx = Number(target.getAttribute('data-child-fw'));
        const val = target.value;
        state.profile.children[idx].framework_type = val === '' ? null : val;
        state.profileDirty = true;
        refreshClientHolidaysOnProfileEdit();
      }
    });

    document.body.addEventListener('click', (ev) => {
      const target = ev.target;
      if (!target) return;
      const shareTriggerBtn =
        typeof target.closest === 'function'
          ? target.closest('[data-share-plan-trigger="true"]')
          : null;
      if (shareTriggerBtn) {
        const idx = Number(shareTriggerBtn.getAttribute('data-proposal-idx'));
        const proposal =
          Number.isInteger(idx) && idx >= 0 ? state.visibleRenderableProposals[idx] : null;
        if (proposal) {
          openSharePlanModal(proposal, { opener: shareTriggerBtn });
        }
        return;
      }
      const guideTriggerBtn =
        typeof target.closest === 'function'
          ? target.closest('[data-booking-guide-trigger="true"]')
          : null;
      if (guideTriggerBtn) {
        const idx = Number(guideTriggerBtn.getAttribute('data-proposal-idx'));
        const proposal =
          Number.isInteger(idx) && idx >= 0 ? state.visibleRenderableProposals[idx] : null;
        if (proposal) {
          openBookingHandoffModal(proposal, { opener: guideTriggerBtn });
        }
        return;
      }
      const elalBookLink =
        typeof target.closest === 'function'
          ? target.closest('a.btn-elal-book[data-elal-book-link="true"]')
          : null;
      if (elalBookLink) {
        const isUnmodifiedLeft =
          ev.button === 0 &&
          !ev.metaKey &&
          !ev.ctrlKey &&
          !ev.shiftKey &&
          !ev.altKey &&
          !ev.defaultPrevented;
        if (isUnmodifiedLeft && !isBookingHandoffSuppressed()) {
          const idx = Number(elalBookLink.getAttribute('data-proposal-idx'));
          const proposal =
            Number.isInteger(idx) && idx >= 0 ? state.visibleRenderableProposals[idx] : null;
          if (proposal) {
            ev.preventDefault();
            openBookingHandoffModal(proposal, { opener: elalBookLink });
            return;
          }
        }
        return;
      }
      const destOptBtn = target.closest('[data-dest-option]');
      if (destOptBtn) {
        const optCode = destOptBtn.getAttribute('data-dest-option');
        toggleDestinationSelection(optCode, true);
        if (optCode === 'ANYWHERE') {
          setDestPickerOpen(false);
        }
        return;
      }
      const removeDestBtn = target.closest('[data-remove-dest]');
      if (removeDestBtn) {
        toggleDestinationSelection(removeDestBtn.getAttribute('data-remove-dest'), true);
        return;
      }
      const clearAllDestBtn = target.closest('#btn-dest-clear-all');
      if (clearAllDestBtn) {
        toggleDestinationSelection('ANYWHERE', true);
        return;
      }
      if (state.isDestPickerOpen && !target.closest('#destination-multiselect')) {
        setDestPickerOpen(false);
      }
      if (state.isAuthPopoverOpen && !target.closest('#header-auth-wrap')) {
        setAuthPopoverOpen(false, { restoreFocus: false });
      }
      const focusMatmidBtn = target.closest('[data-focus-matmid]');
      if (focusMatmidBtn) {
        setProfileSheetOpen(true, { focusMatmid: true, opener: focusMatmidBtn });
        return;
      }
      const clearBudgetEmptyBtn = target.closest('#btn-empty-clear-budget');
      if (clearBudgetEmptyBtn) {
        setWorkdaysBudgetValue(null, true);
        return;
      }
      const toggleFeedBtn = target.closest('[data-toggle-all-proposals]');
      if (toggleFeedBtn) {
        state.showAllProposals = !state.showAllProposals;
        renderProposals();
        return;
      }
      const kpiCellEl =
        typeof target.closest === 'function'
          ? target.closest('.kpi-cell, .stub-weather-card')
          : null;
      if (kpiCellEl) {
        syncKpiTooltipDirection(kpiCellEl);
        const willOpen = !kpiCellEl.classList.contains('is-tooltip-open');
        closeAllKpiTooltips(willOpen ? kpiCellEl : null);
        kpiCellEl.classList.toggle('is-tooltip-open', willOpen);
        const parentScoreHdr = kpiCellEl.closest('.stub-score-header');
        if (parentScoreHdr) {
          parentScoreHdr.classList.toggle('has-open-inline-kpi', willOpen);
        }
        const parentCard = kpiCellEl.closest('.proposal-card');
        if (parentCard) {
          parentCard.classList.toggle('has-open-tooltip', willOpen);
        }
        return;
      }
      closeAllKpiTooltips(null);
      if (!state.profile) return;
      const removeChildBtn = target.closest('[data-remove-child]');
      if (removeChildBtn) {
        const idx = Number(removeChildBtn.getAttribute('data-remove-child'));
        state.profile.children.splice(idx, 1);
        state.profileDirty = true;
        syncPlanningModeUi();
        renderProfileControls();
        refreshClientHolidaysOnProfileEdit();
        renderCalendarTable();
        renderWorkplaceCalendarTable();
      }
    });

    document.body.addEventListener('pointerover', (ev) => {
      if (ev.pointerType && ev.pointerType !== 'mouse') return;
      const target = ev.target;
      if (!target || typeof target.closest !== 'function') return;
      const hoveredKpi = target.closest('.kpi-cell, .stub-weather-card');
      if (hoveredKpi) {
        syncKpiTooltipDirection(hoveredKpi);
        closeAllKpiTooltips(hoveredKpi);
      }
    });

    document.body.addEventListener('focusin', (ev) => {
      const target = ev.target;
      if (!target || typeof target.closest !== 'function') return;
      const focusedKpi = target.closest('.kpi-cell');
      if (focusedKpi) {
        syncKpiTooltipDirection(focusedKpi);
      }
    });

    const btnSyncMoe = document.getElementById('btn-sync-moe-year');
    if (btnSyncMoe) {
      btnSyncMoe.addEventListener('click', async () => {
        try {
          const sy = inferSchoolYearForIso(getReferenceToday());
          await apiSend('POST', `/api/v1/moe-calendar/sync/${sy}`, { force_remote_check: false });
          state.calendarData = await apiGet(`/api/v1/moe-calendar/${sy}`);
          renderCalendarTable();
          renderWorkplaceCalendarTable();
        } catch (err) {
          console.error('MoE calendar sync failed:', err);
        }
      });
    }

    const btnSyncElal = document.getElementById('btn-sync-elal');
    if (btnSyncElal) {
      btnSyncElal.addEventListener('click', async () => {
        try {
          const destCodes = getSelectedDestinationCodes();
          const refIso = getReferenceToday();
          await apiSend('POST', '/api/v1/elal-bonus/sync', {
            destinations: destCodes,
            start_date: refIso,
            end_date: addDaysIso(refIso, 30),
            origin: 'TLV',
            force_refresh: true
          });
          await runVacationSearch();
        } catch (err) {
          console.error('EL AL sync failed:', err);
        }
      });
    }

    const btnCloseCal = document.getElementById('btn-close-calendar');
    if (btnCloseCal) {
      btnCloseCal.addEventListener('click', () => {
        setCalendarVisibility(false);
      });
    }

    const calModalBackdrop = document.getElementById('calendar-modal-backdrop');
    if (calModalBackdrop) {
      calModalBackdrop.addEventListener('click', () => {
        setCalendarVisibility(false);
      });
    }

    document.querySelectorAll('.desktop-nav-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const zoneId = btn.getAttribute('data-desktop-zone');
        if (zoneId === 'zone-calendar') {
          setCalendarVisibility(!state.isCalendarVisible, { opener: btn });
          return;
        }
        setCalendarVisibility(false, { restoreFocus: false });
        document.querySelectorAll('.desktop-nav-btn').forEach((b) => {
          if (b.getAttribute('data-desktop-zone') !== 'zone-calendar') {
            b.classList.remove('active');
          }
        });
        btn.classList.add('active');
        const el = document.getElementById(zoneId);
        if (el) el.scrollIntoView({ behavior: getScrollBehavior() });
      });
    });

    document.querySelectorAll('.mobile-dock-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const zoneId = btn.getAttribute('data-dock-zone');
        if (zoneId === 'zone-calendar') {
          setProfileSheetOpen(false, { restoreFocus: false });
          setCalendarVisibility(!state.isCalendarVisible, { opener: btn });
          return;
        }
        if (zoneId === 'zone-profile') {
          setCalendarVisibility(false, { restoreFocus: false });
          setProfileSheetOpen(!state.isProfileSheetOpen, { focusMatmid: false });
          return;
        }
        state.lastActiveMobileZone = zoneId;
        setCalendarVisibility(false, { restoreFocus: false });
        setProfileSheetOpen(false);
        document.querySelectorAll('.mobile-dock-btn').forEach((b) => {
          if (b.getAttribute('data-dock-zone') !== 'zone-calendar') {
            b.classList.remove('active');
          }
        });
        btn.classList.add('active');
        const el = document.getElementById(zoneId);
        if (el) el.scrollIntoView({ behavior: getScrollBehavior(), block: 'start' });
      });
    });

    bindKeyboardViewportGuard();

    document.querySelectorAll('.mobile-nav-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.mobile-nav-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        const zoneId = btn.getAttribute('data-mobile-zone');
        const el = document.getElementById(zoneId);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      });
    });
  }

  if (typeof window !== 'undefined') {
    window.__fvpSetReferenceDate = async function (isoDate) {
      window.__FVP_REFERENCE_DATE__ = isoDate;
      state.userSelectedHoliday = false;
      state.userEditedMaxNights = false;
      state.userEditedMinNights = false;
      state.userEditedManualDates = false;
      await loadInitialData();
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    loadInitialData();
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  });
})();

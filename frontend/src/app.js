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

  function generateClientChildId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `child-${crypto.randomUUID()}`;
    }
    return `child-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }

  const state = {
    locale: 'he',
    dir: 'rtl',
    dateSelectionMode: 'HOLIDAY_DIRECT_INTENT',
    airlineSelectionMode: 'EL_AL_ONLY',
    selectedVacationTypes: [],
    weatherFilterMode: 'SOFT_PRIORITIZE',
    weatherFallbackMessageHe: null,
    validationErrorHe: null,
    validationErrorEn: null,
    isCalendarVisible: false,
    isSearchFiltersOpen: false,
    isProfileSheetOpen: false,
    lastActiveMobileZone: 'zone-search',
    isDestPickerOpen: false,
    destFilterQuery: '',
    selectedDestinations: [],
    showAllProposals: false,
    auth: {
      authenticated: false,
      oauthConfigured: false,
      testMode: false,
      csrfToken: null,
      user: null
    },
    notificationsOptIn: false,
    authNoticeHe: null,
    authNoticeEn: null,
    saveFeedbackHe: null,
    saveFeedbackEn: null,
    confirmingDeleteProfile: false,
    profile: createCleanGuestProfile(),
    profileDirty: false,
    upcomingHolidays: [],
    userSelectedHoliday: false,
    userEditedMaxNights: false,
    userEditedMinNights: false,
    userEditedManualDates: false,
    calendarData: null,
    proposals: []
  };

  let latestSearchSeq = 0;

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

  function setCalendarVisibility(visible, scrollToIt) {
    state.isCalendarVisible = Boolean(visible);
    const calZone = document.getElementById('zone-calendar');
    const isHe = state.locale === 'he';
    if (calZone) {
      if (state.isCalendarVisible) {
        calZone.removeAttribute('hidden');
        calZone.style.display = 'block';
        if (scrollToIt) {
          calZone.scrollIntoView({ behavior: getScrollBehavior(), block: 'start' });
        }
      } else {
        calZone.setAttribute('hidden', '');
        calZone.style.display = 'none';
      }
    }
    const btnTop = document.getElementById('btn-toggle-calendar');
    if (btnTop) {
      btnTop.classList.toggle('active', state.isCalendarVisible);
      btnTop.textContent = state.isCalendarVisible
        ? isHe
          ? '📅 הסתר לוח'
          : '📅 Hide Calendar'
        : isHe
          ? '📅 לוח חופשות'
          : '📅 MoE Calendar';
    }
    const dockCalBtn = document.getElementById('btn-mobile-dock-calendar');
    if (dockCalBtn) {
      dockCalBtn.classList.toggle('active', state.isCalendarVisible);
      const dockLabel = dockCalBtn.querySelector('.mobile-dock-label');
      if (dockLabel) {
        dockLabel.textContent = state.isCalendarVisible
          ? isHe
            ? 'הסתר לוח'
            : 'Hide'
          : isHe
            ? 'חופשות'
            : 'Calendar';
      }
    }
  }

  function setProfileSheetOpen(open, opts) {
    const options = opts || {};
    const isSheetViewport = typeof window !== 'undefined' && window.innerWidth < 1180;
    const profZone = document.getElementById('zone-profile');
    const backdrop = document.getElementById('profile-sheet-backdrop');
    const btnHeaderHh = document.getElementById('btn-header-household');
    const dockProfBtn = document.querySelector('.mobile-dock-btn[data-dock-zone="zone-profile"]');

    if (!isSheetViewport) {
      state.isProfileSheetOpen = false;
      if (profZone) profZone.classList.remove('is-sheet-open');
      if (backdrop) {
        backdrop.setAttribute('hidden', '');
        backdrop.style.display = 'none';
      }
      document.body.classList.remove('is-sheet-locked');
      if (btnHeaderHh) btnHeaderHh.setAttribute('aria-expanded', 'false');
      if (dockProfBtn) dockProfBtn.classList.remove('active');
      if (open) {
        if (profZone) profZone.scrollIntoView({ behavior: getScrollBehavior(), block: 'start' });
        const focusTarget = document.getElementById(
          options.focusMatmid ? 'prof-matmid-points' : 'prof-adults-count'
        );
        if (focusTarget) {
          setTimeout(() => {
            focusTarget.focus();
            if (options.focusMatmid && typeof focusTarget.select === 'function') {
              focusTarget.select();
            }
          }, 80);
        }
      }
      return;
    }

    state.isProfileSheetOpen = Boolean(open);
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
    document.body.classList.toggle('is-sheet-locked', state.isProfileSheetOpen);
    if (btnHeaderHh) {
      btnHeaderHh.setAttribute('aria-expanded', state.isProfileSheetOpen ? 'true' : 'false');
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
    if (state.isProfileSheetOpen && options.focusMatmid) {
      const matmidEl = document.getElementById('prof-matmid-points');
      if (matmidEl) {
        setTimeout(() => {
          matmidEl.focus();
          if (typeof matmidEl.select === 'function') matmidEl.select();
        }, 90);
      }
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
      const nightsLabel = isHe ? `🌙 ${minN}–${maxN} לילות` : `🌙 ${minN}–${maxN} nights`;
      summaryEl.textContent = `${styleLabel} · ${nightsLabel}`;
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
        if (
          window.innerWidth >= 1180 &&
          (state.isProfileSheetOpen || document.body.classList.contains('is-sheet-locked'))
        ) {
          setProfileSheetOpen(false);
        }
      });
      if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
          if (
            window.innerWidth >= 1180 &&
            (state.isProfileSheetOpen || document.body.classList.contains('is-sheet-locked'))
          ) {
            setProfileSheetOpen(false);
          }
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

  function formatRecommendationTierLabel(tierCode) {
    const code = String(tierCode || '');
    const isHe = state.locale === 'he';
    if (code === 'RECOMMENDED') return isHe ? '🌟 החופשה המומלצת ביותר' : '🌟 Best Overall Vacation';
    if (code === 'TOP_CHOICE') return isHe ? '✨ בחירה מובילה' : '✨ Top Choice';
    return isHe ? '🏖️ חלופה מומלצת' : '🏖️ Alternative Option';
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

  function applyHolidayDurationDefault(holidayDays) {
    const daysNum = Math.min(45, Math.max(1, Math.round(Number(holidayDays) || 7)));
    const maxInput = document.getElementById('input-max-nights');
    const minInput = document.getElementById('input-min-nights');
    if (maxInput) {
      maxInput.value = String(daysNum);
    }
    if (minInput) {
      if (!state.userEditedMinNights) {
        minInput.value = String(Math.min(4, daysNum));
      } else if (Number(minInput.value || 1) > daysNum) {
        minInput.value = String(daysNum);
      }
    }
    syncSearchFiltersSummary();
  }

  function populateHolidaySelector(holidaysList, opts) {
    const options = opts || {};
    const selectEl = document.getElementById('select-direct-holiday');
    if (!selectEl || !Array.isArray(holidaysList) || holidaysList.length === 0) return;

    const prevVal = selectEl.value;
    const isHe = state.locale === 'he';
    const hasPrev =
      Boolean(options.preserveSelection) &&
      holidaysList.some((h) => h.holiday_code === prevVal);
    const activeCode = hasPrev ? prevVal : holidaysList[0].holiday_code;

    selectEl.innerHTML = holidaysList
      .map((h) => {
        const selAttr = h.holiday_code === activeCode ? ' selected' : '';
        const text = isHe ? h.label_he : h.label_en;
        return `<option value="${escapeHtml(h.holiday_code)}"${selAttr} data-year="${escapeHtml(h.target_year)}" data-days="${escapeHtml(h.holiday_days)}" data-start="${escapeHtml(h.start_date)}" data-end="${escapeHtml(h.end_date)}" data-he="${escapeHtml(h.label_he)}" data-en="${escapeHtml(h.label_en)}">${escapeHtml(text)}</option>`;
      })
      .join('');

    selectEl.value = activeCode;
    if (options.applyDurationDefault) {
      const chosen = holidaysList.find((h) => h.holiday_code === activeCode) || holidaysList[0];
      applyHolidayDurationDefault(chosen.holiday_days);
    }
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
    const fmtCompact = (n) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));

    const compactChip = document.getElementById('header-household-compact');
    if (compactChip) {
      compactChip.setAttribute('dir', 'ltr');
      compactChip.textContent = `${adults}+${kids} · ${fmtCompact(matmidTotal)}`;
    }

    const summaryText = document.getElementById('household-summary-text');
    if (summaryText) {
      const aNum = `<span class="num">${escapeHtml(adults)}</span>`;
      const kNum = `<span class="num">${escapeHtml(kids)}</span>`;
      const pNum = `<span class="num">${escapeHtml(matmidTotal.toLocaleString())}</span>`;
      summaryText.innerHTML = isHe
        ? `👨‍👩‍👧‍👦 ${aNum} מבוגרים · ${kNum} ילדים · 💳 ${pNum} מתמיד`
        : `👨‍👩‍👧‍👦 ${aNum} Adults · ${kNum} Kids · 💳 ${pNum} Matmid`;
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

    const ptsPill = document.getElementById('header-points-pill');
    if (ptsPill) {
      const fmtCompact = (n) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));
      ptsPill.setAttribute('dir', 'ltr');
      ptsPill.setAttribute('title', `${matmidTotal.toLocaleString()} El Al Matmid Points`);
      ptsPill.textContent = `${fmtCompact(matmidTotal)} Matmid`;
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

  function renderAuthControls() {
    const isHe = state.locale === 'he';
    const isAuthed = Boolean(state.auth && state.auth.authenticated && state.auth.user);

    const btnHeaderAuth = document.getElementById('btn-header-auth');
    const btnHeaderSignout = document.getElementById('btn-header-signout');
    if (btnHeaderAuth) {
      if (isAuthed) {
        btnHeaderAuth.setAttribute('hidden', '');
        btnHeaderAuth.style.display = 'none';
      } else {
        btnHeaderAuth.removeAttribute('hidden');
        btnHeaderAuth.style.display = 'inline-flex';
        btnHeaderAuth.textContent = isHe ? 'כניסה' : 'Sign in';
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
      emailEl.textContent = isAuthed && state.auth.user ? String(state.auth.user.email || '') : '';
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

    const feedbackEl = document.getElementById('auth-save-feedback');
    if (feedbackEl) {
      const fbMsg = isHe ? state.saveFeedbackHe : state.saveFeedbackEn;
      if (isAuthed && fbMsg) {
        feedbackEl.textContent = fbMsg;
        feedbackEl.removeAttribute('hidden');
        feedbackEl.style.display = 'block';
      } else {
        feedbackEl.textContent = '';
        feedbackEl.setAttribute('hidden', '');
        feedbackEl.style.display = 'none';
      }
    }

    const btnSaveProfile = document.getElementById('btn-save-profile');
    if (btnSaveProfile) {
      if (isAuthed) {
        const heSave = '💾 שמור ועדכן';
        const enSave = '💾 Save & Refresh';
        btnSaveProfile.setAttribute('data-he', heSave);
        btnSaveProfile.setAttribute('data-en', enSave);
        btnSaveProfile.textContent = isHe ? heSave : enSave;
        btnSaveProfile.removeAttribute('hidden');
        btnSaveProfile.style.display = 'inline-flex';
      } else {
        btnSaveProfile.setAttribute('hidden', '');
        btnSaveProfile.style.display = 'none';
      }
    }
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

    const famPill = document.getElementById('header-family-pill');
    if (famPill) {
      // Words render in the body face; only the numerals keep the telemetry face (`.num`)
      const adultsNum = `<span class="num">${escapeHtml(state.profile.adults_count)}</span>`;
      const childrenNum = `<span class="num">${escapeHtml(state.profile.children.length)}</span>`;
      famPill.setAttribute('dir', 'auto');
      famPill.innerHTML = isHe
        ? `${adultsNum} מבוגרים + ${childrenNum} ילדים`
        : `${adultsNum} Adults + ${childrenNum} Children`;
    }
    syncHouseholdDisplaySummary();

    const childrenContainer = document.getElementById('children-list-container');
    if (childrenContainer) {
      const isOptionalMode = state.dateSelectionMode === 'SPECIFIC_DATES';
      if (!state.profile.children || state.profile.children.length === 0) {
        const emptyHint = isHe
          ? 'אין ילדים מוגדרים כרגע — לחצו "+ ילד/ה" להוספת גיל ומסגרת חינוך.'
          : 'No children added yet — click "+ Add Child" to add ages & school frameworks.';
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
    if (!state.calendarData) {
      tbody.innerHTML = '';
      if (syncBadge) syncBadge.textContent = '';
      return;
    }

    const isHe = state.locale === 'he';
    if (syncBadge) {
      const syncSourceLabel = state.calendarData.calendar_sync_source === 'OFFICIAL_MOE_CIRCULAR'
        ? (isHe ? 'חוזר מנכ״ל משרד החינוך' : 'Official MoE Circular')
        : state.calendarData.calendar_sync_source;
      // School year stays in the telemetry face; the worded source label renders in the body face
      syncBadge.innerHTML = `<span class="num" dir="ltr">${escapeHtml(state.calendarData.school_year)}</span> | ${escapeHtml(syncSourceLabel)}`;
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

    const prof = state.profile || {};
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
        ? `Flights to ${destPlace} from ${origPlace} on ${depIso} through ${retIso} with ${paxPhrase} nonstop`
        : `One way flights to ${destPlace} from ${origPlace} on ${depIso} with ${paxPhrase} nonstop`;

    const params = new URLSearchParams();
    params.set('q', qStr);
    params.set('curr', 'USD');
    params.set('gl', 'IL');
    params.set('hl', 'en');
    return `https://www.google.com/travel/flights?${params.toString()}`;
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

  function renderWeatherTooltipHtml(tooltipId, wm, cityTitle, wssVal, isHe) {
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

    const fallbackStyles = recList.length > 0 ? recList.slice(0, 2) : [primaryStyle];
    const fallbackRecText = isHe
      ? fallbackStyles
          .map((vt) => {
            const code = String(vt || '').toUpperCase();
            const lbl = formatVacationTypeBadge(code);
            const idea = WEATHER_STYLE_ACTIVITIES_FALLBACK_HE[code] || '';
            return idea ? `${lbl} — ${idea}` : lbl;
          })
          .join(' · ')
      : `In ${cityTitle}: ` +
        fallbackStyles
          .map((vt) => {
            const code = String(vt || '').toUpperCase();
            const lbl = formatVacationTypeBadge(code);
            const idea = WEATHER_STYLE_ACTIVITIES_FALLBACK_EN[code] || 'local sights and family outings';
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

  function buildKpiExplanations(p, it, dirInfo, seatedCount, hasVal, schoolMissed, fbvsVal, isHe) {
    const totalDays = Math.max(1, diffDaysIso(it.departure_date, it.return_date) + 1);
    const impacts = Array.isArray(p && p.per_child_impact) ? p.per_child_impact : [];
    const fwImpacts = impacts.filter((c) => c && c.framework_type);
    const ccgPct = Math.round(Number((p && p.childcare_coverage_gain) ?? 1) * 100);
    const hasNum = Number(hasVal) || 0;

    let fitCalc = '';
    if (p && p.window_set_type === 'SPECIFIC_USER_WINDOW') {
      const q = state.lastSearchQuery || null;
      const shiftDays =
        q && q.specific_departure_date && q.specific_return_date
          ? Math.abs(diffDaysIso(q.specific_departure_date, it.departure_date)) +
            Math.abs(diffDaysIso(q.specific_return_date, it.return_date))
          : 0;
      fitCalc = isHe
        ? `ציון מ-100 לחלון של ${totalDays} ימי טיול בתאריכים שבחרתם (סטייה של ${shiftDays} ימים מתאריכי היעד ו-${schoolMissed} ימי חיסור מצטברים מלימודים).`
        : `Scored out of 100 for this ${totalDays}-day window (${shiftDays}-day shift from requested dates and ${schoolMissed} combined missed school days).`;
    } else if (fwImpacts.length > 0) {
      fitCalc = isHe
        ? `מחושב על פני ${totalDays} ימי טיול עבור ${fwImpacts.length} ילדים מול לוח משרד החינוך: 65% כיסוי חופשת לימודים, סופ״ש וקייטנות (${ccgPct}% בטיול זה) + 35% חפיפה משותפת, בניכוי ימי חיסור (${schoolMissed}).`
        : `Computed across ${totalDays} trip days for ${fwImpacts.length} school-age children against the MoE calendar: 65% break/weekend/camp coverage (${ccgPct}% here) + 35% shared break overlap, minus missed school days (${schoolMissed}).`;
    } else {
      fitCalc = isHe
        ? `מחושב על פני ${totalDays} ימי טיול מול לוח החופשות הרשמי של משרד החינוך: 80% חפיפה לפגרה הרשמית + 20% התאמה לאורך הטיול המבוקש.`
        : `Computed across ${totalDays} trip days against the official MoE break calendar: 80% overlap with official school break dates + 20% requested duration fit.`;
    }

    let fitMeaning = '';
    if (hasNum >= 85) {
      fitMeaning = isHe
        ? `התאמה גבוהה מאוד (${hasVal}/100) — הטיול יושב ברובו על חופשת בית הספר הרשמית וסופי שבוע.`
        : `Excellent fit (${hasVal}/100) — almost the entire trip sits inside official school break dates and weekends.`;
    } else if (hasNum >= 60) {
      fitMeaning = isHe
        ? `התאמה טובה (${hasVal}/100) — רוב הטיול מכוסה בחופשת לימודים או קייטנה עם גלישה מתונה לימי לימודים.`
        : `Good fit (${hasVal}/100) — most trip days sit on school break or camp dates with modest bridge overlap.`;
    } else {
      fitMeaning = isHe
        ? `חפיפה חלקית (${hasVal}/100) — חלק ניכר מהטיול חורג מחופשת בית הספר הרשמית ודורש ימי גשר.`
        : `Partial overlap (${hasVal}/100) — a sizable share of the trip falls outside the official school break.`;
    }

    const maxSingle = Number((p && p.max_single_child_school_days_missed) || 0);
    const missedCalcAddon =
      fwImpacts.length > 0
        ? (isHe
            ? ` בסוגריים: ימי לימודים פעילים (ללא חגים, שישי-שבת וקייטנות) שמוחסרים על ידי ${fwImpacts.length} ילדים (עד ${maxSingle} לילד/ה).`
            : ` In parentheses: active classroom days (excluding breaks, weekends, and camps) missed across ${fwImpacts.length} children (up to ${maxSingle} per child).`)
        : (isHe
            ? ' בסוגריים: ימי לימודים פעילים שמוחסרים (כרגע 0 ילדים במסגרת חינוכית בפרופיל).'
            : ' In parentheses: active classroom days missed (0 active school frameworks in profile).');
    const missedMeaningAddon =
      schoolMissed === 0
        ? (isHe
            ? ' אפס ימי חיסור משנת הלימודים.'
            : ' Zero missed school days.')
        : (isHe
            ? ` סה״כ ${schoolMissed} ימי היעדרות מצטברים (${maxSingle} בפועל לילד/ה) כימי גשר.`
            : ` ${schoolMissed} combined child-day absences (${maxSingle} actual day(s) per child) as bridge days.`);

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
        ? `כיסוי בונוס משמעותי (${fbvsStr}/100) — מושבי הבונוס מכסים כיוון מלא או חלק מהמשפחה בשני הכיוונים (בסימון \u20662+\u2069 ייתכן שיש מושבים נוספים).`
        : `Substantial award seat coverage (${fbvsStr}/100) — open bonus seats cover one full leg or part of the family both ways (2+ flights may hold more seats).`;
    } else {
      bonusMeaning = isHe
        ? `כיסוי בונוס חלקי (${fbvsStr}/100) — מספר מושבי הבונוס הפתוחים נמוך ממספר הנוסעים הזקוקים למושב.`
        : `Partial award seat coverage (${fbvsStr}/100) — open bonus seats cover only a fraction of your party's needed seats.`;
    }

    return {
      schoolFit: {
        title: isHe ? 'התאמה לחופשת בית ספר וחיסורים' : 'School Break Fit & Absences',
        calc: fitCalc + missedCalcAddon,
        meaning: fitMeaning + missedMeaningAddon
      },
      bonusValue: {
        title: isHe ? 'כדאיות בונוס' : 'Award Value',
        calc: bonusCalc,
        meaning: bonusMeaning
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
      const isStandardUnsynced = !rawHe || rawHe.includes(NO_SYNCED_FLIGHTS_TOKEN_HE);
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

      const badgeText = isHe ? '✈️ מחכה למשיכת טיסות' : '✈️ Awaiting Flight Sync';
      const headlineText = isHe ? 'מחכה למשיכת טיסות' : 'Awaiting Flight Sync';
      const subText = isStandardUnsynced
        ? isHe
          ? 'לא נמצאו מושבי בונוס פנויים במאגר עבור היעד והחופשה שנבחרו (מאגר טיסות הבונוס מתעדכן פעם ביום). מומלץ לנסות יעד נוסף או מועד חופשה אחר.'
          : 'No open award seats are currently available in the database for the selected destination and holiday (the bonus flight database updates once daily). Try another destination or vacation window.'
        : isHe
          ? rawHe
          : String(state.statusMessageEn || 'No matching flights found for the current search filters.');

      container.innerHTML = `
        <div class="awaiting-flights-showcase" role="status" aria-live="polite">
          <div class="awaiting-flights-scrim">
            <div class="awaiting-flights-badges">
              <span class="awaiting-flights-pill">${escapeHtml(badgeText)}</span>
              ${destLabel ? `<span class="awaiting-flights-dest-pill">📍 ${escapeHtml(destLabel)}</span>` : ''}
            </div>
            <h3 class="awaiting-flights-headline">${escapeHtml(headlineText)}</h3>
            <p class="awaiting-flights-sub">${escapeHtml(subText)}</p>
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
            ? '<strong>מאגר טיסות הבונוס מתעדכן פעם ביום.</strong> מספר מושבי הבונוס ומספר הנקודות לכרטיס מבוססים על מאגר כרטיסי הבונוס של אל על ואינם מחייבים. "2+" פירושו שאל על מאשרת לפחות 2 מושבי בונוס בטיסה. הזמינות והנקודות הסופיות נקבעות בעת ההזמנה באל על.'
            : '<strong>The bonus flight database is updated once daily.</strong> Bonus seat counts and points per ticket come from EL AL\'s award seat database and are not binding. "2+" means EL AL confirms at least 2 bonus seats on the flight. Final availability and points are set when you book with EL AL.'
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
            isHe
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

        const paxInfo = buildHouseholdPassengerSummary(state.profile, it, isHe);
        const seatedCount = paxInfo.seatedCount;

        const rankNum = p.rank_order || p.rank || (idx + 1);
        const tierCode = p.recommendation_tier || (idx === 0 ? 'RECOMMENDED' : idx < 4 ? 'TOP_CHOICE' : 'ALTERNATIVE');
        const tierBadgeText = formatRecommendationTierLabel(tierCode);
        const tierBadgeCls =
          tierCode === 'RECOMMENDED'
            ? 'badge-vacation'
            : tierCode === 'TOP_CHOICE'
              ? 'badge-camp'
              : 'badge-tier-alt';
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
          isHe
        );
        const tipIdFit = `kpi-tip-fit-${idx}`;
        const schoolFitTooltipHtml = renderKpiTooltipHtml(
          tipIdFit,
          kpiInfo.schoolFit.title,
          kpiInfo.schoolFit.calc,
          kpiInfo.schoolFit.meaning,
          isHe
        );

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
        const twoPlusTailText = isHe
          ? ' = לפחות 2 מושבי בונוס בטיסה; ייתכן שיש יותר.'
          : ' = at least 2 bonus seats on this flight; there may be more.';
        const twoPlusPartyHint =
          seatedCount > 2
            ? (isHe
                ? ` נדרשים ${seatedCount} מושבים — כדאי לבדוק הזמנה של 2 ועוד 2.`
                : ` ${seatedCount} seats needed — try booking 2 and 2.`)
            : '';
        const twoPlusNoteHtml = showTwoPlusNote
          ? `<p class="two-plus-note"><span dir="ltr">2+</span>${escapeHtml(twoPlusTailText + twoPlusPartyHint)}</p>`
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
                  <div class="stub-fare-row min-points-ticket" data-min-points="${minPtsNum}" data-scope="${minPtsScope}">
                    <span class="stub-fare-label">${escapeHtml(minPtsLabel)}</span>
                    <span class="stub-fare-val stub-fare-points">${escapeHtml(minPtsValue)}</span>
                  </div>`
          : '';

        const elalBookBtnHtml = elalBookUrl
          ? `
              <a class="btn-elal-book" href="${escapeHtml(elalBookUrl)}" target="_blank" rel="noopener noreferrer" data-elal-book-link="true" title="${isHe ? 'פתיחת הטיסה ב-Google Flights לבדיקת זמינות והזמנה באל על' : 'Open the flight on Google Flights to check availability and book with EL AL'}">
                <span>✈️ ${isHe ? 'להזמנת טיסת אל על' : 'Book EL AL Flight'}</span>
                <span dir="ltr" aria-hidden="true">↗</span>
              </a>
            `
          : '';

        return `
          <article class="proposal-card tier-${escapeHtml(tierCode)}" data-strategy="${escapeHtml(strategyCode)}" data-bonus-directions="${escapeHtml(dirInfo.dirAttr)}">
            <div class="proposal-pass-grid">
              <div class="proposal-pass-main">
                <div class="proposal-top-bar">
                  <div class="proposal-dest-header">
                    <span class="proposal-dest-icon" aria-hidden="true">${destIcon}</span>
                    <div class="proposal-title-group">
                      <span class="${tierBadgeCls}">#${rankNum} ${escapeHtml(tierBadgeText)}</span>
                      <strong class="proposal-dest-title">${escapeHtml(cityTitle)}</strong>
                      <span class="proposal-route-pair"><span class="route-pair-origin" dir="ltr">${escapeHtml(it.origin_iata || 'TLV')}</span> <span aria-hidden="true">⇄</span> <span class="route-pair-dest" dir="ltr">${escapeHtml(it.destination_iata)}</span></span>
                      ${topStyleChipHtml}
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
                </div>

                <div class="bonus-direction-block">
                  <div class="bonus-direction-header">
                    <span class="${directionBadgeCls}">
                      <span class="bonus-direction-dot" aria-hidden="true"></span>
                      <span class="bonus-direction-statement">${escapeHtml(directionStatementText)}</span>
                    </span>
                    ${strategyTagHtml}
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
                  <div class="stub-ctos-badge" dir="ltr" title="${isHe ? 'ציון התאמה משוקלל' : 'Overall Optimization Score'}">
                    <span>⭐</span>
                    <span class="stub-ctos-num">${Number(p.combined_trip_optimization_score || 0).toFixed(1)}</span>
                    <span class="stub-ctos-max">/100</span>
                  </div>
                </div>

                <div class="stub-fare-ledger">
                  <div class="stub-pax-summary">👥 ${escapeHtml(paxInfo.paxSummaryText)}</div>${minPointsRowHtml}
                </div>
                ${stubWeatherHtml}

                <div class="stub-kpi-grid">
                  <div class="score-pill kpi-cell" data-kpi="school-fit" data-school-missed="${schoolMissed}" tabindex="0" aria-describedby="${tipIdFit}">
                    <div class="kpi-cell-head">
                      <span class="kpi-cell-label">🏫 ${isHe ? 'התאמה לחופשת בי"ס' : 'School Break Fit'}</span>
                      <span class="kpi-info-cue" aria-hidden="true">ⓘ</span>
                    </div>
                    <strong class="kpi-cell-val"><span class="num" dir="ltr">${hasVal}/100</span> <span class="${missedParenCls}">(${escapeHtml(missedParenText)})</span></strong>
                    ${schoolFitTooltipHtml}
                  </div>
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
    const mode = state.dateSelectionMode;
    if (mode === 'SPECIFIC_DATES') {
      badge.textContent = isHe ? 'תאריכים ידניים (±גמישות)' : 'Manual Dates (±Flex)';
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

    updateActiveModeBadge();
    syncSearchFiltersSummary();
    renderProfileControls();
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

    document.title = isHe
      ? 'breezyflights | מתכנן חופשות משפחתיות חכם וכרטיסי בונוס אל על'
      : 'breezyflights | Smart Family Vacation & EL AL Award Planner';

    const headerTitleLocal = document.getElementById('header-title-local');
    if (headerTitleLocal) {
      headerTitleLocal.textContent = isHe
        ? 'מתכנן חופשות משפחתיות חכם'
        : 'Smart Family Vacation Planner';
    }
    const headerSubtitle = document.getElementById('header-subtitle');
    if (headerSubtitle) {
      headerSubtitle.textContent = isHe
        ? 'תכנון חופשות לפי לוח משרד החינוך, קייטנות ניצנים וכרטיסי בונוס באל על'
        : 'Plan around official MoE school breaks, Nitzanim camps & EL AL Matmid award seats';
    }
    const heroEyebrow = document.getElementById('hero-eyebrow');
    if (heroEyebrow) {
      heroEyebrow.innerHTML = isHe
        ? '🏝️ <span class="hero-eyebrow-short">חופשות חכמות</span><span class="hero-eyebrow-sub">תכנון חכם לחופשה המשפחתית הבאה</span>'
        : '🏝️ <span class="hero-eyebrow-short">Smart Escapes</span><span class="hero-eyebrow-sub">Smart Family Vacation Planning</span>';
    }
    const heroHeadline = document.getElementById('hero-headline');
    if (heroHeadline) {
      heroHeadline.textContent = isHe
        ? 'הפכו כל חופשת בית ספר לחופשה משפחתית חלומית'
        : 'Turn Every School Break Into a Dream Family Escape';
    }
    const heroLead = document.getElementById('hero-lead');
    if (heroLead) {
      heroLead.textContent = isHe
        ? 'הצלבה חכמה בין לוח החופשות של משרד החינוך, קייטנות ניצנים ומושבי בונוס מנתב״ג לכל היעדים הפתוחים.'
        : 'Smart cross-matching of official MoE school breaks, Nitzanim camps, and EL AL Matmid award seats from TLV across all open destinations.';
    }
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
        ? 'תכנון חופשה: לפי חג או תאריכים ידניים'
        : 'Vacation Search: By Holiday or Manual Dates';
    }
    const zProfile = document.getElementById('zone-profile-title');
    if (zProfile) {
      zProfile.textContent = isHe
        ? 'פרופיל משפחה, גילאי ילדים ויתרת מתמיד'
        : 'Family Profile, Children & Matmid Balance';
    }
    const zCalendar = document.getElementById('zone-calendar-title');
    if (zCalendar) {
      zCalendar.textContent = isHe
        ? 'לוח חופשות משרד החינוך וחפיפה רב-גילאית (תצוגה אופציונלית)'
        : 'MoE Multi-Child Vacation Calendar (Optional View)';
    }

    updateActiveModeBadge();
    syncSearchFiltersSummary();
    renderDestinationMultiSelect();
    setCalendarVisibility(state.isCalendarVisible, false);
    renderProfileControls();
    renderCalendarTable();
    renderProposals();
  }

  function collectActiveFrameworksCsv() {
    if (!state.profile || !Array.isArray(state.profile.children)) return '';
    const fws = state.profile.children
      .map((c) => (c && c.framework_type ? String(c.framework_type).trim() : ''))
      .filter(Boolean);
    return fws.join(',');
  }

  function refreshClientHolidaysOnProfileEdit() {
    const refIso = getReferenceToday();
    state.upcomingHolidays = buildUpcomingHolidaysClient(refIso, state.profile);
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: true,
      applyDurationDefault: !state.userEditedMaxNights
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
      setProfileSheetOpen(true);
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
      oauthConfigured: Boolean(state.auth && state.auth.oauthConfigured),
      testMode: Boolean(state.auth && state.auth.testMode),
      csrfToken: null,
      user: null
    };
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
    state.calendarData = null;
    state.proposals = [];
    state.showAllProposals = false;

    await scrubBrowserClientState();
    renderProfileControls();
    renderCalendarTable();
    renderProposals();
    await refreshUpcomingHolidaysFromServer(false);
    await loadCalendarForSchoolYear();
    await runVacationSearch();
  }

  async function handleDeleteSavedProfile() {
    if (!state.auth || !state.auth.authenticated) return;
    try {
      await apiSend('DELETE', '/api/v1/profile', {});
      state.profile = createCleanGuestProfile();
      state.profileDirty = false;
      state.calendarData = null;
      state.confirmingDeleteProfile = false;
      state.validationErrorHe = null;
      state.validationErrorEn = null;
      state.proposals = [];
      state.showAllProposals = false;
      state.saveFeedbackHe = '✓ הנתונים השמורים נמחקו מהחשבון.';
      state.saveFeedbackEn = '✓ Saved family data deleted from your account.';
      await scrubBrowserClientState();
      renderProfileControls();
      renderCalendarTable();
      renderProposals();
      await refreshUpcomingHolidaysFromServer(false);
      await loadCalendarForSchoolYear();
      await runVacationSearch();
    } catch (err) {
      if (err && err.status === 401) {
        await handleSignOut();
      }
    }
  }

  async function refreshUpcomingHolidaysFromServer(applyDefaultNights) {
    const refIso = getReferenceToday();
    const asOfOverride = getAsOfOverrideIso();
    const effectiveAsOf = asOfOverride || refIso;
    const fwCsv = collectActiveFrameworksCsv();
    const qs = fwCsv
      ? `?as_of=${encodeURIComponent(effectiveAsOf)}&frameworks=${encodeURIComponent(fwCsv)}`
      : `?as_of=${encodeURIComponent(effectiveAsOf)}`;
    try {
      const upcomingRes = await apiGet(`/api/v1/moe-calendar/upcoming${qs}`);
      if (upcomingRes && Array.isArray(upcomingRes.holidays) && upcomingRes.holidays.length > 0) {
        state.upcomingHolidays = upcomingRes.holidays;
      }
    } catch (_err) {
      state.upcomingHolidays = buildUpcomingHolidaysClient(refIso, state.profile);
    }
    if (!state.upcomingHolidays || state.upcomingHolidays.length === 0) {
      state.upcomingHolidays = buildUpcomingHolidaysClient(refIso, state.profile);
    }
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: state.userSelectedHoliday,
      applyDurationDefault: Boolean(applyDefaultNights) && !state.userEditedMaxNights
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
  }

  async function loadInitialData() {
    const refIso = getReferenceToday();
    initDefaultManualDates();
    state.validationErrorHe = null;
    state.validationErrorEn = null;
    state.proposals = [];
    state.showAllProposals = false;
    state.profile = createCleanGuestProfile();
    syncDestStateFromNativeSelect();
    renderDestinationMultiSelect();
    renderProfileControls();
    state.upcomingHolidays = buildUpcomingHolidaysClient(refIso, state.profile);
    populateHolidaySelector(state.upcomingHolidays, {
      preserveSelection: state.userSelectedHoliday,
      applyDurationDefault: !state.userEditedMaxNights
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
          oauthConfigured: Boolean(sess.oauth_configured),
          testMode: Boolean(sess.test_mode),
          csrfToken: sess.csrf_token || null,
          user: sess.user
        };
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
            state.saveFeedbackHe = '✓ הפרופיל המשפחתי נשמר בחשבון שלך.';
            state.saveFeedbackEn = '✓ Family profile saved to your account.';
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
          oauthConfigured: Boolean(sess && sess.oauth_configured),
          testMode: Boolean(sess && sess.test_mode),
          csrfToken: null,
          user: null
        };
        state.notificationsOptIn = false;
        try {
          sessionStorage.removeItem('fvp_pending_oauth_draft');
        } catch (_rmErr) {
          // Ignore
        }
        state.profile = createCleanGuestProfile();
        state.profileDirty = false;
      }

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
    const holidayVal = (selectHolidayEl && selectHolidayEl.value) || 'HANUKKAH';
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
    if (yearVal !== undefined && Number.isFinite(yearVal)) {
      payload.direct_target_year = yearVal;
    }

    state.validationErrorHe = null;
    state.validationErrorEn = null;

    try {
      const res = await apiSend('POST', '/api/v1/vacations/search', payload);
      if (mySearchSeq !== latestSearchSeq) return;
      state.lastSearchQuery = res.query || payload || null;
      state.proposals = res.proposals || [];
      state.showAllProposals = false;
      state.statusMessageHe = res.status_message_he || null;
      state.statusMessageEn = res.status_message_en || null;
      state.weatherFallbackMessageHe = res.weather_fallback_message_he || null;
    } catch (err) {
      if (mySearchSeq !== latestSearchSeq) return;
      const detail = extractApiErrorDetail(err);
      const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      state.proposals = [];
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
        state.userEditedMaxNights = false;
        const opt = selectHolidayEl.selectedOptions && selectHolidayEl.selectedOptions[0];
        const days = opt && opt.dataset ? Number(opt.dataset.days || 7) : 7;
        applyHolidayDurationDefault(days);
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
        setProfileSheetOpen(false);
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

    const btnHeaderHh = document.getElementById('btn-header-household');
    if (btnHeaderHh) {
      btnHeaderHh.addEventListener('click', () => {
        setProfileSheetOpen(!state.isProfileSheetOpen, { focusMatmid: false });
      });
    }

    const btnOpenProfileSheet = document.getElementById('btn-open-profile-sheet');
    if (btnOpenProfileSheet) {
      btnOpenProfileSheet.addEventListener('click', () => {
        setProfileSheetOpen(true, { focusMatmid: false });
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
        renderProfileControls();
        setProfileSheetOpen(false);
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

    function closeAllKpiTooltips(exceptCell) {
      document.querySelectorAll('.kpi-cell.is-tooltip-open, .stub-weather-card.is-tooltip-open').forEach((el) => {
        if (el !== exceptCell) {
          el.classList.remove('is-tooltip-open');
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
        if (state.isDestPickerOpen) {
          setDestPickerOpen(false);
        }
        if (state.isProfileSheetOpen) {
          setProfileSheetOpen(false);
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

    const btnHeaderAuth = document.getElementById('btn-header-auth');
    if (btnHeaderAuth) {
      btnHeaderAuth.addEventListener('click', () => {
        startGoogleSignIn();
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

    const btnSaveProfile = document.getElementById('btn-save-profile');
    if (btnSaveProfile) {
      btnSaveProfile.addEventListener('click', async () => {
        if (!state.auth || !state.auth.authenticated) {
          startGoogleSignIn();
          return;
        }
        syncProfileStateFromDom();
        state.validationErrorHe = null;
        state.validationErrorEn = null;
        try {
          const saveBody = {
            ...state.profile,
            notifications_enabled: Boolean(state.notificationsOptIn)
          };
          const saved = await apiSend('PUT', '/api/v1/profile', saveBody);
          saved.passenger_loyalty_wallets = [];
          state.profile = saved;
          state.profileDirty = false;
          state.saveFeedbackHe = '✓ הפרופיל המשפחתי נשמר בחשבון שלך.';
          state.saveFeedbackEn = '✓ Family profile saved to your account.';
          renderProfileControls();
          await refreshUpcomingHolidaysFromServer(false);
          await loadCalendarForSchoolYear();
          await runVacationSearch();
        } catch (err) {
          if (err && err.status === 401) {
            await handleSignOut();
            return;
          }
          const detail = extractApiErrorDetail(err);
          const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
          const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
          state.proposals = [];
          state.showAllProposals = false;
          state.validationErrorHe = `לא ניתן לשמור את פרופיל המשפחה — בדקו שגילאי הילדים (0–18), מספר המבוגרים (1–6) ויתרת המתמיד תקינים.${detailSuffixHe}`;
          state.validationErrorEn = `Could not save family profile — verify adults count (1–6), child ages (0–18), and non-negative Matmid balance.${detailSuffixEn}`;
          renderProposals();
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
          framework_type: state.dateSelectionMode === 'SPECIFIC_DATES' ? null : suggestFrameworkByAge(defaultAge),
          school_week_days: 5,
          holiday_extension_mode: 'NITZANIM_FULL_WITH_JULY',
          treat_camp_as_vacation: true,
          bagrut_blackout_dates: []
        });
        state.profileDirty = true;
        renderProfileControls();
        refreshClientHolidaysOnProfileEdit();
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
        if (state.dateSelectionMode !== 'SPECIFIC_DATES') {
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
      const focusMatmidBtn = target.closest('[data-focus-matmid]');
      if (focusMatmidBtn) {
        setProfileSheetOpen(true, { focusMatmid: true });
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
        const willOpen = !kpiCellEl.classList.contains('is-tooltip-open');
        closeAllKpiTooltips(willOpen ? kpiCellEl : null);
        kpiCellEl.classList.toggle('is-tooltip-open', willOpen);
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
        renderProfileControls();
        refreshClientHolidaysOnProfileEdit();
      }
    });

    document.body.addEventListener('pointerover', (ev) => {
      if (ev.pointerType && ev.pointerType !== 'mouse') return;
      const target = ev.target;
      if (!target || typeof target.closest !== 'function') return;
      const hoveredKpi = target.closest('.kpi-cell, .stub-weather-card');
      if (hoveredKpi) {
        closeAllKpiTooltips(hoveredKpi);
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
        setCalendarVisibility(false, false);
      });
    }

    document.querySelectorAll('.desktop-nav-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const zoneId = btn.getAttribute('data-desktop-zone');
        if (zoneId === 'zone-calendar') {
          setCalendarVisibility(!state.isCalendarVisible, !state.isCalendarVisible);
          return;
        }
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
          setProfileSheetOpen(false);
          setCalendarVisibility(!state.isCalendarVisible, !state.isCalendarVisible);
          return;
        }
        if (zoneId === 'zone-profile') {
          setProfileSheetOpen(!state.isProfileSheetOpen, { focusMatmid: false });
          return;
        }
        state.lastActiveMobileZone = zoneId;
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

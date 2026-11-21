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
    ATH: '🏖️',
    RHO: '🏝️',
    HER: '🏝️',
    SKG: '🌊',
    CFU: '🏝️',
    EFL: '🏖️',
    JTR: '🌅',
    LCA: '☀️',
    PFO: '🏖️',
    TBS: '🏔️',
    BUS: '🌊',
    TIV: '⛵',
    BEG: '🏰',
    OTP: '🏰',
    SOF: '⛰️',
    PAR: '🥐',
    CDG: '🥐',
    NCE: '🏖️',
    LON: '🎡',
    LHR: '🎡',
    LTN: '🎡',
    MAD: '💃',
    BCN: '🌊',
    GVA: '⛷️',
    ZRH: '🏔️',
    MUC: '🏰',
    FRA: '🎢',
    VIE: '🎻',
    PRG: '🏰',
    BUD: '♨️',
    WAW: '🏰',
    KRK: '🎢',
    AMS: '🌷',
    BER: '🐻',
    LIS: '🚋',
    DXB: '☀️',
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
      workweek_type: 'SUN_THU',
      erev_chag_pto_weight: 0.5,
      chol_hamoed_pto_weight: 0.5,
      annual_pto_budget: 18,
      max_pto_per_trip: 5,
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
    showAllProposals: false,
    lastComparison: null,
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
    proposals: [],
    selectedProposalIds: new Set()
  };

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

  function setCalendarVisibility(visible, scrollToIt) {
    state.isCalendarVisible = Boolean(visible);
    const calZone = document.getElementById('zone-calendar');
    const isHe = state.locale === 'he';
    if (calZone) {
      if (state.isCalendarVisible) {
        calZone.removeAttribute('hidden');
        calZone.style.display = 'block';
        if (scrollToIt) {
          calZone.scrollIntoView({ behavior: 'smooth' });
        }
      } else {
        calZone.setAttribute('hidden', '');
        calZone.style.display = 'none';
      }
    }
    const btnTop = document.getElementById('btn-toggle-calendar');
    if (btnTop) {
      btnTop.textContent = state.isCalendarVisible
        ? isHe
          ? '📅 הסתר לוח'
          : '📅 Hide Calendar'
        : isHe
          ? '📅 לוח חופשות'
          : '📅 MoE Calendar';
    }
    const btnInline = document.getElementById('btn-toggle-calendar-inline');
    if (btnInline) {
      btnInline.textContent = state.isCalendarVisible
        ? isHe
          ? '📅 הסתר לוח חופשות משרד החינוך'
          : '📅 Hide MoE Vacation Calendar'
        : isHe
          ? '📅 הצג לוח חופשות משרד החינוך'
          : '📅 Show MoE Vacation Calendar';
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

  function formatGenericPassengerLabel(alloc, fallbackIdx) {
    const pid = String(alloc.passenger_id || '').toUpperCase();
    const rawLabel = String(alloc.passenger_label || '');
    const isHe = state.locale === 'he';

    if (pid.startsWith('ADULT_')) {
      const num = pid.split('_')[1] || (fallbackIdx + 1);
      return isHe ? `מבוגר/הורה ${num}` : `Adult ${num}`;
    }
    if (pid.startsWith('CHILD_')) {
      const num = pid.split('_')[1] || (fallbackIdx + 1);
      const ageMatch = rawLabel.match(/\d+/);
      const ageNum = ageMatch ? Number(ageMatch[0]) : null;
      const childIdx = Number(num) - 1;
      const profChild = state.profile && state.profile.children && state.profile.children[childIdx];
      const resolvedAge = profChild ? profChild.child_age_years : ageNum;
      if (resolvedAge !== null && resolvedAge !== undefined) {
        return isHe ? `ילד/ה #${num} (גיל ${resolvedAge})` : `Child #${num} (Age ${resolvedAge})`;
      }
      return isHe ? `ילד/ה #${num}` : `Child #${num}`;
    }
    return isHe ? `נוסע #${fallbackIdx + 1}` : `Passenger #${fallbackIdx + 1}`;
  }

  function formatStrategyLabel(strategyCode) {
    const code = String(strategyCode || '');
    const isHe = state.locale === 'he';
    const labelsHe = {
      FULL_BONUS_SAME_CABIN: 'בונוס מלא באותה מחלקה',
      SPLIT_CABIN_BONUS: 'בונוס מפוצל בין מחלקות (אותה טיסה)',
      HYBRID_BONUS_PLUS_CASH: 'שילוב כרטיסי בונוס + השלמת מזומן',
      ONE_WAY_BONUS_ONE_WAY_CASH: 'כיוון בונוס + כיוון מזומן / יעד משולב',
      CASH_AND_POINTS: 'מזומן + נקודות (Cash & Points)',
      MULTI_CLUB_PER_PASSENGER_SPLIT: 'פיצול נקודות בין מועדונים ונוסעים',
      COMMERCIAL_CASH_ONLY: 'כרטיסים מסחריים במזומן'
    };
    const labelsEn = {
      FULL_BONUS_SAME_CABIN: 'Full Bonus (Same Cabin)',
      SPLIT_CABIN_BONUS: 'Split-Cabin Bonus (Same Flight)',
      HYBRID_BONUS_PLUS_CASH: 'Hybrid Bonus + Cash',
      ONE_WAY_BONUS_ONE_WAY_CASH: 'One-Way Bonus + Cash / Open-Jaw',
      CASH_AND_POINTS: 'Cash & Points',
      MULTI_CLUB_PER_PASSENGER_SPLIT: 'Multi-Club Per-Passenger Split',
      COMMERCIAL_CASH_ONLY: 'Commercial Cash Only'
    };
    return (isHe ? labelsHe[code] : labelsEn[code]) || code;
  }

  function formatRecommendationTierLabel(tierCode) {
    const code = String(tierCode || '');
    const isHe = state.locale === 'he';
    if (code === 'RECOMMENDED') return isHe ? '🌟 החופשה המומלצת ביותר' : '🌟 Best Overall Vacation';
    if (code === 'TOP_CHOICE') return isHe ? '✨ בחירה מובילה' : '✨ Top Choice';
    return isHe ? '🏖️ חלופה מומלצת' : '🏖️ Alternative Option';
  }

  function buildIntuitiveProposalSummary(p) {
    const it = p.itinerary || {};
    const isHe = state.locale === 'he';
    const city = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);
    const stratLabel = formatStrategyLabel(it.fulfillment_strategy);
    const pts = Number(it.total_matmid_points || 0).toLocaleString();
    const cashOop = Number(it.total_out_of_pocket_cash_usd || 0).toFixed(0);
    const savedNum = Math.round(Number(it.net_cash_saved_usd || 0));
    const savedDisplay =
      savedNum > 0 ? `+$${savedNum}` : savedNum < 0 ? `-$${Math.abs(savedNum)}` : '$0';
    const totalScore = Number(p.combined_trip_optimization_score || 0).toFixed(1);
    const vacScore = Number(p.vacation_utilization_score || 0).toFixed(1);
    const bonusScore = Number(p.flight_bonus_value_score ?? p.family_bonus_value_score ?? 0).toFixed(1);
    const weatherScore = Number(p.weather_suitability_score || 0).toFixed(1);

    if (!isHe) {
      return `${city} (${it.destination_iata}) | ${it.departure_date} to ${it.return_date} (${it.trip_nights} nights) | Strategy: ${stratLabel} | Points: ${pts} | Out-of-Pocket Cash: $${cashOop} (Net Saved: ${savedDisplay}) | Overall Score: ${totalScore}/100 (Weather: ${weatherScore}, Vacation Match: ${vacScore}, Bonus Value: ${bonusScore})`;
    }
    return `${city} (${it.destination_iata}) | ${it.departure_date} עד ${it.return_date} (${it.trip_nights} לילות / ${p.total_vacation_days || (it.trip_nights + 1)} ימים) | אסטרטגיה: ${stratLabel} | נקודות: ${pts} | תשלום במזומן: $${cashOop} (חיסכון נטו: ${savedDisplay}) | ציון משוקלל: ${totalScore}/100 (מזג אוויר: ${weatherScore}, ניצול חופשה: ${vacScore}, כדאיות טיסה ובונוס: ${bonusScore})`;
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
    return matmidTotal;
  }

  function syncProfileStateFromDom() {
    if (!state.profile) {
      state.profile = createCleanGuestProfile();
    }
    const adultsEl = document.getElementById('prof-adults-count');
    const ptoEl = document.getElementById('prof-pto-budget');
    if (adultsEl && adultsEl.value !== '') {
      state.profile.adults_count = Number(adultsEl.value);
    }
    if (ptoEl && ptoEl.value !== '') {
      state.profile.annual_pto_budget = Number(ptoEl.value);
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
      const heSave = isAuthed ? '💾 שמור ועדכן' : '🔒 התחברות לשמירה';
      const enSave = isAuthed ? '💾 Save & Refresh' : '🔒 Sign in to Save';
      btnSaveProfile.setAttribute('data-he', heSave);
      btnSaveProfile.setAttribute('data-en', enSave);
      btnSaveProfile.textContent = isHe ? heSave : enSave;
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
    const ptoInput = document.getElementById('prof-pto-budget');
    const matmidInput = document.getElementById('prof-matmid-points');
    if (adultsInput) adultsInput.value = state.profile.adults_count;
    if (ptoInput) ptoInput.value = state.profile.annual_pto_budget;
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
        return `
          <tr>
            <td class="sticky-col">${escapeHtml(holidayTitle)}</td>
            <td><span style="font-weight: 600; color: var(--text-primary); white-space: normal;">${escapeHtml(fwLabel)}</span></td>
            <td dir="ltr">${escapeHtml(g.start_date)}</td>
            <td dir="ltr">${escapeHtml(g.end_date)}</td>
            <td dir="ltr">${escapeHtml(g.resume_date)}</td>
            <td dir="ltr">${escapeHtml(daysCount)}</td>
            <td>${nitzBadge}</td>
          </tr>
        `;
      })
      .join('');
  }

  function resolveElAlBookingUrl(it) {
    if (!it || !it.is_elal_flight) return null;
    const serverGfUrl = String(it.elal_google_flights_url || '').trim();
    if (serverGfUrl.startsWith('https://www.google.com/travel/flights')) {
      return serverGfUrl;
    }

    // Client-side fallback builder for cached El Al itineraries
    const orig = String(it.origin_iata || 'TLV').toUpperCase();
    const dest = String(it.destination_iata || 'FCO').toUpperCase();
    const retOrig = String(it.return_origin_iata || dest).toUpperCase();
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
        ? `Flights to ${dest} from ${orig} on ${depIso} through ${retIso} with ${paxPhrase} nonstop on EL AL`
        : `Flights from ${orig} to ${dest} on ${depIso} and from ${retOrig} to ${orig} on ${retIso} with ${paxPhrase} nonstop on EL AL`;

    const params = new URLSearchParams();
    params.set('q', qStr);
    params.set('curr', 'USD');
    params.set('gl', 'IL');
    params.set('hl', 'en');
    return `https://www.google.com/travel/flights?${params.toString()}`;
  }

  function formatLegFlightBadge(leg) {
    if (!leg || !leg.flight_number) return '';
    const fn = String(leg.flight_number).trim();
    const depT = leg.departure_time_local ? String(leg.departure_time_local).slice(0, 5) : '';
    const arrT = leg.arrival_time_local ? String(leg.arrival_time_local).slice(0, 5) : '';
    const times = depT && arrT ? ` · ${depT}–${arrT}` : depT ? ` · ${depT}` : '';
    return `<span class="route-flight-meta">${escapeHtml(fn + times)}</span>`;
  }

  function updateZoneResultsTitle() {
    const zResults = document.getElementById('zone-results-title');
    if (!zResults) return;
    const isHe = state.locale === 'he';
    const count = (state.proposals && state.proposals.length) || 0;
    const countSuffix = count > 0 ? ` (${count})` : '';
    zResults.textContent = isHe
      ? `3. תוצאות חיפוש, דירוג חופשות וניצול כרטיסי בונוס${countSuffix}`
      : `3. Ranked Vacation Proposals & Award Fulfillment${countSuffix}`;
  }

  function renderComparisonBanner() {
    const banner = document.getElementById('comparison-banner-container');
    if (!banner) return;
    const cmp = state.lastComparison;
    if (!cmp) {
      banner.style.display = 'none';
      banner.innerHTML = '';
      return;
    }
    const isHe = state.locale === 'he';
    const props = cmp.proposals || [];
    const byId = new Map(props.map((p) => [p.id, p]));
    const fmtWinner = (pid) => {
      const p = byId.get(pid);
      if (!p || !p.itinerary) return null;
      const it = p.itinerary;
      const city = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);
      const strat = formatStrategyLabel(it.fulfillment_strategy);
      return `${city} (${it.departure_date} → ${it.return_date} · ${strat})`;
    };

    const bestOverall = fmtWinner(cmp.best_by_ctos_id);
    const bestSavings = fmtWinner(cmp.best_by_cash_savings_id);
    const bestPer = fmtWinner(cmp.best_by_per_id);
    const bestWeather = fmtWinner(cmp.best_by_weather_id);

    let summaryLine = isHe ? (cmp.summary_he || '') : (cmp.summary_en || '');
    if (!summaryLine) {
      const parts = [];
      if (bestOverall) parts.push(isHe ? `ציון משוקלל מוביל: ${bestOverall}` : `Best Overall Score: ${bestOverall}`);
      if (bestSavings) parts.push(isHe ? `חיסכון כספי מרבי: ${bestSavings}` : `Highest Net Savings: ${bestSavings}`);
      if (bestPer) parts.push(isHe ? `מכפיל ימי חופש מרבי: ${bestPer}` : `Best PTO Multiplier: ${bestPer}`);
      if (bestWeather) parts.push(isHe ? `מזג אוויר מיטבי: ${bestWeather}` : `Best Weather Match: ${bestWeather}`);
      summaryLine = parts.join(' · ');
    }

    banner.style.display = 'block';
    banner.innerHTML = `
      <div class="comparison-banner-card">
        <strong class="comparison-banner-title">⚖️ ${isHe ? `תוצאת השוואת ${props.length} חלופות נבחרות:` : `Comparison Summary (${props.length} selected proposals):`}</strong>
        <p class="comparison-banner-text">${escapeHtml(summaryLine)}</p>
      </div>
    `;
  }

  function renderProposals() {
    const container = document.getElementById('proposals-container');
    if (!container) return;
    const isHe = state.locale === 'he';
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

    if (!state.proposals || state.proposals.length === 0) {
      const NO_SYNCED_FLIGHTS_TOKEN_HE = 'אין משיכה של טיסות מהשרת';
      const rawHe = String(state.statusMessageHe || '');
      const isStandardUnsynced = !rawHe || rawHe.includes(NO_SYNCED_FLIGHTS_TOKEN_HE);
      const selectDestEl = document.getElementById('select-destination');
      const selectedDestOpt = selectDestEl && selectDestEl.selectedOptions && selectDestEl.selectedOptions[0];
      const destCode = selectDestEl ? String(selectDestEl.value || '').trim() : '';
      const destLabel =
        selectedDestOpt && destCode && destCode !== 'ANYWHERE'
          ? String(selectedDestOpt.textContent || '').trim()
          : '';

      const badgeText = isHe ? '✈️ מחכה למשיכת טיסות' : '✈️ Awaiting Flight Sync';
      const headlineText = isHe ? 'מחכה למשיכת טיסות' : 'Awaiting Flight Sync';
      const subText = isStandardUnsynced
        ? isHe
          ? 'טרם נמשכו טיסות בונוס זמינות עבור היעד והחופשה שנבחרו. אפשר לבחור יעד או מועד אחר בטופס, או להריץ סנכרון טיסות מול אל על.'
          : 'No synced award flights are currently loaded for the selected destination and holiday window. Pick another destination or holiday, or sync El Al availability.'
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

    const fallbackBannerHtml = state.weatherFallbackMessageHe
      ? `
        <div class="weather-fallback-card">
          🌤️ ${escapeHtml(isHe ? state.weatherFallbackMessageHe : 'Strict weather filter was relaxed to display the highest-rated weather options for these dates.')}
        </div>
      `
      : '';

    const totalCount = state.proposals.length;
    const visibleList = state.showAllProposals
      ? state.proposals
      : state.proposals.slice(0, INITIAL_PROPOSALS_LIMIT);

    const cardsHtml = visibleList
      .map((p, idx) => {
        const it = p.itinerary || {};
        const wm = p.weather_metrics || null;
        const wssVal = Number(
          p.weather_suitability_score ??
            (wm && wm.overall_weather_suitability_score) ??
            0
        );

        let topStyleChipHtml = '';
        let weatherStripHtml = '';
        if (wm) {
          const scoresByType = wm.scores_by_vacation_type || {};
          const recList = wm.recommended_vacation_types || [];
          if (recList.length > 0) {
            topStyleChipHtml = `<span class="weather-badge-tag">${formatVacationTypeBadge(recList[0])}</span>`;
          }
          const recTypes = recList
            .slice(0, 3)
            .map((vt) => `<span class="weather-badge-tag">${formatVacationTypeBadge(vt)}</span>`)
            .join('');
          const seaTempChip =
            wm.sea_water_temp_c !== null && wm.sea_water_temp_c !== undefined
              ? `<span class="weather-metric-chip">🌊 ${isHe ? 'ים:' : 'Sea:'} <strong dir="ltr">${Number(wm.sea_water_temp_c).toFixed(0)}°C</strong></span>`
              : '';
          const extraSelectedChips = (state.selectedVacationTypes || [])
            .filter((vt) => vt !== 'ANY')
            .slice(0, 2)
            .map(
              (vt) =>
                `<span class="weather-metric-chip">${formatVacationTypeBadge(vt)}: <strong dir="ltr">${Number(scoresByType[vt] ?? 0).toFixed(0)}</strong></span>`
            )
            .join('');
          const summaryNoteText = isHe
            ? (wm.weather_summary_he || '')
            : (wm.weather_summary_en ||
              `Expected ${Number(wm.avg_day_high_c || 0).toFixed(0)}°C day / ${Number(wm.avg_night_low_c || 0).toFixed(0)}°C night` +
                (wm.sea_water_temp_c !== null && wm.sea_water_temp_c !== undefined ? `, sea ${Number(wm.sea_water_temp_c).toFixed(0)}°C` : '') +
                `, ~${Number(wm.sunshine_hours_per_day || 0).toFixed(1)}h daily sunshine & ~${Number(wm.estimated_rain_days_in_trip || 0).toFixed(1)} rain days.`);
          weatherStripHtml = `
            <div class="weather-telemetry-strip">
              <div class="weather-telemetry-row">
                <span class="weather-metric-chip">🌤️ ${isHe ? 'ציון אקלים:' : 'Climate:'} <strong dir="ltr">${wssVal.toFixed(0)}/100</strong></span>
                <span class="weather-metric-chip">🌡️ <strong dir="ltr">${Number(wm.avg_day_high_c || 0).toFixed(0)}°/${Number(wm.avg_night_low_c || 0).toFixed(0)}°C</strong></span>
                ${seaTempChip}
                <span class="weather-metric-chip">☀️ <strong dir="ltr">${Number(wm.sunshine_hours_per_day || 0).toFixed(1)}h</strong></span>
                <span class="weather-metric-chip">🌧️ <strong dir="ltr">${Number(wm.estimated_rain_days_in_trip || 0).toFixed(1)}${isHe ? ' ימי גשם' : 'd rain'}</strong></span>
                ${extraSelectedChips}
              </div>
              <div class="weather-telemetry-footer">
                <span class="weather-summary-note">${escapeHtml(summaryNoteText)}</span>
                <div class="weather-rec-tags">${recTypes}</div>
              </div>
            </div>
          `;
        }

        const allocList = it.family_ticket_allocation || it.passenger_allocations || [];
        const seatedCount = allocList.filter((a) => {
          const pts = Number(a.points_used ?? a.points_charged ?? 0);
          const cash = Number(a.cash_fare_usd ?? a.cash_fare_charged_usd ?? 0);
          const tax = Number(a.taxes_usd ?? a.taxes_and_fees_usd ?? 0);
          return pts > 0 || cash > 0 || tax > 0;
        }).length;

        const twoPlusVerifyBannerHtml = it.requires_two_plus_seat_verification
          ? `
            <div class="two-plus-verify-banner">
              <strong>ℹ️ ${isHe ? `מכסת 2+ מושבי בונוס קלאסי באל על (${seatedCount} מושבים נדרשים):` : `EL AL 2+ Classic Award Seat Cap (${seatedCount} seats needed):`}</strong>
              <span>
                ${
                  isHe
                    ? `אל על מאשרת לפחות 2 מושבי בונוס קלאסי בטיסה זו. אם בחיפוש ל-${seatedCount} נוסעים מופיע תעריף Cash & Points, הזמינו 2 מושבי בונוס קלאסי והשלימו את היתר בנפרד.`
                    : `EL AL confirms at least 2 Classic Award seats on this flight. If searching for ${seatedCount} passengers switches to Cash & Points rates, book 2 Classic Award seats first and complete the remaining seat separately.`
                }
              </span>
            </div>
          `
          : '';

        const allocRows = allocList
          .map((a, aIdx) => {
            const ptsVal = Number(a.points_used ?? a.points_charged ?? 0);
            const taxVal = Number(a.taxes_usd ?? a.taxes_and_fees_usd ?? 0);
            const cashVal = Number(a.cash_fare_usd ?? a.cash_fare_charged_usd ?? 0);
            const isLapInfant =
              String(a.rbd_code || '') === 'INF' ||
              String(a.ticket_mode || '') === 'INFANT_LAP' ||
              (ptsVal === 0 && taxVal === 0 && cashVal === 0);
            const modeLabel = isLapInfant
              ? (isHe ? 'תינוק ללא מושב — על הברכיים (INFANT_LAP)' : 'Lap Infant — No Separate Seat (INFANT_LAP)')
              : `${a.ticket_mode || a.outbound_ticket_kind || ''} (${a.cabin_class || a.outbound_cabin || 'ECONOMY'})`;
            return `
              <tr>
                <td>${escapeHtml(formatGenericPassengerLabel(a, aIdx))}</td>
                <td><code>${escapeHtml(isLapInfant ? 'INFANT' : (a.program_code || a.program_used || 'CASH'))}</code></td>
                <td>${escapeHtml(modeLabel)}</td>
                <td dir="ltr">${ptsVal.toLocaleString()} pts</td>
                <td dir="ltr">$${taxVal.toFixed(0)} + $${cashVal.toFixed(0)}</td>
              </tr>
            `;
          })
          .join('');

        const checked = state.selectedProposalIds.has(p.id) ? 'checked' : '';
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
        const perVal = p.pto_efficiency_ratio ?? p.parent_pto_efficiency_ratio ?? 0;
        const perDisplay = isHe ? `פי ${Number(perVal).toFixed(1)}` : `${Number(perVal).toFixed(1)}x`;
        const schoolMissed = Number(p.total_school_days_missed_across_children || 0);
        const schoolCellCls = schoolMissed === 0 ? 'score-pill kpi-cell kpi-cell-pine' : 'score-pill kpi-cell';
        const schoolText = schoolMissed === 0
          ? (isHe ? '0 ימים ✓' : '0 days ✓')
          : (isHe ? `${schoolMissed} ימים` : `${schoolMissed} days`);
        const stratText = formatStrategyLabel(it.fulfillment_strategy);
        const destIcon = DESTINATION_ICONS[it.destination_iata] || '✈️';
        const cityTitle = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);
        const elalBookUrl = resolveElAlBookingUrl(it);
        const outLeg = (it.outbound_legs && it.outbound_legs[0]) || null;
        const inLeg = (it.inbound_legs && it.inbound_legs[0]) || null;
        const outFlightBadgeHtml = formatLegFlightBadge(outLeg);
        const inFlightBadgeHtml = formatLegFlightBadge(inLeg);
        // Flight-number tags get their own line of the route bar: outbound at the start edge, inbound at the end edge
        const flightsRowHtml = outFlightBadgeHtml || inFlightBadgeHtml
          ? `
                  <div class="route-flights-row">
                    <span class="route-flight-slot">${outFlightBadgeHtml}</span>
                    <span class="route-flight-slot route-flight-slot-end">${inFlightBadgeHtml}</span>
                  </div>`
          : '';
        const returnOriginLabel =
          it.return_origin_iata && it.return_origin_iata !== it.destination_iata
            ? `${it.destination_iata}/${it.return_origin_iata}`
            : it.destination_iata;
        const totalVacDays = p.total_vacation_days || ((Number(it.trip_nights) || 0) + 1);
        const ptsTotal = Number(it.total_matmid_points || 0).toLocaleString();
        const oopCash = Number(it.total_out_of_pocket_cash_usd || 0).toFixed(0);
        const netSavedNum = Math.round(Number(it.net_cash_saved_usd || 0));
        const netSavedDisplay =
          netSavedNum > 0
            ? `+$${netSavedNum}`
            : netSavedNum < 0
              ? `-$${Math.abs(netSavedNum)}`
              : '$0';
        const savedRowCls = netSavedNum > 0 ? 'stub-fare-row stub-fare-saved' : 'stub-fare-row';
        const cppVal = Number(it.cents_per_point_value || 0).toFixed(2);

        const elalBookBtnHtml = elalBookUrl
          ? `
              <a class="btn-elal-book" href="${escapeHtml(elalBookUrl)}" target="_blank" rel="noopener noreferrer" data-elal-book-link="true" title="${isHe ? 'פתיחת טיסת אל על ב-Google Flights למעבר מאומת ישירות להזמנה באל על' : 'Open EL AL flight on Google Flights for verified handoff to EL AL booking'}">
                <span>✈️ ${isHe ? 'להזמנת טיסת אל על (Google Flights)' : 'Book EL AL (Google Flights)'}</span>
                <span dir="ltr" aria-hidden="true">↗</span>
              </a>
            `
          : '';

        return `
          <article class="proposal-card tier-${escapeHtml(tierCode)}">
            <div class="proposal-pass-grid">
              <div class="proposal-pass-main">
                <div class="proposal-top-bar">
                  <div class="proposal-dest-header">
                    <span class="proposal-dest-icon" aria-hidden="true">${destIcon}</span>
                    <div class="proposal-title-group">
                      <span class="${tierBadgeCls}">#${rankNum} ${escapeHtml(tierBadgeText)}</span>
                      <strong class="proposal-dest-title">${escapeHtml(cityTitle)}</strong>
                      <span class="proposal-route-pair" dir="ltr">${escapeHtml(it.origin_iata || 'TLV')} ⇄ ${escapeHtml(it.destination_iata)}</span>
                    </div>
                  </div>
                  ${topStyleChipHtml}
                </div>

                <div class="boarding-route-bar" dir="ltr">
                  <div class="route-endpoint">
                    <span class="route-iata">${escapeHtml(it.origin_iata || 'TLV')}</span>
                    <span class="route-date">${escapeHtml(it.departure_date)}</span>
                  </div>
                  <div class="route-arc-Track">
                    <span class="route-nights-pill" dir="auto">${escapeHtml(it.trip_nights)} ${isHe ? 'לילות' : 'Nights'} · ${escapeHtml(totalVacDays)} ${isHe ? 'ימי חופש' : 'Days'}</span>
                    <div class="route-arc-line">
                      <span>●</span>
                      <span class="route-arc-dash"></span>
                      <span>✈️</span>
                      <span class="route-arc-dash"></span>
                      <span>●</span>
                    </div>
                  </div>
                  <div class="route-endpoint route-endpoint-end">
                    <span class="route-iata">${escapeHtml(returnOriginLabel)}</span>
                    <span class="route-date">${escapeHtml(it.return_date)}</span>
                  </div>${flightsRowHtml}
                </div>

                <div class="score-strip pass-kpi-grid">
                  <div class="score-pill kpi-cell">
                    <span class="kpi-cell-label">🏖️ ${isHe ? 'ניצול חופשה' : 'Vacation Match'}</span>
                    <strong class="kpi-cell-val" dir="ltr">${Number(p.vacation_utilization_score || 0).toFixed(1)}/100</strong>
                  </div>
                  <div class="score-pill kpi-cell">
                    <span class="kpi-cell-label">📈 ${isHe ? 'מכפיל חופש הורה' : 'PTO Multiplier'}</span>
                    <strong class="kpi-cell-val" dir="ltr">${escapeHtml(perDisplay)}</strong>
                  </div>
                  <div class="${schoolCellCls}">
                    <span class="kpi-cell-label">🎒 ${isHe ? 'חיסור מבי״ס' : 'School Missed'}</span>
                    <strong class="kpi-cell-val">${escapeHtml(schoolText)}</strong>
                  </div>
                  <div class="score-pill kpi-cell">
                    <span class="kpi-cell-label">💎 ${isHe ? 'כדאיות בונוס' : 'Award Value'}</span>
                    <strong class="kpi-cell-val" dir="ltr">${Number(fbvsVal).toFixed(1)}/100</strong>
                  </div>
                </div>

                ${weatherStripHtml}
              </div>

              <div class="proposal-pass-stub">
                <div class="stub-score-header">
                  <div class="stub-ctos-badge" dir="ltr" title="${isHe ? 'ציון התאמה משוקלל' : 'Overall Optimization Score'}">
                    <span>⭐</span>
                    <span class="stub-ctos-num">${Number(p.combined_trip_optimization_score || 0).toFixed(1)}</span>
                    <span class="stub-ctos-max">/100</span>
                  </div>
                  <span class="stub-strategy-tag" title="${escapeHtml(stratText)}">${escapeHtml(stratText)}</span>
                </div>

                <div class="stub-fare-ledger">
                  <div class="stub-fare-row">
                    <span class="stub-fare-label">💳 ${isHe ? 'נקודות מתמיד' : 'Matmid Points'}</span>
                    <span class="stub-fare-val stub-fare-points" dir="ltr">${ptsTotal}</span>
                  </div>
                  <div class="stub-fare-row">
                    <span class="stub-fare-label">💵 ${isHe ? 'תשלום במזומן' : 'Out-of-Pocket'}</span>
                    <span class="stub-fare-val" dir="ltr">$${oopCash}</span>
                  </div>
                  <div class="${savedRowCls}">
                    <span class="stub-fare-label">${isHe ? 'חיסכון נטו' : 'Net Saved'}</span>
                    <span class="stub-fare-val" dir="ltr">${netSavedDisplay} (${cppVal}¢)</span>
                  </div>
                </div>

                <div class="stub-actions-stack">
                  ${elalBookBtnHtml}
                  <div class="stub-secondary-actions">
                    <label class="compare-check-label">
                      <input type="checkbox" data-compare-id="${escapeHtml(p.id)}" ${checked} />
                      <span>${isHe ? 'השווה' : 'Compare'}</span>
                    </label>
                    <a class="btn-ics-link" href="/api/v1/vacations/${encodeURIComponent(p.id)}/export.ics" download>
                      📅 ${isHe ? 'ייצוא .ics' : 'Export .ics'}
                    </a>
                  </div>
                </div>
              </div>
            </div>

            <div class="proposal-pass-footer">
              ${twoPlusVerifyBannerHtml}
              <details class="allocations-details">
                <summary class="allocations-summary">
                  🎫 ${isHe ? `פירוט הקצאת כרטיסי בונוס ומתמיד לכל נוסע (${allocList.length} נוסעים)` : `Per-Passenger Ticket & Matmid Allocation (${allocList.length} passengers)`}
                </summary>
                <div class="allocations-table-wrap">
                  <table class="allocations-table">
                    <thead>
                      <tr>
                        <th>${isHe ? 'נוסע' : 'Passenger'}</th>
                        <th>${isHe ? 'מועדון' : 'Club'}</th>
                        <th>${isHe ? 'סוג כרטיס ומחלקה' : 'Ticket Mode & Cabin'}</th>
                        <th>${isHe ? 'נקודות' : 'Points'}</th>
                        <th>${isHe ? 'מסים + השלמת מזומן' : 'Taxes + Cash'}</th>
                      </tr>
                    </thead>
                    <tbody>${allocRows}</tbody>
                  </table>
                </div>
              </details>
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

    container.innerHTML = fallbackBannerHtml + cardsHtml + toggleFeedHtml;
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
      ? 'מתכנן חופשות משפחתיות חכם | משרד החינוך וכרטיסי בונוס אל על'
      : 'Smart Family Vacation Planner | MoE Breaks & EL AL Award Flights';

    const headerTitle = document.getElementById('header-title');
    if (headerTitle) {
      headerTitle.textContent = isHe ? 'מתכנן חופשות משפחתיות חכם' : 'Smart Family Vacation Planner';
    }
    const headerSubtitle = document.getElementById('header-subtitle');
    if (headerSubtitle) {
      headerSubtitle.textContent = isHe
        ? 'מקסום ימי חופשה של משרד החינוך, קייטנות ניצנים וכרטיסי בונוס בנקודות'
        : 'Maximize MoE school holidays, Nitzanim camps & EL AL Matmid award flights';
    }
    const heroEyebrow = document.getElementById('hero-eyebrow');
    if (heroEyebrow) {
      heroEyebrow.textContent = isHe
        ? '✈️ המראות מנתב״ג (TLV) · תכנון חופשות שנה קדימה'
        : '✈️ Departing TLV · Rolling 1-Year Vacation Planner';
    }
    const heroHeadline = document.getElementById('hero-headline');
    if (heroHeadline) {
      heroHeadline.textContent = isHe
        ? 'הפכו כל חופשת בית ספר לחופשת חלומות משפחתית'
        : 'Turn Every School Break Into a Family Escape';
    }
    const heroLead = document.getElementById('hero-lead');
    if (heroLead) {
      heroLead.textContent = isHe
        ? 'הצלבה חכמה בין לוח החופשות של משרד החינוך, קייטנות ניצנים ומושבי בונוס באל על ובמועדון הנוסע המתמיד — מקסימום חופשה במינימום ימי חופש מההורים.'
        : 'Cross-references official MoE school breaks & Nitzanim camps with EL AL Matmid award seats — more vacation days for every parent PTO day.';
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
        ? '1. תכנון חופשה: לפי חג או תאריכים ידניים'
        : '1. Vacation Search: By Holiday or Manual Dates';
    }
    const zProfile = document.getElementById('zone-profile-title');
    if (zProfile) {
      zProfile.textContent = isHe
        ? '2. פרופיל משפחה, גילאי ילדים ויתרת מתמיד'
        : '2. Family Profile, Children & Matmid Balance';
    }
    const zCalendar = document.getElementById('zone-calendar-title');
    if (zCalendar) {
      zCalendar.textContent = isHe
        ? 'לוח חופשות משרד החינוך וחפיפה רב-גילאית (תצוגה אופציונלית)'
        : 'MoE Multi-Child Vacation Calendar (Optional View)';
    }

    updateActiveModeBadge();
    setCalendarVisibility(state.isCalendarVisible, false);
    renderProfileControls();
    renderCalendarTable();
    renderComparisonBanner();
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
      const profZone = document.getElementById('zone-profile');
      if (profZone) profZone.scrollIntoView({ behavior: 'smooth' });
      return;
    }

    syncProfileStateFromDom();
    const hasDraftChanges = Boolean(
      state.profile &&
        (state.profileDirty ||
          Number(state.profile.adults_count || 2) !== 2 ||
          Number(state.profile.annual_pto_budget ?? 18) !== 18 ||
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
            annual_pto_budget: state.profile.annual_pto_budget,
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
    state.profile = createCleanGuestProfile();
    state.profileDirty = false;
    state.calendarData = null;
    state.proposals = [];
    state.showAllProposals = false;
    state.lastComparison = null;
    state.selectedProposalIds = new Set();

    await scrubBrowserClientState();
    renderProfileControls();
    renderCalendarTable();
    renderComparisonBanner();
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
      state.saveFeedbackHe = '✓ הנתונים השמורים נמחקו מהחשבון.';
      state.saveFeedbackEn = '✓ Saved family data deleted from your account.';
      await scrubBrowserClientState();
      renderProfileControls();
      renderCalendarTable();
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
    state.profile = createCleanGuestProfile();
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
          loadedProfile.annual_pto_budget = Number(pendingDraft.annual_pto_budget ?? 18);
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
    syncProfileStateFromDom();
    const destVal = (document.getElementById('select-destination') || {}).value || 'ANYWHERE';
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
        annual_pto_budget: Number((state.profile && state.profile.annual_pto_budget) ?? 18),
        matmid_points_balance: matmidBalanceVal,
        children: inlineChildren
      },
      destination_iatas: [destVal],
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
      state.proposals = res.proposals || [];
      state.showAllProposals = false;
      state.lastComparison = null;
      state.statusMessageHe = res.status_message_he || null;
      state.statusMessageEn = res.status_message_en || null;
      state.weatherFallbackMessageHe = res.weather_fallback_message_he || null;
      state.selectedProposalIds = new Set(state.proposals.slice(0, 2).map((p) => p.id));
    } catch (err) {
      const detail = extractApiErrorDetail(err);
      const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      state.proposals = [];
      state.showAllProposals = false;
      state.lastComparison = null;
      state.selectedProposalIds = new Set();
      state.validationErrorHe = `נא לוודא שטווח התאריכים ומספר הלילות בטופס החיפוש תקינים ולנסות שוב.${detailSuffixHe}`;
      state.validationErrorEn = `Verify that the return date is on or after the departure date and the nights range is valid, then try again.${detailSuffixEn}`;
    }
    renderComparisonBanner();
    renderProposals();
  }

  function bindEvents() {
    document.querySelectorAll('.mode-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        setDateMode(btn.getAttribute('data-mode'));
      });
    });

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
      };
      inputMaxNightsEl.addEventListener('input', markMaxEdited);
      inputMaxNightsEl.addEventListener('change', markMaxEdited);
    }

    const inputMinNightsEl = document.getElementById('input-min-nights');
    if (inputMinNightsEl) {
      const markMinEdited = () => {
        state.userEditedMinNights = true;
      };
      inputMinNightsEl.addEventListener('input', markMinEdited);
      inputMinNightsEl.addEventListener('change', markMinEdited);
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
      btnRunSearch.addEventListener('click', () => {
        runVacationSearch();
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
          btnToggleLocale.textContent = 'עברית / RTL';
        } else {
          state.dir = 'rtl';
          state.locale = 'he';
          document.documentElement.setAttribute('dir', 'rtl');
          document.documentElement.setAttribute('lang', 'he');
          btnToggleLocale.textContent = 'EN / LTR';
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
        }
      };
      profAdultsInput.addEventListener('input', onAdultsChange);
      profAdultsInput.addEventListener('change', onAdultsChange);
    }

    const profPtoInput = document.getElementById('prof-pto-budget');
    if (profPtoInput) {
      const onPtoChange = () => {
        if (state.profile) {
          state.profile.annual_pto_budget = Number(profPtoInput.value || 18);
          state.profileDirty = true;
        }
      };
      profPtoInput.addEventListener('input', onPtoChange);
      profPtoInput.addEventListener('change', onPtoChange);
    }

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
          state.lastComparison = null;
          state.selectedProposalIds = new Set();
          state.validationErrorHe = `לא ניתן לשמור את פרופיל המשפחה — בדקו שגילאי הילדים (0–18), מספר המבוגרים (1–6) ויתרת המתמיד תקינים.${detailSuffixHe}`;
          state.validationErrorEn = `Could not save family profile — verify adults count (1–6), child ages (0–18), and non-negative Matmid balance.${detailSuffixEn}`;
          renderComparisonBanner();
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
      } else if (target.hasAttribute('data-compare-id')) {
        const pid = target.getAttribute('data-compare-id');
        if (target.checked) state.selectedProposalIds.add(pid);
        else state.selectedProposalIds.delete(pid);
      }
    });

    document.body.addEventListener('click', (ev) => {
      const target = ev.target;
      if (!target) return;
      const toggleFeedBtn = target.closest('[data-toggle-all-proposals]');
      if (toggleFeedBtn) {
        state.showAllProposals = !state.showAllProposals;
        renderProposals();
        return;
      }
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
          const destVal = (document.getElementById('select-destination') || {}).value || 'ANYWHERE';
          const refIso = getReferenceToday();
          await apiSend('POST', '/api/v1/elal-bonus/sync', {
            destinations: [destVal],
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

    const btnCompare = document.getElementById('btn-compare-selected');
    if (btnCompare) {
      btnCompare.addEventListener('click', async () => {
        const ids = Array.from(state.selectedProposalIds);
        if (ids.length === 0) return;
        try {
          state.lastComparison = await apiSend('POST', '/api/v1/vacations/compare', { proposal_ids: ids });
          renderComparisonBanner();
        } catch (err) {
          console.error('Comparison failed:', err);
        }
      });
    }

    const btnToggleCalInline = document.getElementById('btn-toggle-calendar-inline');
    if (btnToggleCalInline) {
      btnToggleCalInline.addEventListener('click', () => {
        setCalendarVisibility(!state.isCalendarVisible, !state.isCalendarVisible);
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
          btn.classList.toggle('active', state.isCalendarVisible);
          return;
        }
        document.querySelectorAll('.desktop-nav-btn').forEach((b) => {
          if (b.getAttribute('data-desktop-zone') !== 'zone-calendar') {
            b.classList.remove('active');
          }
        });
        btn.classList.add('active');
        const el = document.getElementById(zoneId);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      });
    });

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

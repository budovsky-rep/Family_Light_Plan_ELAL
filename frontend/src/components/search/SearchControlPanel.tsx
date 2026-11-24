/**
 * SearchControlPanel Component (`frontend/src/components/search/SearchControlPanel.tsx`)
 * Implements Zone 2:
 * - 2 Flight Date Selection Modes:
 *   1. `SPECIFIC_DATES` (תאריכים ספציפיים)
 *   2. `HOLIDAY_DIRECT_INTENT` (תכנון לפי חג/חופשה ספציפיים ושנה — לדוגמה פסח 2027)
 * - 2 Airline Selection Modes:
 *   1. `EL_AL_ONLY` (התמקדות באל על + חיפוש כרטיסי בונוס)
 *   2. `ALL_AIRLINES` (כל חברות התעופה + נרמול עלויות כבודה משפחתית)
 * - Multi-select destination pre-filtering (`destination_iatas`) with `ANYWHERE` default
 */

import type {
  AirlineSelectionMode,
  DateSelectionMode,
  DirectHolidayCode,
} from '../../types/domain';

export const DATE_MODE_LABELS_HE: Record<DateSelectionMode, string> = {
  SPECIFIC_DATES: 'בחירת תאריכים ספציפיים (± ימי גמישות)',
  HOLIDAY_DIRECT_INTENT: 'חיפוש ממוקד לפי חג / חופשה ושנה (למשל פסח 2027)',
};

export const AIRLINE_MODE_LABELS_HE: Record<AirlineSelectionMode, string> = {
  EL_AL_ONLY: 'אל על בלבד + כרטיסי בונוס (rbddataclients)',
  ALL_AIRLINES: 'כל חברות התעופה (כולל השוואת כבודה ומועדונים)',
};

export const DIRECT_HOLIDAY_LABELS_HE: Record<DirectHolidayCode, string> = {
  PESACH: 'חופשת פסח (Pesach)',
  SUKKOT: 'חופשת סוכות (Sukkot)',
  YOM_KIPPUR_SUKKOT_BRIDGE: 'גשר יום כיפור–סוכות (Kippur–Sukkot Bridge)',
  HANUKKAH: 'חופשת חנוכה (Hanukkah)',
  ROSH_HASHANAH: 'ראש השנה (Rosh Hashanah)',
  PURIM: 'חופשת פורים (Purim)',
  SHAVUOT: 'חופשת שבועות (Shavuot)',
  YOM_HAATZMAUT: 'יום העצמאות (Yom HaAtzmaut)',
  LAG_BAOMER: 'ל"ג בעומר (Lag BaOmer)',
  SUMMER_JUNE_20_30: 'החופש הגדול — 20–30 ביוני (חטיבה ותיכון)',
  SUMMER_JULY: 'החופש הגדול — יולי',
  SUMMER_AUGUST: 'החופש הגדול — אוגוסט',
};

export function normalizeDestinationSelection(selectedCodes: string[]): string[] {
  const cleaned = selectedCodes
    .map((code) => code.trim().toUpperCase())
    .filter((code) => code.length > 0);
  if (cleaned.length === 0 || cleaned.includes('ANYWHERE') || cleaned.includes('ALL')) {
    return ['ANYWHERE'];
  }
  return Array.from(new Set(cleaned));
}

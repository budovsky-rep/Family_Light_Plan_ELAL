/**
 * FamilyProfileDrawer Component (`frontend/src/components/profile/FamilyProfileDrawer.tsx`)
 * Manages household adults & Matmid balance, children's ages (`child_age_years`, 0..18) and
 * OPTIONAL educational frameworks (`framework_type` — אופציונלי במצב תאריכים ספציפיים / null),
 * and per-passenger multi-club loyalty wallets across all 10 `LoyaltyProgramCode` programs.
 */

import type {
  FamilyProfile,
  LoyaltyProgramCode,
  MoEFrameworkType,
} from '../../types/domain';

export const MOE_FRAMEWORK_LABELS_HE: Record<MoEFrameworkType, string> = {
  DAYCARE_SUPERVISED: 'מעונות יום בפיקוח (תמ"ת / משרד החינוך — עד 8 באוגוסט)',
  MUNICIPAL_GAN: 'גני ילדים עירוניים (גילאי 3–6 — עד 30 ביוני + ניצנים)',
  ELEMENTARY_1_3: 'בית ספר יסודי כיתות א׳–ג׳ (עד 30 ביוני + ניצנים)',
  ELEMENTARY_4_6: 'בית ספר יסודי כיתות ד׳–ו׳ (עד 30 ביוני)',
  MIDDLE_SCHOOL_7_9: 'חטיבת ביניים כיתות ז׳–ט׳ (עד 20 ביוני — כלל היברידי)',
  HIGH_SCHOOL_10_12: 'תיכון כיתות י׳–י"ב (עד 20 ביוני + אסרו חג סוכות + בגרויות)',
  SPECIAL_ED: 'חינוך מיוחד (הארכת שנת הלימודים עד 15 באוגוסט)',
  RELIGIOUS_HAREDI: 'חינוך ממלכתי-דתי / חרדי (לוח חופשות ייעודי)',
};

export const LOYALTY_PROGRAM_LABELS: Record<LoyaltyProgramCode, string> = {
  ELAL_MATMID: 'El Al Matmid (אל על הנוסע המתמיד)',
  BRITISH_AVIOS: 'British Airways Executive Club (Avios)',
  FLYING_BLUE: 'Air France / KLM Flying Blue',
  UNITED_MILEAGEPLUS: 'United MileagePlus',
  MILES_AND_MORE: 'Lufthansa Group Miles & More',
  DELTA_SKYMILES: 'Delta SkyMiles',
  QANTAS_FREQUENT_FLYER: 'Qantas Frequent Flyer',
  AEGEAN_MILES_BONUS: 'Aegean Miles+Bonus',
  AMEX_MR_ISRAEL: 'Amex Membership Rewards Israel',
  ISRAELI_CC_TRAVEL_POINTS: 'Israeli Credit Card Travel Points (MAX / Cal / Isracard)',
};

export function renderFamilyProfileDrawerSummary(
  profile: FamilyProfile,
  isSpecificDatesMode: boolean
): string {
  const optionalNote = isSpecificDatesMode
    ? 'בחירת מסגרת חינוכית היא אופציונלית (optional / null) במצב תאריכים ספציפיים — רק גיל הילד נדרש לחישוב תעריף טיסה'
    : 'התאמת חופשות משרד החינוך לפי גיל ומסגרת לימודים לכל ילד';

  return `
    <section class="profile-drawer-section" aria-label="פרופיל משפחה ומועדוני תעופה">
      <p class="framework-optional-banner">${optionalNote}</p>
    </section>
  `;
}

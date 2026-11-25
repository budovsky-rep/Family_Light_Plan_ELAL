/**
 * ElAlBonusSearchSubPanel Component (`frontend/src/components/search/ElAlBonusSearchSubPanel.tsx`)
 * Displays live/seeded El Al `https://www.elal.com/rbddataclients/` bonus seat controls,
 * cabin preferences (`ECONOMY`, `PREMIUM`, `BUSINESS`), and the 6 Family Bonus Fulfillment Strategies.
 */

import type { BonusDirectionCoverage, FulfillmentStrategy } from '../../types/domain';

export const ELAL_RBD_SOURCE_URL = 'https://www.elal.com/rbddataclients/';

export const STRATEGY_BADGE_LABELS_HE: Record<FulfillmentStrategy, string> = {
  FULL_BONUS_SAME_CABIN: 'בונוס מלא באותה מחלקה',
  SPLIT_CABIN_BONUS: 'בונוס מפוצל בין מחלקות (אותה טיסה)',
  HYBRID_BONUS_PLUS_CASH: 'בונוס לחלק מהנוסעים + כרטיסים מסחריים',
  ONE_WAY_BONUS_ONE_WAY_CASH: 'כיוון אחד בבונוס + כיוון אחד מסחרי',
  CASH_AND_POINTS: 'נקודות + כסף (Cash & Points)',
  MULTI_CLUB_PER_PASSENGER_SPLIT: 'פיצול נקודות בין מועדונים ונוסעים',
  COMMERCIAL_CASH_ONLY: 'כרטיסים מסחריים (ללא בונוס)',
};

export function resolveStrategyBadgeHe(
  strategy: FulfillmentStrategy,
  coverage: BonusDirectionCoverage,
  destinationIata: string,
  returnOriginIata: string,
  commercialTicketsCount = 0
): string {
  const dest = (destinationIata || '').trim().toUpperCase();
  const retOrig = (returnOriginIata || dest).trim().toUpperCase();
  const isOpenJaw = Boolean(dest && retOrig && dest !== retOrig);

  if (strategy === 'ONE_WAY_BONUS_ONE_WAY_CASH') {
    if (coverage === 'BOTH_DIRECTIONS') {
      if (isOpenJaw) {
        return commercialTicketsCount > 0
          ? `מסלול משולב (${dest}/${retOrig}) · בונוס לחלק מהנוסעים`
          : `מסלול משולב (הלוך ל-${dest}, חזור מ-${retOrig})`;
      }
      return 'מימוש נקודות לכיוון אחד';
    }
    return isOpenJaw ? `מסלול משולב (הלוך ל-${dest}, חזור מ-${retOrig})` : '';
  }
  if (strategy === 'FULL_BONUS_SAME_CABIN') {
    return isOpenJaw ? `מסלול משולב (הלוך ל-${dest}, חזור מ-${retOrig})` : '';
  }
  return STRATEGY_BADGE_LABELS_HE[strategy] || strategy;
}

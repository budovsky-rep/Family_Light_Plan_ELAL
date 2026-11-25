/**
 * ElAlBonusSearchSubPanel Component (`frontend/src/components/search/ElAlBonusSearchSubPanel.tsx`)
 * Displays live/seeded El Al `https://www.elal.com/rbddataclients/` bonus seat controls,
 * cabin preferences (`ECONOMY`, `PREMIUM`, `BUSINESS`), and the 6 Family Bonus Fulfillment Strategies.
 */

import type { FulfillmentStrategy } from '../../types/domain';

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

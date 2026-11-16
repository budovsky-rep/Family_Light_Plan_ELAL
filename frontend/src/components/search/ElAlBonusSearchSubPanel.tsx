/**
 * ElAlBonusSearchSubPanel Component (`frontend/src/components/search/ElAlBonusSearchSubPanel.tsx`)
 * Displays live/seeded El Al `https://www.elal.com/rbddataclients/` bonus seat controls,
 * cabin preferences (`ECONOMY`, `PREMIUM`, `BUSINESS`), and the 6 Family Bonus Fulfillment Strategies.
 */

import type { FulfillmentStrategy } from '../../types/domain';

export const ELAL_RBD_SOURCE_URL = 'https://www.elal.com/rbddataclients/';

export const STRATEGY_BADGE_LABELS_HE: Record<FulfillmentStrategy, string> = {
  FULL_BONUS_SAME_CABIN: 'בונוס מלא באותה מחלקה (100% נקודות מתמיד)',
  SPLIT_CABIN_BONUS: 'פיצול מחלקות בונוס באותה טיסה (הורים + ילדים)',
  HYBRID_BONUS_PLUS_CASH: 'היברידי: כרטיסי בונוס + השלמת כרטיסי מזומן באותה טיסה',
  ONE_WAY_BONUS_ONE_WAY_CASH: 'כיוון אחד בונוס + כיוון שני מזומן',
  CASH_AND_POINTS: 'Cash & Points (שילוב נקודות ומזומן)',
  MULTI_CLUB_PER_PASSENGER_SPLIT: 'פיצול רב-מועדוני לפי נוסע (Matmid + Avios / Flying Blue / Star Alliance)',
  COMMERCIAL_CASH_FARE: 'כרטיס מסחרי רגיל (מזומן כולל כבודה משפחתית)',
};

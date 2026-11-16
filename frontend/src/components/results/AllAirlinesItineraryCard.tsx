/**
 * AllAirlinesItineraryCard Component (`frontend/src/components/results/AllAirlinesItineraryCard.tsx`)
 * Renders commercial & multi-club partner airline itineraries (`ALL_AIRLINES` mode)
 * with normalized family baggage costs (`FamilyBaggageNormalizer`) and multi-club
 * per-passenger award split (`MULTI_CLUB_PER_PASSENGER_SPLIT`).
 */

export interface CommercialBaggageBreakdown {
  carrier_code: string;
  carrier_name: string;
  base_fare_usd: number;
  normalized_baggage_fee_usd: number;
  total_normalized_family_usd: number;
}

export function formatNormalizedBaggageLabel(breakdown: CommercialBaggageBreakdown): string {
  return `${breakdown.carrier_name} (${breakdown.carrier_code}) — סה"כ משפחתי כולל כבודה: $${breakdown.total_normalized_family_usd.toFixed(0)}`;
}

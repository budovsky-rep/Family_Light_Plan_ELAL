/**
 * AllAirlinesItineraryCard Component (`frontend/src/components/results/AllAirlinesItineraryCard.tsx`)
 * Renders commercial & multi-club partner airline itineraries (`ALL_AIRLINES` mode)
 * with family baggage allowance metadata and multi-club per-passenger award split
 * (`MULTI_CLUB_PER_PASSENGER_SPLIT`).
 */

export interface CarrierItinerarySummary {
  carrier_code: string;
  carrier_name: string;
  included_checked_bags: number;
  is_direct_flight: boolean;
}

export function formatCarrierItineraryLabel(summary: CarrierItinerarySummary): string {
  const flightMode = summary.is_direct_flight ? 'טיסה ישירה' : 'טיסת המשך';
  return `${summary.carrier_name} (${summary.carrier_code}) — ${flightMode} · כבודה משפחתית: ${summary.included_checked_bags}`;
}

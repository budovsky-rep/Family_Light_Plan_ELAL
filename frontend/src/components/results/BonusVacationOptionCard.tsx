/**
 * BonusVacationOptionCard Component (`frontend/src/components/results/BonusVacationOptionCard.tsx`)
 * Renders a ranked El Al bonus or multi-club vacation proposal card with:
 * - Recommendation tier badge (`RECOMMENDED`, `ALTERNATIVE`, `BUDGET_STRETCH`)
 * - Mathematical score breakdown (`CTOS`, `HAS`, `FBVS`, `SAP`, `CCG`)
 * - Direction coverage statement, per-direction bonus seat coupons & 1-ticket minimum Matmid points
 * - Direct EL AL Google Flights booking handoff
 */

export interface ProposalSummary {
  id: string;
  rank: number;
  recommendation_tier: string;
  holiday_alignment_score: number;
  flight_bonus_value_score: number;
  combined_trip_optimization_score: number;
  school_absence_penalty: number;
  childcare_coverage_gain: number;
  workplace_vacation_days_cost: number;
  explanation_he: string;
}

export function formatScoreBadge(label: string, score: number): string {
  return `<span class="score-badge" dir="ltr"><strong>${label}:</strong> ${score.toFixed(1)}</span>`;
}

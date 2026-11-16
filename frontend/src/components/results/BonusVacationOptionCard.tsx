/**
 * BonusVacationOptionCard Component (`frontend/src/components/results/BonusVacationOptionCard.tsx`)
 * Renders a ranked El Al bonus or multi-club vacation proposal card with:
 * - Recommendation tier badge (`RECOMMENDED`, `ALTERNATIVE`, `BUDGET_STRETCH`)
 * - Mathematical score breakdown (`CTOS`, `VUS`, `FBVS`, `PER`, `SAP`, `CCG`)
 * - Per-passenger ticket allocation table (`PassengerTicketAllocation[]`)
 * - 1-click `.ics` calendar download & comparison selection checkbox
 */

export interface ProposalSummary {
  id: string;
  rank: number;
  recommendation_tier: string;
  vacation_utilization_score: number;
  family_bonus_value_score: number;
  combined_trip_optimization_score: number;
  parent_pto_efficiency_ratio: number;
  school_absence_penalty: number;
  childcare_coverage_gain: number;
  explanation_he: string;
}

export function formatScoreBadge(label: string, score: number): string {
  return `<span class="score-badge" dir="ltr"><strong>${label}:</strong> ${score.toFixed(1)}</span>`;
}

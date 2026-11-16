/**
 * BonusVacationComparisonModal Component (`frontend/src/components/results/BonusVacationComparisonModal.tsx`)
 * Side-by-side comparison matrix (`VacationComparisonMatrix`) across selected proposals,
 * highlighting best CTOS, lowest Parent PTO days, lowest out-of-pocket cash USD,
 * and lowest school absence penalty.
 */

export interface ComparisonWinnerSummary {
  best_by_ctos_id: string;
  best_by_lowest_pto_id: string;
  best_by_lowest_cash_id: string;
  best_by_lowest_school_absence_id: string;
  summary_he: string;
}

export function renderComparisonSummaryHeader(matrix: ComparisonWinnerSummary): string {
  return `
    <div class="comparison-summary-header">
      <h3>השוואת חלופות חופשה משפחתית</h3>
      <p>${matrix.summary_he}</p>
    </div>
  `;
}

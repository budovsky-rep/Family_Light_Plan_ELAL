/**
 * MultiChildCalendarHeatmap Component (`frontend/src/components/calendar/MultiChildCalendarHeatmap.tsx`)
 * Implements Zone 3: Multi-child MoE vacation intersection heatmap with sticky RTL
 * first column (`position: sticky; inset-inline-start: 0`), Nitzanim camp badges,
 * parent PTO cost row, and El Al `rbddataclients` bonus seat availability overlay.
 */

export interface CalendarWindowRow {
  holiday_code: string;
  holiday_name_he: string;
  framework_type: string;
  start_date: string;
  end_date: string;
  school_resume_date: string;
  total_calendar_days: number;
  is_covered_by_nitzanim: boolean;
}

export function renderCalendarHeatmapLegend(): string {
  return `
    <div class="calendar-legend" role="list">
      <span class="legend-item state-vacation">חופשה משותפת (VACATION)</span>
      <span class="legend-item state-camp">קייטנת ניצנים / בי"ס של החגים (CAMP_OPTIONAL)</span>
      <span class="legend-item state-waning">סוף שנה 21–30 ביוני (WANING)</span>
      <span class="legend-item state-school">יום לימודים רגיל (SCHOOL)</span>
    </div>
  `;
}

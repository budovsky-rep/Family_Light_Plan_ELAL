/**
 * Family Vacation Planner — Interactive Frontend Application (`frontend/src/app.js`)
 *
 * Implements:
 * - All 3 Flight Date Selection Modes:
 *   1. `SPECIFIC_DATES` (תאריכים ספציפיים — בחירת מסגרת לימודים לילד היא אופציונלי / optional / null)
 *   2. `MOE_VACATION_MAXIMIZATION` (מקסום חופשות שנתי לפי משרד החינוך)
 *   3. `HOLIDAY_DIRECT_INTENT` (חיפוש ממוקד לפי חג/חופשה ושנה — כגון פסח 2027)
 * - Both Airline Modes: `EL_AL_ONLY` (כולל חיפוש כרטיסי בונוס באתר https://www.elal.com/rbddataclients/) & `ALL_AIRLINES`
 * - Destination discovery (`ANYWHERE` + 25 destinations & metro codes `ROM`, `NYC`, `LON`, `PAR`, `TYO`)
 * - All 8 Israeli Ministry of Education (`MoEFrameworkType`) frameworks + age-based auto-suggestion
 * - Per-passenger multi-club loyalty wallets across all 10 `LoyaltyProgramCode` programs
 * - All 6 Family Bonus Fulfillment Strategies & side-by-side comparison modal + `.ics` export
 * - BiDi Hebrew (`rtl` / `he`) & English (`ltr` / `en`) live layout switcher
 */

(function () {
  'use strict';

  const MOE_FRAMEWORKS = [
    { value: '', labelHe: 'ללא מסגרת / אופציונלי (Optional / null)', labelEn: 'Optional / None (Specific Dates)' },
    { value: 'DAYCARE_SUPERVISED', labelHe: 'מעונות יום בפיקוח (גילאי 0–3 — עד 8 באוגוסט)', labelEn: 'Supervised Daycare (Ages 0–3)' },
    { value: 'MUNICIPAL_GAN', labelHe: 'גני ילדים עירוניים (גילאי 3–6 — עד 30 ביוני + ניצנים)', labelEn: 'Municipal Kindergarten (Ages 3–6 + Nitzanim)' },
    { value: 'ELEMENTARY_1_3', labelHe: 'יסודי כיתות א׳–ג׳ (גילאי 6–9 — עד 30 ביוני + ניצנים)', labelEn: 'Elementary Grades 1–3 (+ Nitzanim)' },
    { value: 'ELEMENTARY_4_6', labelHe: 'יסודי כיתות ד׳–ו׳ (גילאי 9–12 — עד 30 ביוני)', labelEn: 'Elementary Grades 4–6' },
    { value: 'MIDDLE_SCHOOL_7_9', labelHe: 'חטיבת ביניים כיתות ז׳–ט׳ (גילאי 12–15 — עד 20 ביוני)', labelEn: 'Middle School Grades 7–9 (Ends June 20)' },
    { value: 'HIGH_SCHOOL_10_12', labelHe: 'תיכון כיתות י׳–י"ב (גילאי 15–18 — עד 20 ביוני + בגרויות)', labelEn: 'High School Grades 10–12 (Ends June 20)' },
    { value: 'SPECIAL_ED', labelHe: 'חינוך מיוחד (הארכה עד 15 באוגוסט)', labelEn: 'Special Education (Until Aug 15)' },
    { value: 'RELIGIOUS_HAREDI', labelHe: 'חינוך ממלכתי-דתי / חרדי', labelEn: 'Religious / Haredi Framework' }
  ];

  const LOYALTY_PROGRAMS = [
    { value: 'ELAL_MATMID', label: 'El Al Matmid (אל על הנוסע המתמיד)' },
    { value: 'BRITISH_AVIOS', label: 'British Airways Avios (Oneworld)' },
    { value: 'FLYING_BLUE', label: 'Air France / KLM Flying Blue (SkyTeam)' },
    { value: 'UNITED_MILEAGEPLUS', label: 'United MileagePlus (Star Alliance)' },
    { value: 'MILES_AND_MORE', label: 'Lufthansa Group Miles & More' },
    { value: 'DELTA_SKYMILES', label: 'Delta SkyMiles' },
    { value: 'QANTAS_FREQUENT_FLYER', label: 'Qantas Frequent Flyer' },
    { value: 'AEGEAN_MILES_BONUS', label: 'Aegean Miles+Bonus' },
    { value: 'AMEX_MR_ISRAEL', label: 'Amex Membership Rewards Israel' },
    { value: 'ISRAELI_CC_TRAVEL_POINTS', label: 'Israeli Credit Card Travel Points' }
  ];

  const state = {
    locale: 'he',
    dir: 'rtl',
    dateSelectionMode: 'HOLIDAY_DIRECT_INTENT',
    airlineSelectionMode: 'EL_AL_ONLY',
    isCalendarVisible: false,
    profile: null,
    calendarData: null,
    proposals: [],
    selectedProposalIds: new Set()
  };

  function setCalendarVisibility(visible, scrollToIt) {
    state.isCalendarVisible = Boolean(visible);
    const calZone = document.getElementById('zone-calendar');
    const isHe = state.locale === 'he';
    if (calZone) {
      if (state.isCalendarVisible) {
        calZone.removeAttribute('hidden');
        calZone.style.display = 'block';
        if (scrollToIt) {
          calZone.scrollIntoView({ behavior: 'smooth' });
        }
      } else {
        calZone.setAttribute('hidden', '');
        calZone.style.display = 'none';
      }
    }
    const btnTop = document.getElementById('btn-toggle-calendar');
    if (btnTop) {
      btnTop.textContent = state.isCalendarVisible
        ? isHe
          ? '📅 הסתר לוח משרד החינוך'
          : '📅 Hide MoE Calendar'
        : isHe
          ? '📅 לוח חופשות משרד החינוך (הצג)'
          : '📅 Show MoE Calendar';
    }
    const btnInline = document.getElementById('btn-toggle-calendar-inline');
    if (btnInline) {
      btnInline.textContent = state.isCalendarVisible
        ? isHe
          ? '📅 הסתר לוח חופשות משרד החינוך'
          : '📅 Hide MoE Vacation Calendar'
        : isHe
          ? '📅 הצג לוח חופשות משרד החינוך'
          : '📅 Show MoE Vacation Calendar';
    }
  }

  function suggestFrameworkByAge(ageYears) {
    const age = Number(ageYears) || 0;
    if (age < 3) return 'DAYCARE_SUPERVISED';
    if (age < 6) return 'MUNICIPAL_GAN';
    if (age < 9) return 'ELEMENTARY_1_3';
    if (age < 12) return 'ELEMENTARY_4_6';
    if (age < 15) return 'MIDDLE_SCHOOL_7_9';
    return 'HIGH_SCHOOL_10_12';
  }

  function classifyFareByAge(ageYears) {
    const age = Number(ageYears) || 0;
    if (age < 2) return 'INFANT_LAP (תינוק <2)';
    if (age < 12) return 'CHILD_2_11 (ילד 2–11)';
    return 'YOUTH_12_18 (נוער 12–18)';
  }

  async function apiGet(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
      throw new Error(`GET ${path} failed (${resp.status})`);
    }
    return resp.json();
  }

  async function apiSend(method, path, bodyObj) {
    const resp = await fetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyObj || {})
    });
    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`${method} ${path} failed (${resp.status}): ${errText}`);
    }
    return resp.json();
  }

  function recalculateHouseholdPointsFromWallets() {
    if (!state.profile) return { matmidTotal: 0, allClubsTotal: 0, byProgram: {} };
    const wallets = state.profile.passenger_loyalty_wallets || [];
    let matmidTotal = 0;
    let allClubsTotal = 0;
    const byProgram = {};

    wallets.forEach((w) => {
      const pts = Math.max(0, Number(w.available_points) || 0);
      const prog = String(w.program_code || 'ELAL_MATMID');
      allClubsTotal += pts;
      byProgram[prog] = (byProgram[prog] || 0) + pts;
      if (prog === 'ELAL_MATMID') {
        matmidTotal += pts;
      }
    });

    state.profile.matmid_points_balance = matmidTotal;
    const matmidInput = document.getElementById('prof-matmid-points');
    if (matmidInput) {
      matmidInput.value = matmidTotal;
    }

    const ptsPill = document.getElementById('header-points-pill');
    if (ptsPill) {
      if (allClubsTotal > matmidTotal) {
        ptsPill.textContent = `${matmidTotal.toLocaleString()} Matmid (${allClubsTotal.toLocaleString()} Total pts)`;
      } else {
        ptsPill.textContent = `${matmidTotal.toLocaleString()} Matmid pts`;
      }
    }

    const stripEl = document.getElementById('family-clubs-totals-strip');
    if (stripEl) {
      const isHe = state.locale === 'he';
      const progShortLabels = {
        ELAL_MATMID: isHe ? 'אל על מתמיד' : 'El Al Matmid',
        BRITISH_AVIOS: 'Avios',
        FLYING_BLUE: 'Flying Blue',
        UNITED_MILEAGEPLUS: 'United MP',
        MILES_AND_MORE: 'Miles & More',
        DELTA_SKYMILES: 'Delta SkyMiles',
        QANTAS_FREQUENT_FLYER: 'Qantas FF',
        AEGEAN_MILES_BONUS: 'Aegean',
        AMEX_MR_ISRAEL: 'Amex MR IL',
        ISRAELI_CC_TRAVEL_POINTS: isHe ? 'נקודות אשראי' : 'CC Travel Pts'
      };
      const breakdownPills = Object.entries(byProgram)
        .filter(([, total]) => total > 0)
        .map(
          ([prog, total]) =>
            `<span class="score-pill" dir="ltr">${progShortLabels[prog] || prog}: <strong>${Number(total).toLocaleString()}</strong></span>`
        )
        .join('');
      const totalTitle = isHe ? 'סה״כ נקודות משפחתי (מכל המועדונים):' : 'Total Family Points (All Clubs):';
      stripEl.innerHTML = `
        <span class="score-pill" style="background: #eff6ff; border-color: #93c5fd; color: #1e3a8a;">
          ${totalTitle} <strong dir="ltr">${allClubsTotal.toLocaleString()}</strong>
        </span>
        ${breakdownPills}
      `;
    }

    return { matmidTotal, allClubsTotal, byProgram };
  }

  function renderProfileControls() {
    if (!state.profile) return;
    recalculateHouseholdPointsFromWallets();
    const adultsInput = document.getElementById('prof-adults-count');
    const ptoInput = document.getElementById('prof-pto-budget');
    const matmidInput = document.getElementById('prof-matmid-points');
    if (adultsInput) adultsInput.value = state.profile.adults_count;
    if (ptoInput) ptoInput.value = state.profile.annual_pto_budget;
    if (matmidInput) matmidInput.value = state.profile.matmid_points_balance;

    const famPill = document.getElementById('header-family-pill');
    if (famPill) {
      famPill.textContent = `${state.profile.adults_count} Adults + ${state.profile.children.length} Children`;
    }

    const childrenContainer = document.getElementById('children-list-container');
    if (childrenContainer) {
      const isOptionalMode = state.dateSelectionMode === 'SPECIFIC_DATES';
      childrenContainer.innerHTML = state.profile.children
        .map((child, idx) => {
          const fwOptions = MOE_FRAMEWORKS.map((fw) => {
            const currentFw = child.framework_type === null ? '' : String(child.framework_type || '');
            const selected = currentFw === fw.value ? 'selected' : '';
            const label = state.locale === 'he' ? fw.labelHe : fw.labelEn;
            return `<option value="${fw.value}" ${selected}>${label}</option>`;
          }).join('');
          return `
            <div class="proposal-card" style="padding: 10px; margin-block-end: 8px;">
              <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between;">
                <strong>${child.child_name_he || 'ילד/ה #' + (idx + 1)}</strong>
                <span class="score-pill" dir="ltr">${classifyFareByAge(child.child_age_years)}</span>
                <button type="button" class="btn-secondary" data-remove-child="${idx}" style="min-height: 30px; padding: 2px 8px; font-size: 0.75rem;">${state.locale === 'he' ? 'הסר' : 'Remove'}</button>
              </div>
              <div class="form-grid form-grid-2" style="margin-block-end: 4px; margin-block-start: 6px;">
                <div class="form-field">
                  <label>${state.locale === 'he' ? 'גיל הילד/ה (0–18):' : 'Child Age (0–18):'}</label>
                  <input type="number" min="0" max="18" value="${child.child_age_years}" data-child-age="${idx}" dir="ltr" />
                </div>
                <div class="form-field">
                  <label>${state.locale === 'he' ? 'מסגרת חינוכית (' + (isOptionalMode ? 'אופציונלי / Optional' : 'לפי משרד החינוך') + '):' : 'MoE Framework (' + (isOptionalMode ? 'Optional / אופציונלי' : 'MoE Calendar') + '):'}</label>
                  <select data-child-fw="${idx}">
                    ${fwOptions}
                  </select>
                </div>
              </div>
            </div>
          `;
        })
        .join('');
    }

    const walletsContainer = document.getElementById('wallets-list-container');
    if (walletsContainer) {
      walletsContainer.innerHTML = (state.profile.passenger_loyalty_wallets || [])
        .map((w, idx) => {
          const progOptions = LOYALTY_PROGRAMS.map((p) => {
            const sel = w.program_code === p.value ? 'selected' : '';
            return `<option value="${p.value}" ${sel}>${p.label}</option>`;
          }).join('');
          return `
            <div class="proposal-card" style="padding: 10px; margin-block-end: 8px; border-inline-start-color: #d97706;">
              <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; margin-block-end: 6px;">
                <strong style="font-size: 0.85rem;">💳 ${w.passenger_name || (state.locale === 'he' ? 'נוסע #' + (idx + 1) : 'Passenger #' + (idx + 1))} <span style="font-weight: 400; color: var(--text-secondary);">(${w.passenger_id})</span></strong>
                <button type="button" class="btn-secondary" data-remove-wallet="${idx}" style="min-height: 28px; padding: 2px 10px; font-size: 0.75rem; color: #be123c; border-color: #fecdd3; background: #fff1f2;">
                  ${state.locale === 'he' ? '🗑️ הסר מועדון' : '🗑️ Remove Club'}
                </button>
              </div>
              <div class="form-grid form-grid-3" style="margin-block-end: 0;">
                <div class="form-field">
                  <label>${state.locale === 'he' ? 'נוסע' : 'Passenger'} (${w.passenger_id}):</label>
                  <input type="text" value="${w.passenger_name}" data-wallet-name="${idx}" />
                </div>
                <div class="form-field">
                  <label>${state.locale === 'he' ? 'מועדון תעופה:' : 'Loyalty Club:'}</label>
                  <select data-wallet-prog="${idx}">${progOptions}</select>
                </div>
                <div class="form-field">
                  <label>${state.locale === 'he' ? 'נקודות זמינות לנוסע:' : 'Available Points:'}</label>
                  <input type="number" min="0" step="1000" value="${w.available_points}" data-wallet-pts="${idx}" dir="ltr" />
                </div>
              </div>
            </div>
          `;
        })
        .join('');
    }
  }

  function renderCalendarTable() {
    const tbody = document.getElementById('moe-calendar-tbody');
    const syncBadge = document.getElementById('calendar-sync-badge');
    if (!tbody || !state.calendarData) return;

    if (syncBadge) {
      syncBadge.textContent = `${state.calendarData.school_year} | ${state.calendarData.calendar_sync_source}`;
    }

    const windows = state.calendarData.windows || [];
    const seen = new Set();
    const deduped = windows.filter((w) => {
      const key = `${w.holiday_code}::${w.framework_type}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    tbody.innerHTML = deduped
      .slice(0, 28)
      .map((w) => {
        const nitzBadge = w.is_covered_by_nitzanim
          ? `<span class="badge-camp">ניצנים (${w.nitzanim_start_date} עד ${w.nitzanim_end_date})</span>`
          : '<span class="badge-vacation">חופשה מלאה</span>';
        const resumeDate = w.school_resume_date || w.resume_date || w.end_date || '';
        const daysCount =
          w.total_calendar_days ||
          w.calendar_days_count ||
          Math.max(1, Math.round((new Date(w.end_date) - new Date(w.start_date)) / 86400000) + 1);
        return `
          <tr>
            <td class="sticky-col">${w.holiday_name_he}</td>
            <td><code>${w.framework_type}</code></td>
            <td dir="ltr">${w.start_date}</td>
            <td dir="ltr">${w.end_date}</td>
            <td dir="ltr">${resumeDate}</td>
            <td dir="ltr">${daysCount}</td>
            <td>${nitzBadge}</td>
          </tr>
        `;
      })
      .join('');
  }

  function renderProposals() {
    const container = document.getElementById('proposals-container');
    if (!container) return;
    if (!state.proposals || state.proposals.length === 0) {
      container.innerHTML = '<p>לא נמצאו חלופות תואמות. נסה להרחיב את טווח הלילות או ימי הגשר.</p>';
      return;
    }

    container.innerHTML = state.proposals
      .map((p, idx) => {
        const it = p.itinerary || {};
        const allocList = it.family_ticket_allocation || it.passenger_allocations || [];
        const allocRows = allocList
          .map(
            (a) => `
              <tr>
                <td>${a.passenger_label || a.passenger_id || ''}</td>
                <td><code>${a.program_code || a.program_used || 'CASH'}</code></td>
                <td>${a.ticket_mode || a.outbound_ticket_kind || ''} (${a.cabin_class || a.outbound_cabin || 'ECONOMY'})</td>
                <td dir="ltr">${Number(a.points_used ?? a.points_charged ?? 0).toLocaleString()} pts</td>
                <td dir="ltr">$${Number(a.taxes_usd ?? a.taxes_and_fees_usd ?? 0).toFixed(0)} + $${Number(a.cash_fare_usd ?? a.cash_fare_charged_usd ?? 0).toFixed(0)}</td>
              </tr>
            `
          )
          .join('');

        const checked = state.selectedProposalIds.has(p.id) ? 'checked' : '';
        const rankNum = p.rank_order || p.rank || (idx + 1);
        const tierLabel = p.recommendation_tier || (idx === 0 ? 'RECOMMENDED' : idx < 4 ? 'TOP_CHOICE' : 'ALTERNATIVE');
        const fbvsVal = p.flight_bonus_value_score ?? p.family_bonus_value_score ?? 0;
        const perVal = p.pto_efficiency_ratio ?? p.parent_pto_efficiency_ratio ?? 0;
        const explHe = p.explanation_summary_he || p.explanation_he || '';
        return `
          <article class="proposal-card tier-${tierLabel}">
            <div class="proposal-top-bar">
              <div>
                <span class="badge-vacation">#${rankNum} ${tierLabel}</span>
                <strong style="font-size: 1.02rem; margin-inline-start: 8px;">
                  ✈️ ${it.destination_city_he || it.destination_iata} (${it.origin_iata} ⇄ ${it.destination_iata})
                </strong>
                <span dir="ltr" style="margin-inline-start: 8px; font-weight: 600;">
                  ${it.departure_date} → ${it.return_date} (${it.trip_nights} לילות)
                </span>
              </div>
              <div style="display: flex; gap: 8px; align-items: center;">
                <label style="font-size: 0.8rem; display: flex; align-items: center; gap: 4px;">
                  <input type="checkbox" data-compare-id="${p.id}" ${checked} /> השווה
                </label>
                <a class="btn-secondary" href="/api/v1/vacations/${encodeURIComponent(p.id)}/export.ics" download style="text-decoration: none; font-size: 0.8rem; padding: 6px 10px; min-height: 34px;">
                  📅 ייצוא .ics ליומן
                </a>
              </div>
            </div>

            <div class="score-strip">
              <span class="score-pill" dir="ltr">CTOS: ${Number(p.combined_trip_optimization_score).toFixed(1)}/100</span>
              <span class="score-pill" dir="ltr">VUS (חופש): ${Number(p.vacation_utilization_score).toFixed(1)}</span>
              <span class="score-pill" dir="ltr">FBVS (בונוס): ${Number(fbvsVal).toFixed(1)}</span>
              <span class="score-pill" dir="ltr">PER: ${Number(perVal).toFixed(2)}x</span>
              <span class="score-pill" dir="ltr">SAP (היעדרות): ${Number(p.school_absence_penalty).toFixed(1)}</span>
              <span class="score-pill" dir="ltr">Strategy: ${it.fulfillment_strategy}</span>
              <span class="score-pill" dir="ltr">Points: ${Number(it.total_matmid_points || 0).toLocaleString()}</span>
              <span class="score-pill" dir="ltr">Cash Saved: $${Number(it.net_cash_saved_usd || 0).toFixed(0)} (${Number(it.cents_per_point_value || 0).toFixed(2)}¢/pt)</span>
            </div>

            <p style="margin: 0; font-size: 0.88rem; color: var(--text-secondary);">
              ${explHe}
            </p>

            <details>
              <summary style="cursor: pointer; font-weight: 600; font-size: 0.84rem; color: var(--brand-primary);">
                פירוט הקצאת כרטיסי בונוס ומועדונים לכל נוסע (${allocList.length} נוסעים)
              </summary>
              <table class="allocations-table">
                <thead>
                  <tr>
                    <th>נוסע</th>
                    <th>מועדון</th>
                    <th>סוג כרטיס ומחלקה</th>
                    <th>נקודות</th>
                    <th>מסים + השלמת מזומן</th>
                  </tr>
                </thead>
                <tbody>${allocRows}</tbody>
              </table>
            </details>
          </article>
        `;
      })
      .join('');
  }

  function setDateMode(mode) {
    state.dateSelectionMode = mode;
    document.querySelectorAll('.mode-tab-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-mode') === mode);
    });
    const cHoliday = document.getElementById('controls-holiday-direct');
    const cMoe = document.getElementById('controls-moe-maximize');
    const cSpec = document.getElementById('controls-specific-dates');
    if (cHoliday) cHoliday.style.display = mode === 'HOLIDAY_DIRECT_INTENT' ? 'grid' : 'none';
    if (cMoe) cMoe.style.display = mode === 'MOE_VACATION_MAXIMIZATION' ? 'grid' : 'none';
    if (cSpec) cSpec.style.display = mode === 'SPECIFIC_DATES' ? 'grid' : 'none';

    const badge = document.getElementById('active-mode-badge');
    if (badge) {
      if (mode === 'SPECIFIC_DATES') badge.textContent = 'Mode 1: תאריכים ספציפיים (מסגרת אופציונלית)';
      else if (mode === 'MOE_VACATION_MAXIMIZATION') badge.textContent = 'Mode 2: מקסום שנתי (משרד החינוך)';
      else badge.textContent = 'Mode 3: חג ושנה ספציפיים';
    }
    renderProfileControls();
  }

  async function loadInitialData() {
    try {
      state.profile = await apiGet('/api/v1/profile');
      renderProfileControls();
      state.calendarData = await apiGet('/api/v1/moe-calendar/2026-2027');
      renderCalendarTable();
      await runVacationSearch();
    } catch (err) {
      console.error('Initialization error:', err);
    }
  }

  async function runVacationSearch() {
    const destVal = (document.getElementById('select-destination') || {}).value || 'ROM';
    const airlineVal = (document.getElementById('select-airline-mode') || {}).value || 'EL_AL_ONLY';
    const holidayVal = (document.getElementById('select-direct-holiday') || {}).value || 'PESACH';
    const yearVal = Number((document.getElementById('select-direct-year') || {}).value || 2027);
    const schoolYearVal = (document.getElementById('select-school-year') || {}).value || '2026-2027';
    const overlapVal = (document.getElementById('select-overlap-policy') || {}).value || 'MAXIMIZE_EFFICIENCY_SCORE';
    const depVal = (document.getElementById('input-dep-date') || {}).value || '2027-04-11';
    const retVal = (document.getElementById('input-ret-date') || {}).value || '2027-04-18';
    const flexVal = Number((document.getElementById('input-flex-days') || {}).value || 2);
    const minNights = Number((document.getElementById('input-min-nights') || {}).value || 4);
    const maxNights = Number((document.getElementById('input-max-nights') || {}).value || 10);
    const bridgeDays = Number((document.getElementById('input-bridge-days') || {}).value || 2);

    const payload = {
      date_selection_mode: state.dateSelectionMode,
      airline_selection_mode: airlineVal,
      destination_iatas: [destVal],
      direct_holiday_code: holidayVal,
      direct_target_year: yearVal,
      school_year: schoolYearVal,
      overlap_policy: overlapVal,
      specific_departure_date: depVal,
      specific_return_date: retVal,
      flex_days_plus_minus: flexVal,
      min_trip_nights: minNights,
      max_trip_nights: maxNights,
      max_bridge_days_shift: bridgeDays
    };

    const res = await apiSend('POST', '/api/v1/vacations/search', payload);
    state.proposals = res.proposals || [];
    state.selectedProposalIds = new Set(state.proposals.slice(0, 2).map((p) => p.id));
    renderProposals();
  }

  function bindEvents() {
    document.querySelectorAll('.mode-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        setDateMode(btn.getAttribute('data-mode'));
      });
    });

    const btnRunSearch = document.getElementById('btn-run-search');
    if (btnRunSearch) {
      btnRunSearch.addEventListener('click', () => {
        runVacationSearch();
      });
    }

    const btnToggleLocale = document.getElementById('btn-toggle-locale');
    if (btnToggleLocale) {
      btnToggleLocale.addEventListener('click', () => {
        if (state.dir === 'rtl') {
          state.dir = 'ltr';
          state.locale = 'en';
          document.documentElement.setAttribute('dir', 'ltr');
          document.documentElement.setAttribute('lang', 'en');
          btnToggleLocale.textContent = 'עברית / RTL';
        } else {
          state.dir = 'rtl';
          state.locale = 'he';
          document.documentElement.setAttribute('dir', 'rtl');
          document.documentElement.setAttribute('lang', 'he');
          btnToggleLocale.textContent = 'EN / LTR';
        }
        const isHe = state.locale === 'he';
        const headerTitle = document.getElementById('header-title');
        if (headerTitle) {
          headerTitle.textContent = isHe ? 'מתכנן חופשות משפחתיות חכם' : 'Smart Family Vacation Planner';
        }
        const zSearch = document.getElementById('zone-search-title');
        if (zSearch) {
          zSearch.textContent = isHe
            ? '1. בחירת מצב תאריכים, חברת תעופה ויעד'
            : '1. Select Date Mode, Airline & Destination';
        }
        const zProfile = document.getElementById('zone-profile-title');
        if (zProfile) {
          zProfile.textContent = isHe
            ? '2. פרופיל משפחה, גילאי ומסגרות ילדים ונקודות מועדונים'
            : '2. Family Profile, Children Frameworks & Loyalty Wallets';
        }
        const zCalendar = document.getElementById('zone-calendar-title');
        if (zCalendar) {
          zCalendar.textContent = isHe
            ? 'לוח חופשות משרד החינוך וחפיפה רב-גילאית (תצוגה אופציונלית)'
            : 'MoE Multi-Child Vacation Calendar (Optional View)';
        }
        const zResults = document.getElementById('zone-results-title');
        if (zResults) {
          zResults.textContent = isHe
            ? '3. תוצאות חיפוש, דירוג חופשות וניצול כרטיסי בונוס (CTOS / VUS / FBVS)'
            : '3. Search Results, Ranked Vacation Proposals & Bonus Fulfillment (CTOS / VUS / FBVS)';
        }
        setCalendarVisibility(state.isCalendarVisible, false);
        renderProfileControls();
        renderCalendarTable();
        renderProposals();
      });
    }

    const btnSaveProfile = document.getElementById('btn-save-profile');
    if (btnSaveProfile) {
      btnSaveProfile.addEventListener('click', async () => {
        if (!state.profile) return;
        state.profile.adults_count = Number(document.getElementById('prof-adults-count').value || 2);
        state.profile.annual_pto_budget = Number(document.getElementById('prof-pto-budget').value || 18);
        recalculateHouseholdPointsFromWallets();
        state.profile = await apiSend('PUT', '/api/v1/profile', state.profile);
        renderProfileControls();
        await runVacationSearch();
      });
    }

    const btnAddChild = document.getElementById('btn-add-child');
    if (btnAddChild) {
      btnAddChild.addEventListener('click', () => {
        if (!state.profile) return;
        const nextIdx = state.profile.children.length + 1;
        const defaultAge = 7;
        state.profile.children.push({
          id: `child-custom-${Date.now()}`,
          child_name_he: `ילד/ה ${nextIdx}`,
          child_age_years: defaultAge,
          framework_type: state.dateSelectionMode === 'SPECIFIC_DATES' ? null : suggestFrameworkByAge(defaultAge),
          school_week_days: 5,
          holiday_extension_mode: 'NITZANIM_FULL_WITH_JULY',
          treat_camp_as_vacation: true,
          bagrut_blackout_dates: []
        });
        renderProfileControls();
      });
    }

    const btnAddWallet = document.getElementById('btn-add-wallet');
    if (btnAddWallet) {
      btnAddWallet.addEventListener('click', () => {
        if (!state.profile) return;
        const nextIdx = (state.profile.passenger_loyalty_wallets || []).length + 1;
        const adultNum = Math.max(1, ((nextIdx - 1) % Math.max(1, state.profile.adults_count || 2)) + 1);
        state.profile.passenger_loyalty_wallets.push({
          id: `wallet-custom-${Date.now()}`,
          passenger_id: `ADULT_${adultNum}`,
          passenger_name: `הורה ${adultNum}`,
          program_code: 'ELAL_MATMID',
          available_points: 45000,
          can_pool_with_family: true,
          pool_group_id: 'FAMILY_POOL',
          transfer_ratio_to_airline: 1.0,
          has_club_credit_card: true,
          companion_vouchers_count: 0,
          allow_household_pooling: true,
          point_valuation_cents: 1.6
        });
        recalculateHouseholdPointsFromWallets();
        renderProfileControls();
      });
    }

    document.body.addEventListener('input', (ev) => {
      const target = ev.target;
      if (!target || !state.profile) return;
      if (target.hasAttribute('data-wallet-pts')) {
        const idx = Number(target.getAttribute('data-wallet-pts'));
        if (state.profile.passenger_loyalty_wallets[idx]) {
          state.profile.passenger_loyalty_wallets[idx].available_points = Math.max(0, Number(target.value || 0));
          recalculateHouseholdPointsFromWallets();
        }
      } else if (target.hasAttribute('data-wallet-name')) {
        const idx = Number(target.getAttribute('data-wallet-name'));
        if (state.profile.passenger_loyalty_wallets[idx]) {
          state.profile.passenger_loyalty_wallets[idx].passenger_name = target.value;
        }
      }
    });

    document.body.addEventListener('change', (ev) => {
      const target = ev.target;
      if (!target || !state.profile) return;
      if (target.hasAttribute('data-child-age')) {
        const idx = Number(target.getAttribute('data-child-age'));
        const newAge = Number(target.value || 0);
        state.profile.children[idx].child_age_years = newAge;
        if (state.dateSelectionMode !== 'SPECIFIC_DATES') {
          state.profile.children[idx].framework_type = suggestFrameworkByAge(newAge);
        }
        renderProfileControls();
      } else if (target.hasAttribute('data-child-fw')) {
        const idx = Number(target.getAttribute('data-child-fw'));
        const val = target.value;
        state.profile.children[idx].framework_type = val === '' ? null : val;
      } else if (target.hasAttribute('data-wallet-name')) {
        const idx = Number(target.getAttribute('data-wallet-name'));
        if (state.profile.passenger_loyalty_wallets[idx]) {
          state.profile.passenger_loyalty_wallets[idx].passenger_name = target.value;
          renderProfileControls();
        }
      } else if (target.hasAttribute('data-wallet-prog')) {
        const idx = Number(target.getAttribute('data-wallet-prog'));
        state.profile.passenger_loyalty_wallets[idx].program_code = target.value;
        recalculateHouseholdPointsFromWallets();
      } else if (target.hasAttribute('data-wallet-pts')) {
        const idx = Number(target.getAttribute('data-wallet-pts'));
        state.profile.passenger_loyalty_wallets[idx].available_points = Math.max(0, Number(target.value || 0));
        recalculateHouseholdPointsFromWallets();
      } else if (target.hasAttribute('data-compare-id')) {
        const pid = target.getAttribute('data-compare-id');
        if (target.checked) state.selectedProposalIds.add(pid);
        else state.selectedProposalIds.delete(pid);
      }
    });

    document.body.addEventListener('click', (ev) => {
      const target = ev.target;
      if (!target || !state.profile) return;
      const removeChildBtn = target.closest('[data-remove-child]');
      if (removeChildBtn) {
        const idx = Number(removeChildBtn.getAttribute('data-remove-child'));
        state.profile.children.splice(idx, 1);
        renderProfileControls();
        return;
      }
      const removeWalletBtn = target.closest('[data-remove-wallet]');
      if (removeWalletBtn) {
        const idx = Number(removeWalletBtn.getAttribute('data-remove-wallet'));
        state.profile.passenger_loyalty_wallets.splice(idx, 1);
        recalculateHouseholdPointsFromWallets();
        renderProfileControls();
      }
    });

    const btnSyncMoe = document.getElementById('btn-sync-moe-year');
    if (btnSyncMoe) {
      btnSyncMoe.addEventListener('click', async () => {
        const sy = (document.getElementById('select-school-year') || {}).value || '2027-2028';
        await apiSend('POST', `/api/v1/moe-calendar/sync/${sy}`, { force_remote_check: false });
        state.calendarData = await apiGet(`/api/v1/moe-calendar/${sy}`);
        renderCalendarTable();
      });
    }

    const btnSyncElal = document.getElementById('btn-sync-elal');
    if (btnSyncElal) {
      btnSyncElal.addEventListener('click', async () => {
        const destVal = (document.getElementById('select-destination') || {}).value || 'ROM';
        await apiSend('POST', '/api/v1/elal-bonus/sync', {
          destinations: [destVal],
          start_date: '2027-04-10',
          end_date: '2027-04-28',
          origin: 'TLV',
          force_refresh: false
        });
        await runVacationSearch();
      });
    }

    const btnCompare = document.getElementById('btn-compare-selected');
    if (btnCompare) {
      btnCompare.addEventListener('click', async () => {
        const ids = Array.from(state.selectedProposalIds);
        if (ids.length === 0) return;
        const cmp = await apiSend('POST', '/api/v1/vacations/compare', { proposal_ids: ids });
        const banner = document.getElementById('comparison-banner-container');
        if (banner) {
          banner.style.display = 'block';
          banner.innerHTML = `
            <div class="proposal-card" style="border-inline-start-color: #10b981; background: #ecfdf5;">
              <strong>⚖️ תוצאת השוואת חלופות:</strong>
              <p style="margin: 4px 0 0 0; font-size: 0.88rem;">${cmp.summary_he || ''}</p>
            </div>
          `;
        }
      });
    }

    const btnToggleCalInline = document.getElementById('btn-toggle-calendar-inline');
    if (btnToggleCalInline) {
      btnToggleCalInline.addEventListener('click', () => {
        setCalendarVisibility(!state.isCalendarVisible, !state.isCalendarVisible);
      });
    }

    const btnCloseCal = document.getElementById('btn-close-calendar');
    if (btnCloseCal) {
      btnCloseCal.addEventListener('click', () => {
        setCalendarVisibility(false, false);
      });
    }

    document.querySelectorAll('.desktop-nav-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const zoneId = btn.getAttribute('data-desktop-zone');
        if (zoneId === 'zone-calendar') {
          setCalendarVisibility(!state.isCalendarVisible, !state.isCalendarVisible);
          btn.classList.toggle('active', state.isCalendarVisible);
          return;
        }
        document.querySelectorAll('.desktop-nav-btn').forEach((b) => {
          if (b.getAttribute('data-desktop-zone') !== 'zone-calendar') {
            b.classList.remove('active');
          }
        });
        btn.classList.add('active');
        const el = document.getElementById(zoneId);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      });
    });

    document.querySelectorAll('.mobile-nav-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.mobile-nav-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        const zoneId = btn.getAttribute('data-mobile-zone');
        const el = document.getElementById(zoneId);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    loadInitialData();
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  });
})();

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
 * - Interactive Destination Postcard Strip synced with destination selector & live search
 * - Boarding-Pass styled vacation proposal cards with visual flight route telemetry
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
    { value: 'ELAL_MATMID', labelHe: 'אל על הנוסע המתמיד (El Al Matmid)', labelEn: 'El Al Matmid Frequent Flyer' },
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

  const DESTINATION_ICONS = {
    ROM: '🏛️',
    FCO: '🏛️',
    MXP: '🏔️',
    VCE: '🛶',
    ATH: '🏖️',
    RHO: '🏝️',
    HER: '🏝️',
    SKG: '🌊',
    CFU: '🏝️',
    EFL: '🏖️',
    JTR: '🌅',
    LCA: '☀️',
    PFO: '🏖️',
    TBS: '🏔️',
    BUS: '🌊',
    TIV: '⛵',
    BEG: '🏰',
    OTP: '🏰',
    SOF: '⛰️',
    PAR: '🥐',
    CDG: '🥐',
    NCE: '🏖️',
    LON: '🎡',
    LHR: '🎡',
    LTN: '🎡',
    MAD: '💃',
    BCN: '🌊',
    GVA: '⛷️',
    ZRH: '🏔️',
    MUC: '🏰',
    FRA: '🎢',
    VIE: '🎻',
    PRG: '🏰',
    BUD: '♨️',
    WAW: '🏰',
    KRK: '🎢',
    AMS: '🌷',
    BER: '🐻',
    LIS: '🚋',
    DXB: '☀️',
    NYC: '🗽',
    JFK: '🗽',
    EWR: '🗽',
    BOS: '🍂',
    MIA: '🌴',
    FLL: '🌴',
    LAX: '🎬',
    BKK: '🌴',
    HKT: '🏝️',
    TYO: '⛩️',
    NRT: '⛩️'
  };

  const VACATION_TYPE_LABELS_HE = {
    ANY: '🌍 הכל (ללא סינון)',
    BEACH_AND_POOL: '🏖️ בטן-גב (חוף ובריכה)',
    NATURE_TRIP: '🥾 טיול בטבע ונופים',
    URBAN_CULTURE: '🏛️ עיר, תרבות ושופינג',
    FAMILY_ATTRACTIONS_PARKS: '🎢 פארקים ואטרקציות',
    SNOW_AND_SKI: '⛷️ חופשת שלג וסקי',
    WINTER_FESTIVE: '🎄 שווקי חורף'
  };

  const VACATION_TYPE_LABELS_EN = {
    ANY: '🌍 All Styles',
    BEACH_AND_POOL: '🏖️ Beach & Pool',
    NATURE_TRIP: '🥾 Nature & Hiking',
    URBAN_CULTURE: '🏛️ Urban & Culture',
    FAMILY_ATTRACTIONS_PARKS: '🎢 Theme Parks',
    SNOW_AND_SKI: '⛷️ Snow & Ski',
    WINTER_FESTIVE: '🎄 Winter Markets'
  };

  const INITIAL_PROPOSALS_LIMIT = 6;
  const userEditedWalletKeys = new Set();

  function escapeHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  const state = {
    locale: 'he',
    dir: 'rtl',
    dateSelectionMode: 'HOLIDAY_DIRECT_INTENT',
    airlineSelectionMode: 'EL_AL_ONLY',
    selectedVacationTypes: [],
    weatherFilterMode: 'SOFT_PRIORITIZE',
    weatherFallbackMessageHe: null,
    validationErrorHe: null,
    validationErrorEn: null,
    isCalendarVisible: false,
    showAllProposals: false,
    lastComparison: null,
    profile: null,
    calendarData: null,
    proposals: [],
    selectedProposalIds: new Set()
  };

  function syncVacationTypePills() {
    const activeSet = new Set(state.selectedVacationTypes || []);
    const isAny = activeSet.size === 0 || activeSet.has('ANY');
    document.querySelectorAll('[data-vacation-type]').forEach((btn) => {
      const vt = btn.getAttribute('data-vacation-type');
      if (vt === 'ANY') {
        btn.classList.toggle('active', isAny);
      } else {
        btn.classList.toggle('active', !isAny && activeSet.has(vt));
      }
    });
  }

  function formatVacationTypeBadge(vtype) {
    const code = String(vtype || 'ANY').toUpperCase();
    return state.locale === 'he'
      ? (VACATION_TYPE_LABELS_HE[code] || code)
      : (VACATION_TYPE_LABELS_EN[code] || code);
  }

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
          ? '📅 הסתר לוח'
          : '📅 Hide Calendar'
        : isHe
          ? '📅 לוח חופשות'
          : '📅 MoE Calendar';
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

  function formatGenericChildTitle(idx) {
    return state.locale === 'he' ? `ילד/ה #${idx + 1}` : `Child #${idx + 1}`;
  }

  function formatGenericPassengerLabel(alloc, fallbackIdx) {
    const pid = String(alloc.passenger_id || '').toUpperCase();
    const rawLabel = String(alloc.passenger_label || '');
    const isHe = state.locale === 'he';

    if (pid.startsWith('ADULT_')) {
      const num = pid.split('_')[1] || (fallbackIdx + 1);
      return isHe ? `מבוגר/הורה ${num}` : `Adult ${num}`;
    }
    if (pid.startsWith('CHILD_')) {
      const num = pid.split('_')[1] || (fallbackIdx + 1);
      const ageMatch = rawLabel.match(/\d+/);
      const ageNum = ageMatch ? Number(ageMatch[0]) : null;
      const childIdx = Number(num) - 1;
      const profChild = state.profile && state.profile.children && state.profile.children[childIdx];
      const resolvedAge = profChild ? profChild.child_age_years : ageNum;
      if (resolvedAge !== null && resolvedAge !== undefined) {
        return isHe ? `ילד/ה #${num} (גיל ${resolvedAge})` : `Child #${num} (Age ${resolvedAge})`;
      }
      return isHe ? `ילד/ה #${num}` : `Child #${num}`;
    }
    return isHe ? `נוסע #${fallbackIdx + 1}` : `Passenger #${fallbackIdx + 1}`;
  }

  function formatStrategyLabel(strategyCode) {
    const code = String(strategyCode || '');
    const isHe = state.locale === 'he';
    const labelsHe = {
      FULL_BONUS_SAME_CABIN: 'בונוס מלא באותה מחלקה',
      SPLIT_CABIN_BONUS: 'בונוס מפוצל בין מחלקות (אותה טיסה)',
      HYBRID_BONUS_PLUS_CASH: 'שילוב כרטיסי בונוס + השלמת מזומן',
      ONE_WAY_BONUS_ONE_WAY_CASH: 'כיוון בונוס + כיוון מזומן / יעד משולב',
      CASH_AND_POINTS: 'מזומן + נקודות (Cash & Points)',
      MULTI_CLUB_PER_PASSENGER_SPLIT: 'פיצול נקודות בין מועדונים ונוסעים',
      COMMERCIAL_CASH_ONLY: 'כרטיסים מסחריים במזומן'
    };
    const labelsEn = {
      FULL_BONUS_SAME_CABIN: 'Full Bonus (Same Cabin)',
      SPLIT_CABIN_BONUS: 'Split-Cabin Bonus (Same Flight)',
      HYBRID_BONUS_PLUS_CASH: 'Hybrid Bonus + Cash',
      ONE_WAY_BONUS_ONE_WAY_CASH: 'One-Way Bonus + Cash / Open-Jaw',
      CASH_AND_POINTS: 'Cash & Points',
      MULTI_CLUB_PER_PASSENGER_SPLIT: 'Multi-Club Per-Passenger Split',
      COMMERCIAL_CASH_ONLY: 'Commercial Cash Only'
    };
    return (isHe ? labelsHe[code] : labelsEn[code]) || code;
  }

  function formatRecommendationTierLabel(tierCode) {
    const code = String(tierCode || '');
    const isHe = state.locale === 'he';
    if (code === 'RECOMMENDED') return isHe ? '🌟 החופשה המומלצת ביותר' : '🌟 Best Overall Vacation';
    if (code === 'TOP_CHOICE') return isHe ? '✨ בחירה מובילה' : '✨ Top Choice';
    return isHe ? '🏖️ חלופה מומלצת' : '🏖️ Alternative Option';
  }

  function buildIntuitiveProposalSummary(p) {
    const it = p.itinerary || {};
    const isHe = state.locale === 'he';
    const city = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);
    const stratLabel = formatStrategyLabel(it.fulfillment_strategy);
    const pts = Number(it.total_matmid_points || 0).toLocaleString();
    const cashOop = Number(it.total_out_of_pocket_cash_usd || 0).toFixed(0);
    const savedNum = Math.round(Number(it.net_cash_saved_usd || 0));
    const savedDisplay =
      savedNum > 0 ? `+$${savedNum}` : savedNum < 0 ? `-$${Math.abs(savedNum)}` : '$0';
    const totalScore = Number(p.combined_trip_optimization_score || 0).toFixed(1);
    const vacScore = Number(p.vacation_utilization_score || 0).toFixed(1);
    const bonusScore = Number(p.flight_bonus_value_score ?? p.family_bonus_value_score ?? 0).toFixed(1);
    const weatherScore = Number(p.weather_suitability_score || 0).toFixed(1);

    if (!isHe) {
      return `${city} (${it.destination_iata}) | ${it.departure_date} to ${it.return_date} (${it.trip_nights} nights) | Strategy: ${stratLabel} | Points: ${pts} | Out-of-Pocket Cash: $${cashOop} (Net Saved: ${savedDisplay}) | Overall Score: ${totalScore}/100 (Weather: ${weatherScore}, Vacation Match: ${vacScore}, Bonus Value: ${bonusScore})`;
    }
    return `${city} (${it.destination_iata}) | ${it.departure_date} עד ${it.return_date} (${it.trip_nights} לילות / ${p.total_vacation_days || (it.trip_nights + 1)} ימים) | אסטרטגיה: ${stratLabel} | נקודות: ${pts} | תשלום במזומן: $${cashOop} (חיסכון נטו: ${savedDisplay}) | ציון משוקלל: ${totalScore}/100 (מזג אוויר: ${weatherScore}, ניצול חופשה: ${vacScore}, כדאיות טיסה ובונוס: ${bonusScore})`;
  }

  function classifyFareByAge(ageYears) {
    const age = Number(ageYears) || 0;
    if (age < 2) return state.locale === 'he' ? 'תינוק (גיל <2)' : 'Infant (<2)';
    if (age < 12) return state.locale === 'he' ? 'ילד/ה (גילאי 2–11)' : 'Child (2–11)';
    return state.locale === 'he' ? 'נוער (גילאי 12–18)' : 'Youth (12–18)';
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
      const err = new Error(`${method} ${path} failed (${resp.status}): ${errText}`);
      err.status = resp.status;
      err.bodyText = errText;
      throw err;
    }
    return resp.json();
  }

  function extractApiErrorDetail(err) {
    if (!err) return '';
    if (err.bodyText) {
      try {
        const parsed = JSON.parse(err.bodyText);
        const msg = parsed && (typeof parsed.detail === 'string' ? parsed.detail : typeof parsed.error === 'string' ? parsed.error : '');
        if (msg) {
          return msg.trim();
        }
      } catch (_ignore) {
        // Non-JSON error body
      }
    }
    return '';
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
      const fmtCompact = (n) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));
      ptsPill.setAttribute('dir', 'ltr');
      ptsPill.setAttribute(
        'title',
        `${matmidTotal.toLocaleString()} El Al Matmid / ${allClubsTotal.toLocaleString()} Total Points`
      );
      if (allClubsTotal > matmidTotal) {
        ptsPill.textContent = `${fmtCompact(matmidTotal)} LY · ${fmtCompact(allClubsTotal)} pts`;
      } else {
        ptsPill.textContent = `${fmtCompact(matmidTotal)} Matmid`;
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
            `<span class="score-pill" dir="ltr">${escapeHtml(progShortLabels[prog] || prog)}: <strong>${Number(total).toLocaleString()}</strong></span>`
        )
        .join('');
      const totalTitle = isHe ? 'סה״כ נקודות:' : 'Total Points:';
      stripEl.innerHTML = `
        <span class="score-pill" style="background: var(--azure-tint); border-color: var(--azure-border); color: var(--azure-elal);">
          ${totalTitle} <strong dir="ltr">${allClubsTotal.toLocaleString()}</strong>
        </span>
        ${breakdownPills}
      `;
    }

    return { matmidTotal, allClubsTotal, byProgram };
  }

  function getWalletKey(w, idx) {
    return (w && w.id) ? String(w.id) : `idx-${idx}`;
  }

  const DEFAULT_HE_WALLET_NAMES = new Set([
    'יוני (הורה 1)',
    'בת זוג (הורה 2)',
    'נוסע'
  ]);

  function isDefaultHebrewWalletPlaceholder(raw) {
    if (!raw) return false;
    if (DEFAULT_HE_WALLET_NAMES.has(raw)) return true;
    return /^(הורה|נוסע|ילד\/ה)\s*#?\d+$/.test(raw);
  }

  function formatWalletDisplayName(rawName, passengerId, idx, walletKey) {
    const isHe = state.locale === 'he';
    const raw = String(rawName || '').trim();
    const pid = String(passengerId || '').toUpperCase();
    const wasEditedByUser = walletKey && userEditedWalletKeys.has(walletKey);
    if (!wasEditedByUser && !isHe && isDefaultHebrewWalletPlaceholder(raw)) {
      if (pid.startsWith('ADULT_')) {
        return `Parent ${pid.split('_')[1] || (idx + 1)}`;
      }
      if (pid.startsWith('CHILD_')) {
        return `Child ${pid.split('_')[1] || (idx + 1)}`;
      }
      const numMatch = raw.match(/(\d+)/);
      return numMatch ? `Parent ${numMatch[1]}` : `Passenger #${idx + 1}`;
    }
    if (raw) return raw;
    if (pid.startsWith('ADULT_')) {
      const n = pid.split('_')[1] || (idx + 1);
      return isHe ? `הורה ${n}` : `Parent ${n}`;
    }
    return isHe ? `נוסע #${idx + 1}` : `Passenger #${idx + 1}`;
  }

  function renderProfileControls() {
    if (!state.profile) return;
    const isHe = state.locale === 'he';
    recalculateHouseholdPointsFromWallets();
    const adultsInput = document.getElementById('prof-adults-count');
    const ptoInput = document.getElementById('prof-pto-budget');
    const matmidInput = document.getElementById('prof-matmid-points');
    if (adultsInput) adultsInput.value = state.profile.adults_count;
    if (ptoInput) ptoInput.value = state.profile.annual_pto_budget;
    if (matmidInput) matmidInput.value = state.profile.matmid_points_balance;

    const famPill = document.getElementById('header-family-pill');
    if (famPill) {
      // Words render in the body face; only the numerals keep the telemetry face (`.num`)
      const adultsNum = `<span class="num">${escapeHtml(state.profile.adults_count)}</span>`;
      const childrenNum = `<span class="num">${escapeHtml(state.profile.children.length)}</span>`;
      famPill.setAttribute('dir', 'auto');
      famPill.innerHTML = isHe
        ? `${adultsNum} מבוגרים + ${childrenNum} ילדים`
        : `${adultsNum} Adults + ${childrenNum} Children`;
    }

    const childrenContainer = document.getElementById('children-list-container');
    if (childrenContainer) {
      const isOptionalMode = state.dateSelectionMode === 'SPECIFIC_DATES';
      childrenContainer.innerHTML = state.profile.children
        .map((child, idx) => {
          const fwOptions = MOE_FRAMEWORKS.map((fw) => {
            const currentFw = child.framework_type === null ? '' : String(child.framework_type || '');
            const selected = currentFw === fw.value ? 'selected' : '';
            const label = isHe ? fw.labelHe : fw.labelEn;
            return `<option value="${escapeHtml(fw.value)}" ${selected}>${escapeHtml(label)}</option>`;
          }).join('');
          return `
            <div class="compact-profile-item">
              <div class="compact-item-top">
                <span class="compact-item-title">🧒 ${escapeHtml(formatGenericChildTitle(idx))} · <span class="compact-item-sub compact-item-sub-text">${escapeHtml(classifyFareByAge(child.child_age_years))}</span></span>
                <button type="button" class="btn-secondary btn-remove-inline" data-remove-child="${idx}">${isHe ? 'הסר' : 'Remove'}</button>
              </div>
              <div class="form-grid form-grid-2">
                <div class="form-field">
                  <label>${isHe ? 'גיל (0–18):' : 'Age (0–18):'}</label>
                  <input type="number" min="0" max="18" value="${escapeHtml(child.child_age_years)}" data-child-age="${idx}" dir="ltr" />
                </div>
                <div class="form-field">
                  <label>${isHe ? 'מסגרת (' + (isOptionalMode ? 'אופציונלי / Optional' : 'משרד החינוך') + '):' : 'Framework (' + (isOptionalMode ? 'Optional' : 'MoE Calendar') + '):'}</label>
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
            const progLabel = isHe ? (p.labelHe || p.label) : (p.labelEn || p.label);
            return `<option value="${escapeHtml(p.value)}" ${sel}>${escapeHtml(progLabel)}</option>`;
          }).join('');
          const wKey = getWalletKey(w, idx);
          const dispName = formatWalletDisplayName(w.passenger_name, w.passenger_id, idx, wKey);
          const safeDispName = escapeHtml(dispName);
          const safePassengerId = escapeHtml(w.passenger_id);
          return `
            <div class="compact-profile-item wallet-item">
              <div class="compact-item-top">
                <span class="compact-item-title">💳 ${safeDispName} <span class="compact-item-sub" dir="ltr">(${safePassengerId})</span></span>
                <button type="button" class="btn-secondary btn-remove-inline" data-remove-wallet="${idx}">
                  ${isHe ? 'הסר מועדון' : 'Remove'}
                </button>
              </div>
              <div class="form-grid form-grid-3 wallet-fields">
                <div class="form-field">
                  <label>${isHe ? 'נוסע:' : 'Passenger:'}</label>
                  <input type="text" value="${safeDispName}" data-wallet-name="${idx}" />
                </div>
                <div class="form-field">
                  <label>${isHe ? 'נקודות:' : 'Points:'}</label>
                  <input type="number" min="0" step="1000" value="${escapeHtml(w.available_points)}" data-wallet-pts="${idx}" dir="ltr" />
                </div>
                <div class="form-field wallet-club-field">
                  <label>${isHe ? 'מועדון תעופה:' : 'Loyalty Club:'}</label>
                  <select data-wallet-prog="${idx}">${progOptions}</select>
                </div>
              </div>
            </div>
          `;
        })
        .join('');
    }
  }

  const FRAMEWORK_SHORT_LABELS_HE = {
    DAYCARE_SUPERVISED: 'מעונות יום (0–3)',
    MUNICIPAL_GAN: 'גני ילדים',
    ELEMENTARY_1_3: 'יסודי (א׳–ג׳)',
    ELEMENTARY_4_6: 'יסודי (ד׳–ו׳)',
    MIDDLE_SCHOOL_7_9: 'חטיבת ביניים (ז׳–ט׳)',
    HIGH_SCHOOL_10_12: 'תיכון (י׳–י״ב)',
    SPECIAL_ED: 'חינוך מיוחד',
    RELIGIOUS_HAREDI: 'ממ״ד / חרדי'
  };

  const FRAMEWORK_SHORT_LABELS_EN = {
    DAYCARE_SUPERVISED: 'Daycare (0–3)',
    MUNICIPAL_GAN: 'Kindergarten',
    ELEMENTARY_1_3: 'Elementary (1–3)',
    ELEMENTARY_4_6: 'Elementary (4–6)',
    MIDDLE_SCHOOL_7_9: 'Middle School (7–9)',
    HIGH_SCHOOL_10_12: 'High School (10–12)',
    SPECIAL_ED: 'Special Ed',
    RELIGIOUS_HAREDI: 'Religious / Haredi'
  };

  function formatGroupedFrameworksLabel(frameworkCodes) {
    const isHe = state.locale === 'he';
    const labelsMap = isHe ? FRAMEWORK_SHORT_LABELS_HE : FRAMEWORK_SHORT_LABELS_EN;
    const uniqueCodes = Array.from(new Set(frameworkCodes));
    if (uniqueCodes.length >= 8) {
      return isHe ? 'כל מסגרות החינוך' : 'All Educational Frameworks';
    }
    return uniqueCodes.map((code) => labelsMap[code] || code).join(' · ');
  }

  function renderCalendarTable() {
    const tbody = document.getElementById('moe-calendar-tbody');
    const syncBadge = document.getElementById('calendar-sync-badge');
    if (!tbody || !state.calendarData) return;

    const isHe = state.locale === 'he';
    if (syncBadge) {
      const syncSourceLabel = state.calendarData.calendar_sync_source === 'OFFICIAL_MOE_CIRCULAR'
        ? (isHe ? 'חוזר מנכ״ל משרד החינוך' : 'Official MoE Circular')
        : state.calendarData.calendar_sync_source;
      // School year stays in the telemetry face; the worded source label renders in the body face
      syncBadge.innerHTML = `<span class="num" dir="ltr">${escapeHtml(state.calendarData.school_year)}</span> | ${escapeHtml(syncSourceLabel)}`;
    }

    const windows = state.calendarData.windows || [];
    const groupedMap = new Map();

    windows.forEach((w) => {
      const resumeDate = w.resumes_on_date || w.school_resume_date || w.resume_date || w.end_date || '';
      const nitzFlag = Boolean(w.is_covered_by_nitzanim);
      const nitzStart = w.nitzanim_start_date || '';
      const nitzEnd = w.nitzanim_end_date || '';
      const groupKey = `${w.holiday_code}::${w.start_date}::${w.end_date}::${resumeDate}::${nitzFlag}::${nitzStart}::${nitzEnd}`;

      if (!groupedMap.has(groupKey)) {
        groupedMap.set(groupKey, {
          holiday_name_he: w.holiday_name_he,
          holiday_name_en: w.holiday_name_en || w.holiday_name_he,
          start_date: w.start_date,
          end_date: w.end_date,
          resume_date: resumeDate,
          total_calendar_days: w.total_calendar_days || w.calendar_days_count,
          is_covered_by_nitzanim: nitzFlag,
          nitzanim_start_date: nitzStart,
          nitzanim_end_date: nitzEnd,
          frameworks: []
        });
      }
      const group = groupedMap.get(groupKey);
      if (!group.frameworks.includes(w.framework_type)) {
        group.frameworks.push(w.framework_type);
      }
    });

    const groupedRows = Array.from(groupedMap.values());

    tbody.innerHTML = groupedRows
      .map((g) => {
        // Same wording as before; each date is an unbreakable token so the badge wraps between words, never inside a date
        const nitzBadge = g.is_covered_by_nitzanim
          ? `<span class="badge-camp">${isHe ? 'קייטנת ניצנים' : 'Nitzanim'} (<span class="cal-nowrap">${escapeHtml(g.nitzanim_start_date)}</span> ${isHe ? 'עד' : 'to'} <span class="cal-nowrap">${escapeHtml(g.nitzanim_end_date)}</span>)</span>`
          : `<span class="badge-vacation">${isHe ? 'חופשה מלאה' : 'Full Vacation'}</span>`;
        const daysCount =
          g.total_calendar_days ||
          Math.max(1, Math.round((new Date(g.end_date) - new Date(g.start_date)) / 86400000) + 1);
        const fwLabel = formatGroupedFrameworksLabel(g.frameworks);
        const holidayTitle = isHe ? g.holiday_name_he : g.holiday_name_en;
        return `
          <tr>
            <td class="sticky-col">${escapeHtml(holidayTitle)}</td>
            <td><span style="font-weight: 600; color: var(--text-primary); white-space: normal;">${escapeHtml(fwLabel)}</span></td>
            <td dir="ltr">${escapeHtml(g.start_date)}</td>
            <td dir="ltr">${escapeHtml(g.end_date)}</td>
            <td dir="ltr">${escapeHtml(g.resume_date)}</td>
            <td dir="ltr">${escapeHtml(daysCount)}</td>
            <td>${nitzBadge}</td>
          </tr>
        `;
      })
      .join('');
  }

  function resolveElAlBookingUrl(it) {
    if (!it || !it.is_elal_flight) return null;
    const serverGfUrl = String(it.elal_google_flights_url || '').trim();
    if (serverGfUrl.startsWith('https://www.google.com/travel/flights')) {
      return serverGfUrl;
    }

    // Client-side fallback builder for cached El Al itineraries
    const orig = String(it.origin_iata || 'TLV').toUpperCase();
    const dest = String(it.destination_iata || 'FCO').toUpperCase();
    const retOrig = String(it.return_origin_iata || dest).toUpperCase();
    const depIso = String(it.departure_date || '2027-04-11');
    const retIso = String(it.return_date || '2027-04-18');

    const prof = state.profile || {};
    let adt = Math.max(1, Number(prof.adults_count || 2));
    let chd = 0;
    let inf = 0;
    (prof.children || []).forEach((c) => {
      const age = Number(c.child_age_years ?? 6);
      const pType = String(c.passenger_Current_type || '').toUpperCase();
      if (pType === 'INFANT_LAP' || (!pType && age < 2)) {
        inf += 1;
      } else if (age < 12 || pType === 'CHILD' || pType === 'INFANT_SEAT') {
        chd += 1;
      } else {
        adt += 1;
      }
    });
    inf = Math.min(inf, adt);

    const paxParts = [adt === 1 ? '1 adult' : `${adt} adults`];
    if (chd > 0) paxParts.push(chd === 1 ? '1 child' : `${chd} children`);
    if (inf > 0) paxParts.push(inf === 1 ? '1 infant' : `${inf} infants`);
    const paxPhrase =
      paxParts.length === 1
        ? paxParts[0]
        : paxParts.length === 2
          ? `${paxParts[0]} and ${paxParts[1]}`
          : `${paxParts[0]}, ${paxParts[1]} and ${paxParts[2]}`;

    const qStr =
      retOrig === dest
        ? `Flights to ${dest} from ${orig} on ${depIso} through ${retIso} with ${paxPhrase} nonstop on EL AL`
        : `Flights from ${orig} to ${dest} on ${depIso} and from ${retOrig} to ${orig} on ${retIso} with ${paxPhrase} nonstop on EL AL`;

    const params = new URLSearchParams();
    params.set('q', qStr);
    params.set('curr', 'USD');
    params.set('gl', 'IL');
    params.set('hl', 'en');
    return `https://www.google.com/travel/flights?${params.toString()}`;
  }

  function formatLegFlightBadge(leg) {
    if (!leg || !leg.flight_number) return '';
    const fn = String(leg.flight_number).trim();
    const depT = leg.departure_time_local ? String(leg.departure_time_local).slice(0, 5) : '';
    const arrT = leg.arrival_time_local ? String(leg.arrival_time_local).slice(0, 5) : '';
    const times = depT && arrT ? ` · ${depT}–${arrT}` : depT ? ` · ${depT}` : '';
    return `<span class="route-flight-meta">${escapeHtml(fn + times)}</span>`;
  }

  function updateZoneResultsTitle() {
    const zResults = document.getElementById('zone-results-title');
    if (!zResults) return;
    const isHe = state.locale === 'he';
    const count = (state.proposals && state.proposals.length) || 0;
    const countSuffix = count > 0 ? ` (${count})` : '';
    zResults.textContent = isHe
      ? `3. תוצאות חיפוש, דירוג חופשות וניצול כרטיסי בונוס${countSuffix}`
      : `3. Ranked Vacation Proposals & Award Fulfillment${countSuffix}`;
  }

  function renderComparisonBanner() {
    const banner = document.getElementById('comparison-banner-container');
    if (!banner) return;
    const cmp = state.lastComparison;
    if (!cmp) {
      banner.style.display = 'none';
      banner.innerHTML = '';
      return;
    }
    const isHe = state.locale === 'he';
    const props = cmp.proposals || [];
    const byId = new Map(props.map((p) => [p.id, p]));
    const fmtWinner = (pid) => {
      const p = byId.get(pid);
      if (!p || !p.itinerary) return null;
      const it = p.itinerary;
      const city = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);
      const strat = formatStrategyLabel(it.fulfillment_strategy);
      return `${city} (${it.departure_date} → ${it.return_date} · ${strat})`;
    };

    const bestOverall = fmtWinner(cmp.best_by_ctos_id);
    const bestSavings = fmtWinner(cmp.best_by_cash_savings_id);
    const bestPer = fmtWinner(cmp.best_by_per_id);
    const bestWeather = fmtWinner(cmp.best_by_weather_id);

    let summaryLine = isHe ? (cmp.summary_he || '') : (cmp.summary_en || '');
    if (!summaryLine) {
      const parts = [];
      if (bestOverall) parts.push(isHe ? `ציון משוקלל מוביל: ${bestOverall}` : `Best Overall Score: ${bestOverall}`);
      if (bestSavings) parts.push(isHe ? `חיסכון כספי מרבי: ${bestSavings}` : `Highest Net Savings: ${bestSavings}`);
      if (bestPer) parts.push(isHe ? `מכפיל ימי חופש מרבי: ${bestPer}` : `Best PTO Multiplier: ${bestPer}`);
      if (bestWeather) parts.push(isHe ? `מזג אוויר מיטבי: ${bestWeather}` : `Best Weather Match: ${bestWeather}`);
      summaryLine = parts.join(' · ');
    }

    banner.style.display = 'block';
    banner.innerHTML = `
      <div class="comparison-banner-card">
        <strong class="comparison-banner-title">⚖️ ${isHe ? `תוצאת השוואת ${props.length} חלופות נבחרות:` : `Comparison Summary (${props.length} selected proposals):`}</strong>
        <p class="comparison-banner-text">${escapeHtml(summaryLine)}</p>
      </div>
    `;
  }

  function renderProposals() {
    const container = document.getElementById('proposals-container');
    if (!container) return;
    const isHe = state.locale === 'he';
    updateZoneResultsTitle();

    if (state.validationErrorHe || state.validationErrorEn) {
      const valMsg = isHe
        ? (state.validationErrorHe || 'נא לבדוק את ערכי הקלט בטופס ולנסות שוב.')
        : (state.validationErrorEn || 'Check your search or profile inputs and try again.');
      container.innerHTML = `
        <div class="status-banner-card">
          <strong class="status-banner-title">
            ⚠️ ${isHe ? 'ערכי קלט לא תקינים' : 'Invalid Search or Profile Inputs'}
          </strong>
          <p class="status-banner-body">
            ${escapeHtml(valMsg)}
          </p>
        </div>
      `;
      return;
    }

    if (!state.proposals || state.proposals.length === 0) {
      const NO_SYNCED_FLIGHTS_TOKEN_HE = 'אין משיכה של טיסות מהשרת';
      const rawHe = String(state.statusMessageHe || '');
      const isStandardUnsynced = !rawHe || rawHe.includes(NO_SYNCED_FLIGHTS_TOKEN_HE);
      const selectDestEl = document.getElementById('select-destination');
      const selectedDestOpt = selectDestEl && selectDestEl.selectedOptions && selectDestEl.selectedOptions[0];
      const destCode = selectDestEl ? String(selectDestEl.value || '').trim() : '';
      const destLabel =
        selectedDestOpt && destCode && destCode !== 'ANYWHERE'
          ? String(selectedDestOpt.textContent || '').trim()
          : '';

      const badgeText = isHe ? '✈️ מחכה למשיכת טיסות' : '✈️ Awaiting Flight Sync';
      const headlineText = isHe ? 'מחכה למשיכת טיסות' : 'Awaiting Flight Sync';
      const subText = isStandardUnsynced
        ? isHe
          ? 'טרם נמשכו טיסות בונוס זמינות עבור היעד והחופשה שנבחרו. אפשר לבחור יעד או מועד אחר בטופס, או להריץ סנכרון טיסות מול אל על.'
          : 'No synced award flights are currently loaded for the selected destination and holiday window. Pick another destination or holiday, or sync El Al availability.'
        : isHe
          ? rawHe
          : String(state.statusMessageEn || 'No matching flights found for the current search filters.');

      container.innerHTML = `
        <div class="awaiting-flights-showcase" role="status" aria-live="polite">
          <div class="awaiting-flights-scrim">
            <div class="awaiting-flights-badges">
              <span class="awaiting-flights-pill">${escapeHtml(badgeText)}</span>
              ${destLabel ? `<span class="awaiting-flights-dest-pill">📍 ${escapeHtml(destLabel)}</span>` : ''}
            </div>
            <h3 class="awaiting-flights-headline">${escapeHtml(headlineText)}</h3>
            <p class="awaiting-flights-sub">${escapeHtml(subText)}</p>
          </div>
        </div>
      `;
      return;
    }

    const fallbackBannerHtml = state.weatherFallbackMessageHe
      ? `
        <div class="weather-fallback-card">
          🌤️ ${escapeHtml(isHe ? state.weatherFallbackMessageHe : 'Strict weather filter was relaxed to display the highest-rated weather options for these dates.')}
        </div>
      `
      : '';

    const totalCount = state.proposals.length;
    const visibleList = state.showAllProposals
      ? state.proposals
      : state.proposals.slice(0, INITIAL_PROPOSALS_LIMIT);

    const cardsHtml = visibleList
      .map((p, idx) => {
        const it = p.itinerary || {};
        const wm = p.weather_metrics || null;
        const wssVal = Number(
          p.weather_suitability_score ??
            (wm && wm.overall_weather_suitability_score) ??
            0
        );

        let topStyleChipHtml = '';
        let weatherStripHtml = '';
        if (wm) {
          const scoresByType = wm.scores_by_vacation_type || {};
          const recList = wm.recommended_vacation_types || [];
          if (recList.length > 0) {
            topStyleChipHtml = `<span class="weather-badge-tag">${formatVacationTypeBadge(recList[0])}</span>`;
          }
          const recTypes = recList
            .slice(0, 3)
            .map((vt) => `<span class="weather-badge-tag">${formatVacationTypeBadge(vt)}</span>`)
            .join('');
          const seaTempChip =
            wm.sea_water_temp_c !== null && wm.sea_water_temp_c !== undefined
              ? `<span class="weather-metric-chip">🌊 ${isHe ? 'ים:' : 'Sea:'} <strong dir="ltr">${Number(wm.sea_water_temp_c).toFixed(0)}°C</strong></span>`
              : '';
          const extraSelectedChips = (state.selectedVacationTypes || [])
            .filter((vt) => vt !== 'ANY')
            .slice(0, 2)
            .map(
              (vt) =>
                `<span class="weather-metric-chip">${formatVacationTypeBadge(vt)}: <strong dir="ltr">${Number(scoresByType[vt] ?? 0).toFixed(0)}</strong></span>`
            )
            .join('');
          const summaryNoteText = isHe
            ? (wm.weather_summary_he || '')
            : (wm.weather_summary_en ||
              `Expected ${Number(wm.avg_day_high_c || 0).toFixed(0)}°C day / ${Number(wm.avg_night_low_c || 0).toFixed(0)}°C night` +
                (wm.sea_water_temp_c !== null && wm.sea_water_temp_c !== undefined ? `, sea ${Number(wm.sea_water_temp_c).toFixed(0)}°C` : '') +
                `, ~${Number(wm.sunshine_hours_per_day || 0).toFixed(1)}h daily sunshine & ~${Number(wm.estimated_rain_days_in_trip || 0).toFixed(1)} rain days.`);
          weatherStripHtml = `
            <div class="weather-telemetry-strip">
              <div class="weather-telemetry-row">
                <span class="weather-metric-chip">🌤️ ${isHe ? 'ציון אקלים:' : 'Climate:'} <strong dir="ltr">${wssVal.toFixed(0)}/100</strong></span>
                <span class="weather-metric-chip">🌡️ <strong dir="ltr">${Number(wm.avg_day_high_c || 0).toFixed(0)}°/${Number(wm.avg_night_low_c || 0).toFixed(0)}°C</strong></span>
                ${seaTempChip}
                <span class="weather-metric-chip">☀️ <strong dir="ltr">${Number(wm.sunshine_hours_per_day || 0).toFixed(1)}h</strong></span>
                <span class="weather-metric-chip">🌧️ <strong dir="ltr">${Number(wm.estimated_rain_days_in_trip || 0).toFixed(1)}${isHe ? ' ימי גשם' : 'd rain'}</strong></span>
                ${extraSelectedChips}
              </div>
              <div class="weather-telemetry-footer">
                <span class="weather-summary-note">${escapeHtml(summaryNoteText)}</span>
                <div class="weather-rec-tags">${recTypes}</div>
              </div>
            </div>
          `;
        }

        const allocList = it.family_ticket_allocation || it.passenger_allocations || [];
        const seatedCount = allocList.filter((a) => {
          const pts = Number(a.points_used ?? a.points_charged ?? 0);
          const cash = Number(a.cash_fare_usd ?? a.cash_fare_charged_usd ?? 0);
          const tax = Number(a.taxes_usd ?? a.taxes_and_fees_usd ?? 0);
          return pts > 0 || cash > 0 || tax > 0;
        }).length;

        const twoPlusVerifyBannerHtml = it.requires_two_plus_seat_verification
          ? `
            <div class="two-plus-verify-banner">
              <strong>ℹ️ ${isHe ? `מכסת 2+ מושבי בונוס קלאסי באל על (${seatedCount} מושבים נדרשים):` : `EL AL 2+ Classic Award Seat Cap (${seatedCount} seats needed):`}</strong>
              <span>
                ${
                  isHe
                    ? `אל על מאשרת לפחות 2 מושבי בונוס קלאסי בטיסה זו. אם בחיפוש ל-${seatedCount} נוסעים מופיע תעריף Cash & Points, הזמינו 2 מושבי בונוס קלאסי והשלימו את היתר בנפרד.`
                    : `EL AL confirms at least 2 Classic Award seats on this flight. If searching for ${seatedCount} passengers switches to Cash & Points rates, book 2 Classic Award seats first and complete the remaining seat separately.`
                }
              </span>
            </div>
          `
          : '';

        const allocRows = allocList
          .map((a, aIdx) => {
            const ptsVal = Number(a.points_used ?? a.points_charged ?? 0);
            const taxVal = Number(a.taxes_usd ?? a.taxes_and_fees_usd ?? 0);
            const cashVal = Number(a.cash_fare_usd ?? a.cash_fare_charged_usd ?? 0);
            const isLapInfant = ptsVal === 0 && taxVal === 0 && cashVal === 0 && String(a.rbd_code || '') !== 'Y';
            const modeLabel = isLapInfant
              ? (isHe ? 'תינוק ללא מושב — על הברכיים (INFANT_LAP)' : 'Lap Infant — No Separate Seat (INFANT_LAP)')
              : `${a.ticket_mode || a.outbound_ticket_kind || ''} (${a.cabin_class || a.outbound_cabin || 'ECONOMY'})`;
            return `
              <tr>
                <td>${escapeHtml(formatGenericPassengerLabel(a, aIdx))}</td>
                <td><code>${escapeHtml(isLapInfant ? 'INFANT' : (a.program_code || a.program_used || 'CASH'))}</code></td>
                <td>${escapeHtml(modeLabel)}</td>
                <td dir="ltr">${ptsVal.toLocaleString()} pts</td>
                <td dir="ltr">$${taxVal.toFixed(0)} + $${cashVal.toFixed(0)}</td>
              </tr>
            `;
          })
          .join('');

        const checked = state.selectedProposalIds.has(p.id) ? 'checked' : '';
        const rankNum = p.rank_order || p.rank || (idx + 1);
        const tierCode = p.recommendation_tier || (idx === 0 ? 'RECOMMENDED' : idx < 4 ? 'TOP_CHOICE' : 'ALTERNATIVE');
        const tierBadgeText = formatRecommendationTierLabel(tierCode);
        const tierBadgeCls =
          tierCode === 'RECOMMENDED'
            ? 'badge-vacation'
            : tierCode === 'TOP_CHOICE'
              ? 'badge-camp'
              : 'badge-tier-alt';
        const fbvsVal = p.flight_bonus_value_score ?? p.family_bonus_value_score ?? 0;
        const perVal = p.pto_efficiency_ratio ?? p.parent_pto_efficiency_ratio ?? 0;
        const perDisplay = isHe ? `פי ${Number(perVal).toFixed(1)}` : `${Number(perVal).toFixed(1)}x`;
        const schoolMissed = Number(p.total_school_days_missed_across_children || 0);
        const schoolCellCls = schoolMissed === 0 ? 'score-pill kpi-cell kpi-cell-pine' : 'score-pill kpi-cell';
        const schoolText = schoolMissed === 0
          ? (isHe ? '0 ימים ✓' : '0 days ✓')
          : (isHe ? `${schoolMissed} ימים` : `${schoolMissed} days`);
        const stratText = formatStrategyLabel(it.fulfillment_strategy);
        const destIcon = DESTINATION_ICONS[it.destination_iata] || '✈️';
        const cityTitle = isHe ? (it.destination_city_he || it.destination_iata) : (it.destination_city_en || it.destination_iata);
        const elalBookUrl = resolveElAlBookingUrl(it);
        const outLeg = (it.outbound_legs && it.outbound_legs[0]) || null;
        const inLeg = (it.inbound_legs && it.inbound_legs[0]) || null;
        const outFlightBadgeHtml = formatLegFlightBadge(outLeg);
        const inFlightBadgeHtml = formatLegFlightBadge(inLeg);
        // Flight-number tags get their own line of the route bar: outbound at the start edge, inbound at the end edge
        const flightsRowHtml = outFlightBadgeHtml || inFlightBadgeHtml
          ? `
                  <div class="route-flights-row">
                    <span class="route-flight-slot">${outFlightBadgeHtml}</span>
                    <span class="route-flight-slot route-flight-slot-end">${inFlightBadgeHtml}</span>
                  </div>`
          : '';
        const returnOriginLabel =
          it.return_origin_iata && it.return_origin_iata !== it.destination_iata
            ? `${it.destination_iata}/${it.return_origin_iata}`
            : it.destination_iata;
        const totalVacDays = p.total_vacation_days || ((Number(it.trip_nights) || 0) + 1);
        const ptsTotal = Number(it.total_matmid_points || 0).toLocaleString();
        const oopCash = Number(it.total_out_of_pocket_cash_usd || 0).toFixed(0);
        const netSavedNum = Math.round(Number(it.net_cash_saved_usd || 0));
        const netSavedDisplay =
          netSavedNum > 0
            ? `+$${netSavedNum}`
            : netSavedNum < 0
              ? `-$${Math.abs(netSavedNum)}`
              : '$0';
        const savedRowCls = netSavedNum > 0 ? 'stub-fare-row stub-fare-saved' : 'stub-fare-row';
        const cppVal = Number(it.cents_per_point_value || 0).toFixed(2);

        const elalBookBtnHtml = elalBookUrl
          ? `
              <a class="btn-elal-book" href="${escapeHtml(elalBookUrl)}" target="_blank" rel="noopener noreferrer" data-elal-book-link="true" title="${isHe ? 'פתיחת טיסת אל על ב-Google Flights למעבר מאומת ישירות להזמנה באל על' : 'Open EL AL flight on Google Flights for verified handoff to EL AL booking'}">
                <span>✈️ ${isHe ? 'להזמנת טיסת אל על (Google Flights)' : 'Book EL AL (Google Flights)'}</span>
                <span dir="ltr" aria-hidden="true">↗</span>
              </a>
            `
          : '';

        return `
          <article class="proposal-card tier-${escapeHtml(tierCode)}">
            <div class="proposal-pass-grid">
              <div class="proposal-pass-main">
                <div class="proposal-top-bar">
                  <div class="proposal-dest-header">
                    <span class="proposal-dest-icon" aria-hidden="true">${destIcon}</span>
                    <div class="proposal-title-group">
                      <span class="${tierBadgeCls}">#${rankNum} ${escapeHtml(tierBadgeText)}</span>
                      <strong class="proposal-dest-title">${escapeHtml(cityTitle)}</strong>
                      <span class="proposal-route-pair" dir="ltr">${escapeHtml(it.origin_iata || 'TLV')} ⇄ ${escapeHtml(it.destination_iata)}</span>
                    </div>
                  </div>
                  ${topStyleChipHtml}
                </div>

                <div class="boarding-route-bar" dir="ltr">
                  <div class="route-endpoint">
                    <span class="route-iata">${escapeHtml(it.origin_iata || 'TLV')}</span>
                    <span class="route-date">${escapeHtml(it.departure_date)}</span>
                  </div>
                  <div class="route-arc-Track">
                    <span class="route-nights-pill" dir="auto">${escapeHtml(it.trip_nights)} ${isHe ? 'לילות' : 'Nights'} · ${escapeHtml(totalVacDays)} ${isHe ? 'ימי חופש' : 'Days'}</span>
                    <div class="route-arc-line">
                      <span>●</span>
                      <span class="route-arc-dash"></span>
                      <span>✈️</span>
                      <span class="route-arc-dash"></span>
                      <span>●</span>
                    </div>
                  </div>
                  <div class="route-endpoint route-endpoint-end">
                    <span class="route-iata">${escapeHtml(returnOriginLabel)}</span>
                    <span class="route-date">${escapeHtml(it.return_date)}</span>
                  </div>${flightsRowHtml}
                </div>

                <div class="score-strip pass-kpi-grid">
                  <div class="score-pill kpi-cell">
                    <span class="kpi-cell-label">🏖️ ${isHe ? 'ניצול חופשה' : 'Vacation Match'}</span>
                    <strong class="kpi-cell-val" dir="ltr">${Number(p.vacation_utilization_score || 0).toFixed(1)}/100</strong>
                  </div>
                  <div class="score-pill kpi-cell">
                    <span class="kpi-cell-label">📈 ${isHe ? 'מכפיל חופש הורה' : 'PTO Multiplier'}</span>
                    <strong class="kpi-cell-val" dir="ltr">${escapeHtml(perDisplay)}</strong>
                  </div>
                  <div class="${schoolCellCls}">
                    <span class="kpi-cell-label">🎒 ${isHe ? 'חיסור מבי״ס' : 'School Missed'}</span>
                    <strong class="kpi-cell-val">${escapeHtml(schoolText)}</strong>
                  </div>
                  <div class="score-pill kpi-cell">
                    <span class="kpi-cell-label">💎 ${isHe ? 'כדאיות בונוס' : 'Award Value'}</span>
                    <strong class="kpi-cell-val" dir="ltr">${Number(fbvsVal).toFixed(1)}/100</strong>
                  </div>
                </div>

                ${weatherStripHtml}
              </div>

              <div class="proposal-pass-stub">
                <div class="stub-score-header">
                  <div class="stub-ctos-badge" dir="ltr" title="${isHe ? 'ציון התאמה משוקלל' : 'Overall Optimization Score'}">
                    <span>⭐</span>
                    <span class="stub-ctos-num">${Number(p.combined_trip_optimization_score || 0).toFixed(1)}</span>
                    <span class="stub-ctos-max">/100</span>
                  </div>
                  <span class="stub-strategy-tag" title="${escapeHtml(stratText)}">${escapeHtml(stratText)}</span>
                </div>

                <div class="stub-fare-ledger">
                  <div class="stub-fare-row">
                    <span class="stub-fare-label">💳 ${isHe ? 'נקודות מועדון' : 'Points Used'}</span>
                    <span class="stub-fare-val stub-fare-points" dir="ltr">${ptsTotal}</span>
                  </div>
                  <div class="stub-fare-row">
                    <span class="stub-fare-label">💵 ${isHe ? 'תשלום במזומן' : 'Out-of-Pocket'}</span>
                    <span class="stub-fare-val" dir="ltr">$${oopCash}</span>
                  </div>
                  <div class="${savedRowCls}">
                    <span class="stub-fare-label">${isHe ? 'חיסכון נטו' : 'Net Saved'}</span>
                    <span class="stub-fare-val" dir="ltr">${netSavedDisplay} (${cppVal}¢)</span>
                  </div>
                </div>

                <div class="stub-actions-stack">
                  ${elalBookBtnHtml}
                  <div class="stub-secondary-actions">
                    <label class="compare-check-label">
                      <input type="checkbox" data-compare-id="${escapeHtml(p.id)}" ${checked} />
                      <span>${isHe ? 'השווה' : 'Compare'}</span>
                    </label>
                    <a class="btn-ics-link" href="/api/v1/vacations/${encodeURIComponent(p.id)}/export.ics" download>
                      📅 ${isHe ? 'ייצוא .ics' : 'Export .ics'}
                    </a>
                  </div>
                </div>
              </div>
            </div>

            <div class="proposal-pass-footer">
              ${twoPlusVerifyBannerHtml}
              <details class="allocations-details">
                <summary class="allocations-summary">
                  🎫 ${isHe ? `פירוט הקצאת כרטיסי בונוס ומועדונים לכל נוסע (${allocList.length} נוסעים)` : `Per-Passenger Ticket & Club Allocation (${allocList.length} passengers)`}
                </summary>
                <div class="allocations-table-wrap">
                  <table class="allocations-table">
                    <thead>
                      <tr>
                        <th>${isHe ? 'נוסע' : 'Passenger'}</th>
                        <th>${isHe ? 'מועדון' : 'Club'}</th>
                        <th>${isHe ? 'סוג כרטיס ומחלקה' : 'Ticket Mode & Cabin'}</th>
                        <th>${isHe ? 'נקודות' : 'Points'}</th>
                        <th>${isHe ? 'מסים + השלמת מזומן' : 'Taxes + Cash'}</th>
                      </tr>
                    </thead>
                    <tbody>${allocRows}</tbody>
                  </table>
                </div>
              </details>
            </div>
          </article>
        `;
      })
      .join('');

    const toggleFeedHtml =
      totalCount > INITIAL_PROPOSALS_LIMIT
        ? `
          <div class="proposals-feed-toggle-wrap">
            <button type="button" class="btn-secondary btn-feed-toggle" data-toggle-all-proposals="true">
              ${
                state.showAllProposals
                  ? (isHe ? `הצג ${INITIAL_PROPOSALS_LIMIT} חלופות מובילות בלבד ▴` : `Show top ${INITIAL_PROPOSALS_LIMIT} proposals only ▴`)
                  : (isHe ? `הצג את כל ${totalCount} החלופות ▾` : `Show all ${totalCount} proposals ▾`)
              }
            </button>
          </div>
        `
        : '';

    container.innerHTML = fallbackBannerHtml + cardsHtml + toggleFeedHtml;
  }

  function updateActiveModeBadge() {
    const badge = document.getElementById('active-mode-badge');
    if (!badge) return;
    const isHe = state.locale === 'he';
    const mode = state.dateSelectionMode;
    if (mode === 'SPECIFIC_DATES') {
      badge.textContent = isHe ? 'תאריכים ספציפיים (±גמישות)' : 'Exact Dates (±Flex)';
    } else if (mode === 'MOE_VACATION_MAXIMIZATION') {
      badge.textContent = isHe ? 'מקסום שנתי (משרד החינוך)' : 'Annual MoE Maximization';
    } else {
      badge.textContent = isHe ? 'תכנון לפי חג ושנה' : 'Holiday & Year Intent';
    }
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

    updateActiveModeBadge();
    renderProfileControls();
  }

  function applyLocaleStrings() {
    const isHe = state.locale === 'he';
    const dataAttr = isHe ? 'data-he' : 'data-en';
    const ariaAttr = isHe ? 'data-aria-he' : 'data-aria-en';

    document.querySelectorAll('[data-he][data-en]').forEach((el) => {
      const txt = el.getAttribute(dataAttr);
      if (txt !== null) {
        el.textContent = txt;
      }
    });

    document.querySelectorAll('[data-aria-he][data-aria-en]').forEach((el) => {
      const ariaTxt = el.getAttribute(ariaAttr);
      if (ariaTxt) {
        el.setAttribute('aria-label', ariaTxt);
      }
    });

    document.title = isHe
      ? 'מתכנן חופשות משפחתיות חכם | משרד החינוך וכרטיסי בונוס אל על'
      : 'Smart Family Vacation Planner | MoE Breaks & EL AL Award Flights';

    const headerTitle = document.getElementById('header-title');
    if (headerTitle) {
      headerTitle.textContent = isHe ? 'מתכנן חופשות משפחתיות חכם' : 'Smart Family Vacation Planner';
    }
    const headerSubtitle = document.getElementById('header-subtitle');
    if (headerSubtitle) {
      headerSubtitle.textContent = isHe
        ? 'מקסום ימי חופשה של משרד החינוך, קייטנות ניצנים וכרטיסי בונוס בנקודות'
        : 'Maximize MoE school holidays, Nitzanim camps & airline award flights';
    }
    const heroEyebrow = document.getElementById('hero-eyebrow');
    if (heroEyebrow) {
      heroEyebrow.textContent = isHe
        ? '✈️ המראות מנתב״ג (TLV) · חופשות 2026–2029'
        : '✈️ Departing TLV · Family Vacation Seasons 2026–2029';
    }
    const heroHeadline = document.getElementById('hero-headline');
    if (heroHeadline) {
      heroHeadline.textContent = isHe
        ? 'הפכו כל חופשת בית ספר לחופשת חלומות משפחתית'
        : 'Turn Every School Break Into a Family Escape';
    }
    const heroLead = document.getElementById('hero-lead');
    if (heroLead) {
      heroLead.textContent = isHe
        ? 'הצלבה חכמה בין לוח החופשות של משרד החינוך, קייטנות ניצנים ומושבי בונוס באל על ומועדוני תעופה — מקסימום חופשה במינימום ימי חופש מההורים.'
        : 'Cross-references official MoE school breaks & Nitzanim camps with EL AL Matmid and partner loyalty seats — more vacation days for every parent PTO day.';
    }
    const vtTitle = document.getElementById('vacation-type-title');
    if (vtTitle) {
      vtTitle.textContent = isHe
        ? '🌤️ סגנון חופשה ותיעדוף מזג אוויר ביעד:'
        : '🌤️ Vacation Style & Destination Weather Prioritization:';
    }
    const vtHint = document.getElementById('vacation-type-hint');
    if (vtHint) {
      vtHint.textContent = isHe
        ? 'בחרו סגנון חופשה אחד או יותר לתיעדוף מזג אוויר אידיאלי'
        : 'Select one or more styles to prioritize ideal destination weather';
    }
    const zSearch = document.getElementById('zone-search-title');
    if (zSearch) {
      zSearch.textContent = isHe
        ? '1. תכנון חופשה סביב חגים וחופשות משרד החינוך'
        : '1. Holiday, Dates & Airline Search Controls';
    }
    const zProfile = document.getElementById('zone-profile-title');
    if (zProfile) {
      zProfile.textContent = isHe
        ? '2. פרופיל משפחה, גילאי ילדים וארנקי מועדונים'
        : '2. Family Profile, Children & Loyalty Wallets';
    }
    const zCalendar = document.getElementById('zone-calendar-title');
    if (zCalendar) {
      zCalendar.textContent = isHe
        ? 'לוח חופשות משרד החינוך וחפיפה רב-גילאית (תצוגה אופציונלית)'
        : 'MoE Multi-Child Vacation Calendar (Optional View)';
    }

    updateActiveModeBadge();
    setCalendarVisibility(state.isCalendarVisible, false);
    renderProfileControls();
    renderCalendarTable();
    renderComparisonBanner();
    renderProposals();
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
    const bridgeDays = Number((document.getElementById('input-bridge-days') || {}).value || 3);
    const weatherModeVal =
      (document.getElementById('select-weather-filter-mode') || {}).value ||
      state.weatherFilterMode ||
      'SOFT_PRIORITIZE';
    state.weatherFilterMode = weatherModeVal;

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
      max_bridge_days_shift: bridgeDays,
      preferred_vacation_types: state.selectedVacationTypes || [],
      weather_filter_mode: weatherModeVal
    };

    state.validationErrorHe = null;
    state.validationErrorEn = null;

    try {
      const res = await apiSend('POST', '/api/v1/vacations/search', payload);
      state.proposals = res.proposals || [];
      state.showAllProposals = false;
      state.lastComparison = null;
      state.statusMessageHe = res.status_message_he || null;
      state.statusMessageEn = res.status_message_en || null;
      state.weatherFallbackMessageHe = res.weather_fallback_message_he || null;
      state.selectedProposalIds = new Set(state.proposals.slice(0, 2).map((p) => p.id));
    } catch (err) {
      const detail = extractApiErrorDetail(err);
      const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
      state.proposals = [];
      state.showAllProposals = false;
      state.lastComparison = null;
      state.selectedProposalIds = new Set();
      state.validationErrorHe = `נא לוודא שטווח התאריכים ומספר הלילות בטופס החיפוש תקינים ולנסות שוב.${detailSuffixHe}`;
      state.validationErrorEn = `Verify that the return date is on or after the departure date and the nights range is valid, then try again.${detailSuffixEn}`;
    }
    renderComparisonBanner();
    renderProposals();
  }

  function bindEvents() {
    document.querySelectorAll('.mode-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        setDateMode(btn.getAttribute('data-mode'));
      });
    });

    document.querySelectorAll('[data-vacation-type]').forEach((pillBtn) => {
      pillBtn.addEventListener('click', () => {
        const vt = pillBtn.getAttribute('data-vacation-type');
        if (!vt || vt === 'ANY') {
          state.selectedVacationTypes = [];
        } else {
          const cur = new Set(state.selectedVacationTypes || []);
          cur.delete('ANY');
          if (cur.has(vt)) {
            cur.delete(vt);
          } else {
            cur.add(vt);
          }
          state.selectedVacationTypes = Array.from(cur);
        }
        syncVacationTypePills();
        runVacationSearch();
      });
    });

    const selectWeatherModeEl = document.getElementById('select-weather-filter-mode');
    if (selectWeatherModeEl) {
      selectWeatherModeEl.addEventListener('change', () => {
        state.weatherFilterMode = selectWeatherModeEl.value || 'SOFT_PRIORITIZE';
        runVacationSearch();
      });
    }

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
        applyLocaleStrings();
      });
    }

    const btnSaveProfile = document.getElementById('btn-save-profile');
    if (btnSaveProfile) {
      btnSaveProfile.addEventListener('click', async () => {
        if (!state.profile) return;
        state.profile.adults_count = Number(document.getElementById('prof-adults-count').value || 2);
        state.profile.annual_pto_budget = Number(document.getElementById('prof-pto-budget').value || 18);
        (state.profile.children || []).forEach((ch) => {
          const ageNum = Number(ch.child_age_years ?? 6);
          if (ageNum < 2) {
            if (ch.passenger_Current_type !== 'INFANT_SEAT') ch.passenger_Current_type = 'INFANT_LAP';
          } else if (ageNum <= 11) {
            ch.passenger_Current_type = 'CHILD';
          } else {
            ch.passenger_Current_type = 'YOUTH';
          }
        });
        recalculateHouseholdPointsFromWallets();
        state.validationErrorHe = null;
        state.validationErrorEn = null;
        try {
          state.profile = await apiSend('PUT', '/api/v1/profile', state.profile);
          renderProfileControls();
          await runVacationSearch();
        } catch (err) {
          const detail = extractApiErrorDetail(err);
          const detailSuffixEn = detail && !/[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
          const detailSuffixHe = detail && /[\u0590-\u05FF]/.test(detail) ? ` (${detail})` : '';
          state.proposals = [];
          state.lastComparison = null;
          state.selectedProposalIds = new Set();
          state.validationErrorHe = `לא ניתן לשמור את פרופיל המשפחה — בדקו שגילאי הילדים (0–18) ומספר המבוגרים (1–6) תקינים.${detailSuffixHe}`;
          state.validationErrorEn = `Could not save family profile — verify adults count (1–6), child ages (0–18), and non-negative points.${detailSuffixEn}`;
          renderComparisonBanner();
          renderProposals();
        }
      });
    }

    const btnAddChild = document.getElementById('btn-add-child');
    if (btnAddChild) {
      btnAddChild.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (!state.profile) return;
        const detailsEl = btnAddChild.closest('details');
        if (detailsEl) detailsEl.open = true;
        const nextIdx = state.profile.children.length + 1;
        const defaultAge = 7;
        state.profile.children.push({
          id: `child-custom-${Date.now()}`,
          child_name_he: `ילד/ה ${nextIdx}`,
          child_age_years: defaultAge,
          passenger_Current_type: 'CHILD',
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
      btnAddWallet.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (!state.profile) return;
        const detailsEl = btnAddWallet.closest('details');
        if (detailsEl) detailsEl.open = true;
        const nextIdx = (state.profile.passenger_loyalty_wallets || []).length + 1;
        const adultNum = Math.max(1, ((nextIdx - 1) % Math.max(1, state.profile.adults_count || 2)) + 1);
        state.profile.passenger_loyalty_wallets.push({
          id: `wallet-custom-${Date.now()}`,
          passenger_id: `ADULT_${adultNum}`,
          passenger_name: state.locale === 'he' ? `הורה ${adultNum}` : `Parent ${adultNum}`,
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
        const w = state.profile.passenger_loyalty_wallets[idx];
        if (w) {
          userEditedWalletKeys.add(getWalletKey(w, idx));
          w.passenger_name = target.value;
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
        state.profile.children[idx].passenger_Current_type =
          newAge < 2 ? 'INFANT_LAP' : newAge <= 11 ? 'CHILD' : 'YOUTH';
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
        const w = state.profile.passenger_loyalty_wallets[idx];
        if (w) {
          userEditedWalletKeys.add(getWalletKey(w, idx));
          w.passenger_name = target.value;
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
      if (!target) return;
      const toggleFeedBtn = target.closest('[data-toggle-all-proposals]');
      if (toggleFeedBtn) {
        state.showAllProposals = !state.showAllProposals;
        renderProposals();
        return;
      }
      if (!state.profile) return;
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
        try {
          const sy = (document.getElementById('select-school-year') || {}).value || '2027-2028';
          await apiSend('POST', `/api/v1/moe-calendar/sync/${sy}`, { force_remote_check: false });
          state.calendarData = await apiGet(`/api/v1/moe-calendar/${sy}`);
          renderCalendarTable();
        } catch (err) {
          console.error('MoE calendar sync failed:', err);
        }
      });
    }

    const btnSyncElal = document.getElementById('btn-sync-elal');
    if (btnSyncElal) {
      btnSyncElal.addEventListener('click', async () => {
        try {
          const destVal = (document.getElementById('select-destination') || {}).value || 'ROM';
          await apiSend('POST', '/api/v1/elal-bonus/sync', {
            destinations: [destVal],
            start_date: '2027-04-10',
            end_date: '2027-04-28',
            origin: 'TLV',
            force_refresh: true
          });
          await runVacationSearch();
        } catch (err) {
          console.error('EL AL sync failed:', err);
        }
      });
    }

    const btnCompare = document.getElementById('btn-compare-selected');
    if (btnCompare) {
      btnCompare.addEventListener('click', async () => {
        const ids = Array.from(state.selectedProposalIds);
        if (ids.length === 0) return;
        try {
          state.lastComparison = await apiSend('POST', '/api/v1/vacations/compare', { proposal_ids: ids });
          renderComparisonBanner();
        } catch (err) {
          console.error('Comparison failed:', err);
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

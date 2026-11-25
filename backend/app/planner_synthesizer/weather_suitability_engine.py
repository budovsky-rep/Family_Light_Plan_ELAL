"""Destination Weather Suitability & Vacation Style Scoring Engine (`weather_suitability_engine.py`).

Implements Requirements R1 and R2:
- Evaluates 12-month WMO / Copernicus ERA5 climatological norms across all 25 supported
  destinations in `DESTINATION_CATALOG`.
- Computes continuous `[0.0, 100.0]` weather suitability scores using piecewise-linear
  trapezoidal comfort curves `T(x; a, b, c, d)` for 6 specialized family vacation styles:
  1. `BEACH_AND_POOL` ("חופשת בטן-גב — חוף ובריכה")
  2. `NATURE_TRIP` ("טיול בטבע ונופים")
  3. `URBAN_CULTURE` ("טיול עירוני, תרבות ושופינג")
  4. `FAMILY_ATTRACTIONS_PARKS` ("פארקי שעשועים ואטרקציות משפחתיות")
  5. `SNOW_AND_SKI` ("חופשת שלג וסקי משפחתית")
  6. `WINTER_FESTIVE` ("שווקי חורף ואווירה אירופאית")
- Supports day-exact cross-month holiday interpolation (e.g. Kippur-Sukkot Sep/Oct,
  Pre-Pesach Mar/Apr), 50%/50% Open-Jaw route blending (`MXP` + `FCO`), and multi-type
  synergy scoring (`0.70 * max + 0.30 * mean`).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from backend.app.schemas.domain import (
    DEFAULT_VACATION_TYPE_THRESHOLDS,
    DestinationWeatherMetrics,
    VacationType,
)
from backend.app.storage_cache.seed_data import DESTINATION_CATALOG

VACATION_TYPE_LABELS_HE: dict[str, str] = {
    "ANY": "כל סוגי החופשות",
    "BEACH_AND_POOL": "חופשת בטן-גב (חוף ובריכה)",
    "NATURE_TRIP": "טיול בטבע ונופים",
    "URBAN_CULTURE": "טיול עירוני, תרבות ושופינג",
    "FAMILY_ATTRACTIONS_PARKS": "פארקי שעשועים ואטרקציות משפחתיות",
    "SNOW_AND_SKI": "חופשת שלג וסקי משפחתית",
    "WINTER_FESTIVE": "שווקי חורף ואווירה אירופאית",
}

VACATION_TYPE_LABELS_EN: dict[str, str] = {
    "ANY": "All Vacation Styles",
    "BEACH_AND_POOL": "Beach & Pool Relaxation",
    "NATURE_TRIP": "Nature & Scenic Trip",
    "URBAN_CULTURE": "Urban, Culture & Shopping",
    "FAMILY_ATTRACTIONS_PARKS": "Theme Parks & Family Attractions",
    "SNOW_AND_SKI": "Family Snow & Ski",
    "WINTER_FESTIVE": "Winter Markets & Festive Europe",
}

VACATION_TYPE_ICONS: dict[str, str] = {
    "ANY": "🌍",
    "BEACH_AND_POOL": "🏖️",
    "NATURE_TRIP": "🥾",
    "URBAN_CULTURE": "🏛️",
    "FAMILY_ATTRACTIONS_PARKS": "🎢",
    "SNOW_AND_SKI": "⛷️",
    "WINTER_FESTIVE": "🎄",
}

SPECIALIZED_VACATION_TYPES: tuple[str, ...] = (
    "BEACH_AND_POOL",
    "NATURE_TRIP",
    "URBAN_CULTURE",
    "FAMILY_ATTRACTIONS_PARKS",
    "SNOW_AND_SKI",
    "WINTER_FESTIVE",
)

STYLE_ACTIVITY_FALLBACK_HE: dict[str, str] = {
    "BEACH_AND_POOL": "רחצה בחופים מוגנים, בריכות, טיילת חוף ושייט משפחתי רגוע",
    "NATURE_TRIP": "מסלולי הליכה קלים למשפחות, תצפיות פנורמיות ושמורות טבע",
    "URBAN_CULTURE": "שיטוט בעיר העתיקה, מוזיאונים לכל המשפחה, שווקים ובתי קפה",
    "FAMILY_ATTRACTIONS_PARKS": "אקווריומים, מוזיאוני מדע, פארקי חוויה ואטרקציות אינטראקטיביות לילדים",
    "SNOW_AND_SKI": "מדרונות גלישה לכל הרמות, מזחלות שלג, רכבלים ועיירות אלפיניות",
    "WINTER_FESTIVE": "דוכני חורף מוארים, החלקה על הקרח, מדרחובים חגיגיים ומוזיאונים חמימים",
}

STYLE_ACTIVITY_FALLBACK_EN: dict[str, str] = {
    "BEACH_AND_POOL": "family beaches, resort pools, waterfront promenades, and calm boat outings",
    "NATURE_TRIP": "scenic family trails, panoramic viewpoints, national parks, and nature reserves",
    "URBAN_CULTURE": "historic old-town walks, interactive museums, local markets, and neighborhood cafes",
    "FAMILY_ATTRACTIONS_PARKS": "theme parks, science museums, zoos, aquariums, and hands-on family attractions",
    "SNOW_AND_SKI": "family ski slopes, snow tubing, alpine cable cars, and cozy mountain villages",
    "WINTER_FESTIVE": "illuminated winter markets, outdoor ice rinks, festive plazas, and warm indoor museums",
}


def _clamp(val: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, float(val)))


def trapezoidal_comfort(x: float, a: float, b: float, c: float, d: float) -> float:
    """Piecewise-linear trapezoidal comfort curve returning `[0.0, 100.0]`.

    - `[b, c]` is the 100-point sweet spot.
    - `(a, b)` ramps linearly from 0 to 100.
    - `(c, d)` ramps linearly from 100 down to 0.
    """
    val = float(x)
    if val <= a or val >= d:
        return 0.0
    if b <= val <= c:
        return 100.0
    if val < b:
        return 100.0 * ((val - a) / max(1e-9, b - a))
    return 100.0 * ((d - val) / max(1e-9, d - c))


def _is_festive_market_date(d: date) -> float:
    """Return festive market season factor `[0.0, 1.0]` for calendar date `d`."""
    if (d.month == 11 and d.day >= 15) or d.month == 12 or (d.month == 1 and d.day <= 6):
        return 1.0
    if d.month == 1 or (d.month == 2 and d.day <= 15):
        return 0.25
    return 0.0


class DestinationWeatherSuitabilityEngine:
    """Computes weather suitability scores (`0.0–100.0`) and telemetry for destinations and date windows."""

    def __init__(self, catalog: Optional[dict[str, dict[str, Any]]] = None) -> None:
        self.catalog: dict[str, dict[str, Any]] = (
            catalog if catalog is not None else DESTINATION_CATALOG
        )

    def score_single_month(
        self,
        dest_iata: str,
        month: int,
        festive_overlap_ratio: Optional[float] = None,
    ) -> dict[str, float]:
        """Compute all 6 vacation-type weather scores (`0.0–100.0`) for `(dest_iata, month)`."""
        iata = str(dest_iata or "FCO").strip().upper()
        meta = self.catalog.get(iata) or self.catalog.get("FCO", {})
        c_prof = meta.get("climate_profile") or {}
        m_map = meta.get("monthly_weather") or {}
        m_norm = m_map.get(int(month)) or m_map.get(4) or {}

        t_max = float(m_norm.get("avg_max_temp_c", 20.0))
        t_min = float(m_norm.get("avg_min_temp_c", 10.0))
        t_sea_raw = m_norm.get("sea_water_temp_c")
        t_sea = float(t_sea_raw) if t_sea_raw is not None else None
        d_rain = float(m_norm.get("avg_rain_days", 5.0))
        p_mm = float(m_norm.get("precipitation_mm", 45.0))
        s_sun = float(m_norm.get("sunshine_hours_per_day", 7.0))
        h_rel = float(m_norm.get("avg_humidity_pct", 60.0))
        uv_max = float(m_norm.get("uv_index_max", 6.0))
        i_snow = float(m_norm.get("snow_reliability_index", 0.0))

        k_coast = float(c_prof.get("coastal_factor", 0.60))
        k_nature = float(c_prof.get("nature_affinity_factor", 1.00))
        k_urban = float(c_prof.get("urban_culture_affinity", 1.00))
        k_parks = float(c_prof.get("theme_park_tier", 0.95))
        is_ski = bool(c_prof.get("is_ski_accessible", False))
        has_festive = bool(c_prof.get("has_winter_festive_markets", False))

        # 1. BEACH_AND_POOL ("חופשת בטן-גב")
        s_air = trapezoidal_comfort(t_max, 19.0, 27.0, 33.5, 43.0)
        if t_sea is not None:
            s_water = trapezoidal_comfort(t_sea, 17.5, 24.0, 29.5, 34.0)
        else:
            t_pool = 0.72 * t_max + 0.28 * t_min
            s_water = trapezoidal_comfort(t_pool, 18.0, 24.0, 29.5, 34.0)
        s_dry_beach = (
            100.0
            * _clamp(1.0 - (d_rain / 16.0), 0.0, 1.0)
            * _clamp(1.0 - (max(0.0, p_mm - 40.0) / 280.0), 0.0, 1.0)
        )
        s_sun_beach = 100.0 * _clamp((s_sun - 2.5) / 7.5, 0.0, 1.0)
        s_humid = 100.0 * _clamp(1.0 - (max(0.0, h_rel - 60.0) / 45.0), 0.0, 1.0)

        w_beach_raw = k_coast * (
            0.35 * s_air
            + 0.25 * s_water
            + 0.20 * s_dry_beach
            + 0.15 * s_sun_beach
            + 0.05 * s_humid
        )
        if t_max < 20.0:
            w_beach_raw = min(w_beach_raw, 25.0)
        w_beach = round(_clamp(w_beach_raw, 0.0, 100.0), 1)

        # 2. NATURE_TRIP ("טיול בטבע")
        s_hike_day = trapezoidal_comfort(t_max, 6.0, 16.0, 25.5, 37.0)
        phi_frost = (
            _clamp((t_min + 4.0) / 8.0, 0.3, 1.0) if t_min < 4.0 else 1.0
        )
        s_hike_temp = phi_frost * s_hike_day
        s_trail_dry = (
            100.0
            * _clamp(1.0 - (d_rain / 14.0), 0.0, 1.0)
            * _clamp(1.0 - (max(0.0, p_mm - 30.0) / 200.0), 0.0, 1.0)
        )
        s_daylight = 100.0 * _clamp((s_sun - 1.5) / 5.5, 0.0, 1.0)
        s_air_qual = 100.0 * _clamp(
            1.0
            - (max(0.0, h_rel - 65.0) / 40.0)
            - (max(0.0, uv_max - 8.5) / 8.0),
            0.0,
            1.0,
        )
        w_nature = round(
            _clamp(
                k_nature
                * (
                    0.45 * s_hike_temp
                    + 0.30 * s_trail_dry
                    + 0.15 * s_daylight
                    + 0.10 * s_air_qual
                ),
                0.0,
                100.0,
            ),
            1,
        )

        # 3. URBAN_CULTURE ("טיול עירוני, תרבות ושופינג")
        s_urban_temp = trapezoidal_comfort(t_max, -6.0, 10.0, 28.0, 40.0)
        s_urban_dry = (
            100.0
            * _clamp(1.0 - (d_rain / 18.0), 0.0, 1.0)
            * _clamp(1.0 - (max(0.0, p_mm - 50.0) / 250.0), 0.0, 1.0)
        )
        w_urban = round(
            _clamp(
                k_urban
                * (
                    0.45 * s_urban_temp
                    + 0.30 * s_urban_dry
                    + 0.15 * s_daylight
                    + 0.10 * s_humid
                ),
                0.0,
                100.0,
            ),
            1,
        )

        # 4. FAMILY_ATTRACTIONS_PARKS ("פארקי שעשועים ואטרקציות משפחתיות")
        s_park_temp = trapezoidal_comfort(t_max, 5.0, 15.0, 29.0, 37.0)
        s_park_dry = (
            100.0
            * _clamp(1.0 - (d_rain / 14.0), 0.0, 1.0)
            * _clamp(1.0 - (max(0.0, p_mm - 35.0) / 200.0), 0.0, 1.0)
        )
        w_parks = round(
            _clamp(
                k_parks
                * (
                    0.45 * s_park_temp
                    + 0.35 * s_park_dry
                    + 0.20 * s_daylight
                ),
                0.0,
                100.0,
            ),
            1,
        )

        # 5. SNOW_AND_SKI ("חופשת שלג וסקי משפחתית")
        if not is_ski or i_snow <= 0.05:
            w_ski = 0.0
        else:
            s_cold = 100.0 * _clamp((10.0 - t_min) / 12.0, 0.0, 1.0)
            w_ski = round(
                _clamp(
                    100.0
                    * (
                        0.65 * i_snow
                        + 0.0020 * s_cold
                        + 0.0015 * s_daylight
                    ),
                    0.0,
                    100.0,
                ),
                1,
            )

        # 6. WINTER_FESTIVE ("שווקי חורף ואווירה אירופאית")
        if festive_overlap_ratio is not None:
            rho_festive = float(festive_overlap_ratio)
        else:
            if int(month) == 12:
                rho_festive = 1.0
            elif int(month) == 11:
                rho_festive = 0.55
            elif int(month) == 1:
                rho_festive = 0.45
            elif int(month) == 2:
                rho_festive = 0.25
            else:
                rho_festive = 0.0

        if not has_festive or rho_festive <= 0.0:
            w_festive = 0.0
        else:
            s_fest_temp = trapezoidal_comfort(t_max, -10.0, -2.0, 13.0, 22.0)
            w_festive = round(
                _clamp(
                    rho_festive
                    * (0.55 * s_fest_temp + 0.30 * s_urban_dry + 15.0),
                    0.0,
                    100.0,
                ),
                1,
            )

        return {
            "BEACH_AND_POOL": w_beach,
            "NATURE_TRIP": w_nature,
            "URBAN_CULTURE": w_urban,
            "FAMILY_ATTRACTIONS_PARKS": w_parks,
            "SNOW_AND_SKI": w_ski,
            "WINTER_FESTIVE": w_festive,
        }

    def evaluate_window_weather(
        self,
        dest_iata: str,
        start_date: date,
        end_date: date,
        preferred_vacation_types: Optional[list[str]] = None,
        return_origin_iata: Optional[str] = None,
        min_threshold_override: Optional[float] = None,
    ) -> tuple[float, dict[str, float], list[str], DestinationWeatherMetrics]:
        """Evaluate day-weighted weather suitability for `dest_iata` (and optional Open-Jaw `return_origin_iata`)
        over `[start_date, end_date]`.

        Returns `(weather_suitability_score, vacation_type_scores, recommended_types, weather_metrics)`.
        """
        out_iata = str(dest_iata or "FCO").strip().upper()
        in_iata = (
            str(return_origin_iata).strip().upper()
            if return_origin_iata
            else out_iata
        )
        if end_date < start_date:
            end_date = start_date

        total_days = max(1, (end_date - start_date).days + 1)
        mid_split = total_days // 2

        accum_scores: dict[str, float] = {vt: 0.0 for vt in SPECIALIZED_VACATION_TYPES}
        accum_tmax = 0.0
        accum_tmin = 0.0
        accum_tsea = 0.0
        tsea_days = 0
        accum_rain_prob_days = 0.0
        accum_precip = 0.0
        accum_sun = 0.0
        accum_humid = 0.0
        accum_uv = 0.0
        accum_snow = 0.0

        for idx in range(total_days):
            cur_d = start_date + timedelta(days=idx)
            active_iata = (
                out_iata
                if (out_iata == in_iata or idx < max(1, mid_split))
                else in_iata
            )
            meta = self.catalog.get(active_iata) or self.catalog.get("FCO", {})
            m_map = meta.get("monthly_weather") or {}
            m_norm = m_map.get(cur_d.month) or m_map.get(4) or {}

            fest_factor = _is_festive_market_date(cur_d)
            day_scores = self.score_single_month(
                active_iata, cur_d.month, festive_overlap_ratio=fest_factor
            )
            for vt in SPECIALIZED_VACATION_TYPES:
                accum_scores[vt] += day_scores[vt]

            accum_tmax += float(m_norm.get("avg_max_temp_c", 20.0))
            accum_tmin += float(m_norm.get("avg_min_temp_c", 10.0))
            if m_norm.get("sea_water_temp_c") is not None:
                accum_tsea += float(m_norm["sea_water_temp_c"])
                tsea_days += 1
            accum_rain_prob_days += float(m_norm.get("avg_rain_days", 5.0)) / 30.0
            accum_precip += float(m_norm.get("precipitation_mm", 45.0))
            accum_sun += float(m_norm.get("sunshine_hours_per_day", 7.0))
            accum_humid += float(m_norm.get("avg_humidity_pct", 60.0))
            accum_uv += float(m_norm.get("uv_index_max", 6.0))
            accum_snow += float(m_norm.get("snow_reliability_index", 0.0))

        type_scores: dict[str, float] = {
            vt: round(accum_scores[vt] / float(total_days), 1)
            for vt in SPECIALIZED_VACATION_TYPES
        }

        clean_prefs = [
            str(vt).strip().upper()
            for vt in (preferred_vacation_types or [])
            if str(vt).strip().upper() in SPECIALIZED_VACATION_TYPES
        ]

        if not clean_prefs:
            # When unfiltered ("ANY"), report the best natural vacation style suitability of this destination/season
            wss = max(type_scores.values()) if type_scores else 0.0
            effective_tau = 0.0
        elif len(clean_prefs) == 1:
            vt_sel = clean_prefs[0]
            wss = type_scores.get(vt_sel, 0.0)
            effective_tau = (
                float(min_threshold_override)
                if min_threshold_override is not None
                else DEFAULT_VACATION_TYPE_THRESHOLDS.get(vt_sel, 55.0)
            )
        else:
            sel_vals = [type_scores.get(vt, 0.0) for vt in clean_prefs]
            wss = round(
                0.70 * max(sel_vals) + 0.30 * (sum(sel_vals) / float(len(sel_vals))),
                1,
            )
            effective_tau = (
                float(min_threshold_override)
                if min_threshold_override is not None
                else min(
                    DEFAULT_VACATION_TYPE_THRESHOLDS.get(vt, 55.0)
                    for vt in clean_prefs
                )
            )

        recommended = [
            vt
            for vt, sc in sorted(
                type_scores.items(), key=lambda kv: kv[1], reverse=True
            )
            if sc >= DEFAULT_VACATION_TYPE_THRESHOLDS.get(vt, 55.0)
        ]

        avg_max_c = round(accum_tmax / float(total_days), 1)
        avg_min_c = round(accum_tmin / float(total_days), 1)
        sea_c = round(accum_tsea / float(tsea_days), 1) if tsea_days > 0 else None
        exp_rain_days = round(accum_rain_prob_days, 1)
        avg_precip_mm = round(accum_precip / float(total_days), 1)
        avg_sun_h = round(accum_sun / float(total_days), 1)
        avg_hum = int(round(accum_humid / float(total_days)))
        avg_uv = round(accum_uv / float(total_days), 1)
        avg_snow = round(accum_snow / float(total_days), 2)

        out_meta = self.catalog.get(out_iata) or {}
        in_meta = self.catalog.get(in_iata) or {}
        c_prof = out_meta.get("climate_profile") or {}
        in_c_prof = in_meta.get("climate_profile") or {}
        zone_label_he = str(c_prof.get("climate_zone_label_he") or "")
        highlights_map = c_prof.get("highlights_by_type_he") or {}
        in_highlights_map = in_c_prof.get("highlights_by_type_he") or {}

        top_style = (
            clean_prefs[0]
            if clean_prefs
            else (recommended[0] if recommended else "URBAN_CULTURE")
        )
        style_label_he = VACATION_TYPE_LABELS_HE.get(top_style, "חופשה משפחתית")
        style_label_en = VACATION_TYPE_LABELS_EN.get(top_style, "Family Vacation")
        highlight_he = highlights_map.get(top_style) or ""

        sea_note = f", טמפ' ים {sea_c}°C" if sea_c is not None else ""
        sea_note_en = f", sea {sea_c}°C" if sea_c is not None else ""
        hl_note = f" ({highlight_he})" if highlight_he else ""
        below_thresh = bool(clean_prefs and wss < effective_tau)
        warn_note = (
            f" ⚠️ שים לב: מזג האוויר במועד זה פחות אידיאלי עבור {style_label_he} (ציון {wss}/100 מתחת לסף {effective_tau})."
            if below_thresh
            else ""
        )
        warn_note_en = (
            f" ⚠️ Note: seasonal weather is below ideal comfort for {style_label_en} ({wss}/100 vs {effective_tau} threshold)."
            if below_thresh
            else ""
        )

        summary_he = (
            f"מזג אוויר צפוי: {avg_max_c}°C ביום / {avg_min_c}°C בלילה{sea_note}, "
            f"כ-{avg_sun_h} שעות שמש ביום וכ-{exp_rain_days} ימי גשם משוערים בטיול. "
            f"התאמה ל{style_label_he}: {wss}/100{hl_note}.{warn_note}"
        )
        summary_en = (
            f"Expected weather: {avg_max_c}°C day / {avg_min_c}°C night{sea_note_en}, "
            f"~{avg_sun_h}h daily sunshine and ~{exp_rain_days} expected rain days in trip. "
            f"{style_label_en} suitability: {wss}/100.{warn_note_en}"
        )

        candidate_styles: list[str] = []
        for vt in [*(clean_prefs or []), *recommended, top_style]:
            if vt in SPECIALIZED_VACATION_TYPES and vt not in candidate_styles:
                candidate_styles.append(vt)
            if len(candidate_styles) >= 2:
                break

        rec_parts_he: list[str] = []
        rec_parts_en: list[str] = []
        for vt in candidate_styles:
            vt_lbl_he = VACATION_TYPE_LABELS_HE.get(vt, "חופשה משפחתית")
            vt_lbl_en = VACATION_TYPE_LABELS_EN.get(vt, "Family Trip")
            out_hl = str(highlights_map.get(vt) or "").strip()
            in_hl = (
                str(in_highlights_map.get(vt) or "").strip()
                if in_iata != out_iata
                else ""
            )
            if out_hl and in_hl and in_hl != out_hl:
                dest_hl_he = f"{out_hl}; {in_hl}"
            elif out_hl:
                dest_hl_he = out_hl
            elif in_hl:
                dest_hl_he = in_hl
            else:
                dest_hl_he = STYLE_ACTIVITY_FALLBACK_HE.get(vt, "")
            rec_parts_he.append(
                f"{vt_lbl_he} — {dest_hl_he}" if dest_hl_he else vt_lbl_he
            )
            fb_en = STYLE_ACTIVITY_FALLBACK_EN.get(
                vt, "local highlights and family outings"
            )
            rec_parts_en.append(f"{vt_lbl_en} ({fb_en})")

        out_city_en = str(out_meta.get("city_en") or out_iata).strip()
        in_city_en = str(in_meta.get("city_en") or in_iata).strip()
        loc_en = (
            f"{out_city_en} & {in_city_en}"
            if in_iata != out_iata and in_city_en and in_city_en != out_city_en
            else out_city_en
        )
        activity_rec_he = " · ".join(rec_parts_he)
        activity_rec_en = f"In {loc_en}: " + " · ".join(rec_parts_en) + "."

        metrics = DestinationWeatherMetrics(
            destination_iata=out_iata,
            avg_max_temp_c=avg_max_c,
            avg_min_temp_c=avg_min_c,
            sea_water_temp_c=sea_c,
            expected_rain_days_in_trip=exp_rain_days,
            precipitation_mm=avg_precip_mm,
            sunshine_hours_per_day=avg_sun_h,
            avg_humidity_pct=avg_hum,
            uv_index_max=avg_uv,
            snow_reliability_index=avg_snow,
            climate_zone_label_he=zone_label_he,
            weather_summary_he=summary_he,
            weather_summary_en=summary_en,
            activity_recommendations_he=activity_rec_he,
            activity_recommendations_en=activity_rec_en,
            below_threshold_warning=below_thresh,
            overall_weather_suitability_score=round(wss, 1),
            scores_by_vacation_type=dict(type_scores),
            recommended_vacation_types=list(recommended),
            best_matching_vacation_type=top_style,
        )
        return round(wss, 1), type_scores, recommended, metrics

    def evaluate_destination(
        self,
        destination_iata: str,
        departure_date: date,
        return_date: date,
        preferred_vacation_types: Optional[list[str]] = None,
        return_origin_iata: Optional[str] = None,
        min_threshold_override: Optional[float] = None,
    ) -> DestinationWeatherMetrics:
        """Convenience wrapper returning `DestinationWeatherMetrics` directly."""
        _wss, _t_scores, _rec, metrics = self.evaluate_window_weather(
            dest_iata=destination_iata,
            start_date=departure_date,
            end_date=return_date,
            preferred_vacation_types=preferred_vacation_types,
            return_origin_iata=return_origin_iata,
            min_threshold_override=min_threshold_override,
        )
        return metrics

    def get_effective_threshold(
        self,
        preferred_vacation_types: Optional[list[str]],
        override_score: Optional[float] = None,
    ) -> float:
        """Return effective minimum weather suitability threshold `tau_t`."""
        clean_prefs = [
            str(vt).strip().upper()
            for vt in (preferred_vacation_types or [])
            if str(vt).strip().upper() in SPECIALIZED_VACATION_TYPES
        ]
        if not clean_prefs:
            return 0.0
        if override_score is not None:
            return float(override_score)
        return min(
            DEFAULT_VACATION_TYPE_THRESHOLDS.get(vt, 55.0) for vt in clean_prefs
        )

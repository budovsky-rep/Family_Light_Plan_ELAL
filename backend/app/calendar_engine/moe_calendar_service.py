"""Israeli Ministry of Education (`משרד החינוך`) Calendar Engine & Auto-Updater.

Implements:
1. `HebrewCalendarRuleProjector`: Deterministic Hebrew-to-Gregorian statutory
   holiday projector supporting any school year (`2025-2026` through `2035-2036+`)
   using exact Hebrew calendar arithmetic (Molad Tishrei + Four Dehiyyot + Knesset
   Shabbat avoidance rules).
2. `MoECalendarAutoUpdaterService`: Syncs and projects school year calendars into
   `moe_vacation_windows` via `SQLiteRepository`.
3. `MoECalendarService`: Evaluates daily status across all 8 `MoEFrameworkType`
   frameworks, `5_DAY` vs `6_DAY` school weeks, Nitzanim (`CAMP_OPTIONAL`),
   Middle School (`MIDDLE_SCHOOL_7_9`) hybrid rule, Isru Chag Sukkot divergence,
   Lag BaOmer `תשפ"ו` vs `תשפ"ז` divergence, June 20 vs June 30 split (including
   June 20, 2026 Saturday shift to Jun 18/19), Bagrut blackouts, and `TLV`
   Yom Kippur total shutdown.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backend.app.config_manager.settings import PROJECT_ROOT, get_settings
from backend.app.schemas.domain import (
    ChildDayStatus,
    ChildFramework,
    DailyFamilyCalendarMatrix,
    FamilyProfile,
    HolidayExtensionMode,
    MoECalendarSyncStatus,
    MoEFrameworkType,
    MoEVacationWindow,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    CALENDARS_DIR,
    expand_calendar_json_to_windows,
)

HEBREW_YEAR_LABELS: dict[int, str] = {
    5785: 'תשפ"ה',
    5786: 'תשפ"ו',
    5787: 'תשפ"ז',
    5788: 'תשפ"ח',
    5789: 'תשפ"ט',
    5790: 'תש"צ',
    5791: 'תשצ"א',
    5792: 'תשצ"ב',
    5793: 'תשצ"ג',
    5794: 'תשצ"ד',
    5795: 'תשצ"ה',
    5796: 'תשצ"ו',
}


def normalize_school_year(school_year: str | int) -> str:
    """Normalize `'YYYY-YYYY'` or 4-digit `'YYYY'` (e.g. `'2027'` -> `'2026-2027'`)."""
    raw = str(school_year).strip()
    if "-" in raw:
        parts = raw.split("-")
        if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 4:
            y1 = int(parts[0])
            y2 = int(parts[1])
            if y2 != y1 + 1:
                raise ValueError(f"Invalid school_year span: {raw!r}")
            return f"{y1}-{y2}"
    if len(raw) == 4 and raw.isdigit():
        y2 = int(raw)
        return f"{y2 - 1}-{y2}"
    raise ValueError(f"Invalid school_year format: {school_year!r}")


def gregorian_school_year_to_hebrew_year(school_year: str) -> tuple[int, str]:
    """Return `(hebrew_year_int, hebrew_year_str)` for `'YYYY-YYYY'`."""
    norm = normalize_school_year(school_year)
    end_year = int(norm.split("-")[1])
    heb_year = end_year + 3760
    label = HEBREW_YEAR_LABELS.get(heb_year, f'תשפ"{heb_year - 5780}')
    return heb_year, label


class HebrewCalendarRuleProjector:
    """Pure-Python Hebrew-to-Gregorian calendar projector for MoE vacation schedules."""

    @staticmethod
    def is_hebrew_leap_year(hebrew_year: int) -> bool:
        return ((7 * hebrew_year + 1) % 19) < 7

    @staticmethod
    def _hebrew_calendar_elapsed_days(hebrew_year: int) -> int:
        """Compute days elapsed from Hebrew epoch to 1 Tishrei of `hebrew_year` (Gauss/Reingold)."""
        months_elapsed = (235 * ((hebrew_year - 1) // 19)) + (
            12 * ((hebrew_year - 1) % 19)
        ) + ((7 * ((hebrew_year - 1) % 19) + 1) // 19)
        parts_elapsed = 204 + 793 * (months_elapsed % 1080)
        hours_elapsed = (
            5
            + 12 * months_elapsed
            + 793 * (months_elapsed // 1080)
            + (parts_elapsed // 1080)
        )
        conjunction_day = 1 + 29 * months_elapsed + (hours_elapsed // 24)
        conjunction_parts = 1080 * (hours_elapsed % 24) + (parts_elapsed % 1080)

        if (
            (conjunction_parts >= 19440)
            or (
                (conjunction_day % 7 == 2)
                and (conjunction_parts >= 9924)
                and not HebrewCalendarRuleProjector.is_hebrew_leap_year(hebrew_year)
            )
            or (
                (conjunction_day % 7 == 1)
                and (conjunction_parts >= 16789)
                and HebrewCalendarRuleProjector.is_hebrew_leap_year(hebrew_year - 1)
            )
        ):
            alt_day = conjunction_day + 1
        else:
            alt_day = conjunction_day

        if alt_day % 7 in (0, 3, 5):
            return alt_day + 1
        return alt_day

    @classmethod
    def rosh_hashanah_date(cls, hebrew_year: int) -> date:
        """Return the exact Gregorian `date` of 1 Tishrei (`Rosh Hashanah Day 1`) for `hebrew_year`."""
        # Known anchor: 1 Tishrei 5786 = 2025-09-23
        anchor_elapsed = cls._hebrew_calendar_elapsed_days(5786)
        target_elapsed = cls._hebrew_calendar_elapsed_days(hebrew_year)
        return date(2025, 9, 23) + timedelta(days=(target_elapsed - anchor_elapsed))

    @classmethod
    def pesach_first_day(cls, hebrew_year: int) -> date:
        """Return 15 Nissan (`First Day of Pesach`) for `hebrew_year` (always 163 days before 1 Tishrei H+1)."""
        next_rh = cls.rosh_hashanah_date(hebrew_year + 1)
        return next_rh - timedelta(days=163)

    @classmethod
    def yom_haatzmaut_date(cls, hebrew_year: int) -> date:
        """Return observed Israeli Independence Day (`5 Iyar` with Knesset Shabbat avoidance shifts)."""
        fifth_iyar = cls.pesach_first_day(hebrew_year) + timedelta(days=20)
        wd = fifth_iyar.weekday()  # Mon=0 .. Fri=4, Sat=5, Sun=6
        if wd == 4:  # Friday -> Thursday (4 Iyar)
            return fifth_iyar - timedelta(days=1)
        if wd == 5:  # Saturday -> Thursday (3 Iyar)
            return fifth_iyar - timedelta(days=2)
        if wd == 0:  # Monday -> Tuesday (6 Iyar)
            return fifth_iyar + timedelta(days=1)
        return fifth_iyar

    @classmethod
    def hanukkah_vacation_dates(cls, hebrew_year: int) -> tuple[date, date, date]:
        """Return `(start_date, end_date, resume_date)` for MoE Hanukkah break (26 Kislev - 2 Tevet)."""
        rh_curr = cls.rosh_hashanah_date(hebrew_year)
        rh_next = cls.rosh_hashanah_date(hebrew_year + 1)
        year_len = (rh_next - rh_curr).days
        # Complete year (Cheshvan=30, Kislev=30) -> 26 Kislev is 1 Tishrei + 85 days; else + 84 days
        offset = 85 if (year_len % 10 == 5) else 84
        start_d = rh_curr + timedelta(days=offset)
        end_d = start_d + timedelta(days=6)
        resume_d = end_d + timedelta(days=1)
        if resume_d.weekday() == 5:  # Saturday -> Sunday
            resume_d += timedelta(days=1)
        return start_d, end_d, resume_d

    @classmethod
    def project_school_year_calendar_doc(cls, school_year: str) -> dict[str, Any]:
        """Generate a complete MoE calendar JSON document for `school_year` (`YYYY-YYYY`)."""
        norm_year = normalize_school_year(school_year)
        y1_str, y2_str = norm_year.split("-")
        y1, y2 = int(y1_str), int(y2_str)
        heb_year, heb_label = gregorian_school_year_to_hebrew_year(norm_year)

        # School year start (Sept 1, or Sept 2 if Sept 1 is Saturday)
        sept_1 = date(y1, 9, 1)
        school_start = sept_1 + timedelta(days=1) if sept_1.weekday() == 5 else sept_1

        # June 20 & June 30 end dates with Saturday adjustment
        june_20 = date(y2, 6, 20)
        if june_20.weekday() == 5:  # Saturday (like 2026-06-20)
            end_7_12_6day = date(y2, 6, 19)
            end_7_12_5day = date(y2, 6, 18)
            summer_7_12_start = date(y2, 6, 19)
        elif june_20.weekday() == 4:  # Friday
            end_7_12_6day = date(y2, 6, 20)
            end_7_12_5day = date(y2, 6, 19)
            summer_7_12_start = date(y2, 6, 20)
        else:
            end_7_12_6day = june_20
            end_7_12_5day = june_20
            summer_7_12_start = date(y2, 6, 21)

        june_30 = date(y2, 6, 30)
        end_k6_6day = june_30 - timedelta(days=1) if june_30.weekday() == 5 else june_30
        end_k6_5day = (
            june_30 - timedelta(days=1)
            if june_30.weekday() == 4
            else (june_30 - timedelta(days=2) if june_30.weekday() == 5 else june_30)
        )

        # Hebrew holidays in `heb_year`
        rh1 = cls.rosh_hashanah_date(heb_year)
        rh_start = rh1 - timedelta(days=1)
        rh_end = rh1 + timedelta(days=1)
        rh_resume = rh_end + timedelta(days=1)
        if rh_resume.weekday() == 5:
            rh_resume += timedelta(days=1)

        yk_eve = rh1 + timedelta(days=8)
        yk_day = rh1 + timedelta(days=9)
        sukkot_k9_end = rh1 + timedelta(days=21)
        sukkot_k9_resume = sukkot_k9_end + timedelta(days=1)
        sukkot_10_12_end = rh1 + timedelta(days=22)  # Isru Chag Sukkot
        sukkot_10_12_resume = sukkot_10_12_end + timedelta(days=1)
        if sukkot_10_12_resume.weekday() == 5:
            sukkot_10_12_resume += timedelta(days=1)

        han_start, han_end, han_resume = cls.hanukkah_vacation_dates(heb_year)
        han_nitz_days = [
            han_start + timedelta(days=i)
            for i in range((han_end - han_start).days + 1)
            if (han_start + timedelta(days=i)).weekday() in (6, 0, 1, 2, 3)
        ][:5]
        han_nitz_end = han_nitz_days[-1] if han_nitz_days else han_end
        han_uncovered = [
            (han_start + timedelta(days=i)).isoformat()
            for i in range((han_end - han_start).days + 1)
            if (han_start + timedelta(days=i)) not in han_nitz_days
        ]

        pesach1 = cls.pesach_first_day(heb_year)
        purim_start = pesach1 - timedelta(days=30)
        purim_end = pesach1 - timedelta(days=29)
        purim_resume = purim_end + timedelta(days=1)
        if purim_resume.weekday() == 5:
            purim_resume += timedelta(days=1)

        pesach_start = pesach1 - timedelta(days=9)  # 6 Nissan
        pesach_end = pesach1 + timedelta(days=6)    # 21 Nissan
        pesach_resume = pesach_end + timedelta(days=1)  # 22 Nissan (Isru Chag Pesach is regular school day)
        if pesach_resume.weekday() == 5:
            pesach_resume += timedelta(days=1)

        pesach_nitz_days = [
            pesach_start + timedelta(days=i)
            for i in range(8)
            if (pesach_start + timedelta(days=i)).weekday() in (6, 0, 1, 2, 3)
        ][:5]
        pesach_nitz_end = pesach_nitz_days[-1] if pesach_nitz_days else (pesach1 - timedelta(days=2))
        pesach_uncovered = [
            (pesach_nitz_end + timedelta(days=i)).isoformat()
            for i in range(1, (pesach_end - pesach_nitz_end).days + 1)
        ]

        atzmaut_d = cls.yom_haatzmaut_date(heb_year)
        atzmaut_resume = atzmaut_d + timedelta(days=1)
        if atzmaut_resume.weekday() == 5:
            atzmaut_resume += timedelta(days=1)

        shavuot_start = pesach1 + timedelta(days=49)  # 5 Sivan (Erev Shavuot)
        shavuot_end = pesach1 + timedelta(days=50)    # 6 Sivan (Shavuot)
        shavuot_resume = shavuot_end + timedelta(days=1)
        if shavuot_resume.weekday() == 5:
            shavuot_resume += timedelta(days=1)

        next_sept_1 = date(y2, 9, 1)
        next_school_start = (
            next_sept_1 + timedelta(days=1) if next_sept_1.weekday() == 5 else next_sept_1
        )

        all_8 = [fw.value for fw in MoEFrameworkType]
        k12_no_daycare = [
            fw.value
            for fw in MoEFrameworkType
            if fw != MoEFrameworkType.DAYCARE_SUPERVISED
        ]

        return {
            "school_year_hebrew": heb_label,
            "school_year_gregorian": norm_year,
            "calendar_sync_source": "HEBREW_RULE_PROJECTED",
            "circular_ids": [f"projected-{heb_year}"],
            "frameworks": {
                "DAYCARE_SUPERVISED": {
                    "label_he": "מעונות יום ומשפחתונים בפיקוח",
                    "grades": "גילאי 0-3",
                    "start_date": school_start.isoformat(),
                    "end_date_6day": date(y2, 8, 8).isoformat(),
                    "end_date_5day": date(y2, 8, 8).isoformat(),
                    "nitzanim_eligible": False,
                },
                "MUNICIPAL_GAN": {
                    "label_he": "גני ילדים רשמיים",
                    "grades": "גילאי 3-6",
                    "start_date": school_start.isoformat(),
                    "end_date_6day": end_k6_6day.isoformat(),
                    "end_date_5day": end_k6_5day.isoformat(),
                    "nitzanim_eligible": True,
                },
                "ELEMENTARY_1_3": {
                    "label_he": "בית ספר יסודי (כיתות א'-ג')",
                    "grades": "א'-ג'",
                    "start_date": school_start.isoformat(),
                    "end_date_6day": end_k6_6day.isoformat(),
                    "end_date_5day": end_k6_5day.isoformat(),
                    "nitzanim_eligible": True,
                },
                "ELEMENTARY_4_6": {
                    "label_he": "בית ספר יסודי (כיתות ד'-ו')",
                    "grades": "ד'-ו'",
                    "start_date": school_start.isoformat(),
                    "end_date_6day": end_k6_6day.isoformat(),
                    "end_date_5day": end_k6_5day.isoformat(),
                    "nitzanim_eligible": False,
                },
                "MIDDLE_SCHOOL_7_9": {
                    "label_he": "חטיבת ביניים (כיתות ז'-ט')",
                    "grades": "ז'-ט'",
                    "start_date": school_start.isoformat(),
                    "end_date_6day": end_7_12_6day.isoformat(),
                    "end_date_5day": end_7_12_5day.isoformat(),
                    "nitzanim_eligible": False,
                },
                "HIGH_SCHOOL_10_12": {
                    "label_he": 'חטיבה עליונה (כיתות י\'-י"ב)',
                    "grades": 'י\'-י"ב',
                    "start_date": school_start.isoformat(),
                    "end_date_6day": end_7_12_6day.isoformat(),
                    "end_date_5day": end_7_12_5day.isoformat(),
                    "nitzanim_eligible": False,
                },
                "SPECIAL_ED": {
                    "label_he": "חינוך מיוחד",
                    "grades": "גילאי 3-21",
                    "start_date": school_start.isoformat(),
                    "end_date_6day": date(y2, 8, 15).isoformat(),
                    "end_date_5day": date(y2, 8, 15).isoformat(),
                    "nitzanim_eligible": False,
                },
                "RELIGIOUS_HAREDI": {
                    "label_he": "ממלכתי-דתי / מוסדות חרדיים",
                    "grades": 'א\'-י"ב',
                    "start_date": school_start.isoformat(),
                    "end_date_6day": end_k6_6day.isoformat(),
                    "end_date_5day": end_k6_5day.isoformat(),
                    "nitzanim_eligible": True,
                },
            },
            "periods": [
                {
                    "id": f"rosh_hashanah_{heb_year}",
                    "holiday_code": "ROSH_HASHANAH",
                    "name_he": "ראש השנה",
                    "name_en": "Rosh Hashanah",
                    "start_date": rh_start.isoformat(),
                    "end_date": rh_end.isoformat(),
                    "resume_date": rh_resume.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {},
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"yom_kippur_sukkot_{heb_year}",
                    "holiday_code": "YOM_KIPPUR_SUKKOT",
                    "name_he": "יום הכיפורים, גשר וחג הסוכות",
                    "name_en": "Yom Kippur, Bridge & Sukkot",
                    "start_date": yk_eve.isoformat(),
                    "end_date": sukkot_k9_end.isoformat(),
                    "resume_date": sukkot_k9_resume.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {
                        "HIGH_SCHOOL_10_12": {
                            "start_date": yk_eve.isoformat(),
                            "end_date": sukkot_10_12_end.isoformat(),
                            "resume_date": sukkot_10_12_resume.isoformat(),
                        }
                    },
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [
                        {
                            "start_iso": f"{yk_eve.isoformat()}T13:00:00",
                            "end_iso": f"{yk_day.isoformat()}T22:30:00",
                            "reason": "Yom Kippur Ben Gurion Airport total shutdown",
                        }
                    ],
                },
                {
                    "id": f"hanukkah_{heb_year}",
                    "holiday_code": "HANUKKAH",
                    "name_he": "חופשת חנוכה",
                    "name_en": "Hanukkah",
                    "start_date": han_start.isoformat(),
                    "end_date": han_end.isoformat(),
                    "resume_date": han_resume.isoformat(),
                    "applies_to_frameworks": k12_no_daycare,
                    "framework_overrides": {},
                    "nitzanim_window": {
                        "active": True,
                        "program_name_he": "בית הספר של החגים - חנוכה",
                        "start_date": han_start.isoformat(),
                        "end_date": han_nitz_end.isoformat(),
                        "operating_days_count": len(han_nitz_days),
                        "hours_base": "08:00-13:00",
                        "uncovered_vacation_dates": han_uncovered,
                    },
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"purim_{heb_year}",
                    "holiday_code": "PURIM",
                    "name_he": "חופשת פורים",
                    "name_en": "Purim",
                    "start_date": purim_start.isoformat(),
                    "end_date": purim_end.isoformat(),
                    "resume_date": purim_resume.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {},
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"pesach_{heb_year}",
                    "holiday_code": "PESACH",
                    "name_he": "חופשת פסח",
                    "name_en": "Pesach",
                    "start_date": pesach_start.isoformat(),
                    "end_date": pesach_end.isoformat(),
                    "resume_date": pesach_resume.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {
                        "DAYCARE_SUPERVISED": {
                            "start_date": (pesach1 - timedelta(days=1)).isoformat(),
                            "end_date": pesach_end.isoformat(),
                            "resume_date": pesach_resume.isoformat(),
                        }
                    },
                    "nitzanim_window": {
                        "active": True,
                        "program_name_he": "בית הספר של החגים - פסח",
                        "start_date": pesach_start.isoformat(),
                        "end_date": pesach_nitz_end.isoformat(),
                        "operating_days_count": len(pesach_nitz_days),
                        "hours_base": "08:00-13:00",
                        "uncovered_vacation_dates": pesach_uncovered,
                    },
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"yom_haatzmaut_{heb_year}",
                    "holiday_code": "YOM_HAATZMAUT",
                    "name_he": "יום העצמאות",
                    "name_en": "Independence Day",
                    "start_date": atzmaut_d.isoformat(),
                    "end_date": atzmaut_d.isoformat(),
                    "resume_date": atzmaut_resume.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {},
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"shavuot_{heb_year}",
                    "holiday_code": "SHAVUOT",
                    "name_he": "חג השבועות",
                    "name_en": "Shavuot",
                    "start_date": shavuot_start.isoformat(),
                    "end_date": shavuot_end.isoformat(),
                    "resume_date": shavuot_resume.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {},
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"summer_june_20_30_{heb_year}",
                    "holiday_code": "SUMMER_JUNE_20_30",
                    "name_he": "החופש הגדול — 20–30 ביוני (על-יסודי)",
                    "name_en": "Late June Summer Arbitrage (Grades 7-12)",
                    "start_date": summer_7_12_start.isoformat(),
                    "end_date": date(y2, 6, 30).isoformat(),
                    "resume_date": next_school_start.isoformat(),
                    "applies_to_frameworks": [
                        "MIDDLE_SCHOOL_7_9",
                        "HIGH_SCHOOL_10_12",
                    ],
                    "framework_overrides": {},
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"summer_july_{heb_year}",
                    "holiday_code": "SUMMER_JULY",
                    "name_he": "החופש הגדול — יולי",
                    "name_en": "Summer Vacation - July",
                    "start_date": date(y2, 7, 1).isoformat(),
                    "end_date": date(y2, 7, 31).isoformat(),
                    "resume_date": next_school_start.isoformat(),
                    "applies_to_frameworks": [
                        "MUNICIPAL_GAN",
                        "ELEMENTARY_1_3",
                        "ELEMENTARY_4_6",
                        "MIDDLE_SCHOOL_7_9",
                        "HIGH_SCHOOL_10_12",
                        "RELIGIOUS_HAREDI",
                    ],
                    "framework_overrides": {},
                    "nitzanim_window": {
                        "active": True,
                        "program_name_he": "בית הספר של החופש הגדול - ניצנים",
                        "start_date": date(y2, 7, 1).isoformat(),
                        "end_date": date(y2, 7, 31).isoformat(),
                        "operating_days_count": 22,
                        "hours_base": "08:00-13:00",
                        "uncovered_vacation_dates": [],
                    },
                    "tlv_airport_restrictions": [],
                },
                {
                    "id": f"summer_august_{heb_year}",
                    "holiday_code": "SUMMER_AUGUST",
                    "name_he": "החופש הגדול — אוגוסט",
                    "name_en": "Summer Vacation - August",
                    "start_date": date(y2, 8, 1).isoformat(),
                    "end_date": date(y2, 8, 31).isoformat(),
                    "resume_date": next_school_start.isoformat(),
                    "applies_to_frameworks": all_8,
                    "framework_overrides": {
                        "DAYCARE_SUPERVISED": {
                            "start_date": date(y2, 8, 9).isoformat(),
                            "end_date": date(y2, 8, 31).isoformat(),
                            "resume_date": next_school_start.isoformat(),
                        },
                        "SPECIAL_ED": {
                            "start_date": date(y2, 8, 16).isoformat(),
                            "end_date": date(y2, 8, 31).isoformat(),
                            "resume_date": next_school_start.isoformat(),
                        },
                    },
                    "nitzanim_window": None,
                    "tlv_airport_restrictions": [],
                },
            ],
        }


class IsraeliWorkplaceCalendarService:
    """Deterministic Israeli public & statutory workplace holiday calendar (`לוח חגים ומועדים במשק`).

    Projects statutory holidays directly via `HebrewCalendarRuleProjector` across `1900..2100`
    (never derived from `moe_vacation_windows`) and evaluates per-person workday vacation cost
    under the fixed Sunday–Thursday Israeli workplace schedule:
    1. Friday–Saturday (`weekday in (4, 5)`) -> `0.0` (strict precedence even on holidays/Chol HaMoed)
    2. 9 statutory official Israeli work holidays falling Sun–Thu -> `0.0`
    3. Chol HaMoed Sukkot (`16–21 Tishrei`) & Chol HaMoed Pesach (`16–20 Nissan`) on Sun–Thu -> `0.5`
    4. All other Sunday–Thursday workdays -> `1.0`
    """

    _YEAR_HOLIDAYS_CACHE: dict[int, tuple[frozenset[date], frozenset[date]]] = {}
    _SCHOOL_YEAR_PERIODS_CACHE: dict[str, tuple[dict[str, Any], ...]] = {}

    CANONICAL_WORKPLACE_ROLLING_HOLIDAYS: tuple[tuple[str, str, str], ...] = (
        ("ROSH_HASHANAH", "ראש השנה", "Rosh Hashanah"),
        ("YOM_KIPPUR_SUKKOT_BRIDGE", "גשר כיפור–סוכות", "Yom Kippur–Sukkot Bridge"),
        ("SUKKOT", "סוכות וחול המועד", "Sukkot & Chol HaMoed"),
        ("PESACH", "פסח וחול המועד", "Passover & Chol HaMoed"),
        ("YOM_HAATZMAUT", "יום העצמאות (גשר סופ״ש)", "Independence Day Bridge"),
        ("SHAVUOT", "חג השבועות (סופ״ש ארוך)", "Shavuot Long Weekend"),
    )
    WORKPLACE_INDIVIDUAL_ROLLING_HOLIDAYS: tuple[tuple[str, str, str], ...] = (
        ("ROSH_HASHANAH", "ראש השנה", "Rosh Hashanah"),
        ("SUKKOT", "סוכות בלבד (חול המועד)", "Sukkot Alone (Chol HaMoed)"),
        ("PESACH", "פסח וחול המועד", "Passover & Chol HaMoed"),
        ("YOM_HAATZMAUT", "יום העצמאות", "Independence Day"),
        ("SHAVUOT", "חג השבועות", "Shavuot"),
    )
    WORKPLACE_MEGA_BRIDGE_HOLIDAYS: tuple[
        tuple[str, str, str, tuple[str, ...], int], ...
    ] = (
        (
            "FULL_TISHREI",
            "כל חגי תשרי: ראש השנה → סוכות",
            "All Tishrei Holidays: Rosh Hashanah → Sukkot",
            ("ROSH_HASHANAH", "YOM_KIPPUR", "SUKKOT"),
            1,
        ),
        (
            "YOM_KIPPUR_SUKKOT_BRIDGE",
            "גשר כיפור–סוכות",
            "Yom Kippur–Sukkot Bridge",
            ("YOM_KIPPUR", "SUKKOT"),
            2,
        ),
        (
            "ROSH_HASHANAH_KIPPUR_BRIDGE",
            "גשר ראש השנה–כיפור",
            "Rosh Hashanah–Yom Kippur Bridge",
            ("ROSH_HASHANAH", "YOM_KIPPUR"),
            3,
        ),
    )
    RECOMMENDED_NIGHTS_BY_CODE: dict[str, tuple[int, int]] = {
        "BEST_YEAR_MAXIMIZER": (3, 15),
        "FULL_TISHREI": (16, 23),
        "YOM_KIPPUR_SUKKOT_BRIDGE": (10, 16),
        "YOM_KIPPUR_SUKKOT": (10, 16),
        "ROSH_HASHANAH_KIPPUR_BRIDGE": (9, 13),
        "SUKKOT": (4, 8),
        "PESACH": (4, 7),
        "ROSH_HASHANAH": (2, 4),
        "YOM_HAATZMAUT": (2, 4),
        "SHAVUOT": (2, 4),
    }
    _AUTUMN_WORKPLACE_CODES: frozenset[str] = frozenset(
        {
            "ROSH_HASHANAH",
            "YOM_KIPPUR",
            "YOM_KIPPUR_SUKKOT",
            "YOM_KIPPUR_SUKKOT_BRIDGE",
            "FULL_TISHREI",
            "ROSH_HASHANAH_KIPPUR_BRIDGE",
            "SUKKOT",
            "SUKKOT_I",
            "CHOL_HAMOED_SUKKOT",
            "SIMCHAT_TORAH",
        }
    )

    @staticmethod
    def _parse_hhmm_minutes(local_time: Optional[str]) -> Optional[int]:
        if local_time is None:
            return None
        s = str(local_time).strip()
        if not s:
            return None
        parts = s.split(":")
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, TypeError):
            return None
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour * 60 + minute

    @classmethod
    def yom_kippur_closure_window(cls, gregorian_year: int) -> tuple[date, date]:
        """Return `(yk_eve, yk_day)` for Ben Gurion Airport Yom Kippur closure in `gregorian_year`."""
        rh1 = HebrewCalendarRuleProjector.rosh_hashanah_date(int(gregorian_year) + 3761)
        return (rh1 + timedelta(days=8), rh1 + timedelta(days=9))

    @classmethod
    def is_tlv_yom_kippur_closure(
        cls, target_date: date | datetime | str, local_time: Optional[str] = None
    ) -> bool:
        """Return True iff Ben Gurion Airport (`TLV`) is closed for Yom Kippur on `target_date` (and optional `HH:MM`)."""
        d = cls._coerce_date(target_date)
        yk_eve, yk_day = cls.yom_kippur_closure_window(d.year)
        if d != yk_eve and d != yk_day:
            return False
        if local_time is None or not str(local_time).strip():
            return True
        mins = cls._parse_hhmm_minutes(local_time)
        if mins is None:
            return True
        if d == yk_eve:
            return mins >= 13 * 60
        if d == yk_day:
            return mins <= 22 * 60 + 30
        return False

    @classmethod
    def is_itinerary_blocked_by_tlv_yom_kippur(
        cls,
        dep_date: date | datetime | str,
        ret_date: date | datetime | str,
        outbound_legs: Any = (),
        inbound_legs: Any = (),
        origin_iata: str = "TLV",
    ) -> bool:
        """Check whether an itinerary departs or arrives at TLV during Yom Kippur closure.

        Staying abroad over Yom Kippur (`dep_date < yk_day < ret_date`) is ALLOWED.
        Departing or landing at TLV during closure (date-only `yk_eve`/`yk_day`, timed
        `yk_eve >= 13:00` or `yk_day <= 22:30`, including overnight inbound flights crossing
        midnight into `yk_eve`/`yk_day`) is strictly REJECTED.
        """
        dep_d = cls._coerce_date(dep_date)
        ret_d = cls._coerce_date(ret_date)
        if cls.is_tlv_yom_kippur_closure(dep_d) or cls.is_tlv_yom_kippur_closure(ret_d):
            return True

        orig_u = str(origin_iata or "TLV").strip().upper()
        for leg in outbound_legs or ():
            if isinstance(leg, dict):
                leg_orig = str(leg.get("origin_iata") or "").strip().upper()
                leg_date_raw = leg.get("flight_date")
                dep_time = leg.get("departure_time_local")
            else:
                leg_orig = str(getattr(leg, "origin_iata", "") or "").strip().upper()
                leg_date_raw = getattr(leg, "flight_date", None)
                dep_time = getattr(leg, "departure_time_local", None)
            if leg_orig == orig_u and leg_date_raw is not None:
                leg_d = cls._coerce_date(leg_date_raw)
                if cls.is_tlv_yom_kippur_closure(leg_d, dep_time or None):
                    return True

        for leg in inbound_legs or ():
            if isinstance(leg, dict):
                leg_dest = str(leg.get("destination_iata") or "").strip().upper()
                leg_date_raw = leg.get("flight_date")
                dep_time = leg.get("departure_time_local")
                arr_time = leg.get("arrival_time_local")
            else:
                leg_dest = str(getattr(leg, "destination_iata", "") or "").strip().upper()
                leg_date_raw = getattr(leg, "flight_date", None)
                dep_time = getattr(leg, "departure_time_local", None)
                arr_time = getattr(leg, "arrival_time_local", None)
            if leg_dest == orig_u and leg_date_raw is not None:
                leg_d = cls._coerce_date(leg_date_raw)
                dep_mins = cls._parse_hhmm_minutes(dep_time)
                arr_mins = cls._parse_hhmm_minutes(arr_time)
                arr_d = (
                    leg_d + timedelta(days=1)
                    if (dep_mins is not None and arr_mins is not None and arr_mins < dep_mins)
                    else leg_d
                )
                if cls.is_tlv_yom_kippur_closure(arr_d, arr_time or None):
                    return True

        return False

    @classmethod
    def get_recommended_nights_range(cls, holiday_code: str) -> tuple[int, int]:
        """Return canonical `(recommended_min_nights, recommended_max_nights)` for a workplace holiday code."""
        code = str(holiday_code or "").strip().upper()
        return cls.RECOMMENDED_NIGHTS_BY_CODE.get(code, (4, 7))

    @classmethod
    def detect_merged_workplace_holidays(
        cls, start_date: date | datetime | str, end_date: date | datetime | str
    ) -> list[dict[str, Any]]:
        """Return chronological statutory Israeli workplace holidays overlapped by `[start_date, end_date]`."""
        s_d = cls._coerce_date(start_date)
        e_d = cls._coerce_date(end_date)
        if e_d < s_d:
            return []
        heb_years = sorted(
            {s_d.year + 3760, s_d.year + 3761, e_d.year + 3760, e_d.year + 3761}
        )
        seen: set[tuple[str, str]] = set()
        found: list[dict[str, Any]] = []
        for heb_y in heb_years:
            rh1 = HebrewCalendarRuleProjector.rosh_hashanah_date(heb_y)
            pes1 = HebrewCalendarRuleProjector.pesach_first_day(heb_y)
            atz = HebrewCalendarRuleProjector.yom_haatzmaut_date(heb_y)
            specs = (
                (
                    "ROSH_HASHANAH",
                    "ראש השנה",
                    "Rosh Hashanah",
                    "ראש השנה",
                    "Rosh Hashanah",
                    rh1,
                    rh1 + timedelta(days=1),
                    False,
                ),
                (
                    "YOM_KIPPUR",
                    "יום כיפור (שהייה בחו״ל)",
                    "Yom Kippur (abroad)",
                    "יום כיפור",
                    "Yom Kippur",
                    rh1 + timedelta(days=9),
                    rh1 + timedelta(days=9),
                    True,
                ),
                (
                    "SUKKOT",
                    "סוכות",
                    "Sukkot",
                    "סוכות",
                    "Sukkot",
                    rh1 + timedelta(days=14),
                    rh1 + timedelta(days=21),
                    False,
                ),
                (
                    "PESACH",
                    "פסח",
                    "Passover",
                    "פסח",
                    "Passover",
                    pes1,
                    pes1 + timedelta(days=6),
                    False,
                ),
                (
                    "YOM_HAATZMAUT",
                    "יום העצמאות",
                    "Independence Day",
                    "יום העצמאות",
                    "Independence Day",
                    atz,
                    atz,
                    False,
                ),
                (
                    "SHAVUOT",
                    "שבועות",
                    "Shavuot",
                    "שבועות",
                    "Shavuot",
                    pes1 + timedelta(days=50),
                    pes1 + timedelta(days=50),
                    False,
                ),
            )
            for (
                code,
                name_he,
                name_en,
                short_he,
                short_en,
                h_start,
                h_end,
                is_stay_abroad,
            ) in specs:
                if h_start <= e_d and h_end >= s_d:
                    dedup_key = (code, h_start.isoformat())
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    found.append(
                        {
                            "code": code,
                            "name_he": name_he,
                            "name_en": name_en,
                            "short_name_he": short_he,
                            "short_name_en": short_en,
                            "start_date": h_start.isoformat(),
                            "end_date": h_end.isoformat(),
                            "is_stay_abroad_holiday": is_stay_abroad,
                        }
                    )
        found.sort(key=lambda item: (str(item["start_date"]), str(item["code"])))
        return found

    @staticmethod
    def _coerce_date(val: date | datetime | str) -> date:
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        s = str(val).strip()
        if "T" in s:
            s = s.split("T", 1)[0]
        return date.fromisoformat(s)

    @classmethod
    def get_year_holiday_sets(
        cls, hebrew_year: int
    ) -> tuple[frozenset[date], frozenset[date]]:
        """Return `(official_holidays_9d, chol_hamoed_11d)` for Hebrew year `hebrew_year`."""
        cached = cls._YEAR_HOLIDAYS_CACHE.get(hebrew_year)
        if cached is not None:
            return cached

        rh1 = HebrewCalendarRuleProjector.rosh_hashanah_date(hebrew_year)
        pes1 = HebrewCalendarRuleProjector.pesach_first_day(hebrew_year)
        atz = HebrewCalendarRuleProjector.yom_haatzmaut_date(hebrew_year)

        official_days = frozenset(
            {
                rh1,  # 1 Tishrei — Rosh Hashanah I
                rh1 + timedelta(days=1),  # 2 Tishrei — Rosh Hashanah II
                rh1 + timedelta(days=9),  # 10 Tishrei — Yom Kippur
                rh1 + timedelta(days=14),  # 15 Tishrei — Sukkot I
                rh1 + timedelta(days=21),  # 22 Tishrei — Simchat Torah / Shemini Atzeret
                pes1,  # 15 Nissan — Pesach I
                pes1 + timedelta(days=6),  # 21 Nissan — Pesach VII
                atz,  # Observed 5 Iyar — Yom HaAtzmaut (with Knesset Fri/Sat/Mon shifts)
                pes1 + timedelta(days=50),  # 6 Sivan — Shavuot
            }
        )
        chol_hamoed_days = frozenset(
            [rh1 + timedelta(days=offset) for offset in range(15, 21)]  # 16–21 Tishrei (6d)
            + [pes1 + timedelta(days=offset) for offset in range(1, 6)]  # 16–20 Nissan (5d)
        )
        pair = (official_days, chol_hamoed_days)
        cls._YEAR_HOLIDAYS_CACHE[hebrew_year] = pair
        return pair

    @classmethod
    def classify_workday_date(cls, target_date: date | str) -> tuple[str, float]:
        """Classify a single calendar date under the 4-bucket Israeli workplace rule."""
        d = cls._coerce_date(target_date)
        if d.weekday() in (4, 5):  # Friday=4, Saturday=5
            return ("WEEKEND", 0.0)

        h_spring = d.year + 3760
        h_autumn = d.year + 3761
        off_s, chol_s = cls.get_year_holiday_sets(h_spring)
        off_a, chol_a = cls.get_year_holiday_sets(h_autumn)

        if d in off_s or d in off_a:
            return ("OFFICIAL_HOLIDAY", 0.0)
        if d in chol_s or d in chol_a:
            return ("CHOL_HAMOED", 0.5)
        return ("REGULAR_WORKDAY", 1.0)

    @classmethod
    def evaluate_trip_workdays_cost(
        cls, start_date: date | str, end_date: date | str
    ) -> dict[str, Any]:
        """Evaluate inclusive `[start_date, end_date]` per-person workplace vacation-days cost."""
        s_date = cls._coerce_date(start_date)
        e_date = cls._coerce_date(end_date)
        if e_date < s_date:
            return {
                "workplace_vacation_days_cost": 0.0,
                "regular_workdays_count": 0,
                "chol_hamoed_workdays_count": 0,
                "official_holiday_workdays_saved_count": 0,
                "weekend_days_count": 0,
                "holiday_or_weekend_days_count": 0,
            }

        regular_cnt = 0
        chol_cnt = 0
        holiday_saved_cnt = 0
        weekend_cnt = 0
        total_days = (e_date - s_date).days + 1

        for idx in range(total_days):
            d = s_date + timedelta(days=idx)
            bucket, _cost = cls.classify_workday_date(d)
            if bucket == "WEEKEND":
                weekend_cnt += 1
            elif bucket == "OFFICIAL_HOLIDAY":
                holiday_saved_cnt += 1
            elif bucket == "CHOL_HAMOED":
                chol_cnt += 1
            else:
                regular_cnt += 1

        total_cost = round(regular_cnt * 1.0 + chol_cnt * 0.5, 1)
        return {
            "workplace_vacation_days_cost": total_cost,
            "regular_workdays_count": regular_cnt,
            "chol_hamoed_workdays_count": chol_cnt,
            "official_holiday_workdays_saved_count": holiday_saved_cnt,
            "weekend_days_count": weekend_cnt,
            "holiday_or_weekend_days_count": holiday_saved_cnt + weekend_cnt,
        }

    @classmethod
    def get_workplace_holidays_for_school_year(
        cls, school_year: str
    ) -> list[dict[str, Any]]:
        """Return the 10 chronological statutory Israeli workplace holiday/Chol HaMoed periods."""
        norm_year = normalize_school_year(school_year)
        cached = cls._SCHOOL_YEAR_PERIODS_CACHE.get(norm_year)
        if cached is not None:
            return [dict(item) for item in cached]

        heb_year, heb_label = gregorian_school_year_to_hebrew_year(norm_year)
        rh1 = HebrewCalendarRuleProjector.rosh_hashanah_date(heb_year)
        pes1 = HebrewCalendarRuleProjector.pesach_first_day(heb_year)
        atz = HebrewCalendarRuleProjector.yom_haatzmaut_date(heb_year)

        raw_specs: tuple[tuple[str, str, str, date, date, str], ...] = (
            ("ROSH_HASHANAH", "ראש השנה", "Rosh Hashanah", rh1, rh1 + timedelta(days=1), "OFFICIAL_HOLIDAY"),
            ("YOM_KIPPUR", "יום הכיפורים", "Yom Kippur", rh1 + timedelta(days=9), rh1 + timedelta(days=9), "OFFICIAL_HOLIDAY"),
            ("SUKKOT_I", "חג סוכות א׳", "Sukkot I", rh1 + timedelta(days=14), rh1 + timedelta(days=14), "OFFICIAL_HOLIDAY"),
            ("CHOL_HAMOED_SUKKOT", "חול המועד סוכות", "Chol HaMoed Sukkot", rh1 + timedelta(days=15), rh1 + timedelta(days=20), "CHOL_HAMOED"),
            ("SIMCHAT_TORAH", "שמיני עצרת / שמחת תורה", "Simchat Torah", rh1 + timedelta(days=21), rh1 + timedelta(days=21), "OFFICIAL_HOLIDAY"),
            ("PESACH_I", "חג פסח א׳", "Passover I", pes1, pes1, "OFFICIAL_HOLIDAY"),
            ("CHOL_HAMOED_PESACH", "חול המועד פסח", "Chol HaMoed Pesach", pes1 + timedelta(days=1), pes1 + timedelta(days=5), "CHOL_HAMOED"),
            ("PESACH_VII", "שביעי של פסח", "Passover VII", pes1 + timedelta(days=6), pes1 + timedelta(days=6), "OFFICIAL_HOLIDAY"),
            ("YOM_HAATZMAUT", "יום העצמאות", "Independence Day", atz, atz, "OFFICIAL_HOLIDAY"),
            ("SHAVUOT", "חג השבועות", "Shavuot", pes1 + timedelta(days=50), pes1 + timedelta(days=50), "OFFICIAL_HOLIDAY"),
        )

        entries: list[dict[str, Any]] = []
        for code, name_he, name_en, s_d, e_d, status in raw_specs:
            is_official = status == "OFFICIAL_HOLIDAY"
            eval_res = cls.evaluate_trip_workdays_cost(s_d, e_d)
            entries.append(
                {
                    "id": f"workplace_{heb_year}_{code}",
                    "school_year": norm_year,
                    "school_year_hebrew": heb_label,
                    "holiday_code": code,
                    "name_he": name_he,
                    "name_en": name_en,
                    "start_date": s_d.isoformat(),
                    "end_date": e_d.isoformat(),
                    "calendar_days": (e_d - s_d).days + 1,
                    "workplace_status": status,
                    "workday_cost_per_day": 0.0 if is_official else 0.5,
                    "effective_workdays_cost": eval_res["workplace_vacation_days_cost"],
                    "status_badge_he": "שבתון · 0 ימי חופש" if is_official else "חול המועד · 0.5 יום",
                    "status_badge_en": "Holiday · 0d" if is_official else "Chol HaMoed · 0.5d",
                }
            )

        cls._SCHOOL_YEAR_PERIODS_CACHE[norm_year] = tuple(entries)
        return [dict(item) for item in entries]

    @classmethod
    def resolve_workplace_holiday_span(
        cls, holiday_code: str, target_year: int
    ) -> Optional[tuple[date, date]]:
        """Resolve a statutory Israeli workplace holiday code & Gregorian target year to `(start_date, end_date)`."""
        code = str(holiday_code or "").strip().upper()
        if not code:
            return None
        yr = int(target_year)
        heb_year = (yr + 3761) if code in cls._AUTUMN_WORKPLACE_CODES else (yr + 3760)
        rh1 = HebrewCalendarRuleProjector.rosh_hashanah_date(heb_year)
        pes1 = HebrewCalendarRuleProjector.pesach_first_day(heb_year)
        atz = HebrewCalendarRuleProjector.yom_haatzmaut_date(heb_year)

        if code == "ROSH_HASHANAH":
            return (rh1, rh1 + timedelta(days=1))
        if code == "YOM_KIPPUR":
            return (rh1 + timedelta(days=9), rh1 + timedelta(days=9))
        if code == "FULL_TISHREI":
            return (rh1, rh1 + timedelta(days=21))
        if code == "ROSH_HASHANAH_KIPPUR_BRIDGE":
            return (rh1, rh1 + timedelta(days=9))
        if code in ("YOM_KIPPUR_SUKKOT_BRIDGE", "YOM_KIPPUR_SUKKOT"):
            return (rh1 + timedelta(days=9), rh1 + timedelta(days=21))
        if code == "SUKKOT":
            return (rh1 + timedelta(days=14), rh1 + timedelta(days=21))
        if code == "SUKKOT_I":
            return (rh1 + timedelta(days=14), rh1 + timedelta(days=14))
        if code == "CHOL_HAMOED_SUKKOT":
            return (rh1 + timedelta(days=15), rh1 + timedelta(days=20))
        if code == "SIMCHAT_TORAH":
            return (rh1 + timedelta(days=21), rh1 + timedelta(days=21))
        if code == "PESACH":
            return (pes1, pes1 + timedelta(days=6))
        if code == "PESACH_I":
            return (pes1, pes1)
        if code == "CHOL_HAMOED_PESACH":
            return (pes1 + timedelta(days=1), pes1 + timedelta(days=5))
        if code == "PESACH_VII":
            return (pes1 + timedelta(days=6), pes1 + timedelta(days=6))
        if code == "YOM_HAATZMAUT":
            return (atz, atz)
        if code == "SHAVUOT":
            return (pes1 + timedelta(days=50), pes1 + timedelta(days=50))
        return None

    @classmethod
    def compute_recommended_workplace_window(
        cls, start_date: date | str, end_date: date | str
    ) -> tuple[date, date]:
        """Compute the recommended bridge/trip window for a statutory workplace holiday span.

        Multi-day holidays (`>= 4` calendar days such as Pesach, Sukkot, Kippur–Sukkot bridge)
        use their core statutory span directly. Short 1–2 day holidays (`ROSH_HASHANAH`,
        `YOM_HAATZMAUT`, `SHAVUOT`) expand to the highest-efficiency 4–5 day weekend bridge
        containing the holiday.
        """
        s_date = cls._coerce_date(start_date)
        e_date = cls._coerce_date(end_date)
        core_days = (e_date - s_date).days + 1
        if core_days >= 4:
            return (s_date, e_date)

        best_key: Optional[tuple[float, float, int, int, int, int]] = None
        best_span: tuple[date, date] = (s_date, e_date)
        for length in (4, 5):
            for offset in range(length - core_days + 1):
                ws = s_date - timedelta(days=offset)
                we = ws + timedelta(days=length - 1)
                if we < e_date:
                    continue
                ev = cls.evaluate_trip_workdays_cost(ws, we)
                cost = float(ev["workplace_vacation_days_cost"])
                ratio = round(length / max(0.5, cost), 2)
                wknd_end_bonus = 1 if we.weekday() in (5, 6) else 0
                non_fri_start = 1 if ws.weekday() != 4 else 0
                key = (ratio, -cost, length, wknd_end_bonus, non_fri_start, -offset)
                if best_key is None or key > best_key:
                    best_key = key
                    best_span = (ws, we)
        return best_span

    @classmethod
    def get_upcoming_workplace_holidays_for_rolling_year(
        cls, as_of_date: Optional[date | str] = None
    ) -> list[dict[str, Any]]:
        """Return all 6 canonical statutory Israeli workplace holidays within the rolling 1-year window.

        Computed purely from `HebrewCalendarRuleProjector` (zero dependency on `moe_vacation_windows`),
        sorted chronologically by `(start_date, end_date, holiday_days, holiday_code)`.
        """
        ref_date = (
            datetime.now(UTC).date()
            if as_of_date is None
            else cls._coerce_date(as_of_date)
        )
        y1 = ref_date.year if ref_date.month >= 9 else ref_date.year - 1

        upcoming: list[dict[str, Any]] = []
        for canon_code, name_he, name_en in cls.CANONICAL_WORKPLACE_ROLLING_HOLIDAYS:
            chosen_entry: Optional[dict[str, Any]] = None
            for i in range(3):
                sy_y1 = y1 + i
                sy = f"{sy_y1}-{sy_y1 + 1}"
                heb_y = sy_y1 + 3761
                target_yr = (
                    sy_y1 if canon_code in cls._AUTUMN_WORKPLACE_CODES else (sy_y1 + 1)
                )
                span = cls.resolve_workplace_holiday_span(canon_code, target_yr)
                if span is None:
                    continue
                s_date, e_date = span
                if e_date >= ref_date:
                    holiday_days = max(1, (e_date - s_date).days + 1)
                    off_set, chol_set = cls.get_year_holiday_sets(heb_y)
                    official_holiday_days = sum(
                        1
                        for k in range(holiday_days)
                        if (s_date + timedelta(days=k)) in off_set
                    )
                    chol_hamoed_days = sum(
                        1
                        for k in range(holiday_days)
                        if (s_date + timedelta(days=k)) in chol_set
                    )
                    core_eval = cls.evaluate_trip_workdays_cost(s_date, e_date)
                    rec_s, rec_e = cls.compute_recommended_workplace_window(
                        s_date, e_date
                    )
                    rec_days = max(1, (rec_e - rec_s).days + 1)
                    rec_eval = cls.evaluate_trip_workdays_cost(rec_s, rec_e)
                    rec_cost = float(rec_eval["workplace_vacation_days_cost"])
                    rec_saved = round(max(0.0, rec_days - rec_cost), 1)
                    rec_ratio = round(rec_days / max(0.5, rec_cost), 2)

                    cost_str = f"{rec_cost:g}"
                    cost_unit_he = "יום חופש" if rec_cost == 1.0 else "ימי חופש"
                    cost_unit_en = "workday" if rec_cost == 1.0 else "workdays"
                    day_word_he = "יום" if rec_days == 1 else "ימים"
                    day_word_en = "day" if rec_days == 1 else "days"
                    label_he = (
                        f"{name_he} {s_date.year} "
                        f"({rec_days} {day_word_he} · {cost_str} {cost_unit_he})"
                    )
                    label_en = (
                        f"{name_en} {s_date.year} "
                        f"({rec_days} {day_word_en} · {cost_str} {cost_unit_en})"
                    )
                    chosen_entry = {
                        "holiday_code": canon_code,
                        "name_he": name_he,
                        "name_en": name_en,
                        "target_year": s_date.year,
                        "school_year": sy,
                        "start_date": s_date.isoformat(),
                        "end_date": e_date.isoformat(),
                        "holiday_days": holiday_days,
                        "recommended_window_start": rec_s.isoformat(),
                        "recommended_window_end": rec_e.isoformat(),
                        "recommended_trip_days": rec_days,
                        "recommended_workdays_cost": rec_cost,
                        "recommended_workdays_saved": rec_saved,
                        "recommended_efficiency_ratio": rec_ratio,
                        "workplace_workdays_cost": float(
                            core_eval["workplace_vacation_days_cost"]
                        ),
                        "official_holiday_days": official_holiday_days,
                        "chol_hamoed_days": chol_hamoed_days,
                        "is_ongoing": s_date <= ref_date <= e_date,
                        "calendar_mode": "WORKPLACE",
                        "label_he": label_he,
                        "label_en": label_en,
                    }
                    break
            if chosen_entry is not None:
                upcoming.append(chosen_entry)

        upcoming.sort(
            key=lambda item: (
                str(item["start_date"]),
                str(item["end_date"]),
                int(item["holiday_days"]),
                str(item["holiday_code"]),
            )
        )
        return upcoming

    @classmethod
    def compute_recommended_mega_bridge_window(
        cls,
        holiday_code: str,
        start_date: date | str,
        end_date: date | str,
        constituent_codes: tuple[str, ...] = (),
    ) -> tuple[date, date]:
        """Compute the optimal TLV-open flyable window covering all constituent holidays of a mega-bridge."""
        s_date = cls._coerce_date(start_date)
        e_date = cls._coerce_date(end_date)
        code = str(holiday_code or "").strip().upper()
        req_codes = set(constituent_codes)
        if not req_codes:
            if code == "FULL_TISHREI":
                req_codes = {"ROSH_HASHANAH", "YOM_KIPPUR", "SUKKOT"}
            elif code in ("YOM_KIPPUR_SUKKOT_BRIDGE", "YOM_KIPPUR_SUKKOT"):
                req_codes = {"YOM_KIPPUR", "SUKKOT"}
            elif code == "ROSH_HASHANAH_KIPPUR_BRIDGE":
                req_codes = {"ROSH_HASHANAH", "YOM_KIPPUR"}

        rec_min, rec_max = cls.get_recommended_nights_range(code)
        _, yk_day = cls.yom_kippur_closure_window(s_date.year)

        best_key: Optional[tuple[int, int, float, float, float, int]] = None
        best_span: Optional[tuple[date, date]] = None

        for ds in range(-3, 2):
            ws = s_date + timedelta(days=ds)
            if cls.is_tlv_yom_kippur_closure(ws) or ws.weekday() == 5:
                continue
            for de in range(-2, 4):
                we = e_date + timedelta(days=de)
                if we <= ws:
                    continue
                if cls.is_tlv_yom_kippur_closure(we) or we.weekday() == 5:
                    continue
                nights = (we - ws).days
                merged = cls.detect_merged_workplace_holidays(ws, we)
                found_codes = {m["code"] for m in merged}
                if req_codes and not req_codes.issubset(found_codes):
                    continue
                if "YOM_KIPPUR" in req_codes and not (ws < yk_day < we):
                    continue
                ev = cls.evaluate_trip_workdays_cost(ws, we)
                trip_days = nights + 1
                cost = float(ev["workplace_vacation_days_cost"])
                saved = round(max(0.0, trip_days - cost), 1)
                ratio = round(trip_days / max(0.5, cost), 2)
                in_rec = 1 if (rec_min <= nights <= rec_max) else 0
                pref_span = 1 if (ws <= s_date and we >= e_date - timedelta(days=1)) else 0
                key = (in_rec, pref_span, ratio, saved, -cost, nights)
                if best_key is None or key > best_key:
                    best_key = key
                    best_span = (ws, we)

        if best_span is not None:
            return best_span

        # Guaranteed TLV-open fallback
        ws_fb = s_date
        while cls.is_tlv_yom_kippur_closure(ws_fb) or ws_fb.weekday() == 5:
            ws_fb -= timedelta(days=1)
        we_fb = e_date
        while cls.is_tlv_yom_kippur_closure(we_fb) or we_fb.weekday() == 5:
            we_fb += timedelta(days=1)
        return (ws_fb, we_fb)

    @classmethod
    def get_workplace_holiday_catalog_for_rolling_year(
        cls, as_of_date: Optional[date | str] = None
    ) -> dict[str, Any]:
        """Return the Run 19 two-group workplace holiday catalog + Best-Year Maximizer option.

        - `best_year_option`: Featured `BEST_YEAR_MAXIMIZER` option scanning all rolling 12-month holidays/bridges.
        - `holiday_groups`:
          1. `INDIVIDUAL_HOLIDAYS` (5 deduplicated items: `PESACH`, `YOM_HAATZMAUT`, `SHAVUOT`, `ROSH_HASHANAH`, `SUKKOT`)
          2. `MEGA_BRIDGES` (3 genuine Tishrei bridges: `FULL_TISHREI`, `YOM_KIPPUR_SUKKOT_BRIDGE`, `ROSH_HASHANAH_KIPPUR_BRIDGE`)
        """
        ref_date = (
            datetime.now(UTC).date()
            if as_of_date is None
            else cls._coerce_date(as_of_date)
        )
        try:
            win_end = ref_date.replace(year=ref_date.year + 1)
        except ValueError:
            win_end = ref_date + timedelta(days=365)

        y1 = ref_date.year if ref_date.month >= 9 else ref_date.year - 1

        def _build_entry(
            canon_code: str,
            name_he: str,
            name_en: str,
            group_id: str,
            constituent_codes: tuple[str, ...] = (),
        ) -> Optional[dict[str, Any]]:
            for i in range(3):
                sy_y1 = y1 + i
                sy = f"{sy_y1}-{sy_y1 + 1}"
                heb_y = sy_y1 + 3761
                target_yr = (
                    sy_y1 if canon_code in cls._AUTUMN_WORKPLACE_CODES else (sy_y1 + 1)
                )
                span = cls.resolve_workplace_holiday_span(canon_code, target_yr)
                if span is None:
                    continue
                s_date, e_date = span
                if e_date >= ref_date:
                    holiday_days = max(1, (e_date - s_date).days + 1)
                    off_set, chol_set = cls.get_year_holiday_sets(heb_y)
                    official_holiday_days = sum(
                        1
                        for k in range(holiday_days)
                        if (s_date + timedelta(days=k)) in off_set
                    )
                    chol_hamoed_days = sum(
                        1
                        for k in range(holiday_days)
                        if (s_date + timedelta(days=k)) in chol_set
                    )
                    core_eval = cls.evaluate_trip_workdays_cost(s_date, e_date)
                    is_mega = group_id == "MEGA_BRIDGES"
                    if is_mega:
                        rec_s, rec_e = cls.compute_recommended_mega_bridge_window(
                            canon_code, s_date, e_date, constituent_codes
                        )
                    else:
                        rec_s, rec_e = cls.compute_recommended_workplace_window(
                            s_date, e_date
                        )
                        while cls.is_tlv_yom_kippur_closure(rec_s):
                            rec_s -= timedelta(days=1)
                        while cls.is_tlv_yom_kippur_closure(rec_e):
                            rec_e += timedelta(days=1)
                    rec_days = max(1, (rec_e - rec_s).days + 1)
                    rec_min_n, rec_max_n = cls.get_recommended_nights_range(canon_code)
                    rec_eval = cls.evaluate_trip_workdays_cost(rec_s, rec_e)
                    rec_cost = float(rec_eval["workplace_vacation_days_cost"])
                    rec_saved = round(max(0.0, rec_days - rec_cost), 1)
                    rec_ratio = round(rec_days / max(0.5, rec_cost), 2)
                    merged_list = cls.detect_merged_workplace_holidays(rec_s, rec_e)
                    includes_yk_abroad = any(
                        bool(m.get("is_stay_abroad_holiday")) for m in merged_list
                    )

                    cost_str = f"{rec_cost:g}"
                    cost_unit_he = "יום חופש" if rec_cost == 1.0 else "ימי חופש"
                    cost_unit_en = "workday" if rec_cost == 1.0 else "workdays"
                    day_word_he = "יום" if rec_days == 1 else "ימים"
                    day_word_en = "day" if rec_days == 1 else "days"
                    label_he = (
                        f"{name_he} {s_date.year} "
                        f"({rec_days} {day_word_he} · {cost_str} {cost_unit_he})"
                    )
                    label_en = (
                        f"{name_en} {s_date.year} "
                        f"({rec_days} {day_word_en} · {cost_str} {cost_unit_en})"
                    )
                    return {
                        "id": f"workplace_{heb_y}_{canon_code}",
                        "holiday_code": canon_code,
                        "holiday_group": group_id,
                        "is_mega_vacation": is_mega,
                        "name_he": name_he,
                        "name_en": name_en,
                        "target_year": s_date.year,
                        "school_year": sy,
                        "start_date": s_date.isoformat(),
                        "end_date": e_date.isoformat(),
                        "holiday_days": holiday_days,
                        "recommended_window_start": rec_s.isoformat(),
                        "recommended_window_end": rec_e.isoformat(),
                        "recommended_trip_days": rec_days,
                        "recommended_min_nights": rec_min_n,
                        "recommended_max_nights": rec_max_n,
                        "recommended_workdays_cost": rec_cost,
                        "recommended_workdays_saved": rec_saved,
                        "recommended_efficiency_ratio": rec_ratio,
                        "workplace_workdays_cost": float(
                            core_eval["workplace_vacation_days_cost"]
                        ),
                        "official_holiday_days": official_holiday_days,
                        "chol_hamoed_days": chol_hamoed_days,
                        "merged_holidays": merged_list,
                        "includes_yom_kippur_abroad": includes_yk_abroad,
                        "is_ongoing": s_date <= ref_date <= e_date,
                        "calendar_mode": "WORKPLACE",
                        "label_he": label_he,
                        "label_en": label_en,
                    }
            return None

        individual_items: list[dict[str, Any]] = []
        for canon_code, name_he, name_en in cls.WORKPLACE_INDIVIDUAL_ROLLING_HOLIDAYS:
            entry = _build_entry(canon_code, name_he, name_en, "INDIVIDUAL_HOLIDAYS")
            if entry is not None:
                individual_items.append(entry)
        individual_items.sort(
            key=lambda item: (
                str(item["start_date"]),
                str(item["end_date"]),
                str(item["holiday_code"]),
            )
        )

        mega_sortable: list[tuple[int, int, dict[str, Any]]] = []
        for (
            canon_code,
            name_he,
            name_en,
            constituents,
            prio,
        ) in cls.WORKPLACE_MEGA_BRIDGE_HOLIDAYS:
            entry = _build_entry(
                canon_code, name_he, name_en, "MEGA_BRIDGES", constituents
            )
            if entry is not None:
                mega_sortable.append((int(entry["target_year"]), prio, entry))
        mega_sortable.sort(key=lambda tup: (tup[0], tup[1]))
        mega_items = [tup[2] for tup in mega_sortable]

        rec_min_by, rec_max_by = cls.get_recommended_nights_range("BEST_YEAR_MAXIMIZER")
        best_year_option: dict[str, Any] = {
            "id": "workplace_best_year_maximizer",
            "holiday_code": "BEST_YEAR_MAXIMIZER",
            "holiday_group": "BEST_YEAR",
            "is_mega_vacation": False,
            "is_best_year_maximizer": True,
            "name_he": "✨ המיקסום הטוב ביותר בשנה הקרובה",
            "name_en": "✨ Best Maximization Next Year",
            "label_he": "✨ המיקסום הטוב ביותר בשנה הקרובה",
            "label_en": "✨ Best Maximization Next Year",
            "subtitle_he": "סורק את כל חגי המשק ואיחודי החגים בשנה הקרובה",
            "subtitle_en": "Scans all Israeli workplace holidays & bridges over the next 12 months",
            "start_date": ref_date.isoformat(),
            "end_date": win_end.isoformat(),
            "target_year": win_end.year,
            "recommended_window_start": ref_date.isoformat(),
            "recommended_window_end": win_end.isoformat(),
            "recommended_min_nights": rec_min_by,
            "recommended_max_nights": rec_max_by,
            "merged_holidays": [],
            "includes_yom_kippur_abroad": False,
            "calendar_mode": "WORKPLACE",
        }

        holiday_groups: list[dict[str, Any]] = [
            {
                "group_id": "INDIVIDUAL_HOLIDAYS",
                "label_he": "חגי משק בודדים",
                "label_en": "Individual Market Holidays",
                "items": individual_items,
            },
            {
                "group_id": "MEGA_BRIDGES",
                "label_he": "מגה-חופשות ואיחודי חגים",
                "label_en": "Mega-Vacations & Holiday Bridges",
                "items": mega_items,
            },
        ]
        catalog_items = [*individual_items, *mega_items]
        return {
            "best_year_option": best_year_option,
            "holiday_groups": holiday_groups,
            "catalog_count": len(catalog_items),
            "catalog_items": catalog_items,
        }

    @classmethod
    def resolve_upcoming_workplace_holiday_occurrence(
        cls,
        holiday_code: str,
        as_of_date: Optional[date | str] = None,
    ) -> Optional[dict[str, Any]]:
        """Resolve a statutory workplace holiday code (including mega-bridges) to its upcoming occurrence."""
        norm_code = str(holiday_code or "").strip().upper()
        if not norm_code:
            return None
        lookup_code = (
            "YOM_KIPPUR_SUKKOT_BRIDGE"
            if norm_code == "YOM_KIPPUR_SUKKOT"
            else norm_code
        )
        for item in cls.get_upcoming_workplace_holidays_for_rolling_year(
            as_of_date=as_of_date
        ):
            if item["holiday_code"] == lookup_code:
                return {**item, "holiday_code": norm_code}
        catalog = cls.get_workplace_holiday_catalog_for_rolling_year(
            as_of_date=as_of_date
        )
        for item in catalog.get("catalog_items") or []:
            if item["holiday_code"] == lookup_code:
                return {**item, "holiday_code": norm_code}
        return None


class MoECalendarAutoUpdaterService:
    """Annual MoE Calendar Auto-Updater (`Layer 1` Bundled/Remote + `Layer 2` Hebrew Rule Projector)."""

    BUNDLED_FILES: dict[str, Path] = {
        "2025-2026": CALENDARS_DIR / "moe_5786_2025_2026.json",
        "2026-2027": CALENDARS_DIR / "moe_5787_2026_2027.json",
        "2027-2028": CALENDARS_DIR / "moe_5788_2027_2028.json",
    }

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def load_or_project_calendar_doc(
        self, school_year: str, force_remote_check: bool = False
    ) -> dict[str, Any]:
        norm_year = normalize_school_year(school_year)
        bundled_path = self.BUNDLED_FILES.get(norm_year)
        if bundled_path and bundled_path.exists():
            with bundled_path.open("r", encoding="utf-8") as fh:
                doc = json.load(fh)
            if force_remote_check and norm_year in ("2025-2026", "2026-2027"):
                doc["calendar_sync_source"] = "OFFICIAL_MOE_CIRCULAR"
            return doc
        return HebrewCalendarRuleProjector.project_school_year_calendar_doc(norm_year)

    def sync_school_year(
        self, school_year: str, force_remote_check: bool = False
    ) -> MoECalendarSyncStatus:
        """Sync or deterministically project `school_year` into `moe_vacation_windows`."""
        norm_year = normalize_school_year(school_year)
        doc = self.load_or_project_calendar_doc(
            norm_year, force_remote_check=force_remote_check
        )
        windows = expand_calendar_json_to_windows(doc)
        try:
            synced_count = self.repository.upsert_moe_windows(windows)
        except Exception:
            synced_count = len(windows)
        now_str = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return MoECalendarSyncStatus(
            school_year=norm_year,
            school_year_hebrew=str(doc.get("school_year_hebrew") or ""),
            calendar_sync_source=str(
                doc.get("calendar_sync_source") or "HEBREW_RULE_PROJECTED"
            ),
            windows_synced_count=synced_count,
            last_synced_at=now_str,
            windows=windows,
        )


class MoECalendarService:
    """Evaluates daily multi-child MoE schedules across all 8 frameworks."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.auto_updater = MoECalendarAutoUpdaterService(repository)
        self._settings = get_settings()
        self._penalties = self._settings["daily_state_penalties"]
        self._windows_cache: dict[str, list[MoEVacationWindow]] = {}

    def infer_school_year_for_date(self, target_date: date) -> str:
        """Map any calendar date to its Israeli school year `'YYYY-YYYY'` (Sept 1 - Aug 31)."""
        if target_date.month >= 9:
            return f"{target_date.year}-{target_date.year + 1}"
        return f"{target_date.year - 1}-{target_date.year}"

    def get_calendar_windows(
        self, school_year: str, framework_type: Optional[str] = None
    ) -> list[MoEVacationWindow]:
        """Return `MoEVacationWindow` rows for `school_year`, auto-projecting if not yet in DB."""
        norm_year = normalize_school_year(school_year)
        if norm_year not in self._windows_cache:
            rows = self.repository.get_moe_windows(norm_year)
            if not rows:
                sync_status = self.auto_updater.sync_school_year(norm_year)
                rows = sync_status.windows
            self._windows_cache[norm_year] = rows

        all_rows = self._windows_cache[norm_year]
        if framework_type is None:
            return list(all_rows)
        fw_val = (
            framework_type.value
            if isinstance(framework_type, MoEFrameworkType)
            else str(framework_type)
        )
        return [
            w
            for w in all_rows
            if (
                w.framework_type.value
                if isinstance(w.framework_type, MoEFrameworkType)
                else str(w.framework_type)
            )
            == fw_val
        ]

    CANONICAL_ROLLING_HOLIDAYS: tuple[tuple[str, str, str], ...] = (
        ("ROSH_HASHANAH", "ראש השנה", "Rosh Hashanah"),
        ("YOM_KIPPUR_SUKKOT_BRIDGE", "גשר יום כיפור–סוכות", "Yom Kippur–Sukkot Bridge"),
        ("SUKKOT", "חופשת סוכות", "Sukkot Break"),
        ("HANUKKAH", "חופשת חנוכה", "Hanukkah Break"),
        ("PURIM", "חופשת פורים", "Purim Break"),
        ("PESACH", "חופשת פסח", "Passover Break"),
        ("YOM_HAATZMAUT", "יום העצמאות", "Independence Day"),
        ("SHAVUOT", "חופשת שבועות", "Shavuot Break"),
        ("SUMMER_JUNE_20_30", "החופש הגדול — 20–30 ביוני", "Summer Break — June 20–30"),
        ("SUMMER_JULY", "החופש הגדול — יולי", "Summer Break — July"),
        ("SUMMER_AUGUST", "החופש הגדול — אוגוסט", "Summer Break — August"),
    )

    def get_calendar_metadata(self, school_year: str) -> dict[str, Any]:
        norm_year = normalize_school_year(school_year)
        return self.auto_updater.load_or_project_calendar_doc(norm_year)

    def get_workplace_holidays_for_school_year(
        self, school_year: str
    ) -> list[dict[str, Any]]:
        """Return the 10 chronological statutory Israeli workplace holiday/Chol HaMoed periods."""
        return IsraeliWorkplaceCalendarService.get_workplace_holidays_for_school_year(
            school_year
        )

    def evaluate_trip_workdays_cost(
        self, start_date: date | str, end_date: date | str
    ) -> dict[str, Any]:
        """Evaluate inclusive `[start_date, end_date]` per-person Israeli workplace vacation-days cost."""
        return IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost(
            start_date, end_date
        )

    def get_upcoming_workplace_holidays_for_rolling_year(
        self, as_of_date: Optional[date | str] = None
    ) -> list[dict[str, Any]]:
        """Return all 6 canonical statutory Israeli workplace holidays within the rolling 1-year window."""
        return IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
            as_of_date=as_of_date
        )

    def get_workplace_holiday_catalog_for_rolling_year(
        self, as_of_date: Optional[date | str] = None
    ) -> dict[str, Any]:
        """Return the Run 19 two-group workplace holiday catalog + Best-Year Maximizer option."""
        return IsraeliWorkplaceCalendarService.get_workplace_holiday_catalog_for_rolling_year(
            as_of_date=as_of_date
        )

    def resolve_workplace_holiday_span(
        self, holiday_code: str, target_year: int
    ) -> Optional[tuple[date, date]]:
        """Resolve a statutory Israeli workplace holiday code & target year to `(start_date, end_date)`."""
        return IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span(
            holiday_code=holiday_code, target_year=target_year
        )

    def resolve_upcoming_workplace_holiday_occurrence(
        self,
        holiday_code: str,
        as_of_date: Optional[date | str] = None,
    ) -> Optional[dict[str, Any]]:
        """Resolve a statutory workplace holiday code to its upcoming rolling-year occurrence."""
        return IsraeliWorkplaceCalendarService.resolve_upcoming_workplace_holiday_occurrence(
            holiday_code=holiday_code, as_of_date=as_of_date
        )

    def get_upcoming_holidays_for_rolling_year(
        self,
        as_of_date: Optional[date | str] = None,
        profile: Optional[FamilyProfile] = None,
    ) -> list[dict[str, Any]]:
        """Return all 11 canonical holidays within the rolling 1-year window from `as_of_date`.

        Evaluates `[cur_sy, next_sy_1, next_sy_2]`, picking for each holiday code the earliest
        occurrence whose `end_date >= ref_date`, sorted chronologically by `(start_date, end_date, holiday_days)`.
        """
        if as_of_date is None:
            ref_date = datetime.now(UTC).date()
        elif isinstance(as_of_date, date):
            ref_date = as_of_date
        else:
            ref_date = date.fromisoformat(str(as_of_date).strip()[:10])

        cur_sy = self.infer_school_year_for_date(ref_date)
        y1 = int(cur_sy.split("-")[0])
        school_years = [f"{y1 + i}-{y1 + i + 1}" for i in range(3)]

        child_fws = {
            (
                c.framework_type.value
                if isinstance(c.framework_type, MoEFrameworkType)
                else str(c.framework_type)
            )
            for c in (profile.children if profile is not None else [])
            if c.framework_type is not None
        }

        windows_by_sy: dict[str, list[MoEVacationWindow]] = {
            sy: self.get_calendar_windows(sy) for sy in school_years
        }

        upcoming: list[dict[str, Any]] = []
        for canon_code, name_he, name_en in self.CANONICAL_ROLLING_HOLIDAYS:
            src_code = (
                "YOM_KIPPUR_SUKKOT"
                if canon_code in ("YOM_KIPPUR_SUKKOT_BRIDGE", "SUKKOT")
                else canon_code
            )
            chosen_entry: Optional[dict[str, Any]] = None
            for sy in school_years:
                sy_wins = windows_by_sy[sy]
                h_wins = [w for w in sy_wins if w.holiday_code.upper() == src_code]
                if not h_wins and canon_code == "SUKKOT":
                    h_wins = [w for w in sy_wins if w.holiday_code.upper() == "SUKKOT"]
                if not h_wins:
                    continue

                relevant_wins = (
                    [
                        w
                        for w in h_wins
                        if (
                            w.framework_type.value
                            if isinstance(w.framework_type, MoEFrameworkType)
                            else str(w.framework_type)
                        )
                        in child_fws
                    ]
                    if child_fws
                    else h_wins
                )
                if not relevant_wins:
                    relevant_wins = h_wins

                if canon_code == "SUMMER_AUGUST" and child_fws:
                    s_date = max(w.start_date for w in relevant_wins)
                else:
                    s_date = min(w.start_date for w in relevant_wins)
                e_date = max(w.end_date for w in relevant_wins)

                if canon_code == "SUKKOT" and src_code == "YOM_KIPPUR_SUKKOT":
                    s_date = min(e_date, s_date + timedelta(days=5))

                if e_date >= ref_date:
                    holiday_days = max(1, (e_date - s_date).days + 1)
                    target_year = s_date.year
                    day_word_he = "יום" if holiday_days == 1 else "ימים"
                    day_word_en = "day" if holiday_days == 1 else "days"
                    chosen_entry = {
                        "holiday_code": canon_code,
                        "name_he": name_he,
                        "name_en": name_en,
                        "target_year": target_year,
                        "school_year": sy,
                        "start_date": s_date.isoformat(),
                        "end_date": e_date.isoformat(),
                        "holiday_days": holiday_days,
                        "is_ongoing": s_date <= ref_date <= e_date,
                        "label_he": f"{name_he} {target_year} ({holiday_days} {day_word_he})",
                        "label_en": f"{name_en} {target_year} ({holiday_days} {day_word_en})",
                    }
                    break

            if chosen_entry is not None:
                upcoming.append(chosen_entry)

        upcoming.sort(
            key=lambda item: (
                str(item["start_date"]),
                str(item["end_date"]),
                int(item["holiday_days"]),
                str(item["holiday_code"]),
            )
        )
        return upcoming

    def resolve_upcoming_holiday_occurrence(
        self,
        holiday_code: str,
        as_of_date: Optional[date | str] = None,
        profile: Optional[FamilyProfile] = None,
    ) -> dict[str, Any]:
        """Resolve a single holiday code to its upcoming rolling-year occurrence metadata."""
        norm_code = str(holiday_code or "PESACH").strip().upper()
        lookup_code = (
            "YOM_KIPPUR_SUKKOT_BRIDGE"
            if norm_code == "YOM_KIPPUR_SUKKOT"
            else norm_code
        )
        items = self.get_upcoming_holidays_for_rolling_year(
            as_of_date=as_of_date, profile=profile
        )
        for item in items:
            if item["holiday_code"] == lookup_code:
                return {**item, "holiday_code": norm_code}
        if items:
            return items[0]
        ref_d = (
            as_of_date
            if isinstance(as_of_date, date)
            else (
                date.fromisoformat(str(as_of_date).strip()[:10])
                if as_of_date
                else datetime.now(UTC).date()
            )
        )
        return {
            "holiday_code": norm_code,
            "target_year": ref_d.year,
            "school_year": self.infer_school_year_for_date(ref_d),
            "start_date": ref_d.isoformat(),
            "end_date": ref_d.isoformat(),
            "holiday_days": 7,
        }

    def is_tlv_airport_closed(
        self, target_date: date, departure_or_arrival_time: Optional[str] = None
    ) -> bool:
        """Check if Ben Gurion Airport (`TLV`) is closed for Yom Kippur on `target_date`."""
        return IsraeliWorkplaceCalendarService.is_tlv_yom_kippur_closure(
            target_date, departure_or_arrival_time
        )

    def get_child_day_status(
        self, child: ChildFramework, target_date: date
    ) -> ChildDayStatus:
        """Evaluate daily state $S_c(d)$ and penalty $\\psi(S_c(d))$ for `child` on `target_date`."""
        # 1. Bagrut exam blackout check
        if target_date in child.bagrut_blackout_dates:
            return ChildDayStatus(
                calendar_date=target_date,
                state_code="EXAM_BLACKOUT",
                psi_penalty=float(self._penalties["EXAM_BLACKOUT"]),
                label_he="בחינת בגרות (חסום)",
                holiday_code=None,
            )

        wd = target_date.weekday()  # Mon=0 .. Fri=4, Sat=5, Sun=6

        # 2. Saturday is always off across all Israeli frameworks
        if wd == 5:
            return ChildDayStatus(
                calendar_date=target_date,
                state_code="VACATION",
                psi_penalty=0.0,
                label_he="שבת",
                holiday_code=None,
            )

        # 3. Mode 1 optional framework: if `framework_type` is None, no school penalty
        if child.framework_type is None:
            return ChildDayStatus(
                calendar_date=target_date,
                state_code="VACATION",
                psi_penalty=0.0,
                label_he="ללא שיוך מסגרת חינוכית",
                holiday_code=None,
            )

        fw = (
            child.framework_type
            if isinstance(child.framework_type, MoEFrameworkType)
            else MoEFrameworkType(str(child.framework_type))
        )
        school_year = self.infer_school_year_for_date(target_date)
        windows = self.get_calendar_windows(school_year, fw.value)

        # 4. Special handling for June 20 vs June 30 split (`SUMMER_JUNE_20_30`)
        if target_date.month == 6 and 18 <= target_date.day <= 30:
            june_20 = date(target_date.year, 6, 20)
            if fw in (
                MoEFrameworkType.MIDDLE_SCHOOL_7_9,
                MoEFrameworkType.HIGH_SCHOOL_10_12,
            ):
                if june_20.weekday() == 5:  # Saturday (e.g. 2026-06-20)
                    last_school_day = (
                        date(target_date.year, 6, 18)
                        if child.school_week_days == 5
                        else date(target_date.year, 6, 19)
                    )
                elif june_20.weekday() == 4:  # Friday
                    last_school_day = (
                        date(target_date.year, 6, 19)
                        if child.school_week_days == 5
                        else date(target_date.year, 6, 20)
                    )
                else:
                    last_school_day = june_20

                if target_date > last_school_day:
                    return ChildDayStatus(
                        calendar_date=target_date,
                        state_code="VACATION",
                        psi_penalty=0.0,
                        label_he="החופש הגדול (על-יסודי)",
                        holiday_code="SUMMER_JUNE_20_30",
                    )
            elif fw in (
                MoEFrameworkType.MUNICIPAL_GAN,
                MoEFrameworkType.ELEMENTARY_1_3,
                MoEFrameworkType.ELEMENTARY_4_6,
            ):
                if target_date >= date(target_date.year, 6, 21):
                    if wd == 4:
                        if child.school_week_days == 5:
                            return ChildDayStatus(
                                calendar_date=target_date,
                                state_code="VACATION",
                                psi_penalty=0.0,
                                label_he="יום שישי חופשי (שבוע 5 ימים)",
                                holiday_code=None,
                            )
                        return ChildDayStatus(
                            calendar_date=target_date,
                            state_code="SCHOOL_FRIDAY",
                            psi_penalty=float(self._penalties["SCHOOL_FRIDAY"]),
                            label_he="יום שישי קצר",
                            holiday_code=None,
                        )
                    return ChildDayStatus(
                        calendar_date=target_date,
                        state_code="SCHOOL_END_OF_YEAR_WANING",
                        psi_penalty=float(self._penalties["SCHOOL_END_OF_YEAR_WANING"]),
                        label_he="ימי לימוד דועכים בסוף שנה (יוני 21–30)",
                        holiday_code=None,
                    )

        # 5. Check active MoE vacation windows for this child's framework
        for win in windows:
            if win.holiday_code == "SUMMER_JUNE_20_30":
                continue
            if win.start_date <= target_date <= win.end_date:
                # Check if Nitzanim camp covers this date
                ext_mode = (
                    child.holiday_extension_mode
                    if isinstance(child.holiday_extension_mode, HolidayExtensionMode)
                    else HolidayExtensionMode(str(child.holiday_extension_mode))
                )
                nitz_applies = False
                if (
                    win.is_covered_by_nitzanim
                    and win.nitzanim_start_date is not None
                    and win.nitzanim_end_date is not None
                    and win.nitzanim_start_date <= target_date <= win.nitzanim_end_date
                    and wd in (6, 0, 1, 2, 3)  # Sun-Thu only
                ):
                    if ext_mode == HolidayExtensionMode.NITZANIM_FULL_WITH_JULY:
                        nitz_applies = True
                    elif (
                        ext_mode == HolidayExtensionMode.NITZANIM_CHAGIM_ONLY
                        and win.holiday_code in ("HANUKKAH", "PESACH")
                    ):
                        nitz_applies = True

                if nitz_applies:
                    psi = (
                        float(self._penalties["CAMP_OPTIONAL_AS_VACATION"])
                        if child.treat_camp_as_vacation
                        else float(self._penalties["CAMP_OPTIONAL_AS_CHILDCARE"])
                    )
                    return ChildDayStatus(
                        calendar_date=target_date,
                        state_code="CAMP_OPTIONAL",
                        psi_penalty=psi,
                        label_he=f"ניצנים / בית הספר של החגים ({win.holiday_name_he})",
                        holiday_code=win.holiday_code,
                    )

                return ChildDayStatus(
                    calendar_date=target_date,
                    state_code="VACATION",
                    psi_penalty=0.0,
                    label_he=win.holiday_name_he,
                    holiday_code=win.holiday_code,
                )

        # 6. Regular Friday handling (5-day vs 6-day school week)
        if wd == 4:
            if child.school_week_days == 5:
                return ChildDayStatus(
                    calendar_date=target_date,
                    state_code="VACATION",
                    psi_penalty=0.0,
                    label_he="יום שישי חופשי (שבוע 5 ימים)",
                    holiday_code=None,
                )
            return ChildDayStatus(
                calendar_date=target_date,
                state_code="SCHOOL_FRIDAY",
                psi_penalty=float(self._penalties["SCHOOL_FRIDAY"]),
                label_he="יום לימודים קצר (יום שישי)",
                holiday_code=None,
            )

        # 7. Standard Sun-Thu instructional day
        return ChildDayStatus(
            calendar_date=target_date,
            state_code="SCHOOL_REGULAR",
            psi_penalty=float(self._penalties["SCHOOL_REGULAR"]),
            label_he="יום לימודים רגיל",
            holiday_code=None,
        )

    def get_daily_status_matrix(
        self, profile: FamilyProfile, start_date: date, end_date: date
    ) -> DailyFamilyCalendarMatrix:
        """Build the multi-child daily status matrix and $\\mathcal{I}, \\mathcal{I}_{\\text{camp}}, \\mathcal{U}$ sets."""
        if end_date < start_date:
            raise ValueError("end_date must be >= start_date")

        school_year = self.infer_school_year_for_date(start_date)
        total_days = (end_date - start_date).days + 1
        dates = [start_date + timedelta(days=i) for i in range(total_days)]

        tlv_airport_closed_by_date: dict[str, bool] = {}
        holiday_codes_by_date: dict[str, list[str]] = {}
        child_status_by_id: dict[str, dict[str, ChildDayStatus]] = {
            c.id: {} for c in profile.children
        }

        strict_intersection_dates: list[date] = []
        camp_adjusted_intersection_dates: list[date] = []
        framework_delta_union_dates: list[date] = []

        for d in dates:
            d_iso = d.isoformat()
            tlv_airport_closed_by_date[d_iso] = self.is_tlv_airport_closed(d)

            day_holidays: list[str] = []
            child_states: list[str] = []
            for child in profile.children:
                c_status = self.get_child_day_status(child, d)
                child_status_by_id[child.id][d_iso] = c_status
                child_states.append(c_status.state_code)
                if c_status.holiday_code and c_status.holiday_code not in day_holidays:
                    day_holidays.append(c_status.holiday_code)

            holiday_codes_by_date[d_iso] = day_holidays

            if not child_states:
                strict_intersection_dates.append(d)
                camp_adjusted_intersection_dates.append(d)
                framework_delta_union_dates.append(d)
            else:
                if all(s == "VACATION" for s in child_states):
                    strict_intersection_dates.append(d)
                if all(s in ("VACATION", "CAMP_OPTIONAL") for s in child_states):
                    camp_adjusted_intersection_dates.append(d)
                if any(s in ("VACATION", "CAMP_OPTIONAL") for s in child_states):
                    framework_delta_union_dates.append(d)

        return DailyFamilyCalendarMatrix(
            school_year=school_year,
            start_date=start_date,
            end_date=end_date,
            dates=dates,
            tlv_airport_closed_by_date=tlv_airport_closed_by_date,
            holiday_codes_by_date=holiday_codes_by_date,
            child_status_by_id=child_status_by_id,
            strict_intersection_dates=strict_intersection_dates,
            camp_adjusted_intersection_dates=camp_adjusted_intersection_dates,
            framework_delta_union_dates=framework_delta_union_dates,
        )

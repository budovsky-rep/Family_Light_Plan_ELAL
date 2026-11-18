"""Pre-seeded 2025-2028 dataset for family_vacation_planner.

Provides:
1. Default household profile (`משפחת בודובסקי`) with 2 adults, 3 children
   (`נועה`, `עידו`, `מאיה`), and multi-club `passenger_loyalty_wallets` across all
   10 `LoyaltyProgramCode` programs.
2. Bundled MoE vacation windows loader (`תשפ"ו 2025-2026`, `תשפ"ז 2026-2027`,
   `תשפ"ח 2027-2028`) across all 8 `MoEFrameworkType` frameworks.
3. Rich pre-populated El Al `rbddataclients` Classic Award inventory (`2025-2028`)
   across Zones A-E (`FCO`, `MXP`, `ATH`, `LCA`, `RHO`, `VIE`, `BUD`, `PRG`, `BER`,
   `CDG`, `LHR`, `LTN`, `AMS`, `MAD`, `BCN`, `BKK`, `NRT`, `JFK`, `EWR`, `MIA`, etc.),
   including canonical benchmark flights (`LY381`/`LY384` Rome, `LY541`/`LY544` Athens,
   `LY395`/`LY398` Madrid, `LY387`/`LY388` Milan Open-Jaw, `LHR` UK APD vs `LTN`).
4. Multi-carrier commercial flight catalog supporting `EL_AL_ONLY` and `ALL_AIRLINES`.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backend.app.config_manager.settings import PROJECT_ROOT
from backend.app.schemas.domain import (
    ChildFramework,
    ElAlBonusAvailability,
    FamilyProfile,
    HolidayExtensionMode,
    LoyaltyProgramCode,
    MoEFrameworkType,
    MoEVacationWindow,
    PassengerLoyaltyWallet,
)

CALENDARS_DIR = PROJECT_ROOT / "backend" / "calendars"

YOM_KIPPUR_CLOSED_DATES: set[date] = {
    date(2025, 10, 1),
    date(2025, 10, 2),
    date(2026, 9, 20),
    date(2026, 9, 21),
    date(2027, 10, 10),
    date(2027, 10, 11),
    date(2028, 9, 29),
    date(2028, 9, 30),
}

DESTINATION_CATALOG: dict[str, dict[str, Any]] = {
    "ATH": {
        "city_he": "אתונה",
        "city_en": "Athens",
        "award_zone": "ZONE_A",
        "outbound_flight": "LY541",
        "inbound_flight": "LY544",
        "operating_carrier": "LY",
        "aircraft_type": "788",
        "dep_time_out": "08:00",
        "arr_time_out": "10:15",
        "dep_time_in": "20:30",
        "arr_time_in": "22:35",
        "duration_minutes": 135,
        "economy_points": 8500,
        "premium_points": 18000,
        "business_points": 16000,
        "outbound_taxes_usd": 38.75,
        "inbound_taxes_usd": 38.75,
        "rt_cash_per_pax_usd": 420.0,
        "supplemental_single_pax_cash_usd": 300.0,
        "five_pax_cash_benchmark_usd": 2100.0,
        "alt_carriers": [("A3", "A3929", "A3928", 340.0), ("W6", "W64501", "W64502", 195.0), ("6H", "6H521", "6H522", 290.0)],
    },
    "LCA": {
        "city_he": "לרנקה",
        "city_en": "Larnaca",
        "award_zone": "ZONE_A",
        "outbound_flight": "LY411",
        "inbound_flight": "LY412",
        "operating_carrier": "LY",
        "aircraft_type": "738",
        "dep_time_out": "07:30",
        "arr_time_out": "08:35",
        "dep_time_in": "21:15",
        "arr_time_in": "22:15",
        "duration_minutes": 65,
        "economy_points": 7500,
        "premium_points": 0,
        "business_points": 25000,
        "outbound_taxes_usd": 38.00,
        "inbound_taxes_usd": 38.00,
        "rt_cash_per_pax_usd": 260.0,
        "supplemental_single_pax_cash_usd": 220.0,
        "five_pax_cash_benchmark_usd": 1300.0,
        "alt_carriers": [("IZ", "IZ211", "IZ212", 210.0), ("6H", "6H881", "6H882", 215.0), ("W6", "W64551", "W64552", 140.0)],
    },
    "RHO": {
        "city_he": "רודוס",
        "city_en": "Rhodes",
        "award_zone": "ZONE_A",
        "outbound_flight": "LY5121",
        "inbound_flight": "LY5122",
        "operating_carrier": "2U",
        "aircraft_type": "738",
        "dep_time_out": "09:10",
        "arr_time_out": "10:45",
        "dep_time_in": "19:40",
        "arr_time_in": "21:10",
        "duration_minutes": 95,
        "economy_points": 8500,
        "premium_points": 0,
        "business_points": 0,
        "outbound_taxes_usd": 40.00,
        "inbound_taxes_usd": 40.00,
        "rt_cash_per_pax_usd": 310.0,
        "supplemental_single_pax_cash_usd": 250.0,
        "five_pax_cash_benchmark_usd": 1550.0,
        "alt_carriers": [("A3", "A3541", "A3542", 275.0), ("IZ", "IZ261", "IZ262", 245.0)],
    },
    "PFO": {
        "city_he": "פאפוס",
        "city_en": "Paphos",
        "award_zone": "ZONE_A",
        "outbound_flight": "LY5131",
        "inbound_flight": "LY5132",
        "operating_carrier": "2U",
        "aircraft_type": "738",
        "dep_time_out": "08:20",
        "arr_time_out": "09:30",
        "dep_time_in": "20:00",
        "arr_time_in": "21:05",
        "duration_minutes": 70,
        "economy_points": 7500,
        "premium_points": 0,
        "business_points": 0,
        "outbound_taxes_usd": 36.00,
        "inbound_taxes_usd": 36.00,
        "rt_cash_per_pax_usd": 250.0,
        "supplemental_single_pax_cash_usd": 210.0,
        "five_pax_cash_benchmark_usd": 1250.0,
        "alt_carriers": [("FR", "FR6511", "FR6512", 135.0)],
    },
    "TBS": {
        "city_he": "טביליסי",
        "city_en": "Tbilisi",
        "award_zone": "ZONE_A",
        "outbound_flight": "LY5101",
        "inbound_flight": "LY5102",
        "operating_carrier": "2U",
        "aircraft_type": "738",
        "dep_time_out": "07:00",
        "arr_time_out": "10:35",
        "dep_time_in": "12:00",
        "arr_time_in": "13:45",
        "duration_minutes": 155,
        "economy_points": 11000,
        "premium_points": 0,
        "business_points": 28000,
        "outbound_taxes_usd": 42.00,
        "inbound_taxes_usd": 42.00,
        "rt_cash_per_pax_usd": 360.0,
        "supplemental_single_pax_cash_usd": 290.0,
        "five_pax_cash_benchmark_usd": 1800.0,
        "alt_carriers": [("6H", "6H891", "6H892", 310.0)],
    },
    "FCO": {
        "city_he": "רומא",
        "city_en": "Rome",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY381",
        "inbound_flight": "LY384",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "07:15",
        "arr_time_out": "10:00",
        "dep_time_in": "21:45",
        "arr_time_in": "02:10",
        "duration_minutes": 225,
        "economy_points": 15000,
        "premium_points": 20500,
        "business_points": 45000,
        "outbound_taxes_usd": 48.75,
        "inbound_taxes_usd": 48.75,
        "rt_cash_per_pax_usd": 590.0,
        "supplemental_single_pax_cash_usd": 460.0,
        "five_pax_cash_benchmark_usd": 2950.0,
        "alt_carriers": [("W6", "W68201", "W68202", 260.0), ("FR", "FR4101", "FR4102", 240.0), ("IZ", "IZ331", "IZ332", 430.0)],
    },
    "MXP": {
        "city_he": "מילאנו",
        "city_en": "Milan",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY387",
        "inbound_flight": "LY388",
        "operating_carrier": "LY",
        "aircraft_type": "788",
        "dep_time_out": "07:50",
        "arr_time_out": "10:55",
        "dep_time_in": "12:15",
        "arr_time_in": "17:05",
        "duration_minutes": 245,
        "economy_points": 15000,
        "premium_points": 20500,
        "business_points": 45000,
        "outbound_taxes_usd": 48.75,
        "inbound_taxes_usd": 48.75,
        "rt_cash_per_pax_usd": 570.0,
        "supplemental_single_pax_cash_usd": 450.0,
        "five_pax_cash_benchmark_usd": 2850.0,
        "alt_carriers": [("W6", "W65511", "W65512", 250.0), ("U2", "U23701", "U23702", 275.0)],
    },
    "VIE": {
        "city_he": "וינה",
        "city_en": "Vienna",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY361",
        "inbound_flight": "LY362",
        "operating_carrier": "LY",
        "aircraft_type": "739",
        "dep_time_out": "06:45",
        "arr_time_out": "09:35",
        "dep_time_in": "10:50",
        "arr_time_in": "15:15",
        "duration_minutes": 230,
        "economy_points": 15000,
        "premium_points": 22000,
        "business_points": 45000,
        "outbound_taxes_usd": 55.00,
        "inbound_taxes_usd": 55.00,
        "rt_cash_per_pax_usd": 510.0,
        "supplemental_single_pax_cash_usd": 410.0,
        "five_pax_cash_benchmark_usd": 2550.0,
        "alt_carriers": [("W6", "W62811", "W62812", 230.0), ("FR", "FR3211", "FR3212", 215.0), ("LH", "OS858", "OS857", 460.0)],
    },
    "BUD": {
        "city_he": "בודפשט",
        "city_en": "Budapest",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY2365",
        "inbound_flight": "LY2366",
        "operating_carrier": "LY",
        "aircraft_type": "738",
        "dep_time_out": "06:30",
        "arr_time_out": "08:55",
        "dep_time_in": "20:10",
        "arr_time_in": "00:20",
        "duration_minutes": 205,
        "economy_points": 15000,
        "premium_points": 0,
        "business_points": 45000,
        "outbound_taxes_usd": 46.00,
        "inbound_taxes_usd": 46.00,
        "rt_cash_per_pax_usd": 460.0,
        "supplemental_single_pax_cash_usd": 370.0,
        "five_pax_cash_benchmark_usd": 2300.0,
        "alt_carriers": [("W6", "W62326", "W62325", 205.0), ("IZ", "IZ421", "IZ422", 360.0)],
    },
    "PRG": {
        "city_he": "פראג",
        "city_en": "Prague",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY2521",
        "inbound_flight": "LY2522",
        "operating_carrier": "LY",
        "aircraft_type": "739",
        "dep_time_out": "07:05",
        "arr_time_out": "10:10",
        "dep_time_in": "11:25",
        "arr_time_in": "16:15",
        "duration_minutes": 245,
        "economy_points": 15000,
        "premium_points": 0,
        "business_points": 45000,
        "outbound_taxes_usd": 49.00,
        "inbound_taxes_usd": 49.00,
        "rt_cash_per_pax_usd": 490.0,
        "supplemental_single_pax_cash_usd": 395.0,
        "five_pax_cash_benchmark_usd": 2450.0,
        "alt_carriers": [("6H", "6H761", "6H762", 385.0), ("IZ", "IZ451", "IZ452", 390.0)],
    },
    "BER": {
        "city_he": "ברלין",
        "city_en": "Berlin",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY2371",
        "inbound_flight": "LY2372",
        "operating_carrier": "LY",
        "aircraft_type": "739",
        "dep_time_out": "06:20",
        "arr_time_out": "09:45",
        "dep_time_in": "11:00",
        "arr_time_in": "16:05",
        "duration_minutes": 265,
        "economy_points": 16500,
        "premium_points": 24000,
        "business_points": 50000,
        "outbound_taxes_usd": 62.00,
        "inbound_taxes_usd": 62.00,
        "rt_cash_per_pax_usd": 530.0,
        "supplemental_single_pax_cash_usd": 420.0,
        "five_pax_cash_benchmark_usd": 2650.0,
        "alt_carriers": [("FR", "FR1451", "FR1452", 235.0), ("U2", "U25811", "U25812", 260.0), ("LH", "LH687", "LH686", 495.0)],
    },
    "MUC": {
        "city_he": "מינכן",
        "city_en": "Munich",
        "award_zone": "ZONE_B",
        "outbound_flight": "LY353",
        "inbound_flight": "LY354",
        "operating_carrier": "LY",
        "aircraft_type": "739",
        "dep_time_out": "06:50",
        "arr_time_out": "10:05",
        "dep_time_in": "11:20",
        "arr_time_in": "16:10",
        "duration_minutes": 255,
        "economy_points": 16500,
        "premium_points": 24000,
        "business_points": 50000,
        "outbound_taxes_usd": 64.00,
        "inbound_taxes_usd": 64.00,
        "rt_cash_per_pax_usd": 550.0,
        "supplemental_single_pax_cash_usd": 440.0,
        "five_pax_cash_benchmark_usd": 2750.0,
        "alt_carriers": [("LH", "LH689", "LH688", 510.0)],
    },
    "LHR": {
        "city_he": "לונדון הית'רו",
        "city_en": "London Heathrow",
        "award_zone": "ZONE_C",
        "outbound_flight": "LY315",
        "inbound_flight": "LY316",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "09:05",
        "arr_time_out": "12:35",
        "dep_time_in": "14:50",
        "arr_time_in": "21:45",
        "duration_minutes": 330,
        "economy_points": 20000,
        "premium_points": 32500,
        "business_points": 65000,
        "outbound_taxes_usd": 55.00,
        "inbound_taxes_usd": 165.00,  # High UK Air Passenger Duty (APD) on LHR inbound
        "rt_cash_per_pax_usd": 740.0,
        "supplemental_single_pax_cash_usd": 590.0,
        "five_pax_cash_benchmark_usd": 3700.0,
        "alt_carriers": [("BA", "BA164", "BA165", 690.0)],
    },
    "LTN": {
        "city_he": "לונדון לוטון",
        "city_en": "London Luton",
        "award_zone": "ZONE_C",
        "outbound_flight": "LY311",
        "inbound_flight": "LY312",
        "operating_carrier": "LY",
        "aircraft_type": "788",
        "dep_time_out": "06:15",
        "arr_time_out": "09:50",
        "dep_time_in": "11:05",
        "arr_time_in": "18:00",
        "duration_minutes": 335,
        "economy_points": 20000,
        "premium_points": 30000,
        "business_points": 60000,
        "outbound_taxes_usd": 52.00,
        "inbound_taxes_usd": 82.00,  # Lower airport charges than LHR
        "rt_cash_per_pax_usd": 640.0,
        "supplemental_single_pax_cash_usd": 510.0,
        "five_pax_cash_benchmark_usd": 3200.0,
        "alt_carriers": [("W6", "W64451", "W64452", 280.0), ("U2", "U22084", "U22083", 295.0)],
    },
    "CDG": {
        "city_he": "פריז",
        "city_en": "Paris",
        "award_zone": "ZONE_C",
        "outbound_flight": "LY323",
        "inbound_flight": "LY324",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "09:00",
        "arr_time_out": "13:05",
        "dep_time_in": "15:10",
        "arr_time_in": "20:35",
        "duration_minutes": 305,
        "economy_points": 20000,
        "premium_points": 32500,
        "business_points": 62500,
        "outbound_taxes_usd": 62.00,
        "inbound_taxes_usd": 78.00,
        "rt_cash_per_pax_usd": 680.0,
        "supplemental_single_pax_cash_usd": 540.0,
        "five_pax_cash_benchmark_usd": 3400.0,
        "alt_carriers": [("AF", "AF1321", "AF1320", 620.0), ("U2", "U23838", "U23837", 290.0)],
    },
    "MAD": {
        "city_he": "מדריד",
        "city_en": "Madrid",
        "award_zone": "ZONE_C",
        "outbound_flight": "LY395",
        "inbound_flight": "LY398",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "06:30",
        "arr_time_out": "10:55",
        "dep_time_in": "12:30",
        "arr_time_in": "18:15",
        "duration_minutes": 325,
        "economy_points": 16250,
        "premium_points": 21250,
        "business_points": 60000,
        "outbound_taxes_usd": 51.25,
        "inbound_taxes_usd": 51.25,
        "rt_cash_per_pax_usd": 660.0,
        "supplemental_single_pax_cash_usd": 530.0,
        "five_pax_cash_benchmark_usd": 3300.0,
        "alt_carriers": [("IZ", "IZ511", "IZ512", 520.0)],
    },
    "BCN": {
        "city_he": "ברצלונה",
        "city_en": "Barcelona",
        "award_zone": "ZONE_C",
        "outbound_flight": "LY393",
        "inbound_flight": "LY394",
        "operating_carrier": "LY",
        "aircraft_type": "788",
        "dep_time_out": "06:40",
        "arr_time_out": "10:30",
        "dep_time_in": "12:00",
        "arr_time_in": "17:10",
        "duration_minutes": 290,
        "economy_points": 18500,
        "premium_points": 28000,
        "business_points": 60000,
        "outbound_taxes_usd": 52.00,
        "inbound_taxes_usd": 52.00,
        "rt_cash_per_pax_usd": 620.0,
        "supplemental_single_pax_cash_usd": 495.0,
        "five_pax_cash_benchmark_usd": 3100.0,
        "alt_carriers": [("W6", "W64111", "W64112", 275.0), ("IZ", "IZ521", "IZ522", 470.0)],
    },
    "AMS": {
        "city_he": "אמסטרדם",
        "city_en": "Amsterdam",
        "award_zone": "ZONE_C",
        "outbound_flight": "LY337",
        "inbound_flight": "LY338",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "06:25",
        "arr_time_out": "10:25",
        "dep_time_in": "12:00",
        "arr_time_in": "17:30",
        "duration_minutes": 300,
        "economy_points": 20000,
        "premium_points": 32500,
        "business_points": 62500,
        "outbound_taxes_usd": 60.00,
        "inbound_taxes_usd": 68.00,
        "rt_cash_per_pax_usd": 670.0,
        "supplemental_single_pax_cash_usd": 535.0,
        "five_pax_cash_benchmark_usd": 3350.0,
        "alt_carriers": [("U2", "U27942", "U27941", 285.0)],
    },
    "BKK": {
        "city_he": "בנגקוק",
        "city_en": "Bangkok",
        "award_zone": "ZONE_D",
        "outbound_flight": "LY081",
        "inbound_flight": "LY082",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "23:15",
        "arr_time_out": "14:20",
        "dep_time_in": "23:50",
        "arr_time_in": "06:10",
        "duration_minutes": 665,
        "economy_points": 37500,
        "premium_points": 70000,
        "business_points": 95000,
        "outbound_taxes_usd": 65.00,
        "inbound_taxes_usd": 65.00,
        "rt_cash_per_pax_usd": 1150.0,
        "supplemental_single_pax_cash_usd": 920.0,
        "five_pax_cash_benchmark_usd": 5750.0,
        "alt_carriers": [("FZ", "FZ1626", "FZ1625", 910.0)],
    },
    "NRT": {
        "city_he": "טוקיו נריטה",
        "city_en": "Tokyo Narita",
        "award_zone": "ZONE_D",
        "outbound_flight": "LY091",
        "inbound_flight": "LY092",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "21:30",
        "arr_time_out": "15:15",
        "dep_time_in": "17:15",
        "arr_time_in": "23:45",
        "duration_minutes": 705,
        "economy_points": 42500,
        "premium_points": 75000,
        "business_points": 110000,
        "outbound_taxes_usd": 75.00,
        "inbound_taxes_usd": 75.00,
        "rt_cash_per_pax_usd": 1320.0,
        "supplemental_single_pax_cash_usd": 1060.0,
        "five_pax_cash_benchmark_usd": 6600.0,
        "alt_carriers": [],
    },
    "HKT": {
        "city_he": "פוקט",
        "city_en": "Phuket",
        "award_zone": "ZONE_D",
        "outbound_flight": "LY085",
        "inbound_flight": "LY086",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "22:45",
        "arr_time_out": "13:55",
        "dep_time_in": "22:30",
        "arr_time_in": "05:10",
        "duration_minutes": 670,
        "economy_points": 37500,
        "premium_points": 70000,
        "business_points": 95000,
        "outbound_taxes_usd": 65.00,
        "inbound_taxes_usd": 65.00,
        "rt_cash_per_pax_usd": 1180.0,
        "supplemental_single_pax_cash_usd": 945.0,
        "five_pax_cash_benchmark_usd": 5900.0,
        "alt_carriers": [("FZ", "FZ1630", "FZ1629", 930.0)],
    },
    "JFK": {
        "city_he": "ניו יורק JFK",
        "city_en": "New York JFK",
        "award_zone": "ZONE_E",
        "outbound_flight": "LY001",
        "inbound_flight": "LY002",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "00:45",
        "arr_time_out": "05:50",
        "dep_time_in": "13:30",
        "arr_time_in": "07:05",
        "duration_minutes": 725,
        "economy_points": 40000,
        "premium_points": 72500,
        "business_points": 105000,
        "outbound_taxes_usd": 58.00,
        "inbound_taxes_usd": 58.00,
        "rt_cash_per_pax_usd": 1280.0,
        "supplemental_single_pax_cash_usd": 1020.0,
        "five_pax_cash_benchmark_usd": 6400.0,
        "alt_carriers": [("DL", "DL235", "DL234", 1190.0)],
    },
    "EWR": {
        "city_he": "ניו יורק ניוארק",
        "city_en": "Newark",
        "award_zone": "ZONE_E",
        "outbound_flight": "LY027",
        "inbound_flight": "LY028",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "12:30",
        "arr_time_out": "17:45",
        "dep_time_in": "21:00",
        "arr_time_in": "14:30",
        "duration_minutes": 735,
        "economy_points": 40000,
        "premium_points": 72500,
        "business_points": 105000,
        "outbound_taxes_usd": 56.00,
        "inbound_taxes_usd": 56.00,
        "rt_cash_per_pax_usd": 1260.0,
        "supplemental_single_pax_cash_usd": 1005.0,
        "five_pax_cash_benchmark_usd": 6300.0,
        "alt_carriers": [("UA", "UA085", "UA084", 1180.0)],
    },
    "MIA": {
        "city_he": "מיאמי",
        "city_en": "Miami",
        "award_zone": "ZONE_E",
        "outbound_flight": "LY017",
        "inbound_flight": "LY018",
        "operating_carrier": "LY",
        "aircraft_type": "789",
        "dep_time_out": "11:00",
        "arr_time_out": "17:15",
        "dep_time_in": "20:15",
        "arr_time_in": "15:10",
        "duration_minutes": 795,
        "economy_points": 42500,
        "premium_points": 75000,
        "business_points": 110000,
        "outbound_taxes_usd": 62.00,
        "inbound_taxes_usd": 62.00,
        "rt_cash_per_pax_usd": 1350.0,
        "supplemental_single_pax_cash_usd": 1080.0,
        "five_pax_cash_benchmark_usd": 6750.0,
        "alt_carriers": [],
    },
    "FLL": {
        "city_he": "פורט לודרדייל",
        "city_en": "Fort Lauderdale",
        "award_zone": "ZONE_E",
        "outbound_flight": "LY019",
        "inbound_flight": "LY020",
        "operating_carrier": "LY",
        "aircraft_type": "788",
        "dep_time_out": "10:30",
        "arr_time_out": "16:45",
        "dep_time_in": "20:45",
        "arr_time_in": "15:35",
        "duration_minutes": 795,
        "economy_points": 42500,
        "premium_points": 75000,
        "business_points": 110000,
        "outbound_taxes_usd": 60.00,
        "inbound_taxes_usd": 60.00,
        "rt_cash_per_pax_usd": 1310.0,
        "supplemental_single_pax_cash_usd": 1045.0,
        "five_pax_cash_benchmark_usd": 6550.0,
        "alt_carriers": [],
    },
}

# ==============================================================================
# WMO / Copernicus ERA5 12-Month Climatological Normals & Vacation Style Profiles
# across all 25 supported destinations in DESTINATION_CATALOG
# ==============================================================================

_DESTINATION_CLIMATE_PROFILES: dict[str, dict[str, Any]] = {
    "ATH": {
        "latitude": 37.9364,
        "longitude": 23.9445,
        "climate_zone_label_he": "ים-תיכוני חופי (ריביירת אתונה + אקרופוליס)",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 1.00,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "ריביירת אתונה (ווליאגמני וגליפאדה)",
            "NATURE_TRIP": "כף סוניון והר פרניתה",
            "URBAN_CULTURE": "האקרופוליס, פלאקה ומוזיאוני אתונה",
        },
        "monthly": {
            1: (13.5, 7.0, 15.5, 7.0, 52.0, 4.5, 68, 3.0, 0.0),
            2: (14.5, 7.5, 15.0, 6.0, 45.0, 5.2, 66, 4.0, 0.0),
            3: (17.0, 9.0, 15.5, 5.5, 40.0, 6.5, 63, 5.5, 0.0),
            4: (21.0, 12.0, 17.0, 4.0, 26.0, 8.2, 58, 7.0, 0.0),
            5: (26.0, 16.5, 20.0, 3.0, 18.0, 9.8, 53, 8.5, 0.0),
            6: (31.0, 21.5, 23.5, 1.5, 8.0, 11.4, 46, 9.5, 0.0),
            7: (33.5, 24.5, 26.0, 0.5, 5.0, 11.8, 43, 10.0, 0.0),
            8: (33.5, 24.5, 26.5, 0.5, 5.0, 11.5, 44, 9.5, 0.0),
            9: (29.0, 20.5, 25.0, 2.0, 14.0, 9.6, 51, 7.5, 0.0),
            10: (24.0, 16.0, 22.5, 4.0, 38.0, 7.2, 60, 5.5, 0.0),
            11: (19.0, 12.0, 19.5, 6.0, 58.0, 5.4, 67, 3.5, 0.0),
            12: (15.5, 9.2, 16.8, 7.0, 70.0, 4.5, 70, 2.5, 0.0),
        },
    },
    "LCA": {
        "latitude": 34.8751,
        "longitude": 33.6249,
        "climate_zone_label_he": "ים-תיכוני מזרחי (איה נאפה, פרוטארס והרי הטרודוס)",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 0.88,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "חופי איה נאפה, ניסי ביץ' ופרוטארס",
            "NATURE_TRIP": "כף גרקו והרי הטרודוס",
        },
        "monthly": {
            1: (17.0, 8.0, 17.5, 7.0, 62.0, 5.8, 70, 3.5, 0.0),
            2: (17.5, 8.2, 17.0, 6.0, 48.0, 6.6, 68, 4.5, 0.0),
            3: (20.0, 10.0, 17.5, 4.5, 32.0, 7.8, 65, 6.5, 0.0),
            4: (23.0, 13.0, 19.0, 3.0, 18.0, 9.2, 60, 8.0, 0.0),
            5: (27.5, 17.0, 22.0, 1.5, 10.0, 10.8, 56, 9.5, 0.0),
            6: (31.5, 21.5, 25.5, 0.3, 2.0, 12.0, 54, 10.5, 0.0),
            7: (33.5, 24.0, 27.5, 0.1, 1.0, 12.2, 55, 11.0, 0.0),
            8: (33.8, 24.2, 28.5, 0.1, 1.0, 11.8, 57, 10.5, 0.0),
            9: (31.0, 21.0, 27.0, 0.8, 5.0, 10.4, 58, 8.5, 0.0),
            10: (27.5, 17.5, 25.0, 2.5, 22.0, 8.8, 61, 6.0, 0.0),
            11: (22.5, 13.0, 22.0, 4.5, 40.0, 7.2, 65, 4.0, 0.0),
            12: (18.5, 9.8, 19.0, 6.5, 68.0, 5.8, 70, 3.0, 0.0),
        },
    },
    "RHO": {
        "latitude": 36.4054,
        "longitude": 28.0862,
        "climate_zone_label_he": "אי ים-תיכוני אגאי (ריזורטים, חופים וטבע חופי)",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.05,
        "urban_culture_affinity": 0.88,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "לינדוס, פאליראקי וריזורטי חוף ברודוס",
            "NATURE_TRIP": "עמק הפרפרים ושבעת המעיינות",
        },
        "monthly": {
            1: (15.0, 9.0, 17.0, 9.0, 115.0, 5.0, 70, 3.0, 0.0),
            2: (15.5, 9.2, 16.5, 8.0, 90.0, 5.8, 68, 4.0, 0.0),
            3: (17.5, 11.0, 16.8, 6.0, 55.0, 7.2, 66, 5.5, 0.0),
            4: (21.5, 14.0, 18.5, 3.0, 24.0, 9.0, 62, 7.5, 0.0),
            5: (25.5, 17.5, 21.0, 1.8, 14.0, 10.5, 58, 9.0, 0.0),
            6: (29.5, 22.0, 24.5, 0.4, 3.0, 11.8, 54, 10.0, 0.0),
            7: (31.0, 24.0, 26.5, 0.1, 1.0, 12.2, 53, 10.5, 0.0),
            8: (31.2, 24.5, 27.5, 0.1, 1.0, 11.8, 55, 10.0, 0.0),
            9: (28.5, 21.5, 26.0, 1.2, 10.0, 10.2, 58, 8.0, 0.0),
            10: (24.5, 17.5, 23.8, 4.0, 52.0, 8.0, 64, 5.5, 0.0),
            11: (20.0, 13.5, 20.8, 6.5, 88.0, 6.2, 68, 3.5, 0.0),
            12: (16.5, 10.5, 18.2, 9.0, 125.0, 5.0, 71, 2.5, 0.0),
        },
    },
    "PFO": {
        "latitude": 34.7180,
        "longitude": 32.4857,
        "climate_zone_label_he": "ים-תיכוני חופי (מפרץ האלמוגים וחצי האי אקאמאס)",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.05,
        "urban_culture_affinity": 0.86,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "קורל ביי (Coral Bay) והלגונה הכחולה",
            "NATURE_TRIP": "שמורת חצי האי אקאמאס וקניון אוואקאס",
        },
        "monthly": {
            1: (17.0, 9.0, 17.5, 8.0, 72.0, 5.6, 70, 3.5, 0.0),
            2: (17.5, 9.0, 17.0, 6.5, 55.0, 6.4, 68, 4.5, 0.0),
            3: (19.5, 10.5, 17.5, 5.0, 36.0, 7.6, 66, 6.5, 0.0),
            4: (22.5, 13.0, 19.0, 3.0, 20.0, 9.2, 62, 8.0, 0.0),
            5: (26.0, 16.5, 21.8, 1.5, 10.0, 10.6, 60, 9.5, 0.0),
            6: (29.5, 20.5, 25.0, 0.3, 2.0, 11.8, 58, 10.5, 0.0),
            7: (31.5, 23.0, 27.2, 0.1, 1.0, 12.0, 60, 11.0, 0.0),
            8: (32.0, 23.5, 28.0, 0.1, 1.0, 11.6, 61, 10.5, 0.0),
            9: (29.8, 20.8, 26.8, 0.8, 6.0, 10.2, 60, 8.5, 0.0),
            10: (26.8, 17.5, 24.8, 3.0, 28.0, 8.6, 62, 6.0, 0.0),
            11: (22.2, 13.5, 21.8, 5.0, 48.0, 7.0, 66, 4.0, 0.0),
            12: (18.5, 10.5, 19.0, 7.5, 78.0, 5.6, 70, 3.0, 0.0),
        },
    },
    "TBS": {
        "latitude": 41.6692,
        "longitude": 44.9547,
        "climate_zone_label_he": "עמק קווקזי יבשתי + שער להרי הקווקז הגבוה (גודאורי/קזבגי)",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 1.08,
        "urban_culture_affinity": 0.92,
        "theme_park_tier": 0.95,
        "is_ski_accessible": True,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "NATURE_TRIP": "הדרך הצבאית הגאורגית, קזבגי ובורג'ומי",
            "SNOW_AND_SKI": "אתרי הסקי גודאורי (Gudauri) ובקוריאני",
            "URBAN_CULTURE": "העיר העתיקה של טביליסי ומרחצאות הגופרית",
        },
        "monthly": {
            1: (6.5, -1.5, None, 4.0, 20.0, 3.5, 72, 2.5, 0.88),
            2: (8.5, 0.0, None, 4.5, 25.0, 4.2, 68, 3.5, 0.90),
            3: (13.0, 3.5, None, 6.0, 35.0, 5.2, 64, 5.0, 0.78),
            4: (19.0, 8.5, None, 8.0, 52.0, 6.5, 62, 6.5, 0.35),
            5: (24.0, 13.0, None, 10.0, 78.0, 7.5, 62, 8.0, 0.0),
            6: (28.5, 17.0, None, 7.0, 65.0, 8.8, 56, 9.0, 0.0),
            7: (31.5, 20.0, None, 4.5, 38.0, 9.2, 52, 9.5, 0.0),
            8: (31.5, 20.0, None, 4.0, 34.0, 9.0, 52, 9.0, 0.0),
            9: (26.5, 15.5, None, 5.0, 36.0, 7.6, 58, 7.0, 0.0),
            10: (19.5, 10.0, None, 6.0, 42.0, 5.8, 66, 4.5, 0.0),
            11: (12.5, 4.0, None, 5.0, 30.0, 4.4, 72, 3.0, 0.25),
            12: (8.0, 0.0, None, 4.0, 22.0, 3.8, 74, 2.0, 0.82),
        },
    },
    "FCO": {
        "latitude": 41.8003,
        "longitude": 12.2389,
        "climate_zone_label_he": "בירה ים-תיכונית היסטורית (טוסקנה, אומבריה וחוף טירניה)",
        "coastal_tier": "COASTAL_OR_LAKE_ACCESS",
        "coastal_factor": 0.82,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "הקולוסיאום, הוותיקן, פיאצה נבונה וטרסטוורה",
            "NATURE_TRIP": "גני טיבולי, אגם ברצ'יאנו וגבעות טוסקנה",
        },
        "monthly": {
            1: (12.5, 3.5, 14.5, 7.0, 75.0, 4.3, 75, 2.5, 0.0),
            2: (13.5, 4.0, 14.0, 7.0, 70.0, 5.0, 72, 3.5, 0.0),
            3: (16.5, 6.5, 14.5, 6.5, 62.0, 6.4, 68, 5.0, 0.0),
            4: (20.0, 10.0, 16.0, 6.0, 65.0, 7.5, 66, 6.5, 0.0),
            5: (24.5, 14.0, 19.0, 5.0, 48.0, 9.2, 62, 8.0, 0.0),
            6: (29.0, 18.0, 23.0, 3.0, 28.0, 10.4, 58, 9.0, 0.0),
            7: (32.0, 20.5, 25.5, 1.5, 16.0, 11.2, 55, 9.5, 0.0),
            8: (32.0, 20.5, 26.5, 2.0, 24.0, 10.4, 56, 8.5, 0.0),
            9: (27.5, 17.0, 24.5, 5.0, 68.0, 8.4, 63, 6.5, 0.0),
            10: (22.5, 13.0, 21.5, 7.0, 95.0, 6.6, 70, 4.5, 0.0),
            11: (17.0, 8.0, 18.5, 9.0, 110.0, 4.8, 76, 3.0, 0.0),
            12: (13.5, 4.5, 16.0, 8.0, 90.0, 4.0, 77, 2.0, 0.0),
        },
    },
    "MXP": {
        "latitude": 45.6301,
        "longitude": 8.7255,
        "climate_zone_label_he": "צפון איטליה; אגמי קומו וגארדה, גארדאלנד, הדולומיטים והאלפים",
        "coastal_tier": "COASTAL_OR_LAKE_ACCESS",
        "coastal_factor": 0.82,
        "nature_affinity_factor": 1.08,
        "urban_culture_affinity": 1.04,
        "theme_park_tier": 1.08,
        "is_ski_accessible": True,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "NATURE_TRIP": "אגם קומו, אגם גארדה, מאג'ורה והדולומיטים",
            "FAMILY_ATTRACTIONS_PARKS": "פארק גארדאלנד (Gardaland) ו-Movieland",
            "SNOW_AND_SKI": "צ'רביניה, ליביניו והדולומיטים",
        },
        "monthly": {
            1: (6.5, -1.0, None, 6.0, 58.0, 3.2, 80, 2.0, 0.90),
            2: (9.0, 0.5, None, 5.5, 52.0, 4.5, 74, 3.0, 0.92),
            3: (14.5, 4.5, None, 6.5, 68.0, 5.8, 66, 4.5, 0.80),
            4: (19.0, 9.0, None, 7.0, 75.0, 6.8, 64, 6.0, 0.45),
            5: (23.5, 13.5, None, 8.0, 92.0, 7.8, 62, 7.5, 0.0),
            6: (28.0, 17.5, None, 6.5, 72.0, 9.0, 60, 8.5, 0.0),
            7: (30.5, 19.8, None, 5.0, 58.0, 9.8, 58, 9.0, 0.0),
            8: (29.8, 19.5, None, 5.5, 70.0, 8.8, 61, 8.0, 0.0),
            9: (25.0, 15.5, None, 6.0, 78.0, 7.0, 66, 6.0, 0.0),
            10: (18.5, 10.2, None, 7.5, 105.0, 5.0, 75, 4.0, 0.0),
            11: (11.5, 4.5, None, 8.0, 98.0, 3.4, 82, 2.5, 0.35),
            12: (7.5, 0.5, None, 6.0, 60.0, 3.5, 82, 1.8, 0.85),
        },
    },
    "VIE": {
        "latitude": 48.1103,
        "longitude": 16.5697,
        "climate_zone_label_he": "מרכז אירופה; בירה אימפריאלית, שווקי חורף והאלפים האוסטריים",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 1.05,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 0.95,
        "is_ski_accessible": True,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "ארמון שנברון, הופבורג, מוזיאוני וינה ופראטר",
            "WINTER_FESTIVE": "שווקי חג המולד הקלאסיים בכיכר העירייה (Rathausplatz)",
            "NATURE_TRIP": "עמק הוואכאו, זלצקמרגוט והאלפים האוסטריים",
        },
        "monthly": {
            1: (3.2, -2.0, None, 7.0, 38.0, 2.2, 78, 1.5, 0.85),
            2: (5.5, -0.8, None, 6.5, 36.0, 3.4, 74, 2.5, 0.88),
            3: (10.8, 3.0, None, 7.5, 46.0, 4.8, 68, 4.0, 0.72),
            4: (16.8, 7.5, None, 7.0, 45.0, 6.5, 62, 5.5, 0.30),
            5: (21.5, 12.0, None, 8.5, 62.0, 7.8, 62, 7.0, 0.0),
            6: (25.0, 15.5, None, 8.5, 70.0, 8.4, 61, 8.0, 0.0),
            7: (27.5, 17.5, None, 8.0, 68.0, 8.8, 59, 8.0, 0.0),
            8: (27.0, 17.2, None, 7.5, 62.0, 8.4, 60, 7.0, 0.0),
            9: (21.5, 13.0, None, 6.5, 52.0, 6.4, 66, 5.0, 0.0),
            10: (15.2, 8.0, None, 6.0, 42.0, 4.6, 73, 3.5, 0.0),
            11: (8.5, 3.2, None, 7.5, 46.0, 2.5, 80, 2.0, 0.25),
            12: (4.5, -0.5, None, 7.0, 42.0, 2.0, 80, 1.5, 0.80),
        },
    },
    "BUD": {
        "latitude": 47.4369,
        "longitude": 19.2556,
        "climate_zone_label_he": "מרכז אירופה; מרחצאות תרמיים, הדנובה ושווקי חורף",
        "coastal_tier": "COASTAL_OR_LAKE_ACCESS",
        "coastal_factor": 0.82,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.05,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "הפרלמנט, מרחצאות סצ'ני, האי מרגיט ושיט בדנובה",
            "WINTER_FESTIVE": "שוק החורף בכיכר וורשמארטי ובבזיליקת סנט אישטוון",
        },
        "monthly": {
            1: (3.0, -2.5, None, 6.5, 34.0, 2.2, 79, 1.5, 0.0),
            2: (5.8, -1.0, None, 6.0, 32.0, 3.5, 73, 2.5, 0.0),
            3: (11.5, 3.0, None, 6.5, 36.0, 5.2, 65, 4.0, 0.0),
            4: (18.0, 8.0, None, 6.5, 42.0, 6.8, 59, 5.5, 0.0),
            5: (23.0, 12.8, None, 8.0, 60.0, 8.2, 60, 7.0, 0.0),
            6: (26.5, 16.0, None, 7.5, 65.0, 9.0, 59, 8.0, 0.0),
            7: (28.8, 18.0, None, 6.5, 54.0, 9.6, 56, 8.5, 0.0),
            8: (28.5, 17.5, None, 6.0, 50.0, 9.0, 57, 7.5, 0.0),
            9: (23.0, 13.2, None, 5.5, 45.0, 6.8, 63, 5.5, 0.0),
            10: (16.5, 8.2, None, 5.5, 38.0, 5.0, 70, 3.5, 0.0),
            11: (9.2, 3.2, None, 7.0, 46.0, 2.6, 78, 2.0, 0.0),
            12: (4.2, -1.0, None, 7.0, 38.0, 1.9, 80, 1.5, 0.0),
        },
    },
    "PRG": {
        "latitude": 50.1008,
        "longitude": 14.2600,
        "climate_zone_label_he": "מרכז אירופה; עיר היסטורית, שווקי חורף וגן העדן הבוהמי",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 1.06,
        "theme_park_tier": 0.95,
        "is_ski_accessible": True,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "גשר קארל, מצודת פראג וכיכר העיר העתיקה",
            "WINTER_FESTIVE": "שווקי החורף בכיכר העיר העתיקה ובכיכר ואצלב",
            "NATURE_TRIP": "שמורת שווייץ הבוהמית וגן העדן הבוהמי",
        },
        "monthly": {
            1: (2.0, -3.5, None, 7.0, 24.0, 1.8, 81, 1.2, 0.72),
            2: (4.0, -2.5, None, 6.5, 22.0, 2.8, 77, 2.0, 0.75),
            3: (9.2, 1.0, None, 7.5, 30.0, 4.4, 70, 3.5, 0.55),
            4: (15.5, 5.2, None, 7.0, 35.0, 6.2, 63, 5.0, 0.15),
            5: (20.2, 9.8, None, 9.0, 62.0, 7.4, 64, 6.5, 0.0),
            6: (23.5, 13.0, None, 9.0, 70.0, 7.8, 64, 7.5, 0.0),
            7: (25.8, 15.0, None, 9.0, 72.0, 8.0, 62, 7.5, 0.0),
            8: (25.5, 14.5, None, 8.0, 65.0, 7.6, 64, 6.5, 0.0),
            9: (20.2, 10.5, None, 6.5, 42.0, 5.8, 70, 4.5, 0.0),
            10: (14.0, 6.0, None, 6.5, 32.0, 4.0, 76, 3.0, 0.0),
            11: (7.2, 1.5, None, 7.5, 30.0, 2.0, 82, 1.5, 0.20),
            12: (3.2, -1.8, None, 7.0, 26.0, 1.6, 83, 1.0, 0.68),
        },
    },
    "BER": {
        "latitude": 52.3667,
        "longitude": 13.5033,
        "climate_zone_label_he": "אירופה הממוזגת; מוזיאונים, תרבות, Tropical Islands ושווקי חורף",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.06,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "אי המוזיאונים, שער ברנדנבורג, פוטסדאם וקודאם",
            "WINTER_FESTIVE": "שווקי חג המולד ב-Gendarmenmarkt ואלכסנדרפלאץ",
        },
        "monthly": {
            1: (3.2, -1.5, None, 9.0, 42.0, 1.8, 82, 1.0, 0.0),
            2: (5.0, -1.0, None, 8.0, 35.0, 2.8, 78, 2.0, 0.0),
            3: (9.5, 2.0, None, 8.5, 40.0, 4.4, 71, 3.5, 0.0),
            4: (15.5, 6.0, None, 7.0, 36.0, 6.5, 63, 5.0, 0.0),
            5: (20.5, 10.5, None, 8.0, 52.0, 7.6, 62, 6.5, 0.0),
            6: (23.8, 14.0, None, 8.5, 62.0, 7.8, 63, 7.0, 0.0),
            7: (25.8, 16.0, None, 8.5, 65.0, 7.8, 63, 7.0, 0.0),
            8: (25.5, 15.5, None, 8.0, 58.0, 7.4, 65, 6.0, 0.0),
            9: (20.2, 11.8, None, 7.0, 45.0, 5.6, 71, 4.5, 0.0),
            10: (14.2, 7.5, None, 7.5, 40.0, 3.8, 78, 2.5, 0.0),
            11: (8.0, 3.0, None, 8.5, 44.0, 2.0, 84, 1.5, 0.0),
            12: (4.5, 0.0, None, 9.0, 46.0, 1.5, 85, 1.0, 0.0),
        },
    },
    "MUC": {
        "latitude": 48.3537,
        "longitude": 11.7750,
        "climate_zone_label_he": "שער לאלפים הבוואריים וטירול; טבע אלפיני, סקי, Legoland ושווקי חורף",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 1.08,
        "urban_culture_affinity": 1.02,
        "theme_park_tier": 1.08,
        "is_ski_accessible": True,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "NATURE_TRIP": "האלפים הבוואריים, טירת נוישוונשטיין, צוגשפיצה ואגם קניגסי",
            "FAMILY_ATTRACTIONS_PARKS": "לגולנד גרמניה (Legoland) ופארק אירופה",
            "SNOW_AND_SKI": "גארמיש-פארטנקירכן ואתרי הסקי של טירול באוסטריה",
        },
        "monthly": {
            1: (2.8, -3.5, None, 9.0, 52.0, 2.3, 80, 1.5, 0.92),
            2: (4.8, -2.5, None, 8.0, 46.0, 3.4, 76, 2.5, 0.94),
            3: (9.8, 1.0, None, 9.0, 58.0, 4.8, 70, 4.0, 0.82),
            4: (15.0, 5.0, None, 9.0, 65.0, 6.2, 65, 5.5, 0.40),
            5: (19.8, 9.5, None, 11.0, 98.0, 7.2, 66, 7.0, 0.0),
            6: (23.2, 13.0, None, 11.0, 112.0, 7.6, 66, 8.0, 0.0),
            7: (25.2, 14.8, None, 10.0, 108.0, 8.2, 64, 8.0, 0.0),
            8: (24.8, 14.5, None, 9.5, 102.0, 7.8, 66, 7.0, 0.0),
            9: (20.0, 10.5, None, 8.0, 72.0, 5.8, 72, 5.0, 0.0),
            10: (14.2, 6.0, None, 7.5, 56.0, 4.4, 77, 3.5, 0.0),
            11: (7.8, 1.2, None, 8.5, 54.0, 2.5, 82, 2.0, 0.35),
            12: (4.0, -2.5, None, 9.0, 55.0, 2.2, 82, 1.5, 0.88),
        },
    },
    "LHR": {
        "latitude": 51.4700,
        "longitude": -0.4543,
        "climate_zone_label_he": "אקלים ימי ממוזג; בירת תרבות, תיאטרון, שופינג, Legoland ואורות חורף",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "הווסט אנד, המוזיאון הבריטי, קובנט גארדן ואוקספורד סטריט",
            "FAMILY_ATTRACTIONS_PARKS": "לגולנד וינדזור (Legoland) ואולפני הארי פוטר",
            "WINTER_FESTIVE": "הייד פארק Winter Wonderland ואורות החג בלונדון",
        },
        "monthly": {
            1: (8.5, 3.0, None, 11.0, 58.0, 2.0, 80, 1.0, 0.0),
            2: (9.2, 3.2, None, 9.0, 45.0, 2.8, 76, 2.0, 0.0),
            3: (12.0, 4.8, None, 9.0, 42.0, 4.2, 71, 3.5, 0.0),
            4: (15.5, 7.0, None, 8.5, 44.0, 5.8, 66, 5.0, 0.0),
            5: (19.0, 10.2, None, 8.5, 50.0, 6.8, 65, 6.0, 0.0),
            6: (22.2, 13.2, None, 8.0, 48.0, 7.0, 64, 7.0, 0.0),
            7: (24.5, 15.2, None, 7.5, 46.0, 7.2, 63, 7.0, 0.0),
            8: (24.0, 15.0, None, 8.0, 52.0, 6.6, 65, 6.0, 0.0),
            9: (20.8, 12.5, None, 8.0, 50.0, 5.2, 70, 4.5, 0.0),
            10: (16.2, 9.5, None, 10.0, 65.0, 3.8, 76, 2.5, 0.0),
            11: (11.5, 5.8, None, 10.5, 62.0, 2.3, 81, 1.5, 0.0),
            12: (9.2, 4.2, None, 10.0, 65.0, 1.9, 82, 1.0, 0.0),
        },
    },
    "LTN": {
        "latitude": 51.8747,
        "longitude": -0.3683,
        "climate_zone_label_he": "מטרופולין לונדון; אולפני הארי פוטר (Warner Bros.), תרבות ושופינג",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "FAMILY_ATTRACTIONS_PARKS": "אולפני הארי פוטר (ווטפורד) ולגולנד וינדזור",
            "URBAN_CULTURE": "מרכז לונדון, מוזיאון הטבע ומופעי הווסט אנד",
            "WINTER_FESTIVE": "Winter Wonderland בהייד פארק ושווקי חג המולד",
        },
        "monthly": {
            1: (8.2, 2.8, None, 11.0, 58.0, 2.0, 80, 1.0, 0.0),
            2: (9.0, 3.0, None, 9.0, 45.0, 2.8, 76, 2.0, 0.0),
            3: (11.8, 4.5, None, 9.0, 42.0, 4.2, 71, 3.5, 0.0),
            4: (15.2, 6.8, None, 8.5, 44.0, 5.8, 66, 5.0, 0.0),
            5: (18.8, 10.0, None, 8.5, 50.0, 6.8, 65, 6.0, 0.0),
            6: (22.0, 13.0, None, 8.0, 48.0, 7.0, 64, 7.0, 0.0),
            7: (24.2, 15.0, None, 7.5, 46.0, 7.2, 63, 7.0, 0.0),
            8: (23.8, 14.8, None, 8.0, 52.0, 6.6, 65, 6.0, 0.0),
            9: (20.5, 12.2, None, 8.0, 50.0, 5.2, 70, 4.5, 0.0),
            10: (16.0, 9.2, None, 10.0, 65.0, 3.8, 76, 2.5, 0.0),
            11: (11.2, 5.5, None, 10.5, 62.0, 2.3, 81, 1.5, 0.0),
            12: (9.0, 4.0, None, 10.0, 65.0, 1.9, 82, 1.0, 0.0),
        },
    },
    "CDG": {
        "latitude": 49.0097,
        "longitude": 2.5479,
        "climate_zone_label_he": "מערב אירופה; דיסנילנד פריז, פארק אסטריקס, מוזיאונים וקולינריה",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "FAMILY_ATTRACTIONS_PARKS": "דיסנילנד פריז (Disneyland Paris) ופארק אסטריקס",
            "URBAN_CULTURE": "מגדל אייפל, הלובר, שאנז אליזה ומונמארטר",
        },
        "monthly": {
            1: (7.5, 2.5, None, 10.0, 52.0, 2.1, 81, 1.2, 0.0),
            2: (8.8, 2.8, None, 9.0, 44.0, 3.1, 77, 2.2, 0.0),
            3: (12.8, 5.2, None, 9.0, 46.0, 4.8, 70, 3.8, 0.0),
            4: (16.5, 7.5, None, 9.0, 50.0, 6.0, 65, 5.5, 0.0),
            5: (20.2, 11.0, None, 9.5, 62.0, 6.8, 65, 6.8, 0.0),
            6: (23.8, 14.2, None, 8.0, 54.0, 7.5, 64, 7.5, 0.0),
            7: (26.2, 16.2, None, 7.5, 56.0, 7.8, 62, 7.8, 0.0),
            8: (26.0, 16.0, None, 7.0, 52.0, 7.2, 64, 6.8, 0.0),
            9: (22.0, 12.8, None, 7.5, 48.0, 5.8, 70, 5.0, 0.0),
            10: (16.8, 9.5, None, 9.0, 58.0, 4.0, 77, 3.0, 0.0),
            11: (11.0, 5.2, None, 10.0, 56.0, 2.4, 82, 1.5, 0.0),
            12: (8.0, 3.0, None, 10.5, 60.0, 1.8, 83, 1.0, 0.0),
        },
    },
    "MAD": {
        "latitude": 40.4983,
        "longitude": -3.5676,
        "climate_zone_label_he": "בירת ספרד; תרבות ושופינג, פארק וורנר מדריד והרי גואדרמה",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 1.06,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "פארק רטירו, גראן ויה, הפראדו והארמון המלכותי",
            "FAMILY_ATTRACTIONS_PARKS": "פארק וורנר מדריד (Parque Warner) ו-Parque de Atracciones",
            "NATURE_TRIP": "הפארק הלאומי הרי גואדרמה וטולדו",
        },
        "monthly": {
            1: (10.2, 2.0, None, 5.5, 34.0, 5.2, 70, 2.5, 0.0),
            2: (12.5, 3.2, None, 5.0, 32.0, 6.2, 64, 3.8, 0.0),
            3: (16.2, 5.8, None, 5.5, 30.0, 7.2, 56, 5.5, 0.0),
            4: (19.5, 8.5, None, 6.0, 45.0, 8.2, 54, 7.0, 0.0),
            5: (24.2, 12.2, None, 6.0, 44.0, 9.4, 48, 8.5, 0.0),
            6: (30.2, 17.2, None, 3.0, 20.0, 11.0, 40, 9.8, 0.0),
            7: (34.2, 20.5, None, 1.5, 10.0, 12.0, 34, 10.2, 0.0),
            8: (33.5, 20.2, None, 1.8, 12.0, 11.2, 36, 9.2, 0.0),
            9: (28.0, 16.0, None, 3.5, 28.0, 9.0, 46, 7.0, 0.0),
            10: (21.2, 11.0, None, 6.5, 56.0, 6.8, 60, 4.8, 0.0),
            11: (14.5, 5.8, None, 6.5, 54.0, 5.4, 68, 3.0, 0.0),
            12: (10.8, 2.8, None, 6.0, 44.0, 4.8, 72, 2.2, 0.0),
        },
    },
    "BCN": {
        "latitude": 41.2974,
        "longitude": 2.0833,
        "climate_zone_label_he": "חוף ים-תיכוני מערבי; ברצלונה, קוסטה בראווה, PortAventura והפירנאים",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 1.06,
        "theme_park_tier": 1.08,
        "is_ski_accessible": True,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "חופי ברצלונטה ומפרצי קוסטה בראווה",
            "FAMILY_ATTRACTIONS_PARKS": "פורט אוונטורה (PortAventura World) ו-Ferrari Land",
            "NATURE_TRIP": "הר מונסראט, קוסטה בראווה והרי הפירנאים",
            "SNOW_AND_SKI": "אתרי הסקי באנדורה (Grandvalira) והפירנאים",
        },
        "monthly": {
            1: (13.8, 6.5, 13.8, 4.5, 38.0, 5.0, 68, 2.5, 0.80),
            2: (14.5, 7.0, 13.5, 4.5, 35.0, 5.8, 67, 3.5, 0.82),
            3: (16.8, 9.0, 14.0, 5.0, 42.0, 6.8, 66, 5.2, 0.68),
            4: (19.2, 11.5, 15.5, 5.5, 48.0, 7.6, 66, 6.8, 0.25),
            5: (22.8, 15.0, 18.2, 5.0, 46.0, 8.8, 66, 8.2, 0.0),
            6: (26.8, 19.2, 22.0, 3.5, 30.0, 9.8, 64, 9.2, 0.0),
            7: (29.2, 22.0, 25.0, 2.5, 22.0, 10.4, 64, 9.5, 0.0),
            8: (29.5, 22.2, 26.0, 3.5, 35.0, 9.6, 66, 8.5, 0.0),
            9: (26.2, 19.2, 24.2, 5.5, 72.0, 7.8, 68, 6.5, 0.0),
            10: (22.2, 15.2, 21.2, 6.5, 82.0, 6.2, 71, 4.5, 0.0),
            11: (17.2, 10.2, 17.5, 5.5, 56.0, 5.2, 70, 3.0, 0.15),
            12: (14.5, 7.5, 15.0, 4.5, 40.0, 4.6, 69, 2.0, 0.72),
        },
    },
    "AMS": {
        "latitude": 52.3105,
        "longitude": 4.7683,
        "climate_zone_label_he": "אקלים ימי ממוזג; תעלות ומוזיאונים, פארק אפטלינג (Efteling) וכפרי הולנד",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.05,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "FAMILY_ATTRACTIONS_PARKS": "פארק האגדות אפטלינג (Efteling), וואליבי וחיטהורן",
            "URBAN_CULTURE": "תעלות אמסטרדם, מוזיאון NEMO לילדים ורייקסמוזיאום",
            "NATURE_TRIP": "גני קוקנהוף (באביב), זאנסה סכאנס ושמורת הוחה פלואה",
        },
        "monthly": {
            1: (6.2, 1.2, None, 12.0, 66.0, 2.0, 84, 1.0, 0.0),
            2: (7.0, 1.5, None, 10.0, 52.0, 3.0, 80, 1.8, 0.0),
            3: (10.5, 3.5, None, 10.0, 55.0, 4.5, 75, 3.2, 0.0),
            4: (14.5, 6.2, None, 8.5, 42.0, 6.5, 69, 4.8, 0.0),
            5: (18.2, 9.8, None, 9.0, 55.0, 7.4, 68, 6.2, 0.0),
            6: (21.0, 12.8, None, 9.0, 65.0, 7.2, 70, 6.8, 0.0),
            7: (23.0, 14.8, None, 9.0, 75.0, 7.4, 71, 6.8, 0.0),
            8: (22.8, 14.5, None, 9.5, 82.0, 6.8, 72, 5.8, 0.0),
            9: (19.5, 12.0, None, 10.0, 78.0, 5.2, 76, 4.2, 0.0),
            10: (15.0, 8.5, None, 11.5, 84.0, 3.8, 81, 2.5, 0.0),
            11: (10.0, 4.8, None, 13.0, 82.0, 2.2, 85, 1.2, 0.0),
            12: (7.0, 2.0, None, 12.5, 76.0, 1.7, 86, 0.8, 0.0),
        },
    },
    "BKK": {
        "latitude": 13.6900,
        "longitude": 100.7501,
        "climate_zone_label_he": "טרופי; בנגקוק, ריזורטים ב-Hua Hin / Pattaya ושמורת קנצ'נבורי",
        "coastal_tier": "COASTAL_OR_LAKE_ACCESS",
        "coastal_factor": 0.82,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.04,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "ריזורטי חוף בהואה הין (Hua Hin) וקו סאמט",
            "URBAN_CULTURE": "ארמון המלך, שווקים צפים וקניוני הענק של בנגקוק",
            "NATURE_TRIP": "מפלי ארוואן ושמורת קנצ'נבורי",
        },
        "monthly": {
            1: (32.2, 22.5, 27.5, 1.5, 12.0, 8.6, 66, 10.0, 0.0),
            2: (33.2, 24.0, 28.0, 2.0, 18.0, 8.5, 68, 11.0, 0.0),
            3: (34.5, 25.5, 29.0, 3.5, 35.0, 8.4, 70, 12.0, 0.0),
            4: (35.5, 26.5, 30.0, 6.0, 68.0, 8.2, 71, 12.0, 0.0),
            5: (34.5, 26.2, 30.2, 15.0, 195.0, 6.5, 75, 11.5, 0.0),
            6: (33.5, 25.8, 29.8, 15.0, 155.0, 5.8, 76, 11.0, 0.0),
            7: (33.0, 25.5, 29.2, 16.0, 165.0, 5.5, 77, 11.0, 0.0),
            8: (32.8, 25.5, 29.0, 17.0, 195.0, 5.2, 78, 11.0, 0.0),
            9: (32.2, 25.0, 28.8, 19.0, 310.0, 5.0, 81, 10.5, 0.0),
            10: (32.0, 24.5, 28.5, 15.0, 230.0, 6.0, 79, 10.0, 0.0),
            11: (32.0, 23.5, 28.0, 5.0, 48.0, 7.8, 72, 9.5, 0.0),
            12: (31.8, 22.0, 27.5, 1.5, 12.0, 8.6, 66, 9.5, 0.0),
        },
    },
    "NRT": {
        "latitude": 35.7720,
        "longitude": 140.3929,
        "climate_zone_label_he": "סובטרופי ממוזג; טוקיו דיסני, פריחת הדובדבן, הר פוג'י והאקונה",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "FAMILY_ATTRACTIONS_PARKS": "טוקיו דיסנילנד, DisneySea ו-TeamLab Planets",
            "URBAN_CULTURE": "שיבויה, שינג'וקו, אסאקוסה ותרבות יפנית",
            "NATURE_TRIP": "הר פוג'י, האקונה ושמורת ניקו (Nikko)",
        },
        "monthly": {
            1: (9.8, 1.5, 14.5, 5.0, 52.0, 6.2, 54, 3.0, 0.0),
            2: (10.8, 2.2, 14.0, 6.0, 56.0, 6.0, 56, 4.0, 0.0),
            3: (14.2, 5.2, 14.8, 9.0, 110.0, 5.8, 60, 5.5, 0.0),
            4: (19.0, 10.5, 16.5, 9.0, 120.0, 6.3, 64, 7.5, 0.0),
            5: (23.5, 15.2, 19.0, 10.0, 135.0, 6.2, 68, 8.5, 0.0),
            6: (26.2, 19.0, 21.8, 11.5, 165.0, 4.6, 75, 9.0, 0.0),
            7: (30.2, 23.0, 24.5, 10.0, 150.0, 5.4, 77, 10.0, 0.0),
            8: (31.5, 24.2, 26.2, 8.5, 145.0, 6.2, 75, 9.5, 0.0),
            9: (27.2, 20.5, 25.0, 11.0, 210.0, 4.8, 75, 7.5, 0.0),
            10: (21.8, 14.8, 22.5, 9.5, 185.0, 5.0, 69, 5.5, 0.0),
            11: (16.5, 9.0, 19.5, 7.0, 92.0, 5.4, 63, 3.5, 0.0),
            12: (12.0, 4.0, 16.5, 5.0, 55.0, 6.0, 56, 2.5, 0.0),
        },
    },
    "HKT": {
        "latitude": 8.1132,
        "longitude": 98.3169,
        "climate_zone_label_he": "אי טרופי בים אנדמן (עונה יבשה מושלמת בדצמבר–אפריל)",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.05,
        "urban_culture_affinity": 0.85,
        "theme_park_tier": 0.95,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "חופי קאטה, קארון, באנג טאו ואיי קו פי פי",
            "NATURE_TRIP": "מפרץ פאנג נגה (Phang Nga) ושמורת קאו סוק",
        },
        "monthly": {
            1: (32.0, 24.0, 28.2, 4.0, 35.0, 9.0, 70, 10.5, 0.0),
            2: (33.0, 24.5, 28.8, 3.0, 28.0, 9.2, 69, 11.5, 0.0),
            3: (33.5, 25.0, 29.2, 5.0, 58.0, 8.8, 71, 12.0, 0.0),
            4: (33.0, 25.0, 29.0, 8.0, 120.0, 8.5, 75, 12.0, 0.0),
            5: (31.8, 25.0, 29.5, 18.0, 295.0, 5.8, 80, 11.0, 0.0),
            6: (31.5, 25.0, 29.0, 18.0, 275.0, 5.5, 80, 10.5, 0.0),
            7: (31.0, 25.0, 28.5, 19.0, 305.0, 5.2, 81, 10.5, 0.0),
            8: (31.0, 25.0, 28.5, 19.0, 320.0, 5.2, 81, 10.5, 0.0),
            9: (30.5, 24.5, 28.5, 21.0, 385.0, 4.6, 83, 10.5, 0.0),
            10: (31.0, 24.5, 28.5, 19.0, 315.0, 5.5, 82, 10.0, 0.0),
            11: (31.2, 24.2, 28.5, 12.0, 175.0, 7.2, 77, 9.8, 0.0),
            12: (31.5, 24.0, 28.0, 5.0, 65.0, 8.8, 72, 10.0, 0.0),
        },
    },
    "JFK": {
        "latitude": 40.6413,
        "longitude": -73.7781,
        "climate_zone_label_he": "ניו יורק; ברודוויי, מוזיאונים, שופינג, אורות חורף ועמק ההדסון",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "URBAN_CULTURE": "מנהטן, סנטרל פארק, מופעי ברודוויי ומוזיאוני ניו יורק",
            "WINTER_FESTIVE": "עץ חג המולד ברוקפלר סנטר, החלקה על הקרח וחלונות הראווה בשדרה החמישית",
            "FAMILY_ATTRACTIONS_PARKS": "קניון ופארק American Dream ו-Six Flags Great Adventure",
        },
        "monthly": {
            1: (4.0, -2.5, 5.5, 8.0, 88.0, 5.0, 64, 2.0, 0.0),
            2: (5.5, -1.5, 4.5, 7.5, 78.0, 5.8, 62, 3.0, 0.0),
            3: (10.0, 2.5, 6.0, 9.0, 102.0, 6.8, 61, 4.8, 0.0),
            4: (16.2, 8.0, 9.5, 9.0, 100.0, 7.6, 60, 6.5, 0.0),
            5: (21.8, 13.5, 14.0, 9.0, 98.0, 8.4, 63, 8.0, 0.0),
            6: (26.8, 18.8, 19.0, 8.5, 98.0, 9.2, 65, 9.0, 0.0),
            7: (29.5, 21.8, 22.8, 8.0, 105.0, 9.6, 65, 9.5, 0.0),
            8: (28.8, 21.2, 23.5, 7.5, 102.0, 8.8, 66, 8.5, 0.0),
            9: (24.8, 17.2, 21.5, 6.5, 92.0, 7.8, 67, 6.5, 0.0),
            10: (18.5, 11.2, 17.5, 7.0, 95.0, 6.8, 65, 4.5, 0.0),
            11: (12.2, 5.5, 13.0, 7.5, 86.0, 5.4, 64, 2.5, 0.0),
            12: (6.8, 0.5, 8.5, 8.5, 96.0, 4.6, 65, 1.8, 0.0),
        },
    },
    "EWR": {
        "latitude": 40.6895,
        "longitude": -74.1745,
        "climate_zone_label_he": "מטרופולין ניו יורק וניו ג'רזי; פארק American Dream, מנהטן ושופינג",
        "coastal_tier": "INLAND_URBAN",
        "coastal_factor": 0.60,
        "nature_affinity_factor": 0.90,
        "urban_culture_affinity": 1.08,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": True,
        "highlights_by_type_he": {
            "FAMILY_ATTRACTIONS_PARKS": "פארק Nickelodeon Universe ופארק המים המקורה ב-American Dream",
            "URBAN_CULTURE": "מנהטן, ברודוויי ואאוטלט Jersey Gardens",
        },
        "monthly": {
            1: (4.2, -2.5, 5.5, 8.0, 88.0, 5.0, 64, 2.0, 0.0),
            2: (5.8, -1.5, 4.5, 7.5, 78.0, 5.8, 62, 3.0, 0.0),
            3: (10.5, 2.5, 6.0, 9.0, 102.0, 6.8, 61, 4.8, 0.0),
            4: (16.8, 8.0, 9.5, 9.0, 100.0, 7.6, 60, 6.5, 0.0),
            5: (22.2, 13.5, 14.0, 9.0, 98.0, 8.4, 63, 8.0, 0.0),
            6: (27.2, 18.8, 19.0, 8.5, 98.0, 9.2, 65, 9.0, 0.0),
            7: (30.0, 21.8, 22.8, 8.0, 105.0, 9.6, 65, 9.5, 0.0),
            8: (29.2, 21.2, 23.5, 7.5, 102.0, 8.8, 66, 8.5, 0.0),
            9: (25.0, 17.2, 21.5, 6.5, 92.0, 7.8, 67, 6.5, 0.0),
            10: (18.8, 11.2, 17.5, 7.0, 95.0, 6.8, 65, 4.5, 0.0),
            11: (12.5, 5.5, 13.0, 7.5, 86.0, 5.4, 64, 2.5, 0.0),
            12: (7.0, 0.5, 8.5, 8.5, 96.0, 4.6, 65, 1.8, 0.0),
        },
    },
    "MIA": {
        "latitude": 25.7959,
        "longitude": -80.2870,
        "climate_zone_label_he": "טרופי אטלנטי; חופי מיאמי ביץ', הפלורידה קיז, אוורגליידס ופארקי פלורידה",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 0.98,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "סאות' ביץ', סאני איילז והפלורידה קיז (Key West)",
            "NATURE_TRIP": "הפארק הלאומי אוורגליידס ושמורת ביסקיין",
            "FAMILY_ATTRACTIONS_PARKS": "גישה לפארקי אורלנדו ואטרקציות דרום פלורידה",
        },
        "monthly": {
            1: (24.5, 16.5, 24.0, 5.0, 48.0, 7.5, 71, 6.5, 0.0),
            2: (25.5, 17.5, 24.2, 5.0, 52.0, 8.0, 70, 7.5, 0.0),
            3: (26.8, 19.0, 25.0, 5.5, 62.0, 8.8, 69, 9.0, 0.0),
            4: (28.5, 21.0, 25.5, 6.0, 80.0, 9.5, 68, 10.0, 0.0),
            5: (30.2, 23.2, 27.2, 10.0, 145.0, 9.2, 71, 10.5, 0.0),
            6: (31.5, 25.0, 28.8, 15.0, 235.0, 8.5, 75, 11.0, 0.0),
            7: (32.2, 25.8, 29.8, 14.0, 170.0, 9.2, 74, 11.0, 0.0),
            8: (32.5, 25.8, 30.0, 16.0, 215.0, 8.8, 75, 10.5, 0.0),
            9: (31.5, 25.2, 29.2, 16.0, 240.0, 7.8, 77, 9.5, 0.0),
            10: (29.5, 23.2, 27.8, 11.0, 155.0, 7.6, 74, 8.0, 0.0),
            11: (27.0, 20.2, 26.0, 6.5, 78.0, 7.4, 72, 6.5, 0.0),
            12: (25.5, 17.5, 24.5, 5.0, 52.0, 7.5, 71, 6.0, 0.0),
        },
    },
    "FLL": {
        "latitude": 26.0742,
        "longitude": -80.1506,
        "climate_zone_label_he": "טרופי אטלנטי; פורט לודרדייל, בוקה רטון, חופי דרום פלורידה ואורלנדו",
        "coastal_tier": "PRIMARY_BEACH_RESORT",
        "coastal_factor": 1.00,
        "nature_affinity_factor": 1.00,
        "urban_culture_affinity": 0.96,
        "theme_park_tier": 1.08,
        "is_ski_accessible": False,
        "has_winter_festive_markets": False,
        "highlights_by_type_he": {
            "BEACH_AND_POOL": "חופי פורט לודרדייל, הוליווד ביץ' ובוקה רטון",
            "FAMILY_ATTRACTIONS_PARKS": "נסיעה ישירה לפארקי אורלנדו (Disney World / Universal) וקניון Sawgrass Mills",
        },
        "monthly": {
            1: (24.2, 16.2, 23.8, 5.0, 50.0, 7.5, 71, 6.5, 0.0),
            2: (25.2, 17.2, 24.0, 5.0, 54.0, 8.0, 70, 7.5, 0.0),
            3: (26.5, 18.8, 24.8, 5.5, 65.0, 8.8, 69, 9.0, 0.0),
            4: (28.2, 20.8, 25.5, 6.0, 82.0, 9.5, 68, 10.0, 0.0),
            5: (30.0, 23.0, 27.0, 10.0, 148.0, 9.2, 71, 10.5, 0.0),
            6: (31.2, 24.8, 28.5, 15.0, 238.0, 8.5, 75, 11.0, 0.0),
            7: (32.0, 25.5, 29.5, 14.0, 172.0, 9.2, 74, 11.0, 0.0),
            8: (32.2, 25.5, 29.8, 16.0, 218.0, 8.8, 75, 10.5, 0.0),
            9: (31.2, 25.0, 29.0, 16.0, 242.0, 7.8, 77, 9.5, 0.0),
            10: (29.2, 23.0, 27.5, 11.0, 158.0, 7.6, 74, 8.0, 0.0),
            11: (26.8, 20.0, 25.8, 6.5, 80.0, 7.4, 72, 6.5, 0.0),
            12: (25.2, 17.2, 24.5, 5.0, 54.0, 7.5, 71, 6.0, 0.0),
        },
    },
}


def _attach_climate_profiles_to_destination_catalog() -> None:
    """Attach `climate_profile` and 12-month `monthly_weather` norms to each entry in `DESTINATION_CATALOG`."""
    for iata, meta in DESTINATION_CATALOG.items():
        c_prof = _DESTINATION_CLIMATE_PROFILES.get(iata)
        if not c_prof:
            continue
        meta["climate_profile"] = {
            "latitude": c_prof["latitude"],
            "longitude": c_prof["longitude"],
            "climate_zone_label_he": c_prof["climate_zone_label_he"],
            "coastal_tier": c_prof["coastal_tier"],
            "coastal_factor": c_prof["coastal_factor"],
            "nature_affinity_factor": c_prof["nature_affinity_factor"],
            "urban_culture_affinity": c_prof["urban_culture_affinity"],
            "theme_park_tier": c_prof["theme_park_tier"],
            "is_ski_accessible": c_prof["is_ski_accessible"],
            "has_winter_festive_markets": c_prof["has_winter_festive_markets"],
            "highlights_by_type_he": dict(c_prof.get("highlights_by_type_he") or {}),
        }
        monthly_dict: dict[int, dict[str, Any]] = {}
        for m, tup in c_prof["monthly"].items():
            monthly_dict[int(m)] = {
                "month": int(m),
                "avg_max_temp_c": float(tup[0]),
                "avg_min_temp_c": float(tup[1]),
                "sea_water_temp_c": float(tup[2]) if tup[2] is not None else None,
                "avg_rain_days": float(tup[3]),
                "precipitation_mm": float(tup[4]),
                "sunshine_hours_per_day": float(tup[5]),
                "avg_humidity_pct": int(tup[6]),
                "uv_index_max": float(tup[7]),
                "snow_reliability_index": float(tup[8]),
            }
        meta["monthly_weather"] = monthly_dict


_attach_climate_profiles_to_destination_catalog()


def build_default_family_profile() -> FamilyProfile:
    """Return the canonical pre-seeded household profile `משפחת בודובסקי`."""
    children = [
        ChildFramework(
            id="child-noa-1",
            family_profile_id="default-family-profile",
            child_name="נועה",
            child_age_years=5,
            birth_date=date(2021, 5, 14),
            passenger_Current_type="CHILD",
            framework_type=MoEFrameworkType.MUNICIPAL_GAN,
            education_stream="MAMLACHTI",
            school_week_days=6,
            holiday_extension_mode=HolidayExtensionMode.NITZANIM_FULL_WITH_JULY,
            treat_camp_as_vacation=True,
            max_school_days_missed=2,
            absence_penalty_weight=0.25,
            bagrut_blackout_dates=[],
        ),
        ChildFramework(
            id="child-ido-2",
            family_profile_id="default-family-profile",
            child_name="עידו",
            child_age_years=9,
            birth_date=date(2017, 9, 20),
            passenger_Current_type="CHILD",
            framework_type=MoEFrameworkType.ELEMENTARY_4_6,
            education_stream="MAMLACHTI",
            school_week_days=5,
            holiday_extension_mode=HolidayExtensionMode.NONE,
            treat_camp_as_vacation=True,
            max_school_days_missed=2,
            absence_penalty_weight=0.75,
            bagrut_blackout_dates=[],
        ),
        ChildFramework(
            id="child-maya-3",
            family_profile_id="default-family-profile",
            child_name="מאיה",
            child_age_years=13,
            birth_date=date(2013, 3, 10),
            passenger_Current_type="YOUTH",
            framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9,
            education_stream="MAMLACHTI",
            school_week_days=5,
            holiday_extension_mode=HolidayExtensionMode.NONE,
            treat_camp_as_vacation=True,
            max_school_days_missed=2,
            absence_penalty_weight=1.00,
            bagrut_blackout_dates=[],
        ),
    ]

    wallets = [
        PassengerLoyaltyWallet(
            id="wallet-adult1-elal",
            family_profile_id="default-family-profile",
            passenger_id="ADULT_1",
            passenger_name="יוני (הורה 1)",
            program_code=LoyaltyProgramCode.ELAL_MATMID,
            available_points=115000,
            can_pool_with_family=True,
            pool_group_id="FAMILY_POOL",
            transfer_ratio_to_airline=1.0,
            has_club_credit_card=True,
            companion_vouchers_count=1,
            point_valuation_cents=1.6,
        ),
        PassengerLoyaltyWallet(
            id="wallet-adult2-elal",
            family_profile_id="default-family-profile",
            passenger_id="ADULT_2",
            passenger_name="הורה 2",
            program_code=LoyaltyProgramCode.ELAL_MATMID,
            available_points=70000,
            can_pool_with_family=True,
            pool_group_id="FAMILY_POOL",
            transfer_ratio_to_airline=1.0,
            has_club_credit_card=True,
            companion_vouchers_count=0,
            point_valuation_cents=1.6,
        ),
        PassengerLoyaltyWallet(
            id="wallet-adult1-avios",
            family_profile_id="default-family-profile",
            passenger_id="ADULT_1",
            passenger_name="יוני (הורה 1)",
            program_code=LoyaltyProgramCode.BRITISH_AVIOS,
            available_points=65000,
            can_pool_with_family=True,
            pool_group_id="AVIOS_HOUSEHOLD",
            transfer_ratio_to_airline=1.0,
            has_club_credit_card=False,
            companion_vouchers_count=0,
            point_valuation_cents=1.5,
        ),
        PassengerLoyaltyWallet(
            id="wallet-adult1-amex",
            family_profile_id="default-family-profile",
            passenger_id="ADULT_1",
            passenger_name="יוני (הורה 1)",
            program_code=LoyaltyProgramCode.AMEX_MR_ISRAEL,
            available_points=80000,
            can_pool_with_family=True,
            pool_group_id="FAMILY_POOL",
            transfer_ratio_to_airline=1.0,
            has_club_credit_card=True,
            companion_vouchers_count=0,
            point_valuation_cents=1.5,
        ),
        PassengerLoyaltyWallet(
            id="wallet-adult2-fb",
            family_profile_id="default-family-profile",
            passenger_id="ADULT_2",
            passenger_name="הורה 2",
            program_code=LoyaltyProgramCode.FLYING_BLUE,
            available_points=55000,
            can_pool_with_family=True,
            pool_group_id="FB_FAMILY",
            transfer_ratio_to_airline=1.0,
            has_club_credit_card=False,
            companion_vouchers_count=0,
            point_valuation_cents=1.5,
        ),
        PassengerLoyaltyWallet(
            id="wallet-adult2-ua",
            family_profile_id="default-family-profile",
            passenger_id="ADULT_2",
            passenger_name="הורה 2",
            program_code=LoyaltyProgramCode.UNITED_MILEAGEPLUS,
            available_points=60000,
            can_pool_with_family=True,
            pool_group_id="UA_POOL",
            transfer_ratio_to_airline=1.0,
            has_club_credit_card=False,
            companion_vouchers_count=0,
            point_valuation_cents=1.5,
        ),
    ]

    return FamilyProfile(
        id="default-family-profile",
        profile_name="משפחת בודובסקי",
        adults_count=2,
        workweek_type="SUN_THU",
        erev_chag_pto_weight=0.5,
        chol_hamoed_pto_weight=0.5,
        annual_pto_budget=14.0,
        max_pto_per_trip=5.0,
        matmid_points_balance=185000,
        has_flycard=True,
        flycard_tier="FLY_CARD_PREMIUM",
        flycard_companion_vouchers=1,
        point_valuation_usd=0.016,
        preferred_currency="USD",
        children=children,
        passenger_loyalty_wallets=wallets,
    )


def expand_calendar_json_to_windows(calendar_doc: dict[str, Any]) -> list[MoEVacationWindow]:
    """Convert a MoE calendar JSON payload into `MoEVacationWindow` records across frameworks."""
    school_year = str(calendar_doc["school_year_gregorian"])
    year_slug = school_year.replace("-", "_")
    circular_ids = calendar_doc.get("circular_ids") or ["0363"]
    primary_circular = str(circular_ids[0])
    high_school_circular = str(circular_ids[-1])
    sync_source = str(calendar_doc.get("calendar_sync_source") or "OFFICIAL_MOE_CIRCULAR")
    frameworks_meta = calendar_doc.get("frameworks") or {}

    windows: list[MoEVacationWindow] = []
    for period in calendar_doc.get("periods") or []:
        holiday_code = str(period.get("holiday_code") or period["id"].upper())
        name_he = str(period["name_he"])
        name_en = str(period["name_en"])
        base_start = str(period["start_date"])
        base_end = str(period["end_date"])
        base_resume = str(period["resume_date"])
        parent_status = str(period.get("parent_workday_status") or "REGULAR_WORKDAY")
        overrides = period.get("framework_overrides") or {}
        nitzanim = period.get("nitzanim_window")
        tlv_restrictions = period.get("tlv_airport_restrictions") or []
        tlv_closed = bool(tlv_restrictions)

        for fw in period.get("applies_to_frameworks") or []:
            fw_override = overrides.get(fw) or {}
            start_str = str(fw_override.get("start_date") or base_start)
            end_str = str(fw_override.get("end_date") or base_end)
            resume_str = str(fw_override.get("resume_date") or base_resume)

            fw_info = frameworks_meta.get(fw) or {}
            nitz_eligible = bool(fw_info.get("nitzanim_eligible", fw in ("MUNICIPAL_GAN", "ELEMENTARY_1_3")))
            is_nitz = bool(nitzanim and nitzanim.get("active") and nitz_eligible)
            nitz_start = str(nitzanim["start_date"]) if is_nitz and nitzanim.get("start_date") else None
            nitz_end = str(nitzanim["end_date"]) if is_nitz and nitzanim.get("end_date") else None

            circ = high_school_circular if fw == "HIGH_SCHOOL_10_12" else primary_circular
            win_id = f"{year_slug}_{holiday_code}_{fw}"
            windows.append(
                MoEVacationWindow(
                    id=win_id,
                    school_year=school_year,
                    circular_id=circ,
                    holiday_code=holiday_code,
                    holiday_name_he=name_he,
                    holiday_name_en=name_en,
                    framework_type=fw,
                    start_date=date.fromisoformat(start_str),
                    end_date=date.fromisoformat(end_str),
                    resumes_on_date=date.fromisoformat(resume_str),
                    is_covered_by_nitzanim=is_nitz,
                    nitzanim_start_date=date.fromisoformat(nitz_start) if nitz_start else None,
                    nitzanim_end_date=date.fromisoformat(nitz_end) if nitz_end else None,
                    parent_workday_status=parent_status,
                    tlv_airport_closed=tlv_closed,
                    calendar_sync_source=sync_source,
                    source_reference=f"MoE Circular {circ} ({school_year})",
                )
            )
    return windows


def load_bundled_moe_windows(school_years: Optional[list[str]] = None) -> list[MoEVacationWindow]:
    """Load pre-seeded MoE vacation windows from bundled JSON files."""
    file_map = {
        "2025-2026": CALENDARS_DIR / "moe_5786_2025_2026.json",
        "2026-2027": CALENDARS_DIR / "moe_5787_2026_2027.json",
        "2027-2028": CALENDARS_DIR / "moe_5788_2027_2028.json",
    }
    target_years = school_years or ["2025-2026", "2026-2027", "2027-2028"]
    all_windows: list[MoEVacationWindow] = []
    for sy in target_years:
        path = file_map.get(sy)
        if path and path.exists():
            with path.open("r", encoding="utf-8") as fh:
                doc = json.load(fh)
            all_windows.extend(expand_calendar_json_to_windows(doc))
    return all_windows


def _parse_hhmm_minutes(hhmm: str, default_hour: int = 8) -> int:
    parts = str(hhmm).strip().split(":")
    hour = int(parts[0]) if parts and parts[0].isdigit() else default_hour
    minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return hour * 60 + minute


def is_shabbat_blocked_for_elal(
    flight_date: date,
    departure_time_local: str,
    arrival_time_local: Optional[str] = None,
) -> bool:
    """Check if a date/time violates El Al / Sun d'Or Shabbat or Yom Kippur rules."""
    if flight_date in YOM_KIPPUR_CLOSED_DATES:
        return True
    weekday = flight_date.weekday()  # Mon=0 .. Fri=4, Sat=5, Sun=6
    dep_mins = _parse_hhmm_minutes(departure_time_local, default_hour=8)
    if weekday == 4:
        if dep_mins >= 14 * 60:
            return True
        if arrival_time_local is not None and str(arrival_time_local).strip():
            arr_mins = _parse_hhmm_minutes(arrival_time_local, default_hour=10)
            if arr_mins >= 14 * 60 or arr_mins < dep_mins:
                return True
    if weekday == 5 and dep_mins < 20 * 60 + 30:
        return True
    return False


def _make_bonus_row(
    dest_iata: str,
    flight_date: date,
    direction: str,
    econ_seats: int,
    prem_seats: int,
    biz_seats: int,
    flycard_promo: bool = False,
    fetched_iso: str = "",
    expires_iso: str = "",
    custom_flight_num: Optional[str] = None,
    custom_dep_time: Optional[str] = None,
    custom_arr_time: Optional[str] = None,
    custom_taxes_usd: Optional[float] = None,
    custom_econ_pts: Optional[int] = None,
    custom_prem_pts: Optional[int] = None,
    custom_biz_pts: Optional[int] = None,
) -> ElAlBonusAvailability:
    meta = DESTINATION_CATALOG[dest_iata]
    is_out = direction == "OUTBOUND"
    origin = "TLV" if is_out else dest_iata
    dest = dest_iata if is_out else "TLV"
    f_num = custom_flight_num or (meta["outbound_flight"] if is_out else meta["inbound_flight"])
    dep_time = custom_dep_time or (meta["dep_time_out"] if is_out else meta["dep_time_in"])
    arr_time = custom_arr_time or (meta["arr_time_out"] if is_out else meta["arr_time_in"])

    # If flight falls on Saturday daytime, shift departure time to Motzei Shabbat 21:45
    if flight_date.weekday() == 5:
        hour = int(dep_time.split(":")[0])
        if hour < 21:
            dep_time = "21:45"
            arr_time = "01:15"
    elif flight_date.weekday() == 4:
        dep_mins = _parse_hhmm_minutes(dep_time, default_hour=7)
        arr_mins = _parse_hhmm_minutes(arr_time, default_hour=10)
        if dep_mins >= 14 * 60 or arr_mins >= 14 * 60 or arr_mins < dep_mins:
            dep_time = "06:30"
            arr_time = "11:15"

    econ_pts = custom_econ_pts if custom_econ_pts is not None else int(meta["economy_points"])
    prem_pts = custom_prem_pts if custom_prem_pts is not None else int(meta["premium_points"])
    biz_pts = custom_biz_pts if custom_biz_pts is not None else int(meta["business_points"])
    if flycard_promo:
        econ_pts = max(3750, econ_pts // 2)

    taxes = (
        custom_taxes_usd
        if custom_taxes_usd is not None
        else float(meta["outbound_taxes_usd"] if is_out else meta["inbound_taxes_usd"])
    )

    if meta["aircraft_type"] == "738" and custom_flight_num is None:
        prem_seats = 0
    if prem_seats > 0 and prem_pts <= 0:
        prem_pts = 18000 if meta.get("award_zone") == "ZONE_A" else 22000

    return ElAlBonusAvailability(
        id=f"{f_num}_{flight_date.isoformat()}",
        origin_iata=origin,
        destination_iata=dest,
        direction=direction,
        flight_number=f_num,
        operating_carrier=str(meta["operating_carrier"]),
        flight_date=flight_date,
        departure_time_local=dep_time,
        arrival_time_local=arr_time,
        aircraft_type=str(meta["aircraft_type"]),
        economy_award_seats=econ_seats,
        economy_seats_is_two_plus=econ_seats >= 2,
        economy_rbd_code="E",
        premium_award_seats=prem_seats,
        premium_seats_is_two_plus=prem_seats >= 2,
        premium_rbd_code="P",
        business_award_seats=biz_seats,
        business_seats_is_two_plus=biz_seats >= 2,
        business_rbd_code="I",
        award_zone=str(meta["award_zone"]),
        economy_points_per_pax=econ_pts,
        premium_points_per_pax=prem_pts if prem_pts > 0 else None,
        business_points_per_pax=biz_pts if biz_pts > 0 else None,
        flycard_promo_active=flycard_promo,
        taxes_usd_per_pax=taxes,
        source_url="https://www.elal.com/rbddataclients/",
        fetched_at=fetched_iso,
        expires_at=expires_iso,
    )


def build_seeded_elal_bonus_availability(
    ttl_seconds: int = 14400,
) -> list[ElAlBonusAvailability]:
    """Generate the rich 2025-2028 El Al Classic Award dataset across Zones A-E."""
    now_dt = datetime.now(UTC).replace(microsecond=0)
    fetched_iso = now_dt.isoformat().replace("+00:00", "Z")
    expires_iso = (
        (now_dt + timedelta(seconds=max(ttl_seconds, 86400)))
        .isoformat()
        .replace("+00:00", "Z")
    )

    rows_by_id: dict[str, ElAlBonusAvailability] = {}

    def _add(row: ElAlBonusAvailability) -> None:
        if row.flight_date in YOM_KIPPUR_CLOSED_DATES:
            return
        rows_by_id[row.id] = row

    # 1. Holiday Date Pairings Across 2025-2028 (Outbound Dates, Return Dates, Destinations)
    holiday_clusters: list[tuple[list[date], list[date], list[str]]] = [
        # Rosh Hashanah 2025 (תשפ"ו)
        (
            [date(2025, 9, 19), date(2025, 9, 21)],
            [date(2025, 9, 24), date(2025, 9, 25)],
            ["ATH", "LCA", "RHO", "FCO", "VIE", "BUD", "PRG"],
        ),
        # Sukkot 2025 (תשפ"ו — starting after Oct 1-2 Yom Kippur shutdown)
        (
            [date(2025, 10, 3), date(2025, 10, 5), date(2025, 10, 6), date(2025, 10, 7)],
            [date(2025, 10, 12), date(2025, 10, 13), date(2025, 10, 14), date(2025, 10, 15)],
            ["FCO", "MXP", "ATH", "LCA", "RHO", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "AMS", "MAD", "BCN", "BKK", "JFK", "EWR"],
        ),
        # Hanukkah 2025 (תשפ"ו)
        (
            [date(2025, 12, 15), date(2025, 12, 16), date(2025, 12, 17)],
            [date(2025, 12, 21), date(2025, 12, 22), date(2025, 12, 23)],
            ["ATH", "FCO", "MXP", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "MAD", "BCN", "AMS"],
        ),
        # Purim 2026 (תשפ"ו)
        (
            [date(2026, 3, 2), date(2026, 3, 3)],
            [date(2026, 3, 6), date(2026, 3, 7), date(2026, 3, 8)],
            ["ATH", "LCA", "FCO", "VIE", "BUD", "PRG", "BER", "LTN"],
        ),
        # Pesach 2026 (תשפ"ו)
        (
            [date(2026, 3, 22), date(2026, 3, 24), date(2026, 3, 25), date(2026, 3, 30), date(2026, 3, 31), date(2026, 4, 1)],
            [date(2026, 3, 30), date(2026, 3, 31), date(2026, 4, 6), date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)],
            ["FCO", "MXP", "ATH", "LCA", "RHO", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "AMS", "MAD", "BCN", "BKK", "NRT", "JFK", "EWR", "MIA"],
        ),
        # Yom HaAtzmaut & Lag BaOmer 2026 (תשפ"ו)
        (
            [date(2026, 4, 21), date(2026, 4, 22), date(2026, 5, 3), date(2026, 5, 4)],
            [date(2026, 4, 25), date(2026, 4, 26), date(2026, 5, 7), date(2026, 5, 8)],
            ["ATH", "LCA", "RHO", "PFO", "FCO", "BUD", "PRG"],
        ),
        # Shavuot 2026 (תשפ"ו)
        (
            [date(2026, 5, 20), date(2026, 5, 21)],
            [date(2026, 5, 24), date(2026, 5, 25)],
            ["ATH", "LCA", "RHO", "PFO", "FCO", "VIE", "BUD"],
        ),
        # Summer June 20-30 Arbitrage 2026 (תשפ"ו — Jun 18/19 start)
        (
            [date(2026, 6, 18), date(2026, 6, 19), date(2026, 6, 21), date(2026, 6, 22)],
            [date(2026, 6, 25), date(2026, 6, 26), date(2026, 6, 28), date(2026, 6, 29), date(2026, 6, 30)],
            ["MAD", "BCN", "FCO", "MXP", "ATH", "LCA", "RHO", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "AMS"],
        ),
        # Summer July & August 2026 (תשפ"ו)
        (
            [date(2026, 7, 2), date(2026, 7, 5), date(2026, 7, 12), date(2026, 7, 19), date(2026, 8, 2), date(2026, 8, 9), date(2026, 8, 16), date(2026, 8, 20)],
            [date(2026, 7, 9), date(2026, 7, 12), date(2026, 7, 19), date(2026, 7, 26), date(2026, 8, 9), date(2026, 8, 16), date(2026, 8, 23), date(2026, 8, 27), date(2026, 8, 30)],
            list(DESTINATION_CATALOG.keys()),
        ),
        # Rosh Hashanah 2026 (תשפ"ז)
        (
            [date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 11)],
            [date(2026, 9, 13), date(2026, 9, 14), date(2026, 9, 15)],
            ["ATH", "LCA", "RHO", "PFO", "FCO", "VIE", "BUD", "PRG"],
        ),
        # Ex 1: Kippur-Sukkot Mega-Bridge 2026 (תשפ"ז — after Sep 20-21 Yom Kippur shutdown)
        (
            [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27)],
            [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 5)],
            list(DESTINATION_CATALOG.keys()),
        ),
        # Ex 2 & Option B: Hanukkah 2026 (תשפ"ז)
        (
            [date(2026, 12, 4), date(2026, 12, 6), date(2026, 12, 7), date(2026, 12, 8), date(2026, 12, 10)],
            [date(2026, 12, 10), date(2026, 12, 11), date(2026, 12, 12), date(2026, 12, 13), date(2026, 12, 14)],
            ["ATH", "FCO", "MXP", "LCA", "RHO", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "AMS", "MAD", "BCN", "BKK", "JFK", "EWR", "MIA"],
        ),
        # Ex 3: Purim Long-Weekend Bridge 2027 (תשפ"ז)
        (
            [date(2027, 3, 21), date(2027, 3, 22), date(2027, 3, 23), date(2027, 3, 24)],
            [date(2027, 3, 26), date(2027, 3, 27), date(2027, 3, 28)],
            ["ATH", "LCA", "RHO", "FCO", "MXP", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "MAD", "BCN"],
        ),
        # Ex 4 & Option A: Pesach 2027 (תשפ"ז — Pre-Pesach Shoulder + Nitzanim Week + Uncovered Week)
        (
            [
                date(2027, 4, 11),
                date(2027, 4, 12),
                date(2027, 4, 13),
                date(2027, 4, 14),
                date(2027, 4, 15),
                date(2027, 4, 18),
                date(2027, 4, 19),
                date(2027, 4, 20),
                date(2027, 4, 21),
                date(2027, 4, 22),
            ],
            [
                date(2027, 4, 18),
                date(2027, 4, 19),
                date(2027, 4, 20),
                date(2027, 4, 25),
                date(2027, 4, 26),
                date(2027, 4, 27),
                date(2027, 4, 28),
                date(2027, 4, 29),
            ],
            list(DESTINATION_CATALOG.keys()),
        ),
        # Yom HaAtzmaut 2027 (תשפ"ז)
        (
            [date(2027, 5, 10), date(2027, 5, 11), date(2027, 5, 12)],
            [date(2027, 5, 15), date(2027, 5, 16)],
            ["ATH", "LCA", "RHO", "PFO", "FCO", "VIE", "BUD", "PRG"],
        ),
        # Ex 5: Shavuot Extended Weekend 2027 (תשפ"ז)
        (
            [date(2027, 6, 8), date(2027, 6, 9), date(2027, 6, 10)],
            [date(2027, 6, 12), date(2027, 6, 13), date(2027, 6, 14)],
            ["LCA", "ATH", "RHO", "PFO", "TBS", "FCO", "VIE", "BUD", "PRG"],
        ),
        # Ex 6 & Option C: June 20-30 Inter-Framework Arbitrage 2027 (תשפ"ז)
        (
            [date(2027, 6, 20), date(2027, 6, 21), date(2027, 6, 22), date(2027, 6, 23)],
            [date(2027, 6, 27), date(2027, 6, 28), date(2027, 6, 29), date(2027, 6, 30)],
            list(DESTINATION_CATALOG.keys()),
        ),
        # Summer July & August 2027 (תשפ"ז)
        (
            [date(2027, 7, 1), date(2027, 7, 4), date(2027, 7, 11), date(2027, 7, 18), date(2027, 7, 22), date(2027, 8, 1), date(2027, 8, 8), date(2027, 8, 15), date(2027, 8, 17), date(2027, 8, 22)],
            [date(2027, 7, 8), date(2027, 7, 11), date(2027, 7, 18), date(2027, 7, 25), date(2027, 7, 29), date(2027, 8, 8), date(2027, 8, 15), date(2027, 8, 22), date(2027, 8, 24), date(2027, 8, 29), date(2027, 8, 31)],
            list(DESTINATION_CATALOG.keys()),
        ),
        # School Year 2027-2028 (תשפ"ח — Rosh Hashanah, Sukkot, Hanukkah, Purim, Pesach 2028, Shavuot, Summer 2028)
        (
            [
                date(2027, 9, 30),
                date(2027, 10, 12),
                date(2027, 10, 14),
                date(2027, 12, 24),
                date(2027, 12, 26),
                date(2028, 3, 10),
                date(2028, 3, 12),
                date(2028, 4, 2),
                date(2028, 4, 4),
                date(2028, 4, 9),
                date(2028, 4, 10),
                date(2028, 5, 30),
                date(2028, 6, 21),
                date(2028, 7, 2),
                date(2028, 8, 10),
                date(2028, 8, 16),
            ],
            [
                date(2027, 10, 4),
                date(2027, 10, 21),
                date(2027, 10, 23),
                date(2027, 10, 24),
                date(2027, 12, 31),
                date(2028, 1, 2),
                date(2028, 3, 15),
                date(2028, 4, 9),
                date(2028, 4, 16),
                date(2028, 4, 17),
                date(2028, 4, 18),
                date(2028, 6, 3),
                date(2028, 6, 28),
                date(2028, 7, 9),
                date(2028, 8, 17),
                date(2028, 8, 24),
                date(2028, 8, 29),
            ],
            ["FCO", "MXP", "ATH", "LCA", "RHO", "VIE", "BUD", "PRG", "BER", "CDG", "LHR", "LTN", "AMS", "MAD", "BCN", "BKK", "NRT", "JFK", "EWR", "MIA"],
        ),
    ]

    for out_dates, in_dates, dests in holiday_clusters:
        for dest in dests:
            for d_out in out_dates:
                is_tue = d_out.weekday() == 1
                _add(
                    _make_bonus_row(
                        dest_iata=dest,
                        flight_date=d_out,
                        direction="OUTBOUND",
                        econ_seats=2,
                        prem_seats=2,
                        biz_seats=2,
                        flycard_promo=is_tue,
                        fetched_iso=fetched_iso,
                        expires_iso=expires_iso,
                    )
                )
            for d_in in in_dates:
                is_tue = d_in.weekday() == 1
                _add(
                    _make_bonus_row(
                        dest_iata=dest,
                        flight_date=d_in,
                        direction="INBOUND",
                        econ_seats=2,
                        prem_seats=2,
                        biz_seats=2,
                        flycard_promo=is_tue,
                        fetched_iso=fetched_iso,
                        expires_iso=expires_iso,
                    )
                )

    # 2. Explicit Canonical Benchmark Overrides (Options A, B, C, Open-Jaw MXP/FCO, Peak Return 0-Seat Cash&Points)
    # Option A: Rome (FCO) Pre-Pesach Shoulder Bridge (2027-04-11 -> 2027-04-18)
    _add(
        _make_bonus_row(
            dest_iata="FCO",
            flight_date=date(2027, 4, 11),
            direction="OUTBOUND",
            econ_seats=2,
            prem_seats=2,
            biz_seats=0,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY381",
            custom_dep_time="07:15",
            custom_arr_time="10:00",
            custom_taxes_usd=48.75,
            custom_econ_pts=15000,
            custom_prem_pts=20500,
            custom_biz_pts=45000,
        )
    )
    _add(
        _make_bonus_row(
            dest_iata="FCO",
            flight_date=date(2027, 4, 18),
            direction="INBOUND",
            econ_seats=2,
            prem_seats=1,
            biz_seats=2,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY384",
            custom_dep_time="21:45",
            custom_arr_time="02:10",
            custom_taxes_usd=48.75,
            custom_econ_pts=15000,
            custom_prem_pts=20500,
            custom_biz_pts=45000,
        )
    )

    # Option B: Athens (ATH) Hanukkah (2026-12-06 -> 2026-12-11)
    _add(
        _make_bonus_row(
            dest_iata="ATH",
            flight_date=date(2026, 12, 6),
            direction="OUTBOUND",
            econ_seats=2,
            prem_seats=0,
            biz_seats=2,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY541",
            custom_dep_time="08:00",
            custom_arr_time="10:15",
            custom_taxes_usd=38.75,
            custom_econ_pts=8500,
            custom_prem_pts=18000,
            custom_biz_pts=16000,
        )
    )
    _add(
        _make_bonus_row(
            dest_iata="ATH",
            flight_date=date(2026, 12, 11),
            direction="INBOUND",
            econ_seats=2,
            prem_seats=0,
            biz_seats=2,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY544",
            custom_dep_time="10:30",
            custom_arr_time="12:35",
            custom_taxes_usd=38.75,
            custom_econ_pts=8500,
            custom_prem_pts=18000,
            custom_biz_pts=16000,
        )
    )
    # Peak Saturday Hanukkah return 2026-12-12 has 0 award seats (triggers Strategy 5 CASH_AND_POINTS or Strategy 4)
    _add(
        _make_bonus_row(
            dest_iata="ATH",
            flight_date=date(2026, 12, 12),
            direction="INBOUND",
            econ_seats=0,
            prem_seats=0,
            biz_seats=0,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY544",
            custom_dep_time="21:45",
            custom_arr_time="23:50",
            custom_taxes_usd=38.75,
            custom_econ_pts=8500,
            custom_prem_pts=18000,
            custom_biz_pts=16000,
        )
    )

    # Option C: Madrid (MAD) June 20-30 Inter-Framework Arbitrage (2027-06-21 -> 2027-06-28)
    _add(
        _make_bonus_row(
            dest_iata="MAD",
            flight_date=date(2027, 6, 21),
            direction="OUTBOUND",
            econ_seats=2,
            prem_seats=2,
            biz_seats=1,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY395",
            custom_dep_time="06:30",
            custom_arr_time="10:55",
            custom_taxes_usd=51.25,
            custom_econ_pts=16250,
            custom_prem_pts=21250,
            custom_biz_pts=60000,
        )
    )
    _add(
        _make_bonus_row(
            dest_iata="MAD",
            flight_date=date(2027, 6, 28),
            direction="INBOUND",
            econ_seats=2,
            prem_seats=2,
            biz_seats=1,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY398",
            custom_dep_time="12:30",
            custom_arr_time="18:15",
            custom_taxes_usd=51.25,
            custom_econ_pts=16250,
            custom_prem_pts=21250,
            custom_biz_pts=60000,
        )
    )

    # Strategy 4 Canonical Open-Jaw / Asymmetric Mix: Milan (MXP) Outbound 2027-04-11 has 2+ Econ & 2+ Prem,
    # whereas MXP Inbound 2027-04-18 has 0 award seats (so user either returns from FCO on LY384 or buys OW cash)
    _add(
        _make_bonus_row(
            dest_iata="MXP",
            flight_date=date(2027, 4, 11),
            direction="OUTBOUND",
            econ_seats=2,
            prem_seats=2,
            biz_seats=1,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY387",
            custom_dep_time="07:50",
            custom_arr_time="10:55",
            custom_taxes_usd=48.75,
            custom_econ_pts=15000,
            custom_prem_pts=20500,
            custom_biz_pts=45000,
        )
    )
    _add(
        _make_bonus_row(
            dest_iata="MXP",
            flight_date=date(2027, 4, 18),
            direction="INBOUND",
            econ_seats=0,
            prem_seats=0,
            biz_seats=0,
            flycard_promo=False,
            fetched_iso=fetched_iso,
            expires_iso=expires_iso,
            custom_flight_num="LY388",
            custom_dep_time="12:15",
            custom_arr_time="17:05",
            custom_taxes_usd=48.75,
            custom_econ_pts=15000,
            custom_prem_pts=20500,
            custom_biz_pts=45000,
        )
    )

    return sorted(rows_by_id.values(), key=lambda r: (r.flight_date.isoformat(), r.flight_number))


def generate_commercial_flights_for_route(
    origin: str,
    destinations: list[str],
    departure_date: date,
    return_date: date,
    airline_selection_mode: str = "ALL_AIRLINES",
    include_sundor: bool = True,
    direct_only: bool = True,
) -> list[dict[str, Any]]:
    """Return seeded commercial flight offerings for a route and date pair."""
    if not destinations or "ANYWHERE" in [d.upper() for d in destinations]:
        target_dests = list(DESTINATION_CATALOG.keys())
    else:
        target_dests = [d.upper() for d in destinations if d.upper() in DESTINATION_CATALOG]
        if not target_dests:
            target_dests = ["FCO"]

    results: list[dict[str, Any]] = []
    for dest in target_dests:
        meta = DESTINATION_CATALOG[dest]
        carrier = str(meta["operating_carrier"])
        if carrier == "2U" and not include_sundor:
            continue

        # El Al / Sun d'Or flight offering (unless blocked by Shabbat or Yom Kippur)
        dep_time_out = str(meta["dep_time_out"])
        arr_time_out = str(meta["arr_time_out"])
        if departure_date.weekday() == 4 and is_shabbat_blocked_for_elal(
            departure_date, dep_time_out, arr_time_out
        ):
            dep_time_out = "06:30"
            arr_time_out = "11:15"

        dep_time_in = str(meta["dep_time_in"])
        arr_time_in = str(meta["arr_time_in"])
        if return_date.weekday() == 4 and is_shabbat_blocked_for_elal(
            return_date, dep_time_in, arr_time_in
        ):
            dep_time_in = "06:30"
            arr_time_in = "11:15"

        dep_blocked = is_shabbat_blocked_for_elal(
            departure_date, dep_time_out, arr_time_out
        )
        ret_blocked = is_shabbat_blocked_for_elal(
            return_date, dep_time_in, arr_time_in
        )
        if not dep_blocked and not ret_blocked:
            results.append(
                {
                    "origin_iata": origin.upper(),
                    "destination_iata": dest,
                    "return_origin_iata": dest,
                    "destination_city_he": meta["city_he"],
                    "destination_city_en": meta["city_en"],
                    "departure_date": departure_date.isoformat(),
                    "return_date": return_date.isoformat(),
                    "primary_carrier_iata": carrier,
                    "is_elal_flight": True,
                    "outbound_flight_number": meta["outbound_flight"],
                    "inbound_flight_number": meta["inbound_flight"],
                    "departure_time_out": dep_time_out,
                    "arrival_time_out": arr_time_out,
                    "departure_time_in": dep_time_in,
                    "arrival_time_in": arr_time_in,
                    "aircraft_type": meta["aircraft_type"],
                    "duration_minutes": meta["duration_minutes"],
                    "is_direct": True,
                    "rt_cash_per_pax_usd": float(meta["rt_cash_per_pax_usd"]),
                    "supplemental_single_pax_cash_usd": float(
                        meta["supplemental_single_pax_cash_usd"]
                    ),
                    "five_pax_cash_benchmark_usd": float(
                        meta["five_pax_cash_benchmark_usd"]
                    ),
                    "outbound_taxes_usd": float(meta["outbound_taxes_usd"]),
                    "inbound_taxes_usd": float(meta["inbound_taxes_usd"]),
                    "includes_trolley": True,
                    "includes_checked_bag": True,
                }
            )

        if airline_selection_mode == "ALL_AIRLINES":
            if departure_date in YOM_KIPPUR_CLOSED_DATES or return_date in YOM_KIPPUR_CLOSED_DATES:
                continue
            for alt_carrier, out_num, in_num, base_rt_usd in meta.get("alt_carriers", []):
                is_lcc = alt_carrier in ("W6", "FR", "U2", "6H", "IZ")
                results.append(
                    {
                        "origin_iata": origin.upper(),
                        "destination_iata": dest,
                        "return_origin_iata": dest,
                        "destination_city_he": meta["city_he"],
                        "destination_city_en": meta["city_en"],
                        "departure_date": departure_date.isoformat(),
                        "return_date": return_date.isoformat(),
                        "primary_carrier_iata": alt_carrier,
                        "is_elal_flight": False,
                        "outbound_flight_number": out_num,
                        "inbound_flight_number": in_num,
                        "departure_time_out": "10:15",
                        "arrival_time_out": "13:20",
                        "departure_time_in": "14:35",
                        "arrival_time_in": "19:25",
                        "aircraft_type": "320",
                        "duration_minutes": meta["duration_minutes"],
                        "is_direct": True,
                        "rt_cash_per_pax_usd": float(base_rt_usd),
                        "supplemental_single_pax_cash_usd": float(base_rt_usd),
                        "five_pax_cash_benchmark_usd": float(meta["five_pax_cash_benchmark_usd"]),
                        "outbound_taxes_usd": 42.0,
                        "inbound_taxes_usd": 42.0,
                        "includes_trolley": not is_lcc,
                        "includes_checked_bag": not is_lcc,
                    }
                )
    return results

"""Domain models, Enums, and validation helpers for family_vacation_planner.

Implemented using Python 3.13 standard-library `@dataclass` and `(str, Enum)`
with `.to_dict()` / `.model_dump()` and `.from_dict()` / `.model_validate()`
methods for seamless SQLite, REST API, and Pydantic v2 interface compatibility.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Optional, Self


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_date(val: Any) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if "T" in s:
            s = s.split("T", 1)[0]
        return date.fromisoformat(s)
    raise ValueError(f"Cannot parse date from {val!r}")


def _parse_optional_date(val: Any) -> Optional[date]:
    if val is None or val == "":
        return None
    return _parse_date(val)


def _format_optional_date(val: Optional[date | str]) -> Optional[str]:
    if val is None or val == "":
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()[:10]
    return str(val)[:10]


def _parse_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val not in (0, 1):
            raise ValueError(f"Boolean integer flag must be 0 or 1, got {val!r}")
        return bool(val)
    if isinstance(val, str):
        lowered = val.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    raise ValueError(f"Invalid boolean value: {val!r}")


def _parse_json_list(val: Any, default: Optional[list[Any]] = None) -> list[Any]:
    if val is None:
        return list(default) if default is not None else []
    if isinstance(val, list):
        return list(val)
    if isinstance(val, tuple):
        return list(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return list(default) if default is not None else []
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return parsed
        raise ValueError(f"Expected JSON list, got {type(parsed).__name__}")
    raise ValueError(f"Cannot parse list from {val!r}")


def _parse_json_dict(val: Any, default: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if val is None:
        return dict(default) if default is not None else {}
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return dict(default) if default is not None else {}
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
    raise ValueError(f"Cannot parse dict from {val!r}")


class MoEFrameworkType(str, Enum):
    DAYCARE_SUPERVISED = "DAYCARE_SUPERVISED"
    MUNICIPAL_GAN = "MUNICIPAL_GAN"
    ELEMENTARY_1_3 = "ELEMENTARY_1_3"
    ELEMENTARY_4_6 = "ELEMENTARY_4_6"
    MIDDLE_SCHOOL_7_9 = "MIDDLE_SCHOOL_7_9"
    HIGH_SCHOOL_10_12 = "HIGH_SCHOOL_10_12"
    SPECIAL_ED = "SPECIAL_ED"
    RELIGIOUS_HAREDI = "RELIGIOUS_HAREDI"


class HolidayExtensionMode(str, Enum):
    NONE = "NONE"
    NITZANIM_CHAGIM_ONLY = "NITZANIM_CHAGIM_ONLY"
    NITZANIM_FULL_WITH_JULY = "NITZANIM_FULL_WITH_JULY"


class DateSelectionMode(str, Enum):
    SPECIFIC_DATES = "SPECIFIC_DATES"
    HOLIDAY_DIRECT_INTENT = "HOLIDAY_DIRECT_INTENT"


class AirlineSelectionMode(str, Enum):
    EL_AL_ONLY = "EL_AL_ONLY"
    ALL_AIRLINES = "ALL_AIRLINES"


class LoyaltyProgramCode(str, Enum):
    ELAL_MATMID = "ELAL_MATMID"
    BRITISH_AVIOS = "BRITISH_AVIOS"
    FLYING_BLUE = "FLYING_BLUE"
    UNITED_MILEAGEPLUS = "UNITED_MILEAGEPLUS"
    MILES_AND_MORE = "MILES_AND_MORE"
    DELTA_SKYMILES = "DELTA_SKYMILES"
    QANTAS_FREQUENT_FLYER = "QANTAS_FREQUENT_FLYER"
    AEGEAN_MILES_BONUS = "AEGEAN_MILES_BONUS"
    AMEX_MR_ISRAEL = "AMEX_MR_ISRAEL"
    ISRAELI_CC_TRAVEL_POINTS = "ISRAELI_CC_TRAVEL_POINTS"


class FulfillmentStrategy(str, Enum):
    FULL_BONUS_SAME_CABIN = "FULL_BONUS_SAME_CABIN"
    SPLIT_CABIN_BONUS = "SPLIT_CABIN_BONUS"
    HYBRID_BONUS_PLUS_CASH = "HYBRID_BONUS_PLUS_CASH"
    ONE_WAY_BONUS_ONE_WAY_CASH = "ONE_WAY_BONUS_ONE_WAY_CASH"
    CASH_AND_POINTS = "CASH_AND_POINTS"
    MULTI_CLUB_PER_PASSENGER_SPLIT = "MULTI_CLUB_PER_PASSENGER_SPLIT"
    COMMERCIAL_CASH_ONLY = "COMMERCIAL_CASH_ONLY"


# In which directions a result has at least one available bonus seat (derived from seats only).
BONUS_DIRECTION_COVERAGE_VALUES: tuple[str, ...] = (
    "BOTH_DIRECTIONS",
    "OUTBOUND_ONLY",
    "INBOUND_ONLY",
    "NONE",
)


class VacationType(str, Enum):
    ANY = "ANY"
    BEACH_AND_POOL = "BEACH_AND_POOL"
    NATURE_TRIP = "NATURE_TRIP"
    URBAN_CULTURE = "URBAN_CULTURE"
    FAMILY_ATTRACTIONS_PARKS = "FAMILY_ATTRACTIONS_PARKS"
    SNOW_AND_SKI = "SNOW_AND_SKI"
    WINTER_FESTIVE = "WINTER_FESTIVE"


class WeatherFilterMode(str, Enum):
    SOFT_PRIORITIZE = "SOFT_PRIORITIZE"
    HARD_THRESHOLD = "HARD_THRESHOLD"


VACATION_TYPES = tuple(v.value for v in VacationType)
WEATHER_FILTER_MODES = tuple(m.value for m in WeatherFilterMode)
DEFAULT_VACATION_TYPE_THRESHOLDS: dict[str, float] = {
    "ANY": 0.0,
    "BEACH_AND_POOL": 60.0,
    "NATURE_TRIP": 55.0,
    "URBAN_CULTURE": 45.0,
    "FAMILY_ATTRACTIONS_PARKS": 50.0,
    "SNOW_AND_SKI": 65.0,
    "WINTER_FESTIVE": 55.0,
}
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
    "BEACH_AND_POOL": "Beach & Pool Resort",
    "NATURE_TRIP": "Nature & Scenic Hiking",
    "URBAN_CULTURE": "Urban, Culture & Shopping",
    "FAMILY_ATTRACTIONS_PARKS": "Theme Parks & Family Attractions",
    "SNOW_AND_SKI": "Family Snow & Ski",
    "WINTER_FESTIVE": "European Winter Markets & Festive",
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


FLYCARD_TIERS = ("NONE", "FLY_CARD", "FLY_CARD_PREMIUM")
CURRENCIES = ("USD", "ILS", "EUR")
PASSENGER_FARE_TYPES = ("INFANT_LAP", "INFANT_SEAT", "CHILD", "YOUTH")
EDUCATION_STREAMS = ("MAMLACHTI", "MAMLACHTI_DATI", "CHAREDI", "SPECIAL_EDUCATION")
CALENDAR_SYNC_SOURCES = (
    "OFFICIAL_MOE_CIRCULAR",
    "AUTO_SYNCED_CIRCULAR",
    "HEBREW_RULE_PROJECTED",
    "USER_MUNICIPAL_OVERRIDE",
)
OVERLAP_POLICIES = (
    "STRICT_ALL_CHILDREN_OFF",
    "CAMP_ADJUSTED_INTERSECTION",
)
WINDOW_SET_TYPES = (
    "STRICT_INTERSECTION",
    "CAMP_ADJUSTED_INTERSECTION",
    "FRAMEWORK_DELTA_UNION",
    "SPECIFIC_USER_WINDOW",
)
DIRECT_HOLIDAY_CODES = (
    "PESACH",
    "SUKKOT",
    "YOM_KIPPUR_SUKKOT",
    "HANUKKAH",
    "ROSH_HASHANAH",
    "PURIM",
    "SHAVUOT",
    "YOM_HAATZMAUT",
    "LAG_BAOMER",
    "SUMMER_JUNE_20_30",
    "SUMMER_JULY",
    "SUMMER_AUGUST",
)


def classify_passenger_type(child_age_years: int, infant_seat: bool = False) -> str:
    """Classify child's airline fare category based on age in years (0-21)."""
    if not isinstance(child_age_years, int) or isinstance(child_age_years, bool):
        child_age_years = int(child_age_years)
    if child_age_years < 0 or child_age_years > 21:
        raise ValueError(f"child_age_years must be between 0 and 21, got {child_age_years}")
    if child_age_years < 2:
        return "INFANT_SEAT" if infant_seat else "INFANT_LAP"
    if child_age_years <= 11:
        return "CHILD"
    return "YOUTH"


def suggest_framework_for_age(child_age_years: int) -> str:
    """Suggest default Israeli MoE educational framework for a child's age."""
    if not isinstance(child_age_years, int) or isinstance(child_age_years, bool):
        child_age_years = int(child_age_years)
    if child_age_years < 0 or child_age_years > 21:
        raise ValueError(f"child_age_years must be between 0 and 21, got {child_age_years}")
    if child_age_years <= 2:
        return MoEFrameworkType.DAYCARE_SUPERVISED.value
    if child_age_years <= 5:
        return MoEFrameworkType.MUNICIPAL_GAN.value
    if child_age_years <= 8:
        return MoEFrameworkType.ELEMENTARY_1_3.value
    if child_age_years <= 11:
        return MoEFrameworkType.ELEMENTARY_4_6.value
    if child_age_years <= 14:
        return MoEFrameworkType.MIDDLE_SCHOOL_7_9.value
    return MoEFrameworkType.HIGH_SCHOOL_10_12.value


class _DomainModelBase:
    """Shared serialization mixins for domain dataclasses."""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        raise NotImplementedError

    @classmethod
    def model_validate(cls, data: dict[str, Any] | Self) -> Self:
        return cls.from_dict(data)


@dataclass
class PassengerLoyaltyWallet(_DomainModelBase):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    family_profile_id: str = "default-family-profile"
    passenger_id: str = "ADULT_1"
    passenger_name: str = "נוסע"
    program_code: LoyaltyProgramCode | str = LoyaltyProgramCode.ELAL_MATMID
    available_points: int = 0
    can_pool_with_family: bool = False
    pool_group_id: Optional[str] = None
    transfer_ratio_to_airline: float = 1.0
    has_club_credit_card: bool = False
    companion_vouchers_count: int = 0
    point_valuation_cents: float = 1.5
    updated_at: Optional[str] = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if isinstance(self.program_code, LoyaltyProgramCode):
            code_val = self.program_code.value
        else:
            code_val = str(self.program_code)
            try:
                LoyaltyProgramCode(code_val)
            except ValueError as exc:
                raise ValueError(f"Invalid LoyaltyProgramCode: {code_val!r}") from exc
        self.program_code = LoyaltyProgramCode(code_val)
        self.available_points = int(self.available_points)
        if self.available_points < 0:
            raise ValueError("available_points must be >= 0")
        self.can_pool_with_family = _parse_bool(self.can_pool_with_family, False)
        self.transfer_ratio_to_airline = float(self.transfer_ratio_to_airline)
        if self.transfer_ratio_to_airline <= 0.0:
            raise ValueError("transfer_ratio_to_airline must be > 0.0")
        self.has_club_credit_card = _parse_bool(self.has_club_credit_card, False)
        self.companion_vouchers_count = int(self.companion_vouchers_count)
        if self.companion_vouchers_count < 0:
            raise ValueError("companion_vouchers_count must be >= 0")
        self.point_valuation_cents = float(self.point_valuation_cents)
        if self.point_valuation_cents <= 0.0:
            raise ValueError("point_valuation_cents must be > 0.0")
        if not self.updated_at:
            self.updated_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family_profile_id": self.family_profile_id,
            "passenger_id": self.passenger_id,
            "passenger_name": self.passenger_name,
            "program_code": (
                self.program_code.value
                if isinstance(self.program_code, Enum)
                else str(self.program_code)
            ),
            "available_points": self.available_points,
            "can_pool_with_family": self.can_pool_with_family,
            "pool_group_id": self.pool_group_id,
            "transfer_ratio_to_airline": self.transfer_ratio_to_airline,
            "has_club_credit_card": self.has_club_credit_card,
            "companion_vouchers_count": self.companion_vouchers_count,
            "point_valuation_cents": self.point_valuation_cents,
            "updated_at": self.updated_at or _now_iso(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            family_profile_id=str(data.get("family_profile_id") or "default-family-profile"),
            passenger_id=str(data.get("passenger_id") or "ADULT_1"),
            passenger_name=str(data.get("passenger_name") or "נוסע"),
            program_code=data.get("program_code", LoyaltyProgramCode.ELAL_MATMID),
            available_points=int(data.get("available_points", 0)),
            can_pool_with_family=_parse_bool(data.get("can_pool_with_family", False)),
            pool_group_id=data.get("pool_group_id"),
            transfer_ratio_to_airline=float(data.get("transfer_ratio_to_airline", 1.0)),
            has_club_credit_card=_parse_bool(data.get("has_club_credit_card", False)),
            companion_vouchers_count=int(data.get("companion_vouchers_count", 0)),
            point_valuation_cents=float(data.get("point_valuation_cents", 1.5)),
            updated_at=data.get("updated_at") or _now_iso(),
        )


@dataclass
class ChildFramework(_DomainModelBase):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    family_profile_id: str = "default-family-profile"
    child_name: str = "ילד/ה"
    child_age_years: int = 6
    birth_date: Optional[date | str] = None
    passenger_Current_type: str = ""
    framework_type: Optional[MoEFrameworkType | str] = None
    education_stream: str = "MAMLACHTI"
    school_week_days: int = 5
    holiday_extension_mode: HolidayExtensionMode | str = HolidayExtensionMode.NONE
    treat_camp_as_vacation: bool = True
    max_school_days_missed: int = 2
    absence_penalty_weight: float = 1.0
    bagrut_blackout_dates: list[date] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.child_age_years = int(self.child_age_years)
        if self.child_age_years < 0 or self.child_age_years > 21:
            raise ValueError(
                f"child_age_years must be between 0 and 21, got {self.child_age_years}"
            )
        self.birth_date = _parse_optional_date(self.birth_date)
        if not self.passenger_Current_type:
            self.passenger_Current_type = classify_passenger_type(self.child_age_years)
        elif self.passenger_Current_type not in PASSENGER_FARE_TYPES:
            raise ValueError(
                f"Invalid passenger_Current_type: {self.passenger_Current_type!r}"
            )
        else:
            # Keep passenger_Current_type strictly aligned with child_age_years when age is edited
            if self.child_age_years < 2 and self.passenger_Current_type not in (
                "INFANT_LAP",
                "INFANT_SEAT",
            ):
                self.passenger_Current_type = "INFANT_LAP"
            elif 2 <= self.child_age_years <= 11 and self.passenger_Current_type != "CHILD":
                self.passenger_Current_type = "CHILD"
            elif self.child_age_years >= 12 and self.passenger_Current_type != "YOUTH":
                self.passenger_Current_type = "YOUTH"

        if self.framework_type is None or self.framework_type == "":
            self.framework_type = None
        else:
            fw_str = (
                self.framework_type.value
                if isinstance(self.framework_type, MoEFrameworkType)
                else str(self.framework_type)
            )
            try:
                self.framework_type = MoEFrameworkType(fw_str)
            except ValueError as exc:
                raise ValueError(f"Invalid MoEFrameworkType: {fw_str!r}") from exc

        if self.education_stream not in EDUCATION_STREAMS:
            raise ValueError(f"Invalid education_stream: {self.education_stream!r}")

        self.school_week_days = int(self.school_week_days)
        if self.school_week_days not in (5, 6):
            raise ValueError(f"school_week_days must be 5 or 6, got {self.school_week_days}")

        ext_str = (
            self.holiday_extension_mode.value
            if isinstance(self.holiday_extension_mode, HolidayExtensionMode)
            else str(self.holiday_extension_mode or "NONE")
        )
        try:
            self.holiday_extension_mode = HolidayExtensionMode(ext_str)
        except ValueError as exc:
            raise ValueError(f"Invalid HolidayExtensionMode: {ext_str!r}") from exc

        self.treat_camp_as_vacation = _parse_bool(self.treat_camp_as_vacation, True)
        self.max_school_days_missed = int(self.max_school_days_missed)
        if self.max_school_days_missed < 0 or self.max_school_days_missed > 14:
            raise ValueError(
                f"max_school_days_missed must be between 0 and 14, got {self.max_school_days_missed}"
            )
        self.absence_penalty_weight = float(self.absence_penalty_weight)
        if self.absence_penalty_weight < 0.0:
            raise ValueError("absence_penalty_weight must be >= 0.0")

        raw_dates = _parse_json_list(self.bagrut_blackout_dates, [])
        self.bagrut_blackout_dates = [_parse_date(d) for d in raw_dates]

    @property
    def passenger_current_type(self) -> str:
        return self.passenger_Current_type

    def to_dict(self) -> dict[str, Any]:
        blackout_strs = [d.isoformat() for d in self.bagrut_blackout_dates]
        fw_val = (
            self.framework_type.value
            if isinstance(self.framework_type, Enum)
            else self.framework_type
        )
        ext_val = (
            self.holiday_extension_mode.value
            if isinstance(self.holiday_extension_mode, Enum)
            else str(self.holiday_extension_mode)
        )
        return {
            "id": self.id,
            "family_profile_id": self.family_profile_id,
            "child_name": self.child_name,
            "child_age_years": self.child_age_years,
            "birth_date": _format_optional_date(self.birth_date),
            "passenger_Current_type": self.passenger_Current_type,
            "framework_type": fw_val,
            "education_stream": self.education_stream,
            "school_week_days": self.school_week_days,
            "holiday_extension_mode": ext_val,
            "treat_camp_as_vacation": self.treat_camp_as_vacation,
            "max_school_days_missed": self.max_school_days_missed,
            "absence_penalty_weight": self.absence_penalty_weight,
            "bagrut_blackout_dates": blackout_strs,
            "bagrut_blackout_dates_json": json.dumps(blackout_strs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        raw_blackouts = data.get("bagrut_blackout_dates")
        if raw_blackouts is None:
            raw_blackouts = data.get("bagrut_blackout_dates_json", "[]")
        pax_type = (
            data.get("passenger_Current_type")
            or data.get("passenger_current_type")
            or ""
        )
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            family_profile_id=str(data.get("family_profile_id") or "default-family-profile"),
            child_name=str(data.get("child_name") or "ילד/ה"),
            child_age_years=int(data.get("child_age_years", 6)),
            birth_date=data.get("birth_date"),
            passenger_Current_type=str(pax_type),
            framework_type=data.get("framework_type"),
            education_stream=str(data.get("education_stream") or "MAMLACHTI"),
            school_week_days=int(data.get("school_week_days", 5)),
            holiday_extension_mode=data.get("holiday_extension_mode", "NONE"),
            treat_camp_as_vacation=_parse_bool(data.get("treat_camp_as_vacation", True)),
            max_school_days_missed=int(data.get("max_school_days_missed", 2)),
            absence_penalty_weight=float(data.get("absence_penalty_weight", 1.0)),
            bagrut_blackout_dates=_parse_json_list(raw_blackouts, []),
        )


@dataclass
class FamilyProfile(_DomainModelBase):
    id: str = "default-family-profile"
    profile_name: str = "המשפחה שלי"
    adults_count: int = 2
    matmid_points_balance: int = 0
    has_flycard: bool = True
    flycard_tier: str = "FLY_CARD_PREMIUM"
    flycard_companion_vouchers: int = 0
    point_valuation_usd: float = 0.016
    preferred_currency: str = "USD"
    children: list[ChildFramework] = field(default_factory=list)
    passenger_loyalty_wallets: list[PassengerLoyaltyWallet] = field(default_factory=list)
    created_at: Optional[str] = field(default_factory=_now_iso)
    updated_at: Optional[str] = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.adults_count = int(self.adults_count)
        if self.adults_count < 1 or self.adults_count > 6:
            raise ValueError(f"adults_count must be between 1 and 6, got {self.adults_count}")
        self.matmid_points_balance = int(self.matmid_points_balance)
        if self.matmid_points_balance < 0:
            raise ValueError("matmid_points_balance must be >= 0")
        self.has_flycard = _parse_bool(self.has_flycard, True)
        if self.flycard_tier not in FLYCARD_TIERS:
            raise ValueError(f"Invalid flycard_tier: {self.flycard_tier!r}")
        self.flycard_companion_vouchers = int(self.flycard_companion_vouchers)
        if self.flycard_companion_vouchers < 0:
            raise ValueError("flycard_companion_vouchers must be >= 0")
        self.point_valuation_usd = float(self.point_valuation_usd)
        if self.point_valuation_usd <= 0.0:
            raise ValueError("point_valuation_usd must be > 0.0")
        if self.preferred_currency not in CURRENCIES:
            raise ValueError(f"Invalid preferred_currency: {self.preferred_currency!r}")

        self.children = [
            ChildFramework.from_dict(c) if not isinstance(c, ChildFramework) else c
            for c in (self.children or [])
        ]
        for child in self.children:
            child.family_profile_id = self.id

        self.passenger_loyalty_wallets = [
            PassengerLoyaltyWallet.from_dict(w)
            if not isinstance(w, PassengerLoyaltyWallet)
            else w
            for w in (self.passenger_loyalty_wallets or [])
        ]
        for wallet in self.passenger_loyalty_wallets:
            wallet.family_profile_id = self.id

        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = _now_iso()

    @property
    def total_passengers(self) -> int:
        return self.adults_count + len(self.children)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_name": self.profile_name,
            "adults_count": self.adults_count,
            "matmid_points_balance": self.matmid_points_balance,
            "has_flycard": self.has_flycard,
            "flycard_tier": self.flycard_tier,
            "flycard_companion_vouchers": self.flycard_companion_vouchers,
            "point_valuation_usd": self.point_valuation_usd,
            "preferred_currency": self.preferred_currency,
            "children": [c.to_dict() for c in self.children],
            "passenger_loyalty_wallets": [w.to_dict() for w in self.passenger_loyalty_wallets],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        profile_id = str(data.get("id") or "default-family-profile")
        raw_children = data.get("children") or []
        raw_wallets = data.get("passenger_loyalty_wallets") or []
        return cls(
            id=profile_id,
            profile_name=str(data.get("profile_name") or "המשפחה שלי"),
            adults_count=int(data.get("adults_count", 2)),
            matmid_points_balance=int(data.get("matmid_points_balance", 0)),
            has_flycard=_parse_bool(data.get("has_flycard", True)),
            flycard_tier=str(data.get("flycard_tier") or "FLY_CARD_PREMIUM"),
            flycard_companion_vouchers=int(data.get("flycard_companion_vouchers", 0)),
            point_valuation_usd=float(data.get("point_valuation_usd", 0.016)),
            preferred_currency=str(data.get("preferred_currency") or "USD"),
            children=[ChildFramework.from_dict(c) for c in raw_children],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet.from_dict(w) for w in raw_wallets
            ],
            created_at=data.get("created_at") or _now_iso(),
            updated_at=data.get("updated_at") or _now_iso(),
        )


@dataclass
class MoEVacationWindow(_DomainModelBase):
    id: str
    school_year: str
    circular_id: str
    holiday_code: str
    holiday_name_he: str
    holiday_name_en: str
    framework_type: MoEFrameworkType | str
    start_date: date
    end_date: date
    resumes_on_date: date
    is_covered_by_nitzanim: bool = False
    nitzanim_start_date: Optional[date] = None
    nitzanim_end_date: Optional[date] = None
    tlv_airport_closed: bool = False
    calendar_sync_source: str = "OFFICIAL_MOE_CIRCULAR"
    last_synced_at: Optional[str] = field(default_factory=_now_iso)
    source_reference: str = ""

    def __post_init__(self) -> None:
        fw_str = (
            self.framework_type.value
            if isinstance(self.framework_type, MoEFrameworkType)
            else str(self.framework_type)
        )
        try:
            self.framework_type = MoEFrameworkType(fw_str)
        except ValueError as exc:
            raise ValueError(f"Invalid framework_type: {fw_str!r}") from exc

        self.start_date = _parse_date(self.start_date)
        self.end_date = _parse_date(self.end_date)
        self.resumes_on_date = _parse_date(self.resumes_on_date)
        self.is_covered_by_nitzanim = _parse_bool(self.is_covered_by_nitzanim, False)
        self.nitzanim_start_date = _parse_optional_date(self.nitzanim_start_date)
        self.nitzanim_end_date = _parse_optional_date(self.nitzanim_end_date)

        self.tlv_airport_closed = _parse_bool(self.tlv_airport_closed, False)
        if self.calendar_sync_source not in CALENDAR_SYNC_SOURCES:
            raise ValueError(f"Invalid calendar_sync_source: {self.calendar_sync_source!r}")
        if not self.last_synced_at:
            self.last_synced_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "school_year": self.school_year,
            "circular_id": self.circular_id,
            "holiday_code": self.holiday_code,
            "holiday_name_he": self.holiday_name_he,
            "holiday_name_en": self.holiday_name_en,
            "framework_type": (
                self.framework_type.value
                if isinstance(self.framework_type, Enum)
                else str(self.framework_type)
            ),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "resumes_on_date": self.resumes_on_date.isoformat(),
            "is_covered_by_nitzanim": self.is_covered_by_nitzanim,
            "nitzanim_start_date": _format_optional_date(self.nitzanim_start_date),
            "nitzanim_end_date": _format_optional_date(self.nitzanim_end_date),
            "tlv_airport_closed": self.tlv_airport_closed,
            "calendar_sync_source": self.calendar_sync_source,
            "last_synced_at": self.last_synced_at,
            "source_reference": self.source_reference,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            id=str(data["id"]),
            school_year=str(data["school_year"]),
            circular_id=str(data.get("circular_id") or "0363"),
            holiday_code=str(data["holiday_code"]),
            holiday_name_he=str(data["holiday_name_he"]),
            holiday_name_en=str(data["holiday_name_en"]),
            framework_type=data["framework_type"],
            start_date=_parse_date(data["start_date"]),
            end_date=_parse_date(data["end_date"]),
            resumes_on_date=_parse_date(data["resumes_on_date"]),
            is_covered_by_nitzanim=_parse_bool(data.get("is_covered_by_nitzanim", False)),
            nitzanim_start_date=_parse_optional_date(data.get("nitzanim_start_date")),
            nitzanim_end_date=_parse_optional_date(data.get("nitzanim_end_date")),
            tlv_airport_closed=_parse_bool(data.get("tlv_airport_closed", False)),
            calendar_sync_source=str(
                data.get("calendar_sync_source") or "OFFICIAL_MOE_CIRCULAR"
            ),
            last_synced_at=data.get("last_synced_at") or _now_iso(),
            source_reference=str(data.get("source_reference") or ""),
        )


@dataclass
class FlightSearchQuery(_DomainModelBase):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    family_profile_id: str = "default-family-profile"
    date_selection_mode: DateSelectionMode | str = DateSelectionMode.HOLIDAY_DIRECT_INTENT
    airline_selection_mode: AirlineSelectionMode | str = AirlineSelectionMode.EL_AL_ONLY
    search_elal_bonus_tickets: bool = True
    include_sundor_flights: bool = True
    origin_iata: str = "TLV"
    destination_iatas: list[str] = field(default_factory=lambda: ["FCO"])
    specific_departure_date: Optional[date] = None
    specific_return_date: Optional[date] = None
    flex_days_plus_minus: int = 0
    school_year: Optional[str] = "2026-2027"
    target_holiday_codes: list[str] = field(default_factory=list)
    direct_holiday_code: Optional[str] = None
    direct_target_year: Optional[int] = None
    min_trip_nights: int = 4
    max_trip_nights: int = 10
    max_bridge_days_shift: int = 3
    overlap_policy: str = "CAMP_ADJUSTED_INTERSECTION"
    preferred_cabins: list[str] = field(
        default_factory=lambda: ["ECONOMY", "PREMIUM", "BUSINESS"]
    )
    enabled_loyalty_programs: list[str] = field(
        default_factory=lambda: ["ELAL_MATMID"]
    )
    preferred_vacation_types: list[str] = field(default_factory=list)
    weather_filter_mode: str = "SOFT_PRIORITIZE"
    min_weather_suitability_score: Optional[float] = None
    allow_hybrid_bonus_cash: bool = True
    direct_flights_only: bool = True
    created_at: Optional[str] = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        dm_str = (
            self.date_selection_mode.value
            if isinstance(self.date_selection_mode, DateSelectionMode)
            else str(self.date_selection_mode)
        )
        self.date_selection_mode = DateSelectionMode(dm_str)

        am_str = (
            self.airline_selection_mode.value
            if isinstance(self.airline_selection_mode, AirlineSelectionMode)
            else str(self.airline_selection_mode)
        )
        self.airline_selection_mode = AirlineSelectionMode(am_str)

        self.search_elal_bonus_tickets = _parse_bool(self.search_elal_bonus_tickets, True)
        self.include_sundor_flights = _parse_bool(self.include_sundor_flights, True)
        self.origin_iata = str(self.origin_iata or "TLV").upper()

        if self.destination_iatas is None:
            self.destination_iatas = ["FCO"]
        elif isinstance(self.destination_iatas, str):
            raw_s = self.destination_iatas.strip()
            if not raw_s:
                self.destination_iatas = ["ANYWHERE"]
            elif raw_s.startswith("["):
                parsed_list = _parse_json_list(raw_s, [])
                toks = [str(x).strip().upper() for x in parsed_list if str(x).strip()]
                self.destination_iatas = toks or ["ANYWHERE"]
            else:
                toks = [t.strip().upper() for t in raw_s.split(",") if t.strip()]
                self.destination_iatas = toks or ["ANYWHERE"]
        else:
            raw_items = list(self.destination_iatas)
            if not raw_items:
                self.destination_iatas = ["ANYWHERE"]
            else:
                toks = []
                for x in raw_items:
                    if x is None:
                        continue
                    for sub in str(x).split(","):
                        sc = sub.strip().upper()
                        if sc:
                            toks.append(sc)
                self.destination_iatas = toks or ["ANYWHERE"]

        if any(t in ("ANYWHERE", "ALL", "*") for t in self.destination_iatas):
            self.destination_iatas = ["ANYWHERE"]
        else:
            dedup_dests: list[str] = []
            seen_dests: set[str] = set()
            for t in self.destination_iatas:
                if t not in seen_dests:
                    seen_dests.add(t)
                    dedup_dests.append(t)
            self.destination_iatas = dedup_dests or ["ANYWHERE"]

        self.specific_departure_date = _parse_optional_date(self.specific_departure_date)
        self.specific_return_date = _parse_optional_date(self.specific_return_date)
        if (
            self.date_selection_mode == DateSelectionMode.SPECIFIC_DATES
            and self.specific_departure_date is not None
            and self.specific_return_date is not None
            and self.specific_return_date <= self.specific_departure_date
        ):
            raise ValueError(
                "specific_return_date must be strictly after specific_departure_date"
            )

        self.flex_days_plus_minus = int(self.flex_days_plus_minus)
        if self.flex_days_plus_minus < 0 or self.flex_days_plus_minus > 7:
            raise ValueError(
                f"flex_days_plus_minus must be between 0 and 7, got {self.flex_days_plus_minus}"
            )

        self.target_holiday_codes = [
            str(x).upper() for x in _parse_json_list(self.target_holiday_codes, [])
        ]

        if self.direct_holiday_code is not None and self.direct_holiday_code != "":
            self.direct_holiday_code = str(self.direct_holiday_code).upper()
        else:
            self.direct_holiday_code = None

        if self.direct_target_year is not None and self.direct_target_year != "":
            self.direct_target_year = int(self.direct_target_year)
            if self.direct_target_year < 2025 or self.direct_target_year > 2035:
                raise ValueError(
                    f"direct_target_year must be between 2025 and 2035, got {self.direct_target_year}"
                )
        else:
            self.direct_target_year = None

        self.min_trip_nights = int(self.min_trip_nights)
        self.max_trip_nights = int(self.max_trip_nights)
        if self.min_trip_nights < 1:
            raise ValueError("min_trip_nights must be >= 1")
        if self.max_trip_nights < self.min_trip_nights:
            raise ValueError("max_trip_nights must be >= min_trip_nights")

        self.max_bridge_days_shift = int(self.max_bridge_days_shift)
        if self.max_bridge_days_shift < 0 or self.max_bridge_days_shift > 5:
            raise ValueError(
                f"max_bridge_days_shift must be between 0 and 5, got {self.max_bridge_days_shift}"
            )

        if self.overlap_policy not in OVERLAP_POLICIES:
            raise ValueError(f"Invalid overlap_policy: {self.overlap_policy!r}")

        self.preferred_cabins = [
            str(c).upper()
            for c in _parse_json_list(
                self.preferred_cabins, ["ECONOMY", "PREMIUM", "BUSINESS"]
            )
        ]
        self.enabled_loyalty_programs = [
            str(p).upper()
            for p in _parse_json_list(self.enabled_loyalty_programs, ["ELAL_MATMID"])
        ]
        raw_vtypes = _parse_json_list(self.preferred_vacation_types, [])
        norm_vtypes: list[str] = []
        for vt in raw_vtypes:
            vt_str = (
                vt.value
                if isinstance(vt, VacationType)
                else str(vt or "").strip().upper()
            )
            if not vt_str:
                continue
            if vt_str not in VACATION_TYPES:
                raise ValueError(
                    f"Invalid vacation type {vt!r}: must be one of {VACATION_TYPES}"
                )
            if vt_str != "ANY" and vt_str not in norm_vtypes:
                norm_vtypes.append(vt_str)
        self.preferred_vacation_types = norm_vtypes

        wfm_str = (
            self.weather_filter_mode.value
            if isinstance(self.weather_filter_mode, WeatherFilterMode)
            else str(self.weather_filter_mode or "SOFT_PRIORITIZE").strip().upper()
        )
        if wfm_str not in WEATHER_FILTER_MODES:
            raise ValueError(
                f"Invalid weather_filter_mode {self.weather_filter_mode!r}: must be one of {WEATHER_FILTER_MODES}"
            )
        self.weather_filter_mode = wfm_str

        if (
            self.min_weather_suitability_score is not None
            and self.min_weather_suitability_score != ""
        ):
            self.min_weather_suitability_score = float(
                self.min_weather_suitability_score
            )
            if (
                self.min_weather_suitability_score < 0.0
                or self.min_weather_suitability_score > 100.0
            ):
                raise ValueError(
                    f"min_weather_suitability_score must be between 0.0 and 100.0, got {self.min_weather_suitability_score}"
                )
        else:
            self.min_weather_suitability_score = None

        self.allow_hybrid_bonus_cash = _parse_bool(self.allow_hybrid_bonus_cash, True)
        self.direct_flights_only = _parse_bool(self.direct_flights_only, True)
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family_profile_id": self.family_profile_id,
            "date_selection_mode": (
                self.date_selection_mode.value
                if isinstance(self.date_selection_mode, Enum)
                else str(self.date_selection_mode)
            ),
            "airline_selection_mode": (
                self.airline_selection_mode.value
                if isinstance(self.airline_selection_mode, Enum)
                else str(self.airline_selection_mode)
            ),
            "search_elal_bonus_tickets": self.search_elal_bonus_tickets,
            "include_sundor_flights": self.include_sundor_flights,
            "origin_iata": self.origin_iata,
            "destination_iatas": list(self.destination_iatas),
            "destination_iatas_json": json.dumps(self.destination_iatas),
            "specific_departure_date": _format_optional_date(self.specific_departure_date),
            "specific_return_date": _format_optional_date(self.specific_return_date),
            "flex_days_plus_minus": self.flex_days_plus_minus,
            "school_year": self.school_year,
            "target_holiday_codes": list(self.target_holiday_codes),
            "target_holiday_codes_json": json.dumps(self.target_holiday_codes),
            "direct_holiday_code": self.direct_holiday_code,
            "direct_target_year": self.direct_target_year,
            "min_trip_nights": self.min_trip_nights,
            "max_trip_nights": self.max_trip_nights,
            "max_bridge_days_shift": self.max_bridge_days_shift,
            "overlap_policy": self.overlap_policy,
            "preferred_cabins": list(self.preferred_cabins),
            "preferred_cabins_json": json.dumps(self.preferred_cabins),
            "enabled_loyalty_programs": list(self.enabled_loyalty_programs),
            "enabled_loyalty_programs_json": json.dumps(self.enabled_loyalty_programs),
            "preferred_vacation_types": list(self.preferred_vacation_types),
            "preferred_vacation_types_json": json.dumps(self.preferred_vacation_types),
            "weather_filter_mode": self.weather_filter_mode,
            "min_weather_suitability_score": self.min_weather_suitability_score,
            "allow_hybrid_bonus_cash": self.allow_hybrid_bonus_cash,
            "direct_flights_only": self.direct_flights_only,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        dests: Any = None
        has_explicit_dest = False
        for dest_key in (
            "destination_iatas",
            "destinations",
            "destination",
            "destination_iatas_json",
        ):
            if dest_key in data and data.get(dest_key) is not None:
                dests = data.get(dest_key)
                has_explicit_dest = True
                break
        if not has_explicit_dest:
            dests = ["FCO"]
        holidays = data.get("target_holiday_codes")
        if holidays is None:
            holidays = data.get("target_holiday_codes_json", [])
        cabins = data.get("preferred_cabins")
        if cabins is None:
            cabins = data.get("preferred_cabins_json", ["ECONOMY", "PREMIUM", "BUSINESS"])
        programs = data.get("enabled_loyalty_programs")
        if programs is None:
            programs = data.get("enabled_loyalty_programs_json", ["ELAL_MATMID"])
        vtypes = data.get("preferred_vacation_types")
        if vtypes is None:
            vtypes = data.get("vacation_types")
        if vtypes is None:
            vtypes = data.get("preferred_vacation_types_json", [])

        raw_overlap = str(data.get("overlap_policy") or "CAMP_ADJUSTED_INTERSECTION")
        if raw_overlap == "MAXIMIZE_EFFICIENCY_SCORE":
            raw_overlap = "CAMP_ADJUSTED_INTERSECTION"

        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            family_profile_id=str(data.get("family_profile_id") or "default-family-profile"),
            date_selection_mode=data.get(
                "date_selection_mode", DateSelectionMode.HOLIDAY_DIRECT_INTENT
            ),
            airline_selection_mode=data.get(
                "airline_selection_mode", AirlineSelectionMode.EL_AL_ONLY
            ),
            search_elal_bonus_tickets=_parse_bool(
                data.get("search_elal_bonus_tickets", True)
            ),
            include_sundor_flights=_parse_bool(data.get("include_sundor_flights", True)),
            origin_iata=str(data.get("origin_iata") or "TLV"),
            destination_iatas=dests,
            specific_departure_date=data.get("specific_departure_date"),
            specific_return_date=data.get("specific_return_date"),
            flex_days_plus_minus=int(data.get("flex_days_plus_minus", 0)),
            school_year=data.get("school_year", "2026-2027"),
            target_holiday_codes=_parse_json_list(holidays, []),
            direct_holiday_code=data.get("direct_holiday_code"),
            direct_target_year=data.get("direct_target_year"),
            min_trip_nights=int(data.get("min_trip_nights", 4)),
            max_trip_nights=int(data.get("max_trip_nights", 10)),
            max_bridge_days_shift=int(data.get("max_bridge_days_shift", 3)),
            overlap_policy=raw_overlap,
            preferred_cabins=_parse_json_list(cabins, ["ECONOMY", "PREMIUM", "BUSINESS"]),
            enabled_loyalty_programs=_parse_json_list(programs, ["ELAL_MATMID"]),
            preferred_vacation_types=_parse_json_list(vtypes, []),
            weather_filter_mode=str(
                data.get("weather_filter_mode")
                or data.get("vacation_type_filter_mode")
                or "SOFT_PRIORITIZE"
            ),
            min_weather_suitability_score=data.get("min_weather_suitability_score"),
            allow_hybrid_bonus_cash=_parse_bool(data.get("allow_hybrid_bonus_cash", True)),
            direct_flights_only=_parse_bool(data.get("direct_flights_only", True)),
            created_at=data.get("created_at") or _now_iso(),
        )


@dataclass
class ElAlBonusAvailability(_DomainModelBase):
    id: str
    origin_iata: str
    destination_iata: str
    direction: str
    flight_number: str
    operating_carrier: str = "LY"
    flight_date: date = field(default_factory=lambda: date(2027, 4, 11))
    departure_time_local: str = "07:00"
    arrival_time_local: str = "10:00"
    aircraft_type: Optional[str] = "789"
    economy_award_seats: int = 0
    economy_seats_is_two_plus: bool = False
    economy_rbd_code: str = "E"
    premium_award_seats: int = 0
    premium_seats_is_two_plus: bool = False
    premium_rbd_code: str = "P"
    business_award_seats: int = 0
    business_seats_is_two_plus: bool = False
    business_rbd_code: str = "I"
    award_zone: str = "ZONE_B"
    economy_points_per_pax: Optional[int] = None
    premium_points_per_pax: Optional[int] = None
    business_points_per_pax: Optional[int] = None
    flycard_promo_active: bool = False
    taxes_usd_per_pax: float = 0.0
    source_url: str = "https://www.elal.com/rbddataclients/"
    fetched_at: str = field(default_factory=_now_iso)
    expires_at: str = ""

    def __post_init__(self) -> None:
        self.origin_iata = str(self.origin_iata).upper()
        self.destination_iata = str(self.destination_iata).upper()
        self.direction = str(self.direction).upper()
        if self.direction not in ("OUTBOUND", "INBOUND"):
            raise ValueError(f"direction must be OUTBOUND or INBOUND, got {self.direction!r}")
        self.flight_date = _parse_date(self.flight_date)
        if not self.id:
            self.id = f"{self.flight_number}_{self.flight_date.isoformat()}"

        self.economy_award_seats = int(self.economy_award_seats)
        self.premium_award_seats = int(self.premium_award_seats)
        self.business_award_seats = int(self.business_award_seats)
        for seat_cnt in (
            self.economy_award_seats,
            self.premium_award_seats,
            self.business_award_seats,
        ):
            if seat_cnt < 0 or seat_cnt > 9:
                raise ValueError(f"Award seat count must be between 0 and 9, got {seat_cnt}")

        self.economy_seats_is_two_plus = _parse_bool(
            self.economy_seats_is_two_plus, self.economy_award_seats >= 2
        )
        self.premium_seats_is_two_plus = _parse_bool(
            self.premium_seats_is_two_plus, self.premium_award_seats >= 2
        )
        self.business_seats_is_two_plus = _parse_bool(
            self.business_seats_is_two_plus, self.business_award_seats >= 2
        )
        self.flycard_promo_active = _parse_bool(self.flycard_promo_active, False)
        self.taxes_usd_per_pax = float(self.taxes_usd_per_pax)
        if self.taxes_usd_per_pax < 0.0:
            raise ValueError("taxes_usd_per_pax must be >= 0.0")
        if self.economy_points_per_pax is not None:
            self.economy_points_per_pax = int(self.economy_points_per_pax)
        if self.premium_points_per_pax is not None:
            self.premium_points_per_pax = int(self.premium_points_per_pax)
        if self.business_points_per_pax is not None:
            self.business_points_per_pax = int(self.business_points_per_pax)
        if isinstance(self.fetched_at, datetime):
            self.fetched_at = self.fetched_at.isoformat()
        if isinstance(self.expires_at, datetime):
            self.expires_at = self.expires_at.isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "origin_iata": self.origin_iata,
            "destination_iata": self.destination_iata,
            "direction": self.direction,
            "flight_number": self.flight_number,
            "operating_carrier": self.operating_carrier,
            "flight_date": self.flight_date.isoformat(),
            "departure_time_local": self.departure_time_local,
            "arrival_time_local": self.arrival_time_local,
            "aircraft_type": self.aircraft_type,
            "economy_award_seats": self.economy_award_seats,
            "economy_seats_is_two_plus": self.economy_seats_is_two_plus,
            "economy_rbd_code": self.economy_rbd_code,
            "premium_award_seats": self.premium_award_seats,
            "premium_seats_is_two_plus": self.premium_seats_is_two_plus,
            "premium_rbd_code": self.premium_rbd_code,
            "business_award_seats": self.business_award_seats,
            "business_seats_is_two_plus": self.business_seats_is_two_plus,
            "business_rbd_code": self.business_rbd_code,
            "award_zone": self.award_zone,
            "economy_points_per_pax": self.economy_points_per_pax,
            "premium_points_per_pax": self.premium_points_per_pax,
            "business_points_per_pax": self.business_points_per_pax,
            "flycard_promo_active": self.flycard_promo_active,
            "taxes_usd_per_pax": self.taxes_usd_per_pax,
            "source_url": self.source_url,
            "fetched_at": str(self.fetched_at),
            "expires_at": str(self.expires_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        f_date = _parse_date(data["flight_date"])
        f_num = str(data["flight_number"])
        return cls(
            id=str(data.get("id") or f"{f_num}_{f_date.isoformat()}"),
            origin_iata=str(data["origin_iata"]),
            destination_iata=str(data["destination_iata"]),
            direction=str(data["direction"]),
            flight_number=f_num,
            operating_carrier=str(data.get("operating_carrier") or "LY"),
            flight_date=f_date,
            departure_time_local=str(data.get("departure_time_local") or "07:00"),
            arrival_time_local=str(data.get("arrival_time_local") or "10:00"),
            aircraft_type=data.get("aircraft_type"),
            economy_award_seats=int(data.get("economy_award_seats", 0)),
            economy_seats_is_two_plus=_parse_bool(
                data.get("economy_seats_is_two_plus"),
                int(data.get("economy_award_seats", 0)) >= 2,
            ),
            economy_rbd_code=str(data.get("economy_rbd_code") or "E"),
            premium_award_seats=int(data.get("premium_award_seats", 0)),
            premium_seats_is_two_plus=_parse_bool(
                data.get("premium_seats_is_two_plus"),
                int(data.get("premium_award_seats", 0)) >= 2,
            ),
            premium_rbd_code=str(data.get("premium_rbd_code") or "P"),
            business_award_seats=int(data.get("business_award_seats", 0)),
            business_seats_is_two_plus=_parse_bool(
                data.get("business_seats_is_two_plus"),
                int(data.get("business_award_seats", 0)) >= 2,
            ),
            business_rbd_code=str(data.get("business_rbd_code") or "I"),
            award_zone=str(data.get("award_zone") or "ZONE_B"),
            economy_points_per_pax=data.get("economy_points_per_pax"),
            premium_points_per_pax=data.get("premium_points_per_pax"),
            business_points_per_pax=data.get("business_points_per_pax"),
            flycard_promo_active=_parse_bool(data.get("flycard_promo_active", False)),
            taxes_usd_per_pax=float(data.get("taxes_usd_per_pax", 0.0)),
            source_url=str(
                data.get("source_url") or "https://www.elal.com/rbddataclients/"
            ),
            fetched_at=str(data.get("fetched_at") or _now_iso()),
            expires_at=str(data.get("expires_at") or ""),
        )


@dataclass
class FlightLeg(_DomainModelBase):
    flight_number: str
    operating_carrier: str = "LY"
    origin_iata: str = "TLV"
    destination_iata: str = "FCO"
    flight_date: date = field(default_factory=lambda: date(2027, 4, 11))
    departure_time_local: str = "07:15"
    arrival_time_local: str = "10:00"
    aircraft_type: Optional[str] = "789"
    duration_minutes: int = 225
    is_direct: bool = True

    def __post_init__(self) -> None:
        self.flight_date = _parse_date(self.flight_date)
        self.duration_minutes = int(self.duration_minutes)
        self.is_direct = _parse_bool(self.is_direct, True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flight_number": self.flight_number,
            "operating_carrier": self.operating_carrier,
            "origin_iata": self.origin_iata,
            "destination_iata": self.destination_iata,
            "flight_date": self.flight_date.isoformat(),
            "departure_time_local": self.departure_time_local,
            "arrival_time_local": self.arrival_time_local,
            "aircraft_type": self.aircraft_type,
            "duration_minutes": self.duration_minutes,
            "is_direct": self.is_direct,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            flight_number=str(data["flight_number"]),
            operating_carrier=str(data.get("operating_carrier") or "LY"),
            origin_iata=str(data.get("origin_iata") or "TLV"),
            destination_iata=str(data.get("destination_iata") or "FCO"),
            flight_date=_parse_date(data.get("flight_date") or "2027-04-11"),
            departure_time_local=str(data.get("departure_time_local") or "07:15"),
            arrival_time_local=str(data.get("arrival_time_local") or "10:00"),
            aircraft_type=data.get("aircraft_type"),
            duration_minutes=int(data.get("duration_minutes", 225)),
            is_direct=_parse_bool(data.get("is_direct", True)),
        )


@dataclass
class FlightItinerary(_DomainModelBase):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    search_query_id: str = ""
    origin_iata: str = "TLV"
    destination_iata: str = "FCO"
    return_origin_iata: str = "FCO"
    destination_city_he: str = "רומא"
    destination_city_en: str = "Rome"
    departure_date: date = field(default_factory=lambda: date(2027, 4, 11))
    return_date: date = field(default_factory=lambda: date(2027, 4, 18))
    trip_nights: int = 7
    primary_carrier_iata: str = "LY"
    is_elal_flight: bool = True
    utilizes_elal_bonus: bool = True
    fulfillment_strategy: FulfillmentStrategy | str = (
        FulfillmentStrategy.FULL_BONUS_SAME_CABIN
    )
    outbound_legs: list[FlightLeg] = field(default_factory=list)
    inbound_legs: list[FlightLeg] = field(default_factory=list)
    outbound_bonus_id: Optional[str] = None
    inbound_bonus_id: Optional[str] = None
    seated_passengers_count: int = 1
    bonus_tickets_count: int = 0
    cash_tickets_count: int = 0
    primary_cabin: str = "ECONOMY"
    points_used_by_wallet: dict[str, Any] = field(default_factory=dict)
    requires_two_plus_seat_verification: bool = False
    total_matmid_points: int = 0
    total_taxes_and_fees_usd: float = 0.0
    total_supplemental_cash_fares_usd: float = 0.0
    total_baggage_fees_usd: float = 0.0
    total_out_of_pocket_cash_usd: float = 0.0
    full_cash_benchmark_usd: float = 0.0
    net_cash_saved_usd: float = 0.0
    cents_per_point_value: Optional[float] = None
    rbddataclients_verify_url: Optional[str] = "https://www.elal.com/rbddataclients/"
    booking_deep_link_url: str = "https://www.elal.com/"
    elal_google_flights_url: Optional[str] = None
    # Run 11: results are described by available bonus seats per direction (no cash figures).
    # The cash / all-passenger-points attributes above stay only as defaulted fields so the
    # existing constructors and the NOT NULL SQLite columns keep working; they are neither
    # computed by the planner nor serialized by `to_dict()`.
    bonus_direction_coverage: str = "NONE"
    outbound_bonus_seats: Optional[int] = None
    inbound_bonus_seats: Optional[int] = None
    outbound_bonus_seats_is_two_plus: bool = False
    inbound_bonus_seats_is_two_plus: bool = False
    min_points_per_bonus_ticket: Optional[int] = None
    min_points_basis: Optional[str] = None
    points_are_estimated: bool = True

    def __post_init__(self) -> None:
        self.departure_date = _parse_date(self.departure_date)
        self.return_date = _parse_date(self.return_date)
        self.trip_nights = int(self.trip_nights)
        if self.trip_nights < 1:
            raise ValueError(f"trip_nights must be >= 1, got {self.trip_nights}")
        self.bonus_direction_coverage = (
            str(self.bonus_direction_coverage or "NONE").strip().upper()
        )
        if self.bonus_direction_coverage not in BONUS_DIRECTION_COVERAGE_VALUES:
            raise ValueError(
                f"Invalid bonus_direction_coverage: {self.bonus_direction_coverage!r}"
            )
        self.outbound_bonus_seats = (
            max(0, int(self.outbound_bonus_seats))
            if self.outbound_bonus_seats is not None
            else None
        )
        self.inbound_bonus_seats = (
            max(0, int(self.inbound_bonus_seats))
            if self.inbound_bonus_seats is not None
            else None
        )
        self.outbound_bonus_seats_is_two_plus = _parse_bool(
            self.outbound_bonus_seats_is_two_plus, False
        )
        self.inbound_bonus_seats_is_two_plus = _parse_bool(
            self.inbound_bonus_seats_is_two_plus, False
        )
        self.min_points_per_bonus_ticket = (
            int(self.min_points_per_bonus_ticket)
            if self.min_points_per_bonus_ticket is not None
            else None
        )
        if self.min_points_basis is not None:
            self.min_points_basis = str(self.min_points_basis).strip().upper() or None
        if self.min_points_basis not in (None, "ROUND_TRIP", "ONE_WAY"):
            raise ValueError(f"Invalid min_points_basis: {self.min_points_basis!r}")
        self.points_are_estimated = _parse_bool(self.points_are_estimated, True)
        self.is_elal_flight = _parse_bool(self.is_elal_flight, True)
        self.utilizes_elal_bonus = _parse_bool(self.utilizes_elal_bonus, True)

        fs_str = (
            self.fulfillment_strategy.value
            if isinstance(self.fulfillment_strategy, FulfillmentStrategy)
            else str(self.fulfillment_strategy)
        )
        self.fulfillment_strategy = FulfillmentStrategy(fs_str)

        self.outbound_legs = [
            FlightLeg.from_dict(leg) if not isinstance(leg, FlightLeg) else leg
            for leg in _parse_json_list(self.outbound_legs, [])
        ]
        self.inbound_legs = [
            FlightLeg.from_dict(leg) if not isinstance(leg, FlightLeg) else leg
            for leg in _parse_json_list(self.inbound_legs, [])
        ]
        self.seated_passengers_count = int(self.seated_passengers_count)
        if self.seated_passengers_count < 1:
            raise ValueError(
                f"seated_passengers_count must be >= 1, got {self.seated_passengers_count}"
            )
        self.bonus_tickets_count = int(self.bonus_tickets_count)
        if self.bonus_tickets_count < 0:
            raise ValueError(
                f"bonus_tickets_count must be >= 0, got {self.bonus_tickets_count}"
            )
        self.cash_tickets_count = int(self.cash_tickets_count)
        if self.cash_tickets_count < 0:
            raise ValueError(
                f"cash_tickets_count must be >= 0, got {self.cash_tickets_count}"
            )
        self.primary_cabin = str(self.primary_cabin or "ECONOMY").strip().upper()
        if self.primary_cabin not in ("ECONOMY", "PREMIUM", "BUSINESS"):
            raise ValueError(f"Invalid primary_cabin: {self.primary_cabin!r}")
        self.points_used_by_wallet = _parse_json_dict(self.points_used_by_wallet, {})
        self.requires_two_plus_seat_verification = _parse_bool(
            self.requires_two_plus_seat_verification, False
        )
        self.total_matmid_points = int(self.total_matmid_points)
        self.total_taxes_and_fees_usd = float(self.total_taxes_and_fees_usd)
        self.total_supplemental_cash_fares_usd = float(
            self.total_supplemental_cash_fares_usd
        )
        self.total_baggage_fees_usd = float(self.total_baggage_fees_usd)
        self.total_out_of_pocket_cash_usd = float(self.total_out_of_pocket_cash_usd)
        self.full_cash_benchmark_usd = float(self.full_cash_benchmark_usd)
        self.net_cash_saved_usd = float(self.net_cash_saved_usd)
        if self.cents_per_point_value is not None:
            self.cents_per_point_value = float(self.cents_per_point_value)

    def to_dict(self) -> dict[str, Any]:
        out_legs = [leg.to_dict() for leg in self.outbound_legs]
        in_legs = [leg.to_dict() for leg in self.inbound_legs]
        return {
            "id": self.id,
            "search_query_id": self.search_query_id,
            "origin_iata": self.origin_iata,
            "destination_iata": self.destination_iata,
            "return_origin_iata": self.return_origin_iata,
            "destination_city_he": self.destination_city_he,
            "destination_city_en": self.destination_city_en,
            "departure_date": self.departure_date.isoformat(),
            "return_date": self.return_date.isoformat(),
            "trip_nights": self.trip_nights,
            "primary_carrier_iata": self.primary_carrier_iata,
            "is_elal_flight": self.is_elal_flight,
            "utilizes_elal_bonus": self.utilizes_elal_bonus,
            "fulfillment_strategy": (
                self.fulfillment_strategy.value
                if isinstance(self.fulfillment_strategy, Enum)
                else str(self.fulfillment_strategy)
            ),
            "outbound_legs": out_legs,
            "outbound_legs_json": json.dumps(out_legs),
            "inbound_legs": in_legs,
            "inbound_legs_json": json.dumps(in_legs),
            "outbound_bonus_id": self.outbound_bonus_id,
            "inbound_bonus_id": self.inbound_bonus_id,
            "seated_passengers_count": self.seated_passengers_count,
            "bonus_tickets_count": self.bonus_tickets_count,
            "cash_tickets_count": self.cash_tickets_count,
            "primary_cabin": self.primary_cabin,
            "requires_two_plus_seat_verification": self.requires_two_plus_seat_verification,
            "bonus_direction_coverage": self.bonus_direction_coverage,
            "outbound_bonus_seats": self.outbound_bonus_seats,
            "inbound_bonus_seats": self.inbound_bonus_seats,
            "outbound_bonus_seats_is_two_plus": self.outbound_bonus_seats_is_two_plus,
            "inbound_bonus_seats_is_two_plus": self.inbound_bonus_seats_is_two_plus,
            "min_points_per_bonus_ticket": self.min_points_per_bonus_ticket,
            "min_points_basis": self.min_points_basis,
            "points_are_estimated": self.points_are_estimated,
            "rbddataclients_verify_url": self.rbddataclients_verify_url,
            "booking_deep_link_url": self.booking_deep_link_url,
            "elal_google_flights_url": self.elal_google_flights_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        out_legs = data.get("outbound_legs")
        if out_legs is None:
            out_legs = data.get("outbound_legs_json", [])
        in_legs = data.get("inbound_legs")
        if in_legs is None:
            in_legs = data.get("inbound_legs_json", [])
        wallets = data.get("points_used_by_wallet")
        if wallets is None:
            wallets = data.get("points_used_by_wallet_json", {})

        dep_date = _parse_date(data["departure_date"])
        ret_date = _parse_date(data["return_date"])
        nights = int(data.get("trip_nights") or max(1, (ret_date - dep_date).days))
        dest_iata = str(data.get("destination_iata") or "FCO")
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            search_query_id=str(data.get("search_query_id") or ""),
            origin_iata=str(data.get("origin_iata") or "TLV"),
            destination_iata=dest_iata,
            return_origin_iata=str(data.get("return_origin_iata") or dest_iata),
            destination_city_he=str(data.get("destination_city_he") or dest_iata),
            destination_city_en=str(data.get("destination_city_en") or dest_iata),
            departure_date=dep_date,
            return_date=ret_date,
            trip_nights=nights,
            primary_carrier_iata=str(data.get("primary_carrier_iata") or "LY"),
            is_elal_flight=_parse_bool(data.get("is_elal_flight", True)),
            utilizes_elal_bonus=_parse_bool(data.get("utilizes_elal_bonus", True)),
            fulfillment_strategy=data.get(
                "fulfillment_strategy", FulfillmentStrategy.FULL_BONUS_SAME_CABIN
            ),
            outbound_legs=_parse_json_list(out_legs, []),
            inbound_legs=_parse_json_list(in_legs, []),
            outbound_bonus_id=data.get("outbound_bonus_id"),
            inbound_bonus_id=data.get("inbound_bonus_id"),
            seated_passengers_count=(
                int(data["seated_passengers_count"])
                if data.get("seated_passengers_count") is not None
                else 1
            ),
            bonus_tickets_count=(
                int(data["bonus_tickets_count"])
                if data.get("bonus_tickets_count") is not None
                else 0
            ),
            cash_tickets_count=(
                int(data["cash_tickets_count"])
                if data.get("cash_tickets_count") is not None
                else 0
            ),
            primary_cabin=str(data.get("primary_cabin") or "ECONOMY"),
            points_used_by_wallet=_parse_json_dict(wallets, {}),
            requires_two_plus_seat_verification=_parse_bool(
                data.get("requires_two_plus_seat_verification", False)
            ),
            total_matmid_points=int(data.get("total_matmid_points", 0)),
            total_taxes_and_fees_usd=float(data.get("total_taxes_and_fees_usd", 0.0)),
            total_supplemental_cash_fares_usd=float(
                data.get("total_supplemental_cash_fares_usd", 0.0)
            ),
            total_baggage_fees_usd=float(data.get("total_baggage_fees_usd", 0.0)),
            total_out_of_pocket_cash_usd=float(
                data.get("total_out_of_pocket_cash_usd", 0.0)
            ),
            full_cash_benchmark_usd=float(data.get("full_cash_benchmark_usd", 0.0)),
            net_cash_saved_usd=float(data.get("net_cash_saved_usd", 0.0)),
            cents_per_point_value=data.get("cents_per_point_value"),
            rbddataclients_verify_url=data.get(
                "rbddataclients_verify_url", "https://www.elal.com/rbddataclients/"
            ),
            booking_deep_link_url=str(
                data.get("booking_deep_link_url") or "https://www.elal.com/"
            ),
            elal_google_flights_url=(
                str(data["elal_google_flights_url"])
                if data.get("elal_google_flights_url")
                else None
            ),
            bonus_direction_coverage=str(data.get("bonus_direction_coverage") or "NONE"),
            outbound_bonus_seats=data.get("outbound_bonus_seats"),
            inbound_bonus_seats=data.get("inbound_bonus_seats"),
            outbound_bonus_seats_is_two_plus=_parse_bool(
                data.get("outbound_bonus_seats_is_two_plus", False)
            ),
            inbound_bonus_seats_is_two_plus=_parse_bool(
                data.get("inbound_bonus_seats_is_two_plus", False)
            ),
            min_points_per_bonus_ticket=data.get("min_points_per_bonus_ticket"),
            min_points_basis=data.get("min_points_basis"),
            points_are_estimated=_parse_bool(data.get("points_are_estimated", True)),
        )


@dataclass
class ChildDayStatus(_DomainModelBase):
    calendar_date: date
    state_code: str
    psi_penalty: float
    label_he: str
    holiday_code: Optional[str] = None

    def __post_init__(self) -> None:
        self.calendar_date = _parse_date(self.calendar_date)
        self.psi_penalty = float(self.psi_penalty)

    @property
    def status(self) -> str:
        return self.state_code

    @property
    def penalty_psi(self) -> float:
        return self.psi_penalty

    def to_dict(self) -> dict[str, Any]:
        return {
            "calendar_date": self.calendar_date.isoformat(),
            "state_code": self.state_code,
            "status": self.state_code,
            "psi_penalty": self.psi_penalty,
            "penalty_psi": self.psi_penalty,
            "label_he": self.label_he,
            "holiday_code": self.holiday_code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            calendar_date=_parse_date(data["calendar_date"]),
            state_code=str(data.get("state_code") or data.get("status") or "VACATION"),
            psi_penalty=float(
                data.get("psi_penalty", data.get("penalty_psi", 0.0))
            ),
            label_he=str(data.get("label_he") or ""),
            holiday_code=data.get("holiday_code"),
        )


@dataclass
class ChildTripImpact(_DomainModelBase):
    child_id: str
    child_name: str
    framework_type: Optional[MoEFrameworkType | str]
    official_vacation_days: int = 0
    weekend_days: int = 0
    nitzanim_days_overlapped: int = 0
    bridge_school_days_missed: int = 0
    weighted_absence_score: float = 0.0
    within_allowed_absence_limit: bool = True
    daily_breakdown: list[ChildDayStatus] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.framework_type is None or self.framework_type == "":
            self.framework_type = None
        elif not isinstance(self.framework_type, MoEFrameworkType):
            self.framework_type = MoEFrameworkType(str(self.framework_type))
        self.official_vacation_days = int(self.official_vacation_days)
        self.weekend_days = int(self.weekend_days)
        self.nitzanim_days_overlapped = int(self.nitzanim_days_overlapped)
        self.bridge_school_days_missed = int(self.bridge_school_days_missed)
        self.weighted_absence_score = float(self.weighted_absence_score)
        self.within_allowed_absence_limit = _parse_bool(
            self.within_allowed_absence_limit, True
        )
        self.daily_breakdown = [
            ChildDayStatus.from_dict(d) if not isinstance(d, ChildDayStatus) else d
            for d in (self.daily_breakdown or [])
        ]

    def to_dict(self) -> dict[str, Any]:
        fw_val = (
            self.framework_type.value
            if isinstance(self.framework_type, Enum)
            else self.framework_type
        )
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "framework_type": fw_val,
            "official_vacation_days": self.official_vacation_days,
            "weekend_days": self.weekend_days,
            "nitzanim_days_overlapped": self.nitzanim_days_overlapped,
            "bridge_school_days_missed": self.bridge_school_days_missed,
            "weighted_absence_score": self.weighted_absence_score,
            "within_allowed_absence_limit": self.within_allowed_absence_limit,
            "daily_breakdown": [d.to_dict() for d in self.daily_breakdown],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            child_id=str(data.get("child_id") or ""),
            child_name=str(data.get("child_name") or ""),
            framework_type=data.get("framework_type"),
            official_vacation_days=int(data.get("official_vacation_days", 0)),
            weekend_days=int(data.get("weekend_days", 0)),
            nitzanim_days_overlapped=int(data.get("nitzanim_days_overlapped", 0)),
            bridge_school_days_missed=int(data.get("bridge_school_days_missed", 0)),
            weighted_absence_score=float(data.get("weighted_absence_score", 0.0)),
            within_allowed_absence_limit=_parse_bool(
                data.get("within_allowed_absence_limit", True)
            ),
            daily_breakdown=[
                ChildDayStatus.from_dict(d)
                for d in (data.get("daily_breakdown") or [])
            ],
        )


@dataclass
class DestinationWeatherMetrics(_DomainModelBase):
    destination_iata: str = "FCO"
    avg_max_temp_c: float = 22.0
    avg_min_temp_c: float = 12.0
    sea_water_temp_c: Optional[float] = None
    expected_rain_days_in_trip: float = 1.0
    precipitation_mm: float = 35.0
    sunshine_hours_per_day: float = 8.0
    avg_humidity_pct: int = 60
    uv_index_max: float = 6.0
    snow_reliability_index: float = 0.0
    climate_zone_label_he: str = ""
    weather_summary_he: str = ""
    weather_summary_en: str = ""
    activity_recommendations_he: str = ""
    activity_recommendations_en: str = ""
    below_threshold_warning: bool = False
    overall_weather_suitability_score: float = 0.0
    scores_by_vacation_type: dict[str, float] = field(default_factory=dict)
    recommended_vacation_types: list[str] = field(default_factory=list)
    best_matching_vacation_type: str = "URBAN_CULTURE"

    def __post_init__(self) -> None:
        self.destination_iata = str(self.destination_iata or "FCO").upper()
        self.avg_max_temp_c = round(float(self.avg_max_temp_c), 1)
        self.avg_min_temp_c = round(float(self.avg_min_temp_c), 1)
        if self.sea_water_temp_c is not None and self.sea_water_temp_c != "":
            self.sea_water_temp_c = round(float(self.sea_water_temp_c), 1)
        else:
            self.sea_water_temp_c = None
        self.expected_rain_days_in_trip = round(
            float(self.expected_rain_days_in_trip), 1
        )
        self.precipitation_mm = round(float(self.precipitation_mm), 1)
        self.sunshine_hours_per_day = round(float(self.sunshine_hours_per_day), 1)
        self.avg_humidity_pct = int(round(float(self.avg_humidity_pct)))
        self.uv_index_max = round(float(self.uv_index_max), 1)
        self.snow_reliability_index = round(float(self.snow_reliability_index), 2)
        self.climate_zone_label_he = str(self.climate_zone_label_he or "")
        self.weather_summary_he = str(self.weather_summary_he or "")
        self.weather_summary_en = str(self.weather_summary_en or "")
        self.activity_recommendations_he = str(self.activity_recommendations_he or "")
        self.activity_recommendations_en = str(self.activity_recommendations_en or "")
        self.below_threshold_warning = _parse_bool(self.below_threshold_warning, False)
        self.overall_weather_suitability_score = round(
            float(self.overall_weather_suitability_score or 0.0), 1
        )
        self.scores_by_vacation_type = {
            str(k).upper(): round(float(v), 1)
            for k, v in _parse_json_dict(self.scores_by_vacation_type, {}).items()
        }
        self.recommended_vacation_types = [
            str(x).upper()
            for x in _parse_json_list(self.recommended_vacation_types, [])
        ]
        self.best_matching_vacation_type = str(
            self.best_matching_vacation_type or "URBAN_CULTURE"
        ).upper()

    @property
    def avg_day_high_c(self) -> float:
        return self.avg_max_temp_c

    @property
    def avg_night_low_c(self) -> float:
        return self.avg_min_temp_c

    @property
    def estimated_rain_days_in_trip(self) -> float:
        return self.expected_rain_days_in_trip

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination_iata": self.destination_iata,
            "avg_max_temp_c": self.avg_max_temp_c,
            "avg_min_temp_c": self.avg_min_temp_c,
            "avg_day_high_c": self.avg_max_temp_c,
            "avg_night_low_c": self.avg_min_temp_c,
            "sea_water_temp_c": self.sea_water_temp_c,
            "expected_rain_days_in_trip": self.expected_rain_days_in_trip,
            "estimated_rain_days_in_trip": self.expected_rain_days_in_trip,
            "precipitation_mm": self.precipitation_mm,
            "sunshine_hours_per_day": self.sunshine_hours_per_day,
            "avg_humidity_pct": self.avg_humidity_pct,
            "uv_index_max": self.uv_index_max,
            "snow_reliability_index": self.snow_reliability_index,
            "climate_zone_label_he": self.climate_zone_label_he,
            "weather_summary_he": self.weather_summary_he,
            "weather_summary_en": self.weather_summary_en,
            "activity_recommendations_he": self.activity_recommendations_he,
            "activity_recommendations_en": self.activity_recommendations_en,
            "below_threshold_warning": self.below_threshold_warning,
            "overall_weather_suitability_score": self.overall_weather_suitability_score,
            "scores_by_vacation_type": dict(self.scores_by_vacation_type),
            "recommended_vacation_types": list(self.recommended_vacation_types),
            "best_matching_vacation_type": self.best_matching_vacation_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            destination_iata=str(data.get("destination_iata") or "FCO"),
            avg_max_temp_c=float(
                data.get("avg_max_temp_c", data.get("avg_day_high_c", 22.0))
            ),
            avg_min_temp_c=float(
                data.get("avg_min_temp_c", data.get("avg_night_low_c", 12.0))
            ),
            sea_water_temp_c=data.get("sea_water_temp_c"),
            expected_rain_days_in_trip=float(
                data.get(
                    "expected_rain_days_in_trip",
                    data.get("estimated_rain_days_in_trip", 1.0),
                )
            ),
            precipitation_mm=float(data.get("precipitation_mm", 35.0)),
            sunshine_hours_per_day=float(data.get("sunshine_hours_per_day", 8.0)),
            avg_humidity_pct=int(round(float(data.get("avg_humidity_pct", 60)))),
            uv_index_max=float(data.get("uv_index_max", 6.0)),
            snow_reliability_index=float(data.get("snow_reliability_index", 0.0)),
            climate_zone_label_he=str(data.get("climate_zone_label_he") or ""),
            weather_summary_he=str(data.get("weather_summary_he") or ""),
            weather_summary_en=str(data.get("weather_summary_en") or ""),
            activity_recommendations_he=str(
                data.get("activity_recommendations_he") or ""
            ),
            activity_recommendations_en=str(
                data.get("activity_recommendations_en") or ""
            ),
            below_threshold_warning=_parse_bool(
                data.get("below_threshold_warning", False)
            ),
            overall_weather_suitability_score=float(
                data.get("overall_weather_suitability_score", 0.0) or 0.0
            ),
            scores_by_vacation_type=_parse_json_dict(
                data.get("scores_by_vacation_type"), {}
            ),
            recommended_vacation_types=_parse_json_list(
                data.get("recommended_vacation_types"), []
            ),
            best_matching_vacation_type=str(
                data.get("best_matching_vacation_type") or "URBAN_CULTURE"
            ),
        )


@dataclass
class VacationOptionProposal(_DomainModelBase):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    search_query_id: str = ""
    itinerary_id: str = ""
    associated_holiday_codes: list[str] = field(default_factory=list)
    window_set_type: str = "CAMP_ADJUSTED_INTERSECTION"
    school_absence_penalty: float = 0.0
    childcare_coverage_gain: float = 1.0
    per_child_impact: list[ChildTripImpact] = field(default_factory=list)
    total_school_days_missed_across_children: int = 0
    max_single_child_school_days_missed: int = 0
    holiday_alignment_score: float = 0.0
    flight_bonus_value_score: float = 0.0
    weather_suitability_score: float = 0.0
    vacation_type_scores: dict[str, float] = field(default_factory=dict)
    recommended_vacation_types: list[str] = field(default_factory=list)
    weather_metrics: Optional[DestinationWeatherMetrics] = None
    combined_trip_optimization_score: float = 0.0
    explanation_summary_he: str = ""
    itinerary: Optional[FlightItinerary] = None
    created_at: Optional[str] = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.associated_holiday_codes = [
            str(x) for x in _parse_json_list(self.associated_holiday_codes, [])
        ]
        if self.window_set_type not in WINDOW_SET_TYPES:
            raise ValueError(f"Invalid window_set_type: {self.window_set_type!r}")
        self.school_absence_penalty = float(self.school_absence_penalty)
        self.childcare_coverage_gain = float(self.childcare_coverage_gain)
        self.per_child_impact = [
            ChildTripImpact.from_dict(c) if not isinstance(c, ChildTripImpact) else c
            for c in _parse_json_list(self.per_child_impact, [])
        ]
        self.total_school_days_missed_across_children = int(
            self.total_school_days_missed_across_children
        )
        self.max_single_child_school_days_missed = int(
            self.max_single_child_school_days_missed
        )
        self.holiday_alignment_score = float(self.holiday_alignment_score)
        if self.holiday_alignment_score < 0.0 or self.holiday_alignment_score > 100.0:
            raise ValueError(
                f"holiday_alignment_score must be between 0.0 and 100.0, got {self.holiday_alignment_score}"
            )
        self.flight_bonus_value_score = float(self.flight_bonus_value_score)
        self.weather_suitability_score = round(
            float(self.weather_suitability_score or 0.0), 1
        )
        raw_vts = _parse_json_dict(self.vacation_type_scores, {})
        self.vacation_type_scores = {
            str(k).upper(): round(float(v), 1) for k, v in raw_vts.items()
        }
        self.recommended_vacation_types = [
            str(x).upper()
            for x in _parse_json_list(self.recommended_vacation_types, [])
        ]
        if not self.recommended_vacation_types and self.vacation_type_scores:
            self.recommended_vacation_types = [
                vt
                for vt, sc in sorted(
                    self.vacation_type_scores.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
                if sc >= DEFAULT_VACATION_TYPE_THRESHOLDS.get(vt, 55.0)
            ]
        if self.weather_metrics is not None and not isinstance(
            self.weather_metrics, DestinationWeatherMetrics
        ):
            if isinstance(self.weather_metrics, str):
                wm_parsed = _parse_json_dict(self.weather_metrics, {})
                self.weather_metrics = (
                    DestinationWeatherMetrics.from_dict(wm_parsed)
                    if wm_parsed
                    else None
                )
            elif isinstance(self.weather_metrics, dict):
                self.weather_metrics = DestinationWeatherMetrics.from_dict(
                    self.weather_metrics
                )
        self.combined_trip_optimization_score = float(
            self.combined_trip_optimization_score
        )
        if self.itinerary is not None and not isinstance(
            self.itinerary, FlightItinerary
        ):
            self.itinerary = FlightItinerary.from_dict(self.itinerary)
        if self.itinerary is not None and not self.itinerary_id:
            self.itinerary_id = self.itinerary.id
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        impacts = [c.to_dict() for c in self.per_child_impact]
        wm_dict = self.weather_metrics.to_dict() if self.weather_metrics else None
        return {
            "id": self.id,
            "search_query_id": self.search_query_id,
            "itinerary_id": self.itinerary_id,
            "associated_holiday_codes": list(self.associated_holiday_codes),
            "associated_holiday_codes_json": json.dumps(self.associated_holiday_codes),
            "window_set_type": self.window_set_type,
            "school_absence_penalty": self.school_absence_penalty,
            "childcare_coverage_gain": self.childcare_coverage_gain,
            "per_child_impact": impacts,
            "per_child_impact_json": json.dumps(impacts),
            "total_school_days_missed_across_children": self.total_school_days_missed_across_children,
            "max_single_child_school_days_missed": self.max_single_child_school_days_missed,
            "holiday_alignment_score": self.holiday_alignment_score,
            "flight_bonus_value_score": self.flight_bonus_value_score,
            "weather_suitability_score": self.weather_suitability_score,
            "vacation_type_scores": dict(self.vacation_type_scores),
            "vacation_type_scores_json": json.dumps(self.vacation_type_scores),
            "recommended_vacation_types": list(self.recommended_vacation_types),
            "weather_metrics": wm_dict,
            "weather_metrics_json": json.dumps(wm_dict) if wm_dict else None,
            "combined_trip_optimization_score": self.combined_trip_optimization_score,
            "explanation_summary_he": self.explanation_summary_he,
            "itinerary": self.itinerary.to_dict() if self.itinerary else None,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        holidays = data.get("associated_holiday_codes")
        if holidays is None:
            holidays = data.get("associated_holiday_codes_json", [])
        impacts = data.get("per_child_impact")
        if impacts is None:
            impacts = data.get("per_child_impact_json", [])
        vts = data.get("vacation_type_scores")
        if vts is None:
            vts = data.get("vacation_type_scores_json", {})
        wm = data.get("weather_metrics")
        if wm is None and data.get("weather_metrics_json"):
            wm = _parse_json_dict(data.get("weather_metrics_json"), {})
        itin_data = data.get("itinerary")
        itin = FlightItinerary.from_dict(itin_data) if itin_data else None
        raw_has = data.get("holiday_alignment_score")
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            search_query_id=str(data.get("search_query_id") or ""),
            itinerary_id=str(
                data.get("itinerary_id") or (itin.id if itin is not None else "")
            ),
            associated_holiday_codes=_parse_json_list(holidays, []),
            window_set_type=str(
                data.get("window_set_type") or "CAMP_ADJUSTED_INTERSECTION"
            ),
            school_absence_penalty=float(data.get("school_absence_penalty", 0.0)),
            childcare_coverage_gain=float(data.get("childcare_coverage_gain", 1.0)),
            per_child_impact=_parse_json_list(impacts, []),
            total_school_days_missed_across_children=int(
                data.get("total_school_days_missed_across_children", 0)
            ),
            max_single_child_school_days_missed=int(
                data.get("max_single_child_school_days_missed", 0)
            ),
            holiday_alignment_score=(
                float(raw_has) if raw_has is not None else 0.0
            ),
            flight_bonus_value_score=float(data.get("flight_bonus_value_score", 0.0)),
            weather_suitability_score=float(
                data.get("weather_suitability_score", 0.0) or 0.0
            ),
            vacation_type_scores=_parse_json_dict(vts, {}),
            recommended_vacation_types=_parse_json_list(
                data.get("recommended_vacation_types"), []
            ),
            weather_metrics=(
                DestinationWeatherMetrics.from_dict(wm) if wm else None
            ),
            combined_trip_optimization_score=float(
                data.get("combined_trip_optimization_score", 0.0)
            ),
            explanation_summary_he=str(data.get("explanation_summary_he") or ""),
            itinerary=itin,
            created_at=data.get("created_at") or _now_iso(),
        )


@dataclass
class DailyFamilyCalendarMatrix(_DomainModelBase):
    school_year: str
    start_date: date
    end_date: date
    dates: list[date] = field(default_factory=list)
    tlv_airport_closed_by_date: dict[str, bool] = field(default_factory=dict)
    holiday_codes_by_date: dict[str, list[str]] = field(default_factory=dict)
    child_status_by_id: dict[str, dict[str, ChildDayStatus]] = field(
        default_factory=dict
    )
    strict_intersection_dates: list[date] = field(default_factory=list)
    camp_adjusted_intersection_dates: list[date] = field(default_factory=list)
    framework_delta_union_dates: list[date] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.start_date = _parse_date(self.start_date)
        self.end_date = _parse_date(self.end_date)
        self.dates = [_parse_date(d) for d in self.dates]
        self.strict_intersection_dates = [
            _parse_date(d) for d in self.strict_intersection_dates
        ]
        self.camp_adjusted_intersection_dates = [
            _parse_date(d) for d in self.camp_adjusted_intersection_dates
        ]
        self.framework_delta_union_dates = [
            _parse_date(d) for d in self.framework_delta_union_dates
        ]

    def to_dict(self) -> dict[str, Any]:
        serialized_children: dict[str, dict[str, Any]] = {}
        for cid, day_map in self.child_status_by_id.items():
            serialized_children[cid] = {
                k: (v.to_dict() if isinstance(v, ChildDayStatus) else v)
                for k, v in day_map.items()
            }
        return {
            "school_year": self.school_year,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "dates": [d.isoformat() for d in self.dates],
            "tlv_airport_closed_by_date": dict(self.tlv_airport_closed_by_date),
            "holiday_codes_by_date": dict(self.holiday_codes_by_date),
            "child_status_by_id": serialized_children,
            "strict_intersection_dates": [
                d.isoformat() for d in self.strict_intersection_dates
            ],
            "camp_adjusted_intersection_dates": [
                d.isoformat() for d in self.camp_adjusted_intersection_dates
            ],
            "framework_delta_union_dates": [
                d.isoformat() for d in self.framework_delta_union_dates
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        raw_children = data.get("child_status_by_id") or {}
        parsed_children: dict[str, dict[str, ChildDayStatus]] = {}
        for cid, day_map in raw_children.items():
            parsed_children[cid] = {
                k: ChildDayStatus.from_dict(v) for k, v in day_map.items()
            }
        return cls(
            school_year=str(data.get("school_year") or "2026-2027"),
            start_date=_parse_date(data["start_date"]),
            end_date=_parse_date(data["end_date"]),
            dates=[_parse_date(d) for d in (data.get("dates") or [])],
            tlv_airport_closed_by_date=dict(
                data.get("tlv_airport_closed_by_date") or {}
            ),
            holiday_codes_by_date=dict(data.get("holiday_codes_by_date") or {}),
            child_status_by_id=parsed_children,
            strict_intersection_dates=[
                _parse_date(d)
                for d in (data.get("strict_intersection_dates") or [])
            ],
            camp_adjusted_intersection_dates=[
                _parse_date(d)
                for d in (data.get("camp_adjusted_intersection_dates") or [])
            ],
            framework_delta_union_dates=[
                _parse_date(d)
                for d in (data.get("framework_delta_union_dates") or [])
            ],
        )


@dataclass
class CandidateVacationWindow(_DomainModelBase):
    start_date: date
    end_date: date
    trip_nights: int = 1
    window_set_type: str = "CAMP_ADJUSTED_INTERSECTION"
    associated_holiday_codes: list[str] = field(default_factory=list)
    school_absence_penalty: float = 0.0
    childcare_coverage_gain: float = 0.0
    holiday_alignment_score: float = 0.0
    per_child_impact: list[ChildTripImpact] = field(default_factory=list)
    total_school_days_missed_across_children: int = 0
    max_single_child_school_days_missed: int = 0
    bridge_days_used: int = 0
    has_tlv_airport_closure_on_endpoints: bool = False
    has_bagrut_blackout: bool = False
    explanation_summary_he: str = ""

    def __post_init__(self) -> None:
        self.start_date = _parse_date(self.start_date)
        self.end_date = _parse_date(self.end_date)
        self.trip_nights = int(
            self.trip_nights or max(1, (self.end_date - self.start_date).days)
        )
        self.associated_holiday_codes = [
            str(x) for x in _parse_json_list(self.associated_holiday_codes, [])
        ]
        self.school_absence_penalty = float(self.school_absence_penalty)
        self.childcare_coverage_gain = float(self.childcare_coverage_gain)
        self.holiday_alignment_score = float(self.holiday_alignment_score)
        if self.holiday_alignment_score < 0.0 or self.holiday_alignment_score > 100.0:
            raise ValueError(
                f"holiday_alignment_score must be between 0.0 and 100.0, got {self.holiday_alignment_score}"
            )
        self.per_child_impact = [
            ChildTripImpact.from_dict(c) if not isinstance(c, ChildTripImpact) else c
            for c in (self.per_child_impact or [])
        ]
        self.total_school_days_missed_across_children = int(
            self.total_school_days_missed_across_children
        )
        self.max_single_child_school_days_missed = int(
            self.max_single_child_school_days_missed
        )
        self.bridge_days_used = int(self.bridge_days_used)
        self.has_tlv_airport_closure_on_endpoints = _parse_bool(
            self.has_tlv_airport_closure_on_endpoints, False
        )
        self.has_bagrut_blackout = _parse_bool(self.has_bagrut_blackout, False)

    @property
    def SAP(self) -> float:
        return self.school_absence_penalty

    @property
    def CCG(self) -> float:
        return self.childcare_coverage_gain

    @property
    def HAS(self) -> float:
        return self.holiday_alignment_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "trip_nights": self.trip_nights,
            "window_set_type": self.window_set_type,
            "associated_holiday_codes": list(self.associated_holiday_codes),
            "school_absence_penalty": self.school_absence_penalty,
            "childcare_coverage_gain": self.childcare_coverage_gain,
            "holiday_alignment_score": self.holiday_alignment_score,
            "per_child_impact": [c.to_dict() for c in self.per_child_impact],
            "total_school_days_missed_across_children": self.total_school_days_missed_across_children,
            "max_single_child_school_days_missed": self.max_single_child_school_days_missed,
            "bridge_days_used": self.bridge_days_used,
            "has_tlv_airport_closure_on_endpoints": self.has_tlv_airport_closure_on_endpoints,
            "has_bagrut_blackout": self.has_bagrut_blackout,
            "explanation_summary_he": self.explanation_summary_he,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        s_date = _parse_date(data["start_date"])
        e_date = _parse_date(data["end_date"])
        raw_has = data.get("holiday_alignment_score")
        return cls(
            start_date=s_date,
            end_date=e_date,
            trip_nights=int(
                data.get("trip_nights") or max(1, (e_date - s_date).days)
            ),
            window_set_type=str(
                data.get("window_set_type") or "CAMP_ADJUSTED_INTERSECTION"
            ),
            associated_holiday_codes=_parse_json_list(
                data.get("associated_holiday_codes"), []
            ),
            school_absence_penalty=float(data.get("school_absence_penalty", 0.0)),
            childcare_coverage_gain=float(data.get("childcare_coverage_gain", 0.0)),
            holiday_alignment_score=(
                float(raw_has) if raw_has is not None else 0.0
            ),
            per_child_impact=[
                ChildTripImpact.from_dict(c)
                for c in (data.get("per_child_impact") or [])
            ],
            total_school_days_missed_across_children=int(
                data.get("total_school_days_missed_across_children", 0)
            ),
            max_single_child_school_days_missed=int(
                data.get("max_single_child_school_days_missed", 0)
            ),
            bridge_days_used=int(data.get("bridge_days_used", 0)),
            has_tlv_airport_closure_on_endpoints=_parse_bool(
                data.get("has_tlv_airport_closure_on_endpoints", False)
            ),
            has_bagrut_blackout=_parse_bool(data.get("has_bagrut_blackout", False)),
            explanation_summary_he=str(data.get("explanation_summary_he") or ""),
        )


@dataclass
class MoECalendarSyncStatus(_DomainModelBase):
    school_year: str
    school_year_hebrew: str
    calendar_sync_source: str
    windows_synced_count: int
    last_synced_at: str = field(default_factory=_now_iso)
    windows: list[MoEVacationWindow] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.windows_synced_count = int(self.windows_synced_count)
        self.windows = [
            MoEVacationWindow.from_dict(w)
            if not isinstance(w, MoEVacationWindow)
            else w
            for w in (self.windows or [])
        ]
        if not self.last_synced_at:
            self.last_synced_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "school_year": self.school_year,
            "school_year_hebrew": self.school_year_hebrew,
            "calendar_sync_source": self.calendar_sync_source,
            "windows_synced_count": self.windows_synced_count,
            "last_synced_at": self.last_synced_at,
            "windows": [w.to_dict() for w in self.windows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | Self) -> Self:
        if isinstance(data, cls):
            return data
        raw_windows = data.get("windows") or []
        return cls(
            school_year=str(data["school_year"]),
            school_year_hebrew=str(data.get("school_year_hebrew") or ""),
            calendar_sync_source=str(
                data.get("calendar_sync_source") or "OFFICIAL_MOE_CIRCULAR"
            ),
            windows_synced_count=int(
                data.get("windows_synced_count", len(raw_windows))
            ),
            last_synced_at=str(data.get("last_synced_at") or _now_iso()),
            windows=[MoEVacationWindow.from_dict(w) for w in raw_windows],
        )

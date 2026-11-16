/**
 * Canonical TypeScript Domain Contracts (`frontend/src/types/domain.ts`)
 * Synchronized 1-to-1 with `backend/app/schemas/domain.py`.
 */

export type MoEFrameworkType =
  | 'DAYCARE_SUPERVISED'
  | 'MUNICIPAL_GAN'
  | 'ELEMENTARY_1_3'
  | 'ELEMENTARY_4_6'
  | 'MIDDLE_SCHOOL_7_9'
  | 'HIGH_SCHOOL_10_12'
  | 'SPECIAL_ED'
  | 'RELIGIOUS_HAREDI';

export type HolidayExtensionMode =
  | 'NONE'
  | 'NITZANIM_CHAGIM_ONLY'
  | 'NITZANIM_FULL_WITH_JULY';

export type DateSelectionMode =
  | 'SPECIFIC_DATES'
  | 'MOE_VACATION_MAXIMIZATION'
  | 'HOLIDAY_DIRECT_INTENT';

export type DirectHolidayCode =
  | 'ROSH_HASHANAH'
  | 'YOM_KIPPUR_SUKKOT_BRIDGE'
  | 'SUKKOT'
  | 'HANUKKAH'
  | 'PURIM'
  | 'PESACH'
  | 'YOM_HAATZMAUT'
  | 'LAG_BAOMER'
  | 'SHAVUOT'
  | 'SUMMER_JUNE_20_30'
  | 'SUMMER_JULY'
  | 'SUMMER_AUGUST';

export type AirlineSelectionMode = 'EL_AL_ONLY' | 'ALL_AIRLINES';

export type LoyaltyProgramCode =
  | 'ELAL_MATMID'
  | 'BRITISH_AVIOS'
  | 'FLYING_BLUE'
  | 'UNITED_MILEAGEPLUS'
  | 'MILES_AND_MORE'
  | 'DELTA_SKYMILES'
  | 'QANTAS_FREQUENT_FLYER'
  | 'AEGEAN_MILES_BONUS'
  | 'AMEX_MR_ISRAEL'
  | 'ISRAELI_CC_TRAVEL_POINTS';

export type FulfillmentStrategy =
  | 'FULL_BONUS_SAME_CABIN'
  | 'SPLIT_CABIN_BONUS'
  | 'HYBRID_BONUS_PLUS_CASH'
  | 'ONE_WAY_BONUS_ONE_WAY_CASH'
  | 'CASH_AND_POINTS'
  | 'MULTI_CLUB_PER_PASSENGER_SPLIT'
  | 'COMMERCIAL_CASH_FARE';

export type OverlapPolicy =
  | 'STRICT_ALL_CHILDREN_OFF'
  | 'CAMP_AWARE_ALL_CHILDREN_OFF'
  | 'WEIGHTED_MIN_ABSENCE';

export interface ChildFramework {
  id: string;
  child_name_he: string;
  child_age_years: number;
  passenger_fare_type: 'INFANT_LAP' | 'CHILD_2_11' | 'YOUTH_12_18';
  framework_type: MoEFrameworkType | null;
  school_week_days: 5 | 6;
  holiday_extension_mode: HolidayExtensionMode;
  treat_camp_as_vacation: boolean;
  bagrut_blackout_dates: string[];
}

export interface PassengerLoyaltyWallet {
  id: string;
  passenger_id: string;
  passenger_name: string;
  program_code: LoyaltyProgramCode;
  available_points: number;
  companion_vouchers_count: number;
  allow_household_pooling: boolean;
  point_valuation_cents: number;
}

export interface FamilyProfile {
  id: string;
  profile_name: string;
  adults_count: number;
  workweek_type: 'SUN_THU' | 'SUN_FRI';
  erev_chag_pto_weight: 0.0 | 0.5 | 1.0;
  chol_hamoed_pto_weight: 0.0 | 0.5 | 1.0;
  annual_pto_budget: number;
  max_pto_per_trip: number;
  matmid_points_balance: number;
  has_flycard: boolean;
  flycard_tier: 'NONE' | 'FLYCARD' | 'FLYCARD_PREMIUM';
  flycard_companion_vouchers: number;
  point_valuation_usd: number;
  preferred_currency: 'USD' | 'ILS';
  children: ChildFramework[];
  passenger_loyalty_wallets: PassengerLoyaltyWallet[];
}

export interface FlightSearchQuery {
  origin_iata: string;
  destination_iatas: string[];
  date_selection_mode: DateSelectionMode;
  school_year?: string;
  direct_holiday_code?: DirectHolidayCode;
  direct_target_year?: number;
  overlap_policy: OverlapPolicy;
  specific_departure_date?: string;
  specific_return_date?: string;
  flex_days_plus_minus: number;
  max_bridge_days_shift: number;
  min_trip_nights: number;
  max_trip_nights: number;
  airline_selection_mode: AirlineSelectionMode;
  search_elal_bonus_rbd: boolean;
  preferred_cabins: Array<'ECONOMY' | 'PREMIUM' | 'BUSINESS'>;
  allow_hybrid_bonus_plus_cash: boolean;
  allow_split_cabin_bonus: boolean;
  allow_multi_club_per_passenger: boolean;
  max_stops: 0 | 1 | 2;
  checked_bags_count: number;
}

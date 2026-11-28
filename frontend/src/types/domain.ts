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
  | 'HOLIDAY_DIRECT_INTENT';

export type CalendarPlanningMode = 'MOE' | 'WORKPLACE';

export type WorkplaceHolidayCode =
  | 'ROSH_HASHANAH'
  | 'YOM_KIPPUR_SUKKOT_BRIDGE'
  | 'SUKKOT'
  | 'PESACH'
  | 'YOM_HAATZMAUT'
  | 'SHAVUOT';

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
  | 'COMMERCIAL_CASH_ONLY';

export type BonusDirectionCoverage =
  | 'BOTH_DIRECTIONS'
  | 'OUTBOUND_ONLY'
  | 'INBOUND_ONLY'
  | 'NONE';

export type MinPointsBasis = 'ROUND_TRIP' | 'ONE_WAY';

export type OverlapPolicy =
  | 'STRICT_ALL_CHILDREN_OFF'
  | 'CAMP_AWARE_ALL_CHILDREN_OFF'
  | 'WEIGHTED_MIN_ABSENCE';

export type VacationType =
  | 'ANY'
  | 'BEACH_AND_POOL'
  | 'NATURE_TRIP'
  | 'URBAN_CULTURE'
  | 'FAMILY_ATTRACTIONS_PARKS'
  | 'SNOW_AND_SKI'
  | 'WINTER_FESTIVE';

export type WeatherFilterMode = 'SOFT_PRIORITIZE' | 'HARD_THRESHOLD';

export interface DestinationWeatherMetrics {
  destination_iata: string;
  climate_profile: string;
  avg_day_high_c: number;
  avg_night_low_c: number;
  sea_water_temp_c: number | null;
  rainfall_mm_per_month: number;
  rain_days_per_month: number;
  estimated_rain_days_in_trip: number;
  sunshine_hours_per_day: number;
  uv_index: number;
  humidity_pct: number;
  snow_reliability_index: number;
  scores_by_vacation_type: Record<VacationType, number>;
  best_matching_vacation_type: VacationType;
  overall_weather_suitability_score: number;
  recommended_vacation_types: VacationType[];
  weather_summary_he: string;
  weather_summary_en: string;
}

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
  preferred_vacation_types?: VacationType[];
  weather_filter_mode?: WeatherFilterMode;
  min_weather_suitability_score?: number | null;
}

export interface FlightLeg {
  flight_number: string;
  operating_carrier: string;
  origin_iata: string;
  destination_iata: string;
  flight_date: string;
  departure_time_local: string;
  arrival_time_local: string;
  aircraft_type: string;
  duration_minutes: number;
  is_direct: boolean;
}

export interface FlightItinerary {
  id: string;
  search_query_id: string | null;
  origin_iata: string;
  destination_iata: string;
  return_origin_iata: string;
  destination_city_he: string;
  destination_city_en: string;
  departure_date: string;
  return_date: string;
  trip_nights: number;
  primary_carrier_iata: string;
  is_elal_flight: boolean;
  utilizes_elal_bonus: boolean;
  fulfillment_strategy: FulfillmentStrategy;
  outbound_legs: FlightLeg[];
  inbound_legs: FlightLeg[];
  outbound_bonus_id: string | null;
  inbound_bonus_id: string | null;
  seated_passengers_count: number;
  bonus_tickets_count: number;
  cash_tickets_count: number;
  primary_cabin: 'ECONOMY' | 'PREMIUM' | 'BUSINESS';
  requires_two_plus_seat_verification: boolean;
  bonus_direction_coverage: BonusDirectionCoverage;
  outbound_bonus_seats: number | null;
  inbound_bonus_seats: number | null;
  outbound_bonus_seats_is_two_plus: boolean;
  inbound_bonus_seats_is_two_plus: boolean;
  min_points_per_bonus_ticket: number | null;
  min_points_basis: MinPointsBasis | null;
  points_are_estimated: boolean;
  elal_google_flights_url: string | null;
  elal_google_flights_single_adult_url: string | null;
}

export interface WorkplaceHolidayPeriod {
  id: string;
  school_year: string;
  school_year_hebrew?: string;
  holiday_code: string;
  name_he: string;
  name_en: string;
  start_date: string;
  end_date: string;
  calendar_days: number;
  workplace_status: 'OFFICIAL_HOLIDAY' | 'CHOL_HAMOED';
  workday_cost_per_day: 0 | 0.5;
  effective_workdays_cost: number;
  status_badge_he: string;
  status_badge_en: string;
}

export interface UpcomingWorkplaceHoliday {
  holiday_code: WorkplaceHolidayCode;
  name_he: string;
  name_en: string;
  target_year: number;
  school_year: string;
  start_date: string;
  end_date: string;
  holiday_days: number;
  recommended_window_start: string;
  recommended_window_end: string;
  recommended_trip_days: number;
  recommended_workdays_cost: number;
  recommended_workdays_saved: number;
  recommended_efficiency_ratio: number;
  workplace_workdays_cost: number;
  official_holiday_days: number;
  chol_hamoed_days: number;
  is_ongoing: boolean;
  calendar_mode: 'WORKPLACE';
  label_he: string;
  label_en: string;
}

export interface UpcomingWorkplaceHolidaysResponse {
  as_of_date: string;
  window_end_date: string;
  calendar_mode: 'WORKPLACE';
  count: number;
  holidays: UpcomingWorkplaceHoliday[];
}

export interface VacationOptionProposal {
  id: string;
  search_query_id: string;
  itinerary_id: string;
  associated_holiday_codes: string[];
  window_set_type: WindowSetType;
  school_absence_penalty: number;
  childcare_coverage_gain: number;
  total_school_days_missed_across_children: number;
  max_single_child_school_days_missed: number;
  holiday_alignment_score: number;
  flight_bonus_value_score: number;
  weather_suitability_score: number;
  combined_trip_optimization_score: number;
  workplace_vacation_days_cost: number;
  regular_workdays_count: number;
  chol_hamoed_workdays_count: number;
  official_holiday_workdays_saved_count: number;
  weekend_days_count: number;
  holiday_or_weekend_days_count: number;
  calendar_mode?: CalendarPlanningMode;
  trip_calendar_days?: number;
  workdays_saved_count?: number;
  workday_efficiency_ratio?: number;
  workday_efficiency_score?: number;
  is_zero_workday_trip?: boolean;
  explanation_summary_he?: string;
  itinerary: FlightItinerary | null;
}

export interface VacationSearchResponse {
  query: FlightSearchQuery;
  calendar_mode: CalendarPlanningMode;
  expanded_destinations: string[];
  count: number;
  live_fetch_mode: boolean;
  status_message_he: string | null;
  status_message_en: string | null;
  weather_fallback_message_he: string | null;
  proposals: VacationOptionProposal[];
}

TEST (name "int_delivery_slot_utilisation__flags_holidays_and_compares_with_weekday_average");

WITH __ref__stg_delivery_slots AS (
  SELECT
    'A' AS slot_id,
    'W1' AS warehouse_code,
    '2026-04-06 08:00:00'::TIMESTAMP_NTZ AS slot_start_local,
    NULL AS slot_end_local,
    NULL AS slot_minutes,
    10 AS capacity,
    10 AS booked,
    0 AS remaining_capacity,
    NULL AS excluded_postcode_prefixes,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'B',
    'W1',
    '2026-04-06 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    10,
    5,
    5,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C',
    'W1',
    '2026-04-13 09:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    20,
    5,
    15,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'D',
    'W2',
    '2026-04-11 09:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    4,
    1,
    3,
    NULL,
    NULL,
    NULL
),

__ref__stg_warehouses AS (
  SELECT
    'W1' AS warehouse_code,
    NULL AS warehouse_name,
    'DE' AS country_code,
    NULL AS iana_timezone,
    NULL AS opens_local,
    NULL AS closes_local,
    NULL AS opening_minutes,
    NULL AS supports_same_day,
    NULL AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'W2',
    NULL,
    'ZZ',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__seed__countries AS (
  SELECT
    'DE' AS country_code,
    NULL AS country_name,
    'EU' AS region_code,
    NULL AS default_timezone,
    NULL AS currency_code,
    NULL AS vat_registered
),

__seed__holiday_calendar AS (
  SELECT
    'EU' AS region_code,
    '2026-04-06'::DATE AS holiday_date,
    'Easter Monday' AS holiday_name
  UNION ALL
  SELECT
    'US',
    '2026-04-13'::DATE,
    'Synthetic holiday'
),

__expected__int_delivery_slot_utilisation AS (
  SELECT
    'W1|2026-04-06' AS slot_day_key,
    2 AS slot_count,
    20 AS total_capacity,
    15 AS total_booked,
    0.75::DECIMAL(9, 4) AS utilisation,
    1 AS full_slot_count,
    '2026-04-06 08:00:00'::TIMESTAMPNTZ AS busiest_slot_start_local,
    FALSE AS is_weekend,
    'EU' AS region_code,
    TRUE AS is_holiday,
    0.25::DECIMAL(9, 4) AS utilisation_vs_weekday_avg
  UNION ALL
  SELECT
    'W1|2026-04-13' AS slot_day_key,
    1 AS slot_count,
    20 AS total_capacity,
    5 AS total_booked,
    0.25::DECIMAL(9, 4) AS utilisation,
    0 AS full_slot_count,
    '2026-04-13 09:00:00'::TIMESTAMPNTZ AS busiest_slot_start_local,
    FALSE AS is_weekend,
    'EU' AS region_code,
    FALSE AS is_holiday,
    -0.25::DECIMAL(9, 4) AS utilisation_vs_weekday_avg
  UNION ALL
  SELECT
    'W2|2026-04-11' AS slot_day_key,
    1 AS slot_count,
    4 AS total_capacity,
    1 AS total_booked,
    0.25::DECIMAL(9, 4) AS utilisation,
    0 AS full_slot_count,
    '2026-04-11 09:00:00'::TIMESTAMPNTZ AS busiest_slot_start_local,
    TRUE AS is_weekend,
    CAST(NULL AS VARCHAR) AS region_code,
    FALSE AS is_holiday,
    0.0::DECIMAL(9, 4) AS utilisation_vs_weekday_avg
)

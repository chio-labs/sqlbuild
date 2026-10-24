TEST (name "dim_warehouses__adds_region_offset_bins_and_latest_stock");

WITH __ref__stg_warehouses AS (
  SELECT
    'POND' AS warehouse_code,
    'The Pond' AS warehouse_name,
    'DE' AS country_code,
    'Europe/Berlin' AS iana_timezone,
    NULL AS opens_local,
    NULL AS closes_local,
    720 AS opening_minutes,
    TRUE AS supports_same_day,
    FALSE AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'NEST',
    'The Nest',
    'US',
    'America/New_York',
    NULL,
    NULL,
    480,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL
),

__ref__stg_bin_locations AS (
  SELECT
    'B1' AS bin_id,
    'POND' AS warehouse_code,
    NULL AS bin_label,
    NULL AS aisle,
    NULL AS bay,
    NULL AS shelf_level,
    NULL AS is_pick_face,
    NULL AS max_weight_kg,
    NULL AS temperature_zone,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'B2',
    'POND',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'B3',
    'POND',
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

__ref__int_inventory_valuation_daily AS (
  SELECT
    'POND|2026-03-30' AS valuation_key,
    'POND' AS warehouse_code,
    '2026-03-30'::DATE AS calendar_date,
    NULL AS sku_count,
    100 AS units_on_hand,
    NULL AS stock_value_usd,
    NULL AS unvalued_units,
    NULL AS stocked_out_skus,
    NULL AS value_change_usd
  UNION ALL
  SELECT
    'POND|2026-03-31',
    'POND',
    '2026-03-31'::DATE,
    NULL,
    90,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'POND|2026-04-01',
    'POND',
    '2026-04-01'::DATE,
    NULL,
    50,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_delivery_slot_utilisation AS (
  SELECT
    'POND|2026-03-30' AS slot_day_key,
    'POND' AS warehouse_code,
    NULL AS slot_date_local,
    NULL AS slot_count,
    NULL AS total_capacity,
    NULL AS total_booked,
    0.5::DECIMAL(9, 4) AS utilisation,
    NULL AS full_slot_count,
    NULL AS busiest_slot_start_local,
    NULL AS is_weekend,
    NULL AS region_code,
    NULL AS is_holiday,
    NULL AS utilisation_vs_weekday_avg
  UNION ALL
  SELECT
    'POND|2026-03-31',
    'POND',
    NULL,
    NULL,
    NULL,
    NULL,
    0.75::DECIMAL(9, 4),
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
  UNION ALL
  SELECT
    'US',
    NULL,
    'US',
    NULL,
    NULL,
    NULL
),

__expected__dim_warehouses AS (
  SELECT
    'POND' AS warehouse_code,
    'The Pond' AS warehouse_name,
    'EU' AS region_code,
    2.0::DECIMAL(4, 2) AS utc_offset_hours,
    3 AS bin_count,
    90 AS units_on_hand,
    0.625::DECIMAL(9, 4) AS average_slot_utilisation
  UNION ALL
  SELECT
    'NEST' AS warehouse_code,
    'The Nest' AS warehouse_name,
    'US' AS region_code,
    -4.0::DECIMAL(4, 2) AS utc_offset_hours,
    0 AS bin_count,
    0 AS units_on_hand,
    CAST(NULL AS DECIMAL(9, 4)) AS average_slot_utilisation
),

__assert__warehouse_code_is_unique_and_present AS (
  SELECT t.warehouse_code
  FROM __ref("dim_warehouses") AS t
  GROUP BY
    t.warehouse_code
  HAVING
    COUNT(*) > 1
    OR t.warehouse_code IS NULL
)

TEST (name "snap_warehouses__captures_hours_and_capabilities");

WITH __ref__stg_warehouses AS (
  SELECT
    'POND' AS warehouse_code,
    'The Pond' AS warehouse_name,
    NULL AS country_code,
    'Europe/Berlin' AS iana_timezone,
    '08:00:00'::TIME AS opens_local,
    '20:00:00'::TIME AS closes_local,
    NULL AS opening_minutes,
    TRUE AS supports_same_day,
    FALSE AS supports_cold_chain,
    31.5::DECIMAL(6, 2) AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'NEST',
    'The Nest',
    NULL,
    'America/New_York',
    '07:30:00'::TIME,
    '15:30:00'::TIME,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL
),

__expected__snap_warehouses AS (
  SELECT
    'POND' AS warehouse_code,
    '08:00:00'::TIME AS opens_local,
    TRUE AS supports_same_day,
    31.5::NUMBER(6, 2) AS max_parcel_kg
  UNION ALL
  SELECT
    'NEST' AS warehouse_code,
    '07:30:00'::TIME AS opens_local,
    FALSE AS supports_same_day,
    CAST(NULL AS NUMBER(6, 2)) AS max_parcel_kg
),

__assert__warehouse_code_is_unique_and_present AS (
  SELECT t.warehouse_code
  FROM __ref("snap_warehouses") AS t
  GROUP BY
    t.warehouse_code
  HAVING
    COUNT(*) > 1
    OR t.warehouse_code IS NULL
)

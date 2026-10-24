TEST (name "stg_warehouses__derives_opening_minutes_and_capabilities");

WITH __source__inventory__warehouses AS (
  SELECT
    'pond' AS warehouse_code,
    'The Pond' AS warehouse_name,
    'de' AS country_code,
    'Europe/Berlin' AS iana_timezone,
    '08:00:00'::TIME AS opens_local,
    '20:00:00'::TIME AS closes_local,
    PARSE_JSON('{"services": ["same_day", "returns"], "cold_chain": false, "limits": {"max_parcel_kg": 31.5}}')::VARIANT AS capabilities,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'nest',
    'Nest Annex',
    'us',
    'America/New_York',
    '07:30:00'::TIME,
    '15:30:00'::TIME,
    NULL,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'nest',
    'The Nest',
    'us',
    'America/New_York',
    '07:30:00'::TIME,
    '15:30:00'::TIME,
    NULL,
    'U',
    3,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'reed',
    'The Reedbed',
    'gb',
    'Europe/London',
    '08:00:00'::TIME,
    '16:00:00'::TIME,
    NULL,
    'I',
    4,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'reed',
    'The Reedbed',
    'gb',
    'Europe/London',
    '08:00:00'::TIME,
    '16:00:00'::TIME,
    NULL,
    'D',
    5,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_warehouses AS (
  SELECT
    'POND' AS warehouse_code,
    'The Pond' AS warehouse_name,
    'DE' AS country_code,
    720 AS opening_minutes,
    TRUE AS supports_same_day,
    FALSE AS supports_cold_chain,
    31.5::DECIMAL(6, 2) AS max_parcel_kg,
    1 AS source_seq
  UNION ALL
  SELECT
    'NEST' AS warehouse_code,
    'The Nest' AS warehouse_name,
    'US' AS country_code,
    480 AS opening_minutes,
    FALSE AS supports_same_day,
    FALSE AS supports_cold_chain,
    CAST(NULL AS DECIMAL(6, 2)) AS max_parcel_kg,
    3 AS source_seq
)

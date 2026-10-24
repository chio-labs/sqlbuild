TEST (name "int_pick_performance__ranks_pickers_by_rate_within_warehouse_day");

WITH __ref__stg_pick_tasks AS (
  SELECT
    'T1' AS task_id,
    NULL AS order_id,
    'W1' AS warehouse_code,
    'P1' AS picker_id,
    '2026-04-06 08:15:00'::TIMESTAMPNTZ AS started_at_local,
    '2026-04-06 08:15:00'::TIMESTAMPNTZ AS completed_at_local,
    1800 AS pick_seconds,
    NULL AS line_count,
    30 AS units_picked,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    NULL,
    'W1',
    'P1',
    '2026-04-06 09:00:00'::TIMESTAMPNTZ,
    '2026-04-06 09:00:00'::TIMESTAMPNTZ,
    1800,
    NULL,
    30,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    NULL,
    'W1',
    'P2',
    '2026-04-06 07:30:00'::TIMESTAMPNTZ,
    '2026-04-06 07:30:00'::TIMESTAMPNTZ,
    3600,
    NULL,
    90,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    NULL,
    'W1',
    'P2',
    '2026-04-06 06:00:00'::TIMESTAMPNTZ,
    NULL,
    600,
    NULL,
    10,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T5',
    NULL,
    'W1',
    'P2',
    '2026-04-06 06:30:00'::TIMESTAMPNTZ,
    '2026-04-06 06:30:00'::TIMESTAMPNTZ,
    0,
    NULL,
    10,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T6',
    NULL,
    'W1',
    'P3',
    '2026-04-07 10:00:00'::TIMESTAMPNTZ,
    '2026-04-07 10:00:00'::TIMESTAMPNTZ,
    600,
    NULL,
    5,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T7',
    NULL,
    'W1',
    'P3',
    '2026-04-07 11:00:00'::TIMESTAMPNTZ,
    '2026-04-07 11:00:00'::TIMESTAMPNTZ,
    1200,
    NULL,
    10,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T8',
    NULL,
    'W1',
    'P3',
    '2026-04-07 12:00:00'::TIMESTAMPNTZ,
    '2026-04-07 12:00:00'::TIMESTAMPNTZ,
    1800,
    NULL,
    15,
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
    480 AS opening_minutes,
    NULL AS supports_same_day,
    NULL AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
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
),

__expected__int_pick_performance AS (
  SELECT
    'P1|W1|2026-04-06' AS picker_day_key,
    2 AS task_count,
    60 AS units_picked,
    1.0::DECIMAL(10, 2) AS active_hours,
    60.0::DECIMAL(10, 2) AS units_per_hour,
    1800 AS p90_task_seconds,
    2 AS rank_in_warehouse,
    8 AS first_task_hour_local,
    0.125::DECIMAL(9, 4) AS shift_coverage,
    TRUE AS is_holiday
  UNION ALL
  SELECT
    'P2|W1|2026-04-06' AS picker_day_key,
    1 AS task_count,
    90 AS units_picked,
    1.0::DECIMAL(10, 2) AS active_hours,
    90.0::DECIMAL(10, 2) AS units_per_hour,
    3600 AS p90_task_seconds,
    1 AS rank_in_warehouse,
    7 AS first_task_hour_local,
    0.125::DECIMAL(9, 4) AS shift_coverage,
    TRUE AS is_holiday
  UNION ALL
  SELECT
    'P3|W1|2026-04-07' AS picker_day_key,
    3 AS task_count,
    30 AS units_picked,
    1.0::DECIMAL(10, 2) AS active_hours,
    30.0::DECIMAL(10, 2) AS units_per_hour,
    1800 AS p90_task_seconds,
    1 AS rank_in_warehouse,
    10 AS first_task_hour_local,
    0.125::DECIMAL(9, 4) AS shift_coverage,
    FALSE AS is_holiday
)

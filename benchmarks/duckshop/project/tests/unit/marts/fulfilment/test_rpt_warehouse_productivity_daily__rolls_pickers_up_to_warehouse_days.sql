TEST (name "rpt_warehouse_productivity_daily__rolls_pickers_up_to_warehouse_days");

WITH __ref__int_pick_performance AS (
  SELECT
    'P1|POND|2026-04-06' AS picker_day_key,
    'P1' AS picker_id,
    'POND' AS warehouse_code,
    '2026-04-06'::DATE AS work_date_local,
    NULL AS task_count,
    60 AS units_picked,
    1.0::DECIMAL(10, 2) AS active_hours,
    60.0::DECIMAL(10, 2) AS units_per_hour,
    NULL AS p90_task_seconds,
    NULL AS rank_in_warehouse,
    NULL AS first_task_hour_local,
    NULL AS shift_coverage,
    TRUE AS is_holiday
  UNION ALL
  SELECT
    'P2|POND|2026-04-06',
    'P2',
    'POND',
    '2026-04-06'::DATE,
    NULL,
    90,
    1.0::DECIMAL(10, 2),
    90.0::DECIMAL(10, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE
  UNION ALL
  SELECT
    'P3|NEST|2026-04-07',
    'P3',
    'NEST',
    '2026-04-07'::DATE,
    NULL,
    30,
    1.5::DECIMAL(10, 2),
    20.0::DECIMAL(10, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE
),

__ref__int_delivery_slot_utilisation AS (
  SELECT
    'POND|2026-04-06' AS slot_day_key,
    'POND' AS warehouse_code,
    '2026-04-06'::DATE AS slot_date_local,
    NULL AS slot_count,
    NULL AS total_capacity,
    NULL AS total_booked,
    0.75::DECIMAL(9, 4) AS utilisation,
    NULL AS full_slot_count,
    NULL AS busiest_slot_start_local,
    NULL AS is_weekend,
    NULL AS region_code,
    NULL AS is_holiday,
    NULL AS utilisation_vs_weekday_avg
),

__expected__rpt_warehouse_productivity_daily AS (
  SELECT
    'POND:2026-04-06' AS productivity_key,
    2 AS pickers,
    150 AS units_picked,
    75.0::DECIMAL(10, 2) AS units_per_picker_hour,
    'P2' AS top_picker_id,
    0.75::NUMBER(9, 4) AS slot_utilisation,
    TRUE AS is_holiday
  UNION ALL
  SELECT
    'NEST:2026-04-07' AS productivity_key,
    1 AS pickers,
    30 AS units_picked,
    20.0::DECIMAL(10, 2) AS units_per_picker_hour,
    'P3' AS top_picker_id,
    CAST(NULL AS NUMBER(9, 4)) AS slot_utilisation,
    FALSE AS is_holiday
),

__assert__productivity_key_is_unique_and_present AS (
  SELECT t.productivity_key
  FROM __ref("rpt_warehouse_productivity_daily") AS t
  GROUP BY
    t.productivity_key
  HAVING
    COUNT(*) > 1
    OR t.productivity_key IS NULL
)

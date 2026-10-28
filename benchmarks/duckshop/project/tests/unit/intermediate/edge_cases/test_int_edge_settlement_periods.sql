TEST (name "int_edge_settlement_periods__counts_calendar_boundaries_crossed");

WITH __ref__stg_edge_gateway_callbacks AS (
  SELECT
    v.callback_id,
    NULL AS merchant_zone,
    NULL AS local_wall_time,
    NULL AS event_at,
    NULL AS event_at_ns,
    NULL AS event_time_text,
    NULL AS business_date,
    v.period_start::TIMESTAMP_NTZ AS period_start,
    v.period_end::TIMESTAMP_NTZ AS period_end
  FROM VALUES
    ('CB-01', '2026-03-31 23:59:00', '2026-04-01 00:01:00'),
    ('CB-02', '2026-01-31 00:00:00', '2026-02-01 00:00:00'),
    ('CB-03', '2026-01-01 00:00:00', '2026-12-31 23:59:59'),
    ('CB-04', '2028-02-28 12:00:00', '2028-03-01 12:00:00'),
    ('CB-05', '2026-03-01 10:00:59', '2026-03-01 10:01:00'),
    ('CB-06', '2026-03-29 00:30:00', '2026-03-29 03:30:00'),
    ('CB-07', '2026-12-31 23:00:00', '2027-01-01 01:00:00') AS v(callback_id, period_start, period_end)
),

__expected__int_edge_settlement_periods AS (
  SELECT
    'CB-01' AS callback_id,
    1 AS days_crossed,
    1 AS months_crossed,
    1 AS hours_crossed,
    2 AS minutes_elapsed,
    -1 AS days_backwards,
    '2026-04-01'::DATE AS period_end_month
  UNION ALL
  SELECT
    'CB-02' AS callback_id,
    1 AS days_crossed,
    1 AS months_crossed,
    24 AS hours_crossed,
    1440 AS minutes_elapsed,
    -1 AS days_backwards,
    '2026-02-01'::DATE AS period_end_month
  UNION ALL
  SELECT
    'CB-03' AS callback_id,
    364 AS days_crossed,
    11 AS months_crossed,
    8759 AS hours_crossed,
    525599 AS minutes_elapsed,
    -364 AS days_backwards,
    '2026-12-01'::DATE AS period_end_month
  UNION ALL
  SELECT
    'CB-04' AS callback_id,
    2 AS days_crossed,
    1 AS months_crossed,
    48 AS hours_crossed,
    2880 AS minutes_elapsed,
    -2 AS days_backwards,
    '2028-03-01'::DATE AS period_end_month
  UNION ALL
  SELECT
    'CB-05' AS callback_id,
    0 AS days_crossed,
    0 AS months_crossed,
    0 AS hours_crossed,
    1 AS minutes_elapsed,
    0 AS days_backwards,
    '2026-03-01'::DATE AS period_end_month
  UNION ALL
  SELECT
    'CB-06' AS callback_id,
    0 AS days_crossed,
    0 AS months_crossed,
    3 AS hours_crossed,
    180 AS minutes_elapsed,
    0 AS days_backwards,
    '2026-03-01'::DATE AS period_end_month
  UNION ALL
  SELECT
    'CB-07' AS callback_id,
    1 AS days_crossed,
    1 AS months_crossed,
    2 AS hours_crossed,
    120 AS minutes_elapsed,
    -1 AS days_backwards,
    '2027-01-01'::DATE AS period_end_month
)

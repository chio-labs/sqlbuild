TEST (name "rpt_edge_daily_callbacks__counts_one_instant_sent_at_two_offsets_once");

WITH __ref__int_edge_callback_times AS (
  SELECT
    v.callback_id,
    NULL AS wall_time_utc,
    NULL AS wall_time_as_zoned,
    v.event_at_utc::TIMESTAMP_NTZ AS event_at_utc,
    NULL AS event_at_merchant,
    v.event_local_date::DATE AS event_local_date
  FROM VALUES
    ('CB-01', '2026-03-01 04:15:00', '2026-03-01'),
    ('CB-02', '2026-03-01 04:15:00', '2026-03-01'),
    ('CB-03', '2026-03-01 04:15:00', '2026-03-01'),
    ('CB-04', '2026-03-01 17:45:00', '2026-03-01'),
    ('CB-05', '2026-03-01 04:15:00', '2026-02-28') AS v(callback_id, event_at_utc, event_local_date)
),

__ref__stg_edge_gateway_callbacks AS (
  SELECT
    v.callback_id,
    NULL AS merchant_zone,
    NULL AS local_wall_time,
    v.event_at::TIMESTAMP_TZ AS event_at
  FROM VALUES
    ('CB-01', '2026-03-01 10:00:00 +05:45'),
    ('CB-02', '2026-03-01 04:15:00 +00:00'),
    ('CB-03', '2026-03-01 04:15:00 -00:00'),
    ('CB-04', '2026-03-01 23:30:00 +05:45'),
    ('CB-05', '2026-02-28 18:45:00 -09:30') AS v(callback_id, event_at)
),

__expected__rpt_edge_daily_callbacks AS (
  SELECT
    '2026-02-28'::DATE AS event_local_date,
    1 AS callbacks,
    1 AS distinct_instants,
    1 AS distinct_offsets,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS first_event_utc
  UNION ALL
  SELECT
    '2026-03-01'::DATE AS event_local_date,
    4 AS callbacks,
    2 AS distinct_instants,
    2 AS distinct_offsets,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS first_event_utc
)

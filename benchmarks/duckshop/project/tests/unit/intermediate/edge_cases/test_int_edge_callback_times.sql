TEST (name "int_edge_callback_times__converts_wall_times_across_daylight_saving_changes");

WITH __ref__stg_edge_gateway_callbacks AS (
  SELECT
    v.callback_id,
    v.merchant_zone,
    v.local_wall_time::TIMESTAMP_NTZ AS local_wall_time
  FROM VALUES
    ('CB-01', 'Europe/London', '2026-03-29 00:30:00'),
    ('CB-02', 'Europe/London', '2026-03-29 01:30:00'),
    ('CB-03', 'Europe/London', '2026-03-29 02:30:00'),
    ('CB-04', 'Europe/London', '2026-10-25 01:30:00'),
    ('CB-05', 'America/New_York', '2026-03-08 02:30:00'),
    ('CB-06', 'America/New_York', '2026-11-01 01:30:00'),
    ('CB-07', 'Australia/Sydney', '2026-04-05 02:30:00'),
    ('CB-08', 'Australia/Sydney', '2026-10-04 02:30:00'),
    ('CB-09', 'Asia/Kathmandu', '2026-03-01 10:00:00'),
    ('CB-10', 'Pacific/Marquesas', '2026-03-01 10:00:00') AS v(callback_id, merchant_zone, local_wall_time)
),

__expected__int_edge_callback_times AS (
  SELECT
    'CB-01' AS callback_id,
    '2026-03-29 00:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-03-29 00:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-02' AS callback_id,
    '2026-03-29 01:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-03-29 01:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-03' AS callback_id,
    '2026-03-29 01:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-03-29 02:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-04' AS callback_id,
    '2026-10-25 00:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-10-25 01:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-05' AS callback_id,
    '2026-03-08 07:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-03-08 02:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-06' AS callback_id,
    '2026-11-01 05:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-11-01 01:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-07' AS callback_id,
    '2026-04-04 15:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-04-05 02:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-08' AS callback_id,
    '2026-10-03 16:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-10-04 02:30:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-09' AS callback_id,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-03-01 10:00:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
  UNION ALL
  SELECT
    'CB-10' AS callback_id,
    '2026-03-01 19:30:00'::TIMESTAMP_NTZ(9) AS wall_time_utc,
    '2026-03-01 10:00:00 Z'::TIMESTAMP_TZ(9) AS wall_time_as_zoned
)

TEST (name "int_edge_callback_times__reads_zoned_times_at_fractional_and_zero_offsets");

WITH __ref__stg_edge_gateway_callbacks AS (
  SELECT
    v.callback_id,
    v.merchant_zone,
    NULL AS local_wall_time,
    v.event_at::TIMESTAMP_TZ AS event_at
  FROM VALUES
    ('CB-01', 'Asia/Kathmandu', '2026-03-01 10:00:00 +05:45'),
    ('CB-02', 'Europe/London', '2026-03-01 04:15:00 +00:00'),
    ('CB-03', 'Europe/London', '2026-03-01 04:15:00 -00:00'),
    ('CB-04', 'Pacific/Marquesas', '2026-02-28 18:45:00 -09:30'),
    ('CB-05', 'Asia/Kathmandu', '2026-03-01 23:30:00 +05:45'),
    ('CB-06', 'America/New_York', '2026-03-01 00:30:00 +14:00') AS v(callback_id, merchant_zone, event_at)
),

__expected__int_edge_callback_times AS (
  SELECT
    'CB-01' AS callback_id,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS event_at_utc,
    '2026-03-01 10:00:00 +05:45'::TIMESTAMP_TZ(9) AS event_at_merchant,
    '2026-03-01'::DATE AS event_local_date
  UNION ALL
  SELECT
    'CB-02' AS callback_id,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS event_at_utc,
    '2026-03-01 04:15:00 Z'::TIMESTAMP_TZ(9) AS event_at_merchant,
    '2026-03-01'::DATE AS event_local_date
  UNION ALL
  SELECT
    'CB-03' AS callback_id,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS event_at_utc,
    '2026-03-01 04:15:00 Z'::TIMESTAMP_TZ(9) AS event_at_merchant,
    '2026-03-01'::DATE AS event_local_date
  UNION ALL
  SELECT
    'CB-04' AS callback_id,
    '2026-03-01 04:15:00'::TIMESTAMP_NTZ(9) AS event_at_utc,
    '2026-02-28 18:45:00 -09:30'::TIMESTAMP_TZ(9) AS event_at_merchant,
    '2026-02-28'::DATE AS event_local_date
  UNION ALL
  SELECT
    'CB-05' AS callback_id,
    '2026-03-01 17:45:00'::TIMESTAMP_NTZ(9) AS event_at_utc,
    '2026-03-01 23:30:00 +05:45'::TIMESTAMP_TZ(9) AS event_at_merchant,
    '2026-03-01'::DATE AS event_local_date
  UNION ALL
  SELECT
    'CB-06' AS callback_id,
    '2026-02-28 10:30:00'::TIMESTAMP_NTZ(9) AS event_at_utc,
    '2026-02-28 05:30:00 -05:00'::TIMESTAMP_TZ(9) AS event_at_merchant,
    '2026-03-01'::DATE AS event_local_date
)

TEST (name "int_edge_callback_times__lowers_nanosecond_times_by_truncating");

WITH __ref__stg_edge_gateway_callbacks AS (
  SELECT
    v.callback_id,
    NULL AS merchant_zone,
    NULL AS local_wall_time,
    NULL AS event_at,
    v.event_at_ns::TIMESTAMP_NTZ(9) AS event_at_ns
  FROM VALUES
    ('CB-01', '2026-03-01 23:59:59.9999995'),
    ('CB-02', '2026-03-01 10:00:00.0005'),
    ('CB-03', '2026-03-01 10:00:00.0015'),
    ('CB-04', '2026-03-01 10:00:00.000000001'),
    ('CB-05', '1962-07-01 12:00:00.123456789'),
    ('CB-06', '1969-12-31 23:59:59.9999999'),
    ('CB-07', '2250-06-01 00:00:00.123456'),
    ('CB-08', '2300-01-01 00:00:00.5'),
    ('CB-09', '0001-01-01 00:00:00'),
    ('CB-10', '9999-12-31 23:59:59.999999') AS v(callback_id, event_at_ns)
),

__expected__int_edge_callback_times AS (
  SELECT
    'CB-01' AS callback_id,
    '2026-03-01'::DATE AS event_ns_date,
    '2026-03-01 23:59:59.999'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '2026-03-01 23:59:59.999999'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '2026-03-01 23:59:59.999' AS event_ns_text,
    1772409599 AS epoch_second,
    1772409599999 AS epoch_millisecond,
    1772409599999999 AS epoch_microsecond,
    1772409599999999500 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-02' AS callback_id,
    '2026-03-01'::DATE AS event_ns_date,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '2026-03-01 10:00:00.0005'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '2026-03-01 10:00:00.000' AS event_ns_text,
    1772359200 AS epoch_second,
    1772359200000 AS epoch_millisecond,
    1772359200000500 AS epoch_microsecond,
    1772359200000500000 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-03' AS callback_id,
    '2026-03-01'::DATE AS event_ns_date,
    '2026-03-01 10:00:00.001'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '2026-03-01 10:00:00.0015'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '2026-03-01 10:00:00.001' AS event_ns_text,
    1772359200 AS epoch_second,
    1772359200001 AS epoch_millisecond,
    1772359200001500 AS epoch_microsecond,
    1772359200001500000 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-04' AS callback_id,
    '2026-03-01'::DATE AS event_ns_date,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '2026-03-01 10:00:00.000' AS event_ns_text,
    1772359200 AS epoch_second,
    1772359200000 AS epoch_millisecond,
    1772359200000000 AS epoch_microsecond,
    1772359200000000001 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-05' AS callback_id,
    '1962-07-01'::DATE AS event_ns_date,
    '1962-07-01 12:00:00.123'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '1962-07-01 12:00:00.123456'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '1962-07-01 12:00:00.123' AS event_ns_text,
    -236779200 AS epoch_second,
    -236779199877 AS epoch_millisecond,
    -236779199876544 AS epoch_microsecond,
    -236779199876543211 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-06' AS callback_id,
    '1969-12-31'::DATE AS event_ns_date,
    '1969-12-31 23:59:59.999'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '1969-12-31 23:59:59.999999'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '1969-12-31 23:59:59.999' AS event_ns_text,
    -1 AS epoch_second,
    -1 AS epoch_millisecond,
    -1 AS epoch_microsecond,
    -100 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-07' AS callback_id,
    '2250-06-01'::DATE AS event_ns_date,
    '2250-06-01 00:00:00.123'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '2250-06-01 00:00:00.123456'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '2250-06-01 00:00:00.123' AS event_ns_text,
    8849001600 AS epoch_second,
    8849001600123 AS epoch_millisecond,
    8849001600123456 AS epoch_microsecond,
    8849001600123456000 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-08' AS callback_id,
    '2300-01-01'::DATE AS event_ns_date,
    '2300-01-01 00:00:00.5'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '2300-01-01 00:00:00.5'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '2300-01-01 00:00:00.500' AS event_ns_text,
    10413792000 AS epoch_second,
    10413792000500 AS epoch_millisecond,
    10413792000500000 AS epoch_microsecond,
    10413792000500000000 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-09' AS callback_id,
    '0001-01-01'::DATE AS event_ns_date,
    '0001-01-01 00:00:00'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '0001-01-01 00:00:00'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '0001-01-01 00:00:00.000' AS event_ns_text,
    -62135596800 AS epoch_second,
    -62135596800000 AS epoch_millisecond,
    -62135596800000000 AS epoch_microsecond,
    -62135596800000000000 AS epoch_nanosecond
  UNION ALL
  SELECT
    'CB-10' AS callback_id,
    '9999-12-31'::DATE AS event_ns_date,
    '9999-12-31 23:59:59.999'::TIMESTAMP_NTZ(3) AS event_ns_ms,
    '9999-12-31 23:59:59.999999'::TIMESTAMP_NTZ(6) AS event_ns_us,
    '9999-12-31 23:59:59.999' AS event_ns_text,
    253402300799 AS epoch_second,
    253402300799999 AS epoch_millisecond,
    253402300799999999 AS epoch_microsecond,
    253402300799999999000 AS epoch_nanosecond
)

TEST (name "stg_edge_gateway_callbacks__reads_free_text_times_in_every_lenient_spelling");

WITH __source__edge__gateway_callbacks AS (
  SELECT
    v.callback_id,
    NULL AS merchant_zone,
    NULL AS local_wall_time,
    NULL AS event_at,
    NULL AS event_at_ns,
    v.event_time_text,
    NULL AS business_date,
    NULL AS period_start,
    NULL AS period_end,
    NULL AS body,
    '2026-03-02 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('CB-01', '2026-03-01 10:15:00'),
    ('CB-02', '2026-03-01T10:15:00'),
    ('CB-03', '2026-03-01T10:15:00Z'),
    ('CB-04', '2026-03-01 10:15:00 +05:45'),
    ('CB-05', '2026-03-01T10:15:00-09:30'),
    ('CB-06', '01-MAR-26 10:15'),
    ('CB-07', '2026-03-01 24:00:00'),
    ('CB-08', '2026-3-1 7:5:0'),
    ('CB-09', '  2026-03-01 10:15:00  '),
    ('CB-10', '1772359200'),
    ('CB-11', '1772359200000'),
    ('CB-12', 'now'),
    ('CB-13', '\u0662\u0660\u0662\u0666-\u0660\u0663-\u0660\u0661'),
    ('CB-14', ''),
    ('CB-15', 'n/a'),
    ('CB-16', '1962-07-01 12:00:00.1234567'),
    ('CB-17', '10:15'),
    ('CB-18', '2026-03-01'),
    ('CB-19', '31/12/2026'),
    ('CB-20', '2026-02-30') AS v(callback_id, event_time_text)
),

__expected__stg_edge_gateway_callbacks AS (
  SELECT
    'CB-01' AS callback_id,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:15:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-02' AS callback_id,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:15:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-03' AS callback_id,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:15:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-04' AS callback_id,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:15:00 +05:45'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-05' AS callback_id,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:15:00 -09:30'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-06' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-07' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-08' AS callback_id,
    '2026-03-01 07:05:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 07:05:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-09' AS callback_id,
    '2026-03-01 10:15:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:15:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-10' AS callback_id,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:00:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    '10:00:00'::TIME(9) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-11' AS callback_id,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 10:00:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    '10:00:00'::TIME(9) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-12' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-13' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-14' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-15' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-16' AS callback_id,
    '1962-07-01 12:00:00.1234567'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '1962-07-01 12:00:00.1234567 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '1962-07-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '1962-07-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-17' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    '10:15:00'::TIME(9) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-18' AS callback_id,
    '2026-03-01 00:00:00'::TIMESTAMP_NTZ(9) AS text_timestamp,
    '2026-03-01 00:00:00 Z'::TIMESTAMP_TZ(9) AS text_timestamp_tz,
    '2026-03-01'::DATE AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    '2026-03-01'::DATE AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-19' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
  UNION ALL
  SELECT
    'CB-20' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp,
    CAST(NULL AS TIMESTAMP_TZ(9)) AS text_timestamp_tz,
    CAST(NULL AS DATE) AS text_date,
    CAST(NULL AS TIME(9)) AS text_time,
    CAST(NULL AS DATE) AS text_date_cast,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS text_timestamp_day_month
)

TEST (name "stg_edge_gateway_callbacks__reads_epoch_milliseconds_sent_as_numbers_and_text");

WITH __source__edge__gateway_callbacks AS (
  SELECT
    v.callback_id,
    NULL AS merchant_zone,
    NULL AS local_wall_time,
    NULL AS event_at,
    NULL AS event_at_ns,
    NULL AS event_time_text,
    NULL AS business_date,
    NULL AS period_start,
    NULL AS period_end,
    PARSE_JSON(v.body) AS body,
    '2026-03-02 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('CB-01', '{"ts_ms": 1772359200000}'),
    ('CB-02', '{"ts_ms": "1772359200000"}'),
    ('CB-03', '{"ts_ms": 1772359200}'),
    ('CB-04', '{"ts_ms": "1772359200"}'),
    ('CB-05', '{"ts_ms": 1772359200123}'),
    ('CB-06', '{"ts_ms": 1772359200123.0}'),
    ('CB-07', '{"ts_ms": null}'),
    ('CB-08', '{}') AS v(callback_id, body)
),

__expected__stg_edge_gateway_callbacks AS (
  SELECT
    'CB-01' AS callback_id,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(3) AS sent_at_from_ms,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_from_text,
    '58133-10-29 16:00:00'::TIMESTAMP_NTZ(9) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-02' AS callback_id,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(3) AS sent_at_from_ms,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_from_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-03' AS callback_id,
    '1970-01-21 12:19:19.2'::TIMESTAMP_NTZ(3) AS sent_at_from_ms,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_from_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-04' AS callback_id,
    '1970-01-21 12:19:19.2'::TIMESTAMP_NTZ(3) AS sent_at_from_ms,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_from_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-05' AS callback_id,
    '2026-03-01 10:00:00.123'::TIMESTAMP_NTZ(3) AS sent_at_from_ms,
    '2026-03-01 10:00:00.123'::TIMESTAMP_NTZ(9) AS sent_at_from_text,
    '58133-10-29 16:02:03'::TIMESTAMP_NTZ(9) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-06' AS callback_id,
    '2026-03-01 10:00:00.123'::TIMESTAMP_NTZ(3) AS sent_at_from_ms,
    '2026-03-01 10:00:00.123'::TIMESTAMP_NTZ(9) AS sent_at_from_text,
    '58133-10-29 16:02:03'::TIMESTAMP_NTZ(9) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-07' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(3)) AS sent_at_from_ms,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS sent_at_from_text,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS sent_at_cast
  UNION ALL
  SELECT
    'CB-08' AS callback_id,
    CAST(NULL AS TIMESTAMP_NTZ(3)) AS sent_at_from_ms,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS sent_at_from_text,
    CAST(NULL AS TIMESTAMP_NTZ(9)) AS sent_at_cast
)

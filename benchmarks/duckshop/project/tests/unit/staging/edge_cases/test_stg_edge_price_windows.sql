TEST (name "stg_edge_price_windows__closes_open_windows_with_sentinel_timestamps");

WITH __source__edge__price_windows AS (
  SELECT
    v.window_id,
    v.sku,
    v.price_minor,
    v.valid_from::TIMESTAMP_NTZ(6) AS valid_from,
    v.valid_to::TIMESTAMP_NTZ(6) AS valid_to,
    '2026-03-02 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PW-1', 'MALLARD-01', 1299, NULL, NULL),
    ('PW-2', 'TEAL-02', 899, '0001-01-01 00:00:00', '9999-12-31 23:59:59.999999'),
    ('PW-3', 'EIDER-03', 2450, '2026-01-01 00:00:00', NULL),
    ('PW-4', 'PINTAIL-04', 1575, '1969-12-31 23:59:59.999999', '1970-01-01 00:00:00.000001'),
    ('PW-5', 'MERGANSER-05', 650, '2026-03-29 01:30:00', '9999-06-30 00:00:00') AS v(window_id, sku, price_minor, valid_from, valid_to)
),

__expected__stg_edge_price_windows AS (
  SELECT
    'PW-1' AS window_id,
    '0001-01-01 00:00:00'::TIMESTAMP_NTZ(6) AS valid_from,
    '9999-12-31 23:59:59.999999'::TIMESTAMP_NTZ(6) AS valid_to,
    TRUE AS is_open_ended,
    3652058 AS window_days
  UNION ALL
  SELECT
    'PW-2' AS window_id,
    '0001-01-01 00:00:00'::TIMESTAMP_NTZ(6) AS valid_from,
    '9999-12-31 23:59:59.999999'::TIMESTAMP_NTZ(6) AS valid_to,
    TRUE AS is_open_ended,
    3652058 AS window_days
  UNION ALL
  SELECT
    'PW-3' AS window_id,
    '2026-01-01 00:00:00'::TIMESTAMP_NTZ(6) AS valid_from,
    '9999-12-31 23:59:59.999999'::TIMESTAMP_NTZ(6) AS valid_to,
    TRUE AS is_open_ended,
    2912442 AS window_days
  UNION ALL
  SELECT
    'PW-4' AS window_id,
    '1969-12-31 23:59:59.999999'::TIMESTAMP_NTZ(6) AS valid_from,
    '1970-01-01 00:00:00.000001'::TIMESTAMP_NTZ(6) AS valid_to,
    FALSE AS is_open_ended,
    1 AS window_days
  UNION ALL
  SELECT
    'PW-5' AS window_id,
    '2026-03-29 01:30:00'::TIMESTAMP_NTZ(6) AS valid_from,
    '9999-06-30 00:00:00'::TIMESTAMP_NTZ(6) AS valid_to,
    TRUE AS is_open_ended,
    2912171 AS window_days
)

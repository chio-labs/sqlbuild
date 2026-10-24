TEST (name "snap_price_list_history__keeps_the_last_change_per_load_and_normalises_codes");

WITH __source__catalogue__price_lists AS (
  SELECT
    'PL1' AS price_list_id,
    ' duck-mal-01 ' AS sku,
    'eur' AS currency_code,
    1299 AS list_amount_minor,
    NULL AS valid_from,
    NULL AS valid_to,
    NULL AS conditions,
    'I' AS _op,
    1 AS _seq,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'PL1',
    ' duck-mal-01 ',
    'eur',
    1199,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'PL1',
    'duck-mal-01',
    'eur',
    1099,
    NULL,
    NULL,
    NULL,
    'U',
    3,
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'PL2',
    'pond-pump',
    'eur',
    4999,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ
),

__expected__snap_price_list_history AS (
  SELECT
    'PL1' AS price_list_id,
    'DUCK-MAL-01' AS sku,
    'EUR' AS currency_code,
    1199 AS list_amount_minor,
    'U' AS change_op,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS changed_at
  UNION ALL
  SELECT
    'PL1' AS price_list_id,
    'DUCK-MAL-01' AS sku,
    'EUR' AS currency_code,
    1099 AS list_amount_minor,
    'U' AS change_op,
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ AS changed_at
  UNION ALL
  SELECT
    'PL2' AS price_list_id,
    'POND-PUMP' AS sku,
    'EUR' AS currency_code,
    4999 AS list_amount_minor,
    'D' AS change_op,
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ AS changed_at
),

__assert__version_key_is_unique_and_present AS (
  SELECT t.price_list_id
  FROM __ref("snap_price_list_history") AS t
  GROUP BY
    t.price_list_id,
    t.changed_at
  HAVING
    COUNT(*) > 1
    OR t.price_list_id IS NULL
)

TEST (name "stg_price_lists__keeps_latest_live_version");

WITH __source__catalogue__price_lists AS (
  SELECT
    'K1' AS price_list_id,
    NULL AS sku,
    NULL AS currency_code,
    NULL AS list_amount_minor,
    NULL AS valid_from,
    CAST(NULL AS TIMESTAMP_TZ) AS valid_to,
    NULL AS conditions,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_price_lists AS (
  SELECT
    'K1' AS price_list_id,
    2 AS source_seq
)

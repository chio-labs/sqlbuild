TEST (name "stg_tax_rates__keeps_latest_live_version");

WITH __source__finance__tax_rates AS (
  SELECT
    'K1' AS tax_rate_id,
    NULL AS country_code,
    NULL AS tax_region,
    NULL AS tax_category,
    NULL AS rate_pct,
    NULL AS valid_from,
    NULL AS valid_to,
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

__expected__stg_tax_rates AS (
  SELECT
    'K1' AS tax_rate_id,
    2 AS source_seq
)

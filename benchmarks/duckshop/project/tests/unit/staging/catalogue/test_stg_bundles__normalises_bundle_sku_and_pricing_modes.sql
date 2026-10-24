TEST (name "stg_bundles__normalises_bundle_sku_and_pricing_modes");

WITH __source__catalogue__bundles AS (
  SELECT
    'bnd_01 ' AS bundle_sku,
    'Paddling Six' AS title,
    NULL AS active_from,
    NULL AS active_to,
    PARSE_JSON('{"mode": "PERCENT", "percent_off": 12.5, "currency": "eur"}')::VARIANT AS pricing,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'b2',
    'Teal Twin Pack',
    NULL,
    NULL,
    PARSE_JSON('{"amount_minor": 4999}')::VARIANT,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'b2',
    'Teal Twin Pack',
    NULL,
    NULL,
    PARSE_JSON('{"amount_minor": 3999}')::VARIANT,
    'U',
    1,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_bundles AS (
  SELECT
    'BND-01' AS bundle_sku,
    'percent' AS pricing_mode,
    CAST(NULL AS INT) AS fixed_amount_minor,
    12.5::DECIMAL(5, 2) AS percent_off,
    'EUR' AS pricing_currency_code,
    1 AS source_seq
  UNION ALL
  SELECT
    'B2' AS bundle_sku,
    'fixed' AS pricing_mode,
    4999 AS fixed_amount_minor,
    CAST(NULL AS DECIMAL(5, 2)) AS percent_off,
    CAST(NULL AS VARCHAR) AS pricing_currency_code,
    2 AS source_seq
)

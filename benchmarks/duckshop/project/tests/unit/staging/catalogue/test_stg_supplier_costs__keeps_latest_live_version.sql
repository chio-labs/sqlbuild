TEST (name "stg_supplier_costs__keeps_latest_live_version");

WITH __source__catalogue__supplier_costs AS (
  SELECT
    'K1' AS cost_id,
    NULL AS supplier_code,
    NULL AS sku,
    NULL AS currency_code,
    NULL AS unit_cost_minor,
    NULL AS effective_from,
    NULL AS volume_breaks,
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

__expected__stg_supplier_costs AS (
  SELECT
    'K1' AS cost_id,
    2 AS source_seq
)

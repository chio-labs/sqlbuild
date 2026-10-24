TEST (name "stg_partner_settlements__keeps_latest_live_version");

WITH __source__partners__partner_settlements AS (
  SELECT
    'K1' AS settlement_id,
    NULL AS partner_code,
    NULL AS period_start,
    NULL AS period_end,
    NULL AS currency_code,
    NULL AS statement,
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
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_partner_settlements AS (
  SELECT
    'K1' AS settlement_id,
    2 AS source_seq
)

TEST (name "stg_payouts__keeps_latest_live_version");

WITH __source__finance__payouts AS (
  SELECT
    'K1' AS payout_id,
    NULL AS provider_code,
    NULL AS currency_code,
    NULL AS amount_minor,
    NULL AS fee_minor,
    NULL AS paid_out_on,
    NULL AS lines,
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

__expected__stg_payouts AS (
  SELECT
    'K1' AS payout_id,
    2 AS source_seq
)

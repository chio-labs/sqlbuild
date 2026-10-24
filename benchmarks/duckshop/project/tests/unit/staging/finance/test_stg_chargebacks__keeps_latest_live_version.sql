TEST (name "stg_chargebacks__keeps_latest_live_version");

WITH __source__finance__chargebacks AS (
  SELECT
    'K1' AS chargeback_id,
    NULL AS payment_id,
    NULL AS amount_minor,
    NULL AS currency_code,
    NULL AS reason_code,
    NULL AS opened_at,
    NULL AS closed_at,
    NULL AS outcome,
    NULL AS evidence,
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
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_chargebacks AS (
  SELECT
    'K1' AS chargeback_id,
    2 AS source_seq
)

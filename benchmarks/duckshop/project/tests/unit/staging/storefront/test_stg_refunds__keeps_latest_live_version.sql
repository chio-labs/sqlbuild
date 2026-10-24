TEST (name "stg_refunds__keeps_latest_live_version");

WITH __source__storefront__refunds AS (
  SELECT
    'K1' AS refund_id,
    NULL AS payment_id,
    NULL AS amount_minor,
    NULL AS reason_text,
    NULL AS refunded_at,
    NULL AS initiated_by,
    NULL AS items,
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

__expected__stg_refunds AS (
  SELECT
    'K1' AS refund_id,
    2 AS source_seq
)

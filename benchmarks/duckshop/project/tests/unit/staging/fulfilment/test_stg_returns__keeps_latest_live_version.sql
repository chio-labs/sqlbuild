TEST (name "stg_returns__keeps_latest_live_version");

WITH __source__fulfilment__returns AS (
  SELECT
    'K1' AS return_id,
    NULL AS order_id,
    NULL AS sku,
    NULL AS qty,
    NULL AS reason_text,
    NULL AS return_status,
    NULL AS requested_at,
    NULL AS received_at,
    NULL AS photos,
    NULL AS refund_preference,
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
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_returns AS (
  SELECT
    'K1' AS return_id,
    2 AS source_seq
)

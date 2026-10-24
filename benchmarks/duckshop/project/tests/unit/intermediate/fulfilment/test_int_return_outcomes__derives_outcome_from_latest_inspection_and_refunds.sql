TEST (name "int_return_outcomes__derives_outcome_from_latest_inspection_and_refunds");

WITH __ref__int_return_reasons AS (
  SELECT
    'RT1' AS return_id,
    'O1' AS order_id,
    'DUCK-1' AS sku,
    NULL AS qty,
    NULL AS reason_text,
    'damaged' AS return_reason,
    NULL AS classified_by,
    NULL AS requested_at,
    NULL AS category_level_1,
    NULL AS ordered_qty,
    NULL AS is_over_return,
    NULL AS days_after_order
  UNION ALL
  SELECT
    'RT2',
    'O2',
    'DUCK-1',
    NULL,
    NULL,
    'size_fit',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RT3',
    'O3',
    'DUCK-1',
    NULL,
    NULL,
    'other',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RT4',
    'O4',
    'DUCK-1',
    NULL,
    NULL,
    'other',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_returns AS (
  SELECT
    'RT1' AS return_id,
    NULL AS order_id,
    NULL AS sku,
    NULL AS qty,
    NULL AS reason_text,
    NULL AS return_status,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS requested_at,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS received_at,
    NULL AS photo_count,
    NULL AS refund_preference,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'RT2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-03 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RT3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RT4',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_return_inspections AS (
  SELECT
    'I1' AS inspection_id,
    'RT1' AS return_id,
    NULL AS warehouse_code,
    'B' AS grade,
    FALSE AS is_resellable,
    '2026-03-05 12:00:00'::TIMESTAMP_NTZ AS inspected_at_local,
    PARSE_JSON('["SCUFF"]')::ARRAY AS defect_codes,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'I2',
    'RT1',
    NULL,
    'A',
    TRUE,
    '2026-03-06 12:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('[]')::ARRAY,
    NULL,
    NULL
  UNION ALL
  SELECT
    'I3',
    'RT2',
    NULL,
    'C',
    FALSE,
    '2026-03-04 12:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('["SCRATCH", "DENT"]')::ARRAY,
    NULL,
    NULL
),

__ref__int_refunds_usd AS (
  SELECT
    'F1' AS refund_id,
    NULL AS payment_id,
    'O3' AS order_id,
    NULL AS currency_code,
    '2026-03-03 09:00:00 +00:00'::TIMESTAMP_TZ AS refunded_at,
    NULL AS refunded_date,
    'return' AS reason_category,
    NULL AS amount,
    10.0::DECIMAL(18, 2) AS amount_usd,
    NULL AS days_after_payment,
    NULL AS is_full_refund
  UNION ALL
  SELECT
    'F2',
    NULL,
    'O3',
    NULL,
    '2026-03-04 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'return',
    NULL,
    5.5::DECIMAL(18, 2),
    NULL,
    NULL
  UNION ALL
  SELECT
    'F3',
    NULL,
    'O3',
    NULL,
    '2026-03-02 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'fraud',
    NULL,
    100.0::DECIMAL(18, 2),
    NULL,
    NULL
),

__expected__int_return_outcomes AS (
  SELECT
    'RT1' AS return_id,
    'A' AS grade,
    TRUE AS is_resellable,
    CAST(NULL AS DECIMAL(18, 2)) AS refund_usd,
    4 AS days_to_receive,
    CAST(NULL AS INT) AS days_to_refund,
    'restocked' AS outcome,
    0 AS defect_count
  UNION ALL
  SELECT
    'RT2' AS return_id,
    'C' AS grade,
    FALSE AS is_resellable,
    CAST(NULL AS DECIMAL(18, 2)) AS refund_usd,
    2 AS days_to_receive,
    CAST(NULL AS INT) AS days_to_refund,
    'written_off' AS outcome,
    2 AS defect_count
  UNION ALL
  SELECT
    'RT3' AS return_id,
    CAST(NULL AS VARCHAR) AS grade,
    CAST(NULL AS BOOLEAN) AS is_resellable,
    15.5::DECIMAL(18, 2) AS refund_usd,
    CAST(NULL AS INT) AS days_to_receive,
    2 AS days_to_refund,
    'refunded_not_received' AS outcome,
    0 AS defect_count
  UNION ALL
  SELECT
    'RT4' AS return_id,
    CAST(NULL AS VARCHAR) AS grade,
    CAST(NULL AS BOOLEAN) AS is_resellable,
    CAST(NULL AS DECIMAL(18, 2)) AS refund_usd,
    CAST(NULL AS INT) AS days_to_receive,
    CAST(NULL AS INT) AS days_to_refund,
    'pending' AS outcome,
    0 AS defect_count
)

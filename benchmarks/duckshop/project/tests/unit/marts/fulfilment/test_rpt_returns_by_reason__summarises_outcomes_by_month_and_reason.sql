TEST (name "rpt_returns_by_reason__summarises_outcomes_by_month_and_reason");

WITH __ref__int_return_reasons AS (
  SELECT
    'R1' AS return_id,
    NULL AS order_id,
    NULL AS sku,
    1 AS qty,
    NULL AS reason_text,
    'damaged' AS return_reason,
    NULL AS classified_by,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS requested_at,
    NULL AS category_level_1,
    NULL AS ordered_qty,
    NULL AS is_over_return,
    NULL AS days_after_order
  UNION ALL
  SELECT
    'R2',
    NULL,
    NULL,
    2,
    NULL,
    'damaged',
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R3',
    NULL,
    NULL,
    1,
    NULL,
    'size_fit',
    NULL,
    '2026-03-12 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R4',
    NULL,
    NULL,
    1,
    NULL,
    'damaged',
    NULL,
    '2026-03-31 23:30:00 -02:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_return_outcomes AS (
  SELECT
    'R1' AS return_id,
    NULL AS order_id,
    NULL AS sku,
    NULL AS return_reason,
    NULL AS grade,
    TRUE AS is_resellable,
    10.0::DECIMAL(18, 2) AS refund_usd,
    NULL AS days_to_receive,
    2 AS days_to_refund,
    NULL AS outcome,
    NULL AS defect_count
  UNION ALL
  SELECT
    'R2',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    20.0::DECIMAL(18, 2),
    NULL,
    4,
    NULL,
    NULL
),

__expected__rpt_returns_by_reason AS (
  SELECT
    '2026-03:damaged' AS return_reason_key,
    2 AS returns,
    3 AS units,
    0.5::DECIMAL(9, 4) AS resellable_share,
    30.0::DECIMAL(18, 2) AS refund_usd,
    3.0::DECIMAL(10, 2) AS median_days_to_refund,
    0.6667::DECIMAL(9, 4) AS share_of_month
  UNION ALL
  SELECT
    '2026-03:size_fit' AS return_reason_key,
    1 AS returns,
    1 AS units,
    0.0::DECIMAL(9, 4) AS resellable_share,
    CAST(NULL AS DECIMAL(18, 2)) AS refund_usd,
    CAST(NULL AS DECIMAL(10, 2)) AS median_days_to_refund,
    0.3333::DECIMAL(9, 4) AS share_of_month
  UNION ALL
  SELECT
    '2026-04:damaged' AS return_reason_key,
    1 AS returns,
    1 AS units,
    0.0::DECIMAL(9, 4) AS resellable_share,
    CAST(NULL AS DECIMAL(18, 2)) AS refund_usd,
    CAST(NULL AS DECIMAL(10, 2)) AS median_days_to_refund,
    1.0::DECIMAL(9, 4) AS share_of_month
),

__assert__return_reason_key_is_unique_and_present AS (
  SELECT t.return_reason_key
  FROM __ref("rpt_returns_by_reason") AS t
  GROUP BY
    t.return_reason_key
  HAVING
    COUNT(*) > 1
    OR t.return_reason_key IS NULL
)

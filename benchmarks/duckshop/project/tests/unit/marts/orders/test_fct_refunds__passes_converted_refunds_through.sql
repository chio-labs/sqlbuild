TEST (name "fct_refunds__passes_converted_refunds_through");

WITH __ref__int_refunds_usd AS (
  SELECT
    'F1' AS refund_id,
    'P1' AS payment_id,
    'O1' AS order_id,
    'EUR' AS currency_code,
    NULL AS refunded_at,
    NULL AS refunded_date,
    'return' AS reason_category,
    12.5::DECIMAL(38, 6) AS amount,
    13.75::DECIMAL(18, 2) AS amount_usd,
    NULL AS days_after_payment,
    TRUE AS is_full_refund
  UNION ALL
  SELECT
    'F2',
    'P2',
    'O2',
    'KWD',
    NULL,
    NULL,
    'goodwill',
    0.75::DECIMAL(38, 6),
    2.44::DECIMAL(18, 2),
    NULL,
    FALSE
),

__expected__fct_refunds AS (
  SELECT
    'F1' AS refund_id,
    12.5::NUMBER(38, 6) AS amount,
    13.75::NUMBER(18, 2) AS amount_usd,
    'return' AS reason_category,
    TRUE AS is_full_refund
  UNION ALL
  SELECT
    'F2' AS refund_id,
    0.75::NUMBER(38, 6) AS amount,
    2.44::NUMBER(18, 2) AS amount_usd,
    'goodwill' AS reason_category,
    FALSE AS is_full_refund
),

__assert__refund_id_is_unique_and_present AS (
  SELECT t.refund_id
  FROM __ref("fct_refunds") AS t
  GROUP BY
    t.refund_id
  HAVING
    COUNT(*) > 1
    OR t.refund_id IS NULL
)

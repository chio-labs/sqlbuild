TEST (name "int_refunds_usd__converts_at_rate_on_refund_date");

WITH __ref__stg_refunds AS (
  SELECT
    'RF1' AS refund_id,
    'P1' AS payment_id,
    2500 AS amount_minor,
    NULL AS reason_text,
    'damaged' AS reason_category,
    '2026-03-20 23:30:00 -05:00'::TIMESTAMP_TZ AS refunded_at,
    NULL AS initiated_by,
    NULL AS refunded_line_count,
    NULL AS refunded_items,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'RF2',
    'P2',
    500,
    NULL,
    NULL,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_payments AS (
  SELECT
    'P1' AS payment_id,
    'O1' AS order_id,
    NULL AS payment_method,
    2500 AS amount_minor,
    'EUR' AS currency_code,
    NULL AS authorised_at,
    '2026-03-10 23:00:00 -05:00'::TIMESTAMP_TZ AS captured_at,
    NULL AS card_bin,
    NULL AS gateway_status,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS three_ds_outcome,
    NULL AS gateway_reference,
    NULL AS gateway_response,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'O2',
    NULL,
    1000,
    'GBP',
    NULL,
    '2026-03-01 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-20'::DATE AS rate_date,
    1.05::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'EUR',
    '2026-03-21'::DATE,
    1.1::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'GBP',
    '2026-03-01'::DATE,
    1.25::NUMBER(18, 8),
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'GBP',
    NULL,
    2,
    NULL
),

__expected__int_refunds_usd AS (
  SELECT
    'RF1' AS refund_id,
    'O1' AS order_id,
    '2026-03-21'::DATE AS refunded_date,
    25.0::DECIMAL(38, 6) AS amount,
    27.5::DECIMAL(18, 2) AS amount_usd,
    10 AS days_after_payment,
    TRUE AS is_full_refund
  UNION ALL
  SELECT
    'RF2' AS refund_id,
    'O2' AS order_id,
    '2026-03-05'::DATE AS refunded_date,
    5.0::DECIMAL(38, 6) AS amount,
    6.25::DECIMAL(18, 2) AS amount_usd,
    4 AS days_after_payment,
    FALSE AS is_full_refund
)

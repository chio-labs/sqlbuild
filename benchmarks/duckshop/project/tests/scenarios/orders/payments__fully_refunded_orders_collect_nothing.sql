SCENARIO (
  description """
    Captures, refunds, lost chargebacks and gift card tender net into the collected amount of each
    order
  """,
  tags ["orders", "payments"],
);

WITH __ref__int_orders_usd AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    'EU' AS region_code,
    'EUR' AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    'DELIVERED' AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS amount,
    NULL AS amount_usd,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS rate_age_days,
    NULL AS is_rate_stale,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size
  UNION ALL
  SELECT
    'O2',
    'C2',
    'EU',
    'EUR',
    NULL,
    NULL,
    'SHIPPED',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O3',
    'C3',
    'US',
    'USD',
    NULL,
    NULL,
    'PENDING',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
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

__ref__int_order_status_timeline AS (
  SELECT
    'O1' AS order_id,
    NULL AS transition_count,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS first_paid_at,
    NULL AS first_shipped_at,
    NULL AS first_delivered_at,
    NULL AS cancelled_at,
    NULL AS minutes_to_pay,
    NULL AS hours_paid_to_shipped,
    NULL AS status_path,
    NULL AS has_regression,
    NULL AS last_status,
    NULL AS longest_status
),

__ref__int_customer_order_sequence AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    NULL AS placed_at,
    NULL AS placed_date_local,
    1 AS order_number,
    TRUE AS is_first_order,
    NULL AS days_since_previous_order,
    NULL AS amount_usd,
    NULL AS lifetime_revenue_usd,
    NULL AS rolling_90d_revenue_usd,
    NULL AS previous_sales_channel,
    NULL AS is_channel_switch,
    NULL AS cohort_month
),

__ref__int_payment_attempts AS (
  SELECT
    'P0' AS payment_id,
    'O1' AS order_id,
    1 AS attempt_number,
    NULL AS attempt_count,
    FALSE AS is_final_attempt,
    'card' AS payment_method,
    2000 AS amount_minor,
    'EUR' AS currency_code,
    NULL AS authorised_at,
    NULL AS seconds_since_previous_attempt,
    NULL AS gateway_status,
    FALSE AS is_successful,
    NULL AS decline_family,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS risk_band,
    NULL AS three_ds_outcome,
    NULL AS card_bin_valid,
    NULL AS card_scheme,
    NULL AS had_chargeback
  UNION ALL
  SELECT
    'P1',
    'O1',
    2,
    NULL,
    TRUE,
    'card',
    2000,
    'EUR',
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P2',
    'O2',
    1,
    NULL,
    TRUE,
    'phone_wallet',
    1500,
    'EUR',
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_refunds AS (
  SELECT
    'R1' AS refund_id,
    'P1' AS payment_id,
    2000 AS amount_minor,
    NULL AS reason_text,
    'return' AS reason_category,
    NULL AS refunded_at,
    NULL AS initiated_by,
    NULL AS refunded_line_count,
    NULL AS refunded_items,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_chargebacks AS (
  SELECT
    'CB1' AS chargeback_id,
    'P2' AS payment_id,
    600 AS amount_minor,
    NULL AS currency_code,
    NULL AS reason_code,
    NULL AS reason_family,
    NULL AS opened_at,
    NULL AS closed_at,
    'lost' AS outcome,
    NULL AS evidence_document_count,
    NULL AS evidence,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CB2',
    'P2',
    100,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'won',
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_gift_card_transactions AS (
  SELECT
    'G1' AS transaction_id,
    'GC1' AS gift_card_id,
    'O2' AS order_id,
    'REDEEM' AS transaction_type,
    -500 AS signed_amount_minor,
    NULL AS occurred_at,
    NULL AS channel,
    NULL AS terminal_id,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'G2',
    'GC1',
    'O2',
    'ISSUE',
    1000,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_order_payments_rollup AS (
  SELECT
    'O1' AS order_id,
    2000 AS card_captured_minor,
    0 AS wallet_captured_minor,
    2000 AS captured_minor,
    2000 AS refunded_minor,
    0 AS chargeback_minor,
    0 AS gift_card_tender_minor,
    0 AS net_collected_minor,
    1 AS failed_attempts
  UNION ALL
  SELECT
    'O2' AS order_id,
    0 AS card_captured_minor,
    1500 AS wallet_captured_minor,
    1500 AS captured_minor,
    0 AS refunded_minor,
    600 AS chargeback_minor,
    500 AS gift_card_tender_minor,
    1400 AS net_collected_minor,
    0 AS failed_attempts
),

__expected__fct_orders AS (
  SELECT
    'O1' AS order_id,
    1 AS order_number,
    2000 AS captured_minor,
    2000 AS refunded_minor,
    0 AS net_collected_minor,
    TRUE AS is_fully_refunded
  UNION ALL
  SELECT
    'O2' AS order_id,
    CAST(NULL AS INT) AS order_number,
    1500 AS captured_minor,
    0 AS refunded_minor,
    1400 AS net_collected_minor,
    FALSE AS is_fully_refunded
  UNION ALL
  SELECT
    'O3' AS order_id,
    CAST(NULL AS INT) AS order_number,
    0 AS captured_minor,
    0 AS refunded_minor,
    0 AS net_collected_minor,
    FALSE AS is_fully_refunded
),

__assert__fully_refunded_orders_collect_nothing AS (
  SELECT o.order_id
  FROM __ref("fct_orders") AS o
  WHERE
    o.is_fully_refunded
    AND o.net_collected_minor > 0
)

TEST (name "fct_orders__adds_sequence_and_collection_without_timelines");

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
    'C1',
    'EU',
    'EUR',
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
  UNION ALL
  SELECT
    'O3',
    'C2',
    'US',
    'USD',
    NULL,
    NULL,
    'CANCELLED',
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
    'O4',
    'C2',
    'US',
    'USD',
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
),

__ref__int_order_status_timeline AS (
  SELECT
    CAST(NULL AS VARCHAR) AS order_id,
    CAST(NULL AS INT) AS transition_count,
    CAST(NULL AS TIMESTAMP_TZ) AS first_paid_at,
    CAST(NULL AS TIMESTAMP_TZ) AS first_shipped_at,
    CAST(NULL AS TIMESTAMP_TZ) AS first_delivered_at,
    CAST(NULL AS TIMESTAMP_TZ) AS cancelled_at,
    CAST(NULL AS INT) AS minutes_to_pay,
    CAST(NULL AS DECIMAL(12, 2)) AS hours_paid_to_shipped,
    CAST(NULL AS VARCHAR) AS status_path,
    CAST(NULL AS BOOLEAN) AS has_regression,
    CAST(NULL AS VARCHAR) AS last_status,
    CAST(NULL AS VARCHAR) AS longest_status
  WHERE 1 = 0
),

__ref__int_order_payments_rollup AS (
  SELECT
    'O1' AS order_id,
    NULL AS card_captured_minor,
    NULL AS wallet_captured_minor,
    NULL AS bank_transfer_captured_minor,
    NULL AS other_captured_minor,
    1000 AS captured_minor,
    1000 AS refunded_minor,
    NULL AS chargeback_minor,
    NULL AS gift_card_tender_minor,
    0 AS net_collected_minor,
    NULL AS failed_attempts,
    NULL AS tender_methods
  UNION ALL
  SELECT
    'O3',
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    0,
    NULL,
    NULL,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O4',
    NULL,
    NULL,
    NULL,
    NULL,
    500,
    NULL,
    NULL,
    NULL,
    500,
    NULL,
    NULL
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
  UNION ALL
  SELECT
    'O4',
    'C2',
    NULL,
    NULL,
    2,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__fct_orders AS (
  SELECT
    'O1' AS order_id,
    1 AS order_number,
    TRUE AS is_first_order,
    CAST(NULL AS TIMESTAMP_TZ) AS first_paid_at,
    1000 AS captured_minor,
    1000 AS refunded_minor,
    0 AS net_collected_minor,
    TRUE AS is_fully_refunded
  UNION ALL
  SELECT
    'O2' AS order_id,
    CAST(NULL AS INT) AS order_number,
    FALSE AS is_first_order,
    CAST(NULL AS TIMESTAMP_TZ) AS first_paid_at,
    0 AS captured_minor,
    0 AS refunded_minor,
    0 AS net_collected_minor,
    FALSE AS is_fully_refunded
  UNION ALL
  SELECT
    'O3' AS order_id,
    CAST(NULL AS INT) AS order_number,
    FALSE AS is_first_order,
    CAST(NULL AS TIMESTAMP_TZ) AS first_paid_at,
    0 AS captured_minor,
    0 AS refunded_minor,
    0 AS net_collected_minor,
    FALSE AS is_fully_refunded
  UNION ALL
  SELECT
    'O4' AS order_id,
    2 AS order_number,
    FALSE AS is_first_order,
    CAST(NULL AS TIMESTAMP_TZ) AS first_paid_at,
    500 AS captured_minor,
    0 AS refunded_minor,
    500 AS net_collected_minor,
    FALSE AS is_fully_refunded
),

__assert__order_id_is_unique_and_present AS (
  SELECT t.order_id
  FROM __ref("fct_orders") AS t
  GROUP BY
    t.order_id
  HAVING
    COUNT(*) > 1
    OR t.order_id IS NULL
)

TEST (name "int_revenue_recognition_daily__recognises_revenue_on_regional_delivery_dates");

WITH __ref__int_orders_usd AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    'EU' AS region_code,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS amount,
    119.0::DECIMAL(18, 2) AS amount_usd,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    19.0::DECIMAL(18, 2) AS tax_amount_usd,
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
    NULL,
    'US',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    50.0::DECIMAL(18, 2),
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
    NULL,
    'EU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    70.0::DECIMAL(18, 2),
    NULL,
    NULL,
    0.0::DECIMAL(18, 2),
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
    NULL,
    'EU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    10.0::DECIMAL(18, 2),
    NULL,
    NULL,
    0.0::DECIMAL(18, 2),
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
    'O5',
    NULL,
    'EU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    40.0::DECIMAL(18, 2),
    NULL,
    NULL,
    0.0::DECIMAL(18, 2),
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
    NULL AS first_paid_at,
    NULL AS first_shipped_at,
    '2026-03-30 23:30:00 +00:00'::TIMESTAMP_TZ AS first_delivered_at,
    NULL AS cancelled_at,
    NULL AS minutes_to_pay,
    NULL AS hours_paid_to_shipped,
    NULL AS status_path,
    NULL AS has_regression,
    NULL AS last_status,
    NULL AS longest_status
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    '2026-03-31 02:00:00 +00:00'::TIMESTAMP_TZ,
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
    NULL,
    NULL,
    NULL,
    '2026-04-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O5',
    NULL,
    NULL,
    NULL,
    '2026-03-25 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_refunds_usd AS (
  SELECT
    'F1' AS refund_id,
    NULL AS payment_id,
    'O1' AS order_id,
    NULL AS currency_code,
    NULL AS refunded_at,
    '2026-03-31'::DATE AS refunded_date,
    NULL AS reason_category,
    NULL AS amount,
    20.0::DECIMAL(18, 2) AS amount_usd,
    NULL AS days_after_payment,
    NULL AS is_full_refund
  UNION ALL
  SELECT
    'F2',
    NULL,
    'O9',
    NULL,
    NULL,
    '2026-03-31'::DATE,
    NULL,
    NULL,
    5.0::DECIMAL(18, 2),
    NULL,
    NULL
),

__ref__int_subscription_mrr_daily AS (
  SELECT
    'SUB1:2026-03-31' AS subscription_day_key,
    NULL AS subscription_id,
    'C1' AS customer_id,
    '2026-03-31'::DATE AS calendar_date,
    36.5::DECIMAL(18, 4) AS mrr_usd,
    NULL AS is_first_day
  UNION ALL
  SELECT
    'SUB2:2026-03-31',
    NULL,
    'C2',
    '2026-03-31'::DATE,
    365.0::DECIMAL(18, 4),
    NULL
),

__ref__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    NULL AS email_normalised,
    NULL AS phone_normalised,
    NULL AS first_name,
    NULL AS last_name,
    'EU' AS region_code,
    NULL AS storefront_code,
    NULL AS created_at,
    NULL AS preferred_language,
    NULL AS marketing_opt_in,
    NULL AS consent_types,
    NULL AS birth_year,
    NULL AS preferences,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_revenue_recognition_daily AS (
  SELECT
    '2026-03-25:EU:product' AS recognition_key,
    40.0::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    40.0::DECIMAL(18, 2) AS month_to_date_usd,
    40.0::DECIMAL(18, 2) AS trailing_7d_usd,
    1.0::DECIMAL(9, 6) AS share_of_day
  UNION ALL
  SELECT
    '2026-03-30:US:product' AS recognition_key,
    50.0::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    50.0::DECIMAL(18, 2) AS month_to_date_usd,
    50.0::DECIMAL(18, 2) AS trailing_7d_usd,
    1.0::DECIMAL(9, 6) AS share_of_day
  UNION ALL
  SELECT
    '2026-03-31:EU:product' AS recognition_key,
    100.0::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    140.0::DECIMAL(18, 2) AS month_to_date_usd,
    140.0::DECIMAL(18, 2) AS trailing_7d_usd,
    1.231527::DECIMAL(9, 6) AS share_of_day
  UNION ALL
  SELECT
    '2026-03-31:EU:refund' AS recognition_key,
    -20.0::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    -20.0::DECIMAL(18, 2) AS month_to_date_usd,
    -20.0::DECIMAL(18, 2) AS trailing_7d_usd,
    -0.246305::DECIMAL(9, 6) AS share_of_day
  UNION ALL
  SELECT
    '2026-03-31:EU:subscription' AS recognition_key,
    1.2::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    1.2::DECIMAL(18, 2) AS month_to_date_usd,
    1.2::DECIMAL(18, 2) AS trailing_7d_usd,
    0.014778::DECIMAL(9, 6) AS share_of_day
  UNION ALL
  SELECT
    '2026-03-31:UNKNOWN:refund' AS recognition_key,
    -5.0::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    -5.0::DECIMAL(18, 2) AS month_to_date_usd,
    -5.0::DECIMAL(18, 2) AS trailing_7d_usd,
    -0.714286::DECIMAL(9, 6) AS share_of_day
  UNION ALL
  SELECT
    '2026-03-31:UNKNOWN:subscription' AS recognition_key,
    12.0::DECIMAL(18, 2) AS revenue_usd,
    1 AS document_count,
    12.0::DECIMAL(18, 2) AS month_to_date_usd,
    12.0::DECIMAL(18, 2) AS trailing_7d_usd,
    1.714286::DECIMAL(9, 6) AS share_of_day
)

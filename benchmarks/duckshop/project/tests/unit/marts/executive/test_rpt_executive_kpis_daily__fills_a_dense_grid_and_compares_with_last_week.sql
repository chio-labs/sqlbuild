TEST (name "rpt_executive_kpis_daily__fills_a_dense_grid_and_compares_with_last_week");

WITH __ref__dim_date AS (
  SELECT
    '2026-03-24'::DATE AS calendar_date,
    NULL AS day_of_week_iso,
    NULL AS day_name,
    NULL AS is_weekend,
    NULL AS iso_year,
    NULL AS iso_week,
    NULL AS month_start,
    NULL AS month_end,
    NULL AS quarter_label,
    NULL AS fiscal_year,
    NULL AS fiscal_quarter,
    NULL AS holiday_regions,
    NULL AS is_holiday_somewhere,
    NULL AS is_on_or_before_valuation
  UNION ALL
  SELECT
    '2026-03-31'::DATE,
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
    '2026-04-01'::DATE,
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

__ref__fct_orders AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    'EU' AS region_code,
    NULL AS placed_at,
    '2026-03-24'::DATE AS placed_date_local,
    'DELIVERED' AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS currency_code,
    NULL AS amount,
    100.0::NUMBER(18, 2) AS amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size,
    NULL AS order_number,
    TRUE AS is_first_order,
    NULL AS first_paid_at,
    NULL AS first_delivered_at,
    NULL AS hours_paid_to_shipped,
    NULL AS captured_minor,
    NULL AS refunded_minor,
    NULL AS net_collected_minor,
    NULL AS is_fully_refunded
  UNION ALL
  SELECT
    'O2',
    NULL,
    'EU',
    NULL,
    '2026-03-31'::DATE,
    'SHIPPED',
    NULL,
    NULL,
    NULL,
    NULL,
    150.0::NUMBER(18, 2),
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
    FALSE,
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
    '2026-03-31'::DATE,
    'CANCELLED',
    NULL,
    NULL,
    NULL,
    NULL,
    999.0::NUMBER(18, 2),
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
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__fct_refunds AS (
  SELECT
    CAST(NULL AS VARCHAR) AS refund_id,
    CAST(NULL AS VARCHAR) AS payment_id,
    CAST(NULL AS VARCHAR) AS order_id,
    CAST(NULL AS VARCHAR) AS currency_code,
    CAST(NULL AS NUMBER(38, 6)) AS amount,
    CAST(NULL AS NUMBER(18, 2)) AS amount_usd,
    CAST(NULL AS TIMESTAMP_TZ) AS refunded_at,
    CAST(NULL AS DATE) AS refunded_date,
    CAST(NULL AS VARCHAR) AS reason_category,
    CAST(NULL AS INT) AS days_after_payment,
    CAST(NULL AS BOOLEAN) AS is_full_refund
  WHERE 1 = 0
),

__ref__fct_web_sessions AS (
  SELECT
    CAST(NULL AS VARCHAR) AS session_id,
    CAST(NULL AS VARCHAR) AS anonymous_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS TIMESTAMP_NTZ) AS session_start_utc,
    CAST(NULL AS TIMESTAMP_NTZ) AS session_start_visitor_local,
    CAST(NULL AS INT) AS duration_seconds,
    CAST(NULL AS INT) AS page_view_count,
    CAST(NULL AS VARCHAR) AS landing_page_path,
    CAST(NULL AS VARCHAR) AS channel_code,
    CAST(NULL AS BOOLEAN) AS is_paid,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    CAST(NULL AS VARCHAR) AS first_touch_channel,
    CAST(NULL AS INT) AS touch_number,
    CAST(NULL AS BOOLEAN) AS is_bounce,
    CAST(NULL AS VARCHAR) AS funnel_stage,
    CAST(NULL AS BOOLEAN) AS converted,
    CAST(NULL AS INT) AS visitor_bucket
  WHERE 1 = 0
),

__ref__fct_support_tickets AS (
  SELECT
    CAST(NULL AS VARCHAR) AS ticket_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS VARCHAR) AS channel,
    CAST(NULL AS INT) AS priority,
    CAST(NULL AS VARCHAR) AS ticket_status,
    CAST(NULL AS VARCHAR) AS contact_reason,
    CAST(NULL AS TIMESTAMPNTZ) AS created_at_utc,
    CAST(NULL AS TIMESTAMPTZ) AS solved_at,
    CAST(NULL AS INT) AS minutes_to_first_response,
    CAST(NULL AS INT) AS business_minutes_to_response,
    CAST(NULL AS BOOLEAN) AS is_first_response_breached,
    CAST(NULL AS BOOLEAN) AS is_resolution_breached,
    CAST(NULL AS INT) AS comment_count,
    CAST(NULL AS INT) AS handoff_count,
    CAST(NULL AS VARCHAR) AS sentiment_label,
    CAST(NULL AS INT) AS ticket_number_for_customer,
    CAST(NULL AS BOOLEAN) AS is_repeat_contact_7d,
    CAST(NULL AS INT) AS csat_score,
    CAST(NULL AS TIMESTAMPNTZ) AS source_loaded_at
  WHERE 1 = 0
),

__ref__fct_shipments AS (
  SELECT CAST(NULL AS VARCHAR) AS shipment_id
  WHERE 1 = 0
),

__ref__dim_warehouses AS (
  SELECT
    CAST(NULL AS VARCHAR) AS warehouse_code,
    CAST(NULL AS VARCHAR) AS warehouse_name,
    CAST(NULL AS VARCHAR) AS country_code,
    CAST(NULL AS VARCHAR) AS region_code,
    CAST(NULL AS VARCHAR) AS iana_timezone,
    CAST(NULL AS DECIMAL(4, 2)) AS utc_offset_hours,
    CAST(NULL AS TIME) AS opens_local,
    CAST(NULL AS TIME) AS closes_local,
    CAST(NULL AS INT) AS opening_minutes,
    CAST(NULL AS BOOLEAN) AS supports_same_day,
    CAST(NULL AS BOOLEAN) AS supports_cold_chain,
    CAST(NULL AS INT) AS bin_count,
    CAST(NULL AS INT) AS units_on_hand,
    CAST(NULL AS DECIMAL(9, 4)) AS average_slot_utilisation,
    CAST(NULL AS TIMESTAMPNTZ) AS source_loaded_at
  WHERE 1 = 0
),

__ref__fct_campaign_spend AS (
  SELECT CAST(NULL AS VARCHAR) AS spend_id
  WHERE 1 = 0
),

__ref__fct_inventory_daily AS (
  SELECT CAST(NULL AS VARCHAR) AS stock_day_key
  WHERE 1 = 0
),

__ref__int_revenue_recognition_daily AS (
  SELECT
    CAST(NULL AS VARCHAR) AS recognition_key,
    CAST(NULL AS DATE) AS recognition_date,
    CAST(NULL AS VARCHAR) AS region_code,
    CAST(NULL AS VARCHAR) AS revenue_stream,
    CAST(NULL AS DECIMAL(18, 2)) AS revenue_usd,
    CAST(NULL AS INT) AS document_count,
    CAST(NULL AS DECIMAL(18, 2)) AS month_to_date_usd,
    CAST(NULL AS DECIMAL(18, 2)) AS trailing_7d_usd,
    CAST(NULL AS DECIMAL(9, 6)) AS share_of_day
  WHERE 1 = 0
),

__ref__fct_partner_orders AS (
  SELECT CAST(NULL AS VARCHAR) AS partner_order_key
  WHERE 1 = 0
),

__ref__int_chargeback_exposure AS (
  SELECT
    CAST(NULL AS VARCHAR) AS chargeback_id,
    CAST(NULL AS VARCHAR) AS payment_id,
    CAST(NULL AS VARCHAR) AS order_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS VARCHAR) AS payment_method,
    CAST(NULL AS VARCHAR) AS reason_code,
    CAST(NULL AS VARCHAR) AS reason_family,
    CAST(NULL AS TIMESTAMP_TZ) AS opened_at,
    CAST(NULL AS DATE) AS response_due_on,
    CAST(NULL AS VARCHAR) AS outcome,
    CAST(NULL AS DECIMAL(18, 2)) AS amount_usd,
    CAST(NULL AS DECIMAL(9, 6)) AS share_of_payment,
    CAST(NULL AS ARRAY) AS evidence_kinds,
    CAST(NULL AS BOOLEAN) AS has_delivery_proof,
    CAST(NULL AS INT) AS days_open,
    CAST(NULL AS BOOLEAN) AS is_overdue,
    CAST(NULL AS DECIMAL(18, 2)) AS at_risk_usd,
    CAST(NULL AS INT) AS prior_chargebacks_for_customer
  WHERE 1 = 0
),

__expected__rpt_executive_kpis_daily AS (
  SELECT
    '2026-03-24:EU:orders' AS kpi_key,
    'orders' AS business_area,
    1.0::DECIMAL(18, 4) AS metric_value,
    CAST(NULL AS DECIMAL(18, 4)) AS value_week_ago,
    CAST(NULL AS DECIMAL(12, 2)) AS week_over_week_pct,
    1.0::DECIMAL(18, 4) AS trailing_28d_average,
    CAST(NULL AS BOOLEAN) AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-31:EU:orders' AS kpi_key,
    'orders' AS business_area,
    1.0::DECIMAL(18, 4) AS metric_value,
    1.0::DECIMAL(18, 4) AS value_week_ago,
    0.0::DECIMAL(12, 2) AS week_over_week_pct,
    1.0::DECIMAL(18, 4) AS trailing_28d_average,
    TRUE AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-24:EU:revenue_usd' AS kpi_key,
    'orders' AS business_area,
    100.0::DECIMAL(18, 4) AS metric_value,
    CAST(NULL AS DECIMAL(18, 4)) AS value_week_ago,
    CAST(NULL AS DECIMAL(12, 2)) AS week_over_week_pct,
    100.0::DECIMAL(18, 4) AS trailing_28d_average,
    CAST(NULL AS BOOLEAN) AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-31:EU:revenue_usd' AS kpi_key,
    'orders' AS business_area,
    150.0::DECIMAL(18, 4) AS metric_value,
    100.0::DECIMAL(18, 4) AS value_week_ago,
    50.0::DECIMAL(12, 2) AS week_over_week_pct,
    125.0::DECIMAL(18, 4) AS trailing_28d_average,
    TRUE AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-24:EU:average_order_usd' AS kpi_key,
    'orders' AS business_area,
    100.0::DECIMAL(18, 4) AS metric_value,
    CAST(NULL AS DECIMAL(18, 4)) AS value_week_ago,
    CAST(NULL AS DECIMAL(12, 2)) AS week_over_week_pct,
    100.0::DECIMAL(18, 4) AS trailing_28d_average,
    CAST(NULL AS BOOLEAN) AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-31:EU:average_order_usd' AS kpi_key,
    'orders' AS business_area,
    150.0::DECIMAL(18, 4) AS metric_value,
    100.0::DECIMAL(18, 4) AS value_week_ago,
    50.0::DECIMAL(12, 2) AS week_over_week_pct,
    125.0::DECIMAL(18, 4) AS trailing_28d_average,
    TRUE AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-24:EU:new_customers' AS kpi_key,
    'customers' AS business_area,
    1.0::DECIMAL(18, 4) AS metric_value,
    CAST(NULL AS DECIMAL(18, 4)) AS value_week_ago,
    CAST(NULL AS DECIMAL(12, 2)) AS week_over_week_pct,
    1.0::DECIMAL(18, 4) AS trailing_28d_average,
    CAST(NULL AS BOOLEAN) AS is_favourable_change
  UNION ALL
  SELECT
    '2026-03-31:EU:new_customers' AS kpi_key,
    'customers' AS business_area,
    0.0::DECIMAL(18, 4) AS metric_value,
    1.0::DECIMAL(18, 4) AS value_week_ago,
    -100.0::DECIMAL(12, 2) AS week_over_week_pct,
    0.5::DECIMAL(18, 4) AS trailing_28d_average,
    FALSE AS is_favourable_change
),

__assert__kpi_key_is_unique_and_present AS (
  SELECT t.kpi_key
  FROM __ref("rpt_executive_kpis_daily") AS t
  GROUP BY
    t.kpi_key
  HAVING
    COUNT(*) > 1
    OR t.kpi_key IS NULL
)
